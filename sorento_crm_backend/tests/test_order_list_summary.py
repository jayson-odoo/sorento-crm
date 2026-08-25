"""§QS-C1..C7 — `ListResponse.summary` on the two order lists
(`OrderService.list_orders`, `OrderService.list_orders_by_product`) and the
`order_status` bucket on the by-product path.

The contract under test (sorento_crm_n8n `plans/order-quantity-summary-plan.md` §3):
measures are computed over the WHOLE filter, never the page; delivered is the
canonical predicate (status delivered/completed AND actual_delivery_date set);
the summary exists only when the caller asks (`include_summary=True`; customer-only
asks get counts, product-scoped asks get quantities); absent-not-null everywhere; an empty result
carries no summary.

Postgres only, blank scratch schema (tests/_pg_fixture.blank_session) — so the
delivered statuses are seeded here, exactly as `_delivered_status_ids` reads them.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.base import set_company_scope
from app.models.order import OrderStatus
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.order_service import OrderService

from app.models.order import Order

from tests._mc_lookup_seed import (
    MOCHA_ID,
    customer,
    order,
    order_line,
    product,
    seed_mocha,
    warehouse,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        seed_mocha(session)
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
        # The scratch schema has no statuses; seed the canonical delivered pair
        # plus a non-delivered one, mirroring production's codes.
        for code, name, final in (
            ("NEW", "New Order", False),
            ("DELIVERED", "Picked Up / In Transit", True),
            ("COMPLETED", "Completed", True),
        ):
            session.add(OrderStatus(id=str(uuid.uuid4()), status_code=code, status_name=name,
                                    sequence=0, is_final_status=final))
        session.flush()
        yield session


def _status_id(db, code: str) -> str:
    return db.query(OrderStatus.id).filter(OrderStatus.status_code == code).scalar()


def _do(db, *, cust, prod, wh, qty, status_code, delivered_on: date | None, number=None,
        company_id: str = DEFAULT_COMPANY_ID):
    """One DO with one line of `qty` for `prod`."""
    o = order(db, company_id=company_id, customer_id=cust.id, number=number)
    o.debtor_name = cust.customer_name
    o.order_status_id = _status_id(db, status_code)
    o.actual_delivery_date = delivered_on
    o.order_date = datetime(2026, 1, 1)
    order_line(db, company_id=company_id, order_id=o.id, product_id=prod.id,
               warehouse_id=wh.id, quantity=qty)
    db.flush()
    return o


@pytest.fixture
def scenario(db):
    """The §QS-C1 seed: customer C, product P; 3 delivered DOs (10/20/18), one
    dated-but-NEW DO (12) and one undated DELIVERED-status DO (5)."""
    cust = customer(db, company_id=DEFAULT_COMPANY_ID, name="ECO WORLD SDN BHD")
    prod = product(db, company_id=DEFAULT_COMPANY_ID, code="SRTWC8605")
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    _do(db, cust=cust, prod=prod, wh=wh, qty=10, status_code="DELIVERED", delivered_on=date(2026, 3, 2))
    _do(db, cust=cust, prod=prod, wh=wh, qty=20, status_code="COMPLETED", delivered_on=date(2026, 5, 9))
    _do(db, cust=cust, prod=prod, wh=wh, qty=18, status_code="DELIVERED", delivered_on=date(2026, 7, 15))
    _do(db, cust=cust, prod=prod, wh=wh, qty=12, status_code="NEW", delivered_on=date(2026, 7, 20))  # dated, not delivered
    _do(db, cust=cust, prod=prod, wh=wh, qty=5, status_code="DELIVERED", delivered_on=None)           # status, no date
    db.commit()
    return cust, prod, wh


# ---------------------------------------------------------------- list_orders

def test_qs_c1_summary_is_filter_wide_and_canonically_delivered(db, scenario):
    cust, prod, _ = scenario
    result = OrderService(db).list_orders(include_summary=True, customer_ids=[cust.id], product_ids=[prod.id])

    s = result["summary"]
    assert s["scope"] == "filter"
    assert s["order_count"] == 5 and s["row_count"] == 5
    assert s["delivered_count"] == 3
    assert s["pending_count"] == 2
    assert s["customers"] == ["ECO WORLD SDN BHD"] and s["customer_count"] == 1
    assert s["delivered_from"] == "2026-03-02" and s["delivered_to"] == "2026-07-15"
    assert s["products"] == [
        {"product_code": "SRTWC8605", "order_count": 5, "delivered_quantity": 48, "pending_quantity": 17,
         "delivered_from": "2026-03-02", "delivered_to": "2026-07-15"}
    ]
    # integral quantities are ints, not "48.0000"
    assert isinstance(s["products"][0]["delivered_quantity"], int)
    # customer x product - the unit the question is about (captain 2026-08-25)
    assert s["groups"] == [
        {"customer": "ECO WORLD SDN BHD", "product_code": "SRTWC8605",
         "order_count": 5, "delivered_quantity": 48, "pending_quantity": 17,
         "delivered_from": "2026-03-02", "delivered_to": "2026-07-15"}
    ]
    assert "groups_truncated" not in s


def test_qs_c2_summary_ignores_the_page(db, scenario):
    cust, prod, _ = scenario
    svc = OrderService(db)
    full = svc.list_orders(include_summary=True, customer_ids=[cust.id], product_ids=[prod.id])
    paged = svc.list_orders(include_summary=True, customer_ids=[cust.id], product_ids=[prod.id], limit=2)

    assert len(paged["data"]) == 2
    assert paged["pagination"]["total"] == 5
    assert paged["summary"] == full["summary"]
    assert paged["summary"]["row_count"] == paged["pagination"]["total"]
    assert paged["summary"]["products"][0]["delivered_quantity"] == 48  # not the 2-row sum


def test_qs_c0_not_asked_means_no_summary_and_no_extra_work(db, scenario):
    """"Any delivery to Hanlim for SRTWC286" wants the DOs, not a headline. Without
    include_summary the reply is byte-identical to before and no aggregate runs
    (captain, 2026-08-25: the QUESTION FORM is the signal, not the filter)."""
    cust, prod, _ = scenario
    svc = OrderService(db)
    a = svc.list_orders(customer_ids=[cust.id], product_ids=[prod.id])
    b = svc.list_orders_by_product(product_ids=[prod.id], customer_ids=[cust.id])
    assert a["pagination"]["total"] == 5 and "summary" not in a
    assert b["pagination"]["total"] == 5 and "summary" not in b


def test_qs_c3_no_product_narrower_means_counts_only(db, scenario):
    """"How many DOs did Hanlim take?" - asked, but no product: counts and names, no
    per-product quantity (a sum across unrelated products is not a number)."""
    cust, _, _ = scenario
    result = OrderService(db).list_orders(customer_ids=[cust.id], include_summary=True)

    s = result["summary"]
    # amendment 4: the breakdown comes with every asked summary - per product, never across
    assert [p["product_code"] for p in s["products"]] == ["SRTWC8605"]
    assert s["products"][0]["delivered_quantity"] == 48
    assert [(g["customer"], g["product_code"]) for g in s["groups"]] == [("ECO WORLD SDN BHD", "SRTWC8605")]
    assert s["order_count"] == 5 and s["delivered_count"] == 3 and s["pending_count"] == 2


def test_qs_c4_two_customers_are_counted_and_named(db, scenario):
    cust, prod, wh = scenario
    other = customer(db, company_id=DEFAULT_COMPANY_ID, name="HANLIM TRADING SDN BHD")
    _do(db, cust=other, prod=prod, wh=wh, qty=7, status_code="DELIVERED", delivered_on=date(2026, 8, 1))
    db.commit()

    s = OrderService(db).list_orders(include_summary=True, product_ids=[prod.id])["summary"]
    assert s["customer_count"] == 2
    assert set(s["customers"]) == {"ECO WORLD SDN BHD", "HANLIM TRADING SDN BHD"}
    assert s["products"][0]["delivered_quantity"] == 55
    assert s["products"][0]["order_count"] == 6 and s["products"][0]["delivered_to"] == "2026-08-01"
    assert s["delivered_to"] == "2026-08-01"
    # per customer x product, sorted by customer - each customer sees only its own share and span
    assert s["groups"] == [
        {"customer": "ECO WORLD SDN BHD", "product_code": "SRTWC8605",
         "order_count": 5, "delivered_quantity": 48, "pending_quantity": 17,
         "delivered_from": "2026-03-02", "delivered_to": "2026-07-15"},
        {"customer": "HANLIM TRADING SDN BHD", "product_code": "SRTWC8605",
         "order_count": 1, "delivered_quantity": 7, "pending_quantity": 0,
         "delivered_from": "2026-08-01", "delivered_to": "2026-08-01"},
    ]


def test_qs_c4b_customer_count_is_not_capped_by_the_named_list(db, scenario):
    """Reviewer F-1: the count must be a COUNT(DISTINCT), never len() of the capped list."""
    cust, prod, wh = scenario
    for i in range(6):
        c = customer(db, company_id=DEFAULT_COMPANY_ID, name=f"CUSTOMER {i:02d} SDN BHD")
        _do(db, cust=c, prod=prod, wh=wh, qty=1, status_code="DELIVERED", delivered_on=date(2026, 8, 1))
    db.commit()

    s = OrderService(db).list_orders(include_summary=True, product_ids=[prod.id])["summary"]
    assert s["customer_count"] == 7          # ECO WORLD + 6
    assert len(s["customers"]) == 3          # the named list stays short
    assert s["customers"] == sorted(s["customers"])


def test_qs_c5_empty_result_carries_no_summary(db, scenario):
    _, prod, _ = scenario
    ghost = customer(db, company_id=DEFAULT_COMPANY_ID, name="NOBODY SDN BHD")
    db.commit()
    result = OrderService(db).list_orders(include_summary=True, customer_ids=[ghost.id], product_ids=[prod.id])

    assert result["empty"] is True
    assert "summary" not in result


def test_qs_c1b_delivered_bucket_and_summary_agree(db, scenario):
    cust, prod, _ = scenario
    result = OrderService(db).list_orders(include_summary=True, customer_ids=[cust.id], product_ids=[prod.id],
                                          order_status="delivered")
    assert result["pagination"]["total"] == 3
    s = result["summary"]
    assert s["order_count"] == 3 and s["delivered_count"] == 3 and s["pending_count"] == 0
    assert s["products"][0] == {"product_code": "SRTWC8605", "order_count": 3, "delivered_quantity": 48,
                                "pending_quantity": 0, "delivered_from": "2026-03-02", "delivered_to": "2026-07-15"}


# ------------------------------------------------------- list_orders_by_product

def test_qs_c6_by_product_accepts_delivered_bucket(db, scenario):
    cust, prod, _ = scenario
    result = OrderService(db).list_orders_by_product(include_summary=True, 
        product_ids=[prod.id], customer_ids=[cust.id], order_status="delivered"
    )
    numbers = {o.order_number for o in result["data"]}
    assert len(numbers) == 3  # the dated-but-NEW DO and the undated one are EXCLUDED
    s = result["summary"]
    assert s["delivered_count"] == 3 and s["pending_count"] == 0
    assert s["products"] == [
        {"product_code": "SRTWC8605", "order_count": 3, "delivered_quantity": 48, "pending_quantity": 0,
         "delivered_from": "2026-03-02", "delivered_to": "2026-07-15"}
    ]


def test_qs_c7_by_product_outstanding_bucket_is_the_negation(db, scenario):
    cust, prod, _ = scenario
    result = OrderService(db).list_orders_by_product(include_summary=True, 
        product_ids=[prod.id], customer_ids=[cust.id], order_status="outstanding"
    )
    assert result["pagination"]["total"] == 2
    s = result["summary"]
    assert s["delivered_count"] == 0 and s["pending_count"] == 2
    assert "delivered_from" not in s and "delivered_to" not in s
    assert s["products"] == [
        {"product_code": "SRTWC8605", "order_count": 2, "delivered_quantity": 0, "pending_quantity": 17}
    ]
    assert "delivered_from" not in s["groups"][0]  # nothing delivered -> no span on the group either


def test_qs_c6b_by_product_summary_without_bucket_matches_list_orders(db, scenario):
    cust, prod, _ = scenario
    svc = OrderService(db)
    a = svc.list_orders(include_summary=True, customer_ids=[cust.id], product_ids=[prod.id])["summary"]
    b = svc.list_orders_by_product(include_summary=True, product_ids=[prod.id], customer_ids=[cust.id])["summary"]
    assert a == b


def test_qs_c6c_date_only_predicate_is_not_delivered(db, scenario):
    """The old `has_actual_delivery_date=yes` filter still exists and still admits the
    dated-but-NEW DO; the summary on top of it must still say 3 delivered, not 4."""
    cust, prod, _ = scenario
    result = OrderService(db).list_orders_by_product(include_summary=True, 
        product_ids=[prod.id], customer_ids=[cust.id], has_actual_delivery_date="yes"
    )
    assert result["pagination"]["total"] == 4
    s = result["summary"]
    assert s["order_count"] == 4 and s["delivered_count"] == 3 and s["pending_count"] == 1


# ------------------------------------------------------------ endpoint surface

def test_qs_c6_by_product_route_accepts_order_status():
    """The by-product endpoint declares `order_status`, so an MCP/agent caller
    passing it is no longer silently dropped (FastAPI ignores unknown query
    params — the failure mode this guards against is invisible at runtime)."""
    from fastapi.routing import APIRoute
    route = next(r for r in app.routes
                 if isinstance(r, APIRoute) and r.path.endswith("/order-management/orders/by-product"))
    names = {p.name for p in route.dependant.query_params}
    assert "order_status" in names


# ------------------------------------------------ cross-model review (Codex pass C)

def test_qs_c2b_blank_debtor_name_falls_back_to_customer_name(db, scenario):
    cust, prod, wh = scenario
    o = _do(db, cust=cust, prod=prod, wh=wh, qty=3, status_code="DELIVERED", delivered_on=date(2026, 8, 2))
    o.debtor_name = "   "  # blank, not NULL - coalesce alone would keep it and drop the customer
    db.commit()

    s = OrderService(db).list_orders(include_summary=True, customer_ids=[cust.id], product_ids=[prod.id])["summary"]
    assert s["customer_count"] == 1 and s["customers"] == ["ECO WORLD SDN BHD"]


def test_qs_c3b_null_status_with_a_date_is_pending_in_quantity_too(db, scenario):
    """~delivered is SQL NULL for a NULL order_status_id: the order was counted in
    pending_count (total - delivered) but its quantity vanished from pending_quantity."""
    cust, prod, wh = scenario
    o = _do(db, cust=cust, prod=prod, wh=wh, qty=9, status_code="NEW", delivered_on=date(2026, 8, 3))
    o.order_status_id = None
    db.commit()

    s = OrderService(db).list_orders(include_summary=True, customer_ids=[cust.id], product_ids=[prod.id])["summary"]
    assert s["order_count"] == 6 and s["delivered_count"] == 3 and s["pending_count"] == 3
    assert s["products"][0]["pending_quantity"] == 17 + 9


def test_qs_c9_company_scope_applies_inside_the_aggregate(db, scenario):
    """A Mocha order (and its line) on the same product must not leak into a
    Sorento-scoped summary - the scope predicate has to reach the subquery and
    the joined line/product entities, not only the top-level rows."""
    cust, prod, wh = scenario
    m_cust = customer(db, company_id=MOCHA_ID, name="MOCHA BUYER SDN BHD")
    m_wh = warehouse(db, company_id=MOCHA_ID)
    _do(db, cust=m_cust, prod=prod, wh=m_wh, qty=99, status_code="DELIVERED", delivered_on=date(2026, 8, 4),
        company_id=MOCHA_ID)
    db.commit()

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    r = OrderService(db).list_orders(include_summary=True, product_ids=[prod.id])
    assert r["pagination"]["total"] == 5
    s = r["summary"]
    assert s["row_count"] == 5 and s["customer_count"] == 1
    assert s["products"][0]["delivered_quantity"] == 48  # not 48 + 99
    assert [g["customer"] for g in s["groups"]] == ["ECO WORLD SDN BHD"]  # no Mocha group

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
    s2 = OrderService(db).list_orders(include_summary=True, product_ids=[prod.id])["summary"]
    assert s2["row_count"] == 6 and s2["customer_count"] == 2
    assert s2["products"][0]["delivered_quantity"] == 48 + 99  # the same aggregate, scope widened
    assert [g["customer"] for g in s2["groups"]] == ["ECO WORLD SDN BHD", "MOCHA BUYER SDN BHD"]
