"""Ladder v6: one order's lines for one item, one location and one delivery date are ONE
planning unit (`documentation/plans/scm/PLAN-scm-order-unit-ladder-v6.md`).

The captain, reading SO381895 on the board: lines 31 and 32, same item, same location, same
delivery date, 10 and 20. The board proposed Borrow 10 for one and Buy 20 for the other.
"This is 1 order as a whole, so we should look at the order as a whole instead of line by
line ... for the same delivery date." Each line obeyed the whole-LINE rule; the order did
not.

What is pinned here (the UAC's own numbering):

* **AC-U1** two lines of one order, one item, one location, one date: covered whole from
  stock or bought whole, never "one borrows and the other buys";
* **AC-U2** the unit draws the shared pool ONCE and the draw is split across its lines;
* **AC-U3** a different delivery date is a different unit, and v5's answer stands for it;
* **AC-U4** a different fulfilment location is a different unit;
* **AC-U5** a component that straddles two lines keeps its kind, source, rung and reason on
  both halves, and the halves sum to it;
* **AC-U6** the sheet, the freeze and the board compose one order the same way;
* **AC-U8** `unit_qty` and `unit_line_count` reach the wire on both surfaces
  (`response_model` drops what a schema does not declare);
* **AC-U9** the cross-group donor is a running ledger across the walk: the first unit
  borrows it and the later units buy whole, which is what the confirmation was refusing.

AC-U7 (every ladder v4 / v5 test passes unchanged) is the existing suites, not a test here.

Postgres via `blank_session`, every chain seeded here (CI's database has no data).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.project_so import SO_STATUS_PUBLISHED
from app.services.project_supply_service import ProjectSupplyService
from app.services.scm.front_planning_engine import qty_text

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import (  # noqa: F401  (helpers, not fixtures)
    _core_line,
    _core_so,
    _product,
    _project_line,
    _project_so,
    _sorento,
    _stock,
    _uid,
    _user,
    _warehouse,
)
from .test_ladder_v5 import _cap
from .test_project_supply_service_ladder import (
    REQUIRED_DATE,
    _group_sites,
    _spo_line,
    _world,
)

#: The second delivery date AC-U3 splits the order over. A week later, and still inside the
#: ATP reserve window, so what is being tested is the unit rule and never rung 0.
LATER_DATE = REQUIRED_DATE + timedelta(days=7)


def _seed_order(db, company_id, project, product, *, lines):
    """One core sales order and its project mirror, a line per entry.

    `lines` is a sequence of `(line_no, qty, warehouse, required_date)`. ONE core sales
    order, because the planning unit is a unit OF an order: two orders asking for the same
    item at the same location on the same day are two units and the ladder has always
    walked them as such.

    The mirror HOLDS the core order (`so_id`), which is what an adopted order looks like and
    what makes the board name these lines by the sheet's own line numbers
    (`_mirror_addressing`) rather than deriving its own.
    """
    core_so = _core_so(db, company_id)
    order = _project_so(db, project, status=SO_STATUS_PUBLISHED, so_id=core_so.id)
    mirrors = []
    for line_no, qty, warehouse, when in lines:
        core_line = _core_line(
            db, core_so, product, warehouse, qty_ordered=qty, required_date=when
        )
        mirrors.append(
            _project_line(
                db, order, line_no=line_no, product=product, core_line=core_line
            )
        )
    db.commit()
    return core_so, order, mirrors


def _sheet(db, order):
    """The sheet's lines, keyed by line number."""
    return {
        line["line_no"]: line
        for line in ProjectSupplyService(db).proposal_for(order)["lines"]
    }


def _board(db, core_so, *, as_of):
    """The board's contributions for one sales order, keyed by line number."""
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    board = FulfilmentBoardService(db).build(
        [core_so.so_number], granularity="week", as_of=as_of
    )
    return {row["line_no"]: row for row in board["contributions"]}


def _frozen(db, order):
    """What `confirm` would freeze as the engine's own proposal, keyed by line number.

    `_proposals_for` is the freeze path's own walk (`_compose_for_freeze` in the plan); its
    middle tuple member is the confirmation payload entry, which it does not read.
    """
    service = ProjectSupplyService(db)
    lines = service.lines_of(str(order.id))
    facts = service._facts_for(order, lines)
    proposals = service._proposals_for(
        order, [(line, None, facts[str(line.id)]) for line in lines], facts=facts
    )
    return {line.line_no: proposals[str(line.id)] for line in lines}


def _stated(components):
    """A composition in one vocabulary, whatever surface stated it."""
    return [
        (
            component.kind,
            qty_text(component.qty),
            component.source_location,
            component.rung,
        )
        for component in components
    ]


def _stated_sheet(line):
    return [
        (c["kind"], c["qty"], c["source_location"], c["rung"])
        for c in line["components"]
    ]


def _stated_board(contribution):
    return [
        (c["kind"], c["qty"], c["location"], c["rung"])
        for c in contribution["sources"]
    ]


# --------------------------------------------------------------------------- AC-U1


def test_two_lines_of_one_order_for_one_date_are_bought_as_one_quantity():
    """AC-U1, the captain's own case. 10 and 20 of one item at one location on one date; the
    group nets -30 and offers nothing, the pools net 0, and another group holds 12.

    Under v5 line 31 walked first, borrowed the 10 it needed whole, and line 32 then found 12
    against a need of 20 and bought. Under v6 the two lines are 30, 12 of 30 can be covered,
    and the whole unit is bought - which is what "buy all or use stock for all" means.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        donor = _warehouse(db, f"ZZTDC1-NT{_uid()[:3]}")
        _stock(db, product, donor, on_hand=12)
        _cap(db, f"zzt-v6-{_uid()[:6]}")

        _core_so, order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", own, REQUIRED_DATE),
            ],
        )
        lines = _sheet(db, order)

    assert _stated_sheet(lines[31]) == [("buy", "10", None, "buy")]
    assert _stated_sheet(lines[32]) == [("buy", "20", None, "buy")]
    for line_no in (31, 32):
        reason = lines[line_no]["components"][0]["reason"]
        assert "Only 12 of 30" in reason, (
            "the reason states what the UNIT could be covered with, not the line"
        )


def test_the_unit_is_covered_whole_when_the_ladder_reaches_the_whole_of_it():
    """AC-U1, the other half of the rule: the donor holding 30 covers both lines rather than
    neither. The unit is bought whole ONLY when the ladder cannot reach the whole of it."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        donor = _warehouse(db, f"ZZTDC1-NT{_uid()[:3]}")
        _stock(db, product, donor, on_hand=30)
        _cap(db, f"zzt-v6-{_uid()[:6]}")

        _core_so, order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", own, REQUIRED_DATE),
            ],
        )
        lines = _sheet(db, order)

    assert _stated_sheet(lines[31]) == [
        ("borrow", "10", donor.warehouse_code, "cross_group_borrow")
    ]
    assert _stated_sheet(lines[32]) == [
        ("borrow", "20", donor.warehouse_code, "cross_group_borrow")
    ]


# --------------------------------------------------------------------------- AC-U2


def test_the_unit_draws_the_pool_once_and_the_draw_is_split_in_line_order():
    """AC-U2. The site pools net 63 and this line's own pool holds all of it: the unit takes
    30 in ONE draw and the ledger is 33 for whatever asks next, never 63 twice or 43."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=63)

        _core_so, order, mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", own, REQUIRED_DATE),
            ],
        )
        lines = _sheet(db, order)

        # The ledger itself, which the payload cannot show: both members of the unit are
        # composed against the pool as it stood BEFORE the unit's own draw.
        service = ProjectSupplyService(db)
        mirror_lines = service.lines_of(str(order.id))
        facts = service._facts_for(order, mirror_lines)
        composed = service.compose_lines(
            [
                (
                    line.line_no,
                    facts[str(line.id)],
                    (
                        facts[str(line.id)].product_id,
                        str(facts[str(line.id)].warehouse.id),
                        facts[str(line.id)].required_date,
                    ),
                )
                for line in mirror_lines
            ]
        )

    assert _stated_sheet(lines[31]) == [
        ("reserve", "10", pool.warehouse_code, "pool")
    ]
    assert _stated_sheet(lines[32]) == [
        ("reserve", "20", pool.warehouse_code, "pool")
    ]
    assert composed[31][1] == Decimal("63")
    assert composed[32][1] == Decimal("63"), (
        "the second line of a unit reads the pool as the unit found it, not as the "
        "first line left it - the draw happens once, for the unit"
    )


# --------------------------------------------------------------------------- AC-U3


def test_two_delivery_dates_are_two_units_and_the_v5_answer_stands():
    """AC-U3. The same two lines a week apart: two units, walked as v5 walked them - the
    earlier one borrows the 10 it can cover whole, the later one cannot and buys."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        donor = _warehouse(db, f"ZZTDC1-NT{_uid()[:3]}")
        _stock(db, product, donor, on_hand=12)
        _cap(db, f"zzt-v6-{_uid()[:6]}")

        _core_so, order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", own, LATER_DATE),
            ],
        )
        lines = _sheet(db, order)

    assert _stated_sheet(lines[31]) == [
        ("borrow", "10", donor.warehouse_code, "cross_group_borrow")
    ]
    assert _stated_sheet(lines[32]) == [("buy", "20", None, "buy")]
    assert [lines[31]["unit_line_count"], lines[32]["unit_line_count"]] == [1, 1]
    assert [lines[31]["unit_qty"], lines[32]["unit_qty"]] == ["10", "20"]


# --------------------------------------------------------------------------- AC-U4


def test_two_fulfilment_locations_are_two_units():
    """AC-U4. One order, one item, one date, two locations of the same ownership group:
    stock does not move between locations without a transfer, so each location is planned on
    its own."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        sibling, _sibling_pool = sites["MWH"]
        donor = _warehouse(db, f"ZZTDC1-NT{_uid()[:3]}")
        _stock(db, product, donor, on_hand=12)
        _cap(db, f"zzt-v6-{_uid()[:6]}")

        _core_so, order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", sibling, REQUIRED_DATE),
            ],
        )
        lines = _sheet(db, order)

    assert [lines[31]["unit_line_count"], lines[32]["unit_line_count"]] == [1, 1]
    assert _stated_sheet(lines[31]) == [
        ("borrow", "10", donor.warehouse_code, "cross_group_borrow")
    ]
    assert _stated_sheet(lines[32]) == [("buy", "20", None, "buy")]


# --------------------------------------------------------------------------- AC-U5


def test_a_component_straddling_two_lines_keeps_its_kind_source_rung_and_reason():
    """AC-U5. The unit of 30 is covered by 5 at its own location and 25 from the pool, so the
    pool's component falls across the boundary between the lines: 5 to the first, 20 to the
    second. Both halves say the same thing, because they ARE the same component."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, own, on_hand=5)
        _stock(db, product, pool, on_hand=25)

        _core_so, order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", own, REQUIRED_DATE),
            ],
        )
        lines = _sheet(db, order)

    assert _stated_sheet(lines[31]) == [
        ("reserve", "5", own.warehouse_code, "group_take"),
        ("reserve", "5", pool.warehouse_code, "pool"),
    ]
    assert _stated_sheet(lines[32]) == [
        ("reserve", "20", pool.warehouse_code, "pool")
    ]
    first_half = lines[31]["components"][1]
    second_half = lines[32]["components"][0]
    assert first_half["reason"] == second_half["reason"]
    assert first_half["source_warehouse_id"] == second_half["source_warehouse_id"]
    assert Decimal(first_half["qty"]) + Decimal(second_half["qty"]) == Decimal("25")


# --------------------------------------------------------------------------- AC-U6


def test_the_sheet_the_freeze_and_the_board_compose_one_order_the_same_way():
    """AC-U6. Three walks, one answer. The sheet is what a planner reads on the order, the
    board is what they read across orders, and the freeze is what `confirm` writes down as
    the engine's own suggestion; a unit that composed differently on any of them would make
    the three disagree about the same promise."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=63)

        core_so, order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", own, REQUIRED_DATE),
            ],
        )
        sheet = _sheet(db, order)
        frozen = _frozen(db, order)
        board = _board(db, core_so, as_of=date.today())

    expected = {
        31: [("reserve", "10", pool.warehouse_code, "pool")],
        32: [("reserve", "20", pool.warehouse_code, "pool")],
    }
    for line_no, composition in expected.items():
        assert _stated_sheet(sheet[line_no]) == composition, f"sheet line {line_no}"
        assert _stated(frozen[line_no]) == composition, f"freeze line {line_no}"
        assert _stated_board(board[line_no]) == composition, f"board line {line_no}"


# --------------------------------------------------------------------------- AC-U8


def test_the_sheet_line_states_the_unit_it_was_planned_in():
    """AC-U8, the sheet's half, through the ROUTE: `response_model` drops a field no schema
    declares, so a service that states the unit and a schema that does not is a payload the
    screen never sees."""
    from app.models.base import company_scope

    from ..test_so_supply_confirmation import BASE, _client, _restore

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=63)
        _core_so, order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", own, REQUIRED_DATE),
            ],
        )
        client, originals = _client(db, eling)
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(f"{BASE}/sales-orders/{order.id}/supply")
        finally:
            _restore(originals)

    assert response.status_code == 200, response.text
    lines = {line["line_no"]: line for line in response.json()["lines"]}
    assert lines[31]["unit_qty"] == "30"
    assert lines[31]["unit_line_count"] == 2
    assert lines[32]["unit_qty"] == "30"
    assert lines[32]["unit_line_count"] == 2


def test_the_board_contribution_states_the_unit_it_was_planned_in():
    """AC-U8, the board's half, through the route, for the same reason."""
    from app.models.base import company_scope

    from ..test_fulfilment_board import BASE as BOARD_BASE
    from ..test_fulfilment_board import VIEW
    from ..test_fulfilment_board import _client as _board_client
    from ..test_fulfilment_board import _restore as _board_restore

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=63)
        core_so, _order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", own, REQUIRED_DATE),
            ],
        )
        client, originals = _board_client(db, eling, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BOARD_BASE}/fulfilment-planning/board",
                    params={
                        "orders": core_so.so_number,
                        "granularity": "week",
                        "as_of": date.today().isoformat(),
                    },
                )
        finally:
            _board_restore(originals)

    assert response.status_code == 200, response.text
    rows = {row["line_no"]: row for row in response.json()["contributions"]}
    assert rows[31]["unit_qty"] == "30"
    assert rows[31]["unit_line_count"] == 2
    assert rows[32]["unit_qty"] == "30"
    assert rows[32]["unit_line_count"] == 2


# --------------------------------------------------------------------------- AC-U9


def test_one_donor_is_borrowed_once_across_the_walk_and_the_later_dates_buy():
    """AC-U9, the live failure of 28 August: "0 of 1 orders confirmed ... BRW-SYNT has 0
    free, and 10 was asked for" on four lines that had each been proposed a Borrow of 10
    from a donor holding 10 in all.

    Rung 5 read the donor's free stock fresh for every line, so every delivery date was
    offered the same 10. The pool has had a running ledger across the walk since the sheet
    existed; the cross-group donor now has one too, and the dates after the first buy whole -
    which is the captain's own expectation: the donor is "occupied by the first borrow".
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        donor = _warehouse(db, f"ZZTDC1-NT{_uid()[:3]}")
        _stock(db, product, donor, on_hand=10)
        _cap(db, f"zzt-v6-{_uid()[:6]}")

        core_so, order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (1, "10", own, REQUIRED_DATE),
                (2, "12", own, REQUIRED_DATE + timedelta(days=14)),
                (3, "10", own, REQUIRED_DATE + timedelta(days=21)),
                (4, "5", own, REQUIRED_DATE + timedelta(days=28)),
            ],
        )
        board = _board(db, core_so, as_of=date.today())
        frozen = _frozen(db, order)

    assert _stated_board(board[1]) == [
        ("borrow", "10", donor.warehouse_code, "cross_group_borrow")
    ]
    assert _stated_board(board[2]) == [("buy", "12", None, "buy")]
    assert _stated_board(board[3]) == [("buy", "10", None, "buy")]
    assert _stated_board(board[4]) == [("buy", "5", None, "buy")]
    # The confirm path is the one that refused these, so it has to agree line for line.
    for line_no in (1, 2, 3, 4):
        assert _stated(frozen[line_no]) == _stated_board(board[line_no]), (
            f"the freeze and the board disagree about line {line_no}"
        )


# ------------------------------------------------------- the confirmation (review B1)


def _payload_line(line):
    """This line's own proposal, posted back unamended - what "Confirm" sends.

    Built from the sheet's own components so the test cannot invent a composition the
    engine never offered: the whole question here is whether what was PROPOSED can be
    CONFIRMED.
    """
    components = line["components"]
    return {
        "project_line_id": line["project_line_id"],
        "timely_spo_qty": qty_text(
            sum(
                (Decimal(c["qty"]) for c in components if c["kind"] == "timely_spo"),
                Decimal("0"),
            )
        ),
        "reserve": [
            {"warehouse_id": c["source_warehouse_id"], "qty": c["qty"]}
            for c in components
            if c["kind"] == "reserve"
        ],
        "borrow": [],
        "buy_qty": qty_text(
            sum(
                (Decimal(c["qty"]) for c in components if c["kind"] == "buy"),
                Decimal("0"),
            )
        ),
    }


def _confirm(db, company_id, actor, order, payload_lines):
    """POST the confirmation, the way the board and the sheet both do."""
    from app.models.base import company_scope

    from ..test_so_supply_confirmation import BASE, _client, _restore

    client, originals = _client(db, actor)
    try:
        with company_scope(db, frozenset({company_id})):
            return client.post(
                f"{BASE}/sales-orders/{order.id}/confirm", json={"lines": payload_lines}
            )
    finally:
        _restore(originals)


def test_a_unit_split_across_two_lines_confirms_exactly_as_proposed():
    """B1. The proposal is composed for the UNIT, so the recheck has to be too.

    AC-U5's own fixture: 5 on the floor, 25 in the pool, lines 31 and 32 wanting 10 and 20.
    The unit's offer is `max(group net + 30, 0)` = 5, so line 31 is proposed 5 from its own
    location; the LINE's own offer is `max(-25 + 10, 0)` = 0, and a recheck that re-derived
    it per line refused the proposal it had just made ("has nothing free for this line
    now"). A proposal that cannot be confirmed is worth nothing.
    """
    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, own, on_hand=5)
        _stock(db, product, pool, on_hand=25)

        _core_so, order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", own, REQUIRED_DATE),
            ],
        )
        lines = _sheet(db, order)
        response = _confirm(
            db, company_id, eling, order,
            [_payload_line(lines[31]), _payload_line(lines[32])],
        )

    assert response.status_code == 200, response.text
    assert response.json()["revision_no"] == 1


def test_a_unit_met_from_the_floor_and_the_water_confirms_as_proposed():
    """B1, the water half. The group nets 0 with 10 on a floor and an SPO of 20 landing in
    time, so the unit of 30 is Reserve 10 + Timely SPO 20 - and the split hands the whole of
    the water to line 32, whose own line-level water share is only 10.

    The timely cap is the UNIT's now, drawn down as its members are checked, so the two
    halves of one question cannot be counted twice and cannot refuse their own proposal.
    """
    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        _stock(db, product, own, on_hand=10)
        _spo_line(db, product, own, qty=20, arrives=REQUIRED_DATE - timedelta(days=5))
        db.commit()
        own_code = own.warehouse_code

        _core_so, order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", own, REQUIRED_DATE),
            ],
        )
        lines = _sheet(db, order)
        response = _confirm(
            db, company_id, eling, order,
            [_payload_line(lines[31]), _payload_line(lines[32])],
        )

    assert _stated_sheet(lines[31]) == [("reserve", "10", own_code, "group_take")]
    assert _stated_sheet(lines[32]) == [("timely_spo", "20", own_code, "group_take")]
    assert response.status_code == 200, response.text


# --------------------------------------------------------- the frozen proposal (S2)


def test_confirming_one_line_of_a_unit_freezes_the_proposal_the_sheet_showed():
    """S2. The frozen suggestion is what the planner was shown, so it is composed over the
    ORDER, not over the lines the payload happens to name.

    25 in the pool against a unit of 30: the sheet buys both lines whole. Confirming line 32
    on its own used to freeze "Reserve 20 from the pool" beside it - the composition of a
    line planned alone, which is not a line anybody was ever shown.
    """
    from ..test_so_supply_confirmation import _active_snapshots, _shape

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=25)

        _core_so, order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", own, REQUIRED_DATE),
            ],
        )
        lines = _sheet(db, order)
        response = _confirm(db, company_id, eling, order, [_payload_line(lines[32])])
        assert response.status_code == 200, response.text
        snapshots = {
            snapshot["line_no"]: snapshot for snapshot in _active_snapshots(db, order.id)
        }

    assert _stated_sheet(lines[32]) == [("buy", "20", None, "buy")]
    assert _shape(snapshots[32]["proposed_components"]) == _stated_sheet(lines[32])


# ------------------------------------------------------------- covered lines (S3)


def _cover(db, order, line, actor, *, components):
    """An ACTIVE revision covering one line of the order, as a confirmation leaves it."""
    from datetime import datetime

    from app.models.project_so import SOSupplyDecision

    db.add(
        SOSupplyDecision(
            id=_uid(),
            company_id=order.company_id,
            project_sales_order_id=order.id,
            revision_no=1,
            state="active",
            line_snapshots=[
                {
                    "project_line_id": str(line.id),
                    "core_line_id": str(line.core_sales_order_line_id),
                    "line_no": line.line_no,
                    "open_qty": qty_text(line.qty),
                    "components": components,
                }
            ],
            confirmed_by=actor,
            confirmed_at=datetime.utcnow(),
        )
    )
    db.commit()


def test_a_covered_line_is_out_of_the_unit_on_the_sheet_as_it_is_on_the_board():
    """S3. A covered line is not re-planned - the captain's standing rule - so it is not in
    anybody's planning unit either.

    The board already leaves it out of `proposable`; the sheet was still folding its
    quantity into the unit, so 25 in the pool covered the open line of 20 on the board and
    bought it on the sheet. Same order, same facts, two answers.
    """
    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=25)

        core_so, order, mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (31, "10", own, REQUIRED_DATE),
                (32, "20", own, REQUIRED_DATE),
            ],
        )
        _cover(db, order, mirrors[0], eling, components=[])
        sheet = _sheet(db, order)
        board = _board(db, core_so, as_of=date.today())

    assert _stated_sheet(sheet[32]) == [("reserve", "20", pool.warehouse_code, "pool")]
    assert _stated_board(board[32]) == _stated_sheet(sheet[32])
    assert sheet[32]["unit_line_count"] == 1
    assert board[32]["unit_line_count"] == 1


# ----------------------------------------------------------------- the proof (S1)


def test_the_proof_never_offers_a_donor_the_walk_has_already_spent():
    """S1. AC-U9's board, read as a planner reads it: the donor's 10 went to the first
    delivery date, so the Buy on the later ones must not say it can be borrowed.

    Question 3 was recomputing its candidate list without the walk's donor ledger, so the
    proof said "free stock at DC1-NT, within the cross-group borrow limit" beside a Buy the
    same ledger had just forced.
    """
    from ..test_fulfilment_board import _step

    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        donor = _warehouse(db, f"ZZTDC1-NT{_uid()[:3]}")
        _stock(db, product, donor, on_hand=10)
        _cap(db, f"zzt-v6-{_uid()[:6]}")

        core_so, _order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[
                (1, "10", own, REQUIRED_DATE),
                (2, "12", own, REQUIRED_DATE + timedelta(days=14)),
            ],
        )
        board = _board(db, core_so, as_of=date.today())

    took = _step(board[1], "cross_group_borrow")
    assert took["answer"] == "yes" and took["took"] == "10"
    spent = _step(board[2], "cross_group_borrow")
    assert spent["answer"] == "no"
    assert "within the cross-group borrow limit" not in spent["why"], (
        "the donor was spent by the first date, so question 3 has nothing to offer"
    )
    buy = next(source for source in board[2]["sources"] if source["kind"] == "buy")
    assert donor.warehouse_code not in buy["reason"], (
        "and the Buy must not send a planner to a donor with nothing left"
    )
