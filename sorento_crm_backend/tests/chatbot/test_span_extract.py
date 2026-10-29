"""ENTITY-EXTRACT-MATCH S2 red tests: the span pass before the parser, dark behind `== LOOKUP SPANS ==`.

UAC AC-S2-1..8 (AC-S2-9 lives in test_list_resolver.py). Real `parser.resolve_config`, real `run_turn`, real
registry rows; only `parser.parse` and the provider factory (`llm_provider.get_provider`, which
`llm_call.chat` calls) are faked, plus the embedder (`ll.EMBED = None`). Names are invented (ZZ prefix).

Assumed beyond the contract (the coder reconciles these with the captain):
- the span model answers `{"spans": [{"text": ..., "type": ...}]}`; `type` is a list_resolver span type or null;
- the trace event is a turn-trace entry with `kind == "span_extract"` and keys `spans` (a list of
  `{"text", "type", "status", "close"}`, `close` = close rows before the TOP_K cut), `rows_rendered` (int),
  `ms`, `provider`, `model`, `model_source`, `fallback` (bool), `tokens`;
- the migration module `eem_0001_span_pass` exposes `publish_on_production(db) -> int | None` for the parser
  version (the `diet_0001` pattern) and its `upgrade()` / `downgrade()` seed / remove the span prompt.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import uuid
from pathlib import Path
from unittest import mock

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip
from app.models.ai_assistant import AIAssistantUsageLog
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.models.product import Brand, ProductCategory
from app.models.marketing import PromotionType
from app.models.sales_agent import SalesAgent
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import llm_call
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session
from tests.chatbot.conftest import counting_session_factory, session_factory  # noqa: F401
from tests.chatbot.test_customer_scope_lane import _give_access_type, _link_customers, _other_customer
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, _turn_row, seeded, stub_access  # noqa: F401
from tests.chatbot.test_lookup_lists_s2 import scoped
from tests.chatbot.test_model_per_contact_runtime import (  # noqa: F401
    CHOICE_MODEL, GEMINI_KEY, GLOBAL_KEY, _fresh_caches, _global, _label, _tag_the_contact,
)

SPAN_KEY = "chatbot_span_extractor"
SPAN_FEATURE = "chatbot_span_extract"
SPANS_LINE = "== LOOKUP SPANS =="
LISTS_LINE = "== LOOKUP LISTS =="
BASE = "Rules for {{current_date}}.\nThe Sales channels line lists the channels.\n"
HDR = {
    "brand": "Brand candidates (pick one only if the message means it):",
    "customer": "Customer candidates (pick one only if the message means it):",
    "salesperson": "Salesperson candidates (pick one only if the message means it):",
    "promotion_kind": "Promotion kind candidates (pick one only if the message means it):",
    "spec": "Spec candidates (pick one only if the message means it):",
    "category": "Category candidates (pick one only if the message means it):",
}
BRAND, BRAND_CODE = "ZZMOCHA", "ZZMCH"
OWN, OTHER = "ZZ Quartz Trading Sdn Bhd", "ZZ Marble Works Sdn Bhd"


def spans_json(*pairs: tuple[str, str | None]) -> str:
    return json.dumps({"spans": [{"text": t, "type": ty} for t, ty in pairs]})


class FakeProvider:
    """Stands in for the provider `llm_call.chat` builds. `events` is shared with the parser stub so the call
    order is recorded; `check` runs inside the call (the session-free assertion)."""

    def __init__(self, events: list, output, check=None):
        self.events, self.output, self.check = events, output, check
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        self.events.append("span")
        if self.check:
            self.check()
        out = self.output() if callable(self.output) else self.output
        if isinstance(out, Exception):
            raise out
        return ChatResult(content=out, prompt_tokens=11, completion_tokens=7, total_tokens=18)


def seed_world(session_factory) -> None:
    """A brand, two categories, a promotion kind and three registry words; every test seeds its own chain."""
    db = session_factory()
    db.add_all([
        Brand(id=str(uuid.uuid4()), brand_code=BRAND_CODE, brand_name=BRAND, is_active=True, company_id=DEFAULT_COMPANY_ID),
        ProductCategory(id=str(uuid.uuid4()), category_code="ZZBAS-" + uuid.uuid4().hex[:6], category_name="ZZ Basin",
                        class_label="ZZ Basin", search_synonyms=[], is_searchable=True, company_id=DEFAULT_COMPANY_ID),
        ProductCategory(id=str(uuid.uuid4()), category_code="ZZTRP-" + uuid.uuid4().hex[:6], category_name="ZZ Trap",
                        class_label="ZZ Trap", search_synonyms=[], is_searchable=True, company_id=DEFAULT_COMPANY_ID),
        PromotionType(id=str(uuid.uuid4()), type_code="zz_flyer", type_name="ZZ Flyer"),
    ])
    db.commit()


def _brand_label(session_factory) -> str:
    from app.services.chatbot import turn_runtime
    from app.services.chatbot.turn import context as context_mod

    rows = [r for r in turn_runtime.active_brands(scoped(session_factory)) if r["brand_name"] == BRAND]
    return context_mod.known_brands_line(rows).removeprefix("Known brands: ")


def seed_customers(session_factory, *names: str) -> None:
    from tests._mc_lookup_seed import customer

    db = session_factory()
    for n in names:
        customer(db, company_id=DEFAULT_COMPANY_ID, name=n)
    db.commit()


def seed_prompts(session_factory, *, template: str, parser_label=None, span_label=None,
                 global_kw=None) -> None:
    """Real registry rows and a real global config. `*_label` = (provider, model) on the production label row."""
    db = session_factory()
    _global(db, **(global_kw if global_kw is not None else {"gemini": GEMINI_KEY}))
    pl = parser_label or (None, None)
    _label(db, parser_mod.PROMPT_KEY, template=template, provider=pl[0], model=pl[1])
    if span_label is not None:
        _label(db, SPAN_KEY, template="Copy out the mentions of {{current_date}}.", provider=span_label[0], model=span_label[1])


def run(session_factory, stub_access, monkeypatch, *, text_body: str, span, template: str = BASE + SPANS_LINE + "\n",
        factory=None, seed: bool = True, **seed_kw):
    """One real turn. Returns a namespace: events, parser_configs, blocks, result, provider, factory_calls."""
    if seed:
        seed_prompts(session_factory, template=template, **seed_kw)
    monkeypatch.setattr(ll, "EMBED", None, raising=False)
    factory = factory or session_factory
    events: list = []
    parser_configs: list = []
    blocks: list[str] = []

    def parse(config, user_block):
        events.append("parser")
        parser_configs.append(config)
        blocks.append(str(user_block))
        return _parser_output(intent_hint="check_stock", domain_hint="inventory", user_goal="ask", entities=[])

    check = None
    if hasattr(factory, "state"):
        opened: list[int] = []
        check = lambda: opened.append(factory.state["open"])  # noqa: E731
    else:
        opened = []
    provider = FakeProvider(events, span, check)
    built: list[tuple] = []

    def get_provider(name, api_key, model):
        built.append((name, model))
        return provider

    monkeypatch.setattr("app.services.llm_provider.get_provider", get_provider)
    monkeypatch.setattr(parser_mod, "parse", parse)
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access()
    message = {"event_type": "message.received", "contact": {"id": CONTACT_ID}, "message": {
        "messageId": f"ZZT-span-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
        "traffic": "incoming", "message": {"type": "text", "text": text_body}}}
    result = engine_mod.run_turn(_envelope(message=message), session_factory=factory)
    return type("Run", (), dict(
        events=events, parser_configs=parser_configs, lines=blocks[-1].splitlines() if blocks else [],
        result=result, provider=provider, built=built, opened=opened,
    ))


def trace_events(session_factory, run_, kind: str = "span_extract") -> list[dict]:
    row = _turn_row(session_factory, run_.result.turn_id)
    return [r for r in (row.trace or []) if isinstance(r, dict) and r.get("kind") == kind]


def usage_rows(session_factory) -> list:
    return session_factory().query(AIAssistantUsageLog).filter(AIAssistantUsageLog.feature == SPAN_FEATURE).all()


# ---------------------------------------------------------------------------------------------- AC-S2-1
@pytest.mark.parametrize("template", [BASE + LISTS_LINE + "\n", BASE], ids=["lists_marker_only", "no_marker"])
def test_ac_s2_1_version_without_the_span_marker_makes_no_span_call(
    session_factory, seeded, stub_access, monkeypatch, template
):
    seed_world(session_factory)
    r = run(session_factory, stub_access, monkeypatch, text_body=f"{BRAND.lower()} basin", span=spans_json((BRAND, "brand")),
            template=template)
    assert r.provider.calls == [] and r.events == ["parser"], r.events
    assert trace_events(session_factory, r) == []
    assert usage_rows(session_factory) == []
    if LISTS_LINE in template:  # today's n-gram path still ran
        assert HDR["brand"] in r.lines and f"- {_brand_label(session_factory)}" in r.lines, r.lines


def test_ac_s2_1_the_marker_is_a_parser_config_flag_off_without_the_line(session_factory, seeded):
    seed_prompts(session_factory, template=BASE + LISTS_LINE + "\n")
    db = session_factory()
    cfg = parser_mod.resolve_config(db, current_date="2026-10-26")
    assert getattr(cfg, "lookup_spans") is False
    from app.services.chatbot_lookup_edits import SPAN_MARKER

    assert SPAN_MARKER == SPANS_LINE


def test_ac_s2_1_the_marker_line_switches_lookup_spans_on(session_factory, seeded):
    seed_prompts(session_factory, template=BASE + SPANS_LINE + "\n")
    cfg = parser_mod.resolve_config(session_factory(), current_date="2026-10-26")
    assert cfg.lookup_spans is True


# ---------------------------------------------------------------------------------------------- AC-S2-2
def test_ac_s2_2_one_span_call_before_the_parser_with_no_session_open(
    counting_session_factory, session_factory, seeded, stub_access, monkeypatch
):
    seed_world(session_factory)
    r = run(session_factory, stub_access, monkeypatch, text_body=f"{BRAND.lower()} basin", span=spans_json((BRAND, "brand")),
            factory=counting_session_factory)
    assert r.events == ["span", "parser"], r.events
    assert len(r.provider.calls) == 1
    assert r.opened == [0], ("a DB session was open during the span call", r.opened)
    assert HDR["brand"] in r.lines and f"- {_brand_label(session_factory)}" in r.lines, r.lines


def test_ac_s2_2_a_dealer_is_never_offered_another_dealers_customer(session_factory, seeded, stub_access, monkeypatch):
    _link_customers(session_factory, OWN)
    _other_customer(session_factory, OTHER)
    r = run(session_factory, stub_access, monkeypatch, text_body=f"{OWN} and {OTHER}".lower(),
            span=spans_json((OWN, "customer"), (OTHER, "customer")))
    assert r.provider.calls, "the span call must have run"
    assert HDR["customer"] in r.lines and f"- {OWN}" in r.lines, r.lines
    assert not any(OTHER in ln for ln in r.lines), r.lines


def test_ac_s2_2_staff_sees_every_customer(session_factory, seeded, stub_access, monkeypatch):
    seed_customers(session_factory, OWN, OTHER)
    _give_access_type(session_factory, "Sorento Office")
    r = run(session_factory, stub_access, monkeypatch, text_body=f"{OWN} and {OTHER}".lower(),
            span=spans_json((OWN, "customer"), (OTHER, "customer")))
    assert f"- {OWN}" in r.lines and f"- {OTHER}" in r.lines, r.lines


def test_ac_s2_2_a_contact_with_no_link_and_no_office_access_gets_no_customer_row(
    session_factory, seeded, stub_access, monkeypatch
):
    seed_customers(session_factory, OWN)
    r = run(session_factory, stub_access, monkeypatch, text_body=OWN.lower(), span=spans_json((OWN, "customer")))
    assert r.provider.calls
    assert HDR["customer"] not in r.lines and not any(OWN in ln for ln in r.lines), r.lines


@pytest.mark.parametrize("may_see", [True, False])
def test_ac_s2_2_salespeople_rows_only_when_the_contact_may_see_them(
    session_factory, seeded, stub_access, monkeypatch, may_see
):
    db = session_factory()
    db.add(SalesAgent(id=str(uuid.uuid4()), sales_agent="ZZ SEAN I", person_label="ZZ Sean", aliases="", is_active=True))
    db.commit()
    monkeypatch.setattr(engine_mod, "_may_see_salespeople", lambda db_, resolved: may_see)
    r = run(session_factory, stub_access, monkeypatch, text_body="zz sean i", span=spans_json(("ZZ SEAN I", "salesperson")))
    assert (HDR["salesperson"] in r.lines) is may_see, r.lines
    assert ("- ZZ SEAN I" in r.lines) is may_see, r.lines


# ---------------------------------------------------------------------------------------------- AC-S2-3
def test_ac_s2_3_a_product_code_span_offers_no_customer_promotion_or_spec_rows(
    session_factory, seeded, stub_access, monkeypatch
):
    seed_world(session_factory)
    seed_customers(session_factory, OWN)
    _give_access_type(session_factory, "Sorento Office")
    r = run(session_factory, stub_access, monkeypatch, text_body="check stock SRTWC8065", span=spans_json(("SRTWC8065", "product_code")))
    assert r.provider.calls
    for key in ("customer", "promotion_kind", "spec"):
        assert HDR[key] not in r.lines, (key, r.lines)
    assert not any(ln.startswith("- ") for ln in r.lines if ln in {f"- {OWN}", "- ZZ Flyer"}), r.lines


def test_ac_s2_3_a_brand_span_offers_the_brand_row_and_nothing_unnamed(session_factory, seeded, stub_access, monkeypatch):
    seed_world(session_factory)
    seed_customers(session_factory, OWN)
    _give_access_type(session_factory, "Sorento Office")
    r = run(session_factory, stub_access, monkeypatch, text_body=f"{BRAND.lower()} stock", span=spans_json((BRAND, "brand")))
    assert HDR["brand"] in r.lines and f"- {_brand_label(session_factory)}" in r.lines, r.lines
    assert HDR["customer"] not in r.lines and HDR["promotion_kind"] not in r.lines, r.lines


def test_ac_s2_3_an_empty_span_list_offers_no_rows_at_all(session_factory, seeded, stub_access, monkeypatch):
    seed_world(session_factory)
    r = run(session_factory, stub_access, monkeypatch, text_body="any promotion?", span=spans_json())
    assert r.provider.calls
    assert not any(ln.endswith("(pick one only if the message means it):") for ln in r.lines), r.lines


# ---------------------------------------------------------------------------------------------- AC-S2-4
def test_ac_s2_4_an_ambiguous_span_renders_at_most_top_k_rows_and_the_trace_counts_the_close_ones(
    session_factory, seeded, stub_access, monkeypatch
):
    agents = [SalesAgent(id=str(uuid.uuid4()), sales_agent=f"ZZLEE - {n}", person_label=f"ZZ Lee {n}", aliases="ZZLee", is_active=True)
              for n in ("I", "II", "III", "IV", "V", "VI", "VII")]
    agents += [SalesAgent(id=str(uuid.uuid4()), sales_agent=f"ZZOTHER - {n}", person_label=f"ZZ Other {n}", aliases="", is_active=True)
               for n in ("I", "II", "III")]
    db = session_factory()
    db.add_all(agents)
    db.commit()
    monkeypatch.setattr(engine_mod, "_may_see_salespeople", lambda db_, resolved: True)
    r = run(session_factory, stub_access, monkeypatch, text_body="zzlee sales", span=spans_json(("ZZLee", "salesperson")))
    block = r.lines[r.lines.index(HDR["salesperson"]) + 1:]
    rows = []
    for ln in block:
        if not ln.startswith("- "):
            break
        rows.append(ln)
    assert len(rows) == ll.TOP_K["salesperson"] == 5, rows
    assert all(ln.startswith("- ZZLEE - ") for ln in rows), rows
    ev = trace_events(session_factory, r)
    assert len(ev) == 1
    assert ev[0]["spans"][0]["status"] == "ambiguous" and ev[0]["spans"][0]["close"] == 7, ev[0]["spans"]


# ---------------------------------------------------------------------------------------------- AC-S2-5
@pytest.mark.parametrize("output", [
    RuntimeError("zz provider down"),
    llm_call.TimedOut("zz no answer"),
    "this is not json {",
    json.dumps({"spans": "not a list"}),
], ids=["raises", "timeout", "invalid_json", "wrong_shape"])
def test_ac_s2_5_a_failing_span_call_leaves_todays_ngram_lines_and_the_turn_answers(
    session_factory, seeded, stub_access, monkeypatch, output
):
    seed_world(session_factory)
    body = f"{BRAND.lower()} zz basin"
    db = scoped(session_factory)
    from app.services.chatbot import turn_runtime

    rows = ll.load_rows(db)
    expected = ll.render(ll.shortlist(body, rows, None, brand_words=ll.brand_words(db, turn_runtime.active_brands(db))))
    assert expected, "the control must offer rows or the test proves nothing"
    r = run(session_factory, stub_access, monkeypatch, text_body=body, span=output)
    assert r.events == ["span", "parser"], r.events
    assert all(line in r.lines for line in expected), (expected, r.lines)
    ev = trace_events(session_factory, r)
    assert len(ev) == 1 and ev[0]["fallback"] is True, ev
    assert (r.result.reply or {}).get("text"), r.result


# ---------------------------------------------------------------------------------------------- AC-S2-6
def test_ac_s2_6_usage_row_and_trace_event(session_factory, seeded, stub_access, monkeypatch):
    seed_world(session_factory)
    r = run(session_factory, stub_access, monkeypatch, text_body=f"{BRAND.lower()} stock", span=spans_json((BRAND, "brand")))
    rows = usage_rows(session_factory)
    assert len(rows) == 1, rows
    u = rows[0]
    assert (u.prompt_tokens, u.completion_tokens, u.total_tokens) == (11, 7, 18)
    assert (u.provider, u.model) == ("openai", "gpt-global")
    ev = trace_events(session_factory, r)
    assert len(ev) == 1
    e = ev[0]
    assert e["spans"][0]["text"] == BRAND and e["spans"][0]["type"] == "brand" and e["spans"][0]["status"] == "resolved", e
    assert e["rows_rendered"] >= 1 and isinstance(e["ms"], (int, float)), e
    assert (e["provider"], e["model"], e["model_source"]) == ("openai", "gpt-global", "global"), e
    assert e["fallback"] is False


def test_ac_s2_6_a_failed_call_still_leaves_one_trace_event_and_no_cost_claimed(session_factory, seeded, stub_access, monkeypatch):
    seed_world(session_factory)
    r = run(session_factory, stub_access, monkeypatch, text_body="zz basin", span=RuntimeError("zz down"))
    assert len(trace_events(session_factory, r)) == 1
    assert all(u.total_tokens == 0 for u in usage_rows(session_factory))


# ---------------------------------------------------------------------------------------------- AC-S2-7
def _ladder(session_factory, stub_access, monkeypatch, caplog=None, **kw):
    seed_world(session_factory)
    r = run(session_factory, stub_access, monkeypatch, text_body=f"{BRAND.lower()} stock", span=spans_json((BRAND, "brand")), **kw)
    ev = trace_events(session_factory, r)
    assert len(ev) == 1 and len(r.provider.calls) == 1, (ev, r.events)
    span = (ev[0]["provider"], ev[0]["model"], ev[0]["model_source"])
    assert r.built[0] == (span[0], span[1]), ("the provider the span call built", r.built, span)
    parser_cfg = r.parser_configs[-1]
    return span, (parser_cfg.provider, parser_cfg.model, parser_cfg.model_source), r


def test_ac_s2_7_contact_override_rung(session_factory, seeded, stub_access, monkeypatch):
    seed_world(session_factory)
    db = session_factory()
    db.execute(text("UPDATE respond_contacts SET chatbot_llm_provider = 'gemini', chatbot_llm_model = :m WHERE respond_io_id = :c"),
               {"m": CHOICE_MODEL, "c": str(CONTACT_ID)})
    db.commit()
    r = run(session_factory, stub_access, monkeypatch, text_body=f"{BRAND.lower()} stock", span=spans_json((BRAND, "brand")),
            parser_label=("openai", "gpt-parser-label"), span_label=("openai", "gpt-span-label"))
    ev = trace_events(session_factory, r)[0]
    cfg = r.parser_configs[-1]
    assert (ev["provider"], ev["model"], ev["model_source"]) == ("gemini", CHOICE_MODEL, "contact")
    assert r.built[0] == ("gemini", CHOICE_MODEL)
    assert (cfg.provider, cfg.model, cfg.model_source) == ("gemini", CHOICE_MODEL, "contact")


def test_ac_s2_7_tag_rung(session_factory, seeded, stub_access, monkeypatch):
    seed_world(session_factory)
    _tag_the_contact(session_factory, {"provider": "gemini", "model": CHOICE_MODEL}, name="ZZT span tag")
    r = run(session_factory, stub_access, monkeypatch, text_body=f"{BRAND.lower()} stock", span=spans_json((BRAND, "brand")),
            parser_label=("openai", "gpt-parser-label"), span_label=("openai", "gpt-span-label"))
    ev = trace_events(session_factory, r)[0]
    cfg = r.parser_configs[-1]
    assert (ev["provider"], ev["model"], ev["model_source"]) == ("gemini", CHOICE_MODEL, "tag")
    assert r.built[0] == ("gemini", CHOICE_MODEL)
    assert (cfg.provider, cfg.model, cfg.model_source) == ("gemini", CHOICE_MODEL, "tag")


def test_ac_s2_7_span_prompt_label_rung(session_factory, seeded, stub_access, monkeypatch):
    span, parser, _r = _ladder(session_factory, stub_access, monkeypatch,
                               parser_label=("openai", "gpt-parser-label"), span_label=("openai", "gpt-span-label"))
    assert span == ("openai", "gpt-span-label", "label")
    assert parser == ("openai", "gpt-parser-label", "label")


def test_ac_s2_7_global_rung(session_factory, seeded, stub_access, monkeypatch):
    span, parser, _r = _ladder(session_factory, stub_access, monkeypatch)
    assert span == ("openai", "gpt-global", "global")
    assert parser == ("openai", "gpt-global", "global")


def test_ac_s2_7_chosen_provider_without_a_key_falls_back_and_logs_no_key(
    session_factory, seeded, stub_access, monkeypatch, caplog
):
    seed_world(session_factory)
    _tag_the_contact(session_factory, {"provider": "gemini", "model": CHOICE_MODEL}, name="ZZT nokey tag")
    with caplog.at_level(logging.DEBUG):
        r = run(session_factory, stub_access, monkeypatch, text_body=f"{BRAND.lower()} stock", span=spans_json((BRAND, "brand")),
                parser_label=("openai", "gpt-parser-label"), span_label=("openai", "gpt-span-label"),
                global_kw={"gemini": ""})
    ev = trace_events(session_factory, r)[0]
    cfg = r.parser_configs[-1]
    assert (ev["provider"], ev["model"], ev["model_source"]) == ("openai", "gpt-span-label", "fallback_no_key")
    assert r.built[0] == ("openai", "gpt-span-label")
    assert (cfg.provider, cfg.model, cfg.model_source) == ("openai", "gpt-parser-label", "fallback_no_key")
    for record in caplog.records:
        assert GLOBAL_KEY not in record.getMessage() and GEMINI_KEY not in record.getMessage()


# ---------------------------------------------------------------------------------------------- AC-S2-8
VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
PARSER = "chatbot_semantic_parser"
ANCHOR = "A long wordy span anchor sentence that the diet edit shortens."
PROD_TEXT = f"Rules for {{{{current_date}}}}.\n{ANCHOR}\nTail rule.\n{LISTS_LINE}\n"


def _migration():
    files = sorted(VERSIONS.glob("eem_0001*.py"))
    assert len(files) == 1, f"expected one eem_0001 migration, found {files}"
    spec = importlib.util.spec_from_file_location("_eem_0001_test", files[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def _small_diet(monkeypatch):
    from app.services import chatbot_lookup_edits as lle
    from app.services import chatbot_prompt_diet_edits as diet

    monkeypatch.setattr(diet, "EDITS", (lle.Edit("replace", ANCHOR, "Short."),))


def _versions(db, name=PARSER):
    return db.query(AIPromptVersion).filter(AIPromptVersion.name == name).order_by(AIPromptVersion.version).all()


def _production(db, template=PROD_TEXT, version=80):
    row = AIPromptVersion(id=str(uuid.uuid4()), name=PARSER, version=version, type="text", template=template, variables=["current_date"])
    db.add(row)
    db.flush()
    db.add(AIPromptLabel(name=PARSER, label="production", version_id=row.id))
    db.flush()
    return row


def test_ac_s2_8_revision_ids_and_single_head():
    m = _migration()
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    assert m.revision == "eem_0001_span_pass" and len(m.revision) <= 32
    script = ScriptDirectory.from_config(Config(str(VERSIONS.parents[1] / "alembic.ini")))
    assert script.get_revision(m.down_revision) is not None, m.down_revision
    heads = script.get_heads()
    assert len(heads) == 1, heads
    assert m.revision in {r.revision for r in script.walk_revisions(base="base", head=heads[0])}  # a later migration may follow


def test_ac_s2_8_upgrade_seeds_the_span_prompt_labelled_production(_small_diet):
    m = _migration()
    with blank_session() as db:
        _production(db)
        with mock.patch.object(m.op, "get_bind", return_value=db.connection()):
            m.upgrade()
        db.expire_all()
        label = db.query(AIPromptLabel).filter_by(name=SPAN_KEY, label="production").one()
        v = db.query(AIPromptVersion).filter_by(id=label.version_id).one()
        assert v.name == SPAN_KEY and v.version == 1 and v.template.strip()


def test_ac_s2_8_publishes_one_unlabelled_parser_version_with_the_span_marker(_small_diet):
    m = _migration()
    from app.services.chatbot_lookup_edits import SPAN_MARKER

    with blank_session() as db:
        prod = _production(db)
        assert m.publish_on_production(db) == 81
        rows = _versions(db)
        assert [r.version for r in rows] == [80, 81]
        new = rows[-1]
        assert SPAN_MARKER in new.template.splitlines() and LISTS_LINE not in new.template, new.template
        assert "Short." in new.template and ANCHOR not in new.template
        labels = db.query(AIPromptLabel).filter(AIPromptLabel.name == PARSER).all()
        assert [(lbl.label, lbl.version_id) for lbl in labels] == [("production", prod.id)]
        assert db.query(AIPromptLabel).filter(AIPromptLabel.version_id == new.id).count() == 0


def test_ac_s2_8_a_rerun_publishes_nothing(_small_diet):
    m = _migration()
    with blank_session() as db:
        _production(db)
        assert m.publish_on_production(db) is not None
        assert m.publish_on_production(db) is None
        assert len(_versions(db)) == 2


def test_ac_s2_8_downgrade_removes_only_its_own_rows(_small_diet):
    m = _migration()
    with blank_session() as db:
        prod = _production(db)
        with mock.patch.object(m.op, "get_bind", return_value=db.connection()):
            m.upgrade()
            db.add(AIPromptVersion(id=str(uuid.uuid4()), name=PARSER, version=90, type="text", template="someone else's",
                                   variables=[], commit_message="not ours"))
            db.flush()
            m.downgrade()
        db.expire_all()
        assert [r.version for r in _versions(db)] == [80, 90]
        assert _versions(db)[0].id == prod.id
        assert _versions(db, SPAN_KEY) == []
        assert [(lbl.label, lbl.version_id) for lbl in db.query(AIPromptLabel).filter(AIPromptLabel.name == PARSER)] == [("production", prod.id)]


# ---------------------------------------------------------------------------------------------- S2 review round
def _ngram_expected(session_factory, body: str, *, numbers: bool = False) -> list[str]:
    """Today's lines for `body` offline: shortlist plus (as `_lookup_lines` does) the number hits."""
    from app.services.chatbot import turn_runtime

    db = scoped(session_factory)
    hits = ll.shortlist(body, ll.load_rows(db), None, brand_words=ll.brand_words(db, turn_runtime.active_brands(db)))
    if numbers:
        nums = ll.number_hits(body, db, hidden_spec_keys=frozenset())
        assert nums, "the control message must carry a number the lookup understands"
        hits["spec"] = ll.with_numbers(nums, hits.get("spec", []), hits.get("category"))
    return ll.render(hits)


@pytest.mark.parametrize("output", [
    RuntimeError("zz provider down"), llm_call.TimedOut("zz no answer"), "this is not json {",
    json.dumps({"spans": "not a list"}),
], ids=["raises", "timeout", "invalid_json", "wrong_shape"])
def test_review_fallback_keeps_the_number_hits_of_todays_path(session_factory, seeded, stub_access, monkeypatch, output):
    from tests.chatbot.test_lookup_lists_s2 import HDR_SPEC, seed_world as seed_specs

    seed_world(session_factory)
    seed_specs(session_factory)
    body = "zz basin 200mm"
    expected = _ngram_expected(session_factory, body, numbers=True)
    assert HDR_SPEC in expected, expected
    r = run(session_factory, stub_access, monkeypatch, text_body=body, span=output)
    assert all(line in r.lines for line in expected), (expected, r.lines)


# Changed on purpose per the AC-S2-3 amendment (27 Oct, crew ruling V2): a row the message spells near-exactly
# (spelling >= 0.95) is offered even when the span call names nothing; a row only a LOOSE spelling (< 0.95) or
# the meaning reaches is still not offered.
@pytest.mark.parametrize("answer", [spans_json(), spans_json(("SRTWC8065", "product_code"))], ids=["no_spans", "product_code_only"])
def test_review_a_successful_call_naming_nothing_offers_the_exactly_spelled_row(
    session_factory, seeded, stub_access, monkeypatch, answer
):
    seed_world(session_factory)
    body = "zz basin price"
    control = _ngram_expected(session_factory, body)
    assert HDR["category"] in control and "- ZZ Basin" in control, ("the n-gram path must offer the row", control)
    r = run(session_factory, stub_access, monkeypatch, text_body=body, span=answer)
    assert r.provider.calls
    assert HDR["category"] in r.lines and "- ZZ Basin" in r.lines, r.lines


@pytest.mark.parametrize("answer", [spans_json(), spans_json(("SRTWC8065", "product_code"))], ids=["no_spans", "product_code_only"])
def test_review_a_successful_call_naming_nothing_offers_no_loosely_spelled_row(
    session_factory, seeded, stub_access, monkeypatch, answer
):
    seed_world(session_factory)
    body = "zz basn price"  # "ZZ Basin" by spelling 0.545: the n-gram path offers it, the near-exact rule must not
    control = _ngram_expected(session_factory, body)
    assert "- ZZ Basin" in control, ("control: the n-gram path offers the loose-spelled row", control)
    r = run(session_factory, stub_access, monkeypatch, text_body=body, span=answer)
    assert r.provider.calls
    assert "- ZZ Basin" not in r.lines, r.lines


def test_review_near_exact_rows_join_the_span_rows_without_duplicates_and_top_k_caps_them(
    session_factory, seeded, stub_access, monkeypatch
):
    db = session_factory()
    db.add_all([Brand(id=str(uuid.uuid4()), brand_code=f"ZZ{n[2]}", brand_name=n, is_active=True, company_id=DEFAULT_COMPANY_ID)
                for n in ("ZZALFA", "ZZBRAVO", "ZZCHARLIE", "ZZDELTA")])
    db.commit()
    body = "zzalfa zzbravo zzcharlie zzdelta stock"
    control = _ngram_expected(session_factory, body)
    assert sum(1 for ln in control if ln.startswith("- ZZ")) == 3, ("control: the n-gram path offers spelled brands up to TOP_K", control)
    r = run(session_factory, stub_access, monkeypatch, text_body=body, span=spans_json(("ZZDELTA", "brand")))
    block = r.lines[r.lines.index(HDR["brand"]) + 1:]
    rows = []
    for ln in block:
        if not ln.startswith("- "):
            break
        rows.append(ln)
    assert len(rows) == ll.TOP_K["brand"] == 3, rows
    assert rows[0].startswith("- ZZDELTA"), ("the span row comes first", rows)
    assert sum(1 for ln in rows if ln.startswith("- ZZDELTA")) == 1, rows
    assert all(ln.startswith(("- ZZALFA", "- ZZBRAVO", "- ZZCHARLIE", "- ZZDELTA")) for ln in rows), rows


def test_review_a_resolver_failure_falls_back_to_todays_ngram_lines(session_factory, seeded, stub_access, monkeypatch):
    from app.services.chatbot.head import list_resolver

    seed_world(session_factory)
    body = f"{BRAND.lower()} zz basin"
    expected = _ngram_expected(session_factory, body)
    assert expected

    def boom(*a, **k):
        raise RuntimeError("zz resolver down")

    monkeypatch.setattr(list_resolver, "resolve", boom)
    r = run(session_factory, stub_access, monkeypatch, text_body=body, span=spans_json((BRAND, "brand")))
    assert all(line in r.lines for line in expected), (expected, r.lines)
    ev = trace_events(session_factory, r)
    assert len(ev) == 1 and ev[0]["fallback"] is True, ev
    assert (r.result.reply or {}).get("text"), r.result


def test_review_a_failed_call_records_its_real_elapsed_ms(session_factory, seeded, stub_access, monkeypatch):
    import time

    def slow_fail():
        time.sleep(0.06)
        return RuntimeError("zz slow failure")

    seed_world(session_factory)
    r = run(session_factory, stub_access, monkeypatch, text_body="zz basin", span=slow_fail)
    ev = trace_events(session_factory, r)[0]
    assert ev["fallback"] is True and ev["ms"] >= 50, ev


def test_review_cached_tokens_are_zero_when_the_provider_reports_none(session_factory, seeded, stub_access, monkeypatch):
    """CHAT-CHANNEL-LOOKUPSET AC-CCL-7: a recorded 0, as the parser stores it (`parser.py` usage), so the span call
    prices (`analytics_connector.prices.cost_sql` reads a NULL as cache-unknown and blanks the turn's cost)."""
    seed_world(session_factory)
    run(session_factory, stub_access, monkeypatch, text_body=f"{BRAND.lower()} stock", span=spans_json((BRAND, "brand")))
    rows = usage_rows(session_factory)
    assert len(rows) == 1 and rows[0].cached_tokens == 0, [r.cached_tokens for r in rows]


# ---------------------------------------------------------------------------------------------- S2 crew audit
def test_audit_provider_sdk_is_imported_in_the_calling_thread_before_any_lookup_thread_starts():
    """Cold start: the warm-up / prefetch thread and the span call (main thread) must not both import the provider
    SDK lazily at the same time (KeyError 'openai.resources'). Deterministic: a fresh process, `Thread.start`
    recorded, a fake embedder that imports nothing (so only the caller can have imported the SDK)."""
    import subprocess
    import sys

    backend = Path(__file__).resolve().parents[2]
    code = """
import sys, threading
sys.path.insert(0, %r)
import app.main  # noqa
from app.services.chatbot.head import lookup_lists as ll
assert 'openai.resources' not in sys.modules, 'precondition: the SDK is not imported eagerly by the app'
seen = {}
real = threading.Thread.start
def start(self):
    if (self.name or '').startswith('lookup-lists'):
        seen[self.name] = 'openai.resources' in sys.modules
    return real(self)
threading.Thread.start = start
class E:
    needs_warm = True
    def pieces(self, texts): return [[0.0]] * len(texts)
    def fill(self, texts): return None
    def __call__(self, texts): return [[0.0]] * len(texts)
    def is_cached(self, texts): return False
rows = [ll.LookupRow('brand', 'b1', 'ZZBRAND', ('ZZBRAND',))]
ll.prefetch('zz basin price', E())()
ll.warm(rows, E())
import time; time.sleep(0.3)
print(repr(seen))
""" % str(backend)
    out = subprocess.run([sys.executable, "-I", "-c", code], cwd=backend, capture_output=True, text=True, timeout=120,
                         env={**__import__("os").environ, "PYTHONPATH": str(backend)})
    assert out.returncode == 0, out.stderr[-1500:]
    seen = eval(out.stdout.strip().splitlines()[-1])  # noqa: S307 - our own repr of a dict of bools
    assert set(seen) == {"lookup-lists-prefetch", "lookup-lists-warm"}, seen
    assert all(seen.values()), seen


def _sean_world(session_factory):
    db = session_factory()
    db.add_all([
        SalesAgent(id=str(uuid.uuid4()), sales_agent=f"ZZSEAN {n}", person_label=f"ZZSEAN {n}", aliases="ZZSEAN", is_active=True)
        for n in ("I", "III", "IV")
    ] + [
        SalesAgent(id=str(uuid.uuid4()), sales_agent=f"ZZROMEO {n}", person_label=f"ZZROMEO {n}", aliases="", is_active=True)
        for n in ("I", "II", "III")
    ] + [
        Brand(id=str(uuid.uuid4()), brand_code="ZZSRT", brand_name="ZZSORENTO", is_active=True, company_id=DEFAULT_COMPANY_ID),
        Brand(id=str(uuid.uuid4()), brand_code="ZZCAB", brand_name="ZZCABANA", is_active=True, company_id=DEFAULT_COMPANY_ID),
    ])
    db.commit()


def test_audit_a_merged_name_span_yields_both_the_person_and_the_brand(session_factory, seeded, stub_access, monkeypatch):
    _sean_world(session_factory)
    monkeypatch.setattr(engine_mod, "_may_see_salespeople", lambda db_, resolved: True)
    r = run(session_factory, stub_access, monkeypatch, text_body="Sales agent ZZSean ZZSorento top 10",
            span=spans_json(("ZZSean ZZSorento", "salesperson")))
    assert HDR["salesperson"] in r.lines, r.lines
    for want in ("- ZZSEAN I", "- ZZSEAN III", "- ZZSEAN IV"):
        assert want in r.lines, (want, r.lines)
    assert HDR["brand"] in r.lines and any(ln.startswith("- ZZSORENTO") for ln in r.lines), r.lines


def test_audit_a_fully_matched_span_gets_no_extra_rows(session_factory, seeded, stub_access, monkeypatch):
    _sean_world(session_factory)
    monkeypatch.setattr(engine_mod, "_may_see_salespeople", lambda db_, resolved: True)
    r = run(session_factory, stub_access, monkeypatch, text_body="ZZSorento top 10", span=spans_json(("ZZSorento", "brand")))
    assert any(ln.startswith("- ZZSORENTO") for ln in r.lines), r.lines
    assert HDR["salesperson"] not in r.lines and not any(ln.startswith("- ZZSEAN") for ln in r.lines), r.lines


@pytest.mark.parametrize("mode, reason", [
    ("raises", "call_error"), ("timeout", "timeout"), ("invalid_json", "invalid_answer"),
    ("wrong_shape", "invalid_answer"), ("resolver", "resolver_error"), ("no_config", "no_config"), ("ok", None),
])
def test_audit_the_trace_names_why_it_fell_back(session_factory, seeded, stub_access, monkeypatch, mode, reason):
    from app.services.chatbot.head import list_resolver, span_extract

    seed_world(session_factory)
    answer = {
        "raises": RuntimeError("zz down"), "timeout": llm_call.TimedOut("zz slow"), "invalid_json": "not json {",
        "wrong_shape": json.dumps({"spans": "x"}),
    }.get(mode, spans_json((BRAND, "brand")))

    def boom(*a, **k):
        raise RuntimeError("zz boom")

    if mode == "resolver":
        monkeypatch.setattr(list_resolver, "resolve", boom)
    if mode == "no_config":
        monkeypatch.setattr(span_extract, "resolve_config", boom)
    r = run(session_factory, stub_access, monkeypatch, text_body=f"{BRAND.lower()} stock", span=answer)
    ev = trace_events(session_factory, r)
    assert len(ev) == 1 and "fallback_reason" in ev[0], ev
    assert ev[0]["fallback_reason"] == reason, ev[0]
    assert ev[0]["fallback"] is (reason is not None)


# ---------------------------------------------------------------------------------------------- drawer detail
def test_trace_event_carries_per_span_candidates_the_near_exact_union_and_the_final_block_sources(
    session_factory, seeded, stub_access, monkeypatch
):
    db = session_factory()
    db.add_all([Brand(id=str(uuid.uuid4()), brand_code=f"ZZ{n[2]}", brand_name=n, is_active=True, company_id=DEFAULT_COMPANY_ID)
                for n in ("ZZALFA", "ZZBRAVO", "ZZCHARLIE", "ZZDELTA")])
    db.commit()
    r = run(session_factory, stub_access, monkeypatch, text_body="zzalfa zzbravo zzcharlie zzdelta stock",
            span=spans_json(("ZZDELTA", "brand")))
    e = trace_events(session_factory, r)[0]
    cands = e["spans"][0]["candidates"]
    assert cands and cands[0]["label"].startswith("ZZDELTA") and cands[0]["list"] == "brand", cands
    assert set(cands[0]) == {"list", "label", "score", "signal"} and cands[0]["signal"] in ("exact", "spell", "partial", "meaning")
    near = e["near_exact"]
    assert near and all(n["source"] == "near_exact" and set(n) == {"list", "label", "spelling", "source"} for n in near), near
    assert not any(n["label"].startswith("ZZDELTA") for n in near), near
    assert len(near) == e["near_exact_rows"]
    block = e["final_block"]["brand"]
    assert [b["source"] for b in block][0] == "span" and block[0]["label"].startswith("ZZDELTA"), block
    assert len(block) == ll.TOP_K["brand"] and {b["source"] for b in block[1:]} == {"near_exact"}, block
