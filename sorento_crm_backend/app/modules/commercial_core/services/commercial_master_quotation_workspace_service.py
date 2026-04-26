"""Master quotation workspace extras: checklist activities and master-level attachments."""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.modules.commercial_core.models import CommercialMasterQuotation, CommercialMasterQuotationActivity, CommercialTender
from app.models.user import User
from app.services.entity_attachment_service import EntityAttachmentService
from app.services.error_handler import handle_not_found, handle_validation_error


def _user_brief(db: Session, user_id: Optional[str]) -> Optional[dict]:
    if not user_id:
        return None
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        return {"user_code": user_id, "name": None}
    code = (u.email or u.id or "").strip()
    return {"user_code": code, "name": (u.name or "").strip() or None}


def _resolve_user_id_by_code(db: Session, user_code: Optional[str]) -> Optional[str]:
    if not user_code or not str(user_code).strip():
        return None
    code = str(user_code).strip()
    u = db.query(User.id).filter(User.id == code).first()
    if u:
        return str(u[0])
    u = db.query(User.id).filter(User.email == code).first()
    if u:
        return str(u[0])
    raise handle_validation_error("User not found for the given code.")


def _get_master(db: Session, master_id: str) -> CommercialMasterQuotation:
    mq = db.query(CommercialMasterQuotation).filter(CommercialMasterQuotation.id == master_id).first()
    if not mq:
        raise handle_not_found("Master quotation", master_id)
    return mq


def list_compare_rows(db: Session, tender_code: str) -> List[dict]:
    t = db.query(CommercialTender).filter(CommercialTender.tender_code == (tender_code or "").strip()).first()
    if not t:
        raise handle_not_found("Tender", tender_code)
    rows = (
        db.query(CommercialMasterQuotation)
        .options(
            joinedload(CommercialMasterQuotation.quotation_stage),
            joinedload(CommercialMasterQuotation.current_working_revision),
        )
        .filter(CommercialMasterQuotation.tender_id == t.id)
        .order_by(CommercialMasterQuotation.quotation_code.asc())
        .all()
    )
    out: List[dict] = []
    for mq in rows:
        st = mq.quotation_stage
        salesperson_name: Optional[str] = None
        rev = mq.current_working_revision
        if rev and isinstance(rev.pricing_snapshot, dict):
            meta = rev.pricing_snapshot.get("quotation_meta")
            if isinstance(meta, dict):
                sid = meta.get("salesperson_user_id")
                if sid:
                    u = db.query(User).filter(User.id == str(sid)).first()
                    if u:
                        salesperson_name = ((u.name or "").strip() or u.email) or None
        out.append(
            {
                "tender_code": t.tender_code,
                "quotation_code": mq.quotation_code,
                "title": mq.title,
                "path_role": mq.path_role,
                "stage": {
                    "stage_code": st.code if st else "",
                    "stage_name": st.label if st else "",
                    "is_terminal": bool(st.is_terminal) if st else False,
                },
                "owner": _user_brief(db, mq.owner_user_id),
                "salesperson_name": salesperson_name,
                "quoted_amount": mq.quoted_amount,
                "quoted_currency": mq.quoted_currency,
                "updated_at": mq.updated_at,
            }
        )
    return out


def list_activities(db: Session, master_id: str) -> List[dict]:
    _get_master(db, master_id)
    acts = (
        db.query(CommercialMasterQuotationActivity)
        .filter(CommercialMasterQuotationActivity.master_quotation_id == master_id)
        .order_by(CommercialMasterQuotationActivity.sort_order, CommercialMasterQuotationActivity.created_at)
        .all()
    )
    return [_serialize_activity(db, a) for a in acts]


def _serialize_activity(db: Session, a: CommercialMasterQuotationActivity) -> dict:
    return {
        "id": str(a.id),
        "title": a.title,
        "body": a.body,
        "status": a.status,
        "due_at": a.due_at,
        "assignee": _user_brief(db, a.assignee_user_id),
        "sort_order": a.sort_order,
        "completed_at": a.completed_at,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def create_activity(db: Session, master_id: str, payload: dict) -> dict:
    mq = _get_master(db, master_id)
    mx = (
        db.query(func.max(CommercialMasterQuotationActivity.sort_order))
        .filter(CommercialMasterQuotationActivity.master_quotation_id == mq.id)
        .scalar()
    )
    sort_order = int(payload.get("sort_order")) if payload.get("sort_order") is not None else int(mx or -1) + 1
    assignee = _resolve_user_id_by_code(db, payload.get("assignee_user_code")) if payload.get("assignee_user_code") else None
    row = CommercialMasterQuotationActivity(
        master_quotation_id=mq.id,
        title=payload["title"].strip(),
        body=payload.get("body"),
        status="open",
        due_at=payload.get("due_at"),
        assignee_user_id=assignee,
        sort_order=sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_activity(db, row)


def patch_activity(db: Session, master_id: str, activity_id: str, payload: dict) -> dict:
    _get_master(db, master_id)
    a = (
        db.query(CommercialMasterQuotationActivity)
        .filter(
            CommercialMasterQuotationActivity.id == activity_id,
            CommercialMasterQuotationActivity.master_quotation_id == master_id,
        )
        .first()
    )
    if not a:
        raise handle_not_found("Activity", activity_id)
    if payload.get("title") is not None:
        a.title = str(payload["title"]).strip()
    if "body" in payload:
        a.body = payload.get("body")
    if payload.get("status") is not None:
        st = str(payload["status"]).strip()
        if st not in ("open", "done"):
            raise handle_validation_error("status must be open or done")
        a.status = st
    if "due_at" in payload:
        a.due_at = payload.get("due_at")
    if payload.get("assignee_user_code") is not None:
        a.assignee_user_id = _resolve_user_id_by_code(db, payload.get("assignee_user_code"))
    if payload.get("sort_order") is not None:
        a.sort_order = int(payload["sort_order"])
    if "completed_at" in payload:
        a.completed_at = payload.get("completed_at")
    db.commit()
    db.refresh(a)
    return _serialize_activity(db, a)


def delete_activity(db: Session, master_id: str, activity_id: str) -> None:
    _get_master(db, master_id)
    a = (
        db.query(CommercialMasterQuotationActivity)
        .filter(
            CommercialMasterQuotationActivity.id == activity_id,
            CommercialMasterQuotationActivity.master_quotation_id == master_id,
        )
        .first()
    )
    if not a:
        raise handle_not_found("Activity", activity_id)
    db.delete(a)
    db.commit()


def list_mq_attachment_payloads(db: Session, master_id: str) -> List[dict]:
    _get_master(db, master_id)
    svc = EntityAttachmentService(db)
    links = svc.list_links("master_quotation", master_id)
    return [
        svc.serialize_link(
            l,
            entity_key="master_quotation_id",
            link_type="master_quotation_attachment",
        )
        for l in links
    ]


def link_mq_attachment(db: Session, master_id: str, attachment_id: str, *, created_by: Optional[str]) -> dict:
    _get_master(db, master_id)
    svc = EntityAttachmentService(db)
    link = svc.link_existing_attachment(
        "master_quotation",
        master_id,
        attachment_id,
        created_by=created_by,
    )
    db.commit()
    db.refresh(link)
    return svc.serialize_link(
        link,
        entity_key="master_quotation_id",
        link_type="master_quotation_attachment",
    )


def unlink_mq_attachment(db: Session, link_id: str) -> None:
    svc = EntityAttachmentService(db)
    svc.delete_link(link_id, entity_type="master_quotation")
    db.commit()
