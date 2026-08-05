#!/usr/bin/env python3
"""Fetch the upstream corpora Stage 1 needs.

Everything here is license-clean per plan §3.1 — no commercial dictionary
data touches this repo in any form. Downloads land in ``raw/`` which is
gitignored: we redistribute only our derived JSONL, never somebody else's dump.

  WordNet 3.1     headword + part-of-speech catalogue, English glosses,
                  and the irregular-form exception lists
                  -- WordNet License (BSD-like, attribution)
  CMUdict         pronunciations, converted to IPA by s1_ipa.py
                  -- BSD 2-clause (Carnegie Mellon)
  Hunspell en_US  independent check on generated inflections
                  -- LGPL/MPL/BSD tri-license; used as a validator, not shipped

wordfreq ships its own data as a Python package, so there is nothing to fetch.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RAW = Path(__file__).resolve().parent / "raw"


@dataclass(frozen=True)
class Source:
    key: str
    url: str
    dest: str  # path under raw/
    license: str
    note: str
    #: For tarballs: extract, then keep only files whose name matches.
    extract_prefix: str = ""


SOURCES: list[Source] = [
    Source(
        key="wordnet",
        url="https://wordnetcode.princeton.edu/wn3.1.dict.tar.gz",
        dest="wordnet/",
        license="WordNet License (Princeton)",
        note="index.{noun,verb,adj,adv}, data.*, and the *.exc irregular lists",
        extract_prefix="dict/",
    ),
    Source(
        key="cmudict",
        url="https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict",
        dest="cmudict/cmudict.dict",
        license="BSD 2-clause (Carnegie Mellon University)",
        note="ARPAbet pronunciations with stress digits",
    ),
    Source(
        key="cmudict-phones",
        url="https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.phones",
        dest="cmudict/cmudict.phones",
        license="BSD 2-clause (Carnegie Mellon University)",
        note="phone inventory, used to sanity-check the ARPAbet->IPA table",
    ),
    Source(
        key="wiktionary",
        url="https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl",
        dest="wiktionary/en-wiktionary.jsonl",
        license="CC BY-SA (Wiktionary); extraction by kaikki.org / wiktextract",
        note=(
            "~3.2 GB. Per-sense English->Vietnamese translations plus IPA. "
            "This is the Stage 2 base: every entry matched here is one we never "
            "pay an LLM to translate."
        ),
    ),
    Source(
        key="hunspell-aff",
        url="https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/en/index.aff",
        dest="hunspell/en_US.aff",
        license="MIT (packaging) over LGPL/MPL/BSD en_US wordlist",
        note="affix rules",
    ),
    Source(
        key="hunspell-dic",
        url="https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/en/index.dic",
        dest="hunspell/en_US.dic",
        license="MIT (packaging) over LGPL/MPL/BSD en_US wordlist",
        note="stem list",
    ),
]


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "thichhoc-dict/0.1"})
    with urllib.request.urlopen(req, timeout=180) as resp, tmp.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    tmp.replace(dest)


def _fetch_tarball(source: Source, root: Path, force: bool) -> Path:
    target_dir = root / source.dest.rstrip("/")
    marker = target_dir / ".complete"
    if marker.exists() and not force:
        print(f"  {source.key}: already extracted")
        return target_dir

    archive = root / f"_{source.key}.tar.gz"
    if not archive.exists() or force:
        print(f"  {source.key}: downloading {source.url}")
        _download(source.url, archive)

    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            name = Path(member.name).name
            # Flatten: we only ever want the dict/ files, by basename.
            if source.extract_prefix and source.extract_prefix not in member.name:
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            (target_dir / name).write_bytes(extracted.read())

    marker.write_text("ok\n", encoding="utf-8")
    archive.unlink(missing_ok=True)
    print(f"  {source.key}: extracted to {target_dir}")
    return target_dir


def fetch(source: Source, root: Path = RAW, force: bool = False) -> Path:
    if source.url.endswith(".tar.gz"):
        return _fetch_tarball(source, root, force)

    dest = root / source.dest
    if dest.exists() and not force:
        print(f"  {source.key}: already present ({dest.stat().st_size:,} bytes)")
        return dest
    print(f"  {source.key}: downloading {source.url}")
    _download(source.url, dest)
    print(f"  {source.key}: saved {dest} ({dest.stat().st_size:,} bytes)")
    return dest


def write_manifest(root: Path) -> Path:
    """Record where every byte came from, for the LICENSE-DATA audit trail."""
    lines = ["# Upstream sources fetched into this directory", ""]
    for source in SOURCES:
        lines += [
            f"## {source.key}",
            f"- url: {source.url}",
            f"- path: raw/{source.dest}",
            f"- license: {source.license}",
            f"- contents: {source.note}",
            "",
        ]
    path = root / "MANIFEST.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument("--only", action="append", help="fetch only these source keys")
    parser.add_argument("--root", type=Path, default=RAW)
    args = parser.parse_args(argv)

    wanted = [s for s in SOURCES if not args.only or s.key in args.only]
    if not wanted:
        print(f"no sources match {args.only}; known: {[s.key for s in SOURCES]}", file=sys.stderr)
        return 2

    print(f"Fetching {len(wanted)} source(s) into {args.root}")
    failed: list[str] = []
    for source in wanted:
        try:
            fetch(source, args.root, args.force)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  {source.key}: FAILED — {exc}", file=sys.stderr)
            failed.append(source.key)

    write_manifest(args.root)

    if failed:
        print(f"\n{len(failed)} source(s) failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("\nAll sources ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
