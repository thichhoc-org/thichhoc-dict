#!/usr/bin/env python3
"""Stage 1b — attach IPA pronunciations, converted from CMUdict.

CMUdict rather than a ready-made IPA list because its license is unambiguous
(BSD 2-clause, Carnegie Mellon) and the plan's whole competitive claim rests on
a clean license. The conversion is deterministic: ARPAbet phones map 1:1 to
General American IPA, and stress digits become the ˈ/ˌ marks once the phones
are syllabified.

Syllabification uses the maximal onset principle — consonants between two
vowels attach to the following syllable as far as English phonotactics allow.
Without it the stress mark lands mid-cluster (``bˈeɪkəri`` instead of
``ˈbeɪkəri``), which looks wrong to anyone who reads IPA.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import _paths
from _paths import CMUDICT

from core.schema import Entry

# -- ARPAbet -> IPA (General American) --------------------------------------

VOWELS = {
    "AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ",
    "EH": "ɛ", "ER": "ɝ", "EY": "eɪ", "IH": "ɪ", "IY": "i", "OW": "oʊ",
    "OY": "ɔɪ", "UH": "ʊ", "UW": "u",
}

#: Unstressed AH and ER reduce to schwa — the single biggest readability win.
REDUCED = {"AH": "ə", "ER": "ɚ"}

CONSONANTS = {
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h",
    "JH": "dʒ", "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p",
    "R": "ɹ", "S": "s", "SH": "ʃ", "T": "t", "TH": "θ", "V": "v", "W": "w",
    "Y": "j", "Z": "z", "ZH": "ʒ",
}

# -- English onset phonotactics ---------------------------------------------

_LIQUID_GLIDE = {"l", "ɹ", "w", "j"}

#: Two-consonant onsets that English permits word-initially.
ONSETS_2 = (
    {(c, "l") for c in "pbkɡf"}
    | {(c, "ɹ") for c in ("p", "b", "t", "d", "k", "ɡ", "f", "θ", "ʃ")}
    | {(c, "w") for c in ("t", "d", "k", "ɡ", "s", "θ")}
    | {(c, "j") for c in ("p", "b", "t", "d", "k", "f", "v", "m", "n", "l", "h", "s")}
    | {("s", c) for c in ("p", "t", "k", "f", "m", "n", "l", "w")}
    | {("ʃ", "ɹ"), ("ʃ", "l"), ("ʃ", "m"), ("ʃ", "n"), ("ʃ", "w")}
)

#: s + voiceless stop + liquid/glide, restricted to combinations that also form
#: a legal two-consonant onset on their own.
ONSETS_3 = {
    ("s", stop, third)
    for stop in ("p", "t", "k")
    for third in _LIQUID_GLIDE
    if (stop, third) in ONSETS_2
}

STRESS_MARK = {"1": "ˈ", "2": "ˌ", "0": ""}


def _is_legal_onset(cluster: list[str]) -> bool:
    if len(cluster) <= 1:
        # ŋ never starts a syllable in English.
        return cluster != ["ŋ"]
    if len(cluster) == 2:
        return (cluster[0], cluster[1]) in ONSETS_2
    if len(cluster) == 3:
        return (cluster[0], cluster[1], cluster[2]) in ONSETS_3
    return False


def arpabet_to_ipa(phones: list[str]) -> str:
    """Convert a CMUdict pronunciation to a syllabified, stress-marked IPA string."""
    # 1. Map phones, remembering which are nuclei and what stress they carry.
    symbols: list[str] = []
    nuclei: list[int] = []
    stresses: dict[int, str] = {}

    for phone in phones:
        stress = ""
        base = phone
        if phone[-1].isdigit():
            base, stress = phone[:-1], phone[-1]
        if base in VOWELS:
            symbol = REDUCED[base] if (stress == "0" and base in REDUCED) else VOWELS[base]
            nuclei.append(len(symbols))
            stresses[len(symbols)] = stress
        elif base in CONSONANTS:
            symbol = CONSONANTS[base]
        else:
            continue  # unknown phone: drop rather than emit garbage
        symbols.append(symbol)

    if not symbols:
        return ""
    if not nuclei:
        return "/" + "".join(symbols) + "/"

    # 2. Find each syllable's start using maximal onset: walk the consonants
    #    before a nucleus backwards, taking as many as still form a legal onset.
    starts: list[int] = [0]
    for nucleus in nuclei[1:]:
        onset_start = nucleus
        while onset_start > starts[-1] + 1:
            candidate = symbols[onset_start - 1 : nucleus]
            if not _is_legal_onset(candidate):
                break
            onset_start -= 1
        # Leave at least one segment in the previous syllable.
        starts.append(max(onset_start, starts[-1] + 1))

    # 3. Emit, prefixing each syllable with its stress mark.
    pieces: list[str] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(symbols)
        mark = STRESS_MARK.get(stresses.get(nuclei[i], ""), "")
        pieces.append(mark + "".join(symbols[start:end]))

    # A single-syllable word needs no stress mark; every word has one, so the
    # mark carries no information there and only adds clutter.
    if len(pieces) == 1:
        pieces[0] = pieces[0].lstrip("ˈˌ")

    return "/" + "".join(pieces) + "/"


def load_cmudict(path: Path) -> dict[str, str]:
    """word -> IPA, using CMUdict's first (canonical) pronunciation only."""
    table: dict[str, str] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            word, phones = parts[0], parts[1:]
            # `word(2)` marks an alternative pronunciation; keep only the first.
            if word.endswith(")"):
                continue
            if not phones or word in table:
                continue
            ipa = arpabet_to_ipa(phones)
            if ipa:
                table[word] = ipa
    return table


def pronounce(headword: str, table: dict[str, str]) -> str:
    """Look up a headword, handling multiword entries phrase by phrase."""
    key = headword.lower()
    if key in table:
        return table[key]
    if " " in key or "-" in key:
        words = key.replace("-", " ").split()
        parts = [table.get(w, "") for w in words]
        # All or nothing: a half-transcribed phrase is worse than none.
        if all(parts):
            return "/" + " ".join(p.strip("/") for p in parts) + "/"
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="inp", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--cmudict", type=Path, default=CMUDICT)
    args = parser.parse_args(argv)

    work = _paths.ensure_work()
    inp = args.inp or work / "s1a-lemmas.jsonl"
    out = args.out or work / "s1b-ipa.jsonl"

    _paths.require(args.cmudict)
    table = load_cmudict(args.cmudict)
    print(f"loaded {len(table):,} CMUdict pronunciations")

    from core.store import write_single

    entries: list[Entry] = []
    hits = 0
    with inp.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            entry = Entry.from_line(line)
            ipa = pronounce(entry.headword, table)
            if ipa:
                entry.pron = ipa
                entry.source = f"{entry.source}+cmudict" if entry.source else "cmudict"
                hits += 1
            entries.append(entry)

    count = write_single(out, entries)
    pct = 100.0 * hits / count if count else 0.0
    print(f"wrote {count:,} entries -> {out}")
    print(f"  IPA coverage: {hits:,} ({pct:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
