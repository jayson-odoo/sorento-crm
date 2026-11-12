"""SEARCH-CHIPS slice 1: the Sales orders list search takes several values (one repeated `query`
param per chip) and returns a row matching ANY of them. UAC
`documentation/plans/ui/search-chips-acceptance-criteria.md` B1-B8; the rule lives in ONE place,
`SEARCH_VALUES_MATCH` in `app/utils/list_search.py`.

Red first. Postgres only: every row is seeded here into a blank schema (`blank_session`) and
asserted through HTTP, plus unit tests of `search_values_filter`. Names are fake.
"""
from __future__ import annotations

import re
import uuid
from datetime import date

import pytest
from sqlalchemy import Column, MetaData, String, Table, any_, event, literal
from sqlalchemy.dialects import postgresql

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.sales_agent import SalesAgent
from app.services.scm.po_ref import po_ref_key
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

LIST = "/api/v1/scm/sales-orders"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _so(db, number, **kw):
    row = SalesOrder(id=_u(), so_number=number, status=kw.pop("status", "open"),
                     order_date=kw.pop("order_date", date(2026, 6, 1)), **kw)
    db.add(row)
    db.flush()
    return row


def _line(db, so, product):
    db.add(SalesOrderLine(id=_u(), sales_order_id=so.id, product_id=product.id,
                          qty_ordered=1, qty_delivered=0, line_status="open"))
    db.flush()


@pytest.fixture
def seeded(db):
    """Each value below matches exactly one order, over a different field of today's search."""
    tag = unique_code("SCH", alpha=True)
    cat = ProductCategory(id=_u(), category_code=unique_code("CAT"), category_name=f"{tag} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{tag} u")
    db.add_all([cat, uom])
    db.flush()
    widget = Product(id=_u(), product_code=f"{tag}PWIDGET", product_name=f"{tag} Gizmo Widget",
                     category_id=cat.id, base_uom_id=uom.id, list_price=0,
                     is_active=True, is_discontinued=False)
    sprocket = Product(id=_u(), product_code=f"{tag}PSPROCKET", product_name=f"{tag} Sprocket",
                       category_id=cat.id, base_uom_id=uom.id, list_price=0,
                       is_active=True, is_discontinued=False)
    cust_a = Customer(id=_u(), customer_code=unique_code("CA"), customer_name=f"{tag} Fakeco Holdings")
    cust_b = Customer(id=_u(), customer_code=unique_code("CB"), customer_name=f"{tag} Other Co")
    agent = SalesAgent(id=_u(), sales_agent=unique_code("AGT"), person_label=f"{tag} AGENTPERSON",
                       is_active=True)
    db.add_all([widget, sprocket, cust_a, cust_b, agent])
    db.flush()

    s = dict(tag=tag, cust_a=cust_a, cust_b=cust_b, widget=widget, sprocket=sprocket, agent=agent)
    s["alpha"] = _so(db, f"{tag}-ALPHA", customer_id=cust_b.id)
    s["bravo"] = _so(db, f"{tag}-BRAVO", status="closed", customer_id=cust_b.id)
    s["comma"] = _so(db, f"{tag}-CHARLIE", debtor_name=f"{tag} Acme, Trading")
    s["acme_only"] = _so(db, f"{tag}-DELTA", debtor_name=f"{tag} Acme Holdings")
    s["trading_only"] = _so(db, f"{tag}-ECHO", debtor_name="Trading Bee")
    s["by_customer"] = _so(db, f"{tag}-FOXTROT", customer_id=cust_a.id)
    s["by_line"] = _so(db, f"{tag}-GOLF")
    _line(db, s["by_line"], widget)
    s["by_agent"] = _so(db, f"{tag}-HOTEL", sales_agent_id=agent.id)
    s["by_project"] = _so(db, f"{tag}-INDIA", project_label=f"{tag} BAMBOOPROJECT")
    s["by_po"] = _so(db, f"{tag}-JULIET", po_ref="PO-4500 123", po_ref_key=po_ref_key("PO-4500 123"))
    # Matches the SO-number value AND, on two lines, the product value: still ONE row (B3).
    s["twice"] = _so(db, f"{tag}-KILO")
    _line(db, s["twice"], sprocket)
    _line(db, s["twice"], sprocket)
    return s


def _list(client, pairs):
    resp = get(client, LIST, [("limit", 200), *pairs])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _numbers(body):
    return [r["so_number"] for r in body["data"]]


def _q(*values):
    return [("query", v) for v in values]


def _n(s, *keys):
    return {s[k].so_number for k in keys}


# --------------------------------------------------------------------------- #
# B1 repeated query = union; single query unchanged
# --------------------------------------------------------------------------- #

def test_b1_repeated_query_returns_the_union(client, seeded):
    s = seeded
    body = _list(client, _q(s["alpha"].so_number, s["bravo"].so_number))
    assert set(_numbers(body)) == _n(s, "alpha", "bravo")
    assert body["pagination"]["total"] == 2


def test_b1_single_query_behaves_as_today(client, seeded):
    s = seeded
    body = _list(client, _q(s["alpha"].so_number))
    assert set(_numbers(body)) == _n(s, "alpha")
    assert body["pagination"]["total"] == 1


# --------------------------------------------------------------------------- #
# B2 every value matched over the same fields as today
# --------------------------------------------------------------------------- #

def test_b2_each_value_matched_over_every_search_field(client, seeded):
    s, tag = seeded, seeded["tag"]
    body = _list(client, _q(
        f"{tag}-ALPHA",            # SO number
        "Acme, Trading",          # debtor name
        "Fakeco Holdings",        # linked customer name
        "Gizmo Widget",           # a line's product name
        "AGENTPERSON",            # agent person
        "BAMBOOPROJECT",          # project label
        "po 4500-123",            # folded PO ref key
    ))
    assert set(_numbers(body)) == _n(s, "alpha", "comma", "by_customer", "by_line", "by_agent",
                                     "by_project", "by_po")


@pytest.mark.parametrize("value,key", [
    ("-ALPHA", "alpha"), ("Acme, Trading", "comma"), ("Fakeco Holdings", "by_customer"),
    ("Gizmo Widget", "by_line"), ("AGENTPERSON", "by_agent"), ("BAMBOOPROJECT", "by_project"),
    ("po 4500-123", "by_po"),
])
def test_b2_guard_each_value_alone_finds_its_row_today(client, seeded, value, key):
    """Fixture guard (green before and after): each seeded value finds its row on its own."""
    s = seeded
    body = _list(client, _q(f"{s['tag']}{value}" if value.startswith("-") else value))
    assert set(_numbers(body)) == _n(s, key)


def test_b2_line_product_code_and_agent_code_are_matched(client, seeded):
    s = seeded
    body = _list(client, _q(s["widget"].product_code, s["agent"].sales_agent))
    assert set(_numbers(body)) == _n(s, "by_line", "by_agent")


def test_b2_a_value_matching_nothing_adds_no_rows(client, seeded):
    s = seeded
    body = _list(client, _q(s["alpha"].so_number, "ZZNOTHINGMATCHESTHIS"))
    assert set(_numbers(body)) == _n(s, "alpha")


# --------------------------------------------------------------------------- #
# B3 one row, counted once
# --------------------------------------------------------------------------- #

def test_b3_order_matching_two_values_and_two_lines_is_one_row(client, seeded):
    s = seeded
    body = _list(client, _q(s["twice"].so_number, s["sprocket"].product_code, s["alpha"].so_number))
    assert sorted(_numbers(body)) == sorted(_n(s, "twice", "alpha"))
    assert body["pagination"]["total"] == 2


# --------------------------------------------------------------------------- #
# B4 a comma inside a value is kept whole
# --------------------------------------------------------------------------- #

def test_b4_comma_inside_a_value_is_one_value(client, seeded):
    s = seeded
    # Split on the comma, "Acme" would also find DELTA and "Trading" ECHO.
    body = _list(client, _q("Acme, Trading", s["alpha"].so_number))
    assert set(_numbers(body)) == _n(s, "comma", "alpha")


# --------------------------------------------------------------------------- #
# B5 blanks and case-insensitive duplicates ignored
# --------------------------------------------------------------------------- #

def test_b5_blank_and_duplicate_values_are_ignored(client, seeded):
    s = seeded
    alpha, bravo = s["alpha"].so_number, s["bravo"].so_number
    body = _list(client, _q(alpha, "", "   ", alpha.lower(), alpha.upper(), bravo))
    assert set(_numbers(body)) == _n(s, "alpha", "bravo")
    assert body["pagination"]["total"] == 2


def test_b5_case_duplicates_and_blanks_do_not_count_towards_the_cap(client, seeded):
    s = seeded
    values = [s["alpha"].so_number] + [f"ZZNOPE{i:03d}" for i in range(199)]
    # 200 distinct values, plus blanks and case variants of ones already given: not 201.
    extra = ["", "  ", s["alpha"].so_number.lower(), "zznope000", "ZZnope001"]
    resp = get(client, LIST, [("limit", 200), *_q(*values, *extra)])
    assert resp.status_code == 200, resp.text
    assert set(_numbers(resp.json())) == _n(s, "alpha")


# --------------------------------------------------------------------------- #
# B6 more than 200 values -> 422
# --------------------------------------------------------------------------- #

def test_b6_more_than_200_values_is_422(client, seeded):
    resp = get(client, LIST, _q(*[f"ZZV{i:03d}" for i in range(201)]))
    assert resp.status_code == 422, resp.text
    assert "at most 200 values" in resp.text


def test_b6_exactly_200_values_is_accepted(client, seeded):
    s = seeded
    values = [s["bravo"].so_number] + [f"ZZV{i:03d}" for i in range(199)]
    body = _list(client, _q(*values))
    assert set(_numbers(body)) == _n(s, "bravo")


# --------------------------------------------------------------------------- #
# B7 AND with filters; sort and paging unchanged
# --------------------------------------------------------------------------- #

def test_b7_values_and_with_a_status_filter(client, seeded):
    s = seeded
    body = _list(client, [*_q(s["bravo"].so_number, s["alpha"].so_number), ("status", "closed")])
    assert set(_numbers(body)) == _n(s, "bravo")


def test_b7_values_and_with_a_customer_filter(client, seeded):
    s = seeded
    # alpha + bravo belong to cust_b, by_customer to cust_a.
    pairs = [*_q("Fakeco Holdings", s["alpha"].so_number, s["bravo"].so_number),
             ("customer_code", s["cust_a"].customer_code)]
    body = _list(client, pairs)
    assert set(_numbers(body)) == _n(s, "by_customer")
    assert body["pagination"]["total"] == 1


def test_b7_page_two_continues_the_same_order(client, seeded):
    s, tag = seeded, seeded["tag"]
    values = [f"{tag}-ALPHA", f"{tag}-BRAVO", "Acme, Trading", "Gizmo Widget", "AGENTPERSON"]
    expected = sorted(_n(s, "alpha", "bravo", "comma", "by_line", "by_agent"))

    seen = []
    for page in (1, 2, 3):
        resp = get(client, LIST, [("page", page), ("limit", 2), ("sort", "so_number"), ("dir", "asc"),
                                  *_q(*values)])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["pagination"]["total"] == 5
        seen.extend(_numbers(body))
    assert seen == expected


# --------------------------------------------------------------------------- #
# B8 one statement, ILIKE ANY, predicates do not grow with the values
# --------------------------------------------------------------------------- #

def _capture_sql(db):
    statements: list[str] = []
    conn = db.connection()

    def _before(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(conn, "before_cursor_execute", _before)
    return conn, _before, statements


def _list_sql(client, db, values):
    conn, hook, statements = _capture_sql(db)
    try:
        resp = get(client, LIST, _q(*values))
    finally:
        event.remove(conn, "before_cursor_execute", hook)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []
    return [st for st in statements if re.search(r"\bilike\b", st, re.I)]


def test_b8_list_sql_uses_ilike_any_and_does_not_grow_per_value(client, db, seeded):
    two = _list_sql(client, db, ["ZZNOMATCHA", "ZZNOMATCHB"])
    six = _list_sql(client, db, [f"ZZNOMATCH{i}" for i in range(6)])

    # Same number of searching statements (no per-value query) ...
    assert len(two) == len(six) and len(two) >= 1
    # ... each with the same number of ILIKE predicates (no OR branch per value) ...
    assert [len(re.findall(r"\bilike\b", st, re.I)) for st in two] == \
           [len(re.findall(r"\bilike\b", st, re.I)) for st in six]
    # ... matched against an array of the values.
    assert all(re.search(r"\bilike\s+any\s*\(", st, re.I) for st in six), six


# --------------------------------------------------------------------------- #
# search_values_filter: the rule in ONE place
# --------------------------------------------------------------------------- #

_T = Table("zz_chip_probe", MetaData(), Column("name", String))


def _match_recording(calls):
    def match(values):
        calls.append(list(values))
        return _T.c.name.ilike(any_(postgresql.array([literal(f"%{v}%") for v in values])))
    return match


def _sql(clause) -> str:
    return str(clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_rule_defaults_to_any():
    from app.utils.list_search import SEARCH_VALUES_MATCH

    assert SEARCH_VALUES_MATCH == "any"


def test_any_calls_match_once_with_every_value():
    from app.utils.list_search import search_values_filter

    calls: list[list[str]] = []
    clause = search_values_filter(["A1", "B2", "C3", "D4"], _match_recording(calls))
    assert calls == [["A1", "B2", "C3", "D4"]]
    sql = _sql(clause)
    assert re.search(r"ILIKE ANY \(ARRAY\[", sql), sql
    assert len(re.findall(r"\bILIKE\b", sql)) == 1
    assert " AND " not in sql


def test_any_predicate_count_does_not_grow_with_values():
    from app.utils.list_search import search_values_filter

    few = _sql(search_values_filter(["A"], _match_recording([])))
    many = _sql(search_values_filter([f"V{i}" for i in range(50)], _match_recording([])))
    assert len(re.findall(r"\bILIKE\b", few)) == len(re.findall(r"\bILIKE\b", many)) == 1


def test_all_ands_one_match_per_value(monkeypatch):
    from app.utils import list_search

    monkeypatch.setattr(list_search, "SEARCH_VALUES_MATCH", "all")
    calls: list[list[str]] = []
    clause = list_search.search_values_filter(["A1", "B2", "C3"], _match_recording(calls))
    assert calls == [["A1"], ["B2"], ["C3"]]
    sql = _sql(clause)
    assert len(re.findall(r"\bILIKE\b", sql)) == 3
    assert sql.count(" AND ") == 2
    for value in ["A1", "B2", "C3"]:
        assert f"ARRAY['%{value}%']" in sql, sql


def test_all_switch_reaches_the_list_route(client, seeded, monkeypatch):
    """The route goes through the ONE switch: flipped to "all", a row must match every value."""
    from app.utils import list_search

    s, tag = seeded, seeded["tag"]
    monkeypatch.setattr(list_search, "SEARCH_VALUES_MATCH", "all")
    assert _numbers(_list(client, _q(s["alpha"].so_number, s["bravo"].so_number))) == []
    assert set(_numbers(_list(client, _q(tag, "ALPHA")))) == _n(s, "alpha")
