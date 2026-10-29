"""REPORT-OUTSTANDING-SUMMARY (29 Oct 2026): the outstanding SUMMARY on `GET /order-management/report-ask`.

`documentation/plans/reports/report-outstanding-summary-behaviour-card.md`. #1922 left an outstanding kind with one
total; the pre-#1922 tool printed counts, the quantity lines, the date range, By location and By customer (or By
product). The route now adds a `summary` block, every figure from the same engine run (`reports.ask.run_ask`), when
the basis is undelivered orders or pending delivery, nothing is grouped or compared, and a product or customer is
named (the old tool's subjects; R13: a product gets By customer, a customer gets By product, both get neither).

Postgres only; every row is seeded here.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import unique_code
from tests._report_ask_so_seed import seed_so_line
from tests._report_unify_seed import make_product
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    client,
    db,
    money,
    seed_customer,
    warehouse,
)
from tests.test_report_unify_outstanding_bases import _ok, _pending_world, _staff

D = Decimal


def _rows(rows):
    return [(r["name"], r["qty"], money(r["amount"])) for r in rows]


def _group(summary, axis):
    return next(g["rows"] for g in summary["groups"] if g["axis"] == axis)


# ================================================================ pending delivery (the prod turn's kind)


def test_pending_delivery_for_a_product_carries_the_summary_with_by_location_and_by_customer(client, db):
    """pC, every date: DO1 (C1, Sep, W2 2 / 200) and DO4 (C1, Aug, W2 1 / 100); the delivered DO3 is pA only."""
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id], period=None)
    s = body["summary"]
    assert s["documents"] == 2, s
    assert (s["qty"], money(s["amount"])) == (3, D("300.00")), s
    assert (s["date_first"], s["date_last"]) == ("2026-08-15", "2026-09-10"), s
    assert [g["axis"] for g in s["groups"]] == ["location", "customer"], s
    assert _rows(_group(s, "location")) == [(w.w2.warehouse_code, 3, D("300.00"))], s
    assert _rows(_group(s, "customer")) == [(w.c1.customer_name, 3, D("300.00"))], s
    # The summary is the total's own population.
    assert (body["total"]["qty"], money(body["total"]["amount"])) == (s["qty"], money(s["amount"]))


def test_pending_delivery_for_a_customer_breaks_down_by_product(client, db):
    """C1, every date: DO1 (pA W1 3, pC W2 2), DO4 (pC W2 1). The delivered DO3 is in nothing."""
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", customer_ids=[w.c1.id], period=None)
    s = body["summary"]
    assert s["documents"] == 2, s
    assert (s["qty"], money(s["amount"])) == (6, D("600.00")), s
    assert sorted(_rows(_group(s, "location"))) == sorted(
        [(w.w1.warehouse_code, 3, D("300.00")), (w.w2.warehouse_code, 3, D("300.00"))]
    ), s
    assert [g["axis"] for g in s["groups"]] == ["location", "product"], s
    assert sorted(_rows(_group(s, "product"))) == sorted(
        [(w.pa.product_code, 3, D("300.00")), (w.pc.product_code, 3, D("300.00"))]
    ), s


def test_pending_delivery_naming_product_and_customer_has_by_location_only(client, db):
    w = _pending_world(db)
    body = _ok(
        client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id], customer_ids=[w.c1.id], period=None
    )
    s = body["summary"]
    assert [g["axis"] for g in s["groups"]] == ["location"], s
    assert _rows(_group(s, "location")) == [(w.w2.warehouse_code, 3, D("300.00"))], s


def test_a_period_narrows_the_summary_like_the_total(client, db):
    """September only: pC is DO1 alone."""
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id])
    s = body["summary"]
    assert (s["documents"], s["qty"], s["date_first"], s["date_last"]) == (1, 2, "2026-09-10", "2026-09-10"), s


# ================================================================ undelivered orders


def test_undelivered_orders_for_a_customer_carry_ordered_and_the_open_lines_only(client, db):
    """Two open lines (10 ordered / 4 delivered, 5 / 0) and one fully delivered line (8 / 8): the delivered line is in
    no figure, so Ordered 15, Outstanding 11, Transferred (15 - 11) 4. Dated by the SO's own order date."""
    cust = seed_customer(db, name=unique_code("Cust"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WS"))
    p1, p2, p3 = (make_product(db, unique_code(s)) for s in ("S1", "S2", "S3"))
    seed_so_line(db, cust=cust, prod=p1, qty=10, delivered=4, total="1000.00", wh=wh, order_date=date(2026, 8, 5))
    seed_so_line(db, cust=cust, prod=p2, qty=5, delivered=0, total="500.00", wh=wh, order_date=date(2026, 9, 20))
    seed_so_line(db, cust=cust, prod=p3, qty=8, delivered=8, total="800.00", wh=wh, order_date=date(2025, 1, 1))
    db.commit()
    body = _ok(client, _staff(db), basis="outstanding", customer_ids=[cust.id], period=None)
    s = body["summary"]
    assert s["documents"] == 2, s
    assert (s["ordered_qty"], s["qty"], money(s["amount"])) == (15, 11, D("1100.00")), s
    assert (s["date_first"], s["date_last"]) == ("2026-08-05", "2026-09-20"), s
    assert [(r["name"], r["ordered_qty"], r["qty"]) for r in _group(s, "location")] == [(wh.warehouse_code, 15, 11)], s
    assert [(r["name"], r["ordered_qty"], r["qty"]) for r in _group(s, "product")] == [
        (p1.product_code, 10, 6), (p2.product_code, 5, 5)
    ], s


# ================================================================ no summary


def test_no_subject_no_summary(client, db):
    _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", period=None)
    assert body.get("summary") is None, body


def test_a_brand_alone_is_a_filter_not_a_subject(client, db):
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", brand_ids=[w.brand_b.id], period=None)
    assert body.get("summary") is None, body


def test_a_breakdown_with_no_subject_carries_no_summary(client, db):
    _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", group_by="customer", top_n=10, period=None)
    assert body.get("summary") is None, body


def test_a_sales_basis_carries_no_summary(client, db):
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="ordered", product_ids=[w.pc.id])
    assert body.get("summary") is None, body


# ================================================================ the delivery order list (the offer's target)


def test_pending_delivery_groups_by_delivery_order(client, db):
    """The list the "Reply 1 for the delivery order list." offer runs: the held ask grouped by delivery order."""
    w = _pending_world(db)
    body = _ok(
        client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id], group_by="delivery_order", top_n=50,
        period=None,
    )
    assert body["group_by"] == "delivery_order", body
    assert len(body["rows"]) == 2 and sum(r["qty"] for r in body["rows"]) == 3, body["rows"]
    assert body.get("summary") is None, body  # review B1: the list is the list, never the summary again


def test_the_sales_order_list_carries_no_summary(client, db):
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="outstanding", customer_ids=[w.c1.id], group_by="sales_order", top_n=50, period=None)
    assert body.get("summary") is None, body


def test_a_named_axis_keeps_the_asks_order_count_and_a_month_trend_reads_by_date(client, db):
    """Review S1: "bottom 1 customer" is the bottom one; "by month" lists months oldest first."""
    w = _pending_world(db)
    staff = _staff(db)
    asc = _ok(client, staff, basis="pending_delivery", brand_ids=[w.brand_a.id], product_ids=[w.pa.id, w.pb.id],
              group_by="customer", top_n=1, sort="asc", period=None)
    assert [r["name"] for r in _group(asc["summary"], "customer")] == [w.c1.customer_name], asc["summary"]
    months = _ok(client, staff, basis="pending_delivery", customer_ids=[w.c1.id], group_by="month", top_n=1000, period=None)
    names = [r["name"] for r in _group(months["summary"], "month")]
    assert names == sorted(names) and len(names) == 2, names


# ================================================================ owner 29 Oct: pending delivery without the reveal


from tests.test_report_unify_outstanding_bases import _ask, _holder  # noqa: E402
from tests._sales_report_do_seed import _link  # noqa: E402


def test_office_staff_without_the_outstanding_reveal_see_pending_delivery_but_not_undelivered_orders(client, db):
    """Owner 29 Oct (#b6e9): pre-#1922 the DO half needed no reveal and the SO half needed `sales_orders.outstanding`.
    An office contact with no reveal at all sees every pending delivery; undelivered orders and unpaid stay refused."""
    w = _pending_world(db)
    contact = _holder(db)  # office, no reveal
    body = _ok(client, contact, basis="pending_delivery", product_ids=[w.pc.id], period=None)
    assert body["total"]["qty"] == 3 and _group(body["summary"], "customer"), body
    for basis in ("outstanding", "unpaid"):
        resp = _ask(client, contact, basis=basis, period=None)
        assert resp.status_code == 403 and resp.json()["code"] == "outstanding_not_enabled", (basis, resp.text)


def test_a_linked_contact_without_the_reveal_sees_only_its_own_pending_delivery(client, db):
    w = _pending_world(db)
    contact = _holder(db, office=False)
    _link(db, contact, w.c1)
    db.commit()
    body = _ok(client, contact, basis="pending_delivery", period=None)
    assert body["total"]["qty"] == 6, body  # C1 only (pA 3, pC 2 + 1); C2's 9 is not its own
    assert _ask(client, contact, basis="pending_delivery", customer_ids=[w.c2.id], period=None).status_code == 403


def test_an_unlinked_non_staff_contact_without_the_reveal_is_still_refused_pending_delivery(client, db):
    """Never every customer's deliveries to a contact the company does not know (V1-DOC-SCOPE's own rule)."""
    _pending_world(db)
    contact = _holder(db, office=False)
    resp = _ask(client, contact, basis="pending_delivery", period=None)
    assert resp.status_code == 403 and resp.json()["code"] == "outstanding_not_enabled", resp.text


# ================================================================ owner 29 Oct Q2: the user's own axes and filters win


def test_a_named_axis_replaces_the_default_breakdowns(client, db):
    """"pC outstanding by salesperson": the summary keeps its totals and breaks down by sales agent only."""
    w = _pending_world(db)
    body = _ok(
        client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id], group_by="sales_agent", top_n=1000,
        period=None,
    )
    s = body["summary"]
    assert (s["documents"], s["qty"]) == (2, 3), s
    assert [g["axis"] for g in s["groups"]] == ["sales_agent"], s
    assert _rows(s["groups"][0]["rows"]) == [(w.a1.sales_agent, 3, D("300.00"))], s


def test_a_named_location_filter_drops_by_location(client, db):
    """"pC outstanding only W2": the location is the user's filter, so By location (one row naming it back) goes."""
    w = _pending_world(db)
    body = _ok(
        client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id], warehouse_codes=[w.w2.warehouse_code],
        period=None,
    )
    assert [g["axis"] for g in body["summary"]["groups"]] == ["customer"], body["summary"]


def test_office_staff_without_the_reveal_get_no_agent_axis_or_agent_filter_on_pending_delivery(client, db):
    """Security S1: the opening is pending delivery as before #1922, which had no agent dimension. Without the reveal the
    agent axis and the agent filters stay refused (`own_book_only`)."""
    w = _pending_world(db)
    contact = _holder(db)
    for params in (
        {"group_by": "sales_agent", "top_n": 10}, {"sales_agent_ids": [w.a1.id]}, {"customer_agent_ids": [w.a1.id]},
    ):
        resp = _ask(client, contact, basis="pending_delivery", product_ids=[w.pc.id], period=None, **params)
        assert resp.status_code == 403 and resp.json()["code"] == "report_dimension_not_allowed", (params, resp.text)


def test_a_linked_contact_may_open_its_own_delivery_order_list(client, db):
    """Security N1: the DO list is the dealer's own rows (`enforce_customer_scope`), as before #1922."""
    w = _pending_world(db)
    contact = _holder(db, office=False)
    _link(db, contact, w.c1)
    db.commit()
    body = _ok(client, contact, basis="pending_delivery", product_ids=[w.pc.id], group_by="delivery_order", top_n=50, period=None)
    assert len(body["rows"]) == 2 and sum(r["qty"] for r in body["rows"]) == 3, body["rows"]


# ================================================================ item 1 (owner 29 Oct): dealers as before #1922


def _dealer(db, w):
    contact = _holder(db, "sales_orders.outstanding", office=False)
    _link(db, contact, w.c1)
    db.commit()
    return contact


def test_a_dealer_summary_keeps_by_location(client, db):
    """C1's pending delivery (pA W1 3, pC W2 2 + 1): By location then By product, its own rows only."""
    w = _pending_world(db)
    body = _ok(client, _dealer(db, w), basis="pending_delivery", period=None)
    s = body["summary"]
    assert [g["axis"] for g in s["groups"]] == ["location", "product"], s
    assert sorted(_rows(_group(s, "location"))) == sorted(
        [(w.w1.warehouse_code, 3, D("300.00")), (w.w2.warehouse_code, 3, D("300.00"))]
    ), s


def test_a_dealer_may_name_a_location_and_group_by_location(client, db):
    w = _pending_world(db)
    dealer = _dealer(db, w)
    body = _ok(client, dealer, basis="pending_delivery", warehouse_codes=[w.w2.warehouse_code], period=None)
    assert body["total"]["qty"] == 3, body["total"]  # C1's W2 lines only (pC 2 + 1)
    by_loc = _ok(client, dealer, basis="pending_delivery", group_by="location", top_n=10, period=None)
    assert sum(r["qty"] for r in by_loc["rows"]) == 6, by_loc["rows"]


def test_a_dealer_is_still_refused_the_agent_and_channel_on_outstanding(client, db):
    w = _pending_world(db)
    dealer = _dealer(db, w)
    for params in ({"group_by": "sales_agent", "top_n": 10}, {"channel": "dealer"}, {"group_by": "customer", "top_n": 10}):
        resp = _ask(client, dealer, basis="pending_delivery", period=None, **params)
        assert resp.status_code == 403, (params, resp.text)


def test_a_dealer_keeps_the_location_refusal_on_the_sales_bases(client, db):
    w = _pending_world(db)
    contact = _holder(db, "sales_orders.sales_report", office=False)
    _link(db, contact, w.c1)
    db.commit()
    resp = _ask(client, contact, basis="ordered", warehouse_codes=[w.w1.warehouse_code])
    assert resp.status_code == 403, resp.text


# ================================================================ item 7 (owner 29 Oct): the document lists as before #1922


def test_the_delivery_order_list_is_one_row_per_do_latest_first_every_field(client, db):
    """pC: DO1 (C1, 10 Sep, W2 2) and DO4 (C1, 15 Aug, W2 1). Latest first (R23), Delivered 0 by construction."""
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id], group_by="delivery_order",
               top_n=50, period=None)
    docs = body["documents"]
    assert [(d["customer_name"], d["product_code"], d["location"], d["do_qty"], d["delivered_qty"], d["pending_qty"],
             d["do_date"]) for d in docs] == [
        (w.c1.customer_name, w.pc.product_code, w.w2.warehouse_code, 2, 0, 2, "2026-09-10"),
        (w.c1.customer_name, w.pc.product_code, w.w2.warehouse_code, 1, 0, 1, "2026-08-15"),
    ], docs
    assert all(d["do_number"] for d in docs), docs


def test_a_do_with_two_lines_is_one_row_with_its_products_and_locations_joined(client, db):
    """DO1 carries pA at W1 (3) and pC at W2 (2): one row, both codes, both locations, 5 outstanding."""
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", customer_ids=[w.c1.id], group_by="delivery_order",
               top_n=50, period=None)
    sep = [d for d in body["documents"] if d["do_date"] == "2026-09-10"]
    assert len(sep) == 1, body["documents"]
    assert sep[0]["product_code"] == ", ".join(sorted([w.pa.product_code, w.pc.product_code])), sep
    assert sep[0]["location"] == ", ".join(sorted([w.w1.warehouse_code, w.w2.warehouse_code])), sep
    assert sep[0]["pending_qty"] == 5, sep


def test_the_sales_order_list_is_one_row_per_so_with_ordered_transferred_and_outstanding(client, db):
    cust = seed_customer(db, name=unique_code("CustL"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WL"))
    p1 = make_product(db, unique_code("L1"))
    seed_so_line(db, cust=cust, prod=p1, qty=10, delivered=4, total="1000.00", wh=wh, order_date=date(2026, 8, 5))
    seed_so_line(db, cust=cust, prod=p1, qty=5, delivered=0, total="500.00", wh=wh, order_date=date(2026, 9, 20))
    seed_so_line(db, cust=cust, prod=p1, qty=8, delivered=8, total="800.00", wh=wh, order_date=date(2026, 9, 25))
    db.commit()
    body = _ok(client, _staff(db), basis="outstanding", customer_ids=[cust.id], group_by="sales_order", top_n=50,
               period=None)
    docs = body["documents"]
    assert [(d["ordered_qty"], d["transferred_qty"], d["outstanding_qty"], d["order_date"], d["location"]) for d in docs] == [
        (5, 0, 5, "2026-09-20", wh.warehouse_code), (10, 4, 6, "2026-08-05", wh.warehouse_code),
    ], docs  # the fully delivered SO is not outstanding


def test_a_ranking_by_another_axis_carries_no_documents(client, db):
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", group_by="customer", top_n=10, period=None)
    assert body.get("documents") is None, body


# ================================================================ item 6 (owner 29 Oct): "more" paging, as before #1922


def test_the_route_echoes_the_group_offset_on_a_summary(client, db):
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id], group_offset=20, period=None)
    assert body["summary"]["group_offset"] == 20, body["summary"]
    first = _ok(client, _staff(db), basis="pending_delivery", product_ids=[w.pc.id], period=None)
    assert first["summary"].get("group_offset") in (None, 0), first["summary"]


# ================================================================ review round 2 (B1, S1, S2)


def test_an_undated_sales_order_neither_breaks_the_date_range_nor_lists_first(client, db):
    """Review B1: an open SO with no order date, dated for the figure by its line's required date. The range reads the
    real dates only (never the engine's blank label), and the SO list puts the undated SO last."""
    cust = seed_customer(db, name=unique_code("CustU"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WU"))
    p1 = make_product(db, unique_code("U1"))
    seed_so_line(db, cust=cust, prod=p1, qty=4, delivered=0, total="400.00", wh=wh, order_date=None,
                 required_date=date(2026, 9, 1))
    seed_so_line(db, cust=cust, prod=p1, qty=5, delivered=0, total="500.00", wh=wh, order_date=date(2026, 8, 5))
    db.commit()
    s = _ok(client, _staff(db), basis="outstanding", customer_ids=[cust.id], period=None)["summary"]
    assert s["qty"] == 9, s
    assert (s["date_first"], s["date_last"]) == ("2026-08-05", "2026-08-05"), s
    docs = _ok(client, _staff(db), basis="outstanding", customer_ids=[cust.id], group_by="sales_order", top_n=50,
               period=None)["documents"]
    assert [(d["outstanding_qty"], d["order_date"]) for d in docs] == [(5, "2026-08-05"), (4, None)], docs


def test_the_document_list_reads_every_granted_company_like_the_figure(db):
    """Review S1: from a session scoped to Sorento, a contact granted Sorento and Mocha gets Mocha's SO in the list as it
    does in the summary's count (the dataset owns its company arm, as `engine.run_summary` runs it)."""
    from app.models.base import company_scope
    from app.services.reports import ask
    from app.services.stock_visibility import Policy
    from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha

    seed_mocha(db)
    sp, mp = product(db, company_id=DEFAULT_COMPANY_ID), product(db, company_id=MOCHA_ID)
    sorento, mocha = seed_customer(db, name=unique_code("CS")), seed_customer(db, name=unique_code("CM"), company_id=MOCHA_ID)
    ws, wm = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WS")), warehouse(db, company_id=MOCHA_ID, code=unique_code("WM"))
    seed_so_line(db, cust=sorento, prod=sp, qty=3, delivered=0, total="300.00", wh=ws)
    seed_so_line(db, cust=mocha, prod=mp, qty=2, delivered=0, total="200.00", wh=wm, company_id=MOCHA_ID)
    db.commit()
    run = dict(basis="outstanding", filters={"customer": [sorento.id, mocha.id]}, warehouse_codes=[],
               policy=Policy(mode="detailed", warehouse_ids=None, source="default", source_label=None,
                             hide_zero_locations=False, excluded_warehouse_ids=None),
               company_grants=[DEFAULT_COMPANY_ID, MOCHA_ID], date_from=date(1900, 1, 1), date_to=date(2200, 12, 31))
    with company_scope(db, frozenset({DEFAULT_COMPANY_ID})):
        docs = ask.document_rows(db, **run)
        summary = ask.outstanding_summary(db, axes=[], **{k: v for k, v in run.items() if k != "basis"},
                                          basis="outstanding")
    assert summary["documents"] == 2, summary
    assert sorted(d["outstanding_qty"] for d in docs) == [2, 3], docs


def test_a_by_channel_breakdown_of_undelivered_orders_keeps_the_ordered_quantity(client, db):
    """Review S2: "Dealer: 0 (O/S: 6)" was the ordered measure looked up under the display name."""
    cust = seed_customer(db, name=unique_code("CustC"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WC"))
    p1 = make_product(db, unique_code("C1"))
    seed_so_line(db, cust=cust, prod=p1, qty=10, delivered=4, total="1000.00", wh=wh, order_date=date(2026, 8, 5),
                 demand_class="retail")
    db.commit()
    s = _ok(client, _staff(db), basis="outstanding", product_ids=[p1.id], group_by="channel", top_n=10,
            period=None)["summary"]
    assert [(r["name"], r["ordered_qty"], r["qty"]) for r in _group(s, "channel")] == [("Dealer", 10, 6)], s


# ================================================================ eval send-back hard guard: no unpaged list


def test_a_2000_row_document_list_returns_one_page_of_20_and_the_total(client, db):
    """Eval rpt-010 printed 2,491 delivery orders in ONE message. The route returns one page (20, latest first) and
    the count; `group_offset` asks a later page; past the end is an empty page."""
    from tests._sales_report_do_seed import line, seed_do

    cust = seed_customer(db, name=unique_code("CustP"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WP"))
    p = make_product(db, unique_code("P2K"))
    start = date(2020, 1, 1)
    from datetime import timedelta

    for i in range(2000):
        seed_do(db, customer_id=cust.id, order_date=start + timedelta(days=i), source_book="db1",
                lines=[line(p.id, wh.id, 1, total="10.00")])
    db.commit()
    # A fresh test schema has no planner statistics: unanalyzed, the line query re-scans its per-DO totals for every
    # line (quadratic, minutes at 2,000). Production tables are analyzed.
    from sqlalchemy import text

    db.execute(text("ANALYZE orders"))
    db.execute(text("ANALYZE order_lines"))
    ask = dict(basis="pending_delivery", product_ids=[p.id], group_by="delivery_order", top_n=50, period=None)
    first = _ok(client, _staff(db), **ask)
    assert first["documents_total"] == 2000 and len(first["documents"]) == 20, (first.get("documents_total"),)
    assert first["documents"][0]["do_date"] == (start + timedelta(days=1999)).isoformat(), first["documents"][0]
    last = _ok(client, _staff(db), group_offset=1980, **ask)
    assert len(last["documents"]) == 20 and last["group_offset"] == 1980, last.get("group_offset")
    assert last["documents"][-1]["do_date"] == start.isoformat(), last["documents"][-1]
    past = _ok(client, _staff(db), group_offset=2000, **ask)
    assert past["documents"] == [] and past["documents_total"] == 2000, past
