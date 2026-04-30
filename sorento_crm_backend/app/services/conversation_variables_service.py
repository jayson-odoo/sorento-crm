"""Conversation-variables service: merge/trim turn buffer for Respond.io contacts.

Core data shape stored in `respond_contacts.session_vars`:

    {
      "turns": [
        { "ts": "2026-04-30T08:01:00Z", "inquiry_type": "complaint",
          "vars": { "customer_name": "Sri Binaraya Sdn Bhd" } },
        ...
      ],
      "merged": { "complaint": { "customer_name": "Sri Binaraya Sdn Bhd" }, ... }
    }

`turns` is the source of truth (oldest -> newest). `merged` is recomputed from
`turns` on every write so reads can return it directly without replaying.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


def _normalise_session_vars(raw: Any) -> dict[str, Any]:
    """Coerce a stored session_vars value into the canonical {'turns':[], 'merged':{}} dict."""
    if raw is None:
        return {"turns": [], "merged": {}}
    # JSONB columns may surface as dict already; tolerate raw JSON strings just in case.
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        return {"turns": [], "merged": {}}
    turns = raw.get("turns")
    merged = raw.get("merged")
    if not isinstance(turns, list):
        turns = []
    if not isinstance(merged, dict):
        merged = {}
    return {"turns": turns, "merged": merged}


def recompute_merged(turns: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Replay `turns` oldest -> newest into a per-inquiry_type rollup.

    Null values delete the key from the rollup; empty strings are preserved as a real value.
    Recomputing from scratch is the only safe way after a sliding-window eviction — an evicted
    turn may have been the last carrier of a key that no surviving turn re-supplies.
    """
    merged: dict[str, dict[str, Any]] = {}
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        inquiry_type = str(turn.get("inquiry_type") or "").strip()
        if not inquiry_type:
            continue
        vars_dict = turn.get("vars") or {}
        if not isinstance(vars_dict, dict):
            continue
        bucket = merged.setdefault(inquiry_type, {})
        for k, v in vars_dict.items():
            if v is None:
                bucket.pop(k, None)
            else:
                bucket[k] = v
    return merged


def apply_clear(
    state: dict[str, Any],
    inquiry_type: str,
) -> dict[str, Any]:
    """Drop all turns + merged state for `inquiry_type`. Other inquiry_types untouched."""
    state["turns"] = [
        t for t in state.get("turns", [])
        if isinstance(t, dict) and t.get("inquiry_type") != inquiry_type
    ]
    state.get("merged", {}).pop(inquiry_type, None)
    return state


def apply_turn(
    state: dict[str, Any],
    *,
    inquiry_type: str,
    variables: dict[str, Any],
    max_turns: int,
    clear_inquiry_type: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply one n8n turn to the session_vars dict (mutates + returns it).

    Order: clear (if requested) -> append turn (if vars non-empty) -> trim to max_turns
    -> recompute merged from surviving turns.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    state = _normalise_session_vars(state)

    if clear_inquiry_type:
        apply_clear(state, inquiry_type)

    if variables:
        state["turns"].append(
            {
                "ts": now.isoformat() + "Z",
                "inquiry_type": inquiry_type,
                "vars": variables,
            }
        )

    if max_turns < 1:
        max_turns = 1
    if len(state["turns"]) > max_turns:
        state["turns"] = state["turns"][-max_turns:]

    state["merged"] = recompute_merged(state["turns"])
    return state


def upsert_for_contact(
    db: Session,
    *,
    respond_io_id: str,
    inquiry_type: str,
    variables: dict[str, Any],
    max_turns: int,
    clear_inquiry_type: bool,
) -> dict[str, Any]:
    """Row-locked upsert against respond_contacts.session_vars.

    Returns the full session_vars dict after write so the route can shape the response.
    Raises HTTPException(404) when no respond_contacts row exists for the given respond_io_id.
    """
    row = db.execute(
        text(
            "SELECT id, session_vars FROM respond_contacts "
            "WHERE respond_io_id = :cid FOR UPDATE"
        ),
        {"cid": respond_io_id},
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Respond contact not found for respond_io_id={respond_io_id!r}.",
        )

    state = apply_turn(
        row.session_vars,
        inquiry_type=inquiry_type,
        variables=variables,
        max_turns=max_turns,
        clear_inquiry_type=clear_inquiry_type,
    )

    db.execute(
        text(
            "UPDATE respond_contacts SET session_vars = CAST(:s AS jsonb), updated_at = NOW() "
            "WHERE id = :id"
        ),
        {"s": json.dumps(state), "id": row.id},
    )
    db.commit()
    return state
