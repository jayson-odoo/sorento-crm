"""Dealer targets import, round 10 (lane SALES-TARGET-DEALER, owner rulings 20 Oct 08:55).

Masked shapes from the real files:
1. MCH 82-84: one dealer writes "A/C I" on all three rows of one target. The owner: all three
   are A/C I. Rows that land on one CRM customer are read as that one account when their figures
   agree; when they give the account different rates, the conflict is reported, never guessed.
2. SRT 57-59: a rate cell names "A/C 9", an account no row of the dealer has (the owner: it is
   A/C I). Never hard-coded: the label waits on a pick of one of the dealer's own accounts in
   the import dialog, the same way a name waits on a customer pick.
3. SRT 15-17: a Tier 4 Incentive cell holds "A/C I- <amount>" where a rate belongs. An amount no
   larger than the reader's rate limit of the tier's threshold is a fixed bonus on that tier,
   paid to the account it names; a larger one stays "not a rate".
Masked names, invented figures.
"""
from __future__ import annotations

import json
from decimal import Decimal

from .test_dealer_targets_import_gate6 import _bytes, _customer
from .test_sales_targets_s1 import BASE, api, world  # noqa: F401  (fixtures)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _post(client, db, data, *, picks=None, dry_run=True):
    files = {"file": ("t.xlsx", data, XLSX)}
    form = {"picks": json.dumps(picks)} if picks else None
    db.autoflush = False
    try:
        return client.post(
            f"{BASE}/import", params={"dry_run": str(dry_run).lower(), "year": 2026}, files=files, data=form
        ).json()
    finally:
        db.autoflush = True


def _tiers(db, target_no):
    from app.models.sales import SalesTarget, SalesTargetAccount, SalesTargetCommissionTier, SalesTargetTierRate

    target = db.query(SalesTarget).filter(SalesTarget.target_no == target_no).one()
    tiers = (
        db.query(SalesTargetCommissionTier)
        .filter(SalesTargetCommissionTier.target_id == target.id)
        .order_by(SalesTargetCommissionTier.threshold)
        .all()
    )
    rates = {
        t.id: {r.customer_id: r.rate for r in db.query(SalesTargetTierRate).filter(SalesTargetTierRate.tier_id == t.id)}
        for t in tiers
    }
    accounts = [a.customer_id for a in db.query(SalesTargetAccount).filter(SalesTargetAccount.target_id == target.id)]
    return target, tiers, rates, accounts


# --- 1. MCH 82-84: three rows on one ledger ------------------------------------------------


def _three_a_c_i(rates=None):
    def fill(ws):
        ws["A1"], ws["B1"], ws["C1"] = "DEALER NAME", "ACCOUNT", "Q1"
        ws["A2"] = "ZULU HOME SDN BHD"
        ws.merge_cells("A2:A4")
        if rates is None:
            ws["C2"] = "100,000 - 4%"
            ws.merge_cells("C2:C4")
        for r in (2, 3, 4):
            ws[f"B{r}"] = "A/C I"

    def fill_rates(ws):
        ws["A1"], ws["B1"] = "DEALER NAME", "ACCOUNT"
        ws["C1"] = "Q1"
        ws.merge_cells("C1:D1")
        ws["C2"], ws["D2"] = "Tier 1", "Tier 1 Incentive"
        ws.merge_cells("A1:A2")
        ws.merge_cells("B1:B2")
        ws["A3"] = "ZULU HOME SDN BHD"
        ws.merge_cells("A3:A5")
        ws["C3"] = 100000
        ws.merge_cells("C3:C5")
        for r, rate in zip((3, 4, 5), rates):
            ws[f"B{r}"] = "A/C I"
            ws[f"D{r}"] = rate

    return _bytes(fill if rates is None else fill_rates)


def test_three_rows_on_one_ledger_with_one_figure_are_that_one_account(api):
    client, db, company_id = api
    ledger = _customer(db, company_id, "ZULU HOME SDN BHD [A/C I]", 1)
    out = _post(client, db, _three_a_c_i())
    rows = out["rows"]
    assert [r["status"] for r in rows] == ["mapped"] * 3, rows
    assert all("rows 2, 3 and 4 are one CRM customer: read as one account" in r["warnings"] for r in rows), rows
    assert out["summary"]["targets_new"] == 1, out["summary"]

    done = _post(client, db, _three_a_c_i(), dry_run=False)
    target_no = done["rows"][0]["target_nos"][0]
    _target, tiers, _rates, accounts = _tiers(db, target_no)
    assert accounts == [ledger.id]
    assert [(t.threshold, t.rate) for t in tiers] == [(Decimal("100000"), Decimal("4"))]


def test_three_rows_on_one_ledger_with_the_same_rate_each_are_one_account(api):
    client, db, company_id = api
    _customer(db, company_id, "ZULU HOME SDN BHD [A/C I]", 1)
    rows = _post(client, db, _three_a_c_i(rates=["A/C I- 2%", "A/C I- 2%", "A/C I- 2%"]))["rows"]
    assert [r["status"] for r in rows] == ["mapped"] * 3, [r["reason"] for r in rows]


def test_three_rows_on_one_ledger_with_different_rates_report_the_conflict(api):
    client, db, company_id = api
    _customer(db, company_id, "ZULU HOME SDN BHD [A/C I]", 1)
    rows = _post(client, db, _three_a_c_i(rates=[0.02, 0.03, 0.02]))["rows"]
    assert [r["status"] for r in rows] == ["not_representable"] * 3, rows
    reason = rows[0]["reason"]
    assert "rows 3, 4 and 5 are one CRM customer but give it different rates" in reason, reason
    assert "2%" in reason and "3%" in reason, reason


# --- 2. SRT 57-59: an account label no row has waits on an account pick ------------------------


def _unknown_label(label="A/C 9- 2%"):
    def fill(ws):
        ws.title = "Sorento"
        ws["A1"], ws["B1"], ws["C1"] = "DEALER NAME", "ACCOUNT", "Q1"
        ws.merge_cells("A1:A2")
        ws.merge_cells("B1:B2")
        ws.merge_cells("C1:D1")
        ws["C2"], ws["D2"] = "Tier 1", "Tier 1 Incentive"
        ws["A3"] = "ECHO HOME SDN BHD"
        ws.merge_cells("A3:A4")
        ws["B3"], ws["B4"] = "A/C I", "A/C III"
        ws["C3"] = 100000
        ws.merge_cells("C3:C4")
        ws["D3"] = label
        ws.merge_cells("D3:D4")

    return _bytes(fill)


def _echo(db, company_id):
    return (
        _customer(db, company_id, "ECHO HOME SDN BHD [A/C I]", 1),
        _customer(db, company_id, "ECHO HOME SDN BHD [A/C III]", 3),
    )


def test_a_rate_naming_an_account_no_row_has_waits_on_an_account_pick(api):
    client, db, company_id = api
    _echo(db, company_id)
    rows = _post(client, db, _unknown_label())["rows"]
    assert [r["status"] for r in rows] == ["needs_pick"] * 2, rows
    pick = rows[0]["account_pick"]
    assert pick == {"pick_key": "Sorento!3~A/C 9", "label": "A/C 9", "choices": ["A/C I", "A/C III"]}, pick
    assert rows[1]["account_pick"] == pick
    assert '"A/C 9"' in rows[0]["reason"] and "pick the account it means" in rows[0]["reason"], rows[0]["reason"]


def test_the_picked_account_takes_the_rate(api):
    client, db, company_id = api
    a1, _a3 = _echo(db, company_id)
    picks = {"Sorento!3~A/C 9": "A/C I"}
    rows = _post(client, db, _unknown_label(), picks=picks)["rows"]
    assert [r["status"] for r in rows] == ["mapped"] * 2, [r["reason"] for r in rows]
    assert all(r["account_pick"] is None for r in rows)

    done = _post(client, db, _unknown_label(), picks=picks, dry_run=False)
    _target, tiers, rates, _accounts = _tiers(db, done["rows"][0]["target_nos"][0])
    assert len(tiers) == 1
    assert rates[tiers[0].id] == {a1.id: Decimal("2")}


def test_a_pick_that_is_not_an_account_of_the_dealer_still_waits(api):
    client, db, company_id = api
    _echo(db, company_id)
    rows = _post(client, db, _unknown_label(), picks={"Sorento!3~A/C 9": "A/C V"})["rows"]
    assert [r["status"] for r in rows] == ["needs_pick"] * 2, rows
    assert rows[0]["account_pick"]["label"] == "A/C 9"


def test_a_digit_account_is_never_read_as_its_roman_numeral_on_its_own(api):
    client, db, company_id = api
    _echo(db, company_id)
    rows = _post(client, db, _unknown_label("A/C 1- 2%"))["rows"]
    assert [r["status"] for r in rows] == ["needs_pick"] * 2, rows
    assert rows[0]["account_pick"]["label"] == "A/C 1"


def test_skipping_a_row_of_an_account_pick_skips_it(api):
    client, db, company_id = api
    _echo(db, company_id)
    rows = _post(client, db, _unknown_label(), picks={"Sorento!3": "skip"})["rows"]
    assert rows[0]["status"] == "skipped", rows[0]


# --- 3. SRT 15-17: an amount in an incentive column -------------------------------------------


def _bonus(cell, threshold=300000):
    def fill(ws):
        ws["A1"], ws["B1"], ws["C1"] = "DEALER NAME", "ACCOUNT", "Q1"
        ws.merge_cells("A1:A2")
        ws.merge_cells("B1:B2")
        ws.merge_cells("C1:F1")
        ws["C2"], ws["D2"], ws["E2"], ws["F2"] = "Tier 1", "Tier 1 Incentive", "Tier 4", "Tier 4 Incentive"
        ws["A3"], ws["B3"] = "FOXTROT HOME SDN BHD", "A/C I"
        ws["C3"], ws["D3"] = 100000, 0.02
        ws["E3"], ws["F3"] = threshold, cell

    return _bytes(fill)


def test_an_account_and_an_amount_in_an_incentive_column_is_a_bonus_on_that_tier(api):
    client, db, company_id = api
    ledger = _customer(db, company_id, "FOXTROT HOME SDN BHD [A/C I]", 1)
    rows = _post(client, db, _bonus("A/C I- 15,000"))["rows"]
    assert rows[0]["status"] == "mapped", rows[0]["reason"]

    done = _post(client, db, _bonus("A/C I- 15,000"), dry_run=False)
    target, tiers, _rates, _accounts = _tiers(db, done["rows"][0]["target_nos"][0])
    assert [(t.threshold, t.rate, t.bonus_amount) for t in tiers] == [
        (Decimal("100000"), Decimal("2"), None),
        (Decimal("300000"), Decimal("0"), Decimal("15000")),
    ]
    assert target.payout_customer_id == ledger.id


def test_an_amount_past_the_rate_limit_of_its_threshold_is_not_a_bonus(api):
    client, db, company_id = api
    _customer(db, company_id, "FOXTROT HOME SDN BHD [A/C I]", 1)
    rows = _post(client, db, _bonus("A/C I- 300,000"))["rows"]
    assert rows[0]["status"] == "not_representable", rows[0]
    assert "is not a rate" in rows[0]["reason"], rows[0]["reason"]
    assert "100% of the threshold 300,000" in rows[0]["reason"], rows[0]["reason"]


def test_an_amount_with_no_account_is_still_not_a_rate(api):
    client, db, company_id = api
    _customer(db, company_id, "FOXTROT HOME SDN BHD [A/C I]", 1)
    rows = _post(client, db, _bonus("15,000"))["rows"]
    assert rows[0]["status"] == "not_representable", rows[0]
    assert "is not a rate" in rows[0]["reason"], rows[0]["reason"]
