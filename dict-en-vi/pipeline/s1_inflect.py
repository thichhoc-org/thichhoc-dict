#!/usr/bin/env python3
"""Stage 1c — generate every inflected form for every entry.

This is differentiator #1 (plan §3.2). The complaint that has dogged
Vietnamese e-reader dictionaries for a decade is that looking up ``stopped``
finds nothing and the user has to strip the suffix by hand. A form that is not
in this list is a lookup that fails on the device.

Three sources, deliberately overlapping:

  LemmInflect      the paradigm generator — handles consonant doubling
                   (stop -> stopped), -y -> -ies, -c -> -ck (panic ->
                   panicked) and its own irregular lookup table
  WordNet *.exc    Princeton's curated exception lists, 5,952 irregular forms.
                   Authoritative, and covers rare words LemmInflect has never
                   seen (aardwolf -> aardwolves)
  Hunspell en_US   an independent opinion, used to *drop* forms rather than add
                   them — and only for lemmas Hunspell actually knows, so we
                   never discard the paradigm of a word it has no data for

Multiword lemmas inflect on the syntactic head: nouns on the last word
("ice cream" -> "ice creams"), verbs on the first ("run across" -> "ran
across"), which is what makes phrasal verbs resolve.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import _paths
from _paths import HUNSPELL_AFF, HUNSPELL_DIC, WORDNET_DIR

from core.schema import Entry

#: Our pos -> Universal POS tag used by LemmInflect.
UPOS = {"n": "NOUN", "v": "VERB", "adj": "ADJ", "adv": "ADV"}

EXC_FILES = {"noun.exc": "n", "verb.exc": "v", "adj.exc": "adj", "adv.exc": "adv"}

#: Inflecting a 4-word phrase produces noise, not lookups anyone performs.
MAX_PHRASE_WORDS = 3


def load_exceptions(wordnet_dir: Path) -> dict[tuple[str, str], set[str]]:
    """(base lemma, pos) -> {irregular forms}, from WordNet's *.exc files."""
    table: dict[tuple[str, str], set[str]] = defaultdict(set)
    for name, pos in EXC_FILES.items():
        path = wordnet_dir / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 2:
                    continue
                inflected, bases = parts[0], parts[1:]
                for base in bases:
                    table[(base.replace("_", " "), pos)].add(inflected.replace("_", " "))
    return table


class Speller:
    """Hunspell wrapper that fails open — a missing dictionary must not
    silently strip every inflection out of the build."""

    def __init__(self, aff: Path, dic: Path) -> None:
        self.available = False
        self._cache: dict[str, bool] = {}
        try:
            from spylls.hunspell import Dictionary

            self._dict = Dictionary.from_files(str(dic.with_suffix("")))
            self.available = True
        except Exception as exc:  # noqa: BLE001
            print(f"  hunspell unavailable ({exc}); skipping cross-check")

    def knows(self, word: str) -> bool:
        if not self.available:
            return True
        cached = self._cache.get(word)
        if cached is None:
            try:
                cached = self._dict.lookup(word)
            except Exception:  # noqa: BLE001
                cached = True
            self._cache[word] = cached
        return cached


def _inflect_word(word: str, pos: str) -> tuple[set[str], bool]:
    """All LemmInflect forms of a single word, excluding the word itself.

    Returns ``(forms, from_oov)``. LemmInflect's primary API only consults its
    corpus-derived lookup table and returns nothing for words it has not seen —
    which is most of a 148k-headword dictionary. The rule-based OOV generator
    covers the rest, but it over-generates for adjectives ("beautifuler"), so
    the caller is told which path produced the forms.
    """
    from lemminflect import getAllInflections, getAllInflectionsOOV

    upos = UPOS.get(pos)
    if not upos:
        return set(), False

    def collect(table: dict) -> set[str]:
        forms: set[str] = set()
        for variants in table.values():
            forms.update(variants)
        forms.discard(word)
        return forms

    forms = collect(getAllInflections(word, upos=upos))
    if forms:
        return forms, False

    # Hyphenated compounds inflect on their final element, and LemmInflect has
    # no entry for the compound itself. Retrying on the tail recovers the
    # irregulars — "fine-draw" -> "fine-drew", "breast-feed" -> "breast-fed" —
    # which suffix rules alone would render as "fine-drawed".
    if "-" in word:
        prefix, _, tail = word.rpartition("-")
        if tail:
            tail_forms = collect(getAllInflections(tail, upos=upos))
            if tail_forms:
                return {f"{prefix}-{form}" for form in tail_forms}, False

    return collect(getAllInflectionsOOV(word, upos=upos)), True


def inflect(headword: str, pos: str) -> tuple[set[str], bool]:
    """Generate inflected forms for a headword, handling multiword lemmas."""
    if pos not in UPOS:
        return set(), False

    words = headword.split()
    if len(words) == 1:
        return _inflect_word(headword, pos)

    if len(words) > MAX_PHRASE_WORDS:
        return set(), False

    if pos == "v":
        # "run across" -> "ran across": the verb is the head, the particle is fixed.
        head, rest = words[0], words[1:]
        forms, oov = _inflect_word(head, "v")
        return {" ".join([form, *rest]) for form in forms}, oov
    if pos == "n":
        # "ice cream" -> "ice creams": English pluralises the final noun.
        *rest, head = words
        forms, oov = _inflect_word(head, "n")
        return {" ".join([*rest, form]) for form in forms}, oov

    # Comparatives of multiword adjectives ("more or less"-style) are not
    # productive; generating them would only add noise.
    return set(), False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="inp", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--wordnet", type=Path, default=WORDNET_DIR)
    parser.add_argument(
        "--no-hunspell",
        action="store_true",
        help="skip the Hunspell cross-check (faster; keeps every generated form)",
    )
    args = parser.parse_args(argv)

    work = _paths.ensure_work()
    inp = args.inp or work / "s1b-ipa.jsonl"
    out = args.out or work / "s1c-skeleton.jsonl"

    exceptions = load_exceptions(args.wordnet)
    print(f"loaded {sum(len(v) for v in exceptions.values()):,} WordNet exception forms")

    speller = Speller(HUNSPELL_AFF, HUNSPELL_DIC) if not args.no_hunspell else Speller(Path("x"), Path("x"))
    if speller.available:
        print("hunspell cross-check enabled")

    from core.store import write_single

    source_entries: list[Entry] = []
    with inp.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                source_entries.append(Entry.from_line(line))

    present = {(e.headword, e.pos) for e in source_entries}

    # WordNet's exception lists cover parts of speech the database itself does
    # not always define: it knows "put-putting" is a verb form of "put-put",
    # but only has "put-put" as a noun. Rather than lose the form, hand it to
    # whatever entry does carry that headword — on a device the user just wants
    # "put-putting" to land on the "put-put" page.
    orphan_exc: dict[str, set[str]] = defaultdict(set)
    for (base, pos), forms in exceptions.items():
        if (base, pos) not in present:
            orphan_exc[base] |= forms

    entries: list[Entry] = []
    total_forms = 0
    from_exc = 0
    from_orphan = 0
    dropped = 0
    oov_used = 0
    with_forms = 0

    # Each orphaned form is attached once, to the first entry carrying that
    # headword, so a headword with several parts of speech does not repeat it.
    claimed: set[str] = set()

    for entry in source_entries:
        forms, from_oov = inflect(entry.headword, entry.pos)
        oov_used += bool(forms and from_oov)

        extra = exceptions.get((entry.headword, entry.pos), set())

        # Rule-generated comparatives are the one place LemmInflect invents
        # words ("serendipitousest"). Noun and verb morphology is fully
        # productive, so only gradable classes need the extra proof.
        if from_oov and entry.pos in ("adj", "adv"):
            before = len(forms)
            forms = {f for f in forms if speller.knows(f)} if speller.available else set()
            dropped += before - len(forms)

        if entry.headword in orphan_exc and entry.headword not in claimed:
            claimed.add(entry.headword)
            orphaned = orphan_exc[entry.headword]
            from_orphan += len(orphaned - extra)
            extra = extra | orphaned

        from_exc += len(extra - forms)
        forms |= extra

        # Cross-check single words only, and only when Hunspell knows the
        # lemma — otherwise its verdict says nothing about the paradigm.
        if speller.available and " " not in entry.headword and speller.knows(entry.headword):
            kept = set()
            for form in forms:
                # Never drop a form Princeton lists as an irregular.
                if form in extra or " " in form or speller.knows(form):
                    kept.add(form)
                else:
                    dropped += 1
            forms = kept

        forms.discard(entry.headword)
        entry.inflections = sorted(forms)
        if entry.inflections:
            with_forms += 1
            total_forms += len(entry.inflections)
        entries.append(entry)

    count = write_single(out, entries)
    print(f"\nwrote {count:,} entries -> {out}")
    print(f"  entries with inflections: {with_forms:,} ({100.0 * with_forms / count:.1f}%)")
    print(f"  total inflected forms:    {total_forms:,}")
    print(f"  via rule-based OOV path:  {oov_used:,}")
    print(f"  added by WordNet *.exc:   {from_exc:,}")
    print(f"  rehomed cross-pos forms:  {from_orphan:,}")
    print(f"  dropped by hunspell:      {dropped:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
