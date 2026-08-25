"""What the purchase-order API says about MONEY, and what its detail screen may now write.

The supply-side twin of `test_so_money_api.py`, closing the same two gaps on the other book.

**Money never reached the browser.** `purchase_order_lines` has carried `unit_cost` since the
plan started costing its buys, and the serializer already emitted `warehouse_code` and
`line_status` - but `PurchaseOrderLine` declared none of the three, so `response_model`
dropped them however carefully the service built the dict (the standing `response_model`
trap). The header had no money at all, so an order worth RM 46,000 read as a list of
quantities.

**The order could not be corrected at all.** There was no write route on this router beyond
bulk-confirm / bulk-delete / create-GR, so a wrong supplier, a wrong date or a mistyped
quantity could only be fixed by deleting the order and re-uploading the book.

The line's cost is serialised as `unit_price` on purpose: it is the same fact the sales
screen calls a unit price, one click away in the same menu, and two names for one figure is
how two screens start disagreeing about the same number.

Postgres only, every FK seeded here (never a borrowed `LIMIT 1` row), rolled back with the
`scm_app` savepoint.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.models.inventory import Warehouse
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTPOM"


def _uid() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{_uid()[:8]}".upper()


class World:
    """One supplier, one product, one warehouse and one order, all this test's own."""

    def __init__(self, app, db, supplier, product, warehouse, po):
        self.app = app
        self.db = db
        self.supplier = supplier
        self.product = product
        self.warehouse = warehouse
        self.po = po


def _seed(scm_app, *, lines, status="active", issue_date=date(2026, 7, 16),
          expected_date=date(2026, 8, 4), currency="MYR", role="purchasing"):
    app, db, gcu, gcuak = scm_app
    as_user(app, gcu, gcuak, seed_user(db, role))

    uom = UnitOfMeasure(id=_uid(), uom_code=_code("UOM")[:20], uom_name="Pieces")
    category = ProductCategory(
        id=_uid(), category_code=_code("CAT"), category_name=f"{MARKER} category"
    )
    db.add_all([uom, category])
    db.flush()
    product = Product(
        id=_uid(), product_code=_code("SKU"), product_name=f"{MARKER} basin",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("120.00"),
    )
    supplier = Supplier(
        id=_uid(), supplier_code=_code("SUP")[:30], supplier_name=f"{MARKER} Sanitary Sdn Bhd",
        is_active=True,
    )
    warehouse = Warehouse(
        id=_uid(), warehouse_code=_code("WH")[:20], warehouse_name=f"{MARKER} store",
        is_active=True,
    )
    db.add_all([product, supplier, warehouse])
    db.flush()

    po = PurchaseOrder(
        id=_uid(), po_number=_code("PO"), supplier_id=supplier.id, status=status,
        issue_date=issue_date, expected_date=expected_date, currency=currency,
        source_system="scm_upload",
    )
    db.add(po)
    db.flush()
    for spec in lines:
        db.add(PurchaseOrderLine(
            id=_uid(), purchase_order_id=po.id, product_id=product.id,
            warehouse_id=warehouse.id,
            qty_ordered=Decimal(str(spec.get("qty_ordered", 10))),
            qty_received=Decimal(str(spec.get("qty_received", 0))),
            unit_cost=spec.get("unit_cost"),
            discount=spec.get("discount"),
            line_total=spec.get("line_total"),
            uom=spec.get("uom"),
            currency=spec.get("currency", currency),
            expected_date=spec.get("expected_date", expected_date),
            line_status=spec.get("line_status", "open"),
        ))
    db.flush()
    return World(app, db, supplier, product, warehouse, po)


def _detail(world) -> dict:
    with TestClient(world.app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{world.po.id}")
        assert res.status_code == 200, res.text
        return res.json()


def _put(world, body) -> dict:
    with TestClient(world.app) as c:
        res = c.put(f"/api/v1/scm/purchase-orders/{world.po.id}", json=body)
        assert res.status_code == 200, res.text
        return res.json()


# --- the line's money reaches the browser -----------------------------------

def test_a_line_carries_its_price_discount_and_total(scm_app):
    """`response_model` silently drops an undeclared field, so this is asserted through the
    ROUTE rather than off the serializer."""
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10, "unit_cost": Decimal("100.00"),
         "discount": Decimal("15.00"), "line_total": Decimal("985.00")},
    ])

    line = _detail(world)["lines"][0]

    # The COLUMN is `unit_cost`; the FIELD is `unit_price`, the same word the sales-order
    # screen uses for the same fact.
    assert Decimal(str(line["unit_price"])) == Decimal("100.00")
    assert Decimal(str(line["discount"])) == Decimal("15.00")
    assert Decimal(str(line["line_total"])) == Decimal("985.00")
    assert line["currency"] == "MYR"


def test_a_line_with_no_money_reads_null_rather_than_zero(scm_app):
    """A zero cost reads as free goods; the absence has to survive the wire."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])

    line = _detail(world)["lines"][0]

    assert line["unit_price"] is None
    assert line["discount"] is None
    assert line["line_total"] is None


def test_a_line_carries_its_location_status_and_date(scm_app):
    """All three were already built by the serializer and dropped by `response_model` - the
    detail grid could not colour a closed line or say where a line was going."""
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10, "line_status": "closed", "expected_date": date(2026, 9, 1)},
    ])

    line = _detail(world)["lines"][0]

    assert line["warehouse_code"] == world.warehouse.warehouse_code
    assert line["line_status"] == "closed"
    assert line["expected_date"] == "2026-09-01"


def test_a_line_falls_back_to_the_products_own_unit(scm_app):
    """The per-line override when the book states one, the product's base unit otherwise."""
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10, "uom": "CTN"},
        {"qty_ordered": 4},
    ])

    uoms = {ln["uom"] for ln in _detail(world)["lines"]}

    assert "CTN" in uoms
    assert world.product.base_uom.uom_code in uoms


# --- the header's total -----------------------------------------------------

def test_total_amount_sums_the_stated_line_totals(scm_app):
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10, "line_total": Decimal("985.00")},
        {"qty_ordered": 4, "line_total": Decimal("15.50")},
    ])

    assert Decimal(str(_detail(world)["total_amount"])) == Decimal("1000.50")


def test_total_amount_falls_back_to_cost_times_qty_less_discount(scm_app):
    """A book that states a cost and a discount but no line total is still worth something;
    computing it here beats printing a blank beside 320 units."""
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10, "unit_cost": Decimal("100.00"), "discount": Decimal("15.00")},
    ])

    assert Decimal(str(_detail(world)["total_amount"])) == Decimal("985.00")


def test_total_amount_is_absent_when_no_line_carries_money(scm_app):
    """None, not 0: an order nobody priced is not an order worth nothing."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])

    assert _detail(world)["total_amount"] is None


def test_the_header_states_the_currency_the_order_was_written_in(scm_app):
    """The book is mostly USD. `RM 12.50` against a USD order is a wrong number."""
    world = _seed(scm_app, currency="USD", lines=[
        {"qty_ordered": 10, "unit_cost": Decimal("12.50")},
    ])

    assert _detail(world)["currency"] == "USD"


# --- what the edit screen may now write -------------------------------------

def test_the_order_date_can_be_corrected(scm_app):
    """`issue_date` under the name the screen shows. `scm.receipt_lead_v` measures the
    supplier's lead time from this column, so a wrong one skews every safety stock computed
    from it."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}], issue_date=date(2026, 7, 16))

    assert _put(world, {"order_date": "2026-05-04"})["order_date"] == "2026-05-04"


def test_the_expected_date_can_be_corrected_and_cleared(scm_app):
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])

    assert _put(world, {"expected_date": "2026-09-30"})["expected_date"] == "2026-09-30"
    assert _put(world, {"expected_date": None})["expected_date"] is None


def test_the_supplier_can_be_corrected_by_code(scm_app):
    """By CODE, never the UUID - the same rule `customer_code` follows on the sales side."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])
    other = Supplier(
        id=_uid(), supplier_code=_code("SUP2")[:30], supplier_name=f"{MARKER} Other Sdn Bhd",
        is_active=True,
    )
    world.db.add(other)
    world.db.flush()

    body = _put(world, {"supplier_code": other.supplier_code})

    assert body["supplier_code"] == other.supplier_code
    assert body["supplier_name"] == other.supplier_name


def test_an_unknown_supplier_code_is_refused(scm_app):
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])

    with TestClient(world.app) as c:
        res = c.put(
            f"/api/v1/scm/purchase-orders/{world.po.id}",
            json={"supplier_code": "ZZT-NO-SUCH-SUPPLIER"},
        )

    assert res.status_code == 404, res.text


def test_a_line_edit_writes_the_price_and_the_discount(scm_app):
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10, "unit_cost": Decimal("100.00"), "discount": Decimal("15.00")},
    ])
    sku = world.product.product_code
    line_id = _detail(world)["lines"][0]["id"]

    body = _put(world, {"lines": [{
        "id": line_id, "sku": sku, "qty_ordered": 10,
        "unit_price": 88.5, "discount": 0,
    }]})

    line = body["lines"][0]
    assert Decimal(str(line["unit_price"])) == Decimal("88.50")
    assert Decimal(str(line["discount"])) == Decimal("0")


def test_a_line_edit_that_omits_the_money_leaves_it_alone(scm_app):
    """`model_fields_set`, the same rule `uom` / `warehouse_code` already follow: a qty-only
    edit must not wipe a cost the book imported."""
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10, "unit_cost": Decimal("100.00"), "discount": Decimal("15.00")},
    ])
    sku = world.product.product_code
    line_id = _detail(world)["lines"][0]["id"]

    body = _put(world, {"lines": [{"id": line_id, "sku": sku, "qty_ordered": 12}]})

    line = body["lines"][0]
    assert line["qty_ordered"] == 12
    assert Decimal(str(line["unit_price"])) == Decimal("100.00")
    assert Decimal(str(line["discount"])) == Decimal("15.00")


def test_an_edited_line_keeps_its_id_and_what_has_been_received(scm_app):
    """Matched by `id` FIRST, and updated IN PLACE - a delete-and-reinsert would reset
    `qty_received` to 0 and mint a new line id, severing any goods receipt pointing at it."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10, "qty_received": 4}])
    sku = world.product.product_code
    line_id = _detail(world)["lines"][0]["id"]

    line = _put(world, {"lines": [
        {"id": line_id, "sku": sku, "qty_ordered": 20},
    ]})["lines"][0]

    assert line["id"] == line_id
    assert line["qty_received"] == 4
    assert line["qty_ordered"] == 20


def test_a_line_can_be_added_and_one_nothing_claims_can_be_removed(scm_app):
    world = _seed(scm_app, lines=[{"qty_ordered": 10}, {"qty_ordered": 4}])
    sku = world.product.product_code
    kept = _detail(world)["lines"][0]["id"]

    body = _put(world, {"lines": [{"id": kept, "sku": sku, "qty_ordered": 10}]})

    assert [ln["id"] for ln in body["lines"]] == [kept]


def test_a_line_that_has_received_goods_cannot_be_dropped(scm_app):
    """Removing it would erase the receipt history the measured lead time is built from."""
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10},
        {"qty_ordered": 4, "qty_received": 4, "line_status": "received"},
    ])
    sku = world.product.product_code
    kept = _detail(world)["lines"][0]["id"]

    with TestClient(world.app) as c:
        res = c.put(
            f"/api/v1/scm/purchase-orders/{world.po.id}",
            json={"lines": [{"id": kept, "sku": sku, "qty_ordered": 10}]},
        )

    assert res.status_code == 409, res.text


def test_a_line_a_sales_order_is_waiting_on_cannot_be_dropped(scm_app):
    """The SO<->PO claim is `SET NULL`, so the row would survive pointing at nothing - and
    the sales order it belongs to would silently stop waiting on anything."""
    from app.models.scm import OrderLinkClaim

    world = _seed(scm_app, lines=[{"qty_ordered": 10}, {"qty_ordered": 4}])
    sku = world.product.product_code
    detail = _detail(world)
    kept, claimed = detail["lines"][0]["id"], detail["lines"][1]["id"]
    world.db.add(OrderLinkClaim(
        id=_uid(), so_number=_code("SO"), po_number=world.po.po_number,
        source="po_upload", po_line_id=claimed,
    ))
    world.db.flush()

    with TestClient(world.app) as c:
        res = c.put(
            f"/api/v1/scm/purchase-orders/{world.po.id}",
            json={"lines": [{"id": kept, "sku": sku, "qty_ordered": 10}]},
        )

    assert res.status_code == 409, res.text
    assert world.po.po_number in res.text


def test_a_line_edit_writes_the_location_the_unit_and_the_date(scm_app):
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])
    sku = world.product.product_code
    line_id = _detail(world)["lines"][0]["id"]
    other_wh = Warehouse(
        id=_uid(), warehouse_code=_code("WH2")[:20], warehouse_name=f"{MARKER} depot",
        is_active=True,
    )
    world.db.add(other_wh)
    world.db.flush()

    line = _put(world, {"lines": [{
        "id": line_id, "sku": sku, "qty_ordered": 10,
        "warehouse_code": other_wh.warehouse_code, "uom": "CTN",
        "expected_date": "2026-10-05",
    }]})["lines"][0]

    assert line["warehouse_code"] == other_wh.warehouse_code
    assert line["uom"] == "CTN"
    assert line["expected_date"] == "2026-10-05"


def test_a_quantity_of_zero_is_refused(scm_app):
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])
    sku = world.product.product_code
    line_id = _detail(world)["lines"][0]["id"]

    with TestClient(world.app) as c:
        res = c.put(
            f"/api/v1/scm/purchase-orders/{world.po.id}",
            json={"lines": [{"id": line_id, "sku": sku, "qty_ordered": 0}]},
        )

    assert res.status_code == 422, res.text


def test_an_unknown_purchase_order_is_a_404(scm_app):
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])

    with TestClient(world.app) as c:
        res = c.put(f"/api/v1/scm/purchase-orders/{_uid()}", json={"order_date": "2026-05-04"})

    assert res.status_code == 404, res.text


# --- who may write ----------------------------------------------------------

def test_a_role_without_the_planning_permission_cannot_write(scm_app):
    """Gated on `scm.reorder.run`, the same capability the confirm and delete writes on this
    router already hold. A read-only SCM role must not be able to rewrite the supply book."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}], role=None)

    with TestClient(world.app) as c:
        res = c.put(
            f"/api/v1/scm/purchase-orders/{world.po.id}", json={"order_date": "2026-05-04"}
        )

    assert res.status_code == 403, res.text


# --- the supplier select ----------------------------------------------------

def test_suppliers_are_searchable_on_the_server(scm_app):
    """The edit form's Supplier select. Served off THIS router's own `scm.dashboard.view`
    rather than the procurement master's permission, for the same reason
    `/sales-orders/agents` is: a purchasing/SCM role does not necessarily hold the
    master-data one and would 403 on this select alone."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])
    needle = world.supplier.supplier_code

    with TestClient(world.app) as c:
        res = c.get("/api/v1/scm/purchase-orders/suppliers", params={"query": needle})

    assert res.status_code == 200, res.text
    rows = res.json()
    assert [r["supplier_code"] for r in rows] == [needle]
    assert rows[0]["supplier_name"] == world.supplier.supplier_name


def test_the_supplier_select_pages(scm_app):
    """`limit` / `offset`, the same contract `customers/select` answers, so the select can
    ask for the next page rather than pulling the whole master."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])
    stem = f"{MARKER}-PAGE-{_uid()[:6]}".upper()
    for n in range(3):
        world.db.add(Supplier(
            id=_uid(), supplier_code=f"{stem}-{n}"[:30], supplier_name=f"{stem} supplier {n}",
            is_active=True,
        ))
    world.db.flush()

    with TestClient(world.app) as c:
        first = c.get(
            "/api/v1/scm/purchase-orders/suppliers",
            params={"query": stem, "limit": 2, "offset": 0},
        )
        second = c.get(
            "/api/v1/scm/purchase-orders/suppliers",
            params={"query": stem, "limit": 2, "offset": 2},
        )

    assert first.status_code == 200 and second.status_code == 200
    assert len(first.json()) == 2
    assert len(second.json()) == 1
    # Ordered by code, so the two pages neither repeat nor skip a row.
    codes = [r["supplier_code"] for r in first.json() + second.json()]
    assert codes == sorted(codes)


def test_the_supplier_select_never_shadows_a_purchase_order_id(scm_app):
    """`/purchase-orders/suppliers` has to be declared BEFORE `/purchase-orders/{po_id}`, or
    the word `suppliers` parses as an order id and the select 404s."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])

    with TestClient(world.app) as c:
        res = c.get("/api/v1/scm/purchase-orders/suppliers")

    assert res.status_code == 200, res.text
    assert isinstance(res.json(), list)
