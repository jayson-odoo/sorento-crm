"""Dealer Kit catalogue page endpoints.

Mounted at ``/api/v1/dealer-kit`` behind the package's
``require_module_enabled_with_api_key("dealer_kit")`` guard.

Permissions are split by consequence, not by HTTP verb:

  * ``page.view``    reading pages and their history
  * ``page.edit``    creating pages, saving versions, moving ``staging``
  * ``page.publish`` moving ``published`` - which is what a reader actually sees

That split is the point. Someone can be trusted to draft the 2026 catalogue
without being trusted to put it in front of every dealer, and rollback carries
the publish permission because it has exactly the same blast radius.

Reads use the api-key-tolerant guard so automation can fetch a page. WRITES use
the plain ``require_permission``: ``require_permission_with_api_key`` documents
itself as read-oriented and unsafe on writes without a second real-user gate,
and there is no reason for a machine key to publish a catalogue.

The two label routes are declared as STATIC paths (``/labels/published`` and
``/labels/staging``) rather than one parametric ``/labels/{label}``. FastAPI
resolves dependencies before it knows the path parameter, so a single route
could not carry the right permission declaratively - it would need a runtime
check in the body, which is exactly the kind of gate that gets missed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.dealer_kit import (
    ExportRequestIn,
    ExportRequestOut,
    LabelMove,
    PageCreate,
    PageDetail,
    PageSummary,
    PageVersionOut,
    VersionCreate,
)
from app.services.dealer_kit import export_service
from app.services.dealer_kit import page_service as svc

router = APIRouter()

_VIEW = require_permission_with_api_key("dealer_kit.page.view")
_EDIT = require_permission("dealer_kit.page.edit")
_PUBLISH = require_permission("dealer_kit.page.publish")


def _user_id(user: dict | None) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


def _version_rows(db: Session, page_id: str) -> list[PageVersionOut]:
    labels = svc.labels_for(db, page_id)
    versions = svc.list_versions(db, page_id)
    # Resolved to a person's name here: a user id has no business reaching a screen.
    names = svc.author_names(db, (v.created_by for v in versions))
    return [
        PageVersionOut(
            id=v.id,
            version=v.version,
            commit_message=v.commit_message,
            created_by=names.get(v.created_by) if v.created_by else None,
            created_at=v.created_at,
            labels=labels.get(v.id, []),
        )
        for v in versions
    ]


def _label_response(db: Session, row) -> PageVersionOut:
    version = row.version
    names = svc.author_names(db, [version.created_by])
    return PageVersionOut(
        id=version.id,
        version=version.version,
        commit_message=version.commit_message,
        created_by=names.get(version.created_by) if version.created_by else None,
        created_at=version.created_at,
        labels=[row.label],
    )


@router.get("/pages", response_model=list[PageSummary])
def list_pages(db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    return [PageSummary(**row) for row in svc.list_pages(db)]


@router.post("/pages", response_model=PageDetail, status_code=status.HTTP_201_CREATED)
def create_page(
    payload: PageCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    page = svc.create_page(db, name=payload.name, slug=payload.slug, user_id=_user_id(user))
    return PageDetail(
        id=page.id,
        name=page.name,
        slug=page.slug,
        updated_at=page.updated_at,
        published_version=None,
        latest_version=0,
        public_path=svc.public_path(db, page),
        doc={"sections": [], "printProfile": svc.DEFAULT_PRINT_PROFILE},
        versions=[],
    )


@router.get("/pages/{page_id}", response_model=PageDetail)
def get_page(page_id: str, db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    page = svc.get_page(db, page_id)
    stored = svc.list_versions(db, page_id)
    versions = _version_rows(db, page_id)

    # The editor opens on `staging` when one exists, else the newest version.
    # Opening on `published` instead would silently discard work in progress the
    # moment someone re-saved.
    staging = next((v for v in versions if "staging" in v.labels), None)
    head = staging or (versions[0] if versions else None)
    published = next((v.version for v in versions if "published" in v.labels), None)

    doc: dict = {"sections": [], "printProfile": svc.DEFAULT_PRINT_PROFILE}
    if head is not None:
        doc = next((v.doc for v in stored if v.id == head.id), doc)

    return PageDetail(
        id=page.id,
        name=page.name,
        slug=page.slug,
        updated_at=page.updated_at,
        published_version=published,
        latest_version=versions[0].version if versions else 0,
        public_path=svc.public_path(db, page),
        doc=doc,
        versions=versions,
    )


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_page(page_id: str, db: Session = Depends(get_db), _user: dict = Depends(_EDIT)):
    svc.delete_page(db, page_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/pages/{page_id}/versions", response_model=list[PageVersionOut])
def list_versions(page_id: str, db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    return _version_rows(db, page_id)


@router.post(
    "/pages/{page_id}/versions",
    response_model=PageVersionOut,
    status_code=status.HTTP_201_CREATED,
)
def save_version(
    page_id: str,
    payload: VersionCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    version = svc.save_version(
        db,
        page_id,
        doc=payload.doc,
        commit_message=payload.commit_message,
        user_id=_user_id(user),
    )
    names = svc.author_names(db, [version.created_by])
    return PageVersionOut(
        id=version.id,
        version=version.version,
        commit_message=version.commit_message,
        created_by=names.get(version.created_by) if version.created_by else None,
        created_at=version.created_at,
        labels=[],
    )


@router.put("/pages/{page_id}/labels/published", response_model=PageVersionOut)
def publish_version(
    page_id: str,
    payload: LabelMove,
    db: Session = Depends(get_db),
    user: dict = Depends(_PUBLISH),
):
    """Publish, and also roll back - both are this one call aimed at a version."""
    row = svc.move_label(
        db, page_id, svc.PUBLISHED, version_id=payload.version_id, user_id=_user_id(user)
    )
    return _label_response(db, row)


@router.put("/pages/{page_id}/labels/staging", response_model=PageVersionOut)
def stage_version(
    page_id: str,
    payload: LabelMove,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    row = svc.move_label(
        db, page_id, svc.STAGING, version_id=payload.version_id, user_id=_user_id(user)
    )
    return _label_response(db, row)


@router.post(
    "/pages/{page_id}/exports",
    response_model=ExportRequestOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_export(
    page_id: str,
    payload: ExportRequestIn,
    db: Session = Depends(get_db),
    user: dict = Depends(_VIEW),
):
    """Queue a PDF of this page for the given audience.

    202, not 201: the file does not exist yet. The response carries the download
    id so the caller can watch it in My Downloads rather than blocking on a
    render that takes seconds.

    ``page.view`` rather than ``page.edit`` - exporting a catalogue is reading
    it, and a salesperson who may see a page may take it to a customer.
    """
    from app.services.download_service import DownloadService
    from app.services.queue_service import enqueue_job
    from app.tasks.dealer_kit_export_tasks import generate_catalogue_pdf

    download = export_service.request_export(
        db,
        page_id=page_id,
        audience=payload.audience,
        show_invoice_price=payload.show_invoice_price,
        user_id=_user_id(user) or "",
        version_id=payload.version_id,
    )

    try:
        # Only the download id: everything else comes from the snapshot, so the
        # task can never be invoked with a viewer that disagrees with the
        # request.
        enqueue_job(
            generate_catalogue_pdf,
            str(download.id),
            # Its own queue: a Chromium render is slow and memory-hungry, and
            # sharing `imports` would put one catalogue PDF in front of every
            # Excel upload behind it.
            queue_name="catalogue_render",
            job_timeout=900,
        )
    except Exception as exc:  # noqa: BLE001
        # Redis down: mark it failed so My Downloads shows the truth rather
        # than a row that stays 'pending' forever.
        DownloadService(db).mark_failed(
            str(download.id), f"Could not queue PDF generation: {exc}"
        )

    db.refresh(download)
    return ExportRequestOut(
        download_id=download.id,
        status=str(download.status),
        filename=download.filename,
        audience=payload.audience,
    )
