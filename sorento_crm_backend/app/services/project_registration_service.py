"""Project registration from the portal (PROJECT-REG-PORTAL).

Three halves in one module, because they share one row and one set of rules:

- the portal half (`portal_*`): the contact's own draft, edit, submit, delete and read, which
  `PortalService` delegates to for the `project_registration` kind (D1);
- the CRM half (`list_rows`, `detail`, `approve`, `reject`): the queue a Project Sales Admin
  works (D5, D7);
- the possible-duplicates reader (`find_possible_duplicates`, D8), pure and computed at read
  time, never stored.

Plan: documentation/plans/projects/PLAN-project-registration-portal-25oct.md.
"""
from __future__ import annotations

import logging
import re
import threading
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.models.project_registration import (
    FIELD_KEYS,
    STATUS_APPROVED,
    STATUS_DRAFT,
    STATUS_PENDING,
    STATUS_REJECTED,
    ProjectRegistration,
)
from app.models.projects import Project, ProjectParty, ProjectSalesProfile, ProjectType
from app.services.error_handler import AppException, handle_not_found

logger = logging.getLogger(__name__)

KIND = "project_registration"
APPROVE_PERMISSION = "projects.registrations.approve"

#: Cosine at or above which the meaning signal names a project (D8, calibrated in Phase 2).
REGISTRATION_SEMANTIC_THRESHOLD = 0.80
DUPLICATE_LIMIT = 5

#: Required on submit (UAC A8), in form order.
REQUIRED_ON_SUBMIT = ("title", "state", "developer_name")

#: The title is the one free-text field that feeds a regex and an embedding, so it is bounded
#: like the rest (finding B1); 2000 characters is far past any real project description.
TITLE_MAX_LEN = 2000
MAX_LOT_NUMBERS = 20
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

_LOT = re.compile(r"(?<![A-Za-z])(?:LOT|PT)\s*(?:NO\.?\s*)?(\d+)", re.IGNORECASE)
# The name after MUKIM ends at a comma, a full stop, one of the words that open the next clause
# of a Malaysian title, or the end.
_MUKIM = re.compile(
    r"\bMUKIM\s+(.+?)(?=\s*[,.]|\s+(?:DAERAH|DISTRICT|NEGERI|UNTUK|FOR|DI)\b|$)", re.IGNORECASE
)


def parse_lot_numbers(title: Optional[str]) -> set:
    """Lot numbers in a title: `LOT 9001`, `Lot No. 9001`, `PT 9001`, `PT9001` all read 9001,
    and `LOT 09001` reads the same (leading zeros are not part of the number)."""
    return {n.lstrip("0") or "0" for n in _LOT.findall(title or "")}


def parse_mukim(title: Optional[str]) -> Optional[str]:
    """The mukim named in a title (text after MUKIM up to a comma or the end), normalised."""
    match = _MUKIM.search(title or "")
    return (_norm(match.group(1)) or None) if match else None


def canonical_text(title: str, developer_name: Optional[str], state: Optional[str], mukim: Optional[str]) -> str:
    """What is embedded for a registration or a project: `title | developer | state, mukim`."""
    place = ", ".join(p for p in (_clean(state), _clean(mukim)) if p)
    return " | ".join([_clean(title) or "", _clean(developer_name) or "", place])


_EMBED_CACHE: "OrderedDict[str, List[float]]" = OrderedDict()
_EMBED_LOCK = threading.Lock()


def clear_embedding_cache() -> None:
    with _EMBED_LOCK:
        _EMBED_CACHE.clear()


def embed_texts(texts: List[str], *, timeout: int = REGISTRATION_EMBED_TIMEOUT) -> List[Optional[List[float]]]:
    """Vectors for `texts`, one network call for everything not seen before.

    Cached by the text itself (LRU, `EMBED_CACHE_SIZE`): a registration is read again and
    again while it waits in the queue, and its text does not change between reads.
    """
    with _EMBED_LOCK:
        missing = list(dict.fromkeys(t for t in texts if t not in _EMBED_CACHE))
    if missing:
        from app.services import embedding_worker

        vectors = embedding_worker._embed_text_chunks(missing, timeout=timeout)
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


def prime_meaning(rows: List["ProjectRegistration"]) -> bool:
    """Embed the pending rows of a page in ONE call, so the per-row reads that follow are
    cache hits. False when the call failed: the caller then skips the meaning signal for the
    whole page instead of retrying it row by row."""
    texts = [
        canonical_text(r.title, r.developer_name, r.state, r.mukim)
        for r in rows
        if r.status == STATUS_PENDING and r.title
    ]
    if not texts:
        return True
    try:
        embed_texts(texts)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.info("registration page embedding skipped: %s", exc)
        return False


def _profile_mukims(db: Session, project_ids: Iterable[str]) -> Dict[str, Optional[str]]:
    ids = list(project_ids)
    if not ids:
        return {}
    rows = (
        db.query(ProjectSalesProfile.project_id, ProjectSalesProfile.mukim)
        .filter(ProjectSalesProfile.project_id.in_(ids))
        .all()
    )
    return {str(pid): _norm(m) or None for pid, m in rows}


def _unpadded(normalised_title: str) -> str:
    """`lot 09001` and `lot 9001` are one lot, so they must be one phase designator too."""
    return re.sub(r"(?<![a-z0-9])0+(?=\d)", "", normalised_title)


def lot_pattern(lots) -> str:
    """The case-insensitive regex that finds any of `lots` (at most MAX_LOT_NUMBERS) in a title.
    Leading zeros are optional on the stored side, as they are ignored on the typed side."""
    wanted = sorted(lots)[:MAX_LOT_NUMBERS]
    return (
        r"(^|[^a-z])(lot|pt)\s*(no\.?\s*)?0*("
        + "|".join(re.escape(n) for n in wanted)
        + r")([^0-9]|$)"
    )


def _lot_matches(db: Session, *, company_id: str, title: str, mukim: Optional[str]) -> List[Project]:
    """Projects on the same lot AND mukim. Any failure reads as "no lot match": this is one
    signal among three and must never turn a registration read into a 500."""
    try:
        lots = set(sorted(parse_lot_numbers(title))[:MAX_LOT_NUMBERS])
        wanted_mukim = _norm(mukim) or parse_mukim(title)
        if not lots or not wanted_mukim:
            return []
        with db.begin_nested():
            candidates = (
                db.query(Project)
                .filter(Project.company_id == company_id, Project.title.op("~*")(lot_pattern(lots)))
                .order_by(Project.created_at, Project.id)
                .limit(200)
                .all()
            )
            profile_mukims = _profile_mukims(db, [p.id for p in candidates])
        out = []
        for project in candidates:
            if not (parse_lot_numbers(project.title) & lots):
                continue
            project_mukim = profile_mukims.get(str(project.id)) or parse_mukim(project.title)
            if project_mukim and project_mukim == wanted_mukim:
                out.append(project)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.info("registration lot match skipped: %s", exc)
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
    """Existing projects of this company that may be the registration, strongest first:
    same lot and mukim, then meaning, then spelling. A phase sibling is never named."""
    from app.services.project_clash_service import (
        are_sibling_developments,
        find_clashes,
        normalise_project_title,
    )

    clean_title = _clean(title)
    if not clean_title:
        return []
    key = _unpadded(normalise_project_title(clean_title))
    ordered: List[Project] = []
    seen: set = set()

    def take(project: Optional[Project]) -> None:
        if project is None or project.id in seen or str(project.company_id) != str(company_id):
            return
        if are_sibling_developments(_unpadded(project.normalised_title or normalise_project_title(project.title)), key):
            return
        seen.add(project.id)
        ordered.append(project)

    for project in _lot_matches(db, company_id=company_id, title=clean_title, mukim=mukim):
        take(project)

    meaning = [
        (pid, cosine)
        for pid, cosine in (
            semantic_matches(
                db,
                company_id=company_id,
                text=canonical_text(clean_title, developer_name, state, mukim),
            )
            if use_meaning
            else []
        )
        if cosine >= REGISTRATION_SEMANTIC_THRESHOLD
    ]
    meaning.sort(key=lambda pair: pair[1], reverse=True)
    if meaning:
        by_id = {
            p.id: p
            for p in db.query(Project)
            .filter(Project.company_id == company_id, Project.id.in_([pid for pid, _ in meaning]))
            .all()
        }
        for pid, _cosine in meaning:
            take(by_id.get(pid))

    for candidate in find_clashes(
        db,
        company_id=company_id,
        developer_party_id=None,
        title=clean_title,
        include_other_developers=True,
    ):
        take(db.get(Project, candidate.project_id))

    return [
        {"project_id": p.id, "project_code": p.project_code, "title": p.title}
        for p in ordered[: max(1, limit)]
    ]


def _duplicates_for(db: Session, row: ProjectRegistration, *, use_meaning: bool = True) -> List[Dict[str, str]]:
    """Only a registration still waiting for a decision is checked: that is when it matters."""
    if row.status != STATUS_PENDING or not row.title:
        return []
    return find_possible_duplicates(
        db,
        company_id=row.company_id,
        title=row.title,
        developer_name=row.developer_name,
        state=row.state,
        mukim=row.mukim,
        use_meaning=use_meaning,
    )


# ------------------------------------------------------------------ shared reads


def _agent_name(agent) -> Optional[str]:
    if agent is None:
        return None
    return _clean(agent.person_label) or _clean(agent.description) or agent.sales_agent


def _agent_name_for(db: Session, row: ProjectRegistration) -> Optional[str]:
    if not row.sales_agent_id:
        return None
    from app.models.sales_agent import SalesAgent

    return _agent_name(db.get(SalesAgent, row.sales_agent_id))


def _project_code(db: Session, project_id: Optional[str]) -> Optional[str]:
    if not project_id:
        return None
    return db.query(Project.project_code).filter(Project.id == str(project_id)).scalar()


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


# ------------------------------------------------------------------ portal half


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


def _own(db: Session, token, registration_id: str) -> ProjectRegistration:
    row = (
        db.query(ProjectRegistration)
        .filter(
            ProjectRegistration.id == str(registration_id),
            ProjectRegistration.contact_id == str(token.contact_id),
        )
        .first()
        if _is_uuid(registration_id)
        else None
    )
    if row is None:
        raise handle_not_found("Project registration", registration_id)
    return row


def _is_uuid(value: Any) -> bool:
    from uuid import UUID

    try:
        UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


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


def _check_lengths(payload: Dict[str, Any]) -> None:
    """Refuse an over-long value before anything is written, naming the field."""
    for key, limit in _MAX_LEN.items():
        value = payload.get(key)
        if isinstance(value, str) and len(value.strip()) > limit:
            raise AppException(
                status_code=422,
                message=f"{key.replace('_', ' ').capitalize()} is too long (at most {limit} characters).",
                detail=key,
                code="VALIDATION_ERROR",
            )


def _apply(db: Session, row: ProjectRegistration, contact_id: str, payload: Dict[str, Any]) -> None:
    _check_lengths(payload)
    for key in FIELD_KEYS:
        if key not in payload:
            continue
        if key == "customer_id":
            row.customer_id = _check_customer(db, row.company_id, contact_id, payload[key])
            continue
        value = payload[key]
        value = (str(value).strip() or None) if value is not None else None
        if key != "title":
            value = " ".join(value.split()) if value else None
        setattr(row, key, value)
    # A pick with no typed name shows the debtor's own name.
    if row.customer_id and not row.customer_name:
        from app.models.order import Customer

        row.customer_name = db.query(Customer.customer_name).filter(Customer.id == row.customer_id).scalar()


def _editable(row: ProjectRegistration) -> bool:
    return row.status in (STATUS_DRAFT, STATUS_REJECTED)


def _require_editable(row: ProjectRegistration) -> None:
    if not _editable(row):
        raise AppException(
            status_code=422, message="This registration is locked.", code="PROJECT_REGISTRATION_LOCKED"
        )


def _portal_summary(db: Session, row: ProjectRegistration) -> Dict[str, Any]:
    ppf = _project_code(db, row.project_id) if row.status == STATUS_APPROVED else None
    return {
        "id": str(row.id),
        "kind": KIND,
        "title": row.title or "Project registration",
        "reference": ppf,
        "document_number": None,
        "status": row.status,
        "approval_status": None,
        "rejection_reason": row.reject_reason,
        "is_editable": _editable(row),
        "is_draft": _editable(row),
        "created_at": _iso(row.created_at),
        "developer_name": row.developer_name,
        "state": row.state,
        "customer_name": row.customer_name,
        "ppf_no": ppf,
    }


def _portal_detail(db: Session, row: ProjectRegistration, *, with_duplicates: bool = True) -> Dict[str, Any]:
    base = _portal_summary(db, row)
    base.update({key: getattr(row, key) for key in FIELD_KEYS})
    base.update(
        {
            "customer_id": str(row.customer_id) if row.customer_id else None,
            "submitted_at": _iso(row.submitted_at),
            "sales_agent_name": _agent_name_for(db, row),
            "reject_reason": row.reject_reason,
            "possible_duplicates": [
                {"project_code": d["project_code"], "title": d["title"]} for d in _duplicates_for(db, row)
            ]
            if with_duplicates
            else [],
        }
    )
    return base


def portal_list(db: Session, token, q: Optional[str] = None) -> List[Dict[str, Any]]:
    with _scope(db, token):
        query = db.query(ProjectRegistration).filter(ProjectRegistration.contact_id == str(token.contact_id))
        if q and q.strip():
            like = f"%{q.strip()}%"
            query = query.filter(
                or_(
                    ProjectRegistration.title.ilike(like),
                    ProjectRegistration.developer_name.ilike(like),
                    ProjectRegistration.distributor_name.ilike(like),
                    ProjectRegistration.customer_name.ilike(like),
                    ProjectRegistration.state.ilike(like),
                    ProjectRegistration.mukim.ilike(like),
                )
            )
        rows = query.order_by(ProjectRegistration.created_at.desc(), ProjectRegistration.id).all()
        return [_portal_summary(db, r) for r in rows]


def portal_get(db: Session, token, registration_id: str, *, full: bool = False) -> Dict[str, Any]:
    """`full` builds the possible duplicates (the detail page). Every other caller only needs
    to know the contact owns the row, which must not cost a lot query and an embedding."""
    with _scope(db, token):
        return _portal_detail(db, _own(db, token, registration_id), with_duplicates=full)


def portal_neighbours(db: Session, token, registration_id: str) -> Dict[str, Any]:
    with _scope(db, token):
        _own(db, token, registration_id)
        ids = [
            str(r[0])
            for r in db.query(ProjectRegistration.id)
            .filter(ProjectRegistration.contact_id == str(token.contact_id))
            .order_by(ProjectRegistration.created_at.desc(), ProjectRegistration.id)
            .all()
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
    from app.api.v1.public.portal_price_tag import _resolve_company

    if registration_id is None:
        agent = _require_agent(db, token.contact_id)
        company_id = _resolve_company(db, token)
        with company_scope(db, frozenset({company_id})):
            row = ProjectRegistration(
                company_id=company_id,
                status=STATUS_DRAFT,
                contact_id=str(token.contact_id),
                sales_agent_id=agent.id,
            )
            _apply(db, row, token.contact_id, payload)
            db.add(row)
            db.commit()
            db.refresh(row)
            return _portal_detail(db, row, with_duplicates=False)
    with _scope(db, token):
        row = _own(db, token, registration_id)
        _require_editable(row)
        _apply(db, row, token.contact_id, payload)
        db.commit()
        db.refresh(row)
        return _portal_detail(db, row, with_duplicates=False)


def _missing(values: Dict[str, Any]) -> List[str]:
    return [k for k in REQUIRED_ON_SUBMIT if not _clean(values.get(k))]


def _linked_user_id(db: Session, contact_id: str) -> Optional[str]:
    from app.models.user import User

    return db.query(User.id).filter(User.respond_contact_id == str(contact_id)).scalar()


def portal_submit(
    db: Session, token, registration_id: str, payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    with _scope(db, token):
        row = _own(db, token, registration_id)
        _require_editable(row)
        _require_agent(db, token.contact_id)
        _check_lengths(payload or {})
        merged = {key: getattr(row, key) for key in FIELD_KEYS}
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
            _apply(db, row, token.contact_id, payload)
        row.status = STATUS_PENDING
        row.submitted_at = _now()
        row.reject_reason = None
        row.decided_at = None
        row.decided_by = None
        row.applicant_user_id = _linked_user_id(db, token.contact_id)
        db.commit()
        db.refresh(row)
        notify(db, row, "submitted")
        return _portal_detail(db, row, with_duplicates=False)


def portal_delete(db: Session, token, registration_id: str) -> None:
    with _scope(db, token):
        row = _own(db, token, registration_id)
        if row.status != STATUS_DRAFT:
            raise AppException(status_code=422, message="Only drafts can be deleted.")
        db.delete(row)
        db.commit()


# ------------------------------------------------------------------ notifications (F1, F2)


def _holders(db: Session, row: ProjectRegistration, exclude: Iterable[Any] = ()) -> List[str]:
    from app.services.project_notify_service import approver_user_ids

    return approver_user_ids(
        db, company_id=row.company_id, exclude={str(e) for e in exclude if e}, slug=APPROVE_PERMISSION
    )


def notify(db: Session, row: ProjectRegistration, event: str) -> int:
    """Tell who must act (submitted) or who asked (approved, rejected). Call AFTER the move
    commits; a failure is logged per recipient and never undoes the move."""
    title_text = row.title or "A project"
    try:
        if event == "submitted":
            recipients = _holders(db, row, exclude=[row.applicant_user_id])
            title = f"Project registration waits for your approval: {title_text}"
            link = f"/project-sales/registrations/{row.id}"
        else:
            recipients = [row.applicant_user_id] if row.applicant_user_id else []
            code = _project_code(db, row.project_id)
            title = (
                f"Your project registration is approved as {code}: {title_text}"
                if event == "approved"
                else f"Your project registration was rejected: {title_text}"
            )
            link = f"/project-sales/{row.project_id}" if event == "approved" and row.project_id else None
        from app.services.notification_service import NotificationService

        service = NotificationService(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("project registration notice not sent: %s %s (%s)", event, row.id, exc)
        return 0
    sent = 0
    stamp = row.decided_at or row.submitted_at
    for user_id in {str(u) for u in recipients if u}:
        try:
            service.create_with_channel_preferences(
                user_id=user_id,
                type=f"project_registration_{event}",
                title=title,
                body=title,
                data={"registration_id": str(row.id), **({"link": link} if link else {})},
                source_entity_type="project_registration",
                source_entity_id=str(row.id),
                dedup_key=f"{row.id}:{event}:{stamp.isoformat() if stamp else ''}",
                event_type=f"project_registration_{event}",
                send_in_app=True,
                send_email=True,
                send_whatsapp=False,
                send_web_push=False,
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("project registration notice not sent to %s: %s (%s)", user_id, event, exc)
            if not db.is_active:
                db.rollback()
    return sent


# ------------------------------------------------------------------ CRM half


def get_or_404(db: Session, registration_id: str, *, lock: bool = False) -> ProjectRegistration:
    """`lock` takes the row lock a decision needs, so two approvers cannot both read it as
    pending and each create a project."""
    if not _is_uuid(registration_id):
        row = None
    elif lock:
        row = (
            db.query(ProjectRegistration)
            .filter(ProjectRegistration.id == str(registration_id))
            .with_for_update()
            .populate_existing()
            .first()
        )
    else:
        row = db.get(ProjectRegistration, registration_id)
    if row is None:
        raise handle_not_found("Project registration", registration_id)
    return row


def _first_party(db: Session, company_id: str, party_type: str, name: Optional[str]) -> Optional[str]:
    if not _norm(name):
        return None
    row = (
        db.query(ProjectParty.id)
        .filter(
            ProjectParty.company_id == company_id,
            ProjectParty.party_type == party_type,
            func.lower(func.btrim(ProjectParty.name)) == _norm(name),
        )
        .order_by(ProjectParty.created_at, ProjectParty.id)
        .first()
    )
    return str(row[0]) if row else None


def _prefill(db: Session, row: ProjectRegistration) -> Dict[str, Optional[str]]:
    type_id = None
    if _norm(row.type_of_building):
        found = (
            db.query(ProjectType.id)
            .filter(
                ProjectType.company_id == row.company_id,
                func.lower(func.btrim(ProjectType.name)) == _norm(row.type_of_building),
            )
            .order_by(ProjectType.id)
            .first()
        )
        type_id = str(found[0]) if found else None
    return {
        "developer_party_id": _first_party(db, row.company_id, "developer", row.developer_name),
        "architect_party_id": _first_party(db, row.company_id, "architect", row.architect_name),
        "main_contractor_party_id": _first_party(
            db, row.company_id, "main_contractor", row.main_contractor_name
        ),
        "type_id": type_id,
    }


def _crm_row(db: Session, row: ProjectRegistration, *, use_meaning: bool = True) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "submitted_at": _iso(row.submitted_at),
        "title": row.title,
        "developer_name": row.developer_name,
        "state": row.state,
        "sales_agent_name": _agent_name_for(db, row),
        "status": row.status,
        "possible_duplicates": _duplicates_for(db, row, use_meaning=use_meaning),
        "project_id": str(row.project_id) if row.project_id else None,
        "project_code": _project_code(db, row.project_id),
    }


def detail(db: Session, row: ProjectRegistration) -> Dict[str, Any]:
    from app.models.user import User

    decided_by_name = None
    if row.decided_by:
        user = db.get(User, row.decided_by)
        decided_by_name = (user.name or user.email) if user else None
    out = _crm_row(db, row)
    out.update({key: getattr(row, key) for key in FIELD_KEYS})
    out.update(
        {
            "customer_id": str(row.customer_id) if row.customer_id else None,
            "reject_reason": row.reject_reason,
            "decided_at": _iso(row.decided_at),
            "decided_by_name": decided_by_name,
            "applicant_user_id": row.applicant_user_id,
            "prefill": _prefill(db, row),
        }
    )
    return out


_SORTABLE = {
    "submitted_at": ProjectRegistration.submitted_at,
    "created_at": ProjectRegistration.created_at,
    "title": ProjectRegistration.title,
    "developer_name": ProjectRegistration.developer_name,
    "state": ProjectRegistration.state,
    "status": ProjectRegistration.status,
}


def list_rows(
    db: Session,
    *,
    status: Optional[str],
    query: Optional[str],
    page: int,
    limit: int,
    sort: Optional[str],
    direction: str,
) -> Dict[str, Any]:
    # A contact's unsent draft is not the admin's business, whatever the filter says.
    q = db.query(ProjectRegistration).filter(ProjectRegistration.status != STATUS_DRAFT)
    wanted = (status or STATUS_PENDING).strip().lower()
    if wanted != "all":
        q = q.filter(ProjectRegistration.status.in_([s.strip() for s in wanted.split(",") if s.strip()]))
    if query and query.strip():
        like = f"%{query.strip()}%"
        q = q.filter(
            or_(
                ProjectRegistration.title.ilike(like),
                ProjectRegistration.developer_name.ilike(like),
                ProjectRegistration.distributor_name.ilike(like),
            )
        )
    total = q.count()
    column = _SORTABLE.get(sort or "", ProjectRegistration.submitted_at)
    ordered = column.asc() if (direction or "").lower() == "asc" else column.desc()
    rows = (
        q.order_by(ordered.nulls_last(), ProjectRegistration.id)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    use_meaning = prime_meaning(rows)
    return {
        "data": [_crm_row(db, r, use_meaning=use_meaning) for r in rows],
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }


def _not_pending() -> AppException:
    return AppException(
        status_code=409,
        message="This registration has already been decided.",
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
    """An active, untrashed user with access to the registration's company."""
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
    db: Session, row: ProjectRegistration, requested: Optional[str], actor_user_id: str, actor_slugs
) -> str:
    """Who owns the project (finding S9). The applicant or the approver need no extra grant;
    anyone else is the staff rule: only a sales manager registers a project for someone else."""
    applicant = row.applicant_user_id
    if requested:
        if requested not in (applicant, actor_user_id) and MANAGE_PERMISSION not in actor_slugs:
            raise AppException(
                status_code=403,
                message="Only a sales manager can register a project for someone else.",
                code="project_owner_assign_forbidden",
            )
        if requested != actor_user_id and not _owner_can_own(db, requested, row.company_id):
            raise _unprocessable(
                "That salesperson cannot own a project of this company.",
                "project_registration_owner_invalid",
            )
        return requested
    return applicant if _owner_can_own(db, applicant, row.company_id) else actor_user_id


def _check_company_refs(db: Session, company_id: str, payload: Dict[str, Any]) -> None:
    """Every id the approver sends must belong to the registration's company (finding S10):
    the pickers are company scoped, the API must not trust that."""
    from app.models.product import Brand
    from app.models.projects import ProjectTemplate

    refuse = _unprocessable("Pick the parties, type and template from this company.", "project_registration_ref_invalid")
    for key in ("developer_party_id", "architect_party_id", "main_contractor_party_id"):
        value = payload.get(key)
        if value and not (
            _is_uuid(value)
            and db.query(ProjectParty.id)
            .filter(ProjectParty.id == str(value), ProjectParty.company_id == company_id)
            .first()
        ):
            raise refuse
    for key, model in (("type_id", ProjectType), ("template_id", ProjectTemplate)):
        value = payload.get(key)
        if value and not (
            _is_uuid(value)
            and db.query(model.id).filter(model.id == str(value), model.company_id == company_id).first()
        ):
            raise refuse
    brand_ids = {str(b) for b in (payload.get("brand_ids") or [])}
    if brand_ids:
        if not all(_is_uuid(b) for b in brand_ids) or (
            db.query(func.count(Brand.id)).filter(Brand.id.in_(brand_ids), Brand.company_id == company_id).scalar()
            != len(brand_ids)
        ):
            raise refuse


def approve(
    db: Session,
    row: ProjectRegistration,
    payload: Dict[str, Any],
    *,
    actor_user_id: str,
    actor_slugs=frozenset(),
) -> ProjectRegistration:
    """Create the project (PPF code drawn here) and mark the registration approved.

    A possible duplicate never blocks (D7); only the exact developer + title repeat does, and
    that is answered 409 naming the project. The whole creation sits in a SAVEPOINT so the
    refused attempt neither burns a number nor poisons the session.
    """
    from app.services import project_service
    from app.services.project_clash_service import normalise_project_title

    if row.status != STATUS_PENDING:
        raise _not_pending()
    developer_party_id = payload.get("developer_party_id")
    if not developer_party_id:
        raise AppException(
            status_code=422,
            message="Pick the developer before approving.",
            code="project_registration_developer_required",
        )
    title = _clean(payload.get("title")) or _clean(row.title)
    details = {k: payload[k] for k in _APPROVE_DETAIL_KEYS if k in payload}
    details.setdefault("state", row.state)
    details.setdefault("mukim", row.mukim)
    registration_id = str(row.id)
    company_id = str(row.company_id)
    _check_company_refs(db, company_id, payload)
    owner = _resolve_owner(db, row, payload.get("owner_user_id"), actor_user_id, actor_slugs)
    try:
        with db.begin_nested():
            project = project_service.register_project(
                db,
                company_id=company_id,
                actor_user_id=actor_user_id,
                developer_party_id=developer_party_id,
                title=title or "",
                type_id=payload.get("type_id"),
                template_id=payload.get("template_id"),
                details=details,
                brand_ids=payload.get("brand_ids"),
                owner_user_id=owner,
                skip_clash_check=True,
            )
    except IntegrityError as exc:
        if "uq_projects_company_developer_title" not in str(getattr(exc, "orig", exc)):
            raise
        existing = (
            db.query(Project)
            .filter(
                Project.company_id == company_id,
                Project.developer_party_id == developer_party_id,
                Project.normalised_title == normalise_project_title(title or ""),
            )
            .first()
        )
        code = existing.project_code if existing else "an existing project"
        raise AppException(
            status_code=409,
            message=f"{code} already has this developer and title. Change the title, e.g. add the phase.",
            code="project_registration_exact_duplicate",
        )
    row = get_or_404(db, registration_id)
    row.status = STATUS_APPROVED
    row.project_id = project.id
    row.decided_at = _now()
    row.decided_by = actor_user_id
    db.flush()
    return row


def reject(db: Session, row: ProjectRegistration, reason: Optional[str], *, actor_user_id: str) -> ProjectRegistration:
    text = (reason or "").strip()
    if not text:
        raise AppException(
            status_code=422, message="Give the reason for rejecting.", code="project_registration_reason_required"
        )
    if row.status != STATUS_PENDING:
        raise _not_pending()
    row.status = STATUS_REJECTED
    row.reject_reason = text
    row.decided_at = _now()
    row.decided_by = actor_user_id
    db.flush()
    return row
