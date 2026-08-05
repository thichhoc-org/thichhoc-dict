#!/usr/bin/env python3
"""``thichhoc-dict`` — validate and build an entry store for every device.

    thichhoc-dict validate dict-en-vi/data/entries
    thichhoc-dict build    dict-en-vi/data/entries --target stardict --skeleton

Builders that need an external tool degrade rather than fail: a missing
kindlegen leaves the MOBI source on disk and reports why. Only a real error —
invalid data, a tool that ran and failed — is fatal, so a machine without
Kindle Previewer can still produce the StarDict and Kobo releases.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import attribution
from .builders import kobo, mobi, stardict
from .builders.common import BuildMeta, BuildResult
from .render import EntryRenderer, RenderOptions
from .schema import Entry, validate_all
from .store import iter_entries, load_entries

TARGETS = {"stardict": stardict.build, "mobi": mobi.build, "kobo": kobo.build}

DICT_NAMES = {
    "en-vi": "Từ điển Anh–Việt thichhoc.com",
    "zh-vi": "Từ điển Trung–Việt thichhoc.com",
}


def _find_license_data(entries_dir: Path) -> Path | None:
    """Locate the project's LICENSE-DATA by walking up from the entry store.

    ``dict-en-vi/data/entries`` -> ``dict-en-vi/LICENSE-DATA``. Walking rather
    than hardcoding two levels keeps this working when a build is pointed at a
    subset or a staging copy of the store.
    """
    for parent in entries_dir.resolve().parents:
        candidate = parent / "LICENSE-DATA"
        if candidate.is_file():
            return candidate
    return None


def _detect_lang(entries: list[Entry]) -> str:
    for entry in entries:
        if entry.lang:
            return entry.lang
    return "en-vi"


def cmd_validate(args: argparse.Namespace) -> int:
    entries = load_entries(args.entries)
    if not entries:
        print(f"no entries found in {args.entries}", file=sys.stderr)
        return 1

    errors = validate_all(entries)
    print(f"validated {len(entries):,} entries from {args.entries}")
    if errors:
        print(f"\n{len(errors):,} error(s):")
        for err in errors[: args.max_errors]:
            print(f"  {err}")
        if len(errors) > args.max_errors:
            print(f"  ... and {len(errors) - args.max_errors:,} more")
        return 1
    print("OK — no errors.")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    entries = load_entries(args.entries)
    if not entries:
        print(f"no entries found in {args.entries}", file=sys.stderr)
        return 1

    if not args.skip_validate:
        errors = validate_all(entries)
        if errors:
            print(f"{len(errors):,} validation error(s); refusing to build.", file=sys.stderr)
            for err in errors[:10]:
                print(f"  {err}", file=sys.stderr)
            return 1

    if args.limit:
        entries = entries[: args.limit]
        print(f"limited to {len(entries):,} entries")

    lang = args.lang or _detect_lang(entries)
    lang_in, _, lang_out = lang.partition("-")

    # A build is a skeleton until most of it has meanings. Keying off "any
    # entry has a sense" would flip the whole presentation the moment a single
    # correction lands in overrides/.
    translated = sum(1 for e in entries if e.senses_vi)
    skeleton = args.skeleton or translated < len(entries) // 2
    version = args.version or ("0.1.0-skeleton" if skeleton else "0.1.0")

    # The description ships inside the dictionary and is what a reader sees in
    # their device's dictionary list, so it states measured coverage rather
    # than a label. "Chưa có nghĩa tiếng Việt" was true of the first build and
    # became a lie the moment tier 1 landed; a number cannot go stale that way.
    pct = 100.0 * translated / len(entries) if entries else 0.0
    if translated == 0:
        summary = "chưa có nghĩa tiếng Việt (bản skeleton)"
    elif skeleton:
        summary = f"{translated:,}/{len(entries):,} mục đã có nghĩa tiếng Việt ({pct:.1f}%)"
    else:
        summary = f"{translated:,} mục có nghĩa tiếng Việt ({pct:.1f}%)"

    meta = BuildMeta(
        name=DICT_NAMES.get(lang, f"thichhoc {lang}"),
        lang_in=lang_in,
        lang_out=lang_out,
        version=version,
        date=args.date,
        description=(
            f"Từ điển mở, license sạch, tra được mọi biến thể từ. "
            f"{len(entries):,} mục từ; {summary}."
        ),
        license=attribution.DATA_LICENSE,
        homepage=attribution.HOMEPAGE,
    )

    # Skeleton builds exist to verify lookup on a real device, so they list the
    # inflected forms in the entry body: you can see at a glance which forms
    # should have resolved.
    renderer = EntryRenderer(RenderOptions(show_inflections=skeleton))

    out_dir = args.out / lang
    targets = args.target or list(TARGETS)

    print(f"building {len(entries):,} entries [{lang}] {version} -> {out_dir}")
    if skeleton:
        # Report the count, not a label — "senses_vi is empty" stopped being
        # true the moment tier 1 landed, and a build log that misstates its own
        # input is how a half-translated release gets mistaken for a finished one.
        print(f"  skeleton presentation: {translated:,}/{len(entries):,} translated"
              f" ({pct:.1f}%), inflections shown on the {len(entries) - translated:,}"
              f" entries that have no sense yet")

    # Added after the coverage numbers are computed, so the credit never counts
    # itself as a translated entry, and prepended rather than appended because
    # the MOBI builder chunks in list order — position in the file decides
    # nothing for lookup, but keeps the entry findable when reading the source.
    entries.insert(0, attribution.attribution_entry(meta.name, lang, version, args.date))

    out_dir.mkdir(parents=True, exist_ok=True)
    attribution_path = out_dir / "ATTRIBUTION.txt"
    attribution_path.write_text(
        attribution.attribution_text(
            meta.name, lang, version, args.date, _find_license_data(args.entries)
        ),
        encoding="utf-8",
    )
    print(f"  attribution -> {attribution_path}")

    results: list[BuildResult] = []
    failed = False
    for name in targets:
        builder = TARGETS[name]
        print(f"\n-- {name}")
        try:
            result = builder(entries, out_dir, meta, renderer=renderer)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {exc}", file=sys.stderr)
            failed = True
            continue
        results.append(result)
        print(result.describe())

    print("\n" + "=" * 60)
    for result in results:
        status = "ok" if result.ok else "partial"
        print(f"  {result.target:<10} {status:<8} {len(result.artifacts)} artifact(s)")
    if failed:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thichhoc-dict", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="check an entry store against the schema")
    validate.add_argument("entries", type=Path)
    validate.add_argument("--max-errors", type=int, default=25)
    validate.set_defaults(func=cmd_validate)

    build = sub.add_parser("build", help="build device dictionaries")
    build.add_argument("entries", type=Path)
    build.add_argument("--out", type=Path, default=Path("build"))
    build.add_argument("--target", action="append", choices=sorted(TARGETS))
    build.add_argument("--lang", help="override the language pair, e.g. en-vi")
    build.add_argument("--version", help="version string embedded in the artifacts")
    build.add_argument("--date", default="", help="build date (kept out of the clock for reproducibility)")
    build.add_argument("--skeleton", action="store_true", help="force skeleton presentation")
    build.add_argument("--limit", type=int, help="build only the first N entries (smoke test)")
    build.add_argument("--skip-validate", action="store_true")
    build.set_defaults(func=cmd_build)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
