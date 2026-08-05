#!/usr/bin/env python3
"""Stage 1e — re-apply the headword policy to an existing entry store.

Tier assignment and the junk-headword filter live in ``s1_lemmas.py``, but that
script rebuilds the store from WordNet and so produces entries with no
``senses_vi``. Once Stage 2 has run, re-running it would throw away everything
that was paid for. This applies the same two rules to the store in place:

    make stage1     rebuilds from source   — destroys senses
    make retier     re-applies the policy  — keeps senses

Both read their rules from ``s1_lemmas``, so the two can only agree.

Frequencies are recomputed rather than carried over, because a tier is a rank
within a population and dropping headwords changes the population.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import _paths
from _paths import ENTRIES_DIR

from core.schema import Entry
from core.store import iter_entries, write_shards
from s1_lemmas import assign_tiers, frequency_table, is_junk_headword


def retier(entries: list[Entry]) -> tuple[list[Entry], dict]:
    """Drop unusable headwords and recompute freq/freq_tier. Senses untouched."""
    kept = [e for e in entries if not is_junk_headword(e.headword)]
    dropped = [e for e in entries if is_junk_headword(e.headword)]

    freqs = frequency_table({e.headword for e in kept})
    tiers = assign_tiers(freqs)

    moved = Counter()
    for entry in kept:
        was = entry.freq_tier
        entry.freq = freqs.get(entry.headword, 0.0)
        entry.freq_tier = tiers.get(entry.headword, 5)
        if entry.freq_tier != was:
            moved[(was, entry.freq_tier)] += 1

    stats = {
        "dropped_entries": len(dropped),
        "dropped_headwords": len({e.headword for e in dropped}),
        "dropped_translated": sum(1 for e in dropped if e.senses_vi),
        "moved": moved,
        "kept": kept,
    }
    return kept, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entries", type=Path, default=ENTRIES_DIR)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change and write nothing")
    args = parser.parse_args(argv)

    entries = list(iter_entries(args.entries))
    print(f"read {len(entries):,} entries from {args.entries}")
    before_t1 = sum(1 for e in entries if e.freq_tier == 1)
    translated = sum(1 for e in entries if e.senses_vi)

    kept, stats = retier(entries)

    print(f"\ndropped {stats['dropped_entries']:,} entries on "
          f"{stats['dropped_headwords']:,} unusable headwords"
          + (f" ({stats['dropped_translated']:,} of them already translated)"
             if stats["dropped_translated"] else ""))

    after_t1 = sum(1 for e in kept if e.freq_tier == 1)
    t1_single = sum(1 for e in kept if e.freq_tier == 1 and " " not in e.headword)
    print(f"\ntier 1: {before_t1:,} entries -> {after_t1:,}"
          f" ({t1_single:,} single-word, {after_t1 - t1_single:,} phrases)")
    print(f"tier changes: {sum(stats['moved'].values()):,} entries moved")
    for (a, b), n in sorted(stats["moved"].items()):
        print(f"    tier {a} -> {b}: {n:,}")

    kept_translated = sum(1 for e in kept if e.senses_vi)
    print(f"\nVietnamese senses: {translated:,} before, {kept_translated:,} after"
          f" ({translated - kept_translated:,} lost with dropped headwords)")

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    written = write_shards(args.entries, kept)
    print(f"\nwrote {sum(written.values()):,} entries across {len(written)} shards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
