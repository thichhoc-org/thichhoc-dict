#!/usr/bin/env python3
"""Measure the Ark batch endpoint: does it accept our requests, and how fast?

Batch is a synchronous API in front of a queue, so a client sees nothing at all
while a request waits its turn — there is no "accepted" acknowledgement to
check. The only honest way to verify it works is to fire several concurrently
and watch completions land, which is what this does: one line per response,
with elapsed seconds and the request id the console can be searched by.

Run it in the background and tail the log; do not wait on it interactively.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.llm.prompts import en_vi_system, en_vi_user
from core.llm.prompts import EN_VI_SENSES_SCHEMA

_print_lock = threading.Lock()


def log(message: str) -> None:
    with _print_lock:
        print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=os.environ.get("ARK_BATCH_ENDPOINT", ""),
                        help="ep-bi-... batch inference endpoint id")
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=24 * 3600,
                        help="BytePlus's own example uses 24h; batch queues by design")
    parser.add_argument("--retries", type=int, default=0,
                        help="429 ServerOverloaded is retryable; the SDK backs off for us")
    parser.add_argument("--sample", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data/work/ab-sample.jsonl")
    args = parser.parse_args(argv)

    if not args.endpoint:
        raise SystemExit("pass --endpoint ep-bi-... (or set ARK_BATCH_ENDPOINT)")
    key = os.environ.get("ARK_API_KEY")
    if not key:
        raise SystemExit("set ARK_API_KEY")

    from openai import OpenAI

    # The batch surface is the online one with /batch appended; same request
    # shape, different queue and different price.
    client = OpenAI(
        api_key=key,
        base_url="https://ark.ap-southeast.bytepluses.com/api/v3/batch",
        timeout=args.timeout,
        max_retries=args.retries,
    )

    entries = [json.loads(l) for l in args.sample.open(encoding="utf-8") if l.strip()][: args.n]
    system = en_vi_system(EN_VI_SENSES_SCHEMA) + ArkProvider._shape(EN_VI_SENSES_SCHEMA, False)
    log(f"firing {len(entries)} requests at {args.endpoint}, {args.concurrency} concurrent")
    started = time.monotonic()

    def one(entry: dict) -> tuple[str, float, str]:
        t0 = time.monotonic()
        try:
            raw = client.chat.completions.with_raw_response.create(
                model=args.endpoint,
                max_tokens=512,
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "disabled"}},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": en_vi_user(
                        entry["headword"], entry["pos"], entry.get("pron", ""),
                        entry.get("gloss_en", []))},
                ],
            )
            elapsed = time.monotonic() - t0
            # x-request-id is what the console indexes on, so log it even on success.
            rid = raw.headers.get("x-request-id", "")
            completion = raw.parse()
            text = (completion.choices[0].message.content or "").strip()
            usage = completion.usage
            log(f"  OK   {entry['headword']:16} {elapsed:7.1f}s  "
                f"in={usage.prompt_tokens:5} out={usage.completion_tokens:4}  "
                f"rid={rid[:24]}  {text[:60]}")
            return entry["headword"], elapsed, ""
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            log(f"  ERR  {entry['headword']:16} {elapsed:7.1f}s  {type(exc).__name__}: {str(exc)[:120]}")
            return entry["headword"], elapsed, str(exc)[:120]

    times: list[float] = []
    errors = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for future in as_completed([pool.submit(one, e) for e in entries]):
            _, elapsed, err = future.result()
            times.append(elapsed)
            errors += bool(err)

    wall = time.monotonic() - started
    ok = len(times) - errors
    log("")
    log(f"done: {ok}/{len(entries)} ok, {errors} errors, wall {wall:.1f}s")
    if times:
        ordered = sorted(times)
        log(f"per-request latency: min {ordered[0]:.1f}s  "
            f"median {ordered[len(ordered) // 2]:.1f}s  max {ordered[-1]:.1f}s")
    if ok:
        log(f"throughput at concurrency {args.concurrency}: {ok / wall * 60:.1f} req/min")
        # The number that decides whether batch is usable for the real run.
        log(f"  => 7,200 grouped requests would take ~{7200 / (ok / wall) / 3600:.1f}h")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
