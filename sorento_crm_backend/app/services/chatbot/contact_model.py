"""MODEL-PER-CONTACT: which LLM answers a contact, and how each config reader applies it.

Ladder for every chatbot LLM call of a turn (parser, clarifier, code reader): contact override,
then the contact's tag model, then that call's own `production` label row, then the global AI
assistant config. `contact_llm_choice` owns the top two rungs and reads them live every turn (no
cache, no Apply); `apply_choice` is the one place a reader merges the choice with its own default.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContactLLMChoice:
    provider: Optional[str]
    model: Optional[str]
    source: str  # contact | tag | tag_conflict | none
    tags: list[str] = field(default_factory=list)


def contact_llm_choice(db, contact) -> ContactLLMChoice:
    from app.services import contact_tag_settings as cts

    if contact.chatbot_llm_provider and contact.chatbot_llm_model:
        return ContactLLMChoice(contact.chatbot_llm_provider, contact.chatbot_llm_model, "contact", [])
    cid = str(contact.id)
    entries = []
    for tag in cts.tags_by_contact_with_settings(db, [cid]).get(cid, []):
        for section, key, value in cts.leaves(tag):
            if (section, key) == ("chatbot", "llm"):
                entries.append((tag.name, value))
    if not entries:
        return ContactLLMChoice(None, None, "none", [])
    expected, conflict = cts._m_eq([v for _, v in entries])
    if conflict:
        return ContactLLMChoice(None, None, "tag_conflict", sorted({n for n, _ in entries}))
    return ContactLLMChoice(expected[0], expected[1], "tag", sorted({n for n, _ in entries}))


def apply_choice(
    choice: Optional[ContactLLMChoice], cfg: Any, provider: str, model: str, *, model_from_label: bool
) -> tuple[str, str, str, str]:
    """`(provider, model, api_key, model_source)` for one reader.

    `provider` / `model` are the reader's own label-or-global pair. A choice whose provider has
    no key falls back to that pair with a warning that names the provider, never a key.
    """
    from app.services.llm_provider import resolve_api_key

    default_source = "label" if model_from_label else "global"
    if choice is not None and choice.provider and choice.model:
        key = resolve_api_key(cfg, choice.provider)
        if key:
            return choice.provider, choice.model, key, choice.source
        logger.warning(
            "contact LLM choice provider %s has no API key; using the default model", choice.provider
        )
        return provider, model, resolve_api_key(cfg, provider), "fallback_no_key"
    return provider, model, resolve_api_key(cfg, provider), default_source
