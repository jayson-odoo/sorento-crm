"""Planning horizon (commit 22359023d, "the plan stops at a horizon") hardened for two
review BLOCKERS the feature shipped without a single test against.

B2: `_unlocated_demand_map` / `_apply_unlocated_demand` (~97% of the open book - every
line whose sales-order line names no warehouse) carried NO date predicate at all, so
"Plan until December" left every 2030 line in, for almost all demand. Fixed by threading
the run's `plan_horizon_date` through to the SAME rule `demand.horizon_committed_select_sql`
already uses: a stated `required_date` after the cutoff is excluded, no date at all is
always in.

B3: `_project_supply_reduction_map` (a confirmed Project Reserve/Borrow claim, subtracted
from the Retail free-supply pool at AC-F07) carried no date predicate either, while the
`project_need` it offsets IS horizoned (through the same `committed_v`/horizon-select
swap). A 2030 project reserve kept subtracting its claim from Retail cover after its own
demand had left the plan. Fixed by horizoning the claim on the SAME core line date its
demand is read against.

Both are exercised directly against the private helper (the same idiom
`tests/scm/test_reorder_run_scope_isolation.py` / `test_company_isolation_planning.py`
use for `_planning_rows`) rather than through a full `run_reorder` - the helpers are pure
reads over a handful of rows, and a full run adds fixture weight (stock/demand/supplier)
this fix does not touch.

Postgres only, marker-prefixed, every test seeds its own chain.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest

from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOLineAllocation,
    SOSupplyDecision,
)
from app.services.scm import reorder_run_service as svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg

pytestmark = requires_pg

MARKER = "ZZTHZN"


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _product(db) -> Product:
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat"))
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()
    p = Product(
        id=_u(), product_code=_code("SKU"), product_name="Plan horizon test product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(p)
    db.flush()
    return p


def _warehouse(db) -> Warehouse:
    w = Warehouse(id=_u(), warehouse_code=_code("WH")[:50], warehouse_name="Horizon test WH")
    db.add(w)
    db.flush()
    return w


# =============================================================================
# B2 - `_unlocated_demand_map`: the ~97% path now honours the horizon
# =============================================================================

def _unlocated_line(db, product_id, qty, *, required_date=None) -> SalesOrderLine:
    so = SalesOrder(id=_u(), so_number=_code("SO"), status="open")
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product_id, warehouse_id=None,
        qty_ordered=qty, qty_delivered=0, line_status="open",
        required_date=required_date,
    )
    db.add(line)
    db.flush()
    return line


def test_unlocated_demand_beyond_the_horizon_is_excluded(db):
    p = _product(db)
    _unlocated_line(db, p.id, 40, required_date=date(2030, 1, 1))

    result = svc._unlocated_demand_map(db, [p.id], horizon=date(2026, 12, 31))

    assert result == {}, (
        "a 2030 line should not distort a plan drawn to December, same as the located path"
    )


def test_unlocated_demand_with_no_date_stays_in(db):
    """Undated demand is still demand - never excluded by a cutoff it carries no date to
    compare against. Same shipped rule as `demand.horizon_committed_select_sql`."""
    p = _product(db)
    _unlocated_line(db, p.id, 40, required_date=None)

    result = svc._unlocated_demand_map(db, [p.id], horizon=date(2026, 12, 31))

    assert result == {str(p.id): 40.0}


def test_unlocated_demand_within_the_horizon_stays_in(db):
    p = _product(db)
    _unlocated_line(db, p.id, 25, required_date=date(2026, 6, 1))

    result = svc._unlocated_demand_map(db, [p.id], horizon=date(2026, 12, 31))

    assert result == {str(p.id): 25.0}


def test_unlocated_demand_map_unhorizoned_counts_every_date(db):
    """`horizon=None` (a run created before this column existed, or with the field left
    empty) must reproduce the pre-horizon query exactly - a distant date is still counted."""
    p = _product(db)
    _unlocated_line(db, p.id, 40, required_date=date(2030, 1, 1))

    result = svc._unlocated_demand_map(db, [p.id], horizon=None)

    assert result == {str(p.id): 40.0}


# =============================================================================
# B3 - `_project_supply_reduction_map`: a Reserve/Borrow claim leaves with its own demand
# =============================================================================

def _project_reserve(db, *, product_id, donor_warehouse_id, qty,
                     required_date=None) -> None:
    """The minimal section-4/6.1 chain a Reserve/Borrow claim needs: a core SO line, its
    Project counterpart, an ACTIVE supply decision, and the `so_line_allocations` row
    (`source_type='reserve'`, never `'order'` - that leg is the Buy residual, not a claim
    on existing stock)."""
    so = SalesOrder(id=_u(), so_number=_code("SO"), status="open", demand_class="project")
    db.add(so)
    db.flush()
    core_line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product_id, warehouse_id=donor_warehouse_id,
        qty_ordered=qty, qty_delivered=0, line_status="open", required_date=required_date,
    )
    db.add(core_line)
    db.flush()

    pso = ProjectSalesOrder(id=_u(), provisional_ref=_code("PSO"), so_id=so.id)
    db.add(pso)
    db.flush()
    psl = ProjectSalesOrderLine(
        id=_u(), project_sales_order_id=pso.id, line_no=1, product_id=product_id,
        qty=qty, core_sales_order_line_id=core_line.id,
    )
    db.add(psl)
    db.flush()
    decision = SOSupplyDecision(
        id=_u(), project_sales_order_id=pso.id, revision_no=1, state="active",
        line_snapshots=[],
        # The DB (still) declares this NOT NULL though the model has it nullable - a
        # decided revision has a confirmation time in every real row.
        confirmed_at=datetime.utcnow(),
    )
    db.add(decision)
    db.flush()
    alloc = SOLineAllocation(
        id=_u(), so_line_id=psl.id, source_type="reserve",
        warehouse_id=donor_warehouse_id, qty=qty,
    )
    db.add(alloc)
    db.flush()


def test_a_reserve_claim_beyond_the_horizon_no_longer_reduces_retail_supply(db):
    p = _product(db)
    donor = _warehouse(db)
    _project_reserve(db, product_id=p.id, donor_warehouse_id=donor.id, qty=100,
                     required_date=date(2030, 1, 1))
    rows = [{"product_id": p.id}]

    result = svc._project_supply_reduction_map(db, rows, horizon=date(2026, 12, 31))

    assert result == {}, (
        "a reserve claimed against 2030 project demand must leave the retail pool "
        "together with that demand, once it is horizoned away"
    )


def test_a_reserve_claim_with_no_date_stays_in(db):
    p = _product(db)
    donor = _warehouse(db)
    _project_reserve(db, product_id=p.id, donor_warehouse_id=donor.id, qty=100,
                     required_date=None)
    rows = [{"product_id": p.id}]

    result = svc._project_supply_reduction_map(db, rows, horizon=date(2026, 12, 31))

    assert result == {(str(p.id), str(donor.id)): 100.0}


def test_a_reserve_claim_within_the_horizon_still_reduces_retail_supply(db):
    p = _product(db)
    donor = _warehouse(db)
    _project_reserve(db, product_id=p.id, donor_warehouse_id=donor.id, qty=100,
                     required_date=date(2026, 6, 1))
    rows = [{"product_id": p.id}]

    result = svc._project_supply_reduction_map(db, rows, horizon=date(2026, 12, 31))

    assert result == {(str(p.id), str(donor.id)): 100.0}


def test_project_supply_reduction_map_unhorizoned_counts_every_date(db):
    p = _product(db)
    donor = _warehouse(db)
    _project_reserve(db, product_id=p.id, donor_warehouse_id=donor.id, qty=100,
                     required_date=date(2030, 1, 1))
    rows = [{"product_id": p.id}]

    result = svc._project_supply_reduction_map(db, rows, horizon=None)

    assert result == {(str(p.id), str(donor.id)): 100.0}
