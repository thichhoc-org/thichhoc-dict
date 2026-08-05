"""Shared plumbing for the builders: metadata, results, toolchain discovery."""

from __future__ import annotations

import os
import shutil
import stat
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class BuildMeta:
    """Everything the container formats need to describe a dictionary."""

    name: str  # "Từ điển Anh–Việt thichhoc.com"
    lang_in: str  # "en"
    lang_out: str  # "vi"
    version: str  # "0.1.0-skeleton"
    author: str = "thichhoc.com"
    description: str = ""
    #: Data license and project URL. Carried in the container metadata of every
    #: format that has somewhere to put them, because the attribution CC BY-SA
    #: requires has to survive being copied out of its release bundle — see
    #: core/attribution.py.
    license: str = ""  # "CC BY-SA 4.0"
    homepage: str = ""
    # ISO date as a plain string — builds must be reproducible, so the caller
    # supplies this rather than the builder reading the clock.
    date: str = ""


@dataclass(slots=True)
class BuildResult:
    """What a builder produced, and what it could not finish."""

    target: str
    entry_count: int
    form_count: int  # total lookup forms, incl. inflections
    artifacts: list[Path] = field(default_factory=list)
    #: Non-fatal problems: a missing external tool leaves the intermediate
    #: source on disk and records why the final artifact is absent.
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.artifacts) and not self.warnings

    def describe(self) -> str:
        lines = [
            f"{self.target}: {self.entry_count:,} entries, {self.form_count:,} lookup forms"
        ]
        lines += [f"  -> {p}" for p in self.artifacts]
        lines += [f"  !  {w}" for w in self.warnings]
        return "\n".join(lines)


def chunked(items: list, size: int) -> list[list]:
    """Split a list into fixed-size chunks (kindlegen chokes on huge files)."""
    return [items[i : i + size] for i in range(0, len(items), size)]


# --------------------------------------------------------------------------
# External toolchain
# --------------------------------------------------------------------------

TOOLS_DIR = Path(".tools")

#: Where Kindle Previewer 3 hides kindlegen on each platform. Amazon stopped
#: shipping kindlegen standalone, so the Previewer bundle is now the only
#: legitimate source.
KINDLEGEN_CANDIDATES = [
    "/Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen",
    "/Applications/Kindle Previewer 3.app/Contents/MacOS/lib/fc/bin/kindlegen",
    str(Path.home() / "Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen"),
    str(Path(os.environ.get("LOCALAPPDATA", "")) / "Amazon/Kindle Previewer 3/lib/fc/bin/kindlegen.exe"),
]

KINDLEGEN_HELP = (
    "kindlegen not found. Install Kindle Previewer 3 "
    "(https://www.amazon.com/Kindle-Previewer/b?node=21381691011) — it bundles "
    "kindlegen — or set KINDLEGEN=/path/to/kindlegen. The unpacked MOBI source "
    "has still been written and can be built on any machine that has it."
)

DICTGEN_URL = (
    "https://github.com/pgaskin/dictutil/releases/latest/download/dictgen-{platform}"
)

DICTGEN_HELP = (
    "dictgen not found and could not be downloaded. Get it from "
    "https://github.com/pgaskin/dictutil/releases and put it on PATH, or set "
    "DICTGEN=/path/to/dictgen. The .df dictfile has still been written."
)


def find_kindlegen() -> Path | None:
    """Locate kindlegen: $KINDLEGEN, then PATH, then Kindle Previewer 3."""
    env = os.environ.get("KINDLEGEN")
    if env and Path(env).exists():
        return Path(env)
    found = shutil.which("kindlegen")
    if found:
        return Path(found)
    for candidate in KINDLEGEN_CANDIDATES:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def _dictgen_platform() -> str | None:
    import platform as _platform

    system = _platform.system()
    machine = _platform.machine().lower()
    if system == "Darwin":
        # The darwin build is amd64-only; Rosetta 2 runs it on Apple silicon.
        return "darwin-64bit"
    if system == "Linux":
        if machine in ("x86_64", "amd64"):
            return "linux-64bit"
        if machine in ("i386", "i686"):
            return "linux-32bit"
        if machine.startswith("arm") or machine == "aarch64":
            return "linux-arm"
    if system == "Windows":
        return "windows.exe"
    return None


def find_dictgen(*, download: bool = True, tools_dir: Path = TOOLS_DIR) -> Path | None:
    """Locate dictgen, downloading the official release binary if allowed."""
    env = os.environ.get("DICTGEN")
    if env and Path(env).exists():
        return Path(env)
    found = shutil.which("dictgen")
    if found:
        return Path(found)

    platform_tag = _dictgen_platform()
    if platform_tag is None:
        return None

    cached = tools_dir / f"dictgen-{platform_tag}"
    if cached.exists():
        return cached
    if not download:
        return None

    tools_dir.mkdir(parents=True, exist_ok=True)
    url = DICTGEN_URL.format(platform=platform_tag)
    try:
        tmp = cached.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
        tmp.chmod(tmp.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        tmp.replace(cached)
    except Exception:
        return None
    return cached


__all__ = [
    "BuildMeta",
    "BuildResult",
    "chunked",
    "find_kindlegen",
    "find_dictgen",
    "KINDLEGEN_HELP",
    "DICTGEN_HELP",
]
