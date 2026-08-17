"""Leads: the stage before a development is anybody's to claim (UAC Group O).

The whole design follows from one fact: **a lead is a rumour**.

- It is NOT exclusive. No fuzzy lock, no clash block, no unique title (AC-O3).
  Locking hearsay would let the first person to type a guess own a development nobody
  has confirmed exists, and a lead frequently has no developer to lock on.
- It anchors on the DEVELOPMENT, not on a counterparty (D6, AC-A1). The buyer is
  optional and means the debtor who will issue the PO; the INFORMANT who told us is
  recorded separately, because BCI is a data source and not a debtor.
- Ownership locks at QUALIFY, which is the moment the registration clash check
  finally runs, and where a rumour becomes a claim (AC-O4).
- One lead may produce SEVERAL projects: a masterplan sighting becomes a separate
  registration per phase (AC-O5).

Phase 2 adds the handover handshake (D7, AC-A4..A7): assignment is NOT ownership. A
lead sits `assigned` until the salesperson accepts it, and a decline puts it back in
marketing's pool with a reason on it, rather than dying in somebody's tray.

Near-duplicates ARE surfaced on the list, informationally, using the same matcher the
registration lock uses. Surfacing and enforcing are different things and this module
does exactly one of them here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.lookup import LookupOption, LookupSet
from app.models.order import Customer
from app.models.projects import (
    LEAD_DISQUALIFY_REASON_SET_KEY,
    LEAD_OUTCOME_DISQUALIFIED,
    LEAD_OUTCOME_OPEN,
    LEAD_OUTCOME_QUALIFIED,
    LEAD_SOURCES,
    Project,
    ProjectLead,
    ProjectParty,
)
from app.models.status import Status
from app.schemas.common import MAX_PAGE_LIMIT
from app.services.error_handler import AppException
from app.services.numbering_service import NumberingService
from app.services.project_clash_service import find_clashes, normalise_project_title
from app.status_engine.registry import get_status_entity

logger = logging.getLogger(__name__)

NUMBERING_DOC_TYPE = "project_lead"
LEAD_ENTITY_TYPE = "project_lead"
# The audit listener keys on the TABLE name, not the class name, and the assigner is
# read back out of the trail (see `_assigner_user_id`).
LEAD_AUDIT_ENTITY_TYPE = "project_leads"

OUTCOME_OPEN = LEAD_OUTCOME_OPEN
OUTCOME_QUALIFIED = LEAD_OUTCOME_QUALIFIED
OUTCOME_DISQUALIFIED = LEAD_OUTCOME_DISQUALIFIED

# The handshake (D7). NULL means no handover has happened yet -- a lead somebody
# recorded for themselves is not "awaiting acceptance" by anyone.
ACCEPTANCE_ASSIGNED = "assigned"
ACCEPTANCE_ACCEPTED = "accepted"
ACCEPTANCE_DECLINED = "declined"

# Who told us (AC-A2). The union of the codes named in the contract and in the UAC:
# both lists are real -- `panel` and `contractor` come from how marketing actually
# works, `architect` from the API contract the frontend is built against -- and
# refusing either one would 422 a screen that is following its own spec.
INFORMANT_SOURCE_BCI = "bci"
INFORMANT_SOURCES = (
    INFORMANT_SOURCE_BCI,
    "panel",
    "referral",
    "walk_in",
    "consultant",
    "architect",
    "contractor",
    "other",
)

# Fields a caller may set on create or edit. Everything else about a lead is decided
# by the service (code, outcome, status, qualified_at, and every acceptance column) so
# a client cannot, for example, mark its own lead qualified without going through the
# clash check, or accept a lead nobody assigned to it.
EDITABLE_FIELDS = (
    "customer_id",
    "developer_party_id",
    "title",
    "source",
    "source_detail",
    "estimated_value",
    "location",
    "notes",
    "owner_user_id",
    "informant_source",
    "informant_ref",
    "informant_party_id",
    "informant_contact_name",
)

MANAGE_PERMISSION = "projects.projects.manage"


# --------------------------------------------------------------- validation


def _clean_title(raw: Optional[str]) -> str:
    title = " ".join((raw or "").split())
    if not title:
        raise AppException(
            status_code=422,
            message="A lead title is required. Describe the development you heard about.",
            code="lead_title_required",
        )
    return title


def _assert_buyer(db: Session, customer_id: Optional[str]) -> None:
    """The buyer is OPTIONAL (AC-A1, D6), and means the debtor who will issue the PO.

    Phase 1 required it, matching ecohub's non-nullable ``Lead.clientId``. That is the
    accepted deviation: ecohub's lead IS a consumer enquiry, while a BCI sighting has
    no counterparty at all -- the trading house only exists once a contractor is
    awarded, which is often months after marketing records the development. Asking for
    it on day one would either block the lead or invite a made-up customer row.

    Who told us is recorded on the informant fields instead, and never in ``customers``.
    """
    if not customer_id:
        return
    exists = db.query(Customer.id).filter(Customer.id == customer_id).first()
    if not exists:
        raise AppException(
            status_code=404,
            message="That customer no longer exists.",
            code="lead_customer_not_found",
        )


def _assert_informant(db: Session, payload: Dict[str, Any]) -> None:
    """Validate the informant bucket and its firm, when either was supplied.

    Only what is PRESENT in the payload is checked, so a PUT that touches the title
    cannot be rejected for an informant it never mentioned.
    """
    if "informant_source" in payload:
        source = payload.get("informant_source")
        if source and source not in INFORMANT_SOURCES:
            raise AppException(
                status_code=422,
                message=f"Unknown informant source '{source}'.",
                code="lead_informant_source_invalid",
            )
    if payload.get("informant_party_id"):
        exists = (
            db.query(ProjectParty.id)
            .filter(ProjectParty.id == payload["informant_party_id"])
            .first()
        )
        if not exists:
            raise AppException(
                status_code=404,
                message="That informant no longer exists.",
                code="lead_informant_party_not_found",
            )


def _assert_source(source: Optional[str]) -> None:
    if source and source not in LEAD_SOURCES:
        raise AppException(
            status_code=422,
            message=f"Unknown lead source '{source}'.",
            code="lead_source_invalid",
        )


def _assert_developer(db: Session, developer_party_id: Optional[str]) -> None:
    if not developer_party_id:
        return
    exists = (
        db.query(ProjectParty.id).filter(ProjectParty.id == developer_party_id).first()
    )
    if not exists:
        raise AppException(
            status_code=404,
            message="That developer no longer exists.",
            code="lead_developer_not_found",
        )


def disqualify_reasons(db: Session) -> List[Dict[str, str]]:
    """Active options of the reason lookup set (AC-O6)."""
    lookup_set = (
        db.query(LookupSet)
        .filter(LookupSet.set_key == LEAD_DISQUALIFY_REASON_SET_KEY)
        .first()
    )
    if not lookup_set:
        return []
    rows = (
        db.query(LookupOption)
        .filter(LookupOption.set_id == lookup_set.id, LookupOption.is_active.is_(True))
        .order_by(LookupOption.sort_order.asc(), LookupOption.label.asc())
        .all()
    )
    return [{"value": row.value, "label": row.label} for row in rows]


def _assert_disqualify_reason(db: Session, reason: Optional[str]) -> str:
    """The reason must come from the lookup, not from free text.

    A free-text reason cannot be reported on, and "not interested" typed nine ways is
    nine buckets in the conversion report. If the lookup is empty the action is
    refused rather than silently accepting anything: an empty lookup is a
    configuration problem the admin can fix, and swallowing it would produce
    unreportable data nobody notices until the first review meeting.
    """
    options = {row["value"] for row in disqualify_reasons(db)}
    if not options:
        raise AppException(
            status_code=422,
            message=(
                "No disqualification reasons are configured. Add options to the "
                f"'{LEAD_DISQUALIFY_REASON_SET_KEY}' lookup set first."
            ),
            code="lead_disqualify_reasons_unconfigured",
        )
    if not reason:
        raise AppException(
            status_code=422,
            message="A disqualification reason is required.",
            code="lead_disqualify_reason_required",
        )
    if reason not in options:
        raise AppException(
            status_code=422,
            message=f"'{reason}' is not a configured disqualification reason.",
            code="lead_disqualify_reason_invalid",
        )
    return reason


# ------------------------------------------------------------------- create


def _initial_status_id(db: Session, lead: ProjectLead) -> Optional[str]:
    """From the graph, so the first rung stays configurable.

    A lead with no graph configured is left status-less rather than refused: recording
    the sighting is the valuable part, and the funnel can be set up afterwards. Same
    call the project registration makes.
    """
    from app.services import status_service

    try:
        entity = get_status_entity(LEAD_ENTITY_TYPE)
        scope_id = entity.scope_for(lead) if entity else None
        return status_service.initial_status(db, LEAD_ENTITY_TYPE, scope_id).id
    except AppException:
        return None


def create_lead(
    db: Session,
    *,
    company_id: str,
    actor_user_id: str,
    payload: Dict[str, Any],
) -> ProjectLead:
    """Record a sighting. No clash check, by design (AC-O3)."""
    title = _clean_title(payload.get("title"))
    _assert_buyer(db, payload.get("customer_id"))
    _assert_source(payload.get("source"))
    _assert_developer(db, payload.get("developer_party_id"))
    _assert_informant(db, payload)

    code = NumberingService(db).get_next_number(NUMBERING_DOC_TYPE, commit_rule=False)
    if not code:
        raise AppException(
            status_code=422,
            message=(
                "No enabled numbering rule for leads. Configure one under Settings "
                "before recording a lead."
            ),
            code="lead_numbering_rule_missing",
        )

    lead = ProjectLead(
        company_id=company_id,
        lead_code=code,
        customer_id=payload.get("customer_id"),
        developer_party_id=payload.get("developer_party_id"),
        title=title,
        normalised_title=normalise_project_title(title),
        source=payload.get("source"),
        source_detail=payload.get("source_detail"),
        estimated_value=payload.get("estimated_value"),
        location=payload.get("location"),
        notes=payload.get("notes"),
        informant_source=payload.get("informant_source"),
        informant_ref=payload.get("informant_ref"),
        informant_party_id=payload.get("informant_party_id"),
        informant_contact_name=payload.get("informant_contact_name"),
        outcome=OUTCOME_OPEN,
        owner_user_id=payload.get("owner_user_id") or actor_user_id,
        created_by=actor_user_id,
    )
    db.add(lead)
    db.flush()

    lead.status_id = _initial_status_id(db, lead)
    db.flush()
    return lead


def select_or_create_customer(
    db: Session,
    *,
    company_id: str,
    actor_user_id: str,
    customer_id: Optional[str] = None,
    new_customer: Optional[Dict[str, Any]] = None,
) -> Customer:
    """Pick the BUYER, or create it when it is known and not yet on file.

    Phase 1 also used this for the person who told us, which D6 reverses: an informant
    is a data source, never a debtor, and BCI has no business in a buying ledger. Only a
    counterparty that will actually issue a purchase order comes through here now, which
    is why nothing calls it when neither ``customer_id`` nor ``new_customer`` is given.

    Rows created this way still carry ``source='project_lead'`` so order and invoice
    pickers can filter prospects out if the noise becomes real.
    """
    if customer_id:
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise AppException(
                status_code=404,
                message="That customer no longer exists.",
                code="lead_customer_not_found",
            )
        return customer

    payload = new_customer or {}
    name = " ".join((payload.get("customer_name") or "").split())
    if not name:
        raise AppException(
            status_code=422,
            message="A customer name is required to create one.",
            code="lead_customer_name_required",
        )

    # Case-insensitive reuse before insert. Without this the wizard produces
    # "Gamuda Land" and "GAMUDA LAND" as two prospects and the account view splits.
    existing = (
        db.query(Customer)
        .filter(func.lower(func.btrim(Customer.customer_name)) == name.lower())
        .first()
    )
    if existing:
        return existing

    code = (payload.get("customer_code") or "").strip() or _prospect_code(db, name)
    customer = Customer(
        company_id=company_id,
        customer_code=code,
        customer_name=name,
        email=payload.get("email"),
        phone_number=payload.get("phone_number"),
        registration_number=payload.get("registration_number"),
        notes=payload.get("notes"),
        source="project_lead",
        created_by=actor_user_id,
    )
    db.add(customer)
    db.flush()
    return customer


def _prospect_code(db: Session, name: str) -> str:
    """A readable placeholder code for a non-buyer.

    Real customers get their code from the accounting system on first order. A
    prospect has none yet, and leaving it blank is not an option (NOT NULL, and the
    uniqueness index is on code+name).
    """
    stem = "".join(ch for ch in name.upper() if ch.isalnum())[:8] or "PROSPECT"
    candidate = f"P-{stem}"
    suffix = 1
    while (
        db.query(Customer.id)
        .filter(func.lower(Customer.customer_code) == candidate.lower())
        .first()
    ):
        suffix += 1
        candidate = f"P-{stem}-{suffix}"
    return candidate


# --------------------------------------------------------------------- edit


def get_lead(db: Session, lead_id: str) -> ProjectLead:
    lead = db.query(ProjectLead).filter(ProjectLead.id == lead_id).first()
    if not lead:
        raise AppException(
            status_code=404, message="Lead not found.", code="lead_not_found"
        )
    return lead


def can_edit_lead(lead: ProjectLead, user_id: str, permissions: Set[str]) -> bool:
    """Owner or manager. There is no collaborator concept on leads.

    Deliberately simpler than a project's rule: a lead is not exclusive, so there is
    nothing to negotiate access to. Anybody who wants in records their own.
    """
    if MANAGE_PERMISSION in (permissions or set()):
        return True
    return bool(user_id) and lead.owner_user_id == user_id


def assert_can_edit_lead(lead: ProjectLead, user_id: str, permissions: Set[str]) -> None:
    if not can_edit_lead(lead, user_id, permissions):
        raise AppException(
            status_code=403,
            message=(
                "This lead belongs to somebody else. Record your own sighting instead "
                "-- leads are not exclusive."
            ),
            code="lead_not_editable",
        )


def update_lead(db: Session, lead: ProjectLead, payload: Dict[str, Any]) -> ProjectLead:
    if "title" in payload:
        title = _clean_title(payload.get("title"))
        lead.title = title
        lead.normalised_title = normalise_project_title(title)
    if "customer_id" in payload:
        # Explicitly allowed to go back to NULL: a buyer named in error is corrected by
        # clearing it, not by pointing the lead at some other debtor.
        _assert_buyer(db, payload.get("customer_id"))
        lead.customer_id = payload["customer_id"]
    if "source" in payload:
        _assert_source(payload.get("source"))
    if "developer_party_id" in payload:
        _assert_developer(db, payload.get("developer_party_id"))
    _assert_informant(db, payload)

    for field in EDITABLE_FIELDS:
        if field in ("title", "customer_id"):
            continue
        if field in payload:
            setattr(lead, field, payload[field])

    db.flush()
    return lead


def change_lead_status(db: Session, lead: ProjectLead, to_status_id: str) -> ProjectLead:
    """Move a rung. The engine validates the edge; this only refuses the two rungs
    that have their own action.

    Qualified and Disqualified are reached through ``qualify_lead`` and
    ``disqualify_lead``, which do the work those rungs MEAN (run the clash check,
    create the project, record a reason). Allowing a bare status move onto them would
    produce a lead marked qualified with no project behind it.
    """
    from app.services import status_service

    target = db.query(Status).filter(Status.id == to_status_id).first()
    if not target:
        raise AppException(
            status_code=404, message="Status not found.", code="status_not_found"
        )
    if target.key == "qualified":
        raise AppException(
            status_code=422,
            message="Use Qualify to convert this lead, so the project is created with it.",
            code="lead_qualify_via_action",
        )
    if target.key == "disqualified":
        raise AppException(
            status_code=422,
            message="Use Disqualify, so a reason is recorded.",
            code="lead_disqualify_via_action",
        )

    # scope_id stays None: leads have no template, so there is only ever the default
    # graph to validate against.
    status_service.assert_transition_allowed(
        db, LEAD_ENTITY_TYPE, lead.status_id, to_status_id, scope_id=None
    )
    lead.status_id = to_status_id
    db.flush()
    return lead


def delete_lead(db: Session, lead: ProjectLead) -> None:
    """Hard delete. Any project qualified out of it keeps its own life.

    ``projects.lead_id`` is ON DELETE SET NULL for exactly this: deleting the rumour
    must never take a live registration with it.
    """
    db.delete(lead)
    db.flush()


# ------------------------------------------------- the acceptance handshake
#
# D7 in one sentence: **assignment is not ownership**. Marketing hands a lead over and
# the salesperson either takes it or says why not, and until one of those happens the
# lead is measurably waiting. Their own note started this: the handover has to be
# explicit or the lead dies between the two of them.


def _assert_assignee(db: Session, user_id: Optional[str]):
    """The person being asked to take it must exist and still work here."""
    from app.models.user import User

    if not user_id:
        raise AppException(
            status_code=422,
            message="Pick the salesperson this lead is going to.",
            code="lead_assignee_required",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppException(
            status_code=404,
            message="That user no longer exists.",
            code="lead_assignee_not_found",
        )
    # A trashed user cannot open the lead, so assigning to one is a lead nobody is
    # holding while the list says somebody is.
    if getattr(user, "is_trashed", False):
        raise AppException(
            status_code=422,
            message="That user has been removed. Pick somebody who can act on it.",
            code="lead_assignee_inactive",
        )
    return user


def can_assign_lead(
    lead: ProjectLead, user_id: str, permissions: Optional[Set[str]] = None
) -> bool:
    """Who may hand a lead out: a manager, the current holder, or whoever recorded it.

    The creator matters because of the decline path. A decline clears
    ``owner_user_id``, and ``can_edit_lead`` is owner-or-manager -- so without this the
    marketing user who raised the lead could not re-assign the very lead that just came
    back to them, which is precisely where the journey says it lands.
    """
    if MANAGE_PERMISSION in (permissions or set()):
        return True
    if not user_id:
        return False
    return lead.owner_user_id == user_id or lead.created_by == user_id


def assert_can_assign_lead(
    lead: ProjectLead, user_id: str, permissions: Optional[Set[str]] = None
) -> None:
    if not can_assign_lead(lead, user_id, permissions):
        raise AppException(
            status_code=403,
            message=(
                "This lead belongs to somebody else. Ask its owner or a manager to "
                "hand it over."
            ),
            code="lead_not_assignable",
        )


def assign_lead(
    db: Session,
    *,
    lead: ProjectLead,
    owner_user_id: str,
) -> ProjectLead:
    """Hand the lead over and start the clock (AC-A4).

    Re-assigning an already-assigned lead is allowed and RESETS the clock: the second
    salesperson cannot inherit the first one's silence, and marketing's worklist has to
    read as the wait for the person who is actually holding it now.

    Any earlier decline is cleared for the same reason -- a stale "declined by Ali,
    wrong patch" alongside a live assignment to Siti reads as a refusal of Siti's.
    """
    _assert_assignee(db, owner_user_id)

    lead.owner_user_id = owner_user_id
    lead.acceptance_state = ACCEPTANCE_ASSIGNED
    lead.assigned_at = datetime.utcnow()
    lead.accepted_at = None
    lead.declined_reason = None
    lead.declined_at = None
    db.flush()
    return lead


def can_decide_acceptance(
    lead: ProjectLead, user_id: str, permissions: Optional[Set[str]] = None
) -> bool:
    """Only the person it was handed to answers for it -- or a manager on their behalf.

    The manager exception is not a convenience: somebody has to be able to clear an
    assignment made to a person who has gone on leave, and the alternative is a lead
    frozen `assigned` forever.
    """
    if MANAGE_PERMISSION in (permissions or set()):
        return True
    return bool(user_id) and lead.owner_user_id == user_id


def _assert_pending_acceptance(lead: ProjectLead) -> None:
    if lead.acceptance_state != ACCEPTANCE_ASSIGNED:
        raise AppException(
            status_code=409,
            message=(
                "This lead is not waiting on anybody. Assign it to a salesperson first."
            ),
            code="lead_not_awaiting_acceptance",
        )


def _assert_can_decide(
    lead: ProjectLead, user_id: str, permissions: Optional[Set[str]] = None
) -> None:
    if not can_decide_acceptance(lead, user_id, permissions):
        raise AppException(
            status_code=403,
            message=(
                "This lead was handed to somebody else. Only they -- or their manager "
                "-- can accept or decline it."
            ),
            code="lead_acceptance_not_yours",
        )


def accept_lead(
    db: Session,
    *,
    lead: ProjectLead,
    actor_user_id: str,
    permissions: Optional[Set[str]] = None,
) -> ProjectLead:
    """Take the lead on (AC-A5). From here it is genuinely owned.

    State is checked before authorship on purpose: "nobody assigned this" is the more
    useful answer to an admin pressing Accept on an unassigned lead than "not yours".
    """
    _assert_pending_acceptance(lead)
    _assert_can_decide(lead, actor_user_id, permissions)

    lead.acceptance_state = ACCEPTANCE_ACCEPTED
    lead.accepted_at = datetime.utcnow()
    db.flush()
    return lead


def decline_lead(
    db: Session,
    *,
    lead: ProjectLead,
    reason: Optional[str],
    actor_user_id: str,
    permissions: Optional[Set[str]] = None,
) -> ProjectLead:
    """Refuse the handover and put the lead back in the pool (AC-A5).

    ``owner_user_id`` is cleared, which is the whole point: a declined lead that kept
    its owner would sit in the refuser's list forever and never appear in marketing's
    unassigned view. The reason stays on the lead so the next assignment is made with
    it in view ("not my patch" is routing information, not a complaint).

    The outcome is untouched: a decline is a handover failing, not the development
    going away.
    """
    _assert_pending_acceptance(lead)
    _assert_can_decide(lead, actor_user_id, permissions)

    text = " ".join((reason or "").split())
    if not text:
        raise AppException(
            status_code=422,
            message="Say why it is not yours, so marketing can route it properly.",
            code="lead_decline_reason_required",
        )

    lead.acceptance_state = ACCEPTANCE_DECLINED
    lead.declined_reason = text
    lead.declined_at = datetime.utcnow()
    lead.accepted_at = None
    lead.owner_user_id = None
    db.flush()
    return lead


# ------------------------------------------------- telling the other person
#
# Everything below is BEST-EFFORT and runs AFTER the caller has committed. The handover
# is already recorded, so a notification backend that is down must never turn a
# successful assign into a 500 -- and it especially must not, because the retry would
# re-assign a lead that is already assigned.


def _lead_url(lead: ProjectLead) -> str:
    """The in-system detail page. Recipients are staff, so this is never a portal link;
    the deep-link-after-login carries them back here if their session lapsed."""
    from app.config import settings

    base = (getattr(settings, "frontend_base_url", None) or "").strip().rstrip("/")
    path = f"/project-sales/leads/{lead.id}"
    return f"{base}{path}" if base else path


def _notify_users(
    db: Session,
    *,
    user_ids: Sequence[Optional[str]],
    lead: ProjectLead,
    notif_type: str,
    event_type: str,
    title: str,
    body: str,
    data: Dict[str, Any],
    dedup_key: str,
) -> int:
    """Fan out to a de-duplicated recipient set. Returns how many were notified.

    In-app always fires; email and WhatsApp are each gated by the RECIPIENT's own
    per-event toggle inside ``create_with_channel_preferences``, the same matrix the SLA
    notify uses. The assignment pair is reused for both halves of the handshake: an
    assign and the decline that answers it are one conversation about who is holding
    this lead, and a lead-specific toggle pair would be a `users` column this slice
    cannot add.
    """
    try:
        from app.services.notification_service import NotificationService

        service = NotificationService(db)
        sent = 0
        for user_id in {str(u) for u in user_ids if u}:
            service.create_with_channel_preferences(
                user_id=user_id,
                type=notif_type,
                title=title,
                body=body,
                data=data,
                source_entity_type=LEAD_ENTITY_TYPE,
                source_entity_id=str(lead.id),
                dedup_key=dedup_key,
                event_type=event_type,
                send_in_app=True,
                send_email=True,
                send_whatsapp=True,
                email_pref_attr="notify_email_on_assignment",
                whatsapp_pref_attr="notify_whatsapp_on_assignment",
            )
            sent += 1
        return sent
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lead notification not sent: type=%s lead=%s (%s)", notif_type, lead.id, exc
        )
        return 0


def notify_lead_assigned(
    db: Session,
    *,
    lead: ProjectLead,
    actor_user_id: Optional[str] = None,
    note: Optional[str] = None,
) -> int:
    """Tell the assignee one thing, with enough on it to decide (AC-A4, journey step 2).

    The message CARRIES the development, the developer and the value, because otherwise
    Ali has to open the record just to decide whether to care.
    """
    try:
        developer = _party_name(db, lead.developer_party_id)
        value = f"RM {lead.estimated_value}" if lead.estimated_value is not None else None
        facts = " | ".join(str(part) for part in (developer, lead.location, value) if part)
        body = f"{lead.title}"
        if facts:
            body += f"\n{facts}"
        if note:
            body += f"\n\nFrom the sender: {note}"
        body += "\n\nAccept it to make it yours, or decline with a reason."
        body += f"\n\nOpen: {_lead_url(lead)}"

        return _notify_users(
            db,
            user_ids=[lead.owner_user_id],
            lead=lead,
            notif_type="project_lead_assigned",
            event_type="project_lead_assigned",
            title=f"Lead {lead.lead_code} assigned to you",
            body=body,
            data={
                "lead_id": str(lead.id),
                "lead_code": lead.lead_code,
                "title": lead.title,
                "developer_name": developer,
                "estimated_value": (
                    str(lead.estimated_value)
                    if lead.estimated_value is not None
                    else None
                ),
                "assigned_by_user_id": actor_user_id,
                "note": note,
                "link": _lead_url(lead),
                "whatsapp_context_vars": {
                    "entity_number": lead.lead_code,
                    "message": body,
                },
            },
            # Per ASSIGNMENT, not per lead: a re-assignment resets the clock and has to
            # be able to notify again, which a lead-scoped key would suppress.
            dedup_key=(
                f"{lead.id}:assigned:"
                f"{(lead.assigned_at or datetime.utcnow()).isoformat()}"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        # Guards the message BUILD as well as the send: resolving the developer name is
        # a query, and a failure there would 500 an assignment that already committed.
        logger.warning("lead assigned notify failed: lead=%s (%s)", lead.id, exc)
        return 0


def notify_lead_declined(
    db: Session,
    *,
    lead: ProjectLead,
    actor_user_id: Optional[str] = None,
) -> int:
    """Tell whoever handed it over that it came back, and why (AC-A5).

    Recipient is the assigner read out of the audit trail, falling back to whoever
    recorded the lead -- in the journey they are the same marketing person. A decline
    nobody hears about is the failure mode D7 exists to remove.
    """
    try:
        decliner = _user_label(db, actor_user_id)
        body = f"{lead.title}"
        if decliner:
            body += f"\n{decliner} declined it: {lead.declined_reason}"
        else:
            body += f"\nDeclined: {lead.declined_reason}"
        body += "\n\nIt is back in the unassigned pool. Assign it to somebody else."
        body += f"\n\nOpen: {_lead_url(lead)}"

        return _notify_users(
            db,
            user_ids=_decline_recipients(db, lead),
            lead=lead,
            notif_type="project_lead_declined",
            event_type="project_lead_declined",
            title=f"Lead {lead.lead_code} was declined",
            body=body,
            data={
                "lead_id": str(lead.id),
                "lead_code": lead.lead_code,
                "title": lead.title,
                "declined_by_user_id": actor_user_id,
                "declined_by_name": decliner,
                "declined_reason": lead.declined_reason,
                "link": _lead_url(lead),
                "whatsapp_context_vars": {
                    "entity_number": lead.lead_code,
                    "message": body,
                },
            },
            # Per DECLINE: the same lead can be assigned and declined more than once,
            # and the second refusal is news.
            dedup_key=(
                f"{lead.id}:declined:"
                f"{(lead.declined_at or datetime.utcnow()).isoformat()}"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        # Same guard as the assign side, and for the same reason: resolving the assigner
        # and the decliner are both queries, run after the decline has committed.
        logger.warning("lead declined notify failed: lead=%s (%s)", lead.id, exc)
        return 0


def _decline_recipients(db: Session, lead: ProjectLead) -> List[str]:
    """Whoever assigned it, then whoever recorded it, then management.

    Never empty by design: a lead that came back and told nobody is the tray it was
    supposed to escape from.
    """
    recipients = [uid for uid in (_assigner_user_id(db, lead), lead.created_by) if uid]
    if recipients:
        return recipients

    from app.services.project_notify_service import management_user_ids

    return management_user_ids(db)


def _assigner_user_id(db: Session, lead: ProjectLead) -> Optional[str]:
    """Who last assigned this lead, from the audit trail.

    There is no ``assigned_by`` column, and the audit listener already records the actor
    of every lead UPDATE (``__audit_track__`` on the model), so reading it back is
    cheaper than a column that would duplicate it. Best-effort: an install where the
    listeners are not registered simply falls through to ``created_by``.
    """
    try:
        from app.models.audit import AuditLog

        row = (
            db.query(AuditLog.user_id)
            .filter(
                AuditLog.entity_type == LEAD_AUDIT_ENTITY_TYPE,
                AuditLog.entity_id == str(lead.id),
                AuditLog.new_values["acceptance_state"].astext == ACCEPTANCE_ASSIGNED,
            )
            .order_by(AuditLog.changed_at.desc())
            .first()
        )
        return str(row[0]) if row and row[0] else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("lead assigner lookup failed: lead=%s (%s)", lead.id, exc)
        return None


def _party_name(db: Session, party_id: Optional[str]) -> Optional[str]:
    if not party_id:
        return None
    row = db.query(ProjectParty.name).filter(ProjectParty.id == party_id).first()
    return row[0] if row else None


def _user_label(db: Session, user_id: Optional[str]) -> Optional[str]:
    return _resolve_names(db, [user_id]).get(user_id or "") if user_id else None


# ------------------------------------------------------------------ qualify


def _status_id_by_key(db: Session, key: str) -> Optional[str]:
    row = (
        db.query(Status.id)
        .filter(
            Status.entity_type == LEAD_ENTITY_TYPE,
            Status.scope_id.is_(None),
            Status.key == key,
        )
        .first()
    )
    return row[0] if row else None


def qualify_lead(
    db: Session,
    *,
    lead: ProjectLead,
    actor_user_id: str,
    company_id: str,
    project_payload: Optional[Dict[str, Any]] = None,
) -> Project:
    """Convert a rumour into a claim (AC-O4).

    This is the ONLY place a lead touches the registration lock, and the reason the
    lock is not applied earlier: two salespeople may both have heard about a
    development, and only the one who qualifies it owns it.

    A block here does NOT close the lead. The lead stays open with the incumbent
    surfaced, because the recourse is join-or-dispute on the existing project and the
    lead is the user's record of why they were asking.
    """
    from app.services.project_service import register_project

    payload = dict(project_payload or {})
    title = payload.pop("title", None) or lead.title
    developer_party_id = payload.pop("developer_party_id", None) or lead.developer_party_id

    details = payload.pop("details", None) or {}
    # Carry across what the lead already knows, without overwriting anything the
    # confirm step edited: re-asking for the location we were told about is exactly
    # the re-keying this module exists to remove.
    if lead.location and "location" not in details:
        details["location"] = lead.location
    if lead.estimated_value is not None and "estimated_sales_value" not in details:
        details["estimated_sales_value"] = lead.estimated_value

    project = register_project(
        db,
        company_id=company_id,
        actor_user_id=actor_user_id,
        developer_party_id=developer_party_id,
        title=title,
        type_id=payload.pop("type_id", None),
        template_id=payload.pop("template_id", None),
        details=details,
        brand_ids=payload.pop("brand_ids", None),
        owner_user_id=payload.pop("owner_user_id", None) or lead.owner_user_id,
    )
    project.lead_id = lead.id

    # Qualified is terminal and the lead may qualify again (AC-O5): a masterplan
    # sighting yields one project per phase. `qualified_at` marks the FIRST conversion,
    # which is what the conversion-rate metric measures.
    lead.outcome = OUTCOME_QUALIFIED
    lead.qualified_at = lead.qualified_at or datetime.utcnow()
    qualified_status = _status_id_by_key(db, "qualified")
    if qualified_status:
        lead.status_id = qualified_status
    db.flush()
    return project


def preview_qualify_clashes(
    db: Session,
    *,
    lead: ProjectLead,
    company_id: str,
    title: Optional[str] = None,
    developer_party_id: Optional[str] = None,
) -> Dict[str, Any]:
    """What qualifying WOULD hit, before the user commits to it.

    Same matcher and same thresholds as registration, so the preview cannot disagree
    with the decision. Widened to every developer when the lead has none, since a
    lead without a developer is the common case and a developer-scoped preview would
    stay silent on it.
    """
    check_title = " ".join((title or lead.title or "").split())
    developer = developer_party_id or lead.developer_party_id
    candidates = find_clashes(
        db,
        company_id=company_id,
        developer_party_id=developer,
        title=check_title,
        include_other_developers=developer is None,
    )
    return {
        "candidates": candidates,
        "would_block": any(candidate.blocks for candidate in candidates),
    }


def disqualify_lead(
    db: Session, *, lead: ProjectLead, reason: Optional[str]
) -> ProjectLead:
    """Close a lead that went nowhere, with a reportable reason (AC-O6)."""
    lead.disqualified_reason = _assert_disqualify_reason(db, reason)
    lead.outcome = OUTCOME_DISQUALIFIED
    disqualified_status = _status_id_by_key(db, "disqualified")
    if disqualified_status:
        lead.status_id = disqualified_status
    db.flush()
    return lead


def reopen_lead(db: Session, lead: ProjectLead) -> ProjectLead:
    """Undo a disqualification. Only from disqualified, never from qualified.

    A qualified lead has a project behind it; "reopening" it would leave the project
    orphaned from the funnel it came out of. A disqualified one is just a decision
    somebody changed their mind about.
    """
    if lead.outcome != OUTCOME_DISQUALIFIED:
        raise AppException(
            status_code=422,
            message="Only a disqualified lead can be reopened.",
            code="lead_not_reopenable",
        )
    lead.outcome = OUTCOME_OPEN
    lead.disqualified_reason = None
    initial = _status_id_by_key(db, "new")
    if initial:
        lead.status_id = initial
    db.flush()
    return lead


# --------------------------------------------------------------------- read


def _resolve_names(db: Session, user_ids: Sequence[Optional[str]]) -> Dict[str, str]:
    ids = {uid for uid in user_ids if uid}
    if not ids:
        return {}
    from app.models.user import User

    return {
        row.id: (row.name or row.email)
        for row in db.query(User).filter(User.id.in_(ids)).all()
    }


def serialize_leads(
    db: Session,
    leads: Sequence[ProjectLead],
    *,
    actor_user_id: str = "",
    permissions: Optional[Set[str]] = None,
    with_duplicate_hints: bool = False,
) -> List[Dict[str, Any]]:
    """Bulk-serialise, resolving every id to a label in ONE query per kind.

    ``actor_user_id`` rather than ``user_id`` deliberately: it is the same name
    ``serialize_projects`` uses, and two serializers with different names for the same
    argument is how a route ends up calling one with the other's keyword and 500ing.

    No UUID reaches the UI, per the cursor rules, and per-row lookups here would be
    the N+1 that makes a 200-row list unusable.
    """
    if not leads:
        return []

    names = _resolve_names(db, [lead.owner_user_id for lead in leads])
    customer_ids = {lead.customer_id for lead in leads if lead.customer_id}
    customers = (
        {
            row.id: row.customer_name
            for row in db.query(Customer).filter(Customer.id.in_(customer_ids)).all()
        }
        if customer_ids
        else {}
    )
    # One query for BOTH party roles. The developer and the informant are frequently
    # the same firm, and two queries would be two round trips for one answer.
    party_ids = {
        party_id
        for lead in leads
        for party_id in (lead.developer_party_id, lead.informant_party_id)
        if party_id
    }
    parties = (
        {
            row.id: row.name
            for row in db.query(ProjectParty)
            .filter(ProjectParty.id.in_(party_ids))
            .all()
        }
        if party_ids
        else {}
    )
    status_ids = {lead.status_id for lead in leads if lead.status_id}
    statuses = (
        {
            row.id: (row.key, row.label)
            for row in db.query(Status).filter(Status.id.in_(status_ids)).all()
        }
        if status_ids
        else {}
    )

    hints = _duplicate_hints(db, leads) if with_duplicate_hints else {}
    project_counts = _project_counts(db, [lead.id for lead in leads])

    rows: List[Dict[str, Any]] = []
    for lead in leads:
        status = statuses.get(lead.status_id or "", (None, None))
        rows.append(
            {
                "id": lead.id,
                "lead_code": lead.lead_code,
                "title": lead.title,
                "customer_id": lead.customer_id,
                "customer_name": customers.get(lead.customer_id or ""),
                "developer_party_id": lead.developer_party_id,
                "developer_name": parties.get(lead.developer_party_id or ""),
                "informant_source": lead.informant_source,
                "informant_ref": lead.informant_ref,
                "informant_party_id": lead.informant_party_id,
                "informant_party_label": parties.get(lead.informant_party_id or ""),
                "informant_contact_name": lead.informant_contact_name,
                "acceptance_state": lead.acceptance_state,
                "assigned_at": lead.assigned_at,
                "accepted_at": lead.accepted_at,
                "declined_reason": lead.declined_reason,
                "declined_at": lead.declined_at,
                "source": lead.source,
                "source_detail": lead.source_detail,
                "estimated_value": (
                    str(lead.estimated_value) if lead.estimated_value is not None else None
                ),
                "location": lead.location,
                "notes": lead.notes,
                "status_id": lead.status_id,
                "status_key": status[0],
                "status_label": status[1],
                "outcome": lead.outcome,
                "disqualified_reason": lead.disqualified_reason,
                "qualified_at": lead.qualified_at,
                "owner_user_id": lead.owner_user_id,
                "owner_name": names.get(lead.owner_user_id or ""),
                "project_count": project_counts.get(lead.id, 0),
                "possible_duplicates": hints.get(lead.id, []),
                "can_edit": can_edit_lead(lead, actor_user_id, permissions or set()),
                # Separate from can_edit because the two diverge exactly where it
                # matters: a decline clears the owner, and can_edit is
                # owner-or-manager, so the marketing user who raised the lead could
                # not re-assign the lead that just came back to them. Sent rather
                # than inferred client-side, which was the frontend's only remaining
                # guess about who may act.
                "can_assign": can_assign_lead(lead, actor_user_id, permissions),
                "created_at": lead.created_at,
                "updated_at": lead.updated_at,
            }
        )
    return rows


def _project_counts(db: Session, lead_ids: Sequence[str]) -> Dict[str, int]:
    """How many projects each lead produced. One lead may produce several (AC-O5)."""
    ids = [lead_id for lead_id in lead_ids if lead_id]
    if not ids:
        return {}
    rows = (
        db.query(Project.lead_id, func.count(Project.id))
        .filter(Project.lead_id.in_(ids))
        .group_by(Project.lead_id)
        .all()
    )
    return {row[0]: row[1] for row in rows}


def _duplicate_hints(
    db: Session, leads: Sequence[ProjectLead]
) -> Dict[str, List[Dict[str, Any]]]:
    """Informational only (AC-O3). Never blocks, never warns on save.

    Compares each lead against OTHER OPEN LEADS on exact normalised title. A trigram
    scan per row would be the matcher the registration lock uses, and running it for
    every row of every page is the wrong trade for a hint: the exact-key match catches
    the case that actually happens (two people typing the same name off the same
    signboard) at the cost of one grouped query.
    """
    keys = {lead.normalised_title for lead in leads if lead.normalised_title}
    if not keys:
        return {}

    siblings = (
        db.query(ProjectLead)
        .filter(
            ProjectLead.normalised_title.in_(keys),
            ProjectLead.outcome == OUTCOME_OPEN,
        )
        .all()
    )
    by_key: Dict[str, List[ProjectLead]] = {}
    for sibling in siblings:
        by_key.setdefault(sibling.normalised_title, []).append(sibling)

    names = _resolve_names(db, [sibling.owner_user_id for sibling in siblings])
    hints: Dict[str, List[Dict[str, Any]]] = {}
    for lead in leads:
        others = [
            sibling
            for sibling in by_key.get(lead.normalised_title or "", [])
            if sibling.id != lead.id
        ]
        if others:
            hints[lead.id] = [
                {
                    "lead_id": other.id,
                    "lead_code": other.lead_code,
                    "owner_name": names.get(other.owner_user_id or ""),
                }
                for other in others
            ]
    return hints


def list_leads(
    db: Session,
    *,
    company_id: str,
    actor_user_id: str = "",
    permissions: Optional[Set[str]] = None,
    query: Optional[str] = None,
    outcome: Optional[Sequence[str]] = None,
    status_id: Optional[Sequence[str]] = None,
    owner_user_id: Optional[Sequence[str]] = None,
    customer_id: Optional[Sequence[str]] = None,
    source: Optional[Sequence[str]] = None,
    acceptance_state: Optional[Sequence[str]] = None,
    page: int = 1,
    limit: int = 50,
    sort: str = "created_at",
    dir: str = "desc",
) -> Dict[str, Any]:
    q = db.query(ProjectLead).filter(ProjectLead.company_id == company_id)

    if query:
        like = f"%{query.strip()}%"
        q = q.filter(
            or_(ProjectLead.title.ilike(like), ProjectLead.lead_code.ilike(like))
        )
    if acceptance_state:
        # AC-A7: marketing filters the ordinary list by handshake state too, so
        # "accepted" and "declined" are one click away from the same screen.
        q = q.filter(ProjectLead.acceptance_state.in_(list(acceptance_state)))
    if outcome:
        q = q.filter(ProjectLead.outcome.in_(list(outcome)))
    if status_id:
        q = q.filter(ProjectLead.status_id.in_(list(status_id)))
    if owner_user_id:
        q = q.filter(ProjectLead.owner_user_id.in_(list(owner_user_id)))
    if customer_id:
        q = q.filter(ProjectLead.customer_id.in_(list(customer_id)))
    if source:
        q = q.filter(ProjectLead.source.in_(list(source)))

    total = q.count()

    sortable = {
        "created_at": ProjectLead.created_at,
        "updated_at": ProjectLead.updated_at,
        "title": ProjectLead.title,
        "lead_code": ProjectLead.lead_code,
        "estimated_value": ProjectLead.estimated_value,
        "outcome": ProjectLead.outcome,
    }
    column = sortable.get(sort, ProjectLead.created_at)
    q = q.order_by(column.desc() if (dir or "desc").lower() == "desc" else column.asc())

    page = max(1, int(page or 1))
    limit = max(1, min(int(limit or 50), MAX_PAGE_LIMIT))
    rows = q.offset((page - 1) * limit).limit(limit).all()

    return {
        "data": serialize_leads(
            db,
            rows,
            actor_user_id=actor_user_id,
            permissions=permissions,
            with_duplicate_hints=True,
        ),
        "total": total,
        "page": page,
        "limit": limit,
    }


def hours_since(moment: Optional[datetime], *, now: Optional[datetime] = None) -> Optional[float]:
    """Hours between a naive-UTC timestamp and now, to two decimals.

    Computed here rather than in the browser: the columns are naive UTC, and a
    JavaScript ``new Date()`` on a string with no zone reads it as local time, which
    would put every Malaysian row eight hours out.
    """
    if not moment:
        return None
    delta = (now or datetime.utcnow()) - moment
    return round(delta.total_seconds() / 3600.0, 2)


def awaiting_acceptance(
    db: Session,
    *,
    company_id: str,
    actor_user_id: str = "",
    permissions: Optional[Set[str]] = None,
    owner_user_id: Optional[Sequence[str]] = None,
    min_hours: float = 0,
    query: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """Marketing's worklist: every lead nobody has taken yet (AC-A7).

    Newest assignment first, deliberately, and NOT longest-waiting first: this is the
    handover queue marketing works, and the oldest rows are the ones already chased.
    ``min_hours`` is how "nobody has answered me since Tuesday" is asked for.

    Every row carries ``hours_since_assigned`` so the screen shows the wait without
    doing date maths.
    """
    now = datetime.utcnow()

    q = db.query(ProjectLead).filter(
        ProjectLead.company_id == company_id,
        ProjectLead.acceptance_state == ACCEPTANCE_ASSIGNED,
    )
    if owner_user_id:
        q = q.filter(ProjectLead.owner_user_id.in_(list(owner_user_id)))
    if query:
        like = f"%{query.strip()}%"
        q = q.filter(
            or_(ProjectLead.title.ilike(like), ProjectLead.lead_code.ilike(like))
        )
    if min_hours and float(min_hours) > 0:
        q = q.filter(ProjectLead.assigned_at <= now - timedelta(hours=float(min_hours)))

    total = q.count()
    page = max(1, int(page or 1))
    limit = max(1, min(int(limit or 50), MAX_PAGE_LIMIT))
    rows = (
        q.order_by(ProjectLead.assigned_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    serialised = serialize_leads(
        db, rows, actor_user_id=actor_user_id, permissions=permissions
    )
    # Same `now` for every row, so two rows assigned in the same second cannot report
    # different waits.
    for row, lead in zip(serialised, rows):
        row["hours_since_assigned"] = hours_since(lead.assigned_at, now=now)

    return {"data": serialised, "total": total, "page": page, "limit": limit}


def conversion_metrics(db: Session, *, company_id: str) -> Dict[str, Any]:
    """Lead-to-project conversion and why the rest died (AC-O6).

    Reads OUTCOME, never status, consistent with the rest of the module: status is a
    funnel position an admin may rename or reorder, outcome is the result.
    """
    counts = dict(
        db.query(ProjectLead.outcome, func.count(ProjectLead.id))
        .filter(ProjectLead.company_id == company_id)
        .group_by(ProjectLead.outcome)
        .all()
    )
    total = sum(counts.values())
    qualified = counts.get(OUTCOME_QUALIFIED, 0)
    # Decided = qualified + disqualified. The conversion rate is measured against
    # DECIDED leads, not all of them: counting leads recorded this morning as failures
    # would make the rate fall every time somebody adds one.
    decided = qualified + counts.get(OUTCOME_DISQUALIFIED, 0)

    reason_rows = (
        db.query(ProjectLead.disqualified_reason, func.count(ProjectLead.id))
        .filter(
            ProjectLead.company_id == company_id,
            ProjectLead.outcome == OUTCOME_DISQUALIFIED,
        )
        .group_by(ProjectLead.disqualified_reason)
        .all()
    )
    labels = {row["value"]: row["label"] for row in disqualify_reasons(db)}

    projects_from_leads = (
        db.query(func.count(Project.id))
        .filter(Project.company_id == company_id, Project.lead_id.isnot(None))
        .scalar()
        or 0
    )

    return {
        "total": total,
        "open": counts.get(OUTCOME_OPEN, 0),
        "qualified": qualified,
        "disqualified": counts.get(OUTCOME_DISQUALIFIED, 0),
        "decided": decided,
        "conversion_rate": round(qualified / decided, 4) if decided else None,
        "projects_from_leads": projects_from_leads,
        "disqualified_reasons": [
            {
                "value": row[0],
                "label": labels.get(row[0] or "", row[0] or "Not recorded"),
                "count": row[1],
            }
            for row in sorted(reason_rows, key=lambda r: r[1], reverse=True)
        ],
    }


def leads_for_customer(db: Session, *, customer_id: str) -> List[ProjectLead]:
    """The account view's lead half (AC-O9)."""
    return (
        db.query(ProjectLead)
        .filter(ProjectLead.customer_id == customer_id)
        .order_by(ProjectLead.created_at.desc())
        .all()
    )


def customer_portfolio(db: Session, *, customer_id: str) -> Dict[str, Any]:
    """One customer's leads and projects: the account view (AC-O9).

    A project reaches a customer by TWO independent routes, and showing only one
    under-reports the account:

    1. its developer party is bridged to that customer (``project_parties.customer_id``),
       which is the buying relationship, and
    2. it was qualified out of one of that customer's leads -- the informant is often an
       architect or a contractor who never buys anything.

    Deduplicated by project id, because a lead recorded against the developer itself
    hits both routes and would otherwise render twice.
    """
    from app.services.project_service import serialize_projects

    lead_rows = leads_for_customer(db, customer_id=customer_id)

    party_ids = [
        row[0]
        for row in db.query(ProjectParty.id)
        .filter(ProjectParty.customer_id == customer_id)
        .all()
    ]
    lead_ids = [lead.id for lead in lead_rows]

    conditions = []
    if party_ids:
        conditions.append(Project.developer_party_id.in_(party_ids))
    if lead_ids:
        conditions.append(Project.lead_id.in_(lead_ids))

    projects: List[Project] = []
    if conditions:
        projects = (
            db.query(Project)
            .filter(or_(*conditions))
            .order_by(Project.created_at.desc())
            .all()
        )

    return {
        "leads": serialize_leads(db, lead_rows),
        "projects": serialize_projects(db, projects),
    }
