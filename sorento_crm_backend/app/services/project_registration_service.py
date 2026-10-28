"""Project registration from the portal (PROJECT-REG-PORTAL).

A portal registration IS a `projects.projects` row (owner ruling 25 Oct 17:50, PLAN R1):
`approval_state` draft / pending / rejected / approved, no code until Approve, and the
legacy-only fields the sales agent typed on its `projects.sales_profile`. The submission id
the portal sees is the project id. Three parts, because they share that row and its rules:

- the portal part (`portal_*`): the contact's own draft, edit, submit, delete and read, which
  `PortalService` delegates to for the `project_registration` kind (D1);
- the decision (`approve`, `reject`) the CRM takes on the project itself (R9, R10);
- the possible-duplicates reader (`find_possible_duplicates`, D8), computed at read time over
  APPROVED projects only, never stored.

Plan: documentation/plans/projects/PLAN-project-registration-portal-25oct.md.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.projects import (
    APPROVAL_APPROVED,
    APPROVAL_DRAFT,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    OUTCOME_OPEN,
    Project,
    ProjectParty,
    ProjectSalesProfile,
    ProjectType,
)
from app.services import submission_status
from app.services.error_handler import AppException, handle_not_found

logger = logging.getLogger(__name__)

KIND = "project_registration"
APPROVE_PERMISSION = "projects.registrations.approve"

#: The eleven contact-written fields (D3), in form order. `title` lives on the project, the
#: rest on its sales profile.
FIELD_KEYS = (
    "title",
    "distributor_name",
    "customer_id",
    "customer_name",
    "type_of_building",
    "state",
    "mukim",
    "your_ref",
    "developer_name",
    "main_contractor_name",
    "architect_name",
)
PROFILE_FIELD_KEYS = tuple(k for k in FIELD_KEYS if k != "title")

#: Cosine at or above which the meaning signal names a project (D8, calibrated in Phase 2).
REGISTRATION_SEMANTIC_THRESHOLD = 0.80
DUPLICATE_LIMIT = 5

#: The detail fields a CRM salesperson's draft or submission may carry; they land on the
#: project or its sales profile through `project_service.apply_sales_details`.
_CRM_DETAIL_KEYS = (
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
    "type_id",
    "template_id",
    "admin_ref",
)

#: Required on submit (UAC A8), in form order.
REQUIRED_ON_SUBMIT = ("title", "state", "developer_name")

#: The title is the one free-text field that feeds a regex and an embedding, so it is bounded
#: like the rest (finding B1); 2000 characters is far past any real project description.
TITLE_MAX_LEN = 2000
#: The embedding call from a registration read must never hold the queue for long.
REGISTRATION_EMBED_TIMEOUT = 3
EMBED_CACHE_SIZE = 512

_MAX_LEN = {
    "title": TITLE_MAX_LEN,
    "distributor_name": 255,
    "customer_name": 255,
    "type_of_building": 255,
    "state": 100,
    "mukim": 255,
    "your_ref": 255,
    "developer_name": 255,
    "main_contractor_name": 255,
    "architect_name": 255,
}


def _now() -> datetime:
    return datetime.utcnow()


def _clean(value: Any) -> Optional[str]:
    text = " ".join(str(value).split()) if value is not None else ""
    return text or None


def _norm(value: Optional[str]) -> str:
    return " ".join((value or "").split()).casefold()


# ------------------------------------------------------------------ possible duplicates (D8)

def canonical_text(title: str, developer_name: Optional[str], state: Optional[str], mukim: Optional[str]) -> str:
    """What is embedded for a registration or a project: `title | developer | state, mukim`."""
    place = ", ".join(p for p in (_clean(state), _clean(mukim)) if p)
    return " | ".join([_clean(title) or "", _clean(developer_name) or "", place])


_EMBED_CACHE: "OrderedDict[str, List[float]]" = OrderedDict()
_EMBED_LOCK = threading.Lock()
#: After a failed embedding call the provider is treated as down for a moment, so a page of
#: rows pays the timeout once, not once per row.
EMBED_BACKOFF_SECONDS = 30
_EMBED_DOWN_UNTIL = 0.0


def clear_embedding_cache() -> None:
    global _EMBED_DOWN_UNTIL
    with _EMBED_LOCK:
        _EMBED_CACHE.clear()
        _EMBED_DOWN_UNTIL = 0.0


def embed_texts(texts: List[str], *, timeout: int = REGISTRATION_EMBED_TIMEOUT) -> List[Optional[List[float]]]:
    """Vectors for `texts`, one network call for everything not seen before.

    Cached by the text itself (LRU, `EMBED_CACHE_SIZE`): a registration is read again and
    again while it waits in the queue, and its text does not change between reads.
    """
    with _EMBED_LOCK:
        missing = list(dict.fromkeys(t for t in texts if t not in _EMBED_CACHE))
    if missing:
        global _EMBED_DOWN_UNTIL
        from app.services import embedding_worker

        if time.monotonic() < _EMBED_DOWN_UNTIL:
            raise RuntimeError("embedding provider recently failed")
        try:
            vectors = embedding_worker._embed_text_chunks(missing, timeout=timeout)
        except Exception:
            with _EMBED_LOCK:
                _EMBED_DOWN_UNTIL = time.monotonic() + EMBED_BACKOFF_SECONDS
            raise
        with _EMBED_LOCK:
            for text, vector in zip(missing, vectors):
                _EMBED_CACHE[text] = vector
            while len(_EMBED_CACHE) > EMBED_CACHE_SIZE:
                _EMBED_CACHE.popitem(last=False)
    with _EMBED_LOCK:
        out = []
        for text in texts:
            vector = _EMBED_CACHE.get(text)
            if vector is not None:
                _EMBED_CACHE.move_to_end(text)
            out.append(vector)
        return out


def embed_text(text: str) -> List[float]:
    return embed_texts([text])[0]


def semantic_matches(db: Session, *, company_id: str, text: str, top_k: int = 10) -> List[Tuple[str, float]]:
    """`(project_id, cosine)` for the stored project embeddings closest to `text`.

    Any failure (no key, timeout, no pgvector) yields `[]`: the meaning signal is an extra,
    never a reason a registration cannot be read.
    """
    try:
        vector = embed_text(text)
        from app.services.embedding_service import EmbeddingReadService

        with db.begin_nested():
            hits = EmbeddingReadService(db).search_current(vector, top_k=top_k, source_type="project")
        out: List[Tuple[str, float]] = []
        for chunk, document, similarity in hits:
            owner = (document.metadata_json or {}).get("company_id")
            if owner and str(owner) != str(company_id):
                continue
            out.append((str(chunk.source_id), float(similarity)))
        return out
    except Exception as exc:  # noqa: BLE001
        logger.info("registration semantic match skipped: %s", exc)
        return []


def find_possible_duplicates(
    db: Session,
    *,
    company_id: str,
    title: str,
    developer_name: Optional[str] = None,
    state: Optional[str] = None,
    mukim: Optional[str] = None,
    limit: int = DUPLICATE_LIMIT,
    use_meaning: bool = True,
) -> List[Dict[str, str]]:
    """Existing projects of this company the registration may repeat, named by MEANING ONLY
    (owner ruling, audit round 3): the stored project embeddings at or above
    `REGISTRATION_SEMANTIC_THRESHOLD`, strongest first. No spelling rule, no lot rule, no
    phase filter: the model decides, and a person reads the list. Never blocks."""
    clean_title = _clean(title)
    if not clean_title or not use_meaning:
        return []
    meaning = sorted(
        (
            (pid, cosine)
            for pid, cosine in semantic_matches(
                db,
                company_id=company_id,
                text=canonical_text(clean_title, developer_name, state, mukim),
            )
            if cosine >= REGISTRATION_SEMANTIC_THRESHOLD
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )
    if not meaning:
        return []
    from app.services.project_service import approved_projects

    # Only a PROJECT is a candidate: a registration still waiting (or refused, or a draft)
    # is never named, not even the one being read (R4).
    by_id = {
        p.id: p
        for p in approved_projects(
            db.query(Project).filter(
                Project.company_id == company_id,
                Project.id.in_([pid for pid, _ in meaning if _is_uuid(pid)]),
            )
        ).all()
    }
    out: List[Dict[str, str]] = []
    seen: set = set()
    for pid, _cosine in meaning:
        project = by_id.get(pid)
        if project is None or project.id in seen:
            continue
        seen.add(project.id)
        out.append({"project_id": project.id, "project_code": project.project_code, "title": project.title})
        if len(out) >= max(1, limit):
            break
    return out




def duplicates_for_project(
    db: Session, project: Project, profile: Optional[ProjectSalesProfile] = None
) -> List[Dict[str, str]]:
    """The possible duplicates of a portal registration. Only one still waiting for a decision
    is checked: that is when it matters. The CRM detail and the portal detail embed the SAME
    text, so the second read of a row is a cache hit wherever it comes from."""
    if not _awaiting_decision(project) or not _clean(project.title):
        return []
    if profile is None:
        profile = db.get(ProjectSalesProfile, project.id)
    return find_possible_duplicates(
        db,
        company_id=project.company_id,
        title=project.title,
        developer_name=getattr(profile, "developer_name", None),
        state=getattr(profile, "state", None),
        mukim=getattr(profile, "mukim", None),
    )


# ------------------------------------------------------------------ shared reads


def _agent_name(agent) -> Optional[str]:
    if agent is None:
        return None
    return _clean(agent.person_label) or _clean(agent.description) or agent.sales_agent


#: Public name for the project serialiser: the agent shown by name, never only by code (D4).
agent_display_name = _agent_name


def _agent_name_for(db: Session, profile: Optional[ProjectSalesProfile]) -> Optional[str]:
    if profile is None or not profile.sales_agent_id:
        return None
    from app.models.sales_agent import SalesAgent

    return _agent_name(db.get(SalesAgent, profile.sales_agent_id))


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _is_uuid(value: Any) -> bool:
    from uuid import UUID

    try:
        UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


# ------------------------------------------------------------------ portal part


def _contact_companies(db: Session, contact_id: str) -> frozenset:
    from app.models.company import RespondContactCompany

    return frozenset(
        str(cid)
        for (cid,) in db.query(RespondContactCompany.company_id)
        .filter(RespondContactCompany.respond_contact_id == str(contact_id))
        .all()
    )


def _scope(db: Session, token):
    """The contact's own companies: a portal request carries no staff company scope."""
    return company_scope(db, _contact_companies(db, token.contact_id))


def _active_agents(db: Session, contact_id: str) -> list:
    from app.services.sales.portal_agent import agents_for_contact

    return agents_for_contact(db, contact_id)


def _require_agent(db: Session, contact_id: str):
    agents = _active_agents(db, contact_id)
    if not agents:
        raise AppException(
            status_code=403,
            message="Only a sales agent can register a project.",
            code="NOT_A_SALES_AGENT",
        )
    return agents[0]


def _own_query(db: Session, token):
    """The contact's own registrations: portal rows (an approval state) whose profile names
    this contact. A staff project is nobody's portal submission."""
    return (
        db.query(Project, ProjectSalesProfile)
        .join(ProjectSalesProfile, ProjectSalesProfile.project_id == Project.id)
        .filter(
            Project.approval_state.isnot(None),
            ProjectSalesProfile.contact_id == str(token.contact_id),
        )
    )


def _own(db: Session, token, registration_id: str) -> Tuple[Project, ProjectSalesProfile]:
    row = (
        _own_query(db, token).filter(Project.id == str(registration_id)).first()
        if _is_uuid(registration_id)
        else None
    )
    if row is None:
        raise handle_not_found("Project registration", registration_id)
    return row[0], row[1]


def _check_customer(db: Session, company_id: str, contact_id: str, raw: Any) -> Optional[str]:
    """The pick must be one of the contact's own agents' debtors, in THIS registration's
    company (not the contact's whole company set), else the same 422."""
    if raw is None or str(raw).strip() == "":
        return None
    from app.models.order import Customer

    refuse = AppException(status_code=422, message="Pick a customer from the list.")
    if not _is_uuid(raw):
        raise refuse
    agent_ids = [str(a.id) for a in _active_agents(db, contact_id)]
    with company_scope(db, frozenset({str(company_id)})):
        row = db.query(Customer).filter(Customer.id == str(raw).strip()).first()
    if row is None or not agent_ids or str(row.sales_agent_id) not in agent_ids:
        raise refuse
    return str(row.id)


def _field_label(key: str) -> str:
    return key.replace("_", " ").capitalize()


def _check_lengths(payload: Dict[str, Any]) -> None:
    """Refuse a value that is not text, or is over-long, before anything is written, naming the
    field (a number or a list used to reach the column and come back a 500)."""
    for key in FIELD_KEYS:
        value = payload.get(key)
        if value is not None and not isinstance(value, str):
            raise AppException(
                status_code=422,
                message=f"{_field_label(key)} must be text.",
                detail=key,
                code="VALIDATION_ERROR",
            )
    for key, limit in _MAX_LEN.items():
        value = payload.get(key)
        if isinstance(value, str) and len(value.strip()) > limit:
            raise AppException(
                status_code=422,
                message=f"{_field_label(key)} is too long (at most {limit} characters).",
                detail=key,
                code="VALIDATION_ERROR",
            )


def portal_debtors(db: Session, token, q: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    """The debtors the form may pick: only the contact's own agents' (the set `_check_customer`
    accepts), so the dropdown never offers a customer the save would refuse."""
    from app.api.v1.public.portal_price_tag import _resolve_company
    from app.models.order import Customer
    from app.services.debtor_type import SALES_TYPE_FOR_DEBTOR_TYPE

    agent_ids = [str(a.id) for a in _active_agents(db, token.contact_id)]
    if not agent_ids:
        return []
    with company_scope(db, frozenset({_resolve_company(db, token)})):
        query = db.query(Customer).filter(Customer.is_active.is_(True), Customer.sales_agent_id.in_(agent_ids))
        text = (q or "").strip()
        if text:
            like = f"%{text}%"
            query = query.filter(or_(Customer.customer_name.ilike(like), Customer.customer_code.ilike(like)))
        rows = query.order_by(Customer.customer_name, Customer.customer_code).limit(limit).all()
    return [
        {
            "customer_id": str(r.id),
            "debtor_name": r.customer_name,
            "customer_code": r.customer_code,
            "debtor_type": r.debtor_type,
            "sales_type": SALES_TYPE_FOR_DEBTOR_TYPE.get(r.debtor_type) if r.debtor_type else None,
        }
        for r in rows
    ]


def _cleaned(db: Session, company_id: str, contact_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """The payload's D3 values as they will be stored, every check run BEFORE anything is
    written (a refused value writes no row, not even a draft)."""
    _check_lengths(payload)
    out: Dict[str, Any] = {}
    for key in FIELD_KEYS:
        if key not in payload:
            continue
        if key == "customer_id":
            out[key] = _check_customer(db, company_id, contact_id, payload[key])
            continue
        value = payload[key]
        value = (str(value).strip() or None) if value is not None else None
        if key != "title":
            value = " ".join(value.split()) if value else None
        out[key] = value
    return out


def _apply(db: Session, project: Project, profile: ProjectSalesProfile, values: Dict[str, Any]) -> None:
    from app.services.project_clash_service import normalise_project_title

    if "title" in values:
        # The project row needs a title; a draft may not have one yet.
        project.title = values["title"] or ""
        project.normalised_title = normalise_project_title(project.title)
    for key in PROFILE_FIELD_KEYS:
        if key in values:
            setattr(profile, key, values[key])
    # A pick with no typed name shows the debtor's own name.
    if profile.customer_id and not profile.customer_name:
        from app.models.order import Customer

        profile.customer_name = (
            db.query(Customer.customer_name).filter(Customer.id == profile.customer_id).scalar()
        )


def _values(project: Project, profile: Optional[ProjectSalesProfile]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"title": project.title or None}
    for key in PROFILE_FIELD_KEYS:
        out[key] = getattr(profile, key, None) if profile is not None else None
    if out.get("customer_id"):
        out["customer_id"] = str(out["customer_id"])
    return out


def _editable(project: Project) -> bool:
    return project.approval_state in (APPROVAL_DRAFT, APPROVAL_REJECTED)


def _require_editable(project: Project) -> None:
    if not _editable(project):
        raise AppException(
            status_code=422, message="This registration is locked.", code="PROJECT_REGISTRATION_LOCKED"
        )


def _ppf(project: Project) -> Optional[str]:
    return project.project_code if project.approval_state == APPROVAL_APPROVED else None


def _portal_summary(db: Session, project: Project, profile: Optional[ProjectSalesProfile]) -> Dict[str, Any]:
    ppf = _ppf(project)
    return {
        "id": str(project.id),
        "kind": KIND,
        "title": project.title or "Project registration",
        "reference": ppf,
        "document_number": ppf,
        "status": project.approval_state,
        "approval_status": None,
        "rejection_reason": project.reject_reason,
        "is_editable": _editable(project),
        "is_draft": _editable(project),
        "created_at": _iso(project.created_at),
        "developer_name": getattr(profile, "developer_name", None),
        "state": getattr(profile, "state", None),
        "customer_name": getattr(profile, "customer_name", None),
        "ppf_no": ppf,
    }


def _portal_detail(
    db: Session, project: Project, profile: Optional[ProjectSalesProfile], *, with_duplicates: bool = True
) -> Dict[str, Any]:
    base = _portal_summary(db, project, profile)
    base.update(_values(project, profile))
    base.update(
        {
            "submitted_at": _iso(project.submitted_at),
            "sales_agent_name": _agent_name_for(db, profile),
            "reject_reason": project.reject_reason,
            # Code and title only: no project id and no holder in the portal.
            "possible_duplicates": [
                {"project_code": d["project_code"], "title": d["title"]}
                for d in duplicates_for_project(db, project, profile)
            ]
            if with_duplicates
            else [],
        }
    )
    return base


def portal_list(db: Session, token, q: Optional[str] = None) -> List[Dict[str, Any]]:
    with _scope(db, token):
        query = _own_query(db, token)
        if q and q.strip():
            like = f"%{q.strip()}%"
            query = query.filter(
                or_(
                    Project.title.ilike(like),
                    ProjectSalesProfile.developer_name.ilike(like),
                    ProjectSalesProfile.distributor_name.ilike(like),
                    ProjectSalesProfile.customer_name.ilike(like),
                    ProjectSalesProfile.state.ilike(like),
                    ProjectSalesProfile.mukim.ilike(like),
                )
            )
        rows = query.order_by(Project.created_at.desc(), Project.id).all()
        return [_portal_summary(db, project, profile) for project, profile in rows]


def portal_get(db: Session, token, registration_id: str, *, full: bool = False) -> Dict[str, Any]:
    """`full` builds the possible duplicates (the detail page). Every other caller only needs
    to know the contact owns the row, which must not cost an embedding."""
    with _scope(db, token):
        project, profile = _own(db, token, registration_id)
        return _portal_detail(db, project, profile, with_duplicates=full)


def portal_neighbours(db: Session, token, registration_id: str) -> Dict[str, Any]:
    with _scope(db, token):
        _own(db, token, registration_id)
        ids = [
            str(row[0].id)
            for row in _own_query(db, token).order_by(Project.created_at.desc(), Project.id).all()
        ]
    idx = ids.index(str(registration_id))
    return {
        "prev_id": ids[idx - 1] if idx > 0 else None,
        "next_id": ids[idx + 1] if idx + 1 < len(ids) else None,
        "position": idx + 1,
        "total": len(ids),
    }


def portal_save(
    db: Session, token, payload: Dict[str, Any], registration_id: Optional[str] = None
) -> Dict[str, Any]:
    """Save draft creates the project row with `approval_state = draft` and no code (R5)."""
    from app.api.v1.public.portal_price_tag import _resolve_company
    from app.services import portal_rate_limit

    portal_rate_limit.project_registration_write(token.contact_id)
    if registration_id is None:
        agent = _require_agent(db, token.contact_id)
        company_id = _resolve_company(db, token)
        with company_scope(db, frozenset({company_id})):
            values = _cleaned(db, company_id, token.contact_id, payload)
            project = Project(
                company_id=company_id,
                approval_state=APPROVAL_DRAFT,
                title="",
                normalised_title="",
                outcome=OUTCOME_OPEN,
            )
            db.add(project)
            db.flush()
            profile = ProjectSalesProfile(
                project_id=project.id,
                contact_id=str(token.contact_id),
                sales_agent_id=agent.id,
            )
            db.add(profile)
            _apply(db, project, profile, values)
            db.commit()
            db.refresh(project)
            db.refresh(profile)
            return _portal_detail(db, project, profile, with_duplicates=False)
    with _scope(db, token):
        project, profile = _own(db, token, registration_id)
        _require_editable(project)
        _apply(db, project, profile, _cleaned(db, project.company_id, token.contact_id, payload))
        db.commit()
        db.refresh(project)
        db.refresh(profile)
        return _portal_detail(db, project, profile, with_duplicates=False)


def _missing(values: Dict[str, Any]) -> List[str]:
    return [k for k in REQUIRED_ON_SUBMIT if not _clean(values.get(k))]


def _linked_user_id(db: Session, contact_id: Optional[str]) -> Optional[str]:
    if not contact_id:
        return None
    from app.models.user import User

    return db.query(User.id).filter(User.respond_contact_id == str(contact_id)).scalar()


def portal_submit(
    db: Session, token, registration_id: str, payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Draft (or rejected) -> pending. The owner is the contact's linked CRM user, else nobody
    until Approve (R5). No number is drawn here (C4)."""
    from app.services import portal_rate_limit

    portal_rate_limit.project_registration_write(token.contact_id)
    with _scope(db, token):
        project, profile = _own(db, token, registration_id)
        _require_editable(project)
        _require_agent(db, token.contact_id)
        _check_lengths(payload or {})
        merged = _values(project, profile)
        merged.update({k: v for k, v in (payload or {}).items() if k in FIELD_KEYS})
        missing = _missing(merged)
        if missing:
            raise AppException(
                status_code=422,
                message="Fill in the required fields before submitting.",
                detail=",".join(missing),
                code="VALIDATION_ERROR",
            )
        if payload:
            _apply(db, project, profile, _cleaned(db, project.company_id, token.contact_id, payload))
        resubmitted = project.approval_state == APPROVAL_REJECTED
        project.approval_state = submission_status.status_on_submit(
            was_rejected=resubmitted, stage=APPROVAL_PENDING
        )
        project.submitted_at = _now()
        project.reject_reason = None
        project.decided_at = None
        project.decided_by = None
        project.owner_user_id = _linked_user_id(db, token.contact_id)
        db.commit()
        db.refresh(project)
        db.refresh(profile)
        notify(db, project, "resubmitted" if resubmitted else "submitted")
        return _portal_detail(db, project, profile, with_duplicates=False)


# ------------------------------------------------------------------ CRM salesperson (J)


def require_customer(customer_id: Optional[str]) -> None:
    """A registration needs its customer (PROJECT-REGISTER-V2 A5)."""
    if not customer_id:
        raise AppException(
            status_code=422,
            message="Pick the customer before registering.",
            code="project_customer_required",
        )


def _to_pending(project: Project) -> bool:
    """Draft or rejected -> pending or resubmitted, the state change `portal_submit` makes.
    Returns True when it is a resubmission."""
    resubmitted = project.approval_state == APPROVAL_REJECTED
    project.approval_state = submission_status.status_on_submit(
        was_rejected=resubmitted, stage=APPROVAL_PENDING
    )
    project.submitted_at = _now()
    project.reject_reason = None
    project.decided_at = None
    project.decided_by = None
    return resubmitted


def crm_register(
    db: Session, *, company_id: str, user_id: str, payload: Dict[str, Any], submit: bool
) -> Project:
    """A salesperson who holds only the submit grant saves a draft (title only) or submits a
    new registration (customer required). The caller commits and, when ``submit``, notifies
    with `notify(db, project, "submitted")` AFTER the commit."""
    from app.models.user import User
    from app.services import project_service
    from app.services.project_clash_service import normalise_project_title
    from app.services.sales.portal_agent import agents_for_contact

    title = _clean(payload.get("title"))
    if not title:
        raise AppException(
            status_code=422, message="A project title is required.", code="project_title_required"
        )
    project_service.check_company_refs(db, company_id, payload)
    if submit:
        require_customer(payload.get("customer_id"))
    contact_id = db.query(User.respond_contact_id).filter(User.id == str(user_id)).scalar()
    agents = agents_for_contact(db, contact_id) if contact_id else []
    details = {k: payload[k] for k in _CRM_DETAIL_KEYS if k in payload}
    developer_party_id = payload.get("developer_party_id")
    try:
        with db.begin_nested():
            project = Project(
                company_id=company_id,
                title=title,
                normalised_title=normalise_project_title(title),
                developer_party_id=developer_party_id,
                outcome=OUTCOME_OPEN,
                approval_state=APPROVAL_DRAFT,
                owner_user_id=user_id,
                created_by=user_id,
            )
            db.add(project)
            db.flush()
            db.add(
                ProjectSalesProfile(
                    project_id=project.id,
                    contact_id=str(contact_id) if contact_id else None,
                    sales_agent_id=agents[0].id if agents else None,
                )
            )
            db.flush()
            project_service.apply_sales_details(db, project, details)
            if submit:
                _to_pending(project)
            db.flush()
    except IntegrityError as exc:
        if "uq_projects_company_developer_title" not in str(getattr(exc, "orig", exc)):
            raise
        raise _exact_duplicate(db, project, developer_party_id, title)
    return project


def crm_submit(
    db: Session, project: Project, *, user_id: str, payload: Dict[str, Any], permissions
) -> bool:
    """Submit the user's own draft or rejected registration. Returns True for a resubmission.
    Required fields are checked on what the project holds after ``payload`` is applied; a
    refusal leaves the state as it was."""
    from app.services import project_service

    if project.approval_state not in (APPROVAL_DRAFT, APPROVAL_REJECTED) or str(
        project.owner_user_id or ""
    ) != str(user_id):
        raise AppException(
            status_code=403,
            message="Only your own draft or rejected registration can be submitted.",
            code="project_not_editable",
        )
    if payload:
        project_service.update_project(
            db, project, payload, actor_user_id=user_id, permissions=permissions
        )
    profile = db.get(ProjectSalesProfile, project.id)
    require_customer(getattr(profile, "customer_id", None))
    if not _clean(project.title):
        raise AppException(
            status_code=422, message="A project title is required.", code="project_title_required"
        )
    return _to_pending(project)


def portal_delete(db: Session, token, registration_id: str) -> None:
    with _scope(db, token):
        project, _profile = _own(db, token, registration_id)
        if project.approval_state != APPROVAL_DRAFT:
            raise AppException(status_code=422, message="Only drafts can be deleted.")
        db.delete(project)
        db.commit()


# ------------------------------------------------------------------ notifications (F1, F2)


def _applicant_user_id(db: Session, project: Project) -> Optional[str]:
    """The CRM user linked to the contact who registered it: who hears the decision."""
    profile = db.get(ProjectSalesProfile, project.id)
    contact_id = getattr(profile, "contact_id", None)
    if not contact_id and project.owner_user_id:
        # A CRM-submitted registration whose salesperson has no linked portal contact:
        # the owner is the applicant (PROJECT-REGISTER-V2 J6).
        return str(project.owner_user_id)
    return _linked_user_id(db, contact_id)


def _holders(db: Session, project: Project, exclude: Iterable[Any] = ()) -> List[str]:
    from app.services.project_notify_service import approver_user_ids

    return approver_user_ids(
        db, company_id=project.company_id, exclude={str(e) for e in exclude if e}, slug=APPROVE_PERMISSION
    )


def notify(db: Session, project: Project, event: str) -> int:
    """Tell who must act (submitted) or who asked (approved, rejected). Call AFTER the move
    commits; a failure is logged per recipient and never undoes the move. Every notice links
    to the project itself: there is no registrations page any more (R11)."""
    title_text = _clean(project.title) or "A project"  # one line: a title can carry newlines and tabs
    try:
        applicant = _applicant_user_id(db, project)
        if event == "submitted":
            recipients = _holders(db, project, exclude=[applicant])
            title = f"Project registration waits for your approval: {title_text}"
        elif event == "resubmitted":
            recipients = _holders(db, project, exclude=[applicant])
            title = f"Project registration appealed, waits for your approval: {title_text}"
        else:
            from app.services.project_service import project_label

            recipients = [applicant] if applicant else []
            title = (
                f"Your project registration is approved as {project_label(project)}: {title_text}"
                if event == "approved"
                else f"Your project registration was rejected: {title_text}"
            )
        link = f"/project-sales/{project.id}"
        from app.services.notification_service import NotificationService

        service = NotificationService(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("project registration notice not sent: %s %s (%s)", event, project.id, exc)
        return 0
    sent = 0
    stamp = project.decided_at or project.submitted_at
    for user_id in {str(u) for u in recipients if u}:
        try:
            service.create_with_channel_preferences(
                user_id=user_id,
                type=f"project_registration_{event}",
                title=title,
                body=title,
                data={"project_id": str(project.id), "link": link},
                source_entity_type="project",
                source_entity_id=str(project.id),
                dedup_key=f"{project.id}:{event}:{stamp.isoformat() if stamp else ''}",
                event_type=f"project_registration_{event}",
                send_in_app=True,
                # The approvers hear in-app only; the applicant is told by email as well.
                send_email=event not in ("submitted", "resubmitted"),
                send_whatsapp=False,
                send_web_push=False,
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("project registration notice not sent to %s: %s (%s)", user_id, event, exc)
            if not db.is_active:
                db.rollback()
    return sent


# ------------------------------------------------------------------ the decision (R9, R10)


def lock_project(db: Session, project_id: str) -> Project:
    """The project row under a row lock, so two approvers cannot both read it as pending."""
    from app.services.uuid_path_param import validate_uuid_path

    validate_uuid_path(project_id, resource="Project")
    project = (
        db.query(Project)
        .filter(Project.id == str(project_id))
        .with_for_update()
        .populate_existing()
        .first()
    )
    if project is None:
        raise AppException(status_code=404, message="Project not found.", code="project_not_found")
    return project


def _awaiting_decision(project: Project) -> bool:
    """Pending, or resubmitted after a rejection (RESUBMITTED-STATUS)."""
    return submission_status.is_awaiting_review(project.approval_state, APPROVAL_PENDING)


def _not_pending() -> AppException:
    return AppException(
        status_code=409,
        message="This project is not waiting for approval.",
        code="project_registration_not_pending",
    )


_APPROVE_DETAIL_KEYS = (
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
    "admin_ref",
)


MANAGE_PERMISSION = "projects.projects.manage"


def _unprocessable(message: str, code: str) -> AppException:
    return AppException(status_code=422, message=message, code=code)


def _owner_can_own(db: Session, user_id: Optional[str], company_id: str) -> bool:
    """An active, untrashed user with access to the project's company."""
    if not user_id:
        return False
    from app.models.company import UserCompany
    from app.models.user import User, UserStatus

    return (
        db.query(User.id)
        .join(UserCompany, UserCompany.user_id == User.id)
        .filter(
            User.id == str(user_id),
            User.status == UserStatus.ACTIVE.value,
            User.is_trashed.is_(False),
            UserCompany.company_id == str(company_id),
        )
        .first()
        is not None
    )


def _resolve_owner(
    db: Session, project: Project, requested: Optional[str], actor_user_id: str, actor_slugs
) -> str:
    """Who owns the project (finding S9). The applicant or the approver need no extra grant;
    anyone else is the staff rule: only a sales manager registers a project for someone else."""
    applicant = _applicant_user_id(db, project)
    # The form may send the applicant; one who cannot own a project of this company
    # (inactive, no access) must not leave a non-manager unable to approve: same fallback as
    # sending no owner at all.
    if requested and requested == applicant and not _owner_can_own(db, applicant, project.company_id):
        requested = None
    if requested:
        if requested not in (applicant, actor_user_id) and MANAGE_PERMISSION not in actor_slugs:
            raise AppException(
                status_code=403,
                message="Only a sales manager can register a project for someone else.",
                code="project_owner_assign_forbidden",
            )
        if requested != actor_user_id and not _owner_can_own(db, requested, project.company_id):
            raise _unprocessable(
                "That salesperson cannot own a project of this company.",
                "project_registration_owner_invalid",
            )
        return requested
    return applicant if _owner_can_own(db, applicant, project.company_id) else actor_user_id


def _check_company_refs(db: Session, company_id: str, payload: Dict[str, Any]) -> None:
    """Every id the approver sends must belong to the project's company (finding S10)."""
    from app.services.project_service import check_company_refs

    check_company_refs(db, company_id, payload, code="project_registration_ref_invalid")


def _exact_duplicate(db: Session, project: Project, developer_party_id: str, title: str) -> AppException:
    from app.services.project_clash_service import normalise_project_title
    from app.services.project_service import approved_projects, project_label

    existing = approved_projects(
        db.query(Project).filter(
            Project.company_id == project.company_id,
            Project.id != project.id,
            Project.developer_party_id == developer_party_id,
            Project.normalised_title == normalise_project_title(title),
        )
    ).first()
    name = project_label(existing) if existing else "an existing project"
    return AppException(
        status_code=409,
        message=f"{name} already has this developer and title. Change the title, e.g. add the phase.",
        code="project_registration_exact_duplicate",
        details={
            "existing_project": {
                "project_id": str(existing.id),
                "project_code": existing.project_code,
                "title": existing.title,
            }
        }
        if existing
        else None,
    )


def approve(
    db: Session,
    project: Project,
    payload: Dict[str, Any],
    *,
    actor_user_id: str,
    actor_slugs=frozenset(),
) -> Project:
    """Make the pending registration a project (R9): its PPF code, its first funnel rung, its
    template checklist, `approval_state = approved`.

    A possible duplicate never blocks (D7); only the exact developer + title repeat does, and
    that is answered 409 naming the project. Everything sits in a SAVEPOINT so the refused
    attempt neither burns a number nor leaves the row half-approved.
    """
    from app.services import project_service
    from app.services.project_clash_service import normalise_project_title

    if not _awaiting_decision(project):
        raise _not_pending()
    developer_party_id = payload.get("developer_party_id") or project.developer_party_id
    if not developer_party_id:
        raise AppException(
            status_code=422,
            message="Pick the developer before approving.",
            code="project_registration_developer_required",
        )
    title = _clean(payload.get("title")) or _clean(project.title)
    if not title:
        raise AppException(
            status_code=422, message="A project title is required.", code="project_title_required"
        )
    details = {k: payload[k] for k in _APPROVE_DETAIL_KEYS if k in payload}
    _check_company_refs(db, str(project.company_id), payload)
    owner = _resolve_owner(db, project, payload.get("owner_user_id"), actor_user_id, actor_slugs)
    try:
        with db.begin_nested():
            project.title = title
            project.normalised_title = normalise_project_title(title)
            project.developer_party_id = developer_party_id
            for key in ("type_id", "template_id"):
                if payload.get(key):
                    setattr(project, key, payload[key])
            project.owner_user_id = owner
            project.approval_state = APPROVAL_APPROVED
            project.reject_reason = None
            project.decided_at = _now()
            project.decided_by = actor_user_id
            if not project.created_by:
                project.created_by = actor_user_id
            project_service.start_project(
                db,
                project,
                actor_user_id=actor_user_id,
                details=details,
            )
    except IntegrityError as exc:
        if "uq_projects_company_developer_title" not in str(getattr(exc, "orig", exc)):
            raise
        raise _exact_duplicate(db, project, developer_party_id, title)
    return project


def reject(db: Session, project: Project, reason: Optional[str], *, actor_user_id: str) -> Project:
    """Pending -> rejected with the reason (R10). The project stays visible until the portal
    resubmits it; no number is drawn."""
    text = (reason or "").strip()
    if not text:
        raise AppException(
            status_code=422, message="Give the reason for rejecting.", code="project_registration_reason_required"
        )
    if not _awaiting_decision(project):
        raise _not_pending()
    project.approval_state = APPROVAL_REJECTED
    project.reject_reason = text
    project.decided_at = _now()
    project.decided_by = actor_user_id
    db.flush()
    return project
