"""Requesting a catalogue PDF, and reading back what it should contain.

The whole point of this module is one rule: **the render context is decided at
enqueue and never re-derived later.**

Two things go wrong if it is not. The worker runs with no request and no user,
so "who is this for" has no answer at render time - and the tempting fallback,
a system principal, is a staff principal, which would quietly print internal
prices into a document a consumer asked for. And a page republished while its
PDF sits in the queue would change what that PDF contains, so the file someone
downloads would not be the thing they exported.

Both are fixed by snapshotting: audience, invoice-price toggle and the exact
version id, written when the request is made.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.dealer_kit import ExportRequest, PageLabel, PageVersion
from app.models.download import DownloadStatus, UserDownload
from app.services.dealer_kit import page_service
from app.services.dealer_kit.viewer import ViewerContext
from app.services.error_handler import AppException

KIND = "dealer_kit_catalogue_pdf"

# Who a rendered document is FOR. Not the requester - staff exporting a dealer's
# copy to email out is the normal case.
AUDIENCES = ("staff", "dealer", "consumer")


def _slugify(name: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in name.lower())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "catalogue"


def request_export(
    db: Session,
    *,
    page_id: str,
    audience: str = "staff",
    show_invoice_price: bool = False,
    user_id: str,
    version_id: Optional[str] = None,
) -> UserDownload:
    """Queue a PDF of ``page_id`` and snapshot what it should contain.

    Defaults to the PUBLISHED version, because "export this catalogue" means the
    one people can see. An explicit ``version_id`` lets someone export a draft
    for review.
    """
    if audience not in AUDIENCES:
        raise AppException(
            status_code=422,
            message=f"Unknown audience '{audience}'. Expected one of: {', '.join(AUDIENCES)}",
        )
    if not user_id:
        # Without a requester there is nobody to deliver the file to, and the
        # download drawer is per-user.
        raise AppException(status_code=422, message="An export needs a requesting user")

    page = page_service.get_page(db, page_id)

    if version_id:
        version = (
            db.query(PageVersion)
            .filter(PageVersion.id == version_id, PageVersion.page_id == page_id)
            .first()
        )
        if version is None:
            raise AppException(status_code=404, message="Version not found on this page")
    else:
        label = (
            db.query(PageLabel)
            .filter(PageLabel.page_id == page_id, PageLabel.label == "published")
            .first()
        )
        if label is None:
            raise AppException(
                status_code=409,
                message="This page has not been published yet, so there is nothing to export",
            )
        version = db.query(PageVersion).filter(PageVersion.id == label.version_id).first()
        if version is None:
            raise AppException(status_code=409, message="The published version is missing")

    download = UserDownload(
        user_id=user_id,
        kind=KIND,
        source_entity_type="dealer_kit_page",
        source_entity_id=page_id,
        status=DownloadStatus.PENDING.value,
        filename=f"{_slugify(page.name)}-v{version.version}.pdf",
    )
    db.add(download)
    db.flush()

    db.add(
        ExportRequest(
            download_id=download.id,
            page_id=page_id,
            # Pinned: republishing while this sits in the queue must not change
            # what the file contains.
            page_version_id=version.id,
            audience=audience,
            show_invoice_price=show_invoice_price,
            requested_by=user_id,
        )
    )
    db.commit()
    db.refresh(download)
    return download


def get_request(db: Session, download_id: str) -> ExportRequest:
    row = (
        db.query(ExportRequest)
        .filter(ExportRequest.download_id == download_id)
        .first()
    )
    if row is None:
        # The worker must NEVER carry on without one. No snapshot means no
        # answer to "who is this for", and the only available fallback is a
        # staff principal - which is exactly the leak this exists to prevent.
        raise AppException(
            status_code=404,
            message=(
                "This download has no export request, so there is no viewer to render it "
                "for. Refusing to render rather than guessing."
            ),
        )
    return row


#: What each export audience is entitled to see. `access_codes` is the one knob
#: that decides whether a promotion applies to a reader (ADR 0008) and which
#: imagery they may see, so an audience that maps to nothing produces a document
#: priced and illustrated for nobody in particular.
#:
#: Staff map to no codes on purpose. `is_staff` governs the INVOICE price and not
#: a promotion's audience, because exporting AS a dealer is how somebody asks for
#: the trade view. A staff export therefore shows list prices, which is a
#: commercial choice worth revisiting rather than an accident.
_AUDIENCE_ACCESS_CODES = {
    "dealer": frozenset({"dealer"}),
    "end_user": frozenset({"end_user"}),
    "staff": frozenset(),
}


def viewer_for(request: ExportRequest) -> ViewerContext:
    """The viewer a render must use. Derived only from the snapshot.

    The audience used to set `is_staff` alone, leaving `access_codes` empty, so a
    PDF requested for DEALERS came out priced and illustrated for a consumer. The
    export screen gives no hint of that; the dealer opening the file does.

    An unrecognised audience gets nothing rather than the most generous reading:
    a new audience nobody has taught this function about must not default into
    seeing trade prices.
    """
    return ViewerContext(
        is_staff=(request.audience == "staff"),
        access_codes=_AUDIENCE_ACCESS_CODES.get(request.audience, frozenset()),
        show_invoice_price=bool(request.show_invoice_price),
    )


def render_inputs(db: Session, download_id: str) -> dict:
    """Everything a render needs, and nothing it should decide for itself."""
    request = get_request(db, download_id)
    version = (
        db.query(PageVersion).filter(PageVersion.id == request.page_version_id).first()
    )
    if version is None:
        raise AppException(status_code=404, message="The exported version no longer exists")

    return {
        "page_id": request.page_id,
        "version_id": version.id,
        "version": version.version,
        "doc": version.doc,
        "viewer": viewer_for(request),
        "audience": request.audience,
    }
