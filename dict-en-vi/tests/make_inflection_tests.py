#!/usr/bin/env python3
"""Generate the hard-form test list (``inflection_500.txt``).

Two sources, both of which the users complaining on tinhte/kindlesaigon were
effectively describing:

  1. A hand-curated core of the forms named in those complaints and the
     patterns behind them — consonant doubling, irregular verbs, Latin/Greek
     plurals, suppletive comparatives.
  2. A frequency-weighted sample of WordNet's own irregular exception lists,
     so the suite covers the long tail rather than only the famous examples.

Regenerating is deliberate and rare — the checked-in list is the contract, and
it should only grow when a user reports a form that got away.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import _paths  # noqa: E402
from _paths import WORDNET_DIR  # noqa: E402

#: Forms named directly in user complaints, plus one representative of every
#: pattern that generates them. `form -> expected base lemma`.
CURATED: list[tuple[str, str]] = [
    # Consonant doubling — the "drowned works but stopped doesn't" complaint.
    ("stopped", "stop"), ("stopping", "stop"), ("running", "run"),
    ("planned", "plan"), ("planning", "plan"), ("occurred", "occur"),
    ("occurring", "occur"), ("referred", "refer"), ("referring", "refer"),
    ("controlled", "control"), ("controlling", "control"),
    ("permitted", "permit"), ("preferred", "prefer"), ("beginning", "begin"),
    ("swimming", "swim"), ("shopping", "shop"), ("dropped", "drop"),
    ("hugged", "hug"), ("robbed", "rob"), ("winning", "win"),
    ("getting", "get"), ("putting", "put"), ("sitting", "sit"),
    ("cutting", "cut"), ("hitting", "hit"), ("travelled", "travel"),
    ("equipped", "equip"), ("submitted", "submit"), ("admitted", "admit"),
    ("committed", "commit"), ("regretted", "regret"), ("fitted", "fit"),
    # -e drop before -ing/-ed.
    ("making", "make"), ("hoping", "hope"), ("taking", "take"),
    ("writing", "write"), ("coming", "come"), ("using", "use"),
    ("living", "live"), ("giving", "give"), ("moving", "move"),
    ("closing", "close"), ("driving", "drive"), ("having", "have"),
    # -y -> -ies / -ied.
    ("studies", "study"), ("studied", "study"), ("tried", "try"),
    ("tries", "try"), ("cities", "city"), ("countries", "country"),
    ("families", "family"), ("carried", "carry"), ("copied", "copy"),
    ("babies", "baby"), ("bodies", "body"), ("replied", "reply"),
    ("worried", "worry"), ("stories", "story"), ("companies", "company"),
    # -c -> -ck.
    ("panicked", "panic"), ("panicking", "panic"), ("trafficking", "traffic"),
    ("picnicked", "picnic"), ("mimicked", "mimic"),
    # Irregular verbs — past and participle.
    ("ran", "run"), ("went", "go"), ("gone", "go"), ("was", "be"),
    ("were", "be"), ("been", "be"), ("am", "be"), ("is", "be"),
    ("brought", "bring"), ("taught", "teach"), ("sought", "seek"),
    ("caught", "catch"), ("bought", "buy"), ("fought", "fight"),
    ("thought", "think"), ("felt", "feel"), ("kept", "keep"),
    ("slept", "sleep"), ("left", "leave"), ("meant", "mean"),
    ("sent", "send"), ("spent", "spend"), ("built", "build"),
    ("held", "hold"), ("told", "tell"), ("sold", "sell"),
    ("found", "find"), ("bound", "bind"), ("wound", "wind"),
    ("stood", "stand"), ("understood", "understand"), ("led", "lead"),
    ("fed", "feed"), ("read", "read"), ("said", "say"), ("paid", "pay"),
    ("laid", "lay"), ("made", "make"), ("had", "have"), ("did", "do"),
    ("done", "do"), ("ate", "eat"), ("eaten", "eat"), ("saw", "see"),
    ("seen", "see"), ("took", "take"), ("taken", "take"),
    ("gave", "give"), ("given", "give"), ("came", "come"),
    ("became", "become"), ("knew", "know"), ("known", "know"),
    ("grew", "grow"), ("grown", "grow"), ("threw", "throw"),
    ("thrown", "throw"), ("flew", "fly"), ("flown", "fly"),
    ("drew", "draw"), ("drawn", "draw"), ("blew", "blow"),
    ("wrote", "write"), ("written", "write"), ("drove", "drive"),
    ("driven", "drive"), ("rode", "ride"), ("ridden", "ride"),
    ("rose", "rise"), ("risen", "rise"), ("chose", "choose"),
    ("chosen", "choose"), ("spoke", "speak"), ("spoken", "speak"),
    ("broke", "break"), ("broken", "break"), ("stole", "steal"),
    ("stolen", "steal"), ("froze", "freeze"), ("frozen", "freeze"),
    ("wore", "wear"), ("worn", "wear"), ("tore", "tear"),
    ("swore", "swear"), ("bore", "bear"), ("born", "bear"),
    ("began", "begin"), ("begun", "begin"), ("drank", "drink"),
    ("drunk", "drink"), ("sang", "sing"), ("sung", "sing"),
    ("swam", "swim"), ("swum", "swim"), ("rang", "ring"),
    ("sank", "sink"), ("shrank", "shrink"), ("sprang", "spring"),
    ("hung", "hang"), ("stuck", "stick"), ("struck", "strike"),
    ("dug", "dig"), ("won", "win"), ("shot", "shoot"), ("lost", "lose"),
    ("met", "meet"), ("sat", "sit"), ("got", "get"), ("gotten", "get"),
    ("forgot", "forget"), ("forgotten", "forget"), ("hid", "hide"),
    ("hidden", "hide"), ("bit", "bite"), ("fell", "fall"),
    ("fallen", "fall"), ("felt", "feel"), ("lay", "lie"),
    ("lain", "lie"), ("woke", "wake"), ("woken", "wake"),
    # Irregular plurals — the "geese" complaint and its relatives.
    ("geese", "goose"), ("children", "child"), ("men", "man"),
    ("women", "woman"), ("teeth", "tooth"), ("feet", "foot"),
    ("mice", "mouse"), ("lice", "louse"), ("oxen", "ox"),
    ("people", "person"), ("knives", "knife"), ("wives", "wife"),
    ("lives", "life"), ("leaves", "leaf"), ("wolves", "wolf"),
    ("shelves", "shelf"), ("halves", "half"), ("calves", "calf"),
    ("loaves", "loaf"), ("thieves", "thief"), ("selves", "self"),
    ("scarves", "scarf"), ("hooves", "hoof"),
    # Latin / Greek plurals — heavy in academic reading.
    ("criteria", "criterion"), ("phenomena", "phenomenon"),
    ("indices", "index"), ("matrices", "matrix"), ("vertices", "vertex"),
    ("appendices", "appendix"), ("alumni", "alumnus"), ("fungi", "fungus"),
    ("cacti", "cactus"), ("nuclei", "nucleus"), ("radii", "radius"),
    ("stimuli", "stimulus"), ("syllabi", "syllabus"), ("bacteria", "bacterium"),
    ("curricula", "curriculum"), ("data", "datum"), ("media", "medium"),
    ("memoranda", "memorandum"), ("strata", "stratum"), ("errata", "erratum"),
    ("crises", "crisis"), ("theses", "thesis"), ("analyses", "analysis"),
    ("bases", "basis"), ("diagnoses", "diagnosis"), ("hypotheses", "hypothesis"),
    ("parentheses", "parenthesis"), ("axes", "axis"), ("oases", "oasis"),
    ("formulae", "formula"), ("larvae", "larva"), ("vertebrae", "vertebra"),
    ("automata", "automaton"), ("genera", "genus"),
    # -es after sibilants, -o.
    ("boxes", "box"), ("watches", "watch"), ("buses", "bus"),
    ("dishes", "dish"), ("churches", "church"), ("potatoes", "potato"),
    ("tomatoes", "tomato"), ("heroes", "hero"), ("echoes", "echo"),
    # Comparatives and superlatives, including suppletive.
    ("better", "good"), ("best", "good"), ("worse", "bad"),
    ("worst", "bad"), ("further", "far"), ("furthest", "far"),
    ("farther", "far"), ("farthest", "far"), ("less", "little"),
    ("more", "much"), ("most", "much"), ("bigger", "big"),
    ("biggest", "big"), ("hotter", "hot"), ("hottest", "hot"),
    ("thinner", "thin"), ("happier", "happy"), ("happiest", "happy"),
    ("easier", "easy"), ("easiest", "easy"), ("prettier", "pretty"),
    ("busier", "busy"), ("nicer", "nice"), ("largest", "large"),
    ("simpler", "simple"), ("simplest", "simple"),
    # Phrasal verbs — must resolve to the base phrase, not just the verb.
    ("ran across", "run across"), ("running across", "run across"),
    ("gave up", "give up"), ("giving up", "give up"),
    ("took off", "take off"), ("taken off", "take off"),
    ("brought up", "bring up"), ("put off", "put off"),
    ("came across", "come across"), ("looked after", "look after"),
    ("got over", "get over"), ("broke down", "break down"),
    # Compound nouns pluralise on the head.
    ("ice creams", "ice cream"), ("high schools", "high school"),
    ("post offices", "post office"), ("credit cards", "credit card"),
]

EXC_FILES = {"noun.exc": "n", "verb.exc": "v", "adj.exc": "adj", "adv.exc": "adv"}

HEADER = """\
# Hard inflected forms that MUST resolve, one per line: <form> -> <base lemma>
#
# This suite is a release gate (plan §3.2, §7.3): 100% must pass or the build
# does not ship. It encodes pain point #1 — a decade of users complaining that
# `stopped` and `geese` find nothing.
#
# Sources: hand-curated from user complaints on tinhte / kindlesaigon, plus a
# frequency-weighted sample of WordNet's *.exc irregular lists.
#
# Add a line whenever a user reports a form that failed. Never delete one to
# make the suite pass.
"""


def sample_from_wordnet(wordnet_dir: Path, want: int, exclude: set[str]) -> list[tuple[str, str]]:
    """Frequency-weighted sample of WordNet's irregular forms.

    Restricted to forms whose base is an actual headword in ``index.*``. The
    ``.exc`` files serve WordNet's stemmer and list plenty of bases the
    database itself does not define ("take steps", "fine-draw"); demanding
    those resolve would be testing for entries we never claimed to ship.
    """
    from wordfreq import zipf_frequency
    from s1_lemmas import parse_index

    known = {lemma for lemma, _pos, _synsets, _cnt in parse_index(wordnet_dir)}

    candidates: dict[str, str] = {}
    for name in EXC_FILES:
        path = wordnet_dir / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 2:
                    continue
                form, base = parts[0].replace("_", " "), parts[1].replace("_", " ")
                if form in exclude or form == base or base not in known:
                    continue
                candidates.setdefault(form, base)

    # Rank by how likely a reader is to actually meet the word — a test suite
    # full of forms nobody reads would pass without protecting anyone.
    ranked = sorted(
        candidates.items(),
        key=lambda kv: (-zipf_frequency(kv[0], "en"), kv[0]),
    )
    return ranked[:want]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "inflection_500.txt")
    parser.add_argument("--total", type=int, default=500)
    parser.add_argument("--wordnet", type=Path, default=WORDNET_DIR)
    args = parser.parse_args(argv)

    curated: list[tuple[str, str]] = []
    seen: set[str] = set()
    for form, base in CURATED:
        if form not in seen:
            seen.add(form)
            curated.append((form, base))

    extra = sample_from_wordnet(args.wordnet, max(0, args.total - len(curated)), seen)

    lines = [HEADER, f"# curated from user complaints ({len(curated)})"]
    lines += [f"{form} -> {base}" for form, base in curated]
    lines += ["", f"# sampled from WordNet *.exc, most frequent first ({len(extra)})"]
    lines += [f"{form} -> {base}" for form, base in extra]

    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(curated) + len(extra)} test forms -> {args.out}")
    print(f"  curated: {len(curated)}   sampled: {len(extra)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
