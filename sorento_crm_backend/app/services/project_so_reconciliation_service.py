"""Mapping a published Project SO onto the AutoCount sales order it became (Stage 1B).

Contract: `documentation/plans/scm/STAGE1B-scm-front-planning-reconciliation.md` sections 2
to 4, `PLAN-scm-front-planning.md` sections 3.1 and 4, UAC AC-A01 to AC-A04.

The header half already exists: `ProjectSOIngestService.reconcile_core_order` adopts the
AutoCount number and points `projects.sales_orders.so_id` at the core row. This file adds
the LINE half - which core `sales_order_lines` row each Project line became - and the one
whole-SO review state that follows from it.

## The mapping rule, and why it is two passes

Candidates are the core lines of `so_id` that are not closed AND are not already held by
another Project SO's line. A Project line whose existing `core_sales_order_line_id` still
names one of them KEEPS it, on candidacy alone: reconciliation runs again every time somebody
presses Re-run, and a mapping that reshuffles itself under a person who has already read it is
worse than one that occasionally reports an exception.

The rest are matched inside each `product_id` group, in the same two passes
`app/services/scm/outstanding_diff.py` uses to identify a line across weekly uploads:

1. **exact required-date match**, and ONLY when exactly one Project line and one core line
   share that date. Two of either is a genuine "which of these is which", so both sides are
   reported ambiguous and NOTHING is written - a guess here links a customer's quantity to
   the wrong delivery date.
2. **whatever is left pairs in date order**, both sides sorted by date and zipped. That is
   the rule a person can check by eye: "you had lines due 1 Jul and 3 Aug, the document has
   15 Jul and 3 Aug, so the 1 Jul line moved."

Leftover Project lines are `missing`, or `duplicate` when the core line for that item is held
by another Project SO (two sales orders adopted the same AutoCount document, and one of them is
wrong - `uq_projects_so_line_core_line` allows exactly one holder, so reporting this is the
only alternative to dying on the index). Leftover core lines are `surplus` (the document has a
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
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.exc import IntegrityError
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
from app.services.error_handler import AppException

# Per-line outcomes (slice note section 2). `linked` is the only one that writes.
LINK_LINKED = "linked"
LINK_MISSING = "missing"
LINK_AMBIGUOUS = "ambiguous"
#: The core line this Project line would take is already held by ANOTHER Project SO.
#: A distinct outcome from `missing` because the answer is somewhere else entirely: one
#: of the two sales orders adopted the wrong AutoCount document.
LINK_DUPLICATE = "duplicate"

# Header outcomes.
HEADER_NO_DOCUMENT = "no_document"
HEADER_NO_CORE_SO = "no_core_so"
HEADER_LINKED = "linked"

# Exception kinds. `surplus` is the only one with no Project line behind it.
KIND_HEADER = "header"
KIND_MISSING = "missing"
KIND_AMBIGUOUS = "ambiguous"
KIND_DUPLICATE = "duplicate"
KIND_SURPLUS = "surplus"

#: A per-line outcome is its own exception kind; `linked` raises none.
_KIND_OF_LINK = {
    LINK_MISSING: KIND_MISSING,
    LINK_AMBIGUOUS: KIND_AMBIGUOUS,
    LINK_DUPLICATE: KIND_DUPLICATE,
}

# The whole SO's one state (AC-A03). No line ever carries a state of its own, and there is
# no fourth value: a superseded or challenged decision reads `needs_cs_review` again.
REVIEW_AWAITING = "awaiting_reconciliation"
REVIEW_NEEDS_CS = "needs_cs_review"
#: Stage 1C. The Stage 1B conditions hold AND an active supply decision exists.
REVIEW_CONFIRMED = "confirmed"

#: A core line in this state is not a candidate, and a link naming one is stale. Same word
#: `project_so_ingest_service` retires a superseded row with.
CORE_LINE_CLOSED = "closed"

#: The statuses the worklist covers: a draft has not left the building yet, so there is no
#: AutoCount document for it to disagree with.
LIVE_SO_STATUSES = (SO_STATUS_PUBLISHED, SO_STATUS_AMENDED)

#: Who holds a core line: the Project SO's id, its provisional reference, and the line
#: number on it. The reference and the line number are what an exception names.
_Claim = Tuple[str, Optional[str], Optional[int]]

_SURPLUS_MESSAGE = (
    "On the AutoCount document and not on this sales order. Answer it in AutoCount "
    "Differences."
)


def _duplicate_reason(other_ref: Optional[str], other_line_no: Optional[int]) -> str:
    """Name the sales order holding the core line, so CS knows where to look.

    A reference, never an id: the two orders are told apart on screen by their
    provisional reference, which is what the person reading this has in front of them.
    """
    where = other_ref or "another sales order"
    if other_line_no is None:
        return f"This core line is already linked to Project SO {where}."
    return f"This core line is already linked to Project SO {where}, line {other_line_no}."


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
    #: Whether an ACTIVE `projects.so_supply_decisions` row covers this order (Stage 1C).
    #: Read once per batch, so a page of fifty rows costs one more query, not fifty.
    has_active_decision: bool = False

    @property
    def lines_total(self) -> int:
        return len(self.lines)

    @property
    def lines_linked(self) -> int:
        return sum(1 for row in self.lines if row.link == LINK_LINKED)

    @property
    def review_state(self) -> Optional[str]:
        """AC-A02/AC-A03: entered only when the header AND every line map cleanly.

        None on an order that is not published or amended. A draft, a blocked order or
        one still being costed is reconciled against nothing - there is no AutoCount
        document for it to disagree with - so it carries NO state rather than an
        "awaiting reconciliation" it has not earned, and the screen renders no pill.

        `confirmed` sits on top of the same conditions rather than replacing them: an
        order whose mapping has since broken is back to awaiting reconciliation whatever
        its decision says, and a superseded or challenged decision is not an active one,
        so the order reads Needs CS review again (AC-C06).
        """
        if self.order.status not in LIVE_SO_STATUSES:
            return None
        if self.header_outcome != HEADER_LINKED:
            return REVIEW_AWAITING
        if self.lines_total == 0 or self.lines_linked != self.lines_total:
            return REVIEW_AWAITING
        if self.surplus:
            return REVIEW_AWAITING
        return REVIEW_CONFIRMED if self.has_active_decision else REVIEW_NEEDS_CS

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
                    "kind": _KIND_OF_LINK[row.link],
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
        if self.order.so_id:
            # The link exists and its row is simply out of this company's reach. There
            # is nothing to re-run, so the reason stands on its own.
            return self.header_reason
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
        return self._summary(outcome)

    def review_states_for(self, order_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """The list row's three numbers, for a whole page of orders at once.

        The same pairing the sheet shows, so a row and the sheet it opens can never
        disagree - and batched, so a 50-row page is a handful of queries rather than 50
        evaluations.
        """
        ids = [str(order_id) for order_id in order_ids if order_id]
        if not ids:
            return {}
        # Only a published or amended order has a state at all: a draft is reconciled
        # against nothing, so it carries no review state rather than an "awaiting
        # reconciliation" it has not earned (AC-A03). Absent from this map means absent
        # from the row.
        orders = (
            self.db.query(ProjectSalesOrder)
            .filter(
                ProjectSalesOrder.id.in_(ids),
                ProjectSalesOrder.status.in_(LIVE_SO_STATUSES),
            )
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

        An order that is not published or amended is READ and nothing else: it carries no
        review state (AC-A03), and linking its lines to a core sales order it has not been
        published against would be the system deciding something on its own.
        """
        if order.status not in LIVE_SO_STATUSES:
            return self.evaluate(order)
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
        return self._summary(outcome)

    def _persist(self, outcome: _OrderOutcome) -> None:
        """Clear first, then link.

        Two flushes on purpose: `uq_projects_so_line_core_line` is a unique index, so two
        lines swapping core lines inside one flush would collide on the statement that
        writes the first of them.

        A re-mapping is a material change (AC-C06): an active revision was decided against
        the links that stood then, so if any of them moves it is superseded and the whole
        SO goes back to Needs CS review. When the links stand but the facts behind them
        have drifted - a quantity or a required date on the core line - the revision is
        challenged instead, which says the same thing about the promise and keeps the
        evidence of what was promised.
        """
        relinked = [
            row
            for row in outcome.lines
            if (
                str(row.line.core_sales_order_line_id)
                if row.line.core_sales_order_line_id
                else None
            )
            != row.core_line_id
        ]
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
        try:
            self.db.flush()
        except IntegrityError as exc:
            # Belt and braces behind the `duplicate` outcome: a core line held by another
            # Project SO is kept out of the pool, so this can only fire on a race between
            # two reconciliations. Answered as a conflict naming the document, never an id.
            raise AppException(
                409,
                "Another sales order linked a line of AutoCount document "
                f"{outcome.order.autocount_doc_no or '(none)'} while this one was being "
                "reconciled. Re-run the reconciliation to see which line it took.",
            ) from exc

        from app.services.project_supply_service import ProjectSupplyService

        supply = ProjectSupplyService(self.db)
        if relinked:
            supply.supersede_for_material_change(
                outcome.order,
                "The AutoCount line mapping changed after this revision was confirmed.",
            )
        else:
            supply.challenge_if_drifted(
                outcome.order, lines=[row.line for row in outcome.lines]
            )

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
        claims = self._claims_by_other_orders(core_lines)
        stale = self._stale_link_targets(project_lines, core_lines, orders)
        codes = self._product_codes(
            [line.product_id for lines in project_lines.values() for line in lines]
            + [line.product_id for lines in core_lines.values() for line in lines]
        )
        decided = self._orders_with_an_active_decision(order_ids)

        outcomes = {
            str(order.id): self._outcome(
                order,
                project_lines.get(str(order.id), []),
                core_lines.get(str(order.so_id), []) if order.so_id else [],
                core_numbers=core_numbers,
                claims=claims,
                stale=stale,
                codes=codes,
            )
            for order in orders
        }
        for order_id, outcome in outcomes.items():
            outcome.has_active_decision = order_id in decided
        return outcomes

    def _orders_with_an_active_decision(self, order_ids: Sequence[str]) -> set:
        """Which of these orders CS has already confirmed (Stage 1C)."""
        from app.models.project_so import DECISION_ACTIVE, SOSupplyDecision

        if not order_ids:
            return set()
        return {
            str(row[0])
            for row in self.db.query(SOSupplyDecision.project_sales_order_id)
            .filter(
                SOSupplyDecision.project_sales_order_id.in_(list(order_ids)),
                SOSupplyDecision.state == DECISION_ACTIVE,
            )
            .all()
        }

    def _outcome(
        self,
        order: ProjectSalesOrder,
        project_lines: Sequence[ProjectSalesOrderLine],
        core_lines: Sequence[SalesOrderLine],
        *,
        core_numbers: Dict[str, Optional[str]],
        claims: Dict[str, _Claim],
        stale: Dict[str, Optional[SalesOrderLine]],
        codes: Dict[str, str],
    ) -> _OrderOutcome:
        header_outcome, header_reason, core_so_number = self._header(order, core_numbers)

        # A core line another Project SO already holds is not ours to take: the unique
        # index would refuse the write, and reporting it as `missing` would send CS
        # looking for a line that is sitting on the next sales order along. Out of the
        # pool, and named by the order holding it below.
        available: List[SalesOrderLine] = []
        # One claimed core line answers for one unmatched Project line, in required-date
        # order, so two unmatched lines against one taken core line report one duplicate
        # and one genuinely missing.
        duplicates_by_product: Dict[str, List[_Claim]] = {}
        for line in sorted(core_lines, key=_core_sort_key):
            claim = claims.get(str(line.id))
            if claim and claim[0] != str(order.id):
                duplicates_by_product.setdefault(
                    str(line.product_id or ""), []
                ).append(claim)
            else:
                available.append(line)

        assignments, ambiguity, leftover_core = _map_lines(project_lines, available)

        candidates_by_product: Dict[str, int] = {}
        for line in available:
            key = str(line.product_id or "")
            candidates_by_product[key] = candidates_by_product.get(key, 0) + 1
        # How many lines WE carry for the item, which is what makes "the document has
        # fewer lines for this item" a statement that can be checked rather than a guess.
        lines_by_product: Dict[str, int] = {}
        for line in project_lines:
            key = str(line.product_id or "")
            lines_by_product[key] = lines_by_product.get(key, 0) + 1

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
                product_key = str(line.product_id or "")
                # A line that HELD a core line has its own answer, and it is a truer one
                # than the duplicate fallback: "your core line is now closed" sends CS to
                # the document, while "line 3 of another sales order holds it" would send
                # them to a sales order that never touched this line. So the stale reason
                # is read FIRST, and the duplicate is only for a line that held nothing.
                stale_reason = self._stale_reason(order, line, stale)
                if stale_reason is None and duplicates_by_product.get(product_key):
                    _holder, other_ref, other_line_no = duplicates_by_product[
                        product_key
                    ].pop(0)
                    row = _LineOutcome(
                        line=line,
                        link=LINK_DUPLICATE,
                        core_line_id=None,
                        # Nothing it may take, which is the whole point of the outcome.
                        candidate_count=0,
                        reason=_duplicate_reason(other_ref, other_line_no),
                        item_code=item_code,
                    )
                else:
                    row = _LineOutcome(
                        line=line,
                        link=LINK_MISSING,
                        core_line_id=None,
                        candidate_count=0,
                        reason=stale_reason
                        or self._missing_reason(
                            order,
                            product_candidates=candidates_by_product.get(product_key, 0),
                            product_lines=lines_by_product.get(product_key, 0),
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
            if str(order.so_id) not in core_numbers:
                # The link exists, but the row it names cannot be read under this
                # company's scope. Claiming `linked` to a sales order we cannot even
                # name would be the screen asserting something it has not seen.
                return (
                    HEADER_NO_CORE_SO,
                    "The linked core sales order is not visible to this company.",
                    None,
                )
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

    def _stale_reason(
        self,
        order: ProjectSalesOrder,
        line: ProjectSalesOrderLine,
        stale: Dict[str, Optional[SalesOrderLine]],
    ) -> Optional[str]:
        """What became of the core line this Project line used to hold, if it held one.

        Stated as the core line's CURRENT state, never as something this call did: the
        read path (`evaluate`) writes nothing, so "the link was cleared" would be a
        sentence about an action the reader has not asked for yet.
        """
        if not order.so_id or not line.core_sales_order_line_id:
            return None
        key = str(line.core_sales_order_line_id)
        if key not in stale:
            # Still a candidate of this order, so the link is not stale at all.
            return None
        target = stale[key]
        if target is None:
            return "Its previous core line no longer exists."
        if target.line_status == CORE_LINE_CLOSED:
            return "Its previous core line is now closed."
        return "Its previous core line now belongs to another sales order."

    def _missing_reason(
        self,
        order: ProjectSalesOrder,
        *,
        product_candidates: int,
        product_lines: int,
    ) -> str:
        """Why nothing on the document could be this line, in a checkable sentence.

        The counts are the whole point. Saying the document carries FEWER lines for the
        item is something CS will go and count, so it is said only when it is true; when
        the document carries as many as we do and they were spoken for by an ambiguity
        elsewhere on the order, that is what the sentence says instead.
        """
        if not order.so_id:
            return "There is no core sales order to map this line against."
        if product_candidates == 0:
            return "The AutoCount document has no line for this item."
        if product_candidates < product_lines:
            return (
                "The AutoCount document has fewer lines for this item than this sales "
                "order does."
            )
        return (
            "Every AutoCount line for this item is already accounted for by another line "
            "on this sales order."
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

    def _claims_by_other_orders(
        self, core_lines: Dict[str, List[SalesOrderLine]]
    ) -> Dict[str, _Claim]:
        """Which Project SO already holds each candidate core line, if any.

        `uq_projects_so_line_core_line` allows exactly one holder, so this is a lookup
        rather than a list. Read for EVERY order in the batch at once and filtered per
        order afterwards: two Project SOs that adopted the same document can both be on
        the page, and each has to see the other's claim.
        """
        wanted = {str(line.id) for lines in core_lines.values() for line in lines}
        if not wanted:
            return {}
        rows = (
            self.db.query(
                ProjectSalesOrderLine.core_sales_order_line_id,
                ProjectSalesOrderLine.project_sales_order_id,
                ProjectSalesOrderLine.line_no,
                ProjectSalesOrder.provisional_ref,
            )
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == ProjectSalesOrderLine.project_sales_order_id,
            )
            .filter(ProjectSalesOrderLine.core_sales_order_line_id.in_(list(wanted)))
            .all()
        )
        return {str(row[0]): (str(row[1]), row[3], row[2]) for row in rows}

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
        # Candidacy is per ORDER, not per batch: another order's core line is not this
        # order's candidate, so a batch-wide set would silently declare a genuinely stale
        # link healthy whenever the two orders happen to land on the same page.
        wanted: set[str] = set()
        for order in orders:
            candidate_ids = {
                str(candidate.id)
                for candidate in core_lines.get(str(order.so_id), [])
            }
            for line in project_lines.get(str(order.id), []):
                link_id = (
                    str(line.core_sales_order_line_id)
                    if line.core_sales_order_line_id
                    else None
                )
                if link_id and link_id not in candidate_ids:
                    wanted.add(link_id)
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

    def _summary(self, outcome: _OrderOutcome) -> Dict[str, Any]:
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

        The review state is derived rather than stored, so FILTERING on it means deriving
        it for every order the other filters leave, then paging what is left: a total that
        counted unfiltered rows would be a lie, and there is no column to put in a WHERE.
        That is the honest cost of a state with no column, and it is paid only when the
        filter is actually used.

        Without that filter the database can do the paging, so it does: the ORM query is
        ordered and windowed first and only the page is derived, which keeps a worklist of
        a thousand published sales orders to one page's worth of mapping. `id` breaks a
        tie on `updated_at`, or two orders saved in the same moment could land on both
        pages, or on neither.
        """
        rows = (
            self.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.status.in_(LIVE_SO_STATUSES))
        )
        if project_id:
            rows = rows.filter(ProjectSalesOrder.project_id == project_id)
        needle = (query or "").strip()
        if needle:
            # Everything the row PRINTS is searchable, through the same outer joins
            # `_header_rows` reads those columns with: the screen offers "sales order,
            # project or customer", and a search that quietly covered only the sales
            # order would answer "no results" for a project code sitting in the list.
            like = f"%{needle}%"
            rows = (
                rows.outerjoin(Project, Project.id == ProjectSalesOrder.project_id)
                .outerjoin(
                    ProjectPurchaseOrder,
                    ProjectPurchaseOrder.id == ProjectSalesOrder.purchase_order_id,
                )
                .outerjoin(
                    ProjectParty,
                    ProjectParty.id == ProjectPurchaseOrder.issuing_party_id,
                )
                .outerjoin(Customer, Customer.id == ProjectParty.customer_id)
                .filter(
                    ProjectSalesOrder.provisional_ref.ilike(like)
                    | ProjectSalesOrder.autocount_doc_no.ilike(like)
                    | ProjectSalesOrder.area_group.ilike(like)
                    | Project.project_code.ilike(like)
                    | Project.title.ilike(like)
                    | Customer.customer_name.ilike(like)
                    # The party's own name is the customer column's fallback, so it has
                    # to be searchable or a row would not answer to the name it shows.
                    | ProjectParty.name.ilike(like)
                )
            )
        rows = rows.order_by(
            ProjectSalesOrder.updated_at.desc(), ProjectSalesOrder.id.desc()
        )

        page = max(page, 1)
        offset = (page - 1) * limit
        if review_state:
            orders = rows.all()
            outcomes = self._outcomes_for(orders)
            orders = [
                order
                for order in orders
                if outcomes[str(order.id)].review_state == review_state
            ]
            total = len(orders)
            window = orders[offset : offset + limit]
        else:
            total = rows.count()
            window = rows.offset(offset).limit(limit).all()
            outcomes = self._outcomes_for(window)

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
            # The whole result set, not this page: page 3 of 2 pages is empty of rows
            # without the worklist being empty, and the siblings all read it this way.
            "empty": total == 0,
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
