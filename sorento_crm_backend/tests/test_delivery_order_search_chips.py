"""SEARCH-CHIPS slice 2: the Delivery orders list (`POST /api/v1/list-query/search`, resource
`orders`, `OrderService.list_orders`) takes several search values: `quick_search` in the body
becomes a LIST of strings (a plain string stays accepted) and an order matching ANY value is
returned, each value matched over the list's existing search fields. The export twin
(`POST /api/v1/list-query/export`, `ListQueryExportService._export_orders`) returns the same rows
for the same list. Same behaviour as slice 1, UAC
`documentation/plans/ui/search-chips-acceptance-criteria.md` B1-B6 + S5; plan
`documentation/plans/ui/PLAN-search-chips-b-12nov.md`.

Red first. Postgres only: every row is seeded here into a blank schema (`blank_session`) and
asserted through HTTP. Names are fake.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.list_query_metadata import ListQueryField, ListQueryResource
from app.models.order import Customer, Order
from app.services.user_service import UserPermissionService
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

SEARCH = "/api/v1/list-query/search"
EXPORT = "/api/v1/list-query/export"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"})
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _resource(db):
    res = ListQueryResource(id=_u(), resource_key="orders", display_name="orders", is_active=True)
    db.add(res)
    db.flush()
    db.add(ListQueryField(id=_u(), resource_id=res.id, field_key="order_number", label="order_number",
                          data_type="string", compile_key="order.order_number", allowed_operators=["eq"],
                          filterable=True, exportable=True))
    db.flush()


def _order(db, number, **kw):
    row = Order(id=_u(), order_number=number, **kw)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def seeded(db):
    _resource(db)
    tag = unique_code("DOC", alpha=True)
    fakeco = Customer(id=_u(), customer_code=unique_code("CA"), customer_name=f"{tag} Fakeco Holdings")
    db.add(fakeco)
    db.flush()
    s = dict(tag=tag)
    s["alpha"] = _order(db, f"{tag}-ALPHA")
    s["bravo"] = _order(db, f"{tag}-BRAVO")
    s["comma"] = _order(db, f"{tag}-CHARLIE", debtor_name=f"{tag} Acme, Trading")
    s["acme_only"] = _order(db, f"{tag}-DELTA", debtor_name=f"{tag} Acme Holdings")
    s["trading_only"] = _order(db, f"{tag}-ECHO", debtor_name="Trading Bee")
    s["by_customer"] = _order(db, f"{tag}-FOXTROT", customer_id=fakeco.id)
    s["by_debtor_code"] = _order(db, f"{tag}-GOLF", debtor_code=f"{tag}DCZZ")
    return s


def _search(client, quick_search, **extra):
    return client.post(SEARCH, json={"resource": "orders", "page": 1, "limit": 200,
                                     "quick_search": quick_search, **extra})


def _list(client, quick_search):
    resp = _search(client, quick_search)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _numbers(body):
    return {r["order_number"] for r in body["data"]}


def _n(s, *keys):
    return {s[k].order_number for k in keys}


def _export(client, quick_search):
    resp = client.post(EXPORT, json={"resource": "orders", "fields": [{"field_key": "order_number"}],
                                     "quick_search": quick_search})
    assert resp.status_code == 200, resp.text
    return {r["order_number"] for r in resp.json()["data"]}


# ---- search: a list of values ---------------------------------------------------------------------------

def test_list_quick_search_returns_the_union(client, seeded):
    s = seeded
    body = _list(client, [s["alpha"].order_number, s["bravo"].order_number])
    assert _numbers(body) == _n(s, "alpha", "bravo")
    assert body["pagination"]["total"] == 2


def test_each_value_matched_over_number_debtor_customer_and_debtor_code(client, seeded):
    s, tag = seeded, seeded["tag"]
    body = _list(client, [s["alpha"].order_number, "Acme, Trading", f"{tag} Fakeco Holdings", f"{tag}DCZZ"])
    assert _numbers(body) == _n(s, "alpha", "comma", "by_customer", "by_debtor_code")


def test_plain_string_quick_search_still_accepted_and_unchanged(client, seeded):
    s = seeded
    body = _list(client, s["alpha"].order_number)
    assert _numbers(body) == _n(s, "alpha")
    assert body["pagination"]["total"] == 1


def test_one_item_list_behaves_like_the_plain_string(client, seeded):
    s = seeded
    assert _numbers(_list(client, [s["alpha"].order_number])) == _n(s, "alpha")


def test_a_value_matching_nothing_adds_no_rows(client, seeded):
    s = seeded
    assert _numbers(_list(client, [s["alpha"].order_number, "ZZNOTHINGMATCHESTHIS"])) == _n(s, "alpha")


def test_comma_inside_a_value_is_one_value(client, seeded):
    s = seeded
    # Split on the comma, "Acme" would also find DELTA and "Trading" ECHO.
    body = _list(client, ["Acme, Trading", s["alpha"].order_number])
    assert _numbers(body) == _n(s, "comma", "alpha")


def test_blank_and_case_duplicate_values_are_ignored(client, seeded):
    s = seeded
    a = s["alpha"].order_number
    body = _list(client, [a, "", "  ", a.lower(), s["bravo"].order_number])
    assert _numbers(body) == _n(s, "alpha", "bravo")
    assert body["pagination"]["total"] == 2


def test_more_than_200_values_is_422(client, seeded):
    resp = _search(client, [f"ZZV{i:03d}" for i in range(201)])
    assert resp.status_code == 422, resp.text
    assert "at most 200 values" in resp.text


def test_exactly_200_values_is_accepted(client, seeded):
    s = seeded
    values = [s["bravo"].order_number] + [f"ZZV{i:03d}" for i in range(199)]
    assert _numbers(_list(client, values)) == _n(s, "bravo")


def test_a_value_over_100_characters_is_422(client, seeded):
    resp = _search(client, ["DO1", "X" * 101])
    assert resp.status_code == 422, resp.text
    assert "100" in resp.text, resp.text
    # Refused for its length, not because a list is still the wrong type.
    assert "string_type" not in resp.text, resp.text


def test_a_value_of_exactly_100_characters_is_accepted(client, seeded):
    s = seeded
    assert _numbers(_list(client, [s["alpha"].order_number, "Z" * 100])) == _n(s, "alpha")


# ---- export twin: the same rows as the search ---------------------------------------------------------

def test_export_with_a_list_quick_search_returns_the_union(client, seeded):
    s = seeded
    got = _export(client, [s["alpha"].order_number, s["bravo"].order_number])
    assert got == _n(s, "alpha", "bravo")


def test_export_returns_the_same_rows_as_the_search_for_a_list(client, seeded):
    s, tag = seeded, seeded["tag"]
    values = [s["alpha"].order_number, "Acme, Trading", f"{tag} Fakeco Holdings"]
    searched = _numbers(_list(client, values))
    assert searched == _n(s, "alpha", "comma", "by_customer")
    assert _export(client, values) == searched


def test_export_plain_string_quick_search_still_accepted(client, seeded):
    s = seeded
    assert _export(client, s["alpha"].order_number) == _n(s, "alpha")


def test_export_more_than_200_values_is_422(client, seeded):
    resp = client.post(EXPORT, json={"resource": "orders", "fields": [{"field_key": "order_number"}],
                                     "quick_search": [f"ZZV{i:03d}" for i in range(201)]})
    assert resp.status_code == 422, resp.text
    assert "at most 200 values" in resp.text


# ---- the plain list: GET /api/v1/order-management/orders with repeated `query` -------------------------
# The Delivery orders list without an advanced filter reads this route (`orderService.ts:25`);
# route `app/api/v1/order_management/orders.py:296-300` (`get_orders`, `query: Optional[str]`)
# hands `query` to `OrderService.list_orders` (`orders.py:570-573`), whose search clause is
# `app/services/order_service.py:1089-1136`.

ORDERS = "/api/v1/order-management/orders"


def _get(client, values, **extra):
    return get(client, ORDERS, [("limit", 200), *[("query", v) for v in values], *extra.items()])


def _get_list(client, values):
    resp = _get(client, values)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_get_repeated_query_returns_the_union(client, seeded):
    s = seeded
    body = _get_list(client, [s["alpha"].order_number, s["bravo"].order_number])
    assert _numbers(body) == _n(s, "alpha", "bravo")
    assert body["pagination"]["total"] == 2


def test_get_each_value_matched_over_number_debtor_customer_and_debtor_code(client, seeded):
    s, tag = seeded, seeded["tag"]
    body = _get_list(client, [s["alpha"].order_number, "Acme, Trading", f"{tag} Fakeco Holdings", f"{tag}DCZZ"])
    assert _numbers(body) == _n(s, "alpha", "comma", "by_customer", "by_debtor_code")


def test_get_single_query_behaves_as_today(client, seeded):
    s = seeded
    body = _get_list(client, [s["alpha"].order_number])
    assert _numbers(body) == _n(s, "alpha")
    assert body["pagination"]["total"] == 1


def test_get_comma_inside_a_value_is_one_value(client, seeded):
    s = seeded
    # Split on the comma, "Acme" would also find DELTA and "Trading" ECHO.
    body = _get_list(client, ["Acme, Trading", s["alpha"].order_number])
    assert _numbers(body) == _n(s, "comma", "alpha")


def test_get_blank_and_case_duplicate_values_are_ignored(client, seeded):
    s = seeded
    a = s["alpha"].order_number
    body = _get_list(client, [a, "", "  ", a.lower(), s["bravo"].order_number])
    assert _numbers(body) == _n(s, "alpha", "bravo")
    assert body["pagination"]["total"] == 2


def test_get_more_than_200_values_is_422(client, seeded):
    resp = _get(client, [f"ZZV{i:03d}" for i in range(201)])
    assert resp.status_code == 422, resp.text
    assert "at most 200 values" in resp.text


def test_get_exactly_200_values_is_accepted(client, seeded):
    s = seeded
    values = [s["bravo"].order_number] + [f"ZZV{i:03d}" for i in range(199)]
    assert _numbers(_get_list(client, values)) == _n(s, "bravo")


def test_get_a_value_over_100_characters_is_422(client, seeded):
    resp = _get(client, ["DO1", "X" * 101])
    assert resp.status_code == 422, resp.text
    assert "100" in resp.text, resp.text


def test_get_a_value_of_exactly_100_characters_is_accepted(client, seeded):
    s = seeded
    assert _numbers(_get_list(client, [s["alpha"].order_number, "Z" * 100])) == _n(s, "alpha")


# ---- export equals screen over EVERY search field (review S2) ------------------------------------------
# Each order below matches ONLY through a field the old export never searched (debtor code,
# customer code, the legacy transporter text, the transporter FK's code, a line's product code),
# so an export that matches fewer fields than the list drops rows the screen shows.

@pytest.fixture
def wide(db, seeded):
    from app.models.order import OrderLine, Transporter
    from tests._mc_lookup_seed import product, warehouse
    from app.services.company_scope import DEFAULT_COMPANY_ID

    s, tag = seeded, seeded["tag"]
    plain = Customer(id=_u(), customer_code=f"{tag}CCZZ", customer_name="ZZT Plain Customer")
    carrier = Transporter(id=_u(), code=f"{tag}TCZZ", name="ZZT Plain Carrier",
                          normalized_name="zzt plain carrier")
    db.add_all([plain, carrier])
    db.flush()
    s["by_customer_code"] = _order(db, f"{tag}-HOTEL", customer_id=plain.id)
    s["by_legacy_transporter"] = _order(db, f"{tag}-INDIA", transporter=f"{tag}LTZZ")
    s["by_transporter_fk"] = _order(db, f"{tag}-JULIET", transporter_id=carrier.id)
    s["by_line_product"] = _order(db, f"{tag}-KILO")
    item = product(db, company_id=DEFAULT_COMPANY_ID, code=f"{tag}PCZZ")
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    db.add(OrderLine(id=_u(), order_id=s["by_line_product"].id, product_id=item.id,
                     warehouse_id=wh.id, line_sequence=1, quantity=1))
    db.flush()
    return s


def test_export_equals_search_over_every_search_field(client, wide):
    s, tag = wide, wide["tag"]
    values = [f"{tag}DCZZ", f"{tag}CCZZ", f"{tag}LTZZ", f"{tag}TCZZ", f"{tag}PCZZ"]
    searched = _numbers(_list(client, values))
    # Guard: the screen finds each order through its one field.
    assert searched == _n(s, "by_debtor_code", "by_customer_code", "by_legacy_transporter",
                          "by_transporter_fk", "by_line_product")
    assert _export(client, values) == searched


@pytest.mark.parametrize("suffix,key", [
    ("DCZZ", "by_debtor_code"), ("CCZZ", "by_customer_code"), ("LTZZ", "by_legacy_transporter"),
    ("TCZZ", "by_transporter_fk"), ("PCZZ", "by_line_product"),
])
def test_export_finds_the_order_through_each_field(client, wide, suffix, key):
    s = wide
    values = [f"{s['tag']}{suffix}", s["alpha"].order_number]
    assert _export(client, values) == _n(s, key, "alpha")
