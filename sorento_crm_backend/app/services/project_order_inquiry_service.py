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
from app.models.scm import OrderLinkClaim
from app.models.project_so import (
    ACK_ACKNOWLEDGEABLE,
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_LINKABLE,
    ACK_REJECTED,
    AMENDMENT_PUBLISHED,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_LINK_STATES,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ADVANCE,
    IV_ALREADY_INBOUND,
    IV_CANCEL_BALANCE,
    IV_CHANGE_SO,
    IV_DELAY,
    IV_ORDER,
    IV_ORDER_BACK,
    IV_PRE_ORDERED,
    IV_RESERVE_AND_ORDER,
    SO_STATUS_AMENDED,
    SO_STATUS_PUBLISHED,
    OrderInquiry,
    OrderInquiryLink,
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
from app.services.scm import order_link_service, priority, spo_supply
from app.services.scm.supply_assignment import (
    KIND_PO as SA_KIND_PO,
    KIND_SPO as SA_KIND_SPO,
    parse_supply_key,
)
from app.services.scm.group_netting import (
    GroupNetting,
    group_of_warehouse_code,
    netting_for_products,
)
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

#: How many purchase orders `relink_to_matching_lines` walks per pass. A purchase-history
#: upload names thousands of documents in one call, and one `IN` list that long is a bad
#: plan and, on some drivers, a refused statement.
_RELINK_BATCH = 200

#: The states pre-seeded at zero on the header strip. `placed` (section G) is
#: deliberately NOT one of them - `summary()` adds it to the dict dynamically the moment a
#: placed row actually exists, so a project with none yet keeps reporting the exact four
#: keys this screen has always reported.
INQUIRY_STATES = (INQUIRY_RAISED, INQUIRY_ACTIONED, INQUIRY_CANCELLED)

# The verbs whose rows claim part of a covering pool, and so have to be counted before
# the next publish nets against the same pool again.
_COVERING_VERBS = (IV_PRE_ORDERED, IV_ALREADY_INBOUND)

# Only a row that still costs money and is not yet covered can be LINKED to a document.
# `RESERVE_AND_ORDER` is buying work exactly like `ORDER` (`BUYING_VERBS` on the frontend
# groups them the same way); the rest are either informational or already closed off.
#
# `ORDER_BACK` joined the set in section 3.I. It was kept off it while a link meant a
# purchase order and nothing else - an order back is a shortfall against something already
# ORDERED, so pointing it at a fresh purchase order said the wrong thing. Now that a link
# may name an `spo_allocations` row (part 2 section 4b) that objection is answered: an
# order back is exactly the row that should be able to name the shipping order it is owed
# against, and it is the ONLY verb allowed to.
_LINKABLE_VERBS = (IV_ORDER, IV_RESERVE_AND_ORDER, IV_ORDER_BACK)
#: The verbs whose links may name an SPO allocation. EVERY linkable verb since R5
#: (`PLAN-scm-oi-draft-links.md`, captain 27 Aug 2026): "SPO link is always one, always SPO
#: first then PO". It was the order back alone while an SPO was read as the document a
#: shortfall is owed against; the captain's reading is simpler and is the one that matches
#: the book - an open shipping-order allocation is stock already bought and on its way, so
#: an ORDER should be answered by it before a new purchase order is dealt out. The sort key
#: already put an SPO ahead of a PO, so widening the set is the whole change.
_SPO_LINKABLE_VERBS = _LINKABLE_VERBS
#: The old name, for the readers that have not been renamed yet. Same tuple.
_PLACEABLE_VERBS = _LINKABLE_VERBS

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
    IV_ORDER_BACK: "ORDER BACK",
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


#: The location tiers a link candidate is ranked by (Q5, ruled 25 August 2026). NEVER a
#: filter: "candidate lines are ranked by location fit, never filtered out", because a
#: purchase order that lands at the pool still covers a line standing at BRW-IB - it just
#: has to be moved, and the tier is what tells the buyer which split to key into AutoCount.
TIER_SAME_LOCATION = 1
TIER_SAME_GROUP = 2
TIER_POOL = 3
TIER_SIBLING = 4
TIER_ELSEWHERE = 5


def _also_cited(note: Optional[str]) -> List[str]:
    """The EXTRA documents a form remark named, read back off the row's note.

    `order_inquiry_rows` has one `cited_document` column and a remark routinely names two,
    so the rest are written behind a fixed prefix
    (`project_order_inquiry_import_service.ALSO_CITED_PREFIX`) and read back here.

    ONLY that segment is parsed, never the whole note. The note also carries the cascade's
    own "Linked to 202607-S0031 (...)" stamp and the relocation a book re-upload wrote, and
    reading a document out of those would make an already-linked row cite the document it is
    already sitting on - pinning the walk to its own past, which is the exact trap
    `cited_document` was given its own column to avoid.

    Uses the READER's document-number pattern rather than a second copy of it, so the two
    cannot come to disagree about what a document number looks like.
    """
    from app.services.project_order_inquiry_import_service import ALSO_CITED_PREFIX
    from app.services.project_order_inquiry_reader import _PO_NUMBER

    text_value = str(note or "")
    at = text_value.find(ALSO_CITED_PREFIX)
    if at < 0:
        return []
    segment = text_value[at + len(ALSO_CITED_PREFIX):].split(";")[0]
    return [str(found).strip().upper() for found in _PO_NUMBER.findall(segment)]


def link_location_tier(
    row_location: Optional[str],
    candidate_location: Optional[str],
    pool_codes: set,
) -> Tuple[int, int]:
    """How well a document line's location fits the row's own, as `(tier, sub-rank)`.

    For a row at `BRW-IB`: `BRW-IB` is tier 1; `DC1-IB` / `MWH-IB` (the same ownership
    group at another site) tier 2; a POOL - `BRW` first, then the others - tier 3; a
    sibling at the same site such as `BRW-BB` tier 4; anything else tier 5.

    The sub-rank exists for tier 3 alone and orders the row's OWN site pool ahead of the
    others, which is the "(3) the site pool (BRW, then the other pools)" of the ruling. It
    is a second element rather than a fourth tier so the tier a person reads stays the four
    the plan names.

    Whether a code is a POOL is decided by the FK - the set of warehouses that are some
    location's `pool_warehouse_id` - not by the code's shape. Every pool on the live book
    happens to be a plain site code with no hyphen, but that is a naming convention the
    data does not enforce, and `_pool_codes` reads the same authority the ladder does.

    A row that names NO location can be ranked by nothing, so every candidate is tier 5 and
    the dates decide - which is honest, rather than pretending a fit nobody stated.
    """
    if not row_location or not candidate_location:
        return TIER_ELSEWHERE, 0
    own = str(row_location).strip().upper()
    other = str(candidate_location).strip().upper()
    if own == other:
        return TIER_SAME_LOCATION, 0
    own_site, _, own_group = own.partition("-")
    other_site, _, other_group = other.partition("-")
    if own_group and other_group and own_group == other_group:
        return TIER_SAME_GROUP, 0
    if other in pool_codes:
        return TIER_POOL, 0 if other == own_site else 1
    if other_site and other_site == own_site:
        return TIER_SIBLING, 0
    return TIER_ELSEWHERE, 0


#: How a caller says WHICH horizon it means (S1, `PLAN-scm-oi-handshake.md` section 11).
#: A date lives in `link_up_to`; this field never carries one, so "no horizon" is never a
#: magic string inside a date field.
LINK_HORIZON_DATE = "date"
LINK_HORIZON_PLAN = "plan"
LINK_HORIZON_NONE = "none"


class ProjectOrderInquiryService:
    """Derives, serves, exports and closes off what purchasing is told to do."""

    def __init__(self, db: Session):
        self.db = db
        # Which warehouses are somebody's pool, read once per service instance: the link
        # tier asks it for every candidate of every row, and it does not change inside one
        # request.
        self._pool_codes_cache: Optional[set] = None
        # What every link already claims, per target. `auto_place_for_products` asks for
        # it once per ROW through `_candidates_for_row`, which on a full pass is two
        # aggregate queries per row over the whole link table. Cached here and dropped by
        # `_invalidate_link_cache` on every write, so the cascade cannot read a total it
        # has already changed.
        self._linked_by_target_cache: Optional[Tuple[Dict[str, Decimal], Dict[str, Decimal]]] = None
        # Ladder v4's availability reader (`app.services.scm.group_netting`), over the
        # products this instance has been asked about. A candidate walk needs to know what
        # the group it would link into already owes, and a listing asks the same question
        # of fifty products at once.
        self._netting_value: Optional[GroupNetting] = None
        self._netted_products: set = set()
        # Which ownership groups hold an ACKNOWLEDGED, still-unlinked row of a product,
        # and WHICH rows those are - the deficit exemption's evidence (B1, code review
        # 27 Aug 2026). Five uncached queries per product, and the cascade asks it once
        # per row, so it is answered per product and remembered for the instance.
        self._awaiting_link_cache: Dict[str, Dict[str, set]] = {}

    # ------------------------------------------------------------- derivation

    def refresh_for_decision(
        self,
        order: ProjectSalesOrder,
        decision: Any,
        buy_lines: Sequence[Dict[str, Any]],
        *,
        actor_user_id: Optional[str] = None,
        borrow_shortfalls: Sequence[Dict[str, Any]] = (),
        settle_in_place_line_ids: Sequence[str] = (),
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

        `settle_in_place_line_ids` names the lines a PLANNING CHANGE is applying (part 3,
        AC-P3-5), and on those the supersede-and-re-raise above is the wrong shape: the
        book moved the SAME instruction, so the row is UPDATED - same id, new quantity,
        new date, every link kept, the previous value on its note - and no second raised
        row is created for a line that already has one. `_settle_row_in_place` holds the
        rule, including the over-cover unlink (AC-P3-8) that replaces the CANCEL_BALANCE
        exception for a drop the row can simply absorb. Only where the line has exactly
        ONE still-owed row: where it has two, this build has no way to say which of them
        the book moved, and inventing an answer is worse than the supersede it already
        does.
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
        settle_in_place = {str(line_id) for line_id in (settle_in_place_line_ids or [])}
        # Which lines were ACTUALLY settled in place, not which were offered: the caller
        # decides whether to raise a separate DELAY / ADVANCE row on that answer, and
        # `_settle_row_in_place` declines a line whose rows it cannot read as one.
        settled_in_place: List[str] = []
        for entry in buy_lines:
            line = entry["line"]
            need = _dec(entry.get("buy_qty"))
            carried = bool(entry.get("carried"))
            # Is THIS line's Buy an order back (part 2 section 4b)? Only then does this
            # loop own the line's `ORDER_BACK` rows; on any other line such a row is a
            # DONOR hole raised by `_raise_borrow_shortfalls`, which supersedes and nets it
            # by its own rule. The two writers never meet on one line - the whole-line rule
            # (AC-L5) makes a line either wholly stock or wholly Buy - and this is what
            # keeps them apart.
            order_back = bool(entry.get("order_back")) and need > _ZERO
            owned_verbs = (
                (IV_ORDER, IV_ORDER_BACK, IV_CANCEL_BALANCE)
                if order_back
                else (IV_ORDER, IV_CANCEL_BALANCE)
            )
            # This sales order's OWN inquiry only. An amendment raises its exception verbs
            # under its own inquiry (`amendment_id`), and cancelling those here would
            # delete an instruction purchasing is still working from.
            rows = (
                self.db.query(OrderInquiryRow)
                .filter(
                    OrderInquiryRow.order_inquiry_id == inquiry.id,
                    OrderInquiryRow.so_line_id == line.id,
                    OrderInquiryRow.verb.in_(owned_verbs),
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
            #
            # A PARTLY LINKED row is the case the links table added, and it is netted
            # HALF: the quantity that sits on a document is real supply and counts, and
            # the remainder is demand this revision is about to restate, so the row is
            # shrunk to what is linked rather than cancelled. Cancelling it would have
            # taken the links down with it; leaving it whole would have counted the
            # unlinked half twice, once here and once on the row raised below.
            #
            # A DRAFT settles in place too, whoever asked for the confirmation (B2 as
            # refined in the CI round, 28 Aug). Since R6 the raise links its own rows, so a
            # row nobody has confirmed reads `placed` or `partly linked` within a second of
            # being raised, and the netting below then read it as quantity purchasing had
            # already bought: a reconfirm carrying a new date changed nothing at all, and a
            # lower quantity raised a CANCEL_BALANCE exception about a purchase nobody had
            # agreed to. Settling answers both - the row takes the new date and the new
            # quantity, keeping the drafts it can still hold and giving the excess back
            # latest-dated first (AC-P3-8's own rule) - and it answers them without
            # cancelling anything, so a draft the planning change has just SHIFTED onto
            # this row stays where the shift put it.
            #
            # `_settle_row_in_place` still declines a line it cannot read as one
            # instruction (two still-owed rows, or a lone placed row carrying no link at
            # all), and those fall through to the netting below exactly as they always
            # did: the drafted rows stand and only the outstanding remainder is raised.
            drafted = [
                row
                for row in rows
                if row.verb in (IV_ORDER, IV_ORDER_BACK)
                and row.state in (INQUIRY_PLACED, INQUIRY_PARTLY_LINKED)
                and row.ack_state != ACK_ACKNOWLEDGED
                and not row.redirected_to_pool
            ]
            asked_to_settle = str(line.id) in settle_in_place
            if (asked_to_settle or drafted) and self._settle_row_in_place(
                inquiry, entry, rows, need, decision
            ):
                # Only what the CALLER asked for is reported back: the planning-change
                # apply reads this list to decide whether to raise a separate DELAY /
                # ADVANCE row, and a line it never named is none of its business.
                if asked_to_settle:
                    settled_in_place.append(str(line.id))
                continue
            # Read BEFORE the loop below cancels anything: what purchasing had already
            # taken on for this line, off the rows that are still LIVE. Taken afterwards it
            # would read the rows this loop has just cancelled, which is every superseded
            # row this line ever carried, so a line whose acknowledgement had long since
            # been superseded would keep promoting its replacements to `changed` forever.
            prior_ack = self._live_handshake(rows)
            linked = self._linked_qty_by_row([row.id for row in rows])
            placed = _ZERO
            for row in rows:
                if row.state == INQUIRY_RAISED:
                    row.state = INQUIRY_CANCELLED
                    row.note = f"Superseded by revision {decision.revision_no}"
                    continue
                if row.verb not in owned_verbs or row.verb == IV_CANCEL_BALANCE:
                    continue
                # A planning change already REDIRECTED this row to replenish the pool it
                # drew on (`planning_change_service._apply_placed_redirect`, the captain's
                # ruling 21 Aug 2026) - it is still real placed quantity, just not this
                # line's anymore, so it must not net off this line's need a second time or
                # the new Buy would be silently short.
                if row.redirected_to_pool:
                    continue
                # A DRAFT that reached HERE is one the settle above declined - a line
                # carrying two still-owed rows, or a lone placed row with no link behind it
                # (B2 as refined in the CI round, 28 Aug). There is no way to say which of
                # two rows the book moved, and no draft to give back on a row that holds
                # none, so the old path stands: the drafted rows are netted and left
                # exactly where they are, and only the outstanding remainder is raised -
                # which the raise-time cascade drafts in its turn.
                if row.state == INQUIRY_ACTIONED:
                    # `mark_rows` is the only writer of this state and it carries no
                    # links, so the row's own quantity is what purchasing dealt with.
                    placed += _dec(row.qty)
                elif row.state == INQUIRY_PLACED:
                    placed += _dec(row.qty)
                elif row.state == INQUIRY_PARTLY_LINKED:
                    covered = linked.get(row.id, _ZERO)
                    placed += covered
                    row.qty = covered
                    # Through the one writer, not by hand: the row's derived display
                    # (`po_ref` / `po_line_id` / `spo_ref`) is restated with the state, and
                    # setting `placed` here alone would have left them saying whatever the
                    # last link change happened to leave.
                    self._refresh_link_state([row])
                    row.note = (
                        f"{row.note}; Remainder superseded by revision "
                        f"{decision.revision_no}"
                        if row.note
                        else f"Remainder superseded by revision {decision.revision_no}"
                    )

            # Did purchasing already take this line's instruction on, and is this
            # confirmation actually changing it?
            #
            # A CARRIED line is not a change at all (13.4): this confirmation named other
            # lines, and this one's still-raised row is moved under the new revision by a
            # cancel and a re-raise purely so `confirmed_unplaced_buy_rows` keeps finding
            # it. Promoting it to `changed` there told the buyer, on every confirm of any
            # OTHER line of the same order, that a row they had acknowledged had moved -
            # with no Was and no Now to show for it, because nothing had. So the carried
            # row inherits the handshake verbatim, stamps included.
            #
            # A NAMED line IS a change (AC-H9): a supersede is the same line moving under
            # them, and raising the replacement plain `awaiting` would hide from the buyer
            # that this is one they had already read. The acknowledgement stamps travel
            # with it, so the cell can still say who had taken it on.
            ack_state, acknowledged_by, acknowledged_at, changed_at = self._handshake_for_raise(
                prior_ack, carried=carried
            )
            outstanding = need - placed
            if outstanding > _ZERO:
                # An ORDER BACK is the same Buy said differently: the quantity is owed
                # against something already ordered or already shipped (part 2 section
                # 4b). CS marks it in Amend, optionally naming the document, and the two
                # facts travel to the row: the verb decides that an SPO allocation is a
                # legal link target, and `cited_document` is what the walk tries first.
                order_back = bool(entry.get("order_back"))
                self.db.add(
                    OrderInquiryRow(
                        company_id=order.company_id,
                        order_inquiry_id=inquiry.id,
                        so_line_id=line.id,
                        item_code=entry.get("item_code") or None,
                        qty=outstanding,
                        delivery_date=entry.get("required_date"),
                        stock_location=entry.get("stock_location"),
                        verb=IV_ORDER_BACK if order_back else IV_ORDER,
                        cited_document=(
                            entry.get("cited_document") if order_back else None
                        ),
                        # No netting on this path, so nothing covers this row: the coverage
                        # decision was CS's and is recorded on the supply decision.
                        covered_by=None,
                        supply_decision_id=decision.id,
                        state=INQUIRY_RAISED,
                        ack_state=ack_state,
                        acknowledged_by=acknowledged_by,
                        acknowledged_at=acknowledged_at,
                        changed_at=changed_at,
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
            order,
            inquiry,
            decision,
            borrow_shortfalls,
            # The lines whose ORDER BACK rows the loop above already owns: a Buy CS
            # marked "Order back". NOT every confirmed line - a line with no Buy at all
            # appears in `buy_lines` too, and excluding it would have stopped the donor's
            # own hole being netted against what purchasing had already placed.
            buy_line_ids={
                str(entry["line"].id)
                for entry in buy_lines
                if entry.get("line")
                and entry.get("order_back")
                and _dec(entry.get("buy_qty")) > _ZERO
            },
        )
        created += shortfalls
        raised += shortfalls
        self.db.flush()
        if raised and self.task_for(inquiry.id) is None:
            self._hand_to_purchasing(order, inquiry, raised)
        return {
            "inquiry": inquiry,
            "created": created,
            "exceptions": exceptions,
            "settled_in_place": settled_in_place,
        }

    @staticmethod
    def _live_handshake(
        rows: Sequence[OrderInquiryRow],
    ) -> Optional[OrderInquiryRow]:
        """The row of this line purchasing has actually taken on, if there is one.

        LIVE rows only - raised, partly linked, placed. A cancelled row is a superseded
        instruction and an actioned one was answered elsewhere; neither is what purchasing
        is holding now, so neither may decide what the next row says about them. Rejected
        is deliberately not a match either: a refusal sends the line back to CS, and what
        CS raises next is a fresh instruction nobody has read (AC-H6).
        """
        for row in rows:
            if row.state not in (
                INQUIRY_RAISED,
                INQUIRY_PARTLY_LINKED,
                INQUIRY_PLACED,
            ):
                continue
            if row.ack_state in (ACK_ACKNOWLEDGED, ACK_CHANGED):
                return row
        return None

    @staticmethod
    def _handshake_for_raise(
        prior: Optional[OrderInquiryRow], *, carried: bool
    ) -> Tuple[str, Optional[str], Optional[datetime], Optional[datetime]]:
        """What the row about to be raised says about the handshake.

        Three answers, and the middle one is the whole point: nobody had read this line
        (`awaiting`, no stamps); this confirmation is only CARRYING the line, so its row
        says exactly what the row it replaces said; this confirmation is CHANGING a line
        purchasing had read, so the replacement reads `changed` from today.
        """
        if prior is None:
            return ACK_AWAITING, None, None, None
        if carried:
            return (
                prior.ack_state,
                prior.acknowledged_by,
                prior.acknowledged_at,
                prior.changed_at,
            )
        return (
            ACK_CHANGED,
            prior.acknowledged_by,
            prior.acknowledged_at,
            datetime.utcnow(),
        )

    def _settle_row_in_place(
        self,
        inquiry: OrderInquiry,
        entry: Dict[str, Any],
        rows: Sequence[OrderInquiryRow],
        need: Decimal,
        decision: Any,
    ) -> bool:
        """A planning change moved THIS line: update its one row rather than replace it.

        Part 3's own rule (AC-P3-5): the sales order book moved a line the plan already
        told purchasing about, so what changed is the instruction's quantity and date -
        not which instruction it is. Cancelling and re-raising would have handed the row's
        links back with nothing said (a raised row carries none, but a linked one carries
        everything the buyer has already arranged) and left the line reading as two
        instructions on a screen whose whole point is one per line.

        Three things this writes and the supersede path does not:

        * the PREVIOUS value, in `previous_qty` / `previous_delivery_date` AND as prose on
          the row's own note ("Was 10 on 2026-08-25"). A DELAY that does not say what it
          was is not actionable, and the same is true of a quantity. The columns are what
          the Was / Now table reads; the note is for a person, and is never parsed back;
        * the OVER-COVER unlink (AC-P3-8): more linked than the new quantity gives the
          excess back, LATEST-dated document first, because the earliest arrival is the one
          the line still needs. No `CANCEL_BALANCE` exception is written for a drop the row
          absorbs in place - the exception exists for quantity already bought that this
          line no longer wants, and the unlink is exactly how it stops wanting it;
        * a need of nothing cancels the row outright, which is the honest end of a line the
          book reduced to zero.

        Returns False, changing nothing, when the line has no still-owed row or has more
        than one: with two the caller's supersede is the only answer that does not guess.
        It also declines a lone PLACED (or actioned) row that carries NO link, and that is
        the SO349754 WESERP10B shape: purchasing put 5 on a purchase order through a path
        that writes no link row, so there is nothing here to keep whole - restating the
        row at the new need would silently demote real placed supply back to raised and
        lose the netting that says 5 of it is already bought. The caller's own path nets
        `placed` off the need and raises only the difference, which is the right answer.
        """
        live = [
            row
            for row in rows
            if row.state
            in (INQUIRY_RAISED, INQUIRY_PARTLY_LINKED, INQUIRY_PLACED)
            and row.verb in (IV_ORDER, IV_ORDER_BACK)
            and not row.redirected_to_pool
        ]
        if len(live) != 1:
            return False
        row = live[0]
        if row.state in (INQUIRY_PLACED, INQUIRY_ACTIONED) and not self._links_of(row.id):
            return False
        previous_qty = _dec(row.qty)
        previous_date = row.delivery_date
        moved = (
            f"Was {_qty_str(previous_qty)} on {previous_date.isoformat()}"
            if previous_date
            else f"Was {_qty_str(previous_qty)}, no previous delivery date"
        )

        if need <= _ZERO:
            # Nothing is bought for this line any more - the book reduced it to nothing, or
            # the fresh plan meets it from stock. Its placements go back, so the document is
            # free for whoever needs it next rather than held against a withdrawn
            # instruction; `_remove_links` writes its own "Unlinked from ..." stamp.
            links = self._links_of(row.id)
            if links:
                self._remove_links(row, links)
            row.state = INQUIRY_CANCELLED
            row.note = (
                f"{row.note}; {moved}; the book left nothing to buy"
                if row.note
                else f"{moved}; the book left nothing to buy"
            )
            self._retire_settled_cancel_balance(rows, decision)
            self.db.flush()
            return True

        links = self._links_of(row.id)
        linked = sum((_dec(link.qty) for link in links), _ZERO)
        if linked > need:
            # Latest arrival first: the row keeps the cover that lands soonest.
            by_arrival = sorted(
                links,
                key=lambda link: (
                    self._link_expected_date(link) or date.max,
                    link.linked_at or datetime.min,
                ),
                reverse=True,
            )
            giving_back: List[OrderInquiryLink] = []
            for link in by_arrival:
                excess = linked - need
                if excess <= _ZERO:
                    break
                qty = _dec(link.qty)
                if excess >= qty:
                    giving_back.append(link)
                    linked -= qty
                    continue
                # Only the EXCESS goes back, not the whole placement: the buyer arranged
                # that quantity on that document and the line still wants most of it.
                link.qty = qty - excess
                linked = need
            if giving_back:
                self._remove_links(row, giving_back)

        row.qty = need
        # Only when the confirmation states one. A line whose new composition carries no
        # required date must not have the date purchasing is working to erased.
        if entry.get("required_date"):
            row.delivery_date = entry.get("required_date")
        if entry.get("stock_location"):
            row.stock_location = entry.get("stock_location")
        row.supply_decision_id = decision.id
        row.order_inquiry_id = inquiry.id
        row.note = f"{row.note}; {moved}" if row.note else moved
        # The same two facts as figures, for the Was / Now table (the note above is the
        # sentence a person reads, and stays one). Written on every settle, not only on a
        # row purchasing has read: the question they answer is "what did this row say
        # before", which has the same answer either way.
        row.previous_qty = previous_qty
        row.previous_delivery_date = previous_date
        # The handshake, if there is one to speak of (`PLAN-scm-oi-handshake.md` section
        # 3). A row purchasing had already taken on has just been amended under them, so it
        # reads CHANGED until they acknowledge it again - with its links kept, because the
        # buyer's arrangements are still good for most of the new quantity. A row still
        # AWAITING is left alone and says nothing: CS is free to change what nobody has
        # read, and marking it would ask purchasing to re-read something they never read.
        if row.ack_state in (ACK_ACKNOWLEDGED, ACK_CHANGED):
            row.ack_state = ACK_CHANGED
            row.changed_at = datetime.utcnow()
        self._retire_settled_cancel_balance(rows, decision)
        self._refresh_link_state([row])
        self.db.flush()
        return True

    def _retire_settled_cancel_balance(
        self, rows: Sequence[OrderInquiryRow], decision: Any
    ) -> None:
        """A settle answers the exception an earlier revision raised for the same line.

        A still-raised `CANCEL_BALANCE` says "placed X, new need Y" against a quantity
        this settle has just restated in place - so left standing it asks purchasing to
        answer a question about a figure that no longer exists, beside the very row that
        now carries the true one. The supersede path cancels it on every reconfirm
        (`refresh_for_decision`, the loop below); the settle path skipped it because it
        only ever looks at the row it is updating.
        """
        for row in rows:
            if row.verb == IV_CANCEL_BALANCE and row.state == INQUIRY_RAISED:
                row.state = INQUIRY_CANCELLED
                row.note = f"Superseded by revision {decision.revision_no}"

    def _link_expected_date(self, link: OrderInquiryLink):
        """When the document behind this link arrives, whichever family it names."""
        if link.spo_allocation_id:
            return (
                self.db.query(SPOAllocation.expected_date)
                .filter(SPOAllocation.id == link.spo_allocation_id)
                .scalar()
            )
        if link.po_line_id:
            return (
                self.db.query(PurchaseOrderLine.expected_date)
                .filter(PurchaseOrderLine.id == link.po_line_id)
                .scalar()
            )
        return None

    def _raise_borrow_shortfalls(
        self,
        order: ProjectSalesOrder,
        inquiry: OrderInquiry,
        decision: Any,
        shortfalls: Sequence[Dict[str, Any]],
        buy_line_ids: Optional[set] = None,
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
        # `ORDER_BACK` is written by TWO paths since part 2 section 4b: this one, for the
        # hole a borrow left at the donor's location, and the Buy line CS marked "Order
        # back" in Amend. The two never meet on one sales-order LINE - the whole-line rule
        # (AC-L5) makes a line either wholly stock or wholly Buy - so the line is what
        # tells them apart, and this method leaves the Buy-line rows to
        # `refresh_for_decision`, which supersedes and nets them exactly as it does an
        # ORDER. Without the exclusion every board order-back would be cancelled on the
        # next confirm and never re-raised.
        rows = [
            row
            for row in self.db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.order_inquiry_id == inquiry.id,
                OrderInquiryRow.verb == IV_ORDER_BACK,
            )
            .all()
            if not (buy_line_ids and str(row.so_line_id) in buy_line_ids)
            # A ROW THAT NAMES ITS COVER IS NOT A HOLE (S4). Ladder v7.1 step 3 raises an
            # ORDER_BACK on the ASKER's own line carrying `covered_by` - the document that
            # already covers the quantity, which is exactly what this column has always
            # meant - and the placement link hangs off it. Netted here, that row would have
            # cancelled a real donor hole at the same (item, location) as if purchasing had
            # already bought it. The two live on the same line and only this tells them
            # apart: the hole names no cover, because nothing covers it yet.
            and not (row.covered_by or "").strip()
        ]
        # A PARTLY LINKED row is netted HALF, exactly as an ORDER row is one method up:
        # the quantity sitting on a document is real supply and counts against the hole,
        # and the remainder is a hole this revision is about to restate, so the row is
        # SHRUNK to what is linked rather than cancelled. Cancelling it would have taken
        # its links down with it; leaving it whole would have counted the unlinked half
        # twice, once here and once on the row raised below; and re-raising the FULL hole
        # on top of it - which is what a plain `raised` test does to it - would have told
        # purchasing to buy the covered part a second time.
        linked = self._linked_qty_by_row([row.id for row in rows])
        placed: Dict[Tuple[Optional[str], Optional[str]], Decimal] = {}
        for row in rows:
            key = (row.item_code or None, row.stock_location or None)
            if row.state == INQUIRY_RAISED:
                row.state = INQUIRY_CANCELLED
                row.note = f"Superseded by revision {decision.revision_no}"
            elif row.state == INQUIRY_PARTLY_LINKED:
                covered = linked.get(row.id, _ZERO)
                placed[key] = placed.get(key, _ZERO) + covered
                row.qty = covered
                row.state = INQUIRY_PLACED
                row.note = (
                    f"{row.note}; Remainder superseded by revision {decision.revision_no}"
                    if row.note
                    else f"Remainder superseded by revision {decision.revision_no}"
                )
            # `placed` (section G) is a real, distinct state from `actioned` and a
            # shortfall row purchasing already dealt with must net off just as an actioned
            # one does.
            elif row.state in (INQUIRY_ACTIONED, INQUIRY_PLACED):
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
                    verb=IV_ORDER_BACK,
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

        A DRAFTED row counts as still-raised here (B3, review round 28 Aug). Since R6 the
        raise links its own rows, so a row nobody has confirmed reads `placed` or `partly
        linked` within a second of being raised - and a filter that only knew `raised` left
        every one of them alive on a line CS had taken back out of the decision, holding
        purchase-order quantity for an instruction that no longer exists. The links come
        down with the row, because they were drafts and the document is owed to whoever
        needs it next. A CONFIRMED row is left exactly where it is: purchasing bought it.
        """
        covered = {str(entry["line"].id) for entry in buy_lines}
        stale = (
            self.db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.order_inquiry_id == inquiry.id,
                OrderInquiryRow.state.in_(
                    (INQUIRY_RAISED, INQUIRY_PARTLY_LINKED, INQUIRY_PLACED)
                ),
                OrderInquiryRow.verb.in_((IV_ORDER, IV_CANCEL_BALANCE)),
                OrderInquiryRow.supply_decision_id.isnot(None),
                OrderInquiryRow.supply_decision_id != decision.id,
            )
            .all()
        )
        stamp = f"Superseded by revision {decision.revision_no}"
        for row in stale:
            if str(row.so_line_id) in covered:
                continue
            if row.state == INQUIRY_RAISED:
                row.state = INQUIRY_CANCELLED
                row.note = stamp
                continue
            if row.ack_state == ACK_ACKNOWLEDGED:
                continue
            # The draft's own history is kept rather than overwritten: which document it
            # was holding, and that the retirement is what took it back.
            self._unplace_drafts([row], trigger="retired")
            row.state = INQUIRY_CANCELLED
            row.note = f"{row.note}; {stamp}" if row.note else stamp

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
        """Open SPO lines that have not landed: stock already on the water.

        Outer-joined to the shipment since migration 420: an SPO document exists before
        anybody books a container for it, and an inner join here counted only the ones that
        had one. A row with no shipment offers its own `expected_date` as the arrival, and a
        CLOSED line offers nothing - history is written closed for exactly that reason.

        `spo_supply.open_incoming_clauses` is the shared rule. A promise whose date has
        passed is still a pool (captain, 26 Aug: trust the book) - the goods are owed until
        the book says they arrived - so what a past date changes is the wording elsewhere,
        not whether this pool exists.
        """
        rows = (
            self.db.query(
                SPOAllocation.spo_number,
                SPOAllocation.product_id,
                SPOAllocation.allocated_quantity,
                SPOAllocation.quantity_received,
                func.coalesce(
                    InboundShipment.estimated_arrival_date, SPOAllocation.expected_date
                ).label("eta"),
            )
            .outerjoin(
                InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id
            )
            .filter(
                SPOAllocation.product_id.in_(list(product_ids)),
                SPOAllocation.spo_number.isnot(None),
                # Supply we cannot place is cover for nobody: the pool this fills is read
                # per location, so a row naming a location we do not hold counts nowhere,
                # exactly as `on_order_v` treats it.
                SPOAllocation.warehouse_id.isnot(None),
                *spo_supply.open_incoming_clauses(),
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
                    [IV_ORDER, IV_RESERVE_AND_ORDER, IV_ORDER_BACK]
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
        candidates = self.link_candidate_products(set(product_by_row.values()))
        links_by_row = self.links_for_rows([row.id for row in rows])
        linked_by_row = self._linked_qty_by_row([row.id for row in rows])
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
                    "cited_document": row.cited_document,
                    # WHERE the quantity actually sits (AC-I5/AC-I9). `po_ref` above is the
                    # first of these, kept for the older readers that print one number.
                    "links": links_by_row.get(row.id, []),
                    "linked_qty": _qty_str(linked_by_row.get(row.id, _ZERO)),
                    "has_link_candidate": self.has_link_candidate(
                        row.verb, product_by_row.get(row.id), candidates
                    ),
                    "covered_by": row.covered_by,
                    "note": row.note,
                    "state": row.state,
                    "actioned_at": row.actioned_at,
                    "actioned_by_name": names.get(row.actioned_by),
                    "created_at": row.created_at,
                    # The handshake, beside the supply state (AC-H14). Every column on
                    # the wire: `response_model` drops what it has not been declared.
                    "ack_state": row.ack_state,
                    "acknowledged_by_name": names.get(row.acknowledged_by),
                    "acknowledged_at": row.acknowledged_at,
                    "rejected_by_name": names.get(row.rejected_by),
                    "rejected_at": row.rejected_at,
                    "rejected_reason": row.rejected_reason,
                    "changed_at": row.changed_at,
                    # What the row said before the last settle restated it. The Was / Now
                    # table reads these, never the note's own sentence.
                    "previous_qty": (
                        _qty_str(_dec(row.previous_qty))
                        if row.previous_qty is not None
                        else None
                    ),
                    "previous_delivery_date": row.previous_delivery_date,
                }
            )
        return out

    def links_for_rows(self, row_ids: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Every link on these rows, serialized, keyed by row - one query for a page.

        The ONE reader of `projects.order_inquiry_links` for a screen, used by the
        per-project list, the cross-project worklist and the SCM sales-order detail, so the
        three surfaces answer "where is this linked" with one voice (section 3.I: "Same
        data as the worklist and the PO occupancy panel, one reader").

        Everything a person reads comes off the link itself or off the document it names -
        never an id: `document` is denormalised on the link precisely so a purchase order
        line that has since been re-imported cannot make the answer disappear. `po_id`
        addresses the PO popover and is null on an SPO link, because there is no purchase
        order to open.
        """
        wanted = [row_id for row_id in row_ids if row_id]
        if not wanted:
            return {}
        rows = (
            self.db.query(
                OrderInquiryLink,
                OrderInquiryRow.stock_location,
                OrderInquiryRow.delivery_date,
                PurchaseOrder.id,
                PurchaseOrder.po_number,
                PurchaseOrder.issue_date,
                PurchaseOrderLine.expected_date,
                PurchaseOrderLine.source_ref,
                Warehouse.warehouse_code,
                SPOAllocation.spo_number,
                SPOAllocation.spo_line_number,
                SPOAllocation.issue_date,
                SPOAllocation.expected_date,
                SPOAllocation.location_code,
            )
            .join(OrderInquiryRow, OrderInquiryRow.id == OrderInquiryLink.row_id)
            .outerjoin(PurchaseOrderLine, PurchaseOrderLine.id == OrderInquiryLink.po_line_id)
            .outerjoin(
                PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id
            )
            .outerjoin(
                SPOAllocation, SPOAllocation.id == OrderInquiryLink.spo_allocation_id
            )
            .outerjoin(
                Warehouse,
                Warehouse.id
                == func.coalesce(
                    PurchaseOrderLine.warehouse_id, SPOAllocation.warehouse_id
                ),
            )
            .filter(
                OrderInquiryLink.row_id.in_(wanted),
                # A cancelled row's links are history, not an answer to "where does this
                # quantity sit": the quantity is not owed any more. A superseded revision
                # would otherwise keep printing its documents on the SO detail beside the
                # revision that replaced it.
                OrderInquiryRow.state != INQUIRY_CANCELLED,
            )
            .order_by(OrderInquiryLink.linked_at.asc(), OrderInquiryLink.id.asc())
            .all()
        )
        pools = self._pool_codes()
        from app.services.project_service import resolve_user_names

        names = resolve_user_names(
            self.db, [link.linked_by for link, *_rest in rows if link.linked_by]
        )
        out: Dict[str, List[Dict[str, Any]]] = {}
        for (
            link,
            stock_location,
            row_needed_by,
            po_id,
            po_number,
            po_issue_date,
            po_expected_date,
            po_source_ref,
            warehouse_code,
            spo_number,
            spo_line_number,
            spo_issue_date,
            spo_expected_date,
            spo_location_code,
        ) in rows:
            is_spo = link.spo_allocation_id is not None
            location = warehouse_code or (spo_location_code if is_spo else None)
            tier, _sub = link_location_tier(stock_location, location, pools)
            arrives = spo_expected_date if is_spo else po_expected_date
            # AC-P3-7: the document lands after the row needs it. A fact about two dates,
            # derived here rather than stored, so it cannot go stale against either - and
            # never a reason to unlink: the quantity is still on that document, and taking
            # it off would leave the row with nothing rather than with something late.
            late = bool(arrives and row_needed_by and arrives > row_needed_by)
            # HOW late, in whole days (AC-D17). `None` rather than 0 when it is not late,
            # so the column has nothing to print instead of a zero that reads as on time.
            late_days = (arrives - row_needed_by).days if late else None
            out.setdefault(link.row_id, []).append(
                {
                    "id": link.id,
                    "kind": "spo" if is_spo else "po",
                    # The link's own copy first: the document it was made against, even
                    # when the line it named has since been deleted out from under it.
                    "document": link.document or spo_number or po_number,
                    "line_label": self._line_label(
                        spo_line_number if is_spo else po_source_ref
                    ),
                    "qty": _qty_str(_dec(link.qty)),
                    "location": location,
                    "issue_date": spo_issue_date if is_spo else po_issue_date,
                    "expected_date": spo_expected_date if is_spo else po_expected_date,
                    "tier": tier,
                    "late": late,
                    "late_days": late_days,
                    "auto": bool(link.auto),
                    "linked_at": link.linked_at,
                    # WHO linked it, by name. Null on a cascade link, which nobody did.
                    "linked_by_name": names.get(link.linked_by),
                    "po_id": None if is_spo else po_id,
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

        # Every person a row can name, resolved in ONE call: who acted on it, who
        # acknowledged it and who rejected it are three different people and the screen
        # prints all three by name (`PLAN-scm-oi-handshake.md` section 4).
        names = resolve_user_names(
            self.db,
            [
                user_id
                for row in rows
                for user_id in (row.actioned_by, row.acknowledged_by, row.rejected_by)
                if user_id
            ],
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

    # ----------------------------------------------------------- the handshake

    def acknowledge_rows(
        self,
        row_ids: Sequence[str],
        *,
        actor_user_id: str,
        link_up_to: Optional[date] = None,
        link_horizon: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Purchasing takes these instructions on, and the cascade runs for exactly them.

        `PLAN-scm-oi-handshake.md` section 3 (captain, 27 Aug 2026). Two things happen in
        one press and they are one decision: the row becomes purchasing's work, and the
        documents that can cover it are tied to it. Before this the tie happened at CS's
        confirm, which meant a buyer found their own purchase orders already dealt out to
        instructions they had never read.

        Only `awaiting` and `changed` rows may be acknowledged. An already-acknowledged one
        is refused rather than silently re-stamped - the second press would move the time
        and the name onto somebody who only pressed a button twice - and a rejected one is
        refused because taking it back is CS re-deciding the line, not purchasing changing
        its mind about a row that no longer counts.

        The row's SUPPLY state is refused on too, and it is a different question from the
        handshake: a CANCELLED row was called off and an ACTIONED one was answered
        somewhere else, so taking either on is taking on work nobody is doing, and the
        cascade behind the press would link nothing for it anyway. The checkbox already
        refuses them (`orderInquiryAck.isAcknowledgeable`); this is the same rule where it
        cannot be bypassed by a second tab, a replayed request or a future caller.

        `link_up_to` is the LINK HORIZON the cascade half of the press runs under (section
        11): every named row is TAKEN ON whatever its date, and only the linking stops at
        the horizon, because the acknowledgement is the buyer reading the instruction and
        the link is the buyer answering it. `after_horizon` is what the banner reports as
        "N after <date>".
        """
        rows = self._rows_or_404(row_ids)
        gone = [row for row in rows if row.state not in INQUIRY_LINK_STATES]
        if gone:
            raise AppException(
                status_code=422,
                message=(
                    f"{len(gone)} of those rows are no longer open: a cancelled or "
                    "actioned row is nobody's work to take on."
                ),
                code="order_inquiry_row_not_open",
            )
        refused = [row for row in rows if row.ack_state not in ACK_ACKNOWLEDGEABLE]
        if refused:
            raise AppException(
                status_code=422,
                message=(
                    f"{len(refused)} of those rows cannot be acknowledged: a row is "
                    "acknowledged once, and a rejected one goes back to CS."
                ),
                code="order_inquiry_not_acknowledgeable",
            )
        now = datetime.utcnow()
        for row in rows:
            row.ack_state = ACK_ACKNOWLEDGED
            row.acknowledged_by = actor_user_id
            row.acknowledged_at = now
        # FLUSHED before the cascade: the session runs `autoflush=False` the way the
        # application's does, so the pass below would read these rows at their OLD
        # acknowledgement state and link none of them.
        self.db.flush()
        placed = self.auto_place_for_products(
            None,
            actor_user_id=actor_user_id,
            trigger="acknowledge",
            row_ids=[str(row.id) for row in rows],
            link_up_to=link_up_to,
            link_horizon=link_horizon,
        )
        return {
            "acknowledged": len(rows),
            "linked_rows": placed["placed_rows"],
            "links": placed["allocations"],
            "after_horizon": placed["after_horizon"],
            "link_up_to": placed["link_up_to"],
            "link_horizon": placed["link_horizon"],
        }

    def reject_row(
        self, row_id: str, *, reason: str, actor_user_id: str
    ) -> Dict[str, Any]:
        """Purchasing refuses one instruction, with a reason CS reads on the board cell.

        The row leaves netting and the LINE goes back to the board undecided, carrying the
        refusal - `ProjectSupplyService.uncover_lines`, which is `confirm`'s own un-decide
        seam. A rejection that only marked the row would leave the line reading as decided
        and promised while nobody was buying anything for it, which is the exact state the
        board exists to make impossible.

        The reason is required at the schema. It is required again here because a service
        caller (a test, a script) reaches this without one.

        A row WHOLLY on documents may be refused too (`PLAN-scm-oi-draft-links.md` 5.6).
        It could not before, and the rule made sense while a link meant purchasing had
        already bought: "purchasing rejected it" beside a purchase order that exists is a
        sentence CS cannot act on. With DRAFTS the same state means the opposite - a row
        raised a minute ago is fully linked and nobody has agreed to anything - so refusing
        it would have refused most of the page. The links come down FIRST instead, which is
        the truth of a refusal: the quantity goes back to the document for the next row.

        A cancelled or actioned row is still past refusing, for the same reason
        acknowledging one is: nobody is doing it. Refused before anything is written, so
        such a row keeps its state AND gains no revision on its line.
        """
        text_reason = self._reject_reason(reason)
        row = self._row_or_404(row_id)
        self._assert_rejectable(row)
        self._reject_one(row, reason=text_reason, actor_user_id=actor_user_id)
        return self.serialize_rows([row])[0]

    def reject_rows(
        self, row_ids: Sequence[str], *, reason: str, actor_user_id: str
    ) -> Dict[str, Any]:
        """Refuse a BATCH with ONE reason (`PLAN-scm-oi-draft-links.md` 5.6, item 15).

        ALL OR NOTHING: every row is checked before the first is written, so a batch
        holding one row nobody may refuse writes nothing at all. A press that half happened
        leaves the buyer to work out which half from a screen that has already moved on,
        and the dialog asked one question about all of them.

        Every row is STAMPED first and the sales orders are un-decided afterwards, ONE call
        per order carrying every line the batch refused (B4, review round 28 Aug). Row by
        row it could not work: un-decking one line writes a fresh revision of the whole
        order, and that revision cancels and re-raises the other lines' rows - so the
        second refusal stamped a row that had just been superseded while its live
        replacement went on sitting in front of purchasing as if nobody had refused it. One
        revision per order also matches what the buyer did: they pressed once.
        """
        text_reason = self._reject_reason(reason)
        rows = self._rows_or_404(row_ids)
        for row in rows:
            self._assert_rejectable(row)
        for row in rows:
            self._stamp_rejected(row, reason=text_reason, actor_user_id=actor_user_id)
        self._uncover_rejected_lines(rows, actor_user_id=actor_user_id)
        return {
            "rejected": len(rows),
            "results": [{"row_id": str(row.id), "ok": True} for row in rows],
        }

    @staticmethod
    def _reject_reason(reason: str) -> str:
        """The reason, required at the schema and required again here: a service caller (a
        test, a script) reaches this without one."""
        text_reason = (reason or "").strip()
        if not text_reason:
            raise AppException(
                status_code=422,
                message="Say why this row is being rejected.",
                code="order_inquiry_reject_reason_required",
            )
        return text_reason

    def _assert_rejectable(self, row: OrderInquiryRow) -> None:
        """Whether this row is one a refusal can be about, said before anything is written."""
        if row.state not in (INQUIRY_RAISED, INQUIRY_PARTLY_LINKED, INQUIRY_PLACED):
            raise AppException(
                status_code=422,
                message=(
                    "This row cannot be rejected: it is called off or answered elsewhere."
                ),
                code="order_inquiry_row_not_rejectable",
            )
        if row.ack_state == ACK_REJECTED:
            raise AppException(
                status_code=422,
                message="This row has already been rejected.",
                code="order_inquiry_already_rejected",
            )

    def _reject_one(
        self, row: OrderInquiryRow, *, reason: str, actor_user_id: str
    ) -> None:
        """Take the row's documents back, stamp the refusal, and uncover its line.

        ONE row, which is the per-row endpoint's whole job. The batch stamps every row
        first and then un-decides each ORDER once (`reject_rows`), because a revision
        written between two refusals moves the rows the second one is about.
        """
        self._stamp_rejected(row, reason=reason, actor_user_id=actor_user_id)
        self._uncover_rejected_line(row, actor_user_id=actor_user_id)

    def _stamp_rejected(
        self, row: OrderInquiryRow, *, reason: str, actor_user_id: str
    ) -> None:
        """The refusal itself: the documents back, then who refused it, when and why.

        The unlink comes FIRST and is not optional: every link on a refused row was a claim
        on somebody's purchase order, and leaving it there would hold quantity for an
        instruction nobody is answering.
        """
        links = self._links_of(row.id)
        if links:
            self._remove_links(row, links)
            self._refresh_link_state([row])
            self.db.flush()
        row.ack_state = ACK_REJECTED
        row.rejected_by = actor_user_id
        row.rejected_at = datetime.utcnow()
        row.rejected_reason = reason
        self.db.flush()
        self._refresh_inquiry_states({row.order_inquiry_id})

    def _uncover_rejected_line(self, row: OrderInquiryRow, *, actor_user_id: str) -> None:
        """Send the rejected row's sales-order line back to the board undecided.

        NOT best-effort: every failure below this point takes the rejection down with it,
        because a row marked rejected on a line the board still reads as decided and
        promised is the exact state the board exists to make impossible. What it DOES
        answer quietly is a row that traces to no line at all - an amendment exception, a
        form row the book carries no line for. That row has no decision to uncover, which
        is an ordinary outcome and not a failure. Everything else goes through the ONE
        seam: a fresh revision carrying every line but this one.
        """
        self._uncover_rejected_lines([row], actor_user_id=actor_user_id)

    def _uncover_rejected_lines(
        self, rows: Sequence[OrderInquiryRow], *, actor_user_id: str
    ) -> None:
        """The same un-decide for a BATCH: one call per sales order, every refused line of
        that order named in it.

        Grouped rather than looped (B4): each call writes a revision of the WHOLE order, so
        a second call for a sibling line would be undoing and redoing the first one's work
        - and, worse, would cancel and re-raise the rows the rest of the batch is about.
        """
        by_order: Dict[str, Tuple[Any, List[str]]] = {}
        for row in rows:
            if not row.so_line_id:
                continue
            line = self._line_or_none(str(row.so_line_id))
            if line is None:
                continue
            order = (
                self.db.query(ProjectSalesOrder)
                .filter(ProjectSalesOrder.id == line.project_sales_order_id)
                .first()
            )
            if order is None:
                continue
            _order, line_ids = by_order.setdefault(str(order.id), (order, []))
            if str(line.id) not in line_ids:
                line_ids.append(str(line.id))
        if not by_order:
            return
        from app.services.project_supply_service import ProjectSupplyService

        supply = ProjectSupplyService(self.db)
        for order, line_ids in by_order.values():
            supply.uncover_lines(
                order,
                line_ids,
                actor_user_id=actor_user_id,
                reason="Purchasing rejected the order inquiry row for this line.",
            )

    def link_now(
        self,
        product_ids: Optional[Sequence[str]],
        *,
        actor_user_id: str,
        link_up_to: Optional[date] = None,
        link_horizon: Optional[str] = None,
    ) -> Dict[str, Any]:
        """The cascade over ACKNOWLEDGED rows, now (AC-H13).

        What the buyer presses after uploading a purchase-order or SPO book from their own
        page: the documents that arrived a moment ago meet the instructions already taken
        on. Narrowed to the products the upload touched when the caller knows them, because
        one book must not re-deal every open instruction in the company.

        It is also the page's Auto link all, and that is why it RE-DEALS
        (`PLAN-scm-oi-draft-links.md` R2): a book that has just landed may carry a nearer
        document than the one a draft is sitting on, and the press is the buyer asking for
        the best answer available now. Drafts only - a confirmed row's link is never moved
        - and awaiting rows are in scope, because a draft is exactly what this deals.
        """
        return self.auto_place_for_products(
            list(product_ids) if product_ids else None,
            actor_user_id=actor_user_id,
            trigger="link_now",
            link_up_to=link_up_to,
            link_horizon=link_horizon,
            redeal_drafts=True,
            include_awaiting=True,
        )

    def row_ids_of_decision(self, decision_id: str) -> List[str]:
        """The linkable rows THIS supply decision raised or carried (R6).

        The scope of the raise-time draft pass. By the decision rather than by the products
        those rows name, for the reason the Order Inquiry form's own pass already states: a
        product scope walks every open row in the company that happens to name the same
        item, and one board confirm must not re-deal somebody else's instructions.
        """
        rows = (
            self.db.query(OrderInquiryRow.id)
            .filter(
                OrderInquiryRow.supply_decision_id == decision_id,
                OrderInquiryRow.state.in_(INQUIRY_LINK_STATES),
                OrderInquiryRow.verb.in_(_LINKABLE_VERBS),
            )
            .all()
        )
        return [str(row_id) for (row_id,) in rows]

    def _rows_or_404(self, row_ids: Sequence[str]) -> List[OrderInquiryRow]:
        """The named rows, or a 404 naming how many of them are gone."""
        wanted = [str(row_id) for row_id in row_ids if row_id]
        if not wanted:
            raise AppException(
                status_code=422,
                message="Name at least one row.",
                code="order_inquiry_no_rows",
            )
        rows = (
            self.db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.id.in_(wanted))
            .all()
        )
        found = {str(row.id) for row in rows}
        missing = [row_id for row_id in wanted if row_id not in found]
        if missing:
            raise AppException(
                status_code=404,
                message=f"{len(missing)} of those rows no longer exist.",
                code="order_inquiry_row_not_found",
            )
        return rows

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
            # A PARTLY LINKED row is still waiting on somebody, so its inquiry is open -
            # exactly as a raised one is. Reading it as "actioned" would have closed a
            # header whose own rows still carry unlinked demand.
            if not states or states & {INQUIRY_RAISED, INQUIRY_PARTLY_LINKED}:
                inquiry.state = INQUIRY_RAISED
            elif states == {INQUIRY_CANCELLED}:
                inquiry.state = INQUIRY_CANCELLED
            else:
                inquiry.state = INQUIRY_ACTIONED
        self.db.flush()

    # ------------------------------------------------- Link PO / Link SPO (section 3.I)
    #
    # "identify which outstanding PO has quantity to fulfil this order inquiry, tag it,
    # and the quantity to be ordered is deducted" (the captain, 20 Aug), reworked twice
    # since. What it is today, and why each half is the way it is:
    #
    # **A row keeps its full quantity and carries LINKS.** The captain, 25 August, walking
    # SO414285: "1 line here should correspond to 1 line in sales order, so 1 line can be
    # placed by multiple PO and SPO". `order_inquiry_rows` held exactly one `po_line_id`,
    # so a cascade needing two lines SPLIT the row - and nine sales-order lines read as
    # eleven instructions. `projects.order_inquiry_links` (migration 421) is one row per
    # placement; the row's `state` and `po_ref` are DERIVED from them, never written by
    # hand (`_refresh_link_state`).
    #
    # **The lever on the reorder engine is netting, not a state test.** `committed_v`'s
    # confirmed leg counts `qty - sum(links.qty)` (migration 422), so a fully linked row
    # leaves confirmed demand exactly as `placed` did and a half-linked one leaves half.
    # Linking never makes the document SUPPLY - `on_order_v` still reads `spo_allocations`
    # alone - it retires the DEMAND that document is already covering.
    #
    # **An SPO allocation is a candidate for an ORDER BACK row and for nothing else**
    # (captain, 25 August; `PLAN-scm-purchasing-uat-journey.md` section 4b). A normal ORDER
    # is a NEW purchase and links to purchase order lines; an order back is a shortfall
    # against something already ordered or already shipped, and may name either.
    #
    # **Location ranks a candidate, it never filters one out** (Q5, ruled 25 August). Same
    # location, then the same ownership group at another site, then the site pools, then a
    # sibling location at the site. A link outside tier 1 is not a mistake - it is the
    # split instruction the buyer keys into AutoCount, and the PO occupancy panel marks it.
    #
    # **Then the PO's own date, then the line's** (Q7, ruled): `purchase_orders.issue_date`
    # ascending, then `expected_date`, then the document number. Before Q7 the key was the
    # line's expected date alone, which dealt a January line of an August purchase order
    # ahead of an August line of an April one.
    #
    # **A cited document comes before all of it.** CS naming "202604-S0083" on the form is
    # the most specific thing anybody knows about the row, and a walk that ignored it would
    # be answering a question nobody asked.

    def _refresh_link_state(self, rows: Sequence[OrderInquiryRow]) -> None:
        """Set each row's state and its derived display from its own links.

        The ONE writer of `state` / `po_ref` / `po_line_id` / `spo_ref` on a linkable row,
        so the four cannot come to disagree. `actioned` and `cancelled` are a person's word
        about the row and are left exactly as they are: a link change is not an opinion
        about whether purchasing dealt with it.

        The stored value for "wholly covered" stays `placed` and reads "Linked" on screen.
        Renaming the column value would have rewritten `scm.committed_v`, the worklist's
        own filter and every saved column preference to say the same thing in a different
        word, which buys nothing and breaks a bookmark.
        """
        for row in rows:
            if row.state in (INQUIRY_ACTIONED, INQUIRY_CANCELLED):
                # The STATE is a person's word and is left alone, but the derived display
                # is not a word - it is a reading of the links, and a row whose links have
                # gone must stop naming a document it no longer sits on.
                if not self._links_of(row.id):
                    row.po_ref = None
                    row.po_line_id = None
                    row.spo_ref = None
                continue
            links = self._links_of(row.id)
            linked = sum((_dec(link.qty) for link in links), _ZERO)
            need = _dec(row.qty)
            if linked <= _ZERO:
                row.state = INQUIRY_RAISED
            elif linked < need:
                row.state = INQUIRY_PARTLY_LINKED
            else:
                row.state = INQUIRY_PLACED
            first = links[0] if links else None
            # The FIRST link's document, by when it was made. `po_ref` has carried a PO
            # number since section G and several readers still print it; it is a display of
            # the links now, so it is restated here rather than left holding whatever the
            # last single-line placement happened to set.
            row.po_ref = first.document if first is not None else None
            row.po_line_id = first.po_line_id if first is not None else None
            row.spo_ref = (
                first.document
                if first is not None and first.spo_allocation_id is not None
                else None
            )

    def _links_of(self, row_id: str) -> List[OrderInquiryLink]:
        """This row's links, oldest first - the order "the first link" means."""
        return (
            self.db.query(OrderInquiryLink)
            .filter(OrderInquiryLink.row_id == row_id)
            .order_by(OrderInquiryLink.linked_at.asc(), OrderInquiryLink.id.asc())
            .all()
        )

    def _linked_qty_by_row(self, row_ids: Sequence[str]) -> Dict[str, Decimal]:
        """How much of each row already sits on a document. One query for a whole page."""
        wanted = [row_id for row_id in row_ids if row_id]
        if not wanted:
            return {}
        rows = (
            self.db.query(OrderInquiryLink.row_id, func.sum(OrderInquiryLink.qty))
            .filter(OrderInquiryLink.row_id.in_(wanted))
            .group_by(OrderInquiryLink.row_id)
            .all()
        )
        return {row_id: _dec(qty) for row_id, qty in rows}

    def _linked_by_target(self) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
        """What every link already claims, per PO line and per SPO allocation.

        The netting that stops two rows claiming the same purchase-order quantity. Read off
        the LINKS rather than off the rows' own `po_line_id`, which is derived display now:
        a row linked to two lines claims quantity on both, and the scalar names one.
        """
        if self._linked_by_target_cache is not None:
            return self._linked_by_target_cache
        by_po = {
            str(po_line_id): _dec(qty)
            for po_line_id, qty in self.db.query(
                OrderInquiryLink.po_line_id, func.sum(OrderInquiryLink.qty)
            )
            .filter(OrderInquiryLink.po_line_id.isnot(None))
            .group_by(OrderInquiryLink.po_line_id)
            .all()
        }
        by_spo = {
            str(allocation_id): _dec(qty)
            for allocation_id, qty in self.db.query(
                OrderInquiryLink.spo_allocation_id, func.sum(OrderInquiryLink.qty)
            )
            .filter(OrderInquiryLink.spo_allocation_id.isnot(None))
            .group_by(OrderInquiryLink.spo_allocation_id)
            .all()
        }
        self._linked_by_target_cache = (by_po, by_spo)
        return by_po, by_spo

    def _invalidate_link_cache(self) -> None:
        """Every writer of a link calls this. A stale total is a double-claim.

        BOTH memos go (item 4, re-review 27 Aug 2026). `_awaiting_link_cache` answers
        "which groups hold an acknowledged, still-unlinked row of this product", which a
        link written since is exactly what changes - and the route that writes one
        serialises its answer through this same instance, so the listing read the rows as
        they were before the write and offered a Link for a row it had just fully covered.
        The memo still earns its place inside one cascade pass: a placement is decided
        before its own links are written, so the walk asks between writes rather than
        across them.
        """
        self._linked_by_target_cache = None
        self._awaiting_link_cache = {}

    def _pool_codes(self) -> set:
        """Every warehouse that is SOME location's pool, by code.

        The authoritative test is the FK, not the code's shape - the same reading
        `project_supply_service._site_pool_warehouses` uses, and for the same reason: on the
        live book every pool happens to be a plain site code with no hyphen, but that is a
        naming convention the data does not enforce.
        """
        if self._pool_codes_cache is None:
            pool_ids = {
                str(row[0])
                for row in self.db.query(Warehouse.pool_warehouse_id)
                .filter(Warehouse.pool_warehouse_id.isnot(None))
                .distinct()
                .all()
            }
            self._pool_codes_cache = {
                str(code).upper()
                for (code,) in self.db.query(Warehouse.warehouse_code).filter(
                    Warehouse.id.in_(list(pool_ids)), Warehouse.is_active.is_(True)
                )
                if code
            } if pool_ids else set()
        return self._pool_codes_cache

    def _cited_documents(self, row: OrderInquiryRow) -> Dict[str, int]:
        """Every document this row NAMES, upper-cased, RANKED in the order CS wrote them.

        `cited_document` is the column CS writes into (the Amend "Order back" field, and
        the Order Inquiry Form's remark) and it holds the FIRST document. A form remark
        routinely names more than one - `SPO-2026/08-0061 & 202606-S0082` - and the second
        is not decoration: it is the answer when the first cannot cover the quantity. One
        column cannot hold two, so the rest are written onto the NOTE behind a fixed prefix
        (`project_order_inquiry_import_service.ALSO_CITED_PREFIX`) and read back here.
        Parsed with the reader's own document-number pattern rather than a second one, so
        the two cannot come to disagree about what a document number looks like.

        A RANK rather than a set, because "cited" is not one bucket: the walk must try the
        first document CS named before the second, or a row whose first citation is short
        lands on the wrong one and reads as a rule that ignored the form.

        `spo_ref` is read after them for the rows raised before `cited_document` existed.
        `po_ref` is NOT read: since section 3.I it is the derived display of the first link,
        so reading it would make every already-linked row cite the document it is already on
        and pin the walk to its own past.
        """
        ordered: List[str] = []

        def _add(value: Any) -> None:
            key = str(value or "").strip().upper()
            if key and key not in ordered:
                ordered.append(key)

        _add(row.cited_document)
        for document in _also_cited(row.note):
            _add(document)
        _add(row.spo_ref)
        return {document: rank for rank, document in enumerate(ordered)}

    def _candidates_for_row(
        self, row: OrderInquiryRow, *, manual: bool = False, credit_own_links: bool = False
    ) -> List[Dict[str, Any]]:
        """Every open document line this row could be linked to, in the walk's own order.

        `credit_own_links` asks the question a RE-DEAL has to ask: what could this row
        reach if it gave back what it is already holding? Its own links are added back to
        every line's `remaining`, so the walk compares the document it sits on against the
        alternatives on equal terms - without which a row fully covering itself would find
        its own line "fully claimed" and move to a worse one. Nothing is unlinked to ask
        it (B1, review round 28 Aug): the answer is computed FIRST and the links come down
        only once there is a better one to write, so a row whose candidate has gone, or
        that the horizon holds back, keeps what it has.

        `manual` widens it to a purchase order that is not yet ACTIVE. The automatic walk
        refuses one deliberately - a `draft_recommendation` order is not an outstanding
        order (it is outside `scm.on_order_v` for exactly that reason), and its lines are
        the ones a re-decision may delete out from under a link. A PERSON naming a line by
        hand has always been allowed to, because the dialog is override and audit rather
        than the workflow, and taking that away would have been a narrowing nobody asked
        for.

        ONE query pair feeding both the dialog's candidate list and the auto-link cascade,
        so the preview and the pass can never disagree. `remaining` is already net of every
        OTHER link on the same line, which is why two rows can never be pointed at the same
        quantity.

        SPO allocations are read only for an ORDER BACK row. Their open test is the one
        copy in `app.services.scm.spo_supply` (`open_incoming_clauses`): open line status, a
        receipt status that is not received, no landed shipment - and, per the captain's
        26 August ruling, a promised date in the PAST does not remove a row. The book is
        the record of what is still owed; a supplier being late is not evidence the goods
        stopped existing.

        LADDER V4 (section 1d): a purchase-order line sitting at a `*-<group>` location is
        free only to the extent the GROUP can cover its own backlog with it -
        `group_net + the group's own open PO balance > 0`. In deficit those lines are
        already spoken for, and linking a raised row to one of them says a quantity is
        covered when the group is 15,514 short of covering what it already owes. A
        pool-location line has no group and is always offered; the row that finds nothing
        stays raised and buys, which is the honest outcome.
        """
        product_id = self._resolve_product_id(row)
        if not product_id:
            return []
        by_po, by_spo = self._linked_by_target()
        if credit_own_links:
            by_po, by_spo = dict(by_po), dict(by_spo)
            for link in self._links_of(str(row.id)):
                key = str(link.po_line_id) if link.po_line_id else None
                if key and key in by_po:
                    by_po[key] = by_po[key] - _dec(link.qty)
                key = str(link.spo_allocation_id) if link.spo_allocation_id else None
                if key and key in by_spo:
                    by_spo[key] = by_spo[key] - _dec(link.qty)
        pools = self._pool_codes()
        cited = self._cited_documents(row)
        own_location = (row.stock_location or "").strip().upper() or None
        spo_allowed = row.verb in _SPO_LINKABLE_VERBS

        candidates: List[Dict[str, Any]] = []

        po_rows = (
            self.db.query(PurchaseOrderLine, PurchaseOrder, Supplier, Warehouse)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .outerjoin(Warehouse, Warehouse.id == PurchaseOrderLine.warehouse_id)
            .filter(
                PurchaseOrderLine.product_id == product_id,
                PurchaseOrderLine.line_status == "open",
                PurchaseOrder.po_number.notlike("SPO-%"),
                *(
                    ()
                    if manual
                    else (PurchaseOrder.status.in_(("active", "partial")),)
                ),
            )
            .all()
        )
        # LADDER V4's group-deficit rule applies to what is OFFERED - the dialog's list and
        # the cascade's walk. A PERSON naming a line by hand is let through, exactly as
        # `manual` already lets them through to a purchase order that is not yet active:
        # this dialog is override and audit rather than the workflow, and refusing a link
        # somebody has deliberately typed would be a narrowing nobody asked for.
        #
        # THIS row's own exemption comes off it, and only this row's (B1, code review
        # 27 Aug 2026): a group holding an acknowledged, unlinked row may reach its own
        # purchase order, and the row that earns that is the one being placed. Lifted per
        # product instead, a row at any other group walked first took the line.
        deficit = (
            set()
            if manual
            else (
                self._groups_in_deficit(product_id, po_rows, by_po)
                - self._exempt_groups_for_row(row, product_id)
            )
        )
        for line, po, supplier, warehouse in po_rows:
            remaining = (
                _dec(line.qty_ordered)
                - _dec(line.qty_received)
                - by_po.get(str(line.id), _ZERO)
            )
            if remaining <= _ZERO:
                continue
            location = warehouse.warehouse_code if warehouse else None
            if group_of_warehouse_code(location) in deficit:
                continue
            candidates.append(
                self._candidate(
                    kind="po",
                    target_id=str(line.id),
                    document=po.po_number,
                    line_label=self._line_label(line.source_ref),
                    location=location,
                    issue_date=po.issue_date,
                    expected_date=line.expected_date,
                    remaining=remaining,
                    qty_ordered=_dec(line.qty_ordered),
                    qty_received=_dec(line.qty_received),
                    supplier_name=supplier.supplier_name if supplier else None,
                    unit_cost=line.unit_cost,
                    currency=line.currency,
                    own_location=own_location,
                    pools=pools,
                    cited=cited,
                )
            )

        if spo_allowed:
            spo_rows = (
                self.db.query(SPOAllocation, Supplier, Warehouse)
                .outerjoin(InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id)
                .outerjoin(Supplier, Supplier.id == SPOAllocation.supplier_id)
                .outerjoin(Warehouse, Warehouse.id == SPOAllocation.warehouse_id)
                .filter(
                    SPOAllocation.product_id == product_id,
                    SPOAllocation.spo_number.isnot(None),
                    *spo_supply.open_incoming_clauses(),
                )
                .all()
            )
            for allocation, supplier, warehouse in spo_rows:
                remaining = (
                    _dec(allocation.allocated_quantity)
                    - _dec(allocation.quantity_received)
                    - by_spo.get(str(allocation.id), _ZERO)
                )
                if remaining <= _ZERO:
                    continue
                location = (
                    warehouse.warehouse_code if warehouse else allocation.location_code
                )
                # R11 (`PLAN-scm-oi-draft-links.md`): an SPO is always allocated at a POOL
                # location and moved out from there, so only a pool line is OFFERED. A line
                # at any other code is SHOWN - the lightbox lists every line of the
                # document - and never dealt, because the goods on it are already spoken
                # for by the site that holds them. Read off the warehouse rather than the
                # book's raw code: an unknown code resolved to no warehouse, and a code
                # nobody holds is not a pool.
                #
                # A PERSON naming a line by hand is let through, exactly as `manual`
                # already lets them through to a purchase order that is not yet active and
                # past a group in deficit. The container planner is the caller that needs
                # it: its ticks say "this row is served by THIS container line", the line
                # is at the site the split just sent it to, and that is a deliberate
                # instruction rather than the automatic walk helping itself.
                #
                # The WAREHOUSE and never the book's raw code (review round 28 Aug): the
                # listing's own read of the same rule (`link_candidate_products`) joins the
                # warehouse and can read nothing else, so a book line carrying a pool-shaped
                # code the master does not hold would have been dealt here and reported as
                # no candidate there - the flag offering a Link the dialog then shows empty.
                if not manual and (
                    str(warehouse.warehouse_code if warehouse else "").strip().upper()
                    not in pools
                ):
                    continue
                candidates.append(
                    self._candidate(
                        kind="spo",
                        target_id=str(allocation.id),
                        document=allocation.spo_number,
                        line_label=self._line_label(allocation.spo_line_number),
                        location=location,
                        issue_date=allocation.issue_date,
                        expected_date=allocation.expected_date,
                        remaining=remaining,
                        qty_ordered=_dec(allocation.allocated_quantity),
                        qty_received=_dec(allocation.quantity_received),
                        supplier_name=supplier.supplier_name if supplier else None,
                        unit_cost=allocation.unit_cost,
                        currency=allocation.currency,
                        own_location=own_location,
                        pools=pools,
                        cited=cited,
                    )
                )

        candidates.sort(key=lambda candidate: candidate["sort"])
        return candidates

    def _netting(self, product_ids: Sequence[Optional[str]]) -> GroupNetting:
        """Ladder v4's availability reader, over every product asked about so far.

        Rebuilt when a product it has not seen turns up, so a caller that primes it with
        the whole batch (the cascade does) pays for ONE three-query read and a single-row
        caller pays for one too. It is the same `group_netting` reader the fulfilment ladder
        uses, which is the point: the board refusing to promise a group's stock and
        purchasing linking a row to that group's purchase order would be two answers to one
        question.

        **The same READER, over a WIDER span** (AC-S1-5b, corrected 30 Aug). This call is
        not `planning_only`, so its ownership-group index covers every ACTIVE bin, while the
        board's proposal reads only the bins flagged into fulfilment planning (R17). That is
        deliberate and it is the boundary the AC draws: the flag narrows what a PROPOSAL may
        draw, never what a non-planning consumer may see, so the deficit gate here still
        sees a group's real negative net. The two therefore agree about the ARITHMETIC and
        can legitimately differ about the SPAN.
        """
        wanted = {str(pid) for pid in product_ids if pid}
        if self._netting_value is None or wanted - self._netted_products:
            self._netted_products |= wanted
            self._netting_value = netting_for_products(
                self.db, sorted(self._netted_products)
            )
        return self._netting_value

    def _groups_in_deficit(
        self,
        product_id: str,
        po_rows: Sequence[Any],
        by_po: Dict[str, Decimal],
    ) -> set:
        """The ownership groups whose OPEN PURCHASE ORDERS cannot cover their own backlog
        (ladder v4, section 1d).

        `group_net + everything still to come on the group's own purchase orders`. At or
        above zero the group has purchases nobody has claimed and a row may link to one;
        BELOW zero, every unit already on order is owed to demand the group carries and a
        link would promise the same stock twice.

        ZERO IS OFFERED, and that boundary is the ordinary case rather than an edge one
        (captain, 27 Aug). A purchase order raised off the plan buys exactly what the plan
        said the group was short, so the group lands on precisely `net + remaining == 0`.
        Read as "at or below zero is deficit", that group was refused its own purchase
        order: the rows that sized the buy stayed raised, the PO-confirm cascade offered
        them nothing and the Link dialog listed nothing. Nothing is promised twice at zero -
        the demand the buy covers IS the demand the group carries.

        The second half of the same ruling - a group holding an ACKNOWLEDGED, UNLINKED row
        for this product may reach its own purchase order however short the arithmetic says
        it is - is NOT applied here. It is a per-ROW exemption and it is applied by
        `_candidates_for_row` to the row being placed (B1, code review 27 Aug 2026):
        lifting the group out of this set instead exempted EVERY row of the product, so a
        row at another group entirely - walked first, because candidates are ranked by
        location and never filtered by it - helped itself to the line the exempt group's
        own backlog had been bought.

        The deficit itself is computed off the CANDIDATE ROWS, so it costs no query beyond
        the netting read: those rows already are the product's whole open purchase-order
        book, and `by_po` is already netted for the links written against them. That claim
        was FALSE while the exemption lived here - it ran up to three uncached queries per
        row through `_groups_awaiting_a_link` (S3, code review 27 Aug 2026) - and is true
        again now the exemption is the caller's, and memoised per product besides.
        """
        remaining_by_group: Dict[str, Decimal] = {}
        for line, _po, _supplier, warehouse in po_rows:
            group = group_of_warehouse_code(
                warehouse.warehouse_code if warehouse else None
            )
            if not group:
                continue
            remaining = (
                _dec(line.qty_ordered)
                - _dec(line.qty_received)
                - by_po.get(str(line.id), _ZERO)
            )
            if remaining > _ZERO:
                remaining_by_group[group] = (
                    remaining_by_group.get(group, _ZERO) + remaining
                )
        if not remaining_by_group:
            return set()
        netting = self._netting([product_id])
        return {
            group
            for group, remaining in remaining_by_group.items()
            if netting.group_net(product_id, group).net + remaining < _ZERO
        }

    def _exempt_groups_for_row(self, row: OrderInquiryRow, product_id: str) -> set:
        """The deficit exemption THIS row has earned, and nobody else's (B1, code review
        27 Aug 2026).

        A group holding an acknowledged, still-unlinked row for the product may reach its
        own purchase order however short it is, because that row is the demand somebody
        bought the order for (captain, 27 Aug). The exemption is the ROW's, not the
        product's: subtracting it from the deficit set once per product let any row of the
        product take the line, and the walk ranks candidates by location without ever
        filtering by it, so a row at another group walked first simply took it.

        `set()` for a row that is rejected, fully linked, or resolves to no location - none
        of those is the instruction a buy answers. An AWAITING row does count (R6): its
        draft is the answer purchasing will read, and refusing a group its own purchase
        order until somebody pressed Confirm left the page reading "Not found" for exactly
        the rows the buy was sized from.
        """
        return {
            group
            for group, row_ids in self._rows_awaiting_a_link(product_id).items()
            if str(row.id) in row_ids
        }

    def _groups_awaiting_a_link(self, product_id: str) -> set:
        """The ownership groups holding a still-unlinked row of this product - the demand
        a purchase order at that group was bought for.

        The LISTING's own read (`link_candidate_products`), which answers per product and
        has no row in hand. The per-ROW exemption the candidate walk applies is
        `_exempt_groups_for_row`.
        """
        return set(self._rows_awaiting_a_link(product_id))

    def _rows_awaiting_a_link(self, product_id: str) -> Dict[str, set]:
        """`{group: {row ids}}` - every row of this product a document is still owed to,
        filed under the group it sits at.

        Read off the rows the cascade itself would walk (open supply state, linkable verb,
        anything but rejected), so "there is an instruction waiting" here and "there is a
        row to place" there cannot disagree. AWAITING rows count since
        `PLAN-scm-oi-draft-links.md` R6: the cascade drafts for them now, and the demand a
        group's purchase order was bought for is exactly the row CS has just raised - the
        earlier `ACK_LINKABLE` reading refused a group its own buy until somebody had
        pressed Confirm, which is the press this whole plan exists to answer.

        The row's group is its own stated `stock_location` where it has one, and otherwise
        the reconciled core line's warehouse - the same two arms `rows_needed_at` reads a
        row's location through. A row that resolves to no location belongs to no group and
        is not evidence about one.

        MEMOISED per product on the instance (S3, code review 27 Aug 2026): it costs up to
        three queries and the cascade asks it once per row, which on a full pass over one
        product is the same three queries answered over and over. A row this pass has since
        linked cannot change the answer for the row being placed now - it is placed before
        its own links are written, and it is walked once. The memo is dropped by
        `_invalidate_link_cache` on every link written or removed all the same (item 4),
        because a caller that writes and then READS through one instance - which is every
        link route - would otherwise be answered about a state it has already left.
        """
        cached = self._awaiting_link_cache.get(str(product_id))
        if cached is not None:
            return cached
        answer = self._read_rows_awaiting_a_link(product_id)
        self._awaiting_link_cache[str(product_id)] = answer
        return answer

    def _read_rows_awaiting_a_link(self, product_id: str) -> Dict[str, set]:
        """`_rows_awaiting_a_link` without the memo - the queries themselves."""
        query = self.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.state.in_((INQUIRY_RAISED, INQUIRY_PARTLY_LINKED)),
            OrderInquiryRow.verb.in_(_LINKABLE_VERBS),
            OrderInquiryRow.ack_state.in_(
                tuple(ACK_LINKABLE) + (ACK_AWAITING,)
            ),
        )
        query = self._narrow_to_products(query, [product_id])
        rows = query.all() if query is not None else []
        if not rows:
            return {}
        linked = self._linked_qty_by_row([str(row.id) for row in rows])
        owed = [
            row
            for row in rows
            if _dec(row.qty) - linked.get(str(row.id), _ZERO) > _ZERO
        ]
        if not owed:
            return {}

        # The core line's warehouse CODE, for the rows that state no location of their own.
        so_line_ids = [row.so_line_id for row in owed if row.so_line_id]
        core_code: Dict[str, Optional[str]] = {}
        if so_line_ids:
            for psl_id, code in (
                self.db.query(ProjectSalesOrderLine.id, Warehouse.warehouse_code)
                .join(
                    SalesOrderLine,
                    SalesOrderLine.id == ProjectSalesOrderLine.core_sales_order_line_id,
                )
                .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
                .filter(ProjectSalesOrderLine.id.in_(so_line_ids))
                .all()
            ):
                core_code[str(psl_id)] = code

        groups: Dict[str, set] = {}
        for row in owed:
            code = (row.stock_location or "").strip() or core_code.get(
                str(row.so_line_id or "")
            )
            group = group_of_warehouse_code(code)
            if group:
                groups.setdefault(group, set()).add(str(row.id))
        return groups

    @staticmethod
    def _line_label(raw: Any) -> Optional[str]:
        """`L3`, when the book numbered the line. `None` when it did not.

        The purchase book carries its line number in `purchase_order_lines.source_ref` and
        the shipping book in `spo_allocations.spo_line_number`; plenty of documents on the
        dev copy carry neither, and a made-up ordinal beside a document with six open lines
        would name the wrong one. The reader falls back to the LOCATION, which is a fact.
        """
        if raw is None:
            return None
        text_value = str(raw).strip()
        if not text_value:
            return None
        return f"L{text_value}"

    def _candidate(
        self,
        *,
        kind: str,
        target_id: str,
        document: Optional[str],
        line_label: Optional[str],
        location: Optional[str],
        issue_date: Optional[date],
        expected_date: Optional[date],
        remaining: Decimal,
        qty_ordered: Decimal,
        qty_received: Decimal,
        supplier_name: Optional[str],
        unit_cost: Any,
        currency: Optional[str],
        own_location: Optional[str],
        pools: set,
        cited: Dict[str, int],
    ) -> Dict[str, Any]:
        """One candidate, with the sort key that IS the walk (Q5 then Q7).

        The key, outermost first: WHICH document CS cited, in the order they wrote them -
        `SPO-2026/08-0061 & 202606-S0082` tries the allocation before the purchase order,
        and a rank rather than a flag is what makes that true (a flag puts both in one
        bucket and lets the date decide between two documents the form already ordered);
        then an SPO before a purchase order (an order back is owed against what is already
        shipped before it is owed against a new purchase); then the location tier; then the
        pool sub-rank inside tier 3 (the row's own site pool before the others); then the
        PO's own issue date, then the line's expected date, then the document number, then
        the id so a tie breaks the same way twice.
        """
        tier, sub = link_location_tier(own_location, location, pools)
        # Uncited sorts after every citation, however many there are.
        citation_rank = cited.get(str(document or "").strip().upper(), len(cited) + 1)
        is_cited = bool(document) and citation_rank <= len(cited)
        return {
            "kind": kind,
            "po_line_id": target_id if kind == "po" else None,
            "spo_allocation_id": target_id if kind == "spo" else None,
            "target_id": target_id,
            "document": document,
            "line_label": line_label,
            "location": location,
            "tier": tier,
            # What the automatic pass may take (the captain, 27 Aug): the row's own site
            # pool and better, never a sibling group or another site. A row naming no
            # location ranks nothing and keeps the whole list, as before.
            "cascadable": own_location is None or tier <= TIER_POOL,
            "issue_date": issue_date,
            "expected_date": expected_date,
            "remaining": remaining,
            "qty_ordered": qty_ordered,
            "qty_received": qty_received,
            "supplier_name": supplier_name,
            "unit_cost": unit_cost,
            "currency": currency,
            "cited": is_cited,
            "sort": (
                citation_rank,
                0 if kind == "spo" else 1,
                tier,
                sub,
                (issue_date is None, issue_date or date.min),
                (expected_date is None, expected_date or date.min),
                document or "",
                target_id,
            ),
        }

    @staticmethod
    def _cascade_take(
        candidates: Sequence[Dict[str, Any]], need: Decimal
    ) -> List[Tuple[Dict[str, Any], Decimal]]:
        """`min(what is left on this line, what is still needed)` off each candidate in the
        order it was given, until the need is covered or the candidates run out.

        Partial coverage is allowed and is not a failure: a `need` bigger than every
        candidate's remaining balance combined simply returns less than `need`, and the row
        is left PARTLY LINKED with the rest still counting as demand. Before the links
        table there was nowhere to record that, so the row had to be split for the
        arithmetic to work.
        """
        still = need
        takes: List[Tuple[Dict[str, Any], Decimal]] = []
        for candidate in candidates:
            if still <= _ZERO:
                break
            # The cascade stops at the site pool (the captain, 27 Aug: "we should take
            # from site pool only"). A sibling group's line, or one at another site, is
            # still LISTED in the Link dialog - a buyer may take it by hand - but the
            # automatic pass never does: BRW-IB's purchase is BRW-IB's, and an order at
            # MWH-IR taking 78 of it was the case that ruled it.
            if not candidate.get("cascadable", True):
                continue
            remaining = candidate["remaining"]
            take = remaining if remaining < still else still
            if take > _ZERO:
                takes.append((candidate, take))
                still -= take
        return takes

    def po_candidates_for_row(self, row_id: str) -> List[Dict[str, Any]]:
        """The candidate list the Link dialog shows, in the walk's own order.

        `remaining` already nets what every OTHER link claims on the same line, so `covers`
        and `default_take` are answered against what is ACTUALLY left. `default_take` is
        the cascade's own preview computed by the SAME walk `auto_place_for_products` runs,
        which is what stops the dialog and the automatic pass being two opinions.

        The need is the row's UNLINKED remainder, not its whole quantity: a row already
        linked 5 of 8 opens the dialog looking for 3.
        """
        row = self._row_or_404(row_id)
        self._assert_linkable(row)
        product_id = self._resolve_product_id(row)
        if not product_id:
            raise AppException(
                status_code=409,
                message="This row names no product to match a purchase order line against.",
                code="order_inquiry_no_product",
            )
        need = self._unlinked_need(row)
        candidates = self._candidates_for_row(row)
        cascade = {
            candidate["target_id"]: take
            for candidate, take in self._cascade_take(candidates, need)
        }
        claims_by_line = self._linked_claims_by_target(candidates)
        out: List[Dict[str, Any]] = []
        for candidate in candidates:
            already = (
                candidate["qty_ordered"] - candidate["qty_received"] - candidate["remaining"]
            )
            out.append(
                {
                    "kind": candidate["kind"],
                    "po_line_id": candidate["po_line_id"],
                    "spo_allocation_id": candidate["spo_allocation_id"],
                    "po_number": candidate["document"],
                    "line_label": candidate["line_label"],
                    "location": candidate["location"],
                    "tier": candidate["tier"],
                    "cited": candidate["cited"],
                    "supplier_name": candidate["supplier_name"],
                    "issue_date": candidate["issue_date"],
                    "expected_date": candidate["expected_date"],
                    "qty_ordered": _qty_str(candidate["qty_ordered"]),
                    "qty_received": _qty_str(candidate["qty_received"]),
                    "already_tagged": _qty_str(already),
                    "remaining": _qty_str(candidate["remaining"]),
                    "covers": candidate["remaining"] >= need,
                    "recommended": False,
                    "default_take": _qty_str(cascade.get(candidate["target_id"], _ZERO)),
                    "unit_cost": (
                        _qty_str(_dec(candidate["unit_cost"]))
                        if candidate["unit_cost"] is not None
                        else None
                    ),
                    "currency": candidate["currency"],
                    "claims": claims_by_line.get(candidate["target_id"], []),
                }
            )
        recommended = next((entry for entry in out if entry["covers"]), None)
        if recommended is not None:
            recommended["recommended"] = True
        return out

    def _unlinked_need(self, row: OrderInquiryRow) -> Decimal:
        """What is still to be linked on this row: its quantity, less its links."""
        linked = sum((_dec(link.qty) for link in self._links_of(row.id)), _ZERO)
        return max(_dec(row.qty) - linked, _ZERO)

    def _write_link(
        self,
        row: OrderInquiryRow,
        candidate: Dict[str, Any],
        qty: Decimal,
        *,
        actor_user_id: str,
        auto_trigger: Optional[str] = None,
    ) -> OrderInquiryLink:
        """One link, plus the audit claim behind it.

        `auto_trigger` names WHY this happened without a person clicking it - appended to
        the ROW's own note, which is already this feature's evidence field, rather than a
        new column. The claim is written for a PO link only: `order_link_service` keys a
        claim on (SO number, PO number, item), and an SPO number resolves through the same
        function since migration 420, so both families are claimable - but the claim's
        `source = 'order_inquiry'` delete-on-unlink rule is what makes it safe, and it is
        written for whichever document the link names.
        """
        document = candidate["document"]
        supplier = candidate["supplier_name"] or "unknown supplier"
        expected = (
            candidate["expected_date"].isoformat() if candidate["expected_date"] else "no date"
        )
        stamp = (
            f"Linked to {document or 'an unnamed document'} ({supplier}), "
            f"expected {expected}"
        )
        if auto_trigger:
            stamp = f"{stamp}; auto: {auto_trigger}"
        row.note = f"{row.note}; {stamp}" if row.note else stamp
        row.actioned_by = actor_user_id
        row.actioned_at = datetime.utcnow()

        claim_id = None
        if document:
            so_number, item_code, core_line_id = self._claim_identity(row)
            claim = order_link_service.claim_placed_on_po(
                self.db,
                company_id=row.company_id,
                so_number=so_number,
                po_number=document,
                item_code=item_code,
                so_line_id=core_line_id,
                po_line_id=candidate["po_line_id"],
                spo_allocation_id=candidate["spo_allocation_id"],
            )
            claim_id = claim.id if claim is not None else None

        link = OrderInquiryLink(
            company_id=row.company_id,
            row_id=row.id,
            po_line_id=candidate["po_line_id"],
            spo_allocation_id=candidate["spo_allocation_id"],
            document=document,
            qty=qty,
            linked_by=actor_user_id,
            linked_at=datetime.utcnow(),
            auto=bool(auto_trigger),
            claim_id=claim_id,
        )
        self.db.add(link)
        self.db.flush()
        self._invalidate_link_cache()
        return link

    def place_supply_borrow(
        self,
        row: OrderInquiryRow,
        *,
        supply_key: str,
        qty: Decimal,
        actor_user_id: str,
    ) -> None:
        """Link an ORDER_BACK row to the document ladder v7.1 step 3 gave it (PLAN 3.3).

        The board's Confirm, not a buyer's click, so it takes the row rather than a row id
        and the document by the ASSIGNMENT's own key (`spo:<allocation id>` /
        `po:<line id>`) - the same address the component carries, so there is no second
        lookup and no chance of naming a different line of the same document.

        Everything else is `place_on_po_allocations`' own walk, and deliberately: the
        candidate read, the remaining-quantity test, the ORDER-BACK-only rule for an SPO
        allocation, the claim, the note stamp and the row's link state are all one
        implementation. What is NOT reused is the AUTOMATIC reading of that walk
        (`manual=False`), which applies ladder v4's group-deficit rule: it refuses a
        purchase-order line at a group that cannot cover its own backlog, and a group in
        deficit is the ordinary case for the very unit this step is borrowing for. The
        engine has already decided; this is the write.
        """
        kind, target = parse_supply_key(supply_key)
        if not target:
            return
        self.place_on_po_allocations(
            str(row.id),
            [
                {
                    "spo_allocation_id": target if kind == SA_KIND_SPO else None,
                    "po_line_id": target if kind == SA_KIND_PO else None,
                    "qty": qty,
                }
            ],
            actor_user_id=actor_user_id,
        )

    def release_supply_borrow(
        self, *, supply_key: str, core_line_id: str, qty: Decimal
    ) -> Decimal:
        """Take DOWN a line's placements on one document, up to `qty`, and say how much
        came down (PLAN 3.3's middle clause).

        The donor is giving up what it was holding, so the placement that held it has to go
        - a link left standing would keep the document reserved for an order the board has
        just decided is waiting for a replacement instead, and `_candidates_for_row` would
        then refuse the asker's own link on the grounds that the document is fully claimed.

        LATEST FIRST, and reduced rather than always deleted: a donor holding a document
        through two placements gives up the newest one first, and a placement bigger than
        what is being borrowed keeps its remainder. A link of zero is not a smaller
        placement, it is a row that should not exist, so it is deleted - through
        `_remove_links` like every other unlink in this service, because the audit CLAIM
        the link wrote goes with it. Deleted by hand it stayed behind, naming a document
        the donor no longer holds.
        """
        left = _dec(qty)
        if left <= _ZERO:
            return _ZERO
        rows = self._supply_borrow_links(supply_key, core_line_id=core_line_id)
        released = _ZERO
        touched: List[OrderInquiryRow] = []
        going: Dict[str, Tuple[OrderInquiryRow, List[OrderInquiryLink]]] = {}
        for link, row in rows:
            if left <= _ZERO:
                break
            take = min(left, _dec(link.qty))
            if take <= _ZERO:
                continue
            if take >= _dec(link.qty):
                going.setdefault(str(row.id), (row, []))[1].append(link)
            else:
                link.qty = _dec(link.qty) - take
            left -= take
            released += take
            touched.append(row)
        for row, links in going.values():
            self._remove_links(row, links)
        if released > _ZERO:
            self.db.flush()
            self._invalidate_link_cache()
            self._refresh_link_state(touched)
            self.db.flush()
        return released

    def supply_borrow_held_qty(self, supply_key: str, core_line_id: str) -> Decimal:
        """How much of one document a line holds through LIVE placements of its own.

        The quantity `release_supply_borrow` is about to hand back, read before it does -
        which is what tells the confirmation whether the donor's own row is about to
        re-raise the shortfall by itself (`_borrow_shortfalls`). Same query, so the answer
        and the action cannot disagree.
        """
        return sum(
            (
                _dec(link.qty)
                for link, _row in self._supply_borrow_links(
                    supply_key, core_line_id=core_line_id
                )
            ),
            _ZERO,
        )

    def _supply_borrow_links(
        self, supply_key: str, *, core_line_id: str
    ) -> List[Tuple[OrderInquiryLink, OrderInquiryRow]]:
        """One line's LIVE placements on one document, newest first, with their rows.

        `supply_key` is parsed HERE and nowhere else on this side (`spo:<allocation id>` /
        `po:<purchase order line id>`, the assignment's own address).
        """
        kind, target = parse_supply_key(supply_key)
        if not target:
            return []
        column = (
            OrderInquiryLink.spo_allocation_id
            if kind == SA_KIND_SPO
            else OrderInquiryLink.po_line_id
        )
        return (
            self.db.query(OrderInquiryLink, OrderInquiryRow)
            .join(OrderInquiryRow, OrderInquiryRow.id == OrderInquiryLink.row_id)
            .join(
                ProjectSalesOrderLine,
                ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id,
            )
            .filter(
                column == target,
                ProjectSalesOrderLine.core_sales_order_line_id == core_line_id,
                OrderInquiryRow.state != INQUIRY_CANCELLED,
            )
            .order_by(OrderInquiryLink.linked_at.desc())
            .all()
        )

    def retire_supply_borrow_rows(
        self,
        project_sales_order_id: str,
        *,
        reason: str,
        line_ids: Optional[Sequence[str]] = None,
        except_decision_id: Optional[str] = None,
    ) -> int:
        """Cancel this order's step-3 placement rows, links and all (PLAN 3.3).

        A step-3 row belongs to the DECISION that raised it: it is not an instruction to buy
        anything, it is the record that a line's quantity is coming off a named document, and
        the placement link hanging off it is what holds that document. So when the line
        leaves the revision - undecided through `uncover_lines`, superseded by a material
        change, challenged by drift, or re-decided by a later revision of the same order -
        the row goes and the document is free for whoever needs it next. Left standing, it
        pinned the document forever to an instruction that no longer exists.

        Told apart from every other `ORDER_BACK` row by `covered_by`, which is what that
        column has always meant here: a step-3 row NAMES what covers it, and a donor hole
        names nothing because nothing covers it yet (`_raise_borrow_shortfalls`).

        `line_ids` scopes it to the lines that moved; `except_decision_id` spares the rows
        the confirmation now running has just written. The links come down through
        `_remove_links`, so their claims go with them.
        """
        inquiry = self._existing(project_sales_order_id, None)
        if inquiry is None:
            return 0
        query = self.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.order_inquiry_id == inquiry.id,
            OrderInquiryRow.verb == IV_ORDER_BACK,
            OrderInquiryRow.covered_by.isnot(None),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        if line_ids is not None:
            wanted = sorted({str(line_id) for line_id in line_ids})
            if not wanted:
                return 0
            query = query.filter(OrderInquiryRow.so_line_id.in_(wanted))
        if except_decision_id is not None:
            query = query.filter(
                or_(
                    OrderInquiryRow.supply_decision_id.is_(None),
                    OrderInquiryRow.supply_decision_id != except_decision_id,
                )
            )
        rows = query.all()
        for row in rows:
            links = self._links_of(row.id)
            if links:
                self._remove_links(row, links)
            row.state = INQUIRY_CANCELLED
            row.note = f"{row.note}; {reason}" if row.note else reason
        if rows:
            self.db.flush()
        return len(rows)

    def place_on_po(
        self, row_id: str, po_line_id: str, *, actor_user_id: str
    ) -> Dict[str, Any]:
        """Link this row to ONE open PO line, for its whole unlinked remainder.

        The single-target shape the feature shipped with, kept: a person who names one line
        that covers the row is not asked to compose an allocation.
        """
        row = self._row_or_404(row_id)
        # THE ROW, not a list. `place_on_po_allocations` answers with a list because it
        # once split the row into several; this one has always answered with the single
        # row a caller named, and changing that quietly would have handed every existing
        # caller a list where it indexes a dict.
        written = self.place_on_po_allocations(
            row_id,
            [{"po_line_id": po_line_id, "qty": self._unlinked_need(row)}],
            actor_user_id=actor_user_id,
        )
        return written[0]

    def place_on_po_allocations(
        self,
        row_id: str,
        allocations: Sequence[Dict[str, Any]],
        *,
        actor_user_id: str,
        auto_trigger: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Link this row across one or more document lines, in one call.

        **The row is never split** (AC-I6). It keeps its full quantity and gains one link
        per allocation; what the allocations do not cover stays demand and the row reads
        partly linked. `sum(links) <= row.qty` is held here, and `qty > 0` per link is held
        by the table's own CHECK.

        Refuses, in the words the buyer needs: a line that is no longer open, a line for a
        different product, an SPO allocation named by a row whose verb is not ORDER BACK,
        an allocation bigger than what the line has left, and a total bigger than what the
        row still needs.
        """
        row = self._row_or_404(row_id)
        self._assert_linkable(row)
        if not allocations:
            raise AppException(
                status_code=422,
                message="Name at least one document line.",
                code="order_inquiry_no_allocations",
            )
        product_id = self._resolve_product_id(row)
        if not product_id:
            raise AppException(
                status_code=409,
                message="This row names no product to match a purchase order line against.",
                code="order_inquiry_no_product",
            )

        need = self._unlinked_need(row)
        by_target = {
            candidate["target_id"]: candidate
            for candidate in self._candidates_for_row(row, manual=auto_trigger is None)
        }

        resolved: List[Tuple[Dict[str, Any], Decimal]] = []
        taken_within_call: Dict[str, Decimal] = {}
        total = _ZERO
        for entry in allocations:
            spo_allocation_id = str(entry.get("spo_allocation_id") or "") or None
            po_line_id = str(entry.get("po_line_id") or "") or None
            qty = _dec(entry.get("qty"))
            if qty <= _ZERO:
                continue
            if spo_allocation_id and row.verb not in _SPO_LINKABLE_VERBS:
                raise AppException(
                    status_code=409,
                    message=(
                        "Only an ORDER BACK row can be linked to an SPO allocation - an "
                        "ORDER is a new purchase, and it goes on a purchase order."
                    ),
                    code="order_inquiry_spo_not_order_back",
                )
            target_id = spo_allocation_id or po_line_id
            if not target_id:
                raise AppException(
                    status_code=422,
                    message="Each line must name a purchase order line or an SPO allocation.",
                    code="order_inquiry_no_target",
                )
            candidate = by_target.get(target_id)
            if candidate is None:
                # Not a candidate, and WHY matters: "that line is for a different product"
                # and "that line is closed" send a person to different places, and one
                # message covering both sends them to neither.
                self._refuse_absent_target(
                    po_line_id=po_line_id, spo_allocation_id=spo_allocation_id,
                    product_id=product_id,
                )
            left = candidate["remaining"] - taken_within_call.get(target_id, _ZERO)
            if left < qty:
                raise AppException(
                    status_code=409,
                    message=(
                        f"{candidate['document'] or 'That line'} has {_qty_str(left)} "
                        f"left, {_qty_str(qty - left)} short of the {_qty_str(qty)} "
                        "allocated to it."
                    ),
                    code="order_inquiry_po_line_short",
                )
            taken_within_call[target_id] = taken_within_call.get(target_id, _ZERO) + qty
            resolved.append((candidate, qty))
            total += qty

        if not resolved:
            raise AppException(
                status_code=422,
                message="Name at least one document line.",
                code="order_inquiry_no_allocations",
            )
        if total > need:
            raise AppException(
                status_code=409,
                message=(
                    f"{_qty_str(total)} allocated is more than the {_qty_str(need)} "
                    "this row still needs."
                ),
                code="order_inquiry_over_allocated",
            )

        for candidate, qty in resolved:
            self._write_link(
                row, candidate, qty, actor_user_id=actor_user_id, auto_trigger=auto_trigger
            )

        self._refresh_link_state([row])
        self.db.flush()
        self._refresh_inquiry_states({row.order_inquiry_id})
        return self.serialize_rows([row])

    def _refuse_absent_target(
        self,
        *,
        po_line_id: Optional[str],
        spo_allocation_id: Optional[str],
        product_id: str,
    ) -> None:
        """Say WHICH of the four reasons a named line is not a candidate.

        Only reached when the candidate walk did not offer it, so the row is always one of:
        gone, someone else's product, closed, or fully claimed. Each sends a person
        somewhere different, and one message covering all four sends them nowhere.
        """
        if spo_allocation_id:
            allocation = (
                self.db.query(SPOAllocation)
                .filter(SPOAllocation.id == spo_allocation_id)
                .first()
            )
            if allocation is None:
                raise AppException(
                    status_code=404,
                    message="That SPO allocation no longer exists.",
                    code="po_line_not_found",
                )
            if str(allocation.product_id) != str(product_id):
                raise AppException(
                    status_code=409,
                    message="That SPO allocation is not for this row's product.",
                    code="order_inquiry_product_mismatch",
                )
            raise AppException(
                status_code=409,
                message=(
                    "That SPO allocation is closed, received, or already fully claimed."
                ),
                code="order_inquiry_po_line_closed",
            )

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
        if str(line.product_id) != str(product_id):
            raise AppException(
                status_code=409,
                message="That purchase order line is not for this row's product.",
                code="order_inquiry_product_mismatch",
            )
        if line.line_status != "open":
            raise AppException(
                status_code=409,
                message="That purchase order line is no longer open.",
                code="order_inquiry_po_line_closed",
            )
        raise AppException(
            status_code=409,
            message=(
                "That purchase order line has nothing left on it - every unit of it is "
                "already linked to another row."
            ),
            code="order_inquiry_po_line_short",
        )

    def _linked_claims_by_target(
        self, candidates: Sequence[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Every OTHER row already linked onto these lines - a candidate's expand.

        Read straight off the links: the link IS the evidence, and reading the rows' own
        `po_line_id` would miss every second link a row holds.
        """
        target_ids = [candidate["target_id"] for candidate in candidates]
        if not target_ids:
            return {}
        rows = (
            self.db.query(OrderInquiryLink, OrderInquiryRow, ProjectSalesOrder)
            .join(OrderInquiryRow, OrderInquiryRow.id == OrderInquiryLink.row_id)
            .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == OrderInquiry.project_sales_order_id,
            )
            .filter(
                or_(
                    OrderInquiryLink.po_line_id.in_(target_ids),
                    OrderInquiryLink.spo_allocation_id.in_(target_ids),
                )
            )
            .order_by(OrderInquiryLink.linked_at.asc())
            .all()
        )
        out: Dict[str, List[Dict[str, Any]]] = {}
        for link, row, order in rows:
            key = str(link.po_line_id or link.spo_allocation_id)
            out.setdefault(key, []).append(
                {
                    "so_number": order.autocount_doc_no or order.provisional_ref,
                    "item_code": row.item_code,
                    "qty": _qty_str(_dec(link.qty)),
                    "placed_date": link.linked_at,
                }
            )
        return out

    def _narrow_to_products(self, query, product_ids: Sequence[str]):
        """`query`, narrowed to rows that could be FOR one of these products.

        The same two arms `_resolve_product_id` reads a row's product through, in the same
        order: the reconciled project line's `product_id`, and the row's own `item_code`.
        `None` when neither arm names anything, which is the caller's cue that there is
        nothing to do at all - distinct from "no narrowing", which would scan the book.
        """
        wanted = [pid for pid in product_ids if pid]
        if not wanted:
            return None
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
            return None
        return query.filter(or_(*conditions))

    def rows_needed_at(
        self, cells: Sequence[Tuple[str, Optional[str]]]
    ) -> List[str]:
        """The ids of raised rows whose demand sits at these `(product_id, warehouse_id)`
        cells - the rows that SIZED a plan line, in other words.

        `PLAN-scm-purchasing-uat-journey.md` P7. A purchase order confirmed off the plan is
        a buy for particular plan rows, and a plan row is a `(product, location)` cell whose
        Project figure is exactly the un-linked remainder of the inquiry rows this returns.
        Handing those ids to `auto_place_for_products` first is what makes the confirm link
        back to the rows that asked for it, rather than to whichever open row happens to
        have the earliest date somewhere else in the country.

        The "needed at" location is read the way `scm.committed_v` reads it, because that is
        the figure the plan row shows:

          * a row with a supply decision lands at the reconciled core line's warehouse -
            except an ORDER BACK, which lands at the DONOR location its own
            `stock_location` names (the row hangs off the borrowing line, so the core line's
            warehouse would put the hole in a warehouse that never had one);
          * a row with no decision (the CS form's own instructions) lands at the location
            the ROW states, which is the only location it has.

        A cell whose warehouse is None matches a row that resolves to no location at all -
        the same NULL the view emits and no reader joins to.
        """
        wanted = {(str(pid), str(wid) if wid else None) for pid, wid in cells if pid}
        if not wanted:
            return []
        # Narrowed to the confirmed lines' PRODUCTS before anything is fetched. Without it
        # this walks every raised row in the book to answer a question about one purchase
        # order, which on the live book is thousands of rows and their product lookups.
        query = self.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.state.in_((INQUIRY_RAISED, INQUIRY_PARTLY_LINKED)),
            OrderInquiryRow.verb.in_(_LINKABLE_VERBS),
        )
        query = self._narrow_to_products(query, [pid for pid, _wid in wanted])
        rows = query.all() if query is not None else []
        if not rows:
            return []
        product_by_row = self._resolve_product_ids_bulk(rows)

        # The core line's fulfilment warehouse, one query for the whole set.
        so_line_ids = [row.so_line_id for row in rows if row.so_line_id]
        core_warehouse: Dict[str, Optional[str]] = {}
        if so_line_ids:
            for psl_id, warehouse_id in (
                self.db.query(ProjectSalesOrderLine.id, SalesOrderLine.warehouse_id)
                .join(
                    SalesOrderLine,
                    SalesOrderLine.id == ProjectSalesOrderLine.core_sales_order_line_id,
                )
                .filter(ProjectSalesOrderLine.id.in_(so_line_ids))
                .all()
            ):
                core_warehouse[str(psl_id)] = str(warehouse_id) if warehouse_id else None

        # The warehouse each stated stock location names, keyed by (COMPANY, code).
        # `warehouses.warehouse_code` is unique per company and not globally, so a bare
        # code-to-id map keeps whichever company the query happened to return last - and
        # this pass would then claim a row for a warehouse of the wrong company, which is
        # the same mis-attribution the company scope exists to prevent.
        codes = {
            (row.stock_location or "").strip()
            for row in rows
            if (row.stock_location or "").strip()
        }
        warehouse_by_code: Dict[Tuple[Optional[str], str], str] = {}
        if codes:
            warehouse_by_code = {
                (str(company_id) if company_id else None, str(code)): str(wid)
                for code, wid, company_id in self.db.query(
                    Warehouse.warehouse_code, Warehouse.id, Warehouse.company_id
                ).filter(Warehouse.warehouse_code.in_(list(codes)))
            }

        out: List[str] = []
        for row in rows:
            product_id = product_by_row.get(row.id)
            if not product_id:
                continue
            stated = warehouse_by_code.get((
                str(row.company_id) if row.company_id else None,
                (row.stock_location or "").strip(),
            ))
            if row.supply_decision_id is None:
                warehouse_id = stated
            elif row.verb == IV_ORDER_BACK:
                warehouse_id = stated or core_warehouse.get(str(row.so_line_id or ""))
            else:
                warehouse_id = core_warehouse.get(str(row.so_line_id or ""))
            if (str(product_id), warehouse_id) in wanted:
                out.append(str(row.id))
        return out

    def resolve_link_horizon(
        self, link_up_to: Optional[date], link_horizon: Optional[str] = None
    ) -> Optional[date]:
        """The date this pass may link up to: the caller's own, the plan's, or none at all.

        `PLAN-scm-oi-handshake.md` section 11. Three answers, and until S1 of the 27 August
        review only two could be SAID: a caller that named no date got the plan's, and
        there was no way to ask for no horizon. The buyer's own empty date box therefore
        travelled as silence and came back as the plan's date, so once a plan run named a
        horizon the page could not link a far-future row at all.

          `link_horizon="none"` -> no horizon, `link_up_to` ignored.
          `link_horizon="plan"` -> the reorder plan's own (`scm.priority.plan_link_horizon`).
          `link_horizon="date"` -> `link_up_to`, which must be there.
          OMITTED               -> inferred: the date when one is given, the plan when not.

        The inferred arm is what keeps every existing caller - the CS form's own pass, a
        purchase-order confirm, the MCP - meaning exactly what it always did without
        stating anything new.
        """
        mode = (link_horizon or "").strip().lower() or None
        if mode == LINK_HORIZON_NONE:
            return None
        if mode == LINK_HORIZON_DATE and link_up_to is None:
            raise AppException(
                status_code=422,
                message="Name the date to link up to, or ask for no horizon.",
                code="order_inquiry_horizon_without_a_date",
            )
        if mode != LINK_HORIZON_PLAN and link_up_to is not None:
            return link_up_to
        from app.services.scm import priority

        return priority.plan_link_horizon(self.db)

    @staticmethod
    def _horizon_mode(link_up_to: Optional[date]) -> str:
        """What the RESULT says about the horizon it ran under (S1). `"none"` is "nothing
        was held back for a date", which a null `link_up_to` alone could not tell from "the
        plan has never named one"."""
        return LINK_HORIZON_NONE if link_up_to is None else LINK_HORIZON_DATE

    @staticmethod
    def _after_horizon(row: OrderInquiryRow, link_up_to: Optional[date]) -> bool:
        """Is this row due beyond the horizon, and therefore not this pass's to link?

        A row with NO delivery date is INSIDE it (AC-LH4): the quantity is still owed,
        nobody has said when, and refusing it a document would leave it unbought for a date
        that was never stated.
        """
        return (
            link_up_to is not None
            and row.delivery_date is not None
            and row.delivery_date > link_up_to
        )

    def auto_place_for_products(
        self,
        product_ids: Optional[Sequence[str]],
        *,
        actor_user_id: str,
        trigger: str,
        row_ids: Optional[Sequence[str]] = None,
        link_up_to: Optional[date] = None,
        link_horizon: Optional[str] = None,
        redeal_drafts: bool = False,
        include_awaiting: bool = False,
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
        very query that feeds the next run - the idempotence the three triggers all rely
        on. The doors are ACKNOWLEDGE, Link now, a purchase-order confirm and - since
        `PLAN-scm-oi-draft-links.md` R6 - the board's own confirm again. What the board's
        pass writes is a DRAFT, because its rows are `awaiting`, which is why it is safe:
        purchasing still says the word, and now they say it looking at an answer.

        `trigger` is stamped onto every placement it makes (`_apply_placement`'s
        `auto_trigger`), so "why is this placed" is always answerable from the row's own
        note - never a silent placement with nothing to show for it.

        `link_up_to` is the LINK HORIZON (section 11, captain 27 Aug): a row due AFTER it is
        left Not linked and counted on `after_horizon` rather than skipped silently, so a
        2030 order stops eating a purchase order a nearer one needed. Omitted, it is the
        reorder plan's own horizon (`resolve_link_horizon`) - a press that says nothing is
        a press under the horizon the plan planned to. A caller that genuinely wants NO
        horizon says so, with `link_horizon="none"` (S1).

        `include_awaiting` and `redeal_drafts` are the DRAFT half
        (`PLAN-scm-oi-draft-links.md` R1/R2/R6). A link on a row purchasing has not
        confirmed is a draft, so:

        * `include_awaiting` widens the gate below to awaiting rows, which is what lets the
          board's own confirm - and a purchase-order confirm, and Auto link all - find the
          documents up front rather than leaving the page blank until somebody presses
          Confirm. The links it writes read as drafts because their rows are awaiting;
        * `redeal_drafts` lets a draft MOVE, so a nearer document that has arrived since can
          take over. Only drafts: a confirmed row's link is a promise, and no automatic pass
          ever moves it (R2). The take is computed first and the old links come down only
          when there is a better answer to write in their place, so a row the horizon holds
          back, a row whose document has closed, and a row the walk lands on the same
          document again all come out of the pass exactly as they went in (B1/S4).

        Both default to false, so Confirm's own cascade and every existing caller keep the
        acknowledged-only gate they were written under.
        """
        link_up_to = self.resolve_link_horizon(link_up_to, link_horizon)
        # A row its drafts cover WHOLLY is `placed`, so a re-deal has to be able to see it:
        # moving a link that is already there is the entire point of the press. Only on a
        # re-deal, so an ordinary pass keeps walking exactly the rows it always did.
        states = (
            (INQUIRY_RAISED, INQUIRY_PARTLY_LINKED, INQUIRY_PLACED)
            if redeal_drafts
            else (INQUIRY_RAISED, INQUIRY_PARTLY_LINKED)
        )
        linkable_ack = (
            tuple(ACK_LINKABLE) + (ACK_AWAITING,) if include_awaiting else ACK_LINKABLE
        )
        query = self.db.query(OrderInquiryRow).filter(
            # PARTLY LINKED rows are in scope too, which is new with the links table: a row
            # the last pass could only half cover is exactly the row a fresh purchase order
            # should finish, and before this it left the query the moment it was touched.
            OrderInquiryRow.state.in_(states),
            OrderInquiryRow.verb.in_(_LINKABLE_VERBS),
            # ACKNOWLEDGED (or changed since), and AWAITING too when the caller is one of
            # the DRAFT doors (R6). Held HERE rather than at each caller, because it is one
            # rule and several doors: Confirm, Link now, a purchase-order confirm and the
            # board's own raise. What a link on an awaiting row MEANS is the whole
            # difference: it is a draft, and Confirm is still the buyer's word.
            OrderInquiryRow.ack_state.in_(linkable_ack),
        )
        if row_ids is not None:
            # The NAMED rows and nothing else. A product scope is right for "this purchase
            # order was just confirmed, who was waiting for this item" and wrong for "this
            # upload raised these instructions": the Order Inquiry Form's rows name items
            # half the company's open orders also name, and one CS spreadsheet must not
            # re-cascade somebody else's instructions. Wins over `product_ids`, which a
            # caller passing both would be asking two different questions with.
            wanted_rows = [row_id for row_id in row_ids if row_id]
            if not wanted_rows:
                return self._nothing_placed(link_up_to)
            query = query.filter(OrderInquiryRow.id.in_(wanted_rows))
        elif product_ids:
            narrowed = self._narrow_to_products(query, product_ids)
            if narrowed is None:
                return self._nothing_placed(link_up_to)
            query = narrowed

        rows = query.all()
        rows = self._rank_raised_rows(rows)
        # LADDER V4 (section 1d): prime the availability reader ONCE, from every product
        # this pass will ask about. `_netting` rebuilds whenever it meets a product it has
        # not seen, so a loop that met them one at a time would rebuild per row - three
        # queries each, over a growing product list, on a pass that names thousands.
        self._netting([self._resolve_product_id(row) for row in rows])

        placed_rows = 0
        allocation_count = 0
        after_horizon = 0
        products_touched: set = set()
        for row in rows:
            product_id = self._resolve_product_id(row)
            if not product_id:
                continue
            # A DRAFT this pass may re-deal: its links come down only if the walk finds
            # something better to write, so from here the row is measured as if it were
            # holding nothing (B1, review round 28 Aug). Held per ROW rather than over the
            # whole scope, because every guard below is a reason to leave a row exactly as
            # it is - and a scope-wide unplace had already taken the answer away by then.
            drafts = (
                self._links_of(str(row.id))
                if redeal_drafts and row.ack_state != ACK_ACKNOWLEDGED
                else []
            )
            need = _dec(row.qty) if drafts else self._unlinked_need(row)
            if need <= _ZERO:
                continue
            # The horizon, checked on a row that still has something to link and before any
            # candidate is read: a row already covered is not one the buyer left behind, and
            # counting it would put a number on the banner nobody could act on.
            if self._after_horizon(row, link_up_to):
                after_horizon += 1
                continue
            candidates = self._candidates_for_row(row, credit_own_links=bool(drafts))
            if not candidates:
                continue
            takes = self._cascade_take(candidates, need)
            if not takes:
                continue
            if drafts and self._same_placement(drafts, takes):
                # The best answer today is the one the row already holds. Deleting and
                # rewriting identical links would move the audit trail and append
                # "Unlinked from X; Re-dealt by <trigger>" to the note on every press
                # (S4), so a buyer pressing Auto link all twice read a row that looked
                # like it had changed document twice and had not moved at all.
                continue
            if drafts:
                self._unplace_drafts([row], trigger=trigger)
            self.place_on_po_allocations(
                row.id,
                [
                    {
                        "po_line_id": candidate["po_line_id"],
                        "spo_allocation_id": candidate["spo_allocation_id"],
                        "qty": qty,
                    }
                    for candidate, qty in takes
                ],
                actor_user_id=actor_user_id,
                auto_trigger=trigger,
            )
            # One ROW touched, however many documents it took: the row is never split any
            # more, so counting the rows the call returned would always have said 1.
            placed_rows += 1
            allocation_count += len(takes)
            products_touched.add(str(product_id))

        return {
            "placed_rows": placed_rows,
            "allocations": allocation_count,
            "products_touched": len(products_touched),
            "after_horizon": after_horizon,
            "link_up_to": link_up_to,
            "link_horizon": self._horizon_mode(link_up_to),
        }

    @staticmethod
    def _same_placement(
        links: Sequence[OrderInquiryLink],
        takes: Sequence[Tuple[Dict[str, Any], Decimal]],
    ) -> bool:
        """Would the re-deal write exactly what the row already holds? (S4)

        Compared as a MULTISET of (target, quantity): the walk may return the same
        documents in a different order and that is not a change, while two links of 5 on
        one line are not the same answer as one of 10.
        """
        held = sorted(
            (str(link.spo_allocation_id or link.po_line_id or ""), _dec(link.qty))
            for link in links
        )
        offered = sorted(
            (str(candidate["target_id"]), _dec(qty)) for candidate, qty in takes
        )
        return held == offered

    def _unplace_drafts(self, rows: Sequence[OrderInquiryRow], *, trigger: str) -> None:
        """Take the DRAFT links off these rows so the walk can deal them again (R2).

        A draft is a link whose row is not `acknowledged` - there is no state on the link
        itself (R1) - so the test is the row's own stamp and nothing else. A confirmed row
        is skipped whole: its link is a promise purchasing made, and an automatic pass that
        moved it would move a commitment nobody was asked about.

        WHY, on the row's note: `_remove_links` already writes "Unlinked from X", which
        says what happened and not why. The trigger says why, so a buyer reading a row that
        changed document overnight finds the press that did it.
        """
        touched: List[OrderInquiryRow] = []
        for row in rows:
            if row.ack_state == ACK_ACKNOWLEDGED:
                continue
            links = self._links_of(row.id)
            if not links:
                continue
            self._remove_links(row, links)
            stamp = f"Re-dealt by {trigger}"
            row.note = f"{row.note}; {stamp}" if row.note else stamp
            touched.append(row)
        if touched:
            self._refresh_link_state(touched)
            self.db.flush()
            self._refresh_inquiry_states({row.order_inquiry_id for row in touched})

    @staticmethod
    def _nothing_placed(link_up_to: Optional[date]) -> Dict[str, Any]:
        """The pass had nothing to walk. Still states the horizon it was run under, so a
        caller never has to guess which date a zero was measured against."""
        return {
            "placed_rows": 0,
            "allocations": 0,
            "products_touched": 0,
            "after_horizon": 0,
            "link_up_to": link_up_to,
            "link_horizon": ProjectOrderInquiryService._horizon_mode(link_up_to),
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

    def relink_to_matching_lines(
        self,
        po_ids: Sequence[str],
        *,
        actor_user_id: Optional[str],
        trigger: str,
    ) -> int:
        """Move each placement onto the line of ITS OWN purchase order whose warehouse fits.

        Section 3.G, AC-G3. The occupancy panel exists to show the buyer that a PO line says
        DC1 while the demand is at BRW-BB; acting on that finding means re-keying the split
        in AutoCount and uploading the book again. The book then states BRW-BB 487 + BRW 13,
        and the placements are still sitting on the line that used to be DC1 - so the finding
        the buyer just acted on is still on the screen, and the split reads as if it never
        happened. This is the step that finishes the loop: "keeps every placement attached to
        the line whose warehouse matches; none is orphaned or unplaced".

        Deliberately narrow, in four ways, because a book upload runs over thousands of
        documents and a relocation nobody asked for is worse than no relocation at all:

        * **within ONE purchase order.** A link already names this document; moving it
          between two of the document's own lines re-reads what the buyer restated. Moving it
          to a DIFFERENT document would be buying decision, and that is Link PO's job.
        * **exact location only.** The target line's warehouse must be the row's own
          `stock_location`, not a tier-2 group sibling or a pool. Anything looser would move a
          placement to a line that reads "location differs" just the same, for no gain.
        * **never off a line that already fits.** A row sitting at tier 1 is left exactly
          where it is, or every upload would churn the link audit for nothing.
        * **whole links, never split ones.** A target with less room than the placement needs
          is passed over: half a placement on a line the book has closed is the very state
          this is fixing.

        Capacity is `qty_ordered` less what OTHER links already claim, not `outstanding`. The
        history channel writes its lines closed and fully received, and this is a relocation
        rather than a promise of fresh supply - the quantity was always against this document.
        Open lines are preferred over closed ones, then the earliest expected date.

        Answers how many links moved. Idempotent: a second run finds every placement already
        at tier 1 and moves nothing.
        """
        wanted = [str(po_id) for po_id in (po_ids or []) if po_id]
        if not wanted:
            return 0
        if len(wanted) > _RELINK_BATCH:
            # A purchase-history upload names thousands of documents, and an `IN` list that
            # long is a query plan nobody wants and a parameter list some drivers refuse.
            # Chunked rather than capped: every document the upload touched is still walked.
            moved = 0
            for start in range(0, len(wanted), _RELINK_BATCH):
                moved += self.relink_to_matching_lines(
                    wanted[start:start + _RELINK_BATCH],
                    actor_user_id=actor_user_id,
                    trigger=trigger,
                )
            return moved

        lines = (
            self.db.query(PurchaseOrderLine, Warehouse.warehouse_code)
            .outerjoin(Warehouse, Warehouse.id == PurchaseOrderLine.warehouse_id)
            .filter(PurchaseOrderLine.purchase_order_id.in_(wanted))
            .all()
        )
        if not lines:
            return 0
        location_of = {
            str(line.id): (code or "").strip().upper() for line, code in lines
        }
        by_order: Dict[str, List[Any]] = {}
        for line, code in lines:
            by_order.setdefault(str(line.purchase_order_id), []).append((line, code))

        links = (
            self.db.query(OrderInquiryLink, OrderInquiryRow, PurchaseOrderLine)
            .join(OrderInquiryRow, OrderInquiryRow.id == OrderInquiryLink.row_id)
            .join(PurchaseOrderLine, PurchaseOrderLine.id == OrderInquiryLink.po_line_id)
            .filter(
                OrderInquiryLink.po_line_id.in_(list(location_of)),
                OrderInquiryRow.state != INQUIRY_CANCELLED,
            )
            .order_by(OrderInquiryLink.linked_at.asc(), OrderInquiryLink.id.asc())
            .all()
        )
        if not links:
            return 0

        # What every link claims per line, as this pass sees it - kept in step as links move,
        # so two placements cannot both be given the same 13 units. Tallied off the rows
        # already fetched above rather than fetching them again: the two queries would be
        # the same query, and a second one that drifted from the first is how a line comes
        # to be promised twice.
        claimed: Dict[str, Decimal] = {}
        for link, _row, _line in links:
            key = str(link.po_line_id)
            claimed[key] = claimed.get(key, _ZERO) + _dec(link.qty)

        moved = 0
        touched: List[OrderInquiryRow] = []
        for link, row, current in links:
            wants = (row.stock_location or "").strip().upper()
            if not wants or location_of.get(str(current.id)) == wants:
                continue
            qty = _dec(link.qty)
            candidates = [
                line
                for line, code in by_order.get(str(current.purchase_order_id), [])
                if (code or "").strip().upper() == wants
                and str(line.id) != str(current.id)
                and str(line.product_id) == str(current.product_id)
                and _dec(line.qty_ordered) - claimed.get(str(line.id), _ZERO) >= qty
            ]
            if not candidates:
                continue
            candidates.sort(
                key=lambda line: (
                    0 if line.line_status == "open" else 1,
                    line.expected_date is None,
                    line.expected_date or date.min,
                    str(line.id),
                )
            )
            target = candidates[0]
            claimed[str(current.id)] = claimed.get(str(current.id), _ZERO) - qty
            claimed[str(target.id)] = claimed.get(str(target.id), _ZERO) + qty
            link.po_line_id = str(target.id)
            # The document has not changed - only which of its lines this sits on - so the
            # link's denormalised `document` stays as it is and the claim it put up is still
            # true. What DOES need saying is why the row moved, on the row's own note, which
            # is already this feature's evidence field.
            stamp = (
                f"Moved to the {wants} line of {link.document or 'the same document'} "
                f"after the book was re-uploaded; auto: {trigger}"
            )
            row.note = f"{row.note}; {stamp}" if row.note else stamp
            # `actioned_by` / `actioned_at` are NOT touched. They say who in purchasing
            # dealt with this instruction, and a book upload is not a person dealing with
            # it - stamping the uploader there would erase the buyer who linked it and put
            # a name against work they did not do. The note is where "why did this move"
            # belongs, and it already carries the cascade's own stamp.
            touched.append(row)
            moved += 1

        if moved:
            self.db.flush()
            self._invalidate_link_cache()
            # The derived display (`po_ref` / `po_line_id`) is read off the links, so it has
            # to be restated or the row keeps naming the line it has just left.
            self._refresh_link_state(touched)
            self.db.flush()
        return moved

    def unplace(
        self, row_id: str, *, actor_user_id: str, link_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Unlink. With a `link_id` that ONE link goes; without one every link on the row
        goes, which is what the whole-row action means.

        A partly linked row can therefore give back one of its documents and keep the
        other, which is the point of the child table: before it, "unplace" was the only
        move and it took the whole placement with it.
        """
        row = self._row_or_404(row_id)
        links = self._links_of(row.id)
        if link_id:
            links = [link for link in links if str(link.id) == str(link_id)]
            if not links:
                raise AppException(
                    status_code=404,
                    message="That link no longer exists.",
                    code="order_inquiry_link_not_found",
                )
        if not links:
            raise AppException(
                status_code=409,
                message="This row is not linked to anything.",
                code="order_inquiry_not_placed",
            )
        self._remove_links(row, links)
        self._refresh_link_state([row])
        self.db.flush()
        self._refresh_inquiry_states({row.order_inquiry_id})
        return self.serialize_rows([row])[0]

    def unplace_rows(self, row_ids: Sequence[str]) -> int:
        """Bulk unlink by explicit row id - the WRITE half of "Unlink all".

        Which ids are in scope is entirely the caller's job
        (`OrderInquiryWorklistService.unplace_all` resolves them off the worklist's own
        filters, the same `_base()` the list and the summary already read, so the count a
        person confirmed and the rows this actually touches can never disagree); this
        method only ever writes, through the same `_remove_links` a single Unlink uses.

        **No merging problem left to solve.** Before the links table this had to state a
        policy about split rows - "leave each split row raised at its own quantity, do not
        merge siblings back" - because a cascade had turned one instruction into several
        and there was no reliable key that said they had ever been one. A row is never
        split now, so unlinking it simply returns it to the quantity it always had.

        Idempotent: an empty `row_ids`, or a set none of which holds a link (a second click
        after the first already ran), returns 0.
        """
        wanted = [row_id for row_id in (row_ids or []) if row_id]
        if not wanted:
            return 0
        rows = (
            self.db.query(OrderInquiryRow)
            .join(OrderInquiryLink, OrderInquiryLink.row_id == OrderInquiryRow.id)
            .filter(OrderInquiryRow.id.in_(wanted))
            .distinct()
            .all()
        )
        for row in rows:
            self._remove_links(row, self._links_of(row.id))
        if rows:
            self._refresh_link_state(rows)
            self.db.flush()
            self._refresh_inquiry_states({row.order_inquiry_id for row in rows})
        return len(rows)

    def _remove_links(
        self, row: OrderInquiryRow, links: Sequence[OrderInquiryLink]
    ) -> None:
        """Delete these links and the audit claim each one put up.

        The claim goes only when THIS link is what wrote it (`source = 'order_inquiry'`,
        held by `order_link_service.delete_own_claim`): a claim at the same identity that
        the PO history import is the source of was never this row's to make, and unlinking
        must not take somebody else's evidence down with it.
        """
        going = {str(link.id) for link in links}
        for link in links:
            document = link.document
            stamp = f"Unlinked from {document}" if document else "Unlinked"
            row.note = f"{row.note}; {stamp}" if row.note else stamp
            # By ID, not by identity. `delete_own_claim` matches on (SO number, PO number,
            # item) and would have taken down the claim behind a SIBLING link on the same
            # document - a row linked to two lines of one purchase order lost both claims
            # when one line was given back. The link records which claim it wrote, so this
            # removes exactly that one and nothing else.
            if link.claim_id:
                claim = (
                    self.db.query(OrderLinkClaim)
                    .filter(
                        OrderLinkClaim.id == link.claim_id,
                        OrderLinkClaim.source == "order_inquiry",
                    )
                    .first()
                )
                # Only when no OTHER surviving link leans on the same claim: two links on
                # one document share the one claim, because the claim's identity is the
                # document and not the line.
                if claim is not None and not (
                    self.db.query(OrderInquiryLink)
                    .filter(
                        OrderInquiryLink.claim_id == claim.id,
                        OrderInquiryLink.id.notin_(list(going)),
                    )
                    .first()
                ):
                    self.db.delete(claim)
            self.db.delete(link)
        self.db.flush()
        self._invalidate_link_cache()
        # WHO acted on this row, and when: still true while ANY link stands. Blanking it
        # on a partial unlink would have said nobody had ever touched a row that is still
        # half covered.
        if not self._links_of(row.id):
            row.actioned_by = None
            row.actioned_at = None
        self.db.flush()

    def _row_or_404(self, row_id: str) -> OrderInquiryRow:
        row = self.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).first()
        if row is None:
            raise AppException(
                status_code=404,
                message="That order inquiry row no longer exists.",
                code="order_inquiry_row_not_found",
            )
        return row

    def _assert_linkable(self, row: OrderInquiryRow) -> None:
        """Refuse a row that cannot hold a link, in the words the buyer needs.

        A PARTLY LINKED row is linkable, which is the change the child table brought: it
        still has quantity nobody has covered, and refusing it would leave that quantity
        with no way of ever reaching a document.
        """
        if row.verb not in _LINKABLE_VERBS:
            raise AppException(
                status_code=409,
                message=(
                    "Only an ORDER, RESERVE & ORDER or ORDER BACK row can be linked to a "
                    "document."
                ),
                code="order_inquiry_not_placeable_verb",
            )
        if row.state not in (INQUIRY_RAISED, INQUIRY_PARTLY_LINKED):
            raise AppException(
                status_code=409,
                message="Only a raised or partly linked row can be linked to a document.",
                code="order_inquiry_not_raised",
            )

    #: The name this check carried before section 3.I. Same call.
    _assert_placeable = _assert_linkable

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

    def link_candidate_products(
        self, product_ids: Sequence[Optional[str]]
    ) -> Dict[str, set]:
        """Which of these products still has something to link to, by KIND.

        The exact predicate `po_candidates_for_row` answers per row, computed ONCE for a
        whole listing, so the row action's offer and the dialog can never disagree.

        Two sets, because the answer depends on the ROW's verb and not only on its
        product: an ORDER row may link to a purchase order line, and an ORDER BACK row may
        link to either that or an `spo_allocations` row (part 2 section 4b). Answering with
        one set left an order back whose ONLY open cover was a shipping order reading "no
        candidate", and the screen then offered no Link at all on the one row the feature
        was built for.

        SPO- prefixed PURCHASE orders are excluded from the `po` set as they are in the
        walk: since migration 420 a shipping order is an `spo_allocations` row, and one
        still sitting in `purchase_orders` is a document nobody migrated rather than a
        candidate. The `spo` set applies `spo_supply.open_incoming_clauses`, the one copy
        of "what counts as incoming", so this flag and rung 1 cannot come to disagree.
        """
        wanted = {pid for pid in product_ids if pid}
        if not wanted:
            return {"po": set(), "spo": set()}
        by_po, by_spo = self._linked_by_target()

        # LADDER V4 (section 1d): the flag applies the SAME group-deficit rule the walk
        # does, so a row is never offered a Link that the dialog would then show as empty.
        # Per (product, group), because a product can be flush in one group and 15,514
        # short in another, and a pool-location line belongs to no group and always counts.
        # ZERO IS OFFERED and a group holding an acknowledged unlinked row is offered
        # whatever its arithmetic (captain, 27 Aug 2026) - both halves of the ruling
        # `_groups_in_deficit` and `_candidates_for_row` carry, or the row action would
        # hide the Link the dialog is about to fill. The row exemption is answered per
        # PRODUCT here, which is all a listing-wide flag has to go on: it cannot tell the
        # exempt group's own row from a neighbour's, so it errs towards offering and the
        # dialog stays the exact answer.
        po_open: Dict[str, Dict[Optional[str], Decimal]] = {}
        for line_id, product_id, qty_ordered, qty_received, warehouse_code in (
            self.db.query(
                PurchaseOrderLine.id,
                PurchaseOrderLine.product_id,
                PurchaseOrderLine.qty_ordered,
                PurchaseOrderLine.qty_received,
                Warehouse.warehouse_code,
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .outerjoin(Warehouse, Warehouse.id == PurchaseOrderLine.warehouse_id)
            .filter(
                PurchaseOrderLine.product_id.in_(list(wanted)),
                PurchaseOrderLine.line_status == "open",
                PurchaseOrder.status.in_(("active", "partial")),
                PurchaseOrder.po_number.notlike("SPO-%"),
            )
            .all()
        ):
            remaining = (
                _dec(qty_ordered) - _dec(qty_received) - by_po.get(str(line_id), _ZERO)
            )
            if remaining <= _ZERO:
                continue
            group = group_of_warehouse_code(warehouse_code)
            per_group = po_open.setdefault(str(product_id), {})
            per_group[group] = per_group.get(group, _ZERO) + remaining

        po_products: set = set()
        if po_open:
            netting = self._netting(list(po_open))
            for product_id, per_group in po_open.items():
                awaiting = self._groups_awaiting_a_link(product_id)
                for group, remaining in per_group.items():
                    if (
                        group is None
                        or group in awaiting
                        or netting.group_net(product_id, group).net + remaining >= _ZERO
                    ):
                        po_products.add(product_id)
                        break

        spo_products: set = set()
        pools = self._pool_codes()
        for allocation_id, product_id, allocated, received, warehouse_code in (
            self.db.query(
                SPOAllocation.id,
                SPOAllocation.product_id,
                SPOAllocation.allocated_quantity,
                SPOAllocation.quantity_received,
                Warehouse.warehouse_code,
            )
            .outerjoin(
                InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id
            )
            .outerjoin(Warehouse, Warehouse.id == SPOAllocation.warehouse_id)
            .filter(
                SPOAllocation.product_id.in_(list(wanted)),
                SPOAllocation.spo_number.isnot(None),
                *spo_supply.open_incoming_clauses(),
            )
            .all()
        ):
            # The POOL rule the walk applies (R11), applied here too, or the flag would
            # offer a Link the dialog then shows as empty.
            if str(warehouse_code or "").strip().upper() not in pools:
                continue
            remaining = (
                _dec(allocated) - _dec(received) - by_spo.get(str(allocation_id), _ZERO)
            )
            if remaining > _ZERO:
                spo_products.add(str(product_id))

        return {"po": po_products, "spo": spo_products}

    @staticmethod
    def has_link_candidate(
        verb: Optional[str], product_id: Optional[str], candidates: Dict[str, set]
    ) -> bool:
        """Does THIS row have anywhere to link to? Verb and product together.

        Stated once, so the per-project list, the cross-project worklist and anything else
        that prints the flag cannot each decide it differently.
        """
        if not product_id:
            return False
        if product_id in candidates.get("po", ()):
            return True
        return verb in _SPO_LINKABLE_VERBS and product_id in candidates.get("spo", ())

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
