#!/usr/bin/env python3
"""Read or edit exactly one entry (plan §5).

The point is surgical access. A person fixing a reported mistranslation — or an
LLM doing the same in a Stage 2 repair loop — should not have to load a 2,000
line shard to change one sense, and a reviewer should not have to read a diff
that touches anything else.

``set`` writes to ``overrides/corrections.jsonl`` rather than to the shard, so
the correction survives the next pipeline run. Generated data and human
judgement stay in separate files.

  python -m core.tools.entry get en:run:v
  python -m core.tools.entry find run
  python -m core.tools.entry set en:run:v --sense "chạy" --sense "vận hành"
  python -m core.tools.entry set en:run:v --reviewed --example "She runs." "Cô ấy chạy."
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..render import EntryRenderer, RenderOptions
from ..schema import Entry, validate_entry
from ..store import iter_entries, load_index

DEFAULT_ENTRIES = Path("dict-en-vi/data/entries")
DEFAULT_OVERRIDES = Path("dict-en-vi/data/overrides/corrections.jsonl")


def _read_overrides(path: Path) -> tuple[dict[str, dict], list[str]]:
    """Return the patches plus the file's leading comment block.

    The header documents how to use the file and must survive a rewrite —
    otherwise the first ``set`` silently deletes the instructions for everyone
    who opens the file afterwards.
    """
    patches: dict[str, dict] = {}
    header: list[str] = []
    if not path.exists():
        return patches, header

    seen_data = False
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("//"):
                if not seen_data:
                    header.append(raw.rstrip("\n"))
                continue
            seen_data = True
            patch = json.loads(line)
            patches[patch["id"]] = patch
    return patches, header


def _write_overrides(path: Path, patches: dict[str, dict], header: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for line in header:
            fh.write(line + "\n")
        for entry_id in sorted(patches):
            fh.write(json.dumps(patches[entry_id], ensure_ascii=False, separators=(",", ":")) + "\n")


def cmd_get(args: argparse.Namespace) -> int:
    index = load_index(args.dir)
    entry = index.get(args.id)
    if entry is None:
        print(f"not found: {args.id}", file=sys.stderr)
        return 1

    if args.html:
        renderer = EntryRenderer(RenderOptions(show_inflections=True))
        print(renderer.render(entry))
    elif args.raw:
        print(entry.to_line())
    else:
        print(json.dumps(entry.to_json(), indent=2, ensure_ascii=False))
    return 0


def cmd_find(args: argparse.Namespace) -> int:
    """Locate entries by headword or by any inflected form."""
    needle = args.word.lower()
    hits: list[Entry] = []
    for entry in iter_entries(args.dir):
        if needle in {f.lower() for f in entry.lookup_forms}:
            hits.append(entry)

    if not hits:
        print(f"no entry resolves {args.word!r}", file=sys.stderr)
        return 1

    for entry in hits:
        via = "" if entry.headword.lower() == needle else f"  (via inflection of {entry.headword})"
        senses = "; ".join(entry.senses_vi) or "—"
        print(f"{entry.id:<34} {entry.pos:<4} {senses}{via}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    index = load_index(args.dir)
    base = index.get(args.id)
    if base is None and not args.create:
        print(f"not found: {args.id} (pass --create to add a new entry)", file=sys.stderr)
        return 1

    patches, header = _read_overrides(args.overrides)
    patch = patches.get(args.id, {"id": args.id})

    if args.sense:
        patch["senses_vi"] = list(args.sense)
    if args.gloss:
        patch["gloss_en"] = list(args.gloss)
    if args.pron is not None:
        patch["pron"] = args.pron
    if args.inflection:
        patch["inflections"] = list(args.inflection)
    if args.example:
        patch["examples"] = [{"src": src, "vi": vi} for src, vi in args.example]
    if args.phrase:
        patch["phrases"] = [{"text": text, "vi": vi} for text, vi in args.phrase]
    if args.reviewed:
        patch["reviewed"] = True
    if args.unreviewed:
        patch["reviewed"] = False
    if args.source is not None:
        patch["source"] = args.source

    if len(patch) == 1:
        print("nothing to change; pass at least one field", file=sys.stderr)
        return 2

    # Validate the merged result, not the patch — a correction that produces an
    # invalid entry must fail here, not in CI three commits later.
    merged = (base.to_json() if base else {"id": args.id, "lang": args.lang, "pos": args.pos})
    merged.update(patch)
    errors = validate_entry(Entry.from_json(merged))
    if errors:
        print(f"refusing to write — the result would be invalid:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    patches[args.id] = patch
    _write_overrides(args.overrides, patches, header)
    print(f"wrote override for {args.id} -> {args.overrides}")
    print(json.dumps(patch, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="core.tools.entry", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=DEFAULT_ENTRIES, help="entry store directory")
    sub = parser.add_subparsers(dest="command", required=True)

    get = sub.add_parser("get", help="print one entry")
    get.add_argument("id")
    get.add_argument("--raw", action="store_true", help="print the JSONL line verbatim")
    get.add_argument("--html", action="store_true", help="print the rendered entry HTML")
    get.set_defaults(func=cmd_get)

    find = sub.add_parser("find", help="find entries a word resolves to")
    find.add_argument("word")
    find.set_defaults(func=cmd_find)

    setter = sub.add_parser("set", help="record a correction in overrides/")
    setter.add_argument("id")
    setter.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    setter.add_argument("--sense", action="append", help="Vietnamese sense (repeatable, replaces all)")
    setter.add_argument("--gloss", action="append", help="English gloss (repeatable, replaces all)")
    setter.add_argument("--pron", help="IPA / pinyin")
    setter.add_argument("--inflection", action="append", help="lookup form (repeatable, replaces all)")
    setter.add_argument("--example", action="append", nargs=2, metavar=("SRC", "VI"))
    setter.add_argument("--phrase", action="append", nargs=2, metavar=("TEXT", "VI"))
    setter.add_argument("--reviewed", action="store_true")
    setter.add_argument("--unreviewed", action="store_true")
    setter.add_argument("--source")
    setter.add_argument("--create", action="store_true", help="allow adding an entry that does not exist")
    setter.add_argument("--lang", default="en-vi", help="only used with --create")
    setter.add_argument("--pos", default="n", help="only used with --create")
    setter.set_defaults(func=cmd_set)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
