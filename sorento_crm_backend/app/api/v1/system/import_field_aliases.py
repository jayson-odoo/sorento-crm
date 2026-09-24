"""Import column mappings - which header spelling resolves to which field, per document
type (S5, `scm-supplier-documents-pi-first-acceptance-criteria.md`, section E, AC-E1).

A supplier renaming a header (`箱数` -> `箱數`) used to need a code change to fix - this
page/API makes the alias table (`import_field_alias`, already the whole mechanism every
reader resolves through) an admin surface instead: list what is mapped, add a mapping, take
one away. `fields` answers "map this header to WHAT" from the reader's own declared field
set (`import_alias_service.canonical_fields`), never a hand-typed list that drifts from it.
"""
from __future__ import annotations

import uuid as _uuid
from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.import_alias import ImportFieldAlias
from app.services.error_handler import AppException
from app.services.field_access import field_label
from app.services.import_alias_service import canonical_fields
from app.services.scm.supplier_code_composer import WORD_DOC_TYPE, WORD_TOKEN_RE

router = APIRouter()

#: How each document type reads on screen - the 409 above is shown to an operator, and
#: "packing_list" is our column name, not their word for the document.
_DOC_TYPE_LABELS = {
    "proforma_invoice": "proforma invoices",
    "packing_list": "packing lists",
    "outstanding_so": "outstanding sales orders",
    "supplier_inventory_word": "stock list words",
}

_VIEW = require_permission("system.import_field_aliases.view")
_EDIT = require_permission("system.import_field_aliases.edit")


class ImportFieldAliasCreate(BaseModel):
    # Bounded to the columns' own widths (`import_field_alias`): a body longer than the
    # column is a 422 on the way in rather than a DataError out of the driver.
    doc_type: str = Field(..., min_length=1, max_length=64)
    field: str = Field(..., min_length=1, max_length=64)
    alias: str = Field(..., min_length=1, max_length=255)
    locale: Optional[str] = Field(None, max_length=8)
    # NULL = a shared row, answering for every supplier (D6). Only meaningful for
    # `supplier_inventory_word`; a caller may still send it for another doc type and the row
    # simply carries a supplier it will never be looked up by.
    supplier_id: Optional[str] = None

    @field_validator("supplier_id")
    @classmethod
    def _blank_supplier_id_is_none(cls, value: Optional[str]) -> Optional[str]:
        """A cleared `SearchableSelect` posts `""`, not the field's absence (review round 2,
        item 3) - `""` is not a uuid, so `_assert_supplier_exists`'s `is_uuid` guard would
        reject it as 422 rather than reading it as "no supplier chosen" the way `None` does.
        Normalised here, once, rather than every caller re-deriving "falsy means None"."""
        return value or None


def _label_for(doc_type: str, field: str) -> str:
    """The screen's own label for a field - `field_access.field_label`'s title-case fallback
    for everything else, but the field VERBATIM for a word token (review round 1, item 2):
    `field_label`'s `.capitalize()` fallback turned `SRT` into `Srt` and `HP` into `Hp`,
    which is not a spelling anyone chose - the word list's whole vocabulary is exactly what
    was typed on the form (`WORD_TOKEN_RE`), so nothing here should reshape it."""
    if doc_type == WORD_DOC_TYPE:
        return field
    return field_label(field)


def _assert_known_field(doc_type: str, field: str) -> None:
    """A mapping only means something for a field one of the readers actually asks for
    (AC-E1): the resolver looks up `canonical_fields(doc_type)` and nothing else, so a row
    naming a document type with no reader, or a field that reader never reads, is a row
    that can never resolve anything - and it would sit on the settings page looking as if
    it had.

    `supplier_inventory_word` is the one exception (review round 1, item 4): its vocabulary
    is OPEN, so `canonical_fields` deliberately answers `[]` for it and membership is not
    what decides a valid field - shape is (`WORD_TOKEN_RE`).
    """
    if doc_type == WORD_DOC_TYPE:
        if not WORD_TOKEN_RE.match(field):
            raise AppException(
                422,
                f"'{field}' is not a valid stock-list word token "
                "(1-10 uppercase letters/digits).",
                detail="field",
            )
        return
    known = canonical_fields(doc_type)
    if not known:
        raise AppException(
            422, f"'{doc_type}' is not a document type this system reads.", detail="doc_type"
        )
    if field not in known:
        raise AppException(
            422,
            f"'{field}' is not a field the {doc_type} reader asks for.",
            detail="field",
        )


def _assert_supplier_exists(db: Session, supplier_id: Optional[str]) -> None:
    """A word row scoped to a supplier that does not exist would sit on the page unable to
    ever apply - the composer looks suppliers up by id, never by name.

    A value that is not a uuid at all (review round 1, item 6) is rejected the same way as
    an unknown id, rather than reaching the uuid column comparison - which raises
    `InvalidTextRepresentation`, not an `AppException`, and leaves the session aborted.

    `is None`, not a truthiness check (review round 2, item 3): the Pydantic model already
    normalises a posted `""` to `None`, and an explicit check here means a FUTURE caller
    that skips that normalisation gets the 422 `is_uuid` would have given it anyway, rather
    than a falsy-string silently reading as "no supplier chosen".
    """
    if supplier_id is None:
        return
    from app.models.procurement import Supplier
    from app.services.scm.supplier_scope import is_uuid

    if not is_uuid(supplier_id):
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")
    if db.query(Supplier.id).filter(Supplier.id == supplier_id).first() is None:
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")


def _serialize_alias(row: ImportFieldAlias, supplier_names: Optional[dict[str, str]] = None) -> dict:
    supplier_names = supplier_names or {}
    supplier_id = str(row.supplier_id) if row.supplier_id else None
    return {
        "id": str(row.id),
        "alias": row.alias,
        "locale": row.locale,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        # No UUID in the UI: the id travels for a delete action, the name is what renders.
        "supplier_id": supplier_id,
        "supplier_name": supplier_names.get(supplier_id) if supplier_id else None,
    }


def _supplier_names(db: Session, rows: list[ImportFieldAlias]) -> dict[str, str]:
    ids = {str(r.supplier_id) for r in rows if r.supplier_id}
    if not ids:
        return {}
    from app.models.procurement import Supplier

    return {
        str(sid): name
        for sid, name in db.query(Supplier.id, Supplier.supplier_name)
        .filter(Supplier.id.in_(ids))
        .all()
    }


def _grouped_aliases(db: Session, doc_type: str) -> dict[str, list[dict]]:
    rows = (
        db.query(ImportFieldAlias)
        .filter(ImportFieldAlias.doc_type == doc_type)
        .order_by(ImportFieldAlias.field, ImportFieldAlias.alias)
        .all()
    )
    names = _supplier_names(db, rows)
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row.field, []).append(_serialize_alias(row, names))
    return grouped


@router.get("/import-field-aliases")
def list_import_field_aliases(
    doc_type: str,
    _user: dict = Depends(_VIEW),
    db: Session = Depends(get_db),
):
    """Every SYSTEM field of this document type - even one with no alias yet - each
    carrying every header on file that resolves to it."""
    grouped = _grouped_aliases(db, doc_type)
    fields = sorted(set(canonical_fields(doc_type)) | set(grouped))
    return [
        {"field": f, "label": _label_for(doc_type, f), "aliases": grouped.get(f, [])}
        for f in fields
    ]


@router.get("/import-field-aliases/fields")
def list_import_field_alias_fields(
    doc_type: str,
    _user: dict = Depends(_VIEW),
):
    """The canonical field names this document type's own reader asks for."""
    return [{"field": f, "label": _label_for(doc_type, f)} for f in canonical_fields(doc_type)]


@router.post("/import-field-aliases", status_code=status.HTTP_201_CREATED)
def create_import_field_alias(
    payload: ImportFieldAliasCreate,
    _user: dict = Depends(_EDIT),
    db: Session = Depends(get_db),
):
    """One new header spelling for a field. 409 on a triple already on file."""
    # An open-vocabulary word token is uppercased on write (review round 1, item 4) - the
    # shape check and every later lookup then sees exactly what it validated.
    field_value = (
        payload.field.strip().upper() if payload.doc_type == WORD_DOC_TYPE else payload.field
    )
    _assert_known_field(payload.doc_type, field_value)
    _assert_supplier_exists(db, payload.supplier_id)
    # Matched on the triple WITHIN THE SAME SCOPE (owner ruling A, review round 2, migration
    # `ifa_supplier_uniq` - supersedes review round 3's note that used to live here): a
    # shared row (`supplier_id` NULL) duplicates only another shared row on the same
    # triple - a second supplier saving the identical (doc_type, field, alias) triple is
    # not a duplicate of a DIFFERENT supplier's row, it is that supplier's own first row,
    # exactly what the DB itself now allows (R11). A SUPPLIER payload additionally checks
    # against a SHARED row on the same triple, because that one genuinely IS redundant -
    # the shared row already answers this supplier's header the same way theirs would, the
    # same rule `import_mapping_service.save()` uses to skip writing one (R19's kept half).
    existing_query = db.query(ImportFieldAlias).filter(
        ImportFieldAlias.doc_type == payload.doc_type,
        ImportFieldAlias.field == field_value,
        ImportFieldAlias.alias == payload.alias,
    )
    if payload.supplier_id:
        existing_query = existing_query.filter(
            or_(
                ImportFieldAlias.supplier_id.is_(None),
                ImportFieldAlias.supplier_id == payload.supplier_id,
            )
        )
    else:
        existing_query = existing_query.filter(ImportFieldAlias.supplier_id.is_(None))
    existing = existing_query.first()
    if existing is not None:
        if existing.supplier_id is None:
            message = (
                f"Header {payload.alias} is already the shared mapping to "
                f"{_label_for(payload.doc_type, field_value)} for "
                f"{_DOC_TYPE_LABELS.get(payload.doc_type, payload.doc_type)}."
            )
        else:
            supplier_name = _supplier_names(db, [existing]).get(str(existing.supplier_id))
            scope = f" ({supplier_name})" if supplier_name else " (this supplier)"
            message = (
                f"Header {payload.alias} is already mapped to "
                f"{_label_for(payload.doc_type, field_value)} for "
                f"{_DOC_TYPE_LABELS.get(payload.doc_type, payload.doc_type)}{scope}."
            )
        raise AppException(status.HTTP_409_CONFLICT, message, code="duplicate_alias")
    row = ImportFieldAlias(
        doc_type=payload.doc_type, field=field_value, alias=payload.alias,
        locale=payload.locale, supplier_id=payload.supplier_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    siblings = (
        db.query(ImportFieldAlias)
        .filter(
            ImportFieldAlias.doc_type == payload.doc_type,
            ImportFieldAlias.field == field_value,
        )
        .order_by(ImportFieldAlias.alias)
        .all()
    )
    names = _supplier_names(db, siblings)
    return {
        "field": field_value,
        "label": _label_for(payload.doc_type, field_value),
        "aliases": [_serialize_alias(r, names) for r in siblings],
    }


@router.delete("/import-field-aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_import_field_alias(
    alias_id: str,
    _user: dict = Depends(_EDIT),
    db: Session = Depends(get_db),
):
    """Forget this mapping - the header goes back to reading as unmapped."""
    # A path segment that is not a uuid is a 404, not the DataError the uuid column raises
    # when a bad link is followed.
    try:
        _uuid.UUID(str(alias_id))
    except (ValueError, AttributeError, TypeError):
        raise AppException(404, "That mapping does not exist.", detail="alias_id") from None
    row = db.query(ImportFieldAlias).filter(ImportFieldAlias.id == alias_id).first()
    if row is None:
        raise AppException(404, "That mapping does not exist.", detail="alias_id")
    db.delete(row)
    db.commit()
