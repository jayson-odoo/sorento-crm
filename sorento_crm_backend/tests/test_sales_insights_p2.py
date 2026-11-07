"""Phase 2 RED tests - SALES-INSIGHTS-P2 (leaderboard phase 2: drilldown, perspectives, targets, basis).

Contract: `documentation/plans/sales/PLAN-sales-insights-p2-07nov.md` ("Contract", binding) and
`documentation/plans/sales/sales-insights-p2-07nov-acceptance-criteria.md` (P1, P2, P4, P5, P6, P7, P9, P10).

Postgres only (`tests/_pg_fixture.py`), every row seeded here (CI's database is empty). Reuses the #2227 client
and agent helpers of `tests/test_sales_leaderboard.py`.

The world (October 2026, previous window Aug 31 to Sep 30, company Sorento only):

  Invoiced, Oct (traced to a sales order class through the line's `sales_order_line_id`)
    IV1 ALPHA (a1)   c1  dealer             branded product  1000   (3 units)
    IV2 ALPHA (a2)   c2  project            plain product     400
    IV3 GAMMA (g1)   c3  other              plain product     300
    IV4 X1 (a code with no person label)  c1  no sales order   plain   200
    IV5 no agent     c3  type_not_set       plain             50
    IV6 an agent code AutoCount sent that is no CRM agent ("raw")  c3  no sales order  plain  70
    total 2020; ALPHA 1400, GAMMA 300, X1 200, raw 70, no agent 50. Sep: ALPHA 500 (dealer, c1).
  Sales orders (order bases; qty ordered 2, delivered 2 or 0):
    O1 ALPHA c1 retail  1000 delivered      O2 ALPHA c2 project 400 open      O3 GAMMA c3 other 300 delivered
    O4 X1    c1 (class none) 200 open       O5 none  c3 retail   50 delivered  O6 GAMMA c3 other 120 open
    O7 (Jan 2026, outside October) ALPHA c2 retail 90 open
    delivered Oct 1350 (ALPHA 1000, GAMMA 300, none 50); ordered Oct 2070 (ALPHA 1400, GAMMA 420, X1 200, none 50);
    outstanding Oct 720 (ALPHA 400, X1 200, GAMMA 120), outstanding all dates 810.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.access import RespondContact
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Brand, ProductCategory
from app.models.sales import SalesTarget, SalesTargetPeriod
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.error_handler import AppException
from app.services.sales import invoiced_sales as inv

from tests._mc_lookup_seed import MOCHA_ID, product
from tests._pg_fixture import unique_code
from tests._sales_unified_seed import cust, doc, line, so
from tests.test_sales_leaderboard import (  # noqa: F401  (db is a fixture)
    LB,
    OCT,
    OPTIONS,
    ROUTE,
    SEP,
    _agent,
    _assistant_ask,
    _board,
    db,
    make_client,
)
from tests.test_top_selling_report import _access, _contact

D = Decimal
REPORTS = "sales.reports.view"
ORDERS = "order_management.orders.view"
ALL3 = (LB, REPORTS, ORDERS)
BASES = ("invoiced", "delivered", "ordered", "outstanding")
BYS = ("person", "customer", "product", "brand", "category", "channel")
OCT_D = (date(2026, 10, 1), date(2026, 10, 31))
EVERY = (date(1900, 1, 1), date(2200, 12, 31))
GRANTS = frozenset({DEFAULT_COMPANY_ID, MOCHA_ID})
TOP_KEYS = {
    "basis", "by", "date_from", "date_to", "previous_from", "previous_to", "as_of", "total", "no_agent_amount",
    "rows", "me", "can_drill_others",
}
TOTAL_KEYS = {"amount", "qty", "prev_amount", "change_pct", "customers", "products"}
ROW_KEYS = {"rank", "name", "keys", "amount", "qty", "prev_amount", "change_pct", "customers", "products"}
PERSON_KEYS = ROW_KEYS | {"person", "codes", "is_me", "target"}
TARGET_KEYS = {
    "target_no", "basis", "period_from", "period_to", "target_amount", "achieved_amount", "achieved_pct",
    "like_for_like",
}
FORBIDDEN = ("commission", "tier", "rate", "payout", "bonus")


def _money(value) -> Decimal:
    return D(str(value))


# ---------------------------------------------------------------------------------------- seeds


def _iv(db, kind, net, when, *, cls="retail", agent=None, agent_code=None, customer=None, prod=None, qty="1",
        traced=True):
    """An invoice traced to a sales order of `cls` (`traced=False`: no sales order at all)."""
    spec = {"net": net, "qty": qty, "prod": prod}
    if traced:
        _h, (sol,) = so(db, demand_class=cls, customer=customer)  # no order date: never an order-basis line
        spec["so_line"] = sol
    return doc(db, kind, net, when, customer=customer, agent_row=agent, agent_code=agent_code,
               lines=[line(**spec)])


def _order(db, agent, customer, cls, total, delivered, when=date(2026, 10, 10), prod=None):
    header = SalesOrder(
        id=str(uuid.uuid4()), so_number=unique_code("SO"), customer_id=customer.id, status="open",
        demand_class=cls, company_id=DEFAULT_COMPANY_ID, order_date=when,
        sales_agent_id=agent.id if agent is not None else None,
    )
    db.add(header)
    db.flush()
    db.add(SalesOrderLine(
        id=str(uuid.uuid4()), sales_order_id=header.id, product_id=(prod or product(db, company_id=DEFAULT_COMPANY_ID)).id,
        qty_ordered=2, qty_delivered=2 if delivered else 0, line_total=D(total), line_status="open",
        company_id=DEFAULT_COMPANY_ID,
    ))
    db.flush()
    return header


def _world(db):
    s = unique_code("W", alpha=True)[-8:]
    ns = type("World", (), {})()
    ns.alpha, ns.gamma, ns.raw = f"ZZTALPHA {s}", f"ZZTGAMMA {s}", f"ZZTRAW-{s}"
    ns.a1 = _agent(db, f"ZZT-A1-{s}", person=ns.alpha, company_id=DEFAULT_COMPANY_ID)
    ns.a2 = _agent(db, f"ZZT-A2-{s}", person=ns.alpha, company_id=DEFAULT_COMPANY_ID)
    ns.g1 = _agent(db, f"ZZT-G1-{s}", person=ns.gamma, company_id=DEFAULT_COMPANY_ID)
    ns.x1 = _agent(db, f"ZZT-X1-{s}", person=None, company_id=DEFAULT_COMPANY_ID)
    ns.x1_label = ns.x1.sales_agent
    ns.c1 = cust(db, name=f"ZZT Customer One {s}", code=f"ZZT-C1-{s}")
    ns.c2 = cust(db, name=f"ZZT Customer Two {s}", code=f"ZZT-C2-{s}")
    ns.c3 = cust(db, name=f"ZZT Customer Three {s}", code=f"ZZT-C3-{s}")
    ns.brand = Brand(id=str(uuid.uuid4()), brand_code=unique_code("BR")[:50], brand_name=f"ZZT Brand {s}",
                     company_id=DEFAULT_COMPANY_ID)
    ns.category = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50],
                                  category_name=f"ZZT Category {s}", company_id=DEFAULT_COMPANY_ID)
    db.add_all([ns.brand, ns.category])
    db.flush()
    ns.branded = product(db, company_id=DEFAULT_COMPANY_ID)
    ns.branded.brand_id, ns.branded.category_id = ns.brand.id, ns.category.id
    ns.plain = product(db, company_id=DEFAULT_COMPANY_ID)
    db.flush()

    _iv(db, "invoice", "1000.00", date(2026, 10, 5), cls="retail", agent=ns.a1, customer=ns.c1, prod=ns.branded, qty="3")
    _iv(db, "invoice", "400.00", date(2026, 10, 6), cls="project", agent=ns.a2, customer=ns.c2, prod=ns.plain)
    _iv(db, "invoice", "300.00", date(2026, 10, 7), cls="other", agent=ns.g1, customer=ns.c3, prod=ns.plain)
    _iv(db, "invoice", "200.00", date(2026, 10, 8), agent=ns.x1, customer=ns.c1, prod=ns.plain, traced=False)
    _iv(db, "invoice", "50.00", date(2026, 10, 9), cls=None, customer=ns.c3, prod=ns.plain)
    _iv(db, "invoice", "70.00", date(2026, 10, 10), agent_code=ns.raw, customer=ns.c3, prod=ns.plain, traced=False)
    _iv(db, "invoice", "500.00", date(2026, 9, 10), cls="retail", agent=ns.a1, customer=ns.c1, prod=ns.plain)

    _order(db, ns.a1, ns.c1, "retail", "1000.00", True, prod=ns.plain)
    _order(db, ns.a2, ns.c2, "project", "400.00", False, prod=ns.plain)
    _order(db, ns.g1, ns.c3, "other", "300.00", True, prod=ns.plain)
    _order(db, ns.x1, ns.c1, None, "200.00", False, prod=ns.plain)
    _order(db, None, ns.c3, "retail", "50.00", True, prod=ns.plain)
    _order(db, ns.g1, ns.c3, "other", "120.00", False, prod=ns.plain)
    _order(db, ns.a1, ns.c2, "retail", "90.00", False, when=date(2026, 1, 15), prod=ns.plain)
    db.commit()
    return ns


def _linked_user(db, agent_row):
    contact = RespondContact(id=str(uuid.uuid4()), respond_io_id=unique_code("C"),
                             phone_number=f"+6010{uuid.uuid4().hex[:7]}", name="ZZT Me")
    db.add(contact)
    db.flush()
    agent_row.contact_id = contact.id
    db.flush()
    return contact


# ------------------------------------------------------------------------------------- requests


def _lb(client, basis="invoiced", by="person", window=OCT, **extra):
    params = [("basis", basis), ("by", by)]
    if window:
        params += [("date_from", window[0]), ("date_to", window[1])]
    for key, value in extra.items():
        for item in (value if isinstance(value, (list, tuple)) else [value]):
            params.append((key, item))
    return client.get(ROUTE, params=params)


def _ok(client, *args, **kw):
    resp = _lb(client, *args, **kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _asked(db, basis, group_by=None, window=OCT_D, filters=None):
    from app.services.reports import ask

    return ask.run_ask(
        db, basis=basis, measure="amount", group_by=group_by, date_from=window[0], date_to=window[1],
        filters=filters or {}, warehouse_codes=[], policy=None, capped_by_policy=False,
        top_n=1000 if group_by else None, company_grants=GRANTS,
    )


def _by_name(body):
    return {r["name"]: _money(r["amount"]) for r in body["rows"]}


def _window_of(basis):
    return None if basis == "outstanding" else OCT


def _span_of(basis):
    return EVERY if basis == "outstanding" else OCT_D


def _keys_of(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from _keys_of(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _keys_of(item)


# =============================================================== P1 one engine, View by (P10-1)


@pytest.mark.parametrize("by", BYS)
def test_p1_1_every_view_total_equals_the_person_board_total_and_run_ask(db, by):
    _world(db)
    expected = _money(_asked(db, "invoiced")["total"]["amount"])
    assert expected == D("2020.00")
    with make_client(db, allow=ALL3) as client:
        person_total = _money(_ok(client)["total"]["amount"])
        body = _ok(client, by=by)
    assert person_total == expected
    assert _money(body["total"]["amount"]) == expected
    assert (body["basis"], body["by"]) == ("invoiced", by)


@pytest.mark.parametrize("basis", BASES)
def test_p10_1_every_basis_board_total_equals_run_ask_of_that_basis(db, basis):
    _world(db)
    expected = _money(_asked(db, basis, window=_span_of(basis))["total"]["amount"])
    assert expected == {"invoiced": D("2020.00"), "delivered": D("1350.00"), "ordered": D("2070.00"),
                        "outstanding": D("810.00")}[basis]
    with make_client(db, allow=ALL3) as client:
        body = _ok(client, basis=basis, window=_window_of(basis))
        by_customer = _ok(client, basis=basis, by="customer", window=_window_of(basis))
    assert body["basis"] == basis
    assert _money(body["total"]["amount"]) == expected
    assert _money(by_customer["total"]["amount"]) == expected


def test_p10_2_outstanding_without_dates_is_the_all_dates_total_and_has_no_compare(db):
    _world(db)
    with make_client(db) as client:
        body = _ok(client, basis="outstanding", window=None)
        windowed = _ok(client, basis="outstanding", window=OCT)
        explicit = _ok(client, basis="outstanding", window=None, previous_from=SEP[0], previous_to=SEP[1])
    assert (body["date_from"], body["date_to"]) == (None, None)
    assert (body["previous_from"], body["previous_to"]) == (None, None)
    assert _money(body["total"]["amount"]) == D("810.00")
    assert body["total"]["prev_amount"] is None and body["total"]["change_pct"] is None
    assert all(r["prev_amount"] is None and r["change_pct"] is None for r in body["rows"])
    assert _money(windowed["total"]["amount"]) == D("720.00")
    assert (windowed["date_from"], windowed["date_to"]) == OCT
    assert (windowed["previous_from"], windowed["previous_to"]) == (None, None)  # no compare on outstanding
    assert explicit["total"]["prev_amount"] is None  # previous_* ignored on outstanding


def test_p1_4_the_response_carries_every_contract_field(db):
    world = _world(db)
    with make_client(db, allow=ALL3) as client:
        body = _ok(client)
        customers = _ok(client, by="customer")
    assert set(body) == TOP_KEYS
    assert set(body["total"]) == TOTAL_KEYS
    assert (body["date_from"], body["date_to"]) == OCT
    assert (body["previous_from"], body["previous_to"]) == ("2026-08-31", "2026-09-30")
    assert body["total"]["customers"] == 3 and isinstance(body["total"]["products"], int)
    assert all(set(r) == PERSON_KEYS for r in body["rows"])
    assert all(set(r) == ROW_KEYS | {"code", "companies"} for r in customers["rows"])
    first = body["rows"][0]
    assert first["name"] == first["person"] == world.alpha and first["keys"] == []
    assert isinstance(first["customers"], int) and isinstance(first["products"], int)


@pytest.mark.parametrize("by", BYS)
def test_p1_1_rows_are_nonzero_ranked_by_amount_then_name_dense(db, by):
    _world(db)
    with make_client(db, allow=ALL3) as client:
        rows = _ok(client, by=by)["rows"]
    assert rows
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    assert all(_money(r["amount"]) != 0 for r in rows)
    ordered = sorted(rows, key=lambda r: (-_money(r["amount"]), r["name"]))
    assert [r["name"] for r in rows] == [r["name"] for r in ordered]


def test_p1_non_person_views_have_no_agent_amount_zero_and_no_me(db):
    world = _world(db)
    contact = _linked_user(db, world.a1)
    with make_client(db, allow=ALL3, contact=contact) as client:
        person = _ok(client)
        customers = _ok(client, by="customer")
    assert person["me"] == {"person": world.alpha, "rank": 1}
    assert _money(person["no_agent_amount"]) == D("50.00")
    assert customers["me"] is None and customers["no_agent_amount"] == 0.0


def test_p1_prev_amount_and_change_join_the_previous_window_by_name(db):
    world = _world(db)
    with make_client(db, allow=ALL3) as client:
        person = {r["person"]: r for r in _ok(client)["rows"]}
        customers = {r["name"]: r for r in _ok(client, by="customer")["rows"]}
    assert _money(person[world.alpha]["prev_amount"]) == D("500.00")
    assert person[world.alpha]["change_pct"] == 180.0  # (1400 - 500) / 500
    assert person[world.gamma]["change_pct"] is None  # nothing before
    assert _money(customers[world.c1.customer_name]["prev_amount"]) == D("500.00")
    assert customers[world.c1.customer_name]["change_pct"] == 140.0  # 1200 against 500


# ============================================================================ P2 drilldown


def test_p2_3_person_drill_to_customers_equals_run_ask_filtered_by_the_codes_of_the_person(db):
    world = _world(db)
    expected = _by_name(_asked(db, "invoiced", "customer", filters={"sales_agent": [world.a1.id, world.a2.id]}))
    assert expected == {world.c1.customer_name: D("1000.00"), world.c2.customer_name: D("400.00")}
    with make_client(db, allow=(LB, REPORTS)) as client:
        body = _ok(client, by="customer", person=world.alpha)
    assert _by_name(body) == expected  # a person with two codes drills as one
    assert _money(body["total"]["amount"]) == D("1400.00")
    assert body["total"]["customers"] == 2


def test_p2_4_a_code_without_a_person_label_drills_by_its_code(db):
    world = _world(db)
    with make_client(db, allow=(LB, REPORTS)) as client:
        body = _ok(client, by="customer", person=world.x1_label)
    assert _by_name(body) == {world.c1.customer_name: D("200.00")}


def test_p2_4_a_code_autocount_sent_that_is_not_a_crm_agent_drills_by_that_code(db):
    world = _world(db)
    with make_client(db, allow=(LB, REPORTS)) as client:
        board = {r["person"]: r for r in _ok(client)["rows"]}
        body = _ok(client, by="customer", person=world.raw)
    assert world.raw in board and _money(board[world.raw]["amount"]) == D("70.00")
    assert _by_name(body) == {world.c3.customer_name: D("70.00")}


def test_p2_1_drilling_further_narrows_by_customer_then_product(db):
    world = _world(db)
    with make_client(db, allow=(LB, REPORTS)) as client:
        by_product = _ok(client, by="product", person=world.alpha, customer=world.c1.id)
        by_person = _ok(client, by="person", customer=world.c1.id)
        by_product_only = _ok(client, by="customer", product=world.branded.id)
    assert _by_name(by_product) == {world.branded.product_code: D("1000.00")}
    assert {r["person"]: _money(r["amount"]) for r in by_person["rows"]} == {
        world.alpha: D("1000.00"), world.x1_label: D("200.00"),
    }
    assert _by_name(by_product_only) == {world.c1.customer_name: D("1000.00")}


@pytest.mark.parametrize("basis", ("delivered", "ordered", "outstanding"))
def test_p10_1_person_drill_works_on_every_order_basis(db, basis):
    world = _world(db)
    expected = _by_name(_asked(db, basis, "customer", window=_span_of(basis), filters={"sales_agent": [world.a1.id, world.a2.id]}))
    with make_client(db, allow=(LB, ORDERS)) as client:
        body = _ok(client, basis=basis, by="customer", person=world.alpha, window=_window_of(basis))
    assert _by_name(body) == expected
    assert body["total"]["amount"] != 0


# ================================================================ engine: sales_person word (P5-2)


def test_p5_2_sales_person_is_a_dimension_and_a_filter_on_the_four_bases_only():
    from app.services.reports import ask

    sales = ask.CATALOGUE["sales"]
    for basis in BASES:
        assert "sales_person" in sales[basis]["dimensions"], basis
        assert "sales_person" in sales[basis]["filters"], basis
    for basis in ("pending_delivery", "unpaid"):
        assert "sales_person" not in sales[basis]["dimensions"], basis
        assert "sales_person" not in sales[basis]["filters"], basis


def test_p5_2_every_definition_has_a_sales_person_select_param_and_a_visible_rows_column():
    from app.services.reports import ask
    from app.services.reports import registry as reg

    for basis in BASES:
        definition = ask.CATALOGUE["sales"][basis]["definition"]
        param = next((p for p in definition.params if p.key == "sales_person"), None)
        assert isinstance(param, reg.SelectParam), basis
        column = next((c for c in definition.dataset.columns if c.key == "sales_person"), None)
        assert column is not None and not column.hidden, basis


def test_p5_2_the_invoiced_rows_picker_shows_sales_person_but_top_selling_items_does_not():
    from app.services.reports.datasets import billing_document_lines as bdl

    assert "sales_person" in [c.key for c in bdl.ASK_DEFINITION.dataset.columns if not c.hidden]
    assert "sales_person" not in [c.key for c in bdl.DATASET.columns]


@pytest.mark.parametrize("basis", ("delivered", "ordered", "outstanding"))
def test_p5_2_sales_person_groups_the_order_bases_with_no_agent_as_its_own_row(db, basis):
    from app.services.reports import ask

    world = _world(db)
    rows = _by_name(_asked(db, basis, "sales_person", window=_span_of(basis)))
    assert rows[world.alpha] == {"delivered": D("1000"), "ordered": D("1400"), "outstanding": D("490")}[basis]
    assert (ask.NO_AGENT_KEY and inv.NO_AGENT in rows) is (basis != "outstanding")
    if basis == "ordered":
        assert rows[world.x1_label] == D("200") and rows[world.gamma] == D("420")


@pytest.mark.parametrize("basis", BASES)
def test_p5_2_the_sales_person_filter_keeps_that_persons_figure(db, basis):
    world = _world(db)
    got = _asked(db, basis, window=_span_of(basis), filters={"sales_person": [world.alpha]})
    assert _money(got["total"]["amount"]) == {
        "invoiced": D("1400"), "delivered": D("1000"), "ordered": D("1400"), "outstanding": D("490"),
    }[basis]
    code_only = _asked(db, basis, window=_span_of(basis), filters={"sales_person": [world.x1_label]})
    assert _money(code_only["total"]["amount"]) == {
        "invoiced": D("200"), "delivered": D("0"), "ordered": D("200"), "outstanding": D("200"),
    }[basis]


# ===================================================================================== P9 channel


def test_p9_1_by_channel_rows_carry_the_sales_type_key_on_invoiced(db):
    _world(db)
    with make_client(db, allow=ALL3) as client:
        body = _ok(client, by="channel")
    got = {r["key"]: _money(r["amount"]) for r in body["rows"]}
    assert got == {
        "dealer": D("1000.00"), "project": D("400.00"), "other": D("300.00"),
        "no_sales_order": D("270.00"), "type_not_set": D("50.00"),
    }
    assert all("key" in r for r in body["rows"])
    assert sum(got.values()) == _money(body["total"]["amount"])  # all ticked = the total


def test_p9_1_by_channel_on_the_order_bases_keys_dealer_project_other_and_none(db):
    _world(db)
    with make_client(db, allow=ALL3) as client:
        body = _ok(client, basis="ordered", by="channel")
    got = {r["key"]: _money(r["amount"]) for r in body["rows"]}
    assert got == {"dealer": D("1050.00"), "project": D("400.00"), "other": D("420.00"), None: D("200.00")}


@pytest.mark.parametrize("values,expected", [
    (["dealer"], D("1000.00")),
    (["dealer", "project"], D("1400.00")),
    (["other"], D("300.00")),
    (["no_sales_order"], D("270.00")),
    (["type_not_set"], D("50.00")),
    (["set_apart"], D("0")),
    (["mixed"], D("0")),
])
def test_p9_1_the_channel_filter_keeps_only_that_sales_type_on_invoiced(db, values, expected):
    _world(db)
    with make_client(db) as client:
        body = _ok(client, channel=values)
    assert _money(body["total"]["amount"]) == expected


@pytest.mark.parametrize("basis,expected", [
    ("delivered", D("300.00")), ("ordered", D("420.00")), ("outstanding", D("120.00")),
])
def test_p9_1_other_works_as_a_channel_on_every_order_basis(db, basis, expected):
    _world(db)
    with make_client(db) as client:
        body = _ok(client, basis=basis, channel="other", window=_window_of(basis))
    assert _money(body["total"]["amount"]) == expected


def test_p9_1_dealer_and_project_on_the_order_bases_read_retail_and_project(db):
    _world(db)
    with make_client(db) as client:
        assert _money(_ok(client, basis="ordered", channel="dealer")["total"]["amount"]) == D("1050.00")
        assert _money(_ok(client, basis="ordered", channel="project")["total"]["amount"]) == D("400.00")
        assert _money(_ok(client, basis="delivered", channel="project")["total"]["amount"]) == D("0")


def test_p9_1_run_ask_channel_other_and_the_order_bases_422_on_a_type_they_do_not_have(db):
    _world(db)
    assert _money(_asked(db, "delivered", filters={"channel": ["other"]})["total"]["amount"]) == D("300.00")
    assert _money(_asked(db, "ordered", filters={"channel": ["dealer", "other"]})["total"]["amount"]) == D("1470.00")
    with pytest.raises(AppException) as err:
        _asked(db, "ordered", filters={"channel": ["no_sales_order"]})
    assert err.value.status_code == 422 and err.value.code == "REPORT_INVALID_PARAMS"
    assert _money(_asked(db, "invoiced", filters={"channel": ["no_sales_order"]})["total"]["amount"]) == D("270.00")


@pytest.mark.parametrize("basis", ("delivered", "ordered", "outstanding"))
def test_p9_1_no_sales_order_and_the_other_invoiced_only_types_are_422_on_the_order_bases(db, basis):
    _world(db)
    with make_client(db) as client:
        for value in ("no_sales_order", "set_apart", "mixed", "type_not_set"):
            resp = _lb(client, basis=basis, channel=value, window=_window_of(basis))
            assert resp.status_code == 422, (basis, value, resp.text)
            assert resp.json().get("code") == "REPORT_INVALID_PARAMS"


def test_p9_1_an_unknown_channel_value_is_422_on_every_basis(db):
    with make_client(db) as client:
        for basis in BASES:
            resp = _lb(client, basis=basis, channel="bogus", window=_window_of(basis))
            assert resp.status_code == 422, (basis, resp.text)
            assert resp.json().get("code") == "REPORT_INVALID_PARAMS"


# ============================================================ P1-4 customer and product rows


def test_p1_4_customer_rows_carry_the_customer_code_and_the_company_codes(db):
    from app.models.company import Company

    world = _world(db)
    sorento = db.get(Company, DEFAULT_COMPANY_ID).code
    with make_client(db, allow=ALL3) as client:
        rows = {r["name"]: r for r in _ok(client, by="customer")["rows"]}
    one = rows[world.c1.customer_name]
    assert _money(one["amount"]) == D("1200.00")
    assert one["keys"] == [world.c1.id]
    assert one["code"] == world.c1.customer_code
    assert one["companies"] == [sorento]
    assert rows[world.c3.customer_name]["code"] == world.c3.customer_code
    assert _money(rows[world.c3.customer_name]["amount"]) == D("420.00")


def test_p1_4_product_rows_carry_brand_category_and_qty(db):
    world = _world(db)
    with make_client(db, allow=ALL3) as client:
        rows = {r["name"]: r for r in _ok(client, by="product")["rows"]}
    branded = rows[world.branded.product_code]
    assert _money(branded["amount"]) == D("1000.00") and branded["qty"] == 3
    assert branded["keys"] == [world.branded.id]
    assert branded["brand"] == world.brand.brand_name
    assert branded["category"] == world.category.category_name
    plain = rows[world.plain.product_code]
    assert plain["brand"] is None and plain["category"] == "Category"
    assert set(branded) >= ROW_KEYS | {"brand", "category"}


def test_p1_1_brand_and_category_views_group_by_their_names_and_filters_narrow(db):
    world = _world(db)
    with make_client(db, allow=ALL3) as client:
        brands = _ok(client, by="brand")
        categories = _ok(client, by="category")
        narrowed = _ok(client, by="customer", brand=world.brand.id)
    assert _by_name(brands)[world.brand.brand_name] == D("1000.00")
    assert _by_name(categories)[world.category.category_name] == D("1000.00")
    assert brands["rows"][0]["keys"] == [world.brand.id]
    assert _by_name(narrowed) == {world.c1.customer_name: D("1000.00")}


# ====================================================================== P6 access matrix


def _denied(resp):
    assert resp.status_code == 403, resp.text
    assert resp.json().get("code") == "PERMISSION_DENIED", resp.text


@pytest.mark.parametrize("basis", BASES)
def test_p6_1_leaderboard_view_alone_gets_the_person_board_on_every_basis(db, basis):
    _world(db)
    with make_client(db, allow=(LB,)) as client:
        body = _ok(client, basis=basis, window=_window_of(basis))
    assert body["rows"] and body["can_drill_others"] is False


@pytest.mark.parametrize("basis", BASES)
def test_p6_2_leaderboard_view_alone_gets_403_on_every_other_view(db, basis):
    world = _world(db)
    with make_client(db, allow=(LB,)) as client:
        for by in BYS[1:]:
            _denied(_lb(client, basis=basis, by=by, window=_window_of(basis)))
        _denied(_lb(client, basis=basis, by="person", window=_window_of(basis), customer=world.c1.id))
        _denied(_lb(client, basis=basis, by="person", window=_window_of(basis), product=world.plain.id))


def test_p6_2_a_filter_that_is_not_a_drill_never_needs_the_slug(db):
    world = _world(db)
    with make_client(db, allow=(LB,)) as client:
        assert _ok(client, brand=world.brand.id)["rows"]
        assert _ok(client, category=world.category.id)["rows"]
        assert _ok(client, channel="dealer")["rows"]
        assert _ok(client, company=DEFAULT_COMPANY_ID)["rows"]


def test_p6_2_drilling_another_person_is_403_and_the_own_person_is_200(db):
    world = _world(db)
    contact = _linked_user(db, world.a1)
    with make_client(db, allow=(LB,), contact=contact) as client:
        body = _ok(client, by="customer", person=world.alpha)
        own_product = _ok(client, by="product", person=world.alpha)
        own_on_board = _ok(client, by="person", person=world.alpha)
        _denied(_lb(client, by="customer", person=world.gamma))
        _denied(_lb(client, by="customer", person=[world.alpha, world.gamma]))  # every value must be your own
        _denied(_lb(client, by="person", person=world.gamma))
        _denied(_lb(client, by="person", customer=world.c1.id))
    assert _by_name(body) == {world.c1.customer_name: D("1000.00"), world.c2.customer_name: D("400.00")}
    assert _by_name(own_product)
    assert [r["person"] for r in own_on_board["rows"]] == [world.alpha]


def test_p6_2_an_own_person_drill_on_an_order_basis_needs_no_orders_slug(db):
    world = _world(db)
    contact = _linked_user(db, world.a1)
    with make_client(db, allow=(LB,), contact=contact) as client:
        body = _ok(client, basis="ordered", by="customer", person=world.alpha)
        _denied(_lb(client, basis="ordered", by="customer", person=world.gamma))
    assert _money(body["total"]["amount"]) == D("1400.00")


def test_p6_2_an_unlinked_user_has_no_own_person_to_drill(db):
    world = _world(db)
    with make_client(db, allow=(LB,)) as client:
        _denied(_lb(client, by="customer", person=world.alpha))


def test_p6_2_reports_view_opens_invoiced_only(db):
    world = _world(db)
    with make_client(db, allow=(LB, REPORTS)) as client:
        invoiced = _ok(client, by="customer")
        _denied(_lb(client, basis="delivered", by="customer"))
        _denied(_lb(client, basis="ordered", by="customer"))
        _denied(_lb(client, basis="outstanding", by="customer", window=None))
        board = _ok(client, basis="delivered")
    assert invoiced["can_drill_others"] is True and board["can_drill_others"] is False
    assert world.c1.customer_name in _by_name(invoiced)


def test_p6_2_orders_view_opens_the_order_bases_and_not_invoiced(db):
    _world(db)
    with make_client(db, allow=(LB, ORDERS)) as client:
        for basis in ("delivered", "ordered", "outstanding"):
            body = _ok(client, basis=basis, by="customer", window=_window_of(basis))
            assert body["can_drill_others"] is True and body["rows"]
        _denied(_lb(client, basis="invoiced", by="customer"))
        assert _ok(client, basis="invoiced")["can_drill_others"] is False


@pytest.mark.parametrize("allow,can", [
    ((LB,), dict(invoiced=False, delivered=False, ordered=False, outstanding=False)),
    ((LB, REPORTS), dict(invoiced=True, delivered=False, ordered=False, outstanding=False)),
    ((LB, ORDERS), dict(invoiced=False, delivered=True, ordered=True, outstanding=True)),
    (ALL3, dict(invoiced=True, delivered=True, ordered=True, outstanding=True)),
])
def test_p6_2_options_can_mirrors_the_slugs_held(db, allow, can):
    with make_client(db, allow=allow) as client:
        resp = client.get(OPTIONS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["can"] == can


def test_p9_1_options_list_the_channels_of_each_basis(db):
    with make_client(db) as client:
        body = client.get(OPTIONS).json()
    assert set(body["channels"]) == set(BASES)
    assert body["channels"]["invoiced"] == [{"value": v, "label": label} for v, label in inv.SALES_TYPES]
    order = [{"value": "dealer", "label": "Dealer"}, {"value": "project", "label": "Project team"},
             {"value": "other", "label": "Other"}]
    assert body["channels"]["delivered"] == body["channels"]["ordered"] == body["channels"]["outstanding"] == order
    assert {"companies", "brands", "categories"} <= set(body)  # the #2227 keys stay


# =========================================================================== P4 target (Q3)


_NO = iter(range(900001, 900999))


def _target(db, agent_row, *, basis, start, end, value, no=None, method="none"):
    row = SalesTarget(
        id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, target_no=no or f"TGT-{next(_NO)}",
        name=f"ZZT target {uuid.uuid4().hex[:6]}", subject_kind="agent", sales_agent_id=agent_row.id,
        metric="amount", basis=basis, product_scope="all", start_date=start, end_date=end,
        commission_method=method, threshold_unit="pct", rounding="sen", tiers_per_period=False,
    )
    db.add(row)
    db.flush()
    period = SalesTargetPeriod(id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, target_id=row.id,
                               period_start=start, period_end=end, target_value=D(value))
    db.add(period)
    db.flush()
    return row, period


def _achieved(db, target, period):
    from app.services.sales import target_service

    by_period = target_service._achieved_by_account(db, DEFAULT_COMPANY_ID, [(target, period)])
    return sum(by_period[period.id].values(), D("0"))


def _alpha_row(body, world):
    return next(r for r in body["rows"] if r["person"] == world.alpha)


def test_p4_2_no_target_is_null_on_every_row(db):
    _world(db)
    with make_client(db) as client:
        rows = _ok(client)["rows"]
    assert rows and all("target" in r and r["target"] is None for r in rows)


def test_p4_2_a_target_of_rm_zero_is_null(db):
    world = _world(db)
    _target(db, world.a1, basis="invoiced", start=OCT_D[0], end=OCT_D[1], value="0")
    db.commit()
    with make_client(db) as client:
        assert _alpha_row(_ok(client), world)["target"] is None


def test_p4_1_an_ordered_yearly_target_is_labelled_with_its_own_basis_and_period_not_like_for_like(db):
    world = _world(db)
    target, period = _target(db, world.a2, basis="ordered", start=date(2026, 1, 1), end=date(2026, 12, 31),
                             value="10000", no="TGT-900001")  # a2: the target of any code of the person counts
    db.commit()
    achieved = _achieved(db, target, period)
    assert achieved > 0
    from app.services.sales import achievement_service

    with make_client(db) as client:
        body = _ok(client)
    got = _alpha_row(body, world)["target"]
    assert set(got) == TARGET_KEYS
    assert got["target_no"] == "TGT-900001" and got["basis"] == "ordered"
    assert (got["period_from"], got["period_to"]) == ("2026-01-01", "2026-12-31")
    assert _money(got["target_amount"]) == D("10000.00")
    assert _money(got["achieved_amount"]) == achieved
    assert got["achieved_pct"] == achievement_service.achieved_pct(achieved, D("10000"))
    assert got["like_for_like"] is False
    assert all(r["target"] is None for r in body["rows"] if r["person"] != world.alpha)


def test_p4_1_an_invoiced_monthly_target_on_the_window_is_like_for_like(db):
    world = _world(db)
    _target(db, world.a1, basis="invoiced", start=OCT_D[0], end=OCT_D[1], value="2000")
    db.commit()
    with make_client(db) as client:
        got = _alpha_row(_ok(client), world)["target"]
        shorter = _alpha_row(_ok(client, window=("2026-10-01", "2026-10-15")), world)["target"]
    assert got["basis"] == "invoiced" and (got["period_from"], got["period_to"]) == OCT
    assert _money(got["achieved_amount"]) == D("1400.00")
    assert got["achieved_pct"] == 70.0
    assert got["like_for_like"] is True
    assert shorter is not None and shorter["like_for_like"] is False  # the period is not exactly the window


def test_p4_1_the_period_must_hold_the_board_end_date(db):
    world = _world(db)
    _target(db, world.a1, basis="invoiced", start=date(2026, 11, 1), end=date(2026, 11, 30), value="2000")
    db.commit()
    with make_client(db) as client:
        assert _alpha_row(_ok(client), world)["target"] is None


def test_p4_1_the_lowest_target_no_wins(db):
    world = _world(db)
    _target(db, world.a1, basis="invoiced", start=OCT_D[0], end=OCT_D[1], value="3000", no="TGT-900020")
    _target(db, world.a2, basis="invoiced", start=OCT_D[0], end=OCT_D[1], value="2000", no="TGT-900010")
    db.commit()
    with make_client(db) as client:
        got = _alpha_row(_ok(client), world)["target"]
    assert got["target_no"] == "TGT-900010" and _money(got["target_amount"]) == D("2000.00")


def test_p4_1_only_all_products_amount_agent_targets_count(db):
    world = _world(db)
    row, _p = _target(db, world.a1, basis="invoiced", start=OCT_D[0], end=OCT_D[1], value="2000")
    row.product_scope = "brands"
    other, _q = _target(db, world.a1, basis="invoiced", start=OCT_D[0], end=OCT_D[1], value="5")
    other.metric = "quantity"
    db.commit()
    with make_client(db) as client:
        assert _alpha_row(_ok(client), world)["target"] is None


def test_p4_1_on_outstanding_the_period_must_hold_today_when_there_are_no_dates(db):
    world = _world(db)
    _target(db, world.a1, basis="ordered", start=date(2000, 1, 1), end=date(2099, 12, 31), value="5000")
    db.commit()
    with make_client(db) as client:
        rows = {r["person"]: r for r in _ok(client, basis="outstanding", window=None)["rows"]}
    got = rows[world.alpha]["target"]
    assert got is not None and got["basis"] == "ordered" and got["like_for_like"] is False
    assert (got["period_from"], got["period_to"]) == ("2000-01-01", "2099-12-31")


def test_p4_3_no_commission_tier_rate_payout_or_bonus_key_anywhere(db):
    world = _world(db)
    _target(db, world.a1, basis="invoiced", start=OCT_D[0], end=OCT_D[1], value="2000", method="marginal")
    db.commit()
    with make_client(db, allow=ALL3) as client:
        bodies = [_ok(client), _ok(client, by="customer"), _ok(client, basis="ordered")]
        options = client.get(OPTIONS).json()
    assert _alpha_row(bodies[0], world)["target"] is not None  # the scan is not vacuous
    for body in (*bodies, options):
        bad = [k for k in _keys_of(body) if any(word in str(k).lower() for word in FORBIDDEN)]
        assert bad == []


# ========================================================================== validation (422)


@pytest.mark.parametrize("extra", [
    {"basis": "bogus"}, {"basis": "pending_delivery"}, {"basis": "unpaid"}, {"by": "bogus"}, {"by": "sales_agent"},
])
def test_p10_1_a_bad_basis_or_by_is_422_report_invalid_params(db, extra):
    with make_client(db, allow=ALL3) as client:
        resp = client.get(ROUTE, params={"date_from": OCT[0], "date_to": OCT[1], **extra})
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") == "REPORT_INVALID_PARAMS"


@pytest.mark.parametrize("params", [
    {"basis": "outstanding", "date_from": OCT[0]},
    {"basis": "outstanding", "date_to": OCT[1]},
    {"basis": "invoiced"},
    {"basis": "delivered"},
    {"basis": "ordered", "date_from": OCT[0]},
    {"basis": "invoiced", "date_from": OCT[1], "date_to": OCT[0]},
])
def test_p10_2_dates_are_required_except_outstanding_with_neither(db, params):
    with make_client(db, allow=ALL3) as client:
        resp = client.get(ROUTE, params=params)
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") == "REPORT_INVALID_PARAMS"


def test_p10_1_a_non_uuid_customer_or_product_drill_is_422(db):
    with make_client(db, allow=ALL3) as client:
        for key in ("customer", "product"):
            resp = _lb(client, by="product", **{key: "not-a-uuid"})
            assert resp.status_code == 422, resp.text
            assert resp.json().get("code") == "REPORT_INVALID_PARAMS"


def test_p10_1_the_default_basis_is_invoiced_and_the_default_view_is_person(db):
    _world(db)
    with make_client(db) as client:
        body = client.get(ROUTE, params={"date_from": OCT[0], "date_to": OCT[1]}).json()
    assert (body["basis"], body["by"]) == ("invoiced", "person")
    assert _money(body["total"]["amount"]) == D("2020.00")


# ============================================================================ P7 the assistant


def test_p7_1_crm_report_ask_sales_person_filter_on_invoiced_equals_the_drill_rows(db):
    world = _world(db)
    contact = _contact(db)
    _access(db, contact, "Sorento Office")
    db.commit()
    with make_client(db, allow=ALL3, grants=(DEFAULT_COMPANY_ID,)) as client:
        resp = _assistant_ask(client, contact, basis="invoiced", group_by="customer", measure="amount",
                              top_n=50, sales_person=world.alpha)
        assert resp.status_code == 200, resp.text
        asked = _by_name(resp.json())
        drill = _by_name(_ok(client, by="customer", person=world.alpha, company=DEFAULT_COMPANY_ID))
        echoed = resp.json()["filters"]
    assert asked == drill == {world.c1.customer_name: D("1000.00"), world.c2.customer_name: D("400.00")}
    assert any(world.alpha in f["values"] for f in echoed)


@pytest.mark.parametrize("basis,expected", [("delivered", D("1000.00")), ("ordered", D("1400.00"))])
def test_p7_1_crm_report_ask_sales_person_filter_also_works_on_the_order_bases(db, basis, expected):
    world = _world(db)
    contact = _contact(db)
    _access(db, contact, "Sorento Office")
    db.commit()
    with make_client(db, allow=ALL3, grants=(DEFAULT_COMPANY_ID,)) as client:
        resp = _assistant_ask(client, contact, basis=basis, measure="amount", sales_person=world.alpha,
                              date_from="2026-10-01", date_to="2026-10-31")
    assert resp.status_code == 200, resp.text
    assert _money(resp.json()["total"]["amount"]) == expected
