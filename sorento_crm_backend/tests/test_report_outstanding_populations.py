"""REPORT-OUTSTANDING-SUMMARY item 10 (owner 29 Oct): the chat outstanding figures count what the pre-#1922 outstanding
report counted (`outstanding_report_service._fill_so` / `_fill_do`, 98773e5a^).

* Undelivered orders are dated by the SALES ORDER's date, never the line's required date; a line with no date counts
  when no period is named.
* Pending delivery counts every undelivered DO that is not deleted: a cancelled-but-not-deleted DO, a REP-numbered DO and
  a DO with no date count too (the sales bases keep excluding them).

The numbers are the ones put to the owner (PR comment "item 10, WHY the outstanding figures changed").
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import unique_code
from tests._report_ask_so_seed import seed_so_line
from tests._report_unify_seed import make_product, seed_registry
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    client,
    db,
    line,
    money,
    seed_customer,
    seed_do,
    warehouse,
)
from tests.test_report_unify_outstanding_bases import _ok, _staff

D = Decimal
DEC_2025 = {"date_from": "2025-12-01", "date_to": "2025-12-31"}


def _tot(body):
    return body["total"]["qty"], money(body["total"]["amount"])


def test_example_1_undelivered_orders_are_dated_by_the_sales_order_date(client, db):
    cust = seed_customer(db, name=unique_code("CustA"))
    p1 = make_product(db, unique_code("P1"))
    seed_so_line(db, cust=cust, prod=p1, qty=10, delivered=4, total="1000.00",
                 order_date=date(2025, 12, 20), required_date=date(2026, 1, 15))
    seed_so_line(db, cust=cust, prod=p1, qty=5, delivered=0, total="500.00",
                 order_date=date(2025, 11, 28), required_date=date(2025, 12, 5))
    db.commit()
    body = _ok(client, _staff(db), basis="outstanding", customer_ids=[cust.id], period=DEC_2025)
    assert _tot(body) == (6, D("600.00")), body["total"]  # SO-1 (dated 20 Dec), never SO-2 (required 5 Dec)


def test_an_undated_open_line_counts_over_every_date_but_not_in_a_period(client, db):
    cust = seed_customer(db, name=unique_code("CustU"))
    p1 = make_product(db, unique_code("PU"))
    seed_so_line(db, cust=cust, prod=p1, qty=3, delivered=0, total="300.00", order_date=None, required_date=None)
    db.commit()
    staff = _staff(db)
    assert _tot(_ok(client, staff, basis="outstanding", customer_ids=[cust.id], period=None)) == (3, D("300.00"))
    assert _tot(_ok(client, staff, basis="outstanding", customer_ids=[cust.id], period=DEC_2025)) == (0, D("0.00"))


def test_example_2_pending_delivery_counts_every_undelivered_do_not_deleted(client, db):
    seed_registry(db)
    cust = seed_customer(db, name=unique_code("CustB"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    p2 = make_product(db, unique_code("P2"))
    kw = dict(customer_id=cust.id, source_book="db1")
    seed_do(db, order_date=date(2026, 10, 2), lines=[line(p2.id, wh.id, 8, total="800.00")], **kw)
    seed_do(db, order_date=date(2026, 10, 3), is_cancelled=True, lines=[line(p2.id, wh.id, 5, total="500.00")], **kw)
    seed_do(db, order_date=date(2026, 10, 4), number=unique_code("REP"), lines=[line(p2.id, wh.id, 2, total="200.00")], **kw)
    seed_do(db, order_date=None, lines=[line(p2.id, wh.id, 1, total="100.00")], **kw)
    seed_do(db, order_date=date(2026, 10, 5), deleted=True, lines=[line(p2.id, wh.id, 7, total="700.00")], **kw)
    db.commit()
    staff = _staff(db)
    body = _ok(client, staff, basis="pending_delivery", product_ids=[p2.id], period=None)
    assert body["total"]["qty"] == 16, body["total"]  # 8 + 5 + 2 + 1; the deleted DO is out
    assert body["summary"]["documents"] == 4, body["summary"]
    oct_only = _ok(client, staff, basis="pending_delivery", product_ids=[p2.id],
                   period={"date_from": "2026-10-01", "date_to": "2026-10-31"})
    assert oct_only["total"]["qty"] == 15, oct_only["total"]  # the undated DO has no October


def test_the_delivery_order_sales_dataset_keeps_its_exclusions():
    """Only the pending variant changes: the DO sales dataset (AC-SR-20) still drops cancelled, undated and REP DOs."""
    from types import SimpleNamespace

    from app.services.reports.datasets import delivery_order_lines as dol

    sales = " ".join(str(p) for p in dol._fixed_filters(SimpleNamespace(definition=dol.DEFINITION, db=None)))
    assert "is_cancelled" in sales and "order_number NOT LIKE" in sales and "order_date IS NOT NULL" in sales, sales
