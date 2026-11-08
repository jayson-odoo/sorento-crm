"""Each account earns its own share (lane TARGET-PER-ACCOUNT-PAYOUT, owner rulings 8 Nov).

Pure: no database. `payout_for` returns, beside the period's total, each account's share
(`Payout.by_account`): account sales x that account's rate at the tier the COMBINED total
reached. The shares add up to the period's commission + bonus to the sen, whatever the method.

Synthetic figures shaped like the owner's DELUXE case (three accounts, per-account rates, one
combined tier): 663,071.20 x 1.5% + 583,984.44 x 1% + 37,013.06 x 1.5% = 9,946.07 + 5,839.84 +
555.20 = 16,341.11.
"""
from decimal import Decimal as D

from app.services.sales.commission_service import Tier, payout_for

A, B, C = "acc-a", "acc-b", "acc-c"


def tier(threshold, rate=0, *, accounts=None, bonus=None, additional_rate=None, additional=False):
    return Tier(
        from_pct=None,
        rate=D(str(rate)),
        bonus_amount=None if bonus is None else D(str(bonus)),
        threshold=D(str(threshold)),
        is_additional=additional,
        account_rates=None if accounts is None else {k: D(str(v)) for k, v in accounts.items()},
        additional_rate=None if additional_rate is None else D(str(additional_rate)),
    )


SALES = {A: D("663071.20"), B: D("583984.44"), C: D("37013.06")}


def _total(out):
    return sum(out.by_account.values(), D("0"))


def test_retroactive_per_account_rates_each_account_its_own_share():
    out = payout_for(
        "retroactive",
        [tier(1000000, accounts={A: "1.5", B: 1, C: "1.5"}), tier(2000000, accounts={A: 2, B: 2, C: 2})],
        D("0"), SALES, threshold_unit="amount",
    )
    assert out.commission == D("16341.11")
    assert out.by_account == {A: D("9946.07"), B: D("5839.84"), C: D("555.20")}


def test_below_the_first_tier_every_account_earns_zero():
    out = payout_for("retroactive", [tier(2000000, accounts={A: 2, B: 2})], D("0"), SALES, threshold_unit="amount")
    assert out.commission == D("0")
    assert all(v == D("0") for v in out.by_account.values())


def test_plain_rate_pays_each_account_on_its_own_sales():
    out = payout_for("retroactive", [tier(1000000, 2)], D("0"), SALES, threshold_unit="amount")
    assert out.by_account == {A: D("13261.42"), B: D("11679.69"), C: D("740.26")}
    assert _total(out) == out.commission


def test_an_account_the_tier_does_not_name_earns_zero():
    out = payout_for("retroactive", [tier(1000000, accounts={A: 2})], D("0"), SALES, threshold_unit="amount")
    assert out.by_account[A] == D("13261.42")
    assert out.by_account.get(B, D("0")) == D("0")
    assert out.by_account.get(C, D("0")) == D("0")
    assert _total(out) == out.commission


def test_percentage_additional_is_per_account_too():
    out = payout_for(
        "retroactive", [tier(1000000, accounts={A: 1, B: 1, C: 1}, additional_rate="0.5")],
        D("0"), SALES, threshold_unit="amount",
    )
    # 1% + 0.5% Additional, each line rounded per account then added.
    assert out.by_account[A] == D("6630.71") + D("3315.36")
    assert _total(out) == out.commission


def test_rm_additional_bonus_splits_pro_rata_and_adds_up():
    out = payout_for(
        "retroactive", [tier(1000000, accounts={A: 1, B: 1, C: 1}, bonus=1000)],
        D("0"), SALES, threshold_unit="amount",
    )
    assert out.bonus == D("1000.00")
    assert _total(out) == out.commission + out.bonus
    # The share follows the account's sales: A sold most, C least.
    assert out.by_account[A] > out.by_account[B] > out.by_account[C]


def test_marginal_splits_pro_rata_and_adds_up_to_the_sen():
    out = payout_for(
        "marginal", [tier(500000, 1), tier(1000000, 2)], D("0"), SALES, threshold_unit="amount",
    )
    assert out.commission > 0
    assert _total(out) == out.commission
    assert out.by_account[A] > out.by_account[B] > out.by_account[C]


def test_single_bucket_target_has_one_share():
    out = payout_for("retroactive", [tier(1000, 2)], D("0"), {None: D("5000")}, threshold_unit="amount")
    assert out.by_account == {None: D("100.00")}


def test_no_commission_method_has_no_shares():
    out = payout_for("none", [tier(1000, 2)], D("0"), SALES, threshold_unit="amount")
    assert out.by_account == {}
