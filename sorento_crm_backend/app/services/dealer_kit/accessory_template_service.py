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
from datetime import datetime, timezone
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


def _naive(value: datetime) -> datetime:
    """The column is a naive UTC timestamp; a client may send the same instant with a zone."""
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


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


def _doc_rows(db: Session, preset: AccessoryBoxPreset) -> List[Tuple[Any, str]]:
    """Every row of the PRESET'S OWN company whose document might link it, as `(row, attribute holding the
    doc)`. The company is filtered explicitly (versions through their template, page versions through
    their page), so an all-company session scope can never reach another company's document."""
    shapes = _shapes(preset.id)
    company = preset.company_id

    def has(column):
        return or_(*[column.contains(shape) for shape in shapes])

    def mine(model):
        return model.company_id == company if company is not None else model.company_id.is_(None)

    rows: List[Tuple[Any, str]] = []
    for row in _scoped(db, TagTemplate).filter(mine(TagTemplate), has(TagTemplate.doc)).all():
        rows.append((row, "doc"))
    versions = (
        db.query(TagTemplateVersion)
        .join(TagTemplate, TagTemplateVersion.template_id == TagTemplate.id)
        .filter(mine(TagTemplate), has(TagTemplateVersion.doc))
        .all()
    )
    rows.extend((row, "doc") for row in versions)
    for row in _scoped(db, Page).filter(mine(Page), has(Page.draft_doc)).all():
        rows.append((row, "draft_doc"))
    page_versions = (
        db.query(PageVersion)
        .join(Page, PageVersion.page_id == Page.id)
        .filter(mine(Page), has(PageVersion.doc))
        .all()
    )
    rows.extend((row, "doc") for row in page_versions)
    return rows


def _propagate(db: Session, preset: AccessoryBoxPreset, design: Optional[Dict[str, Any]]) -> int:
    """Write `design` into every linked box (or, with `design=None`, drop their link). Flushes only.
    Returns the number of boxes touched."""
    touched = 0
    preset_id = preset.id
    for row, attribute in _doc_rows(db, preset):
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


def _live_templates(db: Session, preset_ids: List[str]) -> List[TagTemplate]:
    """Non-archived tag templates (in scope) whose draft might link any of `preset_ids`: ONE query."""
    if not preset_ids:
        return []
    return (
        _scoped(db, TagTemplate)
        .filter(TagTemplate.archived_at.is_(None))
        .filter(or_(*[TagTemplate.doc.contains(shape) for pid in preset_ids for shape in _shapes(pid)]))
        .order_by(TagTemplate.name)
        .all()
    )


def usage(db: Session, preset_id: str) -> List[Dict[str, str]]:
    """Tag templates (their draft) with a box linked to `preset_id`; archived ones are hidden."""
    return [
        {"id": row.id, "name": row.name}
        for row in _live_templates(db, [preset_id])
        if _linked_boxes(row.doc, preset_id)
    ]


def usage_counts(db: Session, preset_ids: List[str]) -> Dict[str, int]:
    """`{preset_id: number of tag templates linking it}` for all of them in one pass."""
    wanted = set(preset_ids)
    counts: Dict[str, int] = {pid: 0 for pid in wanted}
    for row in _live_templates(db, list(wanted)):
        found = {
            layer["props"]["presetId"]
            for layers in _layer_lists(row.doc)
            for layer in layers
            if isinstance(layer, dict)
            and layer.get("type") == "accessories"
            and isinstance(layer.get("props"), dict)
            and layer["props"].get("presetId") in wanted
        }
        for pid in found:
            counts[pid] += 1
    return counts


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_presets(db: Session) -> List[AccessoryBoxPreset]:
    return _scoped(db, AccessoryBoxPreset).order_by(func.lower(AccessoryBoxPreset.name), AccessoryBoxPreset.id).all()


def get_preset(db: Session, preset_id: str, *, lock: bool = False) -> AccessoryBoxPreset:
    query = _scoped(db, AccessoryBoxPreset).filter(AccessoryBoxPreset.id == str(preset_id))
    row = (query.with_for_update() if lock else query).first()
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
    base_updated_at: Optional[datetime] = None,
) -> Tuple[AccessoryBoxPreset, int]:
    """Returns `(row, boxes rewritten)`. A new design is written into every linked box first.

    `base_updated_at` is the version the caller's design was based on: when given and it is not the row's
    current `updated_at`, someone saved in between and nothing is written (409 STALE_TEMPLATE)."""
    # Locked FOR UPDATE before the base check: two saves with the same base cannot both pass it.
    row = get_preset(db, preset_id, lock=True)
    if base_updated_at is not None and _naive(base_updated_at) != row.updated_at:
        raise AppException(
            status_code=409,
            message="This accessories template was changed elsewhere.",
            code="STALE_TEMPLATE",
        )
    if name is not None and name.lower() != row.name.lower():
        _refuse_taken(db, name, row.company_id, except_id=row.id)
    rewritten = 0
    try:
        if name is not None:
            row.name = name
        if design is not None:
            row.design = design
            rewritten = _propagate(db, row, design)
        row.updated_by = user_id
        # Stamped here (microseconds, wall clock), not by the database's transaction clock: it is the
        # version marker `base_updated_at` is compared with, so every write must move it.
        if design is not None:
            row.updated_at = datetime.utcnow()
        else:
            # A rename is not a new version of the design: keep `updated_at` (the column's onupdate would
            # move it), so an unpushed design edit based on the current version still lands.
            flag_modified(row, "updated_at")
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
    detached = _propagate(db, row, None)
    db.delete(row)
    db.commit()
    return {"deleted": 1, "detached": detached}


__all__ = ["PER_BOX_KEYS"]
