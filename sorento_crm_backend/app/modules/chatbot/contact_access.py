"""The agent's contact-side reads, published for core (DOC-ACCESS-SIMPLE, AC-002).

The Document Access preview (`app/services/document_access_service.py`) decides who a contact runs
as and which access codes it holds with the SAME helpers the agent uses
(`app/services/chatbot/agent/access.py`), so the page cannot disagree with the bot. Core may not
import the package (`tests/chatbot/test_import_boundary.py`), so it reaches them through this
doorway, as `lane_vocabulary.py` does for the settings screen.

Each function imports at call time and delegates unchanged: there is no second copy of the logic.
"""
from __future__ import annotations


def active_access_codes(db, contact_pk: str) -> frozenset[str]:
    """The contact's assigned access codes whose catalogue row is active. Fail closed: none."""
    from app.services.chatbot.agent import access

    return access._active_access_codes(db, contact_pk)


def contact_row_count(db, contact_respond_id: str) -> int:
    """How many contact rows share the respond.io id (more than one = ambiguous to the agent)."""
    from app.services.chatbot.agent import access

    return access._row_count(db, contact_respond_id)


def agent_switch_on(db, contact) -> bool:
    """The agent switch: the contact AND every row sharing its respond.io id have it on."""
    from app.services.chatbot.agent import access

    return access.agent_switch_on(db, contact)


def linked_active_user(db, contact_pk: str):
    """The active CRM user linked to the contact (the contact then runs as staff), or None."""
    from app.services.chatbot.agent import access

    return access.linked_active_user(db, contact_pk)
