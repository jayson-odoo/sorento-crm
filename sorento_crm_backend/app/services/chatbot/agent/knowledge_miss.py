"""Arming the marketing product team offer after a knowledge miss (AGENTIC-KNOWLEDGE P2 W1).

The write sets the contact's open question to the bot's own single-team pick, so it lives in the
chatbot package: it speaks `turn.pending`, and core must never import the package (AC-002,
`tests/chatbot/test_import_boundary.py`). Who may be offered stays in core
(`knowledge_service.offerable_contact`), because the handoff tool's read and this write must
agree on it, and the read has no reason to cross the boundary.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.services import knowledge_service
from app.services.chatbot.turn import pending as turn_pending

__all__ = ["arm_knowledge_miss_offer"]

_MISS_TEAM = "marketing_product"
_MISS_AGENT = "general_enquiries"


def arm_knowledge_miss_offer(db: Session, contact_pk: str) -> bool:
    """Arm the bot's single-team offer as the contact's open question, so the contact's own next
    "yes" reaches today's escalation lane (no ticket is made here). False, writing nothing, for a
    barred contact, a staff-tier profile, or a missing contact."""
    with company_scope(db, None):
        contact = knowledge_service.offerable_contact(db, contact_pk)
        if contact is None:
            return False
        option = {
            "position": 1, "label": "Marketing product team", "entity_type": "team",
            "payload": {"team": _MISS_TEAM, "agent": _MISS_AGENT, "brand_code": None},
        }
        pending = turn_pending.ask(
            "team_pick", [option], team=_MISS_TEAM, expects="yes_no",
            payload={"source": knowledge_service.KNOWLEDGE_MISS_SOURCE, "agent": _MISS_AGENT},
        )
        session_vars = dict(contact.session_vars) if isinstance(contact.session_vars, dict) else {}
        session_vars["open_question"] = turn_pending.to_wire(pending)
        contact.session_vars = session_vars  # a new dict, so the JSONB change is seen
        db.flush()
    return True
