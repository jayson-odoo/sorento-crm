"""FILTER-MULTISELECT PR6 (order inquiries): the Lines worklist (`GET /order-inquiries`) takes several
Locations, Agents, States, Suppliers, Projects and Raised-by people, the Documents list
(`GET /order-inquiry-headers`) several Raised-by, Agents and Projects, the per-project rows several
Instructions and States. OR within a filter, AND across; comma-joined, repeated and single all read.
Yes/no style filters (linked, dead_document, reserve) stay single. Red first; Postgres only; every row
seeded here.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_CANCEL_BALANCE,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.order import SalesOrder
from app.models.sales_agent import SalesAgent
from app.services import project_seed_service
from app.services.project_service import register_project
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session
from tests.test_order_inquiry_worklist import (
    _customer,
    _inquiry_for,
    _placed_supply,
    _product,
    _row,
    _sorento,
    _user,
)

BASE = "/api/v1/project-sales"
LINES = f"{BASE}/order-inquiries"
HEADERS = f"{BASE}/order-inquiry-headers"
TAG = "ZZT-OIM"


def _uid() -> str:
    return str(uuid.uuid4())


def _order(db, company_id, user_id, key, *, state, location, agent, project, supplier):
    """One registered project, one adopted-style order with an agent, one inquiry, one row."""
    proj = register_project(
        db, company_id=company_id, actor_user_id=user_id, developer_party_id=None, title=f"{TAG} proj {key}", skip_clash_check=True
    )
    customer = _customer(db, company_id, f"{TAG} cust {key}")
    core = SalesOrder(
        id=_uid(), company_id=company_id, so_number=f"ZZTOIM{_uid()[:8]}", customer_id=customer.id,
        sales_agent_id=agent.id,
    )
    db.add(core)
    db.flush()
    pso = ProjectSalesOrder(
        id=_uid(), company_id=company_id, project_id=proj.id, so_id=core.id, provisional_ref=core.so_number,
        autocount_doc_no=core.so_number, status="adopted",
    )
    db.add(pso)
    db.flush()
    product = _product(db, f"ZZT-OIM-{_uid()[:6]}", f"{TAG} prod {key}")
    line = ProjectSalesOrderLine(
        id=_uid(), company_id=company_id, project_sales_order_id=pso.id, line_no=1, product_id=product.id,
        description=f"{TAG} {key}", qty=Decimal("5"), uom="UNIT", unit_price=Decimal("1"), amount=Decimal("5"),
    )
    db.add(line)
    db.flush()
    inquiry = _inquiry_for(db, company_id, pso)
    inquiry.raised_by = user_id
    row = _row(
        db, company_id, inquiry, so_line_id=line.id, item_code=product.product_code, qty="5", state=state,
        stock_location=location,
    )
    return dict(project=proj, agent=agent, inquiry=inquiry, row=row, user=user_id, location=location, pso=pso)


@pytest.fixture
def world():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        users = [_user(db, f"{TAG} user {k}") for k in "abc"]
        agents = []
        for k in "abc":
            a = SalesAgent(id=_uid(), company_id=company_id, sales_agent=f"{TAG}-AG-{k}-{_uid()[:4]}")
            db.add(a)
            agents.append(a)
        db.flush()
        spec = [
            ("a", INQUIRY_RAISED, "ZZT-LOC-A"),
            ("b", INQUIRY_ACTIONED, "ZZT-LOC-B"),
            ("c", INQUIRY_PLACED, "ZZT-LOC-C"),
        ]
        orders = {}
        for i, (k, state, loc) in enumerate(spec):
            orders[k] = _order(
                db, company_id, users[i], k, state=state, location=loc, agent=agents[i], project=None, supplier=None
            )
        orders["a"]["supplier"] = _placed_supply(db, company_id, orders["a"]["row"], supplier_name=f"{TAG} SUP A")["supplier"]
        orders["b"]["supplier"] = _placed_supply(db, company_id, orders["b"]["row"], supplier_name=f"{TAG} SUP B")["supplier"]
        db.commit()
        yield db, company_id, orders


@pytest.fixture
def client(world, monkeypatch):
    db, company_id, _ = world
    with company_scope(db, frozenset({company_id})):
        with open_client(db, monkeypatch, scope=frozenset({company_id})) as (c, _actor):
            yield c


def _line_ids(client, world, pairs):
    _db, _cid, o = world
    ours = {x["row"].id for x in o.values()}
    resp = get(client, LINES, [("limit", 100), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]} & ours


def _header_ids(client, world, pairs):
    _db, _cid, o = world
    ours = {x["inquiry"].id for x in o.values()}
    resp = get(client, HEADERS, [("limit", 100), ("state", "all"), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]} & ours


def _rid(o, *keys):
    return {o[k]["row"].id for k in keys}


# ---- Lines: Location, Agent, State, Supplier, Project, Raised by -------------------------------------

LINE_FILTERS = [
    ("location", lambda o, k: o[k]["location"]),
    ("agent", lambda o, k: o[k]["agent"].id),
    ("state", lambda o, k: o[k]["row"].state),
    ("project_id", lambda o, k: o[k]["project"].id),
    ("raised_by", lambda o, k: o[k]["user"]),
]


@pytest.mark.parametrize("param,val", LINE_FILTERS)
def test_lines_single_value_still_reads(client, world, param, val):
    o = world[2]
    assert _line_ids(client, world, [(param, val(o, "b"))]) == _rid(o, "b")


@pytest.mark.parametrize("param,val", LINE_FILTERS)
def test_lines_comma_joined_is_a_union(client, world, param, val):
    o = world[2]
    assert _line_ids(client, world, [(param, f"{val(o, 'a')},{val(o, 'c')}")]) == _rid(o, "a", "c")


@pytest.mark.parametrize("param,val", LINE_FILTERS)
def test_lines_repeated_param_is_a_union(client, world, param, val):
    o = world[2]
    assert _line_ids(client, world, [(param, val(o, "a")), (param, val(o, "b"))]) == _rid(o, "a", "b")


def test_lines_supplier_union(client, world):
    o = world[2]
    sa, sb = o["a"]["supplier"].id, o["b"]["supplier"].id
    assert _line_ids(client, world, [("supplier_id", sa)]) == _rid(o, "a")
    assert _line_ids(client, world, [("supplier_id", f"{sa},{sb}")]) == _rid(o, "a", "b")
    assert _line_ids(client, world, [("supplier_id", sa), ("supplier_id", sb)]) == _rid(o, "a", "b")


def test_lines_filters_and_across(client, world):
    o = world[2]
    got = _line_ids(
        client, world,
        [("state", f"{INQUIRY_RAISED},{INQUIRY_ACTIONED}"), ("agent", f"{o['b']['agent'].id},{o['c']['agent'].id}")],
    )
    assert got == _rid(o, "b")


def test_lines_malformed_uuid_in_a_list_is_refused_not_a_500(client, world):
    o = world[2]
    resp = get(client, LINES, [("agent", f"{o['a']['agent'].id},not-a-uuid")])
    assert resp.status_code in (404, 422), resp.text


def test_lines_yes_no_style_filters_stay_single(client, world):
    assert get(client, LINES, [("linked", "none")]).status_code == 200
    assert get(client, LINES, [("linked", "po,spo")]).status_code == 422
    assert get(client, LINES, [("dead_document", "po_cancelled,spo_withdrawn")]).status_code == 422
    assert get(client, LINES, [("reserve", "parked,reserved")]).status_code == 422


# ---- Documents (headers): Raised by, Agent, Project -------------------------------------------------

HEADER_FILTERS = [
    ("raised_by", lambda o, k: o[k]["user"]),
    ("agent", lambda o, k: o[k]["agent"].sales_agent),
    ("project", lambda o, k: o[k]["project"].title),
]


@pytest.mark.parametrize("param,val", HEADER_FILTERS)
def test_headers_single_value_still_reads(client, world, param, val):
    o = world[2]
    assert _header_ids(client, world, [(param, val(o, "b"))]) == {o["b"]["inquiry"].id}


@pytest.mark.parametrize("param,val", HEADER_FILTERS)
def test_headers_comma_joined_is_a_union(client, world, param, val):
    o = world[2]
    if param == "project":
        # Free-text titles ride repeated params (a title may hold a comma), never comma-joined.
        pairs = [(param, val(o, "a")), (param, val(o, "c"))]
    else:
        pairs = [(param, f"{val(o, 'a')},{val(o, 'c')}")]
    got = _header_ids(client, world, pairs)
    assert got == {o["a"]["inquiry"].id, o["c"]["inquiry"].id}


@pytest.mark.parametrize("param,val", HEADER_FILTERS)
def test_headers_repeated_param_is_a_union(client, world, param, val):
    o = world[2]
    got = _header_ids(client, world, [(param, val(o, "a")), (param, val(o, "b"))])
    assert got == {o["a"]["inquiry"].id, o["b"]["inquiry"].id}


def test_headers_project_title_with_a_comma_is_not_split_wrongly_for_one_value(client, world):
    o = world[2]
    got = _header_ids(client, world, [("project", o["a"]["project"].title), ("agent", o["a"]["agent"].sales_agent)])
    assert got == {o["a"]["inquiry"].id}


def test_headers_filters_and_across(client, world):
    o = world[2]
    got = _header_ids(
        client, world,
        [("agent", f"{o['a']['agent'].sales_agent},{o['b']['agent'].sales_agent}"), ("raised_by", f"{o['b']['user']},{o['c']['user']}")],
    )
    assert got == {o["b"]["inquiry"].id}


def test_headers_reserve_stays_single(client, world):
    assert get(client, HEADERS, [("reserve", "parked,reserved")]).status_code == 422


# ---- per-project rows: Instruction, State (already List[str]; guard) --------------------------------

def test_project_rows_instruction_and_state_take_several(client, world):
    db, _cid, o = world
    pid = o["c"]["project"].id
    # Row c is an Order instruction in state placed. Repeated is the guard, comma-joined is the FE's new shape.
    url = f"{BASE}/projects/{pid}/order-inquiry-rows"
    only_c = {o["c"]["row"].id}
    repeated = get(client, url, [("state", INQUIRY_RAISED), ("state", INQUIRY_PLACED), ("verb", IV_ORDER), ("verb", IV_CANCEL_BALANCE)])
    assert repeated.status_code == 200, repeated.text
    assert {r["id"] for r in repeated.json()["data"]} == only_c
    joined = get(client, url, [("state", f"{INQUIRY_RAISED},{INQUIRY_PLACED}"), ("verb", f"{IV_ORDER},{IV_CANCEL_BALANCE}")])
    assert joined.status_code == 200, joined.text
    assert {r["id"] for r in joined.json()["data"]} == only_c
