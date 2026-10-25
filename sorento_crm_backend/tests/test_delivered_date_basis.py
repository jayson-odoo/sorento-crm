"""DELIVERED-DATE-BASIS (owner ruling 25 Oct 2026): every DELIVERED sales measure buckets by the
delivery order (DO) date, through one shared dataset (`datasets/delivery_order_lines.py`).

`documentation/plans/chatbot/PLAN-delivered-date-basis-25oct.md`, behaviour card
`delivered-date-basis-behaviour-card.md`. Ordered and outstanding keep their own basis.

The measured bug (crew live check of #1853, prod clone): SRT102-RG, Project, 2026, the ranking
answered 6 pcs / RM 943.12 (SO lines, line date) while the sales report answered 1 pc / RM 148.92
(DO lines, DO date). After this lane the two are one number.

Postgres only, every row seeded here (CI's database has none).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import unique_code
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    client,
    db,
    line,
    money,
    seed_agent,
    seed_customer,
    seed_do,
    seed_so,
    seed_so_line_row,
    warehouse,
)
from tests.test_report_ask_route import _full, _ok, _prod

D = Decimal
SEP = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
OCT = {"date_from": "2026-10-01", "date_to": "2026-10-31"}
Y2026 = {"date_from": "2026-01-01", "date_to": "2026-12-31"}


def _so_line(db, *, cust, prod, wh, qty, total, agent=None, demand_class=None, order_date=date(2026, 9, 24),
             delivered=None, required_date=None):
    """One SO (dated `order_date`) with one line; NO DO yet."""
    from app.models.order import SalesOrder

    so = seed_so(db, customer_id=cust.id, agent_id=agent.id if agent else None, demand_class=demand_class)
    db.query(SalesOrder).filter(SalesOrder.id == so.id).update({"order_date": order_date})
    sol = seed_so_line_row(db, so=so, product_id=prod.id, qty=qty, total=total, warehouse_id=wh.id,
                           delivered=delivered, required_date=required_date)
    return so, sol


def _do(db, *, cust, prod, wh, qty, total, day, sol=None, header_so=None, doc_so=None):
    """One AutoCount DO line dated `day`, linked to its SO by the line (`sol`), the header
    (`header_so`) or the doc number (`doc_so`), or not at all."""
    spec = line(prod.id, wh.id, qty, price=D(str(total)) / qty, total=D(str(total)), sales_order_line_id=sol.id if sol else None)
    if doc_so is not None:
        spec["from_doc_type"], spec["from_doc_no"] = "SO", doc_so.so_number
    return seed_do(db, customer_id=cust.id, order_date=day, source_book="db1", lines=[spec],
                   sales_order_id=header_so.id if header_so else None)


def _world(db):
    """The #1853 shape, one product:

        SO line A (project, agent AG1, SO 24 Sep)  qty 1  RM 148.92  delivered by a DO dated 14 Oct
        SO line B (project, agent AG2, SO 10 Sep)  qty 2  RM 300.00  delivered by a DO dated 12 Sep
        DO with no SO (dated 15 Sep)               qty 4  RM 400.00
        SO line C (retail,  agent AG1, SO  5 Sep)  qty 3  RM 90.00   delivered 3 by a DO dated 6 Sep
    """
    from types import SimpleNamespace

    w = SimpleNamespace()
    w.cust = seed_customer(db, name=unique_code("DDB"))
    w.wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WH"))
    w.prod = _prod(db, unique_code("ZZTDDB").upper())
    w.ag1, w.ag2 = seed_agent(db, code=unique_code("ZZT-DDB1")), seed_agent(db, code=unique_code("ZZT-DDB2"))
    kw = dict(cust=w.cust, prod=w.prod, wh=w.wh)
    _so_a, sol_a = _so_line(db, qty=1, total="148.92", agent=w.ag1, demand_class="project", order_date=date(2026, 9, 24), **kw)
    _do(db, qty=1, total="148.92", day=date(2026, 10, 14), sol=sol_a, **kw)
    _so_b, sol_b = _so_line(db, qty=2, total="300.00", agent=w.ag2, demand_class="project", order_date=date(2026, 9, 10), **kw)
    _do(db, qty=2, total="300.00", day=date(2026, 9, 12), sol=sol_b, **kw)
    _do(db, qty=4, total="400.00", day=date(2026, 9, 15), **kw)
    so_c, _sol_c = _so_line(db, qty=3, total="90.00", agent=w.ag1, demand_class="retail", order_date=date(2026, 9, 5), **kw)
    _do(db, qty=3, total="90.00", day=date(2026, 9, 6), doc_so=so_c, **kw)
    db.commit()
    return w


def _total(body):
    return body["total"]["qty"], money(body["total"]["amount"])


# ------------------------------------------------------------------ the ranking ask


def test_a_delivered_ranking_files_each_line_by_its_do_date(client, db):
    w = _world(db)
    contact = _full(db)
    sep = _ok(client, contact, product_code=w.prod.product_code, **SEP)
    oct_ = _ok(client, contact, product_code=w.prod.product_code, **OCT)
    # Sep: B 2 + no-SO 4 + C 3; A's SO is dated 24 Sep but its DO is 14 Oct.
    assert _total(sep) == (9, D("790.00")), sep["total"]
    assert _total(oct_) == (1, D("148.92")), oct_["total"]


def test_a_do_with_no_sales_order_counts_with_no_channel_and_in_no_channel(client, db):
    w = _world(db)
    contact = _full(db)
    project = _ok(client, contact, product_code=w.prod.product_code, channel="project", **SEP)
    dealer = _ok(client, contact, product_code=w.prod.product_code, channel="dealer", **SEP)
    assert _total(project) == (2, D("300.00")), project["total"]
    assert _total(dealer) == (3, D("90.00")), dealer["total"]


def test_the_sales_agent_is_the_line_linked_sales_orders_agent(client, db):
    """The DO header carries no SO link (true of every DO in dev); the agent still comes from the
    SO the line was delivered from, by the line link or the doc number."""
    w = _world(db)
    body = _ok(client, _full(db), product_code=w.prod.product_code, group_by="sales_agent", top_n=10, **SEP)
    rows = {r["name"]: (r["qty"], money(r["amount"])) for r in body["rows"]}
    assert rows == {
        "(no agent)": (4, D("400.00")),
        w.ag2.sales_agent: (2, D("300.00")),
        w.ag1.sales_agent: (3, D("90.00")),
    }, body["rows"]


def test_the_ranking_and_the_sales_report_answer_the_same_number(client, db):
    w = _world(db)
    contact = _full(db)
    for period in (SEP, OCT, Y2026):
        for channel in (None, "project", "dealer"):
            ranking = _ok(client, contact, product_code=w.prod.product_code, channel=channel, **period)
            params = {"product_code": w.prod.product_code, **period, **({"channel": channel} if channel else {})}
            resp = client.get("/api/v1/order-management/sales-report", params=params)
            assert resp.status_code == 200, resp.text
            report = resp.json()
            assert _total(ranking) == (report["total"]["qty"], money(report["total"]["amount"])), (period, channel)


def test_the_orders_count_on_delivered_counts_delivery_orders(client, db):
    w = _world(db)
    contact = _full(db)
    sep = _ok(client, contact, product_code=w.prod.product_code, measure="orders", **SEP)
    oct_ = _ok(client, contact, product_code=w.prod.product_code, measure="orders", **OCT)
    assert sep["total"]["count"] == 3, sep["total"]  # three DOs dated in Sep, one with no SO
    assert oct_["total"]["count"] == 1, oct_["total"]  # A's DO; no SO is dated in Oct


def test_ordered_keeps_the_sales_order_line_date(client, db):
    w = _world(db)
    contact = _full(db)
    sep = _ok(client, contact, product_code=w.prod.product_code, basis="ordered", **SEP)
    oct_ = _ok(client, contact, product_code=w.prod.product_code, basis="ordered", **OCT)
    assert _total(sep) == (6, D("538.92")), sep["total"]  # A, B, C by their SO dates; the no-SO DO is not ordered
    assert _total(oct_) == (0, D("0.00")), oct_["total"]


def test_a_partial_delivery_splits_across_its_do_months(client, db):
    w = _world(db)
    kw = dict(cust=w.cust, prod=w.prod, wh=w.wh)
    _so, sol = _so_line(db, qty=10, total="1000.00", delivered=10, demand_class="retail", order_date=date(2026, 9, 1), **kw)
    _do(db, qty=6, total="600.00", day=date(2026, 9, 20), sol=sol, **kw)
    _do(db, qty=4, total="400.00", day=date(2026, 10, 2), sol=sol, **kw)
    db.commit()
    contact = _full(db)
    sep = _ok(client, contact, product_code=w.prod.product_code, channel="dealer", **SEP)
    oct_ = _ok(client, contact, product_code=w.prod.product_code, channel="dealer", **OCT)
    assert _total(sep) == (9, D("690.00")), sep["total"]
    assert _total(oct_) == (4, D("400.00")), oct_["total"]


# ------------------------------------------------------------------ the Yearly comparison


def test_the_yearly_comparison_delivered_files_by_the_do_month(db):
    from app.services.reports import registry as reg
    from app.services.reports import engine
    from app.schemas.report import ReportViewConfig

    w = _world(db)
    definition = reg.get("sales_yearly")
    params = {
        "date_basis": "order_date",
        "period": {"kind": "custom", "from": "2026-01-01", "to": "2026-12-31"},
        "company": [DEFAULT_COMPANY_ID],
        "channel": ["project"],
        "basis": ["delivered"],
    }
    view = ReportViewConfig.model_validate({
        "params": params, "detail": {"columns": [], "order": []},
        "pivot": {"rows": "year", "cols": "month_of_year", "measures": ["sales_value"]},
    })
    pivot = engine.run_summary(db, definition, params, view, company_grants=frozenset({DEFAULT_COMPANY_ID}))
    cells = pivot.cells.get("2026", {})
    sep, oct_ = cells.get("09", {}).get("sales_value"), cells.get("10", {}).get("sales_value")
    # Project: B (RM 300) delivered 12 Sep, A (RM 148.92) delivered 14 Oct. The world's own rows
    # are the only project rows in CI's empty database.
    assert money(sep or 0) == D("300.00"), pivot
    assert money(oct_ or 0) == D("148.92"), pivot


def test_the_yearly_note_says_do_date_on_delivered():
    from types import SimpleNamespace

    from app.services.reports.datasets import sales_order_lines as ds

    assert "delivery order date" in ds.note(SimpleNamespace(values={"basis": ["delivered"]})), ds.note
    assert "sales order date" in ds.note(SimpleNamespace(values={"basis": ["ordered"]}))
