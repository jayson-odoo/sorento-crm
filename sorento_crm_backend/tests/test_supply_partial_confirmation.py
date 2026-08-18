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


def test_dropping_a_line_from_the_next_revision_cancels_its_unplaced_buy(api):
    """A line that leaves the decision goes back to undecided, so purchasing must stop
    being told to buy it. Its demand returns through the sheet leg instead, and a raised
    row left behind would be that requirement counted a second time."""
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

    db.expire_all()
    rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_2.id)
        .all()
    )
    assert rows, "the row is cancelled, never deleted - it is what was told to purchasing"
    assert all(row.state == "cancelled" for row in rows), (
        "the line is undecided again, so nothing about it is still raised"
    )
