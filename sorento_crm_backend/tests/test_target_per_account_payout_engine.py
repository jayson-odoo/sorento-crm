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


def tier(threshold, rate=0, *, accounts=None, bonus=None, additional_rate=None, additional=False, bonuses=None):
    return Tier(
        from_pct=None,
        rate=D(str(rate)),
        bonus_amount=None if bonus is None else D(str(bonus)),
        threshold=D(str(threshold)),
        is_additional=additional,
        account_rates=None if accounts is None else {k: D(str(v)) for k, v in accounts.items()},
        additional_rate=None if additional_rate is None else D(str(additional_rate)),
        account_bonuses=None if bonuses is None else {k: D(str(v)) for k, v in bonuses.items()},
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


def test_rm_additional_set_per_account_pays_each_its_own():
    """Owner 8 Nov (Q3): the fixed RM Additional is set per account, like the rate."""
    out = payout_for(
        "retroactive", [tier(1000000, accounts={A: 1, B: 1, C: 1}, bonuses={A: 500, B: 300})],
        D("0"), SALES, threshold_unit="amount",
    )
    assert out.bonus == D("800.00")
    assert out.by_account[A] == D("6630.71") + D("500")
    assert out.by_account[B] == D("5839.84") + D("300")
    assert out.by_account[C] == D("370.13")
    assert _total(out) == out.commission + out.bonus


def test_one_rm_additional_for_all_pays_each_counted_account():
    """As a one-for-all rate pays each account: every counted account gets the RM Additional,
    an account with no sales in the period included."""
    sales = {**SALES, "acc-d": D("0")}
    out = payout_for("retroactive", [tier(1000000, 1, bonus=100)], D("0"), sales, threshold_unit="amount")
    assert out.bonus == D("400.00")
    assert out.by_account["acc-d"] == D("100.00")
    assert _total(out) == out.commission + out.bonus


def test_rm_additional_on_a_single_bucket_pays_once():
    out = payout_for("retroactive", [tier(1000, 1, bonus=100)], D("0"), {None: D("5000")}, threshold_unit="amount")
    assert out.bonus == D("100.00") and out.by_account == {None: D("150.00")}


def test_no_rm_additional_below_the_tier():
    out = payout_for("retroactive", [tier(9000000, 1, bonuses={A: 500})], D("0"), SALES, threshold_unit="amount")
    assert out.bonus == D("0") and _total(out) == D("0")


def test_marginal_each_account_its_own_rate_on_its_part_of_each_slice():
    """The crew-note example: tiers 1M (A 1%, B 2%) and 2M (A 2%, B 3%); A 1.5M, B 1.0M,
    T 2.5M. Slice 1M-2M is 40% of T, slice 2M-2.5M 20%: A 6,000 + 6,000, B 8,000 + 6,000."""
    out = payout_for(
        "marginal",
        [tier(1000000, accounts={A: 1, B: 2}), tier(2000000, accounts={A: 2, B: 3})],
        D("0"), {A: D("1500000"), B: D("1000000")}, threshold_unit="amount",
    )
    assert out.by_account == {A: D("12000.00"), B: D("14000.00")}
    assert out.commission == D("26000.00")


def test_marginal_one_rate_for_all_on_one_bucket_is_unchanged():
    out = payout_for("marginal", [tier(500000, 1), tier(1000000, 2)], D("0"), {None: D("1284068.70")},
                     threshold_unit="amount")
    # 1% x 500,000 + 2% x 284,068.70 = 5,000 + 5,681.374
    assert out.commission == D("10681.37") and out.by_account == {None: D("10681.37")}


def test_marginal_one_rate_for_all_splits_by_each_account_s_part():
    out = payout_for("marginal", [tier(500000, 1), tier(1000000, 2)], D("0"), SALES, threshold_unit="amount")
    assert _total(out) == out.commission
    assert out.by_account[A] > out.by_account[B] > out.by_account[C]


def test_single_bucket_target_has_one_share():
    out = payout_for("retroactive", [tier(1000, 2)], D("0"), {None: D("5000")}, threshold_unit="amount")
    assert out.by_account == {None: D("100.00")}


def test_no_commission_method_has_no_shares():
    out = payout_for("none", [tier(1000, 2)], D("0"), SALES, threshold_unit="amount")
    assert out.by_account == {}
