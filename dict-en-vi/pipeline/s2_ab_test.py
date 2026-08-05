#!/usr/bin/env python3
"""Run the same entries through two providers and put the results side by side.

The question this answers is narrow and worth answering with data rather than
opinion: does the cheaper model produce Vietnamese a reviewer would keep?

The arithmetic that makes it worth measuring — roughly 13,400 entries get read
by a human under the plan's review tiers (§7.2), so the price gap between two
providers buys only a few seconds of extra review time per reviewed entry.
Whether the cheaper model stays inside that budget is not something anyone can
guess from the outside.

    uv run python s2_ab_test.py --limit 100 --dry-run
    uv run python s2_ab_test.py --limit 100
    uv run python s2_ab_test.py --limit 100 --report-only   # re-read caches
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import _paths

from core.llm import Cache, Job, get_provider
from core.llm.prompts import EN_VI_SENSES_SCHEMA, en_vi_system, en_vi_user
from core.schema import Entry

# Import the selection logic rather than duplicating it, so the A/B sample is
# exactly the population the real run would have translated first.
from s2_llm import load_candidates, select


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in", dest="inp", type=Path, default=None)
    parser.add_argument("--providers", default="claude,ark",
                        help="comma-separated provider names")
    parser.add_argument("--tier", type=int, action="append", default=None)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--out", type=Path, default=None,
                        help="side-by-side comparison (markdown)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-only", action="store_true",
                        help="skip the API calls; compare whatever the caches hold")
    args = parser.parse_args(argv)

    work = _paths.ensure_work()
    inp = args.inp or work / "s2a-matched.jsonl"
    out = args.out or work / "ab-comparison.md"
    _paths.require(inp, "make stage2-match")

    entries = load_candidates(inp)
    tiers = set(args.tier) if args.tier else {1}
    sample = select(entries, tiers=tiers, limit=args.limit)
    if not sample:
        print("no candidates.")
        return 1

    by_id = {e.id: e for e in sample}
    system = en_vi_system(EN_VI_SENSES_SCHEMA)
    jobs = [
        Job(id=e.id, content=en_vi_user(e.headword, e.pos, e.pron, e.gloss_en))
        for e in sample
    ]

    names = [n.strip() for n in args.providers.split(",") if n.strip()]
    print(f"A/B over {len(sample):,} entries (tier {sorted(tiers)}): {', '.join(names)}\n")

    caches: dict[str, Cache] = {}
    reports = {}
    for name in names:
        provider = get_provider(name)
        cache = Cache(work / f"llm-cache-{name}.jsonl")
        caches[name] = cache

        print(f"-- {name}: {provider.describe_pricing()}")
        if args.report_only:
            have = sum(1 for j in jobs if j.id in cache)
            print(f"   cached: {have:,}/{len(jobs):,}")
            continue

        print(f"   forecast ~${provider.forecast_usd(jobs, system):.4f}")
        report = provider.translate(
            jobs, system=system, schema=EN_VI_SENSES_SCHEMA, cache=cache,
            dry_run=args.dry_run,
        )
        if not args.dry_run:
            reports[name] = report
            print(report.describe())
        print()

    if args.dry_run:
        return 0

    # -- comparison ------------------------------------------------------
    lines = [
        "# A/B: Vietnamese sense quality",
        "",
        f"{len(sample)} entries, tier {sorted(tiers)}. "
        "Same prompt, same input, same schema — only the model differs.",
        "",
    ]

    if reports:
        lines += ["## Cost", "", "| provider | model | collected | errors | cost |",
                  "|---|---|---:|---:|---:|"]
        for name, report in reports.items():
            lines.append(
                f"| {name} | `{report.model}` | {report.collected:,} |"
                f" {len(report.errors):,} | ${report.cost_usd:.4f} |"
            )
        lines.append("")
        costs = {n: r.cost_usd for n, r in reports.items() if r.cost_usd > 0}
        if len(costs) == 2:
            hi, lo = max(costs.values()), min(costs.values())
            if lo > 0:
                lines += [f"Ratio: **{hi / lo:.1f}x**.", ""]

    lines += ["## Senses", "",
              "| # | headword | pos | " + " | ".join(names) + " |",
              "|---|---|---|" + "---|" * len(names)]

    disagreements = 0
    for i, entry in enumerate(sample, 1):
        row = [str(i), f"**{entry.headword}**", entry.pos]
        rendered = []
        for name in names:
            record = caches[name].get(entry.id)
            if not record:
                rendered.append("—")
                continue
            senses = record.get("senses_vi") or []
            conf = record.get("confidence", "")
            mark = {"high": "", "medium": " ·", "low": " ⚠"}.get(conf, "")
            rendered.append("; ".join(senses).replace("|", "\\|") + mark)
        if len(set(rendered)) > 1:
            disagreements += 1
        lines.append("| " + " | ".join(row + rendered) + " |")

    lines += [
        "",
        f"Rows where the providers differ: **{disagreements}/{len(sample)}**.",
        "",
        "`·` medium confidence, `⚠` low confidence — self-reported by the model.",
        "",
        "## How to read this",
        "",
        "Disagreement is not error: two different but correct renderings are",
        "common in a dictionary. Read the differing rows and count how many you",
        "would have to *fix*, not how many differ. That count, divided by the",
        "sample size, is the extra review burden the cheaper model imposes —",
        "the only number that decides whether its lower price is real.",
    ]

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote comparison -> {out}")
    print(f"  providers differ on {disagreements}/{len(sample)} entries")

    # Console preview so the decision doesn't require opening a file.
    print("\nfirst 12 rows:")
    for entry in sample[:12]:
        print(f"  {entry.headword:14}{entry.pos:5}", end="")
        for name in names:
            record = caches[name].get(entry.id)
            text = "; ".join((record or {}).get("senses_vi") or []) or "—"
            print(f"{name}: {text[:44]:46}", end="")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
