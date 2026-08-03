"""Waiting attribution: the system learns to say "waiting on someone who is not us".

Satisfies AC-M1 to AC-M7 and AC-M36d.

Every delay in this system currently reads as internal inaction. 307 form-SLA trackers
are open and overdue on the production copy and not one of them can say why, so the
dashboard blames whoever holds the record even when the record is sitting on a plumber.
That is one gap behind four separate complaints (R2, R7, R8, R12), and this module is
the whole of the answer.

**Waiting lives on the TRACKER** (Ruling 1, ``PLAN-after-sales-warranty.md``). AC-M1
says "a case", which taken literally is a column on all six ``FORM_SLA_TYPES`` tables
plus ``service_jobs``. Group M itself speaks per-stage twice - R12 and AC-M36d both say
"on the Schedule stage" - a case running Acknowledge, Assess, Schedule and Resolve
concurrently is not waiting on one party, and AC-M7 counts breaches, which are
trackers. ``case_waiting()`` derives the case-level answer from the case's open
trackers instead of storing it.

**The clock is never touched** (AC-M2). Time spent waiting on an external party still
counts toward resolution: pausing makes "how long did this take from the customer's
point of view" unanswerable - their toilet is broken whether or not our clock runs -
and it is the classic gamed metric, where a queue parked on "pending customer" reports
a perfect SLA. SLA numbers will look worse. Attribution is what makes that honest
rather than merely bad. A genuine deadline move is Extend, and only Extend (AC-M6).

**Its own module, not part of ``form_sla_service``.** The status engine has to be able
to ask "is this attributed" before it allows a transition, and ``status_service``
importing 1400 lines of routing and escalation to do it would couple the engine to the
form-SLA layer for one question.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.models.sla import ConversationSLAEventLog, ConversationSLATracking
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ vocabularies

PARTY_SET_KEY = "sla_waiting_party"
PARTY_SET_NAME = "SLA waiting party"
PARTY_SET_DESCRIPTION = (
    "Who a delayed case is waiting on. attributes.is_external answers whether the "
    "delay is ours (AC-M7)."
)

REASON_SET_KEY = "sla_waiting_reason"
REASON_SET_NAME = "SLA waiting reason"
REASON_SET_DESCRIPTION = (
    "Why a case is waiting. ONE vocabulary serves the pending reason and the overdue "
    "reason (AC-M1): 'pending plumber' is the same fact whether or not the clock has "
    "expired, and two lists would drift."
)

# AC-M1's list plus ``dealer``, which AC-M18 requires and AC-M1 omits. The UAC ruled
# the party is configurable master data for exactly that reason: a closed enum was
# already one value short on day one.
PARTIES: tuple[tuple[str, str, bool, str], ...] = (
    ("cs", "Customer Service", False, "Our own CS team holds the case."),
    ("maintenance", "Maintenance", False, "Sorento's own maintenance team."),
    ("warehouse", "Warehouse", False, "Our warehouse: stock, packing, collection."),
    ("plumber", "Plumber", True, "An external plumber or contract technician."),
    ("customer", "Customer", True, "The consumer: a reply, a date, or site access."),
    ("supplier", "Supplier", True, "An external supplier of parts or product."),
    ("dealer", "Dealer", True, "The dealer who sold the product (AC-M18)."),
)

REASONS: tuple[tuple[str, str], ...] = (
    ("awaiting_customer_reply", "Awaiting customer reply"),
    ("awaiting_site_access", "Awaiting site access"),
    ("customer_not_reachable", "Customer not reachable"),
    ("awaiting_visit_date", "Awaiting a confirmed visit date"),
    ("pending_plumber", "Pending plumber attendance"),
    ("pending_maintenance", "Pending maintenance team"),
    ("awaiting_spare_part", "Awaiting spare part"),
    ("awaiting_supplier", "Awaiting supplier response"),
    ("awaiting_dealer_ack", "Awaiting dealer acknowledgement"),
    ("awaiting_collection", "Awaiting collection"),
    ("awaiting_internal_approval", "Awaiting internal approval"),
)

WAITING_TABLE = "conversation_sla_tracking"
PARTY_COLUMN = "waiting_on_party"
REASON_COLUMN = "waiting_on_reason"

WAITING_SET_EVENT = "waiting_set"
WAITING_CLEARED_EVENT = "waiting_cleared"

# The code the FE branches on to open the waiting dropdown, rather than string-matching
# a message that will be reworded.
ATTRIBUTION_ERROR_CODE = "waiting_attribution_required"

# AC-M36d. Three unanswered calls is what makes "waiting on the customer" defensible
# rather than a shrug.
UNANSWERED_CALL_THRESHOLD = 3

# AC-M4, ruled 2026-08-03. Every one of these is a HUMAN action on an already-overdue
# tracker. What is deliberately absent matters as much as what is here:
#
# - anything a machine does. The escalation cron has no answer to give, and guarding it
#   would either stall every overdue tracker forever or force the system to invent an
#   attribution, which is worse than admitting there is none.
# - 'claim' / 'release'. Picking up somebody else's escalated work is the behaviour we
#   want; taxing it with a dropdown before the claimant has even read the case
#   discourages exactly the right action.
# - 'save'. Editing a phone number on an overdue case is not the moment to demand it.
_GUARDED_ACTIONS = frozenset({"resolve", "escalate", "extend"})


def guarded_actions() -> frozenset:
    """The action set AC-M4's "before further action" resolves to."""
    return _GUARDED_ACTIONS


# ------------------------------------------------------------------ the seeder


def _apply(row, values: Dict[str, Any]) -> bool:
    changed = False
    for key, value in values.items():
        if getattr(row, key, None) != value:
            setattr(row, key, value)
            changed = True
    return changed


def seed_sla_waiting_lookups(db: Session) -> Dict[str, int]:
    """Create or CORRECT both vocabularies, their options and their bindings.

    Converging rather than insert-if-absent, for the same reason the disposition seed
    converges: a re-run repairs a drifted label or a wrongly deactivated option in
    place, and can therefore fix a prior bad run. A duplicated set would be worse than
    a drifted one, because the binding would have two candidate option lists and the
    validator would pick between them non-deterministically.

    Existing options that are NOT in the seed are left alone: an operator adding
    "landlord" must survive the next deploy, which is the entire point of the party
    being data.

    ``tenant_id`` is NULL, like every existing binding, while the tenant is a stub.
    """
    summary = {"sets": 0, "options": 0, "bindings": 0}

    def _set(set_key: str, name: str, description: str) -> LookupSet:
        row = (
            db.query(LookupSet)
            .filter(LookupSet.set_key == set_key, LookupSet.tenant_id.is_(None))
            .first()
        )
        values = {"name": name, "description": description, "is_active": True}
        if row is None:
            row = LookupSet(id=str(uuid.uuid4()), tenant_id=None, set_key=set_key, **values)
            db.add(row)
            summary["sets"] += 1
        elif _apply(row, values):
            summary["sets"] += 1
        db.flush()  # the set id must exist before options and bindings reference it
        return row

    def _option(set_row: LookupSet, value: str, values: Dict[str, Any]) -> LookupOption:
        row = (
            db.query(LookupOption)
            .filter(
                LookupOption.set_id == set_row.id,
                func.lower(LookupOption.value) == value.lower(),
            )
            .first()
        )
        if row is None:
            row = LookupOption(id=str(uuid.uuid4()), set_id=set_row.id, value=value, **values)
            db.add(row)
            summary["options"] += 1
        elif _apply(row, values):
            summary["options"] += 1
        return row

    def _binding(set_row: LookupSet, table: str, column: str) -> None:
        row = (
            db.query(LookupBinding)
            .filter(
                LookupBinding.tenant_id.is_(None),
                LookupBinding.table_name == table,
                LookupBinding.column_name == column,
            )
            .first()
        )
        if row is None:
            db.add(
                LookupBinding(
                    id=str(uuid.uuid4()),
                    tenant_id=None,
                    set_id=set_row.id,
                    table_name=table,
                    column_name=column,
                )
            )
            summary["bindings"] += 1
        elif _apply(row, {"set_id": set_row.id}):
            summary["bindings"] += 1

    party_set = _set(PARTY_SET_KEY, PARTY_SET_NAME, PARTY_SET_DESCRIPTION)
    for order, (value, label, is_external, description) in enumerate(PARTIES):
        _option(
            party_set,
            value,
            {
                "label": label,
                "sort_order": order,
                "is_active": True,
                "description": description,
                # Whether the delay is ours is a property of the option, not a tuple in
                # this module: adding a party in the admin UI would otherwise silently
                # file it on one side of the AC-M7 headline.
                "attributes": {"is_external": bool(is_external)},
            },
        )

    reason_set = _set(REASON_SET_KEY, REASON_SET_NAME, REASON_SET_DESCRIPTION)
    for order, (value, label) in enumerate(REASONS):
        _option(reason_set, value, {"label": label, "sort_order": order, "is_active": True})

    _binding(party_set, WAITING_TABLE, PARTY_COLUMN)
    _binding(reason_set, WAITING_TABLE, REASON_COLUMN)
    db.flush()
    return summary


# ------------------------------------------------------------------ party helpers


def _party_options(db: Session) -> List[LookupOption]:
    party_set = (
        db.query(LookupSet)
        .filter(LookupSet.set_key == PARTY_SET_KEY, LookupSet.tenant_id.is_(None))
        .first()
    )
    if party_set is None:
        return []
    return db.query(LookupOption).filter(LookupOption.set_id == party_set.id).all()


def _party_option(db: Session, party: str) -> Optional[LookupOption]:
    value = str(party or "").strip().lower()
    for option in _party_options(db):
        if str(option.value or "").lower() == value:
            return option
    return None


def is_external_party(db: Session, party: Optional[str]) -> bool:
    """Whether this party is somebody other than us (AC-M7).

    Unset reads as INTERNAL. When we do not know whose delay it is, the conservative
    answer is that it is ours: the failure in the other direction is a report that
    quietly excuses us, which is the exact thing attribution exists to prevent.
    """
    option = _party_option(db, party) if party else None
    if option is None:
        return False
    attributes = getattr(option, "attributes", None) or {}
    return bool(attributes.get("is_external", False))


# ------------------------------------------------------------------ overdue


def is_overdue(tracker: ConversationSLATracking, now: Optional[datetime] = None) -> bool:
    """The split-clock breach rule, in one place.

    Pre-response the response deadline gates; post-response ONLY the resolution
    deadline does, because the response clock stops on response and ``extend`` moves
    ``due_at_resolution`` alone. Without the split, a tracker that responded on time
    reads as overdue forever and extend cannot rescue it.

    ``scan_overdue_and_escalate`` calls this, so the guard and the escalation scan can
    never disagree about what "overdue" means - a guard with its own ``due_at < now``
    would reject actions the scan considers perfectly on time.
    """
    if tracker is None or bool(getattr(tracker, "is_resolved", False)):
        return False
    moment = now or datetime.utcnow()
    due = getattr(tracker, "due_at", None)
    due_resolution = getattr(tracker, "due_at_resolution", None)
    responded = bool(getattr(tracker, "is_responded", False))
    return bool(
        (not responded and due is not None and due < moment)
        or (due_resolution is not None and due_resolution < moment)
    )


# ------------------------------------------------------------------ set and clear


def _tracker(db: Session, tracking_id: str) -> ConversationSLATracking:
    tracker = (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.id == str(tracking_id))
        .first()
    )
    if tracker is None:
        raise AppException(status_code=404, message="SLA tracking not found.", code="NOT_FOUND")
    return tracker


def _write_waiting_event(
    db: Session,
    tracker: ConversationSLATracking,
    *,
    event_type: str,
    party: Optional[str],
    reason: Optional[str],
    waiting_since: Optional[datetime],
    reason_text: Optional[str],
    actor_user_id: Optional[str],
) -> None:
    """One event row per waiting change, written directly rather than through
    ``create_event_log``.

    ``create_event_log`` stamps the tracker's LIVE values onto the row, which is right
    for every other event type and wrong for these two: the cleared row must record
    what we STOPPED waiting on, and by the time it is written the live value is already
    gone. A row of NULLs would say nothing, and the duration of the wait would be
    unrecoverable.
    """
    db.add(
        ConversationSLAEventLog(
            id=str(uuid.uuid4()),
            sla_tracking_id=str(tracker.id),
            event_type=event_type,
            event_at=datetime.utcnow(),
            reason=reason_text,
            trigger="manual",
            triggered_by_id=str(actor_user_id) if actor_user_id else None,
            waiting_on_party=party,
            waiting_on_reason=reason,
            waiting_since=waiting_since,
        )
    )
    db.flush()


def set_waiting(
    db: Session,
    tracking_id: str,
    *,
    party: str,
    reason: Optional[str] = None,
    actor_user_id: Optional[str] = None,
) -> ConversationSLATracking:
    """Name who this stage is waiting on (AC-M1). Touches no clock (AC-M2).

    Re-setting the SAME party keeps ``waiting_since``: correcting the reason is an
    edit of one wait, not the start of a new one, and restarting the clock would turn
    "waiting on maintenance since 3 Aug" into "since just now". A DIFFERENT party is a
    different wait and does restart it.
    """
    tracker = _tracker(db, tracking_id)
    option = _party_option(db, party)
    if option is None:
        raise AppException(
            status_code=422,
            message=(
                f"Unknown waiting party '{party}'. Pick one from the "
                f"'{PARTY_SET_KEY}' list, or add it there first - free text here "
                "would split one party into three rows in the attribution report."
            ),
            code="VALIDATION_ERROR",
        )
    if not bool(getattr(option, "is_active", True)):
        raise AppException(
            status_code=422,
            message=(
                f"'{option.label}' is deactivated and cannot be set. Cases already "
                "waiting on it keep reading as they did."
            ),
            code="VALIDATION_ERROR",
        )

    value = str(option.value)
    previous = str(tracker.waiting_on_party) if tracker.waiting_on_party else None
    if previous != value or tracker.waiting_since is None:
        tracker.waiting_since = datetime.utcnow()
    tracker.waiting_on_party = value
    tracker.waiting_on_reason = _reason_value(db, reason)
    db.flush()

    _write_waiting_event(
        db,
        tracker,
        event_type=WAITING_SET_EVENT,
        party=value,
        reason=tracker.waiting_on_reason,
        waiting_since=tracker.waiting_since,
        reason_text=_waiting_reason_text(db, tracker, value),
        actor_user_id=actor_user_id,
    )
    return tracker


def clear_waiting(
    db: Session, tracking_id: str, *, actor_user_id: Optional[str] = None
) -> ConversationSLATracking:
    """Stop waiting. Writes its own event, because "we stopped waiting on the plumber
    on Tuesday" is invisible otherwise and the duration of the wait is lost with it.
    """
    tracker = _tracker(db, tracking_id)
    party = str(tracker.waiting_on_party) if tracker.waiting_on_party else None
    reason = str(tracker.waiting_on_reason) if tracker.waiting_on_reason else None
    since = tracker.waiting_since
    if party is None and since is None:
        return tracker

    tracker.waiting_on_party = None
    tracker.waiting_on_reason = None
    tracker.waiting_since = None
    db.flush()

    _write_waiting_event(
        db,
        tracker,
        event_type=WAITING_CLEARED_EVENT,
        party=party,
        reason=reason,
        waiting_since=since,
        reason_text=None,
        actor_user_id=actor_user_id,
    )
    return tracker


def _waiting_reason_text(
    db: Session, tracker: ConversationSLATracking, party: str
) -> Optional[str]:
    """AC-M36d: the justification travels with the claim.

    "Waiting on the customer" with nothing behind it is the shrug AC-M36d was written
    against. When the party is the customer and we have been unable to reach them, the
    count of unanswered calls lands here, beside the claim it justifies.
    """
    if party != "customer":
        return None
    contact_id = getattr(tracker, "respond_contact_id", None)
    if not contact_id:
        return None
    try:
        evidence = unanswered_call_evidence(db, str(contact_id))
    except Exception as exc:  # pragma: no cover - evidence is never worth a 500
        logger.warning("Unanswered-call evidence lookup failed: %s", exc)
        return None
    if not evidence["count"]:
        return None
    return (
        f"{evidence['count']} unanswered call(s) to the contact, last at "
        f"{evidence['last_at']}."
    )


# ------------------------------------------------------------------ the AC-M4 guard


def _attribution_error(action: str) -> AppException:
    return AppException(
        status_code=422,
        message=(
            "This stage is past its deadline. Say who it is waiting on before you "
            f"{action} it - an unattributed breach reads as our inaction, which is "
            "what the SLA report will show."
        ),
        code=ATTRIBUTION_ERROR_CODE,
    )


def assert_attributed(
    db: Session,
    tracker: ConversationSLATracking,
    action: str,
    *,
    now: Optional[datetime] = None,
) -> None:
    """AC-M4: an overdue stage must name its wait before a human moves it on.

    Silent for an action outside the guarded set, for a tracker inside its deadline,
    for one that already carries a party, and for any tracker whose entity is not an
    after-sales case.

    **That last scope is the whole safety argument.** ``extend_tracking`` serves
    conversation SLA (n8n rows, ``source_entity_type IS NULL``) and all six form types
    from one method, and blocking an n8n extend because an after-sales AC wants
    attribution would break a live integration that no after-sales AC governs - the
    lesson AC-M33 taught one slice ago. In scope means REGISTERED ON THE STATUS ENGINE,
    which today is complaint and workflow_submission, both after-sales cases.
    """
    if action not in _GUARDED_ACTIONS:
        return
    if not is_in_scope(db, getattr(tracker, "source_entity_type", None)):
        return
    if not is_overdue(tracker, now):
        return
    if str(getattr(tracker, "waiting_on_party", "") or "").strip():
        return
    raise _attribution_error(action)


def is_in_scope(db: Session, source_entity_type: Optional[str]) -> bool:
    """Whether waiting attribution governs this entity type at all.

    Registration on the status engine is the test, for two reasons. It is already how
    this build decides an entity is a case with a lifecycle (ADR-0013), and it is data:
    the day somebody registers stock inquiries on the engine, they have opted that flow
    in deliberately rather than discovering it in a 422.
    """
    from app.services.status_service import resolve_graph

    entity_type = str(source_entity_type or "").strip()
    if not entity_type:
        return False  # conversation SLA: an n8n thread, not a case
    try:
        return bool(resolve_graph(db, entity_type, None).statuses)
    except Exception as exc:  # pragma: no cover - an unseeded graph is not a breach
        logger.warning("Status graph lookup failed for %s: %s", entity_type, exc)
        return False


def assert_case_transition_attributed(
    db: Session,
    entity_type: str,
    entity_id: str,
    to_key: Optional[str],
    *,
    now: Optional[datetime] = None,
) -> None:
    """The resolve half of AC-M4, enforced where a rejection can reach a human.

    Form-SLA resolve is event-driven: a status change calls ``emit_form_event``, which
    calls ``_resolve_for_active``. That path swallows exceptions twice - once per
    config inside ``emit_event``'s loop, and again at every call site, each of which
    wraps the emit in ``try/except`` and warns - and both swallows sit AFTER
    ``db.commit()``. A guard raised there would be logged and discarded: the case would
    close and its overdue stage would stay open forever, which is strictly worse than
    no guard. So this runs from the status engine's transition guard, before the
    commit, where the 422 reaches the route.

    Narrow by construction. It fires only for a transition that MATCHES a config's
    ``resolve_event`` for a stage that is actually overdue and unattributed. Everything
    else - recording ordinary progress, a case with nothing overdue, a form type that
    is not registered on the status engine - passes straight through.
    """
    from app.models.sla import FormSLAConfig

    target = str(to_key or "").strip()
    if not target or not entity_id:
        return

    # Scope check here as well as inside assert_attributed, so a caller reading only
    # this function sees the boundary: purchase requests, sponsorship forms, stock
    # inquiries and tickets share emit_form_event but are not on the status engine, and
    # AC-M4 governs none of them.
    if not is_in_scope(db, entity_type):
        return

    configs = (
        db.query(FormSLAConfig)
        .filter(
            FormSLAConfig.source_entity_type == str(entity_type),
            FormSLAConfig.is_active.is_(True),
        )
        .all()
    )
    resolving = [
        c
        for c in configs
        if target in {t.strip() for t in str(c.resolve_event or "").split(",") if t.strip()}
    ]
    if not resolving:
        return

    team_sets = {str(c.team_set_code) for c in resolving if c.team_set_code}
    trackers = (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type == str(entity_type),
            ConversationSLATracking.source_entity_id == str(entity_id),
            ConversationSLATracking.is_resolved.is_(False),
        )
        .all()
    )
    for tracker in trackers:
        if team_sets and str(tracker.team_set_code or "") not in team_sets:
            continue
        assert_attributed(db, tracker, "resolve", now=now)


# ------------------------------------------------------------------ the case view


def case_waiting(
    db: Session, source_entity_type: str, source_entity_id: str
) -> List[Dict[str, Any]]:
    """What a CASE is waiting on right now, derived from its open stages (Ruling 1).

    One entry per open stage that names a wait. A case waiting on the customer at
    Schedule and on maintenance at Assess is waiting on both, which a single stored
    column would have had to pick between. Resolved stages are history and live in the
    event log.
    """
    trackers = (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type == str(source_entity_type),
            ConversationSLATracking.source_entity_id == str(source_entity_id),
            ConversationSLATracking.is_resolved.is_(False),
            ConversationSLATracking.waiting_on_party.isnot(None),
        )
        .order_by(ConversationSLATracking.waiting_since.asc())
        .all()
    )
    if not trackers:
        return []

    reason_labels = _reason_labels(db)
    party_labels = {str(o.value): str(o.label) for o in _party_options(db)}

    return [
        {
            "tracking_id": str(tracker.id),
            "stage": str(tracker.team_set_code or "") or None,
            "party": str(tracker.waiting_on_party),
            "party_label": party_labels.get(str(tracker.waiting_on_party)),
            "reason": str(tracker.waiting_on_reason) if tracker.waiting_on_reason else None,
            "reason_label": reason_labels.get(str(tracker.waiting_on_reason or "")),
            "since": tracker.waiting_since,
            "is_external": is_external_party(db, tracker.waiting_on_party),
            "is_overdue": is_overdue(tracker),
        }
        for tracker in trackers
    ]


def _reason_options(db: Session) -> List[LookupOption]:
    reason_set = (
        db.query(LookupSet)
        .filter(LookupSet.set_key == REASON_SET_KEY, LookupSet.tenant_id.is_(None))
        .first()
    )
    if reason_set is None:
        return []
    return db.query(LookupOption).filter(LookupOption.set_id == reason_set.id).all()


def _reason_labels(db: Session) -> Dict[str, str]:
    return {str(o.value): str(o.label) for o in _reason_options(db)}


def _reason_value(db: Session, reason: Optional[str]) -> Optional[str]:
    """Resolve a reason to its canonical option value, or refuse it.

    Same rule as the party: free text here splits one reason into three rows in any
    report that groups by it. NULL is allowed - naming the party is the mandatory half
    (AC-M4), and a reason we do not have yet should not block saying who we are on.
    """
    if reason is None or not str(reason).strip():
        return None
    wanted = str(reason).strip().lower()
    for option in _reason_options(db):
        if str(option.value or "").lower() == wanted:
            if not bool(getattr(option, "is_active", True)):
                raise AppException(
                    status_code=422,
                    message=f"'{option.label}' is deactivated and cannot be set.",
                    code="VALIDATION_ERROR",
                )
            return str(option.value)
    raise AppException(
        status_code=422,
        message=(
            f"Unknown waiting reason '{reason}'. Pick one from the "
            f"'{REASON_SET_KEY}' list, or add it there first."
        ),
        code="VALIDATION_ERROR",
    )


# ------------------------------------------------------------------ AC-M7 reporting


def attribution_summary(
    db: Session,
    *,
    source_entity_type: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Breaches, attributed (AC-M7).

    Reads the CAPTURED value on the escalation event, never the tracker's live column:
    a report built on the live column silently re-attributes every historical breach
    the next time somebody edits the case, and last month's numbers change shape.

    Three buckets, not two. "Of 40 breaches, 26 were waiting on an external party"
    invites the reader to assume the other 14 were ours; some of them are simply
    unexplained, and folding those into "internal" is how the metric becomes a lie.
    """
    query = db.query(ConversationSLAEventLog).filter(
        ConversationSLAEventLog.event_type == "escalation"
    )
    if source_entity_type:
        query = query.join(
            ConversationSLATracking,
            ConversationSLATracking.id == ConversationSLAEventLog.sla_tracking_id,
        ).filter(ConversationSLATracking.source_entity_type == str(source_entity_type))
    if since:
        query = query.filter(ConversationSLAEventLog.event_at >= since)
    if until:
        query = query.filter(ConversationSLAEventLog.event_at <= until)

    by_party: Dict[str, int] = {}
    external = internal = unattributed = 0
    for row in query.all():
        party = str(row.waiting_on_party or "").strip()
        if not party:
            unattributed += 1
            continue
        by_party[party] = by_party.get(party, 0) + 1
        if is_external_party(db, party):
            external += 1
        else:
            internal += 1

    return {
        "breaches": external + internal + unattributed,
        "external": external,
        "internal": internal,
        "unattributed": unattributed,
        "by_party": by_party,
    }


# ------------------------------------------------------------------ AC-M36d


def unanswered_call_evidence(
    db: Session, respond_contact_id: str, since: Optional[datetime] = None
) -> Dict[str, Any]:
    """How many times we called this contact and nobody picked up, most recent first.

    Counts the UNBROKEN run of unanswered calls, so an answered call resets it:
    reaching somebody is the opposite of being unable to reach them, and counting
    every no-answer ever would let a call from March justify a wait in August.
    """
    from app.models.activities import ActivityEvent
    from app.services.call_activity_service import CALL_ACTIVITY_KIND

    query = db.query(ActivityEvent).filter(
        ActivityEvent.kind == CALL_ACTIVITY_KIND,
        ActivityEvent.system_payload["contact_id"].astext == str(respond_contact_id),
    )
    if since:
        query = query.filter(ActivityEvent.created_at >= since)
    # Ordered by when the call HAPPENED, falling back to when it was recorded. A call
    # logged after the fact is common (CS writes up three chase calls at the end of the
    # day), and ordering by created_at alone would then read them in typing order -
    # which decides whether an answered call resets the run or not. ``created_at``
    # defaults to the TRANSACTION timestamp in Postgres, so several calls written
    # together share it exactly and their order is arbitrary.
    events = sorted(
        query.all(),
        key=lambda e: (
            str((e.system_payload or {}).get("occurred_at") or "") or e.created_at.isoformat(),
            str(e.id),
        ),
        reverse=True,
    )

    count = 0
    last_at = None
    ids: List[str] = []
    for event in events:
        outcome = str((event.system_payload or {}).get("outcome") or "").lower()
        if outcome == "answered":
            break
        if outcome not in {"missed", "no_answer"}:
            continue
        count += 1
        ids.append(str(event.id))
        if last_at is None:
            last_at = (event.system_payload or {}).get("occurred_at") or event.created_at

    return {
        "count": count,
        "last_at": last_at,
        "activity_ids": ids,
        "justifies_customer_waiting": count >= UNANSWERED_CALL_THRESHOLD,
    }
