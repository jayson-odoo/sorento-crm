"""Phase 2 RED tests - `GET /api/v1/order-management/sales-report`.

`documentation/plans/chatbot/PLAN-chatbot-sales-report.md` (Backend contract, Slice
S2); `documentation/plans/chatbot/chatbot-sales-report-acceptance-criteria.md`
AC-1620 to AC-1632.

Written BEFORE the route/service/schema exist (Phase 2, test-first). Every test hits
the route over HTTP and must fail with 404 (route not found) until the coder wires it
up, not an import error, not a fixture bug. Postgres only (`tests/_pg_fixture.py`),
every row seeded here; CI's database has none.

Modelled on `test_outstanding_report.py` (same router file, same auth dependency,
same permission slug) - its seed helpers and fixtures are reused where the shape
matches; only the sales-report-specific pieces (line_total, required_date,
demand_class, months[]) are new here.

Money fields have no precedent on `OutstandingReportResponse` (it is quantity-only),
so this file compares money through `_money()`, which reads the JSON value as a
Decimal whether the coder serializes it as a string or a number - see the report to
the captain for why that is a genuine contract ambiguity, not a guess this file
should have resolved on its own.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.access import RespondContact
from app.models.base import set_company_scope
from app.models.company import RespondContactCompany
from app.models.integration import Integration
from app.models.order import SalesOrder, SalesOrderLine
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
from app.services.outstanding_report_service import _customer_echo

from tests._mc_lookup_seed import customer, product, seed_mocha, warehouse
from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/order-management/sales-report"
PERMISSION_SLUG = "order_management.orders.view"


def _money(v) -> Decimal:
    """Money-agnostic read: the coder may serialize a money figure as a JSON
    number or as a string - both parse cleanly through str(), a raw float does
    not lose precision doing so for the small numbers this file seeds."""
    return Decimal(str(v)).quantize(Decimal("0.01"))


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _seed_superadmin(db) -> dict:
    """A principal that clears `require_permission_with_api_key` via role bypass,
    so every test EXCEPT the permission-focused AC-1632 can ignore RBAC plumbing."""
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
    line_total=None,
    customer_id=None,
    warehouse_id=None,
    line_status="open",
    header_status="open",
    demand_class=None,
    order_date=None,
    required_date=None,
    so_number=None,
):
    """One SO with ONE line - the common case."""
    so = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=so_number or unique_code("SO"),
        customer_id=customer_id,
        order_date=order_date,
        status=header_status,
        demand_class=demand_class,
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
            line_total=line_total,
            line_status=line_status,
            required_date=required_date,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    return so


def _lines_on_one_so(
    db,
    *,
    product_id,
    lines: list[dict],
    customer_id=None,
    warehouse_id=None,
    header_status="open",
    demand_class=None,
    order_date=None,
    so_number=None,
):
    """One SO with SEVERAL lines - for the bucket-per-line and roll-up tests.

    Each dict in `lines` may set `ordered`, `delivered`, `line_total`,
    `line_status` (default "open"), `required_date` (default None) and
    `warehouse_id` (default the header-level `warehouse_id` above).
    """
    so = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=so_number or unique_code("SO"),
        customer_id=customer_id,
        order_date=order_date,
        status=header_status,
        demand_class=demand_class,
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(so)
    db.flush()
    for spec in lines:
        db.add(
            SalesOrderLine(
                id=str(uuid.uuid4()),
                sales_order_id=so.id,
                product_id=product_id,
                warehouse_id=spec.get("warehouse_id", warehouse_id),
                qty_ordered=spec["ordered"],
                qty_delivered=spec["delivered"],
                line_total=spec.get("line_total"),
                line_status=spec.get("line_status", "open"),
                required_date=spec.get("required_date"),
                company_id=DEFAULT_COMPANY_ID,
            )
        )
    return so


# --------------------------------------------------------------------- AC-1620


def test_ordered_equals_confirmed_plus_outstanding(client, db):
    """Four lines on one SO: (a) fully transferred and CLOSED, (b) half transferred
    and OPEN, (c) untouched and OPEN, (d) CANCELLED. `ordered = confirmed +
    outstanding` for both value and quantity; the cancelled line contributes to
    NOTHING; the half line's confirmed value is half its `line_total`."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _lines_on_one_so(
        db,
        product_id=prod.id,
        order_date=date(2026, 6, 15),
        lines=[
            {"ordered": 10, "delivered": 10, "line_total": Decimal("100.00"), "line_status": "closed"},
            {"ordered": 10, "delivered": 5, "line_total": Decimal("200.00"), "line_status": "open"},
            {"ordered": 4, "delivered": 0, "line_total": Decimal("40.00"), "line_status": "open"},
            {"ordered": 9, "delivered": 0, "line_total": Decimal("90.00"), "line_status": "cancelled"},
        ],
    )
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["months"]) == 1, body["months"]
    month = body["months"][0]
    assert month["month"] == "2026-06", month
    assert month["ordered_qty"] == 24, month
    assert month["confirmed_qty"] == 15, month
    assert month["outstanding_qty"] == 9, month
    assert month["ordered_qty"] == month["confirmed_qty"] + month["outstanding_qty"], month
    assert _money(month["ordered_value"]) == Decimal("340.00"), month
    assert _money(month["confirmed_value"]) == Decimal("200.00"), month
    assert _money(month["outstanding_value"]) == Decimal("140.00"), month
    assert _money(month["ordered_value"]) == _money(month["confirmed_value"]) + _money(month["outstanding_value"])


# --------------------------------------------------------------------- AC-1621


def test_over_delivered_capped_and_zero_qty_safe(client, db):
    """`qty_delivered > qty_ordered` contributes `qty_ordered` to confirmed, never
    more; `qty_ordered = 0` contributes 0 everywhere and does not raise (HTTP 200)."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _so_line(
        db, product_id=prod.id, ordered=5, delivered=7, line_total=Decimal("50.00"),
        order_date=date(2026, 6, 1),
    )
    _so_line(
        db, product_id=prod.id, ordered=0, delivered=0, line_total=Decimal("0.00"),
        order_date=date(2026, 6, 1),
    )
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code})
    assert resp.status_code == 200, resp.text
    month = resp.json()["months"][0]
    assert month["confirmed_qty"] == 5, month
    assert _money(month["confirmed_value"]) == Decimal("50.00"), month
    assert month["outstanding_qty"] == 0, month
    assert month["ordered_qty"] == 5, month


# --------------------------------------------------------------------- AC-1622


def test_bucket_required_date_else_order_date(client, db):
    """A line is bucketed by `required_date`; a line with none by its SO's
    `order_date`. An SO dated in June with one line required in July lands one
    line in June's bucket and the other in July's."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _lines_on_one_so(
        db,
        product_id=prod.id,
        order_date=date(2026, 6, 20),
        so_number=unique_code("SO"),
        lines=[
            {"ordered": 7, "delivered": 0, "line_total": Decimal("70.00"), "required_date": date(2026, 7, 10)},
            {"ordered": 3, "delivered": 0, "line_total": Decimal("30.00"), "required_date": None},
        ],
    )
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code})
    assert resp.status_code == 200, resp.text
    by_month = {m["month"]: m for m in resp.json()["months"]}
    assert set(by_month) == {"2026-06", "2026-07"}, by_month
    assert by_month["2026-07"]["ordered_qty"] == 7, by_month
    assert by_month["2026-06"]["ordered_qty"] == 3, by_month


def test_so_counts_in_each_month_it_has_lines(client, db):
    """The SAME SO counts 1 in June's `so_count` AND 1 in July's, since it has a
    live line bucketed into each."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _lines_on_one_so(
        db,
        product_id=prod.id,
        order_date=date(2026, 6, 20),
        so_number=unique_code("SO"),
        lines=[
            {"ordered": 7, "delivered": 0, "line_total": Decimal("70.00"), "required_date": date(2026, 7, 10)},
            {"ordered": 3, "delivered": 0, "line_total": Decimal("30.00"), "required_date": None},
        ],
    )
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code})
    assert resp.status_code == 200, resp.text
    by_month = {m["month"]: m for m in resp.json()["months"]}
    assert by_month["2026-06"]["so_count"] == 1, by_month
    assert by_month["2026-07"]["so_count"] == 1, by_month


# --------------------------------------------------------------------- AC-1623


def test_date_window_on_bucket_date(client, db):
    """`date_from`/`date_to` filter on the SAME bucket date (required date, else
    order date): a 2026-07 window keeps only the July-bucketed line, excluding the
    June-bucketed line of the SAME SO. A month-only `2026-07` input for both
    bounds gives the identical result."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _lines_on_one_so(
        db,
        product_id=prod.id,
        order_date=date(2026, 6, 20),
        so_number=unique_code("SO"),
        lines=[
            {"ordered": 7, "delivered": 0, "line_total": Decimal("70.00"), "required_date": date(2026, 7, 10)},
            {"ordered": 3, "delivered": 0, "line_total": Decimal("30.00"), "required_date": None},
        ],
    )
    db.commit()

    resp = client.get(
        BASE,
        params={"product_code": prod.product_code, "date_from": "2026-07-01", "date_to": "2026-07-31"},
    )
    assert resp.status_code == 200, resp.text
    months = resp.json()["months"]
    assert [m["month"] for m in months] == ["2026-07"], months
    assert months[0]["ordered_qty"] == 7, months

    month_only = client.get(
        BASE, params={"product_code": prod.product_code, "date_from": "2026-07", "date_to": "2026-07"}
    )
    assert month_only.status_code == 200, month_only.text
    mo_months = month_only.json()["months"]
    assert [m["month"] for m in mo_months] == ["2026-07"], mo_months
    assert mo_months[0]["ordered_qty"] == 7, mo_months


def test_bad_date_422(client, db):
    """An unrecognised `date_from` is 422 (`_parse_flex_date`'s own error). With no
    dates at all, every month is returned."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _so_line(
        db, product_id=prod.id, ordered=1, delivered=0, line_total=Decimal("10.00"),
        order_date=date(2026, 6, 1),
    )
    db.commit()

    bad = client.get(BASE, params={"product_code": prod.product_code, "date_from": "notadate"})
    assert bad.status_code == 422, bad.text

    unfiltered = client.get(BASE, params={"product_code": prod.product_code})
    assert unfiltered.status_code == 200, unfiltered.text
    assert len(unfiltered.json()["months"]) == 1, unfiltered.json()


# --------------------------------------------------------------------- AC-1624


def test_months_latest_first_and_breakdown_ranked_and_tallies(client, db):
    """`months[]` arrives latest first. Within a month, `by_product` (the
    customer-subject breakdown, per S6/AC-1628) ranks by `ordered_value`
    descending, ties by `ordered_qty` descending, then `product_code` ascending.
    Every breakdown row sums to its month's totals, value and quantity."""
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name=unique_code("Cust"))
    prod_a = product(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SR-PA")
    prod_b = product(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SR-PB")
    prod_c = product(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SR-PC")
    prod_d1 = product(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SR-PD1")
    prod_d2 = product(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SR-PD2")
    prod_f = product(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SR-PF")

    # 2026-08: a clean top, a value tie broken by quantity, a full tie broken by code.
    _so_line(
        db, product_id=prod_a.id, ordered=10, delivered=0, line_total=Decimal("100.00"),
        customer_id=cust.id, order_date=date(2026, 8, 1),
    )
    _so_line(
        db, product_id=prod_b.id, ordered=60, delivered=0, line_total=Decimal("50.00"),
        customer_id=cust.id, order_date=date(2026, 8, 1),
    )
    _so_line(
        db, product_id=prod_c.id, ordered=40, delivered=0, line_total=Decimal("50.00"),
        customer_id=cust.id, order_date=date(2026, 8, 1),
    )
    _so_line(
        db, product_id=prod_d1.id, ordered=30, delivered=0, line_total=Decimal("30.00"),
        customer_id=cust.id, order_date=date(2026, 8, 1),
    )
    _so_line(
        db, product_id=prod_d2.id, ordered=30, delivered=0, line_total=Decimal("30.00"),
        customer_id=cust.id, order_date=date(2026, 8, 1),
    )
    # An earlier month, to prove months[] sorts latest first.
    _so_line(
        db, product_id=prod_f.id, ordered=5, delivered=0, line_total=Decimal("20.00"),
        customer_id=cust.id, order_date=date(2026, 7, 1),
    )
    db.commit()

    resp = client.get(BASE, params={"customer_ids": cust.id})
    assert resp.status_code == 200, resp.text
    months = resp.json()["months"]
    assert [m["month"] for m in months] == ["2026-08", "2026-07"], months

    aug = months[0]
    ranked = [r["product_code"] for r in aug["by_product"]]
    assert ranked == [
        prod_a.product_code, prod_b.product_code, prod_c.product_code,
        prod_d1.product_code, prod_d2.product_code,
    ], aug["by_product"]

    for figure in ("ordered_qty", "confirmed_qty", "outstanding_qty"):
        assert sum(r[figure] for r in aug["by_product"]) == aug[figure], (figure, aug)
    for figure in ("ordered_value", "confirmed_value", "outstanding_value"):
        total = sum((_money(r[figure]) for r in aug["by_product"]), Decimal("0"))
        assert total == _money(aug[figure]), (figure, aug)


# --------------------------------------------------------------------- AC-1625


def test_channel_filter(client, db):
    """`channel=dealer` counts only `demand_class='retail'` SOs, `channel=project`
    only `'project'`; no channel counts all three including the null-class SO;
    `dealer` excludes the null one; any other value is 422. The response echoes
    `channel`."""
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name=unique_code("Cust"))
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _so_line(
        db, product_id=prod.id, ordered=10, delivered=0, line_total=Decimal("10.00"),
        customer_id=cust.id, order_date=date(2026, 5, 1), demand_class="retail",
    )
    _so_line(
        db, product_id=prod.id, ordered=20, delivered=0, line_total=Decimal("20.00"),
        customer_id=cust.id, order_date=date(2026, 5, 1), demand_class="project",
    )
    _so_line(
        db, product_id=prod.id, ordered=30, delivered=0, line_total=Decimal("30.00"),
        customer_id=cust.id, order_date=date(2026, 5, 1), demand_class=None,
    )
    db.commit()

    dealer = client.get(BASE, params={"customer_ids": cust.id, "channel": "dealer"})
    assert dealer.status_code == 200, dealer.text
    dbody = dealer.json()
    assert dbody["months"][0]["ordered_qty"] == 10, dbody  # retail only, null excluded
    assert dbody["channel"] == "dealer", dbody

    project = client.get(BASE, params={"customer_ids": cust.id, "channel": "project"})
    assert project.status_code == 200, project.text
    pbody = project.json()
    assert pbody["months"][0]["ordered_qty"] == 20, pbody
    assert pbody["channel"] == "project", pbody

    no_channel = client.get(BASE, params={"customer_ids": cust.id})
    assert no_channel.status_code == 200, no_channel.text
    nbody = no_channel.json()
    assert nbody["months"][0]["ordered_qty"] == 60, nbody  # 10 + 20 + 30, null-class included
    assert nbody.get("channel") is None, nbody

    bad = client.get(BASE, params={"customer_ids": cust.id, "channel": "wholesale"})
    assert bad.status_code == 422, bad.text


# --------------------------------------------------------------------- AC-1626


def test_subject_required(client, db):
    """Neither `product_code` nor `customer_ids` nor `customer_query` is 422
    `subject_required`. Product only, customer only and both each return 200."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name=unique_code("Cust"))
    _so_line(
        db, product_id=prod.id, ordered=1, delivered=0, line_total=Decimal("10.00"),
        customer_id=cust.id, order_date=date(2026, 6, 1),
    )
    db.commit()

    neither = client.get(BASE, params={})
    assert neither.status_code == 422, neither.text
    assert "subject_required" in neither.text, neither.text

    product_only = client.get(BASE, params={"product_code": prod.product_code})
    assert product_only.status_code == 200, product_only.text

    customer_only = client.get(BASE, params={"customer_ids": cust.id})
    assert customer_only.status_code == 200, customer_only.text

    both = client.get(BASE, params={"product_code": prod.product_code, "customer_ids": cust.id})
    assert both.status_code == 200, both.text


# --------------------------------------------------------------------- AC-1627


def test_product_exact_and_warehouse_filter(client, db):
    """`product_code=abc1` (lowercase) matches `ABC1` case-insensitively but NEVER
    the sibling `ABC10`. `warehouse_codes` filters lines to those exact codes."""
    w1_code = "ZZT-SR-W1"
    target = product(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-ABC1")
    sibling = product(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-ABC10")
    wh1 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=w1_code)
    wh2 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SR-W2")

    _so_line(
        db, product_id=target.id, ordered=10, delivered=0, line_total=Decimal("100.00"),
        warehouse_id=wh1.id, order_date=date(2026, 6, 1),
    )
    _so_line(
        db, product_id=target.id, ordered=20, delivered=0, line_total=Decimal("200.00"),
        warehouse_id=wh2.id, order_date=date(2026, 6, 1),
    )
    _so_line(
        db, product_id=sibling.id, ordered=99, delivered=0, line_total=Decimal("990.00"),
        warehouse_id=wh1.id, order_date=date(2026, 6, 1),
    )
    db.commit()

    unfiltered = client.get(BASE, params={"product_code": "zzt-abc1"})
    assert unfiltered.status_code == 200, unfiltered.text
    ubody = unfiltered.json()
    assert ubody["product_code"] == "ZZT-ABC1", ubody
    assert sum(m["ordered_qty"] for m in ubody["months"]) == 30, ubody  # 10 + 20, sibling excluded

    filtered = client.get(BASE, params={"product_code": "zzt-abc1", "warehouse_codes": w1_code})
    assert filtered.status_code == 200, filtered.text
    fbody = filtered.json()
    assert sum(m["ordered_qty"] for m in fbody["months"]) == 10, fbody


# --------------------------------------------------------------------- AC-1628


def test_breakdown_key_follows_subject(client, db):
    """Customer subject carries `by_product` and never `by_customer`; product
    subject carries `by_customer` and never `by_product`; both named carries
    neither key at all (R13's rule, ported from the outstanding report)."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name=unique_code("Cust"))
    _so_line(
        db, product_id=prod.id, ordered=10, delivered=0, line_total=Decimal("100.00"),
        customer_id=cust.id, order_date=date(2026, 6, 1),
    )
    db.commit()

    customer_subject = client.get(BASE, params={"customer_ids": cust.id})
    assert customer_subject.status_code == 200, customer_subject.text
    cs_month = customer_subject.json()["months"][0]
    assert "by_product" in cs_month, cs_month
    assert "by_customer" not in cs_month, cs_month

    product_subject = client.get(BASE, params={"product_code": prod.product_code})
    assert product_subject.status_code == 200, product_subject.text
    ps_month = product_subject.json()["months"][0]
    assert "by_customer" in ps_month, ps_month
    assert "by_product" not in ps_month, ps_month

    both_subject = client.get(
        BASE, params={"product_code": prod.product_code, "customer_ids": cust.id}
    )
    assert both_subject.status_code == 200, both_subject.text
    both_month = both_subject.json()["months"][0]
    assert "by_customer" not in both_month, both_month
    assert "by_product" not in both_month, both_month


# --------------------------------------------------------------------- AC-1629


def test_detail_rows_roll_up_sorted_and_tally(client, db):
    """`detail=so` returns `so_rows[]`, one row per SO with its lines rolled up
    over the WHOLE filtered window: `so_number`, `customer_name`, `location`
    (distinct warehouse codes comma-joined), `order_date`, and the six figures.
    Sorted `order_date` descending, ties by `so_number` descending, NULL
    `order_date` last. Row sums equal the sum of the months.

    Ambiguity flagged to the captain (see this file's final assertion below):
    the PLAN's contract table reads "detail: so -> adds so_rows[]", which this
    test takes to mean the key is ABSENT without `detail=so` - unlike
    `outstanding-report`, where `so_rows`/`do_rows` are ALWAYS present (an
    echo-only directive there, per that route's own docstring). If the coder's
    shape instead always includes `so_rows` (empty list without `detail`), that
    is the outstanding-report precedent winning over the plan's literal wording
    and should be confirmed with the captain, not silently changed here.
    """
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    wh1 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SR-DTL-W1")
    wh2 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SR-DTL-W2")
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT SR Rollup Customer")

    _lines_on_one_so(
        db, product_id=prod.id, customer_id=cust.id, order_date=date(2026, 6, 10),
        so_number="ZZT-SR-SO-MID",
        lines=[
            {"ordered": 10, "delivered": 0, "line_total": Decimal("100.00"), "warehouse_id": wh1.id},
            {"ordered": 5, "delivered": 0, "line_total": Decimal("50.00"), "warehouse_id": wh2.id},
        ],
    )
    _lines_on_one_so(
        db, product_id=prod.id, customer_id=cust.id, order_date=date(2026, 7, 5),
        so_number="ZZT-SR-SO-LATEST",
        lines=[{"ordered": 8, "delivered": 8, "line_total": Decimal("80.00"), "warehouse_id": wh1.id}],
    )
    # No header order_date at all - must sort LAST. Its line still carries a real
    # required_date so it lands in a defined month bucket ("2026-05"), keeping
    # the tally identity below clear of undefined "null bucket" behaviour.
    _lines_on_one_so(
        db, product_id=prod.id, customer_id=cust.id, order_date=None,
        so_number="ZZT-SR-SO-UNDATED",
        lines=[
            {
                "ordered": 3, "delivered": 0, "line_total": Decimal("30.00"),
                "warehouse_id": wh1.id, "required_date": date(2026, 5, 1),
            }
        ],
    )
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code, "detail": "so"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["so_rows"]
    assert [r["so_number"] for r in rows] == [
        "ZZT-SR-SO-LATEST", "ZZT-SR-SO-MID", "ZZT-SR-SO-UNDATED",
    ], rows

    latest_row = rows[0]
    assert latest_row["customer_name"] == "ZZT SR Rollup Customer", latest_row
    assert latest_row["ordered_qty"] == 8, latest_row
    assert latest_row["confirmed_qty"] == 8, latest_row
    assert latest_row["outstanding_qty"] == 0, latest_row
    assert _money(latest_row["ordered_value"]) == Decimal("80.00"), latest_row
    assert _money(latest_row["confirmed_value"]) == Decimal("80.00"), latest_row
    assert _money(latest_row["outstanding_value"]) == Decimal("0.00"), latest_row
    assert set(latest_row["location"].split(", ")) == {"ZZT-SR-DTL-W1"}, latest_row

    mid_row = rows[1]
    assert mid_row["ordered_qty"] == 15, mid_row
    assert mid_row["confirmed_qty"] == 0, mid_row
    assert mid_row["outstanding_qty"] == 15, mid_row
    assert _money(mid_row["ordered_value"]) == Decimal("150.00"), mid_row
    assert set(mid_row["location"].split(", ")) == {"ZZT-SR-DTL-W1", "ZZT-SR-DTL-W2"}, mid_row

    undated_row = rows[2]
    assert undated_row["order_date"] is None, undated_row
    assert undated_row["ordered_qty"] == 3, undated_row
    assert _money(undated_row["ordered_value"]) == Decimal("30.00"), undated_row

    for figure in ("ordered_qty", "confirmed_qty", "outstanding_qty"):
        assert sum(r[figure] for r in rows) == sum(m[figure] for m in body["months"]), figure
    for figure in ("ordered_value", "confirmed_value", "outstanding_value"):
        row_total = sum((_money(r[figure]) for r in rows), Decimal("0"))
        month_total = sum((_money(m[figure]) for m in body["months"]), Decimal("0"))
        assert row_total == month_total, figure

    no_detail = client.get(BASE, params={"product_code": prod.product_code})
    assert no_detail.status_code == 200, no_detail.text
    assert "so_rows" not in no_detail.json(), (
        "Reading the PLAN's contract table literally (detail=so ADDS so_rows[]): "
        "the key must be ABSENT without detail=so. This is the one place this "
        "file made a call the plan left ambiguous - see this test's docstring: "
        + str(no_detail.json())
    )


# --------------------------------------------------------------------- R-B2
# reviewer finding, Phase 3 fix round: the outstanding-report route echoes its
# own `detail` query param onto the response body (`if detail in ("so", "do"):
# body["detail"] = detail`, right before its own `return JSONResponse(...)`) so
# the MCP presenter can tell a month-block body from a detail body without
# re-deriving it from `so_rows`'s mere presence. `get_sales_report` never does
# this - `so_rows`/`detail` are both silently dropped from the echo, so the
# presenter has no wire signal at all for which shape it was handed.


def test_detail_so_is_echoed_on_the_body(client, db):
    """`detail=so` echoes `"detail": "so"` onto the body; without `detail` the
    key is absent entirely (never `null`) - the same "declared but present only
    when asked" contract `so_rows` already gets on this response."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _so_line(
        db, product_id=prod.id, ordered=1, delivered=0, line_total=Decimal("10.00"),
        order_date=date(2026, 6, 1),
    )
    db.commit()

    with_detail = client.get(BASE, params={"product_code": prod.product_code, "detail": "so"})
    assert with_detail.status_code == 200, with_detail.text
    assert with_detail.json().get("detail") == "so", with_detail.json()

    without_detail = client.get(BASE, params={"product_code": prod.product_code})
    assert without_detail.status_code == 200, without_detail.text
    assert "detail" not in without_detail.json(), without_detail.json()


def test_a_real_so_detail_body_renders_through_the_real_presenter(client, db):
    """R-B2's end-to-end seam (this file's own choice - it needs the real HTTP
    route, which only the backend TestClient can call): a REAL route body
    obtained with `detail=so` (not a hand-set key, unlike
    `test_catalog_sales_report.py`'s own pure-presenter test at its lines
    90-93, whose `body["detail"] = "so"` is a deliberate hand-set kept there
    for a presenter-only unit test - noted in ITS docstring too) fed through
    `sorento_crm_mcp.presenters.present_response("crm_sales_report", ...)` must
    render the SO detail text, not the month-block text: `*SO Number:*` present,
    `*_By product_*` absent. This only ever renders correctly once the route
    echoes `detail` (R-B2 above) - `present_response`'s own dispatcher reads
    `data.get("detail") == "so"` to choose `_sales_report_detail` over
    `_sales_report` (S3, already wired)."""
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    mcp_root = repo_root / "sorento_crm_mcp"
    if str(mcp_root) not in sys.path:
        sys.path.append(str(mcp_root))
    try:
        from sorento_crm_mcp.presenters import present_response
    except ImportError:  # pragma: no cover - only where the package is not on disk
        pytest.skip("sorento_crm_mcp is not importable in this environment")

    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT SR Presenter Customer")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _so_line(
        db, product_id=prod.id, ordered=10, delivered=4, line_total=Decimal("100.00"),
        customer_id=cust.id, order_date=date(2026, 6, 1), so_number="ZZT-SR-PRESENTER-SO",
    )
    db.commit()

    resp = client.get(BASE, params={"customer_ids": cust.id, "detail": "so"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("detail") == "so", (
        "the route must echo detail=so (R-B2) before the presenter has any wire "
        f"signal to dispatch on: {body}"
    )

    rendered = present_response("crm_sales_report", resp.text)
    import json as _json

    envelope = _json.loads(rendered)
    text = envelope.get("response") or ""
    assert "*SO Number:*" in text, (
        f"a real detail=so body must render through the detail presenter, not the "
        f"month-block one: {text!r}"
    )
    assert "*_By product_*" not in text, text


# --------------------------------------------------------------------- AC-1630


def test_customer_echo_shared(client, db):
    """The header echo `customer_name` is built by the outstanding report's own
    `_customer_echo` (distinct ledger names, first-seen order) - imported, not
    reimplemented."""
    c1 = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT SR Echo One")
    c2 = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT SR Echo Two")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _so_line(
        db, product_id=prod.id, ordered=1, delivered=0, line_total=Decimal("10.00"),
        customer_id=c1.id, order_date=date(2026, 6, 1),
    )
    db.commit()

    ids = f"{c1.id},{c2.id}"
    resp = client.get(BASE, params={"customer_ids": ids})
    assert resp.status_code == 200, resp.text
    expected = _customer_echo(db, None, [c1.id, c2.id])
    assert expected == "ZZT SR Echo One, ZZT SR Echo Two", expected
    assert resp.json()["customer_name"] == expected, resp.json()


# --------------------------------------------------------------------- AC-1631


def test_response_model_keeps_every_field(client, db):
    """Every field of the response is declared and present through the HTTP
    route (`response_model` silently drops undeclared fields - LESSONS-LEARNT.md).
    `location_token` echoes the raw param and never filters."""
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-SR-FIELD-W1")
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT SR Field Customer")
    _so_line(
        db, product_id=prod.id, ordered=10, delivered=2, line_total=Decimal("100.00"),
        customer_id=cust.id, warehouse_id=wh.id, order_date=date(2026, 6, 1),
    )
    db.commit()

    resp = client.get(
        BASE,
        params={
            "product_code": prod.product_code,
            "location_token": "ZZT-NOT-A-REAL-WAREHOUSE",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in (
        "customer_name", "product_code", "channel", "location_token",
        "warehouse_codes", "date_from", "date_to", "months",
    ):
        assert key in body, f"missing field: {key}"
    assert body["location_token"] == "ZZT-NOT-A-REAL-WAREHOUSE", (
        "location_token echoes the raw param; it never filters (S9)"
    )
    assert len(body["months"]) == 1 and body["months"][0]["ordered_qty"] == 10, (
        f"an unmatched location_token must not have filtered the data away: {body}"
    )
    month = body["months"][0]
    for key in (
        "month", "so_count", "ordered_qty", "ordered_value",
        "confirmed_qty", "confirmed_value", "outstanding_qty", "outstanding_value",
    ):
        assert key in month, f"missing months[].{key}: {month}"


# --------------------------------------------------------------------- R-B4
# reviewer finding, Phase 3 fix round: AC-1620's own fixture mixes a cancelled
# LINE into a multi-line SO alongside open ones, and never isolates a whole
# CANCELLED SO on its own. This extends it with both cases on their own SOs -
# a cancelled line beside an open one on an OPEN header, and an open line
# under a CANCELLED header - so neither is masked by the other contributing
# something real to the same totals.


def test_cancelled_lines_and_cancelled_sos_never_count(client, db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _lines_on_one_so(
        db, product_id=prod.id, order_date=date(2026, 6, 1), so_number="ZZT-SR-CANCEL-OPEN",
        lines=[
            {"ordered": 5, "delivered": 2, "line_total": Decimal("50.00"), "line_status": "open"},
            {"ordered": 9, "delivered": 4, "line_total": Decimal("90.00"), "line_status": "cancelled"},
        ],
    )
    _lines_on_one_so(
        db, product_id=prod.id, order_date=date(2026, 6, 1), so_number="ZZT-SR-CANCEL-SO",
        header_status="cancelled",
        lines=[{"ordered": 6, "delivered": 6, "line_total": Decimal("60.00"), "line_status": "open"}],
    )
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code, "detail": "so"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["months"]) == 1, body["months"]
    month = body["months"][0]
    assert month["ordered_qty"] == 5, month
    assert month["confirmed_qty"] == 2, month
    assert month["outstanding_qty"] == 3, month
    assert _money(month["ordered_value"]) == Decimal("50.00"), month
    assert month["so_count"] == 1, (
        "the CANCELLED SO's own line must not count towards so_count at all", month,
    )
    so_numbers = [r["so_number"] for r in body["so_rows"]]
    assert so_numbers == ["ZZT-SR-CANCEL-OPEN"], (
        "neither the cancelled LINE nor the cancelled SO's line may surface in "
        f"so_rows: {so_numbers}"
    )


# --------------------------------------------------------------------- R-S3
# reviewer finding, Phase 3 fix round (captain ruling S15): the pro-rated
# confirmed value rounds to the cent PER LINE, and every total (month,
# breakdown, so_rows) is a SUM of those already-rounded cents - never an exact
# Decimal accumulated across many lines and rounded once at the end. The
# service today accumulates exact fractions (`_new_figures`/`_accumulate`) and
# only calls `_money_edge` once, at the very end, per aggregate
# (`_quantised_figures`) - so three lines whose exact confirmed value is
# 10/3 = 3.333... repeating sum to a total that rounds differently from three
# separately-rounded 3.33s.


def test_rounding_tallies_to_the_cent(client, db):
    """Three lines, one month, two products: qty 3 delivered 1 line_total
    10.00 each (10/3 = 3.333... repeating). Rounded PER LINE: confirmed 3.33,
    outstanding 6.67, each summed three times = 9.99 / 20.01 / 30.00. The
    CURRENT service instead accumulates the exact fraction across all three
    lines before rounding once, which rounds to 10.00 / 20.00 / 30.00 - the
    identity still holds arithmetically, but the CENTS ruling (S15) does not."""
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name=unique_code("Cust"))
    prod_a = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKUA"))
    prod_b = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKUB"))
    for prod in (prod_a, prod_a, prod_b):
        _so_line(
            db, product_id=prod.id, ordered=3, delivered=1, line_total=Decimal("10.00"),
            customer_id=cust.id, order_date=date(2026, 6, 1),
        )
    db.commit()

    resp = client.get(BASE, params={"customer_ids": cust.id})
    assert resp.status_code == 200, resp.text
    month = resp.json()["months"][0]
    assert _money(month["confirmed_value"]) == Decimal("9.99"), month
    assert _money(month["outstanding_value"]) == Decimal("20.01"), month
    assert _money(month["ordered_value"]) == Decimal("30.00"), month

    for figure in ("ordered_value", "confirmed_value", "outstanding_value"):
        total = sum((_money(r[figure]) for r in month["by_product"]), Decimal("0"))
        assert total == _money(month[figure]), (figure, month["by_product"], month)

    detail = client.get(BASE, params={"customer_ids": cust.id, "detail": "so"})
    assert detail.status_code == 200, detail.text
    dbody = detail.json()
    for figure in ("ordered_value", "confirmed_value", "outstanding_value"):
        row_total = sum((_money(r[figure]) for r in dbody["so_rows"]), Decimal("0"))
        month_total = sum((_money(m[figure]) for m in dbody["months"]), Decimal("0"))
        assert row_total == month_total, (figure, dbody["so_rows"], dbody["months"])


# --------------------------------------------------------------------- R-S2
# reviewer finding, Phase 3 fix round (captain ruling S16): a line with NEITHER
# `required_date` NOR its SO's `order_date` is excluded from EVERYTHING - the
# service's own module docstring already states this as the intended rule
# ("A line with no bucket at all... cannot be placed in any month, so it is
# excluded from EVERYTHING"), but the code falls back a THIRD time to the SO's
# `created_at` (`bucket_date = r.required_date or r.order_date or
# r.created_at.date()`), so such a line is never actually excluded - it lands
# in whatever month `created_at` (today, at seed time) falls in instead.


def test_a_line_with_no_dates_is_excluded_everywhere(client, db):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _lines_on_one_so(
        db, product_id=prod.id, order_date=None, so_number="ZZT-SR-NO-DATE-SO",
        lines=[
            {"ordered": 4, "delivered": 0, "line_total": Decimal("40.00"), "required_date": None},
            # A sibling line on the SAME SO with a real bucket, so the SO itself is not
            # absent from the response - only the undated LINE must be missing.
            {"ordered": 2, "delivered": 0, "line_total": Decimal("20.00"), "required_date": date(2026, 6, 1)},
        ],
    )
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code, "detail": "so"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["months"]) == 1, body["months"]
    month = body["months"][0]
    assert month["month"] == "2026-06", month
    assert month["ordered_qty"] == 2, (
        "the undated line (qty 4) must not land in ANY month, including the "
        f"one its SO's sibling line and its own created_at share: {month}"
    )
    row = next(r for r in body["so_rows"] if r["so_number"] == "ZZT-SR-NO-DATE-SO")
    assert row["ordered_qty"] == 2, (
        "the undated line must not surface in so_rows either - a row sum that "
        f"included it would silently disagree with the month total: {row}"
    )

    windowed = client.get(
        BASE,
        params={
            "product_code": prod.product_code, "detail": "so",
            "date_from": "1900-01-01", "date_to": "2100-01-01",
        },
    )
    assert windowed.status_code == 200, windowed.text
    wrow = next(r for r in windowed.json()["so_rows"] if r["so_number"] == "ZZT-SR-NO-DATE-SO")
    assert wrow["ordered_qty"] == 2, (
        "an all-encompassing window must not surface the undated line under "
        f"today's created_at either: {wrow}"
    )


# --------------------------------------------------------------------- SEC-B2
# security review, Phase 3 fix round (captain ruling S17): `customer_query`
# needs at least 3 characters (after strip) - the route today only checks it
# is non-empty (`subject_required`), so a single letter ILIKE scans and returns
# every customer whose name contains it, company-wide.


@pytest.mark.parametrize("query", ["a", "ab", " a "])
def test_customer_query_needs_three_characters(client, db, query):
    """A WHOLLY BLANK query ("  ") is deliberately excluded from this
    parametrization: it strips to "" and already 422s as `subject_required`
    (no subject named at all) - a pre-existing, unrelated check this test must
    not conflate with the NEW minimum-length rule."""
    resp = client.get(BASE, params={"customer_query": query})
    assert resp.status_code == 422, (query, resp.text)


def test_customer_query_of_three_characters_is_accepted(client, db):
    resp = client.get(BASE, params={"customer_query": "abc"})
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------- SEC-B2
# security review, Phase 3 fix round: the report is rolled up from raw ROWS in
# Python (`sales_report_service.py`'s own module docstring: "ONE base query...
# everything else... is rolled up from that SAME result set in Python"). For a
# big dealer (HANLIM: ~80 products/month over 37 months, UAC "Measured") that
# is thousands of rows read into the request process for one WhatsApp reply.
# This does not (and, honestly, cannot from outside the service without
# instrumenting row-fetch counts) prove Python never sees a raw row - it proves
# the report's OWN SELECT never aggregates in SQL (no GROUP BY at all), which
# is the necessary condition for "rolled up in Python" to be true, and is the
# strongest assertion available without a fetch-counting cursor wrapper. See
# the report to the captain for what this test does and does not prove.


def test_report_is_aggregated_in_sql(client, db):
    from sqlalchemy import event

    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name=unique_code("Cust"))
    prods = [product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code(f"SKU{i}")) for i in range(2)]
    for i in range(40):
        _so_line(
            db, product_id=prods[i % 2].id, ordered=1, delivered=0, line_total=Decimal("10.00"),
            customer_id=cust.id, order_date=date(2026, 6, 1),
        )
    db.commit()

    connection = db.get_bind()
    calls: list[str] = []

    def _capture(conn, cursor, statement, *_a, **_kw):
        if statement.strip().upper().startswith("SELECT"):
            calls.append(statement)

    event.listen(connection, "before_cursor_execute", _capture)
    try:
        resp = client.get(BASE, params={"customer_ids": cust.id})
    finally:
        event.remove(connection, "before_cursor_execute", _capture)
    assert resp.status_code == 200, resp.text

    report_calls = [c for c in calls if "sales_order_lines" in c.lower()]
    assert report_calls, "no SELECT touched sales_order_lines at all"
    assert any("group by" in c.lower() for c in report_calls), (
        "the report's own SELECT never aggregates in SQL - it reads every raw "
        f"line into Python instead: {report_calls}"
    )


# --------------------------------------------------------------------- SEC-S1
# security review, Phase 3 fix round (captain ruling S14): the route re-checks
# the per-contact `sales_orders.sales_report` reveal key WHEN a contact_id is
# present - unlike the outstanding-report route, which only ever has the LANE
# withhold scope (`so_refused`), this route has no such caller today at all:
# an n8n workflow or a console session calling the MCP tool directly with a
# contact's own contact_id/space_id bypasses the chatbot lane's own gate
# entirely (`lanes/business/__init__.py`'s `_SALES_REPORT_GRANT` check), so the
# only gate that ever runs is the route's - and today there is none.


def test_contact_without_the_key_is_refused_by_the_route(client, db):
    from app.services.contact_field_reveal_service import set_granted_keys

    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _so_line(
        db, product_id=prod.id, ordered=1, delivered=0, line_total=Decimal("10.00"),
        order_date=date(2026, 6, 1),
    )
    contact = RespondContact(id=str(uuid.uuid4()), phone_number=f"+6{unique_code('PH')[:10]}")
    db.add(contact)
    db.flush()
    db.add(
        RespondContactCompany(
            id=str(uuid.uuid4()), respond_contact_id=contact.id, company_id=DEFAULT_COMPANY_ID,
        )
    )
    db.commit()

    refused = client.get(
        BASE,
        params={"product_code": prod.product_code, "contact_id": contact.id, "space_id": "zzt-space"},
    )
    assert refused.status_code == 403, refused.text
    assert "sales_report_not_enabled" in refused.text, refused.text

    set_granted_keys(db, contact.id, ["sales_orders.sales_report"], actor_id=None)
    db.commit()

    granted = client.get(
        BASE,
        params={"product_code": prod.product_code, "contact_id": contact.id, "space_id": "zzt-space"},
    )
    assert granted.status_code == 200, granted.text

    plain = client.get(BASE, params={"product_code": prod.product_code})
    assert plain.status_code == 200, plain.text


# --------------------------------------------------------------------- SEC-S2
# security review, Phase 3 fix round (captain ruling S14): contact_id and
# space_id are both-or-neither on THIS route - one without the other is 422,
# never silently treated as "no contact at all" (which would skip the SEC-S1
# gate above entirely) or as "no space at all" (which the generic company-scope
# resolver already treats as neither given, per its own `if not contact_id or
# not space_id: return` - the SAME silent-skip this route's own reveal gate
# must not inherit).


@pytest.mark.parametrize(
    "params",
    [
        {"contact_id": "11111111-1111-1111-1111-111111111111"},
        {"space_id": "zzt-space"},
    ],
)
def test_contact_identity_is_both_or_neither(client, db, params):
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _so_line(db, product_id=prod.id, ordered=1, delivered=0, line_total=Decimal("10.00"))
    db.commit()

    resp = client.get(BASE, params={"product_code": prod.product_code, **params})
    assert resp.status_code == 422, (params, resp.text)


# --------------------------------------------------------------------- SEC-B1
# security review, Phase 3 fix round (captain ruling): AC-1642 struck - the
# in-app AI assistant must NEVER carry `crm_sales_report` on its enabled tools
# list, the same reason `crm_low_stock_report` is kept off it (N4, app/main.py,
# above): a staff member who is 403 on the ROUTE (no
# order_management.orders.view permission) could otherwise read the money
# figures through the in-app assistant instead, across every company - the
# assistant is a DIFFERENT auth boundary from the route's RBAC permission.


def test_sales_report_is_not_enabled_for_the_in_app_assistant():
    import importlib
    from pathlib import Path

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.services.sales_report_bootstrap")

    import app.main as main_mod

    source = Path(main_mod.__file__).read_text()
    assert "sales_report_bootstrap" not in source, (
        "app/main.py must not wire the struck bootstrap at all (AC-1642 STRUCK)"
    )


# --------------------------------------------------------------------- AC-1632


def test_auth_401_403_apikey_and_company_scope(db, monkeypatch):
    """No credential is 401; a user without `order_management.orders.view` is
    403; an X-API-Key principal with an act-as user who HOLDS the grant reaches
    the route (200). Separately, with the REAL `apply_company_scope` resolver
    running (not the `client` fixture's override), a contact-scoped API key
    sees only its OWN company's sales orders - mirrors
    test_outstanding_report.py's AC-1118 (`test_route_permission_and_api_key_act_as`)
    and B1 (`test_report_is_company_scoped_for_api_key_contact`)."""
    from app.config import settings

    def _override_db():
        yield db

    async def _override_scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    prod = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("SKU"))
    _so_line(db, product_id=prod.id, ordered=1, delivered=0, line_total=Decimal("10.00"))

    no_grant_user = User(
        id=str(uuid.uuid4()), email=f"{unique_code('NG')}@test.com", name="ZZT No Grant", status="ACTIVE"
    )
    db.add(no_grant_user)
    db.flush()

    permission = UserPermission(id=str(uuid.uuid4()), slug=PERMISSION_SLUG, name=PERMISSION_SLUG)
    role = UserRole(id=str(uuid.uuid4()), slug="zzt_sales_report_view_role", name="ZZT Sales Report View")
    granted_user = User(
        id=str(uuid.uuid4()), email=f"{unique_code('OK')}@test.com", name="ZZT Granted", status="ACTIVE"
    )
    db.add_all([permission, role, granted_user])
    db.flush()
    db.add(UserRoleAssignment(user_id=granted_user.id, role_id=role.id))
    db.add(UserRolePermission(role_id=role.id, permission_id=permission.id))
    db.flush()

    integration = Integration(
        id=str(uuid.uuid4()), name="zzt-sales-report-key", type="automation",
        act_as_user_id=granted_user.id, is_active=True,
    )
    db.add(integration)
    db.flush()
    plaintext_key = IntegrationKeyService(db).issue_key(integration)
    db.commit()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        # No credential at all.
        no_cred_client = TestClient(app)
        no_cred = no_cred_client.get(BASE, params={"product_code": prod.product_code})
        assert no_cred.status_code == 401, no_cred.text

        # A real principal without the permission.
        app.dependency_overrides[get_current_user] = lambda: {"id": no_grant_user.id, "email": no_grant_user.email}
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {
            "id": no_grant_user.id, "email": no_grant_user.email
        }
        no_grant_client = TestClient(app)
        denied = no_grant_client.get(BASE, params={"product_code": prod.product_code})
        assert denied.status_code == 403, denied.text

        # X-API-Key + act-as: remove the override so the real key resolves.
        del app.dependency_overrides[get_current_user_or_api_key]
        del app.dependency_overrides[get_current_user]
        apikey_client = TestClient(app)
        allowed = apikey_client.get(
            BASE, params={"product_code": prod.product_code}, headers={"X-API-Key": plaintext_key}
        )
        assert allowed.status_code == 200, allowed.text
    finally:
        app.dependency_overrides.clear()

    # Company scoping: seed a SECOND company with the SAME product code and an
    # SO of its own, a contact scoped to ONLY the first company, and assert the
    # scoped caller never sees the other company's SO. The REAL
    # apply_company_scope resolver runs here (not overridden).
    mocha = seed_mocha(db)
    shared_code = unique_code("SKU2")
    prod_a = product(db, company_id=DEFAULT_COMPANY_ID, code=shared_code)
    prod_b = product(db, company_id=mocha.id, code=shared_code)

    # R-S2 (Phase 3 fix round, captain ruling S16): the created_at fallback is
    # REMOVED, so a line bucketed by neither required_date nor order_date is
    # now excluded from every total - this seed must carry a real order_date
    # or `total_ordered == 10` below would silently see 0 instead. Assertions
    # unchanged; only this seed's own date is added.
    _so_line(
        db, product_id=prod_a.id, ordered=10, delivered=0, line_total=Decimal("100.00"),
        order_date=date(2026, 6, 1),
    )
    so_b = SalesOrder(
        id=str(uuid.uuid4()), so_number=unique_code("SO"), status="open", company_id=mocha.id,
    )
    db.add(so_b)
    db.flush()
    db.add(
        SalesOrderLine(
            id=str(uuid.uuid4()), sales_order_id=so_b.id, product_id=prod_b.id,
            qty_ordered=500, qty_delivered=0, line_total=Decimal("5000.00"), line_status="open",
            company_id=mocha.id,
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
    # SEED CHANGED BY THE CODER (SEC-S1/ruling S14, Phase 3 fix round): this test's own
    # contact now carries the per-contact `sales_orders.sales_report` reveal key, or the
    # route's new SEC-S1 gate would refuse this AC-1118/B1-style company-scope check with
    # its own 403 before company scoping is ever exercised - no assertion below changed.
    from app.services.contact_field_reveal_service import set_granted_keys

    set_granted_keys(db, contact.id, ["sales_orders.sales_report"], actor_id=None)

    superadmin = _seed_superadmin(db)
    scope_integration = Integration(
        id=str(uuid.uuid4()), name="zzt-sales-report-scope-key", type="automation",
        act_as_user_id=superadmin["id"], is_active=True,
    )
    db.add(scope_integration)
    db.flush()
    scope_key = IntegrationKeyService(db).issue_key(scope_integration)
    db.commit()
    monkeypatch.setattr(settings, "external_api_key", scope_key)

    app.dependency_overrides[get_db] = _override_db
    try:
        scoped_client = TestClient(app)
        resp = scoped_client.get(
            BASE,
            params={"product_code": shared_code, "contact_id": contact.id, "space_id": "zzt-space"},
            headers={"X-API-Key": scope_key},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        total_ordered = sum(m["ordered_qty"] for m in body["months"])
        assert total_ordered == 10, (
            f"a Sorento-only contact must never see Mocha's SO lines: {body}"
        )
    finally:
        app.dependency_overrides.clear()
