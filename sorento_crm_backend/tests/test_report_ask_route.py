"""Phase 2 RED tests - `GET /api/v1/order-management/report-ask` (lane REPORT-ENGINE, slice 1a).

`documentation/plans/chatbot/PLAN-report-engine.md` section 0 and section 10 (the binding
contract) and `report-engine-acceptance-criteria.md` AC-RE-1 to AC-RE-17 and AC-RE-20.

Written BEFORE the route, `app/services/reports/ask.py` or the ask datasets exist: every test
must fail on the missing route (404) and never on a seed error. Postgres only
(`tests/_pg_fixture.py`), every row seeded here (CI's database has none).

Figures are AutoCount DOs (`source_book="db1"`), so a line's amount is its own total.

Ambiguities the tester did NOT resolve by guessing (flagged to the captain):
* a dealer naming another customer: PLAN section 10 lists the customer filter among the
  dimensions that 403 `report_dimension_not_allowed`, AC-RE-14 says 403 `customer_not_permitted`.
  Pinned here as AC-RE-14 (`customer_not_permitted`).
* the row `name` for `group_by=channel` (raw `project` / `retail` or a label): not asserted,
  only the amounts and the order.
* `group_by=month` rows rank by the measure like every other group (not chronologically).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Brand, ProductCategory
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import seed_mocha
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    _as_contact,
    _contact,
    _link,
    client,
    db,
    line,
    money,
    product,
    seed_agent,
    seed_customer,
    seed_do,
    seed_policy,
    seed_segment,
    seed_so,
    warehouse,
)
from tests.test_top_selling_report import _access
from tests._pg_fixture import unique_code

D = Decimal
ROUTE = "/api/v1/order-management/report-ask"
SALES_REPORT = "/api/v1/order-management/sales-report"
KEY = {"X-API-Key": "k"}
PERIOD = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
SEP = date(2026, 9, 10)
AUG = date(2026, 8, 15)
DEALER_MESSAGE = "That breakdown is not available for your account."


# ------------------------------------------------------------------------- helpers


def _ask(client, contact, headers=KEY, **params):
    q = {**PERIOD, **_as_contact(contact), **params}
    q = {k: v for k, v in q.items() if v is not None}
    return client.get(ROUTE, params=q, headers=headers)


def _ok(client, contact, **params):
    resp = _ask(client, contact, **params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _code(resp):
    return resp.json().get("code")


def _rows(body):
    return [(r["name"], r["qty"], money(r["amount"])) for r in body["rows"]]


def _full(db):
    """A grant holder with no customer link: the FULL audience."""
    contact = _contact(db)
    db.commit()
    return contact


def _brand(db, name):
    row = Brand(id=str(uuid.uuid4()), brand_code=unique_code("BR")[:50], brand_name=name,
                company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return row


def _category(db, name):
    row = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50],
                          category_name=name, company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return row


def _prod(db, code, *, brand=None, category=None):
    row = product(db, company_id=DEFAULT_COMPANY_ID, code=code)
    if brand is not None:
        row.brand_id = brand.id
    if category is not None:
        row.category_id = category.id
    db.flush()
    return row


def _sale(db, *, cust, wh, agent, prod, qty, total, when=SEP, so=True):
    """One AutoCount DO with one line, linked to a fresh SO of `agent` (None = SO with no agent;
    `so=False` = a DO with no sales order at all)."""
    so_id = seed_so(db, customer_id=cust.id, agent_id=agent.id if agent else None).id if so else None
    return seed_do(db, customer_id=cust.id, order_date=when, sales_order_id=so_id, source_book="db1",
                   lines=[line(prod.id, wh.id, qty, price=D("1"), total=D(str(total)))])


def _ranking_world(db):
    """Three agents, two brands, two categories, three products (see the table below).

    p1 ZZTAA-1 brand A cat X | p2 ZZTAA-2 brand A cat Y | p3 ZZTBB-1 brand B cat X

        agent  p1          p2         p3          all
        A1     1000 / 10   -          500 / 5     1500 / 15
        A2     600 / 20    100 / 4    -           700 / 24
        A3     -           50 / 1     3000 / 30   3050 / 31
        A4 (August, outside the window)   777 / 7

    all (Sep): A3 3050/31, A1 1500/15, A2 700/24 -> total 5250 / 70.
    """
    w = SimpleNamespace()
    w.cust = seed_customer(db, name=unique_code("Cust"))
    w.wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WH"))
    w.brand_a, w.brand_b = _brand(db, "ZZT-BRAND-A"), _brand(db, "ZZT-BRAND-B")
    w.cat_x, w.cat_y = _category(db, "ZZT-CAT-X"), _category(db, "ZZT-CAT-Y")
    w.p1 = _prod(db, "ZZTAA-1", brand=w.brand_a, category=w.cat_x)
    w.p2 = _prod(db, "ZZTAA-2", brand=w.brand_a, category=w.cat_y)
    w.p3 = _prod(db, "ZZTBB-1", brand=w.brand_b, category=w.cat_x)
    w.a1, w.a2, w.a3, w.a4 = (seed_agent(db, code=f"ZZT-AG-{n}") for n in ("1", "2", "3", "4"))
    kw = dict(cust=w.cust, wh=w.wh)
    _sale(db, agent=w.a1, prod=w.p1, qty=10, total="1000.00", **kw)
    _sale(db, agent=w.a1, prod=w.p3, qty=5, total="500.00", **kw)
    _sale(db, agent=w.a2, prod=w.p1, qty=20, total="600.00", **kw)
    _sale(db, agent=w.a2, prod=w.p2, qty=4, total="100.00", **kw)
    _sale(db, agent=w.a3, prod=w.p2, qty=1, total="50.00", **kw)
    _sale(db, agent=w.a3, prod=w.p3, qty=30, total="3000.00", **kw)
    _sale(db, agent=w.a4, prod=w.p1, qty=7, total="777.00", when=AUG, **kw)
    db.commit()
    return w


def _ordered(db, *, cust, agent, prod, qty, total, order_date, so_status="open", line_status="open",
             required_date=None, demand_class=None, delivered=0):
    so = SalesOrder(id=str(uuid.uuid4()), so_number=unique_code("SO"), customer_id=cust.id,
                    sales_agent_id=agent.id if agent else None, order_date=order_date,
                    status=so_status, demand_class=demand_class, company_id=DEFAULT_COMPANY_ID)
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(id=str(uuid.uuid4()), sales_order_id=so.id, product_id=prod.id,
                          qty_ordered=qty, qty_delivered=delivered, line_total=D(str(total)),
                          line_status=line_status, required_date=required_date,
                          company_id=DEFAULT_COMPANY_ID))
    db.flush()
    return so


# ================================================================ AC-RE-1 / 2 / 3: the filters


def test_ac_re_1_rank_sales_agents_for_a_product_prefix(client, db):
    """AC-RE-1: ZZTAA matches p1 and p2 only: A1 1000/10, A2 700/24, A3 50/1; A4 (August) absent."""
    w = _ranking_world(db)
    body = _ok(client, _full(db), group_by="sales_agent", top_n=10, product_code="zztaa")
    assert body["status"] == "ok" and body["basis"] == "delivered", body
    assert body["group_by"] == "sales_agent" and body["group_label"] == "Sales agent", body
    assert body["date_from"] == "2026-09-01" and body["date_to"] == "2026-09-30", body
    assert [r["rank"] for r in body["rows"]] == [1, 2, 3], body
    assert _rows(body) == [("ZZT-AG-1", 10, D("1000.00")), ("ZZT-AG-2", 24, D("700.00")),
                           ("ZZT-AG-3", 1, D("50.00"))], body["rows"]
    assert body["more"] == 0 and body["total_count"] == 3, body
    assert body["total"]["qty"] == 35 and money(body["total"]["amount"]) == D("1750.00"), body["total"]
    assert w.a4.sales_agent not in [r["name"] for r in body["rows"]]


def test_ac_re_2_rank_sales_agents_for_a_brand(client, db):
    """AC-RE-2: brand B is p3 only: A3 3000/30, A1 500/5."""
    w = _ranking_world(db)
    body = _ok(client, _full(db), group_by="sales_agent", top_n=10, brand_ids=[w.brand_b.id])
    assert _rows(body) == [("ZZT-AG-3", 30, D("3000.00")), ("ZZT-AG-1", 5, D("500.00"))], body["rows"]
    assert body["total_count"] == 2 and money(body["total"]["amount"]) == D("3500.00"), body


def test_ac_re_3_rank_sales_agents_for_a_category(client, db):
    """AC-RE-3: category X is p1 and p3: A3 3000/30, A1 1500/15, A2 600/20."""
    w = _ranking_world(db)
    body = _ok(client, _full(db), group_by="sales_agent", top_n=10, category_ids=[w.cat_x.id])
    assert _rows(body) == [("ZZT-AG-3", 30, D("3000.00")), ("ZZT-AG-1", 15, D("1500.00")),
                           ("ZZT-AG-2", 20, D("600.00"))], body["rows"]
    assert money(body["total"]["amount"]) == D("5100.00") and body["total"]["qty"] == 65, body["total"]


# ================================================================ AC-RE-4 to 7: ranking rules


def test_ac_re_4_top_n_cuts_rows_but_the_total_is_the_whole_set(client, db):
    """AC-RE-4: top_n=1 of 3 agents: 1 row, more=2, total_count=3, total = all three."""
    _ranking_world(db)
    body = _ok(client, _full(db), group_by="sales_agent", top_n=1)
    assert _rows(body) == [("ZZT-AG-3", 31, D("3050.00"))], body["rows"]
    assert body["more"] == 2 and body["total_count"] == 3, body
    assert money(body["total"]["amount"]) == D("5250.00") and body["total"]["qty"] == 70, body["total"]


def test_ac_re_5_sort_asc_ranks_lowest_first_and_skips_agents_without_a_sale(client, db):
    """AC-RE-5: asc = A2 700, A1 1500, A3 3050; A4 (only an August DO) is not listed."""
    _ranking_world(db)
    body = _ok(client, _full(db), group_by="sales_agent", top_n=10, sort="asc")
    assert [r["name"] for r in body["rows"]] == ["ZZT-AG-2", "ZZT-AG-1", "ZZT-AG-3"], body["rows"]
    assert [r["rank"] for r in body["rows"]] == [1, 2, 3], body["rows"]
    assert body["total_count"] == 3, body


def test_ac_re_6_measure_qty_ranks_by_quantity(client, db):
    """AC-RE-6: product ZZTAA: by amount A1, A2, A3; by qty A2 (24), A1 (10), A3 (1)."""
    _ranking_world(db)
    contact = _full(db)
    by_amount = _ok(client, contact, group_by="sales_agent", top_n=10, product_code="ZZTAA")
    assert [r["name"] for r in by_amount["rows"]] == ["ZZT-AG-1", "ZZT-AG-2", "ZZT-AG-3"], by_amount
    assert by_amount["measure"] == "amount", by_amount
    by_qty = _ok(client, contact, group_by="sales_agent", top_n=10, product_code="ZZTAA", measure="qty")
    assert by_qty["measure"] == "qty", by_qty
    assert [(r["name"], r["qty"]) for r in by_qty["rows"]] == [
        ("ZZT-AG-2", 24), ("ZZT-AG-1", 10), ("ZZT-AG-3", 1)], by_qty["rows"]


def test_ac_re_7_no_agent_is_one_row_and_the_rows_sum_to_the_total(client, db):
    """AC-RE-7: a DO with no sales order and a DO whose SO has no agent are ONE "(no agent)" row."""
    cust = seed_customer(db, name=unique_code("Cust"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    prod = _prod(db, "ZZTNOAG-1")
    agent = seed_agent(db, code="ZZT-AG-N")
    _sale(db, cust=cust, wh=wh, agent=agent, prod=prod, qty=1, total="10.00")
    _sale(db, cust=cust, wh=wh, agent=None, prod=prod, qty=2, total="20.00")  # SO without agent
    _sale(db, cust=cust, wh=wh, agent=None, prod=prod, qty=3, total="30.00", so=False)  # no SO
    db.commit()
    body = _ok(client, _full(db), group_by="sales_agent", top_n=10)
    assert _rows(body) == [("(no agent)", 5, D("50.00")), ("ZZT-AG-N", 1, D("10.00"))], body["rows"]
    assert sum(money(r["amount"]) for r in body["rows"]) == money(body["total"]["amount"]), body
    assert money(body["total"]["amount"]) == D("60.00"), body


# ================================================================ AC-RE-8: basis and echo


def test_ac_re_8_ordered_basis_ranks_so_lines_filed_by_so_date(client, db):
    """AC-RE-8: ordered value by SO date. A2's Aug SO (required date in Sep) is out, a cancelled
    SO and a cancelled line are out. A1 1000/10, A2 300/5, A3 200/2."""
    cust = seed_customer(db, name=unique_code("Cust"))
    prod = _prod(db, "ZZTORD-1")
    a1, a2, a3 = (seed_agent(db, code=f"ZZT-OA-{n}") for n in ("1", "2", "3"))
    kw = dict(cust=cust, prod=prod)
    _ordered(db, agent=a1, qty=10, total="1000.00", order_date=SEP, **kw)
    _ordered(db, agent=a2, qty=5, total="300.00", order_date=SEP, **kw)
    _ordered(db, agent=a2, qty=50, total="9999.00", order_date=AUG, required_date=date(2026, 9, 5), **kw)
    _ordered(db, agent=a3, qty=7, total="700.00", order_date=SEP, so_status="cancelled", **kw)
    _ordered(db, agent=a3, qty=8, total="800.00", order_date=SEP, line_status="cancelled", **kw)
    _ordered(db, agent=a3, qty=2, total="200.00", order_date=SEP, **kw)
    db.commit()
    contact = _full(db)
    body = _ok(client, contact, group_by="sales_agent", top_n=10, basis="ordered")
    assert body["basis"] == "ordered" and body["basis_label"] == "ordered sales", body
    assert _rows(body) == [("ZZT-OA-1", 10, D("1000.00")), ("ZZT-OA-2", 5, D("300.00")),
                           ("ZZT-OA-3", 2, D("200.00"))], body["rows"]
    assert money(body["total"]["amount"]) == D("1500.00") and body["total"]["qty"] == 17, body["total"]
    # No DOs exist here: the default (delivered) basis finds nothing on the same data.
    delivered = _ok(client, contact, group_by="sales_agent", top_n=10)
    assert delivered["basis"] == "delivered" and delivered["basis_label"] == "delivered sales", delivered
    assert delivered["rows"] == [] and delivered["total_count"] == 0, delivered


def test_ac_re_8_the_body_echoes_the_filters_by_name(client, db):
    """AC-RE-8: filters echo as {key, label, values:[names]}; the period is echoed."""
    w = _ranking_world(db)
    body = _ok(client, _full(db), group_by="sales_agent", top_n=3, brand_ids=[w.brand_b.id])
    assert {"key": "brand", "label": "Brand", "values": ["ZZT-BRAND-B"]} in body["filters"], body["filters"]
    assert body["date_from"] == "2026-09-01" and body["date_to"] == "2026-09-30", body


# ================================================================ AC-RE-9: every dimension


def test_ac_re_9_group_by_customer_with_a_brand_filter(client, db):
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    brand_a, brand_b = _brand(db, "ZZT-BR-A"), _brand(db, "ZZT-BR-B")
    pa, pb = _prod(db, "ZZTCU-A", brand=brand_a), _prod(db, "ZZTCU-B", brand=brand_b)
    x, y = seed_customer(db, name="ZZT CUST X"), seed_customer(db, name="ZZT CUST Y")
    _sale(db, cust=x, wh=wh, agent=None, prod=pa, qty=1, total="100.00")
    _sale(db, cust=y, wh=wh, agent=None, prod=pa, qty=3, total="300.00")
    _sale(db, cust=y, wh=wh, agent=None, prod=pb, qty=9, total="999.00")  # other brand
    db.commit()
    body = _ok(client, _full(db), group_by="customer", top_n=5, brand_ids=[brand_a.id])
    assert body["group_by"] == "customer", body
    assert _rows(body) == [("ZZT CUST Y", 3, D("300.00")), ("ZZT CUST X", 1, D("100.00"))], body["rows"]


def test_ac_re_9_group_by_location_with_a_product_code(client, db):
    cust = seed_customer(db, name=unique_code("Cust"))
    wh_a = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-LOC-A")
    wh_b = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-LOC-B")
    prod = _prod(db, "ZZTLOC-1")
    _sale(db, cust=cust, wh=wh_a, agent=None, prod=prod, qty=10, total="100.00")
    _sale(db, cust=cust, wh=wh_b, agent=None, prod=prod, qty=30, total="300.00")
    db.commit()
    body = _ok(client, _full(db), group_by="location", top_n=5, product_code="ZZTLOC")
    assert _rows(body) == [("ZZT-LOC-B", 30, D("300.00")), ("ZZT-LOC-A", 10, D("100.00"))], body["rows"]


def test_ac_re_9_group_by_month_with_a_sales_agent_filter(client, db):
    cust = seed_customer(db, name=unique_code("Cust"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    prod = _prod(db, "ZZTMON-1")
    john, other = seed_agent(db, code="ZZT-JOHN"), seed_agent(db, code="ZZT-OTHER")
    _sale(db, cust=cust, wh=wh, agent=john, prod=prod, qty=2, total="200.00", when=date(2026, 8, 3))
    _sale(db, cust=cust, wh=wh, agent=john, prod=prod, qty=4, total="400.00", when=SEP)
    _sale(db, cust=cust, wh=wh, agent=other, prod=prod, qty=99, total="9900.00", when=SEP)
    db.commit()
    body = _ok(client, _full(db), group_by="month", top_n=12, sales_agent_ids=[john.id],
               date_from="2026-08-01", date_to="2026-09-30")
    assert _rows(body) == [("2026-09", 4, D("400.00")), ("2026-08", 2, D("200.00"))], body["rows"]
    assert money(body["total"]["amount"]) == D("600.00"), body


def test_ac_re_9_group_by_brand(client, db):
    _ranking_world(db)
    body = _ok(client, _full(db), group_by="brand", top_n=5)
    assert _rows(body) == [("ZZT-BRAND-B", 35, D("3500.00")), ("ZZT-BRAND-A", 35, D("1750.00"))], body["rows"]
    assert body["group_label"] == "Brand", body


def test_ac_re_9_group_by_category(client, db):
    _ranking_world(db)
    body = _ok(client, _full(db), group_by="category", top_n=5)
    assert _rows(body) == [("ZZT-CAT-X", 65, D("5100.00")), ("ZZT-CAT-Y", 5, D("150.00"))], body["rows"]
    assert body["group_label"] == "Category", body


def test_ac_re_9_group_by_product(client, db):
    _ranking_world(db)
    body = _ok(client, _full(db), group_by="product", top_n=5)
    assert [r["name"] for r in body["rows"]] == ["ZZTBB-1", "ZZTAA-1", "ZZTAA-2"], body["rows"]


def test_ac_re_9_group_by_channel(client, db):
    seed_segment(db, code="ZZT-RETAIL")
    seed_segment(db, code="ZZT-PROJECT-X")
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    prod = _prod(db, "ZZTCH-1")
    retail = seed_customer(db, name="ZZT CH RETAIL", segment_code="ZZT-RETAIL")
    project = seed_customer(db, name="ZZT CH PROJECT", segment_code="ZZT-PROJECT-X")
    _sale(db, cust=retail, wh=wh, agent=None, prod=prod, qty=1, total="100.00")
    _sale(db, cust=project, wh=wh, agent=None, prod=prod, qty=3, total="300.00")
    db.commit()
    body = _ok(client, _full(db), group_by="channel", top_n=5)
    assert body["group_by"] == "channel", body
    assert [(r["qty"], money(r["amount"])) for r in body["rows"]] == [(3, D("300.00")), (1, D("100.00"))], body


# ================================================================ AC-RE-10 / 11: period, top_n


@pytest.mark.parametrize("missing", [("date_from",), ("date_to",), ("date_from", "date_to")])
def test_ac_re_10_period_is_required(client, db, missing):
    contact = _full(db)
    q = {**PERIOD, **_as_contact(contact), "group_by": "product", "top_n": 3}
    for key in missing:
        q.pop(key)
    resp = client.get(ROUTE, params=q, headers=KEY)
    assert resp.status_code == 422 and _code(resp) == "period_required", resp.text


def test_ac_re_11_group_by_without_top_n_is_422(client, db):
    resp = _ask(client, _full(db), group_by="sales_agent")
    assert resp.status_code == 422 and _code(resp) == "top_n_required", resp.text


def test_ac_re_11_no_group_by_and_no_top_n_is_the_number_shape(client, db):
    _ranking_world(db)
    body = _ok(client, _full(db))
    assert body["group_by"] is None and body["rows"] == [], body
    assert body["total"]["qty"] == 70 and money(body["total"]["amount"]) == D("5250.00"), body["total"]


# ================================================================ 422 codes


@pytest.mark.parametrize(
    "params, code",
    [
        ({"group_by": "colour", "top_n": 3}, "unknown_group_by"),
        ({"group_by": "product", "top_n": 3, "basis": "invoiced"}, "unknown_basis"),
        ({"group_by": "product", "top_n": 3, "measure": "profit"}, "unknown_measure"),
        ({"group_by": "product", "top_n": 3, "sort": "sideways"}, "unknown_sort"),
        ({"group_by": "product", "top_n": 0}, "top_n_out_of_range"),
        ({"group_by": "product", "top_n": 101}, "top_n_out_of_range"),
        ({"group_by": "product", "top_n": 3, "channel": "retail"}, "invalid_channel"),
        ({"group_by": "product", "top_n": 3, "date_from": "2026-10-01", "date_to": "2026-09-01"},
         "date_range_inverted"),
    ],
)
def test_ac_re_17_validation_codes(client, db, params, code):
    resp = _ask(client, _full(db), **params)
    assert resp.status_code == 422, resp.text
    assert _code(resp) == code, resp.text


def test_contact_identity_pair_is_required(client, db):
    contact = _full(db)
    resp = client.get(ROUTE, params={**PERIOD, "contact_id": contact.id, "group_by": "product", "top_n": 3},
                      headers=KEY)
    assert resp.status_code == 422 and _code(resp) == "contact_identity_required", resp.text
    resp = client.get(ROUTE, params={**PERIOD, "space_id": "zzt-space"}, headers=KEY)
    assert resp.status_code == 422 and _code(resp) == "contact_identity_required", resp.text


def test_a_request_without_an_api_key_is_403(client, db):
    resp = _ask(client, _full(db), headers={}, group_by="product", top_n=3)
    assert resp.status_code == 403 and _code(resp) == "api_key_required", resp.text


# ================================================================ AC-RE-12: the grant


def test_ac_re_12_a_contact_without_the_grant_is_refused(client, db):
    contact = _contact(db, granted=False)
    db.commit()
    resp = _ask(client, contact, group_by="product", top_n=3)
    assert resp.status_code == 403 and _code(resp) == "sales_report_not_enabled", resp.text


def test_ac_re_12_an_unknown_contact_is_refused(client, db):
    resp = client.get(ROUTE, params={**PERIOD, "contact_id": str(uuid.uuid4()), "space_id": "zzt-space",
                                     "group_by": "product", "top_n": 3}, headers=KEY)
    assert resp.status_code == 403 and _code(resp) == "sales_report_not_enabled", resp.text


# ================================================================ AC-RE-13 / 14 / 15: audiences


def _dealer(db, w):
    contact = _contact(db)
    _link(db, contact, w.cust)
    db.commit()
    return contact


@pytest.mark.parametrize("group_by", ["sales_agent", "location", "customer", "channel"])
def test_ac_re_13_a_dealer_may_not_group_by_staff_dimensions(client, db, group_by):
    w = _ranking_world(db)
    resp = _ask(client, _dealer(db, w), group_by=group_by, top_n=3)
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["code"] == "report_dimension_not_allowed", body
    assert DEALER_MESSAGE in resp.text, body


@pytest.mark.parametrize(
    "extra",
    [
        {"sales_agent_ids": [str(uuid.uuid4())]},
        {"warehouse_codes": ["ZZT-ANY-WH"]},
        {"channel": "dealer"},
    ],
)
def test_ac_re_13_a_dealer_may_not_filter_by_staff_dimensions(client, db, extra):
    w = _ranking_world(db)
    resp = _ask(client, _dealer(db, w), group_by="product", top_n=3, **extra)
    assert resp.status_code == 403 and _code(resp) == "report_dimension_not_allowed", resp.text
    assert DEALER_MESSAGE in resp.text, resp.text


@pytest.mark.parametrize("group_by", ["product", "brand", "category", "month"])
def test_ac_re_13_a_dealer_may_group_by_product_brand_category_month(client, db, group_by):
    w = _ranking_world(db)
    body = _ok(client, _dealer(db, w), group_by=group_by, top_n=3)
    assert body["group_by"] == group_by and body["total_count"] >= 1, body


def test_ac_re_14_a_dealer_sees_only_its_own_customers_figures(client, db):
    w = _ranking_world(db)
    other = seed_customer(db, name=unique_code("Other"))
    _sale(db, cust=other, wh=w.wh, agent=w.a1, prod=w.p1, qty=500, total="50000.00")
    contact = _dealer(db, w)
    body = _ok(client, contact, group_by="product", top_n=10)
    assert body["total"]["qty"] == 70 and money(body["total"]["amount"]) == D("5250.00"), body["total"]


def test_ac_re_14_a_dealer_naming_another_customer_is_refused(client, db):
    w = _ranking_world(db)
    other = seed_customer(db, name=unique_code("Other"))
    db.commit()
    resp = _ask(client, _dealer(db, w), group_by="product", top_n=3, customer_ids=[other.id])
    assert resp.status_code == 403 and _code(resp) == "customer_not_permitted", resp.text


def test_ac_re_15_a_grant_holder_with_no_links_may_rank_sales_agents(client, db):
    _ranking_world(db)
    body = _ok(client, _full(db), group_by="sales_agent", top_n=3)
    assert body["group_by"] == "sales_agent" and body["total_count"] == 3, body


def test_ac_re_15_an_office_contact_linked_to_a_customer_is_not_a_dealer(client, db):
    w = _ranking_world(db)
    contact = _contact(db)
    _link(db, contact, w.cust)
    _access(db, contact, "Sorento Office")
    db.commit()
    body = _ok(client, contact, group_by="sales_agent", top_n=3)
    assert body["group_by"] == "sales_agent" and body["total_count"] == 3, body


# ================================================================ AC-RE-16: company scope


def test_ac_re_16_another_companys_dos_are_not_counted(client, db):
    mocha = seed_mocha(db)
    shared = unique_code("ZZTCO", alpha=True)
    cust = seed_customer(db, name=unique_code("Cust"))
    mocha_cust = seed_customer(db, name=unique_code("MochaCust"), company_id=mocha.id)
    prod_a = _prod(db, shared)
    prod_b = product(db, company_id=mocha.id, code=shared)
    wh_a = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    wh_b = warehouse(db, company_id=mocha.id)
    seed_do(db, customer_id=cust.id, order_date=SEP, source_book="db1",
            lines=[line(prod_a.id, wh_a.id, 10, price=D("1"), total=D("100.00"))])
    seed_do(db, customer_id=mocha_cust.id, order_date=SEP, source_book="db1", company_id=mocha.id,
            lines=[line(prod_b.id, wh_b.id, 500, price=D("1"), total=D("5000.00"))])
    db.commit()
    body = _ok(client, _full(db), product_code=shared)
    assert body["total"]["qty"] == 10 and money(body["total"]["amount"]) == D("100.00"), body["total"]


# ================================================================ AC-RE-17: empty resolution


def test_ac_re_17_a_product_code_matching_nothing_is_404(client, db):
    resp = _ask(client, _full(db), group_by="product", top_n=3, product_code="ZZTNOSUCHPRODUCT")
    assert resp.status_code == 404, resp.text
    assert resp.json().get("code") == "NOT_FOUND", resp.text  # not the missing route's bare 404


def test_ac_re_17_warehouse_codes_naming_no_warehouse_is_zero_rows(client, db):
    _ranking_world(db)
    body = _ok(client, _full(db), group_by="sales_agent", top_n=3, warehouse_codes=["ZZT-NO-SUCH-WH"])
    assert body["status"] == "ok" and body["rows"] == [] and body["total_count"] == 0, body
    assert body["total"]["qty"] == 0 and money(body["total"]["amount"]) == D("0.00"), body["total"]


# ================================================================ location policy


def test_a_named_location_outside_the_policy_is_refused(client, db):
    w = _ranking_world(db)
    barred = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="ZZT-BARRED")
    contact = _contact(db)
    seed_policy(db, contact, excluded_warehouse_ids=[barred.id])
    db.commit()
    body = _ok(client, contact, group_by="sales_agent", top_n=3, warehouse_codes=["ZZT-BARRED"])
    assert body["status"] == "refused", body
    assert body["message"] == "Sorry, ZZT-BARRED isn't one of the locations you can check.", body
    assert w is not None


# ================================================================ AC-RE-20: parity with sales-report


def _parity_world(db):
    c1, c2 = seed_customer(db, name="ZZT PAR ONE"), seed_customer(db, name="ZZT PAR TWO")
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    pa, pb, pc = (_prod(db, f"ZZTPAR-{n}") for n in "ABC")
    a1, a2 = seed_agent(db, code="ZZT-PAR-AG1"), seed_agent(db, code="ZZT-PAR-AG2")
    # Legacy DO: the DOC total 1000.01 is repeated on every line and must count once, split.
    so1 = seed_so(db, customer_id=c1.id, agent_id=a1.id)
    seed_do(db, customer_id=c1.id, order_date=SEP, source_book=None, sales_order_id=so1.id,
            lines=[line(pa.id, wh.id, 1, price=D("10"), total=D("1000.01")),
                   line(pb.id, wh.id, 2, price=D("10"), total=D("1000.01")),
                   line(pc.id, wh.id, 3, price=D("10"), total=D("1000.01"))])
    # AutoCount DO of another customer and agent.
    so2 = seed_so(db, customer_id=c2.id, agent_id=a2.id)
    seed_do(db, customer_id=c2.id, order_date=SEP, source_book="db1", sales_order_id=so2.id,
            lines=[line(pa.id, wh.id, 4, price=D("10"), total=D("250.50")),
                   line(pb.id, wh.id, 5, price=D("10"), total=D("100.25"))])
    # A DO with no sales order.
    seed_do(db, customer_id=c2.id, order_date=SEP, source_book="db1",
            lines=[line(pc.id, wh.id, 6, price=D("10"), total=D("33.33"))])
    db.commit()


@pytest.mark.parametrize("group_by", ["customer", "product", "sales_agent"])
def test_ac_re_20_report_ask_equals_the_sales_report_to_the_sen(client, db, group_by):
    _parity_world(db)
    contact = _full(db)
    ask = _ok(client, contact, group_by=group_by, top_n=100, product_code="ZZTPAR")
    resp = client.get(SALES_REPORT, params={"product_code": "ZZTPAR", "group_by": group_by,
                                            "date_from": "2026-09-01", "date_to": "2026-09-30"})
    assert resp.status_code == 200, resp.text
    old = resp.json()
    assert len(old["rows"]) <= 10, old["rows"]
    assert {r["name"]: (r["qty"], money(r["amount"])) for r in ask["rows"]} == {
        r["name"]: (r["qty"], money(r["amount"])) for r in old["rows"]}, (ask["rows"], old["rows"])
    assert ask["total"]["qty"] == old["total"]["qty"], (ask["total"], old["total"])
    assert money(ask["total"]["amount"]) == money(old["total"]["amount"]), (ask["total"], old["total"])
