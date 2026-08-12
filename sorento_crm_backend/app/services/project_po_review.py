"""The handwriting REVIEW: accepting, editing and rejecting what the pencil said.

One of the three mixins ``ProjectPOExtractionService`` is assembled from (2026-08-12
audit split). Nothing handwritten is ever applied by a model; these are the actions
a PERSON takes on a proposed card, plus the successor-PO adoption that a cancel-and-
redirect card triggers. Methods are verbatim from the original service.
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


class POAnnotationReviewMixin:
    """Requires ``self.db`` and the lifecycle lookups."""

    db: Session

    # -------------------------------------------------------- annotation actions

    def accept_annotation(
        self,
        *,
        annotation: ProjectPOAnnotation,
        actor_user_id: str,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        version = self.get_version(annotation.po_version_id)
        self._assert_actionable(version, annotation)
        purchase_order = self.get_po(version.purchase_order_id)
        applied = self._apply_annotation(annotation, purchase_order)
        self._stamp_action(annotation, ANNOTATION_ACCEPTED, actor_user_id, note)
        return {
            "annotation": annotation,
            "applied": applied,
            "totals": self.recompute_totals(version),
        }

    def edit_annotation(
        self,
        *,
        annotation: ProjectPOAnnotation,
        actor_user_id: str,
        interpretation: str,
        interpretation_json: Optional[Dict[str, Any]] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """The human's reading wins, then applies exactly as an accept does."""
        version = self.get_version(annotation.po_version_id)
        self._assert_actionable(version, annotation)
        reading = (interpretation or "").strip()
        if reading not in INTERPRETATIONS:
            raise AppException(
                status_code=422,
                message=(
                    "Unknown reading. Use one of: "
                    + ", ".join(sorted(INTERPRETATIONS))
                    + "."
                ),
                code="po_annotation_interpretation_unknown",
            )
        # Merged, not replaced: the screen sends the fields it has an input for, and a
        # key it does not render (the strike-through marker, say) must survive an edit.
        merged = dict(annotation.interpretation_json or {})
        merged.update(interpretation_json or {})
        if _payload_value(merged, KEY_LINE_NOS) is None:
            merged[KEY_LINE_NOS] = _int_list(annotation.refers_to_lines)
        annotation.interpretation = reading
        annotation.interpretation_json = merged
        if reading in (INTERP_CANCEL, INTERP_AMEND_CODE, INTERP_AMEND_DESCRIPTION):
            # The lines the reader named are also the lines the card now refers to, so
            # the card and its effect can never disagree on screen.
            annotation.refers_to_lines = _int_list(_payload_value(merged, KEY_LINE_NOS))

        purchase_order = self.get_po(version.purchase_order_id)
        applied = self._apply_annotation(annotation, purchase_order)
        self._stamp_action(annotation, ANNOTATION_EDITED, actor_user_id, note)
        return {
            "annotation": annotation,
            "applied": applied,
            "totals": self.recompute_totals(version),
        }

    def reject_annotation(
        self, *, annotation: ProjectPOAnnotation, actor_user_id: str, note: str
    ) -> Dict[str, Any]:
        """Recorded as rejected, never deleted (AC-D4). Nothing is applied."""
        version = self.get_version(annotation.po_version_id)
        self._assert_actionable(version, annotation)
        if not (note or "").strip():
            raise AppException(
                status_code=422,
                message=(
                    "A rejection needs a reason: it is the only thing that explains "
                    "later why the pencil was ignored."
                ),
                code="po_annotation_reason_required",
            )
        self._stamp_action(annotation, ANNOTATION_REJECTED, actor_user_id, note)
        return {
            "annotation": annotation,
            "applied": {
                "cancelled_line_nos": [],
                "amended_line_nos": [],
                "successor_po_number": None,
                "successor_po_linked": False,
            },
            "totals": self.recompute_totals(version),
        }

    def _assert_actionable(
        self, version: ProjectPOVersion, annotation: ProjectPOAnnotation
    ) -> None:
        self._assert_unconfirmed(version)
        if annotation.state != ANNOTATION_PROPOSED:
            raise AppException(
                status_code=409,
                message=(
                    f"This card was already {annotation.state} by "
                    f"{self._user_name(annotation.actioned_by) or 'another user'}. Correct "
                    "the line itself if the decision needs changing."
                ),
                code="po_annotation_already_actioned",
            )

    def _stamp_action(
        self,
        annotation: ProjectPOAnnotation,
        state: str,
        actor_user_id: str,
        note: Optional[str],
    ) -> None:
        annotation.state = state
        annotation.actioned_by = actor_user_id
        annotation.actioned_at = datetime.utcnow()
        annotation.action_note = (note or "").strip() or None
        self.db.flush()

    def _apply_annotation(
        self, annotation: ProjectPOAnnotation, purchase_order: ProjectPurchaseOrder
    ) -> Dict[str, Any]:
        """The only place a handwritten note changes anything (D11)."""
        payload = dict(annotation.interpretation_json or {})
        interpretation = annotation.interpretation or INTERP_OTHER
        line_nos = _int_list(_payload_value(payload, KEY_LINE_NOS)) or _int_list(
            annotation.refers_to_lines
        )
        wanted = set(line_nos)
        lines = [
            line for line in self._lines(annotation.po_version_id) if line.line_no in wanted
        ]
        applied: Dict[str, Any] = {
            "cancelled_line_nos": [],
            "amended_line_nos": [],
            "successor_po_number": None,
            "successor_po_linked": False,
        }

        if interpretation in (INTERP_CANCEL, INTERP_AMEND_CODE, INTERP_AMEND_DESCRIPTION):
            if not lines:
                raise AppException(
                    status_code=422,
                    message=(
                        "This card does not name a line that exists on the document. Edit "
                        "it to say which printed line the note is about."
                    ),
                    code="po_annotation_lines_unknown",
                )

        if interpretation == INTERP_CANCEL:
            for line in lines:
                line.is_cancelled = True
                applied["cancelled_line_nos"].append(line.line_no)
        elif interpretation == INTERP_AMEND_CODE:
            code = str(_payload_value(payload, KEY_CODE) or "").strip()
            if not code:
                raise AppException(
                    status_code=422,
                    message=(
                        "This note amends a stock code but does not say which code. Edit "
                        "the card and enter it."
                    ),
                    code="po_annotation_code_required",
                )
            for line in lines:
                line.stock_code_raw = code[:180]
                if line.resolution_source != "manual":
                    line.resolved_product_id, line.resolution_source = self._resolve_product(
                        line.stock_code_raw, line.description_raw, company_id=line.company_id
                    )
                applied["amended_line_nos"].append(line.line_no)
        elif interpretation == INTERP_AMEND_DESCRIPTION:
            description = str(_payload_value(payload, KEY_DESCRIPTION) or "").strip()
            if not description:
                raise AppException(
                    status_code=422,
                    message=(
                        "This note amends a description but does not say what to. Edit the "
                        "card and enter it."
                    ),
                    code="po_annotation_description_required",
                )
            for line in lines:
                line.description_raw = description
                applied["amended_line_nos"].append(line.line_no)

        # A successor pointer can ride on a cancellation ("cancel - refer to New P/O
        # HQ/26/05/087"), which is how the client actually writes it.
        successor = str(_payload_value(payload, KEY_PO_NUMBER) or "").strip()
        if interpretation == INTERP_SUCCESSOR_PO and not successor:
            raise AppException(
                status_code=422,
                message=(
                    "This note points at another purchase order but does not name it. Edit "
                    "the card and enter the PO number."
                ),
                code="po_annotation_successor_required",
            )
        if successor:
            applied["successor_po_number"] = successor
            applied["successor_po_linked"] = self._link_successor(purchase_order, successor)
        self.db.flush()
        return applied

    def _link_successor(self, po: ProjectPurchaseOrder, number: str) -> bool:
        """Wire the supersede pointer, if the successor document has arrived (AC-D7).

        A pencil note names the successor months before that PO is uploaded, so the
        text pointer stands alone on the card until then and this returns False. The
        link is made from the other direction as well, by ``_adopt_pending_successors``
        when the named PO finally appears.
        """
        successor = self._po_by_number(po.project_id, number, exclude_id=str(po.id))
        if successor is None:
            return False
        po.superseded_by_po_id = successor.id
        successor.supersedes_po_number = (po.po_number or None)
        self.db.flush()
        return True

    def _adopt_pending_successors(self, po: ProjectPurchaseOrder) -> None:
        """Close the loop when a PO named in an earlier pencil note finally arrives."""
        number = (po.po_number or "").strip()
        if not number:
            return
        rows = (
            self.db.query(ProjectPOAnnotation, ProjectPurchaseOrder)
            .join(ProjectPOVersion, ProjectPOAnnotation.po_version_id == ProjectPOVersion.id)
            .join(
                ProjectPurchaseOrder,
                ProjectPOVersion.purchase_order_id == ProjectPurchaseOrder.id,
            )
            .filter(
                ProjectPurchaseOrder.project_id == po.project_id,
                ProjectPurchaseOrder.id != po.id,
                ProjectPOAnnotation.state.in_([ANNOTATION_ACCEPTED, ANNOTATION_EDITED]),
            )
            .all()
        )
        for annotation, predecessor in rows:
            payload = dict(annotation.interpretation_json or {})
            named = str(_payload_value(payload, KEY_PO_NUMBER) or "").strip()
            if named and named.upper() == number.upper():
                predecessor.superseded_by_po_id = po.id
                po.supersedes_po_number = predecessor.po_number or None
        self.db.flush()

