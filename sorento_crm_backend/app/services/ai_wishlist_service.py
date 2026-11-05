"""Service for tracking unanswered AI assistant queries and exposing clusters.

The clustering itself is performed offline by ``app.jobs.ai_wishlist_clustering``;
this module is the read/write boundary used at request time (insert link rows
when a turn was unanswered) and at admin read time (list clusters).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.ai_assistant import (
    AIAssistantUnansweredQuery,
    AIAssistantWishlistCluster,
)
from app.models.chatbot_turn import ChatbotTurn
from app.models.user import User


logger = logging.getLogger(__name__)

# The trace event the agent loop writes for an ask no tool could do (GAP-SIGNAL). Defined here, in core,
# because core must not import `app.services.chatbot` (`tests/chatbot/test_import_boundary.py`).
NO_TOOL_EVENT = "agent_no_tool"


class AiWishlistService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def tag_unanswered(self, message_id: str) -> None:
        """Insert (or no-op on conflict) a placeholder row for clustering.

        The nightly job fills in the embedding + cluster_id later.
        """
        if not message_id:
            return
        existing = (
            self.db.query(AIAssistantUnansweredQuery)
            .filter(AIAssistantUnansweredQuery.message_id == message_id)
            .first()
        )
        if existing:
            return
        try:
            row = AIAssistantUnansweredQuery(message_id=message_id)
            self.db.add(row)
            self.db.commit()
        except Exception:
            logger.exception("Failed to tag unanswered query message_id=%s", message_id)
            self.db.rollback()

    def list_clusters(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = (
            self.db.query(AIAssistantWishlistCluster)
            .order_by(AIAssistantWishlistCluster.count.desc(), AIAssistantWishlistCluster.last_seen_at.desc())
            .limit(max(1, int(limit)))
            .all()
        )
        return [
            {
                "id": str(r.id),
                "representative_question": r.representative_question or "",
                "category": r.category,
                "count": int(r.count or 0),
                "last_seen_at": r.last_seen_at,
                "created_at": r.created_at,
            }
            for r in rows
        ]

    def list_no_tool(self, days: int = 30, limit: int = 200) -> list[dict[str, Any]]:
        """GAP-SIGNAL: the asks the agent flagged as `no_tool` (no tool could do them), newest first.

        Read straight off `chatbot.turns.trace` (the `agent_no_tool` event the agent loop writes), so it
        needs no clustering job and no embedding key.
        """
        since = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
        turns = (
            self.db.query(ChatbotTurn.id, ChatbotTurn.contact_respond_id, ChatbotTurn.created_at, ChatbotTurn.trace)
            .filter(ChatbotTurn.created_at >= since)
            .filter(ChatbotTurn.trace.contains([{"kind": NO_TOOL_EVENT}]))
            .order_by(ChatbotTurn.created_at.desc())
            .limit(max(1, int(limit)))
            .all()
        )
        rows: list[dict[str, Any]] = []
        for turn_id, contact_id, created_at, trace in turns:
            for event in trace or []:
                if not isinstance(event, dict) or event.get("kind") != NO_TOOL_EVENT:
                    continue
                for item in event.get("items") or []:
                    if isinstance(item, dict) and isinstance(item.get("ask"), str) and item["ask"].strip():
                        rows.append(
                            {
                                "turn_id": str(turn_id),
                                "ask": item["ask"],
                                "area": item.get("area") if isinstance(item.get("area"), str) else None,
                                "user_id": event.get("user_id") or None,
                                "contact_id": contact_id,
                                "channel": event.get("channel") or None,
                                "asked_at": created_at,
                            }
                        )
        user_ids = {r["user_id"] for r in rows if r["user_id"]}
        names: dict[str, str] = {}
        if user_ids:
            names = {str(uid): name for uid, name in self.db.query(User.id, User.name).filter(User.id.in_(user_ids))}
        contact_ids = {r["contact_id"] for r in rows if not r["user_id"] and r["contact_id"]}
        contacts: dict[str, str] = {}
        if contact_ids:
            contacts = {
                str(rid): name
                for rid, name in self.db.query(RespondContact.respond_io_id, RespondContact.name).filter(
                    RespondContact.respond_io_id.in_(contact_ids)
                )
                if name
            }
        for r in rows:
            user_id, contact_id = r.pop("user_id"), r.pop("contact_id")
            r["who"] = names.get(str(user_id)) if user_id else contacts.get(str(contact_id))
        return rows
