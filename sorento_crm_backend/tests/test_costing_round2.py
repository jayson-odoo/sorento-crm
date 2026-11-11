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
    assert cells[6].value == A(1.6, abs=1e-4)  # Rate (per MYR)
    assert cells[10].value == A(31.71875, abs=1e-6)  # Landing


def test_b1_rate_on_and_the_rate_book_are_one_lookup(costing_env):
    from datetime import date

    from app.services.costing.rates import load_rate_book, rate_on

    e, w = _setup(costing_env)
    for day in (date(2026, 8, 31), date(2026, 9, 1), date(2026, 10, 31), date(2026, 11, 1), date(2026, 12, 1)):
        a, b = rate_on(e.db, "RMB", day), load_rate_book(e.db).on("RMB", day)
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
    base = {"currency": "GBP", "effective_from": "2026-12-01"}
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
    from app.models.costing import ExchangeRate

    e, w = _setup(costing_env)
    real = e.user("scm.config.manage", COST_VIEW, name="Real")
    effective = e.user("scm.config.manage", COST_VIEW, name="Effective")
    e.as_impersonated(real, effective)
    r = e.post("/exchange-rates", {"currency": "GBP", "effective_from": "2026-12-01", "rate_to_base": 5.5})
    assert r.status_code in (200, 201), r.text
    row = e.db.query(ExchangeRate).filter(ExchangeRate.currency == "GBP").one()
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
