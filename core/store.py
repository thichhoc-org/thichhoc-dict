"""Sharded JSONL entry store — the on-disk database, kept in git.

Deliberately not a database (plan §5): one entry per line, sorted, split into
small files means `git diff` shows exactly which senses a PR changed, and a
reviewer can read that diff. The cost is that we re-sort on write; that is
cheap next to the benefit of reviewable data.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable, Iterator

from .schema import Entry

#: Target lines per shard. Small enough that a diff stays readable and GitHub
#: still renders the file; see plan §5 ("JSONL ~1-2k entry/file").
SHARD_SIZE = 2000

_ASCII_LOWER = "abcdefghijklmnopqrstuvwxyz"


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def shard_paths(entries_dir: Path) -> list[Path]:
    """All shard files, in a stable order."""
    return sorted(entries_dir.glob("*.jsonl"))


def iter_entries(entries_dir: Path) -> Iterator[Entry]:
    """Stream every entry in the store, shard by shard."""
    for path in shard_paths(entries_dir):
        yield from iter_shard(path)


def iter_shard(path: Path) -> Iterator[Entry]:
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield Entry.from_line(line)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(f"{path}:{lineno}: malformed JSONL line: {exc}") from exc


def load_entries(entries_dir: Path) -> list[Entry]:
    return list(iter_entries(entries_dir))


def load_index(entries_dir: Path) -> dict[str, Entry]:
    """Entries keyed by id. Used by tools/entry.py and Stage 2 resume."""
    return {e.id: e for e in iter_entries(entries_dir)}


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def default_group(entry: Entry) -> str:
    """Pick the shard group for an entry.

    Tier 1 lives in its own file because it is the set reviewed 100% — keeping
    it together means a reviewer can open one file and see their whole queue.
    """
    if entry.freq_tier == 1:
        return "freq-tier1"
    first = entry.headword[:1].lower()
    return f"general-{first}" if first in _ASCII_LOWER else "general-other"


def write_shards(
    entries_dir: Path,
    entries: Iterable[Entry],
    *,
    shard_size: int = SHARD_SIZE,
    group_of: Callable[[Entry], str] = default_group,
    prune: bool = True,
) -> dict[str, int]:
    """Write entries out as sorted shards; returns {filename: line count}.

    Any pre-existing ``*.jsonl`` no longer produced is deleted when ``prune``
    is set, so a shrinking corpus does not leave stale entries behind that
    would then be silently built into a release.
    """
    entries_dir.mkdir(parents=True, exist_ok=True)

    groups: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        groups[group_of(entry)].append(entry)

    written: dict[str, int] = {}
    for group, items in groups.items():
        items.sort(key=lambda e: (e.headword.lower(), e.pos, e.id))
        # A group that fits in one shard keeps its bare name (freq-tier1.jsonl);
        # only split groups get numeric suffixes.
        if len(items) <= shard_size:
            chunks = [(f"{group}.jsonl", items)]
        else:
            chunks = [
                (f"{group}-{i // shard_size + 1:02d}.jsonl", items[i : i + shard_size])
                for i in range(0, len(items), shard_size)
            ]
        for name, chunk in chunks:
            path = entries_dir / name
            path.write_text(
                "".join(e.to_line() + "\n" for e in chunk),
                encoding="utf-8",
            )
            written[name] = len(chunk)

    if prune:
        for path in shard_paths(entries_dir):
            if path.name not in written:
                path.unlink()

    return written


def write_single(path: Path, entries: Iterable[Entry]) -> int:
    """Write one flat JSONL file (used for overrides and debug dumps)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(entry.to_line() + "\n")
            count += 1
    return count


# --------------------------------------------------------------------------
# Overrides
# --------------------------------------------------------------------------


def apply_overrides(entries: list[Entry], overrides_path: Path) -> tuple[list[Entry], int]:
    """Merge hand-written corrections over generated entries.

    ``overrides/corrections.jsonl`` is how a reported bug gets fixed without
    touching generated data: the pipeline can be re-run at will and the
    correction survives (plan §7.6). Each override line is a partial entry —
    only the keys present are replaced.
    """
    if not overrides_path.exists():
        return entries, 0

    patches: dict[str, dict] = {}
    with overrides_path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            patch = json.loads(line)
            if "id" not in patch:
                raise ValueError(f"{overrides_path}:{lineno}: override without an id")
            patches[patch["id"]] = patch

    applied = 0
    out: list[Entry] = []
    for entry in entries:
        patch = patches.get(entry.id)
        if patch is None:
            out.append(entry)
            continue
        merged = entry.to_json()
        merged.update(patch)
        out.append(Entry.from_json(merged))
        applied += 1

    # An override for an id that no longer exists is a silent no-op otherwise,
    # which is how corrections rot. Surface it as a new entry instead.
    known = {e.id for e in entries}
    for entry_id, patch in patches.items():
        if entry_id not in known and patch.get("headword"):
            out.append(Entry.from_json(patch))
            applied += 1

    return out, applied


__all__ = [
    "SHARD_SIZE",
    "iter_entries",
    "iter_shard",
    "load_entries",
    "load_index",
    "shard_paths",
    "write_shards",
    "write_single",
    "apply_overrides",
    "default_group",
]
