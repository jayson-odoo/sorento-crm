"""The inline import column mapper's own two endpoints (B4/B5,
PLAN-import-column-mapper-24sep.md): probe a supplier file's headers, and save what the
operator picked. The FE's `importMappingService.ts` is the contract this module answers -
built against it first (Phase 1, mocked), wired for real here (Phase 2).

Permission (review round 1, R2): PER DOC TYPE, not one blanket gate. `require_any_permission`
alone would grant the caller's ONE permission the FULL `doc_types` list requested, so a
proforma-invoice-only uploader could save (or probe) a STOCK LIST layout through this back
door even though `/scm/supplier-inventory/*` itself refuses them. `_check_doc_type_permission`
below checks each requested doc type against exactly the permission(s) its OWN upload
endpoint accepts - `scm.proforma_invoice.upload` or `scm.reorder.run` for proforma_invoice /
packing_list (mirrors `/scm/supplier-documents/apply`'s own `_WRITE`), `scm.reorder.run` only
for supplier_inventory (mirrors `/scm/supplier-inventory/apply`'s own `_WRITE`). A caller with
neither permission at all is refused before either endpoint does any other work.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.services.import_alias_service import normalize_header
from app.services.scm import import_mapping_service
from app.services.scm.supplier_scope import assert_supplier
from app.services.scm.upload_intake import read_upload
from app.services.user_service import UserPermissionService

router = APIRouter()

#: The mapper's own doc-type vocabulary (R1) - the three doc types the mapper's readers
#: actually serve (`import_mapping_service._required_columns`); anything else (an
#: `outstanding_so` or a typo) is refused rather than silently written to a row no reader
#: will ever ask for.
DocType = Literal["proforma_invoice", "packing_list", "supplier_inventory"]

#: Which permission(s) reach EACH doc type's own upload endpoint (R2, docstring above).
_DOC_TYPE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "proforma_invoice": ("scm.proforma_invoice.upload", "scm.reorder.run"),
    "packing_list": ("scm.proforma_invoice.upload", "scm.reorder.run"),
    "supplier_inventory": ("scm.reorder.run",),
}

#: R3: `import_field_alias.alias` is `String(255)` - refused before it can crash the insert
#: into a raw Postgres `DataError` (500-shaped).
_MAX_HEADER_LENGTH = 255
#: R3: a bound on a caller-supplied array, the same shape as every other batch endpoint here
#: (`supplier_document_service.apply`'s own `_MAX_TRANSLATIONS_PER_APPLY`).
_MAX_MAPPINGS = 500


def _check_doc_type_permission(db: Session, current_user: dict, doc_types: List[str]) -> None:
    """403 the moment ONE requested doc type is not covered by any permission the caller
    holds - superadmin/admin bypass, same rule as every other permission gate here."""
    service = UserPermissionService(db)
    uid = current_user["id"]
    if service.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return
    user_slugs = service.get_user_permission_slugs(uid)
    strict = getattr(settings, "module_guard_strict", False)
    if strict:
        from app.modules.runtime.installer import DEFAULT_TENANT_ID, is_module_enabled, tenant_has_any_module_row
        from app.modules.runtime.permission_module_map import module_for_permission

    for doc_type in doc_types:
        allowed = _DOC_TYPE_PERMISSIONS.get(doc_type, ())
        held = [slug for slug in allowed if slug in user_slugs]
        if not held:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of these permissions required for {doc_type}: {', '.join(allowed)}",
            )
        if strict and tenant_has_any_module_row(db, DEFAULT_TENANT_ID):
            module_ok = any(
                not (mod := module_for_permission(slug)) or is_module_enabled(db, DEFAULT_TENANT_ID, mod)
                for slug in held
            )
            if not module_ok:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Module not enabled for {doc_type}",
                )


class ImportMappingRow(BaseModel):
    header: str = Field(..., min_length=1, max_length=_MAX_HEADER_LENGTH)
    field: str = Field(..., min_length=1)

    @field_validator("header")
    @classmethod
    def _header_must_normalise(cls, value: str) -> str:
        # R3: "   " or "()" carry no alphanumeric/CJK character at all - `normalize_header`
        # folds them to "", which every resolver's own dict can never key on, so a header
        # this blank would be a saved row nothing can ever match.
        if not normalize_header(value):
            raise ValueError("header must contain at least one mappable character")
        return value


class ImportMappingSaveRequest(BaseModel):
    supplier_id: str
    doc_types: List[DocType] = Field(..., min_length=1, max_length=2)
    mappings: List[ImportMappingRow] = Field(default_factory=list, max_length=_MAX_MAPPINGS)


@router.post("/import-mapping/probe")
async def probe_import_mapping(
    file: UploadFile = File(..., description="The supplier's file"),
    supplier_id: str = Form(...),
    doc_types: List[DocType] = Form(
        ..., min_length=1, max_length=2,
        description="One entry normally; two for a combined file (G4/AC-M13).",
    ),
    header_row: Optional[int] = Form(
        None, ge=1, le=1000,
        description="The stepper's current pick (AC-M3); omitted on the first probe.",
    ),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Every column the file's own shape names, with what this supplier's resolver
    already knows about each one."""
    _check_doc_type_permission(db, current_user, doc_types)
    assert_supplier(db, supplier_id)
    data = await read_upload(file)
    return await run_in_threadpool(
        import_mapping_service.probe,
        db,
        data,
        supplier_id=supplier_id,
        doc_types=doc_types,
        header_row=header_row,
    )


@router.post("/import-mapping/save")
def save_import_mapping(
    payload: ImportMappingSaveRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upsert this supplier's mapping - a re-map replaces, never accumulates (AC-M6)."""
    _check_doc_type_permission(db, current_user, payload.doc_types)
    assert_supplier(db, payload.supplier_id)
    import_mapping_service.save(
        db,
        supplier_id=payload.supplier_id,
        doc_types=payload.doc_types,
        mappings=[(row.header, row.field) for row in payload.mappings],
    )
    db.commit()
    return {"ok": True}
