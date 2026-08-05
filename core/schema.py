"""Entry schema shared by every language pair, plus validation.

One entry = one line of JSONL. The line is the unit of review: a PR that
fixes a single sense touches exactly one line, which is what makes
``tools/entry.py`` and human review of a 150k-entry dictionary tractable.

Entry keys:
  EN-VI: (lemma, pos)              -> ``en:run:v`` and ``en:run:n`` are distinct
  ZH-VI: (simp, trad, pinyin)      -> ``zh:xing2:v`` style, disambiguated by pron
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field, fields
from typing import Any, Iterable

# --------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------

#: Parts of speech accepted per language pair. Kept deliberately small — a
#: renderer has to have a Vietnamese label for every one of these.
POS_BY_LANG: dict[str, set[str]] = {
    "en-vi": {"n", "v", "adj", "adv", "prep", "conj", "pron", "det", "intj", "abbr", "phr"},
    "zh-vi": {"n", "v", "adj", "adv", "phr", "idiom", "char", "name", "other"},
}

#: Part-of-speech labels shown in the entry, e.g. ``run /rʌn/`` then ``v.``.
#:
#: These were Vietnamese abbreviations (dt / đt / tt / trt) until a review at
#: real device size: `dt` (danh từ) and `đt` (động từ) differ by one diacritic,
#: and the label renders small on a backlight-free e-ink panel — the two were
#: not tellable apart. The international abbreviations are shorter, unambiguous
#: at any size, and already familiar from Vietnamese school English.
POS_LABEL: dict[str, str] = {
    "n": "n.",
    "v": "v.",
    "adj": "adj.",
    "adv": "adv.",
    "prep": "prep.",
    "conj": "conj.",
    "pron": "pron.",
    "det": "det.",
    "intj": "intj.",
    "abbr": "abbr.",
    "phr": "phr.",
    "idiom": "idiom",
    "char": "chữ",
    "name": "tên riêng",
    "other": "khác",
}

#: 1 = most frequent 5k (reviewed 100%), 5 = no frequency data at all.
FREQ_TIERS = (1, 2, 3, 4, 5)

MAX_TIER = 5

_ID_RE = re.compile(r"^[a-z]{2}:[^\s:]+:[a-z]+$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Characters allowed verbatim in the slug part of an id. Everything else is
# escaped as ~XX so that ids stay ASCII, filename-safe and reversible.
_SLUG_SAFE = set("abcdefghijklmnopqrstuvwxyz0123456789_.-'")


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Example:
    """One bilingual example sentence."""

    src: str  # sentence in the source language (English / Chinese)
    vi: str = ""  # Vietnamese translation; empty in skeleton builds

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"src": self.src}
        if self.vi:
            d["vi"] = self.vi
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Example":
        # ``en`` is accepted as an alias so hand-written en-vi overrides can use
        # the more natural key from the plan document.
        return cls(src=d.get("src") or d.get("en") or "", vi=d.get("vi", ""))


@dataclass(slots=True)
class Phrase:
    """A phrasal verb / collocation attached to its base entry.

    Gathering these onto the base entry (rather than as standalone entries) is
    what lets a Kindle lookup on "run" also show "run out of" — plan §3.3.
    """

    text: str  # "run out of"
    vi: str = ""  # "hết, cạn kiệt"

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"text": self.text}
        if self.vi:
            d["vi"] = self.vi
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Phrase":
        return cls(text=d.get("text", ""), vi=d.get("vi", ""))


@dataclass(slots=True)
class Entry:
    """A single dictionary entry.

    Stage 1 populates everything except :attr:`senses_vi` / :attr:`examples`;
    Stage 2 fills those in. An entry with an empty ``senses_vi`` is a
    *skeleton* entry — it still builds and still looks up on a real device,
    which is exactly what makes the week-1 device test possible.
    """

    id: str
    lang: str  # "en-vi" | "zh-vi"
    headword: str
    pos: str

    # Stage 1 — deterministic, free, safe to regenerate at any time.
    pron: str = ""  # IPA for EN, pinyin for ZH
    inflections: list[str] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)  # spelling / traditional forms
    gloss_en: list[str] = field(default_factory=list)  # short source-language gloss

    # Stage 2 — costs money, incremental, cached.
    senses_vi: list[str] = field(default_factory=list)
    #: The English side of :attr:`senses_vi`, index for index. Distinct from
    #: :attr:`gloss_en`, which is WordNet's own sense list in WordNet's own
    #: order and shares no alignment with the Vietnamese — the noun *go* is
    #: ``gloss_en[0] = "a time period for working"`` against
    #: ``senses_vi[0] = "cờ vây"``. Only a Stage 2 pass that emits both halves
    #: of a sense together can fill this, so it is empty on every entry that
    #: came from Wiktionary matching, and the renderer keys off exactly that:
    #: an English line is shown beside a Vietnamese sense only where this list
    #: says which sense it belongs to.
    senses_en: list[str] = field(default_factory=list)
    examples: list[Example] = field(default_factory=list)
    phrases: list[Phrase] = field(default_factory=list)

    # Bookkeeping.
    freq_tier: int = MAX_TIER
    freq: float = 0.0  # Zipf frequency, 0 = unknown
    source: str = ""  # "wordnet+cmudict" -> "hnd+wordnet+llm"
    reviewed: bool = False
    extra: dict[str, Any] = field(default_factory=dict)  # zh: hanviet, radical...

    # -- derived ----------------------------------------------------------

    @property
    def is_skeleton(self) -> bool:
        return not self.senses_vi

    @property
    def lookup_forms(self) -> list[str]:
        """Every string that must resolve to this entry on a device.

        This is the single most important list in the project: pain point #1
        is that ``stopped`` does not find ``stop``.
        """
        seen: dict[str, None] = {self.headword: None}
        for form in (*self.inflections, *self.variants):
            seen.setdefault(form, None)
        return list(seen)

    # -- serialization ----------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        """Compact dict with a stable key order; empty fields are omitted.

        Omitting defaults keeps JSONL lines short and, more importantly, keeps
        git diffs readable when Stage 2 fills a field in later.
        """
        d: dict[str, Any] = {
            "id": self.id,
            "lang": self.lang,
            "headword": self.headword,
            "pos": self.pos,
        }
        if self.pron:
            d["pron"] = self.pron
        if self.inflections:
            d["inflections"] = self.inflections
        if self.variants:
            d["variants"] = self.variants
        if self.gloss_en:
            d["gloss_en"] = self.gloss_en
        if self.senses_vi:
            d["senses_vi"] = self.senses_vi
        if self.senses_en:
            d["senses_en"] = self.senses_en
        if self.examples:
            d["examples"] = [e.to_json() for e in self.examples]
        if self.phrases:
            d["phrases"] = [p.to_json() for p in self.phrases]
        d["freq_tier"] = self.freq_tier
        if self.freq:
            d["freq"] = round(self.freq, 2)
        if self.source:
            d["source"] = self.source
        if self.reviewed:
            d["reviewed"] = True
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Entry":
        return cls(
            id=d.get("id", ""),
            lang=d.get("lang", ""),
            headword=d.get("headword", ""),
            pos=d.get("pos", ""),
            pron=d.get("pron", ""),
            inflections=list(d.get("inflections", [])),
            variants=list(d.get("variants", [])),
            gloss_en=list(d.get("gloss_en", [])),
            senses_vi=list(d.get("senses_vi", [])),
            senses_en=list(d.get("senses_en", [])),
            examples=[Example.from_json(e) for e in d.get("examples", [])],
            phrases=[Phrase.from_json(p) for p in d.get("phrases", [])],
            freq_tier=int(d.get("freq_tier", MAX_TIER)),
            freq=float(d.get("freq", 0.0)),
            source=d.get("source", ""),
            reviewed=bool(d.get("reviewed", False)),
            extra=dict(d.get("extra", {})),
        )

    def to_line(self) -> str:
        return json.dumps(self.to_json(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_line(cls, line: str) -> "Entry":
        return cls.from_json(json.loads(line))


# --------------------------------------------------------------------------
# Ids
# --------------------------------------------------------------------------


def slug(text: str) -> str:
    """Reversible, ASCII, filename-safe slug of a headword.

    Spaces become ``_``; anything outside :data:`_SLUG_SAFE` becomes ``~XX``
    (hex of each UTF-8 byte). Being injective matters: two different headwords
    must never collapse onto the same id, or one silently shadows the other.
    """
    text = unicodedata.normalize("NFC", text).strip().lower()
    out: list[str] = []
    for ch in text:
        if ch == " ":
            out.append("_")
        elif ch in _SLUG_SAFE:
            out.append(ch)
        else:
            out.extend(f"~{b:02x}" for b in ch.encode("utf-8"))
    return "".join(out)


def make_id(lang: str, headword: str, pos: str, disc: str = "") -> str:
    """Build a stable entry id.

    ``disc`` disambiguates entries that share (headword, pos) — ZH-VI needs it
    for 行 xíng vs 行 háng. It is appended to the slug, not the pos, so the pos
    segment stays a clean part-of-speech token.
    """
    lang_code = lang.split("-")[0]
    body = slug(headword)
    if disc:
        body = f"{body}.{slug(disc)}"
    return f"{lang_code}:{body}:{pos}"


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def _clean_str_list(name: str, values: list[Any], errors: list[str]) -> None:
    seen: set[str] = set()
    for v in values:
        if not isinstance(v, str):
            errors.append(f"{name}: non-string element {v!r}")
        elif not v.strip():
            errors.append(f"{name}: empty element")
        elif _CONTROL_RE.search(v):
            errors.append(f"{name}: control character in {v!r}")
        elif v in seen:
            errors.append(f"{name}: duplicate element {v!r}")
        else:
            seen.add(v)


def validate_entry(entry: Entry) -> list[str]:
    """Return a list of human-readable problems; empty list means valid."""
    errors: list[str] = []

    if entry.lang not in POS_BY_LANG:
        errors.append(f"lang: unknown language pair {entry.lang!r}")

    if not _ID_RE.match(entry.id):
        errors.append(f"id: malformed {entry.id!r} (want lang:slug:pos)")

    if not entry.headword.strip():
        errors.append("headword: empty")
    elif entry.headword != entry.headword.strip():
        errors.append(f"headword: untrimmed whitespace in {entry.headword!r}")
    elif _CONTROL_RE.search(entry.headword):
        errors.append(f"headword: control character in {entry.headword!r}")
    elif '"' in entry.headword:
        # dictgen rejects these outright, and idx:orth value="..." would break.
        errors.append(f'headword: contains a double quote: {entry.headword!r}')

    allowed = POS_BY_LANG.get(entry.lang, set())
    if allowed and entry.pos not in allowed:
        errors.append(f"pos: {entry.pos!r} not valid for {entry.lang}")

    if entry.freq_tier not in FREQ_TIERS:
        errors.append(f"freq_tier: {entry.freq_tier!r} not in {FREQ_TIERS}")

    if entry.freq < 0:
        errors.append(f"freq: negative ({entry.freq})")

    _clean_str_list("inflections", entry.inflections, errors)
    _clean_str_list("variants", entry.variants, errors)
    _clean_str_list("senses_vi", entry.senses_vi, errors)
    _clean_str_list("senses_en", entry.senses_en, errors)
    # The whole value of senses_en is that index i means the same sense on both
    # sides. A ragged pair is worse than no pair: it would put an English line
    # against a Vietnamese sense it does not describe, which is the bug the
    # field exists to end.
    if entry.senses_en and len(entry.senses_en) != len(entry.senses_vi):
        errors.append(
            f"senses_en: {len(entry.senses_en)} entries against "
            f"{len(entry.senses_vi)} in senses_vi (must align index for index)"
        )
    _clean_str_list("gloss_en", entry.gloss_en, errors)

    for ex in entry.examples:
        if not ex.src.strip():
            errors.append("examples: entry with empty source sentence")
    for ph in entry.phrases:
        if not ph.text.strip():
            errors.append("phrases: entry with empty text")

    # A reviewed entry with no Vietnamese sense is a review-process bug: it
    # means somebody ticked the box on an entry that has nothing to review.
    if entry.reviewed and not entry.senses_vi:
        errors.append("reviewed: true but senses_vi is empty")

    return errors


def validate_all(entries: Iterable[Entry]) -> list[str]:
    """Validate a whole corpus, including cross-entry checks (duplicate ids)."""
    errors: list[str] = []
    seen_ids: dict[str, int] = {}

    for n, entry in enumerate(entries, 1):
        for err in validate_entry(entry):
            errors.append(f"{entry.id or f'<entry #{n}>'}: {err}")
        if entry.id in seen_ids:
            errors.append(f"{entry.id}: duplicate id (first seen at entry #{seen_ids[entry.id]})")
        else:
            seen_ids[entry.id] = n

    return errors


__all__ = [
    "Entry",
    "Example",
    "Phrase",
    "POS_BY_LANG",
    "POS_LABEL",
    "FREQ_TIERS",
    "MAX_TIER",
    "make_id",
    "slug",
    "validate_entry",
    "validate_all",
]
