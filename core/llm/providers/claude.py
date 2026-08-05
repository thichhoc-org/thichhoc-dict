"""Anthropic provider — Claude Batch API.

Batch is the right surface for a 150k-entry corpus: half price, and the
turnaround (usually under an hour, up to 24) is irrelevant for a pipeline
nobody is waiting on. Structured outputs give real schema enforcement, so
there is no parse-and-retry loop here — the validation in ``types`` is a
belt-and-braces check that in practice never fires on this provider.
"""

from __future__ import annotations

import json
import time
from typing import Callable

from ..types import Cache, Job, RunReport, Usage, validate_payload
from .base import Provider

DEFAULT_MODEL = "claude-opus-5"

#: Per-million-token list prices, before the Batch API's 50% discount.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

BATCH_DISCOUNT = 0.5

#: Hard API limit per batch; a 155k-entry corpus therefore needs two.
MAX_REQUESTS_PER_BATCH = 100_000

#: Prompts shorter than this never enter the prompt cache, so a system prompt
#: below it silently pays full price on every request (Claude Opus 5).
CACHE_MIN_TOKENS = 512


class ClaudeProvider(Provider):
    name = "claude"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        max_tokens: int = 2048,
        poll_seconds: int = 30,
        use_batch: bool = True,
    ) -> None:
        super().__init__(model)
        self.max_tokens = max_tokens
        self.poll_seconds = poll_seconds
        self.use_batch = use_batch

    # -- pricing ----------------------------------------------------------

    def cost_usd(self, usage: Usage) -> float:
        price_in, price_out = PRICING.get(self.model, PRICING[DEFAULT_MODEL])
        discount = BATCH_DISCOUNT if self.use_batch else 1.0
        dollars = (
            usage.input_tokens * price_in
            + usage.output_tokens * price_out
            # Cache reads bill at ~0.1x input; writes at 1.25x for the 5-min TTL.
            + usage.cache_read_tokens * price_in * 0.1
            + usage.cache_write_tokens * price_in * 1.25
        ) / 1_000_000
        return dollars * discount

    def describe_pricing(self) -> str:
        price_in, price_out = PRICING.get(self.model, PRICING[DEFAULT_MODEL])
        suffix = " (batch -50%)" if self.use_batch else ""
        return f"{self.model}: ${price_in}/${price_out} per M tokens{suffix}"

    # -- plumbing ---------------------------------------------------------

    def _client(self):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("`uv add anthropic` is required for the claude provider") from exc
        # A bare constructor resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN,
        # or an `ant auth login` profile — don't demand a key that may not be
        # the credential the operator uses.
        return anthropic.Anthropic()

    def _request(self, job: Job, system: str, schema: dict) -> dict:
        return {
            "custom_id": job.id,
            "params": {
                "model": self.model,
                "max_tokens": self.max_tokens,
                # The cache breakpoint goes on the system prompt because it is
                # byte-identical across the run; per-entry content sits after
                # it and so never invalidates the prefix.
                "system": [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                "messages": [{"role": "user", "content": job.content}],
                "output_config": {"format": {"type": "json_schema", "schema": schema}},
            },
        }

    # -- run --------------------------------------------------------------

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
        report = RunReport(provider=self.name, model=self.model)
        pending = cache.missing(jobs)
        if not pending:
            return report

        if dry_run:
            print(json.dumps(self._request(pending[0], system, schema),
                             ensure_ascii=False, indent=2)[:1200])
            print(f"\n(dry run — would submit {len(pending):,} request(s))")
            return report

        client = self._client()
        for start in range(0, len(pending), MAX_REQUESTS_PER_BATCH):
            chunk = pending[start : start + MAX_REQUESTS_PER_BATCH]
            self._run_chunk(client, chunk, system, schema, cache, on_result, report)

        report.cost_usd = self.cost_usd(report.usage)
        return report

    def _run_chunk(self, client, jobs, system, schema, cache, on_result, report) -> None:
        requests = [self._request(j, system, schema) for j in jobs]
        batch = client.messages.batches.create(requests=requests)
        print(f"  submitted batch {batch.id} ({len(requests):,} requests)")

        while True:
            batch = client.messages.batches.retrieve(batch.id)
            if batch.processing_status == "ended":
                break
            counts = batch.request_counts
            print(
                f"    {batch.processing_status}: {counts.succeeded:,} ok /"
                f" {counts.errored:,} err / {counts.processing:,} left"
            )
            time.sleep(self.poll_seconds)

        for result in client.messages.batches.results(batch.id):
            # Results arrive in arbitrary order — custom_id is the only safe key.
            entry_id = result.custom_id
            if result.result.type != "succeeded":
                report.errors[entry_id] = result.result.type
                continue

            message = result.result.message
            usage = getattr(message, "usage", None)
            if usage is not None:
                report.usage.add(
                    Usage(
                        input_tokens=getattr(usage, "input_tokens", 0) or 0,
                        output_tokens=getattr(usage, "output_tokens", 0) or 0,
                        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                    )
                )

            text = next((b.text for b in message.content if b.type == "text"), "")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                report.errors[entry_id] = "unparseable"
                continue

            problem = validate_payload(payload, schema)
            if problem:
                report.errors[entry_id] = problem
                continue

            cache.put(entry_id, payload)
            if on_result:
                on_result(entry_id, payload)
            report.collected += 1


__all__ = ["ClaudeProvider", "DEFAULT_MODEL", "PRICING", "CACHE_MIN_TOKENS"]
