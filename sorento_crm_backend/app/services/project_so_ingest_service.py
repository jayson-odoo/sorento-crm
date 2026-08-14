"""Matching an AutoCount sales order back to the one we published (P8a, AC-F11, AC-F11a).

Stage 1 has no ESB and the real document has no spare reference field: `Your Ref No.` is
already the customer PO and `Our Ref No.` is already the project. So the match back is a
NATURAL key - customer, customer PO number, area group - with the line fingerprint used
only to break a tie.

That ordering is the whole subtlety, and it is easy to write backwards. A divergent
document has a DIFFERENT fingerprint by definition, because a difference is what this
slice exists to find. Keying on the fingerprint would report every divergence as
`unmatched`, which is the one outcome that helps nobody.

- exactly one candidate -> matched, whatever the fingerprint says.
- several candidates (finding G4: two sales orders on one PO in one area group) -> the one
  whose fingerprint matches exactly wins. If none or more than one does, the outcome is
  `ambiguous`, NOTHING is written, and a person is asked.
- no candidate -> `unmatched`, and the response says which key was tried.

The transport is deliberately not this file's business. An upload of AutoCount's export
and a stage 2 ESB push both arrive here as an ``IngestDocument``.

## The two numbers (ADR 0010, AC-F2/F3/F5)

The Order Inquiry sheet is exported BEFORE AutoCount has issued the SO number, so the core
`sales_orders` row the sheet creates carries the project's `provisional_ref`. CS's outstanding
book matches on `so_number` alone and inserts on a miss, so the same demand would land twice
under two numbers and `scm.committed_v` would count it twice.

This file is the one place both references are known at once, which is why the reconciliation
lives here rather than in `outstanding_import_service` - that importer stays ignorant of the
module and is unchanged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.project_so import (
    DIVERGENCE_OPEN,
    DIVERGENCE_RESOLVED,
    DIVERGENCE_SOURCE_UPLOAD,
    SO_STATUS_AMENDED,
    SO_STATUS_PUBLISHED,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    ProjectSODivergence,
    ProjectSODivergenceLine,
)
from app.models.projects import Project, ProjectParty, ProjectPurchaseOrder
from app.services.error_handler import AppException
from app.services.project_order_inquiry_import_service import SOURCE_SYSTEM
from app.services.project_so_divergence_engine import (
    OurHeader,
    OurLine,
    TheirHeader,
    TheirLine,
    compare,
    line_fingerprint,
)

logger = logging.getLogger(__name__)

OUTCOME_MATCHED = "matched"
OUTCOME_DIVERGENT = "divergent"
OUTCOME_AMBIGUOUS = "ambiguous"
OUTCOME_UNMATCHED = "unmatched"

#: What a retired provisional row is left as. A STATUS, never a delete, and the word is the
#: one the rest of the codebase already uses for a sales order that is no longer live:
#: `so_history_service` writes `closed` on both the header and its lines, and
#: `outstanding_import_service` states the doctrine outright ("closing is `line_status =
#: 'closed'`, not a delete ... erasing it would make last week's plan unexplainable").
#:
#: It is also the mechanism `scm.committed_v` already honours: the view's WHERE requires
#: `so.status = 'open'` AND `sol.line_status = 'open'`, so closing the header is what removes
#: the double count. The lines are closed with it because several readers in this codebase
#: filter on the line alone, and a retirement that half the readers cannot see is worse than
#: no retirement at all.
RETIRED_ORDER_STATUS = "closed"
RETIRED_LINE_STATUS = "closed"

#: Only rows the Order Inquiry sheet created may be renumbered or retired (AC-F5). The
#: literal is the importer's own stamp, imported rather than repeated so the two cannot drift.
DEMAND_ORIGIN_ORDER_INQUIRY = SOURCE_SYSTEM


@dataclass
class IngestLine:
    product_code: Optional[str]
    qty: Decimal
    unit_price: Decimal
    line_no: Optional[int] = None
    description: Optional[str] = None
    uom: Optional[str] = None
    delivery_date: Optional[date] = None


@dataclass
class IngestDocument:
    """One AutoCount sales order, however it arrived."""

    doc_no: Optional[str] = None
    customer_code: Optional[str] = None
    customer_po_no: Optional[str] = None
    area_group: Optional[str] = None
    terms: Optional[str] = None
    total_amount: Optional[Decimal] = None
    lines: List[IngestLine] = field(default_factory=list)


@dataclass
class IngestResult:
    outcome: str
    project_sales_order_id: Optional[str] = None
    divergence_id: Optional[str] = None
    candidate_ids: List[str] = field(default_factory=list)
    differing_count: int = 0
    message: str = ""


def format_terms(term_days: Optional[int]) -> Optional[str]:
    """As the import file prints them, so a comparison is like for like."""
    return f"*Net {term_days} days" if term_days else None


def _norm(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned.upper() or None


class ProjectSOIngestService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ entry

    def ingest(
        self,
        document: IngestDocument,
        *,
        actor_user_id: Optional[str] = None,
        source: str = DIVERGENCE_SOURCE_UPLOAD,
    ) -> IngestResult:
        candidates = self._candidates(document)
        if not candidates:
            return IngestResult(
                outcome=OUTCOME_UNMATCHED,
                message=(
                    "No published sales order matches customer PO "
                    f"{document.customer_po_no or '(none)'} in area group "
                    f"{document.area_group or '(none)'}."
                ),
            )

        order = self._disambiguate(candidates, document)
        if order is None:
            return IngestResult(
                outcome=OUTCOME_AMBIGUOUS,
                candidate_ids=[row.id for row in candidates],
                message=(
                    f"{len(candidates)} published sales orders share that customer PO and "
                    "area group, and none of them matches the document line for line. "
                    "Pick the one this document belongs to."
                ),
            )

        # AC-F11: adopt the number they gave it. Done before the comparison, because a
        # document that agrees still has to leave our record able to name its counterpart.
        if document.doc_no:
            order.autocount_doc_no = document.doc_no
            self._reconcile_core_order(order, document.doc_no)
            self.db.flush()

        report = compare(*self._ours(order), *self._theirs(document))
        existing = self._open_divergence(order.id)

        if not report.has_differences:
            # Somebody fixed it on their side. Re-ingesting is the honest way to say so.
            if existing is not None:
                existing.status = DIVERGENCE_RESOLVED
                existing.resolved_at = datetime.utcnow()
                existing.compared_count = report.compared_count
                existing.agreeing_count = report.agreeing_count
                existing.differing_count = 0
                self.db.flush()
            return IngestResult(
                outcome=OUTCOME_MATCHED, project_sales_order_id=order.id, differing_count=0
            )

        divergence = self._write(order, document, report, existing=existing, source=source)
        return IngestResult(
            outcome=OUTCOME_DIVERGENT,
            project_sales_order_id=order.id,
            divergence_id=divergence.id,
            differing_count=report.differing_count,
        )

    # ------------------------------------------------------- the two numbers

    def _reconcile_core_order(self, order: ProjectSalesOrder, doc_no: str) -> None:
        """Make the real number and the provisional one name ONE piece of demand.

        Three outcomes, and the third is the one that has to be written down (AC-F5):

        * nothing holds the real number and the sheet made a provisional row -> RENUMBER it
          in place. No second row is created, so nothing has to be merged afterwards.
        * the outstanding book already created the real-numbered row -> LINK `so_id` to it
          and RETIRE the provisional one, so `scm.committed_v` stops counting both.
        * the row at the provisional number is not the sheet's -> nothing at all. Its number
          colliding with ours is an accident, and renaming or closing somebody else's order
          on the strength of a coincidence is the worst thing this function could do.

        `sales_orders.so_number` is UNIQUE, so the rename is only ever attempted after a
        FLUSHED lookup has shown the number free. Flushing first is what makes that check
        honest: a row inserted earlier in this same transaction is otherwise still pending
        and invisible to the query, and the collision would surface as an IntegrityError
        several statements later, with the whole transaction lost.
        """
        # Pending inserts made earlier in this transaction must be visible to both lookups
        # below, or "the number is free" is a statement about the database as it was.
        self.db.flush()

        real = (
            self.db.query(SalesOrder).filter(SalesOrder.so_number == doc_no).first()
        )
        provisional = None
        if order.provisional_ref:
            provisional = (
                self.db.query(SalesOrder)
                .filter(
                    SalesOrder.so_number == order.provisional_ref,
                    SalesOrder.demand_origin == DEMAND_ORIGIN_ORDER_INQUIRY,
                )
                .first()
            )

        if real is None:
            if provisional is None:
                return
            # AC-F2. The row IS this order; only its number was a placeholder.
            provisional.so_number = doc_no
            self.db.flush()
            order.so_id = provisional.id
            logger.info(
                "project SO %s: renumbered sheet-created sales order %s to %s",
                order.id, provisional.id, doc_no,
            )
            return

        # AC-F3. CS got there first, so their row is the one that counts. `so_id` is
        # repointed only when it is unset or still on the row about to be retired: a link a
        # person put somewhere else is not this function's to overwrite.
        if order.so_id is None or (provisional is not None and order.so_id == provisional.id):
            order.so_id = real.id
        if provisional is not None and provisional.id != real.id:
            self._retire(provisional, doc_no)

    def _retire(self, provisional: SalesOrder, doc_no: str) -> None:
        """Close the sheet's row so the demand is counted under the real number only.

        Idempotent by the status check: a second upload of the same document finds the row
        already closed and writes nothing, so the note below is stamped exactly once.
        """
        if provisional.status == RETIRED_ORDER_STATUS:
            return

        provisional.status = RETIRED_ORDER_STATUS
        self.db.query(SalesOrderLine).filter(
            SalesOrderLine.sales_order_id == str(provisional.id),
            SalesOrderLine.line_status != RETIRED_LINE_STATUS,
        ).update({"line_status": RETIRED_LINE_STATUS}, synchronize_session=False)

        # The row survives, so it has to be able to say why it stopped counting. Nothing
        # else on the table carries that: `demand_origin` is history and stays as it is,
        # and `source_doc_no` belongs to `so_history_service` (ADR 0010).
        note = f"Retired: superseded by {doc_no}"
        provisional.internal_note = (
            f"{provisional.internal_note} | {note}" if provisional.internal_note else note
        )
        self.db.flush()
        logger.info(
            "project SO: retired provisional sales order %s, superseded by %s",
            provisional.id, doc_no,
        )

    # ------------------------------------------------------------- match back

    def _candidates(self, document: IngestDocument) -> List[ProjectSalesOrder]:
        po_no = _norm(document.customer_po_no)
        if not po_no:
            return []

        query = (
            self.db.query(ProjectSalesOrder)
            .join(
                ProjectPurchaseOrder,
                ProjectPurchaseOrder.id == ProjectSalesOrder.purchase_order_id,
            )
            .filter(
                ProjectSalesOrder.status.in_((SO_STATUS_PUBLISHED, SO_STATUS_AMENDED)),
                ProjectPurchaseOrder.po_number.ilike(po_no),
            )
        )
        rows = [
            row
            for row in query.all()
            if _norm(row.area_group) == _norm(document.area_group)
        ]

        customer_code = _norm(document.customer_code)
        if customer_code and rows:
            narrowed = [
                row for row in rows if _norm(self._customer_code(row)) == customer_code
            ]
            # A debtor we cannot resolve is not evidence AGAINST a match: a parked
            # pre-order is deliberately raised under another debtor (D18).
            if narrowed:
                rows = narrowed
        return rows

    def _disambiguate(
        self, candidates: Sequence[ProjectSalesOrder], document: IngestDocument
    ) -> Optional[ProjectSalesOrder]:
        if len(candidates) == 1:
            return candidates[0]

        theirs = line_fingerprint(
            [(line.product_code, line.qty, line.delivery_date) for line in document.lines]
        )
        exact = [row for row in candidates if self._fingerprint(row) == theirs]
        return exact[0] if len(exact) == 1 else None

    def _fingerprint(self, order: ProjectSalesOrder) -> str:
        return line_fingerprint(
            [
                (self._product_code(line.product_id), line.qty, line.delivery_date)
                for line in self._lines(order.id)
            ]
        )

    # -------------------------------------------------------------- documents

    def _ours(self, order: ProjectSalesOrder):
        po = (
            self.db.query(ProjectPurchaseOrder)
            .filter(ProjectPurchaseOrder.id == order.purchase_order_id)
            .first()
            if order.purchase_order_id
            else None
        )
        header = OurHeader(
            customer_code=self._customer_code(order),
            customer_po_no=po.po_number if po else None,
            terms=format_terms(po.term_days if po else None),
            total_amount=order.total_amount,
        )
        lines = [
            OurLine(
                so_line_id=line.id,
                line_no=line.line_no,
                product_code=self._product_code(line.product_id),
                description=line.description,
                qty=line.qty,
                unit_price=line.unit_price,
                uom=line.uom,
                delivery_date=line.delivery_date,
            )
            for line in self._lines(order.id)
        ]
        return header, lines

    def _theirs(self, document: IngestDocument):
        header = TheirHeader(
            doc_no=document.doc_no,
            customer_code=document.customer_code,
            customer_po_no=document.customer_po_no,
            terms=document.terms,
            total_amount=document.total_amount,
        )
        lines = [
            TheirLine(
                line_no=line.line_no,
                product_code=line.product_code,
                description=line.description,
                qty=line.qty,
                unit_price=line.unit_price,
                uom=line.uom,
                delivery_date=line.delivery_date,
            )
            for line in document.lines
        ]
        return header, lines

    # ------------------------------------------------------------ persistence

    def _write(
        self,
        order: ProjectSalesOrder,
        document: IngestDocument,
        report,
        *,
        existing: Optional[ProjectSODivergence],
        source: str,
    ) -> ProjectSODivergence:
        """One OPEN divergence per sales order, recomputed rather than stacked.

        A CS uploading the same export twice must see one reconciliation. Rows already
        answered are discarded along with the rest: they were answers about a comparison
        that no longer exists, and carrying them forward would silently apply a decision
        to a value nobody looked at.
        """
        if existing is not None:
            self.db.query(ProjectSODivergenceLine).filter(
                ProjectSODivergenceLine.divergence_id == existing.id
            ).delete(synchronize_session=False)
            divergence = existing
            divergence.corrective_publish_required = False
            divergence.corrective_publish_taken_at = None
        else:
            divergence = ProjectSODivergence(
                company_id=order.company_id,
                project_sales_order_id=order.id,
                status=DIVERGENCE_OPEN,
            )
            self.db.add(divergence)

        divergence.autocount_doc_no = document.doc_no
        divergence.ingest_source = source
        divergence.status = DIVERGENCE_OPEN
        divergence.detected_at = datetime.utcnow()
        divergence.resolved_at = None
        divergence.resolved_by = None
        divergence.compared_count = report.compared_count
        divergence.agreeing_count = report.agreeing_count
        divergence.differing_count = report.differing_count
        self.db.flush()

        for row in report.rows:
            self.db.add(
                ProjectSODivergenceLine(
                    company_id=order.company_id,
                    divergence_id=divergence.id,
                    scope=row.scope,
                    presence=row.presence,
                    so_line_id=row.so_line_id,
                    line_no=row.line_no,
                    product_code=row.product_code,
                    ours_json=row.ours,
                    theirs_json=row.theirs,
                    differing_fields=row.differing_fields,
                )
            )
        self.db.flush()
        return divergence

    # ------------------------------------------------------------------ small

    def _open_divergence(self, pso_id: str) -> Optional[ProjectSODivergence]:
        return (
            self.db.query(ProjectSODivergence)
            .filter(
                ProjectSODivergence.project_sales_order_id == pso_id,
                ProjectSODivergence.status == DIVERGENCE_OPEN,
            )
            .first()
        )

    def _lines(self, pso_id: str) -> List[ProjectSalesOrderLine]:
        return (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == pso_id)
            .order_by(ProjectSalesOrderLine.line_no.asc())
            .all()
        )

    def _product_code(self, product_id: Optional[str]) -> Optional[str]:
        if not product_id:
            return None
        product = self.db.query(Product).filter(Product.id == product_id).first()
        return product.product_code if product else None

    def _customer_code(self, order: ProjectSalesOrder) -> Optional[str]:
        po = (
            self.db.query(ProjectPurchaseOrder)
            .filter(ProjectPurchaseOrder.id == order.purchase_order_id)
            .first()
            if order.purchase_order_id
            else None
        )
        if po is None or not po.issuing_party_id:
            return None
        party = (
            self.db.query(ProjectParty).filter(ProjectParty.id == po.issuing_party_id).first()
        )
        if party is None or not party.customer_id:
            return None
        customer = (
            self.db.query(Customer).filter(Customer.id == party.customer_id).first()
        )
        return customer.customer_code if customer else None
