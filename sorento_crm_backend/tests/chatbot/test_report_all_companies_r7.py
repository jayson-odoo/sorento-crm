"""Round 7 RED tests: O-R2 (no company question, every held company, a named company narrows), C6-1 (a both-table word
that is also a company), C6-2 (a held filter survives a follow-up the model's own outputs do not change).

Flag OFF tests use the flag-off harness (`_status`, `bot`); flag ON tests use `rbot` and the `report_ask` object. Every
assertion is on the args that RAN (or the question asked). Invented data only.
"""
from __future__ import annotations

import pytest

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID
from tests.chatbot.test_report_semantic_carry import (  # noqa: F401 - fixtures
    AGENT_1, AGENT_2, YR, Y, _FIXTURES, _agent_pick, _ent, _pick_of, _ra, _ran, _v, agent_b_sorento, bot, console, rbot, world,
)
from tests.chatbot.test_chat_state_parser_input import _fresh_prompt_cache  # noqa: F401
from tests.chatbot.test_report_unify_company_lane import _pick, _two_companies
from tests.chatbot.test_report_unify_routing import NO_DATES, YEAR, _only_report_ask, _status
from tests.chatbot.test_sales_account_type_lane import BASIS_Q, QUESTION, _ledger

OCT = {"date_from": "2026-10-01", "date_to": "2026-10-31"}
OCTF = {"date_filter_start": "2026-10-01", "date_filter_end": "2026-10-31"}


def _no_company_question(text: str, sorento: str, mocha: str, tag: str) -> None:
    assert f"{sorento} or {mocha}?" not in text, f"O-R2 {tag}: the company question was asked: {text!r}"


# ------------------------------------------------------------------------------------------ O-R2 flag off


def test_o_r2_flag_off_sales_basis_pick_runs_with_no_company(bot) -> None:
    """O-R2 (flag off): 'sales 2026' -> basis question -> 'invoiced' -> a report RUNS with no `company` arg."""
    sorento, mocha = _two_companies(bot)
    text, calls = bot.say(_status("sales_report", basis=None, **YEAR), "sales 2026")
    assert calls == [] and text.strip() == BASIS_Q, (text, calls)
    text, calls = bot.say(_pick(1), "invoiced")
    _no_company_question(text, sorento, mocha, "sales")
    args = _only_report_ask(calls)
    assert "company" not in args and args["basis"] == "invoiced", f"O-R2: {args}"


def test_o_r2_flag_off_ranking_basis_pick_runs_with_no_company(bot) -> None:
    """O-R2 (flag off): 'top 5 products 2026' -> basis question -> 'invoiced' -> runs with no `company` arg."""
    sorento, mocha = _two_companies(bot)
    v = _status("sales_ranking", group_by="product", top_n=5, measure="amount", rank_direction="top", by_words="products",
                basis=None, domain_in_message=True)
    text, calls = bot.say(v, "top 5 products 2026")
    assert calls == [] and text.strip() == BASIS_Q, (text, calls)
    text, calls = bot.say(_pick(1), "invoiced")
    _no_company_question(text, sorento, mocha, "ranking")
    args = _only_report_ask(calls)
    assert "company" not in args and args["basis"] == "invoiced" and args["group_by"] == "product", f"O-R2: {args}"


def test_o_r2_flag_off_a_named_company_narrows_a_sales_ask(bot) -> None:
    sorento, mocha = _two_companies(bot)
    text, calls = bot.say(_status("sales_report", basis="invoiced", sales_company="Mocha", **YEAR), "mocha sales 2026 invoiced")
    assert _only_report_ask(calls)["company"] == MOCHA_ID


def test_o_r2_flag_off_a_named_company_narrows_an_outstanding_ask(bot) -> None:
    """O-R2: today a named company is IGNORED on outstanding; it now narrows."""
    sorento, mocha = _two_companies(bot)
    v = _status("outstanding", basis="outstanding", sales_company="Mocha", **NO_DATES)
    text, calls = bot.say(v, "mocha outstanding orders")
    if not calls:  # the kind question first
        text, calls = bot.say(_pick(1), "the first")
    assert _only_report_ask(calls).get("company") == MOCHA_ID, f"O-R2: a named company is ignored on outstanding: {calls} {text!r}"


@pytest.mark.parametrize("status,basis", [("sales_report", "invoiced"), ("outstanding", "outstanding")])
def test_o_r2_flag_off_a_company_the_contact_does_not_hold_is_refused(bot, status, basis) -> None:
    """Guard (may pass today): a foreign company keeps the forbidden line."""
    from app.services.chatbot.lanes.business import report_ask

    _two_companies(bot)
    extra = YEAR if status == "sales_report" else NO_DATES
    text, calls = bot.say(_status(status, basis=basis, sales_company="Zzt Foreign Trading", **extra), "zzt foreign trading")
    assert calls == [] and text.strip() == report_ask.COMPANY_FORBIDDEN_LINE, (text, calls)


# ------------------------------------------------------------------------------------------ O-R2 flag on


def test_o_r2_flag_on_sales_with_no_company_runs_with_no_company_arg(rbot, world) -> None:
    sorento, mocha = world
    v = _v("sales_report", _ra(basis="invoiced", **Y), basis="invoiced", domain_in_message=True, **YR)
    text, calls = rbot.say(v, "sales 2026 invoiced")
    _no_company_question(text, sorento, mocha, "sales")
    assert _ran(calls) and "company" not in _ran(calls)[0], f"O-R2: {calls} {text!r}"


def test_o_r2_flag_on_ranking_with_no_company_runs_with_no_company_arg(rbot, world) -> None:
    sorento, mocha = world
    ra = _ra(basis="invoiced", group_by="product", top_n=5, measure="amount", **Y)
    v = _v("sales_ranking", ra, basis="invoiced", group_by="product", top_n=5, measure="amount", rank_direction="top",
           domain_in_message=True, **YR)
    text, calls = rbot.say(v, "top 5 products 2026 invoiced")
    _no_company_question(text, sorento, mocha, "ranking")
    assert _ran(calls) and "company" not in _ran(calls)[0], f"O-R2: {calls} {text!r}"


def test_o_r2_flag_on_a_named_company_narrows_sales(rbot, world) -> None:
    sorento, mocha = world
    v = _v("sales_report", _ra(basis="invoiced", company=mocha, **Y), basis="invoiced", sales_company=mocha, domain_in_message=True, **YR)
    text, calls = rbot.say(v, "mocha sales 2026 invoiced")
    assert _ran(calls) and _ran(calls)[0].get("company") == MOCHA_ID, (calls, text)


def test_o_r2_flag_on_a_named_company_narrows_outstanding(rbot, world) -> None:
    """O-R2: today a named company is ignored on outstanding."""
    sorento, mocha = world
    v = _v("outstanding", _ra(kind="outstanding", basis="outstanding", company=mocha), basis="outstanding", sales_company=mocha, domain_in_message=True)
    text, calls = rbot.say(v, "mocha undelivered orders")
    assert _ran(calls) and _ran(calls)[0].get("company") == MOCHA_ID, f"O-R2: a named company is ignored on outstanding: {calls} {text!r}"


@pytest.mark.parametrize("kind", ["sales", "outstanding"])
def test_o_r2_flag_on_a_company_the_contact_does_not_hold_is_refused(rbot, world, kind) -> None:
    """Guard (may pass today)."""
    from app.services.chatbot.lanes.business import report_ask

    basis = "invoiced" if kind == "sales" else "outstanding"
    ra = _ra(kind=kind, basis=basis, company="Zzt Foreign Trading", **(Y if kind == "sales" else {}))
    v = _v("sales_report" if kind == "sales" else "outstanding", ra, basis=basis, sales_company="Zzt Foreign Trading", domain_in_message=True)
    text, calls = rbot.say(v, "zzt foreign trading")
    assert not _ran(calls) and text.strip() == report_ask.COMPANY_FORBIDDEN_LINE, (calls, text)


# ------------------------------------------------------------------------------------------ C6-1 (flag on)

OCT_ASK = dict(channel="dealer", basis="invoiced", **OCT)


def _sorento_type(world_bot) -> None:
    """SORENTO is a brand (world) AND an account type: one ledger stored with that type."""
    db = world_bot.console.session_factory()
    try:
        _ledger(db, DEFAULT_COMPANY_ID, "ZZT SORENTO TYPE LEDGER [A/C VII]", "SORENTO")
        db.commit()
    finally:
        db.close()


def _first_position(text: str, word: str) -> int:
    for ln in text.splitlines():
        if ln[:1].isdigit() and ". " in ln and word in ln.lower():
            return int(ln.split(". ", 1)[0])
    raise AssertionError(f"no numbered option naming {word!r} in {text!r}")


def test_c6_1_a_both_table_word_that_is_a_company_offers_brand_account_type_and_company(rbot, world) -> None:
    """C6-1(a): SORENTO is a brand, an account type and a held company: the question offers all three; picking the company
    runs company Sorento with no SORENTO brand / account type and every other held slot."""
    sorento, _mocha = world
    _sorento_type(rbot)
    ra = _ra(brands=["SORENTO"], **OCT_ASK)
    v = _v("sales_report", ra, _ent("sorento", "brand"), sales_channel="dealer", basis="invoiced", sales_basis="invoiced",
           domain_in_message=True, **OCTF)
    text, calls = rbot.say(v, "sorento dealer sales oct invoiced")
    low = text.lower()
    assert not _ran(calls) and "brand" in low and "account type" in low and "company" in low, f"C6-1: want brand, account type AND company offered, got {text!r}"
    pos = _first_position(text, "company")
    follow = _v("sales_report", _ra(brands=["SORENTO"], **OCT_ASK), entity_op="reuse", continuation=True,
                open_question_answer=_pick_of(pos), reference_positions=[pos])
    text, calls = rbot.say(follow, "company")
    ran = _ran(calls)
    assert ran, f"C6-1: the company pick did not run: {text!r}"
    args = ran[0]
    assert args.get("company") == DEFAULT_COMPANY_ID and not args.get("brand_ids") and not args.get("account_types"), f"C6-1: {args}"
    assert args.get("channel") == "dealer" and args.get("basis") == "invoiced" and args.get("date_from") == "2026-10-01", args


def test_c6_1_an_object_whose_company_is_the_word_settles_with_no_question(rbot, world) -> None:
    """C6-1(b): company 'Sorento' and brands ['SORENTO'] (the model read 'company') -> no question, runs company Sorento."""
    sorento, _mocha = world
    _sorento_type(rbot)
    ra = _ra(company=sorento, brands=["SORENTO"], **OCT_ASK)
    v = _v("sales_report", ra, _ent("sorento", "brand"), sales_channel="dealer", basis="invoiced", sales_basis="invoiced",
           sales_company=sorento, domain_in_message=True, **OCTF)
    text, calls = rbot.say(v, "only company sorento dealer sales oct invoiced")
    ran = _ran(calls)
    assert ran, f"C6-1: want a run with no question, the bot said {text!r}"
    args = ran[0]
    assert args.get("company") == DEFAULT_COMPANY_ID and not args.get("brand_ids") and not args.get("account_types"), f"C6-1: {args}"


def test_c6_1_control_a_both_table_word_that_is_not_a_company_asks_only_brand_or_account_type(rbot, world) -> None:
    """C6-1(c) control: CABANA is no company -> only 'brand or account type' (the existing question), never the company."""
    sorento, _mocha = world
    ra = _ra(company=sorento, brand_or_account_type=["cabana"], **OCT_ASK)
    v = _v("sales_report", ra, _ent("cabana", "brand"), sales_channel="dealer", basis="invoiced", sales_basis="invoiced",
           sales_company=sorento, domain_in_message=True, **OCTF)
    text, calls = rbot.say(v, "cabana dealer sales oct invoiced")
    assert not _ran(calls) and text.strip() == QUESTION and "company" not in text.lower(), (text, calls)


# ------------------------------------------------------------------------------------------ C6-2 (flag on)


def _held_agent_ceramic(rbot, sorento: str) -> None:
    ra = _ra(basis="invoiced", group_by="month", company=sorento, sales_agents=[AGENT_1], account_types=["ceramic"], **Y)
    v = _v("sales_analysis", ra, _ent(AGENT_1, "sales_agent"), _ent("ceramic", "account_type", None, "account type"),
           basis="invoiced", sales_basis="invoiced", group_by="month", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(v, "agent a ceramic account type sales by month 2026 invoiced")
    ran = _ran(calls)
    assert ran and ran[0].get("account_types") == ["CERAMIC"], f"setup: {text!r} {calls}"


def test_c6_2_a_an_agent_change_keeps_the_held_account_type(rbot, world) -> None:
    """C6-2(a) (turn 17023f41): the entities name the agent only; the object dropped account_types -> CERAMIC stays."""
    sorento, _m = world
    _held_agent_ceramic(rbot, sorento)
    ra = _ra(basis="invoiced", group_by="month", company=sorento, sales_agents=[AGENT_2], account_types=[], **Y)
    v = _v("sales_analysis", ra, _ent(AGENT_2.lower(), "sales_agent"), sales_basis="invoiced", group_by="month",
           continuation=True, entity_op="replace_combine", sales_company=sorento, **YR)
    text, calls = rbot.say(v, "for sales agent b")
    ran = _ran(calls)
    assert ran, f"the follow-up did not run: {text!r}"
    args = ran[0]
    assert args.get("sales_agent_ids") and agent_b_sorento(rbot) in args["sales_agent_ids"], args
    assert args.get("account_types") == ["CERAMIC"], f"C6-2(a): the account type was dropped: {args}"
    assert args.get("group_by") == "month", args


def test_c6_2_b_invoiced_after_an_open_question_keeps_type_month_company_and_agent(rbot, world) -> None:
    """C6-2(b) (turn f26a5645, parser_raw copied): the brand-or-account-type question on SORENTO is open (basis held) and
    "invoiced" answers it with no entities, mode fill, picked []; the object dropped account_types and swapped month for
    sales_agent. The reply to "invoiced" is itself the run: CERAMIC + month + company Sorento + agent, SORENTO not applied."""
    sorento, _m = world
    _sorento_type(rbot)
    ra = _ra(basis="invoiced", group_by="month", company=sorento, sales_agents=[AGENT_1], account_types=["ceramic"],
             brand_or_account_type=["SORENTO"], **Y)
    v = _v("sales_analysis", ra, _ent(AGENT_1, "sales_agent"), _ent("ceramic", "account_type", None, "account type"),
           _ent("sorento", "brand"), basis="invoiced", sales_basis="invoiced", group_by="month", sales_company=sorento,
           domain_in_message=True, **YR)
    text, calls = rbot.say(v, "agent a ceramic account type sorento by month 2026 invoiced")
    assert not _ran(calls) and "brand, account type or company?" in text.lower(), f"setup: want the three-option question (Sorento is held), got {text!r} {calls}"
    # f26a5645 parser_raw: report_ask company "Sorento", group_by "sales_agent", account_types [], brand_or_account_type [],
    # entities [], open_question_answer fill / picked [], order_status sales_ranking, entity_op reuse, continuation true.
    ra2 = _ra(basis="invoiced", group_by="sales_agent", company=sorento, sales_agents=[AGENT_1], account_types=[], **Y)
    fill = {"mode": "fill", "items": [], "picked": [], "qty_for_all": None}
    v2 = _v("sales_ranking", ra2, basis="invoiced", group_by="sales_agent", entity_op="reuse", continuation=True,
            open_question_answer=fill, sales_company=sorento)
    text, calls = rbot.say(v2, "invoiced")
    ran = _ran(calls)
    assert ran, f"C6-2(b): the reply to 'invoiced' is not the run; the bot said {text.strip()!r}"
    args = ran[0]
    assert args.get("account_types") == ["CERAMIC"], f"C6-2(b): CERAMIC dropped: {args}"
    assert args.get("group_by") == "month", f"C6-2(b): month swapped for {args.get('group_by')!r}"
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("sales_agent_ids"), args
    assert not args.get("brand_ids") and "SORENTO" not in (args.get("account_types") or []), f"SORENTO applied: {args}"


def test_c6_2_c_a_one_row_breakdown_over_a_filter_is_a_plain_total(rbot, world) -> None:
    """C6-2(c) (turn 23d6cb50): 'ceramic' account type named, the object set group_by account_type: the ask filters to
    one value, so it runs account type CERAMIC with NO group_by."""
    sorento, _m = world
    ra = _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], **Y)
    v = _v("sales_report", ra, _ent(AGENT_1, "sales_agent"), basis="invoiced", sales_basis="invoiced", sales_company=sorento,
           domain_in_message=True, **YR)
    text, calls = rbot.say(v, "sorento invoiced sales agent a 2026")
    assert _ran(calls), f"setup: {text!r}"
    ra2 = _ra(basis="invoiced", group_by="account_type", company=sorento, sales_agents=[AGENT_1], account_types=["ceramic"], **Y)
    v2 = _v("sales_analysis", ra2, _ent("ceramic", "account_type", None, "account type"), sales_basis="invoiced",
            group_by="account_type", continuation=True, entity_op="replace_combine", sales_company=sorento, **YR)
    text, calls = rbot.say(v2, "for ceramic account type")
    ran = _ran(calls)
    assert ran, f"no run: {text!r}"
    args = ran[0]
    assert args.get("account_types") == ["CERAMIC"], args
    assert not args.get("group_by"), f"C6-2(c): a one-row breakdown ran by {args.get('group_by')!r}, want a plain total: {args}"


def test_c6_2_d_a_held_customer_survives_breakdown_and_top_n(rbot, world) -> None:
    """C6-2(d): held customer X (one ledger), invoiced, Oct; 'breakdown product' (no entity, customers []) keeps X;
    'top 5, by invoiced qty' keeps X."""
    from tests.chatbot.test_report_ask_lane import CUSTOMER_NAME

    sorento, _m = world
    ra = _ra(basis="invoiced", company=sorento, customers=[CUSTOMER_NAME], **OCT)
    v = _v("sales_report", ra, _ent(CUSTOMER_NAME, "customer"), basis="invoiced", sales_basis="invoiced", sales_company=sorento,
           domain_in_message=True, **OCTF)
    text, calls = rbot.say(v, "sorento sales customer oct invoiced")
    ran = _ran(calls)
    assert ran and ran[0].get("customer_ids"), f"setup: {text!r}"
    held = ran[0]["customer_ids"]
    ra2 = _ra(basis="invoiced", group_by="product", company=sorento, customers=[], **OCT)
    text, calls = rbot.say(_v("sales_analysis", ra2, group_by="product", sales_basis="invoiced", continuation=True,
                              entity_op="reuse", report_breakdown=True), "breakdown product")
    ran = _ran(calls)
    assert ran and ran[0].get("customer_ids") == held and ran[0].get("group_by") == "product", f"C6-2(d): {ran or text!r}"
    ra3 = _ra(basis="invoiced", group_by="product", top_n=5, measure="qty", company=sorento, customers=[], **OCT)
    text, calls = rbot.say(_v("sales_ranking", ra3, group_by="product", top_n=5, measure="qty", basis="invoiced",
                              rank_direction="top", continuation=True, entity_op="reuse", ranking_refine=True), "top 5, by invoiced qty")
    ran = _ran(calls)
    assert ran and ran[0].get("customer_ids") == held, f"C6-2(d): top 5 dropped the customer: {ran or text!r}"
    assert ran[0].get("top_n") == 5 and ran[0].get("measure") == "qty", ran[0]


def test_c6_2_e_a_new_explicit_account_type_replaces_the_held_one(rbot, world) -> None:
    """C6-2(e) control: the entity names account type CABANA, the object holds [CABANA] over held [CERAMIC] -> CABANA only."""
    sorento, _m = world
    _held_agent_ceramic(rbot, sorento)
    ra = _ra(basis="invoiced", group_by="month", company=sorento, sales_agents=[AGENT_1], account_types=["cabana"], **Y)
    v = _v("sales_analysis", ra, _ent("cabana", "account_type", None, "account type"), sales_basis="invoiced", group_by="month",
           continuation=True, entity_op="replace_combine", sales_company=sorento, **YR)
    text, calls = rbot.say(v, "for cabana account type")
    ran = _ran(calls)
    assert ran and ran[0].get("account_types") == ["CABANA"], f"{ran or text!r}"


def test_c6_2_e_a_topic_reset_carries_nothing(rbot, world) -> None:
    """C6-2(e) control: topic_reset true -> the held account type does not come back."""
    sorento, _m = world
    _held_agent_ceramic(rbot, sorento)
    ra = _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_2], **Y)
    v = _v("sales_report", ra, _ent(AGENT_2.lower(), "sales_agent"), basis="invoiced", sales_basis="invoiced", sales_company=sorento,
           topic_reset=True, entity_op="clear", domain_in_message=True, **YR)
    text, calls = rbot.say(v, "start over, sales for agent b 2026 invoiced")
    ran = _ran(calls)
    assert ran and not ran[0].get("account_types"), f"a reset carried the account type: {ran or text!r}"


def test_c6_2_e_a_typed_breakdown_on_a_plain_turn_still_applies(rbot, world) -> None:
    """C6-2(e) control: object group_by month, top_n null, on a non-answer turn after a total -> month runs."""
    sorento, _m = world
    ra = _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], **Y)
    v = _v("sales_report", ra, _ent(AGENT_1, "sales_agent"), basis="invoiced", sales_basis="invoiced", sales_company=sorento,
           domain_in_message=True, **YR)
    text, calls = rbot.say(v, "sorento invoiced sales agent a 2026")
    assert _ran(calls), f"setup: {text!r}"
    ra2 = _ra(basis="invoiced", group_by="month", company=sorento, sales_agents=[AGENT_1], **Y)
    v2 = _v("sales_analysis", ra2, group_by="month", sales_basis="invoiced", by_words="by month", continuation=True,
            entity_op="modify", domain_in_message=True, sales_company=sorento)
    text, calls = rbot.say(v2, "breakdown by month")
    ran = _ran(calls)
    assert ran and ran[0].get("group_by") == "month", f"{ran or text!r}"


# ------------------------------------------------------------------------------------------ round 7b

THREE = "brand, account type or company?"


def test_b1_flag_on_all_companies_drops_the_held_company(rbot, world) -> None:
    """B1 (flag ON): held company Sorento, then 'and for all companies' (object company null, broaden_axis company,
    broaden_to all) runs with no company arg."""
    sorento, _mocha = world
    t1 = _v("sales_report", _ra(company=sorento, basis="invoiced", **Y), basis="invoiced", sales_company=sorento,
            domain_in_message=True, **YR)
    text, calls = rbot.say(t1, "sorento sales 2026 invoiced")
    assert _ran(calls) and _ran(calls)[0].get("company") == DEFAULT_COMPANY_ID, f"setup: {text!r}"
    t2 = _v("sales_report", _ra(company=None, basis="invoiced", **Y), basis="invoiced", entity_op="replace_combine",
            continuation=True, broaden_axis="company", broaden_to="all")
    text, calls = rbot.say(t2, "and for all companies")
    ran = _ran(calls)
    assert ran and "company" not in ran[0], f"B1: 'all companies' kept the held company: {ran[0] if ran else text!r}"


@pytest.mark.parametrize("code", [None, "SORENTO"], ids=["no-code", "bound-code"])
def test_s2_only_company_sorento_with_sorento_held_offers_brand_account_type_and_company(rbot, world, code) -> None:
    """S2 (SC-19 has no exception for the held company; C6-1): company Sorento HELD, 'only company sorento' read as brands
    [SORENTO] with the object's company null -> the question offers brand, account type AND company; picking company runs
    company Sorento with no SORENTO brand / account type."""
    sorento, _mocha = world
    _sorento_type(rbot)
    t1 = _v("sales_report", _ra(company=sorento, **OCT_ASK), sales_channel="dealer", basis="invoiced", sales_basis="invoiced",
            sales_company=sorento, domain_in_message=True, **OCTF)
    text, calls = rbot.say(t1, "sorento dealer sales oct invoiced")
    assert _ran(calls), f"setup: {text!r}"
    ra = _ra(company=None, brands=["SORENTO"], **OCT_ASK)
    v = _v("sales_report", ra, _ent("sorento", "brand", code), entity_op="replace_combine", continuation=True)
    text, calls = rbot.say(v, "only company sorento")
    assert not _ran(calls) and THREE in text.lower(), f"S2: want the three-option question, got {text!r} {calls}"
    pos = _first_position(text, "company")
    follow = _v("sales_report", _ra(company=None, brands=["SORENTO"], **OCT_ASK), entity_op="reuse", continuation=True,
                open_question_answer=_pick_of(pos), reference_positions=[pos])
    text, calls = rbot.say(follow, "company")
    ran = _ran(calls)
    assert ran, f"S2: the company pick did not run: {text!r}"
    assert ran[0].get("company") == DEFAULT_COMPANY_ID and not ran[0].get("brand_ids") and not ran[0].get("account_types"), ran[0]


def test_q6_an_old_stored_company_question_and_a_reply_is_read_fresh(bot, world) -> None:
    """Q6 (a session stored before the release holds the retired company question): the reply '2' never runs the held ask
    for a company; it is read fresh (the basis question for that shape)."""
    from tests.chatbot.test_report_unify_routing import YEAR as YEAR_F, _status

    sorento, mocha = world
    text, calls = bot.say(_status("sales_report", basis="delivered", sales_company=sorento, **YEAR_F), "sorento total sales 2026")
    assert calls, text
    focus = bot.console.session_vars["focus"]
    opts = [["00000000-0000-0000-0000-000000000001", sorento], ["x", mocha]]
    focus["required_ask"] = {
        "ask": "sales_ranking", "asking": "company", "values": {}, "misses": 0, "options": opts,
        "extras": {"args": {"sort": "desc", "basis": "delivered", "date_from": "2026-01-01", "date_to": "2026-12-31"},
                   "company_options": opts, "company_codes": ["S", "M"]},
    }
    v = _status("sales_report", basis=None, sales_company=None, entity_op="reuse", continuation=True,
                open_question_answer={"mode": "pick", "picked": [2], "items": [], "qty_for_all": None}, reference_positions=[2])
    text, calls = bot.say(v, "2")
    assert not _ran(calls), f"Q6: the reply ran the held ask: {calls}"
    assert text.strip() == BASIS_Q, f"Q6: want the basis question (read fresh), got {text!r}"


# ------------------------------------------------------------------------------------------ round 7c (the `_carry` widening seam, every axis)

WIDE_BRAND = "ZZT WIDEBRAND"


def _seed_wide_brand(b) -> None:
    import uuid

    from app.models.product import Brand

    db = b.console.session_factory()
    try:
        db.add(Brand(id=str(uuid.uuid4()), brand_code="ZZTWIDE", brand_name=WIDE_BRAND, company_id=DEFAULT_COMPANY_ID))
        db.commit()
    finally:
        db.close()


def _axis_specs():
    from tests.chatbot.test_report_ask_lane import CUSTOMER_NAME, PRODUCT_CODE

    # axis word as the parser emits it -> (held entities, held object fields, verdict extras, arg keys of that kind,
    # whether brand / account type clear together)
    return {
        "sales_agent": ([_ent(AGENT_1, "sales_agent")], dict(sales_agents=[AGENT_1]), {}, ("sales_agent_ids",)),
        "brand": ([_ent("zzt widebrand", "brand")], dict(brands=[WIDE_BRAND]), {}, ("brand_ids", "account_types")),
        "account_type": ([_ent("ceramic", "account_type", None, "account type")], dict(account_types=["ceramic"]), {}, ("account_types", "brand_ids")),
        "category": ([_ent("ZZT CATEGORY", "category")], dict(categories=["ZZT CATEGORY"]), {}, ("category_ids",)),
        "customer": ([_ent(CUSTOMER_NAME, "customer")], dict(customers=[CUSTOMER_NAME]), {}, ("customer_ids",)),
        "product": ([_ent(PRODUCT_CODE, "product")], dict(products=[PRODUCT_CODE]), {}, ("product_code", "product_ids")),
        "channel": ([], dict(channel="dealer"), dict(sales_channel="dealer"), ("channel",)),
        "company": ([], dict(), {}, ("company",)),
    }


#: channel is not a carried kind (SC-8: a restated ask drops it), so it has the widen case only.
_C7_CASES = [
    (axis, mode)
    for axis in ("sales_agent", "brand", "account_type", "category", "customer", "product", "channel", "company")
    for mode in ("widen", "no-broaden", "family")
    if not (axis == "channel" and mode != "widen")
]


@pytest.mark.parametrize("axis,mode", _C7_CASES, ids=[f"{a}-{m}" for a, m in _C7_CASES])
def test_c7_a_widened_axis_drops_only_its_own_kind_on_every_axis(rbot, world, axis, mode) -> None:
    """C6-2 + R-P3-09 (flag ON, the `_carry` widening seam): for EVERY carried kind, held X then a follow-up with no
    current-message entity and the object's list for that kind empty. `broaden_to` "all" + `broaden_axis` <kind> -> the run has
    no filter of that kind (brand and account type clear together) and keeps every OTHER held filter. Controls: no broaden
    fields (X carries, C6-2) and `broaden_to` "family" (no widening drop by this rule)."""
    sorento, _m = world
    _seed_wide_brand(rbot)
    ents, held_fields, verdict_extra, keys = _axis_specs()[axis]
    company_held = axis != "company"
    witness_channel = axis not in ("channel",)
    base = dict(basis="invoiced", **Y)
    obj1 = _ra(company=sorento, **held_fields, **base)
    v1 = _v("sales_report", obj1, *ents, basis="invoiced", sales_basis="invoiced", sales_company=sorento, domain_in_message=True,
            **verdict_extra, **YR)
    text, calls = rbot.say(v1, f"sorento invoiced sales {axis} 2026")
    ran = _ran(calls)
    assert ran, f"setup ({axis}): the held ask did not run: {text!r}"
    assert any(ran[0].get(k) for k in keys[:2] if k in ("channel", "company", "sales_agent_ids", "category_ids", "customer_ids", "product_code", "product_ids", "brand_ids", "account_types")), f"setup ({axis}): X not on the first run: {ran[0]}"
    # the follow-up: the model re-states the company (unless the axis is the company) and drops the kind's list
    obj2 = _ra(company=(sorento if company_held else None), channel=None, **base)
    extra = {}
    if mode == "widen":
        extra = dict(broaden_axis=axis, broaden_to="all")
    elif mode == "family":
        extra = dict(broaden_axis=axis, broaden_to="family")
    v2 = _v("sales_report", obj2, basis="invoiced", entity_op="reuse", continuation=True,
            sales_company=(sorento if company_held else None), **extra, **YR)
    text, calls = rbot.say(v2, "and for all" if mode == "widen" else "and again")
    ran2 = _ran(calls)
    assert ran2, f"({axis}, {mode}): no run; the bot said {text.strip()!r}"
    args = ran2[0]
    present = [k for k in keys if args.get(k)]
    if mode == "widen":
        assert not present, f"C6-2/R-P3-09 ({axis}): a widened '{axis}' kept {present}: {args}"
        assert args.get("basis") == "invoiced" and args.get("date_from") == "2026-01-01", f"({axis}) lost a witness: {args}"
        if company_held:
            assert args.get("company") == DEFAULT_COMPANY_ID, f"({axis}) widening one axis dropped the company: {args}"
    else:
        assert any(args.get(k) for k in keys[:1]) or (axis in ("brand", "account_type") and any(args.get(k) for k in keys)), (
            f"C6-2 control ({axis}, {mode}): the held {axis} did not carry: {args}"
        )


@pytest.mark.parametrize("shape", ["reuse", "refine"])
def test_c7_flag_off_and_for_all_companies_runs_with_no_company_keeps_the_rest(bot, world, shape) -> None:
    """R-P3-09 + O-R2 (flag OFF, P5c): 'and for all companies' after a report for company Sorento: broaden_axis company,
    broaden_to all, in the reuse and the refine shapes -> no company arg, the other held filters (channel, basis, period) kept."""
    sorento, _m = world
    t1 = _v("sales_report", None, basis="invoiced", sales_basis="invoiced", sales_channel="dealer", sales_company=sorento,
            domain_in_message=True, **YR)
    text, calls = bot.say(t1, "sorento dealer sales 2026 invoiced")
    assert _ran(calls) and _ran(calls)[0].get("company") == DEFAULT_COMPANY_ID and _ran(calls)[0].get("channel") == "dealer", (text, calls)
    shapes = {
        "reuse": dict(entity_op="reuse", continuation=True),
        "refine": dict(entity_op="modify", continuation=True, ranking_refine=True),
    }
    t2 = _v("sales_report", None, basis="invoiced", sales_basis="invoiced", broaden_axis="company", broaden_to="all",
            **shapes[shape], **YR)
    text, calls = bot.say(t2, "and for all companies")
    ran = _ran(calls)
    assert ran, f"no run; the bot said {text.strip()!r}"
    assert "company" not in ran[0], f"P5c ({shape}): 'all companies' kept the held company: {ran[0]}"
    assert ran[0].get("channel") == "dealer" and ran[0].get("basis") == "invoiced" and ran[0].get("date_from") == "2026-01-01", ran[0]
