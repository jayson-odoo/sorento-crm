"""Targets stack, each account earns its own share, no single "Pays to" (lane
TARGET-PER-ACCOUNT-PAYOUT, owner rulings 8 Nov). Plan:
documentation/plans/sales/PLAN-target-per-account-payout-08nov.md.

Synthetic data shaped like the owner's DELUXE case: three accounts on one combined yearly target
with a rate per account, and one account's own ladder target beside it. Today is 20 Oct 2026
(the S1 fixtures).
"""
from __future__ import annotations

from datetime import date

from .test_dealer_targets_api import RATIOS, _customer, _dealer_body, _period, _product_id, _sale
from .test_sales_targets_s1 import BASE, _uid, api, world  # noqa: F401  (fixtures)


def _yearly(accounts, tiers, **extra):
    return _dealer_body(
        accounts, name="ZZT yearly", split_every=None, split_unit=None, tiers_per_period=False,
        tiers=tiers, **extra,
    )


def _deluxe(client, db, company_id):
    pid = _product_id(db, company_id)
    a1 = _customer(db, company_id, "ZZT DLX A/C I", level=1)
    a2 = _customer(db, company_id, "ZZT DLX A/C II", level=2)
    a3 = _customer(db, company_id, "ZZT DLX A/C III", level=3)
    for acc, amount in ((a1, "663071.20"), (a2, "583984.44"), (a3, "37013.06")):
        _sale(db, company_id, acc, amount, date(2026, 3, 1), product_id=pid)
    combined = client.post(BASE, json=_yearly([a1, a2, a3], [
        {"threshold": 1000000, "rate": 0, "account_rates": [
            {"customer_id": a1.id, "rate": 1.5}, {"customer_id": a2.id, "rate": 1},
            {"customer_id": a3.id, "rate": 1.5},
        ]},
    ]))
    assert combined.status_code == 201, combined.text
    return (a1, a2, a3), combined.json()


def test_each_account_earns_its_own_share_of_a_combined_target(api):
    client, db, company_id = api
    (a1, a2, a3), combined = _deluxe(client, db, company_id)
    period = combined["periods"][0]
    assert period["commission_earned"] == 16341.11
    shares = {a["customer_id"]: a["commission_earned"] for a in period["accounts"]}
    assert shares == {a1.id: 9946.07, a2.id: 5839.84, a3.id: 555.20}
    assert round(sum(shares.values()), 2) == period["commission_earned"] + (period["bonus_earned"] or 0)


def test_a_combined_target_and_an_account_s_own_target_stack(api):
    """Owner 8 Nov: TGT-000025 (combined) pays ON TOP of TGT-000026 (A/C I's own ladder)."""
    client, db, company_id = api
    (a1, _a2, _a3), combined = _deluxe(client, db, company_id)
    own = client.post(BASE, json=_yearly([a1], [
        {"threshold": 650000, "rate": 4}, {"threshold": 850000, "rate": 6}, {"threshold": 1200000, "rate": 8},
    ]))
    assert own.status_code == 201, own.text
    # A/C I sold 663,071.20: its own Tier 1 (4%) pays in full, beside the combined target's share.
    assert own.json()["periods"][0]["commission_earned"] == 26522.85
    again = client.get(f"{BASE}/{combined['id']}").json()
    assert again["periods"][0]["commission_earned"] == 16341.11


def test_no_replaced_by_and_no_pays_to_anywhere(api):
    client, db, company_id = api
    (a1, _a2, _a3), combined = _deluxe(client, db, company_id)
    assert "replaced_by" not in combined and "payout_account" not in combined
    assert all("replaced" not in p for p in combined["periods"])
    for field, value in (("replaced_by_target_id", combined["id"]), ("payout_customer_id", a1.id)):
        res = client.post(BASE, json=_yearly([a1], [{"threshold": 1, "rate": 1}], **{field: value}))
        assert res.status_code == 422, (field, res.text)
        res = client.patch(f"{BASE}/{combined['id']}", json={field: value})
        assert res.status_code == 422, (field, res.text)
    rows = client.get(BASE, params={"subject": "dealer", "all": "true"}).json()["rows"]
    row = next(r for r in rows if r["target_id"] == combined["id"])
    assert "payout_label" not in row or row["payout_label"] is None


def test_no_commission_set_gives_no_account_share(api):
    client, db, company_id = api
    a = _customer(db, company_id, "ZZT NOCOM")
    res = client.post(BASE, json=_yearly([a], []))
    assert res.status_code == 201, res.text
    assert [x["commission_earned"] for x in res.json()["periods"][0]["accounts"]] == [None]


def test_points_target_shows_achieved_points_at_the_engine_s_ratio(api):
    """Owner 8 Nov (Q6 a): Points beside Sales (RM), at the ratio in force on the period's last day."""
    client, db, company_id = api
    pid = _product_id(db, company_id)
    a1 = _customer(db, company_id, "ZZT PTS A/C I", level=1)
    a3 = _customer(db, company_id, "ZZT PTS A/C III", level=3)
    _sale(db, company_id, a1, 60000, date(2026, 8, 1), product_id=pid)
    _sale(db, company_id, a3, 6000, date(2026, 8, 20), product_id=pid)
    # The ratio changes mid-quarter: the period's last day (30 Sep) reads 1.20.
    for effective_from, ratio in (("2026-01-01", 1.00), ("2026-08-15", 1.20)):
        assert client.post(RATIOS, json={"effective_from": effective_from, "rm_per_point": ratio}).status_code in (200, 201)
    res = client.post(BASE, json=_dealer_body([a1, a3], threshold_unit="points", tiers=[
        {"period_start": "2026-07-01", "threshold": 30000, "rate": 2},
    ]))
    assert res.status_code == 201, res.text
    q3 = _period(res.json(), "2026-07-01")
    assert q3["achieved_points"] == 55000.0
    assert {a["customer_id"]: a["achieved_points"] for a in q3["accounts"]} == {a1.id: 50000.0, a3.id: 5000.0}
    # Not a points target: no points.
    plain = client.post(BASE, json=_dealer_body([a1], tiers=[{"period_start": "2026-07-01", "threshold": 1, "rate": 1}]))
    assert _period(plain.json(), "2026-07-01")["achieved_points"] is None


def test_points_target_with_no_ratio_has_no_points(api):
    client, db, company_id = api
    a = _customer(db, company_id, "ZZT PTS NORATIO")
    res = client.post(BASE, json=_dealer_body([a], threshold_unit="points", start_date="2031-01-01",
                                              end_date="2031-12-31", tiers=[]))
    assert res.status_code == 201, res.text
    assert all(p["achieved_points"] is None for p in res.json()["periods"])


def test_duplicate_keeps_accounts_and_needs_no_payee(api):
    client, db, company_id = api
    (_a1, _a2, _a3), combined = _deluxe(client, db, company_id)
    res = client.post(f"{BASE}/{combined['id']}/duplicate")
    assert res.status_code in (200, 201), res.text
    assert len(res.json()["accounts"]) == 3
