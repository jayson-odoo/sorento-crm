"""Answering a divergence: per row, one side wins, and it is recorded (P8a, AC-N3..N7).

Neither side wins by default. ACCEPT THEIRS updates our record; KEEP OURS leaves it alone
and queues a corrective document back to AutoCount. Every answer carries a reason, because
AC-N7 asks for who, when, which side won **and why**, and a resolution log without the why
answers three of those four in six months' time.

Two deliberate refusals to be clever, both from `PLAN-project-so-divergence.md`:

**A line AutoCount dropped is CANCELLED, not deleted.** Allocations, cross-project claims
and order inquiry rows point at it. Zero quantity is already this system's word for a
cancelled balance, and it keeps the audit trail a delete would destroy.

**A header difference never rewrites the customer PO.** Terms and the PO number belong to
the customer's document; AutoCount's copy of them is not authority over it. Accepting
theirs on a header row records the decision and changes nothing, which is stated on screen
rather than left to be discovered.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.project_so import (
    DIVERGENCE_OPEN,
    DIVERGENCE_RESOLVED,
    RESOLUTION_ACCEPT_THEIRS,
    RESOLUTION_KEEP_OURS,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    ProjectSODivergence,
    ProjectSODivergenceLine,
)
from app.models.projects import Project
from app.services.error_handler import AppException
from app.services.project_so_divergence_engine import (
    PRESENCE_BOTH,
    PRESENCE_OURS_ONLY,
    PRESENCE_THEIRS_ONLY,
    SCOPE_HEADER,
    SCOPE_LINE,
)

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_MONEY = Decimal("0.01")

RESOLUTIONS = (RESOLUTION_ACCEPT_THEIRS, RESOLUTION_KEEP_OURS)


def _dec(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _as_date(value: Any):
    from datetime import date

    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


class ProjectSODivergenceService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ guard

    def assert_amendable(self, pso_id: str) -> None:
        """AC-N5. Amending a record we already know is wrong is how two systems drift
        apart for good, so the amendment waits for the reconciliation."""
        open_row = self._open_for_order(pso_id)
        if open_row is None:
            return
        raise AppException(
            status_code=409,
            message=(
                f"This sales order has {open_row.differing_count} unreconciled "
                "difference(s) against AutoCount. Resolve them before amending it."
            ),
            code="so_divergence_unresolved",
        )

    # ------------------------------------------------------------------ reads

    def list_divergences(
        self,
        *,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """AC-N6: a stack of unresolved reconciliations is visible, not discovered."""
        query = (
            self.db.query(ProjectSODivergence, ProjectSalesOrder, Project)
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == ProjectSODivergence.project_sales_order_id,
            )
            .join(Project, Project.id == ProjectSalesOrder.project_id)
        )
        if status:
            query = query.filter(ProjectSODivergence.status == status)
        if project_id:
            query = query.filter(ProjectSalesOrder.project_id == project_id)

        total = query.count()
        rows = (
            query.order_by(ProjectSODivergence.detected_at.asc())
            .offset(max(page - 1, 0) * limit)
            .limit(limit)
            .all()
        )
        now = datetime.utcnow()
        data = [
            {
                "id": divergence.id,
                "project_sales_order_id": order.id,
                "project_id": project.id,
                "project_title": project.title,
                "sales_order_ref": order.autocount_doc_no or order.provisional_ref,
                "provisional_ref": order.provisional_ref,
                "autocount_doc_no": divergence.autocount_doc_no,
                "status": divergence.status,
                "compared_count": divergence.compared_count,
                "agreeing_count": divergence.agreeing_count,
                "differing_count": divergence.differing_count,
                "unresolved_count": self._unresolved_count(divergence.id),
                "corrective_publish_required": divergence.corrective_publish_required,
                "detected_at": divergence.detected_at,
                "resolved_at": divergence.resolved_at,
                "age_days": (now - divergence.detected_at).days
                if divergence.detected_at
                else 0,
            }
            for divergence, order, project in rows
        ]
        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": not data,
        }

    def get_divergence(self, divergence_id: str) -> Dict[str, Any]:
        divergence = self._or_404(divergence_id)
        order = (
            self.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id == divergence.project_sales_order_id)
            .first()
        )
        project = (
            self.db.query(Project).filter(Project.id == order.project_id).first()
            if order
            else None
        )
        rows = self._rows(divergence_id)
        return {
            "id": divergence.id,
            "project_sales_order_id": divergence.project_sales_order_id,
            "project_id": order.project_id if order else None,
            "project_title": project.title if project else None,
            "provisional_ref": order.provisional_ref if order else None,
            "autocount_doc_no": divergence.autocount_doc_no,
            "status": divergence.status,
            "ingest_source": divergence.ingest_source,
            "compared_count": divergence.compared_count,
            "agreeing_count": divergence.agreeing_count,
            "differing_count": divergence.differing_count,
            "unresolved_count": self._unresolved_count(divergence_id),
            "corrective_publish_required": divergence.corrective_publish_required,
            "corrective_publish_taken_at": divergence.corrective_publish_taken_at,
            "detected_at": divergence.detected_at,
            "resolved_at": divergence.resolved_at,
            "resolved_by": divergence.resolved_by,
            "rows": [
                {
                    "id": row.id,
                    "scope": row.scope,
                    "presence": row.presence,
                    "so_line_id": row.so_line_id,
                    "line_no": row.line_no,
                    "product_code": row.product_code,
                    "ours": row.ours_json or {},
                    "theirs": row.theirs_json or {},
                    "differing_fields": row.differing_fields or [],
                    "needs_answer": self._needs_answer(row),
                    "resolution": row.resolution,
                    "reason": row.reason,
                    "resolved_by": row.resolved_by,
                    "resolved_at": row.resolved_at,
                }
                for row in rows
            ],
        }

    # ------------------------------------------------------------- resolution

    def resolve_line(
        self,
        divergence_id: str,
        line_id: str,
        *,
        resolution: str,
        reason: str,
        actor_user_id: str,
    ) -> ProjectSODivergence:
        divergence = self._or_404(divergence_id)
        if resolution not in RESOLUTIONS:
            raise AppException(
                status_code=422,
                message=f"Unknown resolution {resolution!r}.",
                code="divergence_resolution_unknown",
            )
        if not (reason or "").strip():
            raise AppException(
                status_code=422,
                message=(
                    "Say why this side won. A reconciliation without a reason cannot "
                    "answer the question it exists to answer."
                ),
                code="divergence_reason_required",
            )

        row = (
            self.db.query(ProjectSODivergenceLine)
            .filter(
                ProjectSODivergenceLine.id == line_id,
                ProjectSODivergenceLine.divergence_id == divergence_id,
            )
            .first()
        )
        if row is None:
            raise AppException(
                status_code=404,
                message="That row is not part of this reconciliation.",
                code="divergence_line_not_found",
            )
        if row.resolution is not None:
            raise AppException(
                status_code=409,
                message="That row has already been answered.",
                code="divergence_line_already_resolved",
            )
        if not self._needs_answer(row):
            raise AppException(
                status_code=422,
                message="That row agrees on both sides, so there is nothing to answer.",
                code="divergence_line_agrees",
            )

        order = (
            self.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id == divergence.project_sales_order_id)
            .first()
        )
        if order is None:
            raise AppException(
                status_code=404, message="Sales order not found.", code="so_not_found"
            )

        if resolution == RESOLUTION_ACCEPT_THEIRS:
            self._accept_theirs(order, row)
        else:
            divergence.corrective_publish_required = True

        row.resolution = resolution
        row.reason = reason.strip()
        row.resolved_by = actor_user_id
        row.resolved_at = datetime.utcnow()
        self.db.flush()

        self._recompute_total(order)
        self._close_if_answered(divergence, actor_user_id)
        self.db.flush()
        return divergence

    def _accept_theirs(self, order: ProjectSalesOrder, row: ProjectSODivergenceLine) -> None:
        if row.scope == SCOPE_HEADER:
            # Recorded, never applied. The customer's document is not AutoCount's to edit.
            return

        theirs = row.theirs_json or {}

        if row.presence == PRESENCE_OURS_ONLY:
            line = self._line_or_404(row.so_line_id)
            line.qty = _ZERO
            line.amount = _ZERO
            self.db.flush()
            return

        if row.presence == PRESENCE_THEIRS_ONLY:
            line = self._insert_line(order, theirs)
            row.so_line_id = line.id
            self.db.flush()
            return

        line = self._line_or_404(row.so_line_id)
        for field in row.differing_fields or []:
            if field == "qty":
                line.qty = _dec(theirs.get("qty")) or _ZERO
            elif field == "unit_price":
                line.unit_price = _dec(theirs.get("unit_price")) or _ZERO
            elif field == "delivery_date":
                line.delivery_date = _as_date(theirs.get("delivery_date"))
        line.amount = (Decimal(line.qty) * Decimal(line.unit_price)).quantize(_MONEY)
        self.db.flush()

    def _insert_line(
        self, order: ProjectSalesOrder, theirs: Dict[str, Any]
    ) -> ProjectSalesOrderLine:
        code = (theirs.get("product_code") or "").strip()
        product = (
            self.db.query(Product).filter(Product.product_code.ilike(code)).first()
            if code
            else None
        )
        if product is None:
            raise AppException(
                status_code=422,
                message=(
                    f"AutoCount's line names {code or '(no product code)'}, which is not a "
                    "product here. Adopting it would invent a product; add it first, or "
                    "keep ours and correct their document."
                ),
                code="divergence_product_unknown",
            )
        qty = _dec(theirs.get("qty")) or _ZERO
        unit_price = _dec(theirs.get("unit_price")) or _ZERO
        highest = max(
            (line.line_no or 0 for line in self._lines(order.id)),
            default=0,
        )
        line = ProjectSalesOrderLine(
            company_id=order.company_id,
            project_sales_order_id=order.id,
            line_no=highest + 1,
            product_id=product.id,
            description=theirs.get("description") or product.product_name,
            qty=qty,
            uom=theirs.get("uom"),
            unit_price=unit_price,
            amount=(qty * unit_price).quantize(_MONEY),
            delivery_date=_as_date(theirs.get("delivery_date")),
            explosion_source="direct",
        )
        self.db.add(line)
        self.db.flush()
        return line

    def _close_if_answered(
        self, divergence: ProjectSODivergence, actor_user_id: str
    ) -> None:
        if self._unresolved_count(divergence.id) > 0:
            return
        divergence.status = DIVERGENCE_RESOLVED
        divergence.resolved_at = datetime.utcnow()
        divergence.resolved_by = actor_user_id

    # ------------------------------------------------------- corrective publish

    def corrective_import_file(self, divergence_id: str) -> Tuple[str, str]:
        """AC-N4's other half: our values, going back to AutoCount.

        Generated per request and stamped when taken, exactly as the original import file
        is: a stored copy goes stale the moment anything republishes.
        """
        divergence = self._or_404(divergence_id)
        if not divergence.corrective_publish_required:
            raise AppException(
                status_code=409,
                message=(
                    "Nothing on this reconciliation was answered KEEP OURS, so AutoCount "
                    "has nothing to correct."
                ),
                code="divergence_no_corrective_publish",
            )
        from app.services.project_so_draft_service import ProjectSODraftService

        service = ProjectSODraftService(self.db)
        order = service.get_order(divergence.project_sales_order_id)
        filename, body = service.import_file(order)
        divergence.corrective_publish_taken_at = datetime.utcnow()
        self.db.flush()
        return filename, body

    # ------------------------------------------------------------------ small

    def _or_404(self, divergence_id: str) -> ProjectSODivergence:
        row = (
            self.db.query(ProjectSODivergence)
            .filter(ProjectSODivergence.id == divergence_id)
            .first()
        )
        if row is None:
            raise AppException(
                status_code=404,
                message="Reconciliation not found.",
                code="divergence_not_found",
            )
        return row

    def _open_for_order(self, pso_id: str) -> Optional[ProjectSODivergence]:
        return (
            self.db.query(ProjectSODivergence)
            .filter(
                ProjectSODivergence.project_sales_order_id == pso_id,
                ProjectSODivergence.status == DIVERGENCE_OPEN,
            )
            .first()
        )

    def _rows(self, divergence_id: str) -> List[ProjectSODivergenceLine]:
        return (
            self.db.query(ProjectSODivergenceLine)
            .filter(ProjectSODivergenceLine.divergence_id == divergence_id)
            .order_by(
                ProjectSODivergenceLine.scope.desc(),
                ProjectSODivergenceLine.line_no.asc().nullslast(),
            )
            .all()
        )

    def _needs_answer(self, row: ProjectSODivergenceLine) -> bool:
        return bool(row.differing_fields) or row.presence != PRESENCE_BOTH

    def _unresolved_count(self, divergence_id: str) -> int:
        return sum(
            1
            for row in self._rows(divergence_id)
            if self._needs_answer(row) and row.resolution is None
        )

    def _lines(self, pso_id: str) -> List[ProjectSalesOrderLine]:
        return (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == pso_id)
            .order_by(ProjectSalesOrderLine.line_no.asc())
            .all()
        )

    def _line_or_404(self, so_line_id: Optional[str]) -> ProjectSalesOrderLine:
        line = (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.id == so_line_id)
            .first()
            if so_line_id
            else None
        )
        if line is None:
            raise AppException(
                status_code=404,
                message="That sales order line no longer exists.",
                code="so_line_not_found",
            )
        return line

    def _recompute_total(self, order: ProjectSalesOrder) -> None:
        total = sum((Decimal(line.amount or 0) for line in self._lines(order.id)), _ZERO)
        order.total_amount = total.quantize(_MONEY)
        self.db.flush()
