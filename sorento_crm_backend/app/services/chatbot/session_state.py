"""The five-key session shape, read from wherever a contact's row actually holds it.

`respond_contacts.session_vars` is `{focus, open_question, ideation, access_levels,
contains_flyer}` (AC-1504). A contact mid-conversation at deploy still carries the
pre-rearch nest, `{"variables": {...}}`, written by n8n's outer loop - so every read goes
through here and accepts both, and every write goes through `turn/tail.py::persist`,
which only ever writes the five keys at the top level.

This module is the ONE place that knows the legacy nest exists. Nothing else reads
`session_vars.variables`.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot import jsc
from app.services.chatbot.turn.pending import OFFER_KINDS, Pending, from_wire

FIVE_KEYS = ("focus", "open_question", "ideation", "access_levels", "contains_flyer")


def five_keys(session_block: Any) -> dict[str, Any]:
    """The five keys off `get-session-vars`' own body (`{"session_vars": {...}}`)."""
    state = jsc.get(session_block, "session_vars")
    state = state if isinstance(state, dict) else {}
    if any(key in state for key in FIVE_KEYS):
        return {key: state.get(key) for key in FIVE_KEYS}
    legacy = state.get("variables")
    legacy = legacy if isinstance(legacy, dict) else {}
    return {key: legacy.get(key) for key in FIVE_KEYS}


def pending_of(session_block: Any) -> Pending | None:
    """The one open question this contact is carrying, or None."""
    return from_wire(five_keys(session_block).get("open_question"))


def offer_is_open(session_block: Any) -> bool:
    """Is an escalation offer open? (contract 43, R3/AC-106.)

    The marker, never the previous reply's wording: the phrase-matching regex this
    replaces was `head/output_exchange.offer_is_open`, retired with that module. An offer
    kind is any pending that is not a roster - `team_pick` and `member_offer` are what
    reach here in practice, and both are `OFFER_KINDS` members by construction.
    """
    pending = pending_of(session_block)
    return pending is not None and pending.kind in OFFER_KINDS
