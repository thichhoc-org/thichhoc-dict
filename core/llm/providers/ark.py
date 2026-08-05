"""ByteDance Ark provider, via its OpenAI-compatible API.

**Two platforms, and they are not interchangeable.** Ark ships as BytePlus
ModelArk internationally and as Volcengine 火山方舟 in mainland China, with
separate accounts, keys, model names and prices. A key from one returns
``401 AuthenticationError`` on the other — which reads exactly like a bad key
and is the first thing to check when authentication fails. Select with
``ARK_PLATFORM``; ``byteplus`` is the default, since that is what an account
outside mainland China will have.

Beyond the platform split, three things differ from the Claude path:

**Models must be activated before use.** Listing models with ``GET
/api/v3/models`` shows everything a key can *see*, which is not the same as
what it can *call*: an unactivated model fails with ``ModelNotOpen``. That is
account state, not a code problem, so it is raised immediately rather than
recorded once per entry.

**No schema enforcement.** Ark offers OpenAI-style ``json_object`` mode — "emit
valid JSON" — not a schema the server validates against. So the shared system
prompt is augmented with an explicit shape instruction, every response is
checked by ``validate_payload``, and a failure is retried once before being
recorded as an error. On Claude that validation never fires; here it is
load-bearing.

**Online rather than batch.** Ark does document batch inference
(``CreateBatchInferenceJob``, plus a batch chat surface), but its request
format is file-based and not verified here, so this provider issues concurrent
online calls instead. That is the right shape for an A/B trial of a hundred
entries anyway; for the full 144k run the batch path is worth wiring up once
its schema is confirmed, and would only lower the figures further.

Prices below are unverified and platform-specific — check them against a real
invoice before trusting any dollar figure this module prints.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from ..types import Cache, Job, RunReport, Usage, validate_payload
from .base import Provider

#: ByteDance ships Ark on two separate platforms with separate accounts, keys,
#: model names and prices. A key from one returns 401 on the other, which is
#: the first thing to check when authentication fails.
ENDPOINTS = {
    # International (BytePlus ModelArk) — console.byteplus.com
    "byteplus": "https://ark.ap-southeast.bytepluses.com/api/v3",
    # Mainland China (Volcengine 火山方舟) — console.volcengine.com/ark
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
}
DEFAULT_PLATFORM = os.environ.get("ARK_PLATFORM", "byteplus")

#: Model naming differs by platform too: BytePlus drops the "doubao-" prefix
#: its mainland counterpart uses. `GET /api/v3/models` lists what a given key
#: can see; the console decides which of those are actually activated.
DEFAULT_MODELS = {
    "byteplus": "seed-1-6-250915",
    "volcengine": "doubao-seed-1-6-251015",
}

#: Approximate CNY per USD, only used for the Volcengine table below.
CNY_PER_USD = float(os.environ.get("ARK_CNY_PER_USD", "7.2"))

#: (input, cache-hit input, output) per million tokens. Cache-hit is its own
#: column on Ark's price sheet — roughly a twelfth of input on deepseek-v4-pro
#: — so it is priced separately rather than folded in.
#:
#: BytePlus figures are USD, read from its published pricing page (2026-08-01).
#: Volcengine figures are CNY and still unverified — that page would not render
#: for scraping. Batch prices are input and output at half, cache-hit unchanged.
PRICING: dict[str, dict[str, tuple[float, float, float]]] = {
    "byteplus": {
        "deepseek-v4-pro-260425": (1.74, 0.145, 3.48),
        "deepseek-v4-flash-260425": (0.14, 0.028, 0.28),
        "deepseek-v3-2-251201": (0.28, 0.056, 0.42),
        "seed-1-6-250915": (0.25, 0.05, 2.00),
        "seed-1-6-flash-250715": (0.075, 0.015, 0.30),
        "seed-2-0-pro-260328": (0.50, 0.10, 3.00),
        "seed-2-0-mini-260215": (0.10, 0.02, 0.40),
        "glm-4-7-251222": (0.6, 0.11, 2.2),
    },
    "volcengine": {
        "doubao-seed-1-6-251015": (0.8, 0.16, 8.0),
        "doubao-lite-32k": (0.3, 0.06, 0.6),
    },
}

#: Batch halves input and output but leaves cache-hit alone.
BATCH_DISCOUNT = 0.5

#: Appended to the shared system prompt. Ark cannot enforce the schema, and
#: OpenAI-compatible json_object mode additionally wants the word "JSON" to
#: appear in the prompt before it will engage.
_JSON_INSTRUCTION_HEAD = """

## Output format

Reply with a single JSON object and nothing else — no prose, no markdown
fence. Exactly two keys:

"""

#: Grouped mode. The lexicographic half of the system prompt is byte-identical
#: to single mode — only the envelope changes — so the two modes stay
#: comparable and a quality difference between them means the grouping itself,
#: not a different brief.
_JSON_INSTRUCTION_GROUPED_HEAD = """

## Input and output format

The user turn is a JSON array of entries, each with an `id`. Treat every entry
independently: one entry's senses must not influence another's.

Reply with a single JSON object and nothing else — no prose, no markdown
fence. One key, `entries`, holding one object per input entry, in the same
order, each echoing the `id` it answers:

    {"entries": [
"""

class ArkProvider(Provider):
    name = "ark"

    def __init__(
        self,
        model: str | None = None,
        *,
        platform: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 1024,
        concurrency: int = 8,
        retries: int = 1,
        reasoning: bool = False,
        group_size: int = 1,
        batch: bool = False,
    ) -> None:
        self.platform = platform or DEFAULT_PLATFORM
        if self.platform not in ENDPOINTS:
            raise SystemExit(
                f"unknown ARK_PLATFORM {self.platform!r}; known: {', '.join(ENDPOINTS)}"
            )
        super().__init__(model or DEFAULT_MODELS[self.platform])
        self.base_url = base_url or os.environ.get("ARK_BASE_URL") or ENDPOINTS[self.platform]
        self.max_tokens = max_tokens
        self.concurrency = concurrency
        self.retries = retries
        # Reasoning models on Ark emit a chain of thought that is billed as
        # output. Measured on deepseek-v4-pro: 538 output tokens with it, 50
        # without — for a byte-identical answer. Writing three dictionary
        # senses from a supplied gloss is not a task that needs deliberation,
        # so it is off unless asked for.
        self.reasoning = reasoning
        self._thinking_supported = True
        #: Billed as output; tracked separately so a run shows what deliberation cost.
        self.reasoning_tokens = 0
        # The system prompt is ~920 tokens and is resent with every request,
        # so at group_size 1 it is ~95% of the input bill. Packing N entries
        # into one call amortises it N ways: measured 1,039 input tokens per
        # entry alone, versus ~110 at group_size 20. Nothing about the
        # lexicographic instructions changes.
        self.group_size = max(1, group_size)
        #: Groups whose reply could not be used, retried one entry at a time.
        self.group_fallbacks = 0
        #: Batch halves input and output; requires an ep-bi-* endpoint as the
        #: model id and the /batch base path.
        self.batch = batch
        if batch and "/batch" not in self.base_url:
            self.base_url = self.base_url.rstrip("/") + "/batch"

    # -- pricing ----------------------------------------------------------

    def _prices(self) -> tuple[float, float] | None:
        return PRICING.get(self.platform, {}).get(self.model)

    def cost_usd(self, usage: Usage) -> float:
        prices = self._prices()
        if prices is None:
            # Unknown price beats a fabricated one: the report shows token
            # counts and the operator multiplies by their console's rate.
            return 0.0
        price_in, price_cache, price_out = prices
        discount = BATCH_DISCOUNT if self.batch else 1.0
        amount = (
            (usage.input_tokens + usage.cache_write_tokens) * price_in * discount
            + usage.cache_read_tokens * price_cache
            + usage.output_tokens * price_out * discount
        ) / 1_000_000
        return amount / CNY_PER_USD if self.platform == "volcengine" else amount

    def describe_pricing(self) -> str:
        prices = self._prices()
        if prices is None:
            return f"{self.model} on {self.platform}: price not configured — tokens only"
        price_in, price_cache, price_out = prices
        cur = "¥" if self.platform == "volcengine" else "$"
        d = BATCH_DISCOUNT if self.batch else 1.0
        note = " batch -50%" if self.batch else ""
        return (f"{self.model} on {self.platform}: in {cur}{price_in * d:g} /"
                f" cache {cur}{price_cache:g} / out {cur}{price_out * d:g} per M{note}")

    # -- plumbing ---------------------------------------------------------

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("`uv add openai` is required for the ark provider") from exc
        key = os.environ.get("ARK_API_KEY") or os.environ.get("VOLC_ACCESSKEY")
        if not key:
            raise SystemExit(
                "set ARK_API_KEY.\n"
                "  BytePlus (international): https://console.byteplus.com/ark\n"
                "  Volcengine (mainland CN): https://console.volcengine.com/ark\n"
                "Keys are not interchangeable — select with ARK_PLATFORM."
            )
        return OpenAI(api_key=key, base_url=self.base_url)

    @staticmethod
    def _shape(schema: dict, grouped: bool) -> str:
        """The output-format section, derived from the schema being enforced.

        Ark cannot validate a schema server-side, so the shape has to be spelled
        out in prose. Choosing that prose from the schema rather than from a
        separate flag is what stops the two describing different replies.
        """
        from ..prompts import is_paired

        body = ('"senses": [{"en": "...", "vi": "..."}]' if is_paired(schema)
                else '"senses_vi": ["...", "..."]')
        rule = ("`senses` is a list of 1 to 4 objects, each with a non-empty `en` and `vi`."
                if is_paired(schema)
                else "`senses_vi` is a list of 1 to 4 non-empty strings.")
        if not grouped:
            return (_JSON_INSTRUCTION_HEAD
                    + f'    {{{body}, "confidence": "high"}}\n\n' + rule
                    + ' `confidence` is exactly one of "high", "medium", "low".\n')
        return (_JSON_INSTRUCTION_GROUPED_HEAD
                + f'      {{"id": "<the id you were given>", {body}, "confidence": "high"}}\n    ]}}\n\n'
                + rule + ' `confidence` is exactly one of "high", "medium", "low".'
                + " Answer every entry you were given.\n")

    def _messages(self, group: list[Job], system: str, schema: dict | None = None) -> list[dict]:
        if len(group) == 1:
            return [
                {"role": "system", "content": system + self._shape(schema or {}, False)},
                {"role": "user", "content": group[0].content},
            ]
        # Each entry carries its id so the reply can be matched back by id
        # rather than by position — a model that drops or reorders one entry
        # must not shift every later answer onto the wrong headword.
        packed = [{"id": j.id, **json.loads(j.content)} for j in group]
        return [
            {"role": "system", "content": system + self._shape(schema or {}, True)},
            {"role": "user", "content": json.dumps(packed, ensure_ascii=False)},
        ]

    def _unpack(self, group: list[Job], payload: object, schema: dict) -> tuple[dict[str, dict], str]:
        """Split a reply into {job id: payload}, or explain why it cannot be."""
        if len(group) == 1:
            problem = validate_payload(payload, schema)
            return ({} if problem else {group[0].id: payload}), problem

        if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
            return {}, "grouped reply has no `entries` list"

        wanted = {j.id for j in group}
        out: dict[str, dict] = {}
        for item in payload["entries"]:
            if not isinstance(item, dict):
                continue
            entry_id = item.get("id")
            if entry_id not in wanted:
                continue
            body = {k: v for k, v in item.items() if k != "id"}
            if not validate_payload(body, schema):
                out[entry_id] = body

        missing = len(wanted) - len(out)
        # A partial group is still worth keeping; the entries it dropped fall
        # back to individual calls rather than being lost.
        return out, f"{missing} of {len(wanted)} entries missing or invalid" if missing else ""

    def _call(self, client, group: list[Job], system: str, schema: dict
              ) -> tuple[dict[str, dict], Usage, str]:
        """One request covering `group`. Returns ({job id: payload}, usage, error)."""
        usage = Usage()
        last_error = ""
        results: dict[str, dict] = {}

        for attempt in range(self.retries + 1):
            extra: dict = {}
            if not self.reasoning and self._thinking_supported:
                extra["extra_body"] = {"thinking": {"type": "disabled"}}
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    max_tokens=self.max_tokens * max(1, len(group)),
                    response_format={"type": "json_object"},
                    messages=self._messages(group, system, schema),
                    **extra,
                )
            except Exception as exc:  # noqa: BLE001 — one bad entry must not end the run
                detail = str(exc)
                if "thinking" in detail and "InvalidParameter" in detail:
                    # Non-reasoning models reject the parameter; drop it for
                    # the rest of the run rather than failing every entry.
                    self._thinking_supported = False
                    continue
                if "ModelNotOpen" in detail:
                    # Account-side, not a code problem, and it will fail for
                    # every entry — say so once, plainly, rather than 100 times.
                    raise SystemExit(
                        f"model {self.model!r} is not activated on this account.\n"
                        f"Enable it in the {self.platform} console, then re-run.\n"
                        f"`GET {self.base_url}/models` lists what the key can see."
                    ) from exc
                last_error = f"api: {type(exc).__name__}: {detail}"[:200]
                continue

            api_usage = getattr(response, "usage", None)
            if api_usage is not None:
                cached = 0
                details = getattr(api_usage, "prompt_tokens_details", None)
                if details is not None:
                    cached = getattr(details, "cached_tokens", 0) or 0
                out_details = getattr(api_usage, "completion_tokens_details", None)
                if out_details is not None:
                    self.reasoning_tokens += getattr(out_details, "reasoning_tokens", 0) or 0
                usage.add(
                    Usage(
                        input_tokens=max((getattr(api_usage, "prompt_tokens", 0) or 0) - cached, 0),
                        output_tokens=getattr(api_usage, "completion_tokens", 0) or 0,
                        cache_read_tokens=cached,
                    )
                )

            text = (response.choices[0].message.content or "").strip()
            # json_object mode is not always honoured; a fenced block is the
            # usual way it leaks.
            if text.startswith("```"):
                text = text.strip("`")
                if text.lstrip().lower().startswith("json"):
                    text = text.lstrip()[4:]
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                last_error = f"unparseable (attempt {attempt + 1})"
                continue

            found, problem = self._unpack(group, payload, schema)
            results.update(found)
            if problem:
                last_error = f"{problem} (attempt {attempt + 1})"
                continue
            return results, usage, ""

        return results, usage, last_error or "failed"

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
            # Preview the request the run would actually send. This used to
            # print the single-entry envelope and a per-entry request count no
            # matter what --group-size said, which made the one command whose
            # entire job is "show me what you are about to pay for" describe a
            # different run from the one that follows.
            group = pending[: self.group_size]
            messages = self._messages(group, system, schema)
            groups = -(-len(pending) // self.group_size)
            preview = {
                "model": self.model,
                "base_url": self.base_url,
                "response_format": {"type": "json_object"},
                "max_tokens": self.max_tokens * max(1, len(group)),
                "messages": [
                    {"role": m["role"], "content": m["content"][:400] + " ..."
                     if len(m["content"]) > 400 else m["content"]}
                    for m in messages
                ],
            }
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            print(f"\n(dry run — would send {groups:,} request(s) covering "
                  f"{len(pending):,} entries at group size {self.group_size}, "
                  f"{self.concurrency} at a time)")
            return report

        client = self._client()
        groups = [pending[i : i + self.group_size]
                  for i in range(0, len(pending), self.group_size)]
        if self.group_size > 1:
            print(f"    {len(pending):,} entries in {len(groups):,} request(s)"
                  f" of up to {self.group_size}")

        stragglers = self._dispatch(client, groups, system, schema, cache, on_result, report)

        # Entries a grouped reply skipped are retried alone, where the model
        # has one thing to do and the schema check is unambiguous. Losing 20
        # entries to one malformed reply would make grouping a bad trade.
        if stragglers:
            self.group_fallbacks = len(stragglers)
            print(f"    retrying {len(stragglers):,} entr(y/ies) individually")
            self._dispatch(client, [[j] for j in stragglers], system, schema,
                           cache, on_result, report)

        report.cost_usd = self.cost_usd(report.usage)
        return report

    def _dispatch(self, client, groups, system, schema, cache, on_result, report) -> list[Job]:
        """Run groups concurrently; return jobs that came back unanswered."""
        stragglers: list[Job] = []
        done = 0
        total = sum(len(g) for g in groups)
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {pool.submit(self._call, client, g, system, schema): g for g in groups}
            for future in as_completed(futures):
                group = futures[future]
                results, usage, error = future.result()
                report.usage.add(usage)
                done += len(group)
                if done % 25 < len(group) or done >= total:
                    print(f"    {done:,}/{total:,}")
                for job in group:
                    payload = results.get(job.id)
                    if payload is None:
                        if len(group) > 1:
                            stragglers.append(job)
                        else:
                            report.errors[job.id] = error or "no result"
                        continue
                    cache.put(job.id, payload)
                    if on_result:
                        on_result(job.id, payload)
                    report.collected += 1
        return stragglers


__all__ = ["ArkProvider", "ENDPOINTS", "DEFAULT_MODELS", "PRICING", "BATCH_DISCOUNT"]
