"""RED tests B5: the cost basis and the four cost methods (PRODUCT-COSTING, Phase 2).
AC-LC-02, AC-LC-03, AC-LC-04, AC-LC-05 (LC-06 is in test_party_costing_profiles.py and
test_costing_settings.py, where the refusing routes are).

ASSUMED SIGNATURE (module `app/services/costing/basis.py`):

    cost_basis(db, product_id, *, as_of, party_customer_id=None) -> dict

        `as_of` is a date. Money and rates in the dict are Decimal; tests compare via float().
        Keys (the contract Row fields): landing, cost_method, cost_method_source, supplier_code,
        unit_cost, currency, rate_to_base, rate_effective_from, sst_factor, transport_mode,
        transport_value, transport_source, reasons, skipped, po_number, po_date.
        `reasons` is a list of dicts with `code` (and `currency` / `date` for no_rate);
        `skipped` is [{"supplier_code": ..., "reason": ...}].
        Unknown numbers are None, never 0. There is no fallback between methods.

Rate: the 6-dp stored rate is used (CNY 0.617284, not 1/1.62), so the Last-PO figure is
31.4259278 here; the plan's 31.425926 is the same number computed from the unrounded 1/1.62.
"""
from __future__ import annotations

from datetime import date

import pytest

from tests.support.costing_env import AS_OF, AS_OF_OLD, costing_env, f  # noqa: F401


def _basis(e, product, **kw):
    from app.services.costing.basis import cost_basis

    kw.setdefault("as_of", AS_OF)
    return cost_basis(e.db, product.id, **kw)


def _codes(got):
    return [r["code"] for r in got["reasons"]]


# ------------------------------------------------------------------ AC-LC-02 cost in force


def test_ac_lc_02_cost_in_force_changes_with_the_date(costing_env):
    e = costing_env
    e.rate("CNY", "0.625", date(2026, 1, 1))
    cat = e.category("C1", rule=("add", 8))
    p = e.item("ZZ-DATED", category=cat, list_price="100")
    link = e.cost_link(p, e.source("SUP-DT"), primary=True)
    e.cost_row(link, "34.50", "CNY", start_date=date(2026, 1, 1), end_date=date(2026, 10, 31))
    e.cost_row(link, "40.00", "CNY", start_date=date(2026, 11, 1))
    e.db.commit()

    assert f(_basis(e, p, as_of=date(2026, 10, 31))["unit_cost"]) == pytest.approx(34.5)
    assert f(_basis(e, p, as_of=date(2026, 11, 1))["unit_cost"]) == pytest.approx(40.0)
    # nothing in force before the first row: no cost, no fallback to a later row
    early = _basis(e, p, as_of=date(2025, 12, 31))
    assert early["landing"] is None
    assert "no_cost" in _codes(early)


def test_ac_lc_02_standard_packaging_row_wins_over_a_cheaper_packaging(costing_env):
    e = costing_env
    e.rate("CNY", "0.625", date(2026, 1, 1))
    cat = e.category("C2", rule=("add", 8))
    p = e.item("ZZ-PKG", category=cat, list_price="100")
    link = e.cost_link(p, e.source("SUP-PK"), primary=True)
    e.cost_row(link, "30.00", "CNY", packaging="OPP")
    e.cost_row(link, "34.50", "CNY", packaging="standard")
    e.db.commit()
    assert f(_basis(e, p)["unit_cost"]) == pytest.approx(34.5)


def test_ac_lc_02_the_only_packaging_is_used_when_there_is_no_standard_row(costing_env):
    e = costing_env
    e.rate("CNY", "0.625", date(2026, 1, 1))
    cat = e.category("C3", rule=("add", 8))
    p = e.item("ZZ-PKG1", category=cat, list_price="100")
    link = e.cost_link(p, e.source("SUP-PK1"), primary=True)
    e.cost_row(link, "36.00", "CNY", packaging="OPP")
    e.db.commit()
    assert f(_basis(e, p)["unit_cost"]) == pytest.approx(36.0)


def test_ac_lc_02_several_packagings_and_no_standard_row_is_no_cost(costing_env):
    """`current_cost` returns None here; the contract wins over the plan's older 'cheapest' note."""
    e = costing_env
    e.rate("CNY", "0.625", date(2026, 1, 1))
    cat = e.category("C4", rule=("add", 8))
    p = e.item("ZZ-PKG2", category=cat, list_price="100")
    link = e.cost_link(p, e.source("SUP-PK2"), primary=True)
    e.cost_row(link, "30.00", "CNY", packaging="OPP")
    e.cost_row(link, "33.00", "CNY", packaging="BOX")
    e.db.commit()
    got = _basis(e, p)
    assert got["landing"] is None
    assert "no_cost" in _codes(got)


def test_ac_lc_02_a_link_with_no_cost_rows_uses_its_own_unit_cost_and_currency(costing_env):
    e = costing_env
    e.rate("CNY", "0.625", date(2026, 1, 1))
    cat = e.category("C5", rule=("add", 8))
    p = e.item("ZZ-LINKCOST", category=cat, list_price="100")
    e.cost_link(p, e.source("SUP-LC"), cost="34.50", currency="CNY", primary=True, mirror_unit_cost=True)
    e.db.commit()
    got = _basis(e, p)
    assert f(got["unit_cost"]) == pytest.approx(34.5)
    assert got["currency"] == "CNY"
    assert f(got["landing"]) == pytest.approx(31.71875, abs=1e-6)


def test_ac_lc_02_link_with_neither_cost_rows_nor_unit_cost_has_no_cost(costing_env):
    e = costing_env
    w = e.workbook()
    got = _basis(e, w.acc)  # primary link, nothing priced
    assert got["landing"] is None
    assert got["unit_cost"] is None
    assert _codes(got) == ["no_cost"]  # transport rule exists, so no second reason


# ------------------------------------------------------------------ rate and SST


def test_ac_er_02_the_rate_follows_the_as_of_date(costing_env):
    e = costing_env
    w = e.workbook()
    new = _basis(e, w.wb, as_of=AS_OF)
    assert f(new["rate_to_base"]) == pytest.approx(0.625)
    assert new["rate_effective_from"] == date(2026, 11, 1)
    old = _basis(e, w.wb, as_of=AS_OF_OLD)
    assert f(old["rate_to_base"]) == pytest.approx(0.617284)
    assert old["rate_effective_from"] == date(2026, 9, 1)
    assert f(old["landing"]) == pytest.approx(34.5 * 0.617284 * 1.1 + 8, abs=1e-6)


def test_ac_er_03_no_rate_blanks_the_landing_and_names_currency_and_date(costing_env):
    e = costing_env
    w = e.workbook()
    # CNY has no row on or before 15 Aug
    got = _basis(e, w.wb, as_of=date(2026, 8, 15))
    assert got["landing"] is None
    nr = [r for r in got["reasons"] if r["code"] == "no_rate"]
    assert len(nr) == 1 and nr[0]["currency"] == "CNY" and str(nr[0]["date"]) == "2026-08-15"


def test_ac_er_03_myr_is_rate_one_with_sst_still_applied(costing_env):
    e = costing_env
    w = e.workbook()
    e.override(w.wb, cost_method="selected", cost_method_supplier_id=w.sup_l.id)
    e.db.commit()
    got = _basis(e, w.wb)
    assert f(got["rate_to_base"]) == pytest.approx(1.0)
    assert f(got["landing"]) == pytest.approx(54.2, abs=1e-6)  # 42 x 1 x 1.1 + 8


def test_ac_st_01_sst_factor_comes_from_the_company_setting(costing_env):
    e = costing_env
    w = e.workbook()
    assert f(_basis(e, w.wb)["sst_factor"]) == pytest.approx(1.1)
    e.set_settings(sst_factor="1.2")
    e.db.commit()
    got = _basis(e, w.wb)
    assert f(got["sst_factor"]) == pytest.approx(1.2)
    assert f(got["landing"]) == pytest.approx(34.5 * 0.625 * 1.2 + 8, abs=1e-6)


# ------------------------------------------------------------------ AC-LC-03 primary


def test_ac_lc_03_primary_uses_the_primary_links_cost(costing_env):
    e = costing_env
    w = e.workbook()
    got = _basis(e, w.wb)
    assert got["cost_method"] == "primary"
    assert got["cost_method_source"] == "company"
    assert got["supplier_code"] == "SUP-A01"
    assert f(got["unit_cost"]) == pytest.approx(34.5)
    assert got["currency"] == "CNY"
    assert f(got["landing"]) == pytest.approx(31.71875, abs=1e-6)
    assert got["skipped"] == []
    assert got["reasons"] == []


def test_ac_lc_03_no_primary_link_is_set_a_primary_supplier(costing_env):
    e = costing_env
    w = e.workbook()
    from app.models.procurement import ProductSupplier

    w.link_a.is_primary_supplier = False
    e.db.commit()
    got = _basis(e, w.wb)
    assert got["landing"] is None
    assert "no_primary" in _codes(got)

    # a product with no links at all is the same reason
    bare = _basis(e, w.bare)
    assert bare["landing"] is None
    assert _codes(bare) == ["no_primary"]


def test_ac_lc_05_primary_with_no_cost_does_not_fall_back_to_another_supplier(costing_env):
    e = costing_env
    w = e.workbook()
    from app.models.cost_price import ProductSupplierCost

    e.db.query(ProductSupplierCost).filter(ProductSupplierCost.product_supplier_id == w.link_a.id).delete()
    e.db.commit()
    got = _basis(e, w.wb)  # B, L still carry prices
    assert got["landing"] is None
    assert "no_cost" in _codes(got)
    assert got["cost_method"] == "primary"


# ------------------------------------------------------------------ AC-LC-03 selected


def test_ac_lc_03_selected_supplier_uses_the_product_overrides_link(costing_env):
    e = costing_env
    w = e.workbook()
    e.override(w.wb, cost_method="selected", cost_method_supplier_id=w.sup_b.id)
    e.db.commit()
    got = _basis(e, w.wb)
    assert got["cost_method"] == "selected"
    assert got["cost_method_source"] == "product"
    assert got["supplier_code"] == "SUP-B07"
    assert f(got["landing"]) == pytest.approx(34.125, abs=1e-6)


def test_ac_lc_03_selected_supplier_no_longer_linked_is_named_and_not_replaced(costing_env):
    e = costing_env
    w = e.workbook()
    e.override(w.wb, cost_method="selected", cost_method_supplier_id=w.sup_b.id)
    e.db.delete(w.link_b)
    e.db.commit()
    got = _basis(e, w.wb)
    assert got["landing"] is None
    assert "selected_not_linked" in _codes(got)  # no silent switch to the primary (LC-05)


def test_ac_lc_03_deleting_the_selected_supplier_succeeds_and_reads_not_linked(costing_env):
    """The supplier FK is ON DELETE SET NULL and the DB allows `selected` with no supplier
    (contract section 2), so removing a supplier a product override selects never fails; the
    row then says so instead of silently switching method."""
    from app.models.costing import CostingProductOverride

    e = costing_env
    w = e.workbook()
    e.override(w.wb, cost_method="selected", cost_method_supplier_id=w.sup_b.id)
    e.db.commit()
    e.db.delete(w.link_b)
    e.db.flush()
    e.db.delete(w.sup_b)
    e.db.commit()
    e.db.expire_all()
    ov = e.db.get(CostingProductOverride, w.wb.id)
    assert ov.cost_method == "selected" and ov.cost_method_supplier_id is None
    got = _basis(e, w.wb)
    assert got["landing"] is None
    assert "selected_not_linked" in _codes(got)


# ------------------------------------------------------------------ AC-LC-03 average


def test_ac_lc_03_average_of_supplier_landings_with_the_unrated_link_skipped_and_named(costing_env):
    """WB 245: A 31.71875, B 34.125, L 54.20; D is EUR with no EUR rate."""
    e = costing_env
    w = e.workbook()
    e.override(w.wb, cost_method="average")
    e.db.commit()
    got = _basis(e, w.wb)
    assert got["cost_method"] == "average"
    assert got["supplier_code"] is None
    assert f(got["landing"]) == pytest.approx(40.0145833, abs=1e-6)
    assert got["skipped"] == [{"supplier_code": "SUP-D03", "reason": "no_rate"}]
    # KILL TEST: counting the skipped link as 0 would give (31.71875+34.125+54.2+0)/4 = 30.011
    assert f(got["landing"]) != pytest.approx(30.011, abs=0.01)


def test_ac_lc_03_average_skips_a_link_with_no_cost_and_names_it(costing_env):
    e = costing_env
    w = e.workbook()
    e.cost_link(w.wb, e.source("SUP-E09"))  # linked, never priced
    e.override(w.wb, cost_method="average")
    e.db.commit()
    got = _basis(e, w.wb)
    assert f(got["landing"]) == pytest.approx(40.0145833, abs=1e-6)
    skipped = {(s["supplier_code"], s["reason"]) for s in got["skipped"]}
    assert skipped == {("SUP-D03", "no_rate"), ("SUP-E09", "no_cost")}


def test_ac_lc_03_average_with_nothing_usable_is_no_cost(costing_env):
    e = costing_env
    w = e.workbook()
    # the shower has one USD link; remove the USD rate row so nothing is usable
    from app.models.costing import ExchangeRate

    e.db.query(ExchangeRate).filter(ExchangeRate.currency == "USD").delete()
    e.override(w.shower, cost_method="average")
    e.db.commit()
    got = _basis(e, w.shower)
    assert got["landing"] is None
    assert "no_cost" in _codes(got)
    assert got["skipped"] == [{"supplier_code": "SUP-D03", "reason": "no_rate"}]


# ------------------------------------------------------------------ AC-LC-03 last PO


def _last_po(e, w, **kw):
    e.override(w.wb, cost_method="last_po")
    return e.po_line(w.wb, w.sup_a, **kw)


def test_ac_lc_03_last_po_is_converted_at_the_rate_on_the_po_date_not_today(costing_env):
    """CNY 34.50 on 14 Oct 2026: rate then 0.617284 -> 31.4259278. KILL TEST: today's rate
    (0.625) would give 31.71875."""
    e = costing_env
    w = e.workbook()
    _last_po(e, w, po_number="PO-OCT14", issue_date=date(2026, 10, 14), unit_cost="34.50", currency="CNY")
    e.db.commit()
    got = _basis(e, w.wb)
    assert got["cost_method"] == "last_po"
    assert f(got["landing"]) == pytest.approx(31.4259278, abs=1e-6)
    assert f(got["landing"]) != pytest.approx(31.71875, abs=1e-3)
    assert got["po_number"] == "PO-OCT14"
    assert got["po_date"] == date(2026, 10, 14)
    assert f(got["rate_to_base"]) == pytest.approx(0.617284)
    assert got["rate_effective_from"] == date(2026, 9, 1)


def test_ac_lc_03_last_po_picks_the_latest_issue_date_on_or_before_as_of(costing_env):
    e = costing_env
    w = e.workbook()
    _last_po(e, w, po_number="PO-SEP", issue_date=date(2026, 9, 10), unit_cost="30.00", currency="CNY")
    e.po_line(w.wb, w.sup_a, po_number="PO-OCT", issue_date=date(2026, 10, 14), unit_cost="34.50", currency="CNY")
    e.po_line(w.wb, w.sup_a, po_number="PO-NOV20", issue_date=date(2026, 11, 20), unit_cost="99.00", currency="CNY")
    e.db.commit()
    assert _basis(e, w.wb, as_of=date(2026, 11, 11))["po_number"] == "PO-OCT"
    # the <= boundary: a PO issued on the as_of day counts
    assert _basis(e, w.wb, as_of=date(2026, 10, 14))["po_number"] == "PO-OCT"
    assert _basis(e, w.wb, as_of=date(2026, 10, 13))["po_number"] == "PO-SEP"
    assert _basis(e, w.wb, as_of=date(2026, 11, 20))["po_number"] == "PO-NOV20"


def test_ac_lc_03_last_po_ignores_removed_and_unpriced_lines(costing_env):
    e = costing_env
    w = e.workbook()
    _last_po(e, w, po_number="PO-GOOD", issue_date=date(2026, 10, 1), unit_cost="34.50", currency="CNY")
    e.po_line(w.wb, w.sup_a, po_number="PO-REMOVED", issue_date=date(2026, 10, 20),
              unit_cost="50.00", currency="CNY", removed=True)
    e.po_line(w.wb, w.sup_a, po_number="PO-NOPRICE", issue_date=date(2026, 10, 25),
              unit_cost=None, currency="CNY")
    e.db.commit()
    assert _basis(e, w.wb)["po_number"] == "PO-GOOD"


def test_ac_lc_03_last_po_ties_on_issue_date_go_to_the_newest_created_line(costing_env):
    from datetime import datetime

    e = costing_env
    w = e.workbook()
    _last_po(e, w, po_number="PO-FIRST", issue_date=date(2026, 10, 14), unit_cost="30.00",
             currency="CNY", created_at=datetime(2026, 10, 14, 9, 0))
    e.po_line(w.wb, w.sup_a, po_number="PO-SECOND", issue_date=date(2026, 10, 14), unit_cost="34.50",
              currency="CNY", created_at=datetime(2026, 10, 14, 15, 0))
    e.db.commit()
    got = _basis(e, w.wb)
    assert got["po_number"] == "PO-SECOND"
    assert f(got["unit_cost"]) == pytest.approx(34.5)


def test_ac_lc_03_last_po_currency_is_the_line_currency_else_the_po_header(costing_env):
    e = costing_env
    w = e.workbook()
    # header says USD, the line says CNY: the line wins
    _last_po(e, w, po_number="PO-MIX", issue_date=date(2026, 10, 14), unit_cost="34.50",
             currency="CNY", po_currency="USD")
    e.db.commit()
    assert _basis(e, w.wb)["currency"] == "CNY"

    # line currency empty: the header's
    w2 = e.item("ZZ-POHDR", category=w.cat_ceramics, list_price="50")
    e.override(w2, cost_method="last_po")
    e.po_line(w2, w.sup_a, po_number="PO-HDR", issue_date=date(2026, 10, 14), unit_cost="10.00",
              currency=None, po_currency="USD")
    e.db.commit()
    got = _basis(e, w2)
    assert got["currency"] == "USD"
    assert f(got["rate_to_base"]) == pytest.approx(4.4)


def test_ac_lc_03_last_po_with_no_rate_on_the_po_date_is_no_rate(costing_env):
    e = costing_env
    w = e.workbook()
    _last_po(e, w, po_number="PO-OLD", issue_date=date(2026, 8, 1), unit_cost="34.50", currency="CNY")
    e.db.commit()
    got = _basis(e, w.wb)  # CNY has no row on 1 Aug 2026
    assert got["landing"] is None
    nr = [r for r in got["reasons"] if r["code"] == "no_rate"]
    assert nr and nr[0]["currency"] == "CNY" and str(nr[0]["date"]) == "2026-08-01"


def test_ac_lc_05_last_po_with_no_po_is_no_po_price_and_does_not_use_supplier_costs(costing_env):
    e = costing_env
    w = e.workbook()
    e.override(w.wb, cost_method="last_po")
    e.db.commit()
    got = _basis(e, w.wb)  # the links carry plenty of price-list costs
    assert got["landing"] is None
    assert "no_po_price" in _codes(got)
    assert got["po_number"] is None and got["po_date"] is None


# ------------------------------------------------------------------ AC-LC-04 precedence


def test_ac_lc_04_company_default_applies_when_nothing_overrides(costing_env):
    e = costing_env
    w = e.workbook()
    e.set_settings(default_method="average")
    e.db.commit()
    got = _basis(e, w.wb)
    assert (got["cost_method"], got["cost_method_source"]) == ("average", "company")


def test_ac_lc_04_party_method_beats_the_company_default(costing_env):
    e = costing_env
    w = e.workbook()
    e.set_settings(default_method="average")
    w.profile.cost_method = "primary"
    e.db.commit()
    got = _basis(e, w.wb, party_customer_id=w.customer.id)
    assert (got["cost_method"], got["cost_method_source"]) == ("primary", "party")
    assert f(got["landing"]) == pytest.approx(31.71875, abs=1e-6)
    # no party given: the party's method is not in play
    assert _basis(e, w.wb)["cost_method"] == "average"


def test_ac_lc_04_product_override_beats_party_and_company_kill_party_over_product(costing_env):
    """KILL TEST: precedence party > product would report 'primary' / 'party' here."""
    e = costing_env
    w = e.workbook()
    e.set_settings(default_method="average")
    w.profile.cost_method = "primary"
    e.override(w.wb, cost_method="selected", cost_method_supplier_id=w.sup_b.id)
    e.db.commit()
    got = _basis(e, w.wb, party_customer_id=w.customer.id)
    assert (got["cost_method"], got["cost_method_source"]) == ("selected", "product")
    assert f(got["landing"]) == pytest.approx(34.125, abs=1e-6)


def test_ac_lc_04_party_without_a_method_falls_through_to_the_company_default(costing_env):
    e = costing_env
    w = e.workbook()
    e.set_settings(default_method="average")
    e.db.commit()
    got = _basis(e, w.wb, party_customer_id=w.customer.id)  # profile.cost_method is None
    assert (got["cost_method"], got["cost_method_source"]) == ("average", "company")


def test_ac_lc_04_a_customer_with_no_profile_falls_through(costing_env):
    e = costing_env
    w = e.workbook()
    stranger = e.customer(code="304-R999", name="NO PROFILE LTD")
    e.db.commit()
    got = _basis(e, w.wb, party_customer_id=stranger.id)
    assert (got["cost_method"], got["cost_method_source"]) == ("primary", "company")


def test_ac_lc_04_the_company_default_is_primary_when_no_settings_row_exists(costing_env):
    e = costing_env
    w = e.workbook()
    got = _basis(e, w.wb)
    assert (got["cost_method"], got["cost_method_source"]) == ("primary", "company")
