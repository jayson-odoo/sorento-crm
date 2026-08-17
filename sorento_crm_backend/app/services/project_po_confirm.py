"""CONFIRMING a PO version: the person agrees, and phase 1 gets the record.

One of the three mixins ``ProjectPOExtractionService`` is assembled from (2026-08-12
audit split). Confirmation is the only write-through to
``project_purchase_order_lines`` - where the quotation cross-check lives - plus the
quotation binding rules and the approval/countersign handshake.
Methods are verbatim from the original service; only the module boundary is new.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

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
    _OUTCOME_RANK,
    _OUTCOME_RANK_DEFAULT,
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


class POConfirmationMixin:
    """Requires ``self.db`` and the lifecycle lookups."""

    db: Session

    # ------------------------------------------------------------------ confirm

    def confirm_version(
        self, *, version: ProjectPOVersion, actor_user_id: str
    ) -> Dict[str, Any]:
        """Write the confirmed state onto the phase-1 PO row and its lines.

        The version keeps its extracted JSON and lines untouched for ever: they are the
        record of what the document said. What a person agreed to lands on
        ``project_purchase_order_lines``, where the quotation cross-check and its two
        mismatch flags already live, so that comparison is reused rather than rebuilt.
        """
        from app.services import project_po_service as po_svc

        self._assert_unconfirmed(version)
        if version.extraction_state != STATE_DONE:
            raise AppException(
                status_code=409,
                message=(
                    "This document is still being read."
                    if version.extraction_state in (STATE_QUEUED, STATE_RUNNING)
                    else "This document could not be read, so there is nothing to confirm."
                ),
                code="po_version_not_extracted",
            )

        pending = [
            annotation
            for annotation in self._annotations(version.id)
            if annotation.state == ANNOTATION_PROPOSED
        ]
        if pending:
            raise AppException(
                status_code=409,
                message=(
                    f"{len(pending)} handwritten note"
                    f"{'s' if len(pending) > 1 else ''} on this document still need a "
                    "decision. Accept, edit or reject each card first -- a cancellation "
                    "written in pencil is the only place some of these lines exist."
                ),
                code="po_version_annotations_pending",
            )

        lines = self._lines(version.id)
        live = [line for line in lines if not line.is_cancelled]
        if not live:
            raise AppException(
                status_code=409,
                message="Every line on this document is cancelled, so there is nothing to confirm.",
                code="po_version_no_live_lines",
            )

        po = self.get_po(version.purchase_order_id)
        header = (version.extracted_json or {}).get("header") or {}

        number = str(header.get("po_number") or "").strip()
        if number and number.upper() != (po.po_number or "").strip().upper():
            clash = self._po_by_number(po.project_id, number, exclude_id=str(po.id))
            if clash is not None:
                raise AppException(
                    status_code=409,
                    message=(
                        f"PO {clash.po_number} on this project already carries that "
                        "number. Upload this document as a new version of it rather "
                        "than as a second purchase order."
                    ),
                    code="po_number_already_on_project",
                )
            po.po_number = number[:100]

        po_date = _parse_date(header.get("po_date"))
        if po_date is not None:
            po.po_date = po_date
        term_days = _int_or_none(header.get("term"))
        if term_days is not None:
            po.term_days = term_days
        for source_key, attribute, limit in (
            ("sales_person", "sales_person", 120),
            ("customer_order_ref", "customer_order_ref", 180),
        ):
            value = str(header.get(source_key) or "").strip()
            if value:
                setattr(po, attribute, value[:limit])
        remark = str(header.get("remark") or "").strip()
        if remark:
            po.notes = remark

        # Bound BEFORE the lines are written, because `upsert_line` reads
        # `po.quotation_version_id` and is the one place the cross-check runs. A PO that
        # arrived as a scan used to reach here unbound and so got none of the checking a
        # hand-recorded PO gets: every line came out "not quoted" and the panel said, quite
        # correctly, that nothing had been compared against a quoted price.
        self._bind_quotation_version(po)

        # Rewritten, not merged: the confirmed version IS the current statement of what
        # the customer committed to, and a merge would leave lines from a superseded
        # reading standing beside it.
        for existing in po_svc.list_lines(self.db, po_id=po.id):
            po_svc.delete_line(self.db, line=existing)

        written: List[ProjectPurchaseOrderLine] = []
        for line in live:
            code = (line.stock_code_raw or "").strip()
            if not code and line.resolved_product_id is None:
                raise AppException(
                    status_code=422,
                    message=(
                        f"Line {line.line_no} has no stock code and no product. Enter one "
                        "before confirming -- a PO line with neither cannot be checked "
                        "against the quotation."
                    ),
                    code="po_version_line_unidentified",
                )
            written.append(
                po_svc.upsert_line(
                    self.db,
                    po=po,
                    payload={
                        "product_id": line.resolved_product_id,
                        "product_code": code or None,
                        "description": line.description_raw,
                        "unit_price": _money(_to_decimal(line.unit_price)),
                        "quantity": _to_decimal(line.qty) or Decimal("1"),
                        "uom": line.uom_raw,
                        "sort_order": line.line_no,
                    },
                )
            )

        totals = self.recompute_totals(version)
        po.po_amount = totals["lines_total"]
        version.confirmed_by = actor_user_id
        version.confirmed_at = datetime.utcnow()
        self.db.flush()

        self._adopt_pending_successors(po)

        return {
            "purchase_order_id": str(po.id),
            "po_number": po.po_number,
            "po_version_id": str(version.id),
            "version_no": version.version_no,
            "confirmed_at": version.confirmed_at,
            "line_count": len(written),
            "po_amount": po.po_amount,
            "model_mismatch_count": sum(1 for line in written if line.model_mismatch),
            "price_mismatch_count": sum(1 for line in written if line.price_mismatch),
        }

    def _bind_quotation_version(
        self, po: ProjectPurchaseOrder
    ) -> Optional[ProjectQuotationVersion]:
        """Point an unbound PO at the quotation it should be checked against.

        Three rules, and the last one is the reason this is not a one-liner:

        * **An existing binding is never moved.** It was chosen by a person, or by an
          earlier confirm, and re-pointing it would silently change what this PO was
          checked against. A binding to a SUPERSEDED version is legitimate and stays: the
          contractor buys off the document they were given, which is frequently not the
          newest one.
        * **A project with nothing quoted stays unbound.** The panel already says the PO
          is not tied to a quotation version and that nothing is being compared, which is
          the truth in that case.
        * **An ambiguous project stays unbound too.** A development is quoted in scopes,
          and binding to the wrong scope would flag correctly priced lines as "price
          differs" and correctly ordered models as "not quoted". A wrong comparison is
          worse than a stated absence of one, so we bind only when one scope is the
          obvious candidate and leave the manual pick on the PO dialog otherwise.
        """
        if po.quotation_version_id:
            return None

        quotations = (
            self.db.query(ProjectQuotation)
            .filter(ProjectQuotation.project_id == po.project_id)
            .all()
        )
        if not quotations:
            return None

        best_rank = min(_OUTCOME_RANK.get(q.outcome, _OUTCOME_RANK_DEFAULT) for q in quotations)
        candidates = [
            q
            for q in quotations
            if _OUTCOME_RANK.get(q.outcome, _OUTCOME_RANK_DEFAULT) == best_rank
        ]
        if len(candidates) != 1:
            logger.info(
                "PO %s left unbound: %s quotation scopes on project %s are equally good "
                "candidates, so the scope is a person's call",
                po.id,
                len(candidates),
                po.project_id,
            )
            return None

        # Current is MAX(version_no) -- the quotation model has no current pointer and no
        # frozen flag, and reading it any other way would invent a second source of truth.
        version = (
            self.db.query(ProjectQuotationVersion)
            .filter(ProjectQuotationVersion.quotation_id == candidates[0].id)
            .order_by(ProjectQuotationVersion.version_no.desc())
            .first()
        )
        if version is None:
            return None

        po.quotation_version_id = version.id
        self.db.flush()
        return version

    # -------------------------------------------------------- approval handshake

    def approve_po(
        self, *, po: ProjectPurchaseOrder, actor_user_id: str
    ) -> ProjectPurchaseOrder:
        """AC-D8. CS cannot open the SO draft until this has happened (D21)."""
        if po.approved_at is not None:
            raise AppException(
                status_code=409,
                message=(
                    "This purchase order was already approved by "
                    f"{self._user_name(po.approved_by) or 'another user'}."
                ),
                code="po_already_approved",
            )
        # A PO that arrived as a document is approved only once somebody has agreed to
        # what the document said. A PO keyed in by hand has no versions and keeps working
        # on its lines alone, which is the phase-1 path and still legitimate.
        versions = (
            self.db.query(func.count(ProjectPOVersion.id))
            .filter(ProjectPOVersion.purchase_order_id == po.id)
            .scalar()
            or 0
        )
        if versions:
            confirmed = (
                self.db.query(func.count(ProjectPOVersion.id))
                .filter(
                    ProjectPOVersion.purchase_order_id == po.id,
                    ProjectPOVersion.confirmed_at.isnot(None),
                )
                .scalar()
                or 0
            )
            if not confirmed:
                raise AppException(
                    status_code=409,
                    message=(
                        "Confirm the uploaded document first. Approving a purchase order "
                        "nobody has checked against the scan is exactly what the confirm "
                        "screen exists to prevent."
                    ),
                    code="po_version_not_confirmed",
                )
        has_lines = (
            self.db.query(func.count(ProjectPurchaseOrderLine.id))
            .filter(ProjectPurchaseOrderLine.po_id == po.id)
            .scalar()
            or 0
        ) > 0
        if not has_lines:
            raise AppException(
                status_code=409,
                message=(
                    "This purchase order has no lines yet. Confirm an uploaded document "
                    "or enter the lines before approving it."
                ),
                code="po_nothing_to_approve",
            )
        po.approved_by = actor_user_id
        po.approved_at = datetime.utcnow()
        po.status = PO_STATUS_APPROVED
        self.db.flush()
        return po

    def countersign_po(
        self, *, po: ProjectPurchaseOrder, actor_user_id: str
    ) -> ProjectPurchaseOrder:
        if po.approved_at is None:
            raise AppException(
                status_code=409,
                message="A purchase order has to be approved before it can be countersigned.",
                code="po_not_approved",
            )
        if po.countersigned_at is not None:
            raise AppException(
                status_code=409,
                message=(
                    "This purchase order was already countersigned by "
                    f"{self._user_name(po.countersigned_by) or 'another user'}."
                ),
                code="po_already_countersigned",
            )
        if po.approved_by and str(po.approved_by) == str(actor_user_id):
            raise AppException(
                status_code=409,
                message=(
                    "A countersignature has to come from a second person -- that is the "
                    "whole point of it."
                ),
                code="po_countersign_same_user",
            )
        po.countersigned_by = actor_user_id
        po.countersigned_at = datetime.utcnow()
        self.db.flush()
        return po

