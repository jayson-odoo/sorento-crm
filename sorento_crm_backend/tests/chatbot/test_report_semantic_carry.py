"""Phase 2 RED tests: the parser writes the whole report ask each turn (semantic carry, lane SALES-ACCOUNT-TYPE).

`documentation/plans/chatbot/report-semantic-carry-acceptance-criteria.md` SC-1 to SC-6 and SC-8 to SC-14,
plan `PLAN-report-semantic-carry-2nov.md` (rules R1 to R3, value checks V1 to V5).

Contract pinned here (nothing else is assumed):
* `parser.REPORT_ASK_LINE`: a prompt text carrying it makes `ParserConfig.report_ask` True and adds a required,
  nullable `report_ask` object (last in `properties` and `required`) to the strict schema.
* With the flag on and a report held, the user block carries `Held report: ` + compact JSON with the `report_ask`
  keys in order, names never ids; while a field question is open the prefix is
  `Held report (open question: <basis|period|count|company|brand or account type|sales agent>): `.
* With the flag on and a verdict carrying a non-null `report_ask`, the lane builds the report from the object and
  applies only value checks. The OLD flat fields in the fake verdicts below are the noisy ones the live parser
  really emitted (copied from the abandoned #2092 tests): the object must win over them.

Real engine, report lane and MCP presenter (`bot.say(verdict, message) -> (reply, tool_calls)` of
`test_report_unify_routing`); only the parser verdict and the MCP transport are doubles. Invented data only.
The `REPORT_ASK_LINE` name is read with `getattr` so one missing name fails its own tests, not the whole file.
"""
from __future__ import annotations

import dataclasses
import json
import re
import uuid
from typing import Any

import pytest

from app.services.chatbot.head import closed_lists_prompt
from app.services.chatbot.head import parser as parser_mod
from app.models.product import Brand, ProductCategory
from app.models.sales_agent import SalesAgent
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID
from tests.chatbot.test_chat_state_parser_input import (  # noqa: F401 - fixture + helper
    _fresh_prompt_cache,
    _resolve,
)
from tests.chatbot.test_report_ask_lane import CUSTOMER_NAME, PRODUCT_CODE, _e
from tests.chatbot.test_report_unify_company_lane import _two_companies
from tests.chatbot.test_report_unify_routing import Routing, _status, bot, console
from tests.chatbot.test_sales_account_type_lane import BASIS_Q, BOOK, QUESTION, _ledger

_FIXTURES = (bot, console, _fresh_prompt_cache)

LINE = getattr(parser_mod, "REPORT_ASK_LINE", "== ZZT REPORT ASK LINE PLACEHOLDER (contract name missing) ==")
TOOL = "crm_report_ask"
KEYS = [
    "kind", "basis", "date_from", "date_to", "group_by", "top_n", "measure", "channel", "company", "sales_agents",
    "account_types", "brands", "categories", "customers", "products", "brand_or_account_type",
]
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
CLOSED = "Rules {{current_date}}.\n" + closed_lists_prompt.MARKER + "\nlisted items.\n"
PLAIN = "Rules {{current_date}}.\nlisted items.\n"


AGENT_1 = "AGENT A"  # Sorento only
AGENT_2 = "AGENT B"  # a code in both companies
AGENT_M = "AGENT M"  # Mocha only
MOCHA_ONLY_TYPE = "ZZTMOCHATYPE"


@pytest.fixture
def world(bot) -> tuple[str, str]:
    """Two companies (the contact holds both). Sorento: AGENT A, AGENT B, brands Cabana + Sorento, types CABANA +
    CERAMIC. Mocha: AGENT B, AGENT M, types CERAMIC + one of its own. Returns (Sorento's name, Mocha's name)."""
    sorento, mocha = _two_companies(bot)
    db = bot.console.session_factory()
    try:
        for name, company in ((AGENT_2, DEFAULT_COMPANY_ID), (AGENT_2, MOCHA_ID), (AGENT_M, MOCHA_ID)):
            row = SalesAgent(id=str(uuid.uuid4()), sales_agent=name, company_id=company)
            db.add(row)
            bot.ids[f"{name}:{company}"] = row.id
        for code, name in (("CABANA", "Cabana"), ("SORENTO", "Sorento")):
            db.add(Brand(id=str(uuid.uuid4()), brand_code=code, brand_name=name, company_id=DEFAULT_COMPANY_ID))
        db.flush()
        for name, dtype in BOOK:
            _ledger(db, DEFAULT_COMPANY_ID, name, dtype)
        _ledger(db, MOCHA_ID, "ZZT MOCHA LEDGER ONE [A/C III]", "CERAMIC")
        _ledger(db, MOCHA_ID, "ZZT MOCHA LEDGER TWO [A/C IX]", MOCHA_ONLY_TYPE)
        db.commit()
    finally:
        db.close()
    return sorento, mocha


def agent_b_sorento(bot_: Routing) -> str:
    return bot_.ids[f"{AGENT_2}:{DEFAULT_COMPANY_ID}"]


# ------------------------------------------------------------------------------------------ SC-1, SC-2 (schema)


def _schema(config):
    return config.json_schema or parser_mod._base_schema(config)


def _baseline() -> dict:
    return parser_mod.without_by_words(parser_mod.without_report_fields(parser_mod.PARSE_OUTPUT_JSON_SCHEMA))


def _nullable_object(prop: dict) -> bool:
    types = prop.get("type")
    if isinstance(types, list):
        return "object" in types and "null" in types
    kinds = [o.get("type") for o in (prop.get("anyOf") or prop.get("oneOf") or [])]
    return "object" in kinds and "null" in kinds


def _object_part(prop: dict) -> dict:
    if prop.get("type") in ("object", ["object", "null"], ["null", "object"]):
        return prop
    return next(o for o in (prop.get("anyOf") or prop.get("oneOf")) if o.get("type") == "object")


@pytest.mark.parametrize("base", [CLOSED, PLAIN], ids=["closed_lists", "plain"])
def test_sc1_the_marker_line_turns_the_flag_on_and_adds_a_strict_report_ask_object(monkeypatch, session_factory, base) -> None:
    assert hasattr(parser_mod, "REPORT_ASK_LINE"), "contract: parser.REPORT_ASK_LINE is missing"
    config = _resolve(monkeypatch, session_factory, base + LINE + "\nsection text\n")
    assert getattr(config, "report_ask", None) is True, "ParserConfig.report_ask is not True for a text with the marker"
    schema = _schema(config)
    assert "report_ask" in schema["properties"] and "report_ask" in schema["required"]
    assert list(schema["properties"])[-1] == "report_ask" and schema["required"][-1] == "report_ask", "report_ask must be last"
    prop = schema["properties"]["report_ask"]
    assert _nullable_object(prop), prop
    inner = _object_part(prop)
    assert inner.get("additionalProperties") is False, inner
    assert set(inner["properties"]) == set(KEYS), sorted(set(inner["properties"]) ^ set(KEYS))
    assert set(inner.get("required", [])) == set(KEYS), "every key is required (strict mode)"
    if base is PLAIN:
        stripped = json.loads(json.dumps(schema))
        stripped["properties"].pop("report_ask")
        stripped["required"].remove("report_ask")
        assert json.dumps(stripped, sort_keys=True) == json.dumps(_baseline(), sort_keys=True)


@pytest.mark.parametrize("base", [CLOSED, PLAIN], ids=["closed_lists", "plain"])
def test_sc2_a_text_without_the_marker_keeps_todays_schema(monkeypatch, session_factory, base) -> None:
    assert hasattr(parser_mod, "REPORT_ASK_LINE"), "contract: parser.REPORT_ASK_LINE is missing"
    config = _resolve(monkeypatch, session_factory, base + "section text\n")
    assert getattr(config, "report_ask", None) is False, "ParserConfig.report_ask must exist and be False without the marker"
    schema = _schema(config)
    assert "report_ask" not in schema["properties"] and "report_ask" not in schema["required"]
    if base is PLAIN:
        assert json.dumps(schema, sort_keys=True) == json.dumps(_baseline(), sort_keys=True)


# ------------------------------------------------------------------------------------------ harness


def _flag_on(c, monkeypatch) -> None:
    """The harness config with the flag on (and the marker in the prompt text)."""
    def _cfg(db, *, current_date, override_version_id=None):
        base = parser_mod.ParserConfig(
            system_prompt="stub\n" + LINE + "\n", prompt_version=39, provider="openai", model="gpt-test", api_key="sk-test",
        )
        if "report_ask" in {f.name for f in dataclasses.fields(base)}:
            base = dataclasses.replace(base, report_ask=True)
        return base

    monkeypatch.setattr(parser_mod, "resolve_config", _cfg)


def _record_blocks(bot_: Routing, monkeypatch) -> None:
    """Keep every user block the parser receives (`bot_.blocks`); wraps the `parse` double `Routing.say` installs."""
    from app.services.chatbot import console_service

    bot_.blocks = []  # type: ignore[attr-defined]
    real = console_service.run_console_turn

    def _run(*a, **k):
        current = parser_mod.parse
        hook = getattr(bot_, "on_block", None)
        monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: (bot_.blocks.append(user_block), hook(user_block) if hook else None, current(config, user_block))[2])  # type: ignore[attr-defined]
        return real(*a, **k)

    monkeypatch.setattr(console_service, "run_console_turn", _run)


@pytest.fixture
def rbot(bot, monkeypatch) -> Routing:
    """Staff contact, flag on, user blocks recorded."""
    _flag_on(bot.console, monkeypatch)
    _record_blocks(bot, monkeypatch)
    return bot


@pytest.fixture
def rdealer(console, monkeypatch) -> Routing:
    from tests.chatbot.test_report_ask_lane import _link_dealer

    _link_dealer(console)
    _flag_on(console, monkeypatch)
    b = Routing(console)
    _record_blocks(b, monkeypatch)
    return b


def _ra(**over: Any) -> dict[str, Any]:
    """The parser's `report_ask` object, every key present, in contract order."""
    base: dict[str, Any] = dict(
        kind="sales", basis=None, date_from=None, date_to=None, group_by=None, top_n=None, measure=None, channel=None,
        company=None, sales_agents=[], account_types=[], brands=[], categories=[], customers=[], products=[],
        brand_or_account_type=[],
    )
    base.update(over)
    assert list(base) == KEYS, "test bug: report_ask keys out of order"
    return base


Y = {"date_from": "2026-01-01", "date_to": "2026-12-31"}


def _v(status: str, ra: dict[str, Any] | None, *entities: dict[str, Any], **over: Any) -> dict[str, Any]:
    """A verdict: the noisy OLD flat fields (defaults like the live parser) plus the `report_ask` object."""
    base: dict[str, Any] = dict(
        basis=None, sales_basis=None, group_by=None, entity_op="replace_combine", continuation=None, ranking_refine=None,
        topic_reset=False, sales_company=None, domain_in_message=False, date_filter_start=None, date_filter_end=None,
        report_ask=ra,
    )
    base.update(over)
    return _status(status, *entities, **base)


def _ran(calls) -> list[dict[str, Any]]:
    return [a for n, a in calls if n == TOOL]


def _held_line(block: str) -> tuple[str, dict[str, Any]]:
    """The one `Held report` line of a user block: (its prefix, the JSON after it)."""
    lines = [ln for ln in block.splitlines() if ln.startswith("Held report")]
    assert len(lines) == 1, f"want exactly one 'Held report' line, got {len(lines)} in:\n{block}"
    head, _, tail = lines[0].partition("): ") if lines[0].startswith("Held report (") else lines[0].partition(": ")
    prefix = lines[0][: len(lines[0]) - len(tail)]
    return prefix, json.loads(tail)


def _agent_pick(position: int) -> dict[str, Any]:
    return {"mode": "pick", "items": [], "picked": [position], "qty_for_all": None}


# ------------------------------------------------------------------------------------------ SC-3, SC-4, SC-5 (held line)


def _first_full_report(b: Routing, sorento: str):
    ra = _ra(
        basis="invoiced", group_by="month", channel="dealer", company=sorento, sales_agents=[AGENT_1], brands=["Sorento"],
        categories=["ZZT CATEGORY"], customers=[CUSTOMER_NAME], products=[PRODUCT_CODE], **Y,
    )
    v = _v(
        "sales_analysis", ra, _e(AGENT_1, "sales_agent"), _e("Sorento", "brand"), _e("ZZT CATEGORY", "category"),
        _e(CUSTOMER_NAME, "customer"), _e(PRODUCT_CODE, "product"), basis="invoiced", sales_basis="invoiced",
        group_by="month", sales_channel="dealer", sales_company=sorento, domain_in_message=True,
        date_filter_start="2026-01-01", date_filter_end="2026-12-31",
    )
    return b.say(v, "sorento dealer sales by month 2026 invoiced for agent a sorento zzt category zzt customer and the product")


def test_sc3_the_user_block_after_a_report_carries_one_held_line_in_words(rbot, world) -> None:
    sorento, _mocha = world
    text, calls = _first_full_report(rbot, sorento)
    assert _ran(calls), f"setup: the first report did not run: {text!r}"
    follow = _v("sales_analysis", _ra(basis="invoiced", **Y), continuation=True, entity_op="reuse")
    rbot.say(follow, "and again")
    block = rbot.blocks[-1]
    prefix, held = _held_line(block)
    assert prefix == "Held report: ", prefix
    assert list(held) == KEYS, list(held)
    assert held["kind"] == "sales" and held["basis"] == "invoiced", held
    assert held["date_from"] == "2026-01-01" and held["date_to"] == "2026-12-31", held
    assert held["group_by"] == "month" and held["channel"] == "dealer", held
    assert held["company"] == sorento, held
    assert held["sales_agents"] == [AGENT_1], held
    assert held["brands"] == ["Sorento"] and held["categories"] == ["ZZT CATEGORY"], held
    assert held["customers"] == [CUSTOMER_NAME] and held["products"] == [PRODUCT_CODE], held
    assert held["account_types"] == [] and held["brand_or_account_type"] == [], held
    assert not UUID_RE.search(block.split("Held report")[1].splitlines()[0]), "an id leaked into the Held report line"
    for ids in (v for k, v in rbot.ids.items() if isinstance(v, str)):
        assert ids not in block.split("Held report")[1].splitlines()[0], "a row id leaked into the Held report line"


def test_sc3_a_flag_off_user_block_has_no_held_line(bot, monkeypatch, world) -> None:
    sorento, _mocha = world
    _record_blocks(bot, monkeypatch)  # the harness config: flag off
    text, calls = _first_full_report(bot, sorento)
    bot.say(_v("sales_analysis", None, continuation=True, entity_op="reuse", sales_basis="invoiced", **{"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}), "and again")
    assert all("Held report" not in b for b in bot.blocks), "flag off: the user block must not carry a Held report line"


def test_sc4_an_open_basis_question_is_named_in_the_held_line(rbot, world) -> None:
    sorento, _mocha = world
    first = _v("sales_report", _ra(sales_agents=[AGENT_1], company=sorento, **Y), _e(AGENT_1, "sales_agent"), sales_company=sorento, domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31")
    text, calls = rbot.say(first, "sorento sales for agent a 2026")
    assert calls == [] and text.strip() == BASIS_Q, f"setup: want the basis question, got {text!r}"
    rbot.say(_v("sales_report", _ra(basis="invoiced", sales_agents=[AGENT_1], company=sorento, **Y), basis="invoiced", continuation=True), "invoiced")
    prefix, held = _held_line(rbot.blocks[-1])
    assert prefix == "Held report (open question: basis): ", prefix
    assert held["sales_agents"] == [AGENT_1] and held["company"] == sorento and held["basis"] is None, held
    assert not UUID_RE.search(prefix), prefix


def test_sc4_an_open_period_question_is_named_in_the_held_line(rbot, world) -> None:
    sorento, _mocha = world
    first = _v("sales_report", _ra(basis="invoiced", sales_agents=[AGENT_1], company=sorento), _e(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True)
    text, calls = rbot.say(first, "sorento invoiced sales for agent a")
    assert calls == [] and "Which period?" in text, f"setup: want the period question, got {text!r}"
    rbot.say(_v("sales_report", _ra(basis="invoiced", sales_agents=[AGENT_1], company=sorento, **Y), continuation=True), "2026")
    prefix, held = _held_line(rbot.blocks[-1])
    assert prefix == "Held report (open question: period): ", prefix
    assert held["sales_agents"] == [AGENT_1] and held["date_from"] is None, held


def test_sc4_an_open_count_question_is_named_in_the_held_line(rbot, world) -> None:
    sorento, _mocha = world
    first = _v(
        "sales_ranking", _ra(basis="invoiced", group_by="customer", measure="amount", company=sorento, **Y),
        basis="invoiced", group_by="customer", measure="amount", rank_direction="top", sales_company=sorento, domain_in_message=True,
        date_filter_start="2026-01-01", date_filter_end="2026-12-31",
    )
    text, calls = rbot.say(first, "sorento customers ranking 2026 invoiced")
    assert calls == [] and "How many?" in text, f"setup: want the count question, got {text!r}"
    rbot.say(_v("sales_ranking", _ra(basis="invoiced", group_by="customer", top_n=5, measure="amount", company=sorento, **Y), continuation=True), "5")
    prefix, held = _held_line(rbot.blocks[-1])
    assert prefix == "Held report (open question: count): ", prefix
    assert held["group_by"] == "customer" and held["top_n"] is None, held


def test_sc4_an_open_brand_or_account_type_question_is_named_in_the_held_line(rbot, world) -> None:
    sorento, _mocha = world
    first = _v("sales_report", _ra(basis="invoiced", sales_agents=[AGENT_1], brand_or_account_type=["cabana"], **Y), _e(AGENT_1, "sales_agent"), basis="invoiced", domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31")
    text, calls = rbot.say(first, "sales for agent a for cabana 2026 invoiced")
    assert calls == [] and text.strip() == QUESTION, f"setup: want {QUESTION!r}, got {text!r}"
    rbot.say(_v("sales_report", _ra(basis="invoiced", sales_agents=[AGENT_1], account_types=["cabana"], **Y), continuation=True), "account type")
    prefix, held = _held_line(rbot.blocks[-1])
    assert prefix == "Held report (open question: brand or account type): ", prefix
    assert held["brand_or_account_type"] == ["cabana"] and held["sales_agents"] == [AGENT_1], held


def test_sc5_a_held_name_carried_back_runs_with_the_same_agent_id(rbot, world) -> None:
    sorento, _mocha = world
    text, calls = _first_full_report(rbot, sorento)
    first = _ran(calls)
    assert first, f"setup: the first report did not run: {text!r}"
    ra = _ra(basis="invoiced", group_by="month", company=sorento, sales_agents=[AGENT_1], brands=["Sorento"], categories=["ZZT CATEGORY"], customers=[CUSTOMER_NAME], products=[PRODUCT_CODE], channel="dealer", **Y)
    text, calls = rbot.say(_v("sales_analysis", ra, continuation=True, entity_op="reuse", sales_basis="invoiced"), "same again")
    ran = _ran(calls)
    assert ran, f"the carried-back object did not run: {text!r}"
    assert ran[0].get("sales_agent_ids") == first[0].get("sales_agent_ids") == [rbot.ids["agent"]], (first[0], ran[0])
    assert ran[0].get("customer_ids") == first[0].get("customer_ids"), (first[0], ran[0])


# ------------------------------------------------------------------------------------------ SC-6 (the owner's 14 turns)


def _ent(raw: str, hint: str, code: Any = None, kind: Any = None, current: bool = True) -> dict[str, Any]:
    return {"raw": raw, "hint": hint, "canonical_code": code, "kind_said": kind, "current_message": current, "confident": True}


def _pick_of(position: int) -> dict[str, Any]:
    return {"mode": "pick", "items": [], "picked": [position], "qty_for_all": None}


def _turns(sorento: str) -> list[tuple[int, str, dict[str, Any], dict[str, Any] | None]]:
    """(turn, message, verdict, expectation). Expectation: {"ask": text} for a question, else {"ran": {slot: value}}.
    The flat fields are the OLD live shapes (#2092 tests); the report_ask object is what the owner expects."""
    inv = dict(basis="invoiced", **Y)
    sn = {"company": sorento}
    return [
        (1, "sales for agent a for cabana 2026",
         _v("sales_report", _ra(sales_agents=[AGENT_1], brand_or_account_type=["cabana"], **Y), _ent(AGENT_1, "sales_agent"), _ent("cabana", "brand", "CABANA"), domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31"),
         {"ask": BASIS_Q}),
        (2, "ivoiced",
         _v("sales_ranking", _ra(sales_agents=[AGENT_1], brand_or_account_type=["cabana"], **inv), basis="invoiced", entity_op="reuse", continuation=True, open_question_answer=_pick_of(1)),
         {"ask": QUESTION}),
        (3, "account type",
         _v("sales_ranking", _ra(sales_agents=[AGENT_1], account_types=["cabana"], **inv), basis="invoiced", group_by="account_type", entity_op="reuse", continuation=True, ranking_refine=True, open_question_answer=_pick_of(2)),
         {"ran": {"account_types": ["CABANA"], "basis": "invoiced", "date_from": "2026-01-01", "date_to": "2026-12-31", "group_by": None, "agent": "a"}}),
        (4, "breka down by month",
         _v("sales_analysis", _ra(sales_agents=[AGENT_1], account_types=["cabana"], group_by="month", **inv), sales_basis="invoiced", group_by="month", entity_op="modify", continuation=True, domain_in_message=True),
         {"ran": {"account_types": ["CABANA"], "group_by": "month", "basis": "invoiced", "date_from": "2026-01-01", "agent": "a"}}),
        (5, "for ceramic",
         _v("sales_analysis", _ra(sales_agents=[AGENT_1], account_types=["ceramic"], group_by="month", **inv), _ent("ceramic", "account_type"), sales_basis="invoiced", group_by="month", continuation=True, ranking_refine=True),
         {"ran": {"account_types": ["CERAMIC"], "group_by": "month", "basis": "invoiced", "date_from": "2026-01-01", "agent": "a"}}),
        (6, "for slaes agent b",
         _v("sales_analysis", _ra(sales_agents=[AGENT_2], account_types=["ceramic"], group_by="month", **inv), _ent(AGENT_2, "sales_agent"), sales_basis="invoiced", group_by="month", continuation=True),
         {"ran": {"account_types": ["CERAMIC"], "group_by": "month", "basis": "invoiced", "date_from": "2026-01-01", "agent": "b_any", "no_company": True}}),
        (7, "this year",
         _v("sales_analysis", _ra(sales_agents=[AGENT_2], account_types=["ceramic"], group_by="month", **inv), _ent(AGENT_2, "sales_agent", current=False), sales_basis="invoiced", group_by="month", entity_op="reuse", continuation=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31"),
         {"ran": {"account_types": ["CERAMIC"], "group_by": "month", "basis": "invoiced", "date_from": "2026-01-01", "date_to": "2026-12-31", "agent": "b_any", "no_company": True}}),
        (8, "sorento",
         _v("sales_ranking", _ra(sales_agents=[AGENT_2], account_types=["ceramic"], group_by="month", **sn, **inv), entity_op="reuse", continuation=True, open_question_answer=_pick_of(1), escalation={"company_pick": sorento, "is_escalation_confirmation": False}),
         {"ran": {"company": DEFAULT_COMPANY_ID, "account_types": ["CERAMIC"], "group_by": "month", "basis": "invoiced", "date_from": "2026-01-01", "date_to": "2026-12-31", "agent": "b"}}),
        (9, "for slaes agent b",
         _v("sales_analysis", _ra(sales_agents=[AGENT_2], account_types=["ceramic"], group_by="month", **sn, **inv), _ent(AGENT_2, "sales_agent"), group_by="month", sales_company=sorento, domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31"),
         {"ran": {"company": DEFAULT_COMPANY_ID, "account_types": ["CERAMIC"], "group_by": "month", "basis": "invoiced", "date_from": "2026-01-01", "agent": "b"}}),
        (10, "invoiced",
         _v("sales_ranking", _ra(sales_agents=[AGENT_2], account_types=["ceramic"], group_by="month", **sn, **inv), basis="invoiced", entity_op="reuse", continuation=True),
         {"ran": {"company": DEFAULT_COMPANY_ID, "account_types": ["CERAMIC"], "group_by": "month", "basis": "invoiced", "date_from": "2026-01-01", "agent": "b"}}),
        (11, "for ceramic account ty[e",
         _v("sales_analysis", _ra(sales_agents=[AGENT_2], account_types=["ceramic"], group_by="month", **sn, **inv), _ent("ceramic", "account_type", None, "account type"), sales_basis="invoiced", group_by="month", continuation=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31"),
         {"ran": {"company": DEFAULT_COMPANY_ID, "account_types": ["CERAMIC"], "group_by": "month", "agent": "b"}}),
        (12, "sorento",
         _v("sales_analysis", _ra(sales_agents=[AGENT_2], account_types=["ceramic"], group_by="month", **sn, **inv), _ent("sorento", "brand", "SORENTO"), basis="invoiced", sales_basis="invoiced", group_by="month", continuation=True, sales_company=sorento, open_question_answer=_pick_of(1)),
         {"ran": {"company": DEFAULT_COMPANY_ID, "account_types": ["CERAMIC"], "group_by": "month", "agent": "b", "no_brand": True}}),
        (13, "ceramic accoutn type",
         _v("sales_analysis", _ra(sales_agents=[AGENT_2], account_types=["ceramic"], group_by="month", **sn, **inv), _ent("ceramic", "account_type", None, "account type"), sales_basis="invoiced", group_by="month", continuation=True),
         {"ran": {"company": DEFAULT_COMPANY_ID, "account_types": ["CERAMIC"], "group_by": "month", "basis": "invoiced", "date_from": "2026-01-01", "date_to": "2026-12-31", "agent": "b"}}),
        (14, "breakd down by month, only sales agent b",
         _v("sales_analysis", _ra(sales_agents=[AGENT_2], account_types=["ceramic"], group_by="month", **sn, **inv), _ent(AGENT_2, "sales_agent"), sales_basis="invoiced", group_by="month", continuation=True, sales_company=sorento, domain_in_message=True),
         {"ran": {"company": DEFAULT_COMPANY_ID, "account_types": ["CERAMIC"], "group_by": "month", "basis": "invoiced", "date_from": "2026-01-01", "date_to": "2026-12-31", "agent": "b"}}),
    ]


def test_sc6_the_owners_fourteen_turns_hold_slot_by_slot(rbot, world) -> None:
    sorento, mocha = world
    problems: list[str] = []
    for turn, message, verdict, want in _turns(sorento):
        text, calls = rbot.say(verdict, message)
        ran = _ran(calls)
        if "ask" in want:
            if ran or text.strip() != want["ask"]:
                problems.append(f"turn {turn} {message!r}: want the question {want['ask']!r}, got {'ran ' + str(ran[0]) if ran else repr(text.strip())}")
            continue
        if len(ran) != 1:
            problems.append(f"turn {turn} {message!r}: the report did not run, the bot said {text.strip()!r}")
            continue
        args, slots = ran[0], dict(want["ran"])
        agent = slots.pop("agent", None)
        no_brand = slots.pop("no_brand", False)
        no_company = slots.pop("no_company", False)
        if no_company and args.get("company"):
            problems.append(f"turn {turn} {message!r}: a company arg {args.get('company')!r} was sent, the ask named none")
        for slot, value in slots.items():
            if args.get(slot) != value:
                problems.append(f"turn {turn} {message!r}: slot {slot!r} is {args.get(slot)!r}, want {value!r}")
        if agent:
            ids = args.get("sales_agent_ids") or []
            b_rows = {agent_b_sorento(rbot), rbot.ids[f"{AGENT_2}:{MOCHA_ID}"]}
            if agent == "a":
                ok = ids == [rbot.ids["agent"]]
            elif agent == "b_any":  # no company named: whatever the word resolution gives, but only AGENT B rows
                ok = bool(ids) and set(ids) <= b_rows
            else:
                ok = agent_b_sorento(rbot) in ids and rbot.ids[f"{AGENT_2}:{MOCHA_ID}"] not in ids
            if not ok:
                problems.append(f"turn {turn} {message!r}: slot 'sales_agent_ids' is {ids!r}, want agent {agent} (AGENT B rows only, Sorento's alone from turn 8)")
        if no_brand and args.get("brand_ids"):
            problems.append(f"turn {turn} {message!r}: the company word became a brand filter {args.get('brand_ids')}")
        if f"{sorento} or {mocha}?" in text or "brand or account type?" in text:
            problems.append(f"turn {turn} {message!r}: asked a company or brand-or-account-type question")
    assert not problems, "\n".join(problems)


# ------------------------------------------------------------------------------------------ SC-8 (restated ask)


def test_sc8_a_restated_product_ask_runs_every_channel_and_the_header_says_so(rbot, world) -> None:
    sorento, _mocha = world
    rbot.extra_body = {"filters": [{"key": "channel", "label": "Channel", "values": ["Dealer"]}]}
    first = _v(
        "sales_analysis", _ra(basis="invoiced", channel="dealer", company=sorento, products=[PRODUCT_CODE], date_from="2026-05-01", date_to="2026-05-31"),
        _e(PRODUCT_CODE, "product"), sales_channel="dealer", sales_company=sorento, basis="invoiced", domain_in_message=True,
        date_filter_start="2026-05-01", date_filter_end="2026-05-31",
    )
    text, calls = rbot.say(first, f"{PRODUCT_CODE} dealer sales may 2026")
    args = _ran(calls)
    assert args, f"turn 1 did not run: {text.strip()!r}"
    assert args[0].get("channel") == "dealer" and args[0].get("product_code") == PRODUCT_CODE, args[0]
    assert args[0].get("date_from") == "2026-05-01" and args[0].get("date_to") == "2026-05-31", args[0]
    rbot.extra_body = {}
    second = _v(
        "sales_report", _ra(basis="invoiced", company=sorento, products=[PRODUCT_CODE], **Y), _e(PRODUCT_CODE, "product"),
        sales_company=sorento, domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31",
    )
    text, calls = rbot.say(second, f"{PRODUCT_CODE} sales 2026")
    args = _ran(calls)
    assert args, f"turn 2 did not run: {text.strip()!r}"
    assert args[0].get("product_code") == PRODUCT_CODE and args[0].get("basis") == "invoiced", args[0]
    assert args[0].get("date_from") == "2026-01-01" and args[0].get("date_to") == "2026-12-31", args[0]
    assert not args[0].get("channel"), f"the restated ask kept the channel: {args[0]}"
    assert "Dealer" not in text, f"the reply header still names the dealer channel: {text!r}"


# ------------------------------------------------------------------------------------------ SC-9 .. SC-13 (rails)


def test_sc9_an_object_basis_not_said_and_not_held_asks_the_basis(rbot, world) -> None:
    sorento, _mocha = world
    v = _v("sales_report", _ra(basis="invoiced", sales_agents=[AGENT_1], company=sorento, **Y), _e(AGENT_1, "sales_agent"), sales_company=sorento, domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31")
    text, calls = rbot.say(v, "sorento sales for agent a 2026")
    assert not _ran(calls), f"the object's basis ran though neither the message nor a held report said it: {calls}"
    assert text.strip() == BASIS_Q, text


def test_sc9_a_basis_the_held_report_already_has_carries_without_a_question(rbot, world) -> None:
    sorento, _mocha = world
    first = _v("sales_report", _ra(basis="invoiced", sales_agents=[AGENT_1], company=sorento, **Y), _e(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31")
    text, calls = rbot.say(first, "sorento invoiced sales for agent a 2026")
    assert _ran(calls), f"setup: {text!r}"
    again = _v("sales_analysis", _ra(basis="invoiced", sales_agents=[AGENT_1], group_by="month", company=sorento, **Y), group_by="month", continuation=True, entity_op="modify", domain_in_message=True)
    text, calls = rbot.say(again, "by month")
    assert text.strip() != BASIS_Q and _ran(calls), f"the held basis was asked again: {text!r}"
    assert _ran(calls)[0].get("basis") == "invoiced" and _ran(calls)[0].get("group_by") == "month", _ran(calls)


def test_sc10_an_object_company_the_contact_does_not_hold_is_the_forbidden_line(rbot, world) -> None:
    from app.services.chatbot.lanes.business import report_ask

    v = _v("sales_report", _ra(basis="invoiced", company="Zzt Foreign Trading", **Y), basis="invoiced", sales_company="Zzt Foreign Trading", domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31")
    text, calls = rbot.say(v, "zzt foreign trading sales 2026 invoiced")
    assert not _ran(calls) and text.strip() == report_ask.COMPANY_FORBIDDEN_LINE, (calls, text)


def test_sc10_two_companies_and_nothing_naming_one_runs_over_every_company(rbot, world) -> None:
    """O-R2 (was: the company question): no company named -> runs with no `company` arg, never asks "<A> or <B>?"."""
    sorento, mocha = world
    v = _v("sales_report", _ra(basis="invoiced", **Y), basis="invoiced", domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31")
    text, calls = rbot.say(v, "sales 2026 invoiced")
    assert f"{sorento} or {mocha}?" not in text, f"O-R2: the company question was asked: {text!r}"
    assert _ran(calls) and "company" not in _ran(calls)[0], f"O-R2: want a run with no company arg, got {calls} {text!r}"


def test_sc10_an_outstanding_ask_never_asks_the_company(rbot, world) -> None:
    sorento, mocha = world
    v = _v("outstanding", _ra(kind="outstanding", basis="outstanding", sales_agents=[]), basis="outstanding", domain_in_message=True)
    text, calls = rbot.say(v, "undelivered orders")
    assert f"{sorento} or {mocha}?" not in text, text
    assert _ran(calls) and _ran(calls)[0].get("basis") == "outstanding", (calls, text)


def test_sc11_a_dealer_objects_ask_outside_its_own_customer_is_refused(rdealer) -> None:
    from app.services.chatbot.lanes.business import report_ask

    v = _v("sales_report", _ra(basis="invoiced", sales_agents=[AGENT_1], **Y), _e(AGENT_1, "sales_agent"), basis="invoiced", domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31")
    text, calls = rdealer.say(v, "sales for agent a 2026 invoiced")
    assert not _ran(calls) and text.strip() == report_ask.DEALER_REFUSAL, (calls, text)


def test_sc12_a_word_in_both_tables_left_unsure_asks_brand_or_account_type(rbot, world) -> None:
    sorento, _mocha = world
    v = _v("sales_report", _ra(basis="invoiced", company=sorento, brand_or_account_type=["cabana"], **Y), _ent("cabana", "brand", "CABANA"), basis="invoiced", sales_company=sorento, domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31")
    text, calls = rbot.say(v, "sorento cabana sales 2026 invoiced")
    assert not _ran(calls) and text.strip() == QUESTION, (calls, text)


def test_sc12_a_word_in_one_table_only_goes_to_that_table_with_no_question(rbot, world) -> None:
    sorento, _mocha = world
    v = _v("sales_report", _ra(basis="invoiced", company=sorento, brand_or_account_type=["ceramic"], **Y), basis="invoiced", sales_company=sorento, domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31")
    text, calls = rbot.say(v, "sorento ceramic sales 2026 invoiced")
    assert "brand or account type?" not in text, text
    ran = _ran(calls)
    assert ran and ran[0].get("account_types") == ["CERAMIC"] and not ran[0].get("brand_ids"), (calls, text)


def test_sc13_an_agent_name_matching_several_agents_is_the_agent_pick(rbot, world) -> None:
    sorento, _mocha = world
    db = rbot.console.session_factory()
    try:
        for code in ("ZZT-TWIN-1", "ZZT-TWIN-2"):
            db.add(SalesAgent(id=str(uuid.uuid4()), sales_agent=code, aliases="twin", company_id=DEFAULT_COMPANY_ID))
        db.commit()
    finally:
        db.close()
    v = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=["twin"], **Y), _e("twin", "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, date_filter_start="2026-01-01", date_filter_end="2026-12-31")
    text, calls = rbot.say(v, "sorento sales agent twin 2026 invoiced")
    assert not _ran(calls) and "Which sales agent?" in text and "ZZT-TWIN-1" in text and "ZZT-TWIN-2" in text, (calls, text)


def test_sc13_no_period_in_the_object_asks_the_period(rbot, world) -> None:
    sorento, _mocha = world
    v = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1]), _e(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True)
    text, calls = rbot.say(v, "sorento sales for agent a invoiced")
    assert not _ran(calls) and "Which period?" in text, (calls, text)


def test_sc13_a_ranking_without_a_count_asks_the_count(rbot, world) -> None:
    sorento, _mocha = world
    v = _v(
        "sales_ranking", _ra(basis="invoiced", group_by="customer", measure="amount", company=sorento, **Y), basis="invoiced",
        group_by="customer", measure="amount", rank_direction="top", sales_company=sorento, domain_in_message=True,
        date_filter_start="2026-01-01", date_filter_end="2026-12-31",
    )
    text, calls = rbot.say(v, "sorento customers ranking 2026 invoiced")
    assert not _ran(calls) and "How many?" in text, (calls, text)


# ------------------------------------------------------------------------------------------ V4 (a both-table word, from data)
# Cabana is seeded as a brand AND an account type (`world`). The lane decides from the tables and the message's own
# `kind_said`, not from which bucket the object put the word in (the live parser puts it in `brands`).


def _cabana_ask(sorento: str, *, bucket: str, kind_said: Any, hint: str = "brand", **over: Any) -> dict[str, Any]:
    ra = _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], **{bucket: ["Cabana"]}, **Y)
    return _v(
        "sales_report", ra, _ent("cabana", hint, "CABANA" if hint == "brand" else None, kind_said),
        _ent(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True,
        date_filter_start="2026-01-01", date_filter_end="2026-12-31", **over,
    )


def test_v4a_a_both_table_word_in_brands_with_no_kind_said_asks_brand_or_account_type(rbot, world) -> None:
    sorento, _mocha = world
    text, calls = rbot.say(_cabana_ask(sorento, bucket="brands", kind_said=None), "sorento sales for agent a cabana 2026 invoiced")
    assert not _ran(calls), f"V4a: a report ran for a word both tables hold, kind not said: {_ran(calls)}"
    assert text.strip() == QUESTION, f"V4a: want {QUESTION!r}, got {text!r}"


def test_v4b_a_kind_the_message_said_runs_as_that_kind_with_no_question(rbot, world) -> None:
    sorento, _mocha = world
    text, calls = rbot.say(_cabana_ask(sorento, bucket="brands", kind_said="brand"), "sorento sales for agent a cabana brand 2026 invoiced")
    ran = _ran(calls)
    assert ran and text.strip() != QUESTION, f"V4b brand: asked or did not run: {text!r}"
    assert len(ran[0].get("brand_ids") or []) == 1, ran[0]
    assert not ran[0].get("account_types"), f"V4b brand: also sent account_types: {ran[0]}"


def test_v4b_an_account_type_placement_with_kind_said_account_type_runs_as_account_type(rbot, world) -> None:
    sorento, _mocha = world
    text, calls = rbot.say(
        _cabana_ask(sorento, bucket="account_types", kind_said="account type", hint="account_type"),
        "sorento sales for agent a cabana account type 2026 invoiced",
    )
    ran = _ran(calls)
    assert ran and text.strip() != QUESTION, f"V4b account type: asked or did not run: {text!r}"
    assert ran[0].get("account_types") == ["CABANA"] and not ran[0].get("brand_ids"), ran[0]


def test_v4c_a_carried_settled_word_is_not_asked_again(rbot, world) -> None:
    sorento, _mocha = world
    text, calls = rbot.say(_cabana_ask(sorento, bucket="brands", kind_said="brand"), "sorento sales for agent a cabana brand 2026 invoiced")
    first = _ran(calls)
    assert first and first[0].get("brand_ids"), f"setup: the brand report did not run: {text!r}"
    agent_b = _v(
        "sales_analysis", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_2], brands=["Cabana"], **Y),
        _ent(AGENT_2, "sales_agent"), sales_basis="invoiced", sales_company=sorento, continuation=True,
        date_filter_start="2026-01-01", date_filter_end="2026-12-31",
    )
    text, calls = rbot.say(agent_b, f"for {AGENT_2}")
    ran = _ran(calls)
    assert text.strip() != QUESTION, f"V4c: the settled word was asked again: {text!r}"
    assert ran and ran[0].get("brand_ids") == first[0].get("brand_ids"), f"V4c: the held brand was not carried: {ran or text!r}"


def test_v4d_the_declared_pick_of_account_type_wins_over_the_object_bucket(rbot, world) -> None:
    sorento, _mocha = world
    text, calls = rbot.say(_cabana_ask(sorento, bucket="brands", kind_said=None), "sorento sales for agent a cabana 2026 invoiced")
    assert not _ran(calls) and text.strip() == QUESTION, f"V4d setup: want {QUESTION!r}, got {text!r}"
    reply = _v(
        "sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], brands=["Cabana"], **Y),
        entity_op="reuse", continuation=True, open_question_answer=_pick_of(2),
    )
    text, calls = rbot.say(reply, "account type")
    ran = _ran(calls)
    assert ran, f"V4d: the pick of 'account type' did not run the report: {text!r}"
    assert ran[0].get("account_types") == ["CABANA"] and not ran[0].get("brand_ids"), f"V4d: {ran[0]}"
    assert ran[0].get("sales_agent_ids") == [rbot.ids["agent"]] and ran[0].get("basis") == "invoiced", ran[0]
    assert ran[0].get("date_from") == "2026-01-01" and ran[0].get("company") == DEFAULT_COMPANY_ID, ran[0]


# ------------------------------------------------------------------------------------------ review round
KIND_QUESTION = "Undelivered orders or pending delivery?"
YR = dict(date_filter_start="2026-01-01", date_filter_end="2026-12-31")


def test_b1_a_company_switch_sends_the_new_companys_agent_id(rbot, world) -> None:
    sorento, mocha = world
    first = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_2], **Y), _ent(AGENT_2, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(first, "sorento sales for agent b 2026 invoiced")
    assert _ran(calls)[0].get("sales_agent_ids") == [agent_b_sorento(rbot)], f"setup: {calls}"
    second = _v("sales_report", _ra(basis="invoiced", company=mocha, sales_agents=[AGENT_2], **Y), _ent(AGENT_2, "sales_agent"), sales_company=mocha, continuation=True, **YR)
    text, calls = rbot.say(second, "mocha")
    ran = _ran(calls)
    assert ran, f"B1: the Mocha ask did not run: {text!r}"
    assert ran[0].get("company") == MOCHA_ID, f"B1: company {ran[0].get('company')!r}, want Mocha"
    assert ran[0].get("sales_agent_ids") == [rbot.ids[f"{AGENT_2}:{MOCHA_ID}"]], f"B1: Sorento's AGENT B id was kept: {ran[0].get('sales_agent_ids')}"


def test_b2_a_declared_pick_of_a_basis_option_runs_with_that_basis(rbot, world) -> None:
    sorento, _mocha = world
    first = _v("sales_report", _ra(sales_agents=[AGENT_1], company=sorento, **Y), _ent(AGENT_1, "sales_agent"), sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(first, "sorento sales for agent a 2026")
    assert not calls and text.strip() == BASIS_Q, f"setup: {text!r}"
    reply = _v(
        "sales_report", _ra(basis="invoiced", sales_agents=[AGENT_1], company=sorento, **Y), entity_op="reuse",
        continuation=True, open_question_answer=_pick_of(1), reference_positions=[1],
    )
    text, calls = rbot.say(reply, "the first")
    assert text.strip() != BASIS_Q, "B2: the basis was asked again after the pick"
    ran = _ran(calls)
    assert ran and ran[0].get("basis") == "invoiced", f"B2: want a run with basis invoiced, got {ran or text!r}"


def test_b2_a_declared_pick_of_an_outstanding_kind_runs_with_that_kind(rbot, world) -> None:
    first = _v("outstanding", _ra(kind="outstanding"), domain_in_message=True)
    text, calls = rbot.say(first, "outstanding")
    assert not calls and KIND_QUESTION in text, f"setup: {text!r}"
    reply = _v(
        "outstanding", _ra(kind="outstanding", basis="outstanding"), entity_op="reuse", continuation=True,
        open_question_answer=_pick_of(1), reference_positions=[1],
    )
    text, calls = rbot.say(reply, "the first")
    assert KIND_QUESTION not in text, "B2: the kind was asked again after the pick"
    ran = _ran(calls)
    assert ran and ran[0].get("basis") == "outstanding", f"B2: want a run with basis outstanding, got {ran or text!r}"


def _by_customer(sorento: str, status: str = "sales_report", **over: Any) -> dict[str, Any]:
    return _v(
        status, _ra(basis="invoiced", group_by="customer", measure="amount", company=sorento, **Y),
        basis="invoiced", group_by="customer", measure="amount", rank_direction=None, top_n=None, sales_company=sorento,
        domain_in_message=True, **YR, **over,
    )


def test_b3_a_fresh_breakdown_by_customer_runs_every_row_as_flag_off_does(bot, monkeypatch, world) -> None:
    sorento, _mocha = world
    text, calls = bot.say(_by_customer(sorento), "sales by customer by amount")  # flag off (the harness config)
    off = _ran(calls)
    assert off and off[0].get("top_n") == 100, f"baseline: flag off should run every row, got {off or text!r}"
    bot.console.session_vars = {}
    _flag_on(bot.console, monkeypatch)
    text, calls = bot.say(_by_customer(sorento), "sales by customer by amount")
    on = _ran(calls)
    assert "How many?" not in text, f"B3(i): a breakdown asked a count: {text!r}"
    assert on and on[0].get("top_n") == off[0].get("top_n") and on[0].get("group_by") == "customer", f"B3(i): flag on {on or text!r}, flag off {off[0].get('top_n')}"


def test_b3_iii_the_usual_ranking_read_of_by_customer_runs_every_row_as_flag_off_does(bot, monkeypatch, world) -> None:
    """The reviewer's probe: order_status sales_ranking, rank_direction null, top_n null, object measure amount."""
    sorento, _mocha = world
    text, calls = bot.say(_by_customer(sorento, "sales_ranking"), "sales by customer by amount")  # flag off
    off = _ran(calls)
    assert off and off[0].get("top_n") == 100, f"baseline: flag off should run every row, got {off or text!r}"
    bot.console.session_vars = {}
    _flag_on(bot.console, monkeypatch)
    text, calls = bot.say(_by_customer(sorento, "sales_ranking"), "sales by customer by amount")
    on = _ran(calls)
    assert "How many?" not in text, f"B3(iii): a breakdown (sales_ranking, no rank_direction) asked a count: {text!r}"
    assert on and on[0].get("top_n") == off[0].get("top_n"), f"B3(iii): flag on {on or text!r}, flag off {off[0].get('top_n')}"


def test_b3_iv_the_same_after_a_total_runs_every_row(rbot, world) -> None:
    sorento, _mocha = world
    total = _v("sales_report", _ra(basis="invoiced", measure="amount", company=sorento, **Y), basis="invoiced", measure="amount", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(total, "sorento sales 2026 invoiced by amount")
    assert _ran(calls), f"setup: {text!r}"
    text, calls = rbot.say(_by_customer(sorento, "sales_ranking", continuation=True, entity_op="reuse"), "break down by customer")
    assert "How many?" not in text, f"B3(iv): a breakdown (sales_ranking) asked a count: {text!r}"
    ran = _ran(calls)
    assert ran and ran[0].get("group_by") == "customer" and ran[0].get("top_n"), f"B3(iv): {ran or text!r}"


def test_b3_break_down_by_customer_after_a_total_runs_every_row(rbot, world) -> None:
    sorento, _mocha = world
    total = _v("sales_report", _ra(basis="invoiced", measure="amount", company=sorento, **Y), basis="invoiced", measure="amount", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(total, "sorento sales 2026 invoiced by amount")
    assert _ran(calls), f"setup: {text!r}"
    text, calls = rbot.say(_by_customer(sorento, continuation=True, entity_op="reuse"), "break down by customer")
    assert "How many?" not in text, f"B3(ii): a breakdown asked a count: {text!r}"
    ran = _ran(calls)
    assert ran and ran[0].get("group_by") == "customer" and ran[0].get("top_n"), f"B3(ii): {ran or text!r}"


def _twins(bot_: Routing) -> None:
    db = bot_.console.session_factory()
    try:
        for code in ("ZZT-TWIN-1", "ZZT-TWIN-2"):
            row = SalesAgent(id=str(uuid.uuid4()), sales_agent=code, aliases="twin", company_id=DEFAULT_COMPANY_ID)
            db.add(row)
            bot_.ids[code] = row.id
        db.commit()
    finally:
        db.close()


def test_b4_a_held_agent_name_carried_back_maps_to_its_held_id_without_a_pick(rbot, world) -> None:
    """Regression guard only (it does not guard the held name -> id map: an exact agent code resolves fresh). Turn 1
    names ZZT-TWIN-2 and runs; turn 2 copies back whatever name the Held report line shows with a new period and must
    run with the same id and no agent pick. The map itself is guarded by B4c (customers)."""
    sorento, _mocha = world
    _twins(rbot)
    first = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=["ZZT-TWIN-2"], **Y), _ent("ZZT-TWIN-2", "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(first, "sorento sales for zzt-twin-2 2026 invoiced")
    assert _ran(calls) and _ran(calls)[0].get("sales_agent_ids") == [rbot.ids["ZZT-TWIN-2"]], f"setup: {text!r}"
    seen: dict[str, Any] = {}
    again = _v("sales_report", _ra(basis="invoiced", company=sorento, date_from="2025-01-01", date_to="2025-12-31"), continuation=True, entity_op="reuse", date_filter_start="2025-01-01", date_filter_end="2025-12-31")

    def _copy_back(block: str) -> None:  # the parser reads the Held report line and copies the agent name back
        _prefix, held = _held_line(block)
        seen["agents"] = held["sales_agents"]
        again["report_ask"]["sales_agents"] = list(held["sales_agents"])

    rbot.on_block = _copy_back  # type: ignore[attr-defined]
    text, calls = rbot.say(again, "and 2025")
    assert seen.get("agents"), f"B4: the Held report line names no agent: {seen}"
    assert "Which sales agent?" not in text, f"B4: the held agent {seen['agents']} was asked again: {text!r}"
    ran = _ran(calls)
    assert ran and ran[0].get("sales_agent_ids") == [rbot.ids["ZZT-TWIN-2"]], f"B4: want the held id, got {ran[0].get('sales_agent_ids') if ran else text!r} (line showed {seen['agents']})"


def test_s5_a_named_agent_outside_the_named_company_is_said_not_dropped(rbot, world) -> None:
    sorento, _mocha = world
    v = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1, AGENT_M], **Y), _ent(AGENT_1, "sales_agent"), _ent(AGENT_M, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(v, "sorento sales for agent a and agent m 2026 invoiced")
    ran = _ran(calls)
    assert ran and ran[0].get("sales_agent_ids") == [rbot.ids["agent"]], f"S5: want AGENT A alone to run, got {ran or text!r}"
    lines = [ln for ln in text.splitlines() if ln.startswith("Not applied:")]
    assert lines and AGENT_M in lines[0], f"S5: AGENT M was dropped without a Not applied line: {text!r}"


def test_s6_the_state_path_still_lets_the_object_drive_the_args(rbot, world) -> None:
    from tests.chatbot.test_report_smart_step7 import KEEP, NEW_SUBJECT, _state_on

    sorento, _mocha = world
    ran_state = _state_on(rbot.console)
    t1 = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], **Y), _ent(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, state_changes=NEW_SUBJECT, **YR)
    text, calls = rbot.say(t1, "sorento sales for agent a 2026 invoiced")
    assert _ran(calls), f"turn 1: {text!r}"
    t2 = _v("sales_analysis", _ra(basis="invoiced", group_by="month", company=sorento, sales_agents=[AGENT_1], **Y), sales_basis="invoiced", group_by="month", continuation=True, entity_op="modify", state_changes=KEEP)
    text, calls = rbot.say(t2, "by month")
    ran = _ran(calls)
    assert ran_state, "harness: the State path never ran"
    assert ran and ran[0].get("group_by") == "month" and ran[0].get("sales_agent_ids") == [rbot.ids["agent"]], f"turn 2: {ran or text!r}"
    t3 = _v("sales_analysis", _ra(basis="invoiced", group_by="month", company=sorento, sales_agents=[AGENT_2], account_types=["ceramic"], **Y), _ent("ceramic", "account_type", None, "account type"), sales_basis="invoiced", group_by="month", continuation=True, state_changes=[{"op": "set", "axis": "account_type", "position": None}])
    text, calls = rbot.say(t3, "for ceramic account type, agent b")
    ran = _ran(calls)
    assert ran and ran[0].get("account_types") == ["CERAMIC"] and ran[0].get("group_by") == "month", f"turn 3: {ran or text!r}"
    assert ran[0].get("sales_agent_ids") == [agent_b_sorento(rbot)], f"turn 3: {ran[0].get('sales_agent_ids')}"


def test_s7_an_object_with_kind_null_on_a_non_report_parse_runs_no_report(rbot, world) -> None:
    v = _v("none", _ra(kind=None, brands=["Cabana"]), _ent("cabana", "brand", "CABANA"), domain_hint="inventory", intent_hint="check_stock", order_status=None, continuation=None)
    text, calls = rbot.say(v, "cabana stock")
    assert not _ran(calls), f"S7: a stock ask ran a report from the object: {_ran(calls)}"
    for q in ("Which period?", BASIS_Q, "How many?", QUESTION, "Sorento or Mocha?"):
        assert q not in text, f"S7: a non-report parse was answered with a report question {q!r}: {text!r}"


def test_s8_a_continuation_with_bare_flat_fields_is_driven_by_the_object(rbot, world) -> None:
    sorento, _mocha = world
    first = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], **Y), _ent(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(first, "sorento sales for agent a 2026 invoiced")
    assert _ran(calls), f"setup: {text!r}"
    # the follow-up carries no entities, no basis, no dates of its own: only continuation and the object
    follow = _v("sales_analysis", _ra(basis="invoiced", group_by="month", company=sorento, sales_agents=[AGENT_1], account_types=["ceramic"], **Y), continuation=True, entity_op="reuse", topic_reset=False)
    text, calls = rbot.say(follow, "by month for ceramic")
    ran = _ran(calls)
    assert ran and ran[0].get("account_types") == ["CERAMIC"] and ran[0].get("group_by") == "month", f"S8: the object did not drive the args: {ran or text!r}"


def test_sec_a_parser_output_report_ask_ids_never_become_customer_ids(rbot, world) -> None:
    sorento, _mocha = world
    v = _v("sales_report", _ra(basis="invoiced", company=sorento, **Y), basis="invoiced", sales_company=sorento, domain_in_message=True, report_ask_ids={"customer_ids": [rbot.ids["customer"]]}, **YR)
    text, calls = rbot.say(v, "sorento sales 2026 invoiced")
    ran = _ran(calls)
    assert ran, f"setup: {text!r}"
    assert not ran[0].get("customer_ids"), f"SEC: a parser-written report_ask_ids reached the route: {ran[0].get('customer_ids')}"


def test_sec_b_a_dealers_object_with_account_types_or_a_channel_is_refused(rdealer) -> None:
    from app.services.chatbot.lanes.business import report_ask

    for label, ra, extra in (
        ("account_types", _ra(basis="invoiced", account_types=["cabana"], **Y), {}),
        ("channel", _ra(basis="invoiced", channel="dealer", **Y), {"sales_channel": "dealer"}),
    ):
        rdealer.console.session_vars = {}
        v = _v("sales_report", ra, basis="invoiced", domain_in_message=True, **YR, **extra)
        text, calls = rdealer.say(v, f"sales 2026 invoiced {label}")
        assert not _ran(calls) and text.strip() == report_ask.DEALER_REFUSAL, f"SEC {label}: {calls or text!r}"


def test_sec_b_a_dealers_carried_customer_never_widens_to_another_customer(rdealer) -> None:
    from tests.chatbot.test_report_ask_lane import _other_customer

    other = "ZZT OTHER DEALER SDN BHD"
    other_id = _other_customer(rdealer.console, other)
    own = "ZZT OWN DEALER SDN BHD"
    t1 = _v("sales_report", _ra(basis="invoiced", customers=[own], **Y), _e(own, "customer"), basis="invoiced", domain_in_message=True, **YR)
    text, calls = rdealer.say(t1, "my sales 2026 invoiced")
    assert _ran(calls), f"setup: {text!r}"
    t2 = _v("sales_report", _ra(basis="invoiced", customers=[own, other], **Y), _e(other, "customer"), continuation=True, **YR)
    text, calls = rdealer.say(t2, f"and {other}")
    assert not any(other_id in (a.get("customer_ids") or []) for a in _ran(calls)), f"SEC: a dealer's report ran for another customer: {_ran(calls)}"


def test_b4c_a_held_customer_of_a_shared_name_stays_the_one_held(rbot, world) -> None:
    """Two Sorento customers share a name; the held frame holds ONE of them (state injected, the way a list pick
    elsewhere would leave it). The name carried back with a new period must send only that id: a fresh lookup of the
    name would send both, so only the held name -> id map can answer it (SC-5)."""
    from tests._mc_lookup_seed import customer

    sorento, _mocha = world
    name = "ZZ SAME TRADING"
    db = rbot.console.session_factory()
    try:
        both = sorted(customer(db, company_id=DEFAULT_COMPANY_ID, name=name).id for _ in range(2))
        db.commit()
    finally:
        db.close()
    held_id = both[1]
    first = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], **Y), _ent(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(first, "sorento sales for agent a 2026 invoiced")
    assert _ran(calls), f"setup: {text!r}"
    frame = rbot.console.session_vars["focus"]["sales_ranking_frame"]
    frame["customer_ids"] = [held_id]
    frame.setdefault("names", {})["customer_ids"] = {held_id: name}
    again = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], customers=[name], date_from="2025-01-01", date_to="2025-12-31"), continuation=True, entity_op="reuse", date_filter_start="2025-01-01", date_filter_end="2025-12-31")
    text, calls = rbot.say(again, "and 2025")
    _prefix, held = _held_line(rbot.blocks[-1])
    assert held["customers"] == [name], f"B4c: the Held report line shows {held['customers']}, want [{name!r}]"
    ran = _ran(calls)
    assert ran and ran[0].get("customer_ids") == [held_id], f"B4c: want only the held customer, got {ran[0].get('customer_ids') if ran else text!r}"


# ------------------------------------------------------------------------------------------ round 2
MEASURE_Q = "By quantity or by amount?"


def _copy_held(rbot_: Routing, verdict: dict[str, Any], **change: Any) -> dict[str, Any]:
    """The parser copies the Held report line into the object and changes only `change` (what the model does)."""
    seen: dict[str, Any] = {}

    def _hook(block: str) -> None:
        _p, held = _held_line(block)
        seen.update(held)
        verdict["report_ask"] = {**held, **change}

    rbot_.on_block = _hook  # type: ignore[attr-defined]
    return seen


def test_r2_1_a_frame_customer_of_sorento_is_looked_up_in_the_named_company(rbot, world) -> None:
    from tests._mc_lookup_seed import customer

    sorento, mocha = world
    name = "ZZ BOTHCO TWO TRADING"
    db = rbot.console.session_factory()
    try:
        s_id = customer(db, company_id=DEFAULT_COMPANY_ID, name=name).id
        m_id = customer(db, company_id=MOCHA_ID, name=name).id
        db.commit()
    finally:
        db.close()
    t1 = _v("sales_report", _ra(basis="invoiced", company=sorento, **Y), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(t1, "sorento sales 2026 invoiced")
    assert _ran(calls), f"setup: {text!r}"
    frame = rbot.console.session_vars["focus"]["sales_ranking_frame"]
    frame["customer_ids"] = [s_id]
    frame.setdefault("names", {})["customer_ids"] = {s_id: name}
    t2 = _v("sales_report", _ra(basis="invoiced", company=mocha, customers=[name], **Y), sales_company=mocha, continuation=True, entity_op="reuse", **YR)
    text, calls = rbot.say(t2, "mocha")
    ran = _ran(calls)
    assert "I don't know" not in text, f"R2-1: {text!r}"
    assert ran and ran[0].get("customer_ids") == [m_id] and ran[0].get("company") == MOCHA_ID, f"R2-1: want Mocha's customer {m_id}, got {ran[0].get('customer_ids') if ran else text!r}"


def test_r2_2_an_echoed_sorento_agent_id_never_runs_in_mocha(rbot, world) -> None:
    sorento, mocha = world
    sid = agent_b_sorento(rbot)
    v = _v("sales_report", _ra(basis="invoiced", company=mocha, sales_agents=[sid], **Y), basis="invoiced", sales_company=mocha, domain_in_message=True, **YR)
    text, calls = rbot.say(v, "mocha sales for agent b 2026 invoiced")
    ran = _ran(calls)
    assert not (ran and sid in (ran[0].get("sales_agent_ids") or [])), f"R2-2: Sorento's agent id ran in Mocha: {ran[0].get('sales_agent_ids')}"


def test_r2_3_without_the_sales_agents_permission_a_carried_agent_gives_the_args_a_typed_one_does(rbot, world, monkeypatch) -> None:
    from app.services.chatbot.lanes.business import report_ask

    sorento, _mocha = world
    first = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], **Y), _ent(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(first, "sorento sales for agent a 2026 invoiced")
    assert _ran(calls), f"setup: {text!r}"
    perm = report_ask.staff_principal.SALES_AGENTS_VIEW
    monkeypatch.setattr(report_ask.staff_principal, "lacks", lambda db, *slugs: perm in slugs)
    again = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], date_from="2025-01-01", date_to="2025-12-31"), continuation=True, entity_op="reuse", date_filter_start="2025-01-01", date_filter_end="2025-12-31")
    text, calls = rbot.say(again, "and 2025")
    carried = _ran(calls)
    # the same agent typed fresh in the same state (the held report is still the 2026 one)
    typed = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], date_from="2025-01-01", date_to="2025-12-31"), _ent(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, **{"date_filter_start": "2025-01-01", "date_filter_end": "2025-12-31"})
    text2, calls2 = rbot.say(typed, "sorento sales for agent a 2025 invoiced")
    fresh = _ran(calls2)
    got = (carried[0].get("sales_agent_ids") if carried else text)
    want = (fresh[0].get("sales_agent_ids") if fresh else text2)
    assert got == want, f"R2-3: carried agent gave {got!r}, the same agent typed fresh gave {want!r}"


def test_r2_4a_two_companies_and_a_null_object_company_runs_with_no_company_arg(rbot, world) -> None:
    """O-R2 (was: the declared company pick runs that company): the company is never asked, so there is no pick."""
    sorento, mocha = world
    t1 = _v("sales_report", _ra(basis="invoiced", **Y), basis="invoiced", domain_in_message=True, **YR)
    text, calls = rbot.say(t1, "sales 2026 invoiced")
    assert f"{sorento} or {mocha}?" not in text, f"O-R2: the company was asked: {text!r}"
    ran = _ran(calls)
    assert ran and "company" not in ran[0], f"O-R2: want a run with no company arg, got {ran or text!r}"


def test_r2_4b_the_measure_question_is_free_and_the_object_fills_it(rbot, world) -> None:
    """The measure question is a FREE question (R3-4, no numbered options): the object fills `measure` and it runs."""
    sorento, _mocha = world
    ask = _ra(basis="invoiced", group_by="customer", top_n=5, company=sorento, **Y)
    t1 = _v("sales_ranking", ask, basis="invoiced", group_by="customer", top_n=5, rank_direction="top", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(t1, "top 5 customers sorento 2026 invoiced")
    assert not calls and MEASURE_Q in text, f"setup: want {MEASURE_Q!r}, got {text!r}"
    assert not re.search(r"^\s*\d+[.)]\s", text, re.M), f"R3-4: the measure question is shown as a numbered option list: {text!r}"
    t2 = _v("sales_ranking", _ra(basis="invoiced", group_by="customer", top_n=5, measure="amount", company=sorento, **Y), entity_op="reuse", continuation=True)
    text, calls = rbot.say(t2, "by amount")
    assert MEASURE_Q not in text, "R3-4: the measure was asked again after the object filled it"
    ran = _ran(calls)
    assert ran and ran[0].get("measure") == "amount", f"R3-4: want measure amount, got {ran[0].get('measure') if ran else text!r}"


def test_r3_4_the_measure_question_carries_no_options_and_a_bare_number_does_not_settle_it(bot, monkeypatch, world) -> None:
    """With the basis also owed the reply is the owner's ask-all format, as with the flag off. The measure question has
    no offered options (they would collide with the ask-all numbers): none in the stored slot, none in the parser's
    Open question line, and a typed "2" with the object's measure null does not settle the measure."""
    sorento, _mocha = world

    def ranking() -> dict[str, Any]:
        return _v(
            "sales_ranking", _ra(group_by="customer", top_n=5, company=sorento, **Y), group_by="customer", top_n=5,
            rank_direction="top", sales_company=sorento, domain_in_message=True, **YR,
        )

    off_text, off_calls = bot.say(ranking(), "top 5 customers sorento 2026")  # flag off
    assert not off_calls, f"baseline: {off_text!r}"
    bot.console.session_vars = {}
    _flag_on(bot.console, monkeypatch)
    _record_blocks(bot, monkeypatch)
    text, calls = bot.say(ranking(), "top 5 customers sorento 2026")
    assert not calls and text == off_text, f"R3-4 (1): flag on {text!r} differs from flag off {off_text!r}"
    slot = bot.console.session_vars["focus"]["required_ask"]
    stored = [*(slot.get("options") or []), *((slot.get("extras") or {}).get("options") or [])]
    offered = [o for o in stored if "uantity" in str(o) or "mount" in str(o)]
    assert not offered, f"R3-4 (2): the stored slot offers the measure options {offered}"
    t2 = _v("sales_ranking", _ra(group_by="customer", top_n=5, company=sorento, **Y), entity_op="reuse", continuation=True, open_question_answer=_pick_of(2), reference_positions=[2])
    text, calls = bot.say(t2, "2")
    open_line = next((ln for ln in bot.blocks[-1].splitlines() if ln.startswith("Open question")), "")
    assert "Quantity" not in open_line and "Amount" not in open_line, f"R3-4 (2): the Open question line offers the measure options: {open_line!r}"
    ran = _ran(calls)
    assert not (ran and ran[0].get("measure")), f"R3-4 (3): a typed 2 with the object's measure null settled the measure: {ran[0].get('measure') if ran else ''}"
    t3 = _v("sales_ranking", _ra(basis="delivered", group_by="customer", top_n=5, measure="amount", company=sorento, **Y), basis="delivered", entity_op="reuse", continuation=True)
    text, calls = bot.say(t3, "delivered by amount")
    ran = _ran(calls)
    assert ran and ran[0].get("measure") == "amount", f"R3-4 (3): an object measure amount did not run by amount: {ran or text!r}"


def _top10(sorento: str) -> dict[str, Any]:
    return _v(
        "sales_ranking", _ra(basis="invoiced", group_by="customer", top_n=10, measure="amount", company=sorento, **Y),
        basis="invoiced", group_by="customer", top_n=10, measure="amount", rank_direction="top", sales_company=sorento,
        domain_in_message=True, **YR,
    )


def test_r2_5a_a_carried_top_n_survives_an_account_type_change(rbot, world) -> None:
    sorento, _mocha = world
    text, calls = rbot.say(_top10(sorento), "top 10 customers by amount sorento 2026 invoiced")
    assert _ran(calls) and _ran(calls)[0].get("top_n") == 10, f"setup: {text!r}"
    t2 = _v("sales_analysis", _ra(), _ent("ceramic", "account_type", None, "account type"), continuation=True, entity_op="modify")
    seen = _copy_held(rbot, t2, account_types=["ceramic"])
    text, calls = rbot.say(t2, "for ceramic")
    assert "How many?" not in text, f"R2-5a: the count was asked again (held top_n {seen.get('top_n')}): {text!r}"
    ran = _ran(calls)
    assert ran and ran[0].get("top_n") == 10, f"R2-5a: want top_n 10, got {ran[0].get('top_n') if ran else text!r} (held line top_n {seen.get('top_n')})"


def test_r2_5b_a_breakdown_with_no_count_is_not_asked_a_count_on_a_new_period(rbot, world) -> None:
    sorento, _mocha = world
    text, calls = rbot.say(_by_customer(sorento, "sales_ranking"), "sales by customer by amount")
    assert _ran(calls), f"setup: {text!r}"
    t2 = _v("sales_ranking", _ra(), continuation=True, entity_op="reuse", date_filter_start="2025-01-01", date_filter_end="2025-12-31")
    seen = _copy_held(rbot, t2, date_from="2025-01-01", date_to="2025-12-31")
    text, calls = rbot.say(t2, "and 2025")
    assert "How many?" not in text, f"R2-5b: a breakdown was asked a count on a new period (held top_n {seen.get('top_n')}): {text!r}"
    ran = _ran(calls)
    assert ran and ran[0].get("group_by") == "customer" and ran[0].get("date_from") == "2025-01-01", f"R2-5b: {ran or text!r}"


def test_r2_5c_a_top_n_copied_onto_a_month_axis_is_not_sent(rbot, world) -> None:
    sorento, _mocha = world
    text, calls = rbot.say(_top10(sorento), "top 10 customers by amount sorento 2026 invoiced")
    assert _ran(calls), f"setup: {text!r}"
    t2 = _v("sales_analysis", _ra(), continuation=True, entity_op="modify", group_by="month")
    seen = _copy_held(rbot, t2, group_by="month")
    text, calls = rbot.say(t2, "by month")
    ran = _ran(calls)
    assert ran and ran[0].get("group_by") == "month", f"R2-5c: {ran or text!r}"
    assert ran[0].get("top_n") != 10, f"R2-5c: a month axis was cut to the copied top 10 (held top_n {seen.get('top_n')}): {ran[0].get('top_n')}"


def test_r2_6b_a_stock_parse_with_a_sales_object_after_a_report_runs_no_report_and_asks_nothing(rbot, world) -> None:
    sorento, _mocha = world
    t1 = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], **Y), _ent(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(t1, "sorento sales for agent a 2026 invoiced")
    assert _ran(calls), f"setup: {text!r}"
    v = _v("none", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], brands=["Cabana"], **Y), _ent("cabana", "brand", "CABANA"), domain_hint="inventory", intent_hint="check_stock", order_status=None, continuation=None)
    text, calls = rbot.say(v, "cabana stock")
    assert not _ran(calls), f"R2-6b: a stock ask ran a report: {_ran(calls)}"
    for q in ("Which period?", BASIS_Q, "How many?", QUESTION, "brand or account type?", "Sorento or Mocha?"):
        assert q not in text, f"R2-6b: a stock ask was answered with the report question {q!r}: {text!r}"


def test_r2_7_a_continuation_over_a_cut_summary_is_driven_by_the_object(rbot, world, monkeypatch) -> None:
    """The reviewer's shape: an outstanding summary with a breakdown cut at 20 rows arms "more" (fetch.py set_window).
    A follow-up the parser marks `continuation` whose object names a customer is that new ask, not the next page."""
    from tests.chatbot.test_composers_stock_xd import _set_gate

    _set_gate(monkeypatch, True)  # the composers gate
    rbot.extra_body = {
        "summary": {"groups": [{"axis": "customer", "rows": [{"name": f"ZZ CUSTOMER {i}", "qty": 1, "amount": 1.0} for i in range(25)]}]},
    }
    first = _v("outstanding", _ra(kind="outstanding", basis="outstanding"), basis="outstanding", domain_in_message=True)
    text, calls = rbot.say(first, "undelivered orders")
    assert _ran(calls), f"setup: {text!r}"
    page = rbot.console.session_vars.get("focus", {}).get("set_page") or {}
    assert (page.get("set_key") or {}).get("report_groups"), f"setup: no cut summary is armed on screen: {page!r}"
    rbot.extra_body = {}
    follow = _v(
        "outstanding", _ra(kind="outstanding", basis="outstanding", customers=[CUSTOMER_NAME]), _e(CUSTOMER_NAME, "customer"),
        continuation=True, entity_op="reuse",
    )
    text, calls = rbot.say(follow, f"and for {CUSTOMER_NAME}")
    ran = _ran(calls)
    assert ran, f"R2-7: the follow-up over the cut summary did not run: {text!r}"
    assert ran[0].get("customer_ids") == [rbot.ids["customer"]] and not ran[0].get("group_offset"), f"R2-7: the object did not drive the args (read as the next page?): {ran[0]}"


# ------------------------------------------------------------------------------------------ round 3
def _seed_twins(rbot_: Routing, model: Any, rows: list[tuple[str, str]], code_col: str, name_col: str) -> dict[str, str]:
    db = rbot_.console.session_factory()
    ids: dict[str, str] = {}
    try:
        for code, name in rows:
            row = model(id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, **{code_col: code, name_col: name})
            db.add(row)
            ids[code] = str(row.id)
        db.commit()
    finally:
        db.close()
    return ids


def test_r3_1_two_brands_sharing_a_name_carry_only_the_held_one(rbot, world) -> None:
    sorento, _mocha = world
    ids = _seed_twins(rbot, Brand, [("ZZTWB1", "ZZ TWINBRAND"), ("ZZTWB2", "ZZ TWINBRAND")], "brand_code", "brand_name")
    t1 = _v("sales_report", _ra(basis="invoiced", company=sorento, brands=["ZZTWB1"], **Y), _ent("ZZTWB1", "brand", None, "brand"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(t1, "sorento sales for brand zztwb1 2026 invoiced")
    assert _ran(calls) and _ran(calls)[0].get("brand_ids") == [ids["ZZTWB1"]], f"setup: {_ran(calls) or text!r}"
    t2 = _v("sales_report", _ra(), continuation=True, entity_op="reuse", date_filter_start="2025-01-01", date_filter_end="2025-12-31")
    seen = _copy_held(rbot, t2, date_from="2025-01-01", date_to="2025-12-31")
    text, calls = rbot.say(t2, "and 2025")
    ran = _ran(calls)
    assert ran and ran[0].get("brand_ids") == [ids["ZZTWB1"]], f"R3-1: want only ZZTWB1 (held line {seen.get('brands')}), got {ran[0].get('brand_ids') if ran else text!r}"


def test_r3_2_two_categories_sharing_a_name_carry_only_the_held_one(rbot, world) -> None:
    sorento, _mocha = world
    ids = _seed_twins(rbot, ProductCategory, [("ZZTC1", "ZZ TWINCAT"), ("ZZTC2", "ZZ TWINCAT")], "category_code", "category_name")
    t1 = _v("sales_report", _ra(basis="invoiced", company=sorento, categories=["ZZTC1"], **Y), _ent("ZZTC1", "category"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(t1, "sorento sales for category zztc1 2026 invoiced")
    assert _ran(calls) and _ran(calls)[0].get("category_ids") == [ids["ZZTC1"]], f"setup: {_ran(calls) or text!r}"
    t2 = _v("sales_report", _ra(), continuation=True, entity_op="reuse", date_filter_start="2025-01-01", date_filter_end="2025-12-31")
    seen = _copy_held(rbot, t2, date_from="2025-01-01", date_to="2025-12-31")
    text, calls = rbot.say(t2, "and 2025")
    assert "matches several categories" not in text, f"R3-2: {text!r}"
    ran = _ran(calls)
    assert ran and ran[0].get("category_ids") == [ids["ZZTC1"]], f"R3-2: want only ZZTC1 (held line {seen.get('categories')}), got {ran[0].get('category_ids') if ran else text!r}"


def test_r3_3_an_outstanding_parse_with_an_object_of_kind_null_still_runs_the_outstanding_report(rbot, world) -> None:
    v = _v("outstanding", _ra(kind=None), basis="outstanding", domain_in_message=True)
    text, calls = rbot.say(v, "undelivered orders")
    for q in ("Which period?", BASIS_Q):
        assert q not in text, f"R3-3: an outstanding ask was answered with the report question {q!r}: {text!r}"
    ran = _ran(calls)
    assert ran and ran[0].get("basis") == "outstanding", f"R3-3: the outstanding report did not run: {ran or text!r}"


def _seed_customers(rbot_: Routing, rows: list[tuple[str, str]]) -> list[str]:
    from tests._mc_lookup_seed import customer

    db = rbot_.console.session_factory()
    try:
        out = [str(customer(db, company_id=company, name=name).id) for company, name in rows]
        db.commit()
    finally:
        db.close()
    return out


def _hold_customer(rbot_: Routing, sorento: str, cid: str, name: str) -> None:
    """A Sorento report ran, then the frame is set to hold ONE customer (state injected, as a list pick would leave it)."""
    t1 = _v("sales_report", _ra(basis="invoiced", company=sorento, **Y), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot_.say(t1, "sorento sales 2026 invoiced")
    assert _ran(calls), f"setup: {text!r}"
    frame = rbot_.console.session_vars["focus"]["sales_ranking_frame"]
    frame["customer_ids"] = [cid]
    frame.setdefault("names", {})["customer_ids"] = {cid: name}


def _lacks(monkeypatch, slug_attr: str) -> None:
    from app.services.chatbot.lanes.business import report_ask

    perm = getattr(report_ask.staff_principal, slug_attr)
    monkeypatch.setattr(report_ask.staff_principal, "lacks", lambda db_, *slugs: perm in slugs)


def test_r3_5a_without_the_customers_permission_a_held_customer_switch_equals_typing_it_fresh(rbot, world, monkeypatch) -> None:
    import copy

    sorento, mocha = world
    name = "ZZ GATED TRADING"
    s_id, m_id = _seed_customers(rbot, [(DEFAULT_COMPANY_ID, name), (MOCHA_ID, name)])
    _hold_customer(rbot, sorento, s_id, name)
    _lacks(monkeypatch, "CUSTOMERS_VIEW")
    state = copy.deepcopy(rbot.console.session_vars)
    carried = _v("sales_report", _ra(basis="invoiced", company=mocha, customers=[name], **Y), sales_company=mocha, continuation=True, entity_op="reuse", **YR)
    text, calls = rbot.say(carried, "mocha")
    ran = _ran(calls)
    assert not (ran and m_id in (ran[0].get("customer_ids") or [])), f"R3-5a: Mocha's customer was resolved without the permission: {ran[0].get('customer_ids')}"
    rbot.console.session_vars = copy.deepcopy(state)
    typed = _v("sales_report", _ra(basis="invoiced", company=mocha, customers=[name], **Y), _ent(name, "customer"), basis="invoiced", sales_company=mocha, domain_in_message=True, **YR)
    fresh_text, fresh_calls = rbot.say(typed, f"mocha sales for {name} 2026 invoiced")
    assert text == fresh_text, f"R3-5a: carried reply {text!r} differs from the same customer typed fresh {fresh_text!r}"


def test_r3_5b_a_dealers_switch_reply_is_the_same_with_or_without_an_unlinked_same_name_customer(rdealer) -> None:
    sorento, mocha = _two_companies(rdealer)
    own = "ZZT OWN DEALER SDN BHD"

    def run() -> str:
        rdealer.console.session_vars = {}
        t1 = _v("sales_report", _ra(basis="invoiced", company=sorento, customers=[own], **Y), _e(own, "customer"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
        text, calls = rdealer.say(t1, "my sales 2026 invoiced")
        assert _ran(calls), f"setup: {text!r}"
        t2 = _v("sales_report", _ra(basis="invoiced", company=mocha, customers=[own], **Y), sales_company=mocha, continuation=True, entity_op="reuse", **YR)
        text, calls = rdealer.say(t2, "mocha")
        assert "customer_not_permitted" not in text and "403" not in text, f"R3-5b: a permission error was shown: {text!r}"
        return text

    without = run()
    _seed_customers(rdealer, [(MOCHA_ID, own)])
    with_twin = run()
    assert with_twin == without, f"R3-5b: an unlinked same-name customer changes the reply (an existence oracle): {without!r} vs {with_twin!r}"


def test_r4_1_a_held_customer_is_kept_in_its_own_company_without_the_customers_permission(bot, monkeypatch, world) -> None:
    sorento, _mocha = world
    name = "ZZ SAMECO GATED TRADING"
    (s_id,) = _seed_customers(bot, [(DEFAULT_COMPANY_ID, name)])
    _lacks(monkeypatch, "CUSTOMERS_VIEW")

    def again() -> tuple[str, list[dict[str, Any]]]:
        _hold_customer(bot, sorento, s_id, name)
        t2 = _v("sales_report", _ra(basis="invoiced", company=sorento, customers=[name], date_from="2025-01-01", date_to="2025-12-31"), sales_company=sorento, continuation=True, entity_op="reuse", date_filter_start="2025-01-01", date_filter_end="2025-12-31")
        text, calls = bot.say(t2, "and 2025")
        return text, _ran(calls)

    off_text, off = again()  # flag off, the same verdicts
    bot.console.session_vars = {}
    _flag_on(bot.console, monkeypatch)
    text, on = again()
    assert off and off[0].get("customer_ids") == [s_id], f"baseline: flag off should keep the customer: {off or off_text!r}"
    assert "Not applied" not in text, f"R4-1: the held customer was dropped in its own company: {text!r}"
    assert on and on[0].get("customer_ids") == off[0].get("customer_ids"), f"R4-1: flag on {on[0].get('customer_ids') if on else text!r}, flag off {off[0].get('customer_ids')}"


def test_r4_2_a_carried_customer_and_a_carried_agent_that_are_missing_after_a_switch_get_one_reply_rule(rbot, world) -> None:
    sorento, mocha = world
    pattern = re.compile(r"I don't know '.+' as an? (customer|sales agent) in .+\.")
    # the agent: AGENT A is Sorento only
    t1 = _v("sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], **Y), _ent(AGENT_1, "sales_agent"), basis="invoiced", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(t1, "sorento sales for agent a 2026 invoiced")
    assert _ran(calls), f"setup: {text!r}"
    t2 = _v("sales_report", _ra(), continuation=True, entity_op="reuse", sales_company=mocha)
    _copy_held(rbot, t2, company=mocha)
    agent_text, agent_calls = rbot.say(t2, "mocha")
    rbot.on_block = None  # type: ignore[attr-defined]
    # the customer: Sorento only
    rbot.console.session_vars = {}
    name = "ZZ SORENTOONLY TRADING"
    (s_id,) = _seed_customers(rbot, [(DEFAULT_COMPANY_ID, name)])
    _hold_customer(rbot, sorento, s_id, name)
    t3 = _v("sales_report", _ra(basis="invoiced", company=mocha, customers=[name], **Y), sales_company=mocha, continuation=True, entity_op="reuse", **YR)
    cust_text, cust_calls = rbot.say(t3, "mocha")
    assert pattern.fullmatch(agent_text.strip()) and not _ran(agent_calls), f"R4-2 baseline: the agent case is {agent_text!r}"
    assert not _ran(cust_calls), f"R4-2: a Mocha-wide report ran for a missing customer: {_ran(cust_calls)[0].get('customer_ids')}"
    assert pattern.fullmatch(cust_text.strip()), f"R4-2: the customer case reads {cust_text!r}, the agent case {agent_text!r}"


def test_r4_3_the_held_customer_resolves_to_the_exact_name_row_among_many_partial_matches(rbot, world) -> None:
    sorento, mocha = world
    name = "ZZQ LIMTEST"
    ids = _seed_customers(rbot, [(DEFAULT_COMPANY_ID, name), (MOCHA_ID, name), *[(MOCHA_ID, f"AA {name} {i:03d}") for i in range(55)]])
    s_id, m_id = ids[0], ids[1]
    _hold_customer(rbot, sorento, s_id, name)
    t2 = _v("sales_report", _ra(basis="invoiced", company=mocha, customers=[name], **Y), sales_company=mocha, continuation=True, entity_op="reuse", **YR)
    text, calls = rbot.say(t2, "mocha")
    ran = _ran(calls)
    assert ran and ran[0].get("customer_ids") == [m_id], f"R4-3: want Mocha's exact-name row, got {ran[0].get('customer_ids') if ran else text!r}"


# ------------------------------------------------------------------------------------------ round 5 (console pass)


def test_r5_1_a_newer_object_replaces_the_word_an_open_question_asked_even_with_a_declared_pick(rbot, world) -> None:
    """Console step 11: the kind question is open for SORENTO (a brand and an account type); the reply's object holds
    CERAMIC only, and the parse also declares an answer to the open question. SORENTO is not added back."""
    sorento, _mocha = world
    db = rbot.console.session_factory()
    try:
        _ledger(db, DEFAULT_COMPANY_ID, "ZZT LEDGER FIVE [A/C V]", "SORENTO")
        db.commit()
    finally:
        db.close()
    first = _v(
        "sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], brands=["Sorento"], **Y),
        _ent(AGENT_1, "sales_agent"), _ent("sorento", "brand", "SORENTO", None), basis="invoiced", sales_company=sorento,
        domain_in_message=True, **YR,
    )
    text, calls = rbot.say(first, "sorento sales for agent a sorento 2026 invoiced")
    assert not calls and "brand, account type or company?" in text, f"setup: want the three-option question for SORENTO (Sorento is held), got {text or calls!r}"
    reply = _v(
        "sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], account_types=["ceramic"], **Y),
        _ent("ceramic", "account_type", None, "account type"), entity_op="replace_combine", continuation=True,
        open_question_answer=_pick_of(2), **YR,
    )
    text, calls = rbot.say(reply, "for ceramic account type")
    ran = _ran(calls)
    assert ran, f"R5-1: the reply did not run: {text!r}"
    assert ran[0].get("account_types") == ["CERAMIC"], f"R5-1: want CERAMIC only, got {ran[0].get('account_types')} (SORENTO added back from the open question)"
    assert not ran[0].get("brand_ids"), f"R5-1: {ran[0].get('brand_ids')}"


def _seed_agb(rbot_: Routing) -> dict[str, str]:
    """One person, three codes of one company, all answering to the word "zz agb"."""
    db = rbot_.console.session_factory()
    ids: dict[str, str] = {}
    try:
        for code in ("ZZ AGB I", "ZZ AGB III", "ZZ AGB IV"):
            row = SalesAgent(id=str(uuid.uuid4()), sales_agent=code, aliases="zz agb", company_id=DEFAULT_COMPANY_ID)
            db.add(row)
            ids[code] = str(row.id)
        db.commit()
    finally:
        db.close()
    return ids


def test_r5_2_a_person_named_by_the_word_that_matches_three_codes_never_runs_one_silently(rbot, world) -> None:
    """Console step 14, variant (a): the object carries the person word. The held line carries all three codes of one
    person; "only sales agent zz agb" runs all three ids or asks the agent pick, never one code alone."""
    sorento, _mocha = world
    ids = _seed_agb(rbot)
    first = _v("sales_report", _ra(basis="invoiced", group_by="month", company=sorento, **Y), basis="invoiced", group_by="month", sales_company=sorento, domain_in_message=True, **YR)
    text, calls = rbot.say(first, "sorento sales by month 2026 invoiced")
    assert _ran(calls), f"setup: {text!r}"
    frame = rbot.console.session_vars["focus"]["sales_ranking_frame"]
    frame["sales_agent_ids"] = list(ids.values())
    frame.setdefault("names", {})["sales_agent_ids"] = {v: k for k, v in ids.items()}
    follow = _v(
        "sales_analysis", _ra(basis="invoiced", group_by="month", company=sorento, sales_agents=["zz agb"], **Y),
        _ent("zz agb", "sales_agent"), sales_basis="invoiced", group_by="month", sales_company=sorento, continuation=True,
        entity_op="replace_combine", **YR,
    )
    text, calls = rbot.say(follow, "breakd down by month, only sales agent zz agb")
    ran = _ran(calls)
    asked = not ran and "Which sales agent?" in text
    all_three = bool(ran) and set(ran[0].get("sales_agent_ids") or []) == set(ids.values())
    assert asked or all_three, f"R5-2: one code ran silently: {ran[0].get('sales_agent_ids') if ran else text!r}, want all of {sorted(ids.values())} or the agent pick"


def _kind_question_for_cabana(rbot_: Routing, sorento: str) -> None:
    ask = _cabana_ask(sorento, bucket="brands", kind_said=None)
    text, calls = rbot_.say(ask, "sorento sales for agent a cabana 2026 invoiced")
    assert not _ran(calls) and text.strip() == QUESTION, f"setup: want {QUESTION!r}, got {text or calls!r}"


def test_r5_3_an_answer_to_the_kind_question_sets_no_axis_when_the_message_names_none(rbot, world) -> None:
    """Console step 3: "account type" answers the kind question; the object also sets `group_by` account_type and this
    message's `by_words` is null. A plain total runs: no measure question, no one-row account type list."""
    sorento, _mocha = world
    _kind_question_for_cabana(rbot, sorento)
    reply = _v(
        "sales_ranking", _ra(basis="invoiced", group_by="account_type", company=sorento, sales_agents=[AGENT_1], account_types=["cabana"], **Y),
        basis="invoiced", group_by="account_type", entity_op="reuse", continuation=True, ranking_refine=True,
        open_question_answer=_pick_of(2), by_words=None,
    )
    text, calls = rbot.say(reply, "account type")
    ran = _ran(calls)
    assert MEASURE_Q not in text, f"R5-3: the measure was asked on an answer turn: {text!r}"
    assert ran and not ran[0].get("group_by"), f"R5-3: want a plain total, got {ran[0].get('group_by') if ran else text!r}"
    assert "Top 1 account type" not in text, f"R5-3: {text!r}"
    assert ran[0].get("account_types") == ["CABANA"], ran[0]


def test_r5_3_an_answer_that_says_by_account_type_still_breaks_down(rbot, world) -> None:
    sorento, _mocha = world
    _kind_question_for_cabana(rbot, sorento)
    reply = _v(
        "sales_ranking", _ra(basis="invoiced", group_by="account_type", measure="amount", company=sorento, sales_agents=[AGENT_1], account_types=["cabana"], **Y),
        basis="invoiced", group_by="account_type", measure="amount", rank_direction=None, entity_op="reuse", continuation=True,
        open_question_answer=_pick_of(2), by_words="by account type",
    )
    text, calls = rbot.say(reply, "account type, by account type")
    ran = _ran(calls)
    assert ran and ran[0].get("group_by") == "account_type", f"R5-3: a typed axis was dropped: {ran or text!r}"


def _agent_report(sorento: str, words: list[str]) -> dict[str, Any]:
    return _v(
        "sales_report", _ra(basis="invoiced", company=sorento, sales_agents=words, **Y),
        *[_ent(w, "sales_agent") for w in words], basis="invoiced", sales_company=sorento, domain_in_message=True, **YR,
    )


def test_r5_2c_the_held_line_shows_the_person_word_when_it_resolves_back_to_exactly_the_held_agents(rbot, world) -> None:
    sorento, _mocha = world
    ids = _seed_agb(rbot)
    text, calls = rbot.say(_agent_report(sorento, ["zz agb"]), "sorento sales for zz agb 2026 invoiced")
    assert _ran(calls) and set(_ran(calls)[0].get("sales_agent_ids") or []) == set(ids.values()), f"setup: {_ran(calls) or text!r}"
    follow = _v("sales_report", _ra(), continuation=True, entity_op="reuse", date_filter_start="2025-01-01", date_filter_end="2025-12-31")
    seen = _copy_held(rbot, follow, date_from="2025-01-01", date_to="2025-12-31")
    text, calls = rbot.say(follow, "and 2025")
    assert seen.get("sales_agents") == ["zz agb"], f"R5-2c: the Held line shows {seen.get('sales_agents')}, want the one person word ['zz agb']"
    ran = _ran(calls)
    assert ran and set(ran[0].get("sales_agent_ids") or []) == set(ids.values()), f"R5-2c: copying the word back ran {ran[0].get('sales_agent_ids') if ran else text!r}"


def test_r5_2c_guard_separately_typed_codes_stay_codes_on_the_held_line(rbot, world) -> None:
    sorento, _mocha = world
    ids = _seed_agb(rbot)
    typed = ["ZZ AGB I", "ZZ AGB III"]  # no single word resolves to exactly these two ("zz agb" gives all three)
    text, calls = rbot.say(_agent_report(sorento, typed), "sorento sales for zz agb i and zz agb iii 2026 invoiced")
    assert _ran(calls) and set(_ran(calls)[0].get("sales_agent_ids") or []) == {ids[c] for c in typed}, f"setup: {_ran(calls) or text!r}"
    follow = _v("sales_report", _ra(), continuation=True, entity_op="reuse", date_filter_start="2025-01-01", date_filter_end="2025-12-31")
    seen = _copy_held(rbot, follow, date_from="2025-01-01", date_to="2025-12-31")
    rbot.say(follow, "and 2025")
    assert sorted(seen.get("sales_agents") or []) == sorted(typed), f"R5-2c guard: the Held line shows {seen.get('sales_agents')}, want the codes {typed}"


def test_r5_1b_the_asked_word_carries_when_the_answer_names_no_word_of_its_own(rbot, world) -> None:
    """Gold sc-03 shape: "Cabana: brand or account type?" is open; the reply "account type" declares the pick and the
    object holds no brand, account type or brand_or_account_type word. The asked word carries: CABANA runs."""
    sorento, _mocha = world
    _kind_question_for_cabana(rbot, sorento)
    reply = _v(
        "sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], **Y),
        entity_op="reuse", continuation=True, open_question_answer=_pick_of(2), **YR,
    )
    text, calls = rbot.say(reply, "account type")
    ran = _ran(calls)
    assert ran, f"R5-1b: the answer did not run: {text!r}"
    assert ran[0].get("account_types") == ["CABANA"], f"R5-1b: want account type CABANA, got {ran[0].get('account_types')}"


def _sorento_is_a_brand_and_an_account_type(rbot_: Routing) -> None:
    db = rbot_.console.session_factory()
    try:
        _ledger(db, DEFAULT_COMPANY_ID, "ZZT LEDGER FIVE [A/C V]", "SORENTO")
        db.commit()
    finally:
        db.close()


def test_r5_1c_a_carried_brand_does_not_drop_the_asked_account_type(rbot, world) -> None:
    """A settled brand (Cabana) is held; "and sorento" opens the kind question; the reply "account type" declares the pick
    and the object carries Cabana but leaves sorento out. Both run: brand Cabana and account type SORENTO."""
    sorento, _mocha = world
    _sorento_is_a_brand_and_an_account_type(rbot)
    text, calls = rbot.say(_cabana_ask(sorento, bucket="brands", kind_said="brand"), "sorento sales for agent a cabana brand 2026 invoiced")
    assert _ran(calls) and _ran(calls)[0].get("brand_ids"), f"setup: {text!r}"
    add = _v(
        "sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], brands=["Cabana", "Sorento"], **Y),
        _ent("sorento", "brand", "SORENTO", None), basis="invoiced", sales_company=sorento, continuation=True, **YR,
    )
    text, calls = rbot.say(add, "and sorento")
    assert not _ran(calls) and "brand, account type or company?" in text, f"setup: want the three-option question (Sorento is held), got {text!r}"
    reply = _v(
        "sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], brands=["Cabana"], **Y),
        entity_op="reuse", continuation=True, open_question_answer=_pick_of(2), **YR,
    )
    text, calls = rbot.say(reply, "account type")
    ran = _ran(calls)
    assert ran and ran[0].get("account_types") == ["SORENTO"] and len(ran[0].get("brand_ids") or []) == 1, (
        f"R5-1c: want brand Cabana and account type SORENTO, got types {ran[0].get('account_types') if ran else None} "
        f"brands {ran[0].get('brand_ids') if ran else text!r}"
    )


def test_r5_1d_a_carried_account_type_does_not_drop_the_asked_brand(rbot, world) -> None:
    """CERAMIC account type held; "and cabana" opens the kind question; the reply "brand" declares the pick and the object
    carries only ceramic. Both run: CERAMIC and brand Cabana."""
    sorento, _mocha = world
    t1 = _v(
        "sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], account_types=["ceramic"], **Y),
        _ent("ceramic", "account_type", None, "account type"), _ent(AGENT_1, "sales_agent"), basis="invoiced",
        sales_company=sorento, domain_in_message=True, **YR,
    )
    text, calls = rbot.say(t1, "sorento sales for agent a ceramic account type 2026 invoiced")
    assert _ran(calls) and _ran(calls)[0].get("account_types") == ["CERAMIC"], f"setup: {text!r}"
    add = _v(
        "sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], account_types=["ceramic"], brands=["Cabana"], **Y),
        _ent("cabana", "brand", "CABANA", None), basis="invoiced", sales_company=sorento, continuation=True, **YR,
    )
    text, calls = rbot.say(add, "and cabana")
    assert not _ran(calls) and "brand or account type?" in text, f"setup: want the kind question, got {text!r}"
    reply = _v(
        "sales_report", _ra(basis="invoiced", company=sorento, sales_agents=[AGENT_1], account_types=["ceramic"], **Y),
        entity_op="reuse", continuation=True, open_question_answer=_pick_of(1), **YR,
    )
    text, calls = rbot.say(reply, "brand")
    ran = _ran(calls)
    assert ran and ran[0].get("account_types") == ["CERAMIC"] and len(ran[0].get("brand_ids") or []) == 1, (
        f"R5-1d: want CERAMIC and brand Cabana, got types {ran[0].get('account_types') if ran else None} "
        f"brands {ran[0].get('brand_ids') if ran else text!r}"
    )
