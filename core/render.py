"""Shared entry renderer.

One renderer for all three targets (plan §6): content markup is produced here
and is identical everywhere; only the *lookup* markup around it differs, and
that lives in the individual builders. This is what keeps a Kindle entry and a
Kobo entry visually identical.

**The three-line budget.** A Kindle lookup pops up a window about three or four
lines tall; seeing more costs another tap that most readers never make. So the
layout is designed backwards from that: whatever a reader needs while reading
has to survive in three lines. That single constraint explains most of what
follows — the headword printed once for the whole group, senses run on rather
than stacked, the English gloss kept off any card that already has Vietnamese,
and no branding line at all (the dictionary's name is already in the popup's
title bar, from ``bookname`` in the .ifo and the OPF metadata).

CSS is restricted to a conservative subset. E-ink readers run old WebKit forks
with no flexbox/grid support, and hierarchy is carried by size, weight and
italics rather than shades of grey — a panel with no backlight, read in a dim
room, does not reliably distinguish #444 from #666 from #888.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from jinja2 import Environment
from markupsafe import escape

from .schema import Entry, POS_LABEL

#: Shown instead of senses in a Stage 1 build. Visible on purpose: when you are
#: testing lookup on a real Kindle you must be able to tell at a glance that the
#: dictionary found the word but has no meaning yet, versus not finding it.
SKELETON_NOTE = "— chưa có nghĩa tiếng Việt (bản skeleton) —"


def minify_css(css: str) -> str:
    """Collapse a stylesheet onto one line.

    Required for the Kobo dictfile, whose parser is line-oriented: a stylesheet
    embedded in a definition must not contain newlines that could be mistaken
    for its ``@``/``:``/``&`` directives. Harmless (and smaller) elsewhere.
    """
    css = re.sub(r"\s+", " ", css)
    return re.sub(r"\s*([{}:;,])\s*", r"\1", css).strip()


#: Kept inline in every chunk file rather than as a separate stylesheet: the
#: Kobo and StarDict containers have nowhere to put a shared CSS file.
CSS = """\
body { font-family: serif; margin: 0; padding: 0; }
.e { margin: 0 0 0.7em 0; padding: 0; }
.hw { font-size: 1.2em; font-weight: bold; margin: 0 0 0.12em 0; }
.hw .ipa { font-weight: normal; font-size: 0.82em; }
.blk { margin: 0 0 0.35em 0; }
.pos { font-weight: bold; font-size: 0.8em; }
.sn b { font-weight: bold; }
.skel { font-size: 0.85em; font-style: italic; color: #555; margin: 0.2em 0 0 0; }
.ex { margin: 0.15em 0 0 0.9em; padding: 0; list-style: none; }
.ex li { font-size: 0.9em; font-style: italic; margin: 0 0 0.1em 0; }
.ph { margin: 0.15em 0 0 0.9em; padding: 0; list-style: none; }
.ph li { font-size: 0.9em; margin: 0 0 0.1em 0; }
.gl { font-size: 0.82em; font-style: italic; color: #555; }
.inf { font-size: 0.8em; color: #555; margin: 0.15em 0 0 0; }
.xr { font-size: 0.9em; margin: 0.15em 0 0 0; }
"""

#: Single-line form, used by the builders that embed CSS inside an entry body.
CSS_INLINE = minify_css(CSS)

# Whitespace control (``-%}``) matters here: without it Jinja leaves newlines
# between tags, and the Kobo dictfile format treats a bare newline inside a
# definition as content.
_TEMPLATE = """\
<div class="e">\
<div class="hw">{{ headword }}{% if pron %} <span class="ipa">{{ pron }}</span>{% endif %}</div>\
{%- for b in blocks %}<div class="blk">\
{%- if b.pos %}<span class="pos">{{ b.pos }}</span>{% endif %}\
{%- if b.senses %} <span class="sn">{{ b.senses }}</span>{% endif %}\
{%- if b.gloss_inline %} <span class="gl">{{ b.gloss_inline }}</span>{% endif %}\
{%- if b.examples %}<ul class="ex">{% for ex in b.examples %}<li>{{ ex }}</li>{% endfor %}</ul>{% endif %}\
{%- if b.phrases %}<ul class="ph">{% for p in b.phrases %}<li>{{ p }}</li>{% endfor %}</ul>{% endif %}\
{%- if b.inflections %}<div class="inf">Dạng khác: {{ b.inflections }}</div>{% endif %}\
</div>{% endfor %}\
{%- if skeleton_note %}<div class="skel">{{ skeleton_note }}</div>{% endif %}\
{%- if xref %}<div class="xr">▸ dạng của {{ xref }}</div>{% endif %}\
</div>\
"""


@dataclass(slots=True)
class RenderOptions:
    """Knobs that differ between a skeleton build and a release build."""

    #: Cap on senses shown. Plan §3.3: 4–5 main senses, rare ones dropped.
    max_senses: int = 5
    max_examples: int = 2
    max_phrases: int = 6
    #: Show the short English gloss. Solves pain point #3 (cross-referencing an
    #: English–English dictionary for polysemous words).
    show_gloss: bool = True
    #: A WordNet gloss runs to 140 characters and would swallow the whole
    #: popup; the plan asks for "1 dòng định nghĩa tiếng Anh ngắn".
    gloss_max_chars: int = 60
    #: Allow the inflected-form line. Even when on it is only drawn for entries
    #: that have no Vietnamese sense — see :meth:`EntryRenderer._block`.
    show_inflections: bool = False
    skeleton_note: str = SKELETON_NOTE


@dataclass(slots=True)
class _Block:
    """One part-of-speech section, pre-escaped and ready for the template.

    ``pos`` may be empty, and then no label is drawn at all: the attribution
    entry (core/attribution.py) is not a word and has no part of speech, so
    labelling it ``n.`` would be a lie printed on every device.
    """

    pos: str
    senses: str = ""
    gloss_inline: str = ""
    examples: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)
    inflections: str = ""


def shorten(text: str, limit: int) -> str:
    """Truncate at a word boundary, with an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return (cut or text[:limit]) + "…"


class EntryRenderer:
    """Renders :class:`Entry` objects to the shared content HTML."""

    def __init__(self, options: RenderOptions | None = None) -> None:
        self.options = options or RenderOptions()
        # autoescape=False because we escape explicitly below; the template
        # inserts already-escaped strings and a second pass would double-encode
        # every ``&`` in the data.
        self._env = Environment(autoescape=False, trim_blocks=False, lstrip_blocks=False)
        self._template = self._env.from_string(_TEMPLATE)

    # -- pieces -----------------------------------------------------------

    def _gloss(self, entry: Entry) -> str:
        """The English line for an entry that has no Vietnamese sense.

        ``gloss_en`` is WordNet's sense list; ``senses_vi`` is Wiktionary's or
        the LLM's. They are separate sense inventories in separate orders, and
        nothing aligns them — not even at index 0. The noun *go* is "cờ vây" in
        Vietnamese and "a time period for working" in WordNet; the noun *run* is
        "chạy" against "a score in baseball". So this gloss is only ever drawn
        where there is no Vietnamese for it to be mistaken as a caption for.

        A card that has Vietnamese shows no English at all — see :meth:`_senses`.
        This one is the exception that proves it: with ``senses_vi`` empty there
        is nothing else on the card, and a headword with a skeleton note and no
        content answers no lookup at all.
        """
        opt = self.options
        if not (opt.show_gloss and entry.gloss_en) or entry.senses_vi:
            return ""
        # One gloss, not several joined by "; ". WordNet lists distinct senses
        # there and concatenating them produces a wall of English.
        return str(escape(shorten(entry.gloss_en[0], opt.gloss_max_chars)))

    def _senses(self, senses: list[str]) -> str:
        """The Vietnamese sense list, run on rather than stacked.

        A numbered ``<ol>`` costs one line per sense and the popup only has
        three, so the senses share a line and carry their number inline.

        A card that has Vietnamese shows only Vietnamese — including inside the
        parentheses. :attr:`Entry.senses_en` is aligned and could be captioned
        here, and briefly was, but the Vietnamese senses already carry their own
        parenthetical context by convention (``(nước) chảy``), and adding a
        second parenthetical in another language behind it made 19% of senses
        say the same thing twice in two alphabets:

            tòa án gia đình (chuyên xử tranh chấp gia đình, đặc biệt liên quan
            trẻ em) (court for family disputes, especially…)

        The field stays populated — it is what a reviewer needs in order to tell
        which English sense a Vietnamese line is answering — it just does not
        reach the screen.
        """
        if len(senses) == 1:
            return str(escape(senses[0]))
        return " ".join(
            f"<b>{i + 1}.</b> {escape(s)}" for i, s in enumerate(senses)
        )

    def _block(self, entry: Entry) -> _Block:
        opt = self.options
        senses = entry.senses_vi[: opt.max_senses]
        senses_html = self._senses(senses) if senses else ""

        return _Block(
            pos=str(escape(POS_LABEL.get(entry.pos, entry.pos))),
            senses=senses_html,
            # A gloss only survives _gloss() on an entry with no senses, where it
            # carries the block on its own — so it sits on the part-of-speech
            # line and never needs a line to itself.
            gloss_inline=self._gloss(entry),
            examples=[
                f"· {escape(ex.src)}" + (f" — {escape(ex.vi)}" if ex.vi else "")
                for ex in entry.examples[: opt.max_examples]
            ],
            phrases=[
                f"▸ <b>{escape(p.text)}</b>" + (f": {escape(p.vi)}" if p.vi else "")
                for p in entry.phrases[: opt.max_phrases]
            ],
            # Drawn only where it earns its line. The point of listing forms is
            # to check by eye that they resolved on a real device, and that only
            # needs checking on an entry with nothing else in it — a translated
            # entry proves the lookup worked by having answered. Gating per
            # entry rather than per build matters because the store is ~10%
            # translated, so the whole build presents as a skeleton and tier 1
            # was spending a line of a three-line popup on "Dạng khác: springs".
            inflections=(
                str(escape(", ".join(entry.inflections)))
                if opt.show_inflections and entry.inflections and not senses
                else ""
            ),
        )

    def _shell(self, headword: str, pron: str, blocks: list[_Block],
               *, skeleton: bool, xref: str = "") -> str:
        return self._template.render(
            headword=str(escape(headword)),
            pron=str(escape(pron)),
            blocks=blocks,
            skeleton_note=str(escape(self.options.skeleton_note)) if skeleton else "",
            xref=xref,
        )

    # -- public -----------------------------------------------------------

    def render(self, entry: Entry) -> str:
        """Render one entry standalone.

        Used by the MOBI builder, where every entry is its own ``idx:entry``
        and Kindle shows each match as a separate card — so each one needs its
        own headword line.
        """
        return self._shell(
            entry.headword,
            entry.pron,
            [self._block(entry)],
            skeleton=not entry.senses_vi,
        )

    def render_group(self, group) -> str:
        """Render a whole :class:`core.group.HeadwordGroup` as one page.

        The headword and pronunciation are printed once for the group rather
        than repeated per part of speech, and the cross-reference line points
        ``abandoned`` at the verb ``abandon`` on formats that show a single
        page per headword.
        """
        entries = group.entries
        if not entries:
            return ""

        pron = next((e.pron for e in entries if e.pron), "")
        blocks = [self._block(e) for e in entries]

        xref = ""
        if group.xrefs:
            xref = ", ".join(
                f"<b>{escape(base)}</b> ({escape(POS_LABEL.get(pos, pos))})"
                for base, pos in group.xrefs
            )

        return self._shell(
            group.headword,
            pron,
            blocks,
            skeleton=not any(e.senses_vi for e in entries),
            xref=xref,
        )


__all__ = ["EntryRenderer", "RenderOptions", "CSS", "CSS_INLINE", "SKELETON_NOTE", "shorten"]
