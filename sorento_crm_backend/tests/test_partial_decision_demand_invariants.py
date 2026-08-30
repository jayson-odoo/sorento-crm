"""Partial confirmation must not make the undecided lines disappear (PLAN 13.4).

The captain's reason for wanting partial confirmation is this exact number:

> "we shouldn't block the confirm when the decision for the order are incomplete yet, we
>  might want to flow a few product to reorder planning first"

`scm.committed_v`'s `decided` CTE was keyed per ORDER, so ANY active decision took the
WHOLE order out of the sheet leg. Confirming one line of a twelve-line order would have
made the other eleven invisible to the reorder engine - uncovered demand nobody buys, and
the precise opposite of what partial confirmation is for. The two failure modes are
DISAPPEARING DEMAND and DOUBLE COUNTING, and both are pinned here, on the reorder engine's
own read path rather than on a table.

P3 (`PLAN-scm-purchasing-uat-journey.md`, captain 26 Aug 2026) retired the sheet leg, and
that moved where the undecided line lives without changing either failure mode. Project
demand now has ONE source, the un-linked Order Inquiry row, so the confirmed line flows to
planning as its Buy and the undecided one is AWAITING CS - counted and named by
`demand_source_service.set_aside_project_demand` rather than netted. Disappearing demand is
therefore still what these tests refuse: the undecided quantity has to be somewhere a
planner can see it, and it must never be in the plan twice.

The handshake (`PLAN-scm-oi-handshake.md`, captain 27 Aug) adds the second gate the engine
test below now walks: the VIEW counts a Buy the moment CS confirms it, because the customer
is owed it; the PLAN counts it only once purchasing has ACKNOWLEDGED the row.

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

    Line A is open for 50 and line B for 45, so the confirmed leg, the set-aside remainder
    and a double count are three different numbers and the assertions cannot pass by
    accident. The `demand_origin` stamp below is what the retired sheet leg read; it is
    kept because this is the exact shape P3 was ruled against - an order the old Joey feed
    named that nobody has confirmed - and it must now count for nothing.

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


def _acknowledge(db, world, row_ids):
    """Purchasing takes the rows on (AC-H2), through the service the route calls.

    The route itself is exercised by `tests/test_order_inquiry_handshake.py`; what this
    file needs is the state change, so it goes straight at the service rather than
    re-plumbing a permissioned client for one call.
    """
    from app.models.base import company_scope
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    with company_scope(db, frozenset({world.company_id})):
        result = ProjectOrderInquiryService(db).acknowledge_rows(
            row_ids, actor_user_id=world.user_id
        )
    db.commit()
    return result


# ------------------------------------------------- the invariant the captain asked for


def test_the_undecided_lines_of_a_partly_confirmed_order_are_still_demand():
    """One line of a two-line order is confirmed. The other must still be accounted for.

    Numbers: line A open 50, confirmed as a whole-line Buy 50. Line B open 45, undecided.

    * 50 = the confirmed Buy, counted once. Correct since P3.
    * 95 = line B netted through the retired sheet leg as well.
    * 100 = line A counted through two legs at once.

    Line B's 45 does not vanish: it is reported as awaiting CS, which is the half of
    "disappearing demand" that survived the sheet leg.
    """
    from app.models.base import company_scope
    from app.services.scm import demand_source_service

    with pg_session() as db:
        world = _seed(db)
        before = _committed(db, world)
        assert before["project_committed"] == Decimal("0"), (
            "unconfirmed, neither line is demand: a project-class book line becomes "
            "demand when CS raises the Buy for it, and not before (P3)"
        )

        _confirm(
            db,
            world,
            [
                # Wholly bought (AC-L5): a line is met entirely from stock or entirely
                # bought, so a "Reserve 20 + Buy 30" composition can no longer be confirmed.
                _line_payload(world.line_a.id, buy_qty="50")
            ],
        )

        after = _committed(db, world)
        assert after["project_committed"] == Decimal("50"), (
            "the confirmed line flows to planning as its Buy, counted exactly once"
        )
        assert after["confirmed"] == Decimal("50")
        assert after["committed"] == Decimal("50")

        with company_scope(db, frozenset({world.company_id})):
            aside = demand_source_service.set_aside_project_demand(
                db, product_ids=[str(world.product.id)]
            )
        assert Decimal(str(aside["quantity"])) == Decimal("45"), (
            "the undecided line is not demand, but it is not gone either: it is on CS's "
            "desk and the planner is told so by name"
        )
        assert aside["lines"] == 1


def test_the_reorder_engine_reads_the_confirmed_demand_only_once_it_is_acknowledged():
    """Not merely present in the view: present in the rows the engine plans from.

    And the two are deliberately different, which is the handshake
    (`PLAN-scm-oi-handshake.md`): `scm.committed_v` counts CS's Buy immediately, because
    the customer is owed it, while `horizon_committed_select_sql` - the only thing a plan
    run reads - counts `PLANNED_ACK_STATES` alone. An instruction purchasing has not taken
    on yet may still be amended or refused, so buying against it is buying against a
    question. The engine therefore sees nothing until the row is acknowledged, and the
    plan page shows the difference as its awaiting count.
    """
    from app.models.base import company_scope
    from app.models.project_so import OrderInquiryRow

    def _planning_row(db, world):
        with company_scope(db, frozenset({world.company_id})):
            rows = reorder_run_service._planning_rows(
                db, [str(world.warehouse.id)], product_ids=[str(world.product.id)]
            )
        assert len(rows) == 1, "the engine must still see this product at this location"
        return rows[0]

    with pg_session() as db:
        world = _seed(db)
        _confirm(
            db,
            world,
            [
                # Wholly bought (AC-L5): a line is met entirely from stock or entirely
                # bought, so a "Reserve 20 + Buy 30" composition can no longer be confirmed.
                _line_payload(world.line_a.id, buy_qty="50")
            ],
        )

        awaiting = _planning_row(db, world)
        assert Decimal(str(awaiting["project_committed"])) == Decimal("0"), (
            "the row is awaiting acknowledgement, so the plan must not buy against it"
        )
        assert _committed(db, world)["project_committed"] == Decimal("50"), (
            "the VIEW counts it all the same - it is owed to the customer either way"
        )

        row_ids = [
            str(row_id)
            for (row_id,) in db.query(OrderInquiryRow.id)
            .filter(OrderInquiryRow.so_line_id == world.line_a.id)
            .all()
        ]
        assert row_ids, "the confirmation must have raised the Buy as an inquiry row"
        _acknowledge(db, world, row_ids)

        acknowledged = _planning_row(db, world)
        assert Decimal(str(acknowledged["project_committed"])) == Decimal("50")
        assert Decimal(str(acknowledged["project_confirmed_committed"])) == Decimal("50")
        assert Decimal(str(acknowledged["committed"])) == Decimal("50")


def test_a_fully_confirmed_order_counts_its_buy_once_and_its_sheet_quantity_never():
    """The other failure mode. Every line decided: only the two Buy residuals count."""
    with pg_session() as db:
        world = _seed(db)
        _confirm(
            db,
            world,
            [
                _line_payload(world.line_a.id, buy_qty="50"),
                _line_payload(world.line_b.id, buy_qty="45"),
            ],
        )

        after = _committed(db, world)
        assert after["project_committed"] == Decimal("95"), (
            "50 + 45 of confirmed Buy, counted once each and never through the sheet leg"
        )
        assert after["confirmed"] == Decimal("95")


def test_the_order_half_never_speaks_for_a_project_order_and_the_line_half_still_does():
    """The order-level half, and what P3 left of it.

    It used to stop being demand the moment ANY decision existed, which is what took the
    order's undecided lines with it; 13.4 moved that question to the LINE. P3 then took
    the order half out of the argument entirely - it excludes project class whether the
    order is untouched, partly confirmed or fully confirmed - so the answer can no longer
    depend on how far CS has got. The line half is what still varies, and it is what the
    fulfilment board reads as "covered".
    """
    from app.models.order import SalesOrder, SalesOrderLine
    from app.services.scm.demand import is_plan_demand_line, is_plan_demand_order

    def counted_order(db, world):
        return (
            db.query(SalesOrder.id)
            .filter(SalesOrder.id == world.order.so_id, is_plan_demand_order())
            .first()
        )

    def undecided_core_lines(db, world):
        return {
            str(line_id)
            for (line_id,) in db.query(SalesOrderLine.id)
            .filter(
                SalesOrderLine.sales_order_id == world.order.so_id,
                is_plan_demand_line(),
            )
            .all()
        }

    with pg_session() as db:
        world = _seed(db)
        assert counted_order(db, world) is None, (
            "untouched, a project order is not book demand"
        )
        assert undecided_core_lines(db, world) == {
            str(world.line_a.core_sales_order_line_id),
            str(world.line_b.core_sales_order_line_id),
        }

        _confirm(
            db,
            world,
            [
                # Wholly bought (AC-L5): a line is met entirely from stock or entirely
                # bought, so a "Reserve 20 + Buy 30" composition can no longer be confirmed.
                _line_payload(world.line_a.id, buy_qty="50")
            ],
        )
        db.expire_all()

        assert counted_order(db, world) is None, (
            "partly confirmed changes nothing at the order level: the book does not speak "
            "for a project order at all"
        )
        assert undecided_core_lines(db, world) == {
            str(world.line_b.core_sales_order_line_id)
        }, "only the decided line becomes covered, and it does so per LINE"


def test_the_python_twin_and_the_view_agree_about_which_lines_are_decided():
    """`demand.py` exists so the netting engine and the view cannot drift. A per-line rule
    in one and a per-order rule in the other is exactly that drift.

    Since P3 the two agree on a shorter statement, and this is it: NEITHER line of a
    project order reaches the plan through the book, and the view counts the decided one
    exactly once, through the confirmed leg, as its Buy. The Python twin says the same by
    saying the book counts nothing here.
    """
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
                # Wholly bought (AC-L5): a line is met entirely from stock or entirely
                # bought, so a "Reserve 20 + Buy 30" composition can no longer be confirmed.
                _line_payload(world.line_a.id, buy_qty="50")
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
        assert decided_core not in by_line, (
            "the decided line reaches the plan as confirmed Buy, so counting its book "
            "quantity here would be the double count"
        )
        assert undecided_core not in by_line, (
            "and the undecided one is awaiting CS, not book demand: the book leg speaks "
            "for retail alone (P3)"
        )

        committed = _committed(db, world)
        assert committed["project_committed"] == Decimal("50")
        assert committed["confirmed"] == Decimal("50")
