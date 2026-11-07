"""Saved accessories box designs (PRICETAG-ACCESSORY-DESIGNER).

A preset is the shared design of an `accessories` layer; a box carries `props.presetId` and follows
it (live link). Saving a new design writes it into EVERY linked box in every tag template, tag
template version, tag sheet draft and tag sheet version of the same company; deleting the preset
removes `presetId` from those boxes, each keeping its current design.

Company scoped like `tag_size_service` (explicit predicate, not only the session listener). The
version tables are not company owned, so each is joined to its parent. Walks both document shapes
(a template's bare `layers`, a tag sheet's `sheets[].tags[].layers`) as
`asset_service._rewrite_font_family_in_doc` does.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.dealer_kit import (
    AccessoryBoxPreset,
    Page,
    PageVersion,
    TagTemplate,
    TagTemplateVersion,
)
from app.schemas.accessory_template import PER_BOX_KEYS
from app.services.company_scope import build_company_predicate, get_company_scope
from app.services.error_handler import AppException

KEEP_PER_BOX = ("subjectSlot", "subjectPart")


def _not_found() -> AppException:
    return AppException(status_code=404, message="Accessories template not found.", code="NOT_FOUND")


def _duplicate_name(name: str) -> AppException:
    return AppException(
        status_code=409,
        message=f'An accessories template named "{name}" already exists.',
        code="DUPLICATE_NAME",
    )


def _scoped(db: Session, model) -> Query:
    query = db.query(model)
    predicate = build_company_predicate(model, get_company_scope(db))
    return query if predicate is None else query.filter(predicate)


def _scope_filter(query: Query, model, db: Session) -> Query:
    predicate = build_company_predicate(model, get_company_scope(db))
    return query if predicate is None else query.filter(predicate)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


def _shapes(preset_id: str) -> List[dict]:
    layer = {"type": "accessories", "props": {"presetId": preset_id}}
    return [{"layers": [layer]}, {"sheets": [{"tags": [{"layers": [layer]}]}]}]


def _layer_lists(doc: Optional[dict]) -> Iterable[list]:
    if not doc:
        return
    yield doc.get("layers") or []
    for sheet in doc.get("sheets") or []:
        for tag in (sheet or {}).get("tags") or []:
            yield (tag or {}).get("layers") or []


def _linked_boxes(doc: Optional[dict], preset_id: str) -> List[dict]:
    out = []
    for layers in _layer_lists(doc):
        for layer in layers:
            if not isinstance(layer, dict) or layer.get("type") != "accessories":
                continue
            props = layer.get("props")
            if isinstance(props, dict) and props.get("presetId") == preset_id:
                out.append(layer)
    return out


def _doc_rows(db: Session, preset_id: str) -> List[Tuple[Any, str]]:
    """Every row whose document might link `preset_id`, as `(row, attribute holding the doc)`."""
    shapes = _shapes(preset_id)

    def has(column):
        return or_(*[column.contains(shape) for shape in shapes])

    rows: List[Tuple[Any, str]] = []
    for row in _scoped(db, TagTemplate).filter(has(TagTemplate.doc)).all():
        rows.append((row, "doc"))
    versions = (
        _scope_filter(
            db.query(TagTemplateVersion).join(TagTemplate, TagTemplateVersion.template_id == TagTemplate.id),
            TagTemplate,
            db,
        )
        .filter(has(TagTemplateVersion.doc))
        .all()
    )
    rows.extend((row, "doc") for row in versions)
    for row in _scoped(db, Page).filter(has(Page.draft_doc)).all():
        rows.append((row, "draft_doc"))
    page_versions = (
        _scope_filter(
            db.query(PageVersion).join(Page, PageVersion.page_id == Page.id), Page, db
        )
        .filter(has(PageVersion.doc))
        .all()
    )
    rows.extend((row, "doc") for row in page_versions)
    return rows


def _propagate(db: Session, preset_id: str, design: Optional[Dict[str, Any]]) -> int:
    """Write `design` into every linked box (or, with `design=None`, drop their link). Flushes only.
    Returns the number of boxes touched."""
    touched = 0
    for row, attribute in _doc_rows(db, preset_id):
        boxes = _linked_boxes(getattr(row, attribute), preset_id)
        if not boxes:
            continue
        for layer in boxes:
            old = layer["props"]
            if design is None:
                layer["props"] = {key: value for key, value in old.items() if key != "presetId"}
            else:
                layer["props"] = {
                    **copy.deepcopy(design),
                    "kind": "accessories",
                    "presetId": preset_id,
                    **{key: old[key] for key in KEEP_PER_BOX if key in old},
                }
            touched += 1
        flag_modified(row, attribute)
    db.flush()
    return touched


def usage(db: Session, preset_id: str) -> List[Dict[str, str]]:
    """Tag templates (their draft) with a box linked to `preset_id`; archived ones are hidden."""
    rows = (
        _scoped(db, TagTemplate)
        .filter(TagTemplate.archived_at.is_(None))
        .filter(or_(*[TagTemplate.doc.contains(shape) for shape in _shapes(preset_id)]))
        .order_by(TagTemplate.name)
        .all()
    )
    return [{"id": row.id, "name": row.name} for row in rows if _linked_boxes(row.doc, preset_id)]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_presets(db: Session) -> List[AccessoryBoxPreset]:
    return _scoped(db, AccessoryBoxPreset).order_by(func.lower(AccessoryBoxPreset.name), AccessoryBoxPreset.id).all()


def get_preset(db: Session, preset_id: str) -> AccessoryBoxPreset:
    row = _scoped(db, AccessoryBoxPreset).filter(AccessoryBoxPreset.id == str(preset_id)).first()
    if row is None:
        raise _not_found()
    return row


def _refuse_taken(db: Session, name: str, company_id: Optional[str], except_id: Optional[str] = None) -> None:
    query = db.query(AccessoryBoxPreset.id).filter(func.lower(AccessoryBoxPreset.name) == name.lower())
    if company_id is None:
        query = query.filter(AccessoryBoxPreset.company_id.is_(None))
    else:
        query = query.filter(AccessoryBoxPreset.company_id == company_id)
    if except_id:
        query = query.filter(AccessoryBoxPreset.id != except_id)
    if query.first() is not None:
        raise _duplicate_name(name)


def _scope_company(db: Session) -> Optional[str]:
    scope = get_company_scope(db)
    if isinstance(scope, (set, frozenset)) and len(scope) == 1:
        return next(iter(scope))
    return None


def create_preset(db: Session, *, name: str, design: Dict[str, Any], user_id: Optional[str]) -> AccessoryBoxPreset:
    row = AccessoryBoxPreset(name=name, design=design, created_by=user_id, updated_by=user_id)
    # The mixin stamps company_id on insert; the pre-check reads under the same scope.
    _refuse_taken(db, name, _scope_company(db))
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
    design: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> Tuple[AccessoryBoxPreset, int]:
    """Returns `(row, boxes rewritten)`. A new design is written into every linked box first."""
    row = get_preset(db, preset_id)
    if name is not None and name.lower() != row.name.lower():
        _refuse_taken(db, name, row.company_id, except_id=row.id)
    rewritten = 0
    try:
        if name is not None:
            row.name = name
        if design is not None:
            row.design = design
            rewritten = _propagate(db, row.id, design)
        row.updated_by = user_id
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate_name(name or row.name) from exc
    db.refresh(row)
    return row, rewritten


def delete_preset(db: Session, preset_id: str) -> dict:
    """The immediate delete; the deferred `accessory_box_preset.delete` calls this same function.
    Every linked box loses its `presetId` and keeps its current design."""
    row = get_preset(db, preset_id)
    detached = _propagate(db, row.id, None)
    db.delete(row)
    db.commit()
    return {"deleted": 1, "detached": detached}


__all__ = ["PER_BOX_KEYS"]
