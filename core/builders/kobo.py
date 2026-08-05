"""Kobo builder — dictfile (.df) -> dicthtml-*.zip via pgaskin/dictutil.

Kobo's format is undocumented by Kobo; dictgen is the reverse-engineered
generator everyone uses. We emit its ``.df`` intermediate, which is plain text
and diffable, then shell out to dictgen.

Vietnamese on a Kobo also needs redphx/kobo-tieng-viet — the stock firmware
will not offer a vi dictionary otherwise. That is an install-side concern
documented on the landing page, not a build-side one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..group import group_by_headword
from ..render import CSS_INLINE, EntryRenderer
from ..schema import Entry
from .common import DICTGEN_HELP, BuildMeta, BuildResult, find_dictgen

#: dictgen rejects these outright (they collide with its own markup). We strip
#: rather than fail, because a single bad sense should not kill a 150k build.
_FORBIDDEN = ("<w", "</w", "<html", "</html", "<var", "</var", "<a name=")


def _sanitize(html_text: str) -> str:
    for bad in _FORBIDDEN:
        if bad in html_text:
            html_text = html_text.replace(bad, bad.replace("<", "&lt;"))
    return html_text


def write_dictfile(
    entries: list[Entry],
    path: Path,
    *,
    renderer: EntryRenderer | None = None,
) -> tuple[int, int]:
    """Write the .df dictfile. Returns (headword count, variant count)."""
    renderer = renderer or EntryRenderer()
    groups = group_by_headword(entries)

    path.parent.mkdir(parents=True, exist_ok=True)
    headwords = 0
    variants = 0

    with path.open("w", encoding="utf-8") as fh:
        # The stylesheet is emitted once, on the first entry; Kobo keeps it for
        # the whole dictionary.
        style = f"<style>{CSS_INLINE}</style>"
        first = True

        for group in groups:
            body = renderer.render_group(group)
            if first:
                body = style + body
                first = False

            fh.write(f"@ {group.headword}\n")
            # '::' suppresses dictgen's own bolded headword — ours is already
            # in the rendered body, complete with IPA and part of speech.
            fh.write("::\n")
            for form in group.variants:
                fh.write(f"& {form}\n")
                variants += 1
            # The body must be one line: the dictfile parser is line-oriented
            # and would read a leading @/:/& on a wrapped line as a directive.
            fh.write("<html>" + _sanitize(body) + "\n\n")
            headwords += 1

    return headwords, variants


def build(
    entries: list[Entry],
    out_dir: Path,
    meta: BuildMeta,
    *,
    renderer: EntryRenderer | None = None,
    run_dictgen: bool = True,
    download_dictgen: bool = True,
) -> BuildResult:
    """Write the dictfile and, if dictgen is available, the dicthtml zip."""
    out_dir.mkdir(parents=True, exist_ok=True)
    df_path = out_dir / f"dicthtml-{meta.lang_in}-{meta.lang_out}.df"

    headwords, variants = write_dictfile(entries, df_path, renderer=renderer)

    warnings: list[str] = []
    artifacts: list[Path] = [df_path]

    dictgen = find_dictgen(download=download_dictgen) if run_dictgen else None
    if dictgen is None:
        warnings.append(DICTGEN_HELP)
    else:
        zip_path = out_dir / f"dicthtml-{meta.lang_in}-{meta.lang_out}.zip"
        proc = subprocess.run(
            [str(dictgen), "-o", str(zip_path), str(df_path)],
            capture_output=True,
            text=True,
        )
        if zip_path.exists() and proc.returncode == 0:
            artifacts.append(zip_path)
        else:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-15:]
            warnings.append("dictgen failed:\n    " + "\n    ".join(tail))

    return BuildResult(
        target="kobo",
        entry_count=len(entries),
        form_count=headwords + variants,
        artifacts=artifacts,
        warnings=warnings,
    )


__all__ = ["build", "write_dictfile"]
