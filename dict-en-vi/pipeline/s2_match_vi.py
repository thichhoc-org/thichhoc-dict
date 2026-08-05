#!/usr/bin/env python3
"""Stage 2a — fill Vietnamese senses from Wiktionary, for free.

This runs before any LLM call and decides the whole Stage 2 budget: every
entry matched here is an entry we never pay to translate. Deterministic,
re-runnable, and costs nothing, so it is worth doing exhaustively first
(plan §2 — measure coverage before spending).

Source is the kaikki.org extract of English Wiktionary, whose per-sense
``translations`` blocks are exactly an English→Vietnamese mapping already
aligned to the sense they belong to. CC BY-SA, actively maintained, and — the
part that matters for this project — with provenance anyone can audit.

The dump is ~3 GB, so it is streamed and pre-filtered on a raw-bytes check
before the JSON parse; parsing every line would take an order of magnitude
longer for no benefit.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import _paths
from _paths import ENTRIES_DIR, RAW_DIR

from core.schema import Entry

#: Wiktionary part-of-speech names -> ours. We only carry the four WordNet
#: classes, so anything else is skipped rather than mapped approximately.
POS_MAP = {
    "noun": "n",
    "verb": "v",
    "adj": "adj",
    "adv": "adv",
}

#: Cheap reject before `json.loads`. Nearly every line in the dump lacks a
#: Vietnamese translation, and this check throws them out ~50x faster than
#: parsing would. `lang_code` also appears under `descendants`, so a parsed
#: confirmation still follows.
_VI_MARKER = b'"lang_code": "vi"'

#: Translations carrying these are real but would mislead a learner who meets
#: the word in a modern book.
SKIP_TAGS = {"obsolete", "archaic"}

#: Prefer the accent our CMUdict-derived IPA already uses, so a dictionary
#: doesn't mix General American and RP between neighbouring entries.
_ACCENT_PRIORITY = ("General-American", "US", "GenAm")


def load_wanted(entries_dir: Path) -> dict[tuple[str, str], list[Entry]]:
    """(headword, pos) -> entries, for everything Stage 2 could fill."""
    from core.store import iter_entries

    wanted: dict[tuple[str, str], list[Entry]] = defaultdict(list)
    for entry in iter_entries(entries_dir):
        wanted[(entry.headword, entry.pos)].append(entry)
    return wanted


def _pick_ipa(sounds: list[dict]) -> str:
    """Best IPA from a Wiktionary `sounds` block, or ''."""
    candidates = [s for s in sounds if s.get("ipa")]
    if not candidates:
        return ""
    for sound in candidates:
        tags = set(sound.get("tags", []))
        if tags & set(_ACCENT_PRIORITY):
            return sound["ipa"]
    return candidates[0]["ipa"]


def scan_dump(
    path: Path,
    wanted: set[tuple[str, str]],
    *,
    progress_every: int = 500_000,
) -> tuple[dict[tuple[str, str], dict[str, list[str]]], dict[tuple[str, str], str]]:
    """Stream the dump; return per-key sense->translations, and IPA."""
    senses: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(dict)
    ipa: dict[tuple[str, str], str] = {}

    lines = 0
    considered = 0
    with path.open("rb") as fh:
        for raw in fh:
            lines += 1
            if progress_every and lines % progress_every == 0:
                print(f"  ...{lines:,} lines, {len(senses):,} keys matched")
            if _VI_MARKER not in raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue

            pos = POS_MAP.get(record.get("pos", ""))
            if not pos:
                continue
            key = (record.get("word", ""), pos)
            if key not in wanted:
                continue
            considered += 1

            if key not in ipa:
                found = _pick_ipa(record.get("sounds") or [])
                if found:
                    ipa[key] = found

            # Group by the English sense each translation belongs to, keeping
            # Wiktionary's own order — the translation tables are laid out in
            # sense order, which is roughly frequency order.
            #
            # wiktextract emits translations in two places: a top-level block
            # (the page's translation tables, tagged with a `sense` string) and
            # per-sense blocks under `senses[]`. Both carry Vietnamese, and
            # reading only one of them silently halves coverage.
            bucket = senses[key]

            def absorb(translation: dict, sense_hint: str = "") -> None:
                if translation.get("lang_code") != "vi":
                    return
                word = (translation.get("word") or "").strip()
                if not word:
                    return
                if set(translation.get("tags") or []) & SKIP_TAGS:
                    return
                sense_key = translation.get("sense") or sense_hint
                words = bucket.setdefault(sense_key, [])
                if word not in words:
                    words.append(word)

            for translation in record.get("translations") or []:
                absorb(translation)
            for sense in record.get("senses") or []:
                hint = (sense.get("glosses") or [""])[0]
                for translation in sense.get("translations") or []:
                    absorb(translation, hint)

    print(f"  scanned {lines:,} lines; {considered:,} records matched a headword")
    return senses, ipa


def build_senses(bucket: dict[str, list[str]], max_senses: int) -> list[str]:
    """Turn {english sense: [vietnamese words]} into our senses_vi list."""
    out: list[str] = []
    seen: set[str] = set()
    for words in bucket.values():
        text = "; ".join(words)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
        if len(out) >= max_senses:
            break
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entries", type=Path, default=ENTRIES_DIR)
    parser.add_argument("--dump", type=Path, default=RAW_DIR / "wiktionary" / "en-wiktionary.jsonl")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--max-senses", type=int, default=4)
    parser.add_argument("--fill-ipa", action="store_true", default=True,
                        help="also fill pronunciation where CMUdict had none")
    args = parser.parse_args(argv)

    _paths.require(args.dump, "make download")
    out = args.out or _paths.ensure_work() / "s2a-matched.jsonl"

    wanted = load_wanted(args.entries)
    print(f"{sum(len(v) for v in wanted.values()):,} entries across {len(wanted):,} (headword, pos) keys")

    print(f"scanning {args.dump} ({args.dump.stat().st_size / 1e9:.2f} GB)")
    senses, ipa = scan_dump(args.dump, set(wanted))

    from core.store import write_single

    entries: list[Entry] = []
    matched = 0
    ipa_filled = 0
    by_tier_total: dict[int, int] = defaultdict(int)
    by_tier_matched: dict[int, int] = defaultdict(int)

    for key, group in wanted.items():
        bucket = senses.get(key)
        vi = build_senses(bucket, args.max_senses) if bucket else []
        for entry in group:
            by_tier_total[entry.freq_tier] += 1
            if vi:
                entry.senses_vi = vi
                entry.source = f"{entry.source}+wiktionary" if entry.source else "wiktionary"
                matched += 1
                by_tier_matched[entry.freq_tier] += 1
            if args.fill_ipa and not entry.pron and key in ipa:
                entry.pron = ipa[key]
                ipa_filled += 1
            entries.append(entry)

    count = write_single(out, sorted(entries, key=lambda e: e.id))

    print(f"\nwrote {count:,} entries -> {out}")
    print(f"  matched from Wiktionary: {matched:,} ({100.0 * matched / count:.1f}%)")
    print(f"  IPA newly filled:        {ipa_filled:,}")
    print("\nCoverage by tier — this is the Stage 2 budget:")
    print(f"  {'tier':<6}{'entries':>12}{'matched':>12}{'%':>8}{'to translate':>15}")
    for tier in sorted(by_tier_total):
        total = by_tier_total[tier]
        hit = by_tier_matched.get(tier, 0)
        print(f"  {tier:<6}{total:>12,}{hit:>12,}{100.0 * hit / total:>7.1f}%{total - hit:>15,}")
    remaining = count - matched
    print(f"  {'ALL':<6}{count:>12,}{matched:>12,}{100.0 * matched / count:>7.1f}%{remaining:>15,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
