"""Who an inbound WhatsApp message buzzes, and what their phone shows.

PLAN-message-push slice S2. Pure resolution: this module reads a committed
``chat_histories`` row and answers "which users, with which link" - no queue, no
browser, no push endpoint. That is the seam the whole feature is tested through
(UAC AC-M7 to AC-M15); ``app.tasks.message_push_tasks`` does the delivery.

Three traps this module exists to avoid, all of them already paid for elsewhere:

1. **A contact holds SEVERAL open conversation trackings at once.** Conversation
   SLA stopped being one-open-per-contact, so ``get_preferred_tracking_for_contact``
   - which deliberately reduces a multi-open contact to one representative row -
   would silence every assignee but one. Every open ticket is resolved here.
2. **Form-SLA stage rows share ``conversation_sla_tracking``**, discriminated only
   by ``source_entity_type``. Matching one pushes whoever is handling a complaint
   about a message they have nothing to do with, so every query carries
   ``conversation_tracking_scope()``.
3. **``tracking.assigned_to_id`` is the recipient.** The sibling ``assigned_to``
   text column is a legacy Respond user id and is not a ``users.id``.

There is no "drop the message author" guard: an inbound message comes from the
contact, and a contact is not a CRM user, so the guard could never fire.
"""
from __future__ import annotations

import logging
from typing import NamedTuple, Optional

from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.sla import ConversationSLATracking
from app.models.user import User
from app.services.sla_service import conversation_tracking_scope

logger = logging.getLogger(__name__)

# `chat_histories.type` holds 'incoming' / 'outgoing' - the UAC calls the first
# one "inbound", which is the same thing under a name the column has never used.
# Contract note recorded in the UAC beside AC-M11.
INBOUND_TYPE = "incoming"

TRACKING_LINK = "/sla-management/conversation-sla-tracking"
_CHAT_SUFFIX = "?chat=1"

# The lock screen shows about this much anyway, and the rest is a battery cost.
BODY_MAX_CHARS = 120

DEFAULT_SCOPE = "assigned_and_coverage"
SCOPE_OFF = "off"
SCOPE_ASSIGNED_ONLY = "assigned_only"
SCOPE_ASSIGNED_AND_COVERAGE = "assigned_and_coverage"
SCOPE_ALL_CONTACTS = "all_contacts"

# Which scopes accept a push earned in which way. `off` appears in none of them.
_SCOPES_HEARING_OWN_ASSIGNMENT = frozenset(
    {SCOPE_ASSIGNED_ONLY, SCOPE_ASSIGNED_AND_COVERAGE, SCOPE_ALL_CONTACTS}
)
_SCOPES_HEARING_COVERAGE = frozenset({SCOPE_ASSIGNED_AND_COVERAGE, SCOPE_ALL_CONTACTS})


class MessagePushRecipient(NamedTuple):
    user_id: str
    link: str


class MessagePush(NamedTuple):
    """Everything the send task needs, resolved in one pass over the row."""

    title: str
    body: str
    tag: str
    contact_id: str
    recipients: list[MessagePushRecipient]


def _truncate(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= BODY_MAX_CHARS:
        return text
    return text[: BODY_MAX_CHARS - 3].rstrip() + "..."


def _display_name(contact: Optional[RespondContact], row) -> str:
    """The contact as a human, never a uuid and never an empty title.

    The stored contact name wins; a message from a contact we have no row for
    still carries the sender's name from the payload, and the phone number is the
    last readable thing left.
    """
    if contact is not None and (contact.name or "").strip():
        return str(contact.name).strip()
    from_payload = " ".join(
        part
        for part in (
            str(getattr(row, "first_name", "") or "").strip(),
            str(getattr(row, "last_name", "") or "").strip(),
        )
        if part
    )
    if from_payload:
        return from_payload
    if contact is not None and (contact.phone_number or "").strip():
        return str(contact.phone_number).strip()
    return str(getattr(row, "phone_number", "") or "").strip() or "New message"


def _open_conversation_trackings(
    db: Session, contact: RespondContact
) -> list[ConversationSLATracking]:
    """Every OPEN conversation-scope ticket for the contact, newest first.

    Newest first is what makes the de-duplication below land on the right ticket:
    a user assigned two of this contact's tickets gets the one they touched last.
    """
    return (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.respond_contact_id == contact.id,
            ConversationSLATracking.is_resolved.is_(False),
            conversation_tracking_scope(),
        )
        .order_by(ConversationSLATracking.updated_at.desc())
        .all()
    )


def _scopes_for(db: Session, user_ids: set[str]) -> dict[str, str]:
    """One query for every candidate's scope. A user row that vanished mid-flight
    is absent from the map and therefore hears nothing."""
    if not user_ids:
        return {}
    rows = (
        db.query(User.id, User.notify_push_message_scope)
        .filter(User.id.in_(user_ids))
        .all()
    )
    return {str(uid): str(scope or DEFAULT_SCOPE) for uid, scope in rows}


def build_message_push(db: Session, row) -> Optional[MessagePush]:
    """Resolve one committed ``chat_histories`` row into a push, or None.

    None means "nothing to send": an outgoing/bot/template message (AC-M11), or an
    inbound message nobody has asked to hear about.
    """
    if str(getattr(row, "type", "") or "").lower() != INBOUND_TYPE:
        return None

    respond_io_id = str(getattr(row, "contact_id", "") or "")
    contact = (
        db.query(RespondContact)
        .filter(RespondContact.respond_io_id == respond_io_id)
        .first()
        if respond_io_id
        else None
    )

    trackings = _open_conversation_trackings(db, contact) if contact is not None else []
    # An `all_contacts` recipient who owns none of these tickets lands on the most
    # recently updated open one, or on the contact-filtered list when none is open
    # (the list already reads `?contact=` - no new route needed). AC-M14a.
    fallback_link = (
        f"{TRACKING_LINK}/{trackings[0].id}{_CHAT_SUFFIX}"
        if trackings
        else f"{TRACKING_LINK}?contact={respond_io_id}"
    )

    # Candidate -> (link, how they earned it). Built in precedence order so the
    # first offer for a user wins: their own ticket beats coverage beats the
    # all_contacts fallback, and among their own tickets the newest wins because
    # `trackings` is already newest-first (AC-M12).
    offers: list[tuple[str, str, frozenset[str]]] = []
    from app.services.coverage_subscription_service import CoverageSubscriptionService

    coverage = CoverageSubscriptionService(db)
    coverage_offers: list[tuple[str, str, frozenset[str]]] = []
    for tracking in trackings:
        assignee = str(getattr(tracking, "assigned_to_id", None) or "")
        if not assignee:
            # An unassigned thread pushes only `all_contacts` users. No team
            # fallback and no tier walk: an unassigned thread is an SLA problem,
            # and the SLA system raises it through its own events (AC-M10b).
            continue
        link = f"{TRACKING_LINK}/{tracking.id}{_CHAT_SUFFIX}"
        offers.append((assignee, link, _SCOPES_HEARING_OWN_ASSIGNMENT))
        for coverer in coverage.active_subscribers_for(assignee):
            coverage_offers.append((str(coverer), link, _SCOPES_HEARING_COVERAGE))
    offers.extend(coverage_offers)

    all_contacts_ids = [
        str(uid)
        for (uid,) in db.query(User.id)
        .filter(User.notify_push_message_scope == SCOPE_ALL_CONTACTS)
        .all()
    ]
    offers.extend(
        (uid, fallback_link, frozenset({SCOPE_ALL_CONTACTS})) for uid in all_contacts_ids
    )

    scopes = _scopes_for(db, {user_id for user_id, _, _ in offers})
    recipients: list[MessagePushRecipient] = []
    seen: set[str] = set()
    for user_id, link, accepting_scopes in offers:
        if user_id in seen:
            continue
        if scopes.get(user_id, DEFAULT_SCOPE) not in accepting_scopes:
            continue
        seen.add(user_id)
        recipients.append(MessagePushRecipient(user_id=user_id, link=link))

    return MessagePush(
        title=_display_name(contact, row),
        body=_truncate(str(getattr(row, "message", "") or "")),
        tag=f"contact-{respond_io_id}",
        contact_id=respond_io_id,
        recipients=recipients,
    )


def recipients_for_message(db: Session, row) -> list[MessagePushRecipient]:
    """The named testing seam from the plan: who this row buzzes, and where to."""
    push = build_message_push(db, row)
    return push.recipients if push else []
