"""Phase 2 RED tests: CHATBOT-TOTALS-FILTERS owner hand test 1 (UAC rows HT1-1..HT1-11).

Real thread crew/state/handtest/2156/owner-ht1 (T4 "sorento company only", T5 "company sorento", T6 "top 5"); the parses are
copied here as literals. Contract the coder implements:
* lookup_lists: "company" joins HEADER_NOUN ("Company"), TOP_K, DEFAULT_ORDER; `load_rows(..., companies=[names])` builds one
  company row per name. The engine passes `_known_companies` only when the prompt text holds "Company candidates" AND the
  contact holds 2+ companies.
* parser: SAID_AS_WORD = "said_as", `with_said_as(schema)`: entity key `said_as` (company | brand | both | null), required,
  present only when the prompt text holds "said_as".
* report lane: said_as company -> Company only; brand -> Brand only; both -> both; null with the key present and no company
  held -> ONE company/brand/both question; the key absent -> today's behaviour (locks below).
* report lane frame: a held breakdown + frame ranking, top_n null, rank_direction top -> every row, never "How many?".
"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_report_semantic_carry import _ent, _ran, _v, rbot, world  # noqa: F401 - fixtures + helpers
from tests.chatbot.test_report_totals_filters import (  # noqa: F401 - fixtures + helpers
    SEP,
    SEPF,
    TOP_N_Q,
    _args,
    _kind_slot,
    _follow,
    _hold,
    _ra2,
)
from tests.chatbot.test_report_unify_routing import bot, console  # noqa: F401 - fixtures
from tests._mc_lookup_seed import MOCHA_ID
from tests.chatbot.test_chat_state_parser_input import _fresh_prompt_cache  # noqa: F401 - fixture
from tests.chatbot.test_report_ask_lane import console_no_grant  # noqa: F401 - fixture
from tests.chatbot.test_lookup_lists_s2 import scoped
from tests.chatbot.test_sales_account_type_lane import _entity_props, _sent_schema
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401 - fixtures
from tests.chatbot.conftest import session_factory  # noqa: F401 - fixture
from tests.chatbot import test_span_extract as se

@pytest.fixture
def said_as_on(rbot, monkeypatch) -> None:
    """Opt-in over `rbot`'s config: the prompt text in use defines `said_as` (`ParserConfig.said_as`), as the parses these
    tests send carry the key. The shared harness default (`test_report_semantic_carry._flag_on`) is left as it is."""
    current = parser_mod.resolve_config
    monkeypatch.setattr(parser_mod, "resolve_config", lambda *a, **k: dataclasses.replace(current(*a, **k), said_as=True))


COMPANY_HDR = "Company candidates (pick one only if the message means it):"
BRAND_HDR = se.HDR["brand"]
UNSET = "__unset__"


# ------------------------------------------------------------------------------------------ HT1-1 the candidates block


def test_ht1_1_company_joins_the_header_nouns_top_k_and_order() -> None:
    assert ll.HEADER_NOUN.get("company") == "Company"
    assert ll.header("company") == COMPANY_HDR
    assert "company" in ll.TOP_K and "company" in ll.DEFAULT_ORDER


def test_ht1_1_load_rows_builds_one_company_row_per_name_and_renders_the_block(session_factory) -> None:
    rows = ll.load_rows(scoped(session_factory), companies=["ZZ Granite", "ZZ Quartz"])
    comp = [r for r in rows if r.list_name == "company"]
    assert sorted(r.label for r in comp) == ["ZZ Granite", "ZZ Quartz"], comp
    hits = ll.shortlist("zz quartz company only", rows, None)
    assert COMPANY_HDR in ll.render(hits) and "- ZZ Quartz" in ll.render(hits), ll.render(hits)


@pytest.mark.parametrize("companies", [None, []], ids=["none", "empty"])
def test_ht1_1_without_companies_the_rows_and_the_rendered_text_are_todays(session_factory, companies) -> None:
    db = scoped(session_factory)
    rows = ll.load_rows(db, companies=companies)
    assert rows == ll.load_rows(db)
    assert not any(r.list_name == "company" for r in rows)
    assert COMPANY_HDR not in ll.render(ll.shortlist("zz quartz company only", rows, None))


TWO = ["ZZ Granite", "ZZMOCHA"]


def _span_run(session_factory, stub_access, monkeypatch, template: str, companies, span=None):
    from app.services.chatbot import engine as engine_mod

    se.seed_world(session_factory)
    monkeypatch.setattr(engine_mod, "_known_companies", lambda *a, **k: companies)
    return se.run(session_factory, stub_access, monkeypatch, text_body="zzmocha company only",
                  span=span or se.spans_json((se.BRAND, "brand")), template=template)


PHRASED = se.BASE + se.SPANS_LINE + "\nKnown companies lists them. Company candidates lists the company rows.\n"


def test_ht1_1_a_span_message_gets_the_brand_and_the_company_block(session_factory, seeded, stub_access, monkeypatch) -> None:
    r = _span_run(session_factory, stub_access, monkeypatch, PHRASED, TWO)
    assert BRAND_HDR in r.lines, r.lines
    assert COMPANY_HDR in r.lines and "- ZZMOCHA" in r.lines[r.lines.index(COMPANY_HDR):], r.lines


def test_ht1_1_lock_a_text_without_the_company_candidates_phrase_gets_no_block(session_factory, seeded, stub_access, monkeypatch) -> None:
    """Lock (green today and after): Known companies alone does not switch the block on."""
    plain = se.BASE + se.SPANS_LINE + "\nKnown companies lists them.\n"
    r = _span_run(session_factory, stub_access, monkeypatch, plain, TWO)
    assert COMPANY_HDR not in r.lines, r.lines
    assert BRAND_HDR in r.lines, r.lines


def test_ht1_1_a_one_company_contact_gets_no_block(session_factory, seeded, stub_access, monkeypatch) -> None:
    r = _span_run(session_factory, stub_access, monkeypatch, PHRASED, [])
    assert COMPANY_HDR not in r.lines, r.lines


# ------------------------------------------------------------------------------------------ HT1-11 schema gating


@pytest.mark.parametrize("raw,defined", [
    ("Rules {{current_date}} compare_to by_words kind_said said_as Company candidates.\n", True),
    ("Rules {{current_date}} compare_to by_words kind_said Known companies.\n", False),
    ("Rules {{current_date}} compare_to by_words.\n", False),
], ids=["new_text", "dc77a7ac_like", "e4aa6d43_like"])
def test_ht1_11_the_entity_schema_offers_said_as_only_when_the_prompt_defines_it(monkeypatch, session_factory, raw, defined) -> None:
    if defined:
        assert getattr(parser_mod, "SAID_AS_WORD", None) == "said_as"
    _config, schema = _sent_schema(monkeypatch, session_factory, raw)
    props = _entity_props(schema)
    required = schema["properties"]["entities"]["items"]["required"]
    assert ("said_as" in props) is defined, list(props)
    assert ("said_as" in required) is defined, required
    if defined:
        assert props["said_as"]["type"] == ["string", "null"]
        assert props["said_as"]["enum"] == ["company", "brand", "both", None], props["said_as"]


# ------------------------------------------------------------------------------------------ HT1-2..7 routing (T4 parse)


def _t4(said_as: Any = UNSET, *, company: Any = None, **flat: Any) -> dict[str, Any]:
    """The v199 T4 parse of "sorento company only": report_ask frame breakdown by sales_agent, brands [SORENTO], company null;
    entity brand SORENTO kind_said null; said_as added when given (the new prompt's slot)."""
    ent = _ent("sorento", "brand", "SORENTO", None)
    if said_as != UNSET:
        ent["said_as"] = said_as
    ra = _ra2("breakdown", basis="delivered", group_by="sales_agent", company=company, brands=["SORENTO"], **SEP)
    over = dict(basis="delivered", sales_basis="delivered", group_by="sales_agent", continuation=True, entity_op="replace_combine",
                scope_intent="specific", ranking_refine=True, domain_in_message=False, sales_company=company, **SEPF)
    over.update(flat)
    return _v("sales_ranking", ra, ent, **over)


def _hold_agents(b, company: str | None) -> int:
    """Run the held report; returns how many reports have run so far."""
    ra = _ra2("breakdown", basis="delivered", group_by="sales_agent", measure="amount", company=company, **SEP)
    v = _v("sales_analysis", ra, basis="delivered", group_by="sales_agent", measure="amount", sales_company=company,
           domain_in_message=True, **SEPF)
    text, calls = b.say(v, "sales by agent September")
    assert _ran(calls), f"setup: {text!r}"
    return len(_ran(calls))


def _no_question(b, text: str) -> None:
    assert _kind_slot(b).get("asking") != "kind" and TOP_N_Q not in text, f"asked: {text!r}"


def _every_agent(args: dict[str, Any]) -> None:
    assert args.get("group_by") == "sales_agent" and not args.get("agent") and not args.get("sales_agents"), args


@pytest.mark.usefixtures("said_as_on")
def test_ht1_2_said_as_company_is_company_sorento_only_for_every_agent(rbot, world) -> None:
    sorento, _m = world
    _hold_agents(rbot, None)
    text, calls = rbot.say(_t4("company"), "sorento company only")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and not args.get("brand_ids"), f"HT1-2: {args}"
    _every_agent(args)


@pytest.mark.usefixtures("said_as_on")
def test_ht1_3_said_as_brand_is_the_brand_only(rbot, world) -> None:
    _hold_agents(rbot, None)
    text, calls = rbot.say(_t4("brand"), "sorento brand only")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("brand_ids") and "company" not in args, f"HT1-3: {args}"


@pytest.mark.usefixtures("said_as_on")
def test_ht1_4_said_as_both_applies_both_filters(rbot, world) -> None:
    _hold_agents(rbot, None)
    text, calls = rbot.say(_t4("both"), "sorento company and brand")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("brand_ids"), f"HT1-4: {args}"


@pytest.mark.usefixtures("said_as_on")
def test_ht1_5_said_as_null_with_no_company_held_asks_one_company_brand_both_question(rbot, world) -> None:
    _hold_agents(rbot, None)
    text, calls = rbot.say(_t4(None), "sorento company only")
    slot = _kind_slot(rbot)
    assert slot.get("asking") == "kind", f"HT1-5: no kind question: {slot} / {text!r}"
    assert "company" in text.lower() and "brand" in text.lower(), text
    assert not _ran(calls), f"HT1-5: a report ran: {_ran(calls)}"


@pytest.mark.usefixtures("said_as_on")
def test_ht1_6_lock_cp5_a_held_company_with_said_as_null_adds_the_brand_and_asks_nothing(rbot, world) -> None:
    """Lock: green today (CP-5)."""
    sorento, _m = world
    _hold_agents(rbot, sorento)
    text, calls = rbot.say(_t4(None, company=sorento), "Sorento brand only")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("brand_ids"), f"HT1-6: {args}"


@pytest.mark.usefixtures("said_as_on")
def test_ht1_7_lock_a_one_company_contact_with_said_as_null_is_a_brand_no_question(rbot) -> None:
    """Lock: green today (ON-5 / ON-15)."""
    text, calls = rbot.say(_t4(None, continuation=False, entity_op="replace_combine", domain_in_message=True), "sorento total")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("brand_ids") and "company" not in args, f"HT1-7: {args}"


def test_ht1_11_lock_the_v199_t4_parse_without_the_said_as_key_is_todays_brand_filter(rbot, world) -> None:
    """Lock of whatever HEAD does today for the old parse (entity has no said_as key): the brand filter, no question."""
    _hold_agents(rbot, None)
    text, calls = rbot.say(_t4(), "sorento company only")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("brand_ids") and "company" not in args, f"HT1-11 lock: {args}"


# ------------------------------------------------------------------------------------------ HT1-8..10 frame (T5 parse)


def _t5(top_n: Any = None, direction: str = "top", company: str | None = None) -> dict[str, Any]:
    """The real T5 parse of "company sorento": frame ranking, top_n null, rank_direction top, group_by sales_agent."""
    ra = _ra2("ranking", basis="delivered", group_by="sales_agent", top_n=top_n, company=company, brands=[], **SEP)
    return _v("sales_ranking", ra, basis="delivered", group_by="sales_agent", top_n=top_n, rank_direction=direction,
              continuation=False, entity_op="replace_combine", ranking_refine=True, sales_company=company,
              domain_in_message=False, **SEPF)


def test_ht1_8_a_held_every_row_list_with_a_filter_only_ranking_parse_reruns_every_row_never_asks_how_many(rbot, world) -> None:
    sorento, _m = world
    _hold_agents(rbot, sorento)
    text, calls = rbot.say(_t5(company=sorento), "company sorento")
    assert TOP_N_Q not in text, f"HT1-8: {text!r}"
    args = _args(calls)
    assert args.get("group_by") == "sales_agent" and args.get("company") == DEFAULT_COMPANY_ID, args
    assert not args.get("top_n") or args["top_n"] >= 100, f"HT1-8: not every row: {args}"


def test_ht1_9_lock_a_ranking_with_its_own_count_is_cut_to_it(rbot, world) -> None:
    sorento, _m = world
    _hold_agents(rbot, sorento)
    text, calls = rbot.say(_t5(5, company=sorento), "top 5")
    assert TOP_N_Q not in text, text
    assert _args(calls).get("top_n") == 5 and _args(calls).get("group_by") == "sales_agent", _args(calls)


def test_ht1_10_lock_a_bottom_ranking_without_a_count_still_asks_how_many(rbot, world) -> None:
    sorento, _m = world
    _hold_agents(rbot, sorento)
    text, calls = rbot.say(_t5(None, "bottom", company=sorento), "bottom agents")
    assert TOP_N_Q in text, f"HT1-10: {text!r}"


# ------------------------------------------------------------------------------------------ gate 4: the model's own parses
# The exact entity + report_ask the model gave on gate 4 (TFPS5 9ad88b43, gate head 9bb6bed561): the object puts the name in
# `company` AND `brands`; the entity's said_as says which one the message meant. What matters is what the engine does.


def _g4_ent(raw: str, kind_said: Any, said_as: Any) -> dict[str, Any]:
    ent = _ent(raw, "brand", "SORENTO", kind_said)
    ent["said_as"] = said_as
    return ent


def _g4(sorento: str, ent: dict[str, Any], *, frame: str, basis: str | None, group_by: str | None, status: str, **flat: Any):
    ra = _ra2(frame, basis=basis, group_by=group_by, company=sorento, brands=["SORENTO"], **SEP)
    over = dict(basis=basis, group_by=group_by, entity_op="replace_combine", domain_in_message=True, sales_company=None, **SEPF)
    over.update(flat)
    return _v(status, ra, ent, **over)


@pytest.mark.usefixtures("said_as_on")
def test_g4_tf28_company_sorento_over_the_held_brand_list_is_company_only_for_every_agent(rbot, world) -> None:
    """tf-28: held every-agent breakdown with brands [SORENTO]; "company sorento": company AND brands, said_as company."""
    sorento, _m = world
    ra0 = _ra2("breakdown", basis="delivered", group_by="sales_agent", measure="amount", brands=["SORENTO"], **SEP)
    text0, calls0 = rbot.say(_v("sales_analysis", ra0, basis="delivered", group_by="sales_agent", measure="amount",
                                domain_in_message=True, **SEPF), "sorento brand sales by agent September")
    assert _ran(calls0), f"setup: {text0!r}"
    v = _g4(sorento, _g4_ent("sorento", None, "company"), frame="breakdown", basis="delivered", group_by="sales_agent",
            status="sales_ranking", continuation=False, ranking_refine=True, domain_in_message=False)
    text, calls = rbot.say(v, "company sorento")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and not args.get("brand_ids"), f"tf-28: {args}"
    _every_agent(args)


@pytest.mark.usefixtures("said_as_on")
def test_g4_tf29_brand_only_runs_the_brand_with_no_company_filter(rbot, world) -> None:
    """tf-29: fresh "Sorento brand only Sep 2026 delivered": company AND brands, said_as brand, kind_said brand."""
    sorento, _m = world
    v = _g4(sorento, _g4_ent("Sorento", "brand", "brand"), frame="total", basis="delivered", group_by=None,
            status="sales_analysis")
    text, calls = rbot.say(v, "Sorento brand only Sep 2026 delivered")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("brand_ids") and "company" not in args, f"tf-29: {args}"


@pytest.mark.usefixtures("said_as_on")
def test_g4_tf13_a_bare_name_with_said_as_null_asks_one_question_and_runs_nothing(rbot, world) -> None:
    """tf-13: fresh "Sorento total sale September 2026": company AND brands, said_as null (the model's own parse,
    except basis "delivered": the model left it null, which asks the basis question first, a different row's rule)."""
    sorento, _m = world
    v = _g4(sorento, _g4_ent("Sorento", None, None), frame="total", basis="delivered", group_by=None, status="sales_analysis")
    text, calls = rbot.say(v, "Sorento total sale September 2026")
    assert not _ran(calls), f"tf-13: a report ran: {_ran(calls)}"
    assert _kind_slot(rbot).get("asking") == "kind", f"tf-13: no kind question: {_kind_slot(rbot)} / {text!r}"
    assert "company" in text.lower() and "brand" in text.lower(), text


@pytest.mark.usefixtures("said_as_on")
def test_g4_tf30_company_and_brand_runs_both_filters(rbot, world) -> None:
    """tf-30: fresh "sorento company and brand, Sep 2026 delivered": company AND brands, said_as both, kind_said brand."""
    sorento, _m = world
    v = _g4(sorento, _g4_ent("sorento", "brand", "both"), frame="total", basis="delivered", group_by=None,
            status="sales_analysis")
    text, calls = rbot.say(v, "sorento company and brand, Sep 2026 delivered")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("brand_ids"), f"tf-30: {args}"


# ------------------------------------------------------------------------------------------ review round (a900795c1a)


def _fresh(ent: dict[str, Any], *, company: Any, brands: list[str], message: str, basis: str = "delivered"):
    ra = _ra2("total", basis=basis, company=company, brands=brands, **SEP)
    return _v("sales_analysis", ra, ent, basis=basis, entity_op="replace_combine", domain_in_message=True, **SEPF)


@pytest.mark.usefixtures("said_as_on")
def test_f2_said_as_brand_beats_a_same_name_company_when_the_entity_has_no_canonical_code(rbot, world) -> None:
    """F2: fresh, object company "Sorento" + brands [SORENTO]; the entity has canonical_code null, kind_said brand, said_as
    brand. said_as present and non-null decides: Brand only, no company filter, no question (ON-17's company reading applies
    only when said_as is null or absent)."""
    sorento, _m = world
    ent = _ent("Sorento", "brand", None, "brand")
    ent["said_as"] = "brand"
    text, calls = rbot.say(_fresh(ent, company=sorento, brands=["SORENTO"], message=""), "Sorento brand only Sep 2026 delivered")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("brand_ids") and "company" not in args, f"F2: {args}"


def test_f3_the_committed_totals_filters_gold_file_loads_whole() -> None:
    """F3: the repo's own loader reads the committed gold file (every expect key and slot the rows use is known to it)."""
    from pathlib import Path

    from scripts.chatbot_eval import parser_gold as pg

    path = Path(pg.__file__).parent / "gold" / "parser_report_totals_filters.jsonl"
    with open(path, encoding="utf-8") as fh:
        want = sum(1 for ln in fh if ln.strip())
    assert want >= 30
    assert len(pg.load_gold(path)) == want


def test_f5_m7_a_company_row_is_never_a_spans_resolved_match_but_the_block_still_renders(session_factory, seeded, stub_access, monkeypatch) -> None:
    """An UNTYPED span (a brand-typed one already prefers the brand list on a tie) ties the brand and the company row exactly.
    Depends on engine._span_lookup's `all_rows` filter (`r.list_name != "company"`, engine.py:2075): without it the span
    'zzmocha' (typed brand) would also resolve to the Company row ZZMOCHA, so a candidate of list "company" appears."""
    r = _span_run(session_factory, stub_access, monkeypatch, PHRASED, TWO, span=se.spans_json((se.BRAND, None)))
    ev = se.trace_events(session_factory, r)[0]
    cands = [c for s in ev["spans"] for c in s["candidates"]]
    assert cands and {c["list"] for c in cands} == {"brand"}, cands
    assert COMPANY_HDR in r.lines and "- ZZMOCHA" in r.lines[r.lines.index(COMPANY_HDR):], r.lines


@pytest.mark.parametrize("said_as,both", [("company", False), ("both", True)], ids=["company", "both"])
@pytest.mark.usefixtures("said_as_on")
def test_f5_m9_said_as_company_or_both_beats_a_kind_said_brand(rbot, world, said_as, both) -> None:
    """Depends on report_ask._word_kinds' `said_as in ("company", "both")` branch (report_ask.py:3422, covers company/brand/both), which sits
    before the kind_said branch: without it kind_said "brand" wins and the report runs as the brand only."""
    sorento, _m = world
    ent = _ent("sorento", "brand", "SORENTO", "brand")
    ent["said_as"] = said_as
    text, calls = rbot.say(_fresh(ent, company=None, brands=["SORENTO"], message=""), "sorento company")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID, f"M9 {said_as}: {args}"
    assert bool(args.get("brand_ids")) is both, f"M9 {said_as}: {args}"


def test_f5_m14_a_ranking_on_another_axis_than_the_held_list_still_asks_how_many(rbot, world) -> None:
    """Depends on the `axis == held_axis` clause of the HT1-8 rule (report_ask.py:3535): without it a customer ranking with no
    count would be read as the held every-agent list again and run instead of asking."""
    sorento, _m = world
    _hold_agents(rbot, sorento)
    ra = _ra2("ranking", basis="delivered", group_by="customer", top_n=None, company=sorento, **SEP)
    v = _v("sales_ranking", ra, basis="delivered", group_by="customer", rank_direction="top", continuation=False,
           entity_op="replace_combine", ranking_refine=True, sales_company=sorento, domain_in_message=False, **SEPF)
    text, calls = rbot.say(v, "customers")
    assert TOP_N_Q in text, f"M14: {text!r}"


# ------------------------------------------------------------------------------------------ review round 3


@pytest.mark.usefixtures("said_as_on")
def test_r3_lock_cp5_said_as_brand_over_the_held_same_name_company_keeps_the_company(rbot, world) -> None:
    """Lock 1: HT1-6 with said_as "brand". Depends on the brand branch applying the held company (report_ask.py:3633,
    `ask["company"] = held_company`): without it the object's same-name company is dropped even though it is the held
    one (CP-5)."""
    sorento, _m = world
    _hold_agents(rbot, sorento)
    text, calls = rbot.say(_t4("brand", company=sorento), "Sorento brand only")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("brand_ids"), f"R3-1: {args}"


@pytest.mark.usefixtures("said_as_on")
def test_r3_lock_said_as_brand_decides_before_the_c6_1_company_reading_with_kind_said_null(rbot, world) -> None:
    """Lock 2: F2's shape with kind_said null. Depends on the said_as branch sitting ahead of the C6-1 `loose` company reading
    in `_word_kinds` (report_ask.py:3422 before :3426-3432): reordered, the null kind_said + same-name company reads as the
    company and the brand is lost."""
    sorento, _m = world
    ent = _ent("Sorento", "brand", None, None)
    ent["said_as"] = "brand"
    text, calls = rbot.say(_fresh(ent, company=sorento, brands=["SORENTO"], message=""), "Sorento brand only Sep 2026 delivered")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("brand_ids") and "company" not in args, f"R3-2: {args}"


@pytest.mark.usefixtures("said_as_on")
def test_r3_said_as_decides_the_slot_only_for_a_company_name_a_brand_that_is_no_company_still_asks_on6(rbot, world) -> None:
    """ON-6 latent regression: Cabana is a brand and an account type, not one of the contact's companies; said_as "brand"
    must not settle it, the brand-or-account-type question stays."""
    from tests.chatbot.test_sales_account_type_lane import QUESTION

    sorento, _m = world
    ent = _ent("cabana", "brand", "CABANA", None)
    ent["said_as"] = "brand"
    ra = _ra2(None, basis="delivered", company=sorento, brands=["Cabana"], **SEP)
    v = _v("sales_report", ra, ent, basis="delivered", sales_company=sorento, domain_in_message=True, **SEPF)
    text, calls = rbot.say(v, "Cabana sales Sep delivered")
    assert not _ran(calls) and text.strip() == QUESTION, (calls, text)


@pytest.mark.usefixtures("said_as_on")
def test_r3_a_held_company_carries_the_same_with_a_same_name_object_company_as_with_a_null_one(rbot, world) -> None:
    """Owner Q3, an equivalence: from the same held Mocha report, "Sorento brand only" with the object's company "Sorento" +
    brands [SORENTO] + said_as brand answers exactly as the same object with company null (route args and reply text), and
    the held company Mocha carried (the reply is not an every-company run)."""
    import copy

    sorento, mocha = world
    _hold_agents(rbot, mocha)
    held = copy.deepcopy(rbot.console.session_vars)
    text_a, calls_a = rbot.say(_t4("brand", company=None), "Sorento brand only")
    rbot.console.session_vars = copy.deepcopy(held)  # a second thread holding the same Mocha report
    text_b, calls_b = rbot.say(_t4("brand", company=sorento), "Sorento brand only")
    assert mocha in text_a or (_ran(calls_a) and _args(calls_a).get("company") == MOCHA_ID), f"R3-4 A did not carry Mocha: {text_a!r}"
    assert _ran(calls_b) == _ran(calls_a) and text_b == text_a, f"R3-4: A {_ran(calls_a)} {text_a!r} / B {_ran(calls_b)} {text_b!r}"


# ------------------------------------------------------------------------------------------ HT1-13..16 said_as_text


def _with_said_as_text(rbot, monkeypatch, on: bool) -> None:
    """The harness config, with the prompt text defining `said_as_text` (opt in) or not (v200 text). The flag is the
    ParserConfig field `said_as_text` the engine reads; the words ride in the stub system prompt as well."""
    import dataclasses

    from tests.chatbot.test_report_semantic_carry import LINE

    def _cfg(db, *, current_date, override_version_id=None):
        words = "said_as said_as_text" if on else "said_as"
        base = parser_mod.ParserConfig(
            system_prompt=f"stub {words}\n{LINE}\n", prompt_version=39, provider="openai", model="gpt-test",
            api_key="sk-test",
        )
        fields = {f.name for f in dataclasses.fields(base)}
        base = dataclasses.replace(base, report_ask=True, **({"said_as": True} if "said_as" in fields else {}))
        if on:
            if "said_as_text" in fields:
                base = dataclasses.replace(base, said_as_text=True)
            else:  # the field is not there yet: the engine cannot see it either way, which is the red
                object.__setattr__(base, "said_as_text", True)
        return base

    monkeypatch.setattr(parser_mod, "resolve_config", _cfg)


def _with_text(verdict: dict[str, Any], said_as_text: Any) -> dict[str, Any]:
    verdict["entities"][0]["said_as_text"] = said_as_text
    return verdict


def _r2(sorento: str, said_as: Any, said_as_text: Any):
    """The v200 repass r2 parse: fresh "Sorento total sale September 2026 delivered", entity said_as set with no kind word
    (kind_said null), object company Sorento + brands [SORENTO]."""
    ent = _g4_ent("Sorento", None, said_as)
    ent["said_as_text"] = said_as_text
    return _g4(sorento, ent, frame="total", basis="delivered", group_by=None, status="sales_analysis")


@pytest.mark.parametrize("said_as_text", [None, ""], ids=["null", "empty"])
def test_ht1_13_said_as_without_its_typed_word_is_read_as_null_and_asks_the_one_question(rbot, world, monkeypatch, said_as_text) -> None:
    sorento, _m = world
    _with_said_as_text(rbot, monkeypatch, True)
    text, calls = rbot.say(_r2(sorento, "company", said_as_text), "Sorento total sale September 2026 delivered")
    assert not _ran(calls), f"HT1-13: a report ran: {_ran(calls)}"
    assert _kind_slot(rbot).get("asking") == "kind", f"HT1-13: no kind question: {_kind_slot(rbot)} / {text!r}"
    assert "company" in text.lower() and "brand" in text.lower(), text


@pytest.mark.parametrize("said_as,word,company,brand", [
    ("company", "company", True, False),
    ("brand", "brand", False, True),
    ("both", "company and brand", True, True),
], ids=["company", "brand", "both"])
def test_ht1_14_lock_said_as_with_its_typed_word_decides_the_slot(rbot, world, monkeypatch, said_as, word, company, brand) -> None:
    _with_said_as_text(rbot, monkeypatch, True)
    _hold_agents(rbot, None)
    text, calls = rbot.say(_with_text(_t4(said_as), word), f"sorento {word} only")
    _no_question(rbot, text)
    args = _args(calls)
    assert (args.get("company") == DEFAULT_COMPANY_ID) is company, f"HT1-14 {said_as}: {args}"
    assert bool(args.get("brand_ids")) is brand, f"HT1-14 {said_as}: {args}"


def test_ht1_15_lock_a_text_without_said_as_text_keeps_v200_the_company_runs_silently(rbot, world, monkeypatch) -> None:
    """The gate is the prompt text: v200 defines `said_as` only, so the r2 parse (said_as company, no typed word) is the
    Company, no question, exactly today's behaviour."""
    sorento, _m = world
    _with_said_as_text(rbot, monkeypatch, False)
    text, calls = rbot.say(_r2(sorento, "company", None), "Sorento total sale September 2026 delivered")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and not args.get("brand_ids"), f"HT1-15: {args}"


def test_ht1_16_the_entity_schema_offers_said_as_text_before_said_as_only_when_the_prompt_defines_it(monkeypatch, session_factory) -> None:
    assert getattr(parser_mod, "SAID_AS_TEXT_WORD", None) == "said_as_text"
    _c, schema = _sent_schema(monkeypatch, session_factory, "Rules {{current_date}} compare_to by_words kind_said said_as said_as_text.\n")
    entity = schema["properties"]["entities"]["items"]
    props, required = list(entity["properties"]), entity["required"]
    assert entity["properties"].get("said_as_text") == {"type": ["string", "null"]}, props
    assert "said_as_text" in required and "said_as" in required, required
    assert props.index("said_as_text") < props.index("said_as"), props
    assert required.index("said_as_text") < required.index("said_as"), required
    _assert_ordering(entity, parser_mod.with_said_as(parser_mod.with_kind_said(parser_mod.PARSE_OUTPUT_JSON_SCHEMA))["properties"]["entities"]["items"])


def _assert_ordering(entity: dict[str, Any], v200_entity: dict[str, Any]) -> None:
    """`said_as_text` is the one thing inserted: properties / required / propertyOrdering all carry it right before
    `said_as`, propertyOrdering lists exactly the properties (alphabetical, as Gemini writes them, but for that
    insertion), and the Gemini translation keeps it."""
    from app.services import llm_provider

    props, required, po = list(entity["properties"]), list(entity["required"]), entity.get("propertyOrdering")
    assert po is not None, f"no propertyOrdering on the entity: {sorted(entity)}"
    assert set(po) == set(props) and len(po) == len(props), (po, props)
    v200_props = list(v200_entity["properties"])
    assert [k for k in po if k != "said_as_text"] == sorted(k for k in props if k != "said_as_text"), po
    assert po.index("said_as_text") + 1 == po.index("said_as"), po
    assert props.index("said_as_text") + 1 == props.index("said_as"), props
    assert required.index("said_as_text") + 1 == required.index("said_as"), required
    # nothing else moved: the v200 keys keep their v200 order
    assert [k for k in props if k in v200_props] == v200_props, (props, v200_props)
    assert [k for k in required if k != "said_as_text"] == [k for k in v200_entity["required"]], required
    gem = llm_provider._gemini_schema({"type": "object", "properties": {"entities": {"type": "array", "items": entity}}})
    assert gem["properties"]["entities"]["items"].get("propertyOrdering") == po, gem


def test_ht1_16_the_closed_lists_schema_orders_said_as_text_the_same_way() -> None:
    schema = parser_mod.closed_lists_schema(["A", "B"], kind_said=True, said_as=True, said_as_text=True)
    v200 = parser_mod.closed_lists_schema(["A", "B"], kind_said=True, said_as=True)["properties"]["entities"]["items"]
    entity = schema["properties"]["entities"]["items"]
    assert "listed_item" in entity["properties"] and "propertyOrdering" not in v200
    _assert_ordering(entity, v200)


def test_ht1_16_a_v200_text_without_said_as_text_has_no_such_key(monkeypatch, session_factory) -> None:
    _c, v200 = _sent_schema(monkeypatch, session_factory, "Rules {{current_date}} compare_to by_words kind_said said_as.\n")
    assert "said_as_text" not in _entity_props(v200) and "said_as" in _entity_props(v200)
    assert "said_as_text" not in v200["properties"]["entities"]["items"]["required"]


# ------------------------------------------------------------------------------------------ HT1-18..20 held company vs object echo


def _company_held_breakdown(rbot, object_company: str, entities: tuple, message: str, sales_company: Any = "Sorento"):
    """Company Sorento held (total, delivered, Sep 2026); then "break down project and retail" as the v202 parse gave it:
    top-level sales_company the held name, the object's company `object_company`, entities as given."""
    sorento = "Sorento"
    _hold(rbot, sorento, group_by=None)
    ra = _ra2("breakdown", basis="delivered", group_by="channel", company=object_company, brands=[], **SEP)
    v = _follow("sales_analysis", ra, *entities, group_by="channel", sales_company=sales_company, **SEPF)
    return rbot.say(v, message)


FORBIDDEN = "You do not have access to that company."


def test_ht1_18_a_held_company_is_not_overridden_by_an_object_company_echo_that_names_nothing(rbot, world) -> None:
    text, calls = _company_held_breakdown(rbot, "Sorenth", (), "break down project and retail")
    assert FORBIDDEN not in text, f"HT1-18: {text!r}"
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("group_by") == "channel" and args.get("company") == DEFAULT_COMPANY_ID, f"HT1-18: {args}"


def test_ht1_19_lock_a_company_the_message_names_replaces_the_held_one(rbot, world) -> None:
    ent = _ent("Mocha", "brand", None, None)
    text, calls = _company_held_breakdown(rbot, "Mocha", (ent,), "Mocha sales only")
    assert FORBIDDEN not in text, f"HT1-19: {text!r}"
    args = _args(calls)
    assert args.get("company") == MOCHA_ID, f"HT1-19: {args}"


def test_ht1_20_lock_a_company_the_message_names_that_the_contact_does_not_hold_is_forbidden(rbot, world) -> None:
    ent = _ent("Fujiwara", "brand", None, None)
    text, calls = _company_held_breakdown(rbot, "Fujiwara", (ent,), "Fujiwara sales only")
    assert text.strip() == FORBIDDEN, f"HT1-20: {text!r}"
    assert not _ran(calls), _ran(calls)


def test_ht1_18b_a_genuine_switch_with_no_parser_field_naming_the_held_company_runs_the_new_company(rbot, world) -> None:
    text, calls = _company_held_breakdown(rbot, "Mocha", (), "break down project and retail", sales_company=None)
    assert FORBIDDEN not in text, f"HT1-18b: {text!r}"
    args = _args(calls)
    assert args.get("company") == MOCHA_ID, f"HT1-18b: {args}"


def test_ht1_18_a_channel_entity_of_this_message_does_not_disable_the_held_company_rule(rbot, world) -> None:
    ent = _ent("project", "sales_channel", None, None)
    text, calls = _company_held_breakdown(rbot, "Sorenth", (ent,), "break down project and retail")
    assert FORBIDDEN not in text, f"HT1-18 channel: {text!r}"
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("group_by") == "channel" and args.get("company") == DEFAULT_COMPANY_ID, f"HT1-18 channel: {args}"


def test_ht1_18c_lock_an_entity_naming_the_object_company_wins_over_sales_company(rbot, world) -> None:
    ent = _ent("Mocha", "brand", None, None)
    text, calls = _company_held_breakdown(rbot, "Mocha", (ent,), "Mocha sales only", sales_company="Sorento")
    assert FORBIDDEN not in text, f"HT1-18c: {text!r}"
    args = _args(calls)
    assert args.get("company") == MOCHA_ID, f"HT1-18c: {args}"
