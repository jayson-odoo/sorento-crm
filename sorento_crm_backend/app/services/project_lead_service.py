"""Leads: the stage before a development is anybody's to claim (UAC Group O).

The whole design follows from one fact: **a lead is a rumour**.

- It is NOT exclusive. No fuzzy lock, no clash block, no unique title (AC-O3).
  Locking hearsay would let the first person to type a guess own a development nobody
  has confirmed exists, and a lead frequently has no developer to lock on.
- It needs a customer, because somebody told us (AC-O1).
- Ownership locks at QUALIFY, which is the moment the registration clash check
  finally runs, and where a rumour becomes a claim (AC-O4).
- One lead may produce SEVERAL projects: a masterplan sighting becomes a separate
  registration per phase (AC-O5).

Near-duplicates ARE surfaced on the list, informationally, using the same matcher the
registration lock uses. Surfacing and enforcing are different things and this module
does exactly one of them here.
"""
from __future__ import annotations

from datetime import datetime
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

NUMBERING_DOC_TYPE = "project_lead"
LEAD_ENTITY_TYPE = "project_lead"

OUTCOME_OPEN = LEAD_OUTCOME_OPEN
OUTCOME_QUALIFIED = LEAD_OUTCOME_QUALIFIED
OUTCOME_DISQUALIFIED = LEAD_OUTCOME_DISQUALIFIED

# Fields a caller may set on create or edit. Everything else about a lead is decided
# by the service (code, outcome, status, qualified_at) so a client cannot, for
# example, mark its own lead qualified without going through the clash check.
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


def _assert_customer(db: Session, customer_id: Optional[str]) -> None:
    """AC-O1. Required, matching ecohub's non-nullable ``Lead.clientId``.

    A lead with no customer is a note, and notes do not need a pipeline. Checked in
    the service as well as by the NOT NULL column so the caller gets a 422 that says
    what to do rather than an IntegrityError.
    """
    if not customer_id:
        raise AppException(
            status_code=422,
            message=(
                "A lead needs the customer who told us about it. Pick an existing "
                "customer or create one from the wizard."
            ),
            code="lead_customer_required",
        )
    exists = db.query(Customer.id).filter(Customer.id == customer_id).first()
    if not exists:
        raise AppException(
            status_code=404,
            message="That customer no longer exists.",
            code="lead_customer_not_found",
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
    _assert_customer(db, payload.get("customer_id"))
    _assert_source(payload.get("source"))
    _assert_developer(db, payload.get("developer_party_id"))

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
        customer_id=payload["customer_id"],
        developer_party_id=payload.get("developer_party_id"),
        title=title,
        normalised_title=normalise_project_title(title),
        source=payload.get("source"),
        source_detail=payload.get("source_detail"),
        estimated_value=payload.get("estimated_value"),
        location=payload.get("location"),
        notes=payload.get("notes"),
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
    """Step 1 of the wizard: pick a customer, or create one for a non-buyer.

    This is the accepted reversal recorded in the plan: `project_parties` exists to
    keep organisations OUT of the 2,391-row buying ledger, and here we add to it. The
    real data supports it (KHOO SOON LEE REALTY and GLOBAL INGRESS are already
    customers), and rows created this way carry ``source='project_lead'`` so order and
    invoice pickers can filter prospects out if the noise becomes real.
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
        _assert_customer(db, payload.get("customer_id"))
        lead.customer_id = payload["customer_id"]
    if "source" in payload:
        _assert_source(payload.get("source"))
    if "developer_party_id" in payload:
        _assert_developer(db, payload.get("developer_party_id"))

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
    developer_ids = {lead.developer_party_id for lead in leads if lead.developer_party_id}
    developers = (
        {
            row.id: row.name
            for row in db.query(ProjectParty)
            .filter(ProjectParty.id.in_(developer_ids))
            .all()
        }
        if developer_ids
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
                "developer_name": developers.get(lead.developer_party_id or ""),
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
