"""Kindle MOBI builder — idx:entry / idx:orth / idx:iform markup + OPF.

The inflection markup here is the mechanism behind the project's headline
feature: ``<idx:iform value="stopped"/>`` is what makes a Kindle resolve
"stopped" to the "stop" entry without the user editing the word (pain point
#1, plan §3.2).

kindlegen turns the generated source into a .mobi. Amazon no longer ships it
standalone, so when it is absent we still write the complete, valid source
tree and say exactly how to finish the build — the expensive part (rendering
150k entries) is done either way.
"""

from __future__ import annotations

import html
import subprocess
from collections import defaultdict
from pathlib import Path

from ..group import HeadwordGroup, group_by_headword
from ..render import CSS, EntryRenderer
from ..schema import Entry
from .common import (
    KINDLEGEN_HELP,
    BuildMeta,
    BuildResult,
    chunked,
    find_kindlegen,
)

#: Headword cards per HTML file. kindlegen slows to a crawl and eventually fails on
#: very large files; ~10k keeps each chunk a few MB (plan §4.2).
CHUNK_ENTRIES = 10000

_HTML_HEAD = """\
<?xml version="1.0" encoding="utf-8"?>
<html xmlns:idx="www.mobipocket.com" xmlns:mbp="www.mobipocket.com"
      xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
<style type="text/css">
{css}</style>
</head>
<body>
<mbp:pagebreak/>
"""

_HTML_TAIL = """
</body>
</html>
"""

_OPF = """\
<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{title}</dc:title>
    <dc:creator opf:role="aut">{author}</dc:creator>
    <dc:publisher>{author}</dc:publisher>
    <dc:language>{lang_in}</dc:language>
    <dc:identifier id="uid">{uid}</dc:identifier>
    <dc:date>{date}</dc:date>
    <dc:description>{description}</dc:description>
    <dc:rights>{rights}</dc:rights>
    <x-metadata>
      <DictionaryInLanguage>{lang_in}</DictionaryInLanguage>
      <DictionaryOutLanguage>{lang_out}</DictionaryOutLanguage>
      <DefaultLookupIndex>default</DefaultLookupIndex>
    </x-metadata>
  </metadata>
  <manifest>
{manifest}
  </manifest>
  <spine>
{spine}
  </spine>
  <guide>
    <reference type="index" title="IndexName" href="{first_chunk}"/>
  </guide>
</package>
"""


def _esc_attr(value: str) -> str:
    """Escape for an XML attribute; kindlegen is unforgiving about raw & and <."""
    return html.escape(value, quote=True)


def render_group_markup(
    group: HeadwordGroup,
    renderer: EntryRenderer,
    anchor: str,
) -> str:
    """Wrap a whole headword — every part of speech — in one lookup card.

    Kindle returns every ``idx:entry`` whose orth or iform matches, but it
    *stacks* them, and the popup shows about one before the reader has to
    scroll. So one entry per part of speech meant looking up *table* showed the
    noun and hid the verb behind a swipe. One entry per headword puts them on
    consecutive lines of the same card, which is what the other two targets
    have always done via ``render_group``.

    The inflection list is the union across the group rather than
    ``group.variants``. That field drops forms that are themselves headwords,
    which is right for a format with one page per key and wrong here: Kindle
    can return several cards for one form, and dropping *abandoned* from
    *abandon*'s iform list would leave a lookup of "abandoned" showing the
    adjective and never the verb — the exact failure this project exists to fix.
    """
    body = renderer.render_group(group)

    # Only forms other than the headword go in idx:infl — the headword is
    # already matched by idx:orth's value.
    seen = {group.headword}
    inflections: list[str] = []
    for entry in group.entries:
        for form in entry.lookup_forms:
            if form not in seen:
                seen.add(form)
                inflections.append(form)
    infl = ""
    if inflections:
        iforms = "".join(f'<idx:iform value="{_esc_attr(f)}"/>' for f in inflections)
        infl = f"<idx:infl>{iforms}</idx:infl>"

    return (
        f'<idx:entry name="default" scriptable="yes" spell="yes">'
        f'<idx:short><a id="{anchor}"></a>'
        f'<idx:orth value="{_esc_attr(group.headword)}">{infl}</idx:orth>'
        f"{body}"
        f"</idx:short></idx:entry>"
        f"<mbp:pagebreak/>"
    )


def build(
    entries: list[Entry],
    out_dir: Path,
    meta: BuildMeta,
    *,
    renderer: EntryRenderer | None = None,
    basename: str = "",
    chunk_entries: int = CHUNK_ENTRIES,
    run_kindlegen: bool = True,
) -> BuildResult:
    """Write the MOBI source tree into ``out_dir`` and try to build a .mobi."""
    renderer = renderer or EntryRenderer()
    basename = basename or f"thichhoc-{meta.lang_in}-{meta.lang_out}"
    src_dir = out_dir / "mobi-src"
    src_dir.mkdir(parents=True, exist_ok=True)

    # group_by_headword orders the parts of speech inside a group by SemCor
    # frequency, so the reading a reader most likely wants is the first line of
    # the card rather than whichever part of speech sorts first alphabetically.
    groups = group_by_headword(entries)

    # The cross-reference line ("▸ dạng của abandon") earns its line on formats
    # that show exactly one page per key and would otherwise strand the reader.
    # Kindle resolves a form to every matching card at once, so here it points
    # at a card already on screen — a wasted line out of three.
    for group in groups:
        group.xrefs = []

    warnings: list[str] = []
    form_count = 0
    chunk_names: list[str] = []

    for n, chunk in enumerate(chunked(groups, chunk_entries), 1):
        pieces = [_HTML_HEAD.format(css=CSS)]
        for group in chunk:
            form_count += len({f for e in group.entries for f in e.lookup_forms})
            anchor = group.entries[0].id.replace(":", "_")
            pieces.append(render_group_markup(group, renderer, anchor))
        pieces.append(_HTML_TAIL)
        name = f"entries-{n:03d}.html"
        (src_dir / name).write_text("".join(pieces), encoding="utf-8")
        chunk_names.append(name)

    if not chunk_names:  # keep the OPF valid even for an empty corpus
        name = "entries-001.html"
        (src_dir / name).write_text(_HTML_HEAD.format(css=CSS) + _HTML_TAIL, encoding="utf-8")
        chunk_names.append(name)

    manifest = "\n".join(
        f'    <item id="c{i}" href="{name}" media-type="text/x-oeb1-document"/>'
        for i, name in enumerate(chunk_names, 1)
    )
    spine = "\n".join(f'    <itemref idref="c{i}"/>' for i in range(1, len(chunk_names) + 1))

    opf_path = src_dir / f"{basename}.opf"
    opf_path.write_text(
        _OPF.format(
            title=html.escape(meta.name),
            author=html.escape(meta.author),
            lang_in=meta.lang_in,
            lang_out=meta.lang_out,
            uid=f"thichhoc-{meta.lang_in}-{meta.lang_out}-{meta.version}",
            date=meta.date,
            description=html.escape(meta.description or meta.name),
            # dc:rights is the only field in this container that states the
            # data license, and it survives kindlegen into the .mobi — so a
            # copy of the file that has drifted away from its release bundle
            # still says what it is licensed under and where it came from.
            rights=html.escape(
                " ".join(x for x in (meta.license, meta.homepage) if x) or "—"
            ),
            manifest=manifest,
            spine=spine,
            first_chunk=chunk_names[0],
        ),
        encoding="utf-8",
    )

    artifacts: list[Path] = []
    mobi_path = out_dir / f"{basename}.mobi"

    kindlegen = find_kindlegen() if run_kindlegen else None
    if kindlegen is None:
        warnings.append(KINDLEGEN_HELP)
        artifacts.append(opf_path)
    else:
        proc = subprocess.run(
            [str(kindlegen), str(opf_path), "-c1", "-dont_append_source", "-o", mobi_path.name],
            capture_output=True,
            text=True,
        )
        built = src_dir / mobi_path.name
        # kindlegen returns 1 for warnings and still produces output; only a
        # missing file is a real failure.
        if built.exists():
            built.replace(mobi_path)
            artifacts.append(mobi_path)
            if proc.returncode != 0:
                warnings.append(f"kindlegen reported warnings (exit {proc.returncode})")
        else:
            tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-15:]
            warnings.append(
                "kindlegen failed to produce a .mobi:\n    " + "\n    ".join(tail)
            )
            artifacts.append(opf_path)

    return BuildResult(
        target="mobi",
        entry_count=len(groups),
        form_count=form_count,
        artifacts=artifacts,
        warnings=warnings,
    )


__all__ = ["build", "render_group_markup", "CHUNK_ENTRIES"]
