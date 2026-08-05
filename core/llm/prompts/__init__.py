"""Prompt templates and output schemas for Stage 2.

**License boundary.** Prompts may only carry data this project is licensed to
use — WordNet glosses, our own IPA, our own headword list. Nothing derived from
a commercial dictionary enters a prompt, because a paraphrase of licensed
content is still a derivative work (plan §3.1). That rule is the whole
reason thichhoc.com can put its name on the result, so it is enforced here at
the point where prompt content is assembled, not left to reviewer memory.
"""

from __future__ import annotations

import json
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

#: Response shape for English->Vietnamese sense translation. `additionalProperties`
#: must be false and every property listed in `required` for strict validation.
#:
#: Senses come back as *pairs*, not as a bare Vietnamese list. The earlier shape
#: returned only Vietnamese, which left the entry with two sense inventories that
#: nothing tied together: WordNet's ``gloss_en`` in WordNet's order, and the
#: model's Vietnamese in frequency order. The renderer could then not caption a
#: Vietnamese sense with its English without guessing — so it showed no English
#: at all. Asking the model to hand back the English it translated *from*, beside
#: each Vietnamese sense, is what makes that caption possible, and it costs a few
#: output tokens rather than a second pass.
EN_VI_SENSES_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "senses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "en": {
                        "type": "string",
                        "description": (
                            "The English sense this translates, in at most 8 words. "
                            "Condense the WordNet definition you worked from; do not "
                            "copy it verbatim."
                        ),
                    },
                    "vi": {
                        "type": "string",
                        "description": "The Vietnamese sense.",
                    },
                },
                "required": ["en", "vi"],
                "additionalProperties": False,
            },
            "minItems": 1,
            "maxItems": 4,
            "description": "Senses as English/Vietnamese pairs, most frequent first.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "How settled the Vietnamese rendering is; drives review priority.",
        },
    },
    "required": ["senses", "confidence"],
    "additionalProperties": False,
}


def load(name: str) -> str:
    """Read a prompt template by file stem."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"no prompt template at {path}")
    return path.read_text(encoding="utf-8")


#: Vietnamese only — the shape used from tier 4 onward. The English half of a
#: pair is generated text and so is billed as output: measured at 30% of the
#: characters a reply emits, against output being roughly half the bill. It
#: buys one thing, which is letting a reviewer see which English sense a
#: Vietnamese line answers, and the plan only commits to reviewing tier 1. So
#: it is paid for where review happens and not where it does not.
EN_VI_SENSES_SCHEMA_PLAIN: dict = {
    "type": "object",
    "properties": {
        "senses_vi": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 4,
            "description": "Vietnamese senses, most frequent first.",
        },
        "confidence": EN_VI_SENSES_SCHEMA["properties"]["confidence"],
    },
    "required": ["senses_vi", "confidence"],
    "additionalProperties": False,
}


def is_paired(schema: dict) -> bool:
    """True when the schema asks for {en, vi} pairs rather than bare senses.

    Derived from the schema rather than passed alongside it, so the prompt, the
    provider's shape instruction and the validator cannot disagree about which
    reply is being asked for.
    """
    items = (schema.get("properties", {}).get("senses", {}) or {}).get("items", {})
    return items.get("type") == "object"


def en_vi_system(schema: dict | None = None) -> str:
    """The lexicographic brief, plus the pairing section when it applies.

    The brief itself says nothing about JSON shape: that lives in the schema and
    in the provider's own instruction, which is what lets one set of
    lexicographic rules serve both shapes without being written twice and
    drifting.
    """
    text = load("en_vi_senses")
    if schema is not None and is_paired(schema):
        text += "\n" + load("en_vi_pairing")
    return text


def en_vi_user(headword: str, pos: str, pron: str, glosses: list[str]) -> str:
    """Build the per-entry user turn.

    Deliberately compact and in a fixed key order: this text sits after the
    cached system prompt, so it is the only part billed at full input rate.
    """
    payload = {
        "headword": headword,
        "pos": pos,
        "definitions_en": glosses,
    }
    if pron:
        payload["ipa"] = pron
    return json.dumps(payload, ensure_ascii=False)


__all__ = ["EN_VI_SENSES_SCHEMA", "EN_VI_SENSES_SCHEMA_PLAIN", "is_paired",
           "load", "en_vi_system", "en_vi_user", "PROMPTS_DIR"]
