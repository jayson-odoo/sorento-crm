"""Phase 2 RED tests - `GET /api/v1/order-management/outstanding-report`.

`documentation/plans/chatbot/PLAN-chatbot-outstanding-report.md` (Backend contract, Slice
S2); `documentation/plans/chatbot/chatbot-outstanding-report-acceptance-criteria.md`
AC-1110 to AC-1119.

Written BEFORE the route/service/schema exist (Phase 2, test-first). Every test hits the
route over HTTP and must fail with 404 (route not found) until the coder wires it up - not
an import error, not a fixture bug. Postgres only (`tests/_pg_fixture.py`), every row seeded
here; CI's database has none.

AC-1115 (captain ruling, 12 Sep 2026): the `do` block carries the same identity as the `so`
block - `do_qty = delivered_qty + pending_qty` over every DO (pending and delivered) matching
the product/filters, `pending_qty` = SUM over `_outstanding_clause`, `delivered_qty` = SUM over
`_delivered_clause`, `do_count` counts both, and `do_rows[]` lists BOTH pending and delivered
DOs, each row carrying its own `do_qty` / `delivered_qty` / `pending_qty`.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.access import RespondContact
from app.models.base import set_company_scope
from app.models.company import RespondContactCompany
from app.models.integration import Integration, IntegrationApiKey
from app.models.order import Order, OrderLine, OrderStatus, SalesOrder, SalesOrderLine
from app.models.user import (
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.integration_key_service import IntegrationKeyService

from tests._mc_lookup_seed import customer, order, order_line, product, seed_mocha, warehouse
from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/order-management/outstanding-report"
PERMISSION_SLUG = "order_management.orders.view"


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _seed_superadmin(db) -> dict:
    """A principal that clears `require_permission_with_api_key` via role bypass,
    so every test EXCEPT the permission-focused AC-1118 can ignore RBAC plumbing."""
    user = User(id=str(uuid.uuid4()), email=f"{unique_code('SA')}@test.com", name="ZZT Superadmin", status="ACTIVE")
    role = UserRole(id=str(uuid.uuid4()), slug="superadmin", name="Superadmin")
    db.add_all([user, role])
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    db.flush()
    return {"id": user.id, "email": user.email}


@pytest.fixture
def client(db):
    principal = _seed_superadmin(db)

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

    async def _override_scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------- seed helpers


def _so_line(
    db,
    *,
    product_id,
    ordered,
    delivered,
    customer_id=None,
    warehouse_id=None,
    line_status="open",
    header_status="open",
    source_system=None,
    order_date=None,
    so_number=None,
):
    so = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=so_number or unique_code("SO"),
        customer_id=customer_id,
        order_date=order_date,
        status=header_status,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(so)
    db.flush()
    db.add(
        SalesOrderLine(
            id=str(uuid.uuid4()),
            sales_order_id=so.id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            qty_ordered=ordered,
            qty_delivered=delivered,
            line_status=line_status,
            source_system=source_system,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    return so


def _delivered_status(db) -> OrderStatus:
    status = OrderStatus(id=str(uuid.uuid4()), status_code="delivered", status_name="Delivered")
    db.add(status)
    db.flush()
    return status


def _do(
    db,
    *,
    product_id,
    warehouse_id,
    qty,
    customer_id=None,
    order_date=None,
    actual_delivery_date=None,
    order_status_id=None,
    number=None,
):
    o = Order(
        id=str(uuid.uuid4()),
        order_number=number or unique_code("DO"),
        customer_id=customer_id,
        order_date=order_date,
        actual_delivery_date=actual_delivery_date,
        order_status_id=order_status_id,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(o)
    db.flush()
    db.add(
        OrderLine(
            id=str(uuid.uuid4()),
            order_id=o.id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            quantity=qty,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    return o


# --------------------------------------------------------------------- AC-1110


def test_so_figures_share_one_population(client, db):
    """One product, four SO lines: only the live (open header + open line) line
    counts. Cancelled and retired-provisional (line_status='closed', regardless of
    source_system or qty_delivered) contribute to none of the three figures."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _so_line(db, product_id=prod.id, ordered=10, delivered=3, header_status="open", line_status="open")
    _so_line(db, product_id=prod.id, ordered=10, delivered=10, header_status="open", line_status="closed")
    _so_line(db, product_id=prod.id, ordered=8, delivered=0, header_status="open", line_status="cancelled")
    _so_line(
        db,
        product_id=prod.id,
        ordered=5,
        delivered=0,
        header_status="open",
        line_status="closed",
        source_system="scm_order_inquiry",
    )
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code, "scope": "so"})
    assert resp.status_code == 200, resp.text
    so = resp.json()["so"]
    assert (so["ordered_qty"], so["transferred_qty"], so["outstanding_qty"]) == (10, 3, 7)
    assert so["ordered_qty"] == so["transferred_qty"] + so["outstanding_qty"]


# --------------------------------------------------------------------- AC-1111


def test_order_date_window_filters_so_and_do(client, db):
    """A 2026 window keeps only the 2026 SO/DO - in totals, by_location, by_customer
    and the row lists - and never filters on `actual_delivery_date`."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WH"))
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Window Customer")

    _so_line(
        db, product_id=prod.id, ordered=9, delivered=2, customer_id=cust.id, warehouse_id=wh.id,
        order_date=date(2025, 6, 1), so_number=unique_code("SO25"),
    )
    _so_line(
        db, product_id=prod.id, ordered=6, delivered=1, customer_id=cust.id, warehouse_id=wh.id,
        order_date=date(2026, 6, 1), so_number=unique_code("SO26"),
    )
    # A DO with no actual_delivery_date (never delivered) but IN the 2026 order_date window -
    # must still be counted, proving the window is on order_date, not actual_delivery_date.
    _do(
        db, product_id=prod.id, warehouse_id=wh.id, qty=40, customer_id=cust.id,
        order_date=date(2025, 7, 1), actual_delivery_date=None, number=unique_code("DO25"),
    )
    _do(
        db, product_id=prod.id, warehouse_id=wh.id, qty=25, customer_id=cust.id,
        order_date=date(2026, 7, 1), actual_delivery_date=None, number=unique_code("DO26"),
    )
    db.commit()

    resp = client.get(
        BASE,
        params={
            "product_code": prod.product_code,
            "scope": "both",
            "order_date_from": "2026-01-01",
            "order_date_to": "2026-12-31",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert (body["so"]["ordered_qty"], body["so"]["outstanding_qty"]) == (6, 5)
    assert body["so"]["so_count"] == 1
    assert {row["customer_name"] for row in body["so_by_customer"]} == {"ZZT Window Customer"}
    assert sum(row["ordered_qty"] for row in body["so_by_location"]) == 6
    assert [row["order_date"] for row in body["so_rows"]] == ["2026-06-01"]

    assert body["do"]["do_qty"] == 25
    assert body["do"]["do_count"] == 1
    assert [row["do_qty"] for row in body["do_rows"]] == [25]
    assert sum(row["do_qty"] for row in body["do_by_location"]) == 25
    assert sum(row["do_qty"] for row in body["do_by_customer"]) == 25


# --------------------------------------------------------------------- AC-1112


def test_warehouse_codes_filter_and_null_bucket(client, db):
    """`warehouse_codes` filters SO lines on `sales_order_lines.warehouse_id` and DO
    lines on `order_lines.warehouse_id`. A NULL-warehouse SO line is excluded once the
    filter is set, and buckets under `code: null` when it is not (order_lines.warehouse_id
    is NOT NULL at the DB, so only the SO side can show the null bucket)."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    wh_ib = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-BRW-IB")
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT WH Customer")

    _so_line(db, product_id=prod.id, ordered=10, delivered=0, warehouse_id=wh_ib.id, customer_id=cust.id)
    _so_line(db, product_id=prod.id, ordered=4, delivered=0, warehouse_id=None, customer_id=cust.id)
    _do(db, product_id=prod.id, warehouse_id=wh_ib.id, qty=7, customer_id=cust.id)
    db.commit()

    unfiltered = client.get(BASE, params={"product_code": prod.product_code, "scope": "both"})
    assert unfiltered.status_code == 200, unfiltered.text
    body = unfiltered.json()
    assert body["so"]["ordered_qty"] == 14
    codes = {row["code"] for row in body["so_by_location"]}
    assert codes == {"ZZT-BRW-IB", None}

    filtered = client.get(
        BASE,
        params={"product_code": prod.product_code, "scope": "both", "warehouse_codes": "ZZT-BRW-IB"},
    )
    assert filtered.status_code == 200, filtered.text
    fbody = filtered.json()
    assert fbody["so"]["ordered_qty"] == 10  # the NULL-warehouse line is excluded
    assert {row["code"] for row in fbody["so_by_location"]} == {"ZZT-BRW-IB"}
    assert fbody["do"]["do_qty"] == 7
    assert {row["code"] for row in fbody["do_by_location"]} == {"ZZT-BRW-IB"}


# --------------------------------------------------------------------- AC-1113


def test_customer_query_matches_name_not_debtor_code(client, db):
    """`customer_query=Dealer A` matches `customers.customer_name` ILIKE - a customer
    whose CODE contains the query string but whose NAME does not must be excluded."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    match = customer(db, company_id=DEFAULT_COMPANY_ID, name="Dealer A Sdn Bhd")
    match.customer_code = unique_code("CODE")
    no_match = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Totally Different Co")
    no_match.customer_code = "ZZT-DEALER-A-CODE"  # contains the query text, in the CODE only
    db.flush()

    _so_line(db, product_id=prod.id, ordered=10, delivered=0, customer_id=match.id)
    _so_line(db, product_id=prod.id, ordered=20, delivered=0, customer_id=no_match.id)
    db.commit()

    resp = client.get(
        BASE, params={"product_code": prod.product_code, "scope": "so", "customer_query": "Dealer A"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["so"]["ordered_qty"] == 10
    assert body["so"]["so_count"] == 1
    assert {row["customer_name"] for row in body["so_by_customer"]} == {"Dealer A Sdn Bhd"}


# --------------------------------------------------------------------- AC-1114


def test_so_rows_roll_up_lines_per_so(client, db):
    """Two live lines on one SO (205 + 205) roll up to ONE `so_rows` entry with
    `ordered_qty=410` and the distinct warehouse codes joined by ', '. Rows are
    sorted by `order_date` asc then `so_number`."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    wh_a = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-WHA")
    wh_b = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-WHB")
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Rollup Customer")

    so_multi = SalesOrder(
        id=str(uuid.uuid4()), so_number="ZZT-SO-LATER", customer_id=cust.id,
        order_date=date(2026, 6, 2), status="open", company_id=DEFAULT_COMPANY_ID,
    )
    db.add(so_multi)
    db.flush()
    db.add_all([
        SalesOrderLine(
            id=str(uuid.uuid4()), sales_order_id=so_multi.id, product_id=prod.id,
            warehouse_id=wh_a.id, qty_ordered=205, qty_delivered=0, line_status="open",
            company_id=DEFAULT_COMPANY_ID,
        ),
        SalesOrderLine(
            id=str(uuid.uuid4()), sales_order_id=so_multi.id, product_id=prod.id,
            warehouse_id=wh_b.id, qty_ordered=205, qty_delivered=0, line_status="open",
            company_id=DEFAULT_COMPANY_ID,
        ),
    ])

    # An earlier single-line SO, to check the sort (order_date asc).
    _so_line(
        db, product_id=prod.id, ordered=50, delivered=0, customer_id=cust.id, warehouse_id=wh_a.id,
        order_date=date(2026, 6, 1), so_number="ZZT-SO-EARLIER",
    )
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code, "scope": "so"})
    assert resp.status_code == 200, resp.text
    rows = resp.json()["so_rows"]
    assert [r["so_number"] for r in rows] == ["ZZT-SO-EARLIER", "ZZT-SO-LATER"]
    rolled = rows[1]
    assert rolled["ordered_qty"] == 410
    assert set(rolled["location"].split(", ")) == {"ZZT-WHA", "ZZT-WHB"}


# --------------------------------------------------------------------- AC-1115


def test_do_block_pending_and_delivered(client, db):
    """One delivered DO (qty 5) and one pending DO (qty 7) for the same product:
    `do_qty = delivered_qty + pending_qty` (12 = 5 + 7), `do_count` counts both, and
    `do_rows` lists BOTH DOs, each carrying its own `do_qty` / `delivered_qty` /
    `pending_qty` (captain ruling 12 Sep 2026 - see module docstring)."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WH"))
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT DO Customer")
    delivered_status = _delivered_status(db)

    _do(
        db, product_id=prod.id, warehouse_id=wh.id, qty=5, customer_id=cust.id,
        order_status_id=delivered_status.id, actual_delivery_date=date(2026, 3, 1),
        number="ZZT-DO-DELIVERED",
    )
    _do(
        db, product_id=prod.id, warehouse_id=wh.id, qty=7, customer_id=cust.id,
        order_status_id=None, actual_delivery_date=None, number="ZZT-DO-PENDING",
    )
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code, "scope": "do"})
    assert resp.status_code == 200, resp.text
    do = resp.json()["do"]
    assert (do["do_qty"], do["delivered_qty"], do["pending_qty"]) == (12, 5, 7)
    assert do["do_qty"] == do["delivered_qty"] + do["pending_qty"]
    assert do["do_count"] == 2

    rows = {r["do_number"]: r for r in resp.json()["do_rows"]}
    assert set(rows) == {"ZZT-DO-DELIVERED", "ZZT-DO-PENDING"}
    delivered_row = rows["ZZT-DO-DELIVERED"]
    assert (delivered_row["do_qty"], delivered_row["delivered_qty"], delivered_row["pending_qty"]) == (5, 5, 0)
    pending_row = rows["ZZT-DO-PENDING"]
    assert (pending_row["do_qty"], pending_row["delivered_qty"], pending_row["pending_qty"]) == (7, 0, 7)


# --------------------------------------------------------------------- AC-1116


def test_breakdowns_sum_to_totals(client, db):
    """so_by_location/so_by_customer and do_by_location/do_by_customer each sum to
    their block's totals."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    wh1 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WH1"))
    wh2 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WH2"))
    cust1 = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Cust One")
    cust2 = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Cust Two")

    _so_line(db, product_id=prod.id, ordered=10, delivered=2, customer_id=cust1.id, warehouse_id=wh1.id)
    _so_line(db, product_id=prod.id, ordered=6, delivered=1, customer_id=cust2.id, warehouse_id=wh2.id)
    _do(db, product_id=prod.id, warehouse_id=wh1.id, qty=15, customer_id=cust1.id)
    _do(db, product_id=prod.id, warehouse_id=wh2.id, qty=9, customer_id=cust2.id)
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code, "scope": "both"})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert sum(r["ordered_qty"] for r in body["so_by_location"]) == body["so"]["ordered_qty"]
    assert sum(r["outstanding_qty"] for r in body["so_by_location"]) == body["so"]["outstanding_qty"]
    assert sum(r["ordered_qty"] for r in body["so_by_customer"]) == body["so"]["ordered_qty"]
    assert sum(r["outstanding_qty"] for r in body["so_by_customer"]) == body["so"]["outstanding_qty"]

    assert sum(r["do_qty"] for r in body["do_by_location"]) == body["do"]["do_qty"]
    assert sum(r["pending_qty"] for r in body["do_by_location"]) == body["do"]["pending_qty"]
    assert sum(r["do_qty"] for r in body["do_by_customer"]) == body["do"]["do_qty"]
    assert sum(r["pending_qty"] for r in body["do_by_customer"]) == body["do"]["pending_qty"]


# --------------------------------------------------------------------- AC-1117


def test_scope_omits_block_and_response_model_keeps_every_field(client, db):
    """A scope not asked for is ABSENT from the body (not an empty dict); `scope=both`
    (default) keeps every field the plan's contract declares - a `response_model`
    silently drops any undeclared one."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WH"))
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Field Customer")
    _so_line(db, product_id=prod.id, ordered=10, delivered=2, customer_id=cust.id, warehouse_id=wh.id)
    _do(db, product_id=prod.id, warehouse_id=wh.id, qty=5, customer_id=cust.id)
    db.commit()

    so_only = client.get(BASE, params={"product_code": prod.product_code, "scope": "so"})
    assert so_only.status_code == 200, so_only.text
    assert "do" not in so_only.json()
    assert "so" in so_only.json()

    do_only = client.get(BASE, params={"product_code": prod.product_code, "scope": "do"})
    assert do_only.status_code == 200, do_only.text
    assert "so" not in do_only.json()
    assert "do" in do_only.json()

    both = client.get(BASE, params={"product_code": prod.product_code})  # default scope=both
    assert both.status_code == 200, both.text
    body = both.json()
    for key in (
        "product_code", "customer_name", "warehouse_codes", "order_date_from", "order_date_to",
        "so", "do", "so_by_location", "so_by_customer", "do_by_location", "do_by_customer",
        "so_rows", "do_rows",
    ):
        assert key in body, f"missing field: {key}"
    for key in ("ordered_qty", "transferred_qty", "outstanding_qty", "so_count", "order_date_min", "order_date_max"):
        assert key in body["so"], f"missing so.{key}"
    for key in ("do_qty", "delivered_qty", "pending_qty", "do_count", "do_date_min", "do_date_max"):
        assert key in body["do"], f"missing do.{key}"


# --------------------------------------------------------------------- AC-1118


def test_route_permission_and_api_key_act_as(db):
    """403 without `order_management.orders.view`; an X-API-Key principal with an
    act-as user who HOLDS the grant reaches the route."""
    from app.config import settings

    def _override_db():
        yield db

    async def _override_scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _so_line(db, product_id=prod.id, ordered=1, delivered=0)

    no_grant_user = User(id=str(uuid.uuid4()), email=f"{unique_code('NG')}@test.com", name="ZZT No Grant", status="ACTIVE")
    db.add(no_grant_user)
    db.flush()

    permission = UserPermission(id=str(uuid.uuid4()), slug=PERMISSION_SLUG, name=PERMISSION_SLUG)
    role = UserRole(id=str(uuid.uuid4()), slug="zzt_orders_view_role", name="ZZT Orders View")
    granted_user = User(id=str(uuid.uuid4()), email=f"{unique_code('OK')}@test.com", name="ZZT Granted", status="ACTIVE")
    db.add_all([permission, role, granted_user])
    db.flush()
    db.add(UserRoleAssignment(user_id=granted_user.id, role_id=role.id))
    db.add(UserRolePermission(role_id=role.id, permission_id=permission.id))
    db.flush()

    integration = Integration(
        id=str(uuid.uuid4()), name="zzt-outstanding-report-key", type="automation",
        act_as_user_id=granted_user.id, is_active=True,
    )
    db.add(integration)
    db.flush()
    plaintext_key = IntegrationKeyService(db).issue_key(integration)
    db.commit()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        # No grant: JWT-style principal without the permission -> 403.
        app.dependency_overrides[get_current_user] = lambda: {"id": no_grant_user.id, "email": no_grant_user.email}
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": no_grant_user.id, "email": no_grant_user.email}
        client = TestClient(app)
        denied = client.get(BASE, params={"product_code": prod.product_code})
        assert denied.status_code == 403, denied.text

        # X-API-Key + act-as: remove the override so the real key resolves.
        del app.dependency_overrides[get_current_user_or_api_key]
        del app.dependency_overrides[get_current_user]
        client = TestClient(app)
        allowed = client.get(
            BASE, params={"product_code": prod.product_code}, headers={"X-API-Key": plaintext_key}
        )
        assert allowed.status_code == 200, allowed.text
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- AC-1113b


def test_customer_ids_filters_report(client, db):
    """`customer_ids` (csv of `customers.id`) filters the same way `customer_query` does -
    the chatbot lane sends the resolved customer entity's id, never the debtor code.
    `customer_query` and `customer_ids` together intersect (S4 point 9 / AC-1113b)."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    match = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Customer Ids Match")
    other = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Customer Ids Other")

    _so_line(db, product_id=prod.id, ordered=10, delivered=0, customer_id=match.id)
    _so_line(db, product_id=prod.id, ordered=25, delivered=0, customer_id=other.id)
    db.commit()

    resp = client.get(
        BASE, params={"product_code": prod.product_code, "scope": "so", "customer_ids": match.id}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["so"]["ordered_qty"] == 10, (
        f"customer_ids must filter the report the same way customer_query does: {body}"
    )
    assert {row["customer_name"] for row in body["so_by_customer"]} == {"ZZT Customer Ids Match"}


def test_customer_ids_echo_the_resolved_names_in_the_header(client, db):
    """AC-1136 (review round, 13 Sep 2026): the header prints the response's
    `customer_name`, and the chatbot sends `customer_ids` (a resolved UUID), never
    `customer_query`. The echo was set from `customer_query` alone, so a customer ask
    from WhatsApp printed `Customer: all` over figures that WERE filtered to one
    customer - the reply contradicted the numbers under it. Several ids join by ", "."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    first = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Echo Customer A")
    second = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT Echo Customer B")
    _so_line(db, product_id=prod.id, ordered=10, delivered=0, customer_id=first.id)
    _so_line(db, product_id=prod.id, ordered=4, delivered=0, customer_id=second.id)
    db.commit()

    one = client.get(
        BASE, params={"product_code": prod.product_code, "scope": "so", "customer_ids": first.id}
    )
    assert one.status_code == 200, one.text
    assert one.json()["customer_name"] == "ZZT Echo Customer A", one.json()

    both = client.get(
        BASE,
        params={
            "product_code": prod.product_code,
            "scope": "so",
            "customer_ids": f"{first.id},{second.id}",
        },
    )
    assert both.status_code == 200, both.text
    assert both.json()["customer_name"] == "ZZT Echo Customer A, ZZT Echo Customer B", both.json()


def test_fractional_quantities_round_to_whole_units(client, db):
    """`sales_order_lines.qty_ordered` is `Numeric(15,4)`, so a fraction is storable;
    every quantity on this report is declared `int` (the reply prints whole units with
    a thousands separator). 2.5 rounds HALF UP to 3 - never Python's bankers' rounding,
    which would print 2 for 2.5 and 4 for 3.5 in the same reply."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _so_line(db, product_id=prod.id, ordered=Decimal("2.5000"), delivered=Decimal("0"))
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code, "scope": "so"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["so"]["ordered_qty"] == 3, body["so"]
    assert body["so"]["outstanding_qty"] == 3, body["so"]
    assert body["so_rows"][0]["ordered_qty"] == 3, body["so_rows"]


# --------------------------------------------------------------------------- AC-1119


def test_product_code_exact_no_siblings(client, db):
    """`product_code` resolves exactly (case-insensitive); a sibling code
    (`SRTWT7445-A`) never contributes to `SRTWT7445`'s figures."""
    target = product(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SRTWT7445")
    sibling = product(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SRTWT7445-A")
    _so_line(db, product_id=target.id, ordered=10, delivered=0)
    _so_line(db, product_id=sibling.id, ordered=99, delivered=0)
    db.commit()

    resp = client.get(BASE, params={"product_code": "zzt-srtwt7445", "scope": "so"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["so"]["ordered_qty"] == 10
    assert body["product_code"] == "ZZT-SRTWT7445"


# --------------------------------------------------------------------------- B1 (security review, 13 Sep 2026)


def test_report_is_company_scoped_for_api_key_contact(db, monkeypatch):
    """B1 BLOCKER: the `client` fixture above overrides `apply_company_scope` with a
    single hard-coded company, so no other test in this file exercises the REAL
    resolver. Without `contact_id`/`space_id` reaching `crm_outstanding_report`'s
    query_params (the catalog fix this test pins), an X-API-Key call scopes to
    `None` (every company) and a Sorento contact's report would sum in Mocha's SO
    lines too - this test seeds the SAME product code live in both companies and
    asserts only the contact's own company's figures come back.

    `apply_company_scope` is NOT overridden here (that is the whole point): the
    route's own dependency runs for real, off the request's own `X-API-Key` +
    `contact_id` + `space_id`. Two different checks read the same key for two
    different reasons - `_api_key_valid` (company-scope resolution) compares it
    literally against `settings.external_api_key`, while `resolve_integration_
    principal` (route permission) looks it up by hash in `integration_api_keys` -
    so the ONE issued key is used for both, and `settings.external_api_key` is
    pinned to it, mirroring `tests/test_mcp_scope_resolver.py`'s own note on why
    that pin is necessary in a test process that never sets the env var.
    """
    from app.config import settings

    mocha = seed_mocha(db)
    code = unique_code("SKU")

    prod_a = product(db, company_id=DEFAULT_COMPANY_ID, code=code)
    prod_b = product(db, company_id=mocha.id, code=code)

    _so_line(db, product_id=prod_a.id, ordered=10, delivered=3)  # Sorento: outstanding 7
    so_b = SalesOrder(
        id=str(uuid.uuid4()), so_number=unique_code("SO"), status="open", company_id=mocha.id,
    )
    db.add(so_b)
    db.flush()
    db.add(
        SalesOrderLine(
            id=str(uuid.uuid4()), sales_order_id=so_b.id, product_id=prod_b.id,
            qty_ordered=500, qty_delivered=0, line_status="open", company_id=mocha.id,
        )
    )

    contact = RespondContact(id=str(uuid.uuid4()), phone_number=f"+6{unique_code('PH')[:10]}")
    db.add(contact)
    db.flush()
    db.add(
        RespondContactCompany(
            id=str(uuid.uuid4()), respond_contact_id=contact.id, company_id=DEFAULT_COMPANY_ID,
        )
    )

    superadmin = _seed_superadmin(db)
    integration = Integration(
        id=str(uuid.uuid4()), name="zzt-scope-key", type="automation",
        act_as_user_id=superadmin["id"], is_active=True,
    )
    db.add(integration)
    db.flush()
    plaintext_key = IntegrationKeyService(db).issue_key(integration)
    db.commit()
    monkeypatch.setattr(settings, "external_api_key", plaintext_key)

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        client = TestClient(app)
        resp = client.get(
            BASE,
            params={"product_code": code, "scope": "so", "contact_id": contact.id, "space_id": "zzt-space"},
            headers={"X-API-Key": plaintext_key},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["so"]["ordered_qty"] == 10, (
            f"a Sorento-only contact must never see Mocha's SO lines: {body}"
        )
        assert body["so"]["outstanding_qty"] == 7
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- S3 (security review, 13 Sep 2026)


def test_customer_ids_rejects_a_non_uuid_value(client, db):
    """S3: `customer_ids` is a UUID param like every other `<entity>_ids` filter on
    this route file - a non-UUID value is a 400, the same `parse_uuid_list` gives
    `order_ids`/`transporter_ids` elsewhere, never a silent no-match."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code, "customer_ids": "not-a-uuid"})
    assert resp.status_code == 400, resp.text


def test_customer_ids_over_fifty_is_422(client, db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    db.commit()

    too_many = ",".join(str(uuid.uuid4()) for _ in range(51))
    resp = client.get(BASE, params={"product_code": prod.product_code, "customer_ids": too_many})
    assert resp.status_code == 422, resp.text


def test_warehouse_codes_over_fifty_is_422(client, db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    db.commit()

    too_many = ",".join(f"ZZT-WH-{i}" for i in range(51))
    resp = client.get(BASE, params={"product_code": prod.product_code, "warehouse_codes": too_many})
    assert resp.status_code == 422, resp.text
