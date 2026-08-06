"""Certificate register API routes.

Thin: every decision lives in ``CertificateService`` (writes) or
``CertificateQueryService`` (reads). What this file owns is the HTTP surface -
permissions, path/query validation, and the response shapes the list grid and
the agent tools consume.

Two things worth knowing before editing:

**Reads take ``require_permission_with_api_key``, writes take
``require_permission``.** The register is read by the MCP tool under an X-API-Key
principal; nothing here is written by one.

**Delete is a HARD delete.** It takes the revisions, the coverage and the
projection rows with it and leaves the ``attachments`` rows standing (COV-5) -
the PDFs outlive the register row that indexed them.
"""
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.certificate import CERTIFICATE_SOURCE_MANUAL, CertificateProduct
from app.schemas.certificate import (
    BulkDeleteCertificatesRequest,
    CertificateCreate,
    CertificateEditRequest,
    CertificateProductAddRequest,
    CertificateResponse,
)
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.certificate_query_service import CertificateQueryService
from app.services.certificate_service import CertificateService
from app.services.error_handler import handle_internal_error, handle_not_found
from app.services.uuid_list_param import parse_uuid_list
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

_VIEW = "master_data.certificates.view"
_ADD = "master_data.certificates.add"
_EDIT = "master_data.certificates.edit"
_DELETE = "master_data.certificates.delete"


@router.get("/", response_model=ListResponse[CertificateResponse])
def get_certificates(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query(None, description="Sort column (allowlisted server-side)."),
    dir: Optional[str] = Query(None, description="asc | desc."),
    query: Optional[str] = Query(
        None,
        description="Free text over scheme, number (punctuation-insensitive), body, issuer, title.",
    ),
    certificate_ids: Optional[List[str]] = Query(
        None, description="Canonical certificate UUIDs (repeated / csv / JSON array)."
    ),
    certificate_number: Optional[str] = Query(
        None,
        description="Raw certificate number; normalized server-side, so 'PPS 0119' = 'pps-0119'.",
    ),
    product_ids: Optional[List[str]] = Query(
        None, description="Certificates covering these product UUIDs (repeated / csv / JSON array)."
    ),
    scheme: Optional[str] = Query(None, description="Certification scheme, e.g. PPS or SPAN."),
    status_: Optional[str] = Query(None, alias="status", description="active | archived."),
    validity_state: Optional[str] = Query(
        None,
        description=(
            "Comma-separated derived states: valid, expiring_soon, expired, "
            "not_yet_valid, unknown. The default list view sends 'expiring_soon,expired'."
        ),
    ),
    expiring_within_days: Optional[int] = Query(
        None, ge=0, description="Current revision expires between today and today + N days."
    ),
    valid_on: Optional[str] = Query(
        None, description="ISO date; certificates whose current revision is valid on that day."
    ),
    needs_review: Optional[bool] = Query(
        None, description="Filter on the current revision's review flag."
    ),
    expiry_notify_batch_id: Optional[str] = Query(
        None, description="The batch stamped by an expiry reminder, so its link opens that exact set."
    ),
    resolve_signed_urls: bool = Query(
        False,
        description="Sign the CURRENT revision's file into preview_url / download_url. Superseded revisions are never signed.",
    ),
    current_user: dict = Depends(require_permission_with_api_key(_VIEW)),
    db: Session = Depends(get_db),
):
    """List certificates with derived validity, filters and pagination."""
    try:
        from datetime import date as _date

        parsed_valid_on = None
        if valid_on:
            try:
                parsed_valid_on = _date.fromisoformat(str(valid_on).strip())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="valid_on must be an ISO date (YYYY-MM-DD).",
                )

        service = CertificateQueryService(db)
        return service.list_certificates(
            page=page,
            limit=limit,
            sort=sort,
            dir=dir,
            query=query,
            certificate_ids=parse_uuid_list(certificate_ids, param_name="certificate_ids"),
            certificate_number=certificate_number,
            product_ids=parse_uuid_list(product_ids, param_name="product_ids"),
            scheme=scheme,
            status=status_,
            validity_state=validity_state,
            expiring_within_days=expiring_within_days,
            valid_on=parsed_valid_on,
            needs_review=needs_review,
            expiry_notify_batch_id=expiry_notify_batch_id,
            resolve_signed_urls=resolve_signed_urls,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED)
def create_certificate(
    payload: CertificateCreate,
    current_user: dict = Depends(require_permission(_ADD)),
    db: Session = Depends(get_db),
):
    """Create a certificate. Revision 1 is filed in the same call when any of
    ``attachment_id`` / ``issued_at`` / ``valid_from`` / ``valid_until`` is given."""
    try:
        service = CertificateService(db)
        certificate = service.create_certificate(
            payload, created_by=str(current_user.get("id") or "") or None
        )
        return CertificateQueryService(db).get_detail(str(certificate.id))
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
def bulk_delete_certificates(
    body: BulkDeleteCertificatesRequest = Body(...),
    current_user: dict = Depends(require_permission(_DELETE)),
    db: Session = Depends(get_db),
):
    """Hard-delete several certificates. Body: { ids: string[] }.

    Declared before ``/{certificate_id}`` so "bulk" is never swallowed as an id.
    """
    try:
        service = CertificateService(db)
        deleted = 0
        for certificate_id in body.ids or []:
            validate_uuid_path(str(certificate_id), resource="Certificate")
            service.delete_certificate(str(certificate_id))
            deleted += 1
        return {"message": f"Deleted {deleted} certificate(s).", "deleted_count": deleted}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{certificate_id}", response_model=CertificateResponse)
def get_certificate(
    certificate_id: str,
    resolve_signed_urls: bool = Query(
        False, description="Sign the CURRENT revision's file into preview_url / download_url."
    ),
    current_user: dict = Depends(require_permission_with_api_key(_VIEW)),
    db: Session = Depends(get_db),
):
    """One certificate with every detail section: revisions (newest first),
    covered products, unmatched strings, suspected duplicate and reminders.

    A cross-company id is simply not found - 404, never 403-with-data (SEC-2).
    """
    try:
        validate_uuid_path(certificate_id, resource="Certificate")
        return CertificateQueryService(db).get_detail(
            certificate_id, resolve_signed_urls=resolve_signed_urls
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{certificate_id}", response_model=CertificateResponse)
def update_certificate(
    certificate_id: str,
    payload: CertificateEditRequest,
    current_user: dict = Depends(require_permission(_EDIT)),
    db: Session = Depends(get_db),
):
    """Edit identity / lifecycle, and the current revision's dates.

    Only the date keys the caller actually sent are forwarded to
    ``update_revision`` - it nulls whatever it is handed as omitted, so passing
    all three on a partial edit would silently wipe the expiry.
    """
    try:
        validate_uuid_path(certificate_id, resource="Certificate")
        service = CertificateService(db)
        service.update_certificate(certificate_id, payload, commit=False)

        touched = payload.revision_fields_set()
        if touched:
            certificate = service.get_certificate(certificate_id)
            revision = service.get_current_revision(certificate)
            if revision is None:
                # Nothing to date yet: file revision 1 from what was sent.
                service.add_revision(
                    certificate_id,
                    issued_at=payload.issued_at,
                    valid_from=payload.valid_from,
                    valid_until=payload.valid_until,
                    source=CERTIFICATE_SOURCE_MANUAL,
                    created_by=str(current_user.get("id") or "") or None,
                    commit=False,
                )
            else:
                service.update_revision(
                    str(revision.id),
                    issued_at=payload.issued_at,
                    valid_from=payload.valid_from,
                    valid_until=payload.valid_until,
                    fields_set=touched,
                    # A human fixing the flagged field is what clears the flag
                    # (RVW-4); it never clears itself.
                    reviewed_by=str(current_user.get("id") or "") or None,
                    commit=False,
                )
        db.commit()
        return CertificateQueryService(db).get_detail(certificate_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{certificate_id}", status_code=status.HTTP_200_OK)
def delete_certificate(
    certificate_id: str,
    current_user: dict = Depends(require_permission(_DELETE)),
    db: Session = Depends(get_db),
):
    """Hard-delete a certificate: revisions, coverage and projection rows go with
    it; the underlying attachments survive (COV-5)."""
    try:
        validate_uuid_path(certificate_id, resource="Certificate")
        CertificateService(db).delete_certificate(certificate_id)
        return {"message": "Certificate deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/{certificate_id}/merge-into/{target_id}", response_model=CertificateResponse
)
def merge_certificate_into(
    certificate_id: str,
    target_id: str,
    current_user: dict = Depends(require_permission(_EDIT)),
    db: Session = Depends(get_db),
):
    """Fold this certificate into the target and hard-delete the emptied source.

    Only ever reached from a human decision behind a confirmation dialog: the
    near-match probe stamps a suspicion, it never merges (DUP-2). 422 on a
    self-merge or a cross-company pair (DUP-5).
    """
    try:
        validate_uuid_path(certificate_id, resource="Certificate")
        validate_uuid_path(target_id, resource="Certificate")
        target = CertificateService(db).merge_into(certificate_id, target_id)
        return CertificateQueryService(db).get_detail(str(target.id))
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/{certificate_id}/products",
    response_model=CertificateResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_certificate_product(
    certificate_id: str,
    payload: CertificateProductAddRequest,
    current_user: dict = Depends(require_permission(_EDIT)),
    db: Session = Depends(get_db),
):
    """Cover one more product. The coverage row is ``manual`` and the projection
    row for the current revision's attachment is written with it (COV-3)."""
    try:
        validate_uuid_path(certificate_id, resource="Certificate")
        CertificateService(db).add_coverage(
            certificate_id,
            [payload.product_id],
            source=CERTIFICATE_SOURCE_MANUAL,
            created_by=str(current_user.get("id") or "") or None,
        )
        return CertificateQueryService(db).get_detail(certificate_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{certificate_id}/products/{coverage_id}", status_code=status.HTTP_200_OK)
def remove_certificate_product(
    certificate_id: str,
    coverage_id: str,
    current_user: dict = Depends(require_permission(_EDIT)),
    db: Session = Depends(get_db),
):
    """Uncover a product. Hard-deletes the coverage row and its projection row."""
    try:
        validate_uuid_path(certificate_id, resource="Certificate")
        validate_uuid_path(coverage_id, resource="Certificate coverage")
        service = CertificateService(db)
        # Resolve the coverage row THROUGH the certificate: certificate_products
        # is not company-scoped, so a lookup by its own id alone would reach
        # another company's row.
        certificate = service.get_certificate(certificate_id)
        coverage = (
            db.query(CertificateProduct)
            .filter(
                CertificateProduct.id == coverage_id,
                CertificateProduct.certificate_id == certificate.id,
            )
            .first()
        )
        if coverage is None:
            raise handle_not_found("Certificate coverage", coverage_id)
        service.remove_coverage(certificate_id, [str(coverage.product_id)])
        return {"message": "Covered product removed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
