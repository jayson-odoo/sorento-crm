"""Who pushed a sales order to purchasing, and when (PLAN section H, AC-H2 to AC-H4).

`order_inquiries.raised_by` / `raised_at` have been written at confirm since the feature
shipped and were shown nowhere: the worklist printed a raise DATE off the row and never
named the person, so "who asked for this" was a question only the database could answer.

Four things are pinned here, and each one is a way it would silently stop working:

* the row NAMES the person (`raised_by_name`), never their id - and it is asserted on the
  response JSON rather than on the service dict, because `response_model` drops a field
  the schema does not declare and the service would still look right;
* the one search box finds them, by name and by the front of their email address, which is
  what a person types when they only know "cindy";
* the `raised_by` filter narrows the list, and the summary offers ONLY users who have
  actually raised something (a picker listing every user in the company is a picker whose
  entries mostly return nothing);
* a RECONFIRM re-stamps the header, so the name on the screen is the person who last said
  so rather than whoever happened to confirm the first revision.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.models.order import Customer, SalesOrder
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.user import User

from ._pg_fixture import blank_session

MARKER = "zzt-oi-raised-by"
BASE = "/api/v1/project-sales"
LIST = f"{BASE}/order-inquiries"
SUMMARY = f"{BASE}/order-inquiries/summary"

READ_ONLY = ["projects.projects.view"]


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str, email: str) -> User:
    row = User(id=_uid(), email=email, name=name)
    db.add(row)
    db.flush()
    return row


def _product(db, code: str) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=code,
        product_name=f"{MARKER} {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _adopted_order(db, company_id: str, so_number: str) -> ProjectSalesOrder:
    """An order out of the AutoCount book: no project registration at all, which is the
    shape almost every row on this worklist has."""
    customer = Customer(
        id=_uid(),
        company_id=company_id,
        customer_code=f"ZZT-{_uid()[:8]}",
        customer_name=f"{MARKER} Optad Sdn Bhd",
    )
    db.add(customer)
    db.flush()
    core = SalesOrder(
        id=_uid(),
        company_id=company_id,
        so_number=so_number,
        customer_id=customer.id,
        order_date=date(2026, 1, 8),
    )
    db.add(core)
    db.flush()
    order = ProjectSalesOrder(
        id=_uid(),
        company_id=company_id,
        project_id=None,
        so_id=core.id,
        provisional_ref=so_number,
        autocount_doc_no=so_number,
        status="adopted",
    )
    db.add(order)
    db.flush()
    return order


def _line(db, company_id: str, order: ProjectSalesOrder, product: Product) -> ProjectSalesOrderLine:
    row = ProjectSalesOrderLine(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=order.id,
        line_no=1,
        product_id=product.id,
        description=f"{MARKER} line",
        qty=Decimal("932"),
        uom="UNIT",
        unit_price=Decimal("10.00"),
        amount=Decimal("9320.00"),
        delivery_date=date(2026, 3, 2),
    )
    db.add(row)
    db.flush()
    return row


def _inquiry(
    db, company_id: str, order: ProjectSalesOrder, *, raised_by: str, raised_at: datetime
) -> OrderInquiry:
    inquiry = OrderInquiry(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=order.id,
        state=INQUIRY_RAISED,
        raised_by=raised_by,
        raised_at=raised_at,
    )
    db.add(inquiry)
    db.flush()
    return inquiry


def _row(db, company_id: str, inquiry: OrderInquiry, line: ProjectSalesOrderLine, item_code: str):
    row = OrderInquiryRow(
        id=_uid(),
        company_id=company_id,
        order_inquiry_id=inquiry.id,
        so_line_id=line.id,
        item_code=item_code,
        qty=Decimal("932"),
        delivery_date=date(2026, 3, 2),
        verb=IV_ORDER,
        state=INQUIRY_RAISED,
    )
    db.add(row)
    db.flush()
    return row


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
    """Two CS users, one inquiry each, so every assertion below is about telling them
    apart rather than about the only row there is."""
    cindy = _user(db, f"{MARKER} Cindy Lee", f"cindy.{_uid()[:8]}@zzt.test")
    johnson = _user(db, f"{MARKER} Johnson Tan", f"johnson.{_uid()[:8]}@zzt.test")
    # A third CS user who has raised nothing: the filter's own list must not offer them.
    idle = _user(db, f"{MARKER} Never Raised", f"idle.{_uid()[:8]}@zzt.test")

    cindy_order = _adopted_order(db, company_id, f"ZZTSO{_uid()[:8]}")
    cindy_product = _product(db, f"ZZT-WESERP10B-{_uid()[:6]}")
    cindy_line = _line(db, company_id, cindy_order, cindy_product)
    cindy_inquiry = _inquiry(
        db,
        company_id,
        cindy_order,
        raised_by=cindy.id,
        raised_at=datetime(2026, 8, 25, 0, 42),
    )
    cindy_row = _row(db, company_id, cindy_inquiry, cindy_line, cindy_product.product_code)

    johnson_order = _adopted_order(db, company_id, f"ZZTSO{_uid()[:8]}")
    johnson_product = _product(db, f"ZZT-M310CRPJ-{_uid()[:6]}")
    johnson_line = _line(db, company_id, johnson_order, johnson_product)
    johnson_inquiry = _inquiry(
        db,
        company_id,
        johnson_order,
        raised_by=johnson.id,
        raised_at=datetime(2026, 8, 22, 6, 10),
    )
    johnson_row = _row(
        db, company_id, johnson_inquiry, johnson_line, johnson_product.product_code
    )

    db.commit()
    return {
        "cindy": cindy,
        "johnson": johnson,
        "idle": idle,
        "cindy_row": cindy_row,
        "johnson_row": johnson_row,
        "cindy_order": cindy_order,
        "cindy_line": cindy_line,
        "cindy_inquiry": cindy_inquiry,
        "cindy_product": cindy_product,
    }


@pytest.fixture()
def api():
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        seeded = _seed(db, company_id)
        client, originals = _client(db, seeded["cindy"].id, READ_ONLY)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, seeded
        finally:
            _restore(originals)


# ------------------------------------------------------------------ AC-H2


def test_the_worklist_row_names_who_raised_it_and_when(api):
    client, _db, _company_id, seeded = api

    response = client.get(LIST)

    assert response.status_code == 200, response.text
    rows = {row["id"]: row for row in response.json()["data"]}
    cindy = rows[seeded["cindy_row"].id]
    # The NAME, on the wire. A service that resolved it and a schema that dropped it
    # would still pass an assertion made against the service.
    assert cindy["raised_by_name"] == seeded["cindy"].name
    assert cindy["raised_at"] is not None
    # Never the id: the screen prints this cell as it comes.
    assert seeded["cindy"].id not in str(cindy["raised_by_name"])


def test_a_row_whose_inquiry_names_nobody_reads_blank_rather_than_breaking(api):
    client, db, company_id, seeded = api

    order = _adopted_order(db, company_id, f"ZZTSO{_uid()[:8]}")
    product = _product(db, f"ZZT-ANON-{_uid()[:6]}")
    line = _line(db, company_id, order, product)
    inquiry = _inquiry(
        db, company_id, order, raised_by=None, raised_at=datetime(2026, 8, 20, 2, 0)
    )
    row = _row(db, company_id, inquiry, line, product.product_code)
    db.commit()

    response = client.get(LIST, params={"query": product.product_code})

    assert response.status_code == 200, response.text
    rows = {entry["id"]: entry for entry in response.json()["data"]}
    assert rows[row.id]["raised_by_name"] is None


def test_the_worklist_sorts_by_the_raising_person(api):
    client, _db, _company_id, seeded = api

    response = client.get(LIST, params={"sort": "raised_by_name", "dir": "asc"})

    assert response.status_code == 200, response.text
    names = [row["raised_by_name"] for row in response.json()["data"]]
    assert names == sorted(names, key=lambda value: (value is None, value or ""))


# ------------------------------------------------------------------ AC-H3


def test_searching_the_cs_users_name_returns_their_inquiries(api):
    client, _db, _company_id, seeded = api

    response = client.get(LIST, params={"query": "Cindy"})

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert seeded["cindy_row"].id in ids
    assert seeded["johnson_row"].id not in ids


def test_searching_the_front_of_the_cs_users_email_returns_their_inquiries(api):
    client, _db, _company_id, seeded = api
    prefix = seeded["johnson"].email.split("@")[0][:7]

    response = client.get(LIST, params={"query": prefix})

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert seeded["johnson_row"].id in ids
    assert seeded["cindy_row"].id not in ids


def test_the_raised_by_filter_narrows_the_list_to_one_person(api):
    client, _db, _company_id, seeded = api

    response = client.get(LIST, params={"raised_by": seeded["cindy"].id})

    assert response.status_code == 200, response.text
    body = response.json()
    ids = {row["id"] for row in body["data"]}
    assert ids == {seeded["cindy_row"].id}
    assert body["pagination"]["total"] == 1


def test_the_summary_offers_only_people_who_have_raised_something(api):
    client, _db, _company_id, seeded = api

    response = client.get(SUMMARY)

    assert response.status_code == 200, response.text
    facets = response.json()["raised_by"]
    by_id = {entry["id"]: entry for entry in facets}
    assert by_id[seeded["cindy"].id]["label"] == seeded["cindy"].name
    assert by_id[seeded["cindy"].id]["rows"] == 1
    assert seeded["johnson"].id in by_id
    # Somebody who has never raised an inquiry is not a filter option.
    assert seeded["idle"].id not in by_id


def test_the_raised_by_list_keeps_every_person_while_one_of_them_is_selected(api):
    client, _db, _company_id, seeded = api

    response = client.get(SUMMARY, params={"raised_by": seeded["cindy"].id})

    assert response.status_code == 200, response.text
    body = response.json()
    # The control drops its OWN filter, or picking a person makes every other person
    # disappear from the picker and it cannot be used a second time.
    assert {entry["id"] for entry in body["raised_by"]} >= {
        seeded["cindy"].id,
        seeded["johnson"].id,
    }
    # The totals beside it still honour the filter, because they describe the screen.
    assert body["total_rows"] == 1


# ------------------------------------------------------------------ AC-H4


def test_reconfirming_restamps_who_raised_the_inquiry(api):
    """A second person confirms a new revision: the header says THEM, and says when.

    The inquiry itself is reused (purchasing keeps quoting one number through every
    revision), so without an explicit re-stamp the screen would keep naming whoever
    happened to confirm revision 1 forever.
    """
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    client, db, company_id, seeded = api
    order = seeded["cindy_order"]
    line = seeded["cindy_line"]
    inquiry = seeded["cindy_inquiry"]
    service = ProjectOrderInquiryService(db)
    buy_lines = [
        {
            "line": line,
            "buy_qty": Decimal("932"),
            "item_code": seeded["cindy_product"].product_code,
            "required_date": date(2026, 3, 2),
            "line_no": 1,
        }
    ]

    service.refresh_for_decision(
        order,
        SimpleNamespace(id=None, revision_no=1),
        buy_lines,
        actor_user_id=seeded["cindy"].id,
    )
    db.flush()
    first_raised_at = inquiry.raised_at

    service.refresh_for_decision(
        order,
        SimpleNamespace(id=None, revision_no=2),
        buy_lines,
        actor_user_id=seeded["johnson"].id,
    )
    db.commit()

    db.refresh(inquiry)
    assert inquiry.raised_by == seeded["johnson"].id
    assert inquiry.raised_at >= first_raised_at
    # And the worklist agrees, which is the only place a person reads it.
    response = client.get(LIST, params={"raised_by": seeded["johnson"].id})
    assert response.status_code == 200, response.text
    names = {row["raised_by_name"] for row in response.json()["data"]}
    assert names == {seeded["johnson"].name}
