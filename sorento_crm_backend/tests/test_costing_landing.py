"""RED tests B4: the pure landing / mark-up / margin math (PRODUCT-COSTING, Phase 2).

ASSUMED SIGNATURES (the coder implements exactly these; module `app/services/costing/formula.py`):

    landing(unit_cost, rate_to_base, sst_factor, transport_mode, transport_value) -> Decimal
        unit_cost * rate_to_base * sst_factor, then `+ value` (mode "add") or `* value`
        (mode "multiply"); mode None / value None -> `+ 0`. Full precision, no rounding.
    party_final(landing, markup_pct) -> Decimal            landing * (1 + markup_pct / 100)
    achieved_markup(list_price, landing) -> Decimal        (list_price - landing) / landing * 100
    margin(list_price, final) -> Decimal                   (list_price - final) / final * 100
    display2(value) -> Decimal                             2 dp, ROUND_HALF_UP
    All arguments are Decimal (or str/int) and all results are Decimal.

    app/services/costing/basis.py::cost_basis(db, product_id, *, as_of, party_customer_id=None) -> dict
        Decimal money/rates, keys as the contract Row fields. See test_costing_methods.py.

Covers AC-LC-01, AC-ST-02, AC-ST-03, AC-CG-03, AC-CG-04.
Kill tests: ADD before SST; rounding anywhere but the display.
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from tests.support.costing_env import AS_OF, costing_env, f  # noqa: F401


def _formula():
    from app.services.costing import formula

    return formula


# ---------------------------------------------------------------- AC-LC-01 five figures


@pytest.mark.parametrize(
    "unit_cost,rate,mode,value,expected",
    [
        # workbook row: RMB 34.50 x 0.625 x 1.1 + 8
        ("34.50", "0.625", "add", "8", "31.71875"),
        ("120", "0.625", "multiply", "1.07", "88.275"),
        ("260", "0.625", "multiply", "1.1", "196.625"),
        ("20", "4.40", "multiply", "1.07", "103.576"),
        # MYR: rate 1, SST still applied
        ("42", "1", "add", "8", "54.2"),
    ],
)
def test_ac_lc_01_landing_five_workbook_figures_at_full_precision(unit_cost, rate, mode, value, expected):
    got = _formula().landing(D(unit_cost), D(rate), D("1.1"), mode, D(value))
    assert isinstance(got, D)
    assert got == D(expected)


def test_ac_lc_01_add_is_applied_after_sst_not_before():
    """KILL TEST: (34.50 x 0.625 + 8) x 1.1 = 32.5625 would be the ADD-before-SST answer."""
    got = _formula().landing(D("34.50"), D("0.625"), D("1.1"), "add", D("8"))
    assert got == D("31.71875")
    assert got != D("32.5625")


def test_ac_lc_01_sst_factor_is_an_input_not_a_constant():
    got = _formula().landing(D("100"), D("1"), D("1.06"), "add", D("0"))
    assert got == D("106")


# ---------------------------------------------------------------- display rounding


@pytest.mark.parametrize(
    "value,shown",
    [
        ("31.71875", "31.72"),
        ("212.355", "212.36"),
        ("238.815", "238.82"),
        ("0.125", "0.13"),  # banker's rounding would give 0.12
        ("2.675", "2.68"),  # binary float would give 2.67
        ("88.275", "88.28"),
    ],
)
def test_ac_lc_01_display_rounds_half_up_to_two_places(value, shown):
    got = _formula().display2(D(value))
    assert got == D(shown)


def test_display_rounding_does_not_touch_the_stored_figure():
    """Only display2 rounds: landing keeps every digit (KILL: rounding inside the math)."""
    got = _formula().landing(D("34.50"), D("0.625"), D("1.1"), "add", D("8"))
    assert got == D("31.71875")  # not 31.72
    final = _formula().party_final(got, D("8"))
    assert final == D("34.25625")  # 31.72 x 1.08 would be 34.2576


# ---------------------------------------------------------------- party price / mark-up / margin


def test_ac_cg_04_party_final_and_margin_workbook_row():
    fm = _formula()
    final = fm.party_final(D("31.71875"), D("8"))
    assert final == D("34.25625")
    assert fm.display2(final) == D("34.26")
    m = fm.margin(D("79.00"), final)
    assert float(m) == pytest.approx(130.6148513, abs=1e-6)
    assert fm.display2(m) == D("130.61")


def test_ac_cg_04_jacuzzi_row_markup_ten_percent():
    fm = _formula()
    landing = fm.landing(D("2450"), D("0.625"), D("1.1"), "add", D("8"))
    assert landing == D("1692.375")
    final = fm.party_final(landing, D("10"))
    assert final == D("1861.6125")
    assert fm.display2(fm.margin(D("3998.93"), final)) == D("114.81")


def test_ac_cg_04_bath_plus_party_prices_from_the_plan():
    fm = _formula()
    assert fm.display2(fm.party_final(D("88.275"), D("8"))) == D("95.34")
    assert fm.display2(fm.party_final(D("196.625"), D("8"))) == D("212.36")  # 212.355
    assert fm.display2(fm.party_final(D("103.576"), D("8"))) == D("111.86")


def test_ac_cg_03_achieved_markup_company_standard():
    got = _formula().achieved_markup(D("79.00"), D("31.71875"))
    assert float(got) == pytest.approx(149.0640394, abs=1e-6)
    assert _formula().display2(got) == D("149.06")


def test_zero_percent_markup_final_equals_landing():
    assert _formula().party_final(D("12.5"), D("0")) == D("12.5")


# ---------------------------------------------------------------- AC-ST-02 / AC-ST-03 (through cost_basis)


def test_ac_st_03_no_rule_adds_zero_and_flags_it(costing_env):
    e = costing_env
    from app.services.costing.basis import cost_basis

    e.rate("RMB", "0.625", AS_OF.replace(month=11, day=1))
    cat = e.category("NoRuleCat")  # no transport rule
    p = e.item("ZZ-NORULE", category=cat, list_price="100")
    e.cost_link(p, e.source("SUP-NR"), cost="34.50", currency="RMB", primary=True)
    e.db.commit()

    got = cost_basis(e.db, p.id, as_of=AS_OF)
    assert f(got["landing"]) == pytest.approx(23.71875, abs=1e-6)  # 34.5 x 0.625 x 1.1, + 0
    assert got["transport_source"] is None
    assert got["transport_mode"] is None
    assert "no_transport_rule" in [r["code"] for r in got["reasons"]]


def test_ac_st_02_product_override_beats_category_rule(costing_env):
    e = costing_env
    from app.services.costing.basis import cost_basis

    w = e.workbook()
    # category rule ADD 8 -> 31.71875
    base = cost_basis(e.db, w.wb.id, as_of=AS_OF)
    assert base["transport_source"] == "category"
    assert f(base["landing"]) == pytest.approx(31.71875, abs=1e-6)

    e.override(w.wb, transport_mode="multiply", transport_value="1.5")
    e.db.commit()
    got = cost_basis(e.db, w.wb.id, as_of=AS_OF)
    assert got["transport_source"] == "product"
    assert got["transport_mode"] == "multiply"
    assert f(got["transport_value"]) == pytest.approx(1.5)
    assert f(got["landing"]) == pytest.approx(34.5 * 0.625 * 1.1 * 1.5, abs=1e-6)


def test_ac_st_02_only_the_products_own_category_is_read_no_parent_walk(costing_env):
    e = costing_env
    from app.models.product import ProductCategory
    from app.services.costing.basis import cost_basis

    e.rate("RMB", "0.625", AS_OF.replace(month=11, day=1))
    parent = e.category("ParentCat", rule=("add", 8))
    child = ProductCategory(id=str(__import__("uuid").uuid4()), category_code="ZZPC-CHILD",
                            category_name="Child", parent_category_id=parent.id)
    e.db.add(child)
    e.db.flush()
    p = e.item("ZZ-CHILD", category=child, list_price="100")
    e.cost_link(p, e.source("SUP-CH"), cost="34.50", currency="RMB", primary=True)
    e.db.commit()

    got = cost_basis(e.db, p.id, as_of=AS_OF)
    assert got["transport_source"] is None
    assert "no_transport_rule" in [r["code"] for r in got["reasons"]]
