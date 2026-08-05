"""Group entries by headword for the formats that need a single page per word.

Two of the three targets key their index on the headword and show exactly one
page per key, so ``run`` (noun) and ``run`` (verb) must be merged before the
index is written or one of them becomes unreachable.

Grouping also surfaces a subtler gap. About 4% of inflected forms are
themselves headwords — WordNet lists ``abandoned`` as an adjective as well as
the past of ``abandon``. A reader that resolves its main index first will find
the adjective and never consult the synonym table, so the user gets half an
answer to the exact kind of lookup this project exists to fix. Recording a
cross-reference on the colliding headword closes that.

MOBI does not need the merging: Kindle natively returns every ``idx:orth`` and
``idx:iform`` match for a word, so it already shows both. It does share
:func:`entry_order`, because "shows both" means "stacks both cards in file
order" and only the first is visible without scrolling.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .schema import Entry

#: Fallback ordering for words with no corpus evidence either way.
_POS_ORDER = {"n": 0, "v": 1, "adj": 2, "adv": 3, "phr": 4, "idiom": 4}


def entry_order(entry: Entry) -> tuple[int, int, int, str]:
    """Sort key deciding which reading a reader sees first.

    Corpus frequency for *this part of speech* leads (``extra["tag"]``, the
    SemCor tag count collected in Stage 1). A fixed nouns-first order looks
    reasonable and is wrong exactly where it matters: ``run`` is a verb 268
    times to 29, so a noun-first rule opens the entry on a baseball score.
    Where SemCor has nothing to say, the fixed order takes over.
    """
    return (
        -int(entry.extra.get("tag", 0)),
        _POS_ORDER.get(entry.pos, 8),
        entry.freq_tier,
        entry.pos,
    )


@dataclass(slots=True)
class HeadwordGroup:
    """Everything that must appear on the page for one headword."""

    headword: str
    entries: list[Entry] = field(default_factory=list)
    #: Inflected forms that should route here and are not headwords themselves.
    variants: list[str] = field(default_factory=list)
    #: (base headword, pos) pairs this headword is also an inflected form of.
    xrefs: list[tuple[str, str]] = field(default_factory=list)


def group_by_headword(entries: list[Entry]) -> list[HeadwordGroup]:
    """Collapse entries into one group per headword, in sorted order."""
    by_headword: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        by_headword[entry.headword].append(entry)

    # form -> {(base headword, pos)} for every inflection in the corpus.
    inflected_from: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for entry in entries:
        for form in entry.inflections:
            if form != entry.headword:
                inflected_from[form].add((entry.headword, entry.pos))

    groups: list[HeadwordGroup] = []
    for headword in sorted(by_headword, key=lambda w: (w.lower(), w)):
        members = sorted(by_headword[headword], key=entry_order)

        variants: list[str] = []
        for entry in members:
            for form in entry.lookup_forms:
                if form != headword and form not in variants and form not in by_headword:
                    variants.append(form)

        # Only cross-reference bases that are not already on this page.
        own = {e.pos for e in members}
        xrefs = sorted(
            (base, pos)
            for base, pos in inflected_from.get(headword, ())
            if base != headword or pos not in own
        )

        groups.append(HeadwordGroup(headword, members, variants, xrefs))

    return groups


__all__ = ["HeadwordGroup", "group_by_headword", "entry_order"]
