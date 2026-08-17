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

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import SQLAlchemyError
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
from app.models.scm import OrderLinkClaim
from app.services.company_scope import company_scope
from app.services.error_handler import AppException
from app.services.project_order_inquiry_import_service import (
    SOURCE as CLAIM_SOURCE_ORDER_INQUIRY,
)
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


def _same_company(row: SalesOrder, order: ProjectSalesOrder) -> bool:
    """Whether a core row found by an UNSCOPED lookup belongs to this project's company.

    A missing `company_id` on either side counts as a match rather than as a foreign row.
    Postgres has `sales_orders.company_id` NOT NULL since migration 305, so a null here is
    a pre-isolation row or a fixture that never went through the insert auto-stamp, and
    neither is evidence that somebody else owns it.
    """
    theirs = getattr(row, "company_id", None)
    ours = order.company_id
    if theirs is None or ours is None:
        return True
    return str(theirs) == str(ours)


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
            self.reconcile_core_order(order, document.doc_no)
            self.db.flush()

        # AC-A01: the line half, in the SAME call. The upload is the moment both documents
        # are in hand, so leaving the lines to a second step somebody has to remember is how
        # an order sits unreconciled with nothing on screen saying why. Imported here rather
        # than at module scope because that service calls back into this one for the header.
        if order.so_id:
            from app.services.project_so_reconciliation_service import (
                ProjectSOReconciliationService,
            )

            # Best effort, and inside a savepoint. Adopting the document number and
            # recording the divergence are what the upload was FOR; a line write that
            # loses a race on `uq_projects_so_line_core_line` must not take those down
            # with it, and re-running the reconciliation from the sheet is one button.
            # The savepoint is what makes that survivable: an IntegrityError leaves the
            # transaction unusable otherwise, so the divergence write would fail too.
            try:
                with self.db.begin_nested():
                    ProjectSOReconciliationService(self.db).reconcile(order)
            except (AppException, SQLAlchemyError) as exc:
                logger.warning(
                    "Reconciling the lines of sales order %s against AutoCount document "
                    "%s failed (%s). The document number and the comparison stand; the "
                    "lines can be re-run from the sales order.",
                    order.provisional_ref,
                    document.doc_no,
                    exc,
                )

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

    def reconcile_core_order(self, order: ProjectSalesOrder, doc_no: str) -> None:
        """Make the real number and the provisional one name ONE piece of demand.

        Four outcomes, and the last two are the ones that have to be written down (AC-F5):

        * nothing holds the real number and the sheet made a provisional row -> RENUMBER it
          in place. No second row is created, so nothing has to be merged afterwards.
        * the outstanding book already created the real-numbered row -> LINK `so_id` to it
          and RETIRE the provisional one, so `scm.committed_v` stops counting both.
        * the row at the provisional number is not the sheet's -> nothing at all. Its number
          colliding with ours is an accident, and renaming or closing somebody else's order
          on the strength of a coincidence is the worst thing this function could do.
        * the real number is held by ANOTHER COMPANY's row -> nothing at all, and a warning
          naming both numbers and both companies. Isolation is fail-closed: a link across
          companies is never made, not even to stop a double count, because the double
          count is a reporting error and a cross-company link is a data breach.

        Both existence checks run UNSCOPED, and that is load bearing. `sales_orders.so_number`
        is unique across the WHOLE table, but `company_scope` injects its predicate into
        SELECTs only. A scoped lookup therefore reports "the number is free" about our
        company rather than about the unique index, and the rename that follows dies on the
        index instead - an IntegrityError several statements later, with the entire ingest
        transaction lost. Reading unscoped and comparing the company in the open is the only
        version of this check that can be honest; the comparison is right below.

        Flushing first matters for the same reason: a row inserted earlier in this same
        transaction is otherwise still pending and invisible to the query.
        """
        # Pending inserts made earlier in this transaction must be visible to both lookups
        # below, or "the number is free" is a statement about the database as it was.
        self.db.flush()

        # `None` is the sanctioned all-companies scope (app.models.base.company_scope); the
        # previous scope is restored on exit, so nothing later in the ingest reads unscoped.
        with company_scope(self.db, None):
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

        if real is not None and not _same_company(real, order):
            logger.warning(
                "project SO %s (company %s): AutoCount number %s is held by sales order %s "
                "in company %s, so nothing was reconciled. The provisional row %s stays open "
                "and so_id is unchanged.",
                order.id, order.company_id, doc_no, real.id, real.company_id,
                order.provisional_ref,
            )
            return

        if provisional is not None and not _same_company(provisional, order):
            # Same accident as a foreign `demand_origin`, one company further out: the sheet
            # stamp matches but the row is not ours to rename, retire or adopt.
            logger.warning(
                "project SO %s (company %s): provisional number %s is held by sales order %s "
                "in company %s, which this reconciliation leaves alone.",
                order.id, order.company_id, order.provisional_ref, provisional.id,
                provisional.company_id,
            )
            provisional = None

        if real is None:
            if provisional is None:
                return
            # AC-F2. The row IS this order; only its number was a placeholder.
            provisional.so_number = doc_no
            self.db.flush()
            # Every claim naming the placeholder now names a number that no longer exists,
            # resolved ones included: the row moved, so the claim has to move with it.
            self._repoint_claims(order, doc_no, unresolved_only=False)
            # Same narrowness as the merge branch below (AC-F5): a link a person put on some
            # other row is not this function's to overwrite.
            if order.so_id is None or order.so_id == provisional.id:
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
            # The provisional row keeps its number here, so an UNRESOLVED claim would still
            # find it - and resolve onto a line that has just been closed. Resolved claims
            # are left where they are: they are a pairing somebody already made, and the
            # line they name still exists.
            self._repoint_claims(order, doc_no, unresolved_only=True)

    #: The name this was written under. Public since Stage 1B, because the reconciliation
    #: service attempts the header link before mapping the lines; the old name stays so an
    #: existing caller (or a note pointing at it) still resolves.
    _reconcile_core_order = reconcile_core_order

    def _repoint_claims(
        self, order: ProjectSalesOrder, doc_no: str, *, unresolved_only: bool
    ) -> int:
        """Move this project's SO<->PO claims off the provisional number onto the real one.

        `order_link_claim` holds the numbers as TEXT precisely so a claim can outlive the
        absence of either document (`order_link_service`), which also means nothing in the
        database follows a renumber for us. A claim left on the old number resolves against
        a row that has been renamed away or closed, and the resolver reports it as still
        waiting for a sales order we are in fact holding.

        Only claims this feed wrote are touched. The source vocabulary is CHECK-constrained
        and a project's `provisional_ref` is a number only the Order Inquiry sheet emits, so
        anything else naming it is the same coincidence the caller refuses to act on.
        """
        if not order.provisional_ref:
            return 0

        query = self.db.query(OrderLinkClaim).filter(
            OrderLinkClaim.so_number == order.provisional_ref,
            OrderLinkClaim.source == CLAIM_SOURCE_ORDER_INQUIRY,
        )
        # `provisional_ref` is unique per COMPANY (uq_project_so_provisional_ref), not
        # globally, so two companies can legitimately hold claims on the same string. The
        # scope filter is SELECT-only and this is an UPDATE, so the company is stated here.
        if order.company_id is not None:
            query = query.filter(OrderLinkClaim.company_id == order.company_id)
        if unresolved_only:
            query = query.filter(OrderLinkClaim.so_line_id.is_(None))

        old_number = order.provisional_ref
        moved = query.update({"so_number": doc_no}, synchronize_session=False)
        # The statement above did not reach objects this Session already holds; see
        # `_expire_loaded`. Matched on the OLD number, which is still what a cached copy says.
        self._expire_loaded(OrderLinkClaim, "so_number", old_number)
        if moved:
            logger.info(
                "project SO %s: moved %s order-link claim(s) from %s to %s",
                order.id, moved, old_number, doc_no,
            )
        return moved

    def _expire_loaded(self, model, attribute: str, value) -> None:
        """Drop this Session's cached copy of the rows a bulk UPDATE just changed.

        `synchronize_session=False` is the right setting for those statements - the criteria
        are cheap in SQL and awkward in the ORM - but it leaves an object already loaded here
        reporting the value it held BEFORE the update, and the caller has no way to tell.
        Expiring only the matched rows makes the next attribute read re-fetch them.
        `expire_all()` would do it too, and would also throw away every other object loaded
        in this transaction, including the half-built ones the ingest is still writing.

        Matching reads the in-memory state directly rather than the attribute, so scanning
        the identity map never triggers a lazy refresh of its own.
        """
        wanted = str(value)
        for obj in list(self.db.identity_map.values()):
            if not isinstance(obj, model):
                continue
            state = sa_inspect(obj)
            if attribute in state.unloaded:
                continue  # already expired: the next read re-fetches it anyway
            if str(state.dict.get(attribute)) == wanted:
                self.db.expire(obj)

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
        # `synchronize_session=False`: a line object already loaded here still says `open`
        # until it is expired. See `_expire_loaded`.
        self._expire_loaded(SalesOrderLine, "sales_order_id", provisional.id)

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
