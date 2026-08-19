"""``SalesOrderService.update`` upserts lines in place - it never deletes and reinserts
(code-review finding 7 on PLAN-scm-stack-followups-19aug).

Since commit c6cb76d45 the SCM SO detail page edits a line's qty in place and sends the
whole line set on any qty change, so a delete-and-recreate reset `qty_delivered` to 0,
forced `source_system` back to "manual", and minted new line ids - severing
`ProjectSalesOrderLine.core_sales_order_line_id` and any `OrderLinkClaim.so_line_id`
pointing at the old id (both ``ondelete="SET NULL"``) on an ordinary qty edit of an
AutoCount-uploaded order.

Postgres only (`tests/_pg_fixture.py::pg_session`), rolled back - every row this file
creates is its own, marker-prefixed, never a borrowed ``LIMIT 1`` row.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import SO_STATUS_DRAFT, ProjectSalesOrder, ProjectSalesOrderLine
from app.models.scm import OrderLinkClaim
from app.schemas.scm_orders import SalesOrderUpdate
from app.services.error_handler import AppException
from app.services.scm.sales_order_service import SalesOrderService
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTSOLU"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER), category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product_a = Product(id=_u(), product_code=unique_code("SKUA"), product_name=f"{MARKER} a",
                        category_id=cat.id, base_uom_id=uom.id, list_price=0,
                        is_active=True, is_discontinued=False)
    product_b = Product(id=_u(), product_code=unique_code("SKUB"), product_name=f"{MARKER} b",
                        category_id=cat.id, base_uom_id=uom.id, list_price=0,
                        is_active=True, is_discontinued=False)
    customer = Customer(id=_u(), customer_code=unique_code("C"), customer_name=f"{MARKER} Acme")
    warehouse = Warehouse(id=_u(), warehouse_code=unique_code("WH")[:50], warehouse_name=f"{MARKER} wh")
    db.add_all([product_a, product_b, customer, warehouse])
    db.flush()
    return {
        "product_a": product_a, "product_b": product_b, "customer": customer,
        "warehouse": warehouse,
    }


def _uploaded_order(db, world, *, qty_ordered=10, qty_delivered=3) -> tuple[SalesOrder, SalesOrderLine]:
    """One SO with one line that already carries the AutoCount-upload marks a plain
    delete+recreate would wipe: a non-zero `qty_delivered` and `source_system`."""
    so = SalesOrder(id=_u(), so_number=unique_code(MARKER), status="open",
                    customer_id=world["customer"].id, source_system="scm_upload")
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=world["product_a"].id,
        qty_ordered=qty_ordered, qty_delivered=qty_delivered, line_status="open",
        source_system="scm_upload",
    )
    db.add(line)
    db.flush()
    return so, line


# --------------------------------------------------------------------------- #
# qty edit is an upsert, not a replace
# --------------------------------------------------------------------------- #

def test_qty_edit_keeps_the_line_id_qty_delivered_and_source_system(db, world):
    so, line = _uploaded_order(db, world)
    original_id = line.id

    out = SalesOrderService(db).update(
        so.id,
        SalesOrderUpdate(lines=[{"sku": world["product_a"].product_code, "qty_ordered": 25, "uom": ""}]),
        user_id=None,
    )

    assert len(out["lines"]) == 1
    assert out["lines"][0]["id"] == original_id
    assert out["lines"][0]["qty_ordered"] == 25

    db.expire_all()
    row = db.get(SalesOrderLine, original_id)
    assert row is not None, "the matched line must be updated in place, not deleted"
    assert float(row.qty_delivered) == 3
    assert row.source_system == "scm_upload"


def test_qty_edit_keeps_the_reconciled_project_line_link(db, world):
    """The whole point of upserting: a project-side reconciled link survives a qty edit."""
    so, line = _uploaded_order(db, world)
    project_so = ProjectSalesOrder(
        id=_u(), project_id=None, provisional_ref=unique_code(MARKER), status=SO_STATUS_DRAFT,
    )
    db.add(project_so)
    db.flush()
    project_line = ProjectSalesOrderLine(
        id=_u(), project_sales_order_id=project_so.id, core_sales_order_line_id=line.id,
        line_no=1, product_id=world["product_a"].id, qty=10,
    )
    db.add(project_line)
    db.flush()

    SalesOrderService(db).update(
        so.id,
        SalesOrderUpdate(lines=[{"sku": world["product_a"].product_code, "qty_ordered": 40, "uom": ""}]),
        user_id=None,
    )

    db.expire_all()
    refreshed = db.get(ProjectSalesOrderLine, project_line.id)
    assert refreshed.core_sales_order_line_id == line.id


def test_a_new_line_is_inserted_alongside_the_matched_one(db, world):
    so, line = _uploaded_order(db, world)

    out = SalesOrderService(db).update(
        so.id,
        SalesOrderUpdate(lines=[
            {"sku": world["product_a"].product_code, "qty_ordered": 10, "uom": ""},
            {"sku": world["product_b"].product_code, "qty_ordered": 5, "uom": ""},
        ]),
        user_id=None,
    )

    assert len(out["lines"]) == 2
    ids = {ln["id"] for ln in out["lines"]}
    assert line.id in ids
    new_id = (ids - {line.id}).pop()
    db.expire_all()
    new_row = db.get(SalesOrderLine, new_id)
    assert new_row.product_id == world["product_b"].id
    assert float(new_row.qty_delivered) == 0
    assert new_row.source_system == "manual"


def test_a_line_dropped_from_the_payload_is_deleted(db, world):
    so, line = _uploaded_order(db, world)
    second = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=world["product_b"].id,
        qty_ordered=5, qty_delivered=0, line_status="open",
    )
    db.add(second)
    db.flush()

    out = SalesOrderService(db).update(
        so.id,
        SalesOrderUpdate(lines=[{"sku": world["product_a"].product_code, "qty_ordered": 10, "uom": ""}]),
        user_id=None,
    )

    assert len(out["lines"]) == 1
    db.expire_all()
    assert db.get(SalesOrderLine, second.id) is None


# --------------------------------------------------------------------------- #
# a removed line still referenced elsewhere refuses the update, 409
# --------------------------------------------------------------------------- #

def test_dropping_a_line_reconciled_to_a_project_so_is_refused(db, world):
    so, line = _uploaded_order(db, world)
    second = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=world["product_b"].id,
        qty_ordered=5, qty_delivered=0, line_status="open",
    )
    db.add(second)
    db.flush()
    project_so = ProjectSalesOrder(
        id=_u(), project_id=None, provisional_ref=unique_code(MARKER), status=SO_STATUS_DRAFT,
    )
    db.add(project_so)
    db.flush()
    project_line = ProjectSalesOrderLine(
        id=_u(), project_sales_order_id=project_so.id, core_sales_order_line_id=second.id,
        line_no=1, product_id=world["product_b"].id, qty=5,
    )
    db.add(project_line)
    db.flush()

    with pytest.raises(AppException) as exc:
        SalesOrderService(db).update(
            so.id,
            SalesOrderUpdate(lines=[{"sku": world["product_a"].product_code, "qty_ordered": 10, "uom": ""}]),
            user_id=None,
        )
    assert exc.value.status_code == 409
    assert project_so.provisional_ref in exc.value.detail["message"]

    db.expire_all()
    # refused entirely - the surviving line was not touched or half-committed.
    assert db.get(SalesOrderLine, second.id) is not None


def test_dropping_a_line_claimed_by_a_purchase_order_is_refused(db, world):
    so, line = _uploaded_order(db, world)
    second = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=world["product_b"].id,
        qty_ordered=5, qty_delivered=0, line_status="open",
    )
    db.add(second)
    db.flush()
    claim = OrderLinkClaim(
        id=_u(), so_number=so.so_number, po_number=unique_code("PO"), source="order_inquiry",
        so_line_id=second.id,
    )
    db.add(claim)
    db.flush()

    with pytest.raises(AppException) as exc:
        SalesOrderService(db).update(
            so.id,
            SalesOrderUpdate(lines=[{"sku": world["product_a"].product_code, "qty_ordered": 10, "uom": ""}]),
            user_id=None,
        )
    assert exc.value.status_code == 409
    assert claim.po_number in exc.value.detail["message"]

    db.expire_all()
    assert db.get(SalesOrderLine, second.id) is not None


# --------------------------------------------------------------------------- #
# a header-only edit (no `lines` key) still leaves everything untouched
# --------------------------------------------------------------------------- #

def test_header_only_edit_leaves_lines_untouched(db, world):
    so, line = _uploaded_order(db, world)

    SalesOrderService(db).update(so.id, SalesOrderUpdate(priority="urgent"), user_id=None)

    db.expire_all()
    row = db.get(SalesOrderLine, line.id)
    assert row is not None
    assert float(row.qty_ordered) == 10
    assert float(row.qty_delivered) == 3


# --------------------------------------------------------------------------- #
# a malformed agent id is a 404, not a database error
# --------------------------------------------------------------------------- #

def test_malformed_agent_id_is_a_404_not_a_db_error(db, world):
    so, _line = _uploaded_order(db, world)

    with pytest.raises(AppException) as exc:
        SalesOrderService(db).update(
            so.id, SalesOrderUpdate(sales_agent_id="not-a-uuid"), user_id=None,
        )
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# location / delivery date / UoM are editable on a matched line too (19 Aug live
# test: the detail page only let SKU + qty be edited)
# --------------------------------------------------------------------------- #

def test_editing_location_date_and_uom_keeps_the_line_id_and_qty_delivered(db, world):
    so, line = _uploaded_order(db, world)
    original_id = line.id

    out = SalesOrderService(db).update(
        so.id,
        SalesOrderUpdate(lines=[{
            "id": line.id,
            "sku": world["product_a"].product_code,
            "qty_ordered": 10,
            "warehouse_code": world["warehouse"].warehouse_code,
            "required_date": "2026-09-01",
            "uom": "BOX",
        }]),
        user_id=None,
    )

    assert len(out["lines"]) == 1
    out_line = out["lines"][0]
    assert out_line["id"] == original_id
    assert out_line["warehouse_code"] == world["warehouse"].warehouse_code
    assert out_line["required_date"] == "2026-09-01"
    assert out_line["uom"] == "BOX"

    db.expire_all()
    row = db.get(SalesOrderLine, original_id)
    assert row is not None
    assert row.warehouse_id == world["warehouse"].id
    assert row.required_date.isoformat() == "2026-09-01"
    assert row.uom == "BOX"
    assert float(row.qty_delivered) == 3
    assert row.source_system == "scm_upload"


def test_a_line_edit_that_omits_location_date_uom_leaves_them_untouched(db, world):
    """An edit that never mentions these keys (e.g. a qty-only change from the FE, which
    does not yet carry a location it never touched) must not clear a value another edit
    set - `model_fields_set`, not `is not None`."""
    so, line = _uploaded_order(db, world)
    line.warehouse_id = world["warehouse"].id
    from datetime import date as _date
    line.required_date = _date(2026, 8, 1)
    line.uom = "BOX"
    db.flush()

    out = SalesOrderService(db).update(
        so.id,
        SalesOrderUpdate(lines=[{
            "id": line.id,
            "sku": world["product_a"].product_code,
            "qty_ordered": 99,
        }]),
        user_id=None,
    )

    assert out["lines"][0]["qty_ordered"] == 99
    assert out["lines"][0]["warehouse_code"] == world["warehouse"].warehouse_code
    assert out["lines"][0]["required_date"] == "2026-08-01"
    assert out["lines"][0]["uom"] == "BOX"

    db.expire_all()
    row = db.get(SalesOrderLine, line.id)
    assert row.warehouse_id == world["warehouse"].id
    assert row.required_date == _date(2026, 8, 1)
    assert row.uom == "BOX"


def test_explicit_null_clears_location_date_and_uom(db, world):
    so, line = _uploaded_order(db, world)
    line.warehouse_id = world["warehouse"].id
    from datetime import date as _date
    line.required_date = _date(2026, 8, 1)
    line.uom = "BOX"
    db.flush()

    SalesOrderService(db).update(
        so.id,
        SalesOrderUpdate(lines=[{
            "id": line.id,
            "sku": world["product_a"].product_code,
            "qty_ordered": 10,
            "warehouse_code": None,
            "required_date": None,
            "uom": None,
        }]),
        user_id=None,
    )

    db.expire_all()
    row = db.get(SalesOrderLine, line.id)
    assert row.warehouse_id is None
    assert row.required_date is None
    assert row.uom is None


def test_a_malformed_required_date_is_a_422_not_a_db_error(db, world):
    """Code review finding S11: `date.fromisoformat` raising `ValueError` on a bad date
    string must read as a 422 the caller can fix, not a raw 500."""
    so, line = _uploaded_order(db, world)

    with pytest.raises(AppException) as exc:
        SalesOrderService(db).update(
            so.id,
            SalesOrderUpdate(lines=[{
                "id": line.id,
                "sku": world["product_a"].product_code,
                "qty_ordered": 10,
                "required_date": "not-a-date",
            }]),
            user_id=None,
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "INVALID_DATE"

    db.expire_all()
    row = db.get(SalesOrderLine, line.id)
    assert row.required_date is None, "the refused write must not half-apply"


def test_editing_a_line_with_an_unknown_warehouse_code_is_a_404(db, world):
    so, line = _uploaded_order(db, world)

    with pytest.raises(AppException) as exc:
        SalesOrderService(db).update(
            so.id,
            SalesOrderUpdate(lines=[{
                "id": line.id,
                "sku": world["product_a"].product_code,
                "qty_ordered": 10,
                "warehouse_code": f"{MARKER}-NOPE",
            }]),
            user_id=None,
        )
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "WAREHOUSE_NOT_FOUND"

    db.expire_all()
    row = db.get(SalesOrderLine, line.id)
    assert row.warehouse_id is None, "the refused write must not half-apply"
