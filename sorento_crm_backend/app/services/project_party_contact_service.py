"""PS-REGISTRATION-V3: party contacts, party links, lead source, the project's parties read and the
WhatsApp phone fill.

Card: documentation/plans/projects/CARD-ps-registration-v3-02nov.md (rules 3-13).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models.projects import (
    LEAD_SOURCE_SET_KEY,
    LEAD_SOURCES,
    PARTY_LINK_ROLES,
    PARTY_LINK_SINGLE_ROLES,
    Project,
    ProjectParty,
    ProjectPartyContact,
    ProjectPartyLink,
    ProjectSalesProfile,
    ProjectStakeholder,
)
from app.services.error_handler import AppException

# ------------------------------------------------------------------ lead source (rule 8, Q4)


def lead_source_values(db: Session) -> tuple:
    """The active values of the editable lookup set, or the seed where the set was never made."""
    from app.models.lookup import LookupOption, LookupSet

    set_id = (
        db.query(LookupSet.id)
        .filter(LookupSet.set_key == LEAD_SOURCE_SET_KEY, LookupSet.tenant_id.is_(None))
        .scalar()
    )
    if set_id is None:
        return LEAD_SOURCES
    return tuple(
        value
        for (value,) in db.query(LookupOption.value)
        .filter(LookupOption.set_id == set_id, LookupOption.is_active.is_(True))
        .all()
    )


def is_lead_source(db: Session, value: Optional[str]) -> bool:
    return bool(value) and value in lead_source_values(db)


def assert_lead_source(db: Session, value: Optional[str], *, required: bool) -> None:
    if not value:
        if required:
            raise AppException(
                status_code=422,
                message="Pick where this project came from (lead source).",
                code="project_lead_source_required",
            )
        return
    if not is_lead_source(db, value):
        raise AppException(
            status_code=422,
            message="That lead source is not on the list. Pick one from the list.",
            code="project_lead_source_invalid",
        )


def require_lead_source_on_profile(db: Session, project: Project) -> None:
    profile = db.get(ProjectSalesProfile, project.id)
    assert_lead_source(db, getattr(profile, "lead_source", None), required=True)


# ------------------------------------------------------------------ party contacts (rule 4)


def _clean(value: Any) -> Optional[str]:
    text = " ".join(str(value).split()) if value is not None else ""
    return text or None


def list_contacts(db: Session, party: ProjectParty, *, include_inactive: bool = False) -> List[ProjectPartyContact]:
    query = db.query(ProjectPartyContact).filter(ProjectPartyContact.party_id == party.id)
    if not include_inactive:
        query = query.filter(ProjectPartyContact.is_active.is_(True))
    return query.order_by(ProjectPartyContact.name.asc()).all()


def serialize_contact(row: ProjectPartyContact) -> Dict[str, Any]:
    return {
        "id": row.id,
        "party_id": row.party_id,
        "name": row.name,
        "job_title": row.job_title,
        "phone": row.phone,
        "email": row.email,
        "is_active": row.is_active,
    }


def create_contact(db: Session, party: ProjectParty, payload: Dict[str, Any]) -> ProjectPartyContact:
    name = _clean(payload.get("name"))
    if not name:
        raise AppException(
            status_code=422, message="A contact needs a name.", code="project_party_contact_name_required"
        )
    row = ProjectPartyContact(
        company_id=party.company_id,
        party_id=party.id,
        name=name,
        job_title=_clean(payload.get("job_title")),
        phone=_clean(payload.get("phone")),
        email=_clean(payload.get("email")),
        is_active=payload.get("is_active", True) is not False,
    )
    db.add(row)
    db.flush()
    return row


def get_contact_or_404(db: Session, party: ProjectParty, contact_id: str) -> ProjectPartyContact:
    row = (
        db.query(ProjectPartyContact)
        .filter(ProjectPartyContact.id == contact_id, ProjectPartyContact.party_id == party.id)
        .first()
    )
    if row is None:
        raise AppException(status_code=404, message="Contact not found.", code="project_party_contact_not_found")
    return row


def update_contact(db: Session, row: ProjectPartyContact, payload: Dict[str, Any]) -> ProjectPartyContact:
    if "name" in payload:
        name = _clean(payload.get("name"))
        if not name:
            raise AppException(
                status_code=422, message="A contact needs a name.", code="project_party_contact_name_required"
            )
        row.name = name
    for field in ("job_title", "phone", "email"):
        if field in payload:
            setattr(row, field, _clean(payload.get(field)))
    if "is_active" in payload and payload["is_active"] is not None:
        row.is_active = bool(payload["is_active"])
    db.flush()
    return row


def delete_contact(db: Session, row: ProjectPartyContact) -> None:
    """Hard delete. Stakeholders copied from it keep their copy (FK SET NULL)."""
    db.delete(row)
    db.flush()


# ------------------------------------------------------------------ party links (rule 3, Q5)


def _company_party(db: Session, company_id: str, party_id: Any) -> Optional[ProjectParty]:
    from uuid import UUID

    try:
        UUID(str(party_id))
    except (TypeError, ValueError):
        return None
    return (
        db.query(ProjectParty)
        .filter(ProjectParty.id == str(party_id), ProjectParty.company_id == company_id)
        .first()
    )


def set_party_links(db: Session, project: Project, links: Iterable[Dict[str, Any]]) -> None:
    """Replace the project's links with ``links``. Each party must be this company's and of the
    role's type; a repeat is one link."""
    wanted: Dict[tuple, None] = {}
    for link in links or []:
        role = (link or {}).get("role")
        party_id = (link or {}).get("party_id")
        if role not in PARTY_LINK_ROLES:
            raise AppException(
                status_code=422,
                message="That party role is not one a project links.",
                code="project_party_role_invalid",
            )
        party = _company_party(db, str(project.company_id), party_id)
        if party is None:
            raise AppException(
                status_code=422,
                message="Pick the parties, type and template from this company.",
                code="project_ref_invalid",
            )
        if party.party_type != role:
            raise AppException(
                status_code=422,
                message=f'"{party.name}" is not a {role.replace("_", " ")}.',
                code="project_party_role_mismatch",
            )
        wanted[(role, party.id)] = None
    for role in PARTY_LINK_SINGLE_ROLES:
        if sum(1 for r, _p in wanted if r == role) > 1:
            raise AppException(
                status_code=422,
                message=f"A project has one {role.replace('_', ' ')}.",
                code="project_party_role_single",
            )
    db.query(ProjectPartyLink).filter(ProjectPartyLink.project_id == project.id).delete(
        synchronize_session=False
    )
    for role, party_id in wanted:
        db.add(ProjectPartyLink(project_id=project.id, role=role, party_id=party_id))
    db.flush()


def party_links_for(db: Session, project_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """``{project_id: [{role, party_id, name}]}`` for a page of projects, one query."""
    out: Dict[str, List[Dict[str, Any]]] = {pid: [] for pid in project_ids}
    if not project_ids:
        return out
    rows = (
        db.query(ProjectPartyLink.project_id, ProjectPartyLink.role, ProjectParty.id, ProjectParty.name)
        .join(ProjectParty, ProjectParty.id == ProjectPartyLink.party_id)
        .filter(ProjectPartyLink.project_id.in_(project_ids))
        .order_by(ProjectPartyLink.role.asc(), ProjectParty.name.asc())
        .all()
    )
    for project_id, role, party_id, name in rows:
        out.setdefault(project_id, []).append({"role": role, "party_id": party_id, "name": name})
    return out


# ------------------------------------------------------------------ the project's parties


def _single_role_parties(db: Session, project: Project) -> List[tuple]:
    """``(role, party_id)`` for the developer, architect and main contractor columns."""
    profile = db.get(ProjectSalesProfile, project.id)
    pairs = [("developer", project.developer_party_id)]
    if profile is not None:
        pairs += [
            ("architect", profile.architect_party_id),
            ("main_contractor", profile.main_contractor_party_id),
        ]
    return [(role, pid) for role, pid in pairs if pid]


def project_party_roles(db: Session, project: Project) -> List[tuple]:
    """Every ``(role, party_id)`` on the project, single columns first, in a stable order."""
    pairs = _single_role_parties(db, project)
    pairs += [
        (row.role, row.party_id)
        for row in db.query(ProjectPartyLink)
        .filter(ProjectPartyLink.project_id == project.id)
        .order_by(ProjectPartyLink.role.asc())
        .all()
    ]
    return pairs


def _party_ids_on(db: Session, project: Project) -> set:
    return {pid for _role, pid in project_party_roles(db, project)}


# ------------------------------------------------------------------ contacts at registration (rules 5-7)


def add_registered_contacts(db: Session, project: Project, contact_ids: Iterable[str]) -> None:
    """Copy each picked contact into a stakeholder row, once. A contact whose party is not on the
    project is refused."""
    ids = list(dict.fromkeys(str(c) for c in (contact_ids or []) if c))
    if not ids:
        return
    on_project = _party_ids_on(db, project)
    rows = (
        db.query(ProjectPartyContact)
        .filter(
            ProjectPartyContact.id.in_(ids),
            ProjectPartyContact.company_id == project.company_id,
        )
        .all()
    )
    found = {row.id: row for row in rows}
    for contact_id in ids:
        row = found.get(contact_id)
        if row is None or row.party_id not in on_project:
            raise AppException(
                status_code=422,
                message="Pick contacts of the parties on this project.",
                code="project_contact_not_on_party",
            )
    already = {
        cid
        for (cid,) in db.query(ProjectStakeholder.party_contact_id)
        .filter(ProjectStakeholder.project_id == project.id, ProjectStakeholder.party_contact_id.isnot(None))
        .all()
    }
    for contact_id in ids:
        if contact_id in already:
            continue
        row = found[contact_id]
        db.add(
            ProjectStakeholder(
                company_id=project.company_id,
                project_id=project.id,
                party_id=row.party_id,
                party_contact_id=row.id,
                person_name=row.name,
                job_title=row.job_title,
                phone=row.phone,
                email=row.email,
            )
        )
    db.flush()


def apply_registration_extras(db: Session, project: Project, payload: Dict[str, Any]) -> None:
    """The register body's party links, then its picked contacts (which need the links)."""
    if "party_links" in payload and payload["party_links"] is not None:
        set_party_links(db, project, payload["party_links"])
    add_registered_contacts(db, project, payload.get("contact_ids") or [])


# ------------------------------------------------------------------ parties read (rule 10)


def list_project_parties(db: Session, project: Project) -> List[Dict[str, Any]]:
    """One row per (role, party): the party's own phone and the project's people at that party
    (its stakeholders carrying that party)."""
    pairs = project_party_roles(db, project)
    party_ids = {pid for _role, pid in pairs}
    parties = (
        {p.id: p for p in db.query(ProjectParty).filter(ProjectParty.id.in_(party_ids)).all()}
        if party_ids
        else {}
    )
    people: Dict[str, List[Dict[str, Any]]] = {}
    if party_ids:
        for s in (
            db.query(ProjectStakeholder)
            .filter(ProjectStakeholder.project_id == project.id, ProjectStakeholder.party_id.in_(party_ids))
            .order_by(ProjectStakeholder.person_name.asc())
            .all()
        ):
            people.setdefault(s.party_id, []).append(
                {
                    "stakeholder_id": s.id,
                    "party_contact_id": s.party_contact_id,
                    "name": s.person_name,
                    "job_title": s.job_title,
                    "phone": s.phone,
                    "email": s.email,
                }
            )
    out = []
    for role, party_id in pairs:
        party = parties.get(party_id)
        if party is None:
            continue
        out.append(
            {
                "party_id": party.id,
                "party_type": party.party_type,
                "role": role,
                "name": party.name,
                "phone": party.phone,
                "contacts": people.get(party.id, []),
            }
        )
    return out


# ------------------------------------------------------------------ phone fill (rules 11-13)


def fill_party_phone(
    db: Session,
    project: Project,
    *,
    party_id: str,
    phone: Optional[str],
    stakeholder_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Save a number typed at send time: to the stakeholder and its party contact when a person
    was picked, else to the party's own line. Fills an EMPTY number only."""
    number = _clean(phone)
    if not number:
        raise AppException(status_code=422, message="Type the number first.", code="project_party_phone_required")
    if len(number) > 50:
        raise AppException(status_code=422, message="That number is too long.", code="project_party_phone_invalid")
    if str(party_id) not in {str(p) for p in _party_ids_on(db, project)}:
        raise AppException(
            status_code=404, message="That party is not on this project.", code="project_party_not_on_project"
        )
    on_file = AppException(
        status_code=409,
        message="A number is already on file. Change it on the party instead.",
        code="project_party_phone_on_file",
    )
    if stakeholder_id:
        stake = (
            db.query(ProjectStakeholder)
            .filter(
                ProjectStakeholder.id == str(stakeholder_id),
                ProjectStakeholder.project_id == project.id,
                ProjectStakeholder.party_id == str(party_id),
            )
            .first()
        )
        if stake is None:
            raise AppException(
                status_code=404, message="That person is not on this project.", code="project_stakeholder_not_found"
            )
        if _clean(stake.phone):
            raise on_file
        stake.phone = number
        if stake.party_contact_id:
            contact = db.get(ProjectPartyContact, stake.party_contact_id)
            if contact is not None and not _clean(contact.phone):
                contact.phone = number
        db.flush()
        return {"party_id": str(party_id), "stakeholder_id": stake.id, "phone": number}
    party = db.get(ProjectParty, str(party_id))
    if _clean(party.phone):
        raise on_file
    party.phone = number
    db.flush()
    return {"party_id": party.id, "stakeholder_id": None, "phone": number}
