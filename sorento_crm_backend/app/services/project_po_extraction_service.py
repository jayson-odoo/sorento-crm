"""Customer PO intake: read the scan, then let a person agree to it (P4, P5).

The whole slice turns on one sentence: **the AI proposes, arithmetic decides.** A
vision model transcribes a page; nothing it says about a number is believed until
``qty * unit_price == amount`` is recomputed here, in ``Decimal``, from the values it
gave. The measured payoff is exact: the 52 transcribed amounts sum to 1,810,640.62,
and minus the handwritten cancellation of line 7 (4,733.60) that is the quotation
total of 1,805,907.02 to the cent. One number validates the transcription, the
cancellation reading and the cross-check together.

Four rules follow from that, and none of them is negotiable:

* **Handwriting is never applied** (D11). A strike-through becomes a ``cancel_line``
  annotation in ``proposed`` state and the printed line stays exactly as printed.
  ``is_cancelled`` is set by a person accepting the card, through this service, in one
  place. The cancellation of item 7 exists ONLY in pencil, so auto applying it would
  move 4,733.60 on a model's opinion.
* **A version is the record of what the paper said.** Extracted lines and
  ``extracted_json`` never change after confirmation; the CONFIRMED state is written
  onto phase 1's ``project_purchase_order_lines``, which already carries the quotation
  cross-check and its two mismatch flags. That check is reused, never copied.
* **A page that fails does not fail the document.** Nine good pages out of ten is a
  document a person can finish. Every exit path writes a terminal state and a sentence
  they can act on, because a version stuck on "queued" reads as a hung system.
* **The same pencil note on a re-scan is the same note.** ``dedup_key`` is
  ``(written_date, sorted refers_to_lines, sha1 of normalised raw_text)``, and an
  already-actioned card carries its state, its reading AND its consequence forward onto
  the new version. One physical PO accumulates annotations over months and gets
  re-scanned; re-proposing a decision somebody already made is how a review queue stops
  being read.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.project_so import (
    ANNOTATION_ACCEPTED,
    ANNOTATION_EDITED,
    ANNOTATION_PROPOSED,
    ANNOTATION_REJECTED,
    PO_STATUS_APPROVED,
    ProjectPOAnnotation,
    ProjectPOLine,
    ProjectPOVersion,
)
from app.models.projects import (
    QUOTATION_OUTCOME_LOST,
    QUOTATION_OUTCOME_OPEN,
    QUOTATION_OUTCOME_WON,
    Project,
    ProjectPurchaseOrder,
    ProjectPurchaseOrderLine,
    ProjectQuotation,
    ProjectQuotationVersion,
)
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)
from app.services.project_po_confirm import POConfirmationMixin
from app.services.project_po_intake_lifecycle import POIntakeLifecycleMixin
from app.services.project_po_review import POAnnotationReviewMixin
from app.services.project_po_reading import (  # noqa: F401 - shared vocabulary
    STATE_QUEUED,
    STATE_RUNNING,
    STATE_DONE,
    STATE_FAILED,
    INTERP_CANCEL,
    INTERP_AMEND_CODE,
    INTERP_AMEND_DESCRIPTION,
    INTERP_SUCCESSOR_PO,
    INTERP_SIGNATURE,
    INTERP_OTHER,
    INTERPRETATIONS,
    KEY_LINE_NOS,
    KEY_CODE,
    KEY_DESCRIPTION,
    KEY_PO_NUMBER,
    _LEGACY_KEYS,
    ALLOWED_MIMES,
    _EXTENSION_MIMES,
    ATTACHMENT_TYPE_CODE,
    ATTACHMENT_TYPE_NAME,
    ATTACHMENT_ENTITY_TYPE,
    _PENDING_NUMBER,
    _CENTS,
    _CODE_TOKEN,
    _PO_NUMBER_IN_TEXT,
    _PO_NUMBER_TRIGGER,
    _CANCEL_WORDS,
    _SIGNATURE_WORDS,
    _AMEND_WORDS,
    _to_decimal,
    _money,
    _payload_value,
    _reason,
    _int_or_none,
    _is_description_fragment,
    arithmetic_ok,
    _computed_amount,
    _parse_date,
    normalise_annotation_text,
    _int_list,
    dedup_key,
    successor_po_number,
    _looks_like_code,
    _squash,
    _code_tokens,
    _proposed_code,
    classify_annotation,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- the service


class ProjectPOExtractionService(
    POIntakeLifecycleMixin, POConfirmationMixin, POAnnotationReviewMixin
):
    """Everything the customer-PO document does, from upload to countersignature.

    Assembled from three mixins since the 2026-08-12 audit - lifecycle (upload,
    extraction, persistence, edits), confirmation (the phase-1 write-through and the
    approval handshake) and review (the handwriting cards) - because a 2,400-line
    class made the unit of change the whole file. The NAME survives unchanged: the
    worker entry point (``app.tasks.project_document_tasks``), the routes and the
    tests all construct this one class, and the read, the edit and the confirm still
    have to agree about the same four totals, which is why it stays ONE object over
    one session rather than three services with three opinions.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # --------------------------------------------------------------- serialising

    def serialize_version(self, version: ProjectPOVersion) -> Dict[str, Any]:
        from app.models.resources import Attachment
        from app.services.storage_router import resolve_signed_url

        po = self.get_po(version.purchase_order_id)
        project = self.db.query(Project).filter(Project.id == po.project_id).first()
        header = (version.extracted_json or {}).get("header") or {}
        totals = self.recompute_totals(version)

        attachment = (
            self.db.query(Attachment).filter(Attachment.id == version.attachment_id).first()
            if version.attachment_id
            else None
        )
        document_url = (
            resolve_signed_url(
                attachment.file_path, provider=attachment.storage_provider
            )
            if attachment is not None
            else None
        )

        # How much of the document was actually read. "Only 7 of 10 pages were read" is
        # the first thing the screen has to say, and it cannot say it from a state of
        # "done" plus a sentence.
        blobs = (version.extracted_json or {}).get("pages") or []
        pages_extracted = sum(1 for blob in blobs if isinstance(blob, dict) and blob.get("data"))
        failed_pages = [
            blob.get("page_no")
            for blob in blobs
            if isinstance(blob, dict) and not blob.get("data") and blob.get("page_no")
        ]
        line_pages = self._line_pages(version)

        return {
            "id": str(version.id),
            "purchase_order_id": str(po.id),
            "po_number": po.po_number or "",
            "project_id": str(po.project_id),
            "project_title": getattr(project, "title", None),
            "version_no": version.version_no,
            "extraction_state": version.extraction_state,
            "extraction_error": version.extraction_error,
            "extraction_model": version.extraction_model,
            "extraction_elapsed_ms": version.extraction_elapsed_ms,
            "extraction_started_at": version.extraction_started_at,
            "page_count": version.page_count,
            "pages_extracted": pages_extracted,
            "failed_pages": failed_pages,
            "document_url": document_url,
            "source_filename": version.source_filename,
            "header": {
                "po_number": header.get("po_number") or po.po_number or None,
                "po_date": _parse_date(header.get("po_date")) or po.po_date,
                "term_days": _int_or_none(header.get("term")) or po.term_days,
                "sales_person": header.get("sales_person") or po.sales_person,
                "customer_order_ref": (
                    header.get("customer_order_ref") or po.customer_order_ref
                ),
                # D24: the PS filing reference is ours, not something printed on their
                # paper, so it comes off the PO row and never out of the scan.
                "admin_ref": po.admin_ref,
                "remark": header.get("remark") or po.notes,
            },
            "totals": totals,
            "lines": [
                self.serialize_line(line, page_no=line_pages.get(str(line.line_no)))
                for line in self._lines(version.id)
            ],
            "annotations": [
                self.serialize_annotation(annotation)
                for annotation in self._annotations(version.id)
            ],
            # The approval stamps live on the PO, not the version, but the confirm screen
            # is where they are read and shown, so they travel with the version.
            "purchase_order": {
                "po_number": po.po_number or "",
                "status": po.status,
                "approved_by_name": self._user_name(po.approved_by),
                "approved_at": po.approved_at,
                "countersigned_by_name": self._user_name(po.countersigned_by),
                "countersigned_at": po.countersigned_at,
            },
            "confirmed_at": version.confirmed_at,
            "confirmed_by_name": self._user_name(version.confirmed_by),
            "created_at": version.created_at,
        }

    def serialize_line(
        self, line: ProjectPOLine, *, page_no: Optional[int] = None
    ) -> Dict[str, Any]:
        product_code = None
        product_name = None
        if line.resolved_product_id:
            from app.models.product import Product

            product = (
                self.db.query(Product).filter(Product.id == line.resolved_product_id).first()
            )
            if product is not None:
                product_code = product.product_code
                product_name = product.product_name
        return {
            "id": str(line.id),
            "line_no": line.line_no,
            # Which page it was printed on, so selecting a line turns the viewer to it.
            "page_no": page_no,
            "stock_code_raw": line.stock_code_raw,
            "description_raw": line.description_raw,
            "qty": line.qty,
            "uom_raw": line.uom_raw,
            "unit_price": line.unit_price,
            "amount": line.amount,
            "arithmetic_ok": line.arithmetic_ok,
            "is_cancelled": bool(line.is_cancelled),
            "resolved_product_id": line.resolved_product_id,
            "resolved_product_code": product_code,
            "resolved_product_name": product_name,
            "resolution_source": line.resolution_source,
        }

    def serialize_annotation(self, annotation: ProjectPOAnnotation) -> Dict[str, Any]:
        from app.services.storage_router import resolve_signed_url

        crop_url = None
        if annotation.crop_attachment_id:
            from app.models.resources import Attachment

            crop = (
                self.db.query(Attachment)
                .filter(Attachment.id == annotation.crop_attachment_id)
                .first()
            )
            if crop is not None:
                crop_url = resolve_signed_url(
                    crop.file_path, provider=crop.storage_provider
                )
        return {
            "id": str(annotation.id),
            "page_no": annotation.page_no,
            "crop_url": crop_url,
            "raw_text": annotation.raw_text,
            "written_date": annotation.written_date,
            "refers_to_lines": _int_list(annotation.refers_to_lines),
            "interpretation": annotation.interpretation,
            "interpretation_json": dict(annotation.interpretation_json or {}),
            "state": annotation.state,
            "actioned_by_name": self._user_name(annotation.actioned_by),
            "actioned_at": annotation.actioned_at,
            "action_note": annotation.action_note,
        }

    def serialize_po_approval(self, po: ProjectPurchaseOrder) -> Dict[str, Any]:
        return {
            "id": str(po.id),
            "po_number": po.po_number or "",
            "project_id": str(po.project_id),
            "status": po.status,
            "approved_by_name": self._user_name(po.approved_by),
            "approved_at": po.approved_at,
            "countersigned_by_name": self._user_name(po.countersigned_by),
            "countersigned_at": po.countersigned_at,
        }

    # ------------------------------------------------------------------- guards

    def _assert_unconfirmed(self, version: ProjectPOVersion) -> None:
        if version.confirmed_at is not None:
            raise AppException(
                status_code=409,
                message=(
                    "This version is confirmed. It is the record of what the document "
                    "said and cannot be edited -- upload the revised document as a new "
                    "version instead."
                ),
                code="po_version_confirmed",
            )

    def _user_name(self, user_id: Optional[str]) -> Optional[str]:
        if not user_id:
            return None
        from app.models.user import User

        row = self.db.query(User.name, User.email).filter(User.id == user_id).first()
        if row is None:
            return None
        return row[0] or row[1]

