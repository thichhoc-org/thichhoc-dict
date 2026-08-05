#!/usr/bin/env python3
"""Stage 1d — apply overrides, validate, and write the sharded entry store.

This is the end of Stage 1: after this the corpus is a set of reviewable JSONL
files in git, and every later stage (and every device build) reads from there.

Validation is fatal here on purpose. A malformed entry that reaches a builder
becomes a broken lookup on somebody's Kindle, and the plan's release criteria
(§7.1) put schema validation before everything else.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import _paths
from _paths import ENTRIES_DIR, OVERRIDES

from core.schema import Entry, validate_all
from core.store import apply_overrides, write_shards


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="inp", type=Path, default=None)
    parser.add_argument("--entries", type=Path, default=ENTRIES_DIR)
    parser.add_argument("--overrides", type=Path, default=OVERRIDES)
    parser.add_argument(
        "--max-errors", type=int, default=25, help="how many validation errors to print"
    )
    args = parser.parse_args(argv)

    inp = args.inp or _paths.ensure_work() / "s1c-skeleton.jsonl"
    _paths.require(inp, "make stage1")

    entries: list[Entry] = []
    with inp.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                entries.append(Entry.from_line(line))
    print(f"read {len(entries):,} entries from {inp}")

    entries, applied = apply_overrides(entries, args.overrides)
    if applied:
        print(f"applied {applied:,} override(s) from {args.overrides}")

    errors = validate_all(entries)
    if errors:
        print(f"\n{len(errors):,} validation error(s):")
        for err in errors[: args.max_errors]:
            print(f"  {err}")
        if len(errors) > args.max_errors:
            print(f"  ... and {len(errors) - args.max_errors:,} more")
        return 1

    written = write_shards(args.entries, entries)
    print(f"\nvalidated and wrote {sum(written.values()):,} entries "
          f"across {len(written)} shard(s) -> {args.entries}")
    for name in sorted(written)[:5]:
        print(f"  {name}: {written[name]:,}")
    if len(written) > 5:
        print(f"  ... {len(written) - 5} more shards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
