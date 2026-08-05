"""StarDict builder — .ifo / .idx / .dict(.dz) / .syn, in pure Python.

Widest reach of the three targets (plan §6): KOReader (on Kindle, Kobo and
PocketBook), Boox, GoldenDict and — via the same files — MDict. It is also the
only target with no external toolchain, so it is the one that always builds:
when kindlegen is missing, this is still a dictionary you can put on a device
today.

Written directly rather than through PyGlossary because ``.syn`` support is the
whole point of this project (pain point #1) and we need exact control over the
index sort order, which must match the reader's binary-search comparator or
lookups silently fail.
"""

from __future__ import annotations

import struct
from pathlib import Path

from ..group import group_by_headword
from ..render import CSS_INLINE, EntryRenderer
from ..schema import Entry
from . import dictzip
from .common import BuildMeta, BuildResult

# -- Sort order -------------------------------------------------------------
# StarDict compares index words with stardict_strcmp():
#     a = g_ascii_strcasecmp(s1, s2);  return a ? a : strcmp(s1, s2);
# g_ascii_strcasecmp lowercases ASCII only and compares glib's gchar, which is
# *signed* — so bytes >= 0x80 sort before ASCII. Translating each byte by
# +128 (mod 256) turns that signed comparison into an ordinary unsigned byte
# comparison, which is what Python's bytes ordering gives us.
_SIGNED = bytes((b + 128) % 256 for b in range(256))
_ASCII_LOWER = bytes(b + 32 if 65 <= b <= 90 else b for b in range(256))


def sort_key(word: str) -> tuple[bytes, bytes]:
    raw = word.encode("utf-8")
    return raw.translate(_ASCII_LOWER).translate(_SIGNED), raw.translate(_SIGNED)


def build(
    entries: list[Entry],
    out_dir: Path,
    meta: BuildMeta,
    *,
    renderer: EntryRenderer | None = None,
    basename: str = "",
    compress: bool = True,
) -> BuildResult:
    """Write a complete StarDict dictionary into ``out_dir``."""
    renderer = renderer or EntryRenderer()
    basename = basename or f"thichhoc-{meta.lang_in}-{meta.lang_out}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # (run, n) and (run, v) are separate entries in our store but must be a
    # single lookup result, or the reader shows one of them arbitrarily and the
    # other is unreachable.
    groups = group_by_headword(entries)
    groups.sort(key=lambda g: sort_key(g.headword))

    dict_parts: list[bytes] = []
    idx_parts: list[bytes] = []
    offset = 0
    index_of: dict[str, int] = {}

    style = f"<style>{CSS_INLINE}</style>".encode("utf-8")

    for position, group in enumerate(groups):
        word = group.headword
        body = renderer.render_group(group).encode("utf-8")
        # The stylesheet rides along with the first entry only; readers that
        # concatenate results still pick it up, and repeating it 150k times
        # would add tens of megabytes.
        data = (style + body) if position == 0 else body

        if offset + len(data) > 0xFFFFFFFF:
            raise ValueError("dictionary exceeds the 4 GiB limit of 32-bit offsets")

        idx_parts.append(word.encode("utf-8") + b"\x00" + struct.pack(">II", offset, len(data)))
        dict_parts.append(data)
        index_of[word] = position
        offset += len(data)

    # -- .syn: every inflected form that is not itself a headword ----------
    # A form that *is* a headword already has an .idx record, and readers
    # resolve .idx first; grouping has put a cross-reference on that page
    # instead, so nothing is lost.
    syn_pairs: set[tuple[str, int]] = {
        (form, index_of[group.headword])
        for group in groups
        for form in group.variants
    }

    syn_parts = [
        form.encode("utf-8") + b"\x00" + struct.pack(">I", target)
        for form, target in sorted(syn_pairs, key=lambda p: (sort_key(p[0]), p[1]))
    ]

    idx_blob = b"".join(idx_parts)
    syn_blob = b"".join(syn_parts)
    dict_blob = b"".join(dict_parts)

    artifacts: list[Path] = []

    idx_path = out_dir / f"{basename}.idx"
    idx_path.write_bytes(idx_blob)
    artifacts.append(idx_path)

    if syn_blob:
        syn_path = out_dir / f"{basename}.syn"
        syn_path.write_bytes(syn_blob)
        artifacts.append(syn_path)

    if compress:
        dict_path = out_dir / f"{basename}.dict.dz"
        dictzip.write(dict_path, dict_blob)
    else:
        dict_path = out_dir / f"{basename}.dict"
        dict_path.write_bytes(dict_blob)
    artifacts.append(dict_path)

    ifo_lines = [
        "StarDict's dict ifo file",
        "version=2.4.2",
        f"bookname={meta.name}",
        f"wordcount={len(groups)}",
    ]
    if syn_parts:
        ifo_lines.append(f"synwordcount={len(syn_parts)}")
    ifo_lines += [
        f"idxfilesize={len(idx_blob)}",
        "sametypesequence=h",
        f"author={meta.author}",
    ]
    # The .ifo has no license field, so the license rides in `description` —
    # which is the field a reader's dictionary manager displays, and therefore
    # the one place in this format where a credit reaches the person holding
    # the device. `website` is spec'd, so the source stays one lookup away.
    description = meta.description or meta.name
    if meta.license:
        description = f"{description} Dữ liệu: {meta.license}."
    ifo_lines.append(f"description={description}")
    if meta.homepage:
        ifo_lines.append(f"website={meta.homepage}")
    if meta.date:
        ifo_lines.append(f"date={meta.date}")

    ifo_path = out_dir / f"{basename}.ifo"
    ifo_path.write_text("\n".join(ifo_lines) + "\n", encoding="utf-8")
    artifacts.insert(0, ifo_path)

    return BuildResult(
        target="stardict",
        entry_count=len(entries),
        form_count=len(groups) + len(syn_parts),
        artifacts=artifacts,
    )


__all__ = ["build", "sort_key"]
