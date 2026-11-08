"""SORENTO-TOWN Phase 0, the figures: `app.services.town.snapshot.build_snapshot`.

Red until the service exists. UAC AC-1 (town total == sales report), AC-5 (shops), AC-6
(warehouses, reorder), AC-7 (approvals). Postgres only (`blank_session`), every row seeded here.

Kill test (AC-1): sum `local_net_total` without `inv.signed_amount()`'s credit-note sign, or sum
the lines without `counted_line()`, and `test_ac1_*` goes red.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.finance import BillingDocumentLine
from app.models.inventory import Stock
from app.models.procurement import PurchaseRequestHeader
from app.models.projects import Project, ProjectQuotationDocument
from app.models.scm import ReorderLevel
from app.models.status import Status
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha, warehouse
from tests._pg_fixture import blank_session, unique_code
from tests._sales_unified_seed import cust, doc, line
from tests.town._town_seed import (
    DAY, NOW, D, dealer_doc, line_total, project_doc, report_total,
)


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        yield s


def _build(db, company_id=DEFAULT_COMPANY_ID, day=DAY, now=NOW):
    from app.services.town.snapshot import build_snapshot

    return build_snapshot(db, company_id, day, now=now)


# --------------------------------------------------------------------------- AC-1


def _seed_day(db):
    a, b, c = cust(db), cust(db), cust(db)
    # Invoice with a subtotal line: 60 + 40 and the subtotal 100 that restates them.
    with_subtotal = dealer_doc(db, a, "1000.00", DAY)
    plain = doc(db, "invoice", "250.50", DAY, customer=b, lines=[line()])  # no sales order: still counted
    cash = dealer_doc(db, a, "100.25", DAY, kind="cash_sale")
    credit = doc(db, "credit_note", "50.10", DAY, customer=c, lines=[line()])
    cancelled = doc(db, "invoice", "999.99", DAY, customer=b, status="cancelled")
    yesterday = doc(db, "invoice", "777.00", DAY - timedelta(days=1), customer=b)
    other_company = doc(db, "invoice", "5000.00", DAY, customer=cust(db, company_id=MOCHA_ID), company_id=MOCHA_ID)
    db.add_all([
        BillingDocumentLine(id=str(uuid.uuid4()), document_id=with_subtotal.id, company_id=DEFAULT_COMPANY_ID,
                            line_no=90, net_amount=D("1000.00"), quantity=D("1"), is_subtotal=True,
                            source_ref="SUB1"),
    ])
    db.flush()
    return {"a": a, "b": b, "c": c, "ids": [with_subtotal.id, plain.id, cash.id, credit.id,
                                           cancelled.id, yesterday.id, other_company.id]}


def test_ac1_seed_is_what_the_test_thinks(db):
    """Guard: the seeding itself, asserted by direct SQL, so a red below is about the feature."""
    _seed_day(db)
    assert report_total(db, DAY) == D("1300.65")
    assert line_total(db, DAY) == D("1300.65")
    n = db.execute(sa.text("select count(*) from billing_documents where company_id = :c and doc_date = :d"),
                   {"c": DEFAULT_COMPANY_ID, "d": DAY}).scalar_one()
    assert n == 5  # 3 posted sales + credit note + cancelled


def test_ac1_town_total_equals_the_sales_report_and_the_line_sum(db):
    _seed_day(db)
    snap = _build(db)
    expected = report_total(db, DAY)
    assert expected == line_total(db, DAY) == D("1300.65")
    assert snap["today"]["amount"] == "1300.65"
    assert isinstance(snap["today"]["amount"], str)
    assert D(snap["today"]["amount"]) == expected
    assert snap["today"]["invoice_count"] == 3  # 2 invoices + 1 cash sale
    assert snap["today"]["credit_note_count"] == 1
    assert snap["today"]["customer_count"] == 3  # a (twice), b, c; the cancelled and old ones add none


def test_ac1_amount_is_two_decimal_places_even_when_whole(db):
    c = cust(db)
    doc(db, "invoice", "100", DAY, customer=c)
    assert _build(db)["today"]["amount"] == "100.00"


def test_ac1_empty_day_is_zero_not_missing(db):
    snap = _build(db)
    assert snap["today"] == {"amount": "0.00", "invoice_count": 0, "credit_note_count": 0, "customer_count": 0}
    assert snap["shops"] == []


def test_ac1_other_company_is_excluded_and_counted_in_its_own_town(db):
    _seed_day(db)
    mocha = _build(db, MOCHA_ID)
    assert mocha["company_id"] == MOCHA_ID
    assert mocha["today"]["amount"] == "5000.00"
    assert mocha["today"]["invoice_count"] == 1
    assert _build(db)["today"]["amount"] == "1300.65"


def test_snapshot_envelope_schema_phase_and_dates(db):
    snap = _build(db)
    assert snap["schema"] == 1
    assert snap["company_id"] == DEFAULT_COMPANY_ID
    assert snap["day"] == "2026-11-03"
    assert snap["as_of"] == "2026-11-03T15:42:00+08:00"
    assert snap["phase"] == "day"
    assert snap["data_as_of"] is None  # no document carries last_synced_at
    from tests.town._town_seed import myt

    night = _build(db, now=myt(DAY, 22, 0))
    assert night["phase"] == "night"
    assert _build(db, now=myt(DAY, 21, 59))["phase"] == "day"


def test_data_as_of_is_the_newest_last_synced_at(db):
    first = doc(db, "invoice", "10.00", DAY, customer=cust(db))
    second = doc(db, "invoice", "10.00", DAY, customer=cust(db))
    first.last_synced_at = datetime(2026, 11, 3, 9, 0, 0)
    second.last_synced_at = datetime(2026, 11, 3, 14, 30, 0)
    db.flush()
    stamp = _build(db)["data_as_of"]
    assert stamp is not None and stamp.startswith("2026-11-03T14:30") and stamp.endswith("+00:00")


def test_data_as_of_ignores_documents_older_than_a_week(db):
    old = doc(db, "invoice", "10.00", DAY - timedelta(days=30), customer=cust(db))
    old.last_synced_at = datetime(2026, 10, 4, 9, 0, 0)
    db.flush()
    assert _build(db)["data_as_of"] is None


# --------------------------------------------------------------------------- AC-5


def _dealers(db, n, *, base=1000, day_offset=5, label_first=False):
    """n Dealer-type customers with distinct 90-day amounts (base + i*10), invoiced day-offset days back."""
    made = []
    for i in range(n):
        name = f"ZZT Dealer {i:02d} SDN BHD" + (" [A/C III]" if label_first and i == n - 1 else "")
        c = cust(db, name=name, code=unique_code(f"D{i:02d}")[:50])
        dealer_doc(db, c, f"{base + i * 10}.00", DAY - timedelta(days=day_offset))
        made.append(c)
    return made


def test_ac5_top_30_by_90_day_amount_cut_and_project_account_never_a_shop(db):
    dealers = _dealers(db, 31)  # the first (smallest) is the 31st by amount
    project = cust(db, name="ZZT Big Project Co")
    project_doc(db, project, "999999.00", DAY - timedelta(days=5))
    snap = _build(db)
    shops = [s for s in snap["shops"] if s["kind"] == "shop"]
    assert len(shops) == 30
    keys = {s["key"] for s in shops}
    assert dealers[0].id not in keys  # smallest of 31
    assert project.id not in {s["key"] for s in snap["shops"]}
    assert all(d.id in keys for d in dealers[1:])
    assert [s["rank"] for s in shops] == list(range(1, 31))
    amounts = [D(s["ninety_day_amount"]) for s in shops]
    assert amounts == sorted(amounts, reverse=True)
    top = shops[0]
    assert top["key"] == dealers[30].id
    assert top["code"] == dealers[30].customer_code
    assert top["name"] == dealers[30].customer_name
    assert top["ninety_day_amount"] == "1300.00"
    assert top["today_amount"] == "0.00" and top["today_docs"] == 0


def test_ac5_the_31st_account_not_invoiced_today_is_absent_entirely(db):
    dealers = _dealers(db, 31)
    keys = {s["key"] for s in _build(db)["shops"]}
    assert dealers[0].id not in keys  # neither a shop (31st) nor a stall (no document today)


def test_ac5_second_build_reads_the_cached_ranking_and_does_not_recompute_it(db, monkeypatch):
    from app.services.town import snapshot as town

    mine = cust(db, name="ZZT Cached")
    dealer_doc(db, mine, "100.00", DAY - timedelta(days=2))
    first = _build(db)
    assert [s["key"] for s in first["shops"]] == [mine.id]
    from app.services.queue_service import redis_conn

    assert redis_conn.exists(f"town:{DEFAULT_COMPANY_ID}:{DAY.isoformat()}:ranking")
    assert redis_conn.ttl(f"town:{DEFAULT_COMPANY_ID}:{DAY.isoformat()}:ranking") > 35 * 3600

    def boom(*a, **k):
        raise AssertionError("ranking recomputed")

    monkeypatch.setattr(town, "compute_ranking", boom)
    dealer_doc(db, mine, "50.00", DAY)  # today's figures are still live
    second = _build(db)
    shop = second["shops"][0]
    assert shop["ninety_day_amount"] == "100.00"  # the cached nightly ranking figure
    assert shop["today_amount"] == "50.00" and shop["today_docs"] == 1


def _through_the_five_second_session(db, monkeypatch):
    """Run the REAL build_snapshot on `_build_session` (the tick's 5 s path), recording
    `statement_timeout` inside the ranking query and again at the warehouses step."""
    from contextlib import contextmanager

    from app.services.town import snapshot as town

    @contextmanager
    def fake_scheduler_session(name="scheduler"):
        yield db

    monkeypatch.setattr(town, "scheduler_session", fake_scheduler_session)
    seen: dict = {}
    real_rows, real_wh = town._dealer_rows, town._warehouses

    def rows(session, company_id, since, until, *, today):
        if today is None:
            seen["ranking"] = session.execute(sa.text("show statement_timeout")).scalar_one()
        return real_rows(session, company_id, since, until, today=today)

    def warehouses(session, company_id):
        seen["after"] = session.execute(sa.text("show statement_timeout")).scalar_one()
        return real_wh(session, company_id)

    monkeypatch.setattr(town, "_dealer_rows", rows)
    monkeypatch.setattr(town, "_warehouses", warehouses)
    return town, seen


def test_ranking_runs_with_30s_and_the_build_returns_to_5s(db, monkeypatch):
    town, seen = _through_the_five_second_session(db, monkeypatch)
    dealer_doc(db, cust(db, name="ZZT Timeout Shop"), "10.00", DAY - timedelta(days=1))
    with town._build_session() as session:
        town.build_snapshot(session, DEFAULT_COMPANY_ID, DAY, now=NOW)
    assert seen["ranking"] in ("30s", "30000ms"), seen
    assert seen["after"] in ("5s", "5000ms"), seen


def test_a_failed_ranking_is_logged_cached_briefly_and_the_town_still_builds(db, monkeypatch, caplog):
    from sqlalchemy.exc import OperationalError

    from app.services.queue_service import redis_conn

    town, seen = _through_the_five_second_session(db, monkeypatch)
    dealer_doc(db, cust(db, name="ZZT Today Only"), "10.00", DAY)

    def timed_out(session, company_id, day):
        session.execute(sa.text("SET LOCAL statement_timeout = 30000"))
        raise OperationalError("select", {}, Exception("canceling statement due to statement timeout"))

    monkeypatch.setattr(town, "compute_ranking", timed_out)
    with caplog.at_level("ERROR"), town._build_session() as session:
        snap = town.build_snapshot(session, DEFAULT_COMPANY_ID, DAY, now=NOW)
    assert not [s for s in snap["shops"] if s["kind"] == "shop"]
    assert [s["kind"] for s in snap["shops"]] == ["stall"]  # today's figures survive
    assert snap["today"]["amount"] == "10.00"
    key = f"town:{DEFAULT_COMPANY_ID}:{DAY.isoformat()}:ranking"
    assert redis_conn.exists(key) and 0 < redis_conn.ttl(key) <= 1800
    assert "statement timeout" in caplog.text
    assert seen["after"] in ("5s", "5000ms"), seen  # the savepoint rollback undid the 30 s


def test_ac5_ninety_day_window_includes_day_minus_89_excludes_day_minus_90(db):
    inside = cust(db, name="ZZT Inside")
    outside = cust(db, name="ZZT Outside")
    dealer_doc(db, inside, "300.00", DAY - timedelta(days=89))
    dealer_doc(db, outside, "900.00", DAY - timedelta(days=90))
    keys = {s["key"]: s for s in _build(db)["shops"]}
    assert inside.id in keys and keys[inside.id]["ninety_day_amount"] == "300.00"
    assert outside.id not in keys


def test_ac5_credit_note_reduces_the_ninety_day_amount(db):
    c = cust(db, name="ZZT Credit Dealer")
    dealer_doc(db, c, "500.00", DAY - timedelta(days=10))
    dealer_doc(db, c, "120.00", DAY - timedelta(days=9), kind="credit_note")
    shop = next(s for s in _build(db)["shops"] if s["key"] == c.id)
    assert shop["ninety_day_amount"] == "380.00"


def test_ac5_account_label_parsed_from_the_bracket_suffix(db):
    labelled = cust(db, name="ZZT EXAMPLE TILES SDN BHD [A/C III]")
    plain = cust(db, name="ZZT PLAIN TILING SDN BHD")
    dealer_doc(db, labelled, "200.00", DAY - timedelta(days=3))
    dealer_doc(db, plain, "100.00", DAY - timedelta(days=3))
    by_key = {s["key"]: s for s in _build(db)["shops"]}
    assert by_key[labelled.id]["account_label"] == "A/C III"
    assert by_key[plain.id]["account_label"] is None


def test_ac5_one_shop_per_autocount_account_not_per_company(db):
    first = cust(db, name="ZZT TWIN TILING SDN BHD [A/C I]")
    second = cust(db, name="ZZT TWIN TILING SDN BHD [A/C III]")
    dealer_doc(db, first, "200.00", DAY - timedelta(days=3))
    dealer_doc(db, second, "100.00", DAY - timedelta(days=3))
    shops = _build(db)["shops"]
    assert {s["key"] for s in shops} == {first.id, second.id}
    assert {s["account_label"] for s in shops} == {"A/C I", "A/C III"}


def test_ac5_dealer_invoiced_today_outside_top_30_is_a_stall_and_shops_carry_today(db):
    dealers = _dealers(db, 30, base=2000)
    small = cust(db, name="ZZT Small Dealer")
    dealer_doc(db, small, "5.00", DAY)
    dealer_doc(db, dealers[29], "50.00", DAY)  # top shop also sells today, two documents
    dealer_doc(db, dealers[29], "27.00", DAY)
    project_today = cust(db, name="ZZT Project Today")
    project_doc(db, project_today, "400.00", DAY)
    snap = _build(db)
    by_key = {s["key"]: s for s in snap["shops"]}
    stall = by_key[small.id]
    assert stall["kind"] == "stall" and stall["rank"] is None
    assert stall["today_amount"] == "5.00" and stall["today_docs"] == 1
    assert stall["name"] == small.customer_name and stall["code"] == small.customer_code
    shop = by_key[dealers[29].id]
    assert shop["kind"] == "shop" and shop["rank"] == 1
    assert shop["today_amount"] == "77.00" and shop["today_docs"] == 2
    assert project_today.id not in by_key  # a stall is Dealer-type only
    assert len([s for s in snap["shops"] if s["kind"] == "shop"]) == 30


def test_ac5_shops_are_company_scoped(db):
    mine = cust(db, name="ZZT Mine")
    theirs = cust(db, name="ZZT Theirs", company_id=MOCHA_ID)
    dealer_doc(db, mine, "100.00", DAY - timedelta(days=2))
    dealer_doc(db, theirs, "900.00", DAY - timedelta(days=2), company_id=MOCHA_ID)
    assert {s["key"] for s in _build(db)["shops"]} == {mine.id}
    assert {s["key"] for s in _build(db, MOCHA_ID)["shops"]} == {theirs.id}


# --------------------------------------------------------------------------- AC-6


def _stock(db, prod, wh, on_hand, reserved=0, company_id=DEFAULT_COMPANY_ID):
    db.add(Stock(id=str(uuid.uuid4()), product_id=prod.id, warehouse_id=wh.id, quantity_on_hand=on_hand,
                 quantity_reserved=reserved, company_id=company_id))
    db.flush()


def test_ac6_sub_locations_fold_onto_their_pool_and_inactive_is_excluded(db):
    pool = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-POOL")
    sub1 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-POOL-A")
    sub2 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-POOL-B")
    sub1.pool_warehouse_id = pool.id
    sub2.pool_warehouse_id = pool.id
    lone = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-LONE")
    dead = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-DEAD")
    dead.is_active = False
    dead_sub = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-POOL-DEAD")
    dead_sub.pool_warehouse_id = pool.id
    dead_sub.is_active = False
    foreign = warehouse(db, company_id=MOCHA_ID, code="ZZT-MOCHA")
    db.flush()
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    _stock(db, p, pool, 10, 2)
    _stock(db, p, sub1, 5)
    _stock(db, p, sub2, 7, 1)
    _stock(db, p, dead_sub, 1000)
    _stock(db, p, lone, 3)
    _stock(db, p, dead, 500)
    _stock(db, product(db, company_id=MOCHA_ID), foreign, 9999, company_id=MOCHA_ID)
    by_pool = {w["pool"]: w for w in _build(db)["warehouses"]}
    assert set(by_pool) == {"ZZT-POOL", "ZZT-LONE"}  # no entry for the inactive one or the other company
    assert by_pool["ZZT-POOL"]["on_hand"] == 22
    assert by_pool["ZZT-POOL"]["available"] == 19
    assert by_pool["ZZT-POOL"]["locations"] == 3  # the pool itself plus its two active sub-locations
    assert by_pool["ZZT-LONE"] == {"pool": "ZZT-LONE", "on_hand": 3, "available": 3, "locations": 1}


def _level(db, prod, level, *, warehouse_id=None, company_id=DEFAULT_COMPANY_ID):
    db.add(ReorderLevel(id=str(uuid.uuid4()), product_id=prod.id, warehouse_id=warehouse_id, level=level,
                        company_id=company_id))
    db.flush()


def test_ac6_reorder_below_and_set_counts(db):
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    counting_not = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    counting_not.counts_as_available = False
    inactive_wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    inactive_wh.is_active = False
    db.flush()
    mk = lambda: product(db, company_id=DEFAULT_COMPANY_ID)  # noqa: E731
    below, below_excl, equal, nostock, zero, unset, per_loc, dead_stock = (mk() for _ in range(8))
    _level(db, below, 10)
    _stock(db, below, wh, 4)  # 4 < 10
    _level(db, below_excl, 10)
    _stock(db, below_excl, wh, 4)
    _stock(db, below_excl, counting_not, 20)  # does not count as available: still 4
    _level(db, equal, 10)
    _stock(db, equal, wh, 10)  # not below at equal
    _level(db, nostock, 10)  # no stock row = 0, below
    _level(db, zero, 0)  # level 0 is never counted
    _level(db, unset, None)  # NULL = not set
    _level(db, per_loc, 10, warehouse_id=wh.id)  # a per-location row is not product-wide
    _level(db, dead_stock, 10)
    _stock(db, dead_stock, inactive_wh, 50)  # inactive warehouse stock does not count: 0, below
    other = product(db, company_id=MOCHA_ID)
    _level(db, other, 10, company_id=MOCHA_ID)  # another company's level
    reorder = _build(db)["reorder"]
    assert reorder == {"set_count": 5, "below_count": 4}


def test_ac6_inactive_product_is_not_counted(db):
    """The contract says reorder rows are `is_active`; `scm.reorder_level` has no such column, so
    this reads it as the PRODUCT's `is_active` (see the report). Remove if the owner says otherwise."""
    live = product(db, company_id=DEFAULT_COMPANY_ID)
    dead = product(db, company_id=DEFAULT_COMPANY_ID)
    dead.is_active = False
    db.flush()
    _level(db, live, 10)
    _level(db, dead, 10)
    assert _build(db)["reorder"] == {"set_count": 1, "below_count": 1}


# --------------------------------------------------------------------------- AC-7


def _pr(db, approval_status, *, voided=False):
    row = PurchaseRequestHeader(
        id=str(uuid.uuid4()), request_type="purchase_request", request_number=unique_code("PR")[:50],
        approval_status=approval_status,
    )
    if voided:
        row.void_reason = "ZZT voided"
        row.voided_at = datetime(2026, 11, 3, 9, 0, 0)
    db.add(row)
    db.flush()
    return row


def _quotation_status(db, key):
    row = Status(id=str(uuid.uuid4()), entity_type="quotation", key=key, label=key)
    db.add(row)
    db.flush()
    return row


def _project(db, company_id):
    tag = uuid.uuid4().hex[:6]
    row = Project(id=str(uuid.uuid4()), company_id=company_id, project_code=f"ZZT-{tag}",
                  title=f"ZZT Project {tag}", normalised_title=f"zzt project {tag}")
    db.add(row)
    db.flush()
    return row


def _quotation(db, company_id, status):
    project = _project(db, company_id)
    row = ProjectQuotationDocument(
        id=str(uuid.uuid4()), company_id=company_id, project_id=project.id,
        document_no=unique_code("Q")[:60], approval_status_id=status.id if status is not None else None,
    )
    db.add(row)
    db.flush()
    return row


def test_ac7_pending_purchase_requests_counted_approved_and_voided_are_not(db):
    _pr(db, "pending")
    _pr(db, "pending")
    _pr(db, "pending", voided=True)
    _pr(db, "approved")
    _pr(db, "rejected")
    _pr(db, None)
    approvals = _build(db)["approvals"]
    assert approvals == {"total": 2, "purchase_requests": 2, "quotation_documents": 0}
    # no company column: the same count on every company's town
    assert _build(db, MOCHA_ID)["approvals"]["purchase_requests"] == 2


def test_ac7_quotation_documents_pending_or_resubmitted_counted_for_the_company(db):
    pending = _quotation_status(db, "pending_approval")
    resubmitted = _quotation_status(db, "resubmitted")
    approved = _quotation_status(db, "approved")
    draft = _quotation_status(db, "draft")
    _quotation(db, DEFAULT_COMPANY_ID, pending)
    _quotation(db, DEFAULT_COMPANY_ID, resubmitted)
    _quotation(db, DEFAULT_COMPANY_ID, approved)
    _quotation(db, DEFAULT_COMPANY_ID, draft)
    _quotation(db, DEFAULT_COMPANY_ID, None)  # never needed a manager
    _quotation(db, MOCHA_ID, pending)  # another company
    _pr(db, "pending")
    approvals = _build(db)["approvals"]
    assert approvals == {"total": 3, "purchase_requests": 1, "quotation_documents": 2}
    assert _build(db, MOCHA_ID)["approvals"] == {"total": 2, "purchase_requests": 1, "quotation_documents": 1}


def test_ac7_all_clear_is_zeros_not_missing(db):
    assert _build(db)["approvals"] == {"total": 0, "purchase_requests": 0, "quotation_documents": 0}
    assert _build(db)["warehouses"] == []
    assert _build(db)["reorder"] == {"below_count": 0, "set_count": 0}
