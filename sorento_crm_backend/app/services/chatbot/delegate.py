"""The `{delegate, ctx, item}` envelope n8n's remaining lanes run on. MIGRATION ONLY.

This file exists so that S1 can ship the head without waiting for the lanes. Each later
slice removes branch kinds from `DELEGATED_BRANCH_KINDS`; when the set empties at S7 this
whole module is deleted along with the `delegate` field on the response.

`item` must be BYTE-EQUAL to what `route-turn` emits today (AC-101). n8n replaces five
spine nodes with one HTTP call plus two one-line Code nodes that re-emit `response.ctx`
and `response.item` (AC-110), so every by-name reader downstream stays unchanged and the
old nodes can be re-enabled to roll back.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot.contracts import DELEGATED_BRANCH_KINDS


def delegate_for(branch_kind: str) -> str | None:
    """The n8n lane that must still run, or None when the CRM finished the turn."""
    return branch_kind if branch_kind in DELEGATED_BRANCH_KINDS else None


def build_envelope(
    *, turn_id: str, ctx: dict[str, Any], item: dict[str, Any], branch_kind: str
) -> dict[str, Any]:
    """The head's response body during the migration window."""
    return {
        "turn_id": turn_id,
        "ctx": ctx,
        "item": item,
        "branch_kind": branch_kind,
        "delegate": delegate_for(branch_kind),
    }
