"""Calls as the third channel (AC-M34, AC-M35, AC-M35a).

A phone call is the one thing CS does that leaves no trace today. The outbox says what
we messaged; nothing says whether anybody picked up. Fanny's complaint was *"customer
didn't receive any call from maintenance"*, and the evidence that answers it is not
"a call event fired" but whether contact was actually made - so **a call that ended is
not a call that connected**, and the outcome vocabulary is the point of the feature.

**No new table** (AC-M34). A call is an ``activity_events`` row of kind ``call``,
joining the per-entity feed that already carries notes and system events. ``kind`` is
neither ``system`` (no software did it) nor ``user_update`` (not a composer post, and it
carries structured fields no composer produces); those live in ``system_payload``, which
is where the existing system rows already put their structured data. Whether reporting
wants outcome and duration as real columns is an S9 question.

**Attribution is deliberately conservative** (AC-M35): auto-attach only when the contact
has exactly one open case. More than one, or none, and the call parks on the CONTACT
(``entity_type = 'respond_contact'``, AC-M35a) and waits in a per-contact inbox for one
click. A wrong attribution puts false evidence into the record CS relies on, which is
strictly worse than an unattributed call. ``activity_events.entity_type`` and
``entity_id`` are both NOT NULL, so parking on the contact is also the only reading that
honours "no new table" without weakening a core column for every activity type.

This module owns attribution rather than ``activities_service``, because attribution is
a rule about complaints and the generic feed must not learn to depend on them.

S5 fills the same model automatically from Respond.io's ``On Call ended`` webhook via an
MCP write tool, on this same vocabulary (AC-M36c). A second vocabulary invented there is
a migration nobody scheduled, which is why the sets below are declared as data.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.activities import ActivityEvent
from app.models.complaints import Complaint
from app.services.error_handler import handle_not_found, handle_validation_error

logger = logging.getLogger(__name__)

# AC-M34 / AC-M36c. One vocabulary, shared with S5's automatic path.
CALL_OUTCOMES = frozenset({"answered", "missed", "no_answer"})
CALL_DIRECTIONS = frozenset({"inbound", "outbound"})

# ``activity_events.kind`` for a call.
CALL_ACTIVITY_KIND = "call"
CALL_SYSTEM_TEMPLATE = "call.logged"

# AC-M35a: where a call with no attributable case parks.
UNATTACHED_ENTITY_TYPE = "respond_contact"

# AC-M35b. S4's OWN documented set of statuses that close a case for the purpose of
# call attribution, deliberately not read from ``COMPLAINT_STATUS_SEEDS.is_terminal``
# and deliberately not ``complaint_fulfilment_service.LINKABLE_STATUSES``:
#
# - LINKABLE_STATUSES = {processed_by_cs, fulfilled} answers which complaints a
#   delivery order may fulfil. Reusing it would make a freshly SUBMITTED complaint -
#   the case most likely to be the subject of a phone call - invisible to attribution.
# - The status graph marks only ``closed`` and ``voided`` terminal, which is the same
#   set as this one TODAY. It is copied rather than read because the graph is probably
#   wrong (``rejected`` and ``resolved`` look like end states carrying
#   ``is_terminal = False``), and fixing THAT changes complaint editability for live
#   records - a live behaviour change that gets its own decision and its own tests
#   rather than riding along inside S4. Copying pins the two so they move separately
#   and on purpose.
#
# The known consequence, recorded rather than hidden: a contact whose only case was
# rejected in 2024 has today's call auto-attached to it.
CLOSED_CASE_STATUSES = frozenset({"closed", "voided"})


def log_call(
    db: Session,
    *,
    contact_id: str,
    direction: str,
    outcome: str,
    duration_seconds: int = 0,
    next_action: Optional[str] = None,
    actor_id: Optional[str] = None,
    external_call_id: Optional[str] = None,
    occurred_at=None,
) -> ActivityEvent:
    """Record one call against a contact, attaching it to their case when it is safe to.

    Raises rather than parking when the contact is unknown: ``entity_id`` is NOT NULL,
    so an invented contact id would write a row nothing can ever reach - a silent loss
    dressed as a success.
    """
    direction = str(direction or "").strip().lower()
    outcome = str(outcome or "").strip().lower()
    if direction not in CALL_DIRECTIONS:
        raise handle_validation_error(
            f"Unknown call direction '{direction}'. Expected one of "
            f"{', '.join(sorted(CALL_DIRECTIONS))}."
        )
    if outcome not in CALL_OUTCOMES:
        raise handle_validation_error(
            f"Unknown call outcome '{outcome}'. Expected one of "
            f"{', '.join(sorted(CALL_OUTCOMES))} - a call that ended is not a call "
            "that connected, and free text makes that unqueryable."
        )

    contact = (
        db.query(RespondContact).filter(RespondContact.id == str(contact_id)).first()
    )
    if contact is None:
        raise handle_not_found("Contact", str(contact_id))

    case = _sole_open_case(db, str(contact_id))
    entity_type = (
        Complaint.__audit_entity_type__ if case is not None else UNATTACHED_ENTITY_TYPE
    )
    entity_id = str(case.id) if case is not None else str(contact_id)

    event = ActivityEvent(
        id=str(uuid.uuid4()),
        entity_type=entity_type,
        entity_id=entity_id,
        kind=CALL_ACTIVITY_KIND,
        system_template=CALL_SYSTEM_TEMPLATE,
        system_payload={
            "contact_id": str(contact_id),
            "direction": direction,
            "outcome": outcome,
            "duration_seconds": int(duration_seconds or 0),
            "next_action": (str(next_action).strip() if next_action else None),
            "external_call_id": (str(external_call_id) if external_call_id else None),
            "occurred_at": (occurred_at.isoformat() if occurred_at else None),
        },
        actor_id=str(actor_id) if actor_id else None,
        body_text=_summary(direction, outcome, int(duration_seconds or 0), next_action),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def attach_call(
    db: Session,
    *,
    activity_id: str,
    complaint_id: str,
    actor_id: Optional[str] = None,
) -> ActivityEvent:
    """Re-key a parked call onto a case. One click, from the per-contact inbox.

    The SAME row is re-keyed, never copied: a second row would leave the parked one
    behind, double-count the call in the feed and break any audit reference to the
    original id.
    """
    event = (
        db.query(ActivityEvent)
        .filter(
            ActivityEvent.id == str(activity_id),
            ActivityEvent.kind == CALL_ACTIVITY_KIND,
        )
        .first()
    )
    if event is None:
        raise handle_not_found("Call activity", str(activity_id))
    if str(event.entity_type) != UNATTACHED_ENTITY_TYPE:
        # Re-attribution is a rewrite of evidence. It needs its own deliberate action,
        # not a second click on the same button.
        raise handle_validation_error(
            "This call is already attached to a case. Detaching and re-filing "
            "evidence is a separate, deliberate action."
        )

    complaint = (
        db.query(Complaint).filter(Complaint.id == str(complaint_id)).first()
    )
    if complaint is None:
        raise handle_not_found("Complaint", str(complaint_id))

    contact_id = str(event.entity_id or "")
    if str(getattr(complaint, "contact_id", "") or "") != contact_id:
        # One click must not be able to file a call against a stranger's case.
        raise handle_validation_error(
            "That case belongs to a different contact; a call can only be attached "
            "to a case of the contact it was made with."
        )

    payload = dict(event.system_payload or {})
    payload["attached_by"] = str(actor_id) if actor_id else None
    payload["attached_from_contact_id"] = contact_id
    event.entity_type = Complaint.__audit_entity_type__
    event.entity_id = str(complaint.id)
    event.system_payload = payload
    db.commit()
    db.refresh(event)
    return event


def list_unattached_calls(db: Session, *, contact_id: str) -> list[ActivityEvent]:
    """The per-contact inbox (AC-M35). What makes "never auto-attributed" workable."""
    return (
        db.query(ActivityEvent)
        .filter(
            ActivityEvent.kind == CALL_ACTIVITY_KIND,
            ActivityEvent.entity_type == UNATTACHED_ENTITY_TYPE,
            ActivityEvent.entity_id == str(contact_id),
        )
        .order_by(ActivityEvent.created_at.desc())
        .all()
    )


def open_cases_for_contact(db: Session, contact_id: str) -> list[Complaint]:
    """Every non-closed case this contact owns, newest first."""
    return (
        db.query(Complaint)
        .filter(
            Complaint.contact_id == str(contact_id),
            Complaint.status.notin_(tuple(CLOSED_CASE_STATUSES)),
        )
        .order_by(Complaint.created_at.desc())
        .all()
    )


def _sole_open_case(db: Session, contact_id: str) -> Optional[Complaint]:
    """The one open case, or None when there are none or several (AC-M35)."""
    cases = open_cases_for_contact(db, contact_id)
    return cases[0] if len(cases) == 1 else None


def _summary(
    direction: str, outcome: str, duration_seconds: int, next_action: Optional[str]
) -> str:
    """Plain-text line for the feed. The structured truth stays in system_payload."""
    label = {"answered": "answered", "missed": "missed", "no_answer": "no answer"}[outcome]
    line = f"{direction.capitalize()} call - {label}"
    if duration_seconds:
        line += f" ({duration_seconds}s)"
    if next_action:
        line += f". Next: {str(next_action).strip()}"
    return line
