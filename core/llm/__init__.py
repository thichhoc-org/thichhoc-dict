"""LLM layer for Stage 2 — provider-agnostic translation with resume.

Language-pair agnostic like the rest of ``core``: prompts differ per pair, the
caching, cost accounting and job plumbing do not. Providers live in
``providers/`` and are selected by name, so comparing two models is a flag
rather than a rewrite.
"""

from .providers import Provider, get_provider
from .types import Cache, Job, RunReport, Usage, validate_payload

__all__ = [
    "Provider",
    "get_provider",
    "Cache",
    "Job",
    "RunReport",
    "Usage",
    "validate_payload",
]
