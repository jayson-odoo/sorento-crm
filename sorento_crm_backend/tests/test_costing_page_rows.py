"""RED tests B7: GET /api/v1/master-data/costing/rows (+ the supplier expand). PRODUCT-COSTING.
AC-CG-03, AC-CG-04, AC-CG-05, AC-CG-06, AC-CG-07, AC-ER-02 (as_of), AC-PC-01 (party object).

Contract 4.1 / 4.2. Every date is passed explicitly (`as_of`), nothing freezes the clock.
Floats come back rounded to 6 dp, so comparisons use abs=1e-6.

Fixture: `CostingEnv.workbook()` (see tests/support/costing_env.py): eight products, of which
Z-0001 is inactive, A-4001 has a primary link with no price and N-9001 has no links.

Choices the contract leaves open (the coder follows these):
  * A costless row in the Company standard view returns `markup_pct: null` and `landing: null`;
    its `final` is not asserted.
  * `sort=landing` is only checked on the rows that have a landing (NULL placement is free).
  * An unknown `party_id` is 404. A customer without a profile is 200 with has_profile false.
"""
from __future__ import annotations

import pytest

from tests.support.costing_env import AS_OF, COST_VIEW, costing_env  # noqa: F401

A = pytest.approx


def _setup(costing_env):
    e = costing_env
    w = e.workbook()
    e.as_user(e.viewer())
    return e, w


def _codes(r):
    assert r.status_code == 200, r.text
    return [x["product_code"] for x in r.json()["data"]]


ALL_CODES = {"CGB9032B", "JAC-5001", "T-1001", "K-2001", "S-3001", "A-4001", "N-9001", "Z-0001"}
COSTED = {"CGB9032B", "JAC-5001", "T-1001", "K-2001", "S-3001", "Z-0001"}


# ------------------------------------------------------------------ AC-CG-03 company standard


def test_ac_cg_03_standard_view_lists_every_product_inactive_and_costless_included(costing_env):
    e, w = _setup(costing_env)
    r = e.rows(as_of="2026-11-11")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(_codes(r)) == ALL_CODES
    assert body["total"] == 8
    assert body["view"] == "standard"
    assert body["party"] is None
    assert body["as_of"] == "2026-11-11"
    assert body["page"] == 1 and body["limit"] == 50
    assert body["settings"] == {"sst_factor": 1.1, "default_method": "primary"}


def test_ac_cg_03_workbook_row_company_standard_every_field(costing_env):
    e, w = _setup(costing_env)
    row = e.row_of(e.rows(as_of="2026-11-11"), "CGB9032B")
    assert row["product_id"] == w.wb.id
    assert row["product_name"] == "WB 245 basin"
    assert row["category_id"] == w.cat_ceramics.id and row["category_name"] == "Ceramics"
    assert row["brand_id"] == w.brand.id and row["brand_name"] == "Sorento"
    assert row["list_price"] == A(79.0)
    assert row["supplier_id"] == w.sup_a.id and row["supplier_code"] == "SUP-A01"
    assert row["currency"] == "CNY"
    assert row["unit_cost"] == A(34.5)
    assert row["rate_to_base"] == A(0.625, abs=1e-9)
    assert row["units_per_base"] == A(1.6, abs=1e-4)
    assert row["rate_effective_from"] == "2026-11-01"
    assert row["sst_factor"] == A(1.1)
    assert row["transport_mode"] == "add" and row["transport_value"] == A(8.0)
    assert row["transport_source"] == "category"
    assert row["landing"] == A(31.71875, abs=1e-6)
    assert row["cost_method"] == "primary" and row["cost_method_source"] == "company"
    # Company standard: Final is the AutoCount list price, mark-up is the achieved one
    assert row["final"] == A(79.0)
    assert row["markup_pct"] == A(149.0640394, abs=1e-6)
    assert row["markup_source"] == "achieved"
    assert row["margin_pct"] is None
    assert row["party_product_id"] is None
    assert row["reasons"] == [] and row["skipped"] == []
    assert row["po_number"] is None and row["po_date"] is None


def test_ac_cg_03_standard_view_has_no_margin_on_any_row(costing_env):
    e, w = _setup(costing_env)
    for row in e.rows(as_of="2026-11-11").json()["data"]:
        assert row.get("margin_pct") is None, row["product_code"]


def test_ac_lc_01_other_workbook_figures_through_the_page(costing_env):
    e, w = _setup(costing_env)
    r = e.rows(as_of="2026-11-11")
    assert e.row_of(r, "T-1001")["landing"] == A(88.275, abs=1e-6)
    assert e.row_of(r, "K-2001")["landing"] == A(196.625, abs=1e-6)
    assert e.row_of(r, "JAC-5001")["landing"] == A(1692.375, abs=1e-6)
    shower = e.row_of(r, "S-3001")
    assert shower["landing"] == A(103.576, abs=1e-6)  # USD 20 x 4.40 x 1.1 x 1.07
    assert shower["currency"] == "USD" and shower["transport_mode"] == "multiply"


def test_floats_are_rounded_to_six_places_in_the_api(costing_env):
    e, w = _setup(costing_env)
    row = e.row_of(e.rows(as_of="2026-10-31"), "CGB9032B")
    for key in ("landing", "markup_pct", "rate_to_base"):
        assert row[key] == round(row[key], 6), key
    assert row["units_per_base"] == round(row["units_per_base"], 4)


# ------------------------------------------------------------------ AC-CG-05 unknown is blank + reason


def test_ac_cg_05_priced_nothing_is_blank_with_a_reason_never_zero(costing_env):
    e, w = _setup(costing_env)
    r = e.rows(as_of="2026-11-11")
    acc = e.row_of(r, "A-4001")
    assert acc["landing"] is None and acc["unit_cost"] is None
    assert acc["markup_pct"] is None
    assert [x["code"] for x in acc["reasons"]] == ["no_cost"]
    assert acc["cost_method"] == "primary"

    bare = e.row_of(r, "N-9001")
    assert bare["landing"] is None and bare["supplier_code"] is None
    assert [x["code"] for x in bare["reasons"]] == ["no_primary"]
    for row in (acc, bare):
        for key in ("landing", "unit_cost", "markup_pct", "rate_to_base"):
            assert row[key] != 0, (row["product_code"], key)


def test_ac_cg_05_no_rate_reason_names_currency_and_date(costing_env):
    e, w = _setup(costing_env)
    eur = e.item("EUR-1", category=w.cat_ceramics, list_price="60")
    e.cost_link(eur, w.sup_d, cost="7.50", currency="EUR", primary=True)
    e.db.commit()
    row = e.row_of(e.rows(as_of="2026-11-11"), "EUR-1")
    assert row["landing"] is None
    assert row["unit_cost"] == A(7.5)  # the supplier's price is still shown
    assert row["rate_to_base"] is None and row["units_per_base"] is None
    assert row["reasons"] == [{"code": "no_rate", "currency": "EUR", "date": "2026-11-11"}]


def test_ac_st_03_no_transport_rule_is_flagged_and_adds_zero(costing_env):
    e, w = _setup(costing_env)
    cat = e.category("Unruled")
    p = e.item("NR-1", category=cat, list_price="100")
    e.cost_link(p, w.sup_a, cost="34.50", currency="CNY", primary=True)
    e.db.commit()
    row = e.row_of(e.rows(as_of="2026-11-11"), "NR-1")
    assert row["transport_source"] is None
    assert row["transport_mode"] is None and row["transport_value"] is None
    assert row["landing"] == A(34.5 * 0.625 * 1.1, abs=1e-6)
    assert [x["code"] for x in row["reasons"]] == ["no_transport_rule"]


def test_ac_cg_05_row_level_values_are_marked_by_their_source(costing_env):
    e, w = _setup(costing_env)
    e.override(w.tap, transport_mode="add", transport_value="20", cost_method="selected",
               cost_method_supplier_id=w.sup_a.id)
    e.db.commit()
    row = e.row_of(e.rows(as_of="2026-11-11"), "T-1001")
    assert row["transport_source"] == "product" and row["transport_mode"] == "add"
    assert row["transport_value"] == A(20.0)
    assert row["landing"] == A(120 * 0.625 * 1.1 + 20, abs=1e-6)
    assert row["cost_method"] == "selected" and row["cost_method_source"] == "product"
    assert row["cost_method_supplier_id"] == w.sup_a.id


def test_a_row_always_reports_its_category_rule_even_under_a_product_override(costing_env):
    """Clearing an override in edit falls back to this rule, so the page needs it on the row."""
    e, w = _setup(costing_env)
    e.override(w.wb, transport_mode="multiply", transport_value="1.5")
    cat = e.category("Unruled2")
    bare = e.item("NR-2", category=cat, list_price="100")
    e.cost_link(bare, w.sup_a, cost="34.50", currency="CNY", primary=True)
    e.db.commit()
    r = e.rows(as_of="2026-11-11")
    overridden = e.row_of(r, "CGB9032B")
    assert overridden["transport_source"] == "product" and overridden["transport_mode"] == "multiply"
    assert overridden["category_transport_mode"] == "add"
    assert overridden["category_transport_value"] == A(8.0)
    inherited = e.row_of(r, "T-1001")
    assert (inherited["category_transport_mode"], inherited["category_transport_value"]) == ("multiply", A(1.07))
    none = e.row_of(r, "NR-2")
    assert none["category_transport_mode"] is None and none["category_transport_value"] is None


# ------------------------------------------------------------------ AC-CG-07 filters


def test_ac_cg_07_no_has_cost_param_means_no_narrowing_and_false_is_the_same(costing_env):
    """KILL TEST: a hard-coded or default-on cost filter drops A-4001 / N-9001 here."""
    e, w = _setup(costing_env)
    assert set(_codes(e.rows(as_of="2026-11-11"))) == ALL_CODES
    assert set(_codes(e.rows(as_of="2026-11-11", has_cost="false"))) == ALL_CODES


def test_ac_cg_07_has_cost_true_keeps_only_rows_with_a_landing(costing_env):
    e, w = _setup(costing_env)
    r = e.rows(as_of="2026-11-11", has_cost="true")
    assert set(_codes(r)) == COSTED
    assert r.json()["total"] == 6


def test_ac_cg_07_has_cost_counts_a_row_with_a_cost_but_no_rate_as_costless(costing_env):
    e, w = _setup(costing_env)
    eur = e.item("EUR-2", category=w.cat_ceramics, list_price="60")
    e.cost_link(eur, w.sup_d, cost="7.50", currency="EUR", primary=True)
    e.db.commit()
    assert "EUR-2" in _codes(e.rows(as_of="2026-11-11"))
    assert "EUR-2" not in _codes(e.rows(as_of="2026-11-11", has_cost="true"))


def test_ac_cg_07_category_and_brand_filters_take_comma_separated_ids(costing_env):
    e, w = _setup(costing_env)
    r = e.rows(as_of="2026-11-11", category_id=f"{w.cat_taps.id},{w.cat_sinks.id}")
    assert set(_codes(r)) == {"T-1001", "K-2001"}
    r = e.rows(as_of="2026-11-11", brand_id=w.brand.id)
    assert set(_codes(r)) == {"CGB9032B", "JAC-5001", "T-1001", "K-2001"}  # the others have no brand


def test_ac_cg_07_cost_method_filter_is_on_the_effective_method(costing_env):
    e, w = _setup(costing_env)
    assert set(_codes(e.rows(as_of="2026-11-11", cost_method="primary"))) == ALL_CODES
    assert _codes(e.rows(as_of="2026-11-11", cost_method="average")) == []
    e.override(w.tap, cost_method="average")
    e.db.commit()
    assert _codes(e.rows(as_of="2026-11-11", cost_method="average")) == ["T-1001"]
    r = e.rows(as_of="2026-11-11", cost_method="average,last_po")
    assert _codes(r) == ["T-1001"]
    assert "T-1001" not in _codes(e.rows(as_of="2026-11-11", cost_method="primary"))


def test_ac_cg_07_search_matches_code_or_name_case_insensitively(costing_env):
    e, w = _setup(costing_env)
    assert _codes(e.rows(as_of="2026-11-11", q="cgb90")) == ["CGB9032B"]
    assert _codes(e.rows(as_of="2026-11-11", q="jacuzzi")) == ["JAC-5001"]  # by name
    assert _codes(e.rows(as_of="2026-11-11", q="no-such-thing")) == []


def test_ac_cg_07_as_of_31_oct_uses_the_old_rate(costing_env):
    e, w = _setup(costing_env)
    r = e.rows(as_of="2026-10-31")
    assert r.json()["as_of"] == "2026-10-31"
    row = e.row_of(r, "CGB9032B")
    assert row["rate_to_base"] == A(0.617284, abs=1e-9)
    assert row["units_per_base"] == A(1.62, abs=1e-4)
    assert row["rate_effective_from"] == "2026-09-01"
    assert row["landing"] == A(34.5 * 0.617284 * 1.1 + 8, abs=1e-6)  # 31.4259278


def test_ac_cg_07_as_of_defaults_to_today(costing_env):
    from datetime import date

    e, w = _setup(costing_env)
    body = e.rows().json()
    assert abs((date.fromisoformat(body["as_of"]) - date.today()).days) <= 1


def test_ac_cg_07_paging_sorting_and_limits(costing_env):
    e, w = _setup(costing_env)
    first = e.rows(as_of="2026-11-11", limit=3, page=1)
    second = e.rows(as_of="2026-11-11", limit=3, page=2)
    assert first.json()["total"] == 8 and len(first.json()["data"]) == 3
    assert _codes(first) == sorted(ALL_CODES)[:3]  # product_code asc is the default
    assert _codes(second) == sorted(ALL_CODES)[3:6]
    assert _codes(e.rows(as_of="2026-11-11", sort="product_code", dir="desc"))[0] == "Z-0001"

    desc = e.rows(as_of="2026-11-11", sort="landing", dir="desc").json()["data"]
    landings = [r["landing"] for r in desc if r["landing"] is not None]
    assert landings == sorted(landings, reverse=True) and len(landings) == 6
    assert e.rows(as_of="2026-11-11", sort="bogus").status_code == 422
    assert e.rows(as_of="2026-11-11", limit=501).status_code == 422


# ------------------------------------------------------------------ AC-CG-04 party view


def test_ac_cg_04_party_view_lists_only_the_partys_products(costing_env):
    e, w = _setup(costing_env)
    r = e.rows(party_id=w.customer.id, as_of="2026-11-11")
    assert set(_codes(r)) == {"CGB9032B", "JAC-5001"}
    body = r.json()
    assert body["view"] == "party" and body["total"] == 2
    assert body["party"] == {
        "customer_id": w.customer.id,
        "customer_code": "304-R017",
        "customer_name": "RELATED - BATHPLUS SDN BHD",
        "has_profile": True,
        "markup_pct": 8.0,
        "cost_method": None,
        "is_active": True,
        "product_count": 2,
    }


def test_ac_cg_04_party_price_and_margin_for_the_workbook_row(costing_env):
    e, w = _setup(costing_env)
    row = e.row_of(e.rows(party_id=w.customer.id, as_of="2026-11-11"), "CGB9032B")
    assert row["landing"] == A(31.71875, abs=1e-6)
    assert row["markup_pct"] == A(8.0) and row["markup_source"] == "party"
    assert row["final"] == A(34.25625, abs=1e-6)
    assert row["margin_pct"] == A(130.6148513, abs=1e-6)
    assert row["list_price"] == A(79.0)
    assert row["party_product_id"] == w.pp_wb.id


def test_ac_cg_04_a_row_markup_beats_the_partys_and_carries_a_marker(costing_env):
    """Jacuzzi at 10%: 1692.375 x 1.10 = 1861.6125. KILL TEST: ignoring the row mark-up
    gives 1692.375 x 1.08 = 1827.765."""
    e, w = _setup(costing_env)
    row = e.row_of(e.rows(party_id=w.customer.id, as_of="2026-11-11"), "JAC-5001")
    assert row["landing"] == A(1692.375, abs=1e-6)
    assert row["markup_pct"] == A(10.0)
    assert row["markup_source"] == "row"
    assert row["final"] == A(1861.6125, abs=1e-6)
    assert row["final"] != A(1827.765, abs=0.01)
    assert row["margin_pct"] == A(114.8100101, abs=1e-6)
    assert row["party_product_id"] == w.pp_jac.id


def test_ac_cg_04_clearing_the_row_markup_returns_to_the_partys(costing_env):
    e, w = _setup(costing_env)
    w.pp_jac.markup_pct = None
    e.db.commit()
    row = e.row_of(e.rows(party_id=w.customer.id, as_of="2026-11-11"), "JAC-5001")
    assert (row["markup_pct"], row["markup_source"]) == (A(8.0), "party")
    assert row["final"] == A(1692.375 * 1.08, abs=1e-6)


def test_ac_lc_04_the_partys_cost_method_applies_in_its_view(costing_env):
    e, w = _setup(costing_env)
    w.profile.cost_method = "average"
    e.db.commit()
    row = e.row_of(e.rows(party_id=w.customer.id, as_of="2026-11-11"), "CGB9032B")
    assert row["cost_method"] == "average" and row["cost_method_source"] == "party"
    assert row["supplier_code"] is None
    assert row["landing"] == A(40.0145833, abs=1e-6)
    assert row["skipped"] == [{"supplier_code": "SUP-D03", "reason": "no_rate"}]
    assert row["final"] == A(40.0145833 * 1.08, abs=1e-5)
    # the standard view is unaffected by a party's method
    assert e.row_of(e.rows(as_of="2026-11-11"), "CGB9032B")["cost_method"] == "primary"


def test_ac_cg_04_a_costless_party_row_has_no_final_or_margin(costing_env):
    e, w = _setup(costing_env)
    e.party_product(w.customer, w.acc)
    e.db.commit()
    row = e.row_of(e.rows(party_id=w.customer.id, as_of="2026-11-11"), "A-4001")
    assert row["landing"] is None and row["final"] is None and row["margin_pct"] is None
    assert [x["code"] for x in row["reasons"]] == ["no_cost"]


def test_ac_cg_04_party_view_still_filters_and_searches(costing_env):
    e, w = _setup(costing_env)
    assert _codes(e.rows(party_id=w.customer.id, as_of="2026-11-11", q="jac")) == ["JAC-5001"]
    assert _codes(e.rows(party_id=w.customer.id, as_of="2026-11-11", category_id=w.cat_ceramics.id)) == ["CGB9032B"]


def test_ac_pc_01_a_customer_without_a_profile_is_an_empty_party_view(costing_env):
    e, w = _setup(costing_env)
    stranger = e.customer(code="304-R999", name="NO PROFILE LTD")
    e.db.commit()
    r = e.rows(party_id=stranger.id, as_of="2026-11-11")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["view"] == "party" and body["data"] == [] and body["total"] == 0
    assert body["party"]["has_profile"] is False
    assert body["party"]["customer_code"] == "304-R999"
    assert body["party"]["markup_pct"] is None and body["party"]["product_count"] == 0


def test_an_unknown_party_id_is_404(costing_env):
    import uuid

    e, w = _setup(costing_env)
    assert e.rows(party_id=str(uuid.uuid4()), as_of="2026-11-11").status_code == 404


# ------------------------------------------------------------------ AC-CG-06 supplier expand


def _sup(response):
    assert response.status_code == 200, response.text
    return {s["supplier_code"]: s for s in response.json()["data"]}


def test_ac_cg_06_party_expand_shows_margin_if_bought_from_each_supplier(costing_env):
    """WB 245 at Bath Plus 8%: A 130.61, B 114.35, L 34.96; D has no EUR rate."""
    e, w = _setup(costing_env)
    s = _sup(e.get(f"/rows/{w.wb.id}/suppliers", party_id=w.customer.id, as_of="2026-11-11"))
    assert set(s) == {"SUP-A01", "SUP-B07", "SUP-L05", "SUP-D03"}

    a = s["SUP-A01"]
    assert a["supplier_id"] == w.sup_a.id and a["supplier_name"] == "SUP-A01 Ltd"
    assert a["is_primary"] is True and a["lead_time_days"] == 30
    assert a["currency"] == "CNY" and a["unit_cost"] == A(34.5)
    assert a["landing"] == A(31.71875, abs=1e-6)
    assert a["markup_pct"] == A(8.0)
    assert a["final"] == A(34.25625, abs=1e-6)
    assert a["margin_pct"] == A(130.6148513, abs=1e-6)

    assert s["SUP-B07"]["is_primary"] is False
    assert s["SUP-B07"]["landing"] == A(34.125, abs=1e-6)
    assert s["SUP-B07"]["final"] == A(36.855, abs=1e-6)
    assert s["SUP-B07"]["margin_pct"] == A(114.3535477, abs=1e-6)
    assert s["SUP-L05"]["landing"] == A(54.2, abs=1e-6)
    assert s["SUP-L05"]["margin_pct"] == A(34.9596829, abs=1e-6)

    d = s["SUP-D03"]
    assert d["currency"] == "EUR" and d["unit_cost"] == A(7.5)
    assert d["landing"] is None and d["final"] is None and d["margin_pct"] is None
    assert d["reasons"] == [{"code": "no_rate", "currency": "EUR", "date": "2026-11-11"}]


def test_ac_cg_06_expand_uses_the_rows_own_markup(costing_env):
    e, w = _setup(costing_env)
    s = _sup(e.get(f"/rows/{w.jac.id}/suppliers", party_id=w.customer.id, as_of="2026-11-11"))
    assert s["SUP-A01"]["markup_pct"] == A(10.0)
    assert s["SUP-A01"]["final"] == A(1861.6125, abs=1e-6)
    assert s["SUP-A01"]["margin_pct"] == A(114.8100101, abs=1e-6)


def test_ac_cg_06_standard_expand_shows_markup_if_bought_here_and_no_margin(costing_env):
    e, w = _setup(costing_env)
    s = _sup(e.get(f"/rows/{w.wb.id}/suppliers", as_of="2026-11-11"))
    assert s["SUP-A01"]["final"] == A(79.0)
    assert s["SUP-A01"]["markup_pct"] == A(149.0640394, abs=1e-6)
    assert s["SUP-B07"]["markup_pct"] == A((79 - 34.125) / 34.125 * 100, abs=1e-6)
    assert s["SUP-L05"]["markup_pct"] == A((79 - 54.2) / 54.2 * 100, abs=1e-6)
    for row in s.values():
        assert row["margin_pct"] is None
    assert s["SUP-D03"]["markup_pct"] is None and s["SUP-D03"]["landing"] is None


def test_ac_cg_06_expand_follows_as_of(costing_env):
    e, w = _setup(costing_env)
    s = _sup(e.get(f"/rows/{w.wb.id}/suppliers", as_of="2026-10-31"))
    assert s["SUP-A01"]["landing"] == A(34.5 * 0.617284 * 1.1 + 8, abs=1e-6)


def test_ac_cg_06_expand_of_an_unknown_product_is_404(costing_env):
    import uuid

    e, w = _setup(costing_env)
    assert e.get(f"/rows/{uuid.uuid4()}/suppliers", as_of="2026-11-11").status_code == 404
