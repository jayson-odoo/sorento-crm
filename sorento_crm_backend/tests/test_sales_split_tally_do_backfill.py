"""SALES-SPLIT-TALLY: filling the DO feed gap traces the invoices, with no CRM code change.

Root cause measured on prod (`documentation/plans/sales/NOTES-sales-split-tally-28oct.md`
section 2b): January invoice lines name their DO (`from_doc_type = 'DO'`, `from_doc_no`), but the
SRT company holds no AutoCount DO from October 2025 on, only a few CRM-made DOs with no lines, so
`invoiced_sales._traced_sales_order_ids` has nothing to follow and the invoice reads "No sales
order". The repair (section 2c) is to land the DOs through the DO ingest, which the DO pull's
apply runs over the raw snapshot rows (`autocount_pull_tasks._apply_delivery_orders`). These tests
run that ingest on a seeded DO whose line names its SO (`FromDocNo`) and read the invoice's sales
type before and after: no sales order, then the SO's block. All rows are seeded and fictional;
the session is rolled back.
"""
from __future__ import annotations

import copy
import json
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.main import app  # noqa: F401  (import order)
from app.models.base import set_company_scope
from app.models.finance import BillingDocument
from app.models.order import Order, OrderLine, OrderStatus
from app.services.autocount_doc_ingest_service import AutocountDocIngestService
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.sales.invoiced_sales import sales_type
from tests._mc_lookup_seed import product, warehouse
from tests._pg_fixture import pg_session, unique_code
from tests._sales_unified_seed import doc, line, so

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "autocount" / "do_live_sample.json"
JAN15 = date(2026, 1, 15)


@pytest.fixture
def db():
    with pg_session() as s:
        if s.execute(text("SELECT count(*) FROM finance.billing_documents bd JOIN companies c "
                          "ON c.id = bd.company_id WHERE c.code = 'SRT' AND bd.doc_date "
                          ">= '2026-01-01' AND bd.doc_date < '2026-02-01'")).scalar():
            pytest.skip("this database holds real January 2026 SRT documents")
        if s.execute(select(OrderStatus).where(OrderStatus.status_code.in_(["new", "NEW"]))).first() is None:
            s.add(OrderStatus(status_code="new", status_name="New Order"))
            s.flush()
        # Unscoped, as the owner's read-only SQL runs; the report's own scoping is
        # the sales-unified suite's subject, not this one's.
        set_company_scope(s, None)
        yield s


def _do_record(do_no: str, so_no: str, item_code: str, location: str) -> dict:
    """One AutoCount DO as the feed sends it (the live sample's field list), one line that
    names its SO the way AutoCount does on a DO transferred from an SO."""
    rec = copy.deepcopy(json.loads(FIXTURE.read_text())["records"][0])
    key = uuid.uuid4().int % 10**8
    rec.update(DocKey=key, DocNo=do_no, DocDate="2026-01-10T00:00:00", DebtorCode=None,
               SalesAgent=None)
    detail = rec["Details"][0]
    detail.update(DocKey=key, DtlKey=key + 1, ItemCode=item_code, Location=location,
                  FromDocType="SO", FromDocNo=so_no)
    rec["Details"] = [detail]
    return rec


def _ingest(db, record: dict) -> None:
    result = AutocountDocIngestService(db, None, company_id=DEFAULT_COMPANY_ID, book="db1").ingest(
        "delivery_orders", [record]
    )
    assert [r.outcome for r in result.records] in (["created"], ["updated"]), result.records


def _type(db, invoice: BillingDocument) -> str:
    db.expire_all()
    return db.execute(select(sales_type()).where(BillingDocument.id == invoice.id)).scalar_one()


def _setup(db, demand_class: str):
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    order, _ = so(db, demand_class=demand_class)
    do_no = unique_code("DO")
    invoice = doc(db, "invoice", "1000.00", JAN15, lines=[line(from_type="DO", from_no=do_no)])
    return prod, wh, order, do_no, invoice


@pytest.mark.parametrize("demand_class, block", [("retail", "dealer"), ("project", "project")])
def test_a_backfilled_do_traces_the_january_invoice_to_its_sales_orders_block(db, demand_class, block):
    prod, wh, order, do_no, invoice = _setup(db, demand_class)
    assert _type(db, invoice) == "no_sales_order"

    _ingest(db, _do_record(do_no, order.so_number, prod.product_code, wh.warehouse_code))

    assert _type(db, invoice) == block


def test_a_crm_made_do_with_the_same_number_is_adopted_and_then_traces(db):
    """Prod holds a few CRM-made SRT DOs a month (no `doc_key`, no lines), and January invoices
    name some of them. The ingest adopts that row by number, so no second DO appears and the
    adopted row's new line names the SO."""
    prod, wh, order, do_no, invoice = _setup(db, "retail")
    crm_made = Order(order_number=do_no, company_id=DEFAULT_COMPANY_ID, order_date=date(2026, 1, 10))
    db.add(crm_made)
    db.flush()
    assert _type(db, invoice) == "no_sales_order"

    _ingest(db, _do_record(do_no, order.so_number, prod.product_code, wh.warehouse_code))

    db.expire_all()
    rows = db.execute(select(Order).where(Order.order_number == do_no,
                                          Order.company_id == DEFAULT_COMPANY_ID)).scalars().all()
    assert [str(r.id) for r in rows] == [str(crm_made.id)]
    assert rows[0].doc_key is not None
    lines = db.execute(select(OrderLine).where(OrderLine.order_id == crm_made.id)).scalars().all()
    assert [(l.from_doc_type, l.from_doc_no) for l in lines] == [("SO", order.so_number)]
    assert _type(db, invoice) == "dealer"


def test_r14_counts_the_january_lines_whose_do_landed_and_reaches_an_so(db):
    """Owner SQL R14 (the post-backfill check) as written: one line whose DO landed through the
    ingest and names its SO, one line whose DO never arrived."""
    from tests.test_sales_split_tally_owner_sql import _blocks, _statements

    prod, wh, order, do_no, _ = _setup(db, "retail")
    doc(db, "invoice", "50.00", JAN15, lines=[line(from_type="DO", from_no=unique_code("DO"))])
    _ingest(db, _do_record(do_no, order.so_number, prod.product_code, wh.warehouse_code))
    db.execute(text("UPDATE companies SET code = 'SRT' WHERE id = :id"), {"id": DEFAULT_COMPANY_ID})

    (block,) = _blocks("R14.")
    (statement,) = _statements(block, {})
    row = db.execute(text(statement)).mappings().one()

    assert dict(row) == {"lines": 2, "do_found": 1, "reaches_so": 1}


def test_r15_counts_autocount_and_crm_made_dos_per_gap_month(db):
    """Owner SQL R15 as written: one AutoCount DO landed through the ingest (January 2026), one
    CRM-made DO with a delivery date (March 2026), one outside the gap (August 2026)."""
    from tests.test_sales_split_tally_owner_sql import _blocks, _statements

    prod, wh, order, do_no, _ = _setup(db, "retail")
    _ingest(db, _do_record(do_no, order.so_number, prod.product_code, wh.warehouse_code))
    db.add(Order(order_number=unique_code("DO"), company_id=DEFAULT_COMPANY_ID,
                 order_date=date(2026, 3, 5), actual_delivery_date=date(2026, 3, 6)))
    db.add(Order(order_number=unique_code("DO"), company_id=DEFAULT_COMPANY_ID,
                 order_date=date(2026, 8, 5)))
    db.flush()
    db.execute(text("UPDATE companies SET code = 'SRT' WHERE id = :id"), {"id": DEFAULT_COMPANY_ID})

    (block,) = _blocks("R15.")
    (statement,) = _statements(block, {})
    rows = {r["do_month"]: dict(r) for r in db.execute(text(statement)).mappings()}

    assert set(rows) == {date(2026, 1, 1), date(2026, 3, 1)}
    assert (rows[date(2026, 1, 1)]["autocount_dos"], rows[date(2026, 1, 1)]["crm_made"]) == (1, 0)
    assert rows[date(2026, 3, 1)]["crm_made"] == 1 and rows[date(2026, 3, 1)]["crm_made_with_date"] == 1
