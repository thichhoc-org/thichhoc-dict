"""Provider-agnostic pieces of the Stage 2 LLM layer.

Everything here is true regardless of which model translates the entries: the
unit of work, the result shape, token accounting, and the resume cache. The
provider modules under ``providers/`` add only the parts that genuinely differ.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class Job:
    """One entry to translate. ``id`` is the entry id and the cache key."""

    id: str
    content: str


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    #: Tokens served from a prompt cache. Every provider prices these lower,
    #: but by different multipliers, so the split is kept rather than merged.
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


@dataclass(slots=True)
class RunReport:
    """What a provider run produced."""

    provider: str
    model: str
    collected: int = 0
    usage: Usage = field(default_factory=Usage)
    errors: dict[str, str] = field(default_factory=dict)
    cost_usd: float = 0.0

    def describe(self) -> str:
        lines = [
            f"  provider:       {self.provider} ({self.model})",
            f"  collected:      {self.collected:,}",
            f"  input tokens:   {self.usage.input_tokens:,}",
            f"  output tokens:  {self.usage.output_tokens:,}",
        ]
        if self.usage.cache_read_tokens or self.usage.cache_write_tokens:
            lines.append(
                f"  cache r/w:      {self.usage.cache_read_tokens:,}"
                f" / {self.usage.cache_write_tokens:,}"
            )
        lines.append(f"  cost:           ${self.cost_usd:.4f}")
        if self.errors:
            lines.append(f"  errors:         {len(self.errors):,}")
        return "\n".join(lines)


class Cache:
    """Append-only JSONL cache of results, keyed by id.

    This is what makes Stage 2 resumable and what stops the project paying
    twice for the same entry (plan §2). JSONL rather than one file per entry:
    150k small files is hostile to the filesystem and to git, and we only ever
    need whole-file reads.

    Provider-scoped by convention — pass a different path per provider so an
    A/B comparison does not have one model's results shadow the other's.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, dict] = {}
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "id" in record:
                        self._data[record["id"]] = record

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str) -> dict | None:
        return self._data.get(key)

    def put(self, key: str, value: dict) -> None:
        record = {"id": key, **value}
        self._data[key] = record
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def missing(self, jobs: Iterable[Job]) -> list[Job]:
        return [j for j in jobs if j.id not in self._data]


def validate_payload(payload: object, schema: dict) -> str:
    """Cheap structural check of a model response against our schema.

    Providers with real schema enforcement never fail this. Providers that
    only offer "return JSON" mode regularly do, and a malformed sense list
    must be caught here rather than written into the dictionary.

    Returns an error string, or '' when the payload is acceptable.
    """
    if not isinstance(payload, dict):
        return f"expected an object, got {type(payload).__name__}"

    props: dict = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in payload:
            return f"missing required field {name!r}"

    for name, value in payload.items():
        spec = props.get(name)
        if spec is None:
            if schema.get("additionalProperties") is False:
                return f"unexpected field {name!r}"
            continue
        kind = spec.get("type")
        if kind == "array":
            if not isinstance(value, list):
                return f"{name}: expected a list"
            if "minItems" in spec and len(value) < spec["minItems"]:
                return f"{name}: fewer than {spec['minItems']} items"
            # An array's items are strings or objects, per the schema's own
            # `items` spec. This used to assume strings unconditionally, which
            # was true of every schema at the time and silently became the
            # reason a correct paired reply was rejected 40 times out of 40.
            item_kind = (spec.get("items") or {}).get("type", "string")
            if item_kind == "object":
                item_props = (spec.get("items") or {}).get("properties", {})
                required = (spec.get("items") or {}).get("required", list(item_props))
                for item in value:
                    if not isinstance(item, dict):
                        return f"{name}: expected a list of objects"
                    for key in required:
                        if key not in item:
                            return f"{name}: item missing {key!r}"
                        if not isinstance(item[key], str):
                            return f"{name}: {key!r} is not a string"
                        if not item[key].strip():
                            return f"{name}: {key!r} is empty"
            else:
                if not all(isinstance(v, str) for v in value):
                    return f"{name}: expected a list of strings"
                if not all(v.strip() for v in value):
                    return f"{name}: contains an empty string"
        elif kind == "string":
            if not isinstance(value, str):
                return f"{name}: expected a string"
            if "enum" in spec and value not in spec["enum"]:
                return f"{name}: {value!r} not one of {spec['enum']}"

    return ""


__all__ = ["Job", "Usage", "RunReport", "Cache", "validate_payload"]
