"""PRODUCT-COSTING fix round 2: boundary, bounds, park-time gates, formula injection, ids.

Reviewer / security / browser findings, each pinned red-first. Uses the lane harness
(`tests/support/costing_env.py`).
"""
from __future__ import annotations

import uuid
from io import BytesIO

import pytest
from openpyxl import load_workbook

from tests.support.costing_env import BASE, COST_VIEW, MANAGE, costing_env, f  # noqa: F401

A = pytest.approx
PENDING = "/api/v1/pending-actions"


def _setup(costing_env, who="viewer"):
    e = costing_env
    w = e.workbook()
    e.as_user(e.viewer() if who == "viewer" else e.manager())
    return e, w


def _sheet_rows(response):
    ws = load_workbook(BytesIO(response.content)).active
    out = {}
    for cells in ws.iter_rows(min_row=3):
        if cells[1].value is not None:
            out[cells[1].value] = cells
    return out


# ------------------------------------------------------------------ B1 the rate boundary, page path


def test_b1_rate_effective_on_its_own_day_in_rows(costing_env):
    e, w = _setup(costing_env)
    row = e.row_of(e.rows(as_of="2026-11-01"), "CGB9032B")
    assert row["rate_to_base"] == A(0.625, abs=1e-9)
    assert row["units_per_base"] == A(1.6, abs=1e-4)
    assert row["rate_effective_from"] == "2026-11-01"
    assert row["landing"] == A(31.71875, abs=1e-6)


def test_b1_rate_effective_on_its_own_day_in_the_supplier_expand(costing_env):
    e, w = _setup(costing_env)
    data = e.get(f"/rows/{w.wb.id}/suppliers", as_of="2026-11-01").json()["data"]
    a = next(s for s in data if s["supplier_code"] == "SUP-A01")
    assert a["landing"] == A(31.71875, abs=1e-6)


def test_b1_rate_effective_on_its_own_day_in_the_export(costing_env):
    e, w = _setup(costing_env)
    cells = _sheet_rows(e.get("/export", as_of="2026-11-01"))["CGB9032B"]
    assert cells[7].value == A(1.6, abs=1e-4)  # Rate (per MYR)
    assert cells[11].value == A(31.71875, abs=1e-6)  # Landing


def test_b1_rate_on_and_the_rate_book_are_one_lookup(costing_env):
    from datetime import date

    from app.services.costing.rates import load_rate_book, rate_on

    e, w = _setup(costing_env)
    for day in (date(2026, 8, 31), date(2026, 9, 1), date(2026, 10, 31), date(2026, 11, 1), date(2026, 12, 1)):
        a, b = rate_on(e.db, "CNY", day), load_rate_book(e.db).on("CNY", day)
        assert (a.id if a else None) == (b.id if b else None), day


# ------------------------------------------------------------------ H1 / L1 park-time gates


def _park(e, key, etype, eid):
    return e.client.post(
        PENDING, json={"action_key": key, "entity_type": etype, "entity_id": eid, "payload": {}}
    )


def test_h1_parking_unlink_on_another_companys_link_is_404(costing_env):
    e, w = _setup(costing_env, "manager")
    e.as_user(e.manager(), scope=frozenset({e.company_b}))
    r = _park(e, "costing_party_product.unlink", "costing_party_product", w.pp_wb.id)
    assert r.status_code == 404, r.text


def test_h1_parking_unlink_on_own_companys_link_works(costing_env):
    e, w = _setup(costing_env, "manager")
    r = _park(e, "costing_party_product.unlink", "costing_party_product", w.pp_wb.id)
    assert r.status_code == 202, r.text


def test_l1_unlink_needs_cost_view_as_well_as_manage(costing_env):
    e, w = _setup(costing_env)
    e.as_user(e.user(MANAGE))
    r = _park(e, "costing_party_product.unlink", "costing_party_product", w.pp_wb.id)
    assert r.status_code == 403, r.text
    assert COST_VIEW in r.text


def test_l1_rate_delete_needs_cost_view_as_well_as_scm_config_manage(costing_env):
    e, w = _setup(costing_env)
    e.as_user(e.user("scm.config.manage"))
    r = _park(e, "exchange_rate.delete", "exchange_rate", w.rmb_new.id)
    assert r.status_code == 403, r.text
    e.as_user(e.user("scm.config.manage", COST_VIEW))
    assert _park(e, "exchange_rate.delete", "exchange_rate", w.rmb_new.id).status_code == 202


# ------------------------------------------------------------------ M1 formula injection


def test_m1_a_name_that_looks_like_a_formula_exports_as_text(costing_env):
    e, w = _setup(costing_env)
    e.item("EVIL-1", category=w.cat_taps, list_price="10", name='=HYPERLINK("http://x","y")')
    e.db.commit()
    ws = load_workbook(BytesIO(e.get("/export", as_of="2026-11-11").content)).active
    for row in ws.iter_rows(min_row=3):
        for cell in row:
            assert cell.data_type != "f", cell.coordinate
    named = [c for r in ws.iter_rows(min_row=3) for c in r if c.value == '=HYPERLINK("http://x","y")']
    assert named and named[0].data_type == "s"


# ------------------------------------------------------------------ L3 bounds


def _raw(e, method, path, body: str):
    return e.client.request(method, f"{BASE}{path}", content=body, headers={"Content-Type": "application/json"})


def test_l3_patch_rows_is_capped_at_500_changes(costing_env):
    e, w = _setup(costing_env, "manager")
    changes = [{"product_id": str(uuid.uuid4()), "cost_method": "average"} for _ in range(501)]
    assert e.patch_rows({"party_id": None, "changes": changes}).status_code == 422


@pytest.mark.parametrize("change", [
    {"markup_pct": 10000},
    {"transport_mode": "add", "transport_value": 1e8},
])
def test_l3_out_of_range_cells_are_422_not_500(costing_env, change):
    e, w = _setup(costing_env, "manager")
    r = e.patch_rows({"party_id": w.customer.id, "changes": [{"product_id": w.wb.id, **change}]})
    assert r.status_code == 422, r.text


def test_l3_nan_and_infinity_are_422(costing_env):
    e, w = _setup(costing_env, "manager")
    body = '{"party_id": "%s", "changes": [{"product_id": "%s", "markup_pct": NaN}]}' % (w.customer.id, w.wb.id)
    assert _raw(e, "PATCH", "/rows", body).status_code == 422
    assert _raw(e, "PUT", "/settings", '{"sst_factor": Infinity, "default_method": "primary"}').status_code == 422


def test_l3_settings_rule_party_and_rate_bounds(costing_env):
    e, w = _setup(costing_env, "manager")
    assert e.put("/settings", {"sst_factor": 100, "default_method": "primary"}).status_code == 422
    assert e.put(f"/category-rules/{w.cat_taps.id}", {"mode": "add", "value": 1e8}).status_code == 422
    assert e.put(f"/parties/{w.customer.id}", {"markup_pct": 10000, "cost_method": None, "is_active": True}).status_code == 422
    e.as_user(e.user("scm.config.manage", COST_VIEW))
    base = {"currency": "USD", "effective_from": "2026-12-01"}
    assert e.post("/exchange-rates", {**base, "rate_to_base": 1e12}).status_code == 422
    assert e.post("/exchange-rates", {**base, "units_per_base": 1e12}).status_code == 422
    # inside the bound but so large that its inverse rounds to zero: refused, not a CHECK 500
    assert e.post("/exchange-rates", {**base, "units_per_base": 1e11}).status_code == 422


# ------------------------------------------------------------------ L4 filter ids


@pytest.mark.parametrize("param", ["category_id", "brand_id", "party_id"])
def test_l4_a_malformed_filter_id_is_422(costing_env, param):
    e, w = _setup(costing_env)
    assert e.rows(as_of="2026-11-11", **{param: "not-a-uuid"}).status_code == 422
    assert e.get("/export", as_of="2026-11-11", **{param: f"{uuid.uuid4()},nope"}).status_code == 422


# ------------------------------------------------------------------ N1 actor under impersonation


def test_n1_created_by_is_the_real_user_under_impersonation(costing_env):
    from datetime import date

    from app.models.costing import ExchangeRate

    e, w = _setup(costing_env)
    real = e.user("scm.config.manage", COST_VIEW, name="Real")
    effective = e.user("scm.config.manage", COST_VIEW, name="Effective")
    e.as_impersonated(real, effective)
    r = e.post("/exchange-rates", {"currency": "USD", "effective_from": "2026-12-01", "rate_to_base": 5.5})
    assert r.status_code in (200, 201), r.text
    row = e.db.query(ExchangeRate).filter(ExchangeRate.currency == "USD", ExchangeRate.effective_from == date(2026, 12, 1)).one()
    assert row.created_by == real["id"]


# ------------------------------------------------------------------ S4 query alias, S6 product ids


def test_s4_query_is_accepted_and_q_stays_an_alias(costing_env):
    e, w = _setup(costing_env)
    for name in ("query", "q"):
        codes = [r["product_code"] for r in e.rows(as_of="2026-11-11", **{name: "jac"}).json()["data"]]
        assert codes == ["JAC-5001"], name
    assert [r["product_code"] for r in
            e.rows(as_of="2026-11-11", sort="product_code", dir="desc", limit=1).json()["data"]] == ["Z-0001"]


def test_s6_party_product_ids_lists_every_id_without_costing(costing_env):
    e, w = _setup(costing_env)
    r = e.get(f"/parties/{w.customer.id}/product-ids")
    assert r.status_code == 200, r.text
    assert set(r.json()["data"]) == {w.wb.id, w.jac.id}
    assert e.get(f"/parties/{uuid.uuid4()}/product-ids").status_code == 404
    e.as_user(e.user())
    assert e.get(f"/parties/{w.customer.id}/product-ids").status_code == 403


# ------------------------------------------------------------------ round 3: history timestamps


def test_r3_history_changed_at_is_timezone_aware(costing_env):
    from datetime import datetime

    e, w = _setup(costing_env, "manager")
    e.patch_rows({"party_id": w.customer.id, "changes": [{"product_id": w.jac.id, "markup_pct": 15}]})
    e.as_user(e.viewer())
    data = e.get(f"/rows/{w.jac.id}/history", party_id=w.customer.id).json()["data"]
    assert data
    for entry in data:
        stamp = entry["changed_at"]
        assert stamp.endswith("Z") or stamp.endswith("+00:00"), stamp
        assert datetime.fromisoformat(stamp.replace("Z", "+00:00")).tzinfo is not None


# ------------------------------------------------------------------ round 3: currency pick-list


def test_r3_currencies_are_the_known_set_sorted_without_myr(costing_env):
    e, w = _setup(costing_env)
    e.cost_link(w.tap, w.sup_b, cost="5", currency="gbp", primary=False)
    e.cost_link(w.sink, w.sup_b, cost="5", currency="MYR", primary=False)
    e.db.commit()
    got = e.get("/currencies").json()["data"]
    assert got == sorted(got)
    assert {"CNY", "USD", "EUR", "GBP"} <= set(got)  # the upload's three, and one a cost row uses
    assert "MYR" not in got and "gbp" not in got


def test_r3_a_currency_on_no_cost_row_is_refused_and_a_known_one_accepted(costing_env):
    e, w = _setup(costing_env)
    e.as_user(e.user("scm.config.manage", COST_VIEW))
    body = {"effective_from": "2026-12-01", "rate_to_base": 0.6}
    r = e.post("/exchange-rates", {"currency": "RMB", **body})
    assert r.status_code == 422 and "Unknown currency RMB" in r.text
    assert e.post("/exchange-rates", {"currency": "cny", **body}).status_code == 201
    e.cost_link(w.tap, w.sup_b, cost="5", currency="GBP")
    e.db.commit()
    assert e.post("/exchange-rates", {"currency": "GBP", **body}).status_code == 201


def test_r3_the_scm_route_refuses_an_unknown_currency_too(costing_env):
    e, w = _setup(costing_env)
    e.as_user(e.user("scm.config.manage"))
    url = "/api/v1/scm/config/currency-rates"
    r = e.client.put(f"{url}/RMB", json={"rate_to_base": 0.6, "as_of": "2026-12-01"})
    assert r.status_code == 422 and "Unknown currency RMB" in r.text
    assert e.client.put(f"{url}/USD", json={"rate_to_base": 4.4, "as_of": "2026-12-01"}).status_code == 200


def test_r3_currencies_need_cost_view(costing_env):
    e, w = _setup(costing_env)
    e.as_user(e.user())
    assert e.get("/currencies").status_code == 403


# ------------------------------------------------------------------ round 4: the known-currency set


def _scm_put(e, code, rate=0.5, as_of="2026-12-01"):
    return e.client.put(f"/api/v1/scm/config/currency-rates/{code}", json={"rate_to_base": rate, "as_of": as_of})


def test_r4_a_currency_only_on_a_po_line_is_offered_and_gets_a_rate_on_both_routes(costing_env):
    from datetime import date

    e, w = _setup(costing_env)
    e.po_line(w.tap, w.sup_a, po_number="PO-SGD", issue_date=date(2026, 10, 1), unit_cost="9", currency="SGD")
    e.db.commit()
    e.as_user(e.user("scm.config.manage", COST_VIEW))
    assert "SGD" in e.get("/currencies").json()["data"]
    body = {"effective_from": "2026-12-01", "rate_to_base": 3.2}
    assert e.post("/exchange-rates", {"currency": "SGD", **body}).status_code == 201
    assert _scm_put(e, "SGD", 3.3, "2026-12-02").status_code == 200


def test_r4_a_currency_only_on_a_po_header_works_too(costing_env):
    from datetime import date

    e, w = _setup(costing_env)
    e.po_line(w.tap, w.sup_a, po_number="PO-THB", issue_date=date(2026, 10, 1), unit_cost="9",
              currency=None, po_currency="THB")
    e.db.commit()
    e.as_user(e.user("scm.config.manage", COST_VIEW))
    assert "THB" in e.get("/currencies").json()["data"]
    assert e.post("/exchange-rates", {"currency": "THB", "effective_from": "2026-12-01", "rate_to_base": 0.1}).status_code == 201


def test_r4_a_removed_po_line_does_not_offer_its_currency(costing_env):
    from datetime import date

    e, w = _setup(costing_env)
    e.po_line(w.tap, w.sup_a, po_number="PO-GONE", issue_date=date(2026, 10, 1), unit_cost="9",
              currency="NOK", removed=True)
    e.db.commit()
    assert "NOK" not in e.get("/currencies").json()["data"]


def test_r4_an_existing_rate_stays_editable_but_is_not_offered(costing_env):
    e, w = _setup(costing_env)
    row = e.rate("RMB", "0.625", __import__("datetime").date(2026, 11, 1), note="typed by hand")
    e.db.commit()
    e.as_user(e.user("scm.config.manage", COST_VIEW))
    assert "RMB" not in e.get("/currencies").json()["data"]  # a rate alone offers nothing
    assert _scm_put(e, "RMB", 0.63, "2026-11-01").status_code == 200
    assert e.put(f"/exchange-rates/{row.id}", {"rate_to_base": 0.64}).status_code == 200
    # a new dated row for the same currency can be added: it already has a rate
    assert e.post("/exchange-rates", {"currency": "RMB", "effective_from": "2026-12-01", "rate_to_base": 0.65}).status_code == 201


def test_r4_a_currency_with_no_row_anywhere_is_still_refused(costing_env):
    e, w = _setup(costing_env)
    e.as_user(e.user("scm.config.manage", COST_VIEW))
    r = e.post("/exchange-rates", {"currency": "RMB", "effective_from": "2026-12-01", "rate_to_base": 0.6})
    assert r.status_code == 422 and "Unknown currency RMB" in r.text
    assert _scm_put(e, "RMB").status_code == 422


def test_r4_another_companys_supplier_cost_currency_is_offered(costing_env):
    from app.models.base import set_company_scope

    e, w = _setup(costing_env)
    set_company_scope(e.db, frozenset({e.company_b}))
    try:
        sup = e.source("SUP-B-CO")
        item = e.item("OTHER-CO-1", category=e.category("OtherCoCat"), list_price="5")
        e.cost_link(item, sup, cost="3", currency="CHF", primary=True)
        e.db.commit()
    finally:
        set_company_scope(e.db, e.scope)
    e.as_user(e.viewer())  # a company A user
    assert "CHF" in e.get("/currencies").json()["data"]


# ------------------------------------------------------------------ round 5: every column sorts


def _sort_key_of(key: str):
    """What a row sorts on, as the page shows it (None = unknown, sorts last)."""
    labels = {"primary": "Primary supplier", "selected": "Selected supplier",
              "average": "Average of supplier prices", "last_po": "Last PO price"}
    pick = {
        "product_code": lambda r: r["product_code"].lower(),
        "product_name": lambda r: r["product_name"].lower(),
        "category_name": lambda r: (r["category_name"] or "").lower() or None,
        "supplier_name": lambda r: (r["supplier_name"] or "").lower() or None,
        "unit_cost": lambda r: r["unit_cost"],
        "units_per_base": lambda r: r["units_per_base"],
        "sst_factor": lambda r: r["sst_factor"],
        "transport": lambda r: None if r["transport_mode"] is None else (r["transport_mode"], r["transport_value"]),
        "landing": lambda r: r["landing"],
        "cost_method": lambda r: labels[r["cost_method"]].lower(),
        "markup_pct": lambda r: r["markup_pct"],
        "final": lambda r: r["final"],
        "list_price": lambda r: r["list_price"],
        "margin_pct": lambda r: r["margin_pct"],
    }
    return pick[key]


SORT_KEYS = ["product_code", "product_name", "category_name", "supplier_name", "unit_cost", "units_per_base",
             "sst_factor", "transport", "landing", "cost_method", "markup_pct", "final", "list_price", "margin_pct"]


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("key", SORT_KEYS)
def test_r5_every_column_sorts_on_the_server_with_unknowns_last(costing_env, key, direction):
    e, w = _setup(costing_env)
    e.override(w.tap, cost_method="average")
    e.override(w.sink, transport_mode="add", transport_value="3")
    e.party_product(w.customer, w.acc)  # a costless row in the party view
    zero = e.item("ZERO-PRICE", category=w.cat_taps, list_price="0")  # priced 0: no selling price
    e.cost_link(zero, w.sup_a, cost="10", currency="CNY", primary=True)
    e.party_product(w.customer, zero)
    e.db.commit()
    party = key == "margin_pct"
    r = e.rows(as_of="2026-11-11", sort=key, dir=direction, limit=100, **({"party_id": w.customer.id} if party else {}))
    assert r.status_code == 200, r.text
    values = [_sort_key_of(key)(row) for row in r.json()["data"]]
    known = [v for v in values if v is not None]
    assert values == known + [None] * (len(values) - len(known)), (key, direction, values)  # unknowns last
    assert known == sorted(known, reverse=direction == "desc"), (key, direction, known)


def test_r5_the_export_takes_the_same_sort_keys(costing_env):
    e, w = _setup(costing_env)
    for key in SORT_KEYS:
        assert e.get("/export", as_of="2026-11-11", sort=key, dir="desc").status_code == 200, key
    assert e.rows(as_of="2026-11-11", sort="bogus").status_code == 422


# ------------------------------------------------------------------ round 5: the Cost filter


def test_r5_cost_filter_is_a_multi_value(costing_env):
    e, w = _setup(costing_env)
    codes = lambda **p: {r["product_code"] for r in e.rows(as_of="2026-11-11", limit=100, **p).json()["data"]}
    costless = {"A-4001", "N-9001"}
    everything = codes()
    assert costless < everything
    assert codes(cost="none") == costless
    assert codes(cost="has") == everything - costless
    assert codes(cost="has,none") == everything
    assert codes(has_cost="true") == everything - costless  # still works
    assert codes(cost="none", has_cost="false") == costless
    assert e.rows(as_of="2026-11-11", cost="bogus").status_code == 422


# ------------------------------------------------------------------ round 5: supplier name


def test_r5_a_row_carries_the_supplier_name_and_the_export_a_column_for_it(costing_env):
    e, w = _setup(costing_env)
    row = e.row_of(e.rows(as_of="2026-11-11"), "CGB9032B")
    assert row["supplier_code"] == "SUP-A01" and row["supplier_name"] == "SUP-A01 Ltd"
    assert e.row_of(e.rows(as_of="2026-11-11"), "N-9001")["supplier_name"] is None
    ws = load_workbook(BytesIO(e.get("/export", as_of="2026-11-11").content)).active
    headers = [c.value for c in ws[2]]
    assert headers[headers.index("Supplier") + 1] == "Supplier name"
    cells = _sheet_rows(e.get("/export", as_of="2026-11-11"))["CGB9032B"]
    assert cells[headers.index("Supplier name")].value == "SUP-A01 Ltd"


# ------------------------------------------------------------------ round 5: no selling price, no -100%


@pytest.mark.parametrize("price", ["0"])  # products.list_price is NOT NULL: 0 is "not set"
def test_r5_a_row_with_no_list_price_has_no_markup_final_or_margin(costing_env, price):
    e, w = _setup(costing_env)
    p = e.item("NOPRICE-1", category=w.cat_taps, list_price=price)
    e.cost_link(p, w.sup_a, cost="120.00", currency="CNY", primary=True)
    e.party_product(w.customer, p)
    e.db.commit()
    std = e.row_of(e.rows(as_of="2026-11-11"), "NOPRICE-1")
    assert std["landing"] == A(88.275, abs=1e-6)
    assert std["markup_pct"] is None and std["final"] is None and std["margin_pct"] is None
    assert "no_list_price" in [x["code"] for x in std["reasons"]]
    party = e.row_of(e.rows(as_of="2026-11-11", party_id=w.customer.id), "NOPRICE-1")
    assert party["margin_pct"] is None and party["final"] == A(88.275 * 1.08, abs=1e-6)
    assert "no_list_price" in [x["code"] for x in party["reasons"]]
    ws = _sheet_rows(e.get("/export", as_of="2026-11-11"))["NOPRICE-1"]
    assert ws[-1].value is not None and "No list price" in ws[-1].value


def test_r5_a_priced_row_keeps_its_markup_and_has_no_such_reason(costing_env):
    e, w = _setup(costing_env)
    row = e.row_of(e.rows(as_of="2026-11-11"), "CGB9032B")
    assert row["markup_pct"] == A(149.0640394, abs=1e-6)
    assert "no_list_price" not in [x["code"] for x in row["reasons"]]


# ------------------------------------------------------------------ round 5: the party picker's search


@pytest.mark.parametrize("query", ["bath", "BATHPLUS", "304-R017"])
def test_r5_the_customer_select_finds_a_party_by_name_or_code(costing_env, query):
    e, w = _setup(costing_env)
    r = e.client.get("/api/v1/order-management/customers/select", params={"query": query, "limit": 50})
    assert r.status_code == 200, r.text
    assert "304-R017" in [c["customer_code"] for c in r.json()["data"]]


# ------------------------------------------------------------------ round 5 review


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("cost", ["has", "none"])
@pytest.mark.parametrize("key", ["product_code", "product_name", "category_name", "list_price"])
def test_r5_a_cost_filter_keeps_the_plain_sorts(costing_env, key, cost, direction):
    e, w = _setup(costing_env)
    zero = e.item("ZERO-PRICE2", category=w.cat_taps, list_price="0")  # unknown price sorts last
    e.cost_link(zero, w.sup_a, cost="10", currency="CNY", primary=True)
    e.db.commit()
    r = e.rows(as_of="2026-11-11", sort=key, dir=direction, cost=cost, limit=100)
    assert r.status_code == 200, r.text
    values = [_sort_key_of(key)(row) for row in r.json()["data"]]
    assert len(values) >= 2
    known = [v for v in values if v is not None]
    assert values == known + [None] * (len(values) - len(known)), (key, cost, direction, values)
    assert known == sorted(known, reverse=direction == "desc"), (key, cost, direction, known)


def test_r5_the_supplier_expand_of_a_product_priced_zero_has_no_markup_final_or_margin(costing_env):
    e, w = _setup(costing_env)
    zero = e.item("ZERO-PRICE3", category=w.cat_taps, list_price="0")
    e.cost_link(zero, w.sup_a, cost="120", currency="CNY", primary=True)
    e.party_product(w.customer, zero)
    e.db.commit()
    for params in ({}, {"party_id": w.customer.id}):
        row = e.get(f"/rows/{zero.id}/suppliers", as_of="2026-11-11", **params).json()["data"][0]
        assert row["landing"] == A(88.275, abs=1e-6)
        assert row["margin_pct"] is None
        if not params:
            assert row["markup_pct"] is None and row["final"] is None
        assert "no_list_price" in [x["code"] for x in row["reasons"]]


# ------------------------------------------------------------------ round 6


def test_r6_a_duplicate_rate_says_what_to_do_in_the_screens_own_words(costing_env):
    e, w = _setup(costing_env)
    e.as_user(e.user("scm.config.manage", COST_VIEW))
    body = {"currency": "CNY", "effective_from": "2026-12-01", "rate_to_base": 0.6}
    assert e.post("/exchange-rates", body).status_code == 201
    r = e.post("/exchange-rates", body)
    assert r.status_code == 409
    text = r.json()["message"]
    assert "01/12/2026" in text and "Delete that row first" in text
    assert "2026-12-01" not in text and "Edit" not in text
