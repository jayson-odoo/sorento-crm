"""Generic read + annotate service for AutoCount mirror entities.

One service backs every mirror listing/detail/annotation so the behaviour cannot
drift across the 12 entities (CLAUDE.md anti-drift rule). Each route hands it the
model class and the searchable columns; everything else -- pagination, sort,
case-insensitive search, the annotation-only write -- is uniform.

Ingest owns row creation and every business column; this service writes ONLY
``internal_note``/``follow_up`` (AC-G2), so an annotation can never clobber
synced data and a re-sync can never clobber an annotation.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

from app.schemas.common import ListResponse, PaginationResponse
from app.services.error_handler import AppException


class MirrorReadService:
    def __init__(self, db: Session):
        self.db = db

    def list(
        self,
        model: type,
        *,
        search_columns: Sequence[Any],
        page: int,
        limit: int,
        query: Optional[str] = None,
        sort: Optional[str] = None,
        dir: str = "desc",
    ) -> ListResponse:
        q = self.db.query(model)
        if query:
            like = f"%{query}%"
            q = q.filter(or_(*[c.ilike(like) for c in search_columns]))

        total = q.count()

        sort_col = getattr(model, sort, None) if sort else None
        if sort_col is None:
            sort_col = model.created_at
        q = q.order_by(asc(sort_col) if dir == "asc" else desc(sort_col))

        rows = q.offset((page - 1) * limit).limit(limit).all()
        return ListResponse(
            data=rows,
            pagination=PaginationResponse(total=total, page=page, limit=limit),
            empty=total == 0,
        )

    def get(self, model: type, entity_id: str, *, resource: str) -> Any:
        row = self.db.query(model).filter(model.id == entity_id).first()
        if row is None:
            raise AppException(status_code=404, message=f"{resource} not found", code="NOT_FOUND")
        return row

    def annotate(
        self,
        model: type,
        entity_id: str,
        *,
        resource: str,
        internal_note: Optional[str],
        follow_up: Optional[bool],
        set_note: bool,
        set_follow_up: bool,
    ) -> Any:
        """Write ONLY the two annotation columns. ``set_*`` flags distinguish
        "field omitted" from "field set to null/false" so a PATCH that sends only
        ``follow_up`` does not wipe an existing note."""
        row = self.get(model, entity_id, resource=resource)
        if set_note:
            row.internal_note = internal_note
        if set_follow_up:
            row.follow_up = bool(follow_up)
        self.db.commit()
        self.db.refresh(row)
        return row
