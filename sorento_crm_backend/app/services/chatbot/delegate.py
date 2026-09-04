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

import logging

from app.services.chatbot.contracts import BRANCH_KINDS, CRM_COMPLETED_BRANCH_KINDS

logger = logging.getLogger(__name__)


def delegate_for(branch_kind: str, enabled_lanes: frozenset[str] | None = None) -> str | None:
    """The n8n lane that must still run, or None when the CRM finished the turn.

    TWO conditions, and both are required:

    * `CRM_COMPLETED_BRANCH_KINDS` - what the CODE can complete. It grows one slice at a
      time and is a fact about this build.
    * `enabled_lanes` - what the OWNER has turned on, from
      `system_settings.chatbot_completed_lanes`. Default empty, so a freshly deployed lane
      completes nothing.

    Splitting them is what makes a lane deployable on its own. Ship the code, watch the CRM
    and n8n answer the same turn the same way for as long as you like, then add one string
    to the settings row; the n8n Switch output is deleted after that, not before. With only
    the first condition the CRM starts answering the instant it deploys and the n8n edit
    has to land in the same window or the lane runs twice.

    `enabled_lanes=None` means "nothing enabled", not "everything": an unreadable settings
    row must fail towards n8n, which still works, and never towards a half-built lane.
    """
    enabled = enabled_lanes or frozenset()
    if branch_kind in CRM_COMPLETED_BRANCH_KINDS and branch_kind in enabled:
        return None
    return branch_kind


def enabled_lanes_from(raw: object) -> frozenset[str]:
    """`system_settings.chatbot_completed_lanes` as a set, hostile input tolerated.

    This is operator data typed into a settings form, so every failure mode degrades to
    "that lane is not enabled" and warns, rather than raising: a typo must not take the
    turn engine down, and an unknown branch kind is far more likely to be a typo than a
    lane from the future (a real new lane arrives with code that adds it to
    `CRM_COMPLETED_BRANCH_KINDS`, and the pair is checked together above anyway).
    """
    if raw is None:
        return frozenset()
    if not isinstance(raw, (list, tuple)):
        logger.warning(
            "system_settings.chatbot_completed_lanes is %s, not a list - no lane enabled",
            type(raw).__name__,
        )
        return frozenset()
    known: set[str] = set()
    for value in raw:
        if not isinstance(value, str):
            logger.warning(
                "chatbot_completed_lanes entry %r is not a string - ignored", value
            )
            continue
        if value not in BRANCH_KINDS:
            logger.warning(
                "chatbot_completed_lanes names %r, which is not a branch kind - ignored", value
            )
            continue
        known.add(value)
    return frozenset(known)

