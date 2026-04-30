from __future__ import annotations
import uuid
from typing import Optional
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from app.models.lookup import LookupSet, LookupOption, LookupBinding
from app.schemas.lookup import LookupSetCreate, LookupSetUpdate
from app.services.error_handler import handle_not_found, handle_conflict


class LookupSetService:
    def __init__(self, db: Session):
        self.db = db

    def _tenant(self) -> Optional[str]:
        # Stubbed; matches existing pattern. Returns None until real tenant resolution lands.
        return None

    def list(self, *, page: int = 1, limit: int = 50, query: Optional[str] = None):
        q = self.db.query(LookupSet)
        if query:
            q = q.filter(or_(
                LookupSet.set_key.ilike(f"%{query}%"),
                LookupSet.name.ilike(f"%{query}%"),
            ))
        q = q.order_by(LookupSet.name.asc())
        total = q.count()
        offset = (page - 1) * limit
        rows = q.offset(offset).limit(limit).all()
        if not rows:
            return {"data": [], "pagination": {"total": 0, "page": page, "limit": limit}, "empty": True}
        ids = [r.id for r in rows]
        opt_counts = dict(
            self.db.query(LookupOption.set_id, func.count(LookupOption.id))
            .filter(LookupOption.set_id.in_(ids)).group_by(LookupOption.set_id).all()
        )
        bind_counts = dict(
            self.db.query(LookupBinding.set_id, func.count(LookupBinding.id))
            .filter(LookupBinding.set_id.in_(ids)).group_by(LookupBinding.set_id).all()
        )
        data = []
        for r in rows:
            data.append({
                "id": r.id,
                "tenant_id": r.tenant_id,
                "set_key": r.set_key,
                "name": r.name,
                "description": r.description,
                "is_active": r.is_active,
                "option_count": opt_counts.get(r.id, 0),
                "binding_count": bind_counts.get(r.id, 0),
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            })
        return {"data": data, "pagination": {"total": total, "page": page, "limit": limit}, "empty": total == 0}

    def get(self, set_id: str) -> LookupSet:
        s = self.db.query(LookupSet).filter(LookupSet.id == set_id).first()
        if not s:
            raise handle_not_found("LookupSet", set_id)
        return s

    def get_by_key(self, set_key: str) -> LookupSet:
        s = self.db.query(LookupSet).filter(
            LookupSet.set_key == set_key,
            LookupSet.tenant_id.is_(self._tenant()),
        ).first()
        if not s:
            raise handle_not_found("LookupSet", set_key)
        return s

    def create(self, data: LookupSetCreate) -> LookupSet:
        existing = self.db.query(LookupSet).filter(
            LookupSet.set_key == data.set_key,
            LookupSet.tenant_id.is_(self._tenant()),
        ).first()
        if existing:
            raise handle_conflict("Lookup set key already exists.")
        s = LookupSet(
            id=str(uuid.uuid4()),
            tenant_id=self._tenant(),
            set_key=data.set_key,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
        )
        self.db.add(s)
        self.db.commit()
        self.db.refresh(s)
        return s

    def update(self, set_id: str, data: LookupSetUpdate) -> LookupSet:
        s = self.get(set_id)
        update = data.model_dump(exclude_unset=True)
        if "set_key" in update and update["set_key"] != s.set_key:
            clash = self.db.query(LookupSet).filter(
                LookupSet.set_key == update["set_key"],
                LookupSet.tenant_id.is_(self._tenant()),
                LookupSet.id != set_id,
            ).first()
            if clash:
                raise handle_conflict("Lookup set key already exists.")
        for k, v in update.items():
            setattr(s, k, v)
        self.db.commit()
        self.db.refresh(s)
        return s

    def delete(self, set_id: str) -> dict:
        s = self.get(set_id)
        self.db.delete(s)
        self.db.commit()
        return {"message": "Lookup set deleted"}
