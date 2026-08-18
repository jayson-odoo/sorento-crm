"""An unreconciled line on the sheet and at the confirmation.

A mirror line with no reconciled AutoCount line has no open quantity to promise against
(PLAN 3.1 step 2). It used to refuse the WHOLE read and the WHOLE confirmation, which
meant one line waiting on reconciliation stopped its siblings from being planned. Now:

* the sheet still reads (200), and the unreconciled line is returned with no components,
  no donors and an `unplannable_reason` saying why; every plannable line carries `null`;
* a confirmation naming only reconciled lines succeeds beside an unreconciled sibling;
* a confirmation that NAMES the unreconciled line is refused with
  `supply_lines_unreconciled`, listing that line and only that line.

Postgres via `tests/_pg_fixture.py::blank_session`, seeding its own chain. The helpers
are the Stage 1C suite's own, imported so the two files agree about what a Project SO is.
"""
from __future__ import annotations

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

UNPLANNABLE = "No reconciled AutoCount line. Reconcile the sales order first."


def _order_with_an_unreconciled_line(world):
    """Line 10 reconciled to a core line open for 50; line 20 with no core line at all."""
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=100)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    line_1 = _project_line(db, order, line_no=10, product=world.product, core_line=core_1)
    line_2 = _project_line(db, order, line_no=20, product=world.product, core_line=None)
    db.commit()
    return order, line_1, line_2


def test_the_sheet_reads_with_an_unreconciled_line_and_says_why_it_cannot_be_planned(api):
    client, world = api
    order, line_1, line_2 = _order_with_an_unreconciled_line(world)

    response = client.get(f"{BASE}/sales-orders/{order.id}/supply")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lines_total"] == 2
    by_line = {line["project_line_id"]: line for line in body["lines"]}

    plannable = by_line[str(line_1.id)]
    assert plannable["unplannable_reason"] is None
    assert plannable["open_qty"] == "50"
    assert plannable["components"], "the reconciled line is still proposed for"

    waiting = by_line[str(line_2.id)]
    assert waiting["unplannable_reason"] == UNPLANNABLE
    assert waiting["line_no"] == 20
    assert waiting["item_code"] == world.product.product_code
    assert waiting["open_qty"] == "0"
    assert waiting["components"] == []
    assert waiting["borrow_candidates"] == []
    assert waiting["decided"] is False
    assert waiting["frozen"] is None


def test_confirming_the_reconciled_lines_succeeds_beside_an_unreconciled_sibling(api):
    client, world = api
    db = world.db
    order, line_1, _line_2 = _order_with_an_unreconciled_line(world)

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="50")]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["lines_decided"] == 1
    assert response.json()["lines_undecided"] == 1

    decision = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.state == "active",
        )
        .first()
    )
    assert decision is not None
    assert [s["project_line_id"] for s in decision.line_snapshots] == [str(line_1.id)]


def test_naming_the_unreconciled_line_is_refused_naming_only_that_line(api):
    client, world = api
    db = world.db
    order, line_1, line_2 = _order_with_an_unreconciled_line(world)

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line_1.id, buy_qty="50"),
                _line_payload(line_2.id, buy_qty="0"),
            ]
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "supply_lines_unreconciled"
    assert [row["line_no"] for row in body["failing_lines"]] == [20]
    assert body["failing_lines"][0]["item_code"] == world.product.product_code

    assert (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .count()
        == 0
    ), "nothing is written when a named line is refused"
