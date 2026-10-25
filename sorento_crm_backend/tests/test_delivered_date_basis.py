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


# ------------------------------------------------------------------ Q3: the agent fill rate note


def test_the_fill_rate_note_counts_the_orders_the_delivered_ranking_counted(client, db):
    """Q3 (a): the share of the window's delivered orders carrying an agent, on the DO date. SO 1
    (agent, 20 Aug) is delivered on 5 Sep; SO 2 (no agent, 10 Sep) on 12 Sep: 1 of 2 in Sep. The
    SO-date count would read 0 of 1."""
    from tests.test_one_ranking_r3b_fill_rate import _staff

    w = _world(db)
    kw = dict(cust=w.cust, prod=w.prod, wh=w.wh)
    other = _prod(db, unique_code("ZZTDDF").upper())
    _so1, sol1 = _so_line(db, qty=1, total="10.00", agent=w.ag1, order_date=date(2026, 8, 20), **kw)
    _do(db, qty=1, total="10.00", day=date(2026, 9, 5), sol=sol1, **kw)
    _so2, sol2 = _so_line(db, cust=w.cust, prod=other, wh=w.wh, qty=1, total="10.00", order_date=date(2026, 9, 10))
    _do(db, cust=w.cust, prod=other, wh=w.wh, qty=1, total="10.00", day=date(2026, 9, 12), sol=sol2)
    db.commit()
    body = _ok(client, _staff(db), group_by="product", top_n=5, sales_agent_ids=[w.ag1.id],
               customer_ids=[w.cust.id], date_from="2026-09-01", date_to="2026-09-30")
    # The world's own Sep orders count too: B's SO (agent 2), C's SO (agent 1), the no-SO DO.
    # Sep orders: B, C, no-SO DO, SO 1's DO, SO 2's DO = 5; with an agent: B, C, SO 1 = 3.
    assert body.get("sales_agent_fill_rate") == 0.6, body


# ------------------------------------------------------------------ the sales report's DO list


def test_a_delivery_with_no_do_behind_it_lists_as_no_delivery_order(client, db):
    """The residual of an SO line no DO explains is a delivery with no DO number: one row, named
    so, with no date, so the rows still sum to the total."""
    w = _world(db)
    _so_line(db, cust=w.cust, prod=w.prod, wh=w.wh, qty=5, total="50.00", order_date=date(2026, 9, 3))
    db.commit()
    resp = client.get("/api/v1/order-management/sales-report",
                      params={"product_code": w.prod.product_code, "group_by": "delivery_order", **SEP})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = {r["name"]: (r["qty"], r["date"]) for r in body["rows"]}
    assert rows["(no delivery order)"] == (5, None), body["rows"]
    assert "(blank)" not in rows
    assert sum(r["qty"] for r in body["rows"]) == body["total"]["qty"], body


# ------------------------------------------------------------------ Q5: the legacy top selling route


def test_top_selling_delivered_files_by_the_do_date_and_matches_the_ranking(client, db):
    w = _world(db)
    contact = _full(db)
    for period, want in ((SEP, (9, D("790.00"))), (OCT, (1, D("148.92")))):
        resp = client.get("/api/v1/order-management/top-selling",
                          params={"rank_by": "quantity", "basis": "delivered", "customer_ids": w.cust.id, **period})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert (body["totals"]["quantity"], money(body["totals"]["amount"])) == want, (period, body)
        assert [r["code"] for r in body["rows"]] == [w.prod.product_code], body["rows"]
        ranking = _ok(client, contact, customer_ids=[w.cust.id], **period)
        assert _total(ranking) == want, period
    project = client.get("/api/v1/order-management/top-selling",
                         params={"rank_by": "amount", "basis": "delivered", "customer_ids": w.cust.id,
                                 "channel": "project", **SEP}).json()
    assert (project["totals"]["quantity"], money(project["totals"]["amount"])) == (2, D("300.00")), project


def test_top_selling_delivered_detail_lists_customers_and_do_months(client, db):
    w = _world(db)
    resp = client.get("/api/v1/order-management/top-selling",
                      params={"rank_by": "quantity", "basis": "delivered", "customer_ids": w.cust.id,
                              "detail_code": w.prod.product_code.lower(), **Y2026})
    assert resp.status_code == 200, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == w.prod.product_code, detail
    assert [(m["month"], m["quantity"]) for m in detail["by_month"]] == [("2026-09", 9), ("2026-10", 1)], detail
    assert [(c["customer_name"], c["quantity"]) for c in detail["by_customer"]] == [(w.cust.customer_name, 10)], detail


# ------------------------------------------------------------------ Q6: the amount of a DO-linked line


def test_a_do_linked_delivery_is_worth_the_do_lines_own_total(client, db):
    """Q6 (a): the DO line's own total (what the sales report has always printed), never the SO
    line pro-rated; the residual no DO explains stays pro-rated (RM 100 a piece here)."""
    w = _world(db)
    kw = dict(cust=w.cust, prod=w.prod, wh=w.wh)
    _so, sol = _so_line(db, qty=10, total="1000.00", delivered=10, demand_class="retail", order_date=date(2026, 9, 1), **kw)
    _do(db, qty=4, total="380.00", day=date(2026, 9, 20), sol=sol, **kw)
    db.commit()
    body = _ok(client, _full(db), product_code=w.prod.product_code, channel="dealer", **SEP)
    # C (3 pcs, RM 90) + the DO's 4 pcs at RM 380 + the 6 pcs no DO explains at RM 600.
    assert _total(body) == (13, D("1070.00")), body["total"]
