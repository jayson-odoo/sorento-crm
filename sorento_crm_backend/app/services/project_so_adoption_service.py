"""Start planning: adopting a core AutoCount sales order into a planning record.

Contract: `documentation/plans/scm/PLAN-fulfilment-planning-from-autocount-so.md` section
5.1, AC-FP07 to AC-FP12.

The dependency inverts here. Fulfilment planning used to need a Project SO somebody
authored and published; the subject of planning is now the CORE `public.sales_orders` row
that AutoCount already carries, and a Project SO authored here is an optional counterpart.
Adopting one writes a thin `projects.sales_orders` mirror - `status = 'adopted'`, `so_id`
set, `project_id` NULL - plus one mirror line per still-owed core line, each already
carrying its `core_sales_order_line_id`.

**The mirror holds no facts of its own.** Product, quantity, required date and the
fulfilment location are every one of them read off the core line at read time
(`ProjectSupplyService._facts_for`), so the mirror cannot disagree with the book about
anything that matters. It is an ADDRESSING SHIM: what it exists to carry is the pointer
that `projects.so_line_allocations`, `projects.order_inquiry_rows` and `scm.committed_v`
all reach the core line through. The copied columns below (`qty`, `delivery_date`,
`stock_location`, `description`) are display fallbacks for the authored screens that share
these tables, never the source planning reads.

**Adoption is not a decision, so it moves no demand** (AC-FP09). It writes no
`projects.order_inquiry_rows`, no allocation and no supply decision, and `scm.committed_v`
is byte-identical across it - the order is still counted by the sheet leg exactly as it was
a moment before. Only CS confirming the sheet moves it.

**It is idempotent** (AC-FP08), which is why Start planning takes no confirmation dialog:
it destroys nothing and it repeats safely. A double click, a retry or a second CS gets the
record that exists. The partial unique index `uq_projects_so_core_order` is the backstop
under that, not the error path (AC-FP10) - it is checked before the write, and a race that
loses gets a sentence naming the sales order rather than an IntegrityError 500.

**Authorisation with no project.** `assert_can_edit_project` cannot run against a record
with no project, so adoption is gated on the module permission alone
(`projects.projects.edit`, checked at the route). Recorded in plan section 2 as an accepted
narrowing rather than an oversight, and the project check is kept for records that DO have
a project.

Re-sync and Detach (plan 5.1) are the adoption path's other two verbs and land with the
sheet seam; `mirror_missing_lines` below is the additive half of re-sync that AC-FP12 pins
(a later core line takes the next `line_no` and moves nobody).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, UnitOfMeasure
from app.models.project_so import (
    SO_STATUS_ADOPTED,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.services.error_handler import AppException
from app.services.scm.demand import PROJECT_CLASS, is_undecided_demand

logger = logging.getLogger(__name__)

#: The header half of what the BOARD may plan, and since the 14 September 2026 ruling that
#: is two statuses rather than one. `is_undecided_demand()` is the line half and is imported
#: rather than restated, so adoption and the board cannot disagree about which lines exist to
#: be planned - a Completed order whose stock shipped with nothing behind it could not be
#: adopted at all, so CS had no record to confirm the order-back against.
#:
#: `cancelled` is deliberately absent. A closed book is one that shipped; a cancelled one says
#: the demand went away, and there is nothing to put back for it.
_PLANNABLE_STATUSES = ("open", "closed")

#: Sorts an undated line last without ever comparing `None` to a date.
_EARLIEST = date.min


class ProjectSOAdoptionService:
    """Adopt one core sales order, and keep its mirror addressing the right core lines."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ adopt

    def adopt(
        self, sales_order_id: str, actor_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Journey step 2, and the whole of it: one decision, one record.

        Answers with the record's id, the human key, the review state the sheet will open
        on, and whether it already existed. Flushes but does not commit: the route owns the
        transaction, exactly as every other write here does.
        """
        core = self._core_order_or_404(sales_order_id)

        existing = (
            self.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.so_id == core.id)
            .first()
        )
        if existing is not None:
            # Attempt 6 (13 Sep 2026): an AutoCount re-ingest can close the lines this
            # record already mirrored and insert new open ones nobody has mirrored yet -
            # SO419851's own shape. The FE's own retry path for "already adopted" is to
            # POST adopt again and expect it to be caught up, so this branch re-mirrors
            # before answering rather than returning the record exactly as it stood the
            # day it was first adopted.
            self.mirror_missing_lines(existing)
            self.db.flush()
            return self._result(existing, core, already_adopted=True)

        self._assert_plannable(core)
        order = self._insert_record(core)
        self._mirror(order, core, self._open_core_lines(str(core.id)), start_at=1)
        self.db.flush()
        logger.info(
            "Adopted core sales order %s as planning record %s", core.so_number, order.id
        )
        return self._result(order, core, already_adopted=False)

    def adopt_for_migration(
        self,
        sales_order_id: str,
        actor_user_id: Optional[str] = None,
        core_line_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """`adopt`'s sibling, for the order inquiry sheet's migration
        (`PLAN-scm-oi-sheet-migration.md` section 2, AC-S1-7 / AC-S1-26).

        Same record and the same `_mirror`, with two differences, both because HISTORY is
        what this reads (the owner, 13 Sep 2026: "those historical sales orders won't have
        outstanding already ... but we still need to migrate those in"):

        * the only refusal kept is the project-class one. A closed order, and an order with
          nothing outstanding, are the ORDINARY case here rather than a reason to stop;
        * a closed line is mirrored when the caller NAMES it, because the sheet addresses
          the line it names and a line with no mirror has nothing to address.

        `core_line_ids` is what the upload matched. A FRESH record mirrors the still-owed
        lines exactly as `adopt` would, plus those named lines; a record the BOARD already
        owns gains only the named lines it does not carry yet, and nothing else (review
        finding 4, 14 Sep: `_authored_line_totals` sums mirror `qty` with no status filter,
        so a mirror line nobody asked for moves that record's reconciliation figures). Left
        as `None` the caller names nothing in particular and every line is mirrored, which
        is what a direct call with no upload behind it means.

        `adopt` and `mirror_missing_lines` are deliberately untouched, so the board's own
        Start planning gate still refuses exactly what it refused before.
        """
        core = self._core_order_or_404(sales_order_id)
        self._assert_project_class(core)
        named = self._named_core_lines(str(core.id), core_line_ids)

        existing = (
            self.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.so_id == core.id)
            .first()
        )
        if existing is not None:
            self._mirror_missing(existing, core, named)
            self.db.flush()
            return self._result(existing, core, already_adopted=True)

        order = self._insert_record(core)
        self._mirror(
            order, core, self._owed_and_named(str(core.id), named), start_at=1
        )
        self.db.flush()
        logger.info(
            "Adopted core sales order %s for migration as planning record %s",
            core.so_number, order.id,
        )
        return self._result(order, core, already_adopted=False)

    def mirror_missing_lines(self, order: ProjectSalesOrder) -> List[ProjectSalesOrderLine]:
        """Mirror the still-owed core lines this record does not carry yet (AC-FP12).

        Additive and stable: an existing mirror line keeps its `line_no` whatever the new
        line's required date is, and the new one takes `max + 1`. Renumbering would move a
        line under a person who has already read it, and the line number is what every
        refusal names.
        """
        if not order.so_id:
            return []
        held = {
            str(line.core_sales_order_line_id)
            for line in self._mirror_lines(str(order.id))
            if line.core_sales_order_line_id
        }
        missing = [
            line
            for line in self._open_core_lines(str(order.so_id))
            if str(line.id) not in held
        ]
        if not missing:
            return []
        core = self.db.query(SalesOrder).filter(SalesOrder.id == order.so_id).first()
        return self._mirror(order, core, missing, start_at=self._next_line_no(str(order.id)))

    def _mirror_missing(
        self,
        order: ProjectSalesOrder,
        core: Optional[SalesOrder],
        core_lines: Sequence[SalesOrderLine],
    ) -> List[ProjectSalesOrderLine]:
        """Mirror whichever of `core_lines` this record does not carry yet.

        The additive half `mirror_missing_lines` applies to the still-owed lines, taken out
        so the migration can hand it a different line set (every line, not only the owed
        ones) without changing what the board's own re-sync means.
        """
        held = {
            str(line.core_sales_order_line_id)
            for line in self._mirror_lines(str(order.id))
            if line.core_sales_order_line_id
        }
        missing = [line for line in core_lines if str(line.id) not in held]
        if not missing:
            return []
        return self._mirror(order, core, missing, start_at=self._next_line_no(str(order.id)))

    # ----------------------------------------------------------------- pieces

    def _core_order_or_404(self, sales_order_id: str) -> SalesOrder:
        """The core order, inside this company's scope (AC-FP11).

        Out of scope answers 404 AS IF THE ROW DID NOT EXIST, and the message carries no
        id: a 403 naming a sales order tells the caller that a sales order they may not
        read exists, which is the thing company scoping is for.
        """
        try:
            uuid.UUID(str(sales_order_id))
        except (ValueError, AttributeError, TypeError):
            raise AppException(404, "Sales order not found.", code="sales_order_not_found")
        core = (
            self.db.query(SalesOrder).filter(SalesOrder.id == str(sales_order_id)).first()
        )
        if core is None:
            raise AppException(404, "Sales order not found.", code="sales_order_not_found")
        return core

    def _assert_plannable(self, core: SalesOrder) -> None:
        """What is not planning work, said in the words CS would use.

        Each refusal names the sales order, never its id, and says which fact about it is
        the problem - a bare "cannot adopt" sends somebody to ask.
        """
        self._assert_project_class(core)
        if core.status not in _PLANNABLE_STATUSES:
            raise AppException(
                409,
                f"Sales order {core.so_number} is not open, so there is nothing to plan.",
                code="sales_order_not_open",
            )
        if not self._open_core_lines(str(core.id)):
            raise AppException(
                409,
                f"Every line of sales order {core.so_number} is cancelled or marked no "
                "purchase needed, so there is nothing to plan.",
                code="sales_order_nothing_outstanding",
            )

    def _assert_project_class(self, core: SalesOrder) -> None:
        """The one refusal BOTH entry points keep: this is not planning work at all.

        One spelling, because the migration path keeps only this check and a second copy of
        the sentence would let the two drift.
        """
        if core.demand_class != PROJECT_CLASS:
            raise AppException(
                409,
                f"Sales order {core.so_number} is not project demand, so it is not planned "
                "here.",
                code="sales_order_not_project_class",
            )

    def _insert_record(self, core: SalesOrder) -> ProjectSalesOrder:
        """The one row adoption writes.

        `provisional_ref` and `autocount_doc_no` are both the core sales-order number: for
        an order that came out of the book, the AutoCount document number IS that number,
        and `provisional_ref` is `NOT NULL UNIQUE(company, ref)` and read as the display key
        in a dozen places, so filling it is smaller than making it nullable.

        Wrapped in a savepoint so the unique-index refusal can be turned into a sentence
        without poisoning the caller's transaction - the route still rolls back, but the
        message it sends is this one and not `IntegrityError`.
        """
        order = ProjectSalesOrder(
            id=str(uuid.uuid4()),
            project_id=None,
            so_id=str(core.id),
            provisional_ref=core.so_number,
            autocount_doc_no=core.so_number,
            status=SO_STATUS_ADOPTED,
        )
        if core.company_id is not None:
            order.company_id = core.company_id
        savepoint = self.db.begin_nested()
        try:
            self.db.add(order)
            self.db.flush()
            savepoint.commit()
        except IntegrityError as exc:
            savepoint.rollback()
            raise self._collision(core, exc) from exc
        return order

    def _collision(self, core: SalesOrder, exc: IntegrityError) -> AppException:
        """Name the record that got there first, by its reference and never by its id."""
        detail = str(getattr(exc, "orig", exc))
        if "uq_project_so_provisional_ref" in detail:
            return AppException(
                409,
                f"A sales order in this company already uses the reference "
                f"{core.so_number}.",
                code="planning_record_reference_taken",
            )
        holder = (
            self.db.query(ProjectSalesOrder.provisional_ref)
            .filter(ProjectSalesOrder.so_id == core.id)
            .first()
        )
        where = holder[0] if holder and holder[0] else "another planning record"
        return AppException(
            409,
            f"Sales order {core.so_number} is already being planned as {where}. Open that "
            "one instead.",
            code="sales_order_already_adopted",
        )

    def _mirror(
        self,
        order: ProjectSalesOrder,
        core: Optional[SalesOrder],
        core_lines: Sequence[SalesOrderLine],
        *,
        start_at: int,
    ) -> List[ProjectSalesOrderLine]:
        """One mirror line per core line, in a deterministic order.

        Sorted by required date (undated last), then item code, then the core line id, so
        two adoptions of the same order produce the same line numbers and a refusal naming
        "line 3" means the same line to everybody.
        """
        products = self._products([line.product_id for line in core_lines])
        codes = {key: value[0] for key, value in products.items()}
        locations = self._warehouse_codes([line.warehouse_id for line in core_lines])

        ordered = sorted(
            core_lines,
            key=lambda line: (
                line.required_date is None,
                line.required_date or _EARLIEST,
                codes.get(str(line.product_id or ""), ""),
                str(line.id),
            ),
        )
        written: List[ProjectSalesOrderLine] = []
        for offset, line in enumerate(ordered):
            _code, name, uom = products.get(str(line.product_id or ""), (None, None, None))
            qty = Decimal(str(line.qty_ordered or 0))
            unit_price = Decimal(str(line.unit_price or 0))
            row = ProjectSalesOrderLine(
                id=str(uuid.uuid4()),
                project_sales_order_id=order.id,
                core_sales_order_line_id=str(line.id),
                line_no=start_at + offset,
                product_id=line.product_id,
                description=name,
                qty=qty,
                uom=uom,
                unit_price=unit_price,
                amount=(qty * unit_price).quantize(Decimal("0.01")),
                delivery_date=line.required_date,
                stock_location=locations.get(str(line.warehouse_id or "")),
            )
            if order.company_id is not None:
                row.company_id = order.company_id
            elif core is not None and core.company_id is not None:
                row.company_id = core.company_id
            self.db.add(row)
            written.append(row)
        self.db.flush()
        return written

    # ---------------------------------------------------------------- lookups

    def _open_core_lines(self, sales_order_id: str) -> List[SalesOrderLine]:
        """The lines the BOARD will walk, by `is_undecided_demand()` verbatim.

        Imported, never restated, and it is the BOARD's predicate rather than the netting
        one since the 14 September 2026 ruling: the mirror is how a confirmation names a
        line, so a line the board shows and the mirror omits cannot be confirmed at all.
        A delivered line nobody sourced is exactly that line.

        `covered` and `cancelled` lines are still left out, for the same reason the board
        leaves them out - somebody already ruled on them - and because a mirror line no
        screen accounts for moves the record's reconciliation figures
        (`_authored_line_totals` sums mirror `qty` with no status filter).
        """
        return (
            self.db.query(SalesOrderLine)
            .filter(
                SalesOrderLine.sales_order_id == str(sales_order_id),
                is_undecided_demand(),
            )
            .all()
        )

    def _named_core_lines(
        self, sales_order_id: str, core_line_ids: Optional[Sequence[str]]
    ) -> List[SalesOrderLine]:
        """The lines the caller named, whatever their status, scoped to THIS order.

        Scoped rather than fetched by id alone: a caller that named a line of another sales
        order would otherwise mirror it here, and the mirror is what every reader reaches
        the core line through.

        `None` means the caller named nothing in particular, and then every line is the
        answer - the shape a direct call with no upload behind it has.
        """
        query = self.db.query(SalesOrderLine).filter(
            SalesOrderLine.sales_order_id == str(sales_order_id)
        )
        if core_line_ids is None:
            return query.all()
        wanted = [str(value) for value in core_line_ids if value]
        if not wanted:
            return []
        return query.filter(SalesOrderLine.id.in_(wanted)).all()

    def _owed_and_named(
        self, sales_order_id: str, named: Sequence[SalesOrderLine]
    ) -> List[SalesOrderLine]:
        """The still-owed lines `adopt` would mirror, plus the ones this upload named.

        A record this upload CREATES is nobody else's, so it carries what the board would
        have adopted anyway - or the next person to open it finds a planning record missing
        the work that is still owed - plus the history the sheet addresses.
        """
        held = {str(line.id): line for line in self._open_core_lines(sales_order_id)}
        for line in named:
            held.setdefault(str(line.id), line)
        return list(held.values())

    def _mirror_lines(self, order_id: str) -> List[ProjectSalesOrderLine]:
        return (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == str(order_id))
            .order_by(ProjectSalesOrderLine.line_no.asc())
            .all()
        )

    def _next_line_no(self, order_id: str) -> int:
        lines = self._mirror_lines(order_id)
        return max((line.line_no or 0) for line in lines) + 1 if lines else 1

    def _products(self, product_ids) -> Dict[str, tuple]:
        wanted = {str(value) for value in product_ids if value}
        if not wanted:
            return {}
        rows = (
            self.db.query(
                Product.id, Product.product_code, Product.product_name, UnitOfMeasure.uom_code
            )
            .outerjoin(UnitOfMeasure, UnitOfMeasure.id == Product.base_uom_id)
            .filter(Product.id.in_(list(wanted)))
            .all()
        )
        return {str(row[0]): (row[1], row[2], row[3]) for row in rows}

    def _warehouse_codes(self, warehouse_ids) -> Dict[str, str]:
        wanted = {str(value) for value in warehouse_ids if value}
        if not wanted:
            return {}
        return {
            str(row[0]): row[1]
            for row in self.db.query(Warehouse.id, Warehouse.warehouse_code)
            .filter(Warehouse.id.in_(list(wanted)))
            .all()
        }

    def _result(
        self, order: ProjectSalesOrder, core: SalesOrder, *, already_adopted: bool
    ) -> Dict[str, Any]:
        from app.services.project_so_reconciliation_service import (
            ProjectSOReconciliationService,
        )

        return {
            "project_sales_order_id": str(order.id),
            "so_number": core.so_number,
            # Derived through the ONE owner of the review state, so the answer this
            # endpoint gives and the pill the worklist draws can never disagree.
            "review_state": ProjectSOReconciliationService(self.db)
            .evaluate(order)
            .get("review_state"),
            "already_adopted": already_adopted,
        }
