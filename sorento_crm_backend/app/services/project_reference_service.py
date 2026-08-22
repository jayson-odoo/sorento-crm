"""Project reference data: parties, types, templates, template roles, stakeholders.

Kept out of ``project_service`` because none of it needs the registration lock, and
mixing them would put the one security-critical write path in the same file as
ordinary CRUD.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.projects import (
    Project,
    ProjectParty,
    ProjectStakeholder,
    ProjectTemplate,
    ProjectTemplateRole,
    ProjectType,
)
from app.schemas.common import MAX_PAGE_LIMIT
from app.services.error_handler import AppException

PARTY_TYPES = (
    "developer",
    "architect",
    "main_contractor",
    "trading_house",
    "consultant",
)

# The four roles the client named. Seeded, not hardcoded: a template owns its own
# list, so a hotel fitout can add "Operator" without a deploy.
DEFAULT_TEMPLATE_ROLES = (
    "Decision Maker",
    "Influencer",
    "Info Provider",
    "Architect",
)

INFLUENCE_LEVELS = ("high", "medium", "low")


# ------------------------------------------------------------------- parties


def list_parties(
    db: Session,
    *,
    company_id: str,
    party_type: Optional[str] = None,
    search: Optional[str] = None,
    include_inactive: bool = False,
    page: int = 1,
    limit: int = 50,
) -> tuple:
    query = db.query(ProjectParty).filter(ProjectParty.company_id == company_id)
    if party_type:
        query = query.filter(ProjectParty.party_type == party_type)
    if not include_inactive:
        query = query.filter(ProjectParty.is_active.is_(True))
    if search and search.strip():
        query = query.filter(
            func.lower(ProjectParty.name).like(f"%{search.strip().lower()}%")
        )
    total = query.count()
    page = max(1, int(page or 1))
    limit = max(1, min(int(limit or 50), MAX_PAGE_LIMIT))
    rows = (
        query.order_by(ProjectParty.name.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return rows, total


def serialize_parties(db: Session, parties: List[ProjectParty]) -> List[Dict[str, Any]]:
    """Includes ``project_count``, which is the whole reason parties are reusable.

    "Which architects should we prioritise visiting" is answerable only if the same
    firm is one row across projects, and the count is what makes that visible.
    """
    if not parties:
        return []

    party_ids = [p.id for p in parties]
    counts = dict(
        db.query(Project.developer_party_id, func.count(Project.id))
        .filter(Project.developer_party_id.in_(party_ids))
        .group_by(Project.developer_party_id)
        .all()
    )
    stakeholder_counts = dict(
        db.query(
            ProjectStakeholder.party_id, func.count(func.distinct(ProjectStakeholder.project_id))
        )
        .filter(ProjectStakeholder.party_id.in_(party_ids))
        .group_by(ProjectStakeholder.party_id)
        .all()
    )

    customer_names: Dict[str, str] = {}
    customer_ids = [p.customer_id for p in parties if p.customer_id]
    if customer_ids:
        from app.models.order import Customer

        customer_names = {
            c.id: c.customer_name
            for c in db.query(Customer).filter(Customer.id.in_(set(customer_ids))).all()
        }

    return [
        {
            "id": party.id,
            "party_type": party.party_type,
            "name": party.name,
            "registration_no": party.registration_no,
            "address": party.address,
            "phone": party.phone,
            "email": party.email,
            "notes": party.notes,
            "customer_id": party.customer_id,
            "customer_name": customer_names.get(party.customer_id),
            "is_active": party.is_active,
            # As developer, plus as a firm someone on the project belongs to. An
            # architect is never the developer, so a developer-only count would read
            # zero for every architect and make the list look broken.
            "project_count": counts.get(party.id, 0)
            + stakeholder_counts.get(party.id, 0),
            "created_at": party.created_at,
            "updated_at": party.updated_at,
        }
        for party in parties
    ]


def _assert_party_type(party_type: str) -> None:
    if party_type not in PARTY_TYPES:
        raise AppException(
            status_code=422,
            message=(
                "Party type must be one of: "
                + ", ".join(t.replace("_", " ") for t in PARTY_TYPES)
                + "."
            ),
            code="project_party_type_invalid",
        )


def create_party(
    db: Session, *, company_id: str, payload: Dict[str, Any], actor_user_id: str
) -> ProjectParty:
    _assert_party_type(payload.get("party_type"))
    name = (payload.get("name") or "").strip()
    if not name:
        raise AppException(
            status_code=422,
            message="A party name is required.",
            code="project_party_name_required",
        )

    # Same-name, same-type duplicates are what destroy the reuse the table exists
    # for, so they are refused with a pointer to the existing row rather than merged.
    existing = (
        db.query(ProjectParty)
        .filter(
            ProjectParty.company_id == company_id,
            ProjectParty.party_type == payload["party_type"],
            func.lower(ProjectParty.name) == name.lower(),
        )
        .first()
    )
    if existing:
        raise AppException(
            status_code=409,
            message=f'"{existing.name}" already exists. Use the existing record.',
            code="project_party_duplicate",
        )

    party = ProjectParty(
        company_id=company_id,
        party_type=payload["party_type"],
        name=name,
        registration_no=payload.get("registration_no"),
        address=payload.get("address"),
        phone=payload.get("phone"),
        email=payload.get("email"),
        notes=payload.get("notes"),
        customer_id=payload.get("customer_id"),
        is_active=payload.get("is_active", True),
        created_by=actor_user_id,
    )
    db.add(party)
    db.flush()
    return party


def get_party_or_404(db: Session, party_id: str) -> ProjectParty:
    party = db.query(ProjectParty).filter(ProjectParty.id == party_id).first()
    if party is None:
        raise AppException(
            status_code=404, message="Party not found.", code="project_party_not_found"
        )
    return party


def update_party(
    db: Session, party: ProjectParty, payload: Dict[str, Any]
) -> ProjectParty:
    if "party_type" in payload and payload["party_type"] is not None:
        _assert_party_type(payload["party_type"])
    for field in (
        "party_type",
        "name",
        "registration_no",
        "address",
        "phone",
        "email",
        "notes",
        "customer_id",
        "is_active",
    ):
        if field in payload and payload[field] is not None:
            value = payload[field]
            setattr(party, field, value.strip() if field == "name" else value)
    db.flush()
    return party


def delete_party(db: Session, party: ProjectParty) -> None:
    """Blocked while anything references it.

    The FK is ``ON DELETE RESTRICT``, which would surface as a raw driver error; this
    turns it into a sentence naming the count so the user knows what to do instead.
    """
    as_developer = (
        db.query(func.count(Project.id))
        .filter(Project.developer_party_id == party.id)
        .scalar()
    )
    if as_developer:
        raise AppException(
            status_code=409,
            message=(
                f'"{party.name}" is the developer on {as_developer} project(s). '
                "Deactivate it instead of deleting."
            ),
            code="project_party_in_use",
        )
    db.delete(party)
    db.flush()


# ------------------------------------------------------------ types/templates


def list_types(
    db: Session, *, company_id: str, include_inactive: bool = False
) -> List[ProjectType]:
    query = db.query(ProjectType).filter(ProjectType.company_id == company_id)
    if not include_inactive:
        query = query.filter(ProjectType.is_active.is_(True))
    return query.order_by(ProjectType.sort_order.asc(), ProjectType.name.asc()).all()


def serialize_types(db: Session, types: List[ProjectType]) -> List[Dict[str, Any]]:
    if not types:
        return []
    counts = dict(
        db.query(ProjectTemplate.type_id, func.count(ProjectTemplate.id))
        .filter(ProjectTemplate.type_id.in_([t.id for t in types]))
        .group_by(ProjectTemplate.type_id)
        .all()
    )
    return [
        {
            "id": t.id,
            "name": t.name,
            "code": t.code,
            "description": t.description,
            "derives_delivery_from_launch": t.derives_delivery_from_launch,
            "sort_order": t.sort_order,
            "is_active": t.is_active,
            "template_count": counts.get(t.id, 0),
        }
        for t in types
    ]


def create_type(
    db: Session, *, company_id: str, payload: Dict[str, Any]
) -> ProjectType:
    code = (payload.get("code") or "").strip()
    name = (payload.get("name") or "").strip()
    if not code or not name:
        raise AppException(
            status_code=422,
            message="A project type needs both a name and a code.",
            code="project_type_incomplete",
        )
    if (
        db.query(ProjectType)
        .filter(
            ProjectType.company_id == company_id,
            func.lower(ProjectType.code) == code.lower(),
        )
        .first()
    ):
        raise AppException(
            status_code=409,
            message=f'A project type with code "{code}" already exists.',
            code="project_type_duplicate",
        )
    project_type = ProjectType(
        company_id=company_id,
        name=name,
        code=code,
        description=payload.get("description"),
        derives_delivery_from_launch=bool(
            payload.get("derives_delivery_from_launch", False)
        ),
        sort_order=int(payload.get("sort_order") or 0),
        is_active=payload.get("is_active", True),
    )
    db.add(project_type)
    db.flush()
    return project_type


def get_type_or_404(db: Session, type_id: str) -> ProjectType:
    row = db.query(ProjectType).filter(ProjectType.id == type_id).first()
    if row is None:
        raise AppException(
            status_code=404,
            message="Project type not found.",
            code="project_type_not_found",
        )
    return row


def update_type(db: Session, project_type: ProjectType, payload: Dict[str, Any]):
    for field in (
        "name",
        "code",
        "description",
        "derives_delivery_from_launch",
        "sort_order",
        "is_active",
    ):
        if field in payload and payload[field] is not None:
            setattr(project_type, field, payload[field])
    db.flush()
    return project_type


def delete_type(db: Session, project_type: ProjectType) -> None:
    in_use = (
        db.query(func.count(Project.id))
        .filter(Project.type_id == project_type.id)
        .scalar()
    )
    if in_use:
        raise AppException(
            status_code=409,
            message=(
                f'"{project_type.name}" is used by {in_use} project(s). Deactivate it '
                "instead of deleting."
            ),
            code="project_type_in_use",
        )
    db.query(ProjectTemplateRole).filter(
        ProjectTemplateRole.template_id.in_(
            db.query(ProjectTemplate.id).filter(
                ProjectTemplate.type_id == project_type.id
            )
        )
    ).delete(synchronize_session=False)
    db.query(ProjectTemplate).filter(
        ProjectTemplate.type_id == project_type.id
    ).delete(synchronize_session=False)
    db.delete(project_type)
    db.flush()


def list_templates(
    db: Session,
    *,
    company_id: str,
    type_id: Optional[str] = None,
    include_inactive: bool = False,
) -> List[ProjectTemplate]:
    query = db.query(ProjectTemplate).filter(ProjectTemplate.company_id == company_id)
    if type_id:
        query = query.filter(ProjectTemplate.type_id == type_id)
    if not include_inactive:
        query = query.filter(ProjectTemplate.is_active.is_(True))
    return query.order_by(ProjectTemplate.name.asc()).all()


def serialize_templates(
    db: Session, templates: List[ProjectTemplate]
) -> List[Dict[str, Any]]:
    if not templates:
        return []
    template_ids = [t.id for t in templates]
    roles: Dict[str, List[ProjectTemplateRole]] = {}
    for role in (
        db.query(ProjectTemplateRole)
        .filter(ProjectTemplateRole.template_id.in_(template_ids))
        .order_by(ProjectTemplateRole.sort_order.asc(), ProjectTemplateRole.name.asc())
        .all()
    ):
        roles.setdefault(role.template_id, []).append(role)

    type_names = dict(
        db.query(ProjectType.id, ProjectType.name)
        .filter(ProjectType.id.in_({t.type_id for t in templates}))
        .all()
    )

    # A template with its own statuses has forked the graph; the admin screen shows
    # that so nobody wonders why editing the default changed nothing here.
    from app.models.status import Status

    forked = {
        row[0]
        for row in db.query(Status.scope_id)
        .filter(Status.entity_type == "project", Status.scope_id.in_(template_ids))
        .distinct()
        .all()
    }

    return [
        {
            "id": t.id,
            "type_id": t.type_id,
            "type_name": type_names.get(t.type_id),
            "name": t.name,
            "description": t.description,
            "is_active": t.is_active,
            "roles": [
                {
                    "id": r.id,
                    "name": r.name,
                    "sort_order": r.sort_order,
                    "is_active": r.is_active,
                }
                for r in roles.get(t.id, [])
            ],
            "has_forked_status_graph": t.id in forked,
        }
        for t in templates
    ]


def create_template(
    db: Session, *, company_id: str, payload: Dict[str, Any]
) -> ProjectTemplate:
    name = (payload.get("name") or "").strip()
    if not name:
        raise AppException(
            status_code=422,
            message="A template name is required.",
            code="project_template_name_required",
        )
    get_type_or_404(db, payload.get("type_id"))
    template = ProjectTemplate(
        company_id=company_id,
        type_id=payload["type_id"],
        name=name,
        description=payload.get("description"),
        is_active=payload.get("is_active", True),
    )
    db.add(template)
    db.flush()
    set_template_roles(
        db, template, payload.get("role_names") or list(DEFAULT_TEMPLATE_ROLES)
    )
    return template


def get_template_or_404(db: Session, template_id: str) -> ProjectTemplate:
    row = db.query(ProjectTemplate).filter(ProjectTemplate.id == template_id).first()
    if row is None:
        raise AppException(
            status_code=404,
            message="Project template not found.",
            code="project_template_not_found",
        )
    return row


def set_template_roles(
    db: Session, template: ProjectTemplate, role_names: List[str]
) -> None:
    """Reconcile by NAME, keeping existing rows.

    Delete-and-recreate would break every stakeholder pointing at a role (the FK is
    RESTRICT), so a role that survives the edit keeps its id.
    """
    wanted: List[str] = []
    for raw in role_names or []:
        cleaned = (raw or "").strip()
        if cleaned and cleaned.lower() not in {w.lower() for w in wanted}:
            wanted.append(cleaned)

    existing = (
        db.query(ProjectTemplateRole)
        .filter(ProjectTemplateRole.template_id == template.id)
        .all()
    )
    by_name = {r.name.lower(): r for r in existing}
    wanted_lower = {w.lower() for w in wanted}

    for index, name in enumerate(wanted):
        row = by_name.get(name.lower())
        if row is None:
            db.add(
                ProjectTemplateRole(
                    company_id=template.company_id,
                    template_id=template.id,
                    name=name,
                    sort_order=index,
                )
            )
        else:
            row.sort_order = index
            row.is_active = True

    for name_lower, row in by_name.items():
        if name_lower in wanted_lower:
            continue
        in_use = (
            db.query(func.count(ProjectStakeholder.id))
            .filter(ProjectStakeholder.role_id == row.id)
            .scalar()
        )
        # A role someone is already typed under is deactivated, not removed: the
        # historical record of who played what part must survive a config change.
        if in_use:
            row.is_active = False
        else:
            db.delete(row)
    db.flush()


def update_template(
    db: Session, template: ProjectTemplate, payload: Dict[str, Any]
) -> ProjectTemplate:
    for field in ("name", "description", "is_active"):
        if field in payload and payload[field] is not None:
            setattr(template, field, payload[field])
    if payload.get("role_names") is not None:
        set_template_roles(db, template, payload["role_names"])
    db.flush()
    return template


def delete_template(db: Session, template: ProjectTemplate) -> None:
    in_use = (
        db.query(func.count(Project.id))
        .filter(Project.template_id == template.id)
        .scalar()
    )
    if in_use:
        raise AppException(
            status_code=409,
            message=(
                f'"{template.name}" is used by {in_use} project(s). Deactivate it '
                "instead of deleting."
            ),
            code="project_template_in_use",
        )
    db.query(ProjectTemplateRole).filter(
        ProjectTemplateRole.template_id == template.id
    ).delete(synchronize_session=False)
    db.delete(template)
    db.flush()


# -------------------------------------------------------------- stakeholders


def list_stakeholders(db: Session, project_id: str) -> List[ProjectStakeholder]:
    return (
        db.query(ProjectStakeholder)
        .filter(ProjectStakeholder.project_id == project_id)
        .order_by(
            ProjectStakeholder.is_primary.desc(), ProjectStakeholder.person_name.asc()
        )
        .all()
    )


def serialize_stakeholders(
    db: Session, stakeholders: List[ProjectStakeholder]
) -> List[Dict[str, Any]]:
    if not stakeholders:
        return []
    role_names = dict(
        db.query(ProjectTemplateRole.id, ProjectTemplateRole.name)
        .filter(
            ProjectTemplateRole.id.in_(
                {s.role_id for s in stakeholders if s.role_id}
            )
        )
        .all()
    )
    party_names = dict(
        db.query(ProjectParty.id, ProjectParty.name)
        .filter(ProjectParty.id.in_({s.party_id for s in stakeholders if s.party_id}))
        .all()
    )
    return [
        {
            "id": s.id,
            "project_id": s.project_id,
            "person_name": s.person_name,
            "role_id": s.role_id,
            "role_name": role_names.get(s.role_id),
            "party_id": s.party_id,
            "party_name": party_names.get(s.party_id),
            "job_title": s.job_title,
            "phone": s.phone,
            "email": s.email,
            "influence": s.influence,
            "is_primary": s.is_primary,
            "notes": s.notes,
        }
        for s in stakeholders
    ]


def _assert_influence(influence: Optional[str]) -> None:
    if influence and influence not in INFLUENCE_LEVELS:
        raise AppException(
            status_code=422,
            message="Influence must be high, medium or low.",
            code="project_stakeholder_influence_invalid",
        )


def _clear_other_primaries(db: Session, project_id: str, keep_id: str) -> None:
    db.query(ProjectStakeholder).filter(
        ProjectStakeholder.project_id == project_id,
        ProjectStakeholder.id != keep_id,
        ProjectStakeholder.is_primary.is_(True),
    ).update({ProjectStakeholder.is_primary: False}, synchronize_session=False)


def add_stakeholder(
    db: Session, *, project: Project, payload: Dict[str, Any]
) -> ProjectStakeholder:
    person_name = (payload.get("person_name") or "").strip()
    if not person_name:
        raise AppException(
            status_code=422,
            message="A stakeholder needs a name.",
            code="project_stakeholder_name_required",
        )
    _assert_influence(payload.get("influence"))

    role_id = payload.get("role_id")
    if role_id:
        role = (
            db.query(ProjectTemplateRole)
            .filter(ProjectTemplateRole.id == role_id)
            .first()
        )
        if role is None:
            raise AppException(
                status_code=422,
                message="That stakeholder role does not exist.",
                code="project_stakeholder_role_invalid",
            )
        # A role from a different template would silently give this project a role
        # its own template does not offer.
        if project.template_id and role.template_id != project.template_id:
            raise AppException(
                status_code=422,
                message=(
                    "That role belongs to a different project template. Pick a role "
                    "from this project's template."
                ),
                code="project_stakeholder_role_mismatch",
            )

    stakeholder = ProjectStakeholder(
        company_id=project.company_id,
        project_id=project.id,
        person_name=person_name,
        role_id=role_id,
        party_id=payload.get("party_id"),
        job_title=payload.get("job_title"),
        phone=payload.get("phone"),
        email=payload.get("email"),
        influence=payload.get("influence"),
        is_primary=bool(payload.get("is_primary", False)),
        notes=payload.get("notes"),
    )
    db.add(stakeholder)
    db.flush()
    if stakeholder.is_primary:
        _clear_other_primaries(db, project.id, stakeholder.id)
    return stakeholder


def get_stakeholder_or_404(
    db: Session, project_id: str, stakeholder_id: str
) -> ProjectStakeholder:
    row = (
        db.query(ProjectStakeholder)
        .filter(
            ProjectStakeholder.id == stakeholder_id,
            ProjectStakeholder.project_id == project_id,
        )
        .first()
    )
    if row is None:
        raise AppException(
            status_code=404,
            message="Stakeholder not found on this project.",
            code="project_stakeholder_not_found",
        )
    return row


def update_stakeholder(
    db: Session, stakeholder: ProjectStakeholder, payload: Dict[str, Any]
) -> ProjectStakeholder:
    if "influence" in payload:
        _assert_influence(payload.get("influence"))
    for field in (
        "person_name",
        "role_id",
        "party_id",
        "job_title",
        "phone",
        "email",
        "influence",
        "is_primary",
        "notes",
    ):
        if field in payload:
            setattr(stakeholder, field, payload[field])
    db.flush()
    if stakeholder.is_primary:
        _clear_other_primaries(db, stakeholder.project_id, stakeholder.id)
    return stakeholder


def remove_stakeholder(db: Session, stakeholder: ProjectStakeholder) -> None:
    db.delete(stakeholder)
    db.flush()
