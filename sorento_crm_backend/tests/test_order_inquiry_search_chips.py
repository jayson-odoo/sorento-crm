"""SEARCH-CHIPS slice 2: the Order inquiries Documents list (`GET
/api/v1/project-sales/order-inquiry-headers`, `OrderInquiryHeaderService.list`) search takes
several values (one repeated `query` param per chip) and returns a header matching ANY of them,
each value matched over the list's existing search fields (OI no, legacy no, S/O no, customer,
project, agent, a live line's item code or location). Same behaviour as slice 1, UAC
`documentation/plans/ui/search-chips-acceptance-criteria.md` B1-B6; plan
`documentation/plans/ui/PLAN-search-chips-b-12nov.md`.

Red first. Postgres only: every row is seeded here into a blank schema (`blank_session`) and
asserted through HTTP. Names are fake.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.order import SalesOrder
from app.models.project_so import (
    INQUIRY_RAISED,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.sales_agent import SalesAgent
from app.services import project_seed_service
from app.services.project_service import register_project
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code
from tests.test_order_inquiry_worklist import (
    _customer,
    _inquiry_for,
    _product,
    _row,
    _sorento,
    _user,
)

HEADERS = "/api/v1/project-sales/order-inquiry-headers"


def _uid() -> str:
    return str(uuid.uuid4())


def _order(db, company_id, user_id, *, so_number, customer_name, agent, location):
    """One registered project, one adopted-style order, one inquiry, one live row."""
    proj = register_project(
        db, company_id=company_id, actor_user_id=user_id, developer_party_id=None,
        title=f"ZZT OIC proj {so_number}", skip_clash_check=True,
    )
    customer = _customer(db, company_id, customer_name)
    core = SalesOrder(id=_uid(), company_id=company_id, so_number=so_number, customer_id=customer.id,
                      sales_agent_id=agent.id)
    db.add(core)
    db.flush()
    pso = ProjectSalesOrder(
        id=_uid(), company_id=company_id, project_id=proj.id, so_id=core.id, provisional_ref=so_number,
        autocount_doc_no=so_number, status="adopted",
    )
    db.add(pso)
    db.flush()
    product = _product(db, f"ZZT-OIC-{_uid()[:6]}", f"ZZT OIC prod {so_number}")
    line = ProjectSalesOrderLine(
        id=_uid(), company_id=company_id, project_sales_order_id=pso.id, line_no=1, product_id=product.id,
        description=f"ZZT OIC {so_number}", qty=Decimal("5"), uom="UNIT", unit_price=Decimal("1"),
        amount=Decimal("5"),
    )
    db.add(line)
    db.flush()
    inquiry = _inquiry_for(db, company_id, pso)
    inquiry.raised_by = user_id
    _row(db, company_id, inquiry, so_line_id=line.id, item_code=product.product_code, qty="5",
         state=INQUIRY_RAISED, stock_location=location)
    return inquiry


@pytest.fixture
def world():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user = _user(db, "ZZT OIC user")
        agent = SalesAgent(id=_uid(), company_id=company_id, sales_agent=f"ZZT-OIC-AG-{_uid()[:4]}")
        db.add(agent)
        db.flush()
        tag = unique_code("OIC", alpha=True).replace("-", "")
        o = {"tag": tag}
        spec = [
            ("alpha", f"{tag}ALPHA", "ZZT Plain Customer", "ZZT-LOC-A"),
            ("bravo", f"{tag}BRAVO", "ZZT Plain Customer", "ZZT-LOC-B"),
            ("comma", f"{tag}CHARLIE", f"{tag} Acme, Trading", "ZZT-LOC-C"),
            ("acme_only", f"{tag}DELTA", f"{tag} Acme Holdings", "ZZT-LOC-D"),
            ("trading_only", f"{tag}ECHO", "Trading Bee Fakeco", "ZZT-LOC-E"),
            ("by_location", f"{tag}FOXTROT", "ZZT Plain Customer", f"{tag}LOCZZ"),
        ]
        for key, so_number, customer_name, location in spec:
            o[key] = _order(db, company_id, user, so_number=so_number, customer_name=customer_name,
                            agent=agent, location=location)
            o[f"{key}_so"] = so_number
        db.commit()
        yield db, company_id, o


@pytest.fixture
def client(world, monkeypatch):
    db, company_id, _ = world
    with company_scope(db, frozenset({company_id})):
        with open_client(db, monkeypatch, scope=frozenset({company_id})) as (c, _actor):
            yield c


def _q(*values):
    return [("query", v) for v in values]


def _list(client, pairs):
    resp = get(client, HEADERS, [("limit", 100), ("state", "all"), *pairs])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids(body):
    return {r["id"] for r in body["data"]}


def _n(o, *keys):
    return {o[k].id for k in keys}


def test_repeated_query_returns_the_union(client, world):
    _db, _cid, o = world
    body = _list(client, _q(o["alpha_so"], o["bravo_so"]))
    assert _ids(body) == _n(o, "alpha", "bravo")
    assert body["pagination"]["total"] == 2


def test_each_value_matched_over_so_number_customer_and_line_location(client, world):
    _db, _cid, o = world
    body = _list(client, _q(o["alpha_so"], "Acme, Trading", f"{o['tag']}LOCZZ"))
    assert _ids(body) == _n(o, "alpha", "comma", "by_location")


def test_single_query_behaves_as_today(client, world):
    _db, _cid, o = world
    body = _list(client, _q(o["alpha_so"]))
    assert _ids(body) == _n(o, "alpha")
    assert body["pagination"]["total"] == 1


def test_single_query_on_line_location_behaves_as_today(client, world):
    _db, _cid, o = world
    assert _ids(_list(client, _q(f"{o['tag']}LOCZZ"))) == _n(o, "by_location")


def test_a_value_matching_nothing_adds_no_rows(client, world):
    _db, _cid, o = world
    assert _ids(_list(client, _q(o["alpha_so"], "ZZNOTHINGMATCHESTHIS"))) == _n(o, "alpha")


def test_comma_inside_a_value_is_one_value(client, world):
    _db, _cid, o = world
    # Split on the comma, "Acme" would also find DELTA and "Trading" ECHO.
    body = _list(client, _q("Acme, Trading", o["alpha_so"]))
    assert _ids(body) == _n(o, "comma", "alpha")


def test_blank_and_case_duplicate_values_are_ignored(client, world):
    _db, _cid, o = world
    a = o["alpha_so"]
    body = _list(client, _q(a, "", "  ", a.lower(), o["bravo_so"]))
    assert _ids(body) == _n(o, "alpha", "bravo")
    assert body["pagination"]["total"] == 2


def test_more_than_200_values_is_422(client, world):
    resp = get(client, HEADERS, [("state", "all"), *_q(*[f"ZZV{i:03d}" for i in range(201)])])
    assert resp.status_code == 422, resp.text
    assert "at most 200 values" in resp.text


def test_exactly_200_values_is_accepted(client, world):
    _db, _cid, o = world
    values = [o["bravo_so"]] + [f"ZZV{i:03d}" for i in range(199)]
    assert _ids(_list(client, _q(*values))) == _n(o, "bravo")


def test_a_value_over_100_characters_is_422(client, world):
    resp = get(client, HEADERS, [("state", "all"), *_q("OI1", "X" * 101)])
    assert resp.status_code == 422, resp.text
    assert "100" in resp.text, resp.text


def test_a_value_of_exactly_100_characters_is_accepted(client, world):
    _db, _cid, o = world
    resp = get(client, HEADERS, [("limit", 100), ("state", "all"), *_q(o["alpha_so"], "Z" * 100)])
    assert resp.status_code == 200, resp.text
    assert _ids(resp.json()) == _n(o, "alpha")
