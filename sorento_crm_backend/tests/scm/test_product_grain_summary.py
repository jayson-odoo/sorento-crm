"""S2-BE-4: the Product-grain summary row and its channel breakdown
(PLAN-scm-front-planning.md 5.3, 5.4, 6.4; UAC-scm-front-planning.md AC-E03, E05, E06, F03,
F05, F07 through F12).

`scm.order_summary_row` gains three frozen Numeric quantities - `project_buy_qty`,
`retail_replenishment_qty`, `unclassified_demand_qty` - summed from the SAME per-location
`ReorderRecommendation.inputs` channel breakdown S2-BE-3 freezes (`project_need`,
`retail_need`, `unclassified_need`), plus `earliest_project_need_date`,
`channel_calculation_basis` and a frozen `uom_decimal_places` snapshot. `suggested_qty` on a
new run stops being `math.ceil(sum(per-location rounded_qty))` and becomes ONE rounding of
`project_buy_qty + retail_replenishment_qty` (unclassified excluded) at supplier MOQ/multiple
and the frozen `uom_decimal_places` (AC-F11).

Most tests seed `ReorderRecommendation` rows BY HAND with a controlled `inputs` dict - the
same "manually built recommendation, `write_rows` reads it" idiom
`tests/scm/test_summary_order_service.py` already uses - rather than running the whole engine,
so the arithmetic under test is isolated from engine trigger/sizing behaviour (which
`test_channel_read_model.py` covers separately with a real run).

Every construction of a not-yet-existing column or model (`OrderSummaryRow.project_buy_qty`,
`OrderSummaryLocationAllocation`, `ReorderRun.decision_grain`, `UnitOfMeasure.decimal_places`,
...) is deliberate: it is what makes the test fail for "the feature does not exist yet"
(TypeError / AttributeError / ImportError / UndefinedColumn) rather than a fixture bug.

Postgres, marker-prefixed seeding, rolled back at teardown. Nothing borrowed with LIMIT 1.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import ProductSupplier, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import OrderSummaryRow, ReorderRecommendation, ReorderRun
from app.services.error_handler import AppException
from app.services.scm import reorder_engine as eng
from app.services.scm import summary_order_service as svc
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session

MARKER = "ZZTPGS"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _today() -> date:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


def _now():
    return to_naive_datetime(datetime.now(MALAYSIA_TZ))


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


# --------------------------------------------------------------------------- #
# seed helpers - each test builds only the chain it needs (no shared mega-fixture)
# --------------------------------------------------------------------------- #

def _product(db, *, decimal_places=None, stem="P") -> Product:
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=f"{MARKER} cat")
    uom_kwargs = {} if decimal_places is None else {"decimal_places": decimal_places}
    uom = UnitOfMeasure(id=_u(), uom_code=_code("U")[:20], uom_name=f"{MARKER} {stem} uom",
                        **uom_kwargs)
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_u(), product_code=_code(stem), product_name=f"{MARKER} {stem} product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(product)
    db.flush()
    return product


def _warehouse(db, stem="W") -> Warehouse:
    wh = Warehouse(
        id=_u(), warehouse_code=_code(stem)[:30], warehouse_name=f"{MARKER} {stem}",
        is_active=True, counts_as_available=True,
    )
    db.add(wh)
    db.flush()
    return wh


def _run(db, *, decision_grain=None, contract_version=None, status="completed") -> ReorderRun:
    kwargs = {}
    if decision_grain is not None:
        kwargs["decision_grain"] = decision_grain
    if contract_version is not None:
        kwargs["front_planning_contract_version"] = contract_version
    run = ReorderRun(
        id=_u(), status=status, buy_scope="warehouse",
        started_at=_now(), source_system="scm", source_ref=_code("RUN"), **kwargs,
    )
    db.add(run)
    db.flush()
    return run


def _rec(db, run, product, warehouse, *, rounded_qty=0, inputs=None,
         net_position=None, forecast_daily_demand=None) -> ReorderRecommendation:
    r = ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=warehouse.id, rounded_qty=rounded_qty, net_position=net_position,
        forecast_daily_demand=forecast_daily_demand, inputs=inputs or {}, status="proposed",
    )
    db.add(r)
    db.flush()
    return r


def _supplier_link(db, product, *, moq=None, multiple=None) -> Supplier:
    sup = Supplier(id=_u(), supplier_code=_code("S")[:30], supplier_name=f"{MARKER} supplier")
    db.add(sup)
    db.flush()
    db.add(ProductSupplier(
        id=_u(), product_id=product.id, supplier_id=sup.id, standard_lead_time_days=14,
        moq=moq, order_multiple=multiple, unit_cost=10, currency="MYR",
        is_primary_supplier=True,
    ))
    db.flush()
    return sup


def _so_line(db, product, warehouse, *, qty=10, delivered=0, order_type=None,
            demand_class=None) -> SalesOrderLine:
    cust = Customer(id=_u(), customer_code=_code("C")[:30], customer_name=f"{MARKER} customer")
    db.add(cust)
    db.flush()
    so = SalesOrder(
        id=_u(), so_number=_code("SO"), customer_id=cust.id, status="open",
        order_type=order_type, demand_class=demand_class,
        order_date=_today() - timedelta(days=3),
    )
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product.id, warehouse_id=warehouse.id,
        qty_ordered=qty, qty_delivered=delivered, line_status="open",
        required_date=_today() + timedelta(days=10),
    )
    db.add(line)
    db.flush()
    return line


def _row(db, run, product) -> OrderSummaryRow:
    return (
        db.query(OrderSummaryRow)
        .filter(OrderSummaryRow.run_id == run.id, OrderSummaryRow.product_id == product.id)
        .one()
    )


# =========================================================================== #
# the new columns and the new model exist
# =========================================================================== #

def test_order_summary_row_has_the_new_channel_columns(db):
    """PLAN 6.4: nullable Numeric x3, nullable Date, nullable JSONB, nullable SmallInteger,
    all on the SAME `scm.order_summary_row` identity keyed by (run_id, product_id)."""
    product = _product(db)
    run = _run(db)
    row = OrderSummaryRow(
        id=_u(), run_id=run.id, product_id=product.id, as_of=_today(), computed_at=_now(),
        project_buy_qty=12, retail_replenishment_qty=8, unclassified_demand_qty=3,
        earliest_project_need_date=_today() + timedelta(days=5),
        channel_calculation_basis={"note": f"{MARKER} basis"}, uom_decimal_places=2,
    )
    db.add(row)
    db.flush()

    stored = db.execute(
        text(
            "SELECT project_buy_qty, retail_replenishment_qty, unclassified_demand_qty, "
            "earliest_project_need_date, channel_calculation_basis, uom_decimal_places "
            "FROM scm.order_summary_row WHERE id = :id"
        ),
        {"id": row.id},
    ).mappings().one()
    assert float(stored["project_buy_qty"]) == 12
    assert float(stored["retail_replenishment_qty"]) == 8
    assert float(stored["unclassified_demand_qty"]) == 3
    assert stored["earliest_project_need_date"] == _today() + timedelta(days=5)
    assert stored["channel_calculation_basis"]["note"] == f"{MARKER} basis"
    assert stored["uom_decimal_places"] == 2


def test_order_summary_location_allocation_model_exists(db):
    """PLAN 6.4: the narrow child table persisting the PO-worklist location split."""
    from app.models.scm import OrderSummaryLocationAllocation  # noqa: PLC0415 - new model

    product = _product(db)
    run = _run(db)
    wh = _warehouse(db)
    row = OrderSummaryRow(id=_u(), run_id=run.id, product_id=product.id, as_of=_today(),
                          computed_at=_now())
    db.add(row)
    db.flush()

    alloc = OrderSummaryLocationAllocation(
        id=_u(), order_summary_row_id=row.id, warehouse_id=wh.id, allocated_qty=5,
    )
    db.add(alloc)
    db.flush()

    stored = db.query(OrderSummaryLocationAllocation).filter_by(id=alloc.id).one()
    assert float(stored.allocated_qty) == 5
    assert stored.reorder_recommendation_id is None, "nullable - a product-grain split has no single owning recommendation row"


def test_location_allocation_enforces_one_row_per_summary_row_and_warehouse(db):
    from app.models.scm import OrderSummaryLocationAllocation  # noqa: PLC0415

    product = _product(db)
    run = _run(db)
    wh = _warehouse(db)
    row = OrderSummaryRow(id=_u(), run_id=run.id, product_id=product.id, as_of=_today(),
                          computed_at=_now())
    db.add(row)
    db.flush()
    db.add(OrderSummaryLocationAllocation(
        id=_u(), order_summary_row_id=row.id, warehouse_id=wh.id, allocated_qty=5,
    ))
    db.flush()
    db.add(OrderSummaryLocationAllocation(
        id=_u(), order_summary_row_id=row.id, warehouse_id=wh.id, allocated_qty=3,
    ))
    with pytest.raises(IntegrityError):
        db.flush()


def test_location_allocation_rejects_a_negative_allocated_qty(db):
    from app.models.scm import OrderSummaryLocationAllocation  # noqa: PLC0415

    product = _product(db)
    run = _run(db)
    wh = _warehouse(db)
    row = OrderSummaryRow(id=_u(), run_id=run.id, product_id=product.id, as_of=_today(),
                          computed_at=_now())
    db.add(row)
    db.flush()
    db.add(OrderSummaryLocationAllocation(
        id=_u(), order_summary_row_id=row.id, warehouse_id=wh.id, allocated_qty=-1,
    ))
    with pytest.raises(IntegrityError):
        db.flush()


# =========================================================================== #
# write_rows: the three channel quantities, summed across locations
# =========================================================================== #

def test_write_rows_sums_project_and_retail_need_across_locations(db):
    """AC-F05/F07: `project_buy_qty` / `retail_replenishment_qty` are the SUM of the frozen
    per-location `project_need` / `retail_need` - the same figures `test_channel_read_model.py`
    pins on the recommendation `inputs` snapshot, read back here at the product grain."""
    product = _product(db)
    run = _run(db, decision_grain="product", contract_version=1)
    brw, jb = _warehouse(db, "BRW"), _warehouse(db, "JB")
    _rec(db, run, product, brw, rounded_qty=1,
         inputs={"project_need": 1, "retail_need": 0, "unclassified_need": 0})
    _rec(db, run, product, jb, rounded_qty=1,
         inputs={"project_need": 0, "retail_need": 1, "unclassified_need": 2})

    assert svc.write_rows(db, run.id) == 1
    row = _row(db, run, product)

    assert float(row.project_buy_qty) == 1
    assert float(row.retail_replenishment_qty) == 1
    assert float(row.unclassified_demand_qty) == 2


def test_earliest_project_need_date_is_null_when_project_buy_qty_is_zero(db):
    product = _product(db)
    run = _run(db, decision_grain="product", contract_version=1)
    wh = _warehouse(db)
    _rec(db, run, product, wh, rounded_qty=3,
         inputs={"project_need": 0, "retail_need": 3, "unclassified_need": 0})

    svc.write_rows(db, run.id)
    row = _row(db, run, product)

    assert float(row.project_buy_qty) == 0
    assert row.earliest_project_need_date is None


def test_uom_decimal_places_is_copied_from_the_products_base_uom(db):
    product = _product(db, decimal_places=3, stem="KG")
    run = _run(db, decision_grain="product", contract_version=1)
    wh = _warehouse(db)
    _rec(db, run, product, wh, rounded_qty=1,
         inputs={"project_need": 1, "retail_need": 0, "unclassified_need": 0})

    svc.write_rows(db, run.id)
    row = _row(db, run, product)

    assert row.uom_decimal_places == 3


# =========================================================================== #
# AC-F11: MOQ / order multiple round the PRODUCT total once, never per location
# =========================================================================== #

def test_suggested_qty_rounds_the_product_total_once_not_per_location(db):
    """Project need 1 at BRW, retail need 1 at JB, supplier multiple 10, no MOQ.

    The OLD `write_rows` rounds each location's `rounded_qty` up to a whole unit and sums
    (1 + 1 -> 2), which is not even wrong in the direction AC-F11 forbids - it happens to
    also be wrong: the multiple must apply ONCE to the product total (2 -> 10), not never
    and not per-location.
    """
    product = _product(db)
    run = _run(db, decision_grain="product", contract_version=1)
    brw, jb = _warehouse(db, "BRW"), _warehouse(db, "JB")
    _supplier_link(db, product, moq=None, multiple=10)
    _rec(db, run, product, brw, rounded_qty=1,
         inputs={"project_need": 1, "retail_need": 0, "unclassified_need": 0})
    _rec(db, run, product, jb, rounded_qty=1,
         inputs={"project_need": 0, "retail_need": 1, "unclassified_need": 0})

    svc.write_rows(db, run.id)
    row = _row(db, run, product)

    assert float(row.suggested_qty) == 10


def test_suggested_qty_keeps_fractional_precision_with_no_supplier_constraint(db):
    """kg product, `decimal_places=3`, no MOQ or multiple: total need 2.5 stays 2.5 - the
    once-rounded figure is not defaulted to a whole unit just because nothing constrains it.
    """
    product = _product(db, decimal_places=3, stem="KG")
    run = _run(db, decision_grain="product", contract_version=1)
    brw, jb = _warehouse(db, "BRW"), _warehouse(db, "JB")
    _rec(db, run, product, brw, rounded_qty=1.5,
         inputs={"project_need": 1.5, "retail_need": 0, "unclassified_need": 0})
    _rec(db, run, product, jb, rounded_qty=1.0,
         inputs={"project_need": 0, "retail_need": 1.0, "unclassified_need": 0})

    svc.write_rows(db, run.id)
    row = _row(db, run, product)

    assert float(row.suggested_qty) == 2.5


def test_an_ea_products_fractional_need_rounds_to_a_whole_unit_once(db):
    """EA product, `decimal_places=0`, no supplier constraint: need 2.5 rounds to 3 - once,
    at the product total, matching the frozen `uom_decimal_places`."""
    product = _product(db, decimal_places=0, stem="EA")
    run = _run(db, decision_grain="product", contract_version=1)
    wh = _warehouse(db)
    _rec(db, run, product, wh, rounded_qty=2.5,
         inputs={"project_need": 1.2, "retail_need": 1.3, "unclassified_need": 0})

    svc.write_rows(db, run.id)
    row = _row(db, run, product)

    assert float(row.suggested_qty) == 3


def test_unclassified_need_never_enters_the_suggested_quantity(db):
    """AC-E06: unclassified demand stays visible on the row but is excluded from the
    actionable total."""
    product = _product(db)
    run = _run(db, decision_grain="product", contract_version=1)
    wh = _warehouse(db)
    _rec(db, run, product, wh, rounded_qty=5,
         inputs={"project_need": 2, "retail_need": 3, "unclassified_need": 100})

    svc.write_rows(db, run.id)
    row = _row(db, run, product)

    assert float(row.unclassified_demand_qty) == 100
    assert float(row.suggested_qty) == 5, "unclassified must not inflate the actionable total"


def test_project_buy_is_not_suppressed_by_a_retail_reorder_trigger(db):
    """AC-E05 at the product grain: a firm project buy survives even when retail alone
    would not have triggered anything."""
    product = _product(db)
    run = _run(db, decision_grain="product", contract_version=1)
    wh = _warehouse(db)
    _rec(db, run, product, wh, rounded_qty=5,
         inputs={"project_need": 5, "retail_need": 0, "unclassified_need": 0})

    svc.write_rows(db, run.id)
    row = _row(db, run, product)

    assert float(row.project_buy_qty) == 5
    assert float(row.suggested_qty) == 5


# =========================================================================== #
# `_demand_aggregates` and `demand_drill` re-based on `demand_class`
# =========================================================================== #

def test_demand_aggregates_classifies_by_demand_class_not_order_type(db):
    """A `dealer` order_type with a `project` demand_class is Project, full stop - the
    persisted class overrides the legacy order_type basis (AC-E01 applied to the open-SO
    diagnostic figures, not only the confirmed-Buy leg)."""
    product = _product(db)
    run = _run(db)
    wh = _warehouse(db)
    _so_line(db, product, wh, qty=40, order_type="dealer", demand_class="project")
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=wh.id, rounded_qty=10, status="proposed",
    ))
    db.flush()

    svc.write_rows(db, run.id)
    row = svc.report(db, run_id=run.id)["rows"][0]

    assert row["project_demand"] == 40
    assert row["dealer_outstanding"] == 0


def test_a_missing_demand_class_is_reported_as_unclassified_with_a_line_count(db):
    product = _product(db)
    run = _run(db)
    wh = _warehouse(db)
    _so_line(db, product, wh, qty=17, order_type=None, demand_class=None)
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=wh.id, rounded_qty=10, status="proposed",
    ))
    db.flush()

    svc.write_rows(db, run.id)
    row = svc.report(db, run_id=run.id)["rows"][0]

    assert row["unclassified_line_count"] == 1


def test_demand_drill_retail_kind_reads_the_persisted_demand_class(db):
    product = _product(db)
    _so_line(db, product, _warehouse(db), qty=22, order_type=None, demand_class="retail")

    out = svc.demand_drill(db, product.product_code, kind="retail")

    assert out["total_qty"] == 22


def test_demand_drill_dealer_is_an_alias_of_retail(db):
    product = _product(db)
    _so_line(db, product, _warehouse(db), qty=9, order_type=None, demand_class="retail")

    retail = svc.demand_drill(db, product.product_code, kind="retail")
    dealer = svc.demand_drill(db, product.product_code, kind="dealer")

    assert retail["total_qty"] == dealer["total_qty"] == 9


def test_demand_drill_unclassified_kind_returns_lines_and_the_exception(db):
    product = _product(db)
    _so_line(db, product, _warehouse(db), qty=6, order_type=None, demand_class=None)

    out = svc.demand_drill(db, product.product_code, kind="unclassified")

    assert out["total_qty"] == 6
    assert out["kind"] == "unclassified"


# =========================================================================== #
# report serialiser: retail_outstanding, decision_grain, is_legacy
# =========================================================================== #

def test_report_exposes_retail_outstanding_as_an_alias_of_dealer_outstanding(db):
    product = _product(db)
    run = _run(db)
    wh = _warehouse(db)
    _so_line(db, product, wh, qty=14, order_type=None, demand_class="retail")
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=wh.id, rounded_qty=10, status="proposed",
    ))
    db.flush()

    svc.write_rows(db, run.id)
    row = svc.report(db, run_id=run.id)["rows"][0]

    assert row["retail_outstanding"] == row["dealer_outstanding"] == 14
    assert row["retail_outstanding_line_count"] == row["dealer_outstanding_line_count"] == 1


def test_report_exposes_decision_grain_and_is_legacy_on_a_new_run(db):
    product = _product(db)
    run = _run(db, decision_grain="product", contract_version=1)
    wh = _warehouse(db)
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=wh.id, rounded_qty=10, status="proposed",
    ))
    db.flush()

    svc.write_rows(db, run.id)
    row = svc.report(db, run_id=run.id)["rows"][0]

    assert row["decision_grain"] == "product"
    assert row["is_legacy"] is False


def test_a_legacy_run_reports_is_legacy_and_no_channel_fields(db):
    """AC-E03 / AC-F10: a run created before this contract (NULL `front_planning_contract_
    version`) keeps its stored `project_demand` / `dealer_outstanding` figures but returns
    None for the new channel fields - no semantic backfill is attempted."""
    product = _product(db)
    run = _run(db)  # no decision_grain / contract_version kwargs -> both NULL, exactly as a
                    # legacy run stays today
    wh = _warehouse(db)
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=wh.id, rounded_qty=10, status="proposed",
    ))
    db.flush()

    svc.write_rows(db, run.id)
    row = svc.report(db, run_id=run.id)["rows"][0]

    assert row["is_legacy"] is True
    assert row["decision_grain"] is None
    assert row["project_buy_qty"] is None
    assert row["retail_replenishment_qty"] is None
    assert row["unclassified_demand_qty"] is None


# =========================================================================== #
# svc.locations: the drill reconciles against the product row (AC-F07, F08)
# =========================================================================== #

def test_locations_drill_reconciles_the_product_rows_three_quantities(db):
    """AC-F03/F07/F08: the per-location channel breakdown the drill opens to must sum back
    to exactly the three quantities the product row carries - one calculation, two
    presentations, never two different answers for the same number."""
    product = _product(db)
    run = _run(db, decision_grain="product", contract_version=1)
    brw, jb = _warehouse(db, "BRW"), _warehouse(db, "JB")
    _rec(db, run, product, brw, rounded_qty=6,
         inputs={"project_need": 4, "retail_need": 2, "unclassified_need": 1})
    _rec(db, run, product, jb, rounded_qty=5,
         inputs={"project_need": 0, "retail_need": 3, "unclassified_need": 2})
    svc.write_rows(db, run.id)
    row = _row(db, run, product)

    out = svc.locations(db, product.product_code, run_id=run.id)

    assert len(out["locations"]) == 2
    assert sum(l["project_need"] for l in out["locations"]) == float(row.project_buy_qty) == 4
    assert (sum(l["retail_need"] for l in out["locations"])
            == float(row.retail_replenishment_qty) == 5)
    assert (sum(l["unclassified_need"] for l in out["locations"])
            == float(row.unclassified_demand_qty) == 3)
    assert out["suggested_qty"] == float(row.suggested_qty)
    assert out["uom_decimal_places"] == row.uom_decimal_places


def test_locations_drill_earliest_need_date_is_null_when_project_buy_qty_is_zero(db):
    """AC-F08: the gate follows `project_buy_qty`, read through the drill rather than off
    the row directly - nothing confirmed anywhere in the locations means no date, even
    though the product still shows retail need."""
    product = _product(db)
    run = _run(db, decision_grain="product", contract_version=1)
    wh = _warehouse(db)
    _rec(db, run, product, wh, rounded_qty=3,
         inputs={"project_need": 0, "retail_need": 3, "unclassified_need": 0})
    svc.write_rows(db, run.id)
    row = _row(db, run, product)

    out = svc.locations(db, product.product_code, run_id=run.id)

    assert sum(l["project_need"] for l in out["locations"]) == 0 == float(row.project_buy_qty)
    assert row.earliest_project_need_date is None


def test_locations_drill_earliest_need_date_gate_opens_for_a_real_confirmed_buy(db):
    """AC-F08: once a real confirmed Buy backs `project_buy_qty > 0` (the same section-4
    chain `test_channel_read_model.py` proves at the read-model layer), the gate opens and
    the drill's own per-location sum still reconciles against it."""
    from tests.scm.test_channel_read_model import _confirmed_leg  # noqa: PLC0415

    product = _product(db)
    run = _run(db, decision_grain="product", contract_version=1)
    brw, jb = _warehouse(db, "BRW"), _warehouse(db, "JB")
    _confirmed_leg(db, product_id=product.id, warehouse_id=brw.id, buy_qty=4)
    _rec(db, run, product, brw, rounded_qty=6,
         inputs={"project_need": 4, "retail_need": 2, "unclassified_need": 1})
    _rec(db, run, product, jb, rounded_qty=5,
         inputs={"project_need": 0, "retail_need": 3, "unclassified_need": 2})
    svc.write_rows(db, run.id)
    row = _row(db, run, product)

    out = svc.locations(db, product.product_code, run_id=run.id)

    assert sum(l["project_need"] for l in out["locations"]) == float(row.project_buy_qty) == 4
    assert row.earliest_project_need_date is not None, (
        "a real confirmed Buy backs project_buy_qty > 0, so the gate must open"
    )


# =========================================================================== #
# record_decision: precision validation, the frozen split, re-deciding
# =========================================================================== #

def test_a_fractional_choice_on_a_whole_unit_product_is_refused_with_the_precision_code(db):
    """AC-F12: `uom_decimal_places=0` (EA) rejects `2.5`, with error code
    `chosen_qty_precision` - not a generic 422."""
    product = _product(db, decimal_places=0, stem="EA")
    run = _run(db, decision_grain="product", contract_version=1)
    wh = _warehouse(db)
    sup = _supplier_link(db, product)
    _rec(db, run, product, wh, rounded_qty=3,
         inputs={"project_need": 3, "retail_need": 0, "unclassified_need": 0})
    svc.write_rows(db, run.id)

    with pytest.raises(AppException) as e:
        svc.record_decision(
            db, product.product_code, run_id=run.id, chosen_qty=2.5,
            supplier_code=sup.supplier_code, actor="mr loo",
        )
    assert e.value.status_code == 422
    assert e.value.detail["code"] == "chosen_qty_precision"


def test_the_same_fraction_is_accepted_on_a_three_decimal_kg_product(db):
    product = _product(db, decimal_places=3, stem="KG")
    run = _run(db, decision_grain="product", contract_version=1)
    wh = _warehouse(db)
    sup = _supplier_link(db, product)
    _rec(db, run, product, wh, rounded_qty=2.5,
         inputs={"project_need": 2.5, "retail_need": 0, "unclassified_need": 0})
    svc.write_rows(db, run.id)

    out = svc.record_decision(
        db, product.product_code, run_id=run.id, chosen_qty=2.5,
        supplier_code=sup.supplier_code, actor="mr loo",
    )

    assert out["chosen_qty"] == 2.5


def test_accepting_a_decision_splits_it_across_locations_summing_exactly(db):
    """AC-F12: the generalized allocator works in the row's frozen minor units and the
    persisted children sum EXACTLY to `chosen_qty` - equal deficits at BRW/JB give an even
    split of 2.75 (1.375 / 1.375), matching the plan's own decimal worked case."""
    from app.models.scm import OrderSummaryLocationAllocation  # noqa: PLC0415

    product = _product(db, decimal_places=3, stem="KG")
    run = _run(db, decision_grain="product", contract_version=1)
    brw, jb = _warehouse(db, "BRW"), _warehouse(db, "JB")
    sup = _supplier_link(db, product)
    # Equal signals on every plausible weighting source, so the split is even regardless of
    # which one the allocator reads its deficits from.
    _rec(db, run, product, brw, rounded_qty=1.375, net_position=-10, forecast_daily_demand=1,
         inputs={"project_need": 1.375, "retail_need": 0, "unclassified_need": 0})
    _rec(db, run, product, jb, rounded_qty=1.375, net_position=-10, forecast_daily_demand=1,
         inputs={"project_need": 0, "retail_need": 1.375, "unclassified_need": 0})
    svc.write_rows(db, run.id)

    svc.record_decision(
        db, product.product_code, run_id=run.id, chosen_qty=2.75,
        supplier_code=sup.supplier_code, actor="mr loo",
    )

    row = _row(db, run, product)
    splits = (
        db.query(OrderSummaryLocationAllocation)
        .filter(OrderSummaryLocationAllocation.order_summary_row_id == row.id)
        .all()
    )
    assert len(splits) == 2
    total = sum(float(s.allocated_qty) for s in splits)
    assert total == 2.75, "children must sum EXACTLY to chosen_qty"
    assert sorted(float(s.allocated_qty) for s in splits) == [1.375, 1.375]


def test_re_deciding_replaces_the_split_rather_than_rescaling_it(db):
    from app.models.scm import OrderSummaryLocationAllocation  # noqa: PLC0415

    product = _product(db, decimal_places=3, stem="KG")
    run = _run(db, decision_grain="product", contract_version=1)
    brw, jb = _warehouse(db, "BRW"), _warehouse(db, "JB")
    sup = _supplier_link(db, product)
    _rec(db, run, product, brw, rounded_qty=1, net_position=-10,
         inputs={"project_need": 1, "retail_need": 0, "unclassified_need": 0})
    _rec(db, run, product, jb, rounded_qty=1, net_position=-10,
         inputs={"project_need": 0, "retail_need": 1, "unclassified_need": 0})
    svc.write_rows(db, run.id)
    svc.record_decision(db, product.product_code, run_id=run.id, chosen_qty=2,
                        supplier_code=sup.supplier_code, actor="mr loo")

    svc.record_decision(db, product.product_code, run_id=run.id, chosen_qty=6,
                        supplier_code=sup.supplier_code, actor="mr loo")

    row = _row(db, run, product)
    splits = (
        db.query(OrderSummaryLocationAllocation)
        .filter(OrderSummaryLocationAllocation.order_summary_row_id == row.id)
        .all()
    )
    assert len(splits) == 2, "the old split rows are replaced, not accumulated alongside the new ones"
    assert sum(float(s.allocated_qty) for s in splits) == 6


def test_editing_the_uom_afterwards_does_not_change_a_frozen_rows_precision(db):
    """AC-F12: validation and allocation read the SNAPSHOT `uom_decimal_places`, never live
    UOM master data - a later UOM edit cannot change what a frozen run already accepted."""
    product = _product(db, decimal_places=0, stem="EA")
    run = _run(db, decision_grain="product", contract_version=1)
    wh = _warehouse(db)
    sup = _supplier_link(db, product)
    _rec(db, run, product, wh, rounded_qty=3,
         inputs={"project_need": 3, "retail_need": 0, "unclassified_need": 0})
    svc.write_rows(db, run.id)
    frozen_dp = _row(db, run, product).uom_decimal_places

    db.execute(
        text("UPDATE units_of_measure SET decimal_places = 3 WHERE id = :id"),
        {"id": product.base_uom_id},
    )
    db.flush()

    assert _row(db, run, product).uom_decimal_places == frozen_dp == 0
    with pytest.raises(AppException) as e:
        svc.record_decision(
            db, product.product_code, run_id=run.id, chosen_qty=2.5,
            supplier_code=sup.supplier_code, actor="mr loo",
        )
    assert e.value.detail["code"] == "chosen_qty_precision"


def test_a_dp3_decisions_durability_survives_a_uom_downgrade_but_a_new_run_does_not(db):
    """AC-F12, the full replay path. Record 2.75 on a dp-3 row (its split rows must sum
    EXACTLY to 2.75 as Decimal - a float near-miss must not pass). Downgrade the UOM
    master to dp-0 AFTER the run is decided: re-recording the SAME 2.75 on the SAME run
    still succeeds and re-splits exactly, because validation and the allocator both replay
    the ROW's own frozen snapshot (3), never live master data. A brand NEW run for the SAME
    product, planned AFTER the downgrade, freezes 0 from the (now-downgraded) master - its
    own decision rejects 2.75.
    """
    from app.models.scm import OrderSummaryLocationAllocation  # noqa: PLC0415

    product = _product(db, decimal_places=3, stem="KG")
    run = _run(db, decision_grain="product", contract_version=1)
    brw, jb = _warehouse(db, "BRW"), _warehouse(db, "JB")
    sup = _supplier_link(db, product)
    _rec(db, run, product, brw, rounded_qty=1.375, net_position=-10, forecast_daily_demand=1,
         inputs={"project_need": 1.375, "retail_need": 0, "unclassified_need": 0})
    _rec(db, run, product, jb, rounded_qty=1.375, net_position=-10, forecast_daily_demand=1,
         inputs={"project_need": 0, "retail_need": 1.375, "unclassified_need": 0})
    svc.write_rows(db, run.id)

    svc.record_decision(db, product.product_code, run_id=run.id, chosen_qty=2.75,
                        supplier_code=sup.supplier_code, actor="mr loo")
    row = _row(db, run, product)
    assert row.uom_decimal_places == 3

    def _splits(summary_row_id):
        return (
            db.query(OrderSummaryLocationAllocation)
            .filter(OrderSummaryLocationAllocation.order_summary_row_id == summary_row_id)
            .all()
        )

    assert sum(Decimal(str(s.allocated_qty)) for s in _splits(row.id)) == Decimal("2.75"), (
        "split rows must sum EXACTLY to chosen_qty as Decimal, not a float near-miss"
    )

    # Downgrade the UOM master AFTER the run was decided.
    db.execute(
        text("UPDATE units_of_measure SET decimal_places = 0 WHERE id = :id"),
        {"id": product.base_uom_id},
    )
    db.flush()
    assert _row(db, run, product).uom_decimal_places == 3, "the row's own snapshot is untouched"

    # Re-recording the SAME 2.75 on the SAME run still succeeds: the replay reads the row
    # snapshot, not the downgraded master.
    out = svc.record_decision(db, product.product_code, run_id=run.id, chosen_qty=2.75,
                              supplier_code=sup.supplier_code, actor="mr loo again")
    assert out["chosen_qty"] == 2.75
    replay = _splits(row.id)
    assert len(replay) == 2, "the old split rows are replaced, not accumulated alongside the new"
    assert sum(Decimal(str(s.allocated_qty)) for s in replay) == Decimal("2.75")

    # A brand NEW run for the SAME product, planned after the downgrade, freezes 0.
    new_run = _run(db, decision_grain="product", contract_version=1)
    _rec(db, new_run, product, brw, rounded_qty=1.375, net_position=-10, forecast_daily_demand=1,
         inputs={"project_need": 1.375, "retail_need": 0, "unclassified_need": 0})
    _rec(db, new_run, product, jb, rounded_qty=1.375, net_position=-10, forecast_daily_demand=1,
         inputs={"project_need": 0, "retail_need": 1.375, "unclassified_need": 0})
    svc.write_rows(db, new_run.id)
    assert _row(db, new_run, product).uom_decimal_places == 0, (
        "a NEW run's snapshot must read the downgraded master, not the old run's frozen 3"
    )

    with pytest.raises(AppException) as e:
        svc.record_decision(db, product.product_code, run_id=new_run.id, chosen_qty=2.75,
                            supplier_code=sup.supplier_code, actor="mr loo")
    assert e.value.detail["code"] == "chosen_qty_precision"


# =========================================================================== #
# reorder_engine.allocate: generalized to minor units at a given precision
# =========================================================================== #

def test_allocate_at_three_decimal_places_splits_equal_deficits_evenly_and_exactly():
    warehouses = [
        {"warehouse_id": "BRW", "deficit": 10, "demand_rate": 1},
        {"warehouse_id": "JB", "deficit": 10, "demand_rate": 1},
    ]
    result = eng.allocate(2.75, warehouses, decimal_places=3)

    assert result["BRW"] == 1.375
    assert result["JB"] == 1.375
    assert sum(result.values()) == 2.75


def test_allocate_default_precision_is_unchanged():
    """Backward compatibility: every existing call site (location grain, the M3 engine)
    passes no `decimal_places` and must keep getting whole-unit integers back."""
    warehouses = [
        {"warehouse_id": "A", "deficit": 5, "demand_rate": 1},
        {"warehouse_id": "B", "deficit": 5, "demand_rate": 1},
    ]
    result = eng.allocate(10, warehouses)

    assert result == {"A": 5, "B": 5}


# =========================================================================== #
# po_worklist: decision_grain-scoped rows, no channel key
# =========================================================================== #

def test_po_worklist_under_a_product_run_carries_the_location_split(db):
    from app.models.scm import OrderSummaryLocationAllocation  # noqa: PLC0415

    product = _product(db, decimal_places=0, stem="EA")
    run = _run(db, decision_grain="product", contract_version=1)
    brw, jb = _warehouse(db, "BRW"), _warehouse(db, "JB")
    sup = _supplier_link(db, product)
    _rec(db, run, product, brw, rounded_qty=5, net_position=-10,
         inputs={"project_need": 5, "retail_need": 0, "unclassified_need": 0})
    _rec(db, run, product, jb, rounded_qty=5, net_position=-10,
         inputs={"project_need": 0, "retail_need": 5, "unclassified_need": 0})
    svc.write_rows(db, run.id)
    svc.record_decision(db, product.product_code, run_id=run.id, chosen_qty=10,
                        supplier_code=sup.supplier_code, actor="mr loo")

    out = svc.po_worklist(db, run_id=run.id)
    row = next(r for r in out["rows"] if r["product_code"] == product.product_code)

    assert row["decision_grain"] == "product"
    codes = {a["warehouse_code"] for a in row["location_allocations"]}
    assert codes == {brw.warehouse_code, jb.warehouse_code}
    assert "channel" not in row and "demand_class" not in row


def test_a_location_run_rejects_the_product_grain_decision(db):
    """AC-F09: `decision_grain='location'` locks the Product row - a decision write
    against `OrderSummaryRow.chosen_qty` (the Product-grain surface) must be rejected with
    409, never silently accepted into the wrong grain's ownership."""
    product = _product(db)
    run = _run(db, decision_grain="location", contract_version=1)
    wh = _warehouse(db)
    sup = _supplier_link(db, product)
    _rec(db, run, product, wh, rounded_qty=8,
         inputs={"project_need": 8, "retail_need": 0, "unclassified_need": 0})
    svc.write_rows(db, run.id)

    with pytest.raises(AppException) as e:
        svc.record_decision(db, product.product_code, run_id=run.id, chosen_qty=8,
                            supplier_code=sup.supplier_code, actor="mr loo")
    assert e.value.status_code == 409


def test_po_worklist_under_a_location_run_lists_recommendation_decisions(db):
    """Under `decision_grain='location'` the worklist is built from
    `scm.reorder_recommendation` decisions (status accepted/adjusted), not from
    `OrderSummaryRow.chosen_qty` - the Product row stays a read-only aggregate here
    (PLAN 5.4) and no worklist row carries a channel key."""
    product = _product(db)
    run = _run(db, decision_grain="location", contract_version=1)
    wh = _warehouse(db)
    rec = _rec(db, run, product, wh, rounded_qty=8,
              inputs={"project_need": 8, "retail_need": 0, "unclassified_need": 0})
    rec.status = "accepted"
    svc.write_rows(db, run.id)
    db.flush()

    out = svc.po_worklist(db, run_id=run.id)
    row = next(r for r in out["rows"] if r["product_code"] == product.product_code)

    assert row["decision_grain"] == "location"
    assert "channel" not in row and "demand_class" not in row


def test_a_legacy_run_rejects_every_decision(db):
    """AC-F09/F10: a NULL `front_planning_contract_version` run is read-only."""
    product = _product(db)
    run = _run(db)  # legacy: no contract_version, no decision_grain
    wh = _warehouse(db)
    sup = _supplier_link(db, product)
    _rec(db, run, product, wh, rounded_qty=8,
         inputs={"project_need": 8, "retail_need": 0, "unclassified_need": 0})
    svc.write_rows(db, run.id)

    with pytest.raises(AppException) as e:
        svc.record_decision(db, product.product_code, run_id=run.id, chosen_qty=8,
                            supplier_code=sup.supplier_code, actor="mr loo")
    assert e.value.status_code == 409
