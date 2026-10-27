"""SALES-UNIFIED S4/S5: every other sales figure tallies with the reports (AC-25, AC-26, AC-28,
AC-30) and the chatbot's report ask on the invoiced basis (contract section 7).

Two harnesses, kept apart by fixture name:
* `db` / `client` (top selling's superadmin client) for `/order-management/top-selling` and
  `/order-management/report-ask`;
* `adb` + `analysis_client` (API key + contact grant, the chatbot's seam) for
  `/api/v1/sales/analysis`.

Fictional codes only (`ZZT`), every row seeded here.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.main import app  # noqa: F401  (import order)
from app.models.base import set_company_scope
from app.models.sales import SetApartCustomer
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import product, seed_mocha, warehouse
from tests._pg_fixture import blank_session, unique_code
from tests._sales_unified_seed import (
    ALL_TYPES, D, JAN, SALES_TYPE_LABELS, agent, by_type, cust, delivery, doc, grand, line, run, so,
)
from tests.test_sales_analysis_route import (  # noqa: F401  (queue and _no_cloud are fixtures)
    _actor,
    _client as analysis_client,
    _contact as analysis_contact,
    _mark_ready,
    _no_cloud,
    _patch_wait,
    queue,
)
from tests.test_top_selling_report import (  # noqa: F401  (db and client are fixtures)
    _access,
    _as_contact,
    _contact,
    _line as order_line,
    _product,
    client,
    db,
)

JAN15 = date(2026, 1, 15)
TOP = "/api/v1/order-management/top-selling"
ASK = "/api/v1/order-management/report-ask"
ANALYSIS = "/api/v1/sales/analysis"
KEY = {"X-API-Key": "k"}
PERIOD = {"date_from": "2026-01-01", "date_to": "2026-01-31"}


@pytest.fixture
def adb():
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        yield s


# ------------------------------------------------------------------ the January fixture


def _january(db) -> SimpleNamespace:
    """A fixture shaped like January 2026 (AC-28), fictional codes.

    Dealer: IV 1000.00 (agent A, via a DO to a retail SO) + DN 14.26 (agent A, no lines, against
    that invoice). Project team: IV 2000.00 (agent B, via a DO to a project SO) less CN 300.00
    (against it). Set apart: two debtors, 500.00 and 700.00 (their SOs are retail / project).
    Mixed 80.00, type not set 60.00. No sales order: a cash sale 200.00 under an agent code with
    no agent row, and one 40.00 with no agent at all. Noise: a cancelled invoice and a February
    one.
    """
    a, b = agent(db, unique_code("ZZTAGA")), agent(db, unique_code("ZZTAGB"))
    dealer_c = cust(db, debtor_type="ZZTDLR", agent_row=a)
    project_c = cust(db, debtor_type="ZZTPRJ", agent_row=b)
    p1, p2, p3 = (product(db, company_id=DEFAULT_COMPANY_ID) for _ in range(3))

    _h, (retail_line,) = so(db, demand_class="retail", customer=dealer_c)
    do_retail = delivery(db, so_line=retail_line)
    iv_dealer = doc(db, "invoice", "1000.00", JAN15, customer=dealer_c, agent_row=a,
                    lines=[line(qty="10", prod=p1, from_type="DO", from_no=do_retail.order_number)])
    doc(db, "debit_note", "14.26", JAN15, customer=dealer_c, agent_row=a, against=iv_dealer)

    _h, (project_line,) = so(db, demand_class="project", customer=project_c)
    do_project = delivery(db, so_line=project_line)
    iv_project = doc(db, "invoice", "2000.00", JAN15, customer=project_c, agent_row=b,
                     lines=[line(qty="4", prod=p2, from_type="DO", from_no=do_project.order_number)])
    doc(db, "credit_note", "300.00", JAN15, customer=project_c, agent_row=b, against=iv_project)

    for net, demand in (("500.00", "retail"), ("700.00", "project")):
        sa_c = cust(db, debtor_type="ZZTSET")
        db.add(SetApartCustomer(company_id=DEFAULT_COMPANY_ID, customer_id=sa_c.id,
                                from_month=date(2026, 1, 1), to_month=date(2026, 1, 1)))
        db.flush()
        _h, (sa_line,) = so(db, demand_class=demand, customer=sa_c)
        doc(db, "invoice", net, JAN15, customer=sa_c, agent_row=a, lines=[line(so_line=sa_line, prod=p3)])

    _h, (r_line,) = so(db, demand_class="retail")
    _h, (pr_line,) = so(db, demand_class="project")
    doc(db, "invoice", "80.00", JAN15, customer=dealer_c, agent_row=a,
        lines=[line(net="50.00", so_line=r_line, prod=p3), line(net="30.00", so_line=pr_line, prod=p3)])
    _h, (untyped,) = so(db, demand_class=None)
    doc(db, "invoice", "60.00", JAN15, customer=project_c, agent_row=b, lines=[line(so_line=untyped, prod=p3)])

    doc(db, "cash_sale", "200.00", JAN15, agent_code="ZZT-NOROW", lines=[line(qty="2", prod=p1)])
    doc(db, "cash_sale", "40.00", JAN15)

    doc(db, "invoice", "9999.00", JAN15, customer=dealer_c, agent_row=a, status="cancelled")
    doc(db, "invoice", "5.00", date(2026, 2, 1), customer=dealer_c, agent_row=a)
    db.commit()
    return SimpleNamespace(
        buckets={
            SALES_TYPE_LABELS["dealer"]: D("1014.26"),
            SALES_TYPE_LABELS["project"]: D("1700.00"),
            SALES_TYPE_LABELS["set_apart"]: D("1200.00"),
            SALES_TYPE_LABELS["mixed"]: D("80.00"),
            SALES_TYPE_LABELS["type_not_set"]: D("60.00"),
            SALES_TYPE_LABELS["no_sales_order"]: D("240.00"),
        },
        total=D("4294.26"),
        agents=(a, b),
        products=(p1, p2, p3),
    )


# ------------------------------------------------------------------------------ AC-28


def test_ac_28_the_six_buckets_of_a_january_shaped_month_sum_to_all_sales(db):
    world = _january(db)
    buckets = by_type(db)
    assert buckets == world.buckets
    assert sum(buckets.values()) == world.total
    assert grand(run(db, "sales_by_debtor_type")) == world.total


def test_ac_28_the_agent_with_no_agent_row_and_the_document_with_no_agent_both_show(db):
    world = _january(db)
    result = run(db, "sales_by_debtor_type")
    rows = result.layouts.summary.row_totals
    assert D(rows["ZZT-NOROW"]["sales_value"]) == D("200.00")
    assert D(rows["(blank)"]["sales_value"]) == D("40.00")
    assert sum(D(v["sales_value"]) for v in rows.values()) == world.total


# ------------------------------------------------------------------------------ AC-25


def _get_top(client, **params):
    merged = {**PERIOD, "rank_by": "quantity", **params}
    return client.get(TOP, params={k: v for k, v in merged.items() if v is not None})


def _engine_items(db, **kw):
    result = run(db, "top_selling_items", rows="item", cols="year",
                 measures=("quantity", "sales_value", "documents"), **kw)
    return {label.split(" - ")[0]: (D(t["quantity"]), D(t["sales_value"]))
            for label, t in result.layouts.summary.row_totals.items()}


def test_ac_25_top_selling_with_no_basis_is_the_invoiced_figure(client, db):
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    doc(db, "invoice", "250.00", JAN15, lines=[line(qty="5", net="250.00", prod=p)])
    doc(db, "credit_note", "100.00", JAN15, lines=[line(qty="2", net="100.00", prod=p)])
    db.commit()
    resp = _get_top(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["basis"] == "invoiced"
    [row] = body["rows"]
    assert row["code"] == p.product_code
    assert (D(str(row["quantity"])), D(str(row["amount"]))) == (D("3"), D("150.00"))
    assert _engine_items(db) == {p.product_code: (D("3"), D("150.00"))}


@pytest.mark.parametrize("basis", ["ordered", "delivered"])
def test_ac_25_the_order_bases_still_answer_from_the_sales_order_lines(client, db, basis):
    p = _product(db, "ZZTORD-A")
    order_line(db, product_id=p.id, ordered=3, delivered=3, line_total=D("90.00"),
               order_date=date(2026, 1, 10))
    doc(db, "invoice", "999.00", JAN15, lines=[line(qty="9", net="999.00", prod=product(db, company_id=DEFAULT_COMPANY_ID))])
    db.commit()
    resp = _get_top(client, basis=basis)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["basis"] == basis
    assert [r["code"] for r in body["rows"]] == ["ZZTORD-A"]
    assert D(str(body["rows"][0]["amount"])) == D("90.00")


def test_ac_25_grouping_by_category_has_no_invoiced_answer(client, db):
    resp = _get_top(client, basis="invoiced", group="category")
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "group_needs_order_basis"


# ------------------------------------------------------------------------------ AC-26 / AC-30 (analysis)


def _aq(contact, **extra):
    params = {"contact_id": contact.respond_io_id, "space_id": "364817", "rows": "agent",
              "cols": "debtor_type", "date_from": "2026-01-01", "date_to": "2026-01-31"}
    params.update(extra)
    return {k: v for k, v in params.items() if v is not None}


def _analysis(adb, queue, monkeypatch, **extra):
    contact = analysis_contact(adb)
    _patch_wait(monkeypatch, _mark_ready(adb))
    with analysis_client(adb, _actor(adb), [DEFAULT_COMPANY_ID]) as c:
        return c.get(ANALYSIS, params=_aq(contact, **extra))


def test_ac_26_basis_absent_is_invoiced_on_the_default_month_by_year_axes(adb, queue, monkeypatch):
    doc(adb, "invoice", "60.00", JAN15)
    resp = _analysis(adb, queue, monkeypatch, rows="month", cols="year",
                     date_from="2025-01-01", date_to="2026-09-26")
    assert resp.status_code == 200, resp.text
    assert "invoiced" in resp.json()["basis"].lower()
    (_fn, args, _kw), = queue
    _download_id, key, params, _view, _user = args
    assert key == "sales_yearly" and params["basis"] == ["invoiced"]


def test_ac_26_agent_by_debtor_type_runs_on_invoiced_and_answers_the_sales_by_debtor_type_figures(
    adb, queue, monkeypatch
):
    a = agent(adb, unique_code("ZZTAG"))
    typed = cust(adb, debtor_type="ZZTT1")
    doc(adb, "cash_sale", "75.00", JAN15, customer=typed, agent_row=a)
    resp = _analysis(adb, queue, monkeypatch, basis="invoiced")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows_label"].lower() in ("sales agent", "agent")
    assert "ZZTT1" in body["columns"]
    assert [(r["label"], r["total"]) for r in body["rows"]] == [(a.sales_agent, "75.00")]
    (_fn, args, _kw), = queue
    assert args[1] == "sales_by_debtor_type"


@pytest.mark.parametrize("basis", ["delivered", "ordered"])
@pytest.mark.parametrize("axes", [{"rows": "agent", "cols": "year"}, {"rows": "month", "cols": "debtor_type"}])
def test_ac_26_agent_and_debtor_type_axes_are_422_on_the_order_bases(adb, queue, monkeypatch, basis, axes):
    resp = _analysis(adb, queue, monkeypatch, basis=basis, **axes)
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "axis_needs_invoiced"
    assert not queue


@pytest.mark.parametrize("channel", ALL_TYPES)
def test_ac_26_channel_accepts_the_six_sales_type_values_on_invoiced(adb, queue, monkeypatch, channel):
    resp = _analysis(adb, queue, monkeypatch, basis="invoiced", channel=channel)
    assert resp.status_code == 200, resp.text


def _route_rows(body):
    return {r["label"]: D(r["total"]) for r in body["rows"]}


@pytest.mark.parametrize("channel", [None, "dealer", "no_sales_order"])
def test_ac_30_analysis_by_agent_and_debtor_type_equals_the_sales_by_debtor_type_run_to_the_cent(
    adb, queue, monkeypatch, channel
):
    world = _january(adb)
    resp = _analysis(adb, queue, monkeypatch, basis="invoiced", channel=channel)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    extra = {"channel": [channel]} if channel else {}
    engine_result = run(adb, "sales_by_debtor_type", **extra)
    engine_rows = {k: D(v["sales_value"]) for k, v in engine_result.layouts.summary.row_totals.items()}
    engine_total = D(engine_result.layouts.summary.grand_total["sales_value"])

    assert D(body["totals"]["total"]) == engine_total
    if channel is None:
        assert engine_total == world.total
    route_rows = _route_rows(body)
    none_labels = ("(blank)", "(no agent)")
    assert {k: v for k, v in route_rows.items() if k not in none_labels} == {
        k: v for k, v in engine_rows.items() if k not in none_labels}
    assert sum(v for k, v in route_rows.items() if k in none_labels) == sum(
        v for k, v in engine_rows.items() if k in none_labels)


# ------------------------------------------------------------------------------ AC-30 (items)


def test_ac_30_top_selling_invoiced_rows_equal_the_top_selling_items_report(client, db):
    world = _january(db)
    resp = _get_top(client, basis="invoiced", rank_by="amount")
    assert resp.status_code == 200, resp.text
    route = {r["code"]: (D(str(r["quantity"])), D(str(r["amount"]))) for r in resp.json()["rows"]}
    engine_items = _engine_items(db)
    assert route == engine_items
    p1, p2, p3 = world.products
    assert engine_items[p1.product_code] == (D("12"), D("1200.00"))
    assert engine_items[p2.product_code] == (D("4"), D("2000.00"))


def test_ac_30_the_agent_and_channel_filters_map_onto_the_report_params(client, db):
    world = _january(db)
    a, _b = world.agents
    resp = _get_top(client, basis="invoiced", rank_by="amount", sales_agent_ids=[a.id], channel="dealer")
    assert resp.status_code == 200, resp.text
    route = {r["code"]: (D(str(r["quantity"])), D(str(r["amount"]))) for r in resp.json()["rows"]}
    assert route == _engine_items(db, agent=[a.id], channel=["dealer"])
    assert route, "agent A's dealer lines are not empty"


# ------------------------------------------------------------------------------ AC-30 (report ask)


def _ask(client, contact, **params):
    q = {**PERIOD, **_as_contact(contact), **params}
    return client.get(ASK, params={k: v for k, v in q.items() if v is not None}, headers=KEY)


def _staff(db):
    contact = _contact(db)
    _access(db, contact, "Sorento Office")
    db.commit()
    return contact


def test_ac_30_report_ask_invoiced_by_product_equals_the_top_selling_items_report(client, db):
    _january(db)
    resp = _ask(client, _staff(db), basis="invoiced", group_by="product", measure="amount", top_n=50)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["basis"] == "invoiced"
    route = {r["name"]: D(str(r["amount"])) for r in body["rows"]}
    assert route == {code: amount for code, (_qty, amount) in _engine_items(db).items()}


def test_report_ask_with_no_basis_answers_invoiced(client, db):
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    doc(db, "invoice", "70.00", JAN15, lines=[line(qty="1", net="70.00", prod=p)])
    db.commit()
    resp = _ask(client, _staff(db), group_by="product", measure="amount", top_n=5)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["basis"] == "invoiced"
    assert [(r["name"], D(str(r["amount"]))) for r in body["rows"]] == [(p.product_code, D("70.00"))]


def test_report_ask_invoiced_with_a_location_filter_is_422_location_needs_order_basis(client, db):
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("ZZT-WH"))
    db.commit()
    resp = _ask(client, _staff(db), basis="invoiced", group_by="product", measure="amount", top_n=5,
                warehouse_codes=[wh.warehouse_code])
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "location_needs_order_basis"
