"""Migration 396 - collapse a joined `order_inquiry_rows.stock_location` to one code.

`ProjectSupplyService._restamp_stock_location` and `ProjectOrderInquiryService.
_stock_location` used to join every reserve/borrow component's warehouse code onto the
row (`" + "` / `" / "` separated). Both writers are fixed going forward
(PLAN-scm-demo-followups-19aug-b); this backfills rows a pre-fix confirmation already
wrote.

The migration's own SQL hardcodes real schema-qualified names (`projects.
sales_order_lines`, `sales_order_lines`, `warehouses`) rather than going through ORM
Table metadata, so it cannot run against `blank_session`'s schema-translated scratch
copy (those literal names resolve to nothing there). Run via `pg_session` instead - the
real shared local Postgres, rolled back at teardown - the same substrate migration
374's own test uses (`tests/scm/test_loading_plan.py`) for the identical reason. The
all-companies scope mirrors what the real `alembic upgrade` runs with (no request, no
principal), so every row here is stamped with an explicit `company_id` rather than
relying on the single-company auto-stamp.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.projects import Project
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTMIG396"
SORENTO = "00000000-0000-0000-0000-000000000001"

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "396_oi_single_location.py"
)


def _module():
    spec = importlib.util.spec_from_file_location(
        "zzt_migration_396_oi_single_location", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with pg_session() as session:
        # An `alembic upgrade` runs with no request and no principal, same as a backfill
        # script (see tests/test_backfill_retire_superseded_order_inquiry_rows.py).
        set_company_scope(session, None)
        yield session


def _warehouse(db, code: str) -> Warehouse:
    row = Warehouse(
        id=_uid(), company_id=SORENTO, warehouse_code=code, warehouse_name=f"{MARKER} {code}",
        fulfilment_planning=True,
    )
    db.add(row)
    db.flush()
    return row


def _product(db) -> Product:
    uom = UnitOfMeasure(
        id=_uid(), company_id=SORENTO, uom_code=unique_code("uom"), uom_name="Unit"
    )
    category = ProductCategory(
        id=_uid(), company_id=SORENTO, category_code=unique_code("cat"), category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    product = Product(
        id=_uid(),
        company_id=SORENTO,
        product_code=unique_code("CB"),
        product_name=f"{MARKER} basin",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(product)
    db.flush()
    return product


def _seeded_row(db, *, joined_location: str, with_core_line: bool) -> tuple[OrderInquiryRow, Warehouse]:
    """One `order_inquiry_rows` row carrying a pre-fix joined `stock_location`.

    `with_core_line=True` reconciles the project line to a real core line whose
    warehouse is the FIRST code in `joined_location` - the join the migration's first
    pass resolves. `with_core_line=False` leaves it unreconciled, which is what the
    fallback (text before the first separator) has to cover.
    """
    project = Project(
        id=_uid(),
        company_id=SORENTO,
        project_code=unique_code("proj"),
        title=f"{MARKER} tower",
        normalised_title=unique_code(f"{MARKER.lower()} tower"),
    )
    db.add(project)
    db.flush()
    order = ProjectSalesOrder(
        id=_uid(),
        company_id=SORENTO,
        project_id=project.id,
        provisional_ref=unique_code("SO"),
        area_group="TOWER",
    )
    db.add(order)
    db.flush()

    product = _product(db)
    own_code = joined_location.split(" ", 1)[0]
    fulfilment_wh = _warehouse(db, own_code)

    core_line_id = None
    if with_core_line:
        core_so = SalesOrder(id=_uid(), company_id=SORENTO, so_number=unique_code("CORE-SO"))
        db.add(core_so)
        db.flush()
        core_line = SalesOrderLine(
            id=_uid(),
            company_id=SORENTO,
            sales_order_id=core_so.id,
            product_id=product.id,
            warehouse_id=fulfilment_wh.id,
            qty_ordered=Decimal("10"),
            qty_delivered=Decimal("0"),
        )
        db.add(core_line)
        db.flush()
        core_line_id = core_line.id

    project_line = ProjectSalesOrderLine(
        id=_uid(),
        company_id=SORENTO,
        project_sales_order_id=order.id,
        core_sales_order_line_id=core_line_id,
        line_no=1,
        product_id=product.id,
        qty=Decimal("10"),
        delivery_date=date(2027, 1, 7),
        stock_location=joined_location,
    )
    db.add(project_line)
    db.flush()

    inquiry = OrderInquiry(id=_uid(), company_id=SORENTO, project_sales_order_id=order.id)
    db.add(inquiry)
    db.flush()

    row = OrderInquiryRow(
        id=_uid(),
        company_id=SORENTO,
        order_inquiry_id=inquiry.id,
        so_line_id=project_line.id,
        item_code=product.product_code,
        qty=Decimal("10"),
        stock_location=joined_location,
        verb=IV_ORDER,
    )
    db.add(row)
    db.flush()
    return row, fulfilment_wh


def test_a_resolvable_row_takes_the_core_lines_own_warehouse(db):
    row, fulfilment_wh = _seeded_row(
        db, joined_location=f"{MARKER}-IR + {MARKER}", with_core_line=True
    )
    row_id = row.id

    changed = _module().apply(db.connection())

    assert changed >= 1
    db.expire_all()
    reread = db.get(OrderInquiryRow, row_id)
    assert reread.stock_location == fulfilment_wh.warehouse_code == f"{MARKER}-IR"


def test_an_unresolvable_row_falls_back_to_the_text_before_the_first_separator(db):
    row, _ = _seeded_row(
        db, joined_location=f"{MARKER}-IR / {MARKER}", with_core_line=False
    )
    row_id = row.id

    changed = _module().apply(db.connection())

    assert changed >= 1
    db.expire_all()
    reread = db.get(OrderInquiryRow, row_id)
    assert reread.stock_location == f"{MARKER}-IR"


def test_apply_is_idempotent(db):
    row, fulfilment_wh = _seeded_row(
        db, joined_location=f"{MARKER}-IR + {MARKER}", with_core_line=True
    )
    row_id = row.id

    first = _module().apply(db.connection())
    assert first >= 1
    db.expire_all()
    assert db.get(OrderInquiryRow, row_id).stock_location == fulfilment_wh.warehouse_code

    # A second run must not touch THIS row again - it no longer matches the pattern
    # either pass looks for. The global rowcount is not asserted `== 0`: this runs
    # against the real shared database (per the module docstring), and a second run
    # is still free to find whatever else is out there.
    _module().apply(db.connection())
    db.expire_all()
    assert db.get(OrderInquiryRow, row_id).stock_location == fulfilment_wh.warehouse_code


def test_a_row_naming_only_one_location_is_left_alone(db):
    row, _fulfilment_wh = _seeded_row(
        db, joined_location=f"{MARKER}-IR", with_core_line=True
    )
    row_id = row.id
    before = row.stock_location

    # No assertion on the return value here: `apply` runs table-wide, and this is the
    # real shared database (per the module docstring), so a global rowcount is not this
    # test's to own. What IS this test's to own is that THIS row - which names one
    # location and no separator - is untouched by the same run.
    _module().apply(db.connection())

    db.expire_all()
    reread = db.get(OrderInquiryRow, row_id)
    assert reread.stock_location == before == f"{MARKER}-IR"


def test_revert_is_a_no_op(db):
    """Which components made up the joined string is not recorded anywhere once
    collapsed, so downgrade cannot restore it - it changes nothing."""
    _seeded_row(db, joined_location=f"{MARKER}-IR + {MARKER}", with_core_line=True)
    _module().apply(db.connection())

    assert _module().revert(db.connection()) == 0
