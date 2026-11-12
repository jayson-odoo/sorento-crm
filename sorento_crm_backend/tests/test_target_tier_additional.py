"""Tier "Additional" as a column (lane TARGET-TIER-ADDITIONAL, owner answers 5 Nov 11:10).

Plan: documentation/plans/sales/PLAN-target-tier-additional-05nov.md.

- Each main tier carries an optional Additional: a % (`additional_rate`, new) or a fixed RM (the
  existing `bonus_amount`, reused). Only the REACHED tier's Additional pays; it replaces the
  16 Oct Q5 stacking of "+ Additional" rows.
- The % Additional is added on every account the tier pays, as its own line, rounded on its own.
- Legacy "+ Additional from X" rows fold onto the tier of the same period and threshold.

Real numbers: A CRAFT IDEA SDN BHD A/C I, 2026 Q1 achieved 76,793.92 (tiers 60,000 / 75,000 /
85,000 at 5 / 6 / 7 % + 1 %), Q2 achieved 61,804.93 (5 / 6 / 7 %, no Additional).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from app.services.sales.commission_service import FoldRow, Tier, fold_additionals, payout_for

from .test_dealer_targets_api import _customer, _dealer_body, _period, _product_id, _sale
from .test_sales_targets_s1 import BASE, api, world  # noqa: F401  (fixtures)

A1, CE, A3 = "acc-i", "acc-ce", "acc-iii"
Q1_ACHIEVED = D("76793.92")
Q2_ACHIEVED = D("61804.93")


def tier(threshold, rate=0, *, add=None, bonus=None, accounts=None, additional=False):
    return Tier(
        from_pct=None,
        rate=D(str(rate)),
        bonus_amount=None if bonus is None else D(str(bonus)),
        threshold=D(str(threshold)),
        is_additional=additional,
        account_rates=None if accounts is None else {k: D(str(v)) for k, v in accounts.items()},
        additional_rate=None if add is None else D(str(add)),
    )


def _pay(tiers, achieved, method="retroactive", **kw):
    return payout_for(method, tiers, D("0"), achieved, threshold_unit="amount", **kw)


# ------------------------------------------------------------------ engine


def test_a_craft_q1_pays_the_reached_tier_rate_plus_its_additional_only():
    tiers = [tier(60000, 5, add=1), tier(75000, 6, add=1), tier(85000, 7, add=1)]
    out = _pay(tiers, {A1: Q1_ACHIEVED})
    assert out.tier_reached == 2
    # 76,793.92 x 6% = 4,607.6352; x 1% = 767.9392; each line rounded on its own (ruling 3).
    assert [(line.kind, line.amount) for line in out.lines] == [
        ("main", D("4607.64")),
        ("additional", D("767.94")),
    ]
    assert out.commission == D("5375.58")
    assert out.bonus == D("0.00")


def test_a_craft_q2_no_additional():
    out = _pay([tier(60000, 5), tier(75000, 6), tier(85000, 7)], {A1: Q2_ACHIEVED})
    assert out.tier_reached == 1
    assert out.commission == D("3090.25")
    assert [line.kind for line in out.lines] == ["main"]


def test_below_the_first_tier_pays_no_additional():
    out = _pay([tier(60000, 5, add=1)], {A1: D("59999.99")})
    assert out.commission == D("0")
    assert out.lines == []


def test_fixed_rm_additional_is_the_bonus_of_the_reached_tier_only():
    # Owner Q2: Bonus is reused as the RM Additional; reaching tier 2 no longer pays tier 1's too.
    tiers = [tier(60000, 5, bonus=500), tier(75000, 6, bonus=800), tier(85000, 7, bonus=1000)]
    out = _pay(tiers, {A1: Q1_ACHIEVED})
    assert out.bonus == D("800.00")
    assert out.commission == D("4607.64")


def test_pct_additional_adds_on_every_account_the_tier_pays():
    # TGT-000051-shaped: A/C I 6%, CE 3%, + 1% on both; A/C III counted but not paid by the tier.
    tiers = [tier(50000, accounts={A1: 6, CE: 3}, add=1)]
    out = _pay(tiers, {A1: D("50000.00"), CE: D("30000.00"), A3: D("10000.00")})
    assert [(line.kind, line.amount) for line in out.lines] == [
        ("main", D("3900.00")),
        ("additional", D("800.00")),
    ]
    assert out.commission == D("4700.00")


def test_marginal_pays_the_top_reached_tier_additional_on_the_whole_achievement():
    tiers = [tier(60000, 5, add=1), tier(75000, 6, add="0.5")]
    out = _pay(tiers, {None: Q1_ACHIEVED}, method="marginal")
    # Slices: (75,000 - 60,000) x 5% + (76,793.92 - 75,000) x 6% = 750 + 107.6352.
    assert [(line.kind, line.amount) for line in out.lines] == [
        ("main", D("857.64")),
        ("additional", D("383.97")),
    ]


def test_quantity_additional_is_rm_per_unit():
    out = _pay([tier(100, 2, add="0.5")], {None: D("120")}, metric="quantity")
    assert out.commission == D("300.00")


# ------------------------------------------------------------------ fold


def _row(threshold, rate, *, additional=False, accounts=None, add=None, bonus=None, start=date(2026, 1, 1)):
    return FoldRow(
        period_start=start,
        threshold=D(str(threshold)),
        is_additional=additional,
        rate=D(str(rate)),
        account_rates=None if accounts is None else {k: D(str(v)) for k, v in accounts.items()},
        additional_rate=None if add is None else D(str(add)),
        bonus_amount=None if bonus is None else D(str(bonus)),
    )


def test_fold_a_craft_q1_rows_onto_their_tiers():
    rows = [
        _row(60000, 5), _row(75000, 6), _row(85000, 7),
        _row(60000, 1, additional=True), _row(75000, 1, additional=True), _row(85000, 1, additional=True),
        # Q2: no additionals, untouched.
        _row(60000, 5, start=date(2026, 4, 1)),
    ]
    out = fold_additionals(rows)
    assert out.moves == {3: 0, 4: 1, 5: 2}
    assert out.rates == {0: D("1"), 1: D("1"), 2: D("1")}
    assert out.skipped == {}


def test_fold_per_account_additional_naming_one_account_becomes_the_tier_additional():
    rows = [_row(50000, 0, accounts={A1: 6, CE: 3}), _row(50000, 0, additional=True, accounts={A1: 1})]
    out = fold_additionals(rows)
    assert out.moves == {1: 0}
    assert out.rates == {0: D("1")}
    # Now added on CE too (owner Q3 default): reported, never silent.
    assert out.broadened == {0}


def test_fold_pay_all_additional_onto_a_named_tier_is_reported_narrowed():
    # "A/C I- 6% + Additional 1%": the tier names A/C I, the additional cell names no account.
    rows = [_row(75000, 0, accounts={A1: 6}), _row(75000, 1, additional=True)]
    out = fold_additionals(rows)
    assert out.moves == {1: 0}
    assert out.rates == {0: D("1")}
    assert out.narrowed == {0}


def test_fold_leaves_and_reports_what_it_cannot_place():
    rows = [
        _row(150000, 2), _row(200000, 3),
        _row(220000, 1, additional=True),                      # no tier at 220,000 (E2)
        _row(200000, 1, additional=True), _row(200000, "0.5", additional=True),  # two on one tier
        _row(300000, 4, bonus=500), _row(300000, 1, additional=True),  # tier has an RM Additional
        _row(400000, 0, accounts={A1: 2, CE: 1}),
        _row(400000, 0, additional=True, accounts={A1: 1, CE: "0.5"}),  # different rate per account
    ]
    out = fold_additionals(rows)
    assert out.moves == {}
    assert set(out.skipped) == {2, 3, 4, 6, 8}
    assert "no tier" in out.skipped[2]
    assert "two" in out.skipped[3]
    assert "Bonus" in out.skipped[6]
    assert "per account" in out.skipped[8]


# ------------------------------------------------------------------ API


def _a_craft_tiers(add_q1=True):
    q1 = [
        {"period_start": "2026-01-01", "threshold": t, "rate": r, **({"additional_rate": 1} if add_q1 else {})}
        for t, r in ((60000, 5), (75000, 6), (85000, 7))
    ]
    q2 = [{"period_start": "2026-04-01", "threshold": t, "rate": r} for t, r in ((60000, 5), (75000, 6), (85000, 7))]
    return q1 + q2


def test_api_saves_reads_and_pays_the_tier_additional(api):
    client, db, company_id = api
    pid = _product_id(db, company_id)
    a1 = _customer(db, company_id, "ZZT A CRAFT IDEA", level=1)
    _sale(db, company_id, a1, str(Q1_ACHIEVED), date(2026, 2, 10), product_id=pid)
    _sale(db, company_id, a1, str(Q2_ACHIEVED), date(2026, 5, 10), product_id=pid)
    res = client.post(BASE, json=_dealer_body([a1], tiers=_a_craft_tiers()))
    assert res.status_code == 201, res.text
    body = res.json()
    q1_tiers = [t for t in body["tiers"] if t["period_start"] == "2026-01-01"]
    assert [t["additional_rate"] for t in q1_tiers] == [1, 1, 1]
    q1 = _period(body, "2026-01-01")
    assert q1["tier_reached"] == 2
    assert q1["commission_earned"] == 5375.58
    assert q1["tier_rates"] == [{"label": None, "rate": 6.0}]
    assert q1["tier_additional"] == {"kind": "pct", "value": 1.0, "accounts": None}
    q2 = _period(body, "2026-04-01")
    assert q2["commission_earned"] == 3090.25
    assert q2["tier_additional"] is None


def test_api_rm_additional_shows_on_the_period(api):
    client, db, company_id = api
    pid = _product_id(db, company_id)
    a1 = _customer(db, company_id, "ZZT A CRAFT RM", level=1)
    _sale(db, company_id, a1, str(Q1_ACHIEVED), date(2026, 2, 10), product_id=pid)
    tiers = [
        {"period_start": "2026-01-01", "threshold": 60000, "rate": 5, "bonus_amount": 300},
        {"period_start": "2026-01-01", "threshold": 75000, "rate": 6, "bonus_amount": 500},
    ]
    body = client.post(BASE, json=_dealer_body([a1], tiers=tiers)).json()
    q1 = _period(body, "2026-01-01")
    assert q1["tier_additional"] == {"kind": "amount", "value": 500.0, "accounts": None}
    assert q1["bonus_earned"] == 500


def test_api_refuses_a_tier_with_both_a_pct_and_an_rm_additional(api):
    client, db, company_id = api
    a1 = _customer(db, company_id, "ZZT BOTH", level=1)
    res = client.post(BASE, json=_dealer_body([a1], tiers=[
        {"period_start": "2026-01-01", "threshold": 60000, "rate": 5, "additional_rate": 1, "bonus_amount": 100},
    ]))
    assert res.status_code == 422, res.text
    assert "not both" in res.text


# ------------------------------------------------------------------ import


def _a_craft_workbook():
    """The owner's 2026 layout for A CRAFT IDEA A/C I, Q1 only (figures as in his file)."""
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "SORENTO 2026"
    ws.cell(row=2, column=1, value="DEALER NAME")
    ws.cell(row=2, column=2, value="ACCOUNT")
    ws.cell(row=2, column=3, value="Q1")
    ws.merge_cells(start_row=2, start_column=3, end_row=2, end_column=12)
    ws.cell(row=3, column=3, value="JAN-MAR")
    ws.merge_cells(start_row=3, start_column=3, end_row=3, end_column=12)
    cells = [
        (60000, "A/C I- 5% + Additional 1%"),
        (">= 75000", "A/C I- 6% + Additional 1%"),
        (85000, "A/C I- 7%"),
        (">=85000", "A/C I- 7% + Additional 1%"),
        (None, None),
    ]
    for n, (threshold, incentive) in enumerate(cells, start=1):
        col = 3 + 2 * (n - 1)
        ws.cell(row=4, column=col, value=f"Tier {n}")
        ws.cell(row=4, column=col + 1, value=f"Tier {n} Incentive")
        ws.cell(row=5, column=col, value=threshold)
        ws.cell(row=5, column=col + 1, value=incentive)
    ws.cell(row=5, column=1, value="A CRAFT IDEA SDN BHD")
    ws.cell(row=5, column=2, value="A/C I")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_a_craft_reads_each_tier_with_its_additional_and_tier_3_4_as_one():
    from app.services.sales.dealer_target_import import parse_workbook

    parsed = parse_workbook(_a_craft_workbook(), year=2026)
    (scheme,) = [s for s in parsed.schemes if s.kind == "quarterly"]
    q1 = [t for t in scheme.tiers if t.period_start == date(2026, 1, 1)]
    assert [
        (t.threshold, list((t.account_rates or {}).values()) or [t.rate], t.additional_rate, t.is_additional)
        for t in q1
    ] == [
        (D("60000"), [D("5")], D("1"), False),
        (D("75000"), [D("6")], D("1"), False),
        (D("85000"), [D("7")], D("1"), False),
    ]


# ------------------------------------------------------------------ fold script


def test_fold_script_reports_a_craft_old_and_new_then_applies(api):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "fold_tier_additionals", Path(__file__).resolve().parents[1] / "scripts" / "fold_tier_additionals.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    client, db, company_id = api
    pid = _product_id(db, company_id)
    a1 = _customer(db, company_id, "ZZT A CRAFT LEGACY", level=1)
    _sale(db, company_id, a1, str(Q1_ACHIEVED), date(2026, 2, 10), product_id=pid)
    _sale(db, company_id, a1, str(Q2_ACHIEVED), date(2026, 5, 10), product_id=pid)
    legacy = _a_craft_tiers(add_q1=False) + [
        {"period_start": "2026-01-01", "threshold": t, "rate": 1, "is_additional": True}
        for t in (60000, 75000, 85000)
    ]
    created = client.post(BASE, json=_dealer_body([a1], tiers=legacy))
    assert created.status_code == 201, created.text
    body = created.json()
    # Live today: 6% + 1% + 1%, each line rounded on its own.
    assert _period(body, "2026-01-01")["commission_earned"] == 6143.52

    (entry,) = [e for e in script.report(db) if e["target_id"] == body["id"]]
    assert entry["additional_rows"] == 3
    assert len(entry["moves"]) == 3
    assert entry["skipped"] == []
    assert entry["ladder_drops"] == []
    q1, q2 = entry["periods"][0], entry["periods"][1]
    assert (q1["old_commission"], q1["new_commission"], q1["delta"]) == (D("6143.52"), D("5375.58"), D("-767.94"))
    assert (q2["old_commission"], q2["new_commission"], q2["delta"]) == (D("3090.25"), D("3090.25"), D("0"))

    # The count guard: no --expect, or a count that is not the dry run's, writes nothing.
    import pytest

    for wrong in (None, 2, 4):
        with pytest.raises(script.ExpectMismatch):
            script.apply(db, [entry], wrong)
    db.expire_all()
    still = client.get(f"{BASE}/{body['id']}").json()
    assert sum(1 for t in still["tiers"] if t["is_additional"]) == 3
    assert script.apply(db, [entry], 3) == 3
    db.expire_all()
    after = client.get(f"{BASE}/{body['id']}").json()
    q1_tiers = [t for t in after["tiers"] if t["period_start"] == "2026-01-01"]
    assert [(t["threshold"], t["rate"], t["additional_rate"], t["is_additional"]) for t in q1_tiers] == [
        (60000, 5, 1, False), (75000, 6, 1, False), (85000, 7, 1, False),
    ]
    assert _period(after, "2026-01-01")["commission_earned"] == 5375.58


def test_fold_script_reports_bonus_stacking_change(api):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "fold_tier_additionals", Path(__file__).resolve().parents[1] / "scripts" / "fold_tier_additionals.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    client, db, company_id = api
    pid = _product_id(db, company_id)
    a1 = _customer(db, company_id, "ZZT BONUS LEGACY", level=1)
    _sale(db, company_id, a1, str(Q1_ACHIEVED), date(2026, 2, 10), product_id=pid)
    tiers = [
        {"period_start": "2026-01-01", "threshold": 60000, "rate": 5, "bonus_amount": 300},
        {"period_start": "2026-01-01", "threshold": 75000, "rate": 6, "bonus_amount": 500},
    ]
    body = client.post(BASE, json=_dealer_body([a1], tiers=tiers)).json()
    (entry,) = [e for e in script.report(db) if e["target_id"] == body["id"]]
    assert entry["bonus_tiers"] == 2
    q1 = entry["periods"][0]
    assert (q1["old_bonus"], q1["new_bonus"], q1["delta"]) == (D("800"), D("500.00"), D("-300.00"))


def test_api_refuses_a_tier_additional_beside_a_legacy_row_on_its_threshold(api):
    client, db, company_id = api
    a1 = _customer(db, company_id, "ZZT DOUBLE", level=1)
    res = client.post(BASE, json=_dealer_body([a1], tiers=[
        {"period_start": "2026-01-01", "threshold": 75000, "rate": 6, "additional_rate": 1},
        {"period_start": "2026-01-01", "threshold": 75000, "rate": 1, "is_additional": True},
    ]))
    assert res.status_code == 422, res.text
    assert "remove the row" in res.text


def test_statement_rate_cell_carries_the_additional():
    from app.services.sales.commission_statement_xlsx import _reached_rate

    p = {"tier_rates": [{"label": "A/C I", "rate": 6.0}], "tier_additional": {"kind": "pct", "value": 1.0}}
    assert _reached_rate(p, "amount") == "A/C I 6.00% + 1.00%"
    p["tier_additional"] = {"kind": "amount", "value": 500.0}
    assert _reached_rate(p, "amount") == "A/C I 6.00% + RM 500.00"
    assert _reached_rate({"tier_rates": [{"label": None, "rate": 5.0}], "tier_additional": None}, "amount") == "5.00%"
    q = {"tier_rates": [{"label": None, "rate": 1.5}], "tier_additional": {"kind": "pct", "value": 0.5}}
    assert _reached_rate(q, "quantity") == "1.50 RM/unit + RM 0.50/unit"


def _script():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "fold_tier_additionals", Path(__file__).resolve().parents[1] / "scripts" / "fold_tier_additionals.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


def test_ladder_drops_beaufort_shape_names_the_fix():
    # Owner ruling 5 Nov 12:10: no carry-up. 50,000 at 3% + "+ Additional 5% from 50,000", then
    # 60,000 at 4% and 80,000 at 5%: today they pay 8 / 9 / 10 %, after the fold 8 / 4 / 5 %.
    script = _script()
    rows = [_row(50000, 3), _row(60000, 4), _row(80000, 5), _row(50000, 5, additional=True)]
    lines = script.ladder_drops(rows, fold_additionals(rows), False, {})
    assert lines == [
        "2026-01-01: tier 60,000 pays 4% vs 8% at 50,000 -> to keep today's pay "
        "set Additional 5% on 60,000 and 80,000"
    ]


def test_ladder_drops_none_when_every_tier_has_its_own():
    script = _script()
    rows = [
        _row(60000, 5), _row(75000, 6), _row(85000, 7),
        _row(60000, 1, additional=True), _row(75000, 1, additional=True), _row(85000, 1, additional=True),
    ]
    assert script.ladder_drops(rows, fold_additionals(rows), False, {}) == []


def test_ladder_drops_per_account_names_the_account():
    # CE is paid only from 100,000, so it has no ladder to drop: only A/C I is named.
    script = _script()
    rows = [
        _row(80000, 0, accounts={A1: 4}), _row(100000, 0, accounts={A1: 5, CE: 3}),
        _row(80000, 0, additional=True, accounts={A1: 5}),
    ]
    lines = script.ladder_drops(rows, fold_additionals(rows), False, {A1: "300-B001"})
    assert lines == [
        "2026-01-01: 300-B001 tier 100,000 pays 5% vs 9% at 80,000 -> to keep today's pay "
        "set Additional 5% on 100,000"
    ]


def test_ladder_drops_advice_leaves_out_rows_that_still_stack():
    # 2% from 55,000 sits on no tier, so it stays and keeps stacking on 60,000: the tier needs 5%
    # of its own, not 7% (review round 2). Checked against the engine: same pay as today.
    script = _script()
    rows = [
        _row(50000, 3), _row(60000, 4),
        _row(50000, 5, additional=True), _row(55000, 2, additional=True),
    ]
    fold = fold_additionals(rows)
    lines = script.ladder_drops(rows, fold, False, {})
    assert lines == [
        "2026-01-01: tier 60,000 pays 6% vs 8% at 50,000 -> to keep today's pay set Additional 5% on 60,000"
    ]
    achieved = {None: D("60000")}
    today = _pay([tier(50000, 3), tier(60000, 4), tier(50000, 5, additional=True), tier(55000, 2, additional=True)], achieved)
    fixed = _pay([tier(50000, 3, add=5), tier(60000, 4, add=5), tier(55000, 2, additional=True)], achieved)
    assert today.commission == fixed.commission == D("6600.00")


def test_ladder_drops_equal_rates_are_not_a_drop():
    script = _script()
    rows = [_row(50000, 3), _row(60000, 5), _row(50000, 2, additional=True)]
    assert script.ladder_drops(rows, fold_additionals(rows), False, {}) == []


def test_ladder_drops_quantity_target_says_rm_per_unit():
    script = _script()
    rows = [_row(100, 1), _row(200, "1.5"), _row(100, 1, additional=True)]
    assert script.ladder_drops(rows, fold_additionals(rows), False, {}, " RM/unit") == [
        "2026-01-01: tier 200 pays 1.5 RM/unit vs 2 RM/unit at 100 -> to keep today's pay "
        "set Additional 1 RM/unit on 200"
    ]


def test_api_still_saves_a_bonus_tier_beside_a_legacy_row(api):
    # A Bonus beside a legacy row was valid before this lane; the fold leaves it, so saving works.
    client, db, company_id = api
    a1 = _customer(db, company_id, "ZZT BONUS AND ROW", level=1)
    res = client.post(BASE, json=_dealer_body([a1], tiers=[
        {"period_start": "2026-01-01", "threshold": 75000, "rate": 6, "bonus_amount": 300},
        {"period_start": "2026-01-01", "threshold": 75000, "rate": 1, "is_additional": True},
    ]))
    assert res.status_code == 201, res.text
