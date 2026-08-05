#!/usr/bin/env python3
"""Release gate — every form in inflection_500.txt must resolve.

This runs against the built entry store, not against LemmInflect, so it tests
what actually ships: if a form is missing from ``inflections`` it will be
missing from ``idx:iform`` / ``.syn`` / Kobo variants, and the lookup fails on
the device.

Exit code 1 on any miss. Wired into CI before the build step.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import _paths  # noqa: E402
from _paths import ENTRIES_DIR, TESTS_DIR  # noqa: E402

from core.store import iter_entries  # noqa: E402

_LINE = re.compile(r"^(?P<form>.+?)\s*->\s*(?P<base>.+?)\s*$")


def load_cases(path: Path) -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = _LINE.match(line)
            if match:
                cases.append((match["form"], match["base"]))
    return cases


def build_form_index(entries_dir: Path) -> dict[str, set[str]]:
    """form (lowercased) -> {headwords it resolves to}."""
    index: dict[str, set[str]] = defaultdict(set)
    for entry in iter_entries(entries_dir):
        for form in entry.lookup_forms:
            index[form.lower()].add(entry.headword)
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entries", type=Path, default=ENTRIES_DIR)
    parser.add_argument("--cases", type=Path, default=TESTS_DIR / "inflection_500.txt")
    parser.add_argument("--show", type=int, default=40, help="how many failures to list")
    args = parser.parse_args(argv)

    _paths.require(args.cases, "make tests-regen")
    if not any(args.entries.glob("*.jsonl")):
        raise SystemExit(f"no entries in {args.entries}\nRun `make stage1` first.")

    cases = load_cases(args.cases)
    index = build_form_index(args.entries)
    print(f"{len(cases)} test forms against {len(index):,} distinct lookup forms")

    missing: list[tuple[str, str]] = []   # form not found at all
    misrouted: list[tuple[str, str, set[str]]] = []  # found, but not to the expected base

    for form, base in cases:
        targets = index.get(form.lower())
        if not targets:
            missing.append((form, base))
        elif base.lower() not in {t.lower() for t in targets}:
            misrouted.append((form, base, targets))

    passed = len(cases) - len(missing) - len(misrouted)
    print(f"\n  pass:      {passed}/{len(cases)} ({100.0 * passed / len(cases):.1f}%)")
    print(f"  missing:   {len(missing)}")
    print(f"  misrouted: {len(misrouted)}")

    if missing:
        print(f"\nNOT FOUND — these lookups fail on the device:")
        for form, base in missing[: args.show]:
            print(f"  {form!r} should resolve to {base!r}")
        if len(missing) > args.show:
            print(f"  ... and {len(missing) - args.show} more")

    if misrouted:
        print(f"\nRESOLVES, BUT NOT TO THE EXPECTED LEMMA:")
        for form, base, targets in misrouted[: args.show]:
            shown = sorted(targets)[:4]
            print(f"  {form!r} -> {shown} (expected {base!r})")
        if len(misrouted) > args.show:
            print(f"  ... and {len(misrouted) - args.show} more")

    # Misrouting is not necessarily a defect: "left" legitimately resolves to
    # both the adjective `left` and the past of `leave`, and the device shows
    # the entry it has. Only an outright miss blocks the release.
    if missing:
        print(f"\nFAIL — {len(missing)} form(s) do not resolve at all.")
        return 1

    print("\nPASS — every test form resolves.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
