"""Partial confirmation must not make the undecided lines disappear (PLAN 13.4).

The captain's reason for wanting partial confirmation is this exact number:

> "we shouldn't block the confirm when the decision for the order are incomplete yet, we
>  might want to flow a few product to reorder planning first"

`scm.committed_v`'s `decided` CTE was keyed per ORDER, so ANY active decision took the
WHOLE order out of the sheet leg. Confirming one line of a twelve-line order would have
made the other eleven invisible to the reorder engine - uncovered demand nobody buys, and
the precise opposite of what partial confirmation is for. The two failure modes are
DISAPPEARING DEMAND and DOUBLE COUNTING, and both are pinned here, on the reorder engine's
own read path rather than on a table:

* `reorder_run_service._planning_rows` is what the engine plans from. It reads
  `scm.net_position_v` and `scm.committed_v`, so a number that is wrong in the view is
  wrong in the plan.
* the Python twin (`app.services.scm.demand`) must agree with the SQL, which is the whole
  reason both live in one module.

Runs against the REAL database (`_pg_fixture.pg_session`), not the blank scratch schema:
`scm.committed_v` is a VIEW installed by a migration and does not exist in the scratch
schema at all. Everything is seeded by this file with a marker prefix and rolled back.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.services import project_seed_service
from app.services.scm import reorder_run_service

from ._pg_fixture import pg_session
from .test_so_supply_confirmation import (
    BASE,
    MARKER,
    _client,
    _core_line,
    _core_so,
    _line_payload,
    _project_line,
    _project_so,
    _restore,
    _sorento,
    _product,
    _stock,
    _user,
    _warehouse,
)


class _World:
    def __init__(
        self, db, company_id, user_id, product, warehouse, pool_warehouse, order, line_a, line_b
    ):
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.product = product
        self.warehouse = warehouse
        self.pool_warehouse = pool_warehouse
        self.order = order
        self.line_a = line_a
        self.line_b = line_b


def _seed(db):
    """One sheet-named project order, two lines of one product at one location.

    Line A is open for 50 and line B for 45, so the sheet leg, the confirmed leg and a
    double count are three different numbers and the assertions cannot pass by accident.

    Ladder v2 (section E rule 7): the own location is never a Reserve source any more, so
    line A's Reserve component draws from a POOL wired to the line's own warehouse
    (`pool_warehouse_id`), same as `tests/test_project_so_confirm_all_route.py`.
    """
    from app.services.project_service import register_project

    company_id = _sorento(db)
    project_seed_service.run(db, company_id=company_id)
    user_id = _user(db, f"{MARKER} Partial")
    project = register_project(
        db, company_id=company_id, actor_user_id=user_id, developer_party_id=None,
        title=f"{MARKER} Partial Residences",
    )
    product = _product(db)
    pool_warehouse = _warehouse(db, f"ZZT-PL-{str(product.id)[:4]}")
    warehouse = _warehouse(
        db, f"ZZT-PC-{str(product.id)[:4]}", pool_warehouse_id=pool_warehouse.id
    )
    _stock(db, product, pool_warehouse, on_hand=20)

    core_so = _core_so(db, company_id)
    core_so.demand_origin = "scm_order_inquiry"
    core_a = _core_line(db, core_so, product, warehouse, qty_ordered="50")
    core_b = _core_line(db, core_so, product, warehouse, qty_ordered="45")
    order = _project_so(db, project, so_id=core_so.id)
    line_a = _project_line(db, order, line_no=10, product=product, core_line=core_a)
    line_b = _project_line(db, order, line_no=20, product=product, core_line=core_b)
    db.commit()
    return _World(
        db, company_id, user_id, product, warehouse, pool_warehouse, order, line_a, line_b
    )


def _committed(db, world) -> dict:
    row = db.execute(
        text(
            "SELECT COALESCE(SUM(committed), 0) AS committed, "
            "       COALESCE(SUM(project_committed), 0) AS project_committed, "
            "       COALESCE(SUM(project_confirmed_committed), 0) AS confirmed "
            "FROM scm.committed_v WHERE product_id = :pid AND warehouse_id = :wid"
        ),
        {"pid": world.product.id, "wid": world.warehouse.id},
    ).mappings().first()
    return {key: Decimal(str(value)) for key, value in row.items()}


def _confirm(db, world, payload_lines):
    from app.models.base import company_scope

    client, originals = _client(db, world.user_id)
    try:
        with company_scope(db, frozenset({world.company_id})):
            response = client.post(
                f"{BASE}/sales-orders/{world.order.id}/confirm",
                json={"lines": payload_lines},
            )
            assert response.status_code == 200, response.text
            return response.json()
    finally:
        _restore(originals)


# ------------------------------------------------- the invariant the captain asked for


def test_the_undecided_lines_of_a_partly_confirmed_order_are_still_demand():
    """One line of a two-line order is confirmed. The other must still be planned for.

    Numbers: line A open 50, confirmed as Reserve 20 + Buy 30. Line B open 45, undecided.

    * 75 = the undecided 45 through the sheet leg + the confirmed Buy 30. Correct.
    * 30 = the per-ORDER `decided` CTE this slice replaces: line B vanished.
    * 125 = line A counted through both legs at once.
    """
    with pg_session() as db:
        world = _seed(db)
        before = _committed(db, world)
        assert before["project_committed"] == Decimal("95"), (
            "unconfirmed, the sheet leg counts both lines"
        )

        _confirm(
            db,
            world,
            [
                _line_payload(
                    world.line_a.id,
                    reserve=[{"warehouse_id": world.pool_warehouse.id, "qty": "20"}],
                    buy_qty="30",
                )
            ],
        )

        after = _committed(db, world)
        assert after["project_committed"] == Decimal("75"), (
            "the undecided line must keep flowing to reorder planning, and the confirmed "
            "line must be counted once, as its Buy residual"
        )
        assert after["confirmed"] == Decimal("30"), (
            "only the confirmed Buy is firm; the sheet remainder is netted like any other "
            "commitment"
        )
        assert after["committed"] == Decimal("75")


def test_the_reorder_engine_reads_the_undecided_demand_through_its_own_path():
    """Not merely present in the view: present in the rows the engine plans from."""
    from app.models.base import company_scope

    with pg_session() as db:
        world = _seed(db)
        _confirm(
            db,
            world,
            [
                _line_payload(
                    world.line_a.id,
                    reserve=[{"warehouse_id": world.pool_warehouse.id, "qty": "20"}],
                    buy_qty="30",
                )
            ],
        )

        with company_scope(db, frozenset({world.company_id})):
            rows = reorder_run_service._planning_rows(
                db, [str(world.warehouse.id)], product_ids=[str(world.product.id)]
            )
        assert len(rows) == 1, "the engine must still see this product at this location"
        row = rows[0]
        assert Decimal(str(row["project_committed"])) == Decimal("75")
        assert Decimal(str(row["project_confirmed_committed"])) == Decimal("30")
        assert Decimal(str(row["committed"])) == Decimal("75")


def test_a_fully_confirmed_order_counts_its_buy_once_and_its_sheet_quantity_never():
    """The other failure mode. Every line decided: only the two Buy residuals count."""
    with pg_session() as db:
        world = _seed(db)
        _confirm(
            db,
            world,
            [
                _line_payload(
                    world.line_a.id,
                    reserve=[{"warehouse_id": world.pool_warehouse.id, "qty": "20"}],
                    buy_qty="30",
                ),
                _line_payload(world.line_b.id, buy_qty="45"),
            ],
        )

        after = _committed(db, world)
        assert after["project_committed"] == Decimal("75"), (
            "30 + 45 of confirmed Buy, and not one unit of the 95 the sheet named"
        )
        assert after["confirmed"] == Decimal("75")


def test_a_partly_confirmed_order_is_still_a_plan_demand_order():
    """The order-level half. It used to stop being demand the moment ANY decision existed,
    which is what took its undecided lines with it."""
    from app.models.order import SalesOrder
    from app.services.scm.demand import is_plan_demand_order

    with pg_session() as db:
        world = _seed(db)
        _confirm(
            db,
            world,
            [
                _line_payload(
                    world.line_a.id,
                    reserve=[{"warehouse_id": world.pool_warehouse.id, "qty": "20"}],
                    buy_qty="30",
                )
            ],
        )
        db.expire_all()

        core_so_id = (
            db.query(SalesOrder.id)
            .filter(SalesOrder.id == world.order.so_id, is_plan_demand_order())
            .first()
        )
        assert core_so_id is not None, (
            "an order with an undecided line is still demand; which of its LINES count is "
            "the line rule's question, not this one's"
        )


def test_the_python_twin_and_the_view_agree_about_which_lines_are_decided():
    """`demand.py` exists so the netting engine and the view cannot drift. A per-line rule
    in one and a per-order rule in the other is exactly that drift."""
    from app.models.order import SalesOrder, SalesOrderLine
    from app.services.scm.demand import (
        demand_qty,
        is_open_demand,
        is_plan_demand_line,
        is_plan_demand_order,
    )

    with pg_session() as db:
        world = _seed(db)
        _confirm(
            db,
            world,
            [
                _line_payload(
                    world.line_a.id,
                    reserve=[{"warehouse_id": world.pool_warehouse.id, "qty": "20"}],
                    buy_qty="30",
                )
            ],
        )
        db.expire_all()

        counted = (
            db.query(SalesOrderLine.id, demand_qty())
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .filter(
                SalesOrderLine.product_id == world.product.id,
                SalesOrderLine.warehouse_id == world.warehouse.id,
                SalesOrder.status == "open",
                is_open_demand(),
                is_plan_demand_order(),
                is_plan_demand_line(),
            )
            .all()
        )
        by_line = {str(line_id): Decimal(str(qty)) for line_id, qty in counted}

        decided_core = str(world.line_a.core_sales_order_line_id)
        undecided_core = str(world.line_b.core_sales_order_line_id)
        assert undecided_core in by_line and by_line[undecided_core] == Decimal("45")
        assert decided_core not in by_line, (
            "the decided line reaches the plan as confirmed Buy, so counting its sheet "
            "quantity here would be the double count"
        )
