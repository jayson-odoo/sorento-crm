"""Mapping a published Project SO onto the AutoCount sales order it became (Stage 1B).

Contract: `documentation/plans/scm/STAGE1B-scm-front-planning-reconciliation.md` sections 2
to 4, `PLAN-scm-front-planning.md` sections 3.1 and 4, UAC AC-A01 to AC-A04.

The header half already exists: `ProjectSOIngestService.reconcile_core_order` adopts the
AutoCount number and points `projects.sales_orders.so_id` at the core row. This file adds
the LINE half - which core `sales_order_lines` row each Project line became - and the one
whole-SO review state that follows from it.

## The mapping rule, and why it is two passes

Candidates are the core lines of `so_id` that are not closed. A Project line whose existing
`core_sales_order_line_id` still names one of them KEEPS it: reconciliation runs again every
time somebody presses Re-run, and a mapping that reshuffles itself under a person who has
already read it is worse than one that occasionally reports an exception.

The rest are matched inside each `product_id` group, in the same two passes
`app/services/scm/outstanding_diff.py` uses to identify a line across weekly uploads:

1. **exact required-date match**, and ONLY when exactly one Project line and one core line
   share that date. Two of either is a genuine "which of these is which", so both sides are
   reported ambiguous and NOTHING is written - a guess here links a customer's quantity to
   the wrong delivery date.
2. **whatever is left pairs in date order**, both sides sorted by date and zipped. That is
   the rule a person can check by eye: "you had lines due 1 Jul and 3 Aug, the document has
   15 Jul and 3 Aug, so the 1 Jul line moved."

Leftover Project lines are `missing`, leftover core lines are `surplus` (the document has a
line this sales order does not, which is answered in AutoCount Differences).

## What this file must never do (AC-A04)

Reconciling writes core-line links and nothing else. It creates no purchase requirement, no
order inquiry row, and never calls `derive_for_sales_order`: purchasing demand is created
inside the atomic SO confirmation in Stage 1C, from the confirmed Buy residual alone.

## No UUID in a message

Every exception names a Project line number and an item code, or an item code alone for a
surplus core line, and the `message` carries the REASON only - the screen prints the subject
itself ("Line 2, SRT501-CP"), so a message repeating it renders the same fact twice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.project_so import (
    SO_STATUS_AMENDED,
    SO_STATUS_PUBLISHED,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.projects import Project, ProjectParty, ProjectPurchaseOrder

# Per-line outcomes (slice note section 2). `linked` is the only one that writes.
LINK_LINKED = "linked"
LINK_MISSING = "missing"
LINK_AMBIGUOUS = "ambiguous"

# Header outcomes.
HEADER_NO_DOCUMENT = "no_document"
HEADER_NO_CORE_SO = "no_core_so"
HEADER_LINKED = "linked"

# Exception kinds. `surplus` is the only one with no Project line behind it.
KIND_HEADER = "header"
KIND_MISSING = "missing"
KIND_AMBIGUOUS = "ambiguous"
KIND_SURPLUS = "surplus"

# The whole SO's one pre-confirmation state (AC-A03). Stage 1C adds `confirmed` on top of
# these; no line ever carries a state of its own.
REVIEW_AWAITING = "awaiting_reconciliation"
REVIEW_NEEDS_CS = "needs_cs_review"

#: A core line in this state is not a candidate, and a link naming one is stale. Same word
#: `project_so_ingest_service` retires a superseded row with.
CORE_LINE_CLOSED = "closed"

#: The statuses the worklist covers: a draft has not left the building yet, so there is no
#: AutoCount document for it to disagree with.
LIVE_SO_STATUSES = (SO_STATUS_PUBLISHED, SO_STATUS_AMENDED)

_SURPLUS_MESSAGE = (
    "On the AutoCount document and not on this sales order. Answer it in AutoCount "
    "Differences."
)


def _date_phrase(value: Optional[date]) -> str:
    return f"on {value.strftime('%d %b %Y')}" if value else "with no required date"


def _project_sort_key(line: ProjectSalesOrderLine) -> tuple:
    """Date order, then line number. `None` dates sort last without comparing None."""
    return (
        line.delivery_date is None,
        line.delivery_date or date.min,
        line.line_no or 0,
        str(line.id),
    )


def _core_sort_key(line: SalesOrderLine) -> tuple:
    return (
        line.required_date is None,
        line.required_date or date.min,
        str(line.id),
    )


@dataclass
class _LineOutcome:
    """One Project line's verdict, and the link `reconcile` would write for it."""

    line: ProjectSalesOrderLine
    link: str
    core_line_id: Optional[str]
    candidate_count: int
    reason: str
    #: The product code, resolved once for the whole page. Carried here because every
    #: exception names its line by number AND item code, never by an id.
    item_code: Optional[str] = None


@dataclass
class _OrderOutcome:
    """Everything derived for one Project SO, before display fields are added.

    `review_states_for` reads this directly; `evaluate` and `reconcile` add the header
    strip (project, customer, PO) around it.
    """

    order: ProjectSalesOrder
    header_outcome: str
    header_reason: str
    core_so_number: Optional[str]
    lines: List[_LineOutcome] = field(default_factory=list)
    surplus: List[Tuple[Optional[str], str]] = field(default_factory=list)

    @property
    def lines_total(self) -> int:
        return len(self.lines)

    @property
    def lines_linked(self) -> int:
        return sum(1 for row in self.lines if row.link == LINK_LINKED)

    @property
    def review_state(self) -> str:
        """AC-A02/AC-A03: entered only when the header AND every line map cleanly."""
        if not self.order.so_id:
            return REVIEW_AWAITING
        if self.lines_total == 0 or self.lines_linked != self.lines_total:
            return REVIEW_AWAITING
        if self.surplus:
            return REVIEW_AWAITING
        return REVIEW_NEEDS_CS

    @property
    def exceptions(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if self.header_outcome != HEADER_LINKED:
            rows.append(
                {
                    "line_no": None,
                    "item_code": None,
                    "kind": KIND_HEADER,
                    "message": self._header_next_step(),
                }
            )
        for row in self.lines:
            if row.link == LINK_LINKED:
                continue
            rows.append(
                {
                    "line_no": row.line.line_no,
                    "item_code": row.item_code,
                    "kind": KIND_MISSING if row.link == LINK_MISSING else KIND_AMBIGUOUS,
                    "message": row.reason,
                }
            )
        for _core_id, item_code in self.surplus:
            rows.append(
                {
                    "line_no": None,
                    "item_code": item_code or None,
                    "kind": KIND_SURPLUS,
                    "message": _SURPLUS_MESSAGE,
                }
            )
        return rows

    def _header_next_step(self) -> str:
        """The reason, plus where the person goes to answer it. Never an id."""
        if self.header_outcome == HEADER_NO_DOCUMENT:
            return f"{self.header_reason} Upload it on the AutoCount screen for this order."
        return (
            f"{self.header_reason} Re-run this once the weekly outstanding sales order "
            "book carries it."
        )


class ProjectSOReconciliationService:
    """Reads the mapping (`evaluate`), writes it (`reconcile`), summarises it in bulk."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ reads

    def evaluate(self, order: ProjectSalesOrder) -> Dict[str, Any]:
        """What the mapping makes of this order right now. Writes nothing."""
        outcome = self._outcomes_for([order])[str(order.id)]
        return self._summary(outcome, reconciled_at=None)

    def review_states_for(self, order_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """The list row's three numbers, for a whole page of orders at once.

        The same pairing the sheet shows, so a row and the sheet it opens can never
        disagree - and batched, so a 50-row page is a handful of queries rather than 50
        evaluations.
        """
        ids = [str(order_id) for order_id in order_ids if order_id]
        if not ids:
            return {}
        orders = (
            self.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id.in_(ids))
            .all()
        )
        outcomes = self._outcomes_for(orders)
        return {
            order_id: {
                "review_state": outcome.review_state,
                "lines_total": outcome.lines_total,
                "lines_linked": outcome.lines_linked,
                "exception_count": len(outcome.exceptions),
            }
            for order_id, outcome in outcomes.items()
        }

    # ----------------------------------------------------------------- writes

    def reconcile(self, order: ProjectSalesOrder) -> Dict[str, Any]:
        """Link what can be proven, clear what went stale, and say what is left.

        Idempotent: a second run keeps the links the first one wrote (they are candidates
        again, and an existing link is kept before anything is re-matched) and answers with
        the same summary.

        The header link is attempted first when the document number is known but nothing
        has carried it yet - the outstanding SO book may have created the row since the
        upload, and asking CS to re-upload the same document to pick it up would be a step
        the system can take itself.
        """
        if order.so_id is None and order.autocount_doc_no:
            # Imported here rather than at module scope: the ingest service calls back into
            # this one at the end of an upload, and a top-level import both ways is a cycle.
            from app.services.project_so_ingest_service import ProjectSOIngestService

            ProjectSOIngestService(self.db).reconcile_core_order(
                order, str(order.autocount_doc_no)
            )
            self.db.flush()

        outcome = self._outcomes_for([order])[str(order.id)]
        self._persist(outcome)
        return self._summary(outcome, reconciled_at=datetime.utcnow())

    def _persist(self, outcome: _OrderOutcome) -> None:
        """Clear first, then link.

        Two flushes on purpose: `uq_projects_so_line_core_line` is a unique index, so two
        lines swapping core lines inside one flush would collide on the statement that
        writes the first of them.
        """
        cleared = False
        for row in outcome.lines:
            current = (
                str(row.line.core_sales_order_line_id)
                if row.line.core_sales_order_line_id
                else None
            )
            if current is not None and current != row.core_line_id:
                row.line.core_sales_order_line_id = None
                cleared = True
        if cleared:
            self.db.flush()

        for row in outcome.lines:
            if row.core_line_id and not row.line.core_sales_order_line_id:
                row.line.core_sales_order_line_id = row.core_line_id
        self.db.flush()

    # ---------------------------------------------------------------- the map

    def _outcomes_for(
        self, orders: Sequence[ProjectSalesOrder]
    ) -> Dict[str, _OrderOutcome]:
        """Every order's verdict, in a fixed number of queries whatever the page size."""
        orders = [order for order in orders if order is not None]
        if not orders:
            return {}

        order_ids = [str(order.id) for order in orders]
        so_ids = [str(order.so_id) for order in orders if order.so_id]

        project_lines: Dict[str, List[ProjectSalesOrderLine]] = {
            order_id: [] for order_id in order_ids
        }
        for line in (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id.in_(order_ids))
            .order_by(ProjectSalesOrderLine.line_no.asc())
            .all()
        ):
            project_lines.setdefault(str(line.project_sales_order_id), []).append(line)

        core_lines: Dict[str, List[SalesOrderLine]] = {so_id: [] for so_id in so_ids}
        if so_ids:
            for line in (
                self.db.query(SalesOrderLine)
                .filter(
                    SalesOrderLine.sales_order_id.in_(so_ids),
                    SalesOrderLine.line_status.is_distinct_from(CORE_LINE_CLOSED),
                )
                .all()
            ):
                core_lines.setdefault(str(line.sales_order_id), []).append(line)

        core_numbers = self._core_so_numbers(so_ids)
        stale = self._stale_link_targets(project_lines, core_lines, orders)
        codes = self._product_codes(
            [line.product_id for lines in project_lines.values() for line in lines]
            + [line.product_id for lines in core_lines.values() for line in lines]
        )

        return {
            str(order.id): self._outcome(
                order,
                project_lines.get(str(order.id), []),
                core_lines.get(str(order.so_id), []) if order.so_id else [],
                core_numbers=core_numbers,
                stale=stale,
                codes=codes,
            )
            for order in orders
        }

    def _outcome(
        self,
        order: ProjectSalesOrder,
        project_lines: Sequence[ProjectSalesOrderLine],
        core_lines: Sequence[SalesOrderLine],
        *,
        core_numbers: Dict[str, Optional[str]],
        stale: Dict[str, Optional[SalesOrderLine]],
        codes: Dict[str, str],
    ) -> _OrderOutcome:
        header_outcome, header_reason, core_so_number = self._header(order, core_numbers)
        assignments, ambiguity, leftover_core = _map_lines(project_lines, core_lines)

        candidates_by_product: Dict[str, int] = {}
        for line in core_lines:
            key = str(line.product_id or "")
            candidates_by_product[key] = candidates_by_product.get(key, 0) + 1

        rows: List[_LineOutcome] = []
        for line in project_lines:
            item_code = codes.get(str(line.product_id or "")) or None
            core_line = assignments.get(str(line.id))
            if core_line is not None:
                row = _LineOutcome(
                    line=line,
                    link=LINK_LINKED,
                    core_line_id=str(core_line[0].id),
                    candidate_count=1,
                    reason=core_line[1],
                    item_code=item_code,
                )
            elif str(line.id) in ambiguity:
                row = _LineOutcome(
                    line=line,
                    link=LINK_AMBIGUOUS,
                    core_line_id=None,
                    candidate_count=ambiguity[str(line.id)][0],
                    reason=ambiguity[str(line.id)][1],
                    item_code=item_code,
                )
            else:
                row = _LineOutcome(
                    line=line,
                    link=LINK_MISSING,
                    core_line_id=None,
                    candidate_count=0,
                    reason=self._missing_reason(
                        order,
                        line,
                        stale=stale,
                        product_candidates=candidates_by_product.get(
                            str(line.product_id or ""), 0
                        ),
                    ),
                    item_code=item_code,
                )
            rows.append(row)

        return _OrderOutcome(
            order=order,
            header_outcome=header_outcome,
            header_reason=header_reason,
            core_so_number=core_so_number,
            lines=rows,
            surplus=[
                (str(line.id), codes.get(str(line.product_id or ""), ""))
                for line in leftover_core
            ],
        )

    def _header(
        self, order: ProjectSalesOrder, core_numbers: Dict[str, Optional[str]]
    ) -> Tuple[str, str, Optional[str]]:
        """`linked` is decided by `so_id`, not by the document number.

        The slice note lists `no_document` first, but an order that HAS a core sales order
        is linked whatever its document number says: the review state turns on `so_id`, so
        a header reading "nothing uploaded yet" beside a Needs CS review pill would be the
        screen contradicting itself.
        """
        if order.so_id:
            number = core_numbers.get(str(order.so_id))
            if number:
                return HEADER_LINKED, f"Linked to sales order {number}.", number
            return (
                HEADER_LINKED,
                "Linked to the core sales order for this document.",
                None,
            )
        if not order.autocount_doc_no:
            return (
                HEADER_NO_DOCUMENT,
                "No AutoCount document has been uploaded for this sales order yet.",
                None,
            )
        return (
            HEADER_NO_CORE_SO,
            "The outstanding sales order book has not carried document "
            f"{order.autocount_doc_no} yet.",
            None,
        )

    def _missing_reason(
        self,
        order: ProjectSalesOrder,
        line: ProjectSalesOrderLine,
        *,
        stale: Dict[str, Optional[SalesOrderLine]],
        product_candidates: int,
    ) -> str:
        if not order.so_id:
            return "There is no core sales order to map this line against."
        if line.core_sales_order_line_id:
            target = stale.get(str(line.core_sales_order_line_id))
            if target is None:
                return "Its previous core line no longer exists, so the link was cleared."
            if target.line_status == CORE_LINE_CLOSED:
                return "Its previous core line is now closed, so the link was cleared."
            return (
                "Its previous core line now belongs to another sales order, so the link "
                "was cleared."
            )
        if product_candidates == 0:
            return "The AutoCount document has no line for this item."
        return (
            "The AutoCount document has fewer lines for this item than this sales order "
            "does."
        )

    # ----------------------------------------------------------------- lookups

    def _core_so_numbers(self, so_ids: Sequence[str]) -> Dict[str, Optional[str]]:
        if not so_ids:
            return {}
        return {
            str(row[0]): row[1]
            for row in self.db.query(SalesOrder.id, SalesOrder.so_number)
            .filter(SalesOrder.id.in_(list(set(so_ids))))
            .all()
        }

    def _stale_link_targets(
        self,
        project_lines: Dict[str, List[ProjectSalesOrderLine]],
        core_lines: Dict[str, List[SalesOrderLine]],
        orders: Sequence[ProjectSalesOrder],
    ) -> Dict[str, Optional[SalesOrderLine]]:
        """The core lines a stale link still names, so the reason can say WHY it went.

        "Its previous core line is now closed" and "it moved to another sales order" are
        different problems answered in different places, and the difference is only
        knowable by reading the row the dead link points at.
        """
        candidate_ids = {
            str(line.id) for lines in core_lines.values() for line in lines
        }
        wanted = {
            str(line.core_sales_order_line_id)
            for order in orders
            for line in project_lines.get(str(order.id), [])
            if line.core_sales_order_line_id
            and str(line.core_sales_order_line_id) not in candidate_ids
        }
        if not wanted:
            return {}
        found = {
            str(row.id): row
            for row in self.db.query(SalesOrderLine)
            .filter(SalesOrderLine.id.in_(list(wanted)))
            .all()
        }
        return {link_id: found.get(link_id) for link_id in wanted}

    def _product_codes(self, product_ids: Iterable[Any]) -> Dict[str, str]:
        wanted = {str(product_id) for product_id in product_ids if product_id}
        if not wanted:
            return {}
        return {
            str(row[0]): row[1] or ""
            for row in self.db.query(Product.id, Product.product_code)
            .filter(Product.id.in_(list(wanted)))
            .all()
        }

    # ------------------------------------------------------------- the summary

    def _summary(
        self, outcome: _OrderOutcome, *, reconciled_at: Optional[datetime]
    ) -> Dict[str, Any]:
        order = outcome.order
        header = self._display_fields(order)
        return {
            "project_sales_order_id": order.id,
            "provisional_ref": order.provisional_ref,
            "autocount_doc_no": order.autocount_doc_no,
            "project_id": order.project_id,
            "project_code": header["project_code"],
            "project_name": header["project_name"],
            "customer_name": header["customer_name"],
            "po_number": header["po_number"],
            "area_group": order.area_group,
            "status": order.status,
            "review_state": outcome.review_state,
            "header": {
                "outcome": outcome.header_outcome,
                "core_so_number": outcome.core_so_number,
                "reason": outcome.header_reason,
            },
            "lines": [
                {
                    "id": row.line.id,
                    "line_no": row.line.line_no,
                    "product_code": row.item_code,
                    "description": row.line.description,
                    "qty": row.line.qty,
                    "uom": row.line.uom,
                    "delivery_date": row.line.delivery_date,
                    "stock_location": row.line.stock_location,
                    "link": row.link,
                    "candidate_count": row.candidate_count,
                    "reason": row.reason,
                }
                for row in outcome.lines
            ],
            "exceptions": outcome.exceptions,
            "lines_total": outcome.lines_total,
            "lines_linked": outcome.lines_linked,
            # Nothing stores the moment reconciliation last ran (this slice adds no column),
            # so a pure read states the absence rather than printing a date it does not
            # have. A run knows its own moment and says so.
            "reconciled_at": reconciled_at,
        }

    def _display_fields(self, order: ProjectSalesOrder) -> Dict[str, Optional[str]]:
        rows = self._header_rows([str(order.id)])
        return rows.get(
            str(order.id),
            {
                "project_code": None,
                "project_name": None,
                "customer_name": None,
                "po_number": None,
            },
        )

    def _header_rows(self, order_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """Project, customer and PO number for a whole page, in one joined query.

        The customer falls back to the issuing party's own name for the same reason the
        sales-order row does: a pre-order parked under another debtor still has a name a
        person recognises, and a blank column reads as missing data.
        """
        ids = [str(order_id) for order_id in order_ids if order_id]
        if not ids:
            return {}
        rows = (
            self.db.query(
                ProjectSalesOrder.id,
                Project.project_code,
                Project.title,
                ProjectPurchaseOrder.po_number,
                ProjectParty.name,
                Customer.customer_name,
            )
            .outerjoin(Project, Project.id == ProjectSalesOrder.project_id)
            .outerjoin(
                ProjectPurchaseOrder,
                ProjectPurchaseOrder.id == ProjectSalesOrder.purchase_order_id,
            )
            .outerjoin(
                ProjectParty, ProjectParty.id == ProjectPurchaseOrder.issuing_party_id
            )
            .outerjoin(Customer, Customer.id == ProjectParty.customer_id)
            .filter(ProjectSalesOrder.id.in_(ids))
            .all()
        )
        return {
            str(row[0]): {
                "project_code": row[1],
                "project_name": row[2],
                "po_number": row[3],
                "customer_name": row[5] or row[4],
            }
            for row in rows
        }

    # -------------------------------------------------------------- the worklist

    def list_fulfilment_planning(
        self,
        *,
        query: Optional[str] = None,
        review_state: Optional[str] = None,
        project_id: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """One row per published or amended Project SO, across projects (J03 step 1).

        The review state is derived rather than stored, so filtering on it means deriving
        it for every order the other filters leave. That is the honest cost of a state with
        no column: the alternative is a stored flag that silently disagrees with the
        mapping the sheet shows. The set is the published Project SOs of one company, and
        the derivation is a handful of queries whatever its size.
        """
        rows = (
            self.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.status.in_(LIVE_SO_STATUSES))
        )
        if project_id:
            rows = rows.filter(ProjectSalesOrder.project_id == project_id)
        if query:
            needle = f"%{query.strip()}%"
            rows = rows.filter(
                ProjectSalesOrder.provisional_ref.ilike(needle)
                | ProjectSalesOrder.autocount_doc_no.ilike(needle)
                | ProjectSalesOrder.area_group.ilike(needle)
            )
        orders = rows.order_by(ProjectSalesOrder.updated_at.desc()).all()

        outcomes = self._outcomes_for(orders)
        if review_state:
            orders = [
                order
                for order in orders
                if outcomes[str(order.id)].review_state == review_state
            ]

        total = len(orders)
        page = max(page, 1)
        window = orders[(page - 1) * limit : (page - 1) * limit + limit]
        headers = self._header_rows([str(order.id) for order in window])

        data = []
        for order in window:
            outcome = outcomes[str(order.id)]
            display = headers.get(str(order.id), {})
            data.append(
                {
                    "id": order.id,
                    "provisional_ref": order.provisional_ref,
                    "autocount_doc_no": order.autocount_doc_no,
                    "project_id": order.project_id,
                    "project_code": display.get("project_code"),
                    "project_name": display.get("project_name"),
                    "customer_name": display.get("customer_name"),
                    "po_number": display.get("po_number"),
                    "area_group": order.area_group,
                    "status": order.status,
                    "line_count": outcome.lines_total,
                    "lines_linked": outcome.lines_linked,
                    "exception_count": len(outcome.exceptions),
                    "review_state": outcome.review_state,
                    "updated_at": order.updated_at,
                }
            )
        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": not data,
        }


def _map_lines(
    project_lines: Sequence[ProjectSalesOrderLine],
    core_lines: Sequence[SalesOrderLine],
) -> Tuple[
    Dict[str, Tuple[SalesOrderLine, str]],
    Dict[str, Tuple[int, str]],
    List[SalesOrderLine],
]:
    """The whole mapping rule, as a pure function over two line lists.

    Returns the pairs (Project line id -> core line and the sentence that explains it),
    the ambiguous Project lines (id -> candidate count and its sentence), and the core
    lines nothing took. Pure so the same rule serves the sheet, the list row and the
    write, and so it can be reasoned about without a database.
    """
    candidates = {str(line.id): line for line in core_lines}
    assignments: Dict[str, Tuple[SalesOrderLine, str]] = {}
    ambiguity: Dict[str, Tuple[int, str]] = {}
    taken: set[str] = set()

    # Stability first: a link that still names a candidate is kept, and that core line is
    # out of the pool before anything is re-matched.
    for line in project_lines:
        existing = (
            str(line.core_sales_order_line_id) if line.core_sales_order_line_id else None
        )
        if existing and existing in candidates and existing not in taken:
            taken.add(existing)
            assignments[str(line.id)] = (
                candidates[existing],
                "Already linked to this line on the AutoCount document.",
            )

    remaining_project = [
        line for line in project_lines if str(line.id) not in assignments
    ]
    remaining_core = [line for line in core_lines if str(line.id) not in taken]

    by_product_project: Dict[str, List[ProjectSalesOrderLine]] = {}
    for line in remaining_project:
        by_product_project.setdefault(str(line.product_id or ""), []).append(line)
    by_product_core: Dict[str, List[SalesOrderLine]] = {}
    for line in remaining_core:
        by_product_core.setdefault(str(line.product_id or ""), []).append(line)

    leftover_core: List[SalesOrderLine] = []

    for product_key in sorted(set(by_product_project) | set(by_product_core)):
        ours = sorted(by_product_project.get(product_key, []), key=_project_sort_key)
        theirs = sorted(by_product_core.get(product_key, []), key=_core_sort_key)

        # Keyed ``Any`` rather than ``Optional[date]``: a model attribute reads as
        # ``Column[date]`` to the type checker on this codebase's SQLAlchemy version.
        theirs_by_date: Dict[Any, List[SalesOrderLine]] = {}
        for line in theirs:
            theirs_by_date.setdefault(line.required_date, []).append(line)
        ours_by_date: Dict[Any, List[ProjectSalesOrderLine]] = {}
        for line in ours:
            ours_by_date.setdefault(line.delivery_date, []).append(line)

        # --- pass 1: an exact date pairs, but only when it names ONE line on each side.
        spent: set[str] = set()
        still_ours: List[ProjectSalesOrderLine] = []
        for when, group in ours_by_date.items():
            their_group = theirs_by_date.get(when, [])
            if not their_group:
                still_ours.extend(group)
                continue
            if len(group) == 1 and len(their_group) == 1:
                assignments[str(group[0].id)] = (
                    their_group[0],
                    f"Matched on product and required date {when.strftime('%d %b %Y')}."
                    if when
                    else "Matched on product code; neither line carries a required date.",
                )
                spent.add(str(their_group[0].id))
                continue
            # Two of either side at one date: which is which is a question, not a guess.
            # Both sides drop out of pass 2 - the core lines are accounted for by the
            # ambiguity, so they are not surplus either.
            reason = (
                f"{len(their_group)} lines on the AutoCount document carry this item "
                f"{_date_phrase(when)}."
                if len(their_group) > 1
                else (
                    f"{len(group)} lines on this sales order carry this item "
                    f"{_date_phrase(when)}, so no single AutoCount line can be picked."
                )
            )
            for line in group:
                ambiguity[str(line.id)] = (len(their_group), reason)
            for line in their_group:
                spent.add(str(line.id))

        # --- pass 2: what is left pairs in date order, one to one.
        still_theirs = [line for line in theirs if str(line.id) not in spent]
        still_ours.sort(key=_project_sort_key)
        still_theirs.sort(key=_core_sort_key)
        for line, core_line in zip(still_ours, still_theirs):
            assignments[str(line.id)] = (
                core_line,
                "Matched in required-date order after the exact-date pass.",
            )
        leftover_core.extend(still_theirs[len(still_ours) :])

    return assignments, ambiguity, leftover_core
