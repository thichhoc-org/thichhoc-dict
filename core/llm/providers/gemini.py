"""Google Gemini provider, via the Generative Language REST API.

The reason to carry this alongside Ark is not price — the two overlap almost
exactly at the cheap end — but **real schema enforcement**. Gemini accepts a
`responseSchema` the server honours, so the client-side validate-and-retry
loop the Ark provider needs is dead weight here. That check still runs, but on
this provider it should never fire; if it does, that is the finding.

Auth is an API key in the `x-goog-api-key` header — not a Bearer token, which
the endpoint rejects with a 401 that reads like a bad key. Keys come from
aistudio.google.com and need no project or billing setup.

Raw HTTP rather than the SDK: the request shape is three fields, the pipeline
already has no Google dependency, and the schema dialect is the only part
worth getting exactly right.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from ..types import Cache, Job, RunReport, Usage, validate_payload
from .base import Provider

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash-lite"

#: (input, cache-hit input, output) USD per million tokens, from
#: ai.google.dev/gemini-api/docs/pricing. Batch halves input and output.
#: Flash tiers carry a free tier with rate limits rather than token charges,
#: so a small run often bills nothing at all.
PRICING: dict[str, tuple[float, float, float]] = {
    "gemini-2.5-flash-lite": (0.10, 0.025, 0.40),
    "gemini-2.5-flash": (0.30, 0.075, 2.50),
    "gemini-3.1-flash-lite": (0.25, 0.0625, 1.50),
    "gemini-3.5-flash-lite": (0.30, 0.075, 2.50),
    "gemini-3.5-flash": (1.50, 0.15, 9.00),
    "gemini-3.6-flash": (1.50, 0.15, 7.50),
    "gemini-2.5-pro": (1.25, 0.3125, 10.00),
}

BATCH_DISCOUNT = 0.5


def _to_gemini_schema(schema: dict) -> dict:
    """Translate our JSON Schema into Gemini's OpenAPI-flavoured dialect.

    Gemini wants upper-case type names and rejects `additionalProperties`
    outright, so the schema cannot simply be forwarded. Property order is
    preserved via `propertyOrdering`, which is what makes its output stable.
    """
    def convert(node: dict) -> dict:
        kind = node.get("type", "object")
        out: dict[str, Any] = {"type": kind.upper()}
        if "description" in node:
            out["description"] = node["description"]
        if kind == "object":
            props = node.get("properties", {})
            out["properties"] = {k: convert(v) for k, v in props.items()}
            if node.get("required"):
                out["required"] = list(node["required"])
            out["propertyOrdering"] = list(props)
        elif kind == "array":
            out["items"] = convert(node.get("items", {"type": "string"}))
            for src, dst in (("minItems", "minItems"), ("maxItems", "maxItems")):
                if src in node:
                    out[dst] = str(node[src])
        elif kind == "string" and "enum" in node:
            out["enum"] = list(node["enum"])
        return out

    return convert(schema)


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(
        self,
        model: str | None = None,
        *,
        max_tokens: int = 1024,
        concurrency: int = 8,
        retries: int = 1,
        group_size: int = 1,
        batch: bool = False,
    ) -> None:
        super().__init__(model or DEFAULT_MODEL)
        self.max_tokens = max_tokens
        self.concurrency = concurrency
        self.retries = retries
        # Same lever as Ark: the system prompt is ~920 tokens and is resent
        # with every request, so packing N entries per call amortises it.
        self.group_size = max(1, group_size)
        self.batch = batch
        self.group_fallbacks = 0

    # -- pricing ----------------------------------------------------------

    def cost_usd(self, usage: Usage) -> float:
        prices = PRICING.get(self.model)
        if prices is None:
            return 0.0
        price_in, price_cache, price_out = prices
        discount = BATCH_DISCOUNT if self.batch else 1.0
        return (
            (usage.input_tokens + usage.cache_write_tokens) * price_in * discount
            + usage.cache_read_tokens * price_cache
            + usage.output_tokens * price_out * discount
        ) / 1_000_000

    def describe_pricing(self) -> str:
        prices = PRICING.get(self.model)
        if prices is None:
            return f"{self.model}: price not configured — tokens only"
        price_in, _, price_out = prices
        d = BATCH_DISCOUNT if self.batch else 1.0
        note = " batch -50%" if self.batch else " (free tier may apply)"
        return f"{self.model}: in ${price_in * d:g} / out ${price_out * d:g} per M{note}"

    # -- plumbing ---------------------------------------------------------

    def _key(self) -> str:
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise SystemExit(
                "set GEMINI_API_KEY — get one at https://aistudio.google.com\n"
                "(no GCP project or billing needed)"
            )
        return key

    def _messages(self, group: list[Job], system: str) -> tuple[str, str]:
        """Returns (system instruction, user text)."""
        if len(group) == 1:
            return system, group[0].content
        packed = [{"id": j.id, **json.loads(j.content)} for j in group]
        grouped_note = (
            "\n\n## Input and output format\n\n"
            "The user turn is a JSON array of entries, each with an `id`. Treat "
            "every entry independently. Reply with one object per input entry, "
            "in the same order, each echoing the `id` it answers."
        )
        return system + grouped_note, json.dumps(packed, ensure_ascii=False)

    def _schema_for(self, group: list[Job], schema: dict) -> dict:
        single = _to_gemini_schema(schema)
        if len(group) == 1:
            return single
        # Grouped mode returns an array of {id, ...schema}; the id is added
        # here rather than in the shared schema so single mode stays clean.
        item = dict(single)
        item["properties"] = {"id": {"type": "STRING"}, **single["properties"]}
        item["required"] = ["id", *single.get("required", [])]
        item["propertyOrdering"] = ["id", *single.get("propertyOrdering", [])]
        return {"type": "ARRAY", "items": item}

    def _post(self, body: dict) -> dict:
        url = f"{API_ROOT}/{self.model}:generateContent"
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self._key()},
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.load(resp)

    def _unpack(self, group: list[Job], payload: object, schema: dict
                ) -> tuple[dict[str, dict], str]:
        if len(group) == 1:
            problem = validate_payload(payload, schema)
            return ({} if problem else {group[0].id: payload}), problem

        if not isinstance(payload, list):
            return {}, "grouped reply is not a list"
        wanted = {j.id for j in group}
        out: dict[str, dict] = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            entry_id = item.get("id")
            if entry_id not in wanted:
                continue
            body = {k: v for k, v in item.items() if k != "id"}
            if not validate_payload(body, schema):
                out[entry_id] = body
        missing = len(wanted) - len(out)
        return out, f"{missing} of {len(wanted)} entries missing or invalid" if missing else ""

    def _call(self, group: list[Job], system: str, schema: dict
              ) -> tuple[dict[str, dict], Usage, str]:
        usage = Usage()
        results: dict[str, dict] = {}
        last_error = ""

        system_text, user_text = self._messages(group, system)
        body = {
            "systemInstruction": {"parts": [{"text": system_text}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": self._schema_for(group, schema),
                "maxOutputTokens": self.max_tokens * max(1, len(group)),
                # Flash tiers think by default; for translating a supplied
                # gloss that is spend without a return.
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }

        for attempt in range(self.retries + 1):
            try:
                data = self._post(body)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:200]
                if exc.code == 429:
                    last_error = f"rate limited (attempt {attempt + 1})"
                    continue
                last_error = f"http {exc.code}: {detail}"
                continue
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"[:180]
                continue

            meta = data.get("usageMetadata") or {}
            cached = meta.get("cachedContentTokenCount", 0) or 0
            usage.add(Usage(
                input_tokens=max((meta.get("promptTokenCount", 0) or 0) - cached, 0),
                output_tokens=meta.get("candidatesTokenCount", 0) or 0,
                cache_read_tokens=cached,
            ))

            candidates = data.get("candidates") or []
            if not candidates:
                last_error = f"no candidate ({data.get('promptFeedback', '')})"[:150]
                continue
            parts = candidates[0].get("content", {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                last_error = f"unparseable (attempt {attempt + 1})"
                continue

            found, problem = self._unpack(group, payload, schema)
            results.update(found)
            if problem:
                last_error = f"{problem} (attempt {attempt + 1})"
                continue
            return results, usage, ""

        return results, usage, last_error or "failed"

    # -- run --------------------------------------------------------------

    def translate(
        self,
        jobs: list[Job],
        *,
        system: str,
        schema: dict,
        cache: Cache,
        on_result: Callable[[str, dict], None] | None = None,
        dry_run: bool = False,
    ) -> RunReport:
        report = RunReport(provider=self.name, model=self.model)
        pending = cache.missing(jobs)
        if not pending:
            return report

        if dry_run:
            system_text, user_text = self._messages(pending[: self.group_size], system)
            print(json.dumps({
                "url": f"{API_ROOT}/{self.model}:generateContent",
                "systemInstruction": system_text[:300] + " ...",
                "contents": user_text[:300],
                "responseSchema": self._schema_for(pending[: self.group_size], schema),
            }, ensure_ascii=False, indent=2)[:1400])
            print(f"\n(dry run — would send {len(pending):,} entr(y/ies))")
            return report

        groups = [pending[i : i + self.group_size]
                  for i in range(0, len(pending), self.group_size)]
        if self.group_size > 1:
            print(f"    {len(pending):,} entries in {len(groups):,} request(s)"
                  f" of up to {self.group_size}")

        stragglers = self._dispatch(groups, system, schema, cache, on_result, report)
        if stragglers:
            self.group_fallbacks = len(stragglers)
            print(f"    retrying {len(stragglers):,} entr(y/ies) individually")
            self._dispatch([[j] for j in stragglers], system, schema,
                           cache, on_result, report)

        report.cost_usd = self.cost_usd(report.usage)
        return report

    def _dispatch(self, groups, system, schema, cache, on_result, report) -> list[Job]:
        stragglers: list[Job] = []
        done = 0
        total = sum(len(g) for g in groups)
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {pool.submit(self._call, g, system, schema): g for g in groups}
            for future in as_completed(futures):
                group = futures[future]
                results, usage, error = future.result()
                report.usage.add(usage)
                done += len(group)
                if done % 25 < len(group) or done >= total:
                    print(f"    {done:,}/{total:,}")
                for job in group:
                    payload = results.get(job.id)
                    if payload is None:
                        if len(group) > 1:
                            stragglers.append(job)
                        else:
                            report.errors[job.id] = error or "no result"
                        continue
                    cache.put(job.id, payload)
                    if on_result:
                        on_result(job.id, payload)
                    report.collected += 1
        return stragglers


__all__ = ["GeminiProvider", "DEFAULT_MODEL", "PRICING"]
