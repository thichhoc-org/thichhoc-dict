#!/usr/bin/env python3
"""Draw a stratified sample of entries for quality comparison.

The first sample this project drew was taken by sorting tier 1 by frequency
and slicing the top — which returned `in`, `it`, `as`, `at`, `be`: function
words and WordNet's two-letter chemical symbols. Fine for checking that the
plumbing works, useless for judging translation quality, because nobody stops
mid-novel to look up "as".

So the filters here are all about getting words a reader would actually pause
on: long enough to be a content word, below the frequency ceiling where
function words live, and spread across tiers rather than piled at the top.

    uv run python qa/make_sample.py --n 100 --exclude data/work/ab-sample.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.schema import Entry

#: Function words cluster above this Zipf value. Excluding them is the single
#: change that turned the sample from unusable to informative.
FREQ_CEILING = 5.6

#: Below this, headwords are mostly abbreviations and chemical symbols.
MIN_LENGTH = 4

#: (tier, share) — weighted toward the tiers a reader meets most, while still
#: reaching into the long tail where translation is hardest.
STRATA = ((1, 0.4), (2, 0.4), (3, 0.2))


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in", dest="inp", type=Path,
                        default=Path("dict-en-vi/data/work/s2a-matched.jsonl"))
    parser.add_argument("--out", type=Path,
                        default=Path("dict-en-vi/data/work/sample.jsonl"))
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260804,
                        help="fixed so a sample can be reproduced exactly")
    parser.add_argument("--exclude", type=Path, action="append", default=[],
                        help="sample files whose entries must not be drawn again")
    parser.add_argument("--untranslated-only", action="store_true", default=True)
    args = parser.parse_args(argv)

    seen: set[str] = set()
    for path in args.exclude:
        if path.exists():
            seen |= {e["id"] for e in load(path)}
    if seen:
        print(f"excluding {len(seen):,} already-sampled entries")

    pool = [
        e for e in load(args.inp)
        if e["id"] not in seen
        and e.get("gloss_en")
        and (not args.untranslated_only or not e.get("senses_vi"))
        and len(e["headword"]) >= MIN_LENGTH
        and e["headword"].isalpha()
        and e.get("freq", 0) < FREQ_CEILING
    ]
    by_tier: dict[int, list[dict]] = {}
    for e in pool:
        by_tier.setdefault(e["freq_tier"], []).append(e)
    print(f"pool: {len(pool):,} candidates "
          + ", ".join(f"t{t}={len(v):,}" for t, v in sorted(by_tier.items())))

    rng = random.Random(args.seed)
    sample: list[dict] = []
    for tier, share in STRATA:
        want = round(args.n * share)
        available = by_tier.get(tier, [])
        if len(available) < want:
            print(f"  tier {tier}: only {len(available)} available, wanted {want}")
            want = len(available)
        sample += rng.sample(available, want)

    sample.sort(key=lambda e: (e["freq_tier"], -e.get("freq", 0), e["headword"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in sample), encoding="utf-8")

    multi = sum(1 for e in sample if len(e["gloss_en"]) > 1)
    print(f"\nwrote {len(sample)} entries -> {args.out}")
    print(f"  {multi} have more than one gloss — those are where providers diverge")
    for tier in sorted({e["freq_tier"] for e in sample}):
        n = sum(1 for e in sample if e["freq_tier"] == tier)
        print(f"  tier {tier}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
