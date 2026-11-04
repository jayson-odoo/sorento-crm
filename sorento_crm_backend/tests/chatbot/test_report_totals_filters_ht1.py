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
    _ra2,
)
from tests.chatbot.test_report_unify_routing import bot, console  # noqa: F401 - fixtures
from tests.chatbot.test_chat_state_parser_input import _fresh_prompt_cache  # noqa: F401 - fixture
from tests.chatbot.test_report_ask_lane import console_no_grant  # noqa: F401 - fixture
from tests.chatbot.test_lookup_lists_s2 import scoped
from tests.chatbot.test_sales_account_type_lane import _entity_props, _sent_schema
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401 - fixtures
from tests.chatbot.conftest import session_factory  # noqa: F401 - fixture
from tests.chatbot import test_span_extract as se

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


def test_ht1_2_said_as_company_is_company_sorento_only_for_every_agent(rbot, world) -> None:
    sorento, _m = world
    _hold_agents(rbot, None)
    text, calls = rbot.say(_t4("company"), "sorento company only")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and not args.get("brand_ids"), f"HT1-2: {args}"
    _every_agent(args)


def test_ht1_3_said_as_brand_is_the_brand_only(rbot, world) -> None:
    _hold_agents(rbot, None)
    text, calls = rbot.say(_t4("brand"), "sorento brand only")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("brand_ids") and "company" not in args, f"HT1-3: {args}"


def test_ht1_4_said_as_both_applies_both_filters(rbot, world) -> None:
    _hold_agents(rbot, None)
    text, calls = rbot.say(_t4("both"), "sorento company and brand")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("brand_ids"), f"HT1-4: {args}"


def test_ht1_5_said_as_null_with_no_company_held_asks_one_company_brand_both_question(rbot, world) -> None:
    _hold_agents(rbot, None)
    text, calls = rbot.say(_t4(None), "sorento company only")
    slot = _kind_slot(rbot)
    assert slot.get("asking") == "kind", f"HT1-5: no kind question: {slot} / {text!r}"
    assert "company" in text.lower() and "brand" in text.lower(), text
    assert not _ran(calls), f"HT1-5: a report ran: {_ran(calls)}"


def test_ht1_6_lock_cp5_a_held_company_with_said_as_null_adds_the_brand_and_asks_nothing(rbot, world) -> None:
    """Lock: green today (CP-5)."""
    sorento, _m = world
    _hold_agents(rbot, sorento)
    text, calls = rbot.say(_t4(None, company=sorento), "Sorento brand only")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("brand_ids"), f"HT1-6: {args}"


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


def test_g4_tf29_brand_only_runs_the_brand_with_no_company_filter(rbot, world) -> None:
    """tf-29: fresh "Sorento brand only Sep 2026 delivered": company AND brands, said_as brand, kind_said brand."""
    sorento, _m = world
    v = _g4(sorento, _g4_ent("Sorento", "brand", "brand"), frame="total", basis="delivered", group_by=None,
            status="sales_analysis")
    text, calls = rbot.say(v, "Sorento brand only Sep 2026 delivered")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("brand_ids") and "company" not in args, f"tf-29: {args}"


def test_g4_tf13_a_bare_name_with_said_as_null_asks_one_question_and_runs_nothing(rbot, world) -> None:
    """tf-13: fresh "Sorento total sale September 2026": company AND brands, said_as null (the model's own parse,
    except basis "delivered": the model left it null, which asks the basis question first, a different row's rule)."""
    sorento, _m = world
    v = _g4(sorento, _g4_ent("Sorento", None, None), frame="total", basis="delivered", group_by=None, status="sales_analysis")
    text, calls = rbot.say(v, "Sorento total sale September 2026")
    assert not _ran(calls), f"tf-13: a report ran: {_ran(calls)}"
    assert _kind_slot(rbot).get("asking") == "kind", f"tf-13: no kind question: {_kind_slot(rbot)} / {text!r}"
    assert "company" in text.lower() and "brand" in text.lower(), text


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
def test_f5_m9_said_as_company_or_both_beats_a_kind_said_brand(rbot, world, said_as, both) -> None:
    """Depends on report_ask._word_kinds' `said_as in ("company", "both")` branch (report_ask.py:3432), which sits before the
    kind_said branch: without it kind_said "brand" wins and the report runs as the brand only."""
    sorento, _m = world
    ent = _ent("sorento", "brand", "SORENTO", "brand")
    ent["said_as"] = said_as
    text, calls = rbot.say(_fresh(ent, company=None, brands=["SORENTO"], message=""), "sorento company")
    _no_question(rbot, text)
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID, f"M9 {said_as}: {args}"
    assert bool(args.get("brand_ids")) is both, f"M9 {said_as}: {args}"


def test_f5_m14_a_ranking_on_another_axis_than_the_held_list_still_asks_how_many(rbot, world) -> None:
    """Depends on the `axis == held_axis` clause of the HT1-8 rule (report_ask.py:3543): without it a customer ranking with no
    count would be read as the held every-agent list again and run instead of asking."""
    sorento, _m = world
    _hold_agents(rbot, sorento)
    ra = _ra2("ranking", basis="delivered", group_by="customer", top_n=None, company=sorento, **SEP)
    v = _v("sales_ranking", ra, basis="delivered", group_by="customer", rank_direction="top", continuation=False,
           entity_op="replace_combine", ranking_refine=True, sales_company=sorento, domain_in_message=False, **SEPF)
    text, calls = rbot.say(v, "customers")
    assert TOP_N_Q in text, f"M14: {text!r}"
