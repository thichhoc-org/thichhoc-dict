"""Path bootstrap shared by the pipeline scripts.

The project directory is ``dict-en-vi`` — a hyphen, so it is not an importable
Python package. The pipeline scripts are therefore run as files, and this
module puts the repo root on ``sys.path`` so they can ``import core``.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_DIR.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATA_DIR = PROJECT_DIR / "data"
RAW_DIR = DATA_DIR / "source" / "raw"
WORK_DIR = DATA_DIR / "work"
ENTRIES_DIR = DATA_DIR / "entries"
OVERRIDES = DATA_DIR / "overrides" / "corrections.jsonl"
TESTS_DIR = PROJECT_DIR / "tests"

LANG = "en-vi"

WORDNET_DIR = RAW_DIR / "wordnet"
CMUDICT = RAW_DIR / "cmudict" / "cmudict.dict"
HUNSPELL_AFF = RAW_DIR / "hunspell" / "en_US.aff"
HUNSPELL_DIC = RAW_DIR / "hunspell" / "en_US.dic"


def require(path: Path, hint: str = "make download") -> Path:
    if not path.exists():
        raise SystemExit(f"missing {path}\nRun `{hint}` first.")
    return path


def ensure_work() -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    return WORK_DIR
