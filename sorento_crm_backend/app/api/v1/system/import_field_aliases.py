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
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.import_alias import ImportFieldAlias
from app.services.error_handler import AppException
from app.services.field_access import field_label
from app.services.import_alias_service import canonical_fields

router = APIRouter()

#: How each document type reads on screen - the 409 above is shown to an operator, and
#: "packing_list" is our column name, not their word for the document.
_DOC_TYPE_LABELS = {
    "proforma_invoice": "proforma invoices",
    "packing_list": "packing lists",
    "outstanding_so": "outstanding sales orders",
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


def _assert_known_field(doc_type: str, field: str) -> None:
    """A mapping only means something for a field one of the readers actually asks for
    (AC-E1): the resolver looks up `canonical_fields(doc_type)` and nothing else, so a row
    naming a document type with no reader, or a field that reader never reads, is a row
    that can never resolve anything - and it would sit on the settings page looking as if
    it had."""
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


def _serialize_alias(row: ImportFieldAlias) -> dict:
    return {
        "id": str(row.id),
        "alias": row.alias,
        "locale": row.locale,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _grouped_aliases(db: Session, doc_type: str) -> dict[str, list[dict]]:
    rows = (
        db.query(ImportFieldAlias)
        .filter(ImportFieldAlias.doc_type == doc_type)
        .order_by(ImportFieldAlias.field, ImportFieldAlias.alias)
        .all()
    )
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row.field, []).append(_serialize_alias(row))
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
        {"field": f, "label": field_label(f), "aliases": grouped.get(f, [])} for f in fields
    ]


@router.get("/import-field-aliases/fields")
def list_import_field_alias_fields(
    doc_type: str,
    _user: dict = Depends(_VIEW),
):
    """The canonical field names this document type's own reader asks for."""
    return [{"field": f, "label": field_label(f)} for f in canonical_fields(doc_type)]


@router.post("/import-field-aliases", status_code=status.HTTP_201_CREATED)
def create_import_field_alias(
    payload: ImportFieldAliasCreate,
    _user: dict = Depends(_EDIT),
    db: Session = Depends(get_db),
):
    """One new header spelling for a field. 409 on a triple already on file."""
    _assert_known_field(payload.doc_type, payload.field)
    existing = (
        db.query(ImportFieldAlias)
        .filter(
            ImportFieldAlias.doc_type == payload.doc_type,
            ImportFieldAlias.field == payload.field,
            ImportFieldAlias.alias == payload.alias,
        )
        .first()
    )
    if existing is not None:
        raise AppException(
            status.HTTP_409_CONFLICT,
            f"Header {payload.alias} is already mapped to "
            f"{field_label(payload.field)} for {_DOC_TYPE_LABELS.get(payload.doc_type, payload.doc_type)}.",
            code="duplicate_alias",
        )
    row = ImportFieldAlias(
        doc_type=payload.doc_type, field=payload.field, alias=payload.alias,
        locale=payload.locale,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    siblings = (
        db.query(ImportFieldAlias)
        .filter(
            ImportFieldAlias.doc_type == payload.doc_type,
            ImportFieldAlias.field == payload.field,
        )
        .order_by(ImportFieldAlias.alias)
        .all()
    )
    return {
        "field": payload.field,
        "label": field_label(payload.field),
        "aliases": [_serialize_alias(r) for r in siblings],
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
