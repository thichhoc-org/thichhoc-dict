#!/usr/bin/env python3
"""Stage 1a — build the headword catalogue from WordNet, tiered by frequency.

WordNet's ``index.*`` files are a curated (lemma, part-of-speech) list, which
is exactly our entry key for EN-VI: ``run`` the verb and ``run`` the noun are
two entries (plan §2). The English glosses come along for free from
``data.*``; they cost nothing to extract, and they are what lets a skeleton
build show something useful on a device and what later saves a user from
cross-referencing an English–English dictionary (pain point #3).

Frequency tiers come from wordfreq and drive the whole QA plan: tier 1 is the
5k words reviewed 100%, everything else is spot-checked.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

import _paths
from _paths import LANG, WORDNET_DIR

from core.schema import Entry, make_id

#: WordNet's single-letter pos codes -> ours.
POS_MAP = {"n": "n", "v": "v", "a": "adj", "r": "adv"}

INDEX_FILES = {
    "index.noun": "n",
    "index.verb": "v",
    "index.adj": "a",
    "index.adv": "r",
}

DATA_FILES = ["data.noun", "data.verb", "data.adj", "data.adv"]

#: The digit after ``%`` in a WordNet sense key encodes the part of speech.
#: 5 is an adjective satellite, which we fold into plain adjectives.
SENSE_POS = {"1": "n", "2": "v", "3": "adj", "4": "adv", "5": "adj"}

#: Tier boundaries by frequency rank of the *headword*. Tier 1 is the 5k the
#: plan commits to reviewing 100%.
TIER_BOUNDS = ((1, 5_000), (2, 20_000), (3, 50_000))

#: Headwords WordNet carries that a reading dictionary cannot use. A reader
#: tapping a word mid-novel never needs to be told that "1" means "một" or that
#: "15 minutes" is a quarter of an hour — the meaning is the arithmetic. They
#: are dropped rather than demoted because a lookup that fires on them is worse
#: than one that misses: it fills the popup with the answer to a question
#: nobody asked.
_MONTH = (r"january|february|march|april|may|june|july|august|september"
          r"|october|november|december")
_JUNK_HEADWORD = re.compile(
    r"^(?:"
    r"\d+(?:st|nd|rd|th|s)?"                        # 0, 1, 100th, 1530s
    rf"|\d+\s+(?:{_MONTH})|(?:{_MONTH})\s+\d+"      # 11 november, august 6
    r"|\d+\s+(?:minutes?|hours?|days?|years?|yards?|feet|miles?)"  # 15 minutes
    r")$",
    re.IGNORECASE,
)


def is_junk_headword(headword: str) -> bool:
    """True for a headword that should never become an entry.

    Kept narrow on purpose. ``1 kings`` and ``2 samuel`` are books of the Old
    Testament and match the shape of a quantity phrase, so the quantity rule
    names the units it will drop rather than accepting any ``<number> <word>``;
    likewise ``12-tone music`` and ``.22 caliber`` survive because the pattern
    is anchored, not a substring search.
    """
    return bool(_JUNK_HEADWORD.match(headword.strip()))

#: WordNet marks adjective syntactic position as "(p)", "(a)", "(ip)".
_ADJ_MARKER = re.compile(r"\((?:p|a|ip)\)$")

#: Skip WordNet's licence header, which is indented by two spaces.
_HEADER_PREFIX = "  "


def parse_glosses(wordnet_dir: Path) -> dict[str, str]:
    """Map synset offset+pos -> definition (examples stripped)."""
    glosses: dict[str, str] = {}
    for name in DATA_FILES:
        path = wordnet_dir / name
        if not path.exists():
            continue
        pos_char = {"data.noun": "n", "data.verb": "v", "data.adj": "a", "data.adv": "r"}[name]
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith(_HEADER_PREFIX) or "|" not in line:
                    continue
                offset, _, rest = line.partition(" ")
                gloss = rest.split("|", 1)[1].strip()
                # A WordNet gloss is `definition; "example"; "example"`. Keep
                # only the definition — examples are English, and an entry that
                # is meant to be scanned on a 6" screen has no room for them.
                definition = gloss.split(';')[0].strip() if '"' in gloss else gloss
                if definition:
                    glosses[f"{offset}{pos_char}"] = definition
    return glosses


def parse_sense_counts(wordnet_dir: Path) -> dict[tuple[str, str], int]:
    """(lemma, pos) -> how often that reading was tagged in SemCor.

    This is the only per-part-of-speech frequency signal available for free,
    and it decides which reading a reader sees first. wordfreq scores the
    written form and cannot tell ``run`` the verb from ``run`` the noun; SemCor
    can, and says 268 to 29. Without it the entry for ``run`` opens on a
    baseball score, which is the wrong answer for almost every sentence a
    reader will meet it in.
    """
    counts: dict[tuple[str, str], int] = defaultdict(int)
    path = wordnet_dir / "index.sense"
    if not path.exists():
        return counts

    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            fields = line.split()
            # sense_key synset_offset sense_number tag_cnt
            if len(fields) < 4:
                continue
            lemma, _, rest = fields[0].partition("%")
            pos = SENSE_POS.get(rest[:1])
            if not pos:
                continue
            try:
                counts[(lemma.replace("_", " "), pos)] += int(fields[3])
            except ValueError:
                continue
    return counts


def parse_index(wordnet_dir: Path) -> list[tuple[str, str, list[str], int]]:
    """Return (lemma, our_pos, [synset keys], sense_count) from index.*."""
    out: list[tuple[str, str, list[str], int]] = []
    for name, pos_char in INDEX_FILES.items():
        path = _paths.require(wordnet_dir / name)
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith(_HEADER_PREFIX) or not line.strip():
                    continue
                fields = line.split()
                # lemma pos synset_cnt p_cnt [ptrs...] sense_cnt tagsense_cnt offsets...
                lemma_raw, _pos, synset_cnt_s, p_cnt_s = fields[0], fields[1], fields[2], fields[3]
                try:
                    synset_cnt = int(synset_cnt_s)
                    p_cnt = int(p_cnt_s)
                except ValueError:
                    continue
                offsets_start = 4 + p_cnt + 2  # skip ptr symbols, sense_cnt, tagsense_cnt
                offsets = fields[offsets_start : offsets_start + synset_cnt]

                lemma = _ADJ_MARKER.sub("", lemma_raw).replace("_", " ").strip()
                if not lemma:
                    continue
                out.append((lemma, POS_MAP[pos_char], [f"{o}{pos_char}" for o in offsets], synset_cnt))
    return out


def frequency_table(headwords: set[str]) -> dict[str, float]:
    """Zipf frequency per headword (0.0 when wordfreq has no data)."""
    from wordfreq import zipf_frequency

    return {hw: zipf_frequency(hw, "en") for hw in headwords}


#: Share of each tier's places reserved for multi-word headwords. Phrases are
#: ranked on their own ladder and take these many slots; single words take the
#: rest.
#:
#: They cannot share one ladder, because ``wordfreq`` has no frequency for a
#: phrase and estimates one from the component words — it returns roughly the
#: rarest component. So ``family court`` scores 5.22 against ``table``'s 5.05,
#: and every compound built from two ordinary words outranks ordinary words.
#: On a single ladder that took 3,197 of tier 1's 5,000 places (64%) and left
#: *weather*, *trial*, *saturday*, *politics* and *environment* in tier 2.
#:
#: The split is a judgement, not a measurement, and it is written here rather
#: than derived so it can be argued with: phrases are worth real space, because
#: ``on the spot`` and ``bill of health`` are exactly what a reader cannot
#: guess from the parts, but they are not worth two thirds of the budget.
PHRASE_SHARE = ((1, 1_500), (2, 6_000), (3, 15_000))


def _split_ladders(freqs: dict[str, float]) -> tuple[list[str], list[str]]:
    """Rank single-word and multi-word headwords separately, best first."""
    def rank(items):
        return [hw for hw, _ in sorted(items, key=lambda kv: (-kv[1], kv[0]))]

    singles = rank([(h, f) for h, f in freqs.items() if " " not in h])
    phrases = rank([(h, f) for h, f in freqs.items() if " " in h])
    return singles, phrases


def assign_tiers(freqs: dict[str, float]) -> dict[str, int]:
    """Bucket headwords into tiers 1-5 on two separate frequency ladders."""
    singles, phrases = _split_ladders(freqs)
    tiers: dict[str, int] = {}

    for ladder, bounds in (
        (singles, [(t, b - p) for (t, b), (_, p) in zip(TIER_BOUNDS, PHRASE_SHARE)]),
        (phrases, list(PHRASE_SHARE)),
    ):
        for rank, headword in enumerate(ladder, 1):
            if freqs[headword] <= 0.0:
                tiers[headword] = 5
                continue
            for tier, bound in bounds:
                if rank <= bound:
                    tiers[headword] = tier
                    break
            else:
                tiers[headword] = 4
    return tiers


def build(wordnet_dir: Path, max_glosses: int = 3) -> list[Entry]:
    print(f"reading WordNet from {wordnet_dir}")
    glosses = parse_glosses(wordnet_dir)
    print(f"  {len(glosses):,} synset glosses")

    index = parse_index(wordnet_dir)
    print(f"  {len(index):,} (lemma, pos) pairs")

    dropped = [row for row in index if is_junk_headword(row[0])]
    if dropped:
        index = [row for row in index if not is_junk_headword(row[0])]
        print(f"  dropped {len(dropped):,} pairs on {len({r[0] for r in dropped}):,} "
              f"unusable headwords (bare numerals, dates, quantities)")

    sense_counts = parse_sense_counts(wordnet_dir)
    print(f"  {sum(1 for v in sense_counts.values() if v):,} (lemma, pos) pairs with a SemCor count")

    headwords = {lemma for lemma, _, _, _ in index}
    print(f"  {len(headwords):,} distinct headwords; computing frequencies")
    freqs = frequency_table(headwords)
    tiers = assign_tiers(freqs)

    # A (lemma, pos) can appear once per index file only, but guard anyway:
    # a duplicate id would shadow an entry silently.
    seen: dict[str, Entry] = {}
    collisions = 0

    for lemma, pos, synsets, _sense_cnt in index:
        entry_id = make_id(LANG, lemma, pos)
        if entry_id in seen:
            collisions += 1
            continue
        # Distinct synsets can share wording ("get rid of" appears under both
        # `shake off` senses). Showing the same line twice looks like a bug, so
        # dedupe before taking the first few — order is WordNet's sense order,
        # which is roughly frequency order.
        seen_gloss: dict[str, None] = {}
        for key in synsets:
            gloss = glosses.get(key)
            if gloss:
                seen_gloss.setdefault(gloss, None)
            if len(seen_gloss) >= max_glosses:
                break
        gloss_en = list(seen_gloss)
        tag = sense_counts.get((lemma, pos), 0)
        seen[entry_id] = Entry(
            id=entry_id,
            lang=LANG,
            headword=lemma,
            pos=pos,
            gloss_en=gloss_en,
            freq=freqs.get(lemma, 0.0),
            freq_tier=tiers.get(lemma, 5),
            source="wordnet",
            # Zeros are omitted to keep the JSONL line short — most entries
            # never appear in SemCor, and absence already means "no signal".
            extra={"tag": tag} if tag else {},
        )

    if collisions:
        print(f"  {collisions} duplicate (lemma, pos) pairs skipped")

    return list(seen.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wordnet", type=Path, default=WORDNET_DIR)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--max-glosses", type=int, default=3)
    args = parser.parse_args(argv)

    out = args.out or _paths.ensure_work() / "s1a-lemmas.jsonl"
    entries = build(args.wordnet, args.max_glosses)

    from core.store import write_single

    count = write_single(out, sorted(entries, key=lambda e: e.id))

    by_tier: dict[int, int] = defaultdict(int)
    for entry in entries:
        by_tier[entry.freq_tier] += 1
    print(f"\nwrote {count:,} entries -> {out}")
    print("  by tier: " + ", ".join(f"t{t}={by_tier[t]:,}" for t in sorted(by_tier)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
