#!/usr/bin/env python3
"""Stage 2b — translate the entries Wiktionary could not fill.

Only entries with an empty ``senses_vi`` are submitted, and every result is
cached by entry id before the run ends, so this is safe to interrupt and
re-run: the plan's requirement that Stage 2 never pay twice for the same entry
(§2) is enforced by the cache, not by discipline.

Order of work is deliberate: ``--tier 1`` first, because those 5,937 entries
get 100% human review and are where a prompt problem is cheapest to discover.

    # what would be sent, no API call, no cost
    uv run python s2_llm.py --tier 1 --limit 100 --dry-run

    # the real thing
    uv run python s2_llm.py --tier 1 --limit 100
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import _paths
from _paths import ENTRIES_DIR

from core.llm import Cache, Job, get_provider
from core.llm.providers import REGISTRY
from core.llm.prompts import (EN_VI_SENSES_SCHEMA, EN_VI_SENSES_SCHEMA_PLAIN,
                             en_vi_system, en_vi_user)
from core.schema import Entry


def load_candidates(path: Path) -> list[Entry]:
    """Read entries from a single JSONL file, or from a sharded entry store.

    Accepting the store directly matters more than it looks. The intermediates
    under work/ are snapshots: s2b-translated.jsonl was written before the
    retier dropped 286 headwords and re-ranked every tier, so a run reading it
    would select against a tier map the dictionary no longer uses, and write
    back entries that had been deleted. Pointing at data/entries reads what the
    build actually ships.
    """
    if path.is_dir():
        from core.store import iter_entries

        return list(iter_entries(path))

    entries: list[Entry] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                entries.append(Entry.from_line(line))
    return entries


def select(
    entries: list[Entry],
    *,
    tiers: set[int] | None,
    limit: int | None,
    refresh: bool = False,
) -> list[Entry]:
    """Entries still needing a translation, best candidates first.

    By default this is a gap-filler: an entry Wiktionary already answered is
    never sent, so Stage 2b only ever pays for what Stage 2a missed.

    ``refresh`` sends the entry anyway and lets the result replace what is
    there. Gap-filling alone cannot reach a whole class of defect, because
    Wiktionary's answer may be *partial* rather than absent and the pool never
    sees it again: the noun *spring* took "mùa xuân" and "lò xo" from
    Wiktionary, whose Vietnamese translation table has no third entry, and so
    could never acquire "suối" no matter how often Stage 2b ran. 830 of tier
    1's 5,937 entries are in that state. It also re-cuts entries translated
    under the old bare-list schema so they carry an aligned ``senses_en``.
    """
    pool = [e for e in entries if (refresh or not e.senses_vi) and e.gloss_en]
    if tiers:
        pool = [e for e in pool if e.freq_tier in tiers]
    # Most frequent first: if a run is cut short, the entries that landed are
    # the ones most readers will actually look up.
    pool.sort(key=lambda e: (e.freq_tier, -e.freq, e.id))
    return pool[:limit] if limit else pool


def _read_senses(record: dict) -> tuple[list[str], list[str]]:
    """Pull (senses_vi, senses_en) out of a cached result.

    Two shapes exist on disk. The current one is a list of ``{en, vi}`` pairs.
    The older one is a bare ``senses_vi`` list of strings, written before the
    English half was asked for; the caches from those runs are still worth
    reading — they cost real money — so they are accepted and simply produce no
    ``senses_en``. That is exactly the state the renderer treats as "no English
    caption available", so an old cache degrades to the old presentation rather
    than to a wrong one.
    """
    senses = record.get("senses")
    if isinstance(senses, list) and senses and isinstance(senses[0], dict):
        vi = [str(s.get("vi", "")).strip() for s in senses]
        en = [str(s.get("en", "")).strip() for s in senses]
        # Drop a repeated Vietnamese sense and the English that came with it,
        # together, so the two lists stay the same length. The schema rejects a
        # duplicate senses_vi outright, so without this one model slip — `en:
        # straight:adj` answered "thẳng" twice for two different WordNet senses
        # — fails validation for the whole store and blocks every build.
        seen: set[str] = set()
        pairs = []
        for v, e in zip(vi, en):
            if v and v not in seen:
                seen.add(v)
                pairs.append((v, e))
        vi = [v for v, _ in pairs]
        en = [e for _, e in pairs]
        kept_vi = list(vi)
        # The Vietnamese is the product; the English is a caption on it. So a
        # pair with a blank `en` costs the entry its caption, never its sense —
        # dropping the sense would spend the thing we paid for to protect the
        # thing we got for free. Captions are all-or-nothing per entry because
        # a partial list cannot stay aligned index for index.
        if len(kept_vi) == len(vi) and all(en):
            return vi, en
        return kept_vi, []
    # Same de-duplication as the paired branch above. It lived only there at
    # first, which held for as long as every run asked for pairs — and then the
    # first plain run put `false_mallow` twice into one sense list and the
    # validator refused to promote 155,139 entries over one repeated string.
    legacy = record.get("senses_vi") or []
    seen_vi: set[str] = set()
    out: list[str] = []
    for s in legacy:
        s = str(s).strip()
        if s and s not in seen_vi:
            seen_vi.add(s)
            out.append(s)
    return out, []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in", dest="inp", type=Path, default=None,
                        help="entries JSONL (default: work/s2a-matched.jsonl)")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--tier", type=int, action="append",
                        help="restrict to a frequency tier (repeatable)")
    parser.add_argument("--limit", type=int, help="cap the number of entries")
    parser.add_argument("--paired", action="store_true",
                        help="also ask for the English sense beside each Vietnamese one "
                             "(senses_en); costs ~30%% more output, useful only where the "
                             "tier will actually be reviewed")
    parser.add_argument("--refresh", action="store_true",
                        help="also re-send entries that already have senses, and let "
                             "the result replace them (use a fresh --cache)")
    parser.add_argument("--provider", default="claude", choices=sorted(REGISTRY),
                        help="which model provider translates the entries")
    parser.add_argument("--model", default=None, help="override the provider's default model")
    parser.add_argument("--group-size", type=int, default=None,
                        help="ark: entries per request; amortises the system prompt")
    parser.add_argument("--concurrency", type=int, default=None,
                        help="requests in flight at once (provider default 8)")
    parser.add_argument("--reasoning", action="store_true",
                        help="ark: leave the model's chain of thought on (~10x output tokens)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print one request and the cost estimate; call nothing")
    args = parser.parse_args(argv)

    work = _paths.ensure_work()
    inp = args.inp or work / "s2a-matched.jsonl"
    out = args.out or work / "s2b-translated.jsonl"
    # Cache is per provider: an A/B run must not have one model's results
    # shadow the other's.
    cache_path = args.cache or work / f"llm-cache-{args.provider}.jsonl"
    _paths.require(inp, "make stage2-match")

    entries = load_candidates(inp)
    tiers = set(args.tier) if args.tier else None
    todo = select(entries, tiers=tiers, limit=args.limit, refresh=args.refresh)

    have = sum(1 for e in entries if e.senses_vi)
    print(f"{len(entries):,} entries; {have:,} already have senses")
    print(f"selected {len(todo):,} for translation"
          + (f" (tier {sorted(tiers)})" if tiers else "")
          + (f", limit {args.limit}" if args.limit else ""))
    if not todo:
        print("nothing to do.")
        return 0

    cache = Cache(cache_path)
    if len(cache):
        print(f"cache at {cache_path}: {len(cache):,} entries")

    # senses_en is generated text and billed as output — about 30% of what a
    # reply emits. It exists to let a reviewer see which English sense a
    # Vietnamese line answers, and only tier 1 is reviewed, so it is asked for
    # only where somebody will read it.
    schema = EN_VI_SENSES_SCHEMA if args.paired else EN_VI_SENSES_SCHEMA_PLAIN
    system = en_vi_system(schema)
    provider = get_provider(args.provider, model=args.model,
                            reasoning=args.reasoning or None,
                            group_size=args.group_size,
                            concurrency=args.concurrency)
    jobs = [
        Job(id=e.id, content=en_vi_user(e.headword, e.pos, e.pron, e.gloss_en))
        for e in todo
    ]

    print(f"\nsystem prompt: ~{len(system) // 4:,} tokens")
    print(f"provider: {provider.describe_pricing()}")
    print(f"forecast: ~${provider.forecast_usd(jobs, system):.2f} for {len(jobs):,} entries")

    report = provider.translate(
        jobs, system=system, schema=schema, cache=cache,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        return 0

    print()
    print(report.describe())

    # Merge cached results back over the corpus — including results from
    # earlier runs, which is what makes an interrupted job resumable.
    confidence = Counter()
    applied = 0
    replaced = 0
    for entry in entries:
        record = cache.get(entry.id)
        if not record:
            continue
        if entry.senses_vi and not args.refresh:
            continue
        vi, en = _read_senses(record)
        if not vi:
            continue
        had = bool(entry.senses_vi)
        entry.senses_vi = vi
        entry.senses_en = en
        if "llm" not in (entry.source or "").split("+"):
            entry.source = f"{entry.source}+llm" if entry.source else "llm"
        level = record.get("confidence", "unknown")
        entry.extra["llm_confidence"] = level
        confidence[level] += 1
        applied += 1
        replaced += had

    from core.store import write_single

    count = write_single(out, entries)
    print(f"\nwrote {count:,} entries -> {out}")
    print(f"  applied: {applied:,}" + (f" ({replaced:,} replaced existing senses)" if replaced else ""))
    aligned = sum(1 for e in entries if e.senses_en)
    print(f"  with an aligned English side: {aligned:,}")
    if confidence:
        print("  confidence: " + ", ".join(
            f"{k}={v:,}" for k, v in sorted(confidence.items())))
    if report.errors:
        print(f"  errors: {len(report.errors):,} (re-run to retry — cache keeps the rest)")
        for entry_id, why in list(report.errors.items())[:5]:
            print(f"    {entry_id}: {why}")

    total = sum(1 for e in entries if e.senses_vi)
    print(f"\ncoverage now: {total:,}/{count:,} ({100.0 * total / count:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
