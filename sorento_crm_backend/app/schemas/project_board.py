"""The multi-order planning board's wire shapes (PLAN section 13).

Transcribed field for field from the Phase 1 types the frontend was built against
(`sorento_crm_frontend/app/(protected)/project-sales/_shared/types/fulfilmentPlanning.types.ts`).
The conventions are the ones the supply schemas next door already keep: quantities are decimal
STRINGS, and the screen reads codes rather than identifiers - sales-order NUMBER, item CODE,
warehouse CODE. The two id fields that exist (`sales_order_id` on a contribution and on a
standing) are addressing only, the same way `SupplyComponent.source_warehouse_id` is.

Two field names are deliberately camelCase, `dateBuckets` and `productRows`, and they are the
only ones. The board names its axes for what they are ON SCREEN, because the delivery-schedule
matrix next door uses `column` to mean a PRODUCT - its API's inherited word, kept even after
that grid was transposed - and two grids using one word for opposite things is worse than one
pair of odd-looking field names.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

BoardGranularity = Literal["day", "week", "month"]
BoardBucketKind = Literal["dated", "no_date"]
#: `borrow` appears on a COVERED line only. The engine never proposes one - a Borrow needs a
#: donor and a reason from a person (AC-B09) - but a line a decision already covers states the
#: composition that was frozen for it, and a frozen Borrow is a source like any other.
BoardSourceKind = Literal["reserve", "timely_spo", "buy", "borrow", "unplannable"]


class BoardDateBucket(BaseModel):
    """One column: a period, or the one column that is not a period.

    There is no aggregate for the past. Every dated line buckets by its OWN period whether that
    period is past or future, because lumping three years of late demand into one column
    destroys the schedule the board exists to show. `is_past` is how the information survives
    the lumping being removed.
    """

    key: str
    kind: BoardBucketKind
    #: What the column header reads, already formatted. `No date` is not a bucket of time at
    #: all and carries no start.
    label: str
    start: Optional[date] = None
    #: This bucket's whole period ended before `as_of`, so the screen can tint it. The period
    #: CONTAINING `as_of` is not past: some of its dates are still to come. Always false for
    #: `no_date` - an absent date has not passed, it is simply absent.
    is_past: bool = False


class BoardRankFactor(BaseModel):
    """One weighted factor behind a row's rank.

    `present: false` means the value was unknown and the factor was dropped from BOTH sums,
    never scored as zero: an unknown is not a bad score, and treating it as one is how a
    ranking starts lying. A zero WEIGHT is still reported, so "this counted for nothing" is
    visible rather than inferred.
    """

    key: str
    weight: float
    value: Optional[float] = None
    present: bool
    #: The ABSOLUTE fact behind the normalised value, as text: this line's required date, this
    #: order's document date, this customer's terms, this order's demand class. Shown FIRST,
    #: with the normalised value secondary - on its own a 0.00 beside a 1.00 explains nothing,
    #: and under a policy that weights nothing a demand row carries every score is 0.00, which
    #: reads as a broken feature rather than as a rule saying nothing. Null when absent.
    raw: Optional[str] = None


class BoardSource(BaseModel):
    kind: BoardSourceKind
    qty: str
    #: Warehouse code for a Reserve; null for Buy, which has no location by definition.
    location: Optional[str] = None
    #: Addressing only, never rendered: `POST /sales-orders/{pso_id}/confirm` names a Reserve
    #: component's warehouse by ID (`lines[].reserve[].warehouse_id`) while the screen names it
    #: by code, so the pair has to travel together. Null for Buy and for an unplannable row.
    warehouse_id: Optional[str] = None
    #: The sentence the rule wrote, shown beside the quantity. Never a bare code.
    reason: str
    spo_number: Optional[str] = None
    arrival_date: Optional[date] = None
    #: Ladder v2 (section E): which rung produced this source - `pool`, `group_take`,
    #: `group_borrow` or `cross_group_borrow`. `None` on a plain `timely_spo`/`buy` row.
    rung: Optional[str] = None
    donor_so_number: Optional[str] = None
    donor_line_no: Optional[int] = None
    donor_agent_code: Optional[str] = None
    same_agent: bool = False
    #: Addressing only, never rendered: re-identifies the donor's own core line so
    #: approving this source AS PROPOSED still checks against its live commitment.
    donor_core_line_id: Optional[str] = None
    #: The donor's own required date - the order-back's urgency (section E.4), carried
    #: so approving this source AS PROPOSED still posts it (`ConfirmBorrowComponent`
    #: takes it back), rather than making the order-back's urgency a second lookup.
    donor_required_date: Optional[date] = None


#: Ladder v2 (`PLAN-demo-followups-19aug-ladder-v2.md` section E): "incoming" now comes
#: BEFORE the pool, the own-location rung is gone (section E rule 7), and the group rungs
#: are new. `reserve_own` / `reserve_pool` are the pre-v2 spellings, kept in the Literal so
#: an old snapshot's frozen trail (there is none - the trail is never frozen - but a stale
#: client cache might still hold one) does not 422 a read.
BoardTrailKind = Literal[
    "incoming", "pool", "group_take", "group_borrow", "cross_group_borrow", "buy",
    "reserve_own", "reserve_pool", "borrow",
]
BoardTrailOutcome = Literal[
    "took", "nothing_left", "not_eligible", "offered", "none_needed"
]


class BoardAheadLine(BaseModel):
    """One line standing in front of this one at its pile, and what put it there.

    The captain, on a rung reading "18730 across 142 lines": "what does this mean? why do the
    orders stand ahead of me? why?" A total answers neither question, so the queue is NAMED -
    the top of it beside the rung, the whole of it one click away.
    """

    so_number: str
    line_no: Optional[int] = None
    qty: str
    required_date: Optional[date] = None
    rank_score: float = 0.0
    #: The policy factor with the largest weighted difference in this line's favour, which is
    #: literally the term that made its score the bigger one. `line_order` / `tie_break` when
    #: the two scores are EQUAL: the policy separated nothing there and the queue was decided by
    #: the tie-break, so naming a factor would claim a difference that does not exist.
    leading_factor: Optional[str] = None
    #: It is an earlier line of the SAME sales order. Not a rival at all, and the one case where
    #: "somebody outranks you" is the wrong sentence.
    same_order: bool = False


class BoardTrailPool(BaseModel):
    """The shared pool's pile as the pool rung saw it, in AutoCount's vocabulary.

    The captain, on a rung reading `Pool BRW | Had 0` beside an Inventory screen showing
    `Available 1`: "why it shows 0?" Two true numbers with nothing between them. `Had` (here
    `left`) is what the POOL'S OWN book ranked ahead of this line left; `available` is the
    pile's whole position. Both are printed, with the subtraction between them, so the rung
    can be checked against the stock screen instead of argued with.
    """

    location: str
    #: Addressing only, never rendered.
    warehouse_id: Optional[str] = None
    on_hand: str = "0"
    #: What the whole open book still owes at the pool, and what is on the water to it.
    so_qty: str = "0"
    spo_qty: str = "0"
    #: `on_hand - so_qty + spo_qty`, SIGNED and never clamped: an oversold pool says so.
    available: str = "0"
    reserved: str = "0"
    #: On hand less reserved less confirmed holds - what the engine may plan against.
    free: str = "0"
    #: What the pool's own orders ranked AHEAD of this line claim of that, and how many
    #: lines that is. `free - claimed_ahead_qty` is what the rung had, before earlier lines
    #: on this board drew on it.
    claimed_ahead_qty: str = "0"
    claimed_ahead_lines: int = 0
    #: What was left for THIS line when the rung was reached - the rung's own `opening`.
    left: str = "0"
    reorder_level: str = "0"
    #: The old reorder-level cap on a hot-selling line's pool draw. Always null now (19
    #: August 2026, PLAN 3.3a): dealer hot-selling offers the pool nothing and project
    #: hot-selling caps it by the pool's own availability instead. Kept for wire
    #: compatibility, never a number that would read as a limit nobody set.
    cap: Optional[str] = None


class BoardItemFlags(BaseModel):
    """The item facts the ladder judged a line on, said rather than implied.

    The captain, reading the trail: "where is the consideration of dealer hot selling /
    project hot selling / discontinued, to see if we can take from BRW?" They were consulted
    on every line and never printed - stating the flags plainly is the answer.

    Amended 19 August 2026 (PLAN 3.3a): hot-selling is now judged PER DEMAND CLASS - a SKU
    can be hot-selling on retail demand, on project demand, on both (dealer wins) or on
    neither, ranked BY QUANTITY delivered in that class in the trailing-12mo window, not by
    value. Own-location Reserve is always eligible regardless of either flag; the flags gate
    only how much the SHARED POOL contributes.
    """

    #: ABC class A by quantity on RETAIL (dealer)-classed demand (3.3a): the shared pool
    #: contributes nothing at all - it is kept for retail.
    dealer_hot_selling: bool = False
    #: The locations where it earned that, by code. Evidence, not a bare verdict.
    dealer_hot_selling_where: List[str] = []
    #: ABC class A by quantity on PROJECT-classed demand (3.3a): the shared pool contributes
    #: only while its own signed availability stays positive.
    project_hot_selling: bool = False
    #: The locations where it earned that, by code.
    project_hot_selling_where: List[str] = []
    #: Classified (a non-null letter on that class, at an active location) but not hot -
    #: "Cold at retail" / "Cold at project" in the UI's own words. `False` while the class
    #: is hot too - the hot flag above already covers it.
    dealer_classified: bool = False
    project_classified: bool = False
    #: `products.is_discontinued`: a Buy for it needs a reason at confirm, nothing more.
    discontinued: bool = False
    #: Somebody has classified this item - a NON-NULL letter on EITHER demand class - at all.
    #: False is the PLAN's "no classification" state (no delivered demand of either class in
    #: the trailing-12mo window), which is a different answer from "not hot-selling" and must
    #: not be printed as it.
    retail_classification_available: bool = True


class BoardTrailStep(BaseModel):
    """One rung of the source ladder, as it was walked for one line.

    The captain, reading a Buy: "can you justify how you arrive at the buy, like what's the
    process you have gone through: checking the available quantity first, deciding whether to
    reserve it or not, then checking the SPO quantity, then checking whether can borrow" - and
    then, on being shown a paragraph: "the justification needs to be STRUCTURED".

    So EVERY rung is emitted for a plannable line, including the ones that gave nothing: a step
    that is silently omitted reads as a step that was never taken, which is the exact doubt this
    exists to answer. A line that cannot be planned at all carries no trail, because no ladder
    was walked for it.

    The trail is a READ of what `front_planning_engine.propose_line` did. It never decides a
    quantity, so it cannot disagree with the proposal it explains.
    """

    #: 1-based, in the order the ladder walked.
    step: int
    kind: BoardTrailKind
    #: Warehouse CODE of the source. Null for Buy, which is held nowhere, and for Borrow, whose
    #: donors are several and are listed on the contribution itself.
    location: Optional[str] = None
    #: Addressing only, never rendered, exactly as on `BoardSource`.
    warehouse_id: Optional[str] = None
    #: What the source held when the ladder reached this line, BEFORE the demand ranked ahead:
    #: the pile's free stock for the own location, the running pool balance for the pool, the
    #: timely incoming total, the donors' total for Borrow. Null where the question is
    #: meaningless (Buy holds nothing; an absent pool holds nothing).
    opening: Optional[str] = None
    #: Own location only: what the demand ranked ahead of this line still wants there, and how
    #: many lines that is. Null elsewhere - the pool nets its own book before it is offered, and
    #: incoming and Buy have no queue.
    ahead_qty: Optional[str] = None
    ahead_lines: Optional[int] = None
    #: WHO is in that queue: the top of it in rank order, how many more there are, and a count
    #: of the whole queue by the factor that put each line in front. Own location only, for the
    #: same reason `ahead_qty` is - no other rung has a queue.
    ahead: List[BoardAheadLine] = []
    ahead_more: int = 0
    ahead_by_factor: Dict[str, int] = {}
    #: What this source could give THIS line after its own rules were applied.
    offered: str = "0"
    #: What the line actually took from it. Always "0" for Borrow: it is offered and never
    #: proposed, because a Borrow needs a donor and a reason from a person (AC-B09).
    taken: str = "0"
    #: The line's still-uncovered quantity after this step. Zero on the last one.
    remaining_after: str = "0"
    outcome: BoardTrailOutcome
    #: WHY it ended that way, in ONE plain sentence. The numbers above are what the captain was
    #: already looking at when he asked "what does this mean? why do the orders stand ahead of
    #: me? why? and why is the donor offered but I did not take, why?" - so this answers in
    #: words, never by restating the row.
    why: Optional[str] = None
    #: ONE short structured hint, never a paragraph: "hot-selling: pool only", "capped by
    #: reorder level 10", "ZZT-SPO-0001 arrives 2026-08-25", "MWH-IB 12000 · BRW 9000".
    note: Optional[str] = None
    #: The pool's pile behind the `reserve_pool` rung. Null on every other rung, and on a
    #: pool rung with no pile to describe (no shared pool; the pool is this location).
    pool: Optional[BoardTrailPool] = None


class BoardDecisionReserve(BaseModel):
    """One warehouse's share of a frozen Reserve."""

    warehouse_id: Optional[str] = None
    #: The warehouse CODE, which is what the screen reads. The id beside it is addressing.
    location: Optional[str] = None
    qty: str
    #: Which rung the confirmation froze this share under (`group_take` / `pool` / ...).
    #: Carried rather than dropped: without it every reserve row of a covered line reached
    #: the screen unrunged and the vocabulary had to be guessed back from the warehouse
    #: code, which is the reading PLAN section 2 exists to replace. `None` on a revision
    #: frozen before the rung was recorded.
    rung: Optional[str] = None


class BoardDecisionBorrow(BaseModel):
    """One donor of a frozen Borrow, in the words `ConfirmBorrowComponent` takes them."""

    source: str
    warehouse_id: Optional[str] = None
    location: Optional[str] = None
    donor_project_id: Optional[str] = None
    qty: str
    #: The PERSON's reason, not the rule's sentence: the confirmation refuses a Borrow that
    #: carries none, so re-posting this composition needs the one that was given.
    reason: str = ""
    #: Ladder v2 (section E.4): the donor sales-order line this Borrow named, when it was a
    #: `group_borrow`. `None` on an ordinary location/project Borrow.
    rung: Optional[str] = None
    donor_so_number: Optional[str] = None
    donor_line_no: Optional[int] = None
    donor_agent_code: Optional[str] = None
    same_agent: bool = False
    #: Addressing only, never rendered: re-identifies the donor's own line so amending a
    #: covered group-borrow line still names the SAME donor rather than posting it back as
    #: an ordinary free-stock borrow (which the own-location check, rule 7, then refuses).
    donor_core_line_id: Optional[str] = None
    #: The donor's own required date - the order-back's urgency (section E.4).
    donor_required_date: Optional[date] = None
    #: The order-back this component raised: equal to what was taken.
    order_back_qty: Optional[str] = None


class BoardLineDecision(BaseModel):
    """What the ACTIVE revision froze for this line (13.4).

    Read back off `so_supply_decisions.line_snapshots`, which is the only place a decision
    lives: the board writes nothing and holds no decision object of its own. It is the whole
    composition rather than a summary of it, because the board's Confirm re-posts it verbatim -
    a later confirmation on the same order covers the UNION of what was decided before and what
    is being decided now, and a summary could not be posted back.
    """

    revision_no: int
    confirmed_at: Optional[datetime] = None
    timely_spo_qty: str = "0"
    reserve: List[BoardDecisionReserve] = []
    borrow: List[BoardDecisionBorrow] = []
    buy_qty: str = "0"
    #: The reason a discontinued product is still being bought (AC-B11), when one was given.
    buy_reason: Optional[str] = None
    #: Why the composition is not the engine's, in the planner's own words. Absent when they
    #: took the proposal as it stood.
    amend_reason: Optional[str] = None


class BoardLineOrderInquiry(BaseModel):
    """The order inquiry covering one board line, in the two words a person reads it by.

    The ROW's state, not the header's: "purchasing placed this line" is what the column
    answers, and a header still at `raised` while its row has been placed on a purchase
    order would say the opposite.
    """

    #: `OI-000123`. Null only on a row raised before inquiries were numbered.
    inquiry_no: Optional[str] = None
    state: str


class BoardLineLending(BaseModel):
    """One borrow taken OFF this line by another sales order (AC-L6)."""

    #: How much was taken.
    qty: str
    #: The order that took it, by its document number - never a UUID.
    so_number: Optional[str] = None
    #: Its line on that order, so two lines of one order are told apart.
    line_no: Optional[int] = None


class BoardProposed(BaseModel):
    """What the engine suggested for one line, in the same words a source is stated in.

    A wrapper rather than a bare list, so the suggestion has somewhere to grow a fact ABOUT
    itself (when it was frozen, which revision) without every reader re-shaping.
    """

    components: List[BoardSource] = []


class BoardContribution(BaseModel):
    """One contributing sales-order line inside a cell: a row of the breakdown table."""

    #: Stable draft key, and part of the contract because the frontend rebuilds it:
    #: `${sales_order_id}|${line_no}|${item_code}|${bucket_key}`. Addressing only.
    key: str
    sales_order_id: str
    #: The CORE sales-order line id, which is how the pile queue is addressed
    #: (`GET .../fulfilment-planning/queue?line_id=`). Addressing only, never rendered. NOT the
    #: same as `project_line_id`: that is the mirror, and a line with no mirror still stands in
    #: the queue at its pile.
    line_id: Optional[str] = None
    #: The product, for the same drill-down and by the same rule as `BoardCellLocation`: two
    #: products on the live book share the item code `B2155-NL-BLUE`, so a pile looked up by
    #: code would be the wrong pile. Addressing only, never rendered.
    product_id: Optional[str] = None
    #: The MIRROR line id, which is how `confirm` names a line (`lines[].project_line_id`):
    #: the service builds its index from the planning record's own lines and refuses anything
    #: else. NULL until somebody adopts this sales order - there is no planning record yet, and
    #: a null is the honest answer rather than an absent key the screen has to interpret.
    project_line_id: Optional[str] = None
    so_number: str
    customer_name: Optional[str] = None
    #: Addressing only, and what a pivot BY CUSTOMER groups on: two different customers can
    #: carry the same name, and grouping by the label would merge them.
    customer_id: Optional[str] = None
    #: Who sold it (`sales_orders.sales_agent_id` -> `sales_agents.sales_agent`). The code the
    #: sales-order book carries; null on a line the upload could not resolve to one.
    agent_code: Optional[str] = None
    #: Who the code belongs to (`sales_agents.person_label`), when the master states one.
    #: Shown as the code's `title`, never in place of the code.
    agent_label: Optional[str] = None
    project_label: Optional[str] = None
    #: What a pivot BY PROJECT groups on: the project string, normalised. An order adopted from
    #: the AutoCount book has no project registration by design, so the string is the only
    #: identity a project has here.
    project_key: Optional[str] = None
    line_no: int
    item_code: str
    qty: str
    #: What the customer ordered on this line, what has gone out, and what is still owed.
    #: Three names rather than one `qty`, because they differ the moment a delivery is
    #: part-made and the board plans against the last of them.
    qty_ordered: str = "0"
    qty_delivered: str = "0"
    qty_outstanding: str = "0"
    #: What the engine proposes to meet it with, from the SAME ladder the per-order sheet runs
    #: (own location, then the shared pool under the hot-selling rules, then timely incoming,
    #: then Buy). The three add up to `qty_outstanding`.
    qty_proposed_reserve: str = "0"
    qty_proposed_incoming: str = "0"
    qty_proposed_buy: str = "0"
    # ---- why the Reserve is the size it is, in the strip's vocabulary ----
    #: What the demand ranked AHEAD of this line at its own pile still wants, and how many
    #: lines that is. The active policy decides the order; required date is the tie-break.
    #:
    #: NULL, never zero, on a line an active decision covers: such a line is not in the queue
    #: at all (`_pile_book` leaves it out, because its claim is already expressed as a hold),
    #: and "0 left for this line" is a claim about a contest it is not in. Absent is the only
    #: honest answer, and the screen says nothing rather than something false.
    so_qty_ahead: Optional[str] = None
    lines_ahead: Optional[int] = None
    #: What was LEFT AT THIS LINE'S OWN LOCATION when it was reached: on hand, less reserved,
    #: less what confirmed decisions hold, less `so_qty_ahead`. Three numbers live near each
    #: other and none may be printed as another:
    #:   * the strip's `available_qty` is the WHOLE pile's position (on hand - all SO + all SPO);
    #:   * this is what was left for THIS line at its own location;
    #:   * `qty_proposed_reserve` is what the line actually took - which can EXCEED this one,
    #:     because the shared pool is a second source with a queue of its own.
    #: Null on a covered line, for the reason given on `so_qty_ahead`.
    available_to_this_line: Optional[str] = None
    #: What could be borrowed instead of bought, and from where. Borrow is never proposed on
    #: either surface - it needs a donor and a reason from a person - but a Buy printed with no
    #: mention of it reads as "this stock exists nowhere".
    qty_borrow_available: str = "0"
    borrow_candidates: List[BorrowCandidate] = []
    #: The line's REAL required date, never the bucket it landed in.
    required_date: Optional[date] = None
    #: This line's own date is behind `as_of`. Per LINE, which is what a "N of M lines are past
    #: their required date" summary counts: a line dated yesterday is past even when the week
    #: it sits in has not ended, so the bucket flag alone would undercount it.
    is_past: bool = False
    fulfilment_location: Optional[str] = None
    #: The same warehouse by ID, addressing only. Needed on the LINE and not merely on the
    #: sources: an amendment that reserves on a line the engine proposed nothing for has no
    #: Reserve source to read a warehouse off, and inventing one from the code would be
    #: guessing at an id. Null for an unplannable line, which names no location at all.
    fulfilment_warehouse_id: Optional[str] = None
    #: The sales-order line states no location, so it cannot be planned (AC-FP16).
    unplannable: bool = False
    priority: Optional[str] = None
    rank_score: float
    rank_factors: List[BoardRankFactor] = []
    sources: List[BoardSource] = []
    #: What the ENGINE suggested for this line, beside what was decided (AC-D2).
    #:
    #: The LIVE ladder on an undecided line (the same list as `sources`), and the composition
    #: frozen at confirm on a covered one - where `sources` states the DECISION and the
    #: suggestion would otherwise be lost the moment somebody amended it. Null, never an
    #: empty object, on a revision written before the proposal was frozen: "not recorded" and
    #: "the engine suggested nothing" are different answers and the screen says which.
    proposed: Optional[BoardProposed] = None
    #: The ladder, rung by rung, in the order it was walked (see `BoardTrailStep`). Empty for a
    #: line that cannot be planned: no ladder was walked for it.
    trail: List[BoardTrailStep] = []
    #: The item facts the ladder judged this line on. Null, never a set of `false`s, on a
    #: line the ladder did not walk (unplannable, covered): it was judged against nothing.
    item_flags: Optional[BoardItemFlags] = None
    #: The supply this row would otherwise have had was taken by a row served before it.
    #: Always false on a covered line: a decided line is not competing for anything.
    contested: bool = False
    #: An ACTIVE decision on this line's sales order already covers it (13.4).
    #:
    #: The board went on proposing for such a line - "Buy 43" beside a decision that had
    #: borrowed 10 and bought 33 - because it kept the line in its demand while the pile's
    #: queue rightly left it out. A covered line is not re-planned: it states what was frozen
    #: and offers Amend, which is the only decision left to take about it.
    covered: bool = False
    #: What was frozen, when the line is covered. Null otherwise, and never an empty object:
    #: "nobody decided this" and "decided, to nothing" are different answers.
    decision: Optional[BoardLineDecision] = None
    #: What purchasing was already TOLD about this line, reached through the planning
    #: record's mirror (`projects.sales_order_lines.core_sales_order_line_id`), and how far
    #: they got with it.
    #:
    #: The other half of `decision`: that is the promise, this is the instruction the
    #: promise produced. Null when nobody has raised one - which is most of the board, since
    #: an inquiry exists only once somebody has confirmed supply - and never an empty
    #: object, by the same rule `decision` follows.
    order_inquiry: Optional[BoardLineOrderInquiry] = None
    #: What ANOTHER sales order borrowed off THIS line (AC-L6, the captain 25 August 2026:
    #: the donor's cell reads "71 lent to SO415472"). A borrow used to be visible only on the
    #: taking side, so the agent whose stock moved found out when the delivery did not.
    #: An empty list when nothing was lent, never absent: the cell has one shape to read.
    lent_to: List[BoardLineLending] = Field(default_factory=list)


class BorrowDonorImpact(BaseModel):
    """What borrowing this quantity does to whoever is holding it now (AC-B09)."""

    free_before: str
    free_after_full_borrow: str
    #: Already committed to another sales order at that location.
    committed_qty: str


class BorrowCandidate(BaseModel):
    """Where a Buy could be borrowed from instead. Offered, never proposed (AC-B09).

    The same four facts the sheet's candidate carries, because the board now COMPOSES a
    Borrow rather than only mentioning that one is possible: `ConfirmBorrowComponent` takes a
    `warehouse_id` and a `donor_project_id`, and neither can be resolved from a warehouse code
    on the client without guessing at an id. A donor that can only be read is a donor that
    cannot be used, which is what a narrower copy of this shape made it.
    """

    source: str
    warehouse_code: str
    #: Addressing only, never rendered: the screen names warehouses by code and the confirm
    #: payload names them by id.
    warehouse_id: Optional[str] = None
    donor_project_ref: Optional[str] = None
    donor_project_id: Optional[str] = None
    #: What this donor can give: the location's free stock, or the donor project's own hold.
    free_qty: str
    #: AutoCount's Stock Status columns for the DONOR's own pile, so the planner can see
    #: whether taking from them hurts (PLAN 13.11). `available_qty` is SIGNED.
    qty_on_hand: Optional[str] = None
    so_qty: Optional[str] = None
    spo_qty: Optional[str] = None
    available_qty: Optional[str] = None
    qty_free: Optional[str] = None
    qty_committed: Optional[str] = None
    #: This line's residual at the borrow rung, and what the donor keeps once it is met.
    #: `available_after_need` is the ranking key and is signed.
    need_qty: Optional[str] = None
    available_after_need: Optional[str] = None
    #: First in the ranking - the donor this borrow hurts least. Exactly one row carries it.
    recommended: bool = False
    #: Absent only on a payload built before this field existed; the engine always states it.
    donor_impact: Optional[BorrowDonorImpact] = None
    #: Ladder v2 (section E): `group_borrow` or `cross_group_borrow` for a new group-aware
    #: donor row, `None` for a plain `other_location`/`other_project` donor.
    rung: Optional[str] = None
    donor_so_number: Optional[str] = None
    donor_line_no: Optional[int] = None
    donor_agent_code: Optional[str] = None
    donor_core_line_id: Optional[str] = None
    lower_ranked: bool = False
    same_agent: bool = False
    over_cap: bool = False
    cap_reason: Optional[str] = None


class StockDetailSalesOrder(BaseModel):
    """One document contributing to a location's SO Qty, as AutoCount's drill-down lists it."""

    sales_order_id: str
    so_number: str
    customer_name: Optional[str] = None
    customer_id: Optional[str] = None
    #: Who sold it. Null for a purchase-order row (`StockDetailIncoming`), which is not a
    #: sales document and carries no agent by construction.
    agent_code: Optional[str] = None
    project_label: Optional[str] = None
    demand_class: Optional[str] = None
    #: The document's own date, and the date the quantity is wanted.
    doc_date: Optional[date] = None
    delivery_date: Optional[date] = None
    so_qty: str
    #: A confirmed decision already covers this line: committed demand, not merely outstanding.
    is_covered: bool = False
    #: The CORE sales-order line this document row IS. Addressing only: one order stands
    #: behind a location once per line, so the order id alone does not name a row.
    line_id: Optional[str] = None
    line_no: Optional[int] = None
    #: Where this line stands in the pile's queue (1-based, `pile_book` order) and the score
    #: that put it there, with the same per-factor breakdown the queue screen shows. Null on a
    #: covered line: its claim is already a hold, so it is not in the queue at all.
    rank_position: Optional[int] = None
    rank_score: Optional[float] = None
    rank_factors: List[BoardRankFactor] = []


class StockDetailIncoming(BaseModel):
    """One undelivered supply-PO allocation: AutoCount's PO Qty, which in Sorento is the SPO."""

    spo_number: Optional[str] = None
    supplier_name: Optional[str] = None
    expected_date: Optional[date] = None
    spo_qty: str


class StockDetail(BaseModel):
    """`GET /project-sales/fulfilment-planning/stock-detail`.

    AutoCount's Stock Status with Detail for one product at one location: the four totals, and
    every document behind them. The lists ADD UP to the totals by construction - both are
    summed from the same rows - so the drill-down can never justify a number the strip did not
    print.
    """

    product_id: str
    item_code: str
    description: Optional[str] = None
    warehouse_id: str
    location: str
    qty_on_hand: str
    #: What the whole book still owes here, by the shared `is_open_demand()` rule, every demand
    #: class: a dealer order occupies the stock as completely as a project one.
    so_qty: str
    spo_qty: str
    #: `on hand - SO + SPO`, SIGNED. A negative is the point, not an error.
    available_qty: str
    qty_reserved: str
    qty_held_by_decisions: str
    qty_free: str
    sales_orders: List[StockDetailSalesOrder] = []
    incoming: List[StockDetailIncoming] = []
    #: The `scm.priority_policy` the ranks in `sales_orders` came from.
    policy_name: Optional[str] = None


class PileQueueLine(BaseModel):
    """One line of the queue at a pile, with the rank that put it where it is."""

    #: 1-based, in the order the stock is served.
    position: int
    #: The CORE sales-order line. Addressing only.
    line_id: str
    #: The sales order it belongs to, so the screen can link to it. Addressing only.
    sales_order_id: Optional[str] = None
    so_number: str
    #: Null until the order has been adopted onto a planning record: an un-mirrored line has no
    #: line number of its own, and inventing one would name a line that does not exist.
    line_no: Optional[int] = None
    customer_name: Optional[str] = None
    qty: str
    required_date: Optional[date] = None
    order_date: Optional[date] = None
    payment_terms_days: Optional[int] = None
    demand_class: Optional[str] = None
    rank_score: float = 0.0
    #: The same per-factor breakdown a board row carries, so one row's rank popover explains a
    #: queued line exactly as it explains a contributor.
    rank_factors: List[BoardRankFactor] = []
    #: Which factor puts this line in front of the line that ASKED. Null for the asked line
    #: itself, and null when nobody asked.
    leading_factor: Optional[str] = None
    #: What the queue has claimed by the time it has served this row, this row included.
    cumulative_ahead_qty: str = "0"
    is_this_line: bool = False
    #: Always false on a row that is here: a line an active decision covers is EXCLUDED from
    #: the queue, because its claim already came out of the opening stock as a hold and
    #: counting it again would subtract the same units twice.
    is_covered_excluded: bool = False


class PileQueue(BaseModel):
    """`GET /project-sales/fulfilment-planning/queue`.

    Who is standing in front of this line at its pile, and why. The captain: "I need to know
    what is ahead of me to have the visibility, and why they are ahead of me, meaning I need to
    know their rank also."

    The SAME queue the trail counted (`_pile_book`), never a second ranking of one pile: two
    orderings of the same stock would eventually disagree, and then the screen would be arguing
    with the plan it is explaining.
    """

    product_id: str
    item_code: str
    description: Optional[str] = None
    warehouse_id: str
    location: str
    #: What the pile held before the queue drew on it - the trail's own opening figure.
    qty_free_opening: str
    #: Where the asked-about line stands. Null when no line was named.
    this_line_position: Optional[int] = None
    #: The rule that produced this order, named. It is the LIVE policy: the queue is what the
    #: stock is actually served in, and a previewed weighting has not served anything.
    policy_name: str
    lines: List[PileQueueLine] = []


class BoardCellLocation(BaseModel):
    """One (product, location) of a cell: what is owed there, and what is actually there.

    The strip used to read "BRW-BB 22" with 22 being the DEMAND, which is the one reading
    nobody guessed. Every number is now named, and the stock facts sit beside the demand.

    Every stock figure is null (never zero) for the location-less row of a line whose sales
    order states no warehouse: there is no location whose stock could be counted, and a zero
    would read as "that location is empty".
    """

    location: Optional[str] = None
    #: Where this location stands relative to the cell: `own` (a location the cell's own lines
    #: name), `group` (the sales agent's ownership group), `site_pool` (a pool the ladder drew
    #: from and a proposal cites) or `other_group` (outside the group, where a Borrow was
    #: proposed from). The table lists every location the ladder consulted, so this is what
    #: tells the pool holding 1716 from a group warehouse holding nothing.
    where: str = "own"
    #: Addressing only: what the stock drill-down is opened by. Never rendered, and never
    #: derived on the client from a warehouse code or an item code.
    product_id: Optional[str] = None
    warehouse_id: Optional[str] = None
    #: The demand, under the name the frontend's source strip already reads.
    qty: str
    #: The same number, said unambiguously.
    qty_demand: str
    qty_on_hand: Optional[str] = None
    qty_reserved: Optional[str] = None
    #: What this engine may actually use: on hand, less reserved, less what confirmed decisions
    #: already hold. The figure the proposal was computed from.
    qty_free: Optional[str] = None
    #: Of that, what was still unclaimed when THIS cell's lines were served - earlier dates
    #: draw first, so a December cell can face a smaller pile than `qty_free` suggests.
    qty_free_remaining: Optional[str] = None
    #: What confirmed decisions are holding here. On hand, less reserved, less this, IS
    #: `qty_free` - the third term of that arithmetic, printed so the sum closes on screen.
    qty_held_by_decisions: Optional[str] = None
    #: What the WHOLE BOOK still owes at this location: every open line of every open sales
    #: order, not merely the ones on this board, by the shared `is_open_demand()` rule. Without
    #: it "478 free" reads as "478 available to me" while 47,009 is owed at that location.
    qty_owed_all_orders: Optional[str] = None
    #: Of that, the part a confirmed decision already covers (per LINE, the rule
    #: `scm.committed_v` applies), so committed pressure can be told from uncommitted.
    qty_owed_confirmed: Optional[str] = None
    #: Allocated on a supply PO and not yet received, at this location.
    qty_incoming: Optional[str] = None
    # ---- AutoCount's Stock Status vocabulary, which is the strip's first line ----
    #: "SO Qty": the same number as `qty_owed_all_orders`, under the word the planner uses.
    so_qty: Optional[str] = None
    #: "PO Qty" in AutoCount is the supplier order; in Sorento that is the SPO.
    spo_qty: Optional[str] = None
    #: "Available Qty": `on hand - SO + SPO`, SIGNED and never clamped - "oversold here by 632"
    #: is the signal, and a floor of zero would report it as "nothing left" instead.
    available_qty: Optional[str] = None
    #: "PO qty": the open PURCHASE-order balance at this location, less what an order-inquiry
    #: row already claims off those lines. SPO documents are excluded - they are already
    #: `spo_qty`, and counting them twice would invent supply.
    #:
    #: INFORMATION ONLY, and deliberately outside `available_qty`: a purchase order reaches a
    #: project line through a link, never by sitting at the location (PLAN section I).
    po_open_qty: Optional[str] = None
    #: LADDER V4 (`PLAN-scm-cs-planning-uat.md` section 1d): what the SET this row belongs
    #: to nets between its locations, signed - the ownership group for an `own` / `group`
    #: row, the five site pools for a `site_pool` row, and the donor group's own net for an
    #: `other_group` row. THE NUMBER THE ENGINE ACTUALLY DECIDED ON: `MWH-IB` reading 7000
    #: available offers nothing while the IB group nets -15514, so a table that showed only
    #: the per-row figure could not explain why nothing was taken from it.
    #:
    #: Stated by the server rather than summed on the client, because the rows shown are the
    #: ones this cell consulted and the net is over the whole set, `RSW-IB` and every other
    #: silent member included.
    net: Optional[str] = None
    #: Which set that net is over, for the subtotal's own label: the group code (`IB`),
    #: `pools`, or None where no set applies.
    net_of: Optional[str] = None
    incoming: List["BoardIncoming"] = []
    qty_proposed_reserve: str = "0"
    qty_proposed_incoming: str = "0"
    qty_proposed_buy: str = "0"


class BoardIncoming(BaseModel):
    """One undelivered supply-PO allocation: how much, when, and on which document."""

    spo_number: Optional[str] = None
    arrival_date: Optional[date] = None
    qty: str


class BoardCell(BaseModel):
    item_code: str
    bucket_key: str
    #: Summed across every contributing line, including the unplannable ones.
    total_qty: str
    #: The sales agents' warehouse-suffix ownership group whose locations are listed below
    #: alongside the ones this cell's own lines name (`BB` for BRW-BB / MWH-BB / DC1-BB).
    #: Several, joined by " / ", when the cell holds orders of agents in different groups.
    #: None when none could be resolved, and then `location_group_note` says why - silence
    #: would read as "this product lives in exactly one place".
    location_group: Optional[str] = None
    #: Why only the line's own location is listed, when that is all there is. Set ONLY when
    #: `location_group` is None.
    location_group_note: Optional[str] = None
    locations: List[BoardCellLocation] = []
    contributions: List[BoardContribution] = []
    unplannable_count: int = 0
    contested_count: int = 0
    #: Contributions whose own required date is already past.
    past_count: int = 0
    #: How many DISTINCT sales orders contribute here, and whether the ranking told any two of
    #: these rows apart. "The active policy separates none of these rows" is TRUE of a cell
    #: holding a single line, and of a cell holding several lines of one order, and in both
    #: cases it reads as a policy failure when nothing failed. These say which case it is.
    distinct_order_count: int = 0
    rank_separates: bool = False


class BoardProductRow(BaseModel):
    item_code: str
    description: Optional[str] = None


class BoardOrderStanding(BaseModel):
    sales_order_id: str
    #: The planning record this order's confirmation posts to
    #: (`POST /project-sales/sales-orders/{pso_id}/confirm`). NULL when nobody has adopted the
    #: sales order yet, which is what lets the screen state that rather than guess it.
    project_sales_order_id: Optional[str] = None
    so_number: str
    customer_name: Optional[str] = None
    line_count: int
    #: Always 0 from the server: the verdicts live in the board's client draft (13.4).
    decided_count: int = 0
    unplannable_count: int = 0


class BoardPolicy(BaseModel):
    """The `scm.priority_policy` row a board was ranked by. Named on screen, never assumed."""

    name: str
    factors: Dict[str, float] = {}
    demand_class_weights: Dict[str, float] = {}
    #: A what-if the planner asked for rather than the row that is live. A previewed ranking
    #: is labelled and may never be committed against.
    is_preview: bool = False
    #: This policy cannot separate these rows at all - every weighted factor is absent, or
    #: holds one value across the whole board. Reported rather than left to be inferred: the
    #: live seeded rule weights only `po_document_sequence`, which no sales-order line can
    #: carry, so every row scores 0.0 and a flat ranking would otherwise read as a considered
    #: one (13.5).
    discriminates_nothing: bool = False


class PlanningBoard(BaseModel):
    """`GET /project-sales/fulfilment-planning/board`. A pure read: opening it claims nothing."""

    model_config = ConfigDict(populate_by_name=True)

    granularity: BoardGranularity
    policy: BoardPolicy
    #: The date the board was built against, so which periods read as past is reproducible
    #: rather than whatever the client's clock said.
    as_of: date
    date_buckets: List[BoardDateBucket] = Field(default=[], alias="dateBuckets")
    product_rows: List[BoardProductRow] = Field(default=[], alias="productRows")
    cells: List[BoardCell] = []
    orders: List[BoardOrderStanding] = []
    #: Every contributing line of the SELECTION, in the same `BoardContribution` shape a cell
    #: carries, but never windowed: at day granularity `cells` only covers the 30 days on
    #: screen (`DAY_WINDOW_COLUMNS`), and a line outside that window is still fully proposed
    #: (allocation runs over the whole selection - see `build`'s docstring) even though no cell
    #: shows it. Approve all, the "N approved - M undecided" strip, the List view and the
    #: confirm-all call all need EVERY decidable line, not only the ones currently rendered in
    #: the grid, so they read this list rather than flattening `cells`.
    contributions: List[BoardContribution] = []

    # ---- selection-scoped totals -------------------------------------------------
    #
    # Counted over every contributing line of the SELECTION, before any window is applied.
    # Read these for a banner; never sum the cells on screen for one.
    #
    # The difference bites at day granularity. The 30-column window opens on work still to
    # come, so it holds no past cell at all: a banner summing `BoardCell.past_count` reads
    # "143 of 153 lines are already past their required date" at week and month and then
    # DISAPPEARS at day, losing the most important number on the board exactly when the
    # planner is looking closest.
    #: Contributing lines in the selection.
    line_count: int = 0
    #: Of those, the ones whose own required date is behind `as_of`.
    past_line_count: int = 0
    #: Of those, the ones whose sales order states no fulfilment location (AC-FP16).
    unplannable_line_count: int = 0
    #: Of those, the ones the ranking could not cover because a higher-ranked line took the
    #: supply first. Allocation runs over the whole selection, not over the window, so this is
    #: the selection's contest count on every granularity.
    contested_line_count: int = 0
