#!/usr/bin/env python3
"""Coverage report for an entry store (plan §7).

Two audiences. Internally this is the Stage 2 budget estimate: the count of
entries still missing ``senses_vi``, tier by tier, is exactly what we are about
to spend LLM money on. Externally it is the number we publish — pain point #2
is dictionaries that claim to be "Full" and turn out not to be, so we state
coverage plainly instead of a marketing adjective.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.store import iter_entries  # noqa: E402

TIER_LABEL = {
    1: "tier 1  (top 5k, review 100%)",
    2: "tier 2  (to 20k)",
    3: "tier 3  (to 50k)",
    4: "tier 4  (rest, known freq)",
    5: "tier 5  (no freq data)",
}


def collect(entries_dir: Path) -> dict:
    total = 0
    headwords: set[str] = set()
    forms: set[str] = set()
    by_pos: Counter[str] = Counter()
    by_tier: Counter[int] = Counter()
    with_pron = with_infl = with_senses = with_gloss = reviewed = 0
    infl_total = 0
    senses_by_tier: dict[int, int] = defaultdict(int)

    for entry in iter_entries(entries_dir):
        total += 1
        headwords.add(entry.headword)
        forms.update(f.lower() for f in entry.lookup_forms)
        by_pos[entry.pos] += 1
        by_tier[entry.freq_tier] += 1
        with_pron += bool(entry.pron)
        with_gloss += bool(entry.gloss_en)
        reviewed += bool(entry.reviewed)
        if entry.inflections:
            with_infl += 1
            infl_total += len(entry.inflections)
        if entry.senses_vi:
            with_senses += 1
            senses_by_tier[entry.freq_tier] += 1

    return {
        "entries": total,
        "headwords": len(headwords),
        "lookup_forms": len(forms),
        "by_pos": dict(by_pos.most_common()),
        "by_tier": {t: by_tier[t] for t in sorted(by_tier)},
        "with_pron": with_pron,
        "with_inflections": with_infl,
        "inflected_forms": infl_total,
        "with_gloss_en": with_gloss,
        "with_senses_vi": with_senses,
        "senses_by_tier": {t: senses_by_tier.get(t, 0) for t in sorted(by_tier)},
        "reviewed": reviewed,
    }


def _pct(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:5.1f}%" if whole else "    -"


def render(stats: dict) -> str:
    total = stats["entries"]
    lines = [
        "=" * 62,
        f"  {stats['entries']:>9,} entries",
        f"  {stats['headwords']:>9,} distinct headwords",
        f"  {stats['lookup_forms']:>9,} distinct lookup forms (headwords + inflections)",
        "=" * 62,
        "",
        "By part of speech",
    ]
    for pos, count in stats["by_pos"].items():
        lines.append(f"  {pos:<6} {count:>9,}  {_pct(count, total)}")

    lines += ["", "By frequency tier"]
    for tier, count in stats["by_tier"].items():
        label = TIER_LABEL.get(tier, f"tier {tier}")
        lines.append(f"  {label:<32} {count:>9,}  {_pct(count, total)}")

    lines += ["", "Stage 1 — skeleton coverage"]
    for label, key in [
        ("pronunciation (IPA)", "with_pron"),
        ("inflected forms", "with_inflections"),
        ("English gloss", "with_gloss_en"),
    ]:
        lines.append(f"  {label:<32} {stats[key]:>9,}  {_pct(stats[key], total)}")
    if stats["with_inflections"]:
        avg = stats["inflected_forms"] / stats["with_inflections"]
        lines.append(f"  {'avg forms per inflected entry':<32} {avg:>9.2f}")

    lines += ["", "Stage 2 — meaning coverage"]
    lines.append(f"  {'Vietnamese senses':<32} {stats['with_senses_vi']:>9,}  {_pct(stats['with_senses_vi'], total)}")
    lines.append(f"  {'reviewed':<32} {stats['reviewed']:>9,}  {_pct(stats['reviewed'], total)}")

    remaining = total - stats["with_senses_vi"]
    lines += ["", f"Remaining for Stage 2: {remaining:,} entries"]
    for tier, count in stats["by_tier"].items():
        done = stats["senses_by_tier"].get(tier, 0)
        left = count - done
        if left:
            lines.append(f"  tier {tier}: {left:>9,} to translate")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "entries",
        nargs="?",
        type=Path,
        default=Path("dict-en-vi/data/entries"),
        help="entry store directory",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    if not args.entries.exists():
        raise SystemExit(f"no such directory: {args.entries}")

    stats = collect(args.entries)
    if args.json:
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    else:
        print(render(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
