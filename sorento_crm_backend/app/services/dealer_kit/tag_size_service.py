"""Tag size preset CRUD (PLAN-price-tag-ux-r3.md S4, D2).

A saved, named tag size - a shortcut the request designer's Tag Size dropdown
offers under "Saved sizes", editable at `/dealer-kit/tag-sizes`. Company
scoped like `tag_template_service`, and for the same reason: `_scoped` splices
the company predicate explicitly rather than leaning only on the
`do_orm_execute` listener, so a delete's safety does not depend on that
listener happening to be installed (see the module docstring on
`tag_template_service.py` for the full argument).

Unique per `(company_id, name)` at the database - `create_preset`/
`update_preset` catch the resulting `IntegrityError` and translate it to a 409
rather than pre-checking, which would still race under concurrent writers.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session

from app.models.dealer_kit import TagSizePreset
from app.services.company_scope import build_company_predicate, get_company_scope
from app.services.error_handler import AppException


def _not_found() -> AppException:
    return AppException(status_code=404, message="Tag size not found.", code="NOT_FOUND")


def _duplicate_name(name: str) -> AppException:
    return AppException(
        status_code=409,
        message=f'A tag size named "{name}" already exists.',
        code="DUPLICATE_NAME",
    )


def _scoped(db: Session) -> Query:
    query = db.query(TagSizePreset)
    predicate = build_company_predicate(TagSizePreset, get_company_scope(db))
    return query if predicate is None else query.filter(predicate)


def list_presets(db: Session) -> list[TagSizePreset]:
    return _scoped(db).order_by(TagSizePreset.name).all()


def get_preset(db: Session, preset_id: str) -> TagSizePreset:
    row = _scoped(db).filter(TagSizePreset.id == str(preset_id)).first()
    if row is None:
        raise _not_found()
    return row


def create_preset(
    db: Session,
    *,
    name: str,
    width_mm: float,
    height_mm: float,
    created_by: Optional[str] = None,
) -> TagSizePreset:
    row = TagSizePreset(
        name=name, width_mm=width_mm, height_mm=height_mm, created_by=created_by
    )
    db.add(row)
    try:
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate_name(name) from exc
    db.refresh(row)
    return row


def update_preset(
    db: Session,
    preset_id: str,
    *,
    name: Optional[str] = None,
    width_mm: Optional[float] = None,
    height_mm: Optional[float] = None,
) -> TagSizePreset:
    row = get_preset(db, preset_id)
    if name is not None:
        row.name = name
    if width_mm is not None:
        row.width_mm = width_mm
    if height_mm is not None:
        row.height_mm = height_mm
    try:
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate_name(name or row.name) from exc
    db.refresh(row)
    return row


def delete_preset(db: Session, preset_id: str) -> dict:
    """The immediate delete. The deferred one (`tag_size_preset.delete`, both
    the listing's row menu and the Tag Size control's saved-size `x`) calls
    the SAME function, so the two cannot drift - the exact relationship
    `tag_template_service.delete_template` has with `tag_template.delete`."""
    row = get_preset(db, preset_id)
    db.delete(row)
    db.commit()
    return {"deleted": 1}
