"""Order inquiry derivation, the SCM handoff and the Excel (P10, AC-I1 to AC-I7).

The netting and the verb rule are the pure engine next door
(``project_order_inquiry_engine.py``). This file is everything around them: where the
covering pools come from, where the stock location comes from, how the rows are written
once and only once, how purchasing is handed them, and how they leave the system as the
spreadsheet the client already reads.

Five things worth knowing before changing anything here.

**The standard demand row is the confirmed Buy residual, and only that**
(`PLAN-scm-front-planning.md` section 4). `refresh_for_decision` is its ONLY writer and it
runs inside the atomic CS confirmation. Publish writes no inquiry and reconciliation writes
none (AC-D01), because a published order may be covered entirely by Reserve, Borrow or
timely SPO cover and ordering all of it would buy it twice. The netting engine below still
serves AMENDMENTS, whose exception verbs are a different thing from new demand.

**The inquiry is never a second source of demand** (AC-I6). Committed quantity lives on
`sales_order_lines` and the SCM reorder engine reads that, exactly as it does today.
These rows say what to DO about that quantity. The only thing they are read back for is
the coverage LEDGER below, which is a record of what a pool has already been promised
to, not a record of what anybody has ordered.

**The covering pool is consumed across publishes, not just within one.** Publishing a
second sales order against a project whose pre-order is already spoken for must not net
against the same 5,950 twice, so the pool is reduced by every row that already claims
it. ``covered_by`` is the key for that: the engine writes a stable label, not free text.
It stays NULL on a confirmed-Buy row: nothing covers it, because CS already removed the
covered part of the line.

**The stock location is never invented** (AC-H5). It is the warehouse on a CONFIRMED
allocation from slice P9. No confirmation yet means the column is empty, and the screen
and the spreadsheet both say so rather than defaulting to the master location.

**Purchasing is handed a task, not an email** (AC-I4). It is a `project_tasks` row on
the delivery phase, linked to the inquiry, plus an in-app notification. The rows stay in
`project_order_inquiry_rows` and the task points at them, so marking one actioned
updates the one record rather than a copy pasted into a description.
"""
from __future__ import annotations

import io
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import (
    InboundShipment,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product
from app.models.project_so import (
    AMENDMENT_PUBLISHED,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ADVANCE,
    IV_ALREADY_INBOUND,
    IV_BORROW_SHORTFALL,
    IV_CANCEL_BALANCE,
    IV_CHANGE_SO,
    IV_DELAY,
    IV_ORDER,
    IV_PRE_ORDERED,
    IV_RESERVE_AND_ORDER,
    SO_STATUS_AMENDED,
    SO_STATUS_PUBLISHED,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOAmendment,
    SOLineAllocation,
    next_inquiry_no as _next_inquiry_no,
)
from app.models.projects import (
    TASK_LINK_ORDER_INQUIRY,
    TASK_PHASE_DELIVERY,
    Project,
    ProjectParty,
    ProjectPurchaseOrder,
    ProjectTask,
)
from app.services.error_handler import AppException
from app.services.scm import order_link_service, priority
from app.services.project_order_inquiry_engine import (
    CHANGE_DATE_EARLIER,
    CHANGE_DATE_LATER,
    CHANGE_QTY_DECREASE,
    CHANGE_QTY_INCREASE,
    CHANGE_REPOINT,
    POOL_INBOUND_SPO,
    POOL_PRE_ORDER,
    CoveringPool,
    DemandRow,
    net_demand,
)

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")

#: The states pre-seeded at zero on the header strip. `placed` (section G) is
#: deliberately NOT one of them - `summary()` adds it to the dict dynamically the moment a
#: placed row actually exists, so a project with none yet keeps reporting the exact four
#: keys this screen has always reported.
INQUIRY_STATES = (INQUIRY_RAISED, INQUIRY_ACTIONED, INQUIRY_CANCELLED)

# The verbs whose rows claim part of a covering pool, and so have to be counted before
# the next publish nets against the same pool again.
_COVERING_VERBS = (IV_PRE_ORDERED, IV_ALREADY_INBOUND)

# Section G: only a row that still costs money and is still undecided can be tagged onto
# an outstanding PO. `RESERVE_AND_ORDER` is buying work exactly like `ORDER` (BUYING_VERBS
# on the frontend groups them the same way); the rest are either informational or already
# closed off.
_PLACEABLE_VERBS = (IV_ORDER, IV_RESERVE_AND_ORDER)

# How the client spells each verb in the order inquiry they send today. `ALREADY_INBOUND`
# is deliberately absent: their file writes the SPO reference itself in that column
# (`202511-S0022`), which is the thing purchasing looks up.
REMARK_SPELLING = {
    IV_ORDER: "ORDER",
    IV_RESERVE_AND_ORDER: "RESERVE & ORDER",
    IV_ADVANCE: "ADVANCE",
    IV_DELAY: "DELAY",
    IV_CHANGE_SO: "CHANGE SO NO",
    IV_CANCEL_BALANCE: "CANCEL BALANCE",
    IV_PRE_ORDERED: "PRE-ORDERED, DO NOT ORDER",
    IV_ALREADY_INBOUND: "ALREADY INBOUND",
    # Not a spelling of theirs: this row is new to them, and it says what it is.
    IV_BORROW_SHORTFALL: "BORROW SHORTFALL",
}

# The headings on `(04).03.2026 MARYAM TUJU RESIDENCE.xlsx`, committed to the golden set
# as `e2e/fixtures/project-cs/expected-order-inquiry-2026-03-04.xlsx`. Read off the file
# rather than retyped: this is the spreadsheet purchasing already works from, and a
# renamed column is a column their own filters stop finding.
EXPORT_TITLE = "ORDER INQUIRY"
EXPORT_SHEET = "NEW"
EXPORT_HEADINGS = (
    "SO DATE",
    "S/O NO",
    "ITEM CODE",
    "QTY",
    "DELIVERY DATE",
    "PROJECT/CUSTOMER",
    "STOCK LOCATION",
    "REMARK",
)

# How an amendment's own verb reads as a change to this line. The delta service spells
# its verbs the way the client writes them; the inquiry stores the AC-I2 constants.
_DELTA_VERB_CHANGE = {
    "DELAY": CHANGE_DATE_LATER,
    "ADVANCE": CHANGE_DATE_EARLIER,
    "CANCEL BALANCE": CHANGE_QTY_DECREASE,
    "CHANGE SO NO": CHANGE_REPOINT,
    "ORDER": CHANGE_QTY_INCREASE,
    "RESERVE & ORDER": CHANGE_QTY_INCREASE,
}


def next_inquiry_no(db: Session, company_id: str) -> str:
    """`OI-000001` for this company, from the ONE minting function (`app.models.project_so`).

    Re-exported here rather than reimplemented: the `before_insert` stamp on the model
    already guarantees every inquiry gets a number, and a second series generator in this
    file would be a second answer to the same question the day the two drifted.

    Deliberately NOT routed through `NumberingService` the way `PSO-000001` optionally is:
    nothing seeds a rule for this document type, so that branch would be a configuration
    surface with no configuration behind it. If a client ever wants to word their own
    inquiry numbers, that is the moment to add it.
    """
    return _next_inquiry_no(db, company_id)


def _dec(value: Any, default: Decimal = _ZERO) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 - a malformed stored number is data, not a crash
        return default


def _qty_str(value: Decimal) -> str:
    """`600`, not `600.0000`. ``normalize()`` alone turns 100 into `1E+2`."""
    return format(_dec(value).normalize(), "f")


def project_customer_label(
    customer_name: Optional[str],
    project_title: Optional[str],
    is_pre_order: Optional[bool] = False,
) -> Optional[str]:
    """`BUIMACO / TUJU RESIDENCE`, the way purchasing reads the column.

    The billed party first because that is who the document is against, then the project,
    then the parking note when the order is a pre-order rather than a real commercial
    commitment (D18).

    A module-level function rather than a method because TWO screens print this column -
    the per-project inquiry and purchasing's cross-project worklist - and two screens
    spelling the same customer differently is a support call. Each supplies the three
    facts its own query already has; the rule for turning them into words lives here.
    """
    parts = [part for part in (customer_name, project_title) if part]
    if is_pre_order:
        parts.append("PRE-ORDER")
    return " / ".join(parts) if parts else None


def _as_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class ProjectOrderInquiryService:
    """Derives, serves, exports and closes off what purchasing is told to do."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------- derivation

    def refresh_for_decision(
        self,
        order: ProjectSalesOrder,
        decision: Any,
        buy_lines: Sequence[Dict[str, Any]],
        *,
        actor_user_id: Optional[str] = None,
        borrow_shortfalls: Sequence[Dict[str, Any]] = (),
    ) -> Dict[str, Any]:
        """The Buy-only handoff, written INSIDE the atomic confirmation (PLAN section 4).

        The only creator of standard demand rows. Publish creates none and reconciliation
        creates none (AC-D01): a published-but-unconfirmed order may be covered entirely by
        Reserve, Borrow or timely SPO cover, and ordering all of it would buy it twice.

        What reaches purchasing is the confirmed Buy residual and nothing else - no netting
        pass, no coverage verbs, `covered_by` NULL. The evidence for why the rest of the
        line needs nothing bought belongs to the decision, not to a purchasing instruction.

        Three lifecycle rules, all of them AC-C07/AC-D05:

        * a still-unplaced row from a superseded revision is CANCELLED with the revision
          that replaced it named, never edited in place;
        * a row purchasing already actioned STAYS. Placed supply is in the ledger and this
          service does not get to rewrite history;
        * when the new need is lower than what was already placed, the difference becomes a
          `CANCEL_BALANCE` exception row stating both figures, so somebody answers it.

        Since partial confirmation (PLAN-fulfilment-planning-from-autocount-so.md 13.4) a
        revision covers the lines the planner chose. A line the previous revision covered
        and this confirmation did not name is CARRIED into the new revision by
        `ProjectSupplyService.confirm` and arrives here in `buy_lines` like any other, so
        its Buy stays on purchasing's list. `_retire_uncovered_rows` still cancels the
        still-raised rows of a line genuinely absent from the revision (one no longer on
        the order): that line is undecided again and its whole open quantity goes back to
        counting as demand, so a raised Buy row left behind would be the same requirement
        told to purchasing twice. Cancelled by the same rule and with the same words as
        any other superseded row - never deleted, because they are what purchasing was
        told.

        `borrow_shortfalls` is the fourth thing purchasing is handed, and the only one that
        is not about the borrowing line's own quantity: a borrow that pushed a DONOR
        location below zero availability opened a hole at THAT location, and it is raised
        there under its own verb (PLAN 13.11). A donor the borrow left covered raises
        nothing.

        `created` counts the rows this confirmation ADDED to purchasing's list. A carried
        line (`carried: True`) has its still-raised row moved under this revision - a
        cancel and a re-raise, so `confirmed_unplaced_buy_rows` keeps seeing it under the
        ACTIVE decision - but purchasing already had that row, so it is not counted.
        """
        inquiry = self._existing(order.id, None)
        if inquiry is None:
            inquiry = OrderInquiry(
                company_id=order.company_id,
                project_sales_order_id=order.id,
                amendment_id=None,
                state=INQUIRY_RAISED,
                raised_by=actor_user_id,
                # The number is stamped by the model's own `before_insert` (there is one
                # minting path, so no writer can forget). Numbered ONCE, on the header this
                # order keeps: a re-confirm reuses the same inquiry (`_existing` above), so
                # purchasing keeps quoting one number through every revision.
            )
            self.db.add(inquiry)
            self.db.flush()
        elif actor_user_id:
            # A reconfirm RE-STAMPS the header (PLAN section H, AC-H4). The inquiry is
            # deliberately reused so purchasing keeps quoting one number, which means
            # without this the screen would name whoever confirmed revision 1 forever,
            # long after somebody else decided what purchasing is actually holding. The
            # rows keep their own `actioned_by` - that is purchasing's answer, not CS's
            # instruction.
            inquiry.raised_by = actor_user_id
            inquiry.raised_at = datetime.utcnow()

        created = 0
        raised = 0
        exceptions: List[Dict[str, Any]] = []
        for entry in buy_lines:
            line = entry["line"]
            need = _dec(entry.get("buy_qty"))
            carried = bool(entry.get("carried"))
            # This sales order's OWN inquiry only. An amendment raises its exception verbs
            # under its own inquiry (`amendment_id`), and cancelling those here would
            # delete an instruction purchasing is still working from.
            rows = (
                self.db.query(OrderInquiryRow)
                .filter(
                    OrderInquiryRow.order_inquiry_id == inquiry.id,
                    OrderInquiryRow.so_line_id == line.id,
                    OrderInquiryRow.verb.in_((IV_ORDER, IV_CANCEL_BALANCE)),
                )
                .all()
            )
            # A still-raised CANCEL_BALANCE exception is superseded like a raised ORDER
            # row, or every reconfirm at the same lower need would stack another copy.
            # `placed` sums ORDER rows only: the exception row is a message, not supply.
            #
            # `INQUIRY_PLACED` counts here too, and it is not a cosmetic addition: the
            # live "Place on PO" path (section G) writes rows straight to `placed`, never
            # to `actioned` - `mark_rows` is the only writer of `actioned`, and nothing on
            # the real workflow calls it for an ORDER row anymore. A predicate that only
            # recognised `actioned` was blind to every placed row in the company (145
            # placed / 0 actioned, live, 20 Aug), so a qty-up reconfirm re-raised the FULL
            # new need on top of supply that was already there (SO349754 WESERP10B: placed
            # 5 untouched, a fresh 10 raised, 15 against a 10 line).
            placed = _ZERO
            for row in rows:
                if row.state == INQUIRY_RAISED:
                    row.state = INQUIRY_CANCELLED
                    row.note = f"Superseded by revision {decision.revision_no}"
                elif (
                    row.state in (INQUIRY_ACTIONED, INQUIRY_PLACED)
                    and row.verb == IV_ORDER
                    # A planning change already REDIRECTED this row to replenish the
                    # pool it drew on (`planning_change_service._apply_placed_redirect`,
                    # the captain's ruling 21 Aug 2026) - it is still real placed
                    # quantity, just not this line's anymore, so it must not net off
                    # this line's need a second time or the new Buy would be silently
                    # short.
                    and not row.redirected_to_pool
                ):
                    placed += _dec(row.qty)

            outstanding = need - placed
            if outstanding > _ZERO:
                self.db.add(
                    OrderInquiryRow(
                        company_id=order.company_id,
                        order_inquiry_id=inquiry.id,
                        so_line_id=line.id,
                        item_code=entry.get("item_code") or None,
                        qty=outstanding,
                        delivery_date=entry.get("required_date"),
                        stock_location=entry.get("stock_location"),
                        verb=IV_ORDER,
                        # No netting on this path, so nothing covers this row: the coverage
                        # decision was CS's and is recorded on the supply decision.
                        covered_by=None,
                        supply_decision_id=decision.id,
                        state=INQUIRY_RAISED,
                    )
                )
                raised += 1
                if not carried:
                    created += 1
            elif placed > need:
                message = (
                    f"Placed {_qty_str(placed)}, new need {_qty_str(need)}"
                )
                self.db.add(
                    OrderInquiryRow(
                        company_id=order.company_id,
                        order_inquiry_id=inquiry.id,
                        so_line_id=line.id,
                        item_code=entry.get("item_code") or None,
                        qty=placed - need,
                        delivery_date=entry.get("required_date"),
                        stock_location=entry.get("stock_location"),
                        verb=IV_CANCEL_BALANCE,
                        note=message,
                        supply_decision_id=decision.id,
                        state=INQUIRY_RAISED,
                    )
                )
                exceptions.append(
                    {
                        "line_no": entry.get("line_no"),
                        "item_code": entry.get("item_code"),
                        "message": message,
                    }
                )

        self._retire_uncovered_rows(inquiry, decision, buy_lines)
        shortfalls = self._raise_borrow_shortfalls(
            order, inquiry, decision, borrow_shortfalls
        )
        created += shortfalls
        raised += shortfalls
        self.db.flush()
        if raised and self.task_for(inquiry.id) is None:
            self._hand_to_purchasing(order, inquiry, raised)
        return {"inquiry": inquiry, "created": created, "exceptions": exceptions}

    def _raise_borrow_shortfalls(
        self,
        order: ProjectSalesOrder,
        inquiry: OrderInquiry,
        decision: Any,
        shortfalls: Sequence[Dict[str, Any]],
    ) -> int:
        """One row per donor location this confirmation left oversold (PLAN 13.11).

        Its own verb rather than `ORDER`, and that is not cosmetic: the quantity belongs to
        the DONOR's location while the row hangs off the borrowing line, so counted as
        `ORDER` it would reach `confirmed_unplaced_buy_rows` attributed to the borrowing
        line's warehouse and be cancelled by the Buy-residual rules on the next re-confirm.

        The lifecycle is the same as every other row here: a still-raised one from an
        earlier revision is CANCELLED and kept, never edited in place, and one purchasing
        has already actioned stays - AND is netted, exactly as an actioned ORDER row is
        netted off the line's next Buy. A hole of 10 that purchasing placed is not
        raised again by the next revision; a hole that has widened to 15 raises the 5
        still outstanding. Netted per (item, donor location), which is the pile the hole
        is in: a donor short of two products has two holes.

        **`placed` is a POOL, consumed once, not restated per entry** (B3). Two order-backs
        can share one (item, donor location) key - a group borrow at one location, and a
        location-pile shortfall at the same one - and the actioned quantity purchasing
        already placed there covers the FIRST entry that draws on it, then whatever is
        left over covers the next. Netting the whole `placed[key]` off every entry sharing
        the key (rather than decrementing it as each entry consumes it) under-raised every
        entry after the first by the SAME amount, as if purchasing had placed it twice.
        """
        rows = (
            self.db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.order_inquiry_id == inquiry.id,
                OrderInquiryRow.verb == IV_BORROW_SHORTFALL,
            )
            .all()
        )
        placed: Dict[Tuple[Optional[str], Optional[str]], Decimal] = {}
        for row in rows:
            if row.state == INQUIRY_RAISED:
                row.state = INQUIRY_CANCELLED
                row.note = f"Superseded by revision {decision.revision_no}"
            # Same widening as the ORDER-row netting above, for the same reason: `placed`
            # (section G) is a real, distinct state from `actioned` and a shortfall row
            # purchasing already dealt with must net off just as an actioned one does. A
            # borrow shortfall row is not one of `_PLACEABLE_VERBS` today, so this state
            # is not reachable through the current UI - kept in step with the vocabulary
            # rather than left to silently disagree with it.
            elif row.state in (INQUIRY_ACTIONED, INQUIRY_PLACED):
                key = (row.item_code or None, row.stock_location or None)
                placed[key] = placed.get(key, _ZERO) + _dec(row.qty)

        created = 0
        for entry in shortfalls:
            key = (entry.get("item_code") or None, entry.get("stock_location") or None)
            raw_qty = _dec(entry.get("qty"))
            already_placed = placed.get(key, _ZERO)
            netted = min(raw_qty, already_placed)
            if netted > _ZERO:
                placed[key] = already_placed - netted
            qty = raw_qty - netted
            if qty <= _ZERO:
                continue
            line = entry.get("line")
            self.db.add(
                OrderInquiryRow(
                    company_id=order.company_id,
                    order_inquiry_id=inquiry.id,
                    so_line_id=line.id if line is not None else None,
                    item_code=entry.get("item_code") or None,
                    qty=qty,
                    delivery_date=entry.get("required_date"),
                    #: The DONOR's location, which is where the hole is.
                    stock_location=entry.get("stock_location"),
                    verb=IV_BORROW_SHORTFALL,
                    note=entry.get("note"),
                    covered_by=None,
                    supply_decision_id=decision.id,
                    state=INQUIRY_RAISED,
                )
            )
            created += 1
        return created

    def _retire_uncovered_rows(
        self, inquiry: OrderInquiry, decision: Any, buy_lines: Sequence[Dict[str, Any]]
    ) -> None:
        """Cancel still-raised rows of an EARLIER revision on lines this one dropped.

        Scoped to rows that carry a `supply_decision_id` other than this decision's: a row
        with none belongs to the amendment path, which is a different instruction to
        purchasing and is not this method's to touch. An `actioned` row stays, exactly as
        it does on a covered line - placed supply is in the ledger.
        """
        covered = {str(entry["line"].id) for entry in buy_lines}
        stale = (
            self.db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.order_inquiry_id == inquiry.id,
                OrderInquiryRow.state == INQUIRY_RAISED,
                OrderInquiryRow.verb.in_((IV_ORDER, IV_CANCEL_BALANCE)),
                OrderInquiryRow.supply_decision_id.isnot(None),
                OrderInquiryRow.supply_decision_id != decision.id,
            )
            .all()
        )
        for row in stale:
            if str(row.so_line_id) in covered:
                continue
            row.state = INQUIRY_CANCELLED
            row.note = f"Superseded by revision {decision.revision_no}"

    def derive_for_amendment(
        self, amendment: SOAmendment, *, actor_user_id: Optional[str] = None
    ) -> OrderInquiry:
        """An amendment says what CHANGED, in the same verbs purchasing already reads.

        The delta is read AFTER it has been applied, so the line carries the new date and
        the new quantity. What the row adds is the previous value, which is the half of
        a DELAY that makes it actionable.
        """
        existing = self._existing(amendment.project_sales_order_id, amendment.id)
        if existing is not None:
            return existing

        order = self._order_or_404(amendment.project_sales_order_id)
        delta = amendment.delta_json or {}
        # Section 9.3: a declined row was never applied to the order, so it must not
        # become a purchasing instruction either. `row_decisions` defaults every row
        # absent from it to accepted, which is why an amendment nobody touched still
        # derives exactly as it always has.
        row_decisions = amendment.row_decisions or {}
        demand: List[DemandRow] = []
        for index, row in enumerate(delta.get("rows") or []):
            row_key = str(row.get("row_key") or index)
            if (row_decisions.get(row_key) or {}).get("decision") == "declined":
                continue
            change = _DELTA_VERB_CHANGE.get(str(row.get("verb") or ""))
            if change is None:
                continue
            line = self._line_or_none(row.get("so_line_id"))
            qty = _dec(row.get("qty"))
            if qty <= _ZERO:
                continue
            delivery_date = (
                _as_date(row.get("to_value"))
                if change in (CHANGE_DATE_LATER, CHANGE_DATE_EARLIER)
                else (line.delivery_date if line else None)
            )
            demand.append(
                DemandRow(
                    line_id=line.id if line else str(row.get("so_line_id") or ""),
                    product_id=str(row.get("product_id") or ""),
                    item_code=row.get("product_code")
                    or self._product_code(row.get("product_id")),
                    qty=qty,
                    delivery_date=delivery_date,
                    stock_location=self._stock_location(line.id) if line else None,
                    change=change,
                    note=self._change_note(change, row),
                )
            )
        return self._write(order, amendment, demand, actor_user_id=actor_user_id)

    def derive_for_book_change(
        self,
        order: ProjectSalesOrder,
        rows: Sequence[Dict[str, Any]],
        *,
        batch_id: str,
        actor_user_id: Optional[str] = None,
    ) -> Optional[OrderInquiry]:
        """A planning-change batch's accepted reactions, in purchasing's own verbs
        (`PLAN-so-book-diff-replanning.md` AC-R08).

        `rows` is one already-resolved demand row per accepted line: `{line_id, product_id,
        item_code, qty, delivery_date, stock_location, change, note}` - the caller
        (`planning_change_service.apply`) is the one that knows which reaction happened and
        what the previous value was, so this stays as thin a wrapper over `net_demand` as
        `derive_for_amendment` is.

        Written under its OWN `SOAmendment` row rather than the order's `amendment_id IS
        NULL` inquiry `refresh_for_decision` owns: the two are different instructions (a
        confirmed Buy residual vs a reaction to what changed) and the DB-level singleton on
        `amendment_id IS NULL` would otherwise collide with whatever `confirm()` just wrote
        earlier in the same apply. `from_version_kind='planning_change_batch'` names where
        this one came from; nothing reads that column back for routing, so it costs no
        contract anywhere else.
        """
        demand: List[DemandRow] = []
        verb_summary: Dict[str, int] = {}
        for row in rows:
            qty = _dec(row.get("qty"))
            if qty <= _ZERO:
                continue
            change = str(row.get("change") or "")
            demand.append(
                DemandRow(
                    line_id=str(row.get("line_id") or ""),
                    product_id=str(row.get("product_id") or ""),
                    item_code=row.get("item_code") or "",
                    qty=qty,
                    delivery_date=row.get("delivery_date"),
                    stock_location=row.get("stock_location"),
                    change=change,
                    note=row.get("note"),
                )
            )
            verb_summary[change] = verb_summary.get(change, 0) + 1
        if not demand:
            return None
        amendment = SOAmendment(
            company_id=order.company_id,
            project_sales_order_id=order.id,
            from_version_kind="planning_change_batch",
            from_version_id=batch_id,
            verb_summary=verb_summary,
            status=AMENDMENT_PUBLISHED,
            published_at=datetime.utcnow(),
        )
        self.db.add(amendment)
        self.db.flush()
        return self._write(order, amendment, demand, actor_user_id=actor_user_id)

    def _change_note(self, change: str, row: Dict[str, Any]) -> Optional[str]:
        """The half of the instruction the verb does not carry."""
        before = row.get("from_value")
        after = row.get("to_value")
        if change in (CHANGE_DATE_LATER, CHANGE_DATE_EARLIER):
            moved = _as_date(before)
            return f"Was {moved.isoformat()}" if moved else "No previous delivery date"
        if change == CHANGE_REPOINT:
            return f"Moved to {after}" if after else None
        if change in (CHANGE_QTY_DECREASE, CHANGE_QTY_INCREASE):
            if before is None or after is None:
                return None
            return f"Was {before}, now {after}"
        return None

    def _write(
        self,
        order: ProjectSalesOrder,
        amendment: Optional[SOAmendment],
        demand: Sequence[DemandRow],
        *,
        actor_user_id: Optional[str],
    ) -> OrderInquiry:
        plans = net_demand(demand, self._pools(order, demand))

        inquiry = OrderInquiry(
            company_id=order.company_id,
            project_sales_order_id=order.id,
            amendment_id=amendment.id if amendment else None,
            state=INQUIRY_RAISED,
            raised_by=actor_user_id,
            # An amendment raises its OWN inquiry, so the stamp gives it its own number: it
            # is a separate instruction to purchasing and gets referred to as one.
        )
        self.db.add(inquiry)
        self.db.flush()

        for plan in plans:
            self.db.add(
                OrderInquiryRow(
                    company_id=order.company_id,
                    order_inquiry_id=inquiry.id,
                    so_line_id=plan.line_id or None,
                    item_code=plan.item_code or None,
                    qty=plan.qty,
                    delivery_date=plan.delivery_date,
                    stock_location=plan.stock_location,
                    verb=plan.verb,
                    spo_ref=plan.spo_ref,
                    covered_by=plan.covered_by,
                    note=plan.note,
                    state=INQUIRY_RAISED,
                )
            )
        self.db.flush()
        self._hand_to_purchasing(order, inquiry, len(plans))
        return inquiry

    def _existing(self, pso_id: str, amendment_id: Optional[str]) -> Optional[OrderInquiry]:
        query = self.db.query(OrderInquiry).filter(
            OrderInquiry.project_sales_order_id == pso_id
        )
        query = (
            query.filter(OrderInquiry.amendment_id == amendment_id)
            if amendment_id
            else query.filter(OrderInquiry.amendment_id.is_(None))
        )
        return query.first()

    # ----------------------------------------------------------- covering pools

    def _pools(
        self, order: ProjectSalesOrder, demand: Sequence[DemandRow]
    ) -> List[CoveringPool]:
        """What already exists, or is on the water, for the products being asked for.

        Only the products in front of us, so a project with one product does not drag
        every open shipment in the company into the calculation.
        """
        product_ids = {row.product_id for row in demand if row.product_id}
        if not product_ids:
            return []
        pools = self._pre_order_pools(order, product_ids) + self._inbound_pools(product_ids)
        claimed = self._claimed(pools)
        out: List[CoveringPool] = []
        for pool in pools:
            balance = pool.qty - claimed.get((pool.label, pool.product_id), _ZERO)
            if balance > _ZERO:
                out.append(
                    CoveringPool(
                        kind=pool.kind,
                        reference=pool.reference,
                        product_id=pool.product_id,
                        qty=balance,
                        available_from=pool.available_from,
                    )
                )
        return out

    def _pre_order_pools(
        self, order: ProjectSalesOrder, product_ids: set
    ) -> List[CoveringPool]:
        """Published pre-order sales orders on the SAME PROJECT.

        The project is the anchor, not the customer (D18): a pre-order parked under
        another debtor still belongs to this project, so the join goes through
        `project_id` rather than through whoever the document is billed to. The order
        being published is excluded, or a pre-order would net against itself.
        """
        rows = (
            self.db.query(
                ProjectSalesOrder.provisional_ref,
                ProjectSalesOrder.autocount_doc_no,
                ProjectSalesOrderLine.product_id,
                func.sum(ProjectSalesOrderLine.qty),
            )
            .join(
                ProjectSalesOrderLine,
                ProjectSalesOrderLine.project_sales_order_id == ProjectSalesOrder.id,
            )
            .filter(
                ProjectSalesOrder.project_id == order.project_id,
                ProjectSalesOrder.id != order.id,
                ProjectSalesOrder.is_pre_order.is_(True),
                ProjectSalesOrder.status.in_([SO_STATUS_PUBLISHED, SO_STATUS_AMENDED]),
                ProjectSalesOrderLine.product_id.in_(list(product_ids)),
            )
            .group_by(
                ProjectSalesOrder.provisional_ref,
                ProjectSalesOrder.autocount_doc_no,
                ProjectSalesOrderLine.product_id,
            )
            .all()
        )
        return [
            CoveringPool(
                kind=POOL_PRE_ORDER,
                reference=doc_no or ref,
                product_id=str(product_id),
                qty=_dec(qty),
            )
            for ref, doc_no, product_id, qty in rows
            if _dec(qty) > _ZERO
        ]

    def _inbound_pools(self, product_ids: set) -> List[CoveringPool]:
        """SPO allocations on shipments that have not landed: stock already on the water."""
        rows = (
            self.db.query(
                SPOAllocation.spo_number,
                SPOAllocation.product_id,
                SPOAllocation.allocated_quantity,
                SPOAllocation.quantity_received,
                InboundShipment.estimated_arrival_date,
            )
            .join(InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id)
            .filter(
                SPOAllocation.product_id.in_(list(product_ids)),
                SPOAllocation.spo_number.isnot(None),
                InboundShipment.actual_arrival_date.is_(None),
                or_(
                    SPOAllocation.receipt_status.is_(None),
                    SPOAllocation.receipt_status != "received",
                ),
            )
            .all()
        )
        pools: List[CoveringPool] = []
        for spo_number, product_id, allocated, received, eta in rows:
            balance = _dec(allocated) - _dec(received)
            if balance <= _ZERO:
                continue
            pools.append(
                CoveringPool(
                    kind=POOL_INBOUND_SPO,
                    reference=str(spo_number),
                    product_id=str(product_id),
                    qty=balance,
                    available_from=eta,
                )
            )
        return pools

    def _claimed(self, pools: Sequence[CoveringPool]) -> Dict[Tuple[str, str], Decimal]:
        """What earlier inquiries already promised out of these same pools.

        Keyed on ``covered_by`` because the engine writes it as a stable label rather
        than as prose. A cancelled row releases its claim: purchasing said the
        instruction is dead, so the quantity behind it is available again.
        """
        labels = {pool.label for pool in pools}
        if not labels:
            return {}
        rows = (
            self.db.query(
                OrderInquiryRow.covered_by,
                OrderInquiryRow.so_line_id,
                OrderInquiryRow.qty,
            )
            .filter(
                OrderInquiryRow.covered_by.in_(list(labels)),
                OrderInquiryRow.verb.in_(list(_COVERING_VERBS)),
                OrderInquiryRow.state != INQUIRY_CANCELLED,
            )
            .all()
        )
        if not rows:
            return {}
        line_ids = [row[1] for row in rows if row[1]]
        products = dict(
            self.db.query(ProjectSalesOrderLine.id, ProjectSalesOrderLine.product_id)
            .filter(ProjectSalesOrderLine.id.in_(line_ids))
            .all()
        ) if line_ids else {}

        claimed: Dict[Tuple[str, str], Decimal] = {}
        for covered_by, line_id, qty in rows:
            product_id = products.get(line_id)
            if not product_id:
                continue
            key = (covered_by, str(product_id))
            claimed[key] = claimed.get(key, _ZERO) + _dec(qty)
        return claimed

    # ------------------------------------------------------------ stock location

    def _stock_location(self, so_line_id: str) -> Optional[str]:
        """The line's OWN fulfilment warehouse (AC-H5), or nothing at all.

        One row names one location: the amendment row is a Buy/schedule instruction the
        same way `refresh_for_decision`'s ORDER row is, and its destination is where the
        CORE reconciled line is fulfilled from, not a list of every reserve/borrow
        location a past confirmation drew on to cover it (those live on the confirmed
        decision's snapshots, not here). Joining several warehouses with `" / "` used to
        read as a real place purchasing could act on; it never was one - mirrors
        `ProjectSupplyService._restamp_stock_location`.

        Never a default the other way either: a line with no reconciled core line, or a
        core line with no warehouse set, leaves the column empty - nobody has said yet
        where this is coming from.
        """
        row = (
            self.db.query(Warehouse.warehouse_code)
            .join(SalesOrderLine, SalesOrderLine.warehouse_id == Warehouse.id)
            .join(
                ProjectSalesOrderLine,
                ProjectSalesOrderLine.core_sales_order_line_id == SalesOrderLine.id,
            )
            .filter(ProjectSalesOrderLine.id == so_line_id)
            .first()
        )
        return row[0] if row and row[0] else None

    # -------------------------------------------------------- the SCM handoff

    def _hand_to_purchasing(
        self, order: ProjectSalesOrder, inquiry: OrderInquiry, row_count: int
    ) -> None:
        """A task on the project's delivery phase, with the rows attached (AC-I4).

        Best-effort on purpose. The rows this task points at are already written when
        this runs, so a notification backend that is down must not turn that success
        into a 500 the retry cannot repair. The write sits in a SAVEPOINT because this
        now also runs INSIDE the atomic confirmation transaction: a swallowed DB error
        without one would leave that transaction aborted, and the caller's commit would
        then fail for an operation that had already succeeded (the post-commit
        side-effect lesson in CLAUDE.md, applied pre-commit).
        """
        try:
            with self.db.begin_nested():
                project = (
                    self.db.query(Project).filter(Project.id == order.project_id).first()
                )
                if project is None:
                    return
                reference = order.autocount_doc_no or order.provisional_ref
                to_buy = self._buying_count(inquiry.id)
                task = ProjectTask(
                    company_id=order.company_id,
                    project_id=project.id,
                    name=f"Order inquiry {reference}",
                    description=(
                        f"{row_count} instruction{'' if row_count == 1 else 's'} from "
                        f"{reference}, {to_buy} of which still need buying."
                    ),
                    task_phase=TASK_PHASE_DELIVERY,
                    category="Purchasing",
                    linked_entity_type=TASK_LINK_ORDER_INQUIRY,
                    linked_entity_id=inquiry.id,
                )
                self.db.add(task)
                self.db.flush()
                self._notify_purchasing(project, order, inquiry, row_count, to_buy)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "order inquiry %s raised, but the purchasing task was not created (%s)",
                inquiry.id,
                exc,
            )

    def _notify_purchasing(
        self,
        project: Project,
        order: ProjectSalesOrder,
        inquiry: OrderInquiry,
        row_count: int,
        to_buy: int,
    ) -> None:
        from app.services.notification_service import NotificationService

        reference = order.autocount_doc_no or order.provisional_ref
        service = NotificationService(self.db)
        for user_id in self._purchasing_user_ids():
            service.create_with_channel_preferences(
                user_id=str(user_id),
                type="project_order_inquiry_raised",
                title=f"Order inquiry {reference}",
                body=(
                    f"{project.title}: {row_count} instruction"
                    f"{'' if row_count == 1 else 's'}, {to_buy} still to buy."
                ),
                data={
                    "project_id": str(project.id),
                    "project_code": project.project_code,
                    "order_inquiry_id": str(inquiry.id),
                    "sales_order_ref": reference,
                    "row_count": row_count,
                    "to_buy": to_buy,
                },
                source_entity_type="order_inquiry",
                source_entity_id=str(inquiry.id),
                dedup_key=f"{inquiry.id}:order_inquiry_raised",
                event_type="project_order_inquiry_raised",
                send_in_app=True,
                # Deliberately not email. AC-I4 is that this stops being an email: the
                # task is the record, and a mailbox is the thing it replaces.
                send_email=False,
            )

    def _purchasing_user_ids(self) -> List[str]:
        """Everyone holding the `purchasing` role, which is what SCM is granted through."""
        from app.models.user import User, UserRole, UserRoleAssignment, UserStatus

        rows = (
            self.db.query(UserRoleAssignment.user_id)
            .join(UserRole, UserRole.id == UserRoleAssignment.role_id)
            .join(User, User.id == UserRoleAssignment.user_id)
            .filter(
                UserRole.slug == "purchasing",
                User.status == UserStatus.ACTIVE.value,
                User.is_trashed.is_(False),
            )
            .distinct()
            .all()
        )
        return [str(row[0]) for row in rows]

    def _buying_count(self, inquiry_id: str) -> int:
        return (
            self.db.query(func.count(OrderInquiryRow.id))
            .filter(
                OrderInquiryRow.order_inquiry_id == inquiry_id,
                # A borrow shortfall is buying work too: the donor is oversold and
                # somebody has to buy the hole (PLAN 13.11).
                OrderInquiryRow.verb.in_(
                    [IV_ORDER, IV_RESERVE_AND_ORDER, IV_BORROW_SHORTFALL]
                ),
            )
            .scalar()
            or 0
        )

    def task_for(self, inquiry_id: str) -> Optional[ProjectTask]:
        return (
            self.db.query(ProjectTask)
            .filter(
                ProjectTask.linked_entity_type == TASK_LINK_ORDER_INQUIRY,
                ProjectTask.linked_entity_id == inquiry_id,
            )
            .first()
        )

    # -------------------------------------------------------------- reading

    def list_rows(
        self,
        project_id: str,
        *,
        query: Optional[str] = None,
        verb: Optional[Sequence[str]] = None,
        state: Optional[Sequence[str]] = None,
        pso_id: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
        sort: str = "delivery_date",
        direction: str = "asc",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Every instruction raised on one project, newest inquiry first by default."""
        base = self._rows_query(project_id, query=query, verb=verb, state=state, pso_id=pso_id)
        total = base.with_entities(func.count(OrderInquiryRow.id)).scalar() or 0

        sortable = {
            "delivery_date": OrderInquiryRow.delivery_date,
            "item_code": OrderInquiryRow.item_code,
            "qty": OrderInquiryRow.qty,
            "verb": OrderInquiryRow.verb,
            "state": OrderInquiryRow.state,
            "created_at": OrderInquiryRow.created_at,
        }
        column = sortable.get(sort, OrderInquiryRow.delivery_date)
        ordering = column.desc() if str(direction).lower() == "desc" else column.asc()
        rows = (
            base.order_by(ordering, OrderInquiryRow.item_code.asc())
            .offset(max(page - 1, 0) * limit)
            .limit(limit)
            .all()
        )
        return self.serialize_rows(rows), int(total)

    def all_rows(
        self,
        project_id: str,
        *,
        query: Optional[str] = None,
        verb: Optional[Sequence[str]] = None,
        state: Optional[Sequence[str]] = None,
        pso_id: Optional[str] = None,
    ) -> List[OrderInquiryRow]:
        """The same set the list serves, unpaged, for the export."""
        return (
            self._rows_query(project_id, query=query, verb=verb, state=state, pso_id=pso_id)
            .order_by(OrderInquiryRow.created_at.asc(), OrderInquiryRow.item_code.asc())
            .all()
        )

    def _rows_query(
        self,
        project_id: str,
        *,
        query: Optional[str],
        verb: Optional[Sequence[str]],
        state: Optional[Sequence[str]],
        pso_id: Optional[str],
    ):
        base = (
            self.db.query(OrderInquiryRow)
            .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == OrderInquiry.project_sales_order_id,
            )
            .filter(ProjectSalesOrder.project_id == project_id)
        )
        if pso_id:
            base = base.filter(OrderInquiry.project_sales_order_id == pso_id)
        if query:
            like = f"%{query.strip()}%"
            base = base.filter(
                or_(
                    OrderInquiryRow.item_code.ilike(like),
                    OrderInquiryRow.spo_ref.ilike(like),
                    OrderInquiryRow.stock_location.ilike(like),
                    ProjectSalesOrder.autocount_doc_no.ilike(like),
                    ProjectSalesOrder.provisional_ref.ilike(like),
                )
            )
        if verb:
            base = base.filter(OrderInquiryRow.verb.in_(list(verb)))
        if state:
            base = base.filter(OrderInquiryRow.state.in_(list(state)))
        return base

    def summary(self, project_id: str) -> Dict[str, Any]:
        """How much of this project's inquiry is still open, for the screen's header."""
        rows = (
            self._rows_query(project_id, query=None, verb=None, state=None, pso_id=None)
            .with_entities(OrderInquiryRow.state, func.count(OrderInquiryRow.id))
            .group_by(OrderInquiryRow.state)
            .all()
        )
        counts = {state: 0 for state in INQUIRY_STATES}
        total = 0
        for state, count in rows:
            counts[state] = int(count)
            # Summed off the actual rows, not off the pre-seeded keys: a `placed` row
            # (section G) grows this dict dynamically rather than being one of the
            # states pre-seeded above, and a total that only added the three seeded
            # keys would silently drop it.
            total += int(count)
        counts["total"] = total
        return counts

    def serialize_rows(self, rows: Sequence[OrderInquiryRow]) -> List[Dict[str, Any]]:
        if not rows:
            return []
        context, names = self._context_for(rows)
        traces = self._decision_traces(rows)
        product_by_row = self._resolve_product_ids_bulk(rows)
        open_products = self.open_po_line_product_ids(set(product_by_row.values()))
        out: List[Dict[str, Any]] = []
        for row in rows:
            meta = context.get(row.order_inquiry_id, {})
            trace = traces.get(row.id, {})
            out.append(
                {
                    "id": row.id,
                    "order_inquiry_id": row.order_inquiry_id,
                    "so_line_id": row.so_line_id,
                    "sales_order_ref": meta.get("sales_order_ref"),
                    "project_sales_order_id": meta.get("project_sales_order_id"),
                    # AC-D06: the buyer traces a Buy back to the Project SO, the line
                    # number and the revision that decided it, in identifiers a person
                    # reads - never an id.
                    "project_so_ref": meta.get("project_so_ref"),
                    "line_no": trace.get("line_no"),
                    "decision_revision": trace.get("decision_revision"),
                    "so_date": meta.get("so_date"),
                    "project_customer": meta.get("project_customer"),
                    "is_amendment": meta.get("is_amendment", False),
                    "item_code": row.item_code,
                    "qty": _qty_str(_dec(row.qty)),
                    "delivery_date": row.delivery_date,
                    "stock_location": row.stock_location,
                    "verb": row.verb,
                    "remark": self._remark(row),
                    "spo_ref": row.spo_ref,
                    "po_ref": row.po_ref,
                    "po_line_id": row.po_line_id,
                    "has_open_po_line": product_by_row.get(row.id) in open_products,
                    "covered_by": row.covered_by,
                    "note": row.note,
                    "state": row.state,
                    "actioned_at": row.actioned_at,
                    "actioned_by_name": names.get(row.actioned_by),
                    "created_at": row.created_at,
                }
            )
        return out

    def _context_for(
        self, rows: Sequence[OrderInquiryRow]
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
        """One query per fact the rows need, rather than one per row."""
        inquiry_ids = {row.order_inquiry_id for row in rows}
        joined = (
            self.db.query(OrderInquiry, ProjectSalesOrder)
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == OrderInquiry.project_sales_order_id,
            )
            .filter(OrderInquiry.id.in_(list(inquiry_ids)))
            .all()
        )
        labels = self._project_customer_labels({so.id for _inq, so in joined})
        context: Dict[str, Dict[str, Any]] = {}
        for inquiry, order in joined:
            context[inquiry.id] = {
                "project_sales_order_id": order.id,
                "sales_order_ref": order.autocount_doc_no or order.provisional_ref,
                # The Project SO's OWN reference, beside the AutoCount number the
                # sales_order_ref prefers: they are two different documents and the buyer
                # tracing a Buy back to a project needs the one this system minted.
                "project_so_ref": order.provisional_ref,
                "so_date": (order.published_at or order.created_at),
                "project_customer": labels.get(order.id),
                "is_amendment": bool(inquiry.amendment_id),
            }

        from app.services.project_service import resolve_user_names

        names = resolve_user_names(
            self.db, [row.actioned_by for row in rows if row.actioned_by]
        )
        return context, names

    def _decision_traces(
        self, rows: Sequence[OrderInquiryRow]
    ) -> Dict[str, Dict[str, Any]]:
        """The line number and decision revision behind each row (AC-D06).

        Both are absent on an amendment exception row and on anything raised before
        Stage 1C, which is honest: those rows were not decided by a supply revision.
        """
        from app.models.project_so import SOSupplyDecision

        line_ids = {row.so_line_id for row in rows if row.so_line_id}
        decision_ids = {row.supply_decision_id for row in rows if row.supply_decision_id}
        line_nos = (
            dict(
                self.db.query(
                    ProjectSalesOrderLine.id, ProjectSalesOrderLine.line_no
                )
                .filter(ProjectSalesOrderLine.id.in_(list(line_ids)))
                .all()
            )
            if line_ids
            else {}
        )
        revisions = (
            dict(
                self.db.query(SOSupplyDecision.id, SOSupplyDecision.revision_no)
                .filter(SOSupplyDecision.id.in_(list(decision_ids)))
                .all()
            )
            if decision_ids
            else {}
        )
        return {
            row.id: {
                "line_no": line_nos.get(row.so_line_id),
                "decision_revision": revisions.get(row.supply_decision_id),
            }
            for row in rows
        }

    def _project_customer_labels(self, pso_ids: set) -> Dict[str, Optional[str]]:
        """`BUIMACO / TUJU RESIDENCE` per sales order, via `project_customer_label`.

        The join to `Project` is OUTER, and that is a fix rather than a style choice: an
        order ADOPTED from the AutoCount book has no project registration by design, so an
        inner join answered nothing for it and the column came back blank on a row that
        plainly has a customer. When there is no project party to bill, the CORE sales
        order's own customer is that customer - it is the same document, read through the
        table it was imported into.
        """
        if not pso_ids:
            return {}
        rows = (
            self.db.query(
                ProjectSalesOrder.id,
                ProjectSalesOrder.is_pre_order,
                Project.title,
                Customer.customer_name,
            )
            .outerjoin(Project, Project.id == ProjectSalesOrder.project_id)
            .outerjoin(
                ProjectPurchaseOrder,
                ProjectPurchaseOrder.id == ProjectSalesOrder.purchase_order_id,
            )
            .outerjoin(ProjectParty, ProjectParty.id == ProjectPurchaseOrder.issuing_party_id)
            .outerjoin(SalesOrder, SalesOrder.id == ProjectSalesOrder.so_id)
            # ONE join through a coalesce rather than two aliases of `customers`: the
            # company-scope listener emits an UNALIASED `customers.company_id` into an
            # aliased ON clause, which Postgres refuses outright.
            .outerjoin(
                Customer,
                Customer.id
                == func.coalesce(ProjectParty.customer_id, SalesOrder.customer_id),
            )
            .filter(ProjectSalesOrder.id.in_(list(pso_ids)))
            .all()
        )
        return {
            pso_id: project_customer_label(customer_name, title, is_pre_order)
            for pso_id, is_pre_order, title, customer_name in rows
        }

    def _remark(self, row: OrderInquiryRow) -> str:
        """The REMARK column, spelled the way the client's own file spells it.

        An inbound row prints its SPO reference rather than a verb, because the
        reference is the thing purchasing looks up when they want to know when it lands.
        """
        if row.verb == IV_ALREADY_INBOUND and row.spo_ref:
            return row.spo_ref
        return REMARK_SPELLING.get(row.verb, row.verb)

    def get_for_sales_order(self, pso_id: str) -> Optional[Dict[str, Any]]:
        """The latest inquiry raised on one sales order, with its rows."""
        inquiry = (
            self.db.query(OrderInquiry)
            .filter(OrderInquiry.project_sales_order_id == pso_id)
            .order_by(OrderInquiry.raised_at.desc())
            .first()
        )
        if inquiry is None:
            return None
        rows = (
            self.db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.order_inquiry_id == inquiry.id)
            .order_by(OrderInquiryRow.created_at.asc())
            .all()
        )
        task = self.task_for(inquiry.id)
        return {
            "id": inquiry.id,
            # What the screen prints. The id is addressing; this is the name.
            "inquiry_no": inquiry.inquiry_no,
            "project_sales_order_id": inquiry.project_sales_order_id,
            "amendment_id": inquiry.amendment_id,
            "state": inquiry.state,
            "raised_at": inquiry.raised_at,
            "task_id": task.id if task else None,
            "task_name": task.name if task else None,
            "rows": self.serialize_rows(rows),
        }

    # --------------------------------------------------------------- acting

    def mark_rows(
        self, row_ids: Sequence[str], *, state: str, actor_user_id: str
    ) -> List[Dict[str, Any]]:
        """Purchasing says what happened to a row (AC-I7)."""
        if state not in (INQUIRY_ACTIONED, INQUIRY_CANCELLED, INQUIRY_RAISED):
            raise AppException(
                status_code=422,
                message="An inquiry row is raised, actioned or cancelled.",
                code="order_inquiry_state_invalid",
            )
        if not row_ids:
            raise AppException(
                status_code=422,
                message="Name at least one row.",
                code="order_inquiry_no_rows",
            )
        rows = (
            self.db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.id.in_(list(row_ids)))
            .all()
        )
        found = {row.id for row in rows}
        missing = [row_id for row_id in row_ids if row_id not in found]
        if missing:
            raise AppException(
                status_code=404,
                message=f"{len(missing)} of those rows no longer exist.",
                code="order_inquiry_row_not_found",
            )
        now = datetime.utcnow()
        for row in rows:
            # A row this bulk action moves OFF `placed` (section G) drops its PO tag too:
            # "blank means not placed yet" is what the worklist's PO no / Supplier columns
            # promise, and a cancelled or reopened row that still carried one would read
            # as placed when it no longer is. The claim itself is left alone here - it is
            # evidence of what the row WAS tagged to, and only Untag owns removing it.
            if row.state == INQUIRY_PLACED and state != INQUIRY_PLACED:
                row.po_ref = None
                row.po_line_id = None
            row.state = state
            # Back to raised is an undo, and an undo has to clear the claim it made or
            # the row would still read as something somebody dealt with.
            row.actioned_by = actor_user_id if state != INQUIRY_RAISED else None
            row.actioned_at = now if state != INQUIRY_RAISED else None
        self.db.flush()
        self._refresh_inquiry_states({row.order_inquiry_id for row in rows})
        return self.serialize_rows(rows)

    def _refresh_inquiry_states(self, inquiry_ids: set) -> None:
        """An inquiry is closed when nothing on it is still waiting."""
        for inquiry_id in inquiry_ids:
            inquiry = (
                self.db.query(OrderInquiry).filter(OrderInquiry.id == inquiry_id).first()
            )
            if inquiry is None:
                continue
            states = {
                state
                for (state,) in self.db.query(OrderInquiryRow.state)
                .filter(OrderInquiryRow.order_inquiry_id == inquiry_id)
                .distinct()
                .all()
            }
            if not states or INQUIRY_RAISED in states:
                inquiry.state = INQUIRY_RAISED
            elif states == {INQUIRY_CANCELLED}:
                inquiry.state = INQUIRY_CANCELLED
            else:
                inquiry.state = INQUIRY_ACTIONED
        self.db.flush()

    # --------------------------------------------------- tag an outstanding PO (section G)
    #
    # "identify which outstanding PO has quantity to fulfil this order inquiry, tag it,
    # and the quantity to be ordered is deducted" (the captain, 20 Aug). A deliberate,
    # evidence-carrying exception on the DEMAND side only: tagging never makes the PO
    # supply (`on_order_v` still reads `spo_allocations` only). The lever is the existing
    # one - `committed_v`'s confirmed leg counts `state = 'raised'` rows only - so moving
    # a row to `placed` is what removes it from the reorder engine's suggestion, with no
    # view change and no silent hole where "mark actioned" used to cover it with nothing
    # to show for it.
    #
    # G2 (the captain, 20 Aug, live-testing the shipped feature): "we need to link
    # already at first already instead of suggesting and needing the users to click 1 by
    # 1" - placements now happen AUTOMATICALLY (`auto_place_for_products`, cascading from
    # the earliest expected-date PO line, ties by document sequence, partial coverage
    # allowed, POs only - never SPO-). The dialog survives as override + audit, not as
    # the workflow: `place_on_po` (one line) and `place_on_po_allocations` (a cascade,
    # possibly several lines) are both still here for a human to use by exception.

    def _open_po_lines_for_product(
        self, product_id: str
    ) -> List[Tuple[PurchaseOrderLine, PurchaseOrder, Optional[Supplier], Decimal]]:
        """Open PO lines of one product, in CASCADE ORDER - soonest `expected_date`
        first, ties broken by document sequence (the PO's own number, then the line's
        own id) - netted for what other PLACED rows already tagged. The ONE query both
        the dialog's candidates and the auto-place cascade walk, so the two can never
        disagree (G2 rule 1).

        SPO- prefixed documents are never candidates here (G2 rule 3, "those are SPO,
        not PO" - the captain, live-testing): "Place on PO" tags an outstanding PURCHASE
        ORDER, never a scheduled purchase order. SPO coverage stays the ladder engine's
        job (`net_demand` / `_pools` above), untouched by this feature.

        ``PurchaseOrder.status`` is also gated to active/partial (code review, 21 Aug,
        B3, same family as G2 rule 3 above): a ``draft_recommendation`` PO is not yet an
        outstanding order - it is OUTSIDE `scm.on_order_v` for exactly that reason
        (M4-D5) - and its lines are also not the ones a re-decision at
        ``decision_service._remove_product_lines`` may delete out from under a tag
        without ceremony. Without this gate, auto-place could tag an order-inquiry row
        onto an unconfirmed draft's line; the buyer edits the decision before
        confirming; the draft line is deleted; and the row is left ``state='placed'``
        with a NULL ``po_line_id`` - the exact stranding
        ``purchase_order_service.bulk_delete`` already guards a PO's own delete against.
        """
        tagged = self._tagged_by_po_line()
        rows = (
            self.db.query(PurchaseOrderLine, PurchaseOrder, Supplier)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .filter(
                PurchaseOrderLine.product_id == product_id,
                PurchaseOrderLine.line_status == "open",
                PurchaseOrder.status.in_(("active", "partial")),
                PurchaseOrder.po_number.notlike("SPO-%"),
            )
            .order_by(
                PurchaseOrderLine.expected_date.asc().nulls_last(),
                PurchaseOrder.po_number.asc(),
                PurchaseOrderLine.id.asc(),
            )
            .all()
        )
        out: List[Tuple[PurchaseOrderLine, PurchaseOrder, Optional[Supplier], Decimal]] = []
        for line, po, supplier in rows:
            balance = _dec(line.qty_ordered) - _dec(line.qty_received)
            remaining = balance - tagged.get(line.id, _ZERO)
            if remaining > _ZERO:
                out.append((line, po, supplier, remaining))
        return out

    @staticmethod
    def _cascade_take(
        lines: Sequence[Tuple[PurchaseOrderLine, PurchaseOrder, Optional[Supplier], Decimal]],
        need: Decimal,
    ) -> List[Tuple[str, Decimal]]:
        """G2 rule 2, "take from the earliest PO, then subsequently from subsequent PO":
        `min(remaining balance, still needed)` off each line in the order it is given,
        until the need is covered or the candidates run out. Partial coverage is allowed
      - a `need` bigger than every line's remaining balance combined simply returns
        less than `need`, and it is the CALLER's job to decide what an unfinished walk
        means for the row (the uncovered remainder stays a raised Buy).
        """
        still = need
        takes: List[Tuple[str, Decimal]] = []
        for line, _po, _supplier, remaining in lines:
            if still <= _ZERO:
                break
            take = remaining if remaining < still else still
            if take > _ZERO:
                takes.append((line.id, take))
                still -= take
        return takes

    def po_candidates_for_row(self, row_id: str) -> List[Dict[str, Any]]:
        """Open PO lines of this row's own product, soonest `expected_date` first.

        `remaining` already nets what OTHER placed rows have tagged onto the same line -
        the reason two rows can never be pointed at the same PO quantity - so `covers`
        and `recommended` are both answered against what is ACTUALLY left, not the line's
        raw balance. `default_take` is the cascade's own preview (G2): what
        `auto_place_for_products` would take off THIS line for THIS row, computed by the
        SAME walk - the dialog's starting point, not a second opinion.
        """
        row = self._row_or_404(row_id)
        self._assert_placeable(row)
        product_id = self._resolve_product_id(row)
        if not product_id:
            raise AppException(
                status_code=409,
                message="This row names no product to match a purchase order line against.",
                code="order_inquiry_no_product",
            )
        need = _dec(row.qty)
        lines = self._open_po_lines_for_product(product_id)
        cascade = dict(self._cascade_take(lines, need))
        claims_by_line = self._placed_claims_by_po_line([line.id for line, _po, _s, _r in lines])
        candidates: List[Dict[str, Any]] = []
        for line, po, supplier, remaining in lines:
            already = _dec(line.qty_ordered) - _dec(line.qty_received) - remaining
            candidates.append(
                {
                    "po_line_id": line.id,
                    "po_number": po.po_number,
                    "supplier_name": supplier.supplier_name if supplier else None,
                    "expected_date": line.expected_date,
                    "qty_ordered": _qty_str(_dec(line.qty_ordered)),
                    "qty_received": _qty_str(_dec(line.qty_received)),
                    "already_tagged": _qty_str(already),
                    "remaining": _qty_str(remaining),
                    "covers": remaining >= need,
                    "recommended": False,
                    "default_take": _qty_str(cascade.get(line.id, _ZERO)),
                    "unit_cost": (
                        _qty_str(_dec(line.unit_cost)) if line.unit_cost is not None else None
                    ),
                    "currency": line.currency,
                    "claims": claims_by_line.get(line.id, []),
                }
            )
        recommended = next((c for c in candidates if c["covers"]), None)
        if recommended is not None:
            recommended["recommended"] = True
        return candidates

    def _apply_placement(
        self,
        row: OrderInquiryRow,
        line: PurchaseOrderLine,
        po: Optional[PurchaseOrder],
        supplier: Optional[Supplier],
        *,
        actor_user_id: str,
        auto_trigger: Optional[str] = None,
    ) -> None:
        """The write half of a placement, shared by a single manual tag, a cascade split
        row and an auto placement: stamp the note, set the tag, write the audit claim.

        `auto_trigger` names WHY this happened without a person clicking it (G2 rule 4:
        "every auto placement writes the same OrderLinkClaim evidence with an auto
        marker") - appended to the row's OWN note, which is already this feature's
        evidence field (`"Placed on <po> (<supplier>), expected <date>"`), rather than a
        new column: `OrderLinkClaim` carries no free-text field to reuse instead
        (`source` is a closed 30-char vocabulary another feed also writes), so the note a
        person already reads on the row is where "how did this happen" is answered.
        """
        po_number = po.po_number if po else "an unnamed purchase order"
        supplier_name = supplier.supplier_name if supplier else "unknown supplier"
        expected = line.expected_date.isoformat() if line.expected_date else "no date"
        stamp = f"Placed on {po_number} ({supplier_name}), expected {expected}"
        if auto_trigger:
            stamp = f"{stamp}; auto: {auto_trigger}"
        row.note = f"{row.note}; {stamp}" if row.note else stamp
        row.po_ref = po_number if po else None
        row.po_line_id = line.id
        row.state = INQUIRY_PLACED
        row.actioned_by = actor_user_id
        row.actioned_at = datetime.utcnow()

        if po:
            so_number, item_code, core_line_id = self._claim_identity(row)
            order_link_service.claim_placed_on_po(
                self.db,
                company_id=row.company_id,
                so_number=so_number,
                po_number=po.po_number,
                item_code=item_code,
                so_line_id=core_line_id,
                po_line_id=line.id,
            )

    def place_on_po(
        self, row_id: str, po_line_id: str, *, actor_user_id: str
    ) -> Dict[str, Any]:
        """Tag this row to ONE open PO line. The captain's "quantity to be ordered is
        deducted" - the deduction IS the row leaving `state = 'raised'`.

        The single-line shape section G shipped with, kept byte-for-byte: a row a human
        places on one line that covers it whole never becomes a split.
        """
        row = self._row_or_404(row_id)
        self._assert_placeable(row)

        line = (
            self.db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.id == po_line_id)
            .first()
        )
        if line is None:
            raise AppException(
                status_code=404,
                message="That purchase order line no longer exists.",
                code="po_line_not_found",
            )
        if line.line_status != "open":
            raise AppException(
                status_code=409,
                message="That purchase order line is no longer open.",
                code="order_inquiry_po_line_closed",
            )
        product_id = self._resolve_product_id(row)
        if not product_id or str(line.product_id) != str(product_id):
            raise AppException(
                status_code=409,
                message="That purchase order line is not for this row's product.",
                code="order_inquiry_product_mismatch",
            )

        po = (
            self.db.query(PurchaseOrder)
            .filter(PurchaseOrder.id == line.purchase_order_id)
            .first()
        )
        balance = _dec(line.qty_ordered) - _dec(line.qty_received)
        already = self._tagged_by_po_line().get(line.id, _ZERO)
        remaining = balance - already
        need = _dec(row.qty)
        if remaining < need:
            raise AppException(
                status_code=409,
                message=(
                    f"{po.po_number if po else 'That line'} has {_qty_str(remaining)} "
                    f"left, {_qty_str(need - remaining)} short of the {_qty_str(need)} "
                    "this row needs."
                ),
                code="order_inquiry_po_line_short",
            )

        supplier = (
            self.db.query(Supplier).filter(Supplier.id == po.supplier_id).first()
            if po and po.supplier_id
            else None
        )
        self._apply_placement(row, line, po, supplier, actor_user_id=actor_user_id)

        self.db.flush()
        self._refresh_inquiry_states({row.order_inquiry_id})
        return self.serialize_rows([row])[0]

    def place_on_po_allocations(
        self,
        row_id: str,
        allocations: Sequence[Dict[str, Any]],
        *,
        actor_user_id: str,
        auto_trigger: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Tag this row across ONE OR MORE outstanding PO lines - the cascade shape (G2
        rule 2), used by both the reworked dialog (a person adjusting the cascade's own
        preview) and `auto_place_for_products` (nobody adjusting it at all).

        **Multi-line coverage shape: SPLIT, one row per allocation.**
        `order_inquiry_rows` holds exactly one `po_line_id` (migration 400) - a row a
        single PO line cannot cover whole has nowhere to hold a second tag, so it is
        split into one row per PO line taken, the same way this module already treats a
        quantity that outgrows one instruction (`_write`/`net_demand` writing one row per
        `DemandPlan`, never packing several coverages onto one row). The FIRST allocation
        reuses the row that was already raised - the ordinary single-line case, still the
        common one, therefore changes nothing about the row's own identity or the ids
        anything else already points at (`supply_decision_id`, an existing claim); every
        FURTHER allocation is a brand-new row carrying the same `so_line_id` / item code /
        delivery date / `supply_decision_id` as the row it split from.

        **Partial coverage keeps the netting honest.** `committed_v`'s confirmed leg
        counts a `raised` ORDER row and nothing else (demand.py); a `placed` row leaves
        it. So when the allocations do not cover the row's whole quantity, the ORIGINAL
        row is left `raised` at the REMAINING quantity instead of being reused for an
        allocation - every placed allocation becomes its own new `placed` row, and the
        genuinely still-needed remainder never quietly leaves the confirmed leg. Either
        way `sum(qty of every row this call touches) == the row's qty before the call`.
        """
        row = self._row_or_404(row_id)
        self._assert_placeable(row)
        if not allocations:
            raise AppException(
                status_code=422,
                message="Name at least one purchase order line.",
                code="order_inquiry_no_allocations",
            )
        product_id = self._resolve_product_id(row)
        if not product_id:
            raise AppException(
                status_code=409,
                message="This row names no product to match a purchase order line against.",
                code="order_inquiry_no_product",
            )

        need = _dec(row.qty)
        tagged = self._tagged_by_po_line()
        line_ids = [str(entry["po_line_id"]) for entry in allocations if entry.get("po_line_id")]
        lines = (
            self.db.query(PurchaseOrderLine, PurchaseOrder, Supplier)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .filter(PurchaseOrderLine.id.in_(line_ids))
            .all()
        )
        by_id = {line.id: (line, po, supplier) for line, po, supplier in lines}

        resolved: List[
            Tuple[PurchaseOrderLine, Optional[PurchaseOrder], Optional[Supplier], Decimal]
        ] = []
        claimed_within_call: Dict[str, Decimal] = {}
        total_alloc = _ZERO
        for entry in allocations:
            po_line_id = str(entry.get("po_line_id") or "")
            qty = _dec(entry.get("qty"))
            if qty <= _ZERO:
                continue
            found = by_id.get(po_line_id)
            if found is None:
                raise AppException(
                    status_code=404,
                    message="That purchase order line no longer exists.",
                    code="po_line_not_found",
                )
            line, po, supplier = found
            if line.line_status != "open":
                raise AppException(
                    status_code=409,
                    message="That purchase order line is no longer open.",
                    code="order_inquiry_po_line_closed",
                )
            if str(line.product_id) != str(product_id):
                raise AppException(
                    status_code=409,
                    message="That purchase order line is not for this row's product.",
                    code="order_inquiry_product_mismatch",
                )
            balance = _dec(line.qty_ordered) - _dec(line.qty_received)
            already = tagged.get(line.id, _ZERO) + claimed_within_call.get(line.id, _ZERO)
            remaining = balance - already
            if remaining < qty:
                raise AppException(
                    status_code=409,
                    message=(
                        f"{po.po_number if po else 'That line'} has {_qty_str(remaining)} "
                        f"left, {_qty_str(qty - remaining)} short of the {_qty_str(qty)} "
                        "allocated to it."
                    ),
                    code="order_inquiry_po_line_short",
                )
            claimed_within_call[line.id] = already + qty - tagged.get(line.id, _ZERO)
            resolved.append((line, po, supplier, qty))
            total_alloc += qty

        if not resolved:
            raise AppException(
                status_code=422,
                message="Name at least one purchase order line.",
                code="order_inquiry_no_allocations",
            )
        if total_alloc > need:
            raise AppException(
                status_code=409,
                message=(
                    f"{_qty_str(total_alloc)} allocated is more than the {_qty_str(need)} "
                    "this row needs."
                ),
                code="order_inquiry_over_allocated",
            )

        remainder = need - total_alloc
        full_coverage = remainder <= _ZERO
        written: List[OrderInquiryRow] = []
        for index, (line, po, supplier, qty) in enumerate(resolved):
            if full_coverage and index == 0:
                target = row
                target.qty = qty
            else:
                target = OrderInquiryRow(
                    company_id=row.company_id,
                    order_inquiry_id=row.order_inquiry_id,
                    so_line_id=row.so_line_id,
                    item_code=row.item_code,
                    qty=qty,
                    delivery_date=row.delivery_date,
                    stock_location=row.stock_location,
                    verb=row.verb,
                    covered_by=row.covered_by,
                    supply_decision_id=row.supply_decision_id,
                    state=INQUIRY_RAISED,
                )
                self.db.add(target)
                self.db.flush()
            self._apply_placement(
                target, line, po, supplier, actor_user_id=actor_user_id, auto_trigger=auto_trigger
            )
            written.append(target)

        if not full_coverage:
            # `row` was never reused for an allocation above - it stays `raised`, only its
            # quantity shrinks to what the cascade could not cover.
            row.qty = remainder

        self.db.flush()
        self._refresh_inquiry_states({row.order_inquiry_id})
        return self.serialize_rows(written)

    def auto_place_for_products(
        self,
        product_ids: Optional[Sequence[str]],
        *,
        actor_user_id: str,
        trigger: str,
    ) -> Dict[str, Any]:
        """The bulk, idempotent cascade pass (G2 rule 1: "we need to link already at
        first already instead of suggesting and needing the users to click 1 by 1").

        Every RAISED, placeable row of the named products - or of every product with one,
        when `product_ids` is omitted - is cascaded against its own open PO lines,
        HIGHEST FULFILMENT PRIORITY FIRST. AC-H5 says the ranking that decides ANY
        draw-down is the SAME policy, everywhere it applies - so which row claims a
        scarce PO line first is scored through `scm.priority.factors_for_demand_rows`,
        the identical assembly the fulfilment board and the Loading Plan already use,
        rather than a private sort this method grew on its own. That answers the
        captain's 20 Aug question - "do we account for both SO date and delivery date?"
      - with both: `need_by_date` from the row's own `delivery_date`, and
        `document_age` from the sales order's own document date (`published_at`, or
        `created_at` before publish - see `_rank_raised_rows`). With no active
        `PriorityPolicy` the call falls back to `DEFAULT_WEIGHTS` on its own; ties
        (including "this policy weights nothing here") fall back to the original
        ordering (`delivery_date` then `created_at`), so this is a strict refinement of
        the old behaviour, never a different one. A second run places nothing further: a
        row this pass placed (or split) is no longer `raised`, so it drops out of the
        very query that feeds the next run - the idempotence the three triggers (import,
        decision confirm, the worklist button) all rely on.

        `trigger` is stamped onto every placement it makes (`_apply_placement`'s
        `auto_trigger`), so "why is this placed" is always answerable from the row's own
        note - never a silent placement with nothing to show for it.
        """
        query = self.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.state == INQUIRY_RAISED,
            OrderInquiryRow.verb.in_(_PLACEABLE_VERBS),
        )
        if product_ids:
            wanted = [pid for pid in product_ids if pid]
            so_line_ids = [
                line_id
                for (line_id,) in self.db.query(ProjectSalesOrderLine.id).filter(
                    ProjectSalesOrderLine.product_id.in_(wanted)
                )
            ]
            codes = [
                code
                for (code,) in self.db.query(Product.product_code).filter(
                    Product.id.in_(wanted)
                )
                if code
            ]
            conditions = []
            if so_line_ids:
                conditions.append(OrderInquiryRow.so_line_id.in_(so_line_ids))
            if codes:
                conditions.append(OrderInquiryRow.item_code.in_(codes))
            if not conditions:
                return {"placed_rows": 0, "allocations": 0, "products_touched": 0}
            query = query.filter(or_(*conditions))

        rows = self._rank_raised_rows(query.all())

        placed_rows = 0
        allocation_count = 0
        products_touched: set = set()
        for row in rows:
            product_id = self._resolve_product_id(row)
            if not product_id:
                continue
            need = _dec(row.qty)
            if need <= _ZERO:
                continue
            lines = self._open_po_lines_for_product(product_id)
            if not lines:
                continue
            takes = self._cascade_take(lines, need)
            if not takes:
                continue
            written = self.place_on_po_allocations(
                row.id,
                [{"po_line_id": line_id, "qty": qty} for line_id, qty in takes],
                actor_user_id=actor_user_id,
                auto_trigger=trigger,
            )
            placed_rows += len(written)
            allocation_count += len(takes)
            products_touched.add(str(product_id))

        return {
            "placed_rows": placed_rows,
            "allocations": allocation_count,
            "products_touched": len(products_touched),
        }

    def _rank_raised_rows(
        self, rows: Sequence[OrderInquiryRow]
    ) -> List[OrderInquiryRow]:
        """Highest fulfilment priority first, for `auto_place_for_products` (AC-H5).

        Scores every row through `scm.priority.factors_for_demand_rows` - the same call
        the fulfilment board and the Loading Plan already use - so which RAISED row
        claims a scarce PO line first is decided by the one active `PriorityPolicy`,
        never a second convention this method invents for itself. The mapping per row:

          * `row_key`            <- the row's own id.
          * `required_date`      <- the row's `delivery_date` (`need_by_date`).
          * `order_date`         <- the sales order's own document date, `published_at`
            or `created_at` before publish - the identical fact `_context_for` already
            surfaces as `so_date` for this same row set (`document_age`).
          * `demand_class`       <- always `"project"`: every row this cascade sees came
            off a project order inquiry.
          * `payment_terms_days` <- the resolved customer's terms
            (`_customer_ids_for_pso` + `priority.payment_terms_by_customer`) when a
            customer is reachable, `None` otherwise - an unknown is ABSENT, not a
            default.

        `factors_for_demand_rows` resolves the active policy itself (falling back to
        `DEFAULT_WEIGHTS` when none is active), so nothing here hand-rolls a fallback.
        Rows tie on their score - including "this policy weights nothing here" - break
        to the ORIGINAL ordering, `delivery_date` then `created_at`: this is a strict
        refinement of what the cascade did before, not a different rule.

        **Scored per PRODUCT, one contender group at a time** (S5, code review, 20 Aug
        2026): `factors_for_demand_rows`'s own docstring is explicit that it normalizes
        VALUES ACROSS THE ROWS PASSED IN - "the caller passes one cell's contributors,
        not the world" - because a rank only means anything against the rows actually
        competing for the SAME scarce PO lines. `auto_place_for_products` calls this
        with every raised row across EVERY product in one batch; passing the whole batch
        through in one `factors_for_demand_rows` call let an unrelated product's extreme
        `order_date` compress the `document_age` axis for every OTHER product's rows too,
        which could flip which of two genuinely competing rows on the SAME product wins
        the only PO line there is. Grouped by product here instead, each group scored in
        isolation, then the ranked groups concatenated back in the order their product
        first appeared in `rows` - so which PRODUCT is processed first is unchanged, only
        the SCORE within a product no longer depends on demand for a different one.
        """
        if not rows:
            return []

        inquiry_ids = {row.order_inquiry_id for row in rows}
        joined = (
            self.db.query(OrderInquiry.id, ProjectSalesOrder)
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == OrderInquiry.project_sales_order_id,
            )
            .filter(OrderInquiry.id.in_(list(inquiry_ids)))
            .all()
        )
        order_dates: Dict[str, Any] = {}
        pso_by_inquiry: Dict[str, str] = {}
        pso_ids: set = set()
        for inquiry_id, order in joined:
            order_dates[inquiry_id] = order.published_at or order.created_at
            pso_by_inquiry[inquiry_id] = order.id
            pso_ids.add(order.id)

        customer_ids = self._customer_ids_for_pso(pso_ids)
        terms_by_customer = priority.payment_terms_by_customer(
            self.db, [cid for cid in customer_ids.values() if cid]
        )

        # One contender group per product (`None` for a row that resolves to no product
        # at all - it competes with nothing and is filtered out downstream anyway), each
        # group keeping the rows' relative order from `rows` and the groups themselves
        # ordered by each product's first appearance - `auto_place_for_products` still
        # processes products in the same order it always has.
        product_by_row = self._resolve_product_ids_bulk(rows)
        groups: Dict[Optional[str], List[OrderInquiryRow]] = {}
        group_order: List[Optional[str]] = []
        for row in rows:
            key = product_by_row.get(row.id)
            bucket = groups.get(key)
            if bucket is None:
                bucket = []
                groups[key] = bucket
                group_order.append(key)
            bucket.append(row)

        def _sort_key(row: OrderInquiryRow, scores: Dict[str, float]) -> Tuple[float, date, datetime]:
            return (
                -scores.get(row.id, 0.0),
                row.delivery_date or date.max,
                row.created_at or datetime.max,
            )

        # S5 (code review, 20 Aug 2026): hoisted OUT of the per-product loop below.
        # `factors_for_demand_rows` resolves `active_policy(db)` itself whenever `weights`/
        # `class_weights` is left None - an uncached query - so leaving it unset here issued
        # one identical query PER PRODUCT GROUP (300 products, 300 queries) for a policy row
        # that cannot change mid-call. Resolved once and passed explicitly into every group;
        # the grouping/scoring semantics are unchanged, only the resolution moved.
        weights, class_weights = priority.policy_weights(priority.active_policy(self.db))

        ranked: List[OrderInquiryRow] = []
        for key in group_order:
            group_rows = groups[key]
            demand_rows = []
            for row in group_rows:
                pso_id = pso_by_inquiry.get(row.order_inquiry_id)
                customer_id = customer_ids.get(pso_id) if pso_id else None
                demand_rows.append(
                    {
                        "row_key": row.id,
                        "required_date": row.delivery_date,
                        "order_date": order_dates.get(row.order_inquiry_id),
                        "payment_terms_days": (
                            terms_by_customer.get(customer_id) if customer_id else None
                        ),
                        "demand_class": "project",
                    }
                )
            factors_by_row = priority.factors_for_demand_rows(
                self.db, demand_rows, weights=weights, class_weights=class_weights
            )
            scores = priority.scores_for(factors_by_row)
            ranked.extend(sorted(group_rows, key=lambda r: _sort_key(r, scores)))

        return ranked

    def _customer_ids_for_pso(self, pso_ids: set) -> Dict[str, Optional[str]]:
        """Customer id per project sales order, the same resolution
        `_project_customer_labels` uses for the display name: the project's billing
        party first (`ProjectParty.customer_id` through the issuing purchase order),
        the CORE sales order's own customer when there is no project party - an ADOPTED
        order has none by design. Cheap on purpose: this only feeds an optional ranking
        factor, so a customer that costs more than one join to reach stays ABSENT.
        """
        if not pso_ids:
            return {}
        rows = (
            self.db.query(
                ProjectSalesOrder.id,
                func.coalesce(ProjectParty.customer_id, SalesOrder.customer_id),
            )
            .outerjoin(
                ProjectPurchaseOrder,
                ProjectPurchaseOrder.id == ProjectSalesOrder.purchase_order_id,
            )
            .outerjoin(ProjectParty, ProjectParty.id == ProjectPurchaseOrder.issuing_party_id)
            .outerjoin(SalesOrder, SalesOrder.id == ProjectSalesOrder.so_id)
            .filter(ProjectSalesOrder.id.in_(list(pso_ids)))
            .all()
        )
        return {pso_id: customer_id for pso_id, customer_id in rows}

    def unplace(self, row_id: str, *, actor_user_id: str) -> Dict[str, Any]:
        """Untag: the row goes back to `raised` and the reorder engine sees it again."""
        row = self._row_or_404(row_id)
        if row.state != INQUIRY_PLACED:
            raise AppException(
                status_code=409,
                message="This row is not placed on a purchase order.",
                code="order_inquiry_not_placed",
            )
        self._unplace_row(row)
        self.db.flush()
        self._refresh_inquiry_states({row.order_inquiry_id})
        return self.serialize_rows([row])[0]

    def unplace_rows(self, row_ids: Sequence[str]) -> int:
        """Bulk untag by explicit row id - the WRITE half of "Unplace all" (the captain,
        20/21 Aug). Which ids are in scope is entirely the caller's job
        (`OrderInquiryWorklistService.unplace_all` resolves them off the worklist's own
        filters, the same `_base()` the list and the summary already read, so the count a
        person confirmed and the rows this actually touches can never disagree); this
        method only ever writes, via the same `_unplace_row` a single Untag uses.

        **Split-row decision: leave each split row raised at its own quantity, do not
        merge siblings back into one row.** A cascade placement (`place_on_po_allocations`)
        may have split one raised row into several PLACED rows across different PO lines
        (migration 400 - one `po_line_id` per row), and by the time this runs there is no
        reliable join key that says two rows were ever "the same row": they share
        `so_line_id` / `item_code` / `delivery_date` at split time, but so does any other
        still-open row of the same line, and a person may since have acted on one sibling
        (marked it cancelled, changed its note) while another stayed placed. Merging would
        either invent a merge rule this module does not otherwise have, or silently
        overwrite something a person already touched. Leaving every row raised at its own
        quantity is the simplest thing that is still correct: the sum of open quantity on
        the line is unchanged, and the next Auto-place cascades every one of them exactly
        as it would any other raised row - which is the whole point of the round trip.

        Idempotent: an empty `row_ids`, or a set none of which is still placed (a second
        click after the first already ran), returns 0. Re-filtered to `state = placed`
        here as well as by the caller - this method never touches a row on the caller's
        say-so alone.
        """
        wanted = [row_id for row_id in (row_ids or []) if row_id]
        if not wanted:
            return 0
        rows = (
            self.db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.id.in_(wanted), OrderInquiryRow.state == INQUIRY_PLACED
            )
            .all()
        )
        for row in rows:
            self._unplace_row(row)
        if rows:
            self.db.flush()
            self._refresh_inquiry_states({row.order_inquiry_id for row in rows})
        return len(rows)

    def _unplace_row(self, row: OrderInquiryRow) -> None:
        """The write half of an untag, shared by the single-row action and the
        per-product bulk pass: stamp the note, drop the tag, release the audit claim."""
        po_ref = row.po_ref
        so_number, item_code, _core_line_id = self._claim_identity(row)
        stamp = f"Unplaced from {po_ref}" if po_ref else "Unplaced"
        row.note = f"{row.note}; {stamp}" if row.note else stamp
        row.po_ref = None
        row.po_line_id = None
        row.state = INQUIRY_RAISED
        row.actioned_by = None
        row.actioned_at = None

        if po_ref:
            order_link_service.delete_own_claim(
                self.db,
                company_id=row.company_id,
                so_number=so_number,
                po_number=po_ref,
                item_code=item_code,
            )

    def _row_or_404(self, row_id: str) -> OrderInquiryRow:
        row = self.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).first()
        if row is None:
            raise AppException(
                status_code=404,
                message="That order inquiry row no longer exists.",
                code="order_inquiry_row_not_found",
            )
        return row

    def _assert_placeable(self, row: OrderInquiryRow) -> None:
        if row.verb not in _PLACEABLE_VERBS:
            raise AppException(
                status_code=409,
                message="Only an ORDER or RESERVE & ORDER row can be placed on a purchase order.",
                code="order_inquiry_not_placeable_verb",
            )
        if row.state != INQUIRY_RAISED:
            raise AppException(
                status_code=409,
                message="Only a raised row can be placed on a purchase order.",
                code="order_inquiry_not_raised",
            )

    def _resolve_product_id(self, row: OrderInquiryRow) -> Optional[str]:
        """The product this row is FOR: the reconciled line's product first, the item
        code second. Never invented when neither resolves."""
        if row.so_line_id:
            line = (
                self.db.query(ProjectSalesOrderLine.product_id)
                .filter(ProjectSalesOrderLine.id == row.so_line_id)
                .first()
            )
            if line and line[0]:
                return line[0]
        if row.item_code:
            product = (
                self.db.query(Product.id)
                .filter(Product.product_code == row.item_code)
                .first()
            )
            if product:
                return product[0]
        return None

    def _resolve_product_ids_bulk(
        self, rows: Sequence[OrderInquiryRow]
    ) -> Dict[str, Optional[str]]:
        """Row id -> product id, the SAME precedence as `_resolve_product_id` (the
        reconciled line's product first, the item code second), but one query per source
        rather than one per row - the batch version a listing needs."""
        so_line_ids = {row.so_line_id for row in rows if row.so_line_id}
        item_codes = {row.item_code for row in rows if row.item_code}
        line_products = (
            dict(
                self.db.query(
                    ProjectSalesOrderLine.id, ProjectSalesOrderLine.product_id
                )
                .filter(ProjectSalesOrderLine.id.in_(list(so_line_ids)))
                .all()
            )
            if so_line_ids
            else {}
        )
        code_products = (
            dict(
                self.db.query(Product.product_code, Product.id)
                .filter(Product.product_code.in_(list(item_codes)))
                .all()
            )
            if item_codes
            else {}
        )
        out: Dict[str, Optional[str]] = {}
        for row in rows:
            product_id = line_products.get(row.so_line_id) if row.so_line_id else None
            if not product_id and row.item_code:
                product_id = code_products.get(row.item_code)
            out[row.id] = product_id
        return out

    def open_po_line_product_ids(self, product_ids: Sequence[Optional[str]]) -> set:
        """Which of these products still has an outstanding PO line left, once every
        OTHER placed row's tag is netted off - the exact predicate `po_candidates_for_row`
        answers per row, computed ONCE for a whole listing (`has_open_po_line`) so the
        flag and the dialog can never disagree. SPO- prefixed documents are excluded here
        too (G2 rule 3) - the same join `_open_po_lines_for_product` filters on, so this
        flag can never promise a candidate the cascade would refuse.
        """
        wanted = {pid for pid in product_ids if pid}
        if not wanted:
            return set()
        tagged = self._tagged_by_po_line()
        lines = (
            self.db.query(
                PurchaseOrderLine.id,
                PurchaseOrderLine.product_id,
                PurchaseOrderLine.qty_ordered,
                PurchaseOrderLine.qty_received,
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(
                PurchaseOrderLine.product_id.in_(list(wanted)),
                PurchaseOrderLine.line_status == "open",
                PurchaseOrder.po_number.notlike("SPO-%"),
            )
            .all()
        )
        open_products: set = set()
        for line_id, product_id, qty_ordered, qty_received in lines:
            remaining = _dec(qty_ordered) - _dec(qty_received) - tagged.get(line_id, _ZERO)
            if remaining > _ZERO:
                open_products.add(str(product_id))
        return open_products

    def _tagged_by_po_line(self) -> Dict[str, Decimal]:
        """What every currently PLACED row already claims, per PO line - the netting
        that stops two rows tagging the same purchase-order quantity."""
        rows = (
            self.db.query(OrderInquiryRow.po_line_id, func.sum(OrderInquiryRow.qty))
            .filter(
                OrderInquiryRow.state == INQUIRY_PLACED,
                OrderInquiryRow.po_line_id.isnot(None),
            )
            .group_by(OrderInquiryRow.po_line_id)
            .all()
        )
        return {po_line_id: _dec(qty) for po_line_id, qty in rows}

    def _placed_claims_by_po_line(
        self, po_line_ids: Sequence[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Every OTHER row already tagged onto these lines - the nested table a candidate's
        expand shows (section G, the row's own expand). Read straight off the placed rows
        themselves: the tag IS the evidence."""
        if not po_line_ids:
            return {}
        rows = (
            self.db.query(OrderInquiryRow, ProjectSalesOrder)
            .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == OrderInquiry.project_sales_order_id,
            )
            .filter(
                OrderInquiryRow.po_line_id.in_(list(po_line_ids)),
                OrderInquiryRow.state == INQUIRY_PLACED,
            )
            .order_by(OrderInquiryRow.actioned_at.asc())
            .all()
        )
        out: Dict[str, List[Dict[str, Any]]] = {}
        for row, order in rows:
            out.setdefault(row.po_line_id, []).append(
                {
                    "so_number": order.autocount_doc_no or order.provisional_ref,
                    "item_code": row.item_code,
                    "qty": _qty_str(_dec(row.qty)),
                    "placed_date": row.actioned_at,
                }
            )
        return out

    def _claim_identity(
        self, row: OrderInquiryRow
    ) -> Tuple[str, Optional[str], Optional[str]]:
        """The (so_number, item_code, core so_line_id) the audit claim is written and
        matched on - the same identity `order_link_service.resolve()` already reads."""
        inquiry = (
            self.db.query(OrderInquiry).filter(OrderInquiry.id == row.order_inquiry_id).first()
        )
        order = (
            self.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id == inquiry.project_sales_order_id)
            .first()
            if inquiry is not None
            else None
        )
        so_number = (
            (order.autocount_doc_no or order.provisional_ref)
            if order is not None
            else str(row.order_inquiry_id)
        )
        core_line_id = None
        if row.so_line_id:
            line = (
                self.db.query(ProjectSalesOrderLine.core_sales_order_line_id)
                .filter(ProjectSalesOrderLine.id == row.so_line_id)
                .first()
            )
            core_line_id = line[0] if line else None
        return so_number, row.item_code, core_line_id

    # ---------------------------------------------------------------- export

    def export_xlsx(
        self,
        project_id: str,
        *,
        query: Optional[str] = None,
        verb: Optional[Sequence[str]] = None,
        state: Optional[Sequence[str]] = None,
        pso_id: Optional[str] = None,
    ) -> Tuple[str, bytes]:
        """The same rows, as the spreadsheet purchasing already reads (AC-I5).

        Generated on demand rather than stored, for the same reason the AutoCount import
        file is: a stored file goes stale the moment an amendment publishes, and a stale
        instruction is exactly what this slice exists to stop being emailed around.
        """
        import openpyxl

        rows = self.all_rows(project_id, query=query, verb=verb, state=state, pso_id=pso_id)
        serialized = self.serialize_rows(rows)

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = EXPORT_SHEET
        sheet.append([EXPORT_TITLE])
        sheet.append(list(EXPORT_HEADINGS))
        for row in serialized:
            sheet.append(
                [
                    self._as_naive(row.get("so_date")),
                    row.get("sales_order_ref") or "",
                    row.get("item_code") or "",
                    float(_dec(row.get("qty"))),
                    row.get("delivery_date"),
                    row.get("project_customer") or "",
                    # Empty rather than a guess when no allocation is confirmed.
                    row.get("stock_location") or "",
                    row.get("remark") or "",
                ]
            )
        buffer = io.BytesIO()
        workbook.save(buffer)
        project = self.db.query(Project).filter(Project.id == project_id).first()
        stem = (project.project_code if project else "project") or "project"
        filename = f"order-inquiry-{stem}-{date.today().isoformat()}.xlsx"
        return filename, buffer.getvalue()

    def _as_naive(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        return value

    # --------------------------------------------------------------- helpers

    def _order_or_404(self, pso_id: str) -> ProjectSalesOrder:
        order = (
            self.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.id == pso_id).first()
        )
        if order is None:
            raise AppException(
                status_code=404, message="Sales order not found.", code="so_not_found"
            )
        return order

    def _lines_of(self, pso_id: str) -> List[ProjectSalesOrderLine]:
        return (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == pso_id)
            .order_by(ProjectSalesOrderLine.line_no.asc())
            .all()
        )

    def _line_or_none(self, line_id: Optional[str]) -> Optional[ProjectSalesOrderLine]:
        if not line_id:
            return None
        return (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.id == line_id)
            .first()
        )

    def _product_code(self, product_id: Optional[str]) -> str:
        if not product_id:
            return ""
        row = self.db.query(Product.product_code).filter(Product.id == product_id).first()
        return row[0] if row else ""


def confirmed_unplaced_buy_rows(
    db: Session,
    *,
    product_id: Optional[str] = None,
    warehouse_id: Optional[str] = None,
) -> List[OrderInquiryRow]:
    """Confirmed, still-unplaced Project Buy - the one thing SCM reads (AC-D04).

    Counts the current `raised` ORDER rows of ACTIVE decisions DIRECTLY. No re-netting
    against pre-order or inbound pools, and no subtracting customer deliveries a second
    time: CS already decided what still has to be bought, and repeating that arithmetic
    downstream is how the same requirement gets bought twice or vanishes entirely.

    The join to core stock facts runs through
    `projects.sales_order_lines.core_sales_order_line_id` (front planning section 4),
    never through a reference, a document number or an item code.
    """
    from app.models.project_so import DECISION_ACTIVE, SOSupplyDecision

    query = (
        db.query(OrderInquiryRow)
        .join(
            SOSupplyDecision, SOSupplyDecision.id == OrderInquiryRow.supply_decision_id
        )
        .join(
            ProjectSalesOrderLine,
            ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id,
        )
        .join(
            SalesOrderLine,
            SalesOrderLine.id == ProjectSalesOrderLine.core_sales_order_line_id,
        )
        .filter(
            SOSupplyDecision.state == DECISION_ACTIVE,
            OrderInquiryRow.verb == IV_ORDER,
            OrderInquiryRow.state == INQUIRY_RAISED,
        )
    )
    if product_id:
        query = query.filter(SalesOrderLine.product_id == product_id)
    if warehouse_id:
        query = query.filter(SalesOrderLine.warehouse_id == warehouse_id)
    return query.all()
