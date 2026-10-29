"""Project Sales service layer.

Registration is the entry point to the whole module: everything downstream
(quotations, samples, forecast) hangs off a project that someone claimed.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.projects import (
    APPROVAL_APPROVED,
    APPROVAL_DRAFT,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    APPROVAL_RESUBMITTED,
    OUTCOME_OPEN,
    Project,
    ProjectCollaborator,
    ProjectParty,
    ProjectPurchaseOrder,
    ProjectSalesProfile,
    ProjectStakeholder,
    ProjectTakeoverRequest,
    ProjectTemplate,
    ProjectTemplateRole,
    ProjectType,
)
from app.models.status import Status
from app.status_engine.registry import get_status_entity
from app.schemas.common import MAX_PAGE_LIMIT
from app.services import submission_status
from app.services.error_handler import AppException
from app.services.numbering_service import NumberingService
from app.services.project_clash_service import (
    ClashCandidate,
    find_clashes,
    normalise_project_title,
)
from app.services.submission_status import APPEALED_LABEL

NUMBERING_DOC_TYPE = "project"

#: What a project with no code yet (a portal registration before Approve) is called in every
#: message and title, so nothing ever reads "None" (PROJECT-REG-PORTAL R2).
AWAITING_APPROVAL_LABEL = "Awaiting approval"
#: Lets an approver work a portal registration while it waits (R7, R8).
APPROVE_REGISTRATIONS_PERMISSION = "projects.registrations.approve"


REJECTED_LABEL = "Rejected"
RESUBMITTED_LABEL = APPEALED_LABEL


def project_label(project) -> str:
    """The project's code; while it has none, "Rejected" for a refused registration,
    "Appealed" for one sent back after a rejection, and "Awaiting approval" for any other."""
    code = (getattr(project, "project_code", None) or "").strip()
    if code:
        return code
    state = getattr(project, "approval_state", None)
    if state == APPROVAL_REJECTED:
        return REJECTED_LABEL
    if state == APPROVAL_RESUBMITTED:
        return RESUBMITTED_LABEL
    return AWAITING_APPROVAL_LABEL


def is_approved(project) -> bool:
    """A staff project (no approval state) or an approved portal registration."""
    return getattr(project, "approval_state", None) in (None, APPROVAL_APPROVED)


def approved_projects(query):
    """Narrow a `Project` query to the rows that are projects yet (R4): staff-registered
    ones and approved portal registrations. Every internal path (pickers, validators,
    reports, the clash check, the sweeps, embeddings) reads through this."""
    return query.filter(
        or_(Project.approval_state.is_(None), Project.approval_state == APPROVAL_APPROVED)
    )


# Each opens with the label the project carries in place of a code (R2).
_NOT_APPROVED_MESSAGES = {
    APPROVAL_PENDING: (
        f"{AWAITING_APPROVAL_LABEL}: nothing can be added to this project until it is approved."
    ),
    APPROVAL_RESUBMITTED: (
        f"{AWAITING_APPROVAL_LABEL}: nothing can be added to this project until it is approved."
    ),
    APPROVAL_REJECTED: (
        f"{REJECTED_LABEL}: this project registration is not approved, so nothing can be "
        "added to it."
    ),
    APPROVAL_DRAFT: (
        f"{AWAITING_APPROVAL_LABEL}: this project registration has not been submitted for "
        "approval yet."
    ),
}


def check_company_refs(
    db: Session, company_id: str, payload: Dict[str, Any], *, code: str = "project_ref_invalid"
) -> None:
    """Every party, type and template id a caller sends must belong to the project's
    company (security S10 / N1): the pickers are company scoped, the API must not trust that."""
    from uuid import UUID

    def is_uuid(value: Any) -> bool:
        try:
            UUID(str(value))
            return True
        except (TypeError, ValueError):
            return False

    refuse = AppException(
        status_code=422,
        message="Pick the parties, type and template from this company.",
        code=code,
    )
    for key in ("developer_party_id", "architect_party_id", "main_contractor_party_id"):
        value = payload.get(key)
        if value and not (
            is_uuid(value)
            and db.query(ProjectParty.id)
            .filter(ProjectParty.id == str(value), ProjectParty.company_id == company_id)
            .first()
        ):
            raise refuse
    customer_id = payload.get("customer_id")
    if customer_id:
        from app.models.order import Customer

        if not (
            is_uuid(customer_id)
            and db.query(Customer.id)
            .filter(Customer.id == str(customer_id), Customer.company_id == company_id)
            .first()
        ):
            raise AppException(
                status_code=422, message="Pick the customer from this company.", code=code
            )
    for key, model in (("type_id", ProjectType), ("template_id", ProjectTemplate)):
        value = payload.get(key)
        if value and not (
            is_uuid(value)
            and db.query(model.id).filter(model.id == str(value), model.company_id == company_id).first()
        ):
            raise refuse


def assert_linkable_project(
    db: Session, project_id: Optional[str], current: Optional[str] = None, *, code: str
) -> None:
    """A record (complaint, purchase request) links to a PROJECT, never a portal
    registration still waiting for approval (R4). Re-saving the link a record already has
    is not a change, so an older link keeps saving."""
    if not project_id or str(project_id) == str(current or ""):
        return
    if approved_projects(db.query(Project.id).filter(Project.id == str(project_id))).first() is None:
        raise AppException(
            status_code=422,
            message="That project is not approved yet. Pick a project from the list.",
            code=code,
        )


def _changed_refs(db: Session, project: Project, payload: Dict[str, Any]) -> Dict[str, Any]:
    """The ids in an edit that differ from what the project already links. The edit form
    sends every field back, so checking unchanged ones would lock a legacy project that
    already links a record of another company out of every save."""
    stored = {
        "developer_party_id": project.developer_party_id,
        "type_id": project.type_id,
        "template_id": project.template_id,
    }
    profile = db.query(ProjectSalesProfile).filter(ProjectSalesProfile.project_id == project.id).first()
    stored["customer_id"] = getattr(profile, "customer_id", None)
    stored["architect_party_id"] = getattr(profile, "architect_party_id", None)
    stored["main_contractor_party_id"] = getattr(profile, "main_contractor_party_id", None)
    out: Dict[str, Any] = {
        key: payload[key]
        for key in stored
        if key in payload and str(payload[key] or "") != str(stored[key] or "")
    }
    return out


def assert_project_approved(project) -> None:
    """409 `project_not_approved` for a portal registration that is not a project yet: no
    quotation, sample, PO, schedule, sales order, task, stakeholder or stage move (R4, R8)."""
    if is_approved(project):
        return
    raise AppException(
        status_code=409,
        message=_NOT_APPROVED_MESSAGES.get(
            project.approval_state, "This project is not approved yet."
        ),
        code="project_not_approved",
    )


def _describe_blockers(
    db: Session, blockers: List[ClashCandidate], actor_user_id: Optional[str] = None
) -> str:
    """The refusal message. Names the incumbent so the user knows who to talk to.

    "Already registered" on its own is a dead end; the point of the block is to
    route the second person to the first one, or to the request-to-join path.

    Except to a user who may see only their own projects (PORTAL-P2-ONLY-THEIRS): naming a
    project they cannot open would let them probe for other people's pursuits by
    registering guesses, so they are sent to a manager instead.
    """
    from app.services import own_scope

    if actor_user_id and own_scope.user_is_limited(
        db, str(actor_user_id), own_scope.PROJECTS_VIEW, own_scope.PROJECTS_VIEW_OWN
    ):
        return "This development is already registered. Ask a sales manager about it."
    owner_ids = [b.owner_user_id for b in blockers if b.owner_user_id]
    names = {}
    if owner_ids:
        from app.models.user import User

        names = {
            u.id: (u.name or u.email)
            for u in db.query(User).filter(User.id.in_(owner_ids)).all()
        }

    parts = []
    for blocker in blockers:
        who = names.get(blocker.owner_user_id) or "an unassigned owner"
        parts.append(f'"{blocker.title}" ({blocker.project_code}), held by {who}')

    joined = "; ".join(parts)
    return (
        f"This development is already registered as {joined}. "
        "Ask to join the project, or raise a dispute for a manager to decide."
    )


def register_project(
    db: Session,
    *,
    company_id: str,
    actor_user_id: str,
    developer_party_id: Optional[str],
    title: str,
    type_id: Optional[str] = None,
    template_id: Optional[str] = None,
    details: Optional[dict] = None,
    owner_user_id: Optional[str] = None,
    surface_threshold: Optional[float] = None,
    block_threshold: Optional[float] = None,
    skip_clash_check: bool = False,
) -> Project:
    """Claim a development for ``actor_user_id``.

    Raises 409 when an open project under the same developer is the same
    development. There is no override flag: the recourse is request-to-join or a
    dispute (ADR-0004), both of which leave a record, whereas a force-create flag
    would leave none and would become the default click.

    The clash check runs BEFORE the number is drawn, so a rejected attempt does not
    burn a project code and leave a gap in the sequence.
    """
    clean_title = " ".join((title or "").split())
    if not clean_title:
        raise AppException(
            status_code=422,
            message="A project title is required.",
            code="project_title_required",
        )

    # `skip_clash_check` (PROJECT-REG-PORTAL D7): a possible duplicate is the caller's call,
    # and only an exact developer + title repeat is refused (by the DB identity index). Staff
    # registration keeps its lock.
    blockers = (
        []
        if skip_clash_check
        else [
            candidate
            for candidate in find_clashes(
                db,
                company_id=company_id,
                developer_party_id=developer_party_id,
                title=clean_title,
                surface_threshold=surface_threshold,
                block_threshold=block_threshold,
            )
            if candidate.blocks
        ]
    )
    if blockers:
        raise AppException(
            status_code=409,
            message=_describe_blockers(db, blockers, actor_user_id),
            code="project_already_registered",
        )

    project = Project(
        company_id=company_id,
        title=clean_title,
        normalised_title=normalise_project_title(clean_title),
        developer_party_id=developer_party_id,
        type_id=type_id,
        template_id=template_id,
        outcome=OUTCOME_OPEN,
        owner_user_id=owner_user_id or actor_user_id,
        created_by=actor_user_id,
    )
    start_project(db, project, actor_user_id=actor_user_id, details=details)
    return project


def draw_project_code(db: Session) -> str:
    """The next code from the `project` numbering rule (PPF, D6).

    commit_rule=False so drawing the number joins the caller's transaction: if the
    insert that follows fails, the sequence rolls back with it rather than leaving a hole.
    """
    code = NumberingService(db).get_next_number(NUMBERING_DOC_TYPE, commit_rule=False)
    if not code:
        raise AppException(
            status_code=422,
            message=(
                "No enabled numbering rule for projects. Configure one under "
                "Settings before registering a project."
            ),
            code="project_numbering_rule_missing",
        )
    return code


def start_project(
    db: Session,
    project: Project,
    *,
    actor_user_id: str,
    details: Optional[dict] = None,
) -> Project:
    """Give ``project`` its code, its first funnel rung, its details and its template
    checklist. A staff registration runs it on a new row; Approve runs it on the portal
    registration's own row (R9). Flushes, so the identity index answers here."""
    project.project_code = draw_project_code(db)
    if project not in db:
        db.add(project)
    db.flush()

    # The initial funnel position comes from the graph, so it is configurable and a
    # forked template graph starts its projects on its own first rung. A project with
    # no graph configured yet is left status-less rather than refused: the
    # registration is the valuable part, and the funnel can be set up after.
    from app.services import status_service

    try:
        entity = get_status_entity("project")
        scope_id = entity.scope_for(project) if entity else None
        project.status_id = status_service.initial_status(db, "project", scope_id).id
    except AppException:
        project.status_id = None

    if details:
        apply_sales_details(db, project, details)

    # The template's checklist lands with the project (AC-N1), so a new registration
    # already knows its next action instead of being an empty shell someone has to
    # remember to populate.
    if project.template_id:
        from app.services.project_task_service import instantiate_template_tasks

        instantiate_template_tasks(
            db, project=project, actor_user_id=actor_user_id
        )

    db.flush()
    return project


# ------------------------------------------------------------- edit rights


MANAGE_PERMISSION = "projects.projects.manage"
EDIT_PERMISSION = "projects.projects.edit"
CUSTOMERS_VIEW_PERMISSION = "order_management.customers.view"

TAKEOVER_JOIN = "join"
TAKEOVER_DISPUTE = "dispute"
TAKEOVER_KINDS = (TAKEOVER_JOIN, TAKEOVER_DISPUTE)

TAKEOVER_PENDING = "pending"
TAKEOVER_APPROVED = "approved"
TAKEOVER_REJECTED = "rejected"


def _is_collaborator(db: Session, project_id: str, user_id: str) -> bool:
    return (
        db.query(ProjectCollaborator)
        .filter(
            ProjectCollaborator.project_id == project_id,
            ProjectCollaborator.user_id == user_id,
        )
        .first()
        is not None
    )


def can_edit_project(
    db: Session, project: Project, user_id: str, permissions: Set[str]
) -> bool:
    """Owner, approved collaborator, or manager; and, for a portal registration still
    PENDING approval, whoever may approve it (R8: the approver fixes it up before Approve).
    The approve grant opens nothing else: not a staff project, not an approved or a
    rejected one.

    Reading is intentionally wide open (UAC Group J) and is NOT gated here: the module
    exists to make other people's pursuits visible, so a read filter would defeat it.
    """
    if MANAGE_PERMISSION in (permissions or set()):
        return True
    if (
        submission_status.is_awaiting_review(project.approval_state, APPROVAL_PENDING)
        and APPROVE_REGISTRATIONS_PERMISSION in (permissions or set())
    ):
        return True
    if user_id and project.owner_user_id == user_id:
        return True
    return bool(user_id) and _is_collaborator(db, project.id, user_id)


def assert_can_edit_project(
    db: Session, project: Project, user_id: str, permissions: Set[str]
) -> None:
    if can_edit_project(db, project, user_id, permissions):
        return
    raise AppException(
        status_code=403,
        message=(
            f"{project_label(project)} belongs to another salesperson. Ask to join it "
            "as a collaborator, or raise a dispute for a manager to decide."
        ),
        code="project_not_editable",
    )


def assert_can_write_project(
    db: Session, project: Project, user_id: str, permissions: Set[str]
) -> None:
    """The edit right plus R8: work hung on a project (quotations, samples, POs, schedules,
    sales orders, tasks, stakeholders) waits until the project is approved."""
    assert_can_edit_project(db, project, user_id, permissions)
    assert_project_approved(project)


def _add_collaborator(
    db: Session, project_id: str, user_id: str, granted_by: Optional[str]
) -> None:
    """Idempotent: an already-granted user must not raise on the composite PK."""
    if _is_collaborator(db, project_id, user_id):
        return
    db.add(
        ProjectCollaborator(
            project_id=project_id, user_id=user_id, granted_by=granted_by
        )
    )
    db.flush()


# --------------------------------------------------- join / dispute requests


def create_takeover_request(
    db: Session,
    *,
    project: Project,
    requester_user_id: str,
    kind: str,
    reason: str,
) -> ProjectTakeoverRequest:
    """The recourse path from a blocked registration (AC-C7).

    Hard blocking with no way out produces defensive land-grabbing and pushes the
    argument back into WhatsApp, so both routes exist and both leave a record.
    """
    # Nobody joins or disputes a registration that is not a project yet (security N3).
    assert_project_approved(project)
    if kind not in TAKEOVER_KINDS:
        raise AppException(
            status_code=422,
            message="A request must be either a join request or a dispute.",
            code="project_takeover_kind_invalid",
        )
    if not (reason or "").strip():
        raise AppException(
            status_code=422,
            message="Give a reason -- the owner or manager decides on it.",
            code="project_takeover_reason_required",
        )
    if project.owner_user_id and project.owner_user_id == requester_user_id:
        raise AppException(
            status_code=422,
            message=f"You already own {project_label(project)}.",
            code="project_takeover_self",
        )

    existing = (
        db.query(ProjectTakeoverRequest)
        .filter(
            ProjectTakeoverRequest.project_id == project.id,
            ProjectTakeoverRequest.requester_user_id == requester_user_id,
            ProjectTakeoverRequest.status == TAKEOVER_PENDING,
        )
        .first()
    )
    if existing:
        raise AppException(
            status_code=409,
            message=(
                f"You already have a request open on {project_label(project)}. "
                "Wait for it to be decided."
            ),
            code="project_takeover_already_open",
        )

    request = ProjectTakeoverRequest(
        project_id=project.id,
        requester_user_id=requester_user_id,
        kind=kind,
        reason=reason.strip(),
        status=TAKEOVER_PENDING,
    )
    db.add(request)
    db.flush()
    return request


def decide_takeover_request(
    db: Session,
    *,
    request: ProjectTakeoverRequest,
    decider_user_id: str,
    decider_permissions: Set[str],
    approve: bool,
    decision_note: Optional[str] = None,
) -> ProjectTakeoverRequest:
    """Approve or reject, once.

    The two kinds resolve differently on purpose. A JOIN grants collaborator rights
    and leaves ownership alone. A DISPUTE transfers ownership -- and demotes the
    previous owner to collaborator rather than locking them out, because they did
    real work on the project and the decision was about who leads it, not about
    erasing their access.
    """
    if request.status != TAKEOVER_PENDING:
        raise AppException(
            status_code=409,
            message=f"This request was already {request.status}.",
            code="project_takeover_already_decided",
        )

    project = db.query(Project).filter(Project.id == request.project_id).first()
    if project is None:
        raise AppException(
            status_code=404,
            message="The project this request refers to no longer exists.",
            code="project_not_found",
        )

    is_manager = MANAGE_PERMISSION in (decider_permissions or set())
    is_owner = bool(decider_user_id) and project.owner_user_id == decider_user_id
    # A dispute is a manager decision by definition: letting the incumbent rule on a
    # claim against themselves is not a decision.
    if request.kind == TAKEOVER_DISPUTE:
        allowed = is_manager
    else:
        allowed = is_manager or is_owner
    if not allowed:
        raise AppException(
            status_code=403,
            message=(
                "Only the project owner or a sales manager can decide this request."
                if request.kind == TAKEOVER_JOIN
                else "Only a sales manager can decide a dispute."
            ),
            code="project_takeover_not_decidable",
        )

    request.status = TAKEOVER_APPROVED if approve else TAKEOVER_REJECTED
    request.decided_by = decider_user_id
    request.decided_at = datetime.utcnow()
    request.decision_note = (decision_note or "").strip() or None

    if approve:
        if request.kind == TAKEOVER_JOIN:
            _add_collaborator(
                db, project.id, request.requester_user_id, decider_user_id
            )
        else:
            previous_owner = project.owner_user_id
            project.owner_user_id = request.requester_user_id
            if previous_owner and previous_owner != request.requester_user_id:
                _add_collaborator(db, project.id, previous_owner, decider_user_id)
            names = resolve_user_names(db, [previous_owner, request.requester_user_id])
            from_name = names.get(str(previous_owner)) or "nobody"
            to_name = names.get(str(request.requester_user_id)) or "a colleague"
            from app.services import project_activity_service as activity

            activity.record_project_event(
                db,
                project=project,
                template="owner_reassigned",
                payload={
                    "from_user_id": str(previous_owner) if previous_owner else None,
                    "to_user_id": str(request.requester_user_id),
                    "from_name": from_name,
                    "to_name": to_name,
                },
                actor_id=decider_user_id,
                body_text=f"Reassigned from {from_name} to {to_name}",
            )

    db.flush()
    return request


# ------------------------------------------------------------- serialisation


def _name_map(db: Session, user_ids) -> Dict[str, str]:
    ids = [uid for uid in set(user_ids) if uid]
    if not ids:
        return {}
    from app.models.user import User

    return {
        u.id: (u.name or u.email)
        for u in db.query(User).filter(User.id.in_(ids)).all()
    }


def _party_name_map(db: Session, party_ids) -> Dict[str, str]:
    ids = [pid for pid in set(party_ids) if pid]
    if not ids:
        return {}
    return {
        p.id: p.name
        for p in db.query(ProjectParty).filter(ProjectParty.id.in_(ids)).all()
    }


def _days_since(moment: Optional[datetime]) -> Optional[int]:
    if moment is None:
        return None
    return max(0, (datetime.utcnow() - moment).days)


def serialize_projects(
    db: Session,
    projects: List[Project],
    *,
    actor_user_id: Optional[str] = None,
    permissions: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Resolve every FK to a human-readable name in bulk.

    Bulk because the pipeline board renders every open project at once, and a
    per-row owner/developer/brand lookup would be a few hundred queries per load.

    ``can_edit`` is computed here so the FE never has to re-derive the ownership
    rule -- a second implementation of it in TypeScript is a second place for it to
    be wrong.
    """
    if not projects:
        return []

    permissions = permissions or set()
    is_manager = MANAGE_PERMISSION in permissions

    owner_names = _name_map(db, [p.owner_user_id for p in projects])
    party_names = _party_name_map(
        db, [p.developer_party_id for p in projects]
    )

    profiles = {
        row.project_id: row
        for row in db.query(ProjectSalesProfile)
        .filter(ProjectSalesProfile.project_id.in_([p.id for p in projects]))
        .all()
    }
    profile_party_names = _party_name_map(
        db,
        [pr.architect_party_id for pr in profiles.values()]
        + [pr.main_contractor_party_id for pr in profiles.values()],
    )

    status_ids = [p.status_id for p in projects if p.status_id]
    statuses = (
        {
            s.id: s
            for s in db.query(Status).filter(Status.id.in_(set(status_ids))).all()
        }
        if status_ids
        else {}
    )

    type_ids = [p.type_id for p in projects if p.type_id]
    types = (
        {
            t.id: t.name
            for t in db.query(ProjectType).filter(ProjectType.id.in_(set(type_ids))).all()
        }
        if type_ids
        else {}
    )
    template_ids = [p.template_id for p in projects if p.template_id]
    templates = (
        {
            t.id: t.name
            for t in db.query(ProjectTemplate)
            .filter(ProjectTemplate.id.in_(set(template_ids)))
            .all()
        }
        if template_ids
        else {}
    )

    # Where the pursuit came from, when it came from a lead (AC-O10). Bulk, and only
    # when some project on the page HAS a lead: a directly-registered pipeline pays
    # nothing for a feature it does not use.
    lead_ids = {p.lead_id for p in projects if p.lead_id}
    leads = {}
    if lead_ids:
        from app.models.projects import ProjectLead

        leads = {
            row.id: row
            for row in db.query(ProjectLead).filter(ProjectLead.id.in_(lead_ids)).all()
        }

    # The customer is the one picked on the register form (sales_profile.customer_id);
    # where none was, the linked lead's buyer. The Overview shows it and the quotation
    # header defaults its name, phone and Attn from it (owner, 13 Oct). Bulk like the rest.
    def _effective_customer_id(project_row):
        pr = profiles.get(project_row.id)
        if pr and pr.customer_id:
            return pr.customer_id
        lead = leads.get(project_row.lead_id) if project_row.lead_id else None
        return getattr(lead, "customer_id", None)

    customers = _customers_for(db, [_effective_customer_id(p) for p in projects])
    # The phone and the main contact are the customer master's, which sits behind its own
    # grant; a project reader without it sees the buyer's name only (security review, 13 Oct).
    can_see_customer_contact = CUSTOMERS_VIEW_PERMISSION in permissions

    # Next action is DERIVED from the earliest open task (AC-N6). One bulk query for
    # the whole page, because the board renders every open project at once.
    from app.services.project_task_service import next_action_for_projects

    next_actions = next_action_for_projects(db, [p.id for p in projects])

    # A portal registration's legacy-only fields (R7), read-only under the detail header.
    # The agent is shown by name, never only by code.
    agent_ids = {
        pr.sales_agent_id for pr in profiles.values() if pr.sales_agent_id
    }
    agent_names: Dict[str, Optional[str]] = {}
    if agent_ids:
        from app.models.sales_agent import SalesAgent
        from app.services.project_registration_service import agent_display_name

        agent_names = {
            row.id: agent_display_name(row)
            for row in db.query(SalesAgent).filter(SalesAgent.id.in_(agent_ids)).all()
        }
    may_approve = APPROVE_REGISTRATIONS_PERMISSION in permissions

    collaborating = set()
    if actor_user_id and not is_manager:
        collaborating = {
            row.project_id
            for row in db.query(ProjectCollaborator)
            .filter(
                ProjectCollaborator.user_id == actor_user_id,
                ProjectCollaborator.project_id.in_([p.id for p in projects]),
            )
            .all()
        }

    out: List[Dict[str, Any]] = []
    for project in projects:
        status = statuses.get(project.status_id) if project.status_id else None
        profile = profiles.get(project.id)
        out.append(
            {
                "id": project.id,
                "project_code": project.project_code,
                "title": project.title,
                "outcome": project.outcome,
                "loss_reason": project.loss_reason,
                "admin_ref": project.admin_ref,
                "developer_party_id": project.developer_party_id,
                "developer_name": party_names.get(project.developer_party_id),
                "type_id": project.type_id,
                "type_name": types.get(project.type_id),
                "template_id": project.template_id,
                "template_name": templates.get(project.template_id),
                # Null here is meaningful, not missing: the project was registered
                # directly, and the detail page says so rather than showing a blank.
                "lead_id": project.lead_id,
                "lead_code": (
                    leads[project.lead_id].lead_code
                    if project.lead_id in leads
                    else None
                ),
                "lead_source": (
                    leads[project.lead_id].source if project.lead_id in leads else None
                ),
                "lead_created_at": (
                    leads[project.lead_id].created_at
                    if project.lead_id in leads
                    else None
                ),
                "lead_owner_user_id": (
                    leads[project.lead_id].owner_user_id
                    if project.lead_id in leads
                    else None
                ),
                **_customer_fields(
                    customers.get(_effective_customer_id(project)),
                    with_contact=can_see_customer_contact,
                ),
                "status_id": project.status_id,
                "status_key": status.key if status else None,
                "status_label": status.label if status else None,
                "owner_user_id": project.owner_user_id,
                "owner_name": owner_names.get(project.owner_user_id),
                "is_critical": project.is_critical,
                "critical_at": project.critical_at,
                "management_support": project.management_support,
                "management_notes": project.management_notes,
                "registered_company_name": (
                    profile.registered_company_name if profile else None
                ),
                "location": profile.location if profile else None,
                "address": profile.address if profile else None,
                "state": profile.state if profile else None,
                "mukim": profile.mukim if profile else None,
                "architect_party_id": profile.architect_party_id if profile else None,
                "architect_name": (
                    profile_party_names.get(profile.architect_party_id)
                    if profile
                    else None
                ),
                "main_contractor_party_id": (
                    profile.main_contractor_party_id if profile else None
                ),
                "main_contractor_name": (
                    profile_party_names.get(profile.main_contractor_party_id)
                    if profile
                    else None
                ),
                "estimated_sales_value": (
                    profile.estimated_sales_value if profile else None
                ),
                "launch_date": profile.launch_date if profile else None,
                "expected_delivery_from": (
                    profile.expected_delivery_from if profile else None
                ),
                "expected_delivery_to": (
                    profile.expected_delivery_to if profile else None
                ),
                "last_meaningful_activity_at": project.last_meaningful_activity_at,
                "days_since_last_activity": _days_since(
                    project.last_meaningful_activity_at
                ),
                "next_action_date": next_actions.get(project.id, {}).get(
                    "next_action_date"
                ),
                "next_action_overdue": next_actions.get(project.id, {}).get(
                    "next_action_overdue", False
                ),
                "open_task_count": next_actions.get(project.id, {}).get(
                    "open_task_count", 0
                ),
                # Staleness ladder (AC-H6). Sent as the stamped level rather than recomputed
                # per row: the sweep is what decides a rung, and a list that computed its own
                # answer could disagree with the notification the owner just received.
                "stale_level": int(project.stale_level or 0),
                "stale_reason": project.stale_reason,
                "stale_since": project.stale_since,
                "is_unattended": int(project.stale_level or 0) >= 3,
                "can_edit": (
                    is_manager
                    or (
                        bool(actor_user_id)
                        and project.owner_user_id == actor_user_id
                    )
                    or project.id in collaborating
                    or (
                        may_approve
                        and submission_status.is_awaiting_review(
                            project.approval_state, APPROVAL_PENDING
                        )
                    )
                ),
                "approval_state": project.approval_state,
                "reject_reason": project.reject_reason,
                "submitted_at": project.submitted_at,
                "decided_at": project.decided_at,
                "registration": (
                    _registration_block(profile, agent_names)
                    if project.approval_state is not None
                    else None
                ),
                # Filled for a pending project's detail only (the route): the list never
                # pays an embedding call per row.
                "possible_duplicates": [],
                "created_at": project.created_at,
                "updated_at": project.updated_at,
            }
        )
    if "projects.registrations.submit" in permissions and "projects.projects.edit" not in permissions:
        # A submit-only user edits only their own draft or rejected registration (J3b).
        for row, project in zip(out, projects):
            row["can_edit"] = bool(
                actor_user_id
                and project.owner_user_id == actor_user_id
                and project.approval_state in (APPROVAL_DRAFT, APPROVAL_REJECTED)
            )
    return out


def _registration_block(
    profile: Optional[ProjectSalesProfile], agent_names: Dict[str, Optional[str]]
) -> Dict[str, Any]:
    def value(key: str):
        return getattr(profile, key, None) if profile is not None else None

    return {
        "sales_agent_name": agent_names.get(value("sales_agent_id")),
        "distributor_name": value("distributor_name"),
        "customer_name": value("customer_name"),
        "your_ref": value("your_ref"),
        "type_of_building": value("type_of_building"),
        "developer_name": value("developer_name"),
        "main_contractor_name": value("main_contractor_name"),
        "architect_name": value("architect_name"),
    }


def serialize_project(
    db: Session,
    project: Project,
    *,
    actor_user_id: Optional[str] = None,
    permissions: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    return serialize_projects(
        db, [project], actor_user_id=actor_user_id, permissions=permissions
    )[0]


def _draft_visible_to(viewer_user_id: Optional[str]):
    """Not a draft, or a draft its owner is looking at (PROJECT-REGISTER-V2 J3)."""
    not_draft = or_(Project.approval_state.is_(None), Project.approval_state != APPROVAL_DRAFT)
    if not viewer_user_id:
        return not_draft
    return or_(
        not_draft,
        (Project.approval_state == APPROVAL_DRAFT) & (Project.owner_user_id == str(viewer_user_id)),
    )


def get_project_or_404(
    db: Session, project_id: str, viewer_user_id: Optional[str] = None
) -> Project:
    """The project for a STAFF route. A contact's unsent portal draft is nobody else's
    business (security N2), so every staff route reads it as not found; the portal reaches
    its own drafts through `project_registration_service._own`, never through here. A
    salesperson's own draft (owner = ``viewer_user_id``) is the one draft a staff route shows."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, _draft_visible_to(viewer_user_id))
        .first()
    )
    if project is None:
        raise AppException(
            status_code=404,
            message="Project not found.",
            code="project_not_found",
        )
    return project


# ---------------------------------------------------------------- listing


def status_ids_for_keys(db: Session, keys: List[str]) -> List[str]:
    """Translate funnel KEYS to status ids, across the default graph and every fork.

    Keys, not ids, because `key` is the documented stable identity per entity_type (grill
    finding G3) and a caller (an AI agent, a report, a webhook) should be able to say
    "tendering" without a status-table round trip. Every scope is included: a template that
    forked its graph still has a rung keyed `tendering`, and "which projects are tendering"
    means all of them.

    An unknown key raises 422 naming the valid ones -- returning zero rows would read as
    "nothing is at that stage", which is a different and wrong answer.
    """
    from app.models.status import Status

    wanted = [k.strip() for k in keys if (k or "").strip()]
    if not wanted:
        return []

    rows = (
        db.query(Status.id, Status.key)
        .filter(Status.entity_type == "project", Status.key.in_(wanted))
        .all()
    )
    found = {row[1] for row in rows}
    missing = [k for k in wanted if k not in found]
    if missing:
        known = sorted(
            {
                row[0]
                for row in db.query(Status.key)
                .filter(Status.entity_type == "project")
                .distinct()
                .all()
            }
        )
        raise AppException(
            status_code=422,
            message=(
                f"Unknown project stage {', '.join(repr(k) for k in missing)}. "
                f"Valid stages: {', '.join(known)}."
            ),
            code="project_status_key_unknown",
        )
    return [str(row[0]) for row in rows]


def list_projects(
    db: Session,
    *,
    company_id: str,
    search: Optional[str] = None,
    status_ids: Optional[List[str]] = None,
    outcomes: Optional[List[str]] = None,
    owner_user_ids: Optional[List[str]] = None,
    developer_party_ids: Optional[List[str]] = None,
    project_ids: Optional[List[str]] = None,
    type_ids: Optional[List[str]] = None,
    only_critical: bool = False,
    approval_states: Optional[List[str]] = None,
    approved_only: bool = False,
    visible_to=None,
    viewer_user_id: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    sort: str = "created_at",
    direction: str = "desc",
) -> tuple:
    """``(projects, total)``.

    ``visible_to`` (an ``own_scope.Me``) narrows to that user's own projects, for a user who
    may only see their own (PORTAL-P2-ONLY-THEIRS); ``None`` is the wide-open read.

    Sorting is whitelisted rather than reflected off the model: an arbitrary
    ``sort`` string would let a caller order by any column, including ones the
    listing never exposes.

    Pending and rejected portal registrations are listed (R6), a contact's unsent
    draft never is, whatever the filter (a salesperson's own draft is listed to its owner). ``approved_only`` is the pickers' filter:
    staff and approved projects only.
    """
    query = db.query(Project).filter(
        Project.company_id == company_id, _draft_visible_to(viewer_user_id)
    )
    if visible_to is not None:
        from app.services import own_scope

        query = query.filter(own_scope.project_clause(visible_to))
    if approved_only:
        query = approved_projects(query)
    if approval_states:
        query = query.filter(Project.approval_state.in_(approval_states))

    if search and search.strip():
        needle = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Project.title).like(needle),
                func.lower(Project.project_code).like(needle),
            )
        )
    if status_ids:
        query = query.filter(Project.status_id.in_(status_ids))
    if outcomes:
        query = query.filter(Project.outcome.in_(outcomes))
    if owner_user_ids:
        query = query.filter(Project.owner_user_id.in_(owner_user_ids))
    if developer_party_ids:
        query = query.filter(Project.developer_party_id.in_(developer_party_ids))
    if project_ids:
        query = query.filter(Project.id.in_(project_ids))
    if type_ids:
        query = query.filter(Project.type_id.in_(type_ids))
    if only_critical:
        query = query.filter(Project.is_critical.is_(True))

    total = query.count()

    sortable = {
        "created_at": Project.created_at,
        "updated_at": Project.updated_at,
        "project_code": Project.project_code,
        "title": Project.title,
        "outcome": Project.outcome,
        "last_meaningful_activity_at": Project.last_meaningful_activity_at,
    }
    column = sortable.get(sort, Project.created_at)
    ordered = column.asc() if str(direction).lower() == "asc" else column.desc()
    if column is Project.project_code:
        # A project with no code yet sorts after every coded one, whichever the direction.
        ordered = ordered.nulls_last()
    query = query.order_by(ordered)

    page = max(1, int(page or 1))
    limit = max(1, min(int(limit or 50), MAX_PAGE_LIMIT))
    rows = query.offset((page - 1) * limit).limit(limit).all()
    return rows, total


# ------------------------------------------------------------ profile + edit


def _profile_for(db: Session, project_id: str) -> ProjectSalesProfile:
    profile = (
        db.query(ProjectSalesProfile)
        .filter(ProjectSalesProfile.project_id == project_id)
        .first()
    )
    if profile is None:
        profile = ProjectSalesProfile(project_id=project_id)
        db.add(profile)
        db.flush()
    return profile


_PROFILE_FIELDS = (
    "customer_id",
    "registered_company_name",
    "location",
    "address",
    "state",
    "mukim",
    "architect_party_id",
    "main_contractor_party_id",
    "estimated_sales_value",
    "launch_date",
    "expected_delivery_from",
    "expected_delivery_to",
)

_PROJECT_FIELDS = (
    "type_id",
    "template_id",
    "loss_reason",
    "admin_ref",
    "management_support",
    "management_notes",
)


def apply_sales_details(
    db: Session,
    project: Project,
    payload: Dict[str, Any],
) -> None:
    """Write the Sorento-specific half plus the shared optional fields.

    Split across two tables (ADR-0003) so the generic skeleton stays portable, which
    is why this helper exists rather than one setattr loop.
    """
    profile_updates = {
        key: payload[key] for key in _PROFILE_FIELDS if key in payload
    }
    if profile_updates:
        profile = _profile_for(db, project.id)
        for key, value in profile_updates.items():
            setattr(profile, key, value)

    for key in _PROJECT_FIELDS:
        if key in payload:
            setattr(project, key, payload[key])

    db.flush()


def update_project(
    db: Session,
    project: Project,
    payload: Dict[str, Any],
    *,
    actor_user_id: str,
    permissions: Set[str],
) -> Project:
    """Edit a project. Retitling re-runs the clash check.

    A rename is how the lock would otherwise be bypassed: register "Setia Alam
    Phase 9", then rename it to the colleague's project. The DB unique index catches
    the exact-key case, but only the matcher catches the near-duplicate.
    """
    assert_can_edit_project(db, project, actor_user_id, permissions)
    check_company_refs(db, str(project.company_id), _changed_refs(db, project, payload))

    new_title = payload.get("title")
    new_developer = (
        payload["developer_party_id"]
        if "developer_party_id" in payload
        else project.developer_party_id
    )
    retitling = bool(new_title) and (
        normalise_project_title(new_title) != project.normalised_title
    )
    redeveloping = new_developer != project.developer_party_id

    if retitling or redeveloping:
        effective_title = new_title or project.title
        # A portal registration waiting for approval sits outside the lock (R3): fixing its
        # title or developer is the approver's preparation, and a possible duplicate never
        # blocks it (D7). Approve answers the exact repeat.
        blockers = [] if not is_approved(project) else [
            candidate
            for candidate in find_clashes(
                db,
                company_id=project.company_id,
                developer_party_id=new_developer,
                title=effective_title,
            )
            if candidate.blocks and candidate.project_id != project.id
        ]
        if blockers:
            raise AppException(
                status_code=409,
                message=_describe_blockers(db, blockers, actor_user_id),
                code="project_already_registered",
            )
        if new_title:
            project.title = " ".join(new_title.split())
            project.normalised_title = normalise_project_title(project.title)
        project.developer_party_id = new_developer

    if "owner_user_id" in payload and payload["owner_user_id"]:
        # Reassignment is a manager act. The owner handing their own project to
        # someone else quietly is how accountability for a stalled pursuit vanishes.
        if MANAGE_PERMISSION not in (permissions or set()):
            if payload["owner_user_id"] != project.owner_user_id:
                raise AppException(
                    status_code=403,
                    message="Only a sales manager can reassign a project owner.",
                    code="project_owner_reassign_forbidden",
                )
        project.owner_user_id = payload["owner_user_id"]

    if "is_critical" in payload and payload["is_critical"] is not None:
        set_critical(project, bool(payload["is_critical"]))

    own_leads_only = "projects.registrations.submit" in permissions and EDIT_PERMISSION not in permissions
    if payload.get("lead_id") and payload["lead_id"] != project.lead_id:
        # The lead governs the customer (LEAD-GOVERNS-REGISTER E4).
        from app.services import project_lead_service as leads

        lead = leads.lead_for_registration(
            db, payload["lead_id"], actor_user_id=actor_user_id, own_leads_only=own_leads_only
        )
        if lead.customer_id:
            payload = {**payload, "customer_id": leads.customer_from_lead(lead, payload.get("customer_id"))}
    apply_sales_details(db, project, payload)

    # Present-and-null is an unlink; absent leaves the link alone (#1339).
    if "lead_id" in payload:
        from app.services.project_lead_service import set_project_lead

        set_project_lead(
            db,
            project,
            payload["lead_id"],
            actor_user_id=actor_user_id,
            permissions=permissions,
            own_leads_only=own_leads_only,
        )
    return project


def _customers_for(db: Session, customer_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Name, phone and main contact per customer, in two queries for the whole page."""
    ids = {cid for cid in customer_ids if cid}
    if not ids:
        return {}
    from app.models.order import Customer, CustomerContact

    rows = db.query(Customer).filter(Customer.id.in_(ids)).all()
    contacts = {
        row.customer_id: row
        for row in db.query(CustomerContact)
        .filter(
            CustomerContact.customer_id.in_(ids),
            CustomerContact.contact_role == "main",
        )
        .all()
    }
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        contact = contacts.get(row.id)
        out[row.id] = {
            "customer_id": row.id,
            "customer_name": row.customer_name,
            "customer_code": row.customer_code,
            # The office line first, then the mobile, then the main contact's own number.
            "customer_phone": row.phone_number
            or row.mobile_number
            or (contact.phone or contact.mobile if contact else None),
            "customer_attn": contact.full_name if contact else None,
        }
    return out


def _customer_fields(
    customer: Optional[Dict[str, Any]], *, with_contact: bool
) -> Dict[str, Any]:
    if customer:
        if with_contact:
            return customer
        return {**customer, "customer_phone": None, "customer_attn": None}
    return {
        "customer_id": None,
        "customer_name": None,
        "customer_code": None,
        "customer_phone": None,
        "customer_attn": None,
    }


def set_critical(project: Project, critical: bool) -> None:
    """AC-G7. Stamps the date only on the transition INTO critical.

    Re-saving a project that is already critical must not reset the clock -- "days in
    final negotiation" is the number management acts on.
    """
    if critical and not project.is_critical:
        project.critical_at = datetime.utcnow()
    if not critical:
        project.critical_at = None
    project.is_critical = critical


def change_status(
    db: Session,
    project: Project,
    *,
    to_status_id: str,
    actor_user_id: str,
    permissions: Set[str],
) -> Project:
    """Move a project along the funnel, through the engine's legality check.

    Server-side (AC-B4): an illegal drag on the board is rejected here regardless of
    what the client sends.
    """
    assert_can_write_project(db, project, actor_user_id, permissions)

    from app.services import status_service

    entity_type = "project"
    scope_id = None
    entity = get_status_entity(entity_type)
    if entity is not None:
        scope_id = entity.scope_for(project)

    if project.status_id is None:
        # A project with no status yet (imported, or created before its graph was
        # configured) may enter the graph at its initial status only.
        initial = status_service.initial_status(db, entity_type, scope_id)
        if to_status_id != initial.id:
            raise AppException(
                status_code=422,
                message=(
                    f"{project_label(project)} has no status yet, so it can only start "
                    f"at '{initial.label}'."
                ),
                code="project_status_not_started",
            )
    else:
        status_service.assert_transition_allowed(
            db, entity_type, project.status_id, to_status_id, scope_id=scope_id
        )

    project.status_id = to_status_id
    db.flush()

    # A funnel move is real work (AC-H2), so it advances the staleness clock and writes the
    # feed row. Done here rather than in the route because the board, the detail page and
    # any future automation all come through this one function.
    from app.services import project_activity_service as activity

    activity.record_project_event(
        db,
        project=project,
        template="stage_changed",
        payload={"to_status_id": str(to_status_id)},
        actor_id=actor_user_id,
    )
    db.flush()
    return project


def delete_project(
    db: Session,
    project: Project,
    *,
    actor_user_id: str,
    permissions: Set[str],
) -> None:
    """Hard delete (AC-G10), blocked once a Project PO exists.

    A project with a customer PO against it is commercial history, and deleting it
    would silently remove revenue from every report that reads it. Archive is the
    action for that case.
    """
    assert_can_edit_project(db, project, actor_user_id, permissions)
    # An approver may edit a pending registration but never delete one: a registration
    # that should not stand is Rejected, so the salesperson reads why (security S2).
    if not is_approved(project) and MANAGE_PERMISSION not in (permissions or set()):
        raise AppException(
            status_code=403,
            message="Reject this registration instead: only a sales manager can delete it.",
            code="project_delete_forbidden",
        )

    # Through the ORM rather than raw SQL: the table is `projects.purchase_orders` and
    # `public.purchase_orders` is a DIFFERENT, supplier-side table (ADR-0002, ADR-0011),
    # so an unqualified count would silently read procurement's rows. The model carries
    # the schema, and a test fixture's schema translation carries with it.
    po_count = db.query(ProjectPurchaseOrder).filter_by(project_id=project.id).count()
    if po_count:
        raise AppException(
            status_code=409,
            message=(
                f"{project_label(project)} has {po_count} purchase order(s) "
                "recorded against it. Archive it instead of deleting."
            ),
            code="project_has_purchase_orders",
        )

    db.delete(project)
    db.flush()


def resolve_user_names(db: Session, user_ids) -> Dict[str, str]:
    """Public alias for the bulk user-name lookup, for route serialisers."""
    return _name_map(db, user_ids)


def serialize_clash_candidates(db: Session, candidates) -> List[Dict[str, Any]]:
    """Render each candidate with enough context to judge it (AC-C6a).

    Owner, status and value are what let someone tell "my colleague's live tender" from
    "a different phase with a similar name". A bare title would make the block look
    arbitrary.

    Lives here rather than in a router because two routers need it: the registration
    preview and the lead qualify preview must describe a clash identically, or the same
    collision reads as two different problems.
    """
    if not candidates:
        return []

    rows_by_id = {
        p.id: p
        for p in db.query(Project)
        .filter(Project.id.in_([c.project_id for c in candidates]))
        .all()
    }
    serialised = serialize_projects(
        db, [rows_by_id[c.project_id] for c in candidates if c.project_id in rows_by_id]
    )
    by_id = {row["id"]: row for row in serialised}

    out: List[Dict[str, Any]] = []
    for candidate in candidates:
        row = by_id.get(candidate.project_id, {})
        out.append(
            {
                "project_id": candidate.project_id,
                "project_code": candidate.project_code,
                "title": candidate.title,
                "outcome": candidate.outcome,
                "status_label": row.get("status_label"),
                "owner_user_id": candidate.owner_user_id,
                "owner_name": row.get("owner_name"),
                "developer_name": row.get("developer_name"),
                "estimated_sales_value": row.get("estimated_sales_value"),
                "last_activity_at": row.get("last_meaningful_activity_at"),
                "similarity": candidate.similarity,
                "blocks": candidate.blocks,
            }
        )
    return out
