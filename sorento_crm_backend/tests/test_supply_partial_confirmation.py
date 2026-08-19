"""Partial confirmation: the planner commits the lines they have decided (PLAN 13.4).

> "we shouldn't block the confirm when the decision for the order are incomplete yet, we
>  might want to flow a few product to reorder planning first"   (captain, 18 August 2026)

Stage 1C's confirmation is atomic over every line of the ORDER (AC-C01). This slice makes
it atomic over every line of THIS CONFIRMATION, chosen by the planner, and leaves the rest
EXPLICITLY undecided - never implicitly zero and never implicitly covered - so their demand
keeps flowing to reorder planning (the view half of that is
`tests/test_partial_decision_demand_invariants.py`).

The shape is 13.4's option (B): one active decision per order, `line_snapshots` covering a
SUBSET of its lines. No key, no index and no revision rule changes.

Postgres via `tests/_pg_fixture.py::blank_session`, seeding its own chain, per PRINCIPLES.
The seeding helpers are imported from the Stage 1C suite next door rather than copied, so
the two files cannot come to disagree about what a Project SO looks like.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.project_so import SOSupplyDecision

from .test_so_supply_confirmation import (  # noqa: F401  (api is a fixture)
    BASE,
    _core_line,
    _core_so,
    _line_payload,
    _project_line,
    _project_so,
    _stock,
    _uid,
    _warehouse,
    api,
)


def _decision(db, order, *, state="active"):
    return (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.state == state,
        )
        .order_by(SOSupplyDecision.revision_no.desc())
        .first()
    )


def _two_line_order(world):
    """One project SO, two lines, 50 and 30 open, enough stock to reserve either."""
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=100)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    core_2 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="30")
    line_1 = _project_line(db, order, line_no=10, product=world.product, core_line=core_1)
    line_2 = _project_line(db, order, line_no=20, product=world.product, core_line=core_2)
    db.commit()
    return order, line_1, line_2


# ------------------------------------------------------------------ the confirmation


def test_confirming_one_line_of_a_two_line_order_is_accepted(api):
    """The captain's decision: an incomplete order confirms the part that is decided."""
    client, world = api
    db = world.db
    order, line_1, _line_2 = _two_line_order(world)

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert response.status_code == 200, response.text

    decision = _decision(db, order)
    assert decision is not None
    assert decision.revision_no == 1
    assert len(decision.line_snapshots) == 1, (
        "the decision covers the line that was confirmed, and only that one"
    )
    assert decision.line_snapshots[0]["project_line_id"] == str(line_1.id)


def test_the_result_says_how_much_of_the_order_is_decided(api):
    """The counter stays as information (13.4): it no longer disables anything, and it is
    the only honest way to say a confirmed order is not a finished one."""
    client, world = api
    order, line_1, _line_2 = _two_line_order(world)

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lines_decided"] == 1
    assert body["lines_undecided"] == 1


def test_an_undecided_line_reads_as_undecided_on_the_sheet(api):
    """Explicitly undecided, never implicitly zero and never implicitly covered."""
    client, world = api
    order, line_1, line_2 = _two_line_order(world)

    confirmed = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert confirmed.status_code == 200, confirmed.text

    sheet = client.get(f"{BASE}/sales-orders/{order.id}/supply")
    assert sheet.status_code == 200, sheet.text
    body = sheet.json()
    assert body["lines_total"] == 2
    assert body["lines_decided"] == 1

    by_line = {line["project_line_id"]: line for line in body["lines"]}
    assert by_line[str(line_1.id)]["decided"] is True
    assert by_line[str(line_1.id)]["frozen"] is not None
    assert by_line[str(line_2.id)]["decided"] is False
    assert by_line[str(line_2.id)]["frozen"] is None, (
        "an undecided line states no frozen composition, because nobody froze one"
    )
    assert by_line[str(line_2.id)]["open_qty"] == "30", (
        "and it still states its whole open quantity, which is what keeps flowing to "
        "reorder planning"
    )


def test_the_reason_an_amendment_gives_is_frozen_with_the_line(api):
    """A planner who overrides the engine says why, and the snapshot has to keep it.

    On the board an amendment is a composition a person typed in place of the one the engine
    proposed, and its reason was being collected on screen and thrown away at the call: the
    snapshot then explained the quantities with the ENGINE's sentences, which are the reasons
    for a decision nobody took. It reads back on the frozen line, where the rest of what was
    decided already lives.
    """
    client, world = api
    db = world.db
    order, line_1, _line_2 = _two_line_order(world)

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                {
                    **_line_payload(line_1.id, buy_qty="50"),
                    "amend_reason": "Holding the free stock for the site that is already late.",
                }
            ]
        },
    )
    assert response.status_code == 200, response.text

    snapshot = _decision(db, order).line_snapshots[0]
    assert snapshot["amend_reason"] == (
        "Holding the free stock for the site that is already late."
    )

    sheet = client.get(f"{BASE}/sales-orders/{order.id}/supply")
    assert sheet.status_code == 200, sheet.text
    frozen = next(
        line["frozen"]
        for line in sheet.json()["lines"]
        if line["project_line_id"] == str(line_1.id)
    )
    assert frozen["amend_reason"] == (
        "Holding the free stock for the site that is already late."
    )


def test_a_line_nobody_amended_freezes_no_amendment_reason(api):
    """Absent, never an empty string: a blank reason beside a proposal taken as it stands
    would read as an amendment somebody declined to explain."""
    client, world = api
    db = world.db
    order, line_1, _line_2 = _two_line_order(world)

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert response.status_code == 200, response.text

    assert _decision(db, order).line_snapshots[0]["amend_reason"] is None


def test_confirming_nothing_is_refused_and_leaves_the_active_decision_alone(api):
    """A confirmation of no lines is not a decision. Accepting it would supersede the
    revision that IS holding stock and quietly un-decide the whole order."""
    client, world = api
    db = world.db
    order, line_1, _line_2 = _two_line_order(world)

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert first.status_code == 200, first.text

    empty = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json={"lines": []})
    assert empty.status_code == 422, empty.text
    assert empty.json()["code"] == "supply_nothing_to_confirm"

    db.expire_all()
    still_active = _decision(db, order)
    assert still_active is not None and still_active.revision_no == 1


def test_a_second_confirmation_covering_more_lines_supersedes_the_first(api):
    """Deciding more lines later is a NEW revision covering the union - which is exactly
    what revisions already do (13.4). History is preserved, not rewritten."""
    client, world = api
    db = world.db
    order, line_1, line_2 = _two_line_order(world)

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert first.status_code == 200, first.text

    both = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line_1.id, buy_qty="50"),
                _line_payload(line_2.id, buy_qty="30"),
            ]
        },
    )
    assert both.status_code == 200, both.text
    assert both.json()["revision_no"] == 2
    assert both.json()["lines_undecided"] == 0

    db.expire_all()
    active = _decision(db, order)
    assert active.revision_no == 2
    assert len(active.line_snapshots) == 2

    superseded = _decision(db, order, state="superseded")
    assert superseded is not None and superseded.revision_no == 1
    assert superseded.superseded_at is not None
    assert superseded.supersedes_id is None
    assert active.supersedes_id == superseded.id


def test_an_unbalanced_line_inside_the_confirmation_still_rolls_the_whole_thing_back(api):
    """AC-C02, as amended: atomic over the lines in THIS confirmation. The line nobody
    chose is not what fails it, and the line that was chosen still takes the lot down."""
    client, world = api
    db = world.db
    order, line_1, line_2 = _two_line_order(world)

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line_1.id, buy_qty="50"),
                _line_payload(line_2.id, buy_qty="20"),  # open for 30
            ]
        },
    )
    assert response.status_code == 422, response.text
    failing = response.json()["failing_lines"]
    assert [row["line_no"] for row in failing] == [20]

    assert _decision(db, order) is None, "nothing may be written when a chosen line fails"


def test_a_partial_decision_is_not_challenged_for_covering_fewer_lines(api):
    """The drift check compares the lines a revision COVERS against live facts. A line it
    deliberately never covered is not drift - it is the undecided remainder."""
    client, world = api
    db = world.db
    order, line_1, _line_2 = _two_line_order(world)

    confirmed = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert confirmed.status_code == 200, confirmed.text

    sheet = client.get(f"{BASE}/sales-orders/{order.id}/supply")
    assert sheet.status_code == 200, sheet.text
    assert sheet.json()["decision"]["state"] == "active"

    db.expire_all()
    assert _decision(db, order) is not None


def test_a_covered_line_that_drifts_still_challenges_the_partial_decision(api):
    """The other half of the same rule: what the revision DID cover is still watched."""
    from app.models.order import SalesOrderLine

    client, world = api
    db = world.db
    order, line_1, _line_2 = _two_line_order(world)

    confirmed = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert confirmed.status_code == 200, confirmed.text

    core = (
        db.query(SalesOrderLine)
        .filter(SalesOrderLine.id == line_1.core_sales_order_line_id)
        .first()
    )
    core.qty_ordered = Decimal("60")
    db.commit()

    sheet = client.get(f"{BASE}/sales-orders/{order.id}/supply")
    assert sheet.status_code == 200, sheet.text
    assert sheet.json()["decision"]["state"] == "challenged"


def test_a_line_the_next_confirmation_does_not_name_keeps_its_raised_buy(api):
    """A confirmation that names fewer lines than the active revision covers does NOT
    un-decide the rest: the unnamed line is carried forward, so purchasing goes on being
    told to buy it. There is no un-decide verb yet; a raised row that vanished because a
    planner approved a DIFFERENT line would be a requirement silently dropped."""
    from app.models.project_so import OrderInquiryRow

    client, world = api
    db = world.db
    order, line_1, line_2 = _two_line_order(world)

    both = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line_1.id, buy_qty="50"),
                _line_payload(line_2.id, buy_qty="30"),
            ]
        },
    )
    assert both.status_code == 200, both.text
    assert both.json()["inquiry_rows_created"] == 2

    narrowed = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert narrowed.status_code == 200, narrowed.text
    assert narrowed.json()["lines_decided"] == 2
    assert narrowed.json()["lines_undecided"] == 0
    # Line 1 was decided again, so its row counts; line 2's row is carried under the new
    # revision but purchasing already had it, and the toast must not say two rows again.
    assert narrowed.json()["inquiry_rows_created"] == 1

    db.expire_all()
    rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_2.id)
        .all()
    )
    raised = [row for row in rows if row.state == "raised"]
    assert len(raised) == 1, "line 2 is still decided, so purchasing is still told once"
    assert str(raised[0].qty) in ("30", "30.0000")


# ------------------------------------------------- the union is the server's (F1, F2)


def _snapshot_of(decision, line_id):
    return next(
        snapshot
        for snapshot in decision.line_snapshots
        if snapshot["project_line_id"] == str(line_id)
    )


def test_a_later_confirmation_carries_the_covered_lines_forward(api):
    """Confirm {1}, then confirm {2}: revision 2 covers BOTH, and line 1's snapshot is the
    one revision 1 froze, byte for byte. The board posts only what the planner just
    decided (a day window cannot even see every covered line), so the union has to be
    the server's or a second confirm silently un-decides everything before it."""
    client, world = api
    db = world.db
    order, line_1, line_2 = _two_line_order(world)

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert first.status_code == 200, first.text
    frozen_1 = _snapshot_of(_decision(db, order), line_1.id)

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_2.id, buy_qty="30")]},
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["revision_no"] == 2
    assert body["lines_decided"] == 2, "the carried line counts as decided"
    assert body["lines_undecided"] == 0
    assert body["inquiry_rows_created"] == 1, (
        "line 2's Buy is new to purchasing; line 1's carried row is not counted again"
    )

    db.expire_all()
    active = _decision(db, order)
    assert active.revision_no == 2
    assert {s["project_line_id"] for s in active.line_snapshots} == {
        str(line_1.id),
        str(line_2.id),
    }
    assert _snapshot_of(active, line_1.id) == frozen_1


def test_a_carried_line_keeps_its_borrow_reason_its_buy_reason_and_its_hold(api):
    """The carried snapshot is verbatim (the person's borrow reason and buy reason
    included), and the stock it holds is held by revision 2 exactly as revision 1 held it:
    same warehouses, same quantities, and the claim it made is not made a second time."""
    from app.models.project_so import AllocationClaim, SOLineAllocation
    from app.services.project_supply_service import ProjectSupplyService

    client, world = api
    db = world.db
    donor_wh = _warehouse(db, f"ZZT-DONOR-{_uid()[:4]}")
    _stock(db, world.product, donor_wh, on_hand=100)
    order, line_1, line_2 = _two_line_order(world)
    # Ladder v2 has no own-location Reserve any more; the pool is the only Reserve
    # source, so it needs its own stock.
    _stock(db, world.product, world.pool_wh, on_hand=100)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line_1.id,
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "20"}],
                    borrow=[
                        {
                            "source": "other_location",
                            "warehouse_id": donor_wh.id,
                            "qty": "10",
                            "reason": "Their hand-over is in December.",
                        }
                    ],
                    buy_qty="20",
                    buy_reason="Nothing else is free before the date.",
                )
            ]
        },
    )
    assert first.status_code == 200, first.text
    rev_1 = _decision(db, order)
    frozen_1 = _snapshot_of(rev_1, line_1.id)
    borrow = next(c for c in frozen_1["components"] if c["kind"] == "borrow")
    buy = next(c for c in frozen_1["components"] if c["kind"] == "buy")
    assert borrow["cs_reason"] == "Their hand-over is in December."
    assert buy["cs_reason"] == "Nothing else is free before the date."

    supply = ProjectSupplyService(db)
    held_before = supply.held_stock_by_location([world.product.id])
    assert held_before[(world.product.id, world.pool_wh.id)] == Decimal("20")
    assert held_before[(world.product.id, donor_wh.id)] == Decimal("10")

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_2.id, buy_qty="30")]},
    )
    assert second.status_code == 200, second.text

    db.expire_all()
    rev_2 = _decision(db, order)
    assert rev_2.revision_no == 2
    assert _snapshot_of(rev_2, line_1.id) == frozen_1

    held_after = ProjectSupplyService(db).held_stock_by_location([world.product.id])
    assert held_after == held_before, "the carried line's hold is neither lost nor doubled"

    def rows_of(decision):
        return sorted(
            (row.source_type, str(row.warehouse_id), str(row.qty))
            for row in db.query(SOLineAllocation)
            .filter(
                SOLineAllocation.decision_id == decision.id,
                SOLineAllocation.so_line_id == line_1.id,
            )
            .all()
        )

    assert rows_of(rev_2) == rows_of(rev_1)
    assert db.query(AllocationClaim).count() == 0, (
        "an other-location borrow makes no claim, and carrying it must not invent one"
    )


def test_naming_a_covered_line_again_replaces_its_frozen_composition(api):
    """A named line is an amendment: it REPLACES the frozen one rather than sitting beside
    it, so the revision never covers one line twice."""
    client, world = api
    db = world.db
    order, line_1, _line_2 = _two_line_order(world)
    # Ladder v2 has no own-location Reserve any more; the pool is the only Reserve source.
    _stock(db, world.product, world.pool_wh, on_hand=100)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert first.status_code == 200, first.text

    amended = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                {
                    **_line_payload(
                        line_1.id,
                        reserve=[{"warehouse_id": world.pool_wh.id, "qty": "50"}],
                    ),
                    "amend_reason": "The stock arrived at the pool.",
                }
            ]
        },
    )
    assert amended.status_code == 200, amended.text
    assert amended.json()["lines_decided"] == 1

    db.expire_all()
    active = _decision(db, order)
    assert len(active.line_snapshots) == 1
    snapshot = active.line_snapshots[0]
    assert snapshot["buy_qty"] == "0"
    assert snapshot["reserve_qty"] == "50"
    assert snapshot["amend_reason"] == "The stock arrived at the pool."


def test_a_discontinued_covered_line_survives_a_later_confirmation_of_another_line(api):
    """F2. Line 1 is a discontinued product bought with a reason. Approving line 2 later
    must not re-judge line 1 against live facts (the board rebuilt it WITHOUT its buy
    reason and the whole confirmation 422'd): the covered line is carried, not re-posted.
    """
    from .test_so_supply_confirmation import _product

    client, world = api
    db = world.db
    retired = _product(db, discontinued=True)
    _stock(db, world.product, world.own_wh, on_hand=100)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_1 = _core_line(db, core_so, retired, world.own_wh, qty_ordered="50")
    core_2 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="30")
    line_1 = _project_line(db, order, line_no=10, product=retired, core_line=core_1)
    line_2 = _project_line(db, order, line_no=20, product=world.product, core_line=core_2)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line_1.id, buy_qty="50", buy_reason="Last batch for the show flat."
                )
            ]
        },
    )
    assert first.status_code == 200, first.text
    frozen_1 = _snapshot_of(_decision(db, order), line_1.id)

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_2.id, buy_qty="30")]},
    )
    assert second.status_code == 200, second.text

    db.expire_all()
    active = _decision(db, order)
    assert active.revision_no == 2
    carried = _snapshot_of(active, line_1.id)
    assert carried == frozen_1
    assert carried["buy_reason"] == "Last batch for the show flat."


def test_a_covered_line_whose_open_quantity_drifted_is_not_carried_and_the_revision_is_challenged(api):
    """A carried line is not re-validated - but a revision whose frozen facts have moved is
    no promise anybody can keep, and carrying its snapshot verbatim into a fresh revision
    stamped confirmed NOW would be re-making that promise against facts that are gone.
    The confirmation runs the same drift check the sheet runs (`challenge_if_drifted`)
    before it reads the active revision for the carry: revision 1 (lines 1 and 2) is
    challenged, line 1 alone is confirmed into revision 2, and line 2 - whose open
    quantity moved - is undecided again rather than carried on a stale snapshot."""
    from app.models.order import SalesOrderLine

    client, world = api
    db = world.db
    order, line_1, line_2 = _two_line_order(world)

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line_1.id, buy_qty="50"),
                _line_payload(line_2.id, buy_qty="30"),
            ]
        },
    )
    assert first.status_code == 200, first.text

    core = (
        db.query(SalesOrderLine)
        .filter(SalesOrderLine.id == line_2.core_sales_order_line_id)
        .first()
    )
    core.qty_ordered = Decimal("40")
    db.commit()

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert second.status_code == 200, second.text
    assert second.json()["revision_no"] == 2
    assert second.json()["lines_decided"] == 1
    assert second.json()["lines_undecided"] == 1

    db.expire_all()
    active = _decision(db, order)
    assert active.revision_no == 2
    assert [s["project_line_id"] for s in active.line_snapshots] == [str(line_1.id)], (
        "line 2's stale snapshot is not carried into a revision confirmed now"
    )
    challenged = _decision(db, order, state="challenged")
    assert challenged is not None and challenged.revision_no == 1
    assert "Line 20" in (challenged.superseded_reason or "")
    assert _decision(db, order, state="superseded") is None
