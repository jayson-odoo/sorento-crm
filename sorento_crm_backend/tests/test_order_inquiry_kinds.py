"""The three cards' own numbers: `kinds` on the worklist summary (I2, AC-I11 to AC-I14).

`_kinds()` sums, over the matching rows, what sits on SPO allocations, what sits on
purchase order lines, and the remainder nobody has put anywhere - the same three the
`OrderInquiryStrip` cards read. What is worth pinning:

* a row linked PART of its quantity carries BOTH a kind and a Buy remainder - the split
  the bar draws as "PO 5 . Buy 3";
* the facet honours every filter except its OWN (`kind`), the same rule the month,
  supplier, project and raised-by controls already hold to - so pressing one card leaves
  the other two readable;
* the visible TOTALS (`total_rows` / `total_qty`) DO honour `kind`, because they describe
  what is on screen;
* a CANCELLED row contributes to neither the facet nor the `kind` filter - its quantity
  is not owed any more;
* `kind` is a closed set, refused at 422 like every other filter here.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
    IV_ORDER,
    SO_STATUS_DRAFT,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.user import User

from ._pg_fixture import blank_session

MARKER = "zzt-oi-kinds"
BASE = "/api/v1/project-sales"
LIST = f"{BASE}/order-inquiries"
SUMMARY = f"{LIST}/summary"

READ_ONLY = ["projects.projects.view"]


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _product(db, code: str, name: str) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=code,
        product_name=name,
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _project(db, company_id: str, user_id: str, title: str):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=user_id,
        developer_party_id=None,
        title=title,
    )


def _order_and_line(
    db, company_id: str, project_id, product: Product, qty: str, delivery_date: date
):
    order = ProjectSalesOrder(
        id=_uid(),
        company_id=company_id,
        project_id=project_id,
        area_group="TOWER",
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
        status=SO_STATUS_DRAFT,
        grouping_origin="area",
        published_at=datetime(2026, 1, 1, 9, 0),
    )
    db.add(order)
    db.flush()
    line = ProjectSalesOrderLine(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=order.id,
        line_no=1,
        product_id=product.id,
        description=f"{MARKER} line",
        qty=Decimal(str(qty)),
        uom="UNIT",
        unit_price=Decimal("10.00"),
        amount=Decimal(str(qty)) * Decimal("10.00"),
        delivery_date=delivery_date,
    )
    db.add(line)
    db.flush()
    return order, line


def _inquiry(db, company_id: str, order_id, raised_by: str) -> OrderInquiry:
    inquiry = OrderInquiry(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=order_id,
        state=INQUIRY_RAISED,
        raised_by=raised_by,
    )
    db.add(inquiry)
    db.flush()
    return inquiry


def _row(
    db,
    company_id: str,
    inquiry_id,
    so_line_id,
    item_code: str,
    qty: str,
    *,
    delivery_date: date | None = None,
    state: str = INQUIRY_RAISED,
) -> OrderInquiryRow:
    row = OrderInquiryRow(
        id=_uid(),
        company_id=company_id,
        order_inquiry_id=inquiry_id,
        so_line_id=so_line_id,
        item_code=item_code,
        qty=Decimal(str(qty)),
        delivery_date=delivery_date,
        verb=IV_ORDER,
        state=state,
    )
    db.add(row)
    db.flush()
    return row


def _link(
    db,
    company_id: str,
    row_id,
    qty: str,
    *,
    po_line_id=None,
    spo_allocation_id=None,
    document: str | None = None,
) -> OrderInquiryLink:
    link = OrderInquiryLink(
        id=_uid(),
        company_id=company_id,
        row_id=row_id,
        po_line_id=po_line_id,
        spo_allocation_id=spo_allocation_id,
        document=document,
        qty=Decimal(str(qty)),
    )
    db.add(link)
    db.flush()
    return link


def _po_line(db, company_id: str, product: Product, supplier: Supplier):
    order = PurchaseOrder(
        id=_uid(),
        company_id=company_id,
        po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    db.add(order)
    db.flush()
    line = PurchaseOrderLine(
        id=_uid(),
        company_id=company_id,
        purchase_order_id=order.id,
        product_id=product.id,
        qty_ordered=Decimal("20"),
    )
    db.add(line)
    db.flush()
    return order, line


def _spo_allocation(db, company_id: str, product: Product, qty: int = 3) -> SPOAllocation:
    allocation = SPOAllocation(
        id=_uid(),
        company_id=company_id,
        spo_number=f"ZZT-SPO-{_uid()[:6]}",
        allocated_quantity=qty,
        product_id=product.id,
    )
    db.add(allocation)
    db.flush()
    return allocation


def _client(db, user_id: str, permissions):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    granted = list(permissions)
    UserPermissionService.check_user_has_permission = (
        lambda self, uid, slug: slug in granted
    )
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


def _seed(db, company_id: str) -> dict:
    """Five rows, four of which count, laid out so every axis of the facet can be
    exercised on its own:

    * ``row_po`` - qty 8, linked 5 of it to a purchase order line (remainder 3). In
      project P, delivering January, raised by raiser 1, on a PO with a real supplier.
    * ``row_spo`` - qty 3, linked the whole of it to an SPO allocation (remainder 0). In
      project P, January, raised by raiser 2. No purchase order, so no supplier.
    * ``row_rest`` - qty 20, unlinked. In project P, but delivering FEBRUARY, raised by
      raiser 2 - the row every month filter is there to exclude.
    * ``row_other_project`` - qty 50, unlinked. Project P2, January, raised by raiser 1 -
      the row every project filter is there to exclude.
    * ``row_cancelled`` - qty 100, unlinked, state cancelled, otherwise identical to
      ``row_po``'s own project/month/raiser. Its remainder would swamp every total above
      if it were ever counted; it never should be.
    """
    raiser1 = _user(db, f"{MARKER} raiser1")
    raiser2 = _user(db, f"{MARKER} raiser2")
    project_p = _project(db, company_id, raiser1, f"{MARKER} Tuju Residence {_uid()[:8]}")
    project_p2 = _project(db, company_id, raiser1, f"{MARKER} Curvo Setapak {_uid()[:8]}")

    supplier = Supplier(
        id=_uid(),
        company_id=company_id,
        supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} DAFUYUAN",
    )
    db.add(supplier)
    db.flush()

    po_product = _product(db, f"ZZT-KIND-PO-{_uid()[:6]}", f"{MARKER} po product")
    order_po, line_po = _order_and_line(
        db, company_id, project_p.id, po_product, "8", date(2026, 1, 15)
    )
    inquiry_po = _inquiry(db, company_id, order_po.id, raiser1)
    row_po = _row(
        db,
        company_id,
        inquiry_po.id,
        line_po.id,
        po_product.product_code,
        "8",
        delivery_date=date(2026, 1, 15),
    )
    _, purchase_line = _po_line(db, company_id, po_product, supplier)
    _link(db, company_id, row_po.id, "5", po_line_id=purchase_line.id, document="ZZT-PO")

    spo_product = _product(db, f"ZZT-KIND-SPO-{_uid()[:6]}", f"{MARKER} spo product")
    order_spo, line_spo = _order_and_line(
        db, company_id, project_p.id, spo_product, "3", date(2026, 1, 15)
    )
    inquiry_spo = _inquiry(db, company_id, order_spo.id, raiser2)
    row_spo = _row(
        db,
        company_id,
        inquiry_spo.id,
        line_spo.id,
        spo_product.product_code,
        "3",
        delivery_date=date(2026, 1, 15),
    )
    allocation = _spo_allocation(db, company_id, spo_product, qty=3)
    _link(
        db,
        company_id,
        row_spo.id,
        "3",
        spo_allocation_id=allocation.id,
        document=allocation.spo_number,
    )

    rest_product = _product(db, f"ZZT-KIND-REST-{_uid()[:6]}", f"{MARKER} rest product")
    order_rest, line_rest = _order_and_line(
        db, company_id, project_p.id, rest_product, "20", date(2026, 2, 10)
    )
    inquiry_rest = _inquiry(db, company_id, order_rest.id, raiser2)
    row_rest = _row(
        db,
        company_id,
        inquiry_rest.id,
        line_rest.id,
        rest_product.product_code,
        "20",
        delivery_date=date(2026, 2, 10),
    )

    other_product = _product(
        db, f"ZZT-KIND-OTHERPROJ-{_uid()[:6]}", f"{MARKER} other project product"
    )
    order_other, line_other = _order_and_line(
        db, company_id, project_p2.id, other_product, "50", date(2026, 1, 20)
    )
    inquiry_other = _inquiry(db, company_id, order_other.id, raiser1)
    row_other_project = _row(
        db,
        company_id,
        inquiry_other.id,
        line_other.id,
        other_product.product_code,
        "50",
        delivery_date=date(2026, 1, 20),
    )

    cancelled_product = _product(
        db, f"ZZT-KIND-CANCELLED-{_uid()[:6]}", f"{MARKER} cancelled product"
    )
    order_cancelled, line_cancelled = _order_and_line(
        db, company_id, project_p.id, cancelled_product, "100", date(2026, 1, 15)
    )
    inquiry_cancelled = _inquiry(db, company_id, order_cancelled.id, raiser1)
    row_cancelled = _row(
        db,
        company_id,
        inquiry_cancelled.id,
        line_cancelled.id,
        cancelled_product.product_code,
        "100",
        delivery_date=date(2026, 1, 15),
        state=INQUIRY_CANCELLED,
    )

    db.commit()
    return {
        "project_p": project_p,
        "project_p2": project_p2,
        "supplier": supplier,
        "raiser1": raiser1,
        "raiser2": raiser2,
        "row_po": row_po,
        "row_spo": row_spo,
        "row_rest": row_rest,
        "row_other_project": row_other_project,
        "row_cancelled": row_cancelled,
        "po_product": po_product,
    }


@pytest.fixture()
def api():
    from app.models.base import company_scope
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        seeded = _seed(db, company_id)
        client, originals = _client(db, seeded["raiser1"], READ_ONLY)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, seeded
        finally:
            _restore(originals)


# --------------------------------------------------------------- the facet itself


def test_kinds_sums_spo_po_and_the_unlinked_remainder_across_the_matching_rows(api):
    """AC-I11: a row linked 5 of 8 carries BOTH the `po` 5 and a `buy` 3 remainder."""
    client, _db, _company_id, _seeded = api

    body = client.get(SUMMARY).json()

    assert set(body["kinds"].keys()) == {"spo", "po", "buy"}
    assert body["kinds"]["spo"] == "3"
    assert body["kinds"]["po"] == "5"
    # row_po's own remainder (3) + row_rest (20) + row_other_project (50). row_spo
    # contributes nothing here - it is wholly linked - and row_cancelled contributes
    # nothing at all, however large its own quantity is.
    assert body["kinds"]["buy"] == "73"


def test_a_cancelled_row_contributes_to_the_facet_not_at_all(api):
    """Its quantity is not owed any more (AC-I11's own reasoning) - a 100-unit cancelled
    row must not appear anywhere in a total that would otherwise read 173, not 73."""
    client, _db, _company_id, _seeded = api

    body = client.get(SUMMARY).json()

    assert body["kinds"]["buy"] == "73"


# ------------------------------------------------------- the facet honours other axes


def test_the_facet_honours_the_delivery_month_filter(api):
    """row_rest delivers in February and is the one this filter is there to drop."""
    client, _db, _company_id, _seeded = api

    body = client.get(SUMMARY, params={"delivery_month": "2026-01"}).json()

    assert body["kinds"] == {"spo": "3", "po": "5", "buy": "53"}  # 3 + 50, February out


def test_the_facet_honours_the_project_filter(api):
    """row_other_project sits in a different project and is the one this filter drops."""
    client, _db, _company_id, seeded = api

    body = client.get(
        SUMMARY, params={"project_id": seeded["project_p"].id}
    ).json()

    assert body["kinds"] == {"spo": "3", "po": "5", "buy": "23"}  # 3 + 20, P2 out


def test_the_facet_honours_the_supplier_filter(api):
    """Only `row_po` traces to a placed purchase order at all, so a supplier filter
    leaves it standing alone - `row_spo`, unlinked to any PO, disappears with it."""
    client, _db, _company_id, seeded = api

    body = client.get(
        SUMMARY, params={"supplier_id": seeded["supplier"].id}
    ).json()

    assert body["kinds"] == {"spo": "0", "po": "5", "buy": "3"}


def test_the_facet_honours_the_raised_by_filter(api):
    client, _db, _company_id, seeded = api

    by_raiser1 = client.get(SUMMARY, params={"raised_by": seeded["raiser1"]}).json()
    by_raiser2 = client.get(SUMMARY, params={"raised_by": seeded["raiser2"]}).json()

    # raiser1: row_po (po 5, buy 3), row_other_project (buy 50). row_spo/row_rest are
    # raiser2's own rows and drop out.
    assert by_raiser1["kinds"] == {"spo": "0", "po": "5", "buy": "53"}
    # raiser2: row_spo (spo 3), row_rest (buy 20). row_po/row_other_project drop out.
    assert by_raiser2["kinds"] == {"spo": "3", "po": "0", "buy": "20"}


def test_the_facet_honours_the_search_query(api):
    client, _db, _company_id, seeded = api

    body = client.get(
        SUMMARY, params={"query": seeded["po_product"].product_code}
    ).json()

    assert body["kinds"] == {"spo": "0", "po": "5", "buy": "3"}


def test_the_facet_does_not_honour_its_own_kind_filter(api):
    """Pressing a card must not empty the two cards beside it (AC-I11) - `kind=po` narrows
    the visible rows, never the facet computed off them."""
    client, _db, _company_id, _seeded = api

    pressed_po = client.get(SUMMARY, params={"kind": "po"}).json()
    pressed_spo = client.get(SUMMARY, params={"kind": "spo"}).json()
    pressed_buy = client.get(SUMMARY, params={"kind": "buy"}).json()
    unpressed = client.get(SUMMARY).json()

    assert pressed_po["kinds"] == pressed_spo["kinds"] == pressed_buy["kinds"] == unpressed["kinds"]


# --------------------------------------------------------- the totals DO honour kind


def test_the_visible_totals_honour_the_kind_filter_unlike_the_facet(api):
    """The strip's own row/qty badges describe what is ACTUALLY on screen (section 3.I2),
    the opposite rule from the facet beside them."""
    client, _db, _company_id, _seeded = api

    everything = client.get(SUMMARY).json()
    only_po = client.get(SUMMARY, params={"kind": "po"}).json()

    assert everything["total_rows"] == 5
    # Only row_po carries a po link.
    assert only_po["total_rows"] == 1
    assert only_po["total_qty"] == "8"
    # And the facet beside it is unmoved (previous test covers this more directly, this
    # pins the two side by side on the same response).
    assert only_po["kinds"] == everything["kinds"]


# -------------------------------------------------------------------- the kind filter


def test_kind_buy_returns_every_row_still_carrying_an_unlinked_remainder(api):
    """AC-I12/AC-I14: the partly-linked row answers to `buy` as well as to `po` - it is
    genuinely still a purchase to make."""
    client, _db, _company_id, seeded = api

    body = client.get(LIST, params={"kind": "buy", "limit": 50}).json()

    ids = {row["id"] for row in body["data"]}
    assert seeded["row_po"].id in ids  # partly linked - its 3 remainder is a Buy
    assert seeded["row_rest"].id in ids
    assert seeded["row_other_project"].id in ids
    assert seeded["row_spo"].id not in ids  # wholly linked, no remainder
    assert seeded["row_cancelled"].id not in ids  # cancelled, owes nothing
    assert body["pagination"]["total"] == 3


def test_kind_spo_returns_only_the_row_linked_to_an_allocation(api):
    client, _db, _company_id, seeded = api

    body = client.get(LIST, params={"kind": "spo"}).json()

    ids = {row["id"] for row in body["data"]}
    assert ids == {seeded["row_spo"].id}


def test_kind_po_returns_only_the_row_linked_to_a_purchase_order_line(api):
    client, _db, _company_id, seeded = api

    body = client.get(LIST, params={"kind": "po"}).json()

    ids = {row["id"] for row in body["data"]}
    assert ids == {seeded["row_po"].id}


def test_kind_rejects_anything_outside_the_closed_set(api):
    client, _db, _company_id, _seeded = api

    response = client.get(LIST, params={"kind": "nope"})

    assert response.status_code == 422


def test_kind_rejects_anything_outside_the_closed_set_on_the_summary_too(api):
    client, _db, _company_id, _seeded = api

    response = client.get(SUMMARY, params={"kind": "nope"})

    assert response.status_code == 422


# ------------------------------------------------- survives `response_model` (LESSONS)


def test_kinds_survives_response_model(api):
    """`response_model` silently drops a key it has not been told about - the failure
    mode this pins is `kinds` quietly vanishing from the wire the way an undeclared field
    always does."""
    client, _db, _company_id, _seeded = api

    raw = client.get(SUMMARY).json()

    assert "kinds" in raw
    assert set(raw["kinds"].keys()) == {"spo", "po", "buy"}
    for value in raw["kinds"].values():
        assert isinstance(value, str)  # a decimal STRING, never a float
