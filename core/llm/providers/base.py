"""The contract every Stage 2 provider implements.

Kept deliberately small. Providers differ in ways that matter — Anthropic has
an asynchronous Batch API at half price, Volcengine Ark exposes an
OpenAI-compatible endpoint, DeepSeek has no batch surface at all and discounts
by time of day — so the abstraction covers only what is genuinely common:
turn jobs into validated payloads, record what it cost, and never re-do work
the cache already holds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from ..types import Cache, Job, RunReport, Usage


class Provider(ABC):
    """Translates jobs into schema-valid JSON payloads."""

    #: Short registry key, e.g. "claude" or "ark".
    name: str = "provider"

    def __init__(self, model: str) -> None:
        self.model = model

    # -- required ---------------------------------------------------------

    @abstractmethod
    def translate(
        self,
        jobs: list[Job],
        *,
        system: str,
        schema: dict,
        cache: Cache,
        on_result: Callable[[str, dict], None] | None = None,
        dry_run: bool = False,
    ) -> RunReport:
        """Translate every job not already in ``cache``, writing as it goes."""

    @abstractmethod
    def cost_usd(self, usage: Usage) -> float:
        """Dollar cost of `usage` on this provider's current settings."""

    # -- optional ---------------------------------------------------------

    def forecast_usd(self, jobs: list[Job], system: str) -> float:
        """Rough pre-flight cost estimate, before anything is sent.

        The ~3.5 chars/token figure is a Latin-script approximation and is only
        used for the go/no-go number printed before a run; every provider
        replaces it with real token counts afterwards.
        """
        if not jobs:
            return 0.0
        avg_chars = sum(len(j.content) for j in jobs) / len(jobs)
        return self.cost_usd(
            Usage(
                input_tokens=int(len(jobs) * (avg_chars / 3.5 + 40)),
                output_tokens=int(len(jobs) * 70),
            )
        )

    def describe_pricing(self) -> str:
        return f"{self.name}:{self.model}"


__all__ = ["Provider"]
