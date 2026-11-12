from __future__ import annotations
import uuid
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.lookup import LookupOption, LookupOptionKeyword
from app.schemas.lookup import LookupOptionCreate, LookupOptionUpdate, LookupKeywordIn
from app.services import project_party_roles
from app.services.error_handler import handle_not_found, handle_conflict


class LookupOptionService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, set_id: str, *, page: int = 1, limit: int = 100):
        q = self.db.query(LookupOption).filter(LookupOption.set_id == set_id).order_by(
            LookupOption.sort_order.asc(), LookupOption.label.asc())
        total = q.count()
        offset = (page - 1) * limit
        rows = q.offset(offset).limit(limit).all()
        return {"data": rows, "pagination": {"total": total, "page": page, "limit": limit},
                "empty": total == 0}

    def get(self, option_id: str, set_id: Optional[str] = None) -> LookupOption:
        q = self.db.query(LookupOption).filter(LookupOption.id == option_id)
        # Found through its own set only (security review N1): the URL names the set.
        if set_id is not None:
            q = q.filter(LookupOption.set_id == set_id)
        o = q.first()
        if not o:
            raise handle_not_found("LookupOption", option_id)
        return o

    def _check_value_unique(self, set_id: str, value: str, exclude_id: Optional[str] = None):
        from sqlalchemy import func
        q = self.db.query(LookupOption).filter(
            LookupOption.set_id == set_id,
            func.lower(LookupOption.value) == value.lower(),
        )
        if exclude_id:
            q = q.filter(LookupOption.id != exclude_id)
        if q.first():
            raise handle_conflict(f"Option value '{value}' already exists in this set")

    def _replace_keywords(self, option: LookupOption, items: List[LookupKeywordIn]):
        self.db.query(LookupOptionKeyword).filter(
            LookupOptionKeyword.option_id == option.id).delete(synchronize_session=False)
        seen = set()
        for kw in items:
            norm = (kw.keyword or "").strip().lower()
            if not norm:
                continue
            key = (norm, kw.locale)
            if key in seen:
                continue
            seen.add(key)
            self.db.add(LookupOptionKeyword(
                id=str(uuid.uuid4()), option_id=option.id,
                keyword=norm, locale=kw.locale,
            ))

    def create(self, set_id: str, data: LookupOptionCreate) -> LookupOption:
        self._check_value_unique(set_id, data.value)
        o = LookupOption(
            id=str(uuid.uuid4()), set_id=set_id,
            value=data.value, label=data.label,
            sort_order=data.sort_order, is_active=data.is_active,
            description=data.description, allows_many=data.allows_many,
        )
        self.db.add(o)
        self.db.flush()
        self._replace_keywords(o, data.keywords)
        self.db.commit()
        self.db.refresh(o)
        return o

    def update(self, option_id: str, data: LookupOptionUpdate, set_id: Optional[str] = None) -> LookupOption:
        o = self.get(option_id, set_id)
        update = data.model_dump(exclude_unset=True)
        if update.get("allows_many") is None:
            update.pop("allows_many", None)
        project_party_roles.assert_option_change(
            self.db, o, new_value=update.get("value"), deactivate=update.get("is_active") is False
        )
        if "value" in update and update["value"].lower() != (o.value or "").lower():
            self._check_value_unique(o.set_id, update["value"], exclude_id=o.id)
        new_keywords = update.pop("keywords", None)
        for k, v in update.items():
            setattr(o, k, v)
        if new_keywords is not None:
            self._replace_keywords(o, [LookupKeywordIn(**k) if isinstance(k, dict) else k for k in new_keywords])
        self.db.commit()
        self.db.refresh(o)
        return o

    def delete(self, option_id: str, set_id: Optional[str] = None) -> dict:
        o = self.get(option_id, set_id)
        project_party_roles.assert_option_change(self.db, o, delete=True)
        self.db.delete(o)
        self.db.commit()
        return {"message": "Option deleted"}
