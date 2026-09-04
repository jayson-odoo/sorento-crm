"""Canned bot copy, owned by the prompt registry instead of by an n8n Code node (AC-302).

The STRINGS live in `app/services/chatbot_reply_copy.py`, outside this package, because
`ai_prompt_registry` needs them as its fallback bodies and core must never import the
chatbot package (AC-002). This file is the turn-side half: resolve every key once, hand
the result down as data.

**Resolved once per turn, then passed as data.** `escalate_catalog` is a pure function
over captured JSON so the replay corpus can grade it, which means it cannot reach for a
database. `resolve(db)` builds a `CannedCopy` at the top of the tail; `fallback_copy()`
is the same object with no DB at all, and that is what node replay uses.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.services.chatbot_reply_copy import CHATBOT_REPLY_COPY

logger = logging.getLogger(__name__)

# `short name -> registry key` and `short name -> today's text`, projected off the one
# table so this file cannot list a key the registry does not have.
REPLY_KEYS: dict[str, str] = {name: key for name, (key, _, _) in CHATBOT_REPLY_COPY.items()}
FALLBACKS: dict[str, str] = {name: text for name, (_, text, _) in CHATBOT_REPLY_COPY.items()}

_TOKEN_PREFIX = "{{"


@dataclass(frozen=True)
class CannedCopy:
    """One turn's resolved templates, keyed by the short name.

    Templates, not finished sentences: `escalate_catalog` still has to interpolate the
    team it picked (the resolved entity's company team outranks the parser's guess) and
    the parser's `user_goal`, neither of which is known when this is built.
    """

    templates: dict[str, str]

    def render(self, key: str, **variables: Any) -> str:
        """Substitute `{{token}}`. An unsupplied token is LEFT ALONE, never blanked.

        Left alone because a literal `{{team}}` in a customer reply is a loud, greppable
        defect, while a silent blank reads as a wording choice and would survive to
        production. Callers always supply what the key declares; this is the belt for a
        published template that grew a token nobody wired.
        """
        text = self.templates.get(key, FALLBACKS.get(key, ""))
        if _TOKEN_PREFIX not in text:
            return text
        for name, value in variables.items():
            text = text.replace("{{" + name + "}}", "" if value is None else str(value))
        return text


def fallback_copy() -> CannedCopy:
    """Today's text, no database. What node replay grades against."""
    return CannedCopy(templates=dict(FALLBACKS))


def resolve(db: Any) -> CannedCopy:
    """Every canned template for one turn, in ONE pass over the registry.

    Never raises: `ai_prompt_registry.get_prompt` already falls back to the hardcoded
    body on a DB error, and anything it does not catch is caught here. A bot that cannot
    read its own copy still answers with the text it shipped with.
    """
    from app.services.ai_prompt_registry import get_prompt

    templates = dict(FALLBACKS)
    for short_name, key in REPLY_KEYS.items():
        try:
            rendered = get_prompt(db, key)
        except Exception:  # noqa: BLE001 - copy resolution must never fail a turn
            logger.warning("chatbot copy key %s could not be resolved", key, exc_info=True)
            continue
        if rendered.text:
            templates[short_name] = rendered.text
    return CannedCopy(templates=templates)
