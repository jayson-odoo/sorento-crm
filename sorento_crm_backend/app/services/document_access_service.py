"""DOC-ACCESS-SIMPLE: the Document Access matrix and the "what does this contact read" preview.

Counts run under the session's company scope (the route widens it for `company_scope=grants`). The
preview decides a document with `knowledge_service.contact_readable_clause`, the predicate
`search_for_contact` uses, and the contact side (codes, agent switch, ambiguity, linked user) with the
helpers in `chatbot/agent/access.py` (reached through `app/modules/chatbot/contact_access.py`), so the
page cannot disagree with the bot.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.base import company_scope, get_company_scope
from app.services import knowledge_service as ks
from app.services.error_handler import handle_not_found


def _catalogue(db: Session) -> list:
    from app.models.access import ContactAccessType

    return (
        db.query(ContactAccessType.code, ContactAccessType.name)
        .filter(ContactAccessType.is_active.is_(True))
        .order_by(ContactAccessType.sort_order, ContactAccessType.code)
        .all()
    )


def _allowed_company_ids(db: Session, user_id: Optional[str]) -> Optional[set]:
    """Company ids the caller may see: the active scope plus the caller's grants. None = every company."""
    from app.services.company_scope_resolver import grants_scope_value

    scope = grants_scope_value(db, str(user_id)) if user_id else get_company_scope(db)
    return None if scope is None else {str(c) for c in scope}


def _contact_block(db: Session, contact_id: str, catalogue_codes: list, user_id: Optional[str] = None) -> dict:
    from app.models.access import RespondContact
    from app.models.company import Company, RespondContactCompany
    from app.modules.chatbot.contact_access import (
        active_access_codes,
        agent_switch_on,
        contact_row_count,
        linked_active_user,
    )

    allowed = _allowed_company_ids(db, user_id)  # the caller's scope, read before it is lifted below
    with company_scope(db, None):  # a contact row must not read as missing because of the caller's scope
        contact = db.query(RespondContact).filter(RespondContact.id == str(contact_id)).first()
        if contact is None:
            raise handle_not_found("Contact", str(contact_id))
        companies = (
            db.query(Company.id, Company.name)
            .join(RespondContactCompany, RespondContactCompany.company_id == Company.id)
            .filter(RespondContactCompany.respond_contact_id == str(contact.id))
            .order_by(Company.name)
            .all()
        )
        agent_on = agent_switch_on(db, contact)
        staff = linked_active_user(db, str(contact.id)) is not None
        ambiguous = (not staff) and bool(contact.respond_io_id) and contact_row_count(db, contact.respond_io_id) > 1
    held = active_access_codes(db, str(contact.id))
    codes = [c for c in catalogue_codes if c in held]
    blocked = None
    if not staff:
        if ambiguous:
            blocked = "ambiguous"
        elif not codes:
            blocked = "no_access_type"
        elif not companies:
            blocked = "no_company"
    # Only companies the caller is granted are named: the block must not reveal the contact's others.
    if allowed is not None:
        companies = [c for c in companies if str(c[0]) in allowed]
    return {
        "id": str(contact.id),
        "name": contact.name,
        "runs_as": "staff" if staff else "contact",
        "agent_on": agent_on,
        "access_types": codes,
        "companies": [{"id": str(i), "name": n} for i, n in companies],
        "blocked": blocked,
    }


def _attachment_rows(db: Session, type_id: Optional[str] = None) -> list:
    """Non-deleted files of the types, as (id, type id, filename, levels, company id, company-free status)."""
    from app.models.resources import Attachment

    q = db.query(
        Attachment.id,
        Attachment.attachment_type_id,
        Attachment.original_filename,
        Attachment.access_levels,
        Attachment.company_id,
        Attachment.ai_read_status,
    ).filter(Attachment.is_deleted.is_(False), Attachment.attachment_type_id.isnot(None))
    if type_id is not None:
        q = q.filter(Attachment.attachment_type_id == str(type_id))
    return q.all()


def _code_ok_ids(db: Session, codes: list, type_id: Optional[str] = None) -> set:
    """Ids of files the contact's codes reach through the type's ticks: the SAME clause the bot uses."""
    from app.models.resources import Attachment, AttachmentType

    if not codes:
        return set()
    q = (
        db.query(Attachment.id)
        .join(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
        .filter(Attachment.is_deleted.is_(False), ks.contact_readable_clause(codes))
    )
    if type_id is not None:
        q = q.filter(Attachment.attachment_type_id == str(type_id))
    return {str(r[0]) for r in q.all()}


def _doc_verdict(contact: dict, code_ok: bool, company_id) -> Optional[str]:
    if contact["runs_as"] == "staff":
        return None
    if contact["blocked"]:
        return contact["blocked"]
    if not code_ok:
        return "no_shared_code"
    if company_id is not None and str(company_id) not in {c["id"] for c in contact["companies"]}:
        return "other_company"
    return "reads"


def _grant_counts(db: Session, user_id: Optional[str]) -> dict:
    """Document-type grants per type, counting only contacts linked to a company the caller may see."""
    from app.models.access import ContactAttachmentType
    from app.models.company import RespondContactCompany

    allowed = _allowed_company_ids(db, user_id)
    with company_scope(db, None):
        q = db.query(
            ContactAttachmentType.attachment_type_id, func.count(func.distinct(ContactAttachmentType.contact_id))
        ).group_by(ContactAttachmentType.attachment_type_id)
        if allowed is not None:  # an unscoped caller counts every grant, a contact with no company included
            q = q.join(RespondContactCompany, RespondContactCompany.respond_contact_id == ContactAttachmentType.contact_id).filter(
                RespondContactCompany.company_id.in_(allowed)
            )
        return {str(k): int(v) for k, v in q.all()}


def build_matrix(db: Session, *, contact_id: Optional[str] = None, user_id: Optional[str] = None) -> dict:
    from app.models.resources import AttachmentType

    catalogue = _catalogue(db)
    codes = [str(c) for c, _ in catalogue]
    contact = _contact_block(db, contact_id, codes, user_id) if contact_id else None

    types = db.query(AttachmentType).order_by(AttachmentType.type_name).all()
    grants = _grant_counts(db, user_id)

    files: dict = {str(t.id): [] for t in types}
    for row in _attachment_rows(db):
        files.setdefault(str(row.attachment_type_id), []).append(row)
    contact_run = contact is not None and contact["runs_as"] == "contact" and contact["blocked"] is None
    code_ok = _code_ok_ids(db, contact["access_types"]) if contact_run else set()
    company_ids = {c["id"] for c in contact["companies"]} if contact else set()

    rows = []
    for t in types:
        tid = str(t.id)
        mine = files.get(tid, [])
        readable = [r for r in mine if ks.is_readable_filename(r.original_filename)]
        ticked = [str(c) for c in (t.ai_read_codes or [])]
        row = {
            "id": tid,
            "type_name": t.type_name,
            "is_shared": bool(t.is_shared),
            "is_direct_access": bool(t.is_direct_access),
            "grant_count": grants.get(tid, 0),
            "file_count": len(mine),
            "readable_count": len(readable),
            "ai_read_staff": bool(t.ai_read_staff),
            "ai_read_codes": ticked,
            "reach": {c: sum(1 for r in readable if c in (r.access_levels or [])) for c in codes},
            "preview": None,
        }
        if contact is not None:
            row["preview"] = _row_preview(t, ticked, readable, contact, contact_run, code_ok, company_ids)
        rows.append(row)
    return {"access_types": [{"code": str(c), "name": n} for c, n in catalogue], "contact": contact, "rows": rows}


def _row_preview(t, ticked: list, readable: list, contact: dict, contact_run: bool, code_ok: set, company_ids: set) -> dict:
    reads = no_code = other = 0
    if contact_run:
        for r in readable:
            if str(r.id) not in code_ok:
                no_code += 1
            elif r.company_id is not None and str(r.company_id) not in company_ids:
                other += 1
            else:
                reads += 1
    if contact["runs_as"] == "staff":
        verdict = "staff_reads" if t.ai_read_staff else "not_for_staff"
    elif contact["blocked"]:
        verdict = contact["blocked"]
    elif not (t.ai_read_staff or ticked):
        verdict = "off"
    elif not ticked:
        verdict = "staff_only"
    elif not set(ticked) & set(contact["access_types"]):
        verdict = "not_ticked"
    elif not readable:
        verdict = "no_documents"
    else:
        verdict = "reads"
    return {"verdict": verdict, "reads": reads, "total": len(readable), "no_shared_code": no_code, "other_company": other}


def list_documents(
    db: Session,
    type_id: str,
    *,
    contact_id: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    user_id: Optional[str] = None,
    can_upload: bool = False,
    active_companies=None,
) -> dict:
    """`can_edit_levels` per document: the caller may upload AND the file is shared or in an active company."""
    from app.models.company import Company
    from app.models.resources import AttachmentType

    if db.query(AttachmentType.id).filter(AttachmentType.id == str(type_id)).first() is None:
        raise handle_not_found("Attachment Type", str(type_id))
    contact = _contact_block(db, contact_id, [str(c) for c, _ in _catalogue(db)], user_id) if contact_id else None
    readable = [r for r in _attachment_rows(db, type_id) if ks.is_readable_filename(r.original_filename)]
    readable.sort(key=lambda r: ((r.original_filename or "").lower(), str(r.id)))
    total = len(readable)
    window = readable[(page - 1) * limit : page * limit]
    names = {str(i): n for i, n in db.query(Company.id, Company.name).all()}
    code_ok = _code_ok_ids(db, contact["access_types"], type_id) if contact is not None and contact["blocked"] is None else set()
    items = [
        {
            "id": str(r.id),
            "original_filename": r.original_filename,
            "access_levels": list(r.access_levels or []),
            "company_name": names.get(str(r.company_id)) if r.company_id else None,
            "ai_read_status": r.ai_read_status,
            "can_edit_levels": bool(
                can_upload
                and (r.company_id is None or active_companies is None or str(r.company_id) in active_companies)
            ),
            "verdict": _doc_verdict(contact, str(r.id) in code_ok, r.company_id) if contact is not None else None,
        }
        for r in window
    ]
    return {"items": items, "total": total, "page": page, "limit": limit}
