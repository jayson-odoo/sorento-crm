"""REPORT-OUTSTANDING-SUMMARY item 10 (owner ruling 29 Oct): pending delivery counts REP-numbered DOs (a delivery still
owed, as the pre-#1922 outstanding report counted it); cancelled DOs stay out; undated DOs stay out until lane
DO-IMPORT-DATE fixes them at source; undelivered orders keep the line required date (else the SO date), as the engine
does. The engine and the screen run one rule set.
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


def test_undelivered_orders_keep_the_line_required_date(client, db):
    """SO-2 (required 5 Dec) is December's; SO-1 (dated 20 Dec, required 15 Jan) is January's."""
    cust = seed_customer(db, name=unique_code("CustA"))
    p1 = make_product(db, unique_code("P1"))
    seed_so_line(db, cust=cust, prod=p1, qty=10, delivered=4, total="1000.00",
                 order_date=date(2025, 12, 20), required_date=date(2026, 1, 15))
    seed_so_line(db, cust=cust, prod=p1, qty=5, delivered=0, total="500.00",
                 order_date=date(2025, 11, 28), required_date=date(2025, 12, 5))
    db.commit()
    body = _ok(client, _staff(db), basis="outstanding", customer_ids=[cust.id], period=DEC_2025)
    assert _tot(body) == (5, D("500.00")), body["total"]


def test_pending_delivery_counts_a_rep_do_but_not_a_cancelled_undated_or_deleted_one(client, db):
    seed_registry(db)
    cust = seed_customer(db, name=unique_code("CustB"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    p2 = make_product(db, unique_code("P2"))
    kw = dict(customer_id=cust.id, source_book="db1")
    seed_do(db, order_date=date(2026, 10, 2), lines=[line(p2.id, wh.id, 8, total="800.00")], **kw)
    seed_do(db, order_date=date(2026, 10, 3), is_cancelled=True, lines=[line(p2.id, wh.id, 5, total="500.00")], **kw)
    seed_do(db, order_date=date(2026, 10, 4), number="REP" + unique_code("X"), lines=[line(p2.id, wh.id, 2, total="200.00")], **kw)
    seed_do(db, order_date=None, lines=[line(p2.id, wh.id, 1, total="100.00")], **kw)
    seed_do(db, order_date=date(2026, 10, 5), deleted=True, lines=[line(p2.id, wh.id, 7, total="700.00")], **kw)
    db.commit()
    body = _ok(client, _staff(db), basis="pending_delivery", product_ids=[p2.id], period=None)
    assert body["total"]["qty"] == 10, body["total"]  # 8 + the REP 2
    assert body["summary"]["documents"] == 2, body["summary"]


def test_the_delivery_order_sales_dataset_keeps_its_exclusions():
    """Only the pending variant counts REP DOs: the DO sales dataset (AC-SR-20) still drops cancelled, undated and REP."""
    from types import SimpleNamespace

    from app.services.reports.datasets import delivery_order_lines as dol

    sales = " ".join(str(p) for p in dol._fixed_filters(SimpleNamespace(definition=dol.DEFINITION, db=None)))
    assert "is_cancelled" in sales and "order_number NOT LIKE" in sales and "order_date IS NOT NULL" in sales, sales
