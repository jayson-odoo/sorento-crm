"""Service layer for complaint root cause and resolution master data."""
from typing import Optional
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.models.complaint_master_data import ComplaintRootCause, ComplaintResolution
from app.models.complaints import Complaint
from app.schemas.complaint_master_data import (
    ComplaintRootCauseCreate,
    ComplaintRootCauseUpdate,
    ComplaintResolutionCreate,
    ComplaintResolutionUpdate,
)
from app.services.error_handler import handle_conflict, handle_not_found


class ComplaintRootCauseService:
    """CRUD service for complaint root causes."""

    def __init__(self, db: Session):
        self.db = db

    def list_root_causes(self, page: int = 1, limit: int = 50, query: Optional[str] = None,
                        is_active: Optional[bool] = None):
        q = self.db.query(ComplaintRootCause)
        if query:
            term = f"%{query.strip()}%"
            q = q.filter(or_(ComplaintRootCause.name.ilike(term),
                             ComplaintRootCause.description.ilike(term)))
        if is_active is not None:
            q = q.filter(ComplaintRootCause.is_active.is_(is_active))

        total = q.count()
        offset = (page - 1) * limit
        rows = q.order_by(ComplaintRootCause.name.asc()).offset(offset).limit(limit).all()
        if not rows:
            return {"data": [], "pagination": {"total": 0, "page": page, "limit": limit}, "empty": True}

        ids = [r.id for r in rows]
        counts = (
            self.db.query(Complaint.root_cause_id, func.count(Complaint.id))
            .filter(Complaint.root_cause_id.in_(ids))
            .group_by(Complaint.root_cause_id)
            .all()
        )
        count_by_id = {str(rid): c for rid, c in counts}
        data = [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "is_active": r.is_active,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "complaint_count": count_by_id.get(r.id, 0),
            }
            for r in rows
        ]
        return {"data": data, "pagination": {"total": total, "page": page, "limit": limit}, "empty": total == 0}

    def get_root_cause(self, root_cause_id: str) -> ComplaintRootCause:
        row = self.db.query(ComplaintRootCause).filter(ComplaintRootCause.id == root_cause_id).first()
        if not row:
            raise handle_not_found("Complaint root cause", root_cause_id)
        return row

    def create_root_cause(self, payload: ComplaintRootCauseCreate) -> ComplaintRootCause:
        existing = (
            self.db.query(ComplaintRootCause)
            .filter(func.lower(ComplaintRootCause.name) == payload.name.lower())
            .first()
        )
        if existing:
            raise handle_conflict(f"A complaint root cause named '{payload.name}' already exists.")
        row = ComplaintRootCause(**payload.model_dump())
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_root_cause(self, root_cause_id: str, payload: ComplaintRootCauseUpdate) -> ComplaintRootCause:
        row = self.get_root_cause(root_cause_id)
        update_data = payload.model_dump(exclude_unset=True)
        if "name" in update_data and update_data["name"]:
            clash = (
                self.db.query(ComplaintRootCause)
                .filter(func.lower(ComplaintRootCause.name) == update_data["name"].lower(),
                        ComplaintRootCause.id != root_cause_id)
                .first()
            )
            if clash:
                raise handle_conflict(f"A complaint root cause named '{update_data['name']}' already exists.")
        for key, value in update_data.items():
            setattr(row, key, value)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_root_cause(self, root_cause_id: str):
        row = self.get_root_cause(root_cause_id)
        in_use = (
            self.db.query(func.count(Complaint.id))
            .filter(Complaint.root_cause_id == root_cause_id)
            .scalar()
            or 0
        )
        if in_use > 0:
            raise handle_conflict(
                f"Cannot delete — {in_use} complaint(s) still reference this root cause. "
                "Reassign or remove them first."
            )
        self.db.delete(row)
        self.db.commit()
        return {"message": "Complaint root cause deleted successfully"}


class ComplaintResolutionService:
    """CRUD service for complaint resolutions."""

    def __init__(self, db: Session):
        self.db = db

    def list_resolutions(self, page: int = 1, limit: int = 50, query: Optional[str] = None,
                         is_active: Optional[bool] = None):
        q = self.db.query(ComplaintResolution)
        if query:
            term = f"%{query.strip()}%"
            q = q.filter(or_(ComplaintResolution.name.ilike(term),
                             ComplaintResolution.description.ilike(term)))
        if is_active is not None:
            q = q.filter(ComplaintResolution.is_active.is_(is_active))

        total = q.count()
        offset = (page - 1) * limit
        rows = q.order_by(ComplaintResolution.name.asc()).offset(offset).limit(limit).all()
        if not rows:
            return {"data": [], "pagination": {"total": 0, "page": page, "limit": limit}, "empty": True}

        ids = [r.id for r in rows]
        counts = (
            self.db.query(Complaint.resolution_id, func.count(Complaint.id))
            .filter(Complaint.resolution_id.in_(ids))
            .group_by(Complaint.resolution_id)
            .all()
        )
        count_by_id = {str(rid): c for rid, c in counts}
        data = [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "is_active": r.is_active,
                # Hand-built dicts silently drop any field not named here - inheriting it
                # on the response model is NOT enough. The column reached the detail
                # endpoint and this one returned the schema default, so the list showed
                # every resolution as not raising a job while the database said otherwise.
                "requires_service_job": r.requires_service_job,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "complaint_count": count_by_id.get(r.id, 0),
            }
            for r in rows
        ]
        return {"data": data, "pagination": {"total": total, "page": page, "limit": limit}, "empty": total == 0}

    def get_resolution(self, resolution_id: str) -> ComplaintResolution:
        row = self.db.query(ComplaintResolution).filter(ComplaintResolution.id == resolution_id).first()
        if not row:
            raise handle_not_found("Complaint resolution", resolution_id)
        return row

    def create_resolution(self, payload: ComplaintResolutionCreate) -> ComplaintResolution:
        existing = (
            self.db.query(ComplaintResolution)
            .filter(func.lower(ComplaintResolution.name) == payload.name.lower())
            .first()
        )
        if existing:
            raise handle_conflict(f"A complaint resolution named '{payload.name}' already exists.")
        row = ComplaintResolution(**payload.model_dump())
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_resolution(self, resolution_id: str, payload: ComplaintResolutionUpdate) -> ComplaintResolution:
        row = self.get_resolution(resolution_id)
        update_data = payload.model_dump(exclude_unset=True)
        if "name" in update_data and update_data["name"]:
            clash = (
                self.db.query(ComplaintResolution)
                .filter(func.lower(ComplaintResolution.name) == update_data["name"].lower(),
                        ComplaintResolution.id != resolution_id)
                .first()
            )
            if clash:
                raise handle_conflict(f"A complaint resolution named '{update_data['name']}' already exists.")
        for key, value in update_data.items():
            setattr(row, key, value)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_resolution(self, resolution_id: str):
        row = self.get_resolution(resolution_id)
        in_use = (
            self.db.query(func.count(Complaint.id))
            .filter(Complaint.resolution_id == resolution_id)
            .scalar()
            or 0
        )
        if in_use > 0:
            raise handle_conflict(
                f"Cannot delete — {in_use} complaint(s) still reference this resolution. "
                "Reassign or remove them first."
            )
        self.db.delete(row)
        self.db.commit()
        return {"message": "Complaint resolution deleted successfully"}
