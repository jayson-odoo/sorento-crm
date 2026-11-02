"""Project spec sheet routes (PS-SPEC-SHEET), on a quotation document.

The Spec sheet tab reads and saves its settings here, previews the pages with the same payload the
PDF prints from, and queues the PDF into My Downloads. Reads take the quotation's read permission;
saving takes the same right as editing the quotation (edit + write access to the project).
Card: ``documentation/plans/project-sales/CARD-ps-spec-sheet-02nov.md``.
"""
from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.projects.quotation_documents import EDIT, READ, _editable_project
from app.database import get_db
from app.dependencies import require_any_permission_with_api_key, require_permission
from app.models.dealer_kit import TagTemplate
from app.services import project_quotation_document_service as qdocs
from app.services import project_service as projects
from app.services import project_spec_sheet_service as spec
from app.services.error_handler import AppException, handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

BASE = "/projects/{project_id}/quotation-documents/{document_id}/spec-sheet"


class SpecSheetRowIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=120)
    area: Optional[str] = Field(None, max_length=spec.AREA_MAX)
    comment: Optional[str] = Field(None, max_length=spec.COMMENT_MAX)
    marker: Optional[str] = Field(None, max_length=spec.MARKER_MAX)
    hidden: bool = False
    accessories: List[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=20
    )


class SpecSheetSettingsIn(BaseModel):
    """Every field optional: a field left out keeps its saved value."""

    cover_template_id: Optional[str] = None
    page_template_id: Optional[str] = None
    single_page_template_id: Optional[str] = None
    issue_id: Optional[str] = None
    rows: Optional[List[SpecSheetRowIn]] = Field(None, max_length=500)


def _document(db: Session, project_id: str, document_id: str):
    validate_uuid_path(project_id, resource="Project")
    validate_uuid_path(document_id, resource="Quotation")
    projects.get_project_or_404(db, project_id)
    return qdocs.get_document_or_404(db, project_id, document_id)


def _issue(db: Session, document, issue_id: Optional[str]):
    if issue_id:
        validate_uuid_path(issue_id, resource="Revision")
    issue = spec.issue_for(db, document, issue_id)
    if issue_id and (issue is None or str(issue.id) != issue_id):
        raise AppException(
            status_code=404, message="Revision not found.", code="quotation_issue_not_found"
        )
    return issue


def _templates(db: Session) -> dict:
    rows = (
        db.query(TagTemplate)
        .filter(
            TagTemplate.family.in_([spec.COVER_FAMILY, spec.PAGE_FAMILY]),
            TagTemplate.published_version_id.isnot(None),
        )
        .order_by(TagTemplate.name)
        .all()
    )
    out: dict = {"cover": [], "page": []}
    for row in rows:
        doc = (row.published_version.doc if row.published_version else None) or {}
        out["cover" if row.family == spec.COVER_FAMILY else "page"].append(
            {
                "id": row.id,
                "name": row.name,
                "width_mm": doc.get("width_mm"),
                "height_mm": doc.get("height_mm"),
            }
        )
    return out


def _public(page: dict) -> dict:
    """A page without its print-only (underscore) keys, accessories included."""
    out = {k: v for k, v in page.items() if not k.startswith("_")}
    out["accessories"] = [
        {k: v for k, v in acc.items() if not k.startswith("_")} for acc in page["accessories"]
    ]
    return out


def _view(db: Session, document, issue) -> dict:
    issues = qdocs.list_issues(db, document)
    return {
        "settings": spec.settings_of(document),
        "issue_id": issue.id if issue is not None else None,
        "issues": [
            {
                "id": row.id,
                "issue_no": row.issue_no,
                # Built, never read back from `our_ref_text`, as every other reader does.
                "label": qdocs.quotation_no(document.document_no, row.issue_no),
                "issued_at": row.issued_at.isoformat() if row.issued_at else None,
            }
            for row in issues
        ],
        "pages": [_public(page) for page in spec.pages(db, document, issue)],
        "templates": _templates(db),
    }


@router.get(BASE)
def read_spec_sheet(
    project_id: str,
    document_id: str,
    issue_id: Optional[str] = Query(None),
    _user: dict = Depends(require_any_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    try:
        document = _document(db, project_id, document_id)
        return _view(db, document, _issue(db, document, issue_id))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(BASE)
def save_spec_sheet(
    project_id: str,
    document_id: str,
    payload: SpecSheetSettingsIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        _editable_project(db, project_id, current_user)
        document = _document(db, project_id, document_id)
        spec.save_settings(db, document, payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(document)
        return _view(db, document, _issue(db, document, None))
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(f"{BASE}/preview")
def preview_spec_sheet(
    project_id: str,
    document_id: str,
    issue_id: Optional[str] = Query(None),
    _user: dict = Depends(require_any_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    """The exact payload the PDF prints from, for the tab's on-screen pages."""
    try:
        document = _document(db, project_id, document_id)
        issue = _issue(db, document, issue_id)
        if issue is None:
            raise AppException(
                status_code=409,
                message="Issue a revision first.",
                code="spec_sheet_no_issue",
            )
        return spec.build_print_payload(db, document, issue)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(f"{BASE}/export")
def export_spec_sheet(
    project_id: str,
    document_id: str,
    issue_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_any_permission_with_api_key(READ)),
    db: Session = Depends(get_db),
):
    """Queue the PDF; it appears in My Downloads when it is ready."""
    from app.schemas.download import DownloadResponse

    try:
        document = _document(db, project_id, document_id)
        issue = _issue(db, document, issue_id)
        if issue is None:
            raise AppException(
                status_code=409,
                message="Issue a revision first.",
                code="spec_sheet_no_issue",
            )
        download = spec.request_export(db, document, issue, user_id=str(current_user["id"]))
        return DownloadResponse.model_validate(download)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
