"""Phase 2 RED tests - REPORT-UNIFY slice 3: span binding.

`documentation/plans/reports/PLAN-report-unify-27oct.md` section 3 and UAC AC-RU-18 to AC-RU-22, cases named
after the owner messages H2, H3, H4 and the prod turn P6 of `CARD-report-unify-27oct.md` section 3.

Full console turns, the harness of `test_report_ask_lane.py` and `test_report_unify_routing.py`: the REAL engine,
lane, span resolver and MCP presenter. Doubles: the parser (it returns the emission a model would, and the
`user_block` it was shown is captured), the span extractor (`span_extract.extract` returns the spans the owner's
trace shows) and the MCP transport. The prompt is the span-pass version (`ParserConfig.lookup_spans`), so the
candidate blocks the parser sees are the real `lookup_lists.render` output.

Readings the tester PINNED where the contract is silent (flagged to the captain):
* The binding wire is the parser's entity: `{raw, hint, canonical_code}`, where `canonical_code` is the label OR
  the row id of the candidate the parser chose (plan 3.1). The lane binds a brand, sales agent or category from
  `canonical_code` when present and never re-reads `raw` (plan 3.2). Both forms are tested.
* A candidate row's id is printed on its line of the candidate block, so the parser can echo it: each line of
  the Brand, Salesperson and Category candidate blocks carries the row id (plan 3.1 "with a stable id"). Only
  the id-bearing test pins that; the labels-only test (AC-RU-22) holds for any rendering.
* "Which sales agent?" is a numbered pick like every other pick: options are numbered lines, and the reply is
  the parser's `reference_positions` + `answers_open_question.picks` for the number (the convention of
  `test_rearch_s2_number_answers.py`). The tests read the number off the printed line, never assume an order.
* "Agents only" means no line of the question carries a customer name; a pick of an agent runs the ask the
  first turn held (product, period, basis) with `sales_agent_ids` = the picked row and no `group_by`.
* A category word bound by the span pass never reaches the customer resolver: no customer question, no
  `customer_ids` (P6).
* AC-RU-22 is tested on `engine._span_lookup` (the seam `test_semantic_bridge.py` already drives) with six
  salesperson rows that all carry the alias "yu": the resolver then returns all six as close, exact rows, and
  the rendered block must print all six, not the first `TOP_K["salesperson"]` (5).
* The sales ask parses carry `basis: "delivered"`: a missing basis is asked (AC-RU-16), which is not what these
  cases are about.
"""
from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any
from unittest import mock

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import list_resolver, lookup_lists, span_extract
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_engine import CONTACT_ID
from tests.chatbot.test_outstanding_lane import AnswerServices, FetchServices, _present_response
from tests.chatbot.test_report_ask_lane import (  # noqa: F401  (console is a fixture)
    TOOL,
    _SNAKE,
    _fake_body,
    _rank,
    _reply,
    console,
)
from tests.chatbot.test_report_unify_routing import BASIS_LABELS, YEAR, _status
from tests.chatbot._turn_helpers import make_office_access_type

PRODUCT = "SRTSP231"
AGENT_CODES = [f"ZZT-YU-{n}" for n in range(1, 7)]
CUSTOMER_WITH_YU = "G-YU TRADING SDN BHD"
KITCHEN_CUSTOMERS = ["KITCHEN WORLD SDN BHD", "KITCHEN KING TRADING SDN BHD"]
WHICH_AGENT = "Which sales agent?"
DONT_KNOW_BRAND = "I don't know 'mch' as a brand"


# ------------------------------------------------------------------------- seeds and harness


def _ent(raw: str, hint: str, canonical: str | None = None, **over: Any) -> dict[str, Any]:
    return {"raw": raw, "hint": hint, "canonical_code": canonical, "current_message": True, "confident": True, **over}


def _seed_world(session_factory) -> dict[str, Any]:
    """MOCHA brand, six agents answering to "yu", customers that merely contain YU / KITCHEN, a KITCHEN SINK
    category and the product of the card (H3 / H4)."""
    from app.models.product import Brand, ProductCategory
    from app.models.sales_agent import SalesAgent
    from tests._mc_lookup_seed import customer, product

    db = session_factory()
    try:
        ids: dict[str, Any] = {}
        mocha = Brand(id=str(uuid.uuid4()), brand_code="ZZTMOCHA", brand_name="MOCHA", company_id=DEFAULT_COMPANY_ID)
        sink = ProductCategory(
            id=str(uuid.uuid4()), category_code="ZZTKSINK", category_name="KITCHEN SINK", company_id=DEFAULT_COMPANY_ID
        )
        tap = ProductCategory(
            id=str(uuid.uuid4()), category_code="ZZTTAP", category_name="WATER TAP", company_id=DEFAULT_COMPANY_ID
        )
        agents = [
            SalesAgent(id=str(uuid.uuid4()), sales_agent=code, aliases="yu", company_id=DEFAULT_COMPANY_ID)
            for code in AGENT_CODES
        ]
        db.add_all([mocha, sink, tap, *agents])
        db.flush()
        ids.update(mocha=mocha.id, sink=sink.id, tap=tap.id, agents=dict(zip(AGENT_CODES, (a.id for a in agents))))
        ids["product"] = product(db, company_id=DEFAULT_COMPANY_ID, code=PRODUCT).id
        for name in [CUSTOMER_WITH_YU, *KITCHEN_CUSTOMERS]:
            customer(db, company_id=DEFAULT_COMPANY_ID, name=name)
        db.commit()
        return {k: (v if isinstance(v, dict) else str(v)) for k, v in ids.items()}
    finally:
        db.close()


class SpanBot:
    """Console turns with the span pass on. `spans` is what the span double returns for the turn; `blocks` keeps
    the `user_block` of every parser call; `say` returns the reply and EVERY tool call as `(name, args)`."""

    def __init__(self, console_, monkeypatch) -> None:
        self.console, self.mp = console_, monkeypatch
        self.spans: list[list_resolver.Span] = []
        self.blocks: list[str] = []
        self.ids = _seed_world(console_.session_factory)

    def say(self, qf: dict[str, Any], body: str, spans: list[list_resolver.Span] | None = None):
        from app.services.chatbot import console_service
        from app.services.chatbot.head import parser as parser_mod

        c, mp = self.console, self.mp
        self.spans = list(spans or [])
        mp.setattr(
            parser_mod, "resolve_config",
            lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
                system_prompt="stub", prompt_version=39, provider="openai", model="gpt-test", api_key="sk-test",
                lookup_lists=True, lookup_spans=True, row_ids=True,
            ),
        )
        mp.setattr(span_extract, "resolve_config", lambda db, *, llm_choice=None: span_extract.SpanConfig(
            "sys", 1, "openai", "gpt-zz", "ZZ-key", "label"))
        mp.setattr(span_extract, "extract", lambda config, message: span_extract.SpanAnswer(list(self.spans), {}, 1))

        def _parse(config, user_block):
            self.blocks.append(user_block)
            return qf

        mp.setattr(parser_mod, "parse", _parse)
        calls: list[tuple[str, dict[str, Any]]] = []
        present = _present_response()

        def _mcp(name: str, args: dict[str, Any]) -> Any:
            calls.append((name, dict(args)))
            if name != TOOL:
                return json.dumps({"has_result": False, "items": []})
            fake = _fake_body(args)
            fake["basis_label"] = BASIS_LABELS.get(args.get("basis", "delivered"), fake["basis_label"])
            return present(name, json.dumps(fake))

        mp.setattr(engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=_mcp))
        mp.setattr(
            engine_mod.business_services, "answer_services_for",
            lambda session_factory: AnswerServices(
                mcp_probe=lambda name, args: {"data": []}, family_fetch=lambda query: {"data": []}
            ),
        )
        db = c.session_factory()
        try:
            result = console_service.run_console_turn(
                db, contact_respond_id=str(CONTACT_ID), text=body,
                session_vars=copy.deepcopy(c.session_vars), run_id="zzt-report-unify-span",
            )
        finally:
            db.close()
        c.session_vars = result.session_vars or {}
        text = result.reply_text or ""
        self.last_text = text
        assert not _SNAKE.search(text), (body, text)
        assert chr(0x2014) not in text and chr(0x2013) not in text, body
        return text, calls

    def block(self) -> str:
        return self.blocks[-1] if self.blocks else ""


@pytest.fixture
def bot(console, monkeypatch) -> SpanBot:
    """The harness contact as STAFF holding the sales report reveal: it sees the Salesperson and Customer blocks."""
    from sqlalchemy import text as sql

    from app.services.contact_field_reveal_service import set_granted_keys

    make_office_access_type(console.session_factory, CONTACT_ID)
    db = console.session_factory()
    try:
        internal = db.execute(
            sql("SELECT id FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": str(CONTACT_ID)}
        ).scalar_one()
        # The Salesperson block is built only for a contact holding the reveal in the DATABASE (the route's own
        # grant), not just the mocked access check of the console harness.
        set_granted_keys(db, str(internal), ["sales_orders.sales_report"], actor_id=None)
        db.commit()
    finally:
        db.close()
    return SpanBot(console, monkeypatch)


def _report_calls(calls):
    return [a for n, a in calls if n == TOOL]


def _only_report(calls, text="") -> dict[str, Any]:
    assert [n for n, _a in calls] == [TOOL], (calls, "REPLY:", text)
    return calls[0][1]


def _number_of(text: str, word: str) -> int:
    """The number of the printed option line that holds `word`."""
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)[.)]\s+(.*)", line)
        if m and word in m.group(2):
            return int(m.group(1))
    raise AssertionError(f"no numbered option holds {word!r}: {text!r}")


def _pick(n: int) -> dict[str, Any]:
    return _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[], reference_positions=[n],
        answers_open_question={"resolved": True, "picks": [n], "answer": None},
        # Parser only (owner rule 28 Oct): the pick counts through the parser's declared answer to the open question.
        open_question_answer={"mode": "pick", "picked": [n], "items": [], "qty_for_all": None},
    )


# ================================================================ AC-RU-18: a bound brand reaches the report as its id


def test_h2_mch_bound_to_mocha_by_the_span_pass_reaches_the_report_as_the_mocha_brand_id(bot) -> None:
    """AC-RU-18 / H2 "top 100 hot selling mch watr tap in 2026, by delivered qty": the parser returns
    {raw:"mch", hint:"brand", canonical_code:"MOCHA"}; the ranking runs with MOCHA's brand id and category Tap,
    and the reply is never "I don't know 'mch' as a brand"."""
    text, calls = bot.say(
        _rank(
            _ent("mch", "brand", "MOCHA"), _ent("watr tap", "category", "WATER TAP"),
            group_by="product", top_n=100, measure="qty", basis="delivered", **YEAR,
        ),
        "top 100 hot selling mch watr tap in 2026, by delivered qty",
        spans=[list_resolver.Span("mch", "brand"), list_resolver.Span("watr tap", "category")],
    )
    args = _only_report(calls, text)
    assert args["brand_ids"] == [bot.ids["mocha"]], args
    assert args["category_ids"] == [bot.ids["tap"]], args
    assert DONT_KNOW_BRAND not in text and "don't know" not in text.lower(), text


def test_ac_ru_18_a_brand_bound_by_row_id_wins_over_a_raw_word_that_names_no_brand(bot) -> None:
    """AC-RU-18 / plan 3.2: canonical_code = the row id; the raw word ("zzxqv") names nothing and is never read."""
    text, calls = bot.say(
        _rank(_ent("zzxqv", "brand", bot.ids["mocha"]), group_by="product", top_n=10, measure="qty",
              basis="delivered", **YEAR),
        "top 10 zzxqv products 2026 by qty",
        spans=[list_resolver.Span("zzxqv", "brand")],
    )
    args = _only_report(calls, text)
    assert args["brand_ids"] == [bot.ids["mocha"]], args


def test_ac_ru_18_a_brand_whose_label_differs_from_the_raw_word_binds_by_the_label(bot) -> None:
    """AC-RU-18 / plan 3.2: canonical_code = the label "MOCHA", raw "the coffee brand": bound, not guessed."""
    text, calls = bot.say(
        _rank(_ent("the coffee brand", "brand", "MOCHA"), group_by="product", top_n=10, measure="qty",
              basis="delivered", **YEAR),
        "top 10 the coffee brand products 2026 by qty",
        spans=[list_resolver.Span("the coffee brand", "brand")],
    )
    args = _only_report(calls, text)
    assert args["brand_ids"] == [bot.ids["mocha"]], args


def test_ac_ru_18_a_brand_bound_on_a_sales_total_also_reaches_the_report(bot) -> None:
    """AC-RU-18: the binding is not only for rankings: a sales total with the same bound brand."""
    text, calls = bot.say(
        _status("sales_report", _ent("mch", "brand", "MOCHA")), "mch total sales 2026",
        spans=[list_resolver.Span("mch", "brand")],
    )
    args = _only_report(calls, text)
    assert args["brand_ids"] == [bot.ids["mocha"]], args
    assert not args.get("group_by"), args


# ================================================================ AC-RU-19 / 20: an agent word never offers customers


def _agent_spans() -> list[list_resolver.Span]:
    return [list_resolver.Span("yu", "salesperson")]


def _ask_h3(bot) -> tuple[str, list]:
    return bot.say(
        _status("sales_report", _ent("yu", "sales_agent"), _ent(PRODUCT, "product"), basis="delivered", **YEAR),
        "sales agent yu sales for SRTSP231 in 2026",
        spans=_agent_spans(),
    )


def test_h3_several_agents_for_yu_ask_which_sales_agent_listing_agents_only(bot) -> None:
    """AC-RU-19 / H3 "sales agent yu sales for SRTSP231 in 2026": six agent rows answer to "yu"; the bot asks
    "Which sales agent?" with the six agents and no customer (the customer G-YU ... is never offered); no tool runs."""
    text, calls = _ask_h3(bot)
    assert calls == [], (calls, text)
    assert WHICH_AGENT in text, text
    for code in AGENT_CODES:
        assert code in text, (code, text)
    assert CUSTOMER_WITH_YU not in text and "G-YU" not in text, text
    assert "customer" not in text.lower(), text
    assert "Which one do you mean?" not in text, text


def test_h3_the_pick_runs_the_held_ask_with_that_agent_the_product_and_no_grouping(bot) -> None:
    """AC-RU-19 / H3: after the pick, crm_report_ask gets sales_agent_ids = the picked agent, the product, 2026
    and no group_by; the header names the agent."""
    text, _calls = _ask_h3(bot)
    n = _number_of(text, "ZZT-YU-3")
    text, calls = bot.say(_pick(n), str(n))
    args = _only_report(calls, text)
    assert args["sales_agent_ids"] == [bot.ids["agents"]["ZZT-YU-3"]], args
    assert args["product_code"] == PRODUCT, args
    assert not args.get("group_by"), args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert not args.get("customer_ids"), args


def test_a_typed_agent_digit_with_no_parser_answer_is_never_the_pick(bot) -> None:
    """Parser only (owner rule 28 Oct): the digit typed under "Which sales agent?" is not an answer unless the parser
    declared one; it is a new message, and no agent filter runs."""
    text, _calls = _ask_h3(bot)
    n = _number_of(text, "ZZT-YU-3")
    text, calls = bot.say(
        _reply(message_type="business_query", domain_hint=None, intent_hint=None, entities=[]), str(n)
    )
    assert not [a for name, a in calls if a.get("sales_agent_ids")], (calls, text)


@pytest.mark.parametrize("typed", ["3", "ZZT-YU-3"])
@pytest.mark.parametrize("mode", ["pick", "fill"])
def test_a_declared_agent_answer_that_picks_nothing_never_sends_an_agent(bot, mode, typed) -> None:
    text, _calls = _ask_h3(bot)
    declared = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[],
        open_question_answer={"mode": mode, "picked": [], "items": [], "qty_for_all": None},
    )
    text, calls = bot.say(declared, typed)
    assert not [a for n, a in calls if a.get("sales_agent_ids")], (calls, text)


def test_h4_total_sale_gives_the_same_pick_and_the_same_args_as_h3(bot) -> None:
    """AC-RU-20 / H4 "sales agent yu total sale for SRTSP231 in 2026": the same question, and the same args after
    the same pick, as H3."""
    text3, _ = _ask_h3(bot)
    n = _number_of(text3, "ZZT-YU-3")
    _t, calls3 = bot.say(_pick(n), str(n))
    args3 = _only_report(calls3)

    text4, calls = bot.say(
        _status("sales_report", _ent("yu", "sales_agent"), _ent(PRODUCT, "product"), basis="delivered", **YEAR),
        "sales agent yu total sale for SRTSP231 in 2026",
        spans=_agent_spans(),
    )
    assert calls == [] and WHICH_AGENT in text4, (calls, text4)
    assert CUSTOMER_WITH_YU not in text4, text4
    n4 = _number_of(text4, "ZZT-YU-3")
    _t, calls4 = bot.say(_pick(n4), str(n4))
    args4 = _only_report(calls4)
    drop = {"_diagnostics", "contact_id", "space_id"}
    assert {k: v for k, v in args4.items() if k not in drop} == {k: v for k, v in args3.items() if k not in drop}, (
        args3, args4,
    )


def test_ac_ru_19_a_single_agent_match_runs_at_once_with_the_agent_filter_and_no_customer(bot) -> None:
    """AC-RU-19: when the span pass finds exactly one agent the ask runs, headed by that agent; the word
    "yu" is never put to the customer resolver (G-YU TRADING SDN BHD is not a filter)."""
    one = _status("sales_report", _ent("ZZT-YU-2", "sales_agent", bot.ids["agents"]["ZZT-YU-2"]),
                  _ent(PRODUCT, "product"), basis="delivered", **YEAR)
    text, calls = bot.say(one, "sales agent zzt-yu-2 sales for SRTSP231 in 2026",
                          spans=[list_resolver.Span("ZZT-YU-2", "salesperson")])
    args = _only_report(calls, text)
    assert args["sales_agent_ids"] == [bot.ids["agents"]["ZZT-YU-2"]], args
    assert not args.get("customer_ids"), args


def test_ac_ru_19_a_sales_agent_word_that_matches_a_customer_name_is_never_a_customer_filter(bot) -> None:
    """AC-RU-19: even a bound agent id with a raw word ("yu") that is also a word of a customer name does not
    reach the customer resolver."""
    text, calls = bot.say(
        _status("sales_report", _ent("yu", "sales_agent", bot.ids["agents"]["ZZT-YU-4"]), _ent(PRODUCT, "product"),
                basis="delivered", **YEAR),
        "sales agent yu sales for SRTSP231 in 2026", spans=_agent_spans(),
    )
    args = _only_report(calls, text)
    assert args["sales_agent_ids"] == [bot.ids["agents"]["ZZT-YU-4"]], args
    assert not args.get("customer_ids"), args


# ================================================================ AC-RU-21: a category word never triggers a customer pick


def test_p6_a_category_word_bound_by_the_span_pass_never_triggers_a_customer_pick(bot) -> None:
    """AC-RU-21 / P6 "Total quantity sale for Sorento brand kitchen sink on September 2026": customers with
    KITCHEN in their names exist; no customer question, the category id is in the args."""
    text, calls = bot.say(
        _status(
            "sales_report", _ent("Sorento", "brand"), _ent("kitchen sink", "category", "KITCHEN SINK"),
            basis="delivered", measure="qty", date_filter_start="2026-09-01", date_filter_end="2026-09-30",
        ),
        "Total quantity sale for Sorento brand kitchen sink on September 2026",
        spans=[list_resolver.Span("Sorento", "brand"), list_resolver.Span("kitchen sink", "category")],
    )
    args = _only_report(calls, text)
    assert args["category_ids"] == [bot.ids["sink"]], args
    assert not args.get("customer_ids"), args
    for name in KITCHEN_CUSTOMERS:
        assert name not in text, text
    assert "Which one do you mean?" not in text, text


def test_ac_ru_21_a_category_bound_by_row_id_wins_over_a_raw_word_that_names_no_category(bot) -> None:
    """AC-RU-21 / plan 3.2 (generalised to every kind): canonical_code = the category row id; raw is noise."""
    text, calls = bot.say(
        _status("sales_report", _ent("zzxqv", "category", bot.ids["sink"]), basis="delivered", measure="qty", **YEAR),
        "total quantity zzxqv 2026", spans=[list_resolver.Span("zzxqv", "category")],
    )
    args = _only_report(calls, text)
    assert args["category_ids"] == [bot.ids["sink"]], args


def test_ac_ru_21_a_category_whose_label_differs_from_the_raw_word_binds_by_the_label(bot) -> None:
    """AC-RU-21: canonical "KITCHEN SINK", raw "dapur sink"."""
    text, calls = bot.say(
        _status("sales_report", _ent("dapur sink", "category", "KITCHEN SINK"), basis="delivered", measure="qty", **YEAR),
        "total quantity dapur sink 2026", spans=[list_resolver.Span("dapur sink", "category")],
    )
    args = _only_report(calls, text)
    assert args["category_ids"] == [bot.ids["sink"]], args


# ================================================================ AC-RU-22: no cap cuts an exact match


def _salesperson_rows(n: int) -> list[lookup_lists.LookupRow]:
    return [
        lookup_lists.LookupRow("salesperson", f"zz-id-{i}", f"ZZT-YU-{i}", (f"ZZT-YU-{i}", "yu")) for i in range(1, n + 1)
    ]


def _span_block(rows, spans):
    prep = engine_mod._SpanPrep(
        message="sales agent yu sales", rows=rows, spec_key_rows=[], brand_words=frozenset(), numbers=[], held={},
        embed=None, config=span_extract.SpanConfig("sys", 1, "openai", "gpt-zz", "ZZ-key", "label"),
    )
    answer = span_extract.SpanAnswer(spans, {}, 1)
    with mock.patch.object(span_extract, "extract", return_value=answer):
        return engine_mod._span_lookup(
            prep, session_factory=None, contact_respond_id="ZZ-contact", dry_run=True, turn_id=None
        )


def test_ac_ru_22_every_agent_the_span_pass_matched_for_yu_reaches_the_parser_block() -> None:
    """AC-RU-22: six salesperson rows answer to "yu" exactly: the block printed for the parser lists all six
    (today it stops at TOP_K["salesperson"] = 5)."""
    lines, _lookup, event = _span_block(_salesperson_rows(6), [list_resolver.Span("yu", "salesperson")])
    printed = [ln for ln in lines if ln.startswith("- ")]
    for i in range(1, 7):
        assert any(f"ZZT-YU-{i}" in ln for ln in printed), (i, lines)
    entry = next(s for s in event["spans"] if s["text"] == "yu")
    assert entry["close"] == 6, entry


def test_ac_ru_22_no_cap_cuts_an_exact_match_however_many_there_are() -> None:
    """AC-RU-22: eight exact rows, eight printed."""
    lines, _lookup, _event = _span_block(_salesperson_rows(8), [list_resolver.Span("yu", "salesperson")])
    printed = [ln for ln in lines if ln.startswith("- ")]
    assert len(printed) == 8, lines


def test_ac_ru_22_the_cap_still_bounds_rows_no_span_named_exactly() -> None:
    """AC-RU-22 control: the cap is not removed for rows the message only spells near (no span names them):
    TOP_K["salesperson"] rows at most come from the spelling-only path."""
    rows = [
        lookup_lists.LookupRow("salesperson", f"zz-id-{i}", f"ZZT-YU-{i}", (f"ZZT-YU-{i}",)) for i in range(1, 9)
    ]
    lines, _lookup, _event = _span_block(rows, [])
    printed = [ln for ln in lines if ln.startswith("- ")]
    assert len(printed) <= lookup_lists.TOP_K["salesperson"], lines


def test_ac_ru_22_the_parser_is_shown_every_agent_in_a_whole_turn(bot) -> None:
    """AC-RU-22 on a console turn: the six agents are in the block the parser double receives."""
    _ask_h3(bot)
    block = bot.block()
    for code in AGENT_CODES:
        assert code in block, (code, block)


def test_ac_ru_22_each_candidate_line_carries_the_row_id_the_parser_binds_by(bot) -> None:
    """AC-RU-18 / plan 3.1 (pinned reading): the Brand, Salesperson and Category blocks print each row's id."""
    bot.say(
        _status("sales_report", _ent("mch", "brand", "MOCHA"), _ent("kitchen sink", "category", "KITCHEN SINK"),
                _ent("yu", "sales_agent"), basis="delivered", **YEAR),
        "mch kitchen sink yu sales 2026",
        spans=[list_resolver.Span("mch", "brand"), list_resolver.Span("kitchen sink", "category"),
               list_resolver.Span("yu", "salesperson")],
    )
    block = bot.block()
    assert bot.ids["mocha"] in block, block
    assert bot.ids["sink"] in block, block
    for agent_id in bot.ids["agents"].values():
        assert agent_id in block, block
