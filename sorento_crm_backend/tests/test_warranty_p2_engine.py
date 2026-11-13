"""AFTER-SALES-P2 red tests: the warranty engine (UAC E1-E8) and kind suggestion (K1-K3).

Engine contract the coder implements, module `app.services.warranty_service` (names as unmerged #163):

    warranty_today() -> date                      # Malaysian date; always read via the module attribute
    add_months(start: date, months: int) -> date  # clamps to the month's last day
    policy_in_force(db, purchase_date, *, company_id) -> WarrantyPolicy | None
    resolve(db, *, kind_id: str | None, purchase_date: date | None,
            defect_type_id: str | None = None, company_id: str) -> list[WarrantyVerdict]
    rank_kind_matches(db, *, product_code=None, category_code=None, product_name=None,
                      extra_rules=()) -> list[match]       # match has .kind, .rule, sorted best first
    resolve_kind_match(db, *, product_code=None, category_code=None, product_name=None) -> match | None
    resolve_kind(db, *, product_code=None, category_code=None, product_name=None) -> WarrantyProductKind | None
    KIND_RULE_MATCH_TYPES = ("series", "model_list", "category", "code_prefix")
    KIND_RULE_SPECIFICITY = ("model_list", "code_prefix", "series", "category")   # narrowest first

    WarrantyVerdict fields: part_name, verdict, expiry, reason, is_lifetime, installation_included,
    policy_version (and policy_id, kind_id, term_id). Verdict values: covered, expired,
    defect_not_covered, no_term, unknown. "Today" for the judgement is warranty_today().

Reason texts pinned here: "N years from dd/mm/yyyy" (whole years), "N months from dd/mm/yyyy" (otherwise),
"Lifetime cover", "No policy in force on dd/mm/yyyy", "Purchase date not entered", "No warranty rule for this product yet",
"Defect not stated".  Verdict order inside one line: the terms' sort order, then part name (the term table
has no sort column unless the coder adds one; ties fall to part name).  A line with a kind but no purchase
date gets one `unknown` per term of the policy in force today (so the card can name the parts).
"""
from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone

import pytest

from ._warranty_p2_support import (
    TODAY,
    BA,
    CB,
    WC,
    defect,
    dmy,
    env,  # noqa: F401
    kind_by_code,
    make_company,
    make_kind,
    make_policy,
    make_rule,
    make_term,
    seed_v15,
    today,  # noqa: F401
)
from ._pg_fixture import unique_code


def svc():
    from app.services import warranty_service

    return warranty_service


def run(env, *, kind, purchase, defect_id=None, company_id=None):
    return svc().resolve(
        env.db,
        kind_id=kind.id if kind is not None else None,
        purchase_date=purchase,
        defect_type_id=defect_id,
        company_id=company_id or env.company_id,
    )


def one_term(env, *, months=None, lifetime=False, defects=None, purchase=date(2020, 3, 15), part="Body"):
    kind = make_kind(env)
    policy = make_policy(env)
    make_term(env, policy, kind, part, months=months, lifetime=lifetime, defects=defects)
    return kind, policy


# ---------------------------------------------------------------- E4 dates


@pytest.mark.parametrize(
    "start,months,expected",
    [
        (date(2024, 1, 31), 1, date(2024, 2, 29)),
        (date(2023, 1, 31), 1, date(2023, 2, 28)),
        (date(2020, 3, 15), 60, date(2025, 3, 15)),
        (date(2024, 8, 31), 6, date(2025, 2, 28)),
        (date(2020, 2, 29), 12, date(2021, 2, 28)),
        (date(2024, 5, 31), 1, date(2024, 6, 30)),
    ],
)
def test_e4_add_months_clamps_to_the_last_day_and_never_rolls_forward(start, months, expected):
    assert svc().add_months(start, months) == expected


def test_e4_the_expiry_day_is_covered_and_the_day_after_is_expired(env, monkeypatch):
    kind, _ = one_term(env, months=24)
    expiry = date(2022, 3, 15)
    for day, want in ((expiry, "covered"), (expiry + timedelta(days=1), "expired")):
        monkeypatch.setattr(svc(), "warranty_today", lambda d=day: d)
        (v,) = run(env, kind=kind, purchase=date(2020, 3, 15))
        assert v.verdict == want
        assert v.expiry == expiry


def test_e4_a_claim_on_the_purchase_date_is_covered(env, monkeypatch):
    kind, _ = one_term(env, months=12)
    monkeypatch.setattr(svc(), "warranty_today", lambda: date(2020, 3, 15))
    assert run(env, kind=kind, purchase=date(2020, 3, 15))[0].verdict == "covered"


def test_e4_lifetime_is_covered_with_no_expiry(env, today):
    kind, _ = one_term(env, lifetime=True)
    (v,) = run(env, kind=kind, purchase=date(2001, 5, 5))
    assert (v.verdict, v.expiry, v.is_lifetime) == ("covered", None, True)


def test_e4_month_end_purchase_expiry_is_clamped_in_the_verdict(env, today):
    kind, _ = one_term(env, months=1)
    (v,) = run(env, kind=kind, purchase=date(2024, 1, 31))
    assert v.expiry == date(2024, 2, 29)
    assert v.verdict == "expired"


# ---------------------------------------------------------------- E1 / E2 / E3


def test_e1_one_verdict_per_term_in_part_name_order(env, today):
    kind = make_kind(env)
    policy = make_policy(env)
    for part, months in (("Seat Cover", 24), ("Ceramic Body", None), ("Flushing Fittings", 60)):
        make_term(env, policy, kind, part, months=months, lifetime=months is None)
    verdicts = run(env, kind=kind, purchase=date(2020, 3, 15))
    assert [v.part_name for v in verdicts] == ["Ceramic Body", "Flushing Fittings", "Seat Cover"]


def test_e2_the_policy_is_the_one_in_force_on_the_purchase_date_not_todays(env, today):
    kind = make_kind(env)
    old = make_policy(env, "OLD", date(2000, 1, 1), date(2019, 12, 31))
    new = make_policy(env, "NEW", date(2020, 1, 1), None)
    make_term(env, old, kind, "Body", months=240)  # long cover under the old version
    make_term(env, new, kind, "Body", lifetime=True)
    (v,) = run(env, kind=kind, purchase=date(2019, 6, 1))
    assert v.policy_version == "OLD"
    assert v.expiry == date(2039, 6, 1)
    (v2,) = run(env, kind=kind, purchase=date(2020, 1, 1))
    assert (v2.policy_version, v2.is_lifetime) == ("NEW", True)


@pytest.mark.parametrize("purchase,version", [(date(2010, 1, 1), "W"), (date(2010, 12, 31), "W")])
def test_e2_both_window_dates_are_inclusive(env, today, purchase, version):
    kind = make_kind(env)
    policy = make_policy(env, "W", date(2010, 1, 1), date(2010, 12, 31))
    make_term(env, policy, kind, "Body", months=120)
    assert run(env, kind=kind, purchase=purchase)[0].policy_version == version


def test_e2_an_open_ended_policy_holds_every_later_date(env, today):
    kind = make_kind(env)
    policy = make_policy(env, "OPEN", date(2000, 1, 1), None)
    make_term(env, policy, kind, "Body", months=12)
    assert run(env, kind=kind, purchase=date(2026, 11, 1))[0].policy_version == "OPEN"


def test_e2_no_policy_holds_the_date_gives_one_unknown_with_the_date_in_the_reason(env, today):
    kind = make_kind(env)
    policy = make_policy(env, "SHORT", date(2000, 1, 1), date(2009, 12, 31))
    make_term(env, policy, kind, "Body", months=12)
    verdicts = run(env, kind=kind, purchase=date(2015, 6, 1))
    assert len(verdicts) == 1
    assert verdicts[0].verdict == "unknown"
    assert "No policy in force on 01/06/2015" in verdicts[0].reason


def test_e2_another_companys_policy_does_not_answer(env, today):
    kind = make_kind(env)
    other = make_company(env)
    theirs = make_policy(env, "THEIRS", date(2000, 1, 1), None, company_id=other)
    make_term(env, theirs, kind, "Body", lifetime=True)
    (v,) = run(env, kind=kind, purchase=date(2020, 1, 1))
    assert v.verdict == "unknown"
    assert "No policy in force" in v.reason


def test_e2_overlapping_windows_resolve_to_the_latest_effective_from(env, today):
    kind = make_kind(env)
    a = make_policy(env, "A", date(2000, 1, 1), None)
    b = make_policy(env, "B", date(2015, 1, 1), None)
    make_term(env, a, kind, "Body", months=12)
    make_term(env, b, kind, "Body", months=24)
    assert svc().policy_in_force(env.db, date(2020, 1, 1), company_id=env.company_id).version == "B"


def test_e3_a_kind_without_a_term_in_the_policy_gives_one_no_term(env, today):
    kind = make_kind(env)
    make_policy(env)
    verdicts = run(env, kind=kind, purchase=date(2020, 3, 15))
    assert [v.verdict for v in verdicts] == ["no_term"]


def test_e3_every_verdict_is_one_of_the_five_values(env, today):
    kind = make_kind(env)
    policy = make_policy(env)
    leak = defect(env, "Leakage")
    make_term(env, policy, kind, "A", months=12)
    make_term(env, policy, kind, "B", lifetime=True, defects=[leak])
    make_term(env, policy, kind, "C", months=600, defects=[defect(env, "Rust")])
    got = {v.verdict for v in run(env, kind=kind, purchase=date(2020, 3, 15), defect_id=leak)}
    assert got <= {"covered", "expired", "defect_not_covered", "no_term", "unknown"}
    assert got == {"expired", "covered", "defect_not_covered"}


# ---------------------------------------------------------------- E5 defect scope


def test_e5_a_null_or_empty_defect_list_covers_every_defect(env, today):
    kind = make_kind(env)
    policy = make_policy(env)
    make_term(env, policy, kind, "NullList", lifetime=True, defects=None)
    make_term(env, policy, kind, "EmptyList", lifetime=True, defects=[])
    verdicts = run(env, kind=kind, purchase=date(2020, 3, 15), defect_id=defect(env, "Rust"))
    assert [v.verdict for v in verdicts] == ["covered", "covered"]
    no_defect = run(env, kind=kind, purchase=date(2020, 3, 15), defect_id=None)
    assert [v.verdict for v in no_defect] == ["covered", "covered"]


def test_e5_a_defect_in_the_list_is_judged_by_date(env, today):
    leak = defect(env, "Leakage")
    kind, _ = one_term(env, months=24, defects=[leak])
    assert run(env, kind=kind, purchase=date(2025, 1, 1), defect_id=leak)[0].verdict == "covered"
    assert run(env, kind=kind, purchase=date(2020, 1, 1), defect_id=leak)[0].verdict == "expired"


def test_e5_a_defect_outside_the_list_is_defect_not_covered(env, today):
    kind, _ = one_term(env, lifetime=True, defects=[defect(env, "Crack line")])
    (v,) = run(env, kind=kind, purchase=date(2020, 3, 15), defect_id=defect(env, "Rust"))
    assert v.verdict == "defect_not_covered"


def test_e5_no_defect_on_the_line_with_a_restricted_term_is_unknown_never_not_covered(env, today):
    kind, _ = one_term(env, lifetime=True, defects=[defect(env, "Crack line")])
    (v,) = run(env, kind=kind, purchase=date(2020, 3, 15), defect_id=None)
    assert v.verdict == "unknown"
    assert "Defect not stated" in v.reason


# ---------------------------------------------------------------- E6 missing inputs


def test_e6_no_purchase_date_gives_unknown_per_term_never_expired(env, today):
    kind = make_kind(env)
    policy = make_policy(env)
    make_term(env, policy, kind, "Manufacturing Defects", months=24)
    make_term(env, policy, kind, "PC Auto Controller", months=12)
    verdicts = run(env, kind=kind, purchase=None)
    assert [v.part_name for v in verdicts] == ["Manufacturing Defects", "PC Auto Controller"]
    assert all(v.verdict == "unknown" and "Purchase date not entered" in v.reason for v in verdicts)


def test_e6_no_kind_gives_unknown_no_warranty_rule(env, today):
    make_policy(env)
    verdicts = svc().resolve(
        env.db, kind_id=None, purchase_date=date(2020, 3, 15), defect_type_id=None, company_id=env.company_id
    )
    assert [v.verdict for v in verdicts] == ["unknown"]
    assert verdicts[0].reason == "No warranty rule for this product yet"


# ---------------------------------------------------------------- E7 verdict fields


@pytest.mark.parametrize("months,text", [(60, "5 years from 15/03/2020"), (24, "2 years from 15/03/2020"), (18, "18 months from 15/03/2020")])
def test_e7_reason_states_the_term_and_the_purchase_date(env, today, months, text):
    kind, _ = one_term(env, months=months)
    assert text in run(env, kind=kind, purchase=date(2020, 3, 15))[0].reason


def test_e7_lifetime_reason_and_fields(env, today):
    from app.models.warranty import WarrantyTerm

    kind, policy = one_term(env, lifetime=True, part="Ceramic Body")
    env.db.query(WarrantyTerm).filter(WarrantyTerm.policy_id == policy.id).update({"installation_included": True})
    env.db.flush()
    env.db.expire_all()
    (v,) = run(env, kind=kind, purchase=date(2020, 3, 15))
    assert "Lifetime cover" in v.reason
    assert (v.part_name, v.is_lifetime, v.installation_included, v.policy_version) == (
        "Ceramic Body", True, True, policy.version,
    )


def test_e7_an_expired_verdict_carries_its_expiry(env, today):
    kind, _ = one_term(env, months=60)
    (v,) = run(env, kind=kind, purchase=date(2020, 3, 15))
    assert (v.verdict, v.expiry, v.is_lifetime) == ("expired", date(2025, 3, 15), False)


# ---------------------------------------------------------------- E8 not applied


def test_e8_registration_bonus_and_installation_context_are_not_inputs(env, today):
    params = set(inspect.signature(svc().resolve).parameters)
    assert not {"registered", "installation", "installation_context", "usage", "customer_type"} & params
    from app.models.warranty import WarrantyTerm

    if hasattr(WarrantyTerm, "registration_bonus_months"):
        kind, policy = one_term(env, months=24)
        env.db.query(WarrantyTerm).filter(WarrantyTerm.policy_id == policy.id).update({"registration_bonus_months": 12})
        env.db.flush()
        env.db.expire_all()
        (v,) = run(env, kind=kind, purchase=date(2024, 6, 1))
        assert v.expiry == date(2026, 6, 1)
        assert v.verdict == "expired"


def test_warranty_today_is_the_malaysian_date():
    mytz = timezone(timedelta(hours=8))
    assert svc().warranty_today() in {datetime.now(mytz).date(), (datetime.now(mytz) - timedelta(seconds=5)).date()}


# ---------------------------------------------------------------- the card's examples through the v15 seed


def _by_part(verdicts):
    return {v.part_name: v for v in verdicts}


def test_card_example_1_water_closet_2020_leakage(env, today):
    seed_v15(env)
    wc = kind_by_code(env, "water_closet")
    got = _by_part(run(env, kind=wc, purchase=date(2020, 3, 15), defect_id=defect(env, "Leakage")))
    assert (got["Ceramic Body"].verdict, got["Ceramic Body"].is_lifetime) == ("covered", True)
    assert (got["Flushing Fittings"].verdict, got["Flushing Fittings"].expiry) == ("expired", date(2025, 3, 15))
    seat = next(v for p, v in got.items() if p.startswith("Seat Cover"))
    assert (seat.verdict, seat.expiry) == ("expired", date(2022, 3, 15))


def test_card_example_2_water_closet_2024_no_defect(env, today):
    seed_v15(env)
    got = _by_part(run(env, kind=kind_by_code(env, "water_closet"), purchase=date(2024, 5, 2)))
    assert got["Ceramic Body"].verdict == "unknown"
    assert "Defect not stated" in got["Ceramic Body"].reason
    assert (got["Flushing Fittings"].verdict, got["Flushing Fittings"].expiry) == ("covered", date(2029, 5, 2))
    seat = next(v for p, v in got.items() if p.startswith("Seat Cover"))
    assert (seat.verdict, seat.expiry) == ("expired", date(2026, 5, 2))


def test_card_example_3_steel_sink_with_leakage_is_defect_not_covered(env, today):
    seed_v15(env)
    (v,) = run(env, kind=kind_by_code(env, "kitchen_sink_ss304"), purchase=date(2010, 1, 10), defect_id=defect(env, "Leakage"))
    assert v.verdict == "defect_not_covered"
    assert "Rust" in v.reason


def test_card_example_4_booster_pump_without_a_purchase_date(env, today):
    seed_v15(env)
    verdicts = run(env, kind=kind_by_code(env, "booster_pump"), purchase=None)
    assert {v.part_name for v in verdicts} == {"Manufacturing Defects", "PC Auto Controller"}
    assert all(v.verdict == "unknown" and "Purchase date not entered" in v.reason for v in verdicts)


def test_card_example_5_mirror_cabinet_month_end_broken_holder(env, today):
    seed_v15(env)
    got = _by_part(run(env, kind=kind_by_code(env, "mirror_cabinet"), purchase=date(2024, 1, 31), defect_id=defect(env, "Broken holder")))
    assert (got["Aluminum Frame"].verdict, got["Aluminum Frame"].expiry) == ("covered", date(2034, 1, 31))
    assert (got["Hinges"].verdict, got["Hinges"].expiry) == ("covered", date(2049, 1, 31))
    assert (got["Mirror Glass"].verdict, got["Mirror Glass"].expiry) == ("expired", date(2026, 1, 31))


# ---------------------------------------------------------------- K kind suggestion


def test_k1_the_match_types_are_the_four_declared_ones():
    assert set(svc().KIND_RULE_MATCH_TYPES) == {"series", "model_list", "category", "code_prefix"}
    assert tuple(svc().KIND_RULE_SPECIFICITY) == ("model_list", "code_prefix", "series", "category")


@pytest.mark.parametrize(
    "match_type,value,query",
    [
        ("category", "SRT-WC", dict(category_code="SRT-WC")),
        ("category", "srt-wc", dict(category_code="SRT-WC")),
        ("code_prefix", "SRTWC", dict(product_code="SRTWC6020-SH-UF")),
        ("code_prefix", "srtwc", dict(product_code="SRTWC6020-SH-UF")),
        ("model_list", "CB109, CB110 ,CB111", dict(product_code="cb110")),
        ("series", "Honeycomb", dict(product_name="Honeycomb Wall Cabinet")),
    ],
)
def test_k1_each_match_type_matches_case_insensitively(env, match_type, value, query):
    kind = make_kind(env)
    make_rule(env, kind, match_type, value)
    assert svc().resolve_kind(env.db, **query).id == kind.id


@pytest.mark.parametrize(
    "match_type,value,query",
    [
        ("code_prefix", "SRTWC", dict(product_code="XSRTWC6020")),
        ("model_list", "CB11", dict(product_code="CB110")),
        ("category", "SRT-W", dict(category_code="SRT-WC")),
    ],
)
def test_k1_a_non_match_is_not_a_match(env, match_type, value, query):
    make_rule(env, make_kind(env), match_type, value)
    assert svc().resolve_kind(env.db, **query) is None


def test_k1_a_rule_matches_on_a_real_dev_product_without_a_products_row(env):
    kind = make_kind(env, "water_closet_t")
    make_rule(env, kind, "category", WC[1])
    assert svc().resolve_kind(env.db, product_code=WC[0], category_code=WC[1], product_name="x").id == kind.id
    assert svc().resolve_kind(env.db, product_code=CB[0], category_code=CB[1]) is None
    assert svc().resolve_kind(env.db, product_code=BA[0], category_code=BA[1]) is None


@pytest.mark.parametrize("narrow,broad", [(0, 1), (1, 2), (2, 3), (0, 3)])
def test_k2_the_narrower_match_type_wins_at_equal_priority(env, narrow, broad):
    order = [("model_list", "SRTWC8152"), ("code_prefix", "SRTWC"), ("series", "Honeycomb"), ("category", "SRT-WC")]
    tag = unique_code("k2", alpha=True)
    narrow_kind = make_kind(env, f"{tag}-z")  # sorts last by code, so code is not what decides
    broad_kind = make_kind(env, f"{tag}-a")
    make_rule(env, broad_kind, *order[broad])
    make_rule(env, narrow_kind, *order[narrow])
    got = svc().resolve_kind(env.db, product_code="SRTWC8152", category_code="SRT-WC", product_name="Honeycomb Basin")
    assert got.id == narrow_kind.id


def test_k2_priority_outranks_specificity(env):
    tag = unique_code("k2p", alpha=True)
    listed = make_kind(env, f"{tag}-a")
    cat = make_kind(env, f"{tag}-b")
    make_rule(env, listed, "model_list", "SRTWC8152", priority=0)
    make_rule(env, cat, "category", "SRT-WC", priority=5)
    assert svc().resolve_kind(env.db, product_code="SRTWC8152", category_code="SRT-WC").id == cat.id


def test_k2_the_longest_matched_value_wins_then_the_kind_code(env):
    tag = unique_code("k2l", alpha=True)
    short, long_, other = make_kind(env, f"{tag}-c"), make_kind(env, f"{tag}-b"), make_kind(env, f"{tag}-a")
    make_rule(env, short, "code_prefix", "SRT")
    make_rule(env, long_, "code_prefix", "SRTWC")
    assert svc().resolve_kind(env.db, product_code="SRTWC8152").id == long_.id
    make_rule(env, other, "code_prefix", "SRTWC")  # same length, kind code sorts first
    assert svc().resolve_kind(env.db, product_code="SRTWC8152").id == other.id
    assert [m.kind.id for m in svc().rank_kind_matches(env.db, product_code="SRTWC8152")][:2] == [other.id, long_.id]


def test_k3_only_active_kinds_are_suggested(env):
    tag = unique_code("k3", alpha=True)
    archived = make_kind(env, f"{tag}-a", active=False)
    live = make_kind(env, f"{tag}-b")
    make_rule(env, archived, "category", "SRT-WC", priority=9)
    assert svc().resolve_kind(env.db, category_code="SRT-WC") is None
    make_rule(env, live, "category", "SRT-WC")
    assert svc().resolve_kind(env.db, category_code="SRT-WC").id == live.id


def test_k3_no_input_and_no_match_give_none_not_an_error(env):
    assert svc().resolve_kind(env.db) is None
    assert svc().resolve_kind_match(env.db, product_code="NOPE") is None


def test_k2_the_winning_match_names_the_rule_that_decided(env):
    kind = make_kind(env)
    rule = make_rule(env, kind, "code_prefix", "SRTWC")
    match = svc().resolve_kind_match(env.db, product_code=WC[0])
    assert (match.kind.id, match.rule.id) == (kind.id, rule.id)
