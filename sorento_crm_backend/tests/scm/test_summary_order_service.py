"""S3b: the Summary Order Report, its drill-downs, its supplier choice and its decision.

The properties pinned here are the ones the printed sheet cannot hold and the ones a screen
can quietly lie about:

* **The report is FROZEN by the run** (AC-C2.9). Moving the order book after the run must not
  move the report, or a past week's decision cannot be reviewed.
* **On order and in transit stay separate** (AC-C2.2), because only the on-order half is still
  negotiable.
* **The project / dealer split reads `order_type`**, and a line with no type is in NEITHER
  aggregate rather than folded into one.
* **Server-owned ordering** (AC-C2.4): dealer lines come back worst-first by ageing, so the
  ageing a person reads is the ageing the server computed.
* **A missing input is named, never zeroed**: no average daily demand and no recorded
  dimensions produce NULL, because 0 reads as "already out of stock" and "no space needed".
* **A quantity above the shortfall is a valid decision** (AC-C2.7), and the engine's figure
  survives beside it with the actor and time (AC-C2.8).
* **A supplier who has never delivered this item says so** (AC-C2.5) and a long-ago last PO is
  flagged by the SERVER (AC-C2.6).

Postgres, marker-prefixed seeding of its own chain, inside `pg_session`'s rolled-back
transaction. Nothing borrowed with `LIMIT 1`: CI's database has no products, no suppliers and
no runs at all, and a borrowed row is the difference between green locally and a NOT NULL
violation in CI.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import OrderSummaryRow, ReorderRecommendation, ReorderRun
from app.services.error_handler import AppException
from app.services.scm import summary_order_service as svc
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session

MARKER = "ZZTSOR"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _today() -> date:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def chain(db):
    """One product, one pool with one member bin, and a completed run recommending a buy.

    Dimensions are set on the product so the volume figure is exercised; a second product
    without them is added by the test that pins the NULL.
    """
    cat = ProductCategory(
        id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat")
    )
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()

    product = Product(
        id=_u(), product_code=_code("SKU"), product_name="wall hung wc",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
        dimensions_length=1000, dimensions_width=500, dimensions_height=200,
    )
    pool = Warehouse(
        id=_u(), warehouse_code=_code("POOL")[:30], warehouse_name="pool",
        is_active=True, counts_as_available=True,
    )
    db.add_all([product, pool])
    db.flush()
    bin_a = Warehouse(
        id=_u(), warehouse_code=_code("BIN")[:30], warehouse_name="bin",
        is_active=True, counts_as_available=True, pool_warehouse_id=pool.id,
    )
    pool.pool_warehouse_id = pool.id
    db.add(bin_a)
    db.flush()

    run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse",
        started_at=to_naive_datetime(datetime.now(MALAYSIA_TZ)),
        source_system="scm", source_ref=_code("RUN"),
    )
    db.add(run)
    db.flush()
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=bin_a.id, rounded_qty=120, status="proposed",
    ))
    db.flush()
    return {"product": product, "pool": pool, "bin": bin_a, "run": run,
            "cat": cat, "uom": uom}


def _supplier(db, name="guangdong sw"):
    s = Supplier(id=_u(), supplier_code=_code("S")[:30], supplier_name=name)
    db.add(s)
    db.flush()
    return s


def _stock(db, product, wh, qty):
    db.add(Stock(id=_u(), product_id=product.id, warehouse_id=wh.id, quantity_on_hand=qty))
    db.flush()


def _so(db, product, wh, qty, *, order_type, ordered_days_ago=3, required_in=10):
    cust = Customer(id=_u(), customer_code=_code("C")[:30], customer_name=f"{order_type} co")
    db.add(cust)
    db.flush()
    so = SalesOrder(
        id=_u(), so_number=_code("SO")[:50], customer_id=cust.id, status="open",
        order_type=order_type, order_date=_today() - timedelta(days=ordered_days_ago),
    )
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=qty, qty_delivered=0,
        required_date=_today() + timedelta(days=required_in), line_status="open",
    ))
    db.flush()
    return so, cust


def _po(db, product, wh, qty, *, supplier, cost=None, currency="USD",
        issued_days_ago=30, received=0, expected_in=20):
    po = PurchaseOrder(
        id=_u(), po_number=_code("PO")[:50], supplier_id=supplier.id, status="active",
        issue_date=_today() - timedelta(days=issued_days_ago),
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=qty, qty_received=received, unit_cost=cost, currency=currency,
        expected_date=_today() + timedelta(days=expected_in), line_status="open",
    ))
    db.flush()
    return po


# =========================================================================== #
# freeze + report
# =========================================================================== #


def test_the_report_states_the_dated_position_the_run_froze(db, chain):
    """The row's figures come off the frozen snapshot, not off a live read."""
    f = chain
    _stock(db, f["product"], f["bin"], 40)
    _so(db, f["product"], f["bin"], 100, order_type="project")
    _po(db, f["product"], f["bin"], 25, supplier=_supplier(db))

    assert svc.write_rows(db, f["run"].id) == 1
    out = svc.report(db, run_id=f["run"].id)

    assert len(out["rows"]) == 1
    row = out["rows"][0]
    assert row["product_code"] == f["product"].product_code
    assert row["on_hand"] == 40
    assert row["project_demand"] == 100
    assert row["dealer_outstanding"] == 0
    assert row["qty_on_order"] == 25
    assert row["qty_in_transit"] == 0
    # 40 on hand plus 25 arriving in 20 days against 100 due in 10: short 60 on the demand
    # date, which a dateless net position (40 + 25 - 100 = -35) would understate.
    assert row["shortfall"] == 60
    assert row["suggested_qty"] == 120
    assert out["as_of"] == _today().isoformat()


def test_moving_the_order_book_after_the_run_does_not_move_the_report(db, chain):
    """AC-C2.9, the whole reason the row is frozen.

    A recomputation would answer today's question under last week's date, so the decision
    could never be reviewed against what the decider actually saw.
    """
    f = chain
    _stock(db, f["product"], f["bin"], 40)
    svc.write_rows(db, f["run"].id)
    frozen = svc.report(db, run_id=f["run"].id)["rows"][0]["on_hand"]

    _stock(db, f["product"], f["pool"], 500)  # the book moves after the run

    assert svc.report(db, run_id=f["run"].id)["rows"][0]["on_hand"] == frozen == 40


def test_rewriting_the_same_run_updates_in_place(db, chain):
    """A retried job must not duplicate the book.

    With two rows for one product the report reads whichever comes back first, which is the
    `system_settings` failure again: a screen that non-deterministically shows one of two
    figures.
    """
    f = chain
    _stock(db, f["product"], f["bin"], 10)
    svc.write_rows(db, f["run"].id)
    _stock(db, f["product"], f["pool"], 5)
    svc.write_rows(db, f["run"].id)

    rows = db.query(OrderSummaryRow).filter(OrderSummaryRow.run_id == f["run"].id).all()
    assert len(rows) == 1
    assert float(rows[0].on_hand) == 15, "the rewrite must restate, not keep the old figure"


def test_a_run_with_no_buy_recommendation_freezes_nothing(db, chain):
    """Products the engine had nothing to say about are not 22,805 rows nobody can act on."""
    f = chain
    db.query(ReorderRecommendation).filter(
        ReorderRecommendation.run_id == f["run"].id
    ).delete()
    db.flush()

    assert svc.write_rows(db, f["run"].id) == 0
    out = svc.report(db, run_id=f["run"].id)
    assert out["rows"] == []
    # No rows means no computed date, and inventing today's would date a book never built.
    assert out["as_of"] is None


def test_an_unknown_run_is_a_404_rather_than_an_empty_report(db, chain):
    """An empty report and a wrong link look identical on screen, so they must not be."""
    with pytest.raises(AppException) as e:
        svc.report(db, run_id=_u())
    assert e.value.status_code == 404


# =========================================================================== #
# the project / dealer split, and what is in neither
# =========================================================================== #


def test_the_split_reads_order_type_and_leaves_an_unset_row_in_neither(db, chain):
    """A split nobody stated is not a split.

    `demand_class` is populated in 0 of 17 rows, so `order_type` is the source of truth. A
    line whose order carries no type is real demand, and folding it into the bigger bucket
    would state a classification the data does not hold.
    """
    f = chain
    _so(db, f["product"], f["bin"], 30, order_type="project")
    _so(db, f["product"], f["bin"], 12, order_type="dealer")
    _so(db, f["product"], f["bin"], 99, order_type=None)

    svc.write_rows(db, f["run"].id)
    row = svc.report(db, run_id=f["run"].id)["rows"][0]

    assert row["project_demand"] == 30
    assert row["dealer_outstanding"] == 12
    assert row["project_demand_line_count"] == 1
    assert row["dealer_outstanding_line_count"] == 1


def test_the_worst_dealer_ageing_reaches_the_row(db, chain):
    """AC-C2.4's point on the row itself: the row can flag ageing without listing the lines."""
    f = chain
    _so(db, f["product"], f["bin"], 2, order_type="dealer", ordered_days_ago=214)
    _so(db, f["product"], f["bin"], 200, order_type="dealer", ordered_days_ago=6)

    svc.write_rows(db, f["run"].id)
    row = svc.report(db, run_id=f["run"].id)["rows"][0]

    assert row["max_days_outstanding"] == 214, "the row flagged the newest order, not the worst"


def test_nothing_outstanding_leaves_the_ageing_absent_rather_than_zero(db, chain):
    """Null and 0 days outstanding are different facts, and 0 reads as "raised today"."""
    f = chain
    svc.write_rows(db, f["run"].id)

    assert svc.report(db, run_id=f["run"].id)["rows"][0]["max_days_outstanding"] is None


# =========================================================================== #
# a missing input is named, never zeroed
# =========================================================================== #


def test_a_product_with_no_recorded_dimensions_reports_no_volume(db, chain):
    """84% of the book has no dimensions, and a volume of 0 reads as "no space needed"."""
    f = chain
    bare = Product(
        id=_u(), product_code=_code("NODIM"), product_name="no dimensions",
        category_id=f["cat"].id, base_uom_id=f["uom"].id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(bare)
    db.flush()
    db.add(ReorderRecommendation(
        id=_u(), run_id=f["run"].id, rec_type="buy", product_id=bare.id,
        warehouse_id=f["bin"].id, rounded_qty=10, status="proposed",
    ))
    db.flush()

    svc.write_rows(db, f["run"].id)
    rows = {r["product_code"]: r for r in svc.report(db, run_id=f["run"].id)["rows"]}

    assert rows[bare.product_code]["unit_volume_cbm"] is None
    # 1000 x 500 x 200 mm is 0.1 cubic metres, so the populated case is a real figure.
    assert rows[f["product"].product_code]["unit_volume_cbm"] == 0.1


def test_no_demand_statistic_reports_no_average_rather_than_zero(db, chain):
    """A zero average makes months of cover infinite, i.e. "will never run out"."""
    f = chain
    svc.write_rows(db, f["run"].id)

    assert svc.report(db, run_id=f["run"].id)["rows"][0]["avg_daily_demand"] is None


def test_stock_held_nowhere_gives_the_spare_no_stated_home(db, chain):
    """Naming a pool at random is worse than saying the spare has nowhere stated to land."""
    f = chain
    svc.write_rows(db, f["run"].id)
    assert svc.report(db, run_id=f["run"].id)["rows"][0]["spare_lands_at"] is None

    _stock(db, f["product"], f["bin"], 7)
    svc.write_rows(db, f["run"].id)
    # The bin belongs to the pool, so the spare lands in the POOL, not the bin.
    assert (
        svc.report(db, run_id=f["run"].id)["rows"][0]["spare_lands_at"]
        == f["pool"].warehouse_code
    )


# =========================================================================== #
# drill-downs
# =========================================================================== #


def test_the_dealer_drill_comes_back_worst_first(db, chain):
    """AC-C2.4: the SERVER owns the ordering.

    A small quantity that has waited 214 days outranks a large one raised last week, and a
    client free to re-sort could disagree with the row's own ageing flag.
    """
    f = chain
    _so(db, f["product"], f["bin"], 200, order_type="dealer", ordered_days_ago=6)
    _so(db, f["product"], f["bin"], 2, order_type="dealer", ordered_days_ago=214)
    _so(db, f["product"], f["bin"], 50, order_type="dealer", ordered_days_ago=40)

    out = svc.demand_drill(db, f["product"].product_code, kind="dealer")

    assert [l["days_outstanding"] for l in out["dealer_lines"]] == [214, 40, 6]
    assert out["total_qty"] == 252
    assert out["project_lines"] == []


def test_the_project_drill_is_dated_with_undated_lines_last(db, chain):
    """Ordering by date puts the urgent line first; `date.min` would put the undated one there."""
    f = chain
    _so(db, f["product"], f["bin"], 10, order_type="project", required_in=60)
    _so(db, f["product"], f["bin"], 20, order_type="project", required_in=5)

    out = svc.demand_drill(db, f["product"].product_code, kind="project")

    assert [l["qty"] for l in out["project_lines"]] == [20, 10]
    assert out["dealer_lines"] == []


def test_a_drill_total_equals_the_row_aggregate(db, chain):
    """The row figure is derived from these lines and never retyped by a person (AC-C2.3)."""
    f = chain
    _so(db, f["product"], f["bin"], 30, order_type="project")
    _so(db, f["product"], f["bin"], 45, order_type="project")
    svc.write_rows(db, f["run"].id)

    row = svc.report(db, run_id=f["run"].id)["rows"][0]
    drill = svc.demand_drill(db, f["product"].product_code, kind="project")

    assert drill["total_qty"] == row["project_demand"] == 75


def test_an_unknown_drill_kind_is_refused(db, chain):
    with pytest.raises(AppException) as e:
        svc.demand_drill(db, chain["product"].product_code, kind="everything")
    assert e.value.status_code == 422


# =========================================================================== #
# supplier candidates
# =========================================================================== #


def test_a_supplier_who_never_delivered_this_item_says_so(db, chain):
    """AC-C2.5: otherwise a low price makes them look merely cheap.

    Delivered means RECEIVED against, not ordered: ten open orders and no arrivals is a
    supplier who has never actually delivered it.
    """
    f = chain
    never = _supplier(db, "never delivered")
    has = _supplier(db, "has delivered")
    _po(db, f["product"], f["bin"], 100, supplier=never, cost=10, received=0)
    _po(db, f["product"], f["bin"], 100, supplier=has, cost=25, received=100)

    out = svc.suppliers_for(db, f["product"].product_code)
    by_code = {c["supplier_code"]: c for c in out["candidates"]}

    assert by_code[never.supplier_code]["delivered_line_count"] == 0
    assert by_code[has.supplier_code]["delivered_line_count"] == 1
    # Cheapest first, so the one who never delivered leads the list - which is exactly why the
    # count has to be on the row.
    assert out["candidates"][0]["supplier_code"] == never.supplier_code


def test_a_long_ago_last_purchase_is_flagged_by_the_server(db, chain):
    """AC-C2.6: the verdict is the server's so it cannot drift between screens."""
    f = chain
    old = _supplier(db, "last bought years ago")
    recent = _supplier(db, "bought last month")
    _po(db, f["product"], f["bin"], 10, supplier=old, cost=5, issued_days_ago=900)
    _po(db, f["product"], f["bin"], 10, supplier=recent, cost=6, issued_days_ago=30)

    out = svc.suppliers_for(db, f["product"].product_code)
    by_code = {c["supplier_code"]: c for c in out["candidates"]}

    assert by_code[old.supplier_code]["is_stale"] is True
    assert by_code[old.supplier_code]["stale_days"] == 900
    assert by_code[recent.supplier_code]["is_stale"] is False
    # The threshold travels with the answer so the screen can say what stale means.
    assert out["stale_after_days"] == svc.DEFAULT_STALE_AFTER_DAYS


def test_the_last_purchase_order_is_the_newest_one(db, chain):
    """A buyer reading "last PO cost" must be reading the last one, not an arbitrary one."""
    f = chain
    sup = _supplier(db)
    _po(db, f["product"], f["bin"], 10, supplier=sup, cost=9, issued_days_ago=400)
    _po(db, f["product"], f["bin"], 10, supplier=sup, cost=11, issued_days_ago=20)

    out = svc.suppliers_for(db, f["product"].product_code)

    assert len(out["candidates"]) == 1, "one supplier is one candidate"
    assert out["candidates"][0]["last_po_cost"] == 11


def test_no_incoming_cost_recorded_means_no_variance_rather_than_a_zero_one(db, chain):
    """AC-C3.3 with the data as it is: incoming cost is populated in 0 of 1,015 rows.

    A variance of 0 would say the supplier held its price, which is a claim nobody can make
    from a missing figure. The whole point of the variance is catching a reprice after we
    committed, so inventing one defeats it.
    """
    f = chain
    sup = _supplier(db)
    _po(db, f["product"], f["bin"], 10, supplier=sup, cost=20)

    c = svc.suppliers_for(db, f["product"].product_code)["candidates"][0]

    assert c["last_incoming_cost"] is None
    assert c["cost_variance"] is None


def test_an_incoming_cost_in_another_currency_produces_no_variance(db, chain):
    """Subtracting different units yields a number that looks like a reprice and is not one."""
    f = chain
    sup = _supplier(db)
    _po(db, f["product"], f["bin"], 10, supplier=sup, cost=20, currency="USD")
    ship = InboundShipment(
        id=_u(), shipment_number=_code("SH")[:50], supplier_id=sup.id,
        shipment_date=_today() - timedelta(days=10),
        estimated_arrival_date=_today() + timedelta(days=5),
        shipment_status="in_transit",
    )
    db.add(ship)
    db.flush()
    db.add(InboundShipmentLine(
        id=_u(), shipment_id=ship.id, product_id=f["product"].id,
        quantity_shipped=10, quantity_received=0, cartons_count=1,
        unit_cost=95, currency="MYR", line_status="in_transit",
    ))
    db.flush()

    c = svc.suppliers_for(db, f["product"].product_code)["candidates"][0]

    assert c["last_incoming_cost"] == 95
    assert c["cost_variance"] is None, "a cross-currency subtraction is not a variance"


def test_an_incoming_cost_above_the_ordered_cost_is_a_positive_variance(db, chain):
    """AC-C3.3: a supplier whose incoming cost drifts UP repriced after we committed."""
    f = chain
    sup = _supplier(db)
    _po(db, f["product"], f["bin"], 10, supplier=sup, cost=20, currency="USD")
    ship = InboundShipment(
        id=_u(), shipment_number=_code("SH")[:50], supplier_id=sup.id,
        shipment_date=_today() - timedelta(days=10),
        estimated_arrival_date=_today() + timedelta(days=5),
        shipment_status="in_transit",
    )
    db.add(ship)
    db.flush()
    db.add(InboundShipmentLine(
        id=_u(), shipment_id=ship.id, product_id=f["product"].id,
        quantity_shipped=10, quantity_received=0, cartons_count=1,
        unit_cost=23, currency="USD", line_status="in_transit",
    ))
    db.flush()

    c = svc.suppliers_for(db, f["product"].product_code)["candidates"][0]

    assert c["cost_variance"] == 3


# =========================================================================== #
# the decision
# =========================================================================== #


def test_a_quantity_above_the_shortfall_is_recorded_without_complaint(db, chain):
    """AC-C2.7: buying spare is a legitimate call, and warning on it teaches a workaround."""
    f = chain
    _so(db, f["product"], f["bin"], 100, order_type="project")
    sup = _supplier(db)
    svc.write_rows(db, f["run"].id)

    out = svc.record_decision(
        db, f["product"].product_code, run_id=f["run"].id,
        chosen_qty=500, supplier_code=sup.supplier_code, actor="mr loo",
    )

    assert out["chosen_qty"] == 500
    # The engine's figure survives beside it (AC-C2.8), never replaced by it.
    assert out["suggested_qty"] == 120
    assert out["decided_by"] == "mr loo"
    assert out["decided_at"]
    assert out["chosen_supplier_code"] == sup.supplier_code


def test_the_decision_reaches_the_report_row(db, chain):
    """Recorded and invisible is the same as not recorded, from the next reader's seat."""
    f = chain
    sup = _supplier(db)
    svc.write_rows(db, f["run"].id)
    svc.record_decision(
        db, f["product"].product_code, run_id=f["run"].id,
        chosen_qty=200, supplier_code=sup.supplier_code, actor="mr loo",
    )

    row = svc.report(db, run_id=f["run"].id)["rows"][0]

    assert row["chosen_qty"] == 200
    assert row["chosen_supplier_code"] == sup.supplier_code
    assert row["chosen_supplier_name"] == sup.supplier_name
    assert row["decided_by"] == "mr loo"
    assert row["suggested_qty"] == 120, "the suggestion is still there to compare against"


def test_deciding_to_buy_nothing_is_recordable(db, chain):
    """Zero is the "use the pool, do not buy" answer this module exists to be able to give.

    It has to be storable or S4's worklist shows a gap where a decision was made, and cannot
    reconcile one-for-one against the decisions.
    """
    f = chain
    sup = _supplier(db)
    svc.write_rows(db, f["run"].id)

    out = svc.record_decision(
        db, f["product"].product_code, run_id=f["run"].id,
        chosen_qty=0, supplier_code=sup.supplier_code, actor="mr loo",
    )

    assert out["chosen_qty"] == 0
    assert svc.report(db, run_id=f["run"].id)["rows"][0]["chosen_qty"] == 0


def test_a_negative_quantity_is_refused(db, chain):
    """Unlike zero, there is no reading of a negative order quantity."""
    f = chain
    sup = _supplier(db)
    svc.write_rows(db, f["run"].id)

    with pytest.raises(AppException) as e:
        svc.record_decision(
            db, f["product"].product_code, run_id=f["run"].id,
            chosen_qty=-5, supplier_code=sup.supplier_code,
        )
    assert e.value.status_code == 422


def test_deciding_on_a_product_the_plan_does_not_hold_is_refused(db, chain):
    """A decision with nowhere to land would return 200 and change nothing."""
    f = chain
    sup = _supplier(db)
    other = Product(
        id=_u(), product_code=_code("OTHER"), product_name="not planned",
        category_id=f["cat"].id, base_uom_id=f["uom"].id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(other)
    db.flush()
    svc.write_rows(db, f["run"].id)

    with pytest.raises(AppException) as e:
        svc.record_decision(
            db, other.product_code, run_id=f["run"].id,
            chosen_qty=10, supplier_code=sup.supplier_code,
        )
    assert e.value.status_code == 404


def test_an_unknown_supplier_code_is_refused(db, chain):
    f = chain
    svc.write_rows(db, f["run"].id)

    with pytest.raises(AppException) as e:
        svc.record_decision(
            db, f["product"].product_code, run_id=f["run"].id,
            chosen_qty=10, supplier_code=_code("NOSUCH"),
        )
    assert e.value.status_code == 404


def test_a_second_decision_restates_the_first(db, chain):
    """Changing your mind is normal; the row states the CURRENT decision.

    The audit trail of the change is the audit listeners' job, not a second column here.
    """
    f = chain
    sup = _supplier(db)
    svc.write_rows(db, f["run"].id)
    svc.record_decision(
        db, f["product"].product_code, run_id=f["run"].id,
        chosen_qty=200, supplier_code=sup.supplier_code, actor="mr loo",
    )
    out = svc.record_decision(
        db, f["product"].product_code, run_id=f["run"].id,
        chosen_qty=150, supplier_code=sup.supplier_code, actor="mr loo",
    )

    assert out["chosen_qty"] == 150
    assert svc.report(db, run_id=f["run"].id)["rows"][0]["chosen_qty"] == 150


# =========================================================================== #
# the candidate SET is the linked suppliers, not the receipts
# =========================================================================== #


def _link(db, product, supplier, *, cost=None, currency="USD", lead=14,
          moq=None, multiple=None, primary=False):
    """A `product_suppliers` row: the link that makes a supplier choosable at all.

    `standard_lead_time_days` is NOT NULL in the database, so it defaults to a real figure
    here rather than None - the model marks it nullable, which is model-vs-column drift, and
    the constraint is the one that decides.
    """
    from app.models.procurement import ProductSupplier

    row = ProductSupplier(
        id=_u(), product_id=product.id, supplier_id=supplier.id,
        unit_cost=cost, currency=currency, standard_lead_time_days=lead,
        moq=moq, order_multiple=multiple, is_primary_supplier=primary,
    )
    db.add(row)
    db.flush()
    return row


def test_a_linked_supplier_with_no_purchase_history_is_still_choosable(db, chain):
    """The defect this fixes, seen on the live page.

    C-FH24 showed a supplier and a cost on the plan grid while this screen said "No supplier
    linked to this item": the plan sources from `product_suppliers` and the screen was built
    from PO lines, so an item never bought had no choosable supplier and a newly linked one
    could never be picked. "Supplier is a selectable choice" (AC-C2.5) means the choices are
    the LINKS.
    """
    f = chain
    sup = _supplier(db, "linked, never bought from")
    _link(db, f["product"], sup, cost=42, lead=45)

    out = svc.suppliers_for(db, f["product"].product_code)
    codes = [c["supplier_code"] for c in out["candidates"]]

    assert sup.supplier_code in codes
    c = next(c for c in out["candidates"] if c["supplier_code"] == sup.supplier_code)
    # The link's quoted price stands in for the ordered cost until there IS an ordered cost.
    assert c["last_po_cost"] == 42
    assert c["last_po_date"] is None
    assert c["lead_time_days"] == 45
    # Never bought is never delivered, and never bought is not stale either - there is no
    # last purchase to be old.
    assert c["delivered_line_count"] == 0
    assert c["is_stale"] is False
    assert c["stale_days"] is None


def test_the_ordered_cost_beats_the_links_quoted_price(db, chain):
    """AC-C3.1 reads the cost off the PO line. The link is a quote; the PO is a commitment."""
    f = chain
    sup = _supplier(db)
    _link(db, f["product"], sup, cost=42, currency="USD")
    _po(db, f["product"], f["bin"], 10, supplier=sup, cost=55, currency="USD")

    c = svc.suppliers_for(db, f["product"].product_code)["candidates"][0]

    assert c["last_po_cost"] == 55
    assert c["last_po_number"]


def test_a_supplier_bought_from_but_no_longer_linked_still_appears(db, chain):
    """Dropping them would lose the comparison that makes a switch arguable.

    They are a real historical source with a real price; the screen's job is to let a buyer
    see it, not to hide it because somebody removed a link.
    """
    f = chain
    unlinked = _supplier(db, "bought from, link removed")
    _po(db, f["product"], f["bin"], 10, supplier=unlinked, cost=7)

    codes = [
        c["supplier_code"]
        for c in svc.suppliers_for(db, f["product"].product_code)["candidates"]
    ]

    assert unlinked.supplier_code in codes


def test_the_primary_supplier_leads_the_list_even_when_another_is_cheaper(db, chain):
    """Burying the deliberately marked link under a cheaper one argues for an unproposed switch."""
    f = chain
    primary = _supplier(db, "the primary")
    cheaper = _supplier(db, "cheaper but not primary")
    _link(db, f["product"], primary, cost=100, primary=True)
    _link(db, f["product"], cheaper, cost=10, primary=False)

    out = svc.suppliers_for(db, f["product"].product_code)

    assert out["candidates"][0]["supplier_code"] == primary.supplier_code
    assert out["candidates"][1]["supplier_code"] == cheaper.supplier_code
    # And the private sort marker does not leak onto the wire.
    assert "_is_primary" not in out["candidates"][0]


def test_an_unset_moq_is_absent_rather_than_one(db, chain):
    """`moq` and `order_multiple` are populated in 0 of 17,408 links.

    A 1 would read as "round to anything", which is a rounding rule nobody set.
    """
    f = chain
    sup = _supplier(db)
    _link(db, f["product"], sup, cost=5)

    c = svc.suppliers_for(db, f["product"].product_code)["candidates"][0]

    assert c["moq"] is None
    assert c["order_multiple"] is None


def test_a_stated_moq_and_multiple_reach_the_wire(db, chain):
    """So the day somebody fills the columns in, the screen shows them without a code change."""
    f = chain
    sup = _supplier(db)
    _link(db, f["product"], sup, cost=5, moq=50, multiple=25)

    c = svc.suppliers_for(db, f["product"].product_code)["candidates"][0]

    assert c["moq"] == 50
    assert c["order_multiple"] == 25
