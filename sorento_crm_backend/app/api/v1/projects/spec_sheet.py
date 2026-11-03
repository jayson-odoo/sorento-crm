"""Project spec sheet routes (SPEC-SHEET-V2), on a quotation document.

A spec sheet is a saved record (SS1, SS2 ...). The list, the create dialog's options, the reader's
page list and its windowed previews, the per-page designer and the PDF export all live here.
Reads take the quotation's read permission; every write takes the same right as editing the
quotation (edit + write access to the project). Every route checks project -> document -> sheet,
so a sheet id from another document answers 404.
Plan: ``documentation/plans/project-sales/PLAN-spec-sheet-v2-03nov.md``.
"""
from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.api.v1.projects.quotation_documents import EDIT, READ, _editable_project
from app.database import get_db
from app.dependencies import require_any_permission_with_api_key, require_permission
from app.models.projects import ProjectQuotationSpecSheet
from app.services import project_quotation_document_service as qdocs
from app.services import project_service as projects
from app.services import project_spec_sheet_service as spec
from app.services.error_handler import AppException, handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

BASE = "/projects/{project_id}/quotation-documents/{document_id}/spec-sheets"


class SpecSheetRowIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=120)
    area: Optional[str] = Field(None, max_length=spec.AREA_MAX)
    comment: Optional[str] = Field(None, max_length=spec.COMMENT_MAX)
    marker: Optional[str] = Field(None, max_length=spec.MARKER_MAX)
    hidden: bool = False
    accessories: List[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=20
    )


class SpecSheetCreateIn(BaseModel):
    source: str = Field(..., min_length=1, max_length=64)
    cover_template_id: Optional[str] = None
    page_template_id: Optional[str] = None
    single_page_template_id: Optional[str] = None


class SpecSheetPatchIn(BaseModel):
    """Every field optional: a field left out keeps its saved value."""

    rows: Optional[List[SpecSheetRowIn]] = Field(None, max_length=500)
    use_latest_templates: Optional[bool] = None


class SpecSheetLayersIn(BaseModel):
    layers: List[dict] = Field(default_factory=list, max_length=spec.LAYERS_MAX)


def _document(db: Session, project_id: str, document_id: str):
    validate_uuid_path(project_id, resource="Project")
    validate_uuid_path(document_id, resource="Quotation")
    projects.get_project_or_404(db, project_id)
    return qdocs.get_document_or_404(db, project_id, document_id)


def _sheet(db: Session, document, sheet_id: str) -> ProjectQuotationSpecSheet:
    validate_uuid_path(sheet_id, resource="Spec sheet")
    sheet = (
        db.query(ProjectQuotationSpecSheet)
        .filter(
            ProjectQuotationSpecSheet.id == sheet_id,
            ProjectQuotationSpecSheet.document_id == document.id,
        )
        .first()
    )
    if sheet is None:
        raise AppException(
            status_code=404, message="Spec sheet not found.", code="spec_sheet_not_found"
        )
    return sheet


def _can_edit(db: Session, project_id: str, user: dict) -> bool:
    if EDIT not in permission_slugs(db, user["id"]):
        return False
    try:
        _editable_project(db, project_id, user)
    except AppException:
        return False
    return True


def _fail(exc: Exception):
    return exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(BASE)
def list_spec_sheets(
    project_id: str,
    document_id: str,
    user: dict = Depends(require_any_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    try:
        document = _document(db, project_id, document_id)
        return spec.list_view(db, document, str(user["id"]))
    except Exception as exc:
        raise _fail(exc)


@router.post(BASE, status_code=201)
def create_spec_sheet(
    project_id: str,
    document_id: str,
    payload: SpecSheetCreateIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        _editable_project(db, project_id, current_user)
        document = _document(db, project_id, document_id)
        sheet = spec.create_sheet(
            db,
            document,
            source=payload.source,
            cover_template_id=payload.cover_template_id,
            page_template_id=payload.page_template_id,
            single_page_template_id=payload.single_page_template_id,
            user_id=str(current_user["id"]),
        )
        db.commit()
        db.refresh(sheet)
        return spec.detail_view(db, document, sheet, can_edit=True)
    except Exception as exc:
        raise _fail(exc)


@router.get(f"{BASE}/{{sheet_id}}")
def read_spec_sheet(
    project_id: str,
    document_id: str,
    sheet_id: str,
    user: dict = Depends(require_any_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    try:
        document = _document(db, project_id, document_id)
        sheet = _sheet(db, document, sheet_id)
        return spec.detail_view(db, document, sheet, can_edit=_can_edit(db, project_id, user))
    except Exception as exc:
        raise _fail(exc)


@router.patch(f"{BASE}/{{sheet_id}}")
def update_spec_sheet(
    project_id: str,
    document_id: str,
    sheet_id: str,
    payload: SpecSheetPatchIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        _editable_project(db, project_id, current_user)
        document = _document(db, project_id, document_id)
        sheet = _sheet(db, document, sheet_id)
        spec.update_sheet(
            db, sheet, payload.model_dump(exclude_unset=True), user_id=str(current_user["id"])
        )
        db.commit()
        db.refresh(sheet)
        return spec.detail_view(db, document, sheet, can_edit=True)
    except Exception as exc:
        raise _fail(exc)


@router.get(f"{BASE}/{{sheet_id}}/preview")
def preview_spec_sheet(
    project_id: str,
    document_id: str,
    sheet_id: str,
    keys: str = Query("", description="Comma separated page keys, at most 12"),
    _user: dict = Depends(require_any_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    """The print payload for one window of pages, thumbnails only (the reader's single call)."""
    try:
        document = _document(db, project_id, document_id)
        sheet = _sheet(db, document, sheet_id)
        wanted = list(dict.fromkeys(k.strip() for k in keys.split(",") if k.strip()))
        if not wanted or len(wanted) > spec.PREVIEW_KEYS_MAX:
            raise AppException(
                status_code=422,
                message=f"Ask for 1 to {spec.PREVIEW_KEYS_MAX} pages at a time.",
                code="spec_sheet_keys_invalid",
            )
        return spec.build_print_payload(db, sheet, keys=wanted)
    except Exception as exc:
        raise _fail(exc)


@router.get(f"{BASE}/{{sheet_id}}/pages/{{page_key}}/design")
def design_spec_sheet_page(
    project_id: str,
    document_id: str,
    sheet_id: str,
    page_key: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        # The designer is the edit surface: edit right on this project, though nothing is written.
        _editable_project(db, project_id, current_user, write=False)
        document = _document(db, project_id, document_id)
        sheet = _sheet(db, document, sheet_id)
        return spec.design(db, sheet, page_key)
    except Exception as exc:
        raise _fail(exc)


@router.put(f"{BASE}/{{sheet_id}}/pages/{{page_key}}/edit")
def save_spec_sheet_page(
    project_id: str,
    document_id: str,
    sheet_id: str,
    page_key: str,
    payload: SpecSheetLayersIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        _editable_project(db, project_id, current_user)
        document = _document(db, project_id, document_id)
        sheet = _sheet(db, document, sheet_id)
        spec.save_page_edit(db, sheet, page_key, payload.layers, user_id=str(current_user["id"]))
        db.commit()
        db.refresh(sheet)
        return spec.detail_view(db, document, sheet, can_edit=True)
    except Exception as exc:
        raise _fail(exc)


@router.post(f"{BASE}/{{sheet_id}}/export")
def export_spec_sheet(
    project_id: str,
    document_id: str,
    sheet_id: str,
    current_user: dict = Depends(require_any_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    """Queue the PDF; it appears in My Downloads when it is ready."""
    from app.schemas.download import DownloadResponse

    try:
        document = _document(db, project_id, document_id)
        sheet = _sheet(db, document, sheet_id)
        download = spec.request_export(db, sheet, user_id=str(current_user["id"]))
        db.commit()
        return DownloadResponse.model_validate(download)
    except Exception as exc:
        raise _fail(exc)
