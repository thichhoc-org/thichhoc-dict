"""Stage 2 provider registry.

Adding a provider means one module here plus one line in ``REGISTRY``; nothing
in the pipeline scripts changes. DeepSeek would slot in the same way — it is
OpenAI-compatible like Ark, but has no batch surface at all (it discounts by
time of day instead), so it would subclass the online-call shape.
"""

from __future__ import annotations

from .base import Provider


def _claude(**kwargs) -> Provider:
    from .claude import DEFAULT_MODEL, ClaudeProvider

    kwargs.setdefault("model", DEFAULT_MODEL)
    return ClaudeProvider(**kwargs)


def _ark(**kwargs) -> Provider:
    from .ark import ArkProvider

    # Model default depends on the platform, so leave it to the provider.
    return ArkProvider(**kwargs)


def _gemini(**kwargs) -> Provider:
    from .gemini import GeminiProvider

    return GeminiProvider(**kwargs)


REGISTRY = {
    "claude": _claude,
    "ark": _ark,
    "gemini": _gemini,
}


def get_provider(name: str, **kwargs) -> Provider:
    """Build a provider by registry key."""
    factory = REGISTRY.get(name)
    if factory is None:
        raise SystemExit(f"unknown provider {name!r}; known: {', '.join(sorted(REGISTRY))}")
    # Drop keys the caller left as None so each provider keeps its own defaults.
    return factory(**{k: v for k, v in kwargs.items() if v is not None})


__all__ = ["Provider", "REGISTRY", "get_provider"]
