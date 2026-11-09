"""SORENTO-TOWN mock v3 extension of snapshot schema 1: `compare`, `today.dealer_customer_count`,
`deliveries.to_deliver` (plan "Mock v3 approved", "Phase 0 extension").

Red until `build_snapshot` / `redact` / `strip_names` carry the new keys. Postgres only, every row
seeded here.

Kill tests: drop the credit-note sign from `compare` (the day-7 amount gets bigger), or count lines
instead of distinct sales orders in `deliveries`, and the matching test goes red.
"""
from __future__ import annotations

import json
import gzip
from datetime import date, datetime, timedelta

import pytest
from app.main import app  # noqa: F401

from app.models.base import set_company_scope
from app.models.order import SalesOrder
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session
from tests._sales_unified_seed import cust, doc, line, so
from tests.test_sales_yearly_routes import _client
from tests.town._town_seed import (
    DAY, NOW, D, all_keys, dealer_doc, fake_full, project_doc, report_total,
)

WEEK_AGO = DAY - timedelta(days=7)  # Tue 27 Oct 2026


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        yield s


def _build(db, company_id=DEFAULT_COMPANY_ID):
    from app.services.town.snapshot import build_snapshot

    return build_snapshot(db, company_id, DAY, now=NOW)


# ------------------------------------------------------------------------------ compare


def _at(d, hh, mm=0):
    """Stamp a seeded document's `created_at` (naive UTC, as stored) at hh:mm UTC on its own day."""
    d.created_at = datetime(d.doc_date.year, d.doc_date.month, d.doc_date.day, hh, mm)
    return d


def test_compare_is_day_minus_7_with_the_same_calculation(db):
    a, b = cust(db), cust(db)
    _at(doc(db, "invoice", "200.00", WEEK_AGO, customer=a, lines=[line()]), 1)
    _at(dealer_doc(db, b, "50.00", WEEK_AGO, kind="cash_sale"), 1)
    _at(doc(db, "credit_note", "30.00", WEEK_AGO, customer=a, lines=[line()]), 1)
    _at(doc(db, "invoice", "999.00", WEEK_AGO, customer=a, status="cancelled"), 1)
    doc(db, "invoice", "111.00", WEEK_AGO + timedelta(days=1), customer=a)  # day-6
    doc(db, "invoice", "222.00", WEEK_AGO - timedelta(days=1), customer=a)  # day-8
    doc(db, "invoice", "5000.00", WEEK_AGO, customer=cust(db, company_id=MOCHA_ID), company_id=MOCHA_ID)
    assert report_total(db, WEEK_AGO) == D("220.00")  # the seed itself, by the shared expression
    compare = _build(db)["compare"]
    assert compare["label"] == "Tue 27 Oct"
    assert compare["last_week_amount"] == "220.00"
    assert compare["last_week_invoice_count"] == 2  # IV + CS; the credit note is not an invoice
    assert set(compare) == {"label", "last_week_amount", "last_week_invoice_count"}


def test_compare_is_the_whole_day_by_document_date_whenever_the_document_arrived(db):
    """`created_at` is when the CRM received the document, not when it was raised: a day-7 document that
    arrived on day-6 or much later still counts, in the daytime and at night alike."""
    from app.services.town.snapshot import build_snapshot
    from tests.town._town_seed import myt

    c = cust(db)
    _at(doc(db, "invoice", "100.00", WEEK_AGO, customer=c), 1)  # arrived early on its own day
    late = doc(db, "invoice", "40.00", WEEK_AGO, customer=c)
    late.created_at = datetime(WEEK_AGO.year, WEEK_AGO.month, WEEK_AGO.day) + timedelta(days=1, hours=3)  # day-6
    later = doc(db, "invoice", "30.00", WEEK_AGO, customer=c)
    later.created_at = datetime(DAY.year, DAY.month, DAY.day, 9, 0)  # arrived on the day itself
    db.flush()
    for now in (NOW, myt(DAY, 22, 0)):
        compare = build_snapshot(db, DEFAULT_COMPANY_ID, DAY, now=now)["compare"]
        assert compare["last_week_amount"] == "170.00" and compare["last_week_invoice_count"] == 3
        assert compare["label"] == "Tue 27 Oct"


def test_compare_for_a_quiet_week_ago_is_zero_not_missing(db):
    compare = _build(db)["compare"]
    assert compare == {"label": "Tue 27 Oct", "last_week_amount": "0.00", "last_week_invoice_count": 0}


def test_compare_label_is_the_weekday_day_and_month_of_the_seeded_date(db):
    from app.services.town.snapshot import build_snapshot

    other = date(2026, 12, 9)  # day-7 = Wed 2 Dec: no zero padding on the day
    snap = build_snapshot(db, DEFAULT_COMPANY_ID, other, now=NOW.replace(year=2026, month=12, day=9))
    assert snap["compare"]["label"] == "Wed 2 Dec"


# ------------------------------------------------------------------------------ redaction


def _v3_full():
    full = fake_full()
    full["compare"] = {"label": "Tue 27 Oct", "last_week_amount": "123456.78", "last_week_invoice_count": 201}
    full["today"]["dealer_customer_count"] = 88
    full["deliveries"] = {"to_deliver": 17}
    return full


def test_redact_drops_last_week_amount_and_keeps_the_count_and_label():
    from app.services.town.snapshot import redact

    out = redact(_v3_full())
    assert out["compare"] == {"label": "Tue 27 Oct", "last_week_invoice_count": 201}
    assert "last_week_amount" not in all_keys(out)
    assert "123456.78" not in json.dumps(out)
    assert out["today"]["dealer_customer_count"] == 88
    assert out["deliveries"] == {"to_deliver": 17}


def test_wallboard_of_a_full_viewer_keeps_last_week_amount_the_redacted_wallboard_drops_it():
    from app.services.town.snapshot import redact, strip_names

    full_wb = strip_names(_v3_full())
    assert full_wb["compare"]["last_week_amount"] == "123456.78"
    red_wb = strip_names(redact(_v3_full()))
    assert "last_week_amount" not in all_keys(red_wb)
    assert red_wb["compare"]["last_week_invoice_count"] == 201


def test_the_deliveries_count_is_the_same_in_full_redacted_and_wallboard():
    from app.services.town.snapshot import redact, strip_names

    full = _v3_full()
    variants = [full, redact(full), strip_names(full), strip_names(redact(full))]
    assert [v["deliveries"] for v in variants] == [{"to_deliver": 17}] * 4
    assert [v["today"]["dealer_customer_count"] for v in variants] == [88] * 4


def test_endpoint_serves_the_v3_keys_per_variant():
    """Through the route: the redacted body has no last_week_amount, full has it, deliveries in all."""
    from app.services.queue_service import redis_conn
    from app.services.town.snapshot import store
    from tests.town.test_town_snapshot_endpoint import URL, _today

    with blank_session() as db:
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        full = _v3_full()
        full["day"] = _today().isoformat()
        store(redis_conn, DEFAULT_COMPANY_ID, _today(), full)
        from tests.town.test_town_snapshot_endpoint import _user

        principal = _user(db, DEFAULT_COMPANY_ID)
        with _client(db, principal, allow=("sales.reports.view",)) as client:
            holder = client.get(URL).json()
            holder_wb = client.get(URL, params={"mode": "wallboard"}).json()
        with _client(db, principal, allow=()) as client:
            plain = client.get(URL).json()
            plain_wb = client.get(URL, params={"mode": "wallboard"}).json()
    assert holder["compare"]["last_week_amount"] == "123456.78"
    assert holder_wb["compare"]["last_week_amount"] == "123456.78"
    assert "last_week_amount" not in plain["compare"] and "last_week_amount" not in plain_wb["compare"]
    for body in (holder, holder_wb, plain, plain_wb):
        assert body["deliveries"] == {"to_deliver": 17}
        assert body["compare"]["last_week_invoice_count"] == 201
        assert body["today"]["dealer_customer_count"] == 88


# ------------------------------------------------------------------------------ dealer_customer_count


def test_dealer_customer_count_is_distinct_customers_of_todays_dealer_documents(db):
    a, b, project, plain, old, cancelled = (cust(db) for _ in range(6))
    dealer_doc(db, a, "10.00", DAY)
    dealer_doc(db, a, "20.00", DAY)  # same customer twice: once
    dealer_doc(db, b, "30.00", DAY)
    project_doc(db, project, "40.00", DAY)  # project type
    doc(db, "invoice", "50.00", DAY, customer=plain, lines=[line()])  # no sales order
    dealer_doc(db, old, "60.00", DAY - timedelta(days=1))  # another day
    cancelled_doc = dealer_doc(db, cancelled, "70.00", DAY)
    cancelled_doc.status = "cancelled"
    other = cust(db, company_id=MOCHA_ID)
    dealer_doc(db, other, "80.00", DAY, company_id=MOCHA_ID)
    db.flush()
    snap = _build(db)
    assert snap["today"]["dealer_customer_count"] == 2
    assert snap["today"]["customer_count"] == 4  # a, b, project, plain (all types)
    assert _build(db, MOCHA_ID)["today"]["dealer_customer_count"] == 1


def test_dealer_customer_count_is_zero_on_a_quiet_day(db):
    assert _build(db)["today"]["dealer_customer_count"] == 0


# ------------------------------------------------------------------------------ deliveries


def _order(db, lines, *, header_date=None, company_id=DEFAULT_COMPANY_ID):
    """A sales order with one line per dict: ordered, delivered, status, required."""
    header, made = so(db, company_id=company_id, lines=len(lines))
    header.requested_delivery_date = header_date
    for row, spec in zip(made, lines):
        row.qty_ordered = D(spec.get("ordered", 10))
        row.qty_delivered = D(spec.get("delivered", 0))
        row.line_status = spec.get("status", "open")
        row.required_date = spec.get("required")
    db.flush()
    return header


def test_deliveries_seed_is_what_the_test_thinks(db):
    _order(db, [{"required": DAY}])
    n = db.execute(
        __import__("sqlalchemy").text(
            "select count(*) from sales_order_lines where line_status='open' and qty_ordered-qty_delivered>0"
        )
    ).scalar_one()
    assert n == 1


def test_to_deliver_counts_distinct_open_overdue_orders(db):
    counted = [
        _order(db, [{"ordered": 10, "delivered": 4, "required": DAY}]),  # due today, part delivered
        _order(db, [{"required": DAY - timedelta(days=10)}]),  # overdue
        _order(db, [{"required": DAY}, {"required": DAY - timedelta(days=2)}]),  # two lines: once
        _order(db, [{"required": None}], header_date=DAY - timedelta(days=3)),  # header date, line null
        _order(db, [{"required": DAY - timedelta(days=1)}], header_date=DAY + timedelta(days=5)),  # line wins
        _order(db, [{"status": "closed", "required": DAY}, {"required": DAY}]),  # one open line is enough
    ]
    not_counted = [
        _order(db, [{"ordered": 10, "delivered": 10, "required": DAY - timedelta(days=5)}]),  # delivered
        _order(db, [{"ordered": 10, "delivered": 12, "required": DAY}]),  # over-delivered
        _order(db, [{"status": "closed", "required": DAY - timedelta(days=5)}]),
        _order(db, [{"status": "cancelled", "required": DAY - timedelta(days=5)}]),
        _order(db, [{"required": DAY + timedelta(days=1)}], header_date=DAY - timedelta(days=9)),  # due tomorrow
        _order(db, [{"required": None}], header_date=DAY + timedelta(days=1)),  # header tomorrow
        _order(db, [{"required": None}], header_date=None),  # no date at all
        _order(db, [{"required": DAY - timedelta(days=5)}], company_id=MOCHA_ID),  # other company
    ]
    assert len(counted) == 6 and len(not_counted) == 8
    assert _build(db)["deliveries"] == {"to_deliver": 6}
    assert _build(db, MOCHA_ID)["deliveries"] == {"to_deliver": 1}


def test_to_deliver_is_zero_with_no_orders_not_missing(db):
    assert _build(db)["deliveries"] == {"to_deliver": 0}


def test_deliveries_is_a_count_only_no_names_or_amounts(db):
    _order(db, [{"required": DAY}])
    assert set(_build(db)["deliveries"]) == {"to_deliver"}
