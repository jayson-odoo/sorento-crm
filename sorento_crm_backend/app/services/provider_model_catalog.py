"""What models a provider will actually take, and whether one of them works.

Two questions an operator asks on the AI settings screens, and until now both
were answered by a hardcoded list in the frontend:

  1. Which models can I pick? -> `list_models`, asked of the provider itself.
  2. Does this one work? -> `probe_model`, a real call on the real request shape.

They are separate because a provider's catalogue is authority on what EXISTS and
not on what WORKS. Google lists `gemini-2.5-flash-lite` to a key that gets
`404 ... no longer available to new users` on the first generateContent - which
is exactly how every over-quota photo in the media lane came back "I could not
read anything" while the settings page showed a model picked from a valid list.
Listing alone would not have caught it; the probe does.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.llm_provider import (
    ProviderModel,
    get_provider,
    resolve_api_key,
)

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ("openai", "anthropic", "gemini")

# The list served when the provider cannot be asked (no key yet, network down,
# a 401 on a rotated key). Deliberately short and deliberately here rather than
# in the frontend: it is the SECOND source of truth for this data and a second
# source has to be somewhere one edit reaches. Ordering is newest first, which is
# the order the picker shows.
FALLBACK_MODELS: dict[str, list[ProviderModel]] = {
    "openai": [
        ProviderModel("gpt-5.4-mini", "GPT-5.4 mini"),
        ProviderModel("gpt-5.4", "GPT-5.4"),
        ProviderModel("gpt-4.1", "GPT-4.1"),
        ProviderModel("gpt-4o-mini", "GPT-4o mini"),
        ProviderModel("gpt-4o", "GPT-4o"),
    ],
    "anthropic": [
        ProviderModel("claude-haiku-4-5", "Claude Haiku 4.5"),
        ProviderModel("claude-sonnet-4-6", "Claude Sonnet 4.6"),
        ProviderModel("claude-opus-4-7", "Claude Opus 4.7"),
    ],
    "gemini": [
        ProviderModel("gemini-2.5-pro", "Gemini 2.5 Pro"),
        ProviderModel("gemini-2.5-flash", "Gemini 2.5 Flash"),
    ],
}

# A provider adds a model every few weeks, not every few seconds, and the settings
# page is opened far more often than that. An hour keeps a newly released model
# at most an hour away while a page full of pickers costs one upstream call.
CACHE_TTL_SECONDS = 3600.0

# The probe asks for one word but pays for a few dozen tokens, because a Gemini
# 2.5+ model spends its first tokens thinking: a 1-token ceiling returns an empty
# candidate and would report a working model as broken (the same trap that made
# Gemini's `test_connection` a ListModels call rather than a generate).
PROBE_MAX_TOKENS = 64
PROBE_PROMPT = "Reply with the single word OK."


@dataclass
class CatalogResult:
    """The answer to "which models", plus where it came from.

    `source` is carried to the screen rather than swallowed: a list that silently
    fell back to the built-in one looks identical to a live list, and an operator
    reading a stale name off a page that could not reach the provider is how a
    retired model gets picked in the first place.
    """

    provider: str
    models: list[ProviderModel]
    source: str  # "live" | "fallback"
    message: Optional[str] = None


@dataclass
class _CacheEntry:
    expires_at: float
    models: list[ProviderModel] = field(default_factory=list)


# Keyed by (provider, key fingerprint) so a rotated key is not served the old
# key's catalogue. The fingerprint is a length + last 4, never the key itself.
_cache: dict[tuple[str, str], _CacheEntry] = {}


def _fingerprint(api_key: str) -> str:
    return f"{len(api_key)}:{api_key[-4:]}" if api_key else "none"


def clear_cache() -> None:
    """Drop every cached catalogue. Used by tests and by a key change."""
    _cache.clear()


def _config(db: Session):
    from app.models.ai_assistant import AIAssistantConfig

    return (
        db.query(AIAssistantConfig)
        .order_by(AIAssistantConfig.created_at.asc())
        .first()
    )


def _resolve_key(db: Session, provider: str) -> Optional[str]:
    return resolve_api_key(_config(db), provider)


def resolve_provider_name(db: Session, provider: Optional[str]) -> str:
    """The provider a blank setting actually runs on.

    The media settings page leaves provider blank to mean "whatever the AI
    assistant is configured with", and until now the model picker answered that
    by offering EVERY provider's models grouped together - which is how a Gemini
    id ends up saved against an OpenAI key. Resolving it here means the picker
    can offer one provider's models and be right about which.
    """
    named = (provider or "").strip().lower()
    if named:
        return named
    cfg = _config(db)
    return str(getattr(cfg, "provider", "") or "").strip().lower() or "openai"


def list_models(db: Session, provider: str, *, now: Optional[float] = None) -> CatalogResult:
    """The models `provider` will accept, live where possible.

    Never raises for an upstream failure: an unreachable provider degrades to
    `FALLBACK_MODELS` with the reason attached, because a settings page that
    500s is worse than one showing a short list next to "could not reach".
    """
    name = resolve_provider_name(db, provider)
    if name not in SUPPORTED_PROVIDERS:
        return CatalogResult(
            provider=name,
            models=[],
            source="fallback",
            message=f"Unknown provider '{provider}'.",
        )

    api_key = _resolve_key(db, name)
    if not api_key:
        return CatalogResult(
            provider=name,
            models=list(FALLBACK_MODELS.get(name, [])),
            source="fallback",
            message=(
                f"No API key is configured for {name}, so this is the built-in "
                "list rather than what the provider offers."
            ),
        )

    clock = time.monotonic() if now is None else now
    cache_key = (name, _fingerprint(api_key))
    hit = _cache.get(cache_key)
    if hit is not None and hit.expires_at > clock:
        return CatalogResult(provider=name, models=list(hit.models), source="live")

    try:
        provider_impl = get_provider(name, api_key)
        models = provider_impl.list_models()
    except Exception as exc:  # noqa: BLE001 - an upstream failure is a fallback, not a 500
        logger.warning("could not list %s models: %s", name, exc)
        return CatalogResult(
            provider=name,
            models=list(FALLBACK_MODELS.get(name, [])),
            source="fallback",
            message=f"Could not reach {name}: {exc}",
        )

    if not models:
        return CatalogResult(
            provider=name,
            models=list(FALLBACK_MODELS.get(name, [])),
            source="fallback",
            message=f"{name} returned no usable models.",
        )

    _cache[cache_key] = _CacheEntry(expires_at=clock + CACHE_TTL_SECONDS, models=list(models))
    return CatalogResult(provider=name, models=models, source="live")


def probe_model(db: Session, provider: str, model: str) -> tuple[bool, str, int]:
    """Call `model` for real, once, and report what the provider said.

    The point is that it goes through `provider.chat` - the same path the media
    lane and the assistant use, carrying the same generation config. A probe that
    hand-rolled its own request would have passed on `gemini-3.5-flash-lite`
    while the real lane failed on it, because the failure was our own
    `thinkingBudget: 0` and not the model.

    Returns `(ok, message, latency_ms)`. The provider's own words are the message
    on failure: "404 ... no longer available to new users" tells an operator what
    to do, and any sentence we substitute for it does not.
    """
    name = resolve_provider_name(db, provider)
    model_name = (model or "").strip()
    if not model_name:
        return False, "No model named.", 0

    api_key = _resolve_key(db, name)
    if not api_key:
        return False, f"No API key is configured for the '{name}' provider.", 0

    started = time.perf_counter()
    try:
        impl = get_provider(name, api_key, model=model_name)
    except ValueError as exc:
        return False, str(exc), 0
    try:
        result = impl.chat(
            [{"role": "user", "content": PROBE_PROMPT}],
            temperature=0.0,
            max_tokens=PROBE_MAX_TOKENS,
            model=model_name,
        )
    except Exception as exc:  # noqa: BLE001 - the provider's refusal IS the answer
        return False, str(exc), int((time.perf_counter() - started) * 1000)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    content = (getattr(result, "content", "") or "").strip()
    if not content:
        # A model that answers with nothing is not a model this lane can use: the
        # extraction path parses JSON out of the content, and an empty candidate
        # (a thinking budget that ate the whole ceiling) fails there instead.
        return False, "The model answered with an empty response.", elapsed_ms
    return True, "OK", elapsed_ms


def model_choices(result: CatalogResult) -> list[dict[str, Any]]:
    """`CatalogResult` models as the wire shape the pickers read."""
    return [{"value": m.value, "label": m.label} for m in result.models]
