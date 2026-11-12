"""Technician roster for service jobs (after-sales P1)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

from app.models.service_jobs import ServiceJob, Technician
from app.schemas.service_jobs import TechnicianCreate, TechnicianUpdate
from app.services.error_handler import AppException, handle_not_found

SORTS = {
    "name": Technician.name,
    "phone": Technician.phone,
    "employment_type": Technician.employment_type,
    "is_active": Technician.is_active,
}


def serialize(row: Technician, in_use: bool = False) -> Dict[str, Any]:
    return {
        "in_use": in_use,
        "id": row.id,
        "name": row.name,
        "phone": row.phone,
        "employment_type": row.employment_type,
        "is_active": bool(row.is_active),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def get(db: Session, technician_id: str) -> Technician:
    try:
        uuid.UUID(str(technician_id))
    except ValueError:
        raise handle_not_found("Technician", str(technician_id))
    row = db.query(Technician).filter(Technician.id == str(technician_id)).first()
    if row is None:
        raise handle_not_found("Technician", str(technician_id))
    return row


def list_technicians(
    db: Session,
    *,
    page: int,
    limit: int,
    query: Optional[str],
    sort: Optional[str],
    direction: str,
    employment_types: Optional[list] = None,
    active_values: Optional[list] = None,
) -> Dict[str, Any]:
    q = db.query(Technician)
    if query and query.strip():
        like = f"%{query.strip()}%"
        q = q.filter(or_(Technician.name.ilike(like), Technician.phone.ilike(like)))
    if employment_types:
        q = q.filter(Technician.employment_type.in_(employment_types))
    flags = {v.strip().lower() == "true" for v in (active_values or []) if v.strip().lower() in ("true", "false")}
    if flags:
        q = q.filter(Technician.is_active.in_(flags))
    total = q.count()
    column = SORTS.get(sort or "", Technician.name)
    order = desc(column) if (direction or "asc").lower() == "desc" else asc(column)
    rows = q.order_by(order, Technician.id).offset((page - 1) * limit).limit(limit).all()
    used = {
        str(t)
        for (t,) in db.query(ServiceJob.technician_id)
        .filter(ServiceJob.technician_id.in_([r.id for r in rows]))
        .distinct()
        .all()
    }
    return {
        "data": [serialize(r, r.id in used) for r in rows],
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }


def create(db: Session, payload: TechnicianCreate) -> Dict[str, Any]:
    row = Technician(id=str(uuid.uuid4()), **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize(row)


def update(db: Session, technician_id: str, payload: TechnicianUpdate) -> Dict[str, Any]:
    row = get(db, technician_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key in ("name", "employment_type", "is_active") and value is None:
            continue
        setattr(row, key, value)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return serialize(row)


def delete(db: Session, technician_id: str) -> Dict[str, str]:
    row = get(db, technician_id)
    in_use = db.query(ServiceJob.id).filter(ServiceJob.technician_id == row.id).first() is not None
    if in_use:
        raise AppException(
            status_code=409,
            message="This technician is in use on a service job. Archive instead.",
            code="technician_in_use",
        )
    db.delete(row)
    db.commit()
    return {"message": "Technician deleted successfully"}
