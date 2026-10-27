"""EEM-CATEGORY-PICK red tests (AC-CP-1..11): parser markers, grouped category block, class report, parsed reply
language. Plan: documentation/plans/chatbot/PLAN-eem-category-pick-27oct.md. Category codes only, no customer names."""
from __future__ import annotations

import dataclasses
import types
import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.models.base import set_company_scope
from app.models.product import ProductCategory
from app.services import ai_prompt_registry, llm_provider
from app.services import chatbot_prompt_vars as pv
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import language
from app.services.chatbot.head import list_resolver, span_extract
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.lanes import business as business_pkg
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services import product_class_signal
from tests._pg_fixture import blank_session
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import stub_access  # noqa: F401
from tests.chatbot.test_lookup_lists_engine import _fresh_caches  # noqa: F401

WC_CODES = ["BRT-WC", "CB-WC", "IDC-WC", "M-WC", "SRT-WC"]
CLASS = "Water Closet"


# ------------------------------------------------------------------------------------------------ A markers
@pytest.fixture(autouse=True)
def _prompt_caches():
    ai_prompt_registry.bust_cache()
    pv.clear_cache()
    yield
    ai_prompt_registry.bust_cache()
    pv.clear_cache()


def _config_for(session_factory, monkeypatch, template):
    from app.services import ai_assistant_service

    db = session_factory()
    v = AIPromptVersion(id=str(uuid.uuid4()), name=parser_mod.PROMPT_KEY, version=1, type="text",
                        template=template, variables=["current_date"])
    db.add(v)
    db.flush()
    db.add(AIPromptLabel(id=str(uuid.uuid4()), name=parser_mod.PROMPT_KEY, label="production", version_id=v.id))
    db.commit()
    cfg = types.SimpleNamespace(provider="openai", model="gpt-test")
    monkeypatch.setattr(ai_assistant_service, "AIAssistantConfigService", lambda d: types.SimpleNamespace(get=lambda: cfg))
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda config, provider: "sk-test")
    db = session_factory()
    try:
        return parser_mod.resolve_config(db, current_date="2026-10-27")
    finally:
        db.close()


GATE = "== CLOSED LISTS ==\n"


def test_ac_cp_1_the_markers_are_string_constants():
    assert isinstance(parser_mod.CATEGORY_PICK_ASK, str) and parser_mod.CATEGORY_PICK_ASK.strip()
    assert isinstance(parser_mod.LANGUAGE_ASK, str) and parser_mod.LANGUAGE_ASK.strip()
    assert parser_mod.CATEGORY_PICK_ASK != parser_mod.LANGUAGE_ASK


def test_ac_cp_1_a_template_with_the_category_sentence_sets_category_pick(session_factory, monkeypatch):
    config = _config_for(session_factory, monkeypatch,
                         "Rules {{current_date}}.\n" + GATE + parser_mod.CATEGORY_PICK_ASK + "\n")
    assert config.category_pick is True


def test_ac_cp_1_a_template_without_the_sentence_keeps_category_pick_false(session_factory, monkeypatch):
    config = _config_for(session_factory, monkeypatch, "Rules {{current_date}}.\n" + GATE)
    assert getattr(config, "category_pick", "missing") is False


def test_ac_cp_9_the_language_sentence_adds_message_language_to_the_schema(session_factory, monkeypatch):
    config = _config_for(session_factory, monkeypatch,
                         "Rules {{current_date}}.\n" + GATE + parser_mod.LANGUAGE_ASK + "\n")
    prop = config.json_schema["properties"]["message_language"]
    values = prop.get("enum") or [v for branch in prop.get("anyOf", []) for v in branch.get("enum", [])]
    assert {"en", "ms", "zh"} <= set(values), prop
    assert "message_language" in config.json_schema["required"]


def test_ac_cp_9_without_the_sentence_the_schema_is_exactly_todays(session_factory, monkeypatch):
    config = _config_for(session_factory, monkeypatch, "Rules {{current_date}}.\n" + GATE)
    assert "message_language" not in config.json_schema["properties"]
    assert "message_language" not in config.json_schema["required"]


def test_ac_cp_9_with_message_language_is_a_pure_copy_that_only_adds_the_key():
    base = parser_mod._build_base_json_schema()
    out = parser_mod.with_message_language(base)
    assert "message_language" not in base["properties"]
    assert set(out["properties"]) - set(base["properties"]) == {"message_language"}
    assert out["required"][-1] == "message_language"


# ------------------------------------------------------------------------------------------------ B block
def _row(label, group, key=None, *texts):
    return ll.LookupRow("category", key or label, label, tuple(texts) or (label,), group)


def _hit(row):
    return ll.Hit(row, row.label, 1.0, 0.0)


def test_ac_cp_3_lookup_row_has_an_optional_group():
    assert ll.LookupRow("category", "k", "L", ("L",)).group is None


def test_ac_cp_3_render_grouped_prints_one_line_per_class():
    cls = _row(CLASS, CLASS, "type:water closet")
    rows = [_row(c, CLASS) for c in ("BRT-WC", "CB-WC", "IDC-WC", "M-WC", "SRT-WC", "WC")]
    hits = {"category": [_hit(r) for r in [cls, *rows]]}
    lines = ll.render(hits, group_categories=True)
    assert lines == [ll.header("category"), "- Water Closet: BRT-WC, CB-WC, IDC-WC, M-WC, SRT-WC, WC"], lines


def test_ac_cp_3_a_class_with_only_its_own_row_prints_the_bare_class():
    hits = {"category": [_hit(_row(CLASS, CLASS, "type:water closet"))]}
    assert ll.render(hits, group_categories=True) == [ll.header("category"), "- Water Closet"]


def test_ac_cp_3_groups_keep_first_seen_order_and_group_none_prints_its_label():
    sink = _row("SRT-KS", "Kitchen Sink")
    plain = _row("ZZ Plain", None)
    wc = _row("SRT-WC", CLASS)
    sink2 = _row("CB-KS", "Kitchen Sink")
    lines = ll.render({"category": [_hit(sink), _hit(plain), _hit(wc), _hit(sink2)]}, group_categories=True)
    assert lines[1:] == ["- Kitchen Sink: SRT-KS, CB-KS", "- ZZ Plain", "- Water Closet: SRT-WC"], lines


def test_ac_cp_5_grouping_off_is_byte_identical_to_today():
    rows = [_row("BRT-WC", CLASS), _row("WC", CLASS), _row("ZZ Plain", None)]
    hits = {"category": [_hit(r) for r in rows]}
    assert ll.render(hits) == [ll.header("category"), "- BRT-WC", "- WC", "- ZZ Plain"]
    assert ll.render(hits, group_categories=False) == ll.render(hits)


def test_ac_cp_3_other_lists_are_not_grouped():
    hits = {"brand": [_hit(ll.LookupRow("brand", "b1", "SORENTO", ("SORENTO",), "x"))]}
    assert ll.render(hits, group_categories=True) == [ll.header("brand"), "- SORENTO"]


# category + class seeding on a blank schema
def _seed_categories(db):
    set_company_scope(db, None)
    made = {}
    for code in WC_CODES:
        made[code] = ProductCategory(id=str(uuid.uuid4()), category_code=code, category_name=code,
                                     class_label=CLASS, search_synonyms=["wc"], company_id=DEFAULT_COMPANY_ID)
    made["WC"] = ProductCategory(id=str(uuid.uuid4()), category_code="WC", category_name="WC",
                                 company_id=DEFAULT_COMPANY_ID)
    made["SRT-KS"] = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS",
                                     class_label="Kitchen Sink", search_synonyms=["sink"], company_id=DEFAULT_COMPANY_ID)
    made["ZZMISC"] = ProductCategory(id=str(uuid.uuid4()), category_code="ZZMISC", category_name="ZZ Misc",
                                     company_id=DEFAULT_COMPANY_ID)
    db.add_all(made.values())
    db.flush()
    return made


def test_ac_cp_4_category_class_prefers_the_class_label():
    with blank_session() as db:
        _seed_categories(db)
        assert product_class_signal.category_class(db, code="SRT-WC", name="SRT-WC", class_label=CLASS) == CLASS
        assert product_class_signal.category_class(db, code="X", name="X", class_label="Whatever") == "Whatever"


def test_ac_cp_4_a_classless_generic_code_takes_the_one_vocabulary_class():
    with blank_session() as db:
        _seed_categories(db)
        assert product_class_signal.category_class(db, code="WC", name="WC", class_label=None) == CLASS


def test_ac_cp_4_no_class_or_several_classes_is_none():
    with blank_session() as db:
        made = _seed_categories(db)
        assert product_class_signal.category_class(db, code="ZZMISC", name="ZZ Misc", class_label=None) is None
        for c in (made["SRT-WC"], made["SRT-KS"]):
            c.search_synonyms = [*c.search_synonyms, "zzpot"]
        db.flush()
        assert product_class_signal.category_class(db, code="ZZPOT", name="ZZPOT", class_label=None) is None


def test_ac_cp_4_load_rows_sets_group_on_category_and_class_rows():
    with blank_session() as db:
        made = _seed_categories(db)
        rows = ll.load_rows(db, group_categories=True)
        by_key = {r.key: r for r in rows if r.list_name == "category"}
        assert by_key[made["SRT-WC"].id].group == CLASS
        assert by_key[made["WC"].id].group == CLASS  # class-less generic joins the vocabulary class
        assert by_key[made["SRT-KS"].id].group == "Kitchen Sink"
        assert by_key[made["ZZMISC"].id].group is None
        class_row = next(r for r in rows if r.key.startswith("type:") and r.label == CLASS)
        assert class_row.group == CLASS


def _grouped_rows():
    cls = _row(CLASS, CLASS, "type:water closet", CLASS, "wc")
    return [cls, *[_row(c, CLASS, c, c, "wc") for c in ("BRT-WC", "CB-WC")]]


def _items(line):
    return {x.strip() for x in line.split(":", 1)[1].split(",")}


def test_ac_cp_3_lookup_lines_group_when_the_config_has_category_pick(session_factory, monkeypatch):
    monkeypatch.setattr(ll, "EMBED", None)
    rows = _grouped_rows()
    monkeypatch.setattr(ll, "load_rows", lambda *a, **k: rows)
    db = session_factory()
    config = types.SimpleNamespace(category_pick=True)
    lines, event = engine_mod._lookup_lines(db, "wc", config, frozenset(), "ZZ-no-contact", None)
    assert not event.get("failed"), event
    grouped = [ln for ln in lines if ln.startswith("- Water Closet: ")]
    assert len(grouped) == 1 and _items(grouped[0]) == {"BRT-WC", "CB-WC"}, lines


def test_ac_cp_5_lookup_lines_without_category_pick_stay_one_line_per_row(session_factory, monkeypatch):
    monkeypatch.setattr(ll, "EMBED", None)
    rows = _grouped_rows()
    monkeypatch.setattr(ll, "load_rows", lambda *a, **k: rows)
    db = session_factory()
    for config in (None, types.SimpleNamespace(category_pick=False)):
        lines, _event = engine_mod._lookup_lines(db, "wc", config, frozenset(), "ZZ-no-contact", None)
        assert "- BRT-WC" in lines and "- CB-WC" in lines and not any(": " in ln and ln.startswith("- ") for ln in lines), lines


def _span_run(group_categories):
    prep_kwargs = dict(
        message="zz message", rows=_grouped_rows(), spec_key_rows=[], brand_words=frozenset(), numbers=[], held={},
        embed=None, config=span_extract.SpanConfig("sys", 2, "openai", "gpt-zz", "ZZ-key", "label"),
    )
    if group_categories is not None:
        prep_kwargs["group_categories"] = group_categories
    prep = engine_mod._SpanPrep(**prep_kwargs)
    answer = span_extract.SpanAnswer([list_resolver.Span("wc", "category")], {}, 1)
    from unittest import mock

    with mock.patch.object(span_extract, "extract", return_value=answer):
        return engine_mod._span_lookup(prep, session_factory=None, contact_respond_id="ZZ", dry_run=True, turn_id=None)[0]


def test_ac_cp_3_span_lookup_groups_when_the_prep_says_so():
    lines = _span_run(True)
    grouped = [ln for ln in lines if ln.startswith("- Water Closet: ")]
    assert len(grouped) == 1 and _items(grouped[0]) == {"BRT-WC", "CB-WC"}, lines


def test_ac_cp_5_span_lookup_default_is_one_line_per_row():
    lines = _span_run(None)
    assert "- BRT-WC" in lines and "- CB-WC" in lines, lines


def test_ac_cp_3_span_prep_takes_a_group_categories_keyword():
    import inspect

    assert "group_categories" in inspect.signature(engine_mod._span_prep).parameters
    assert engine_mod._SpanPrep.__dataclass_fields__["group_categories"].default is False


# ------------------------------------------------------------------------------------------------ C report
def _ids_for(db, **slot):
    return business_pkg._top_selling_category_ids(slot, db=db)


def test_ac_cp_6_a_class_label_takes_every_class_category_generic_included():
    with blank_session() as db:
        made = _seed_categories(db)
        ids, named, ambiguous, unknown = _ids_for(db, category_words=["Water Closet"])
        assert set(ids) == {made[c].id for c in (*WC_CODES, "WC")} and not ambiguous and not unknown, (ids, ambiguous)


def test_ac_cp_6_a_generic_code_word_also_takes_the_class():
    with blank_session() as db:
        made = _seed_categories(db)
        ids, named, ambiguous, unknown = _ids_for(db, category_words=["wc"])
        assert set(ids) == {made[c].id for c in (*WC_CODES, "WC")} and not ambiguous and not unknown, (ids, ambiguous)


def test_ac_cp_6_a_classed_code_stays_exact():
    with blank_session() as db:
        made = _seed_categories(db)
        ids, _named, ambiguous, unknown = _ids_for(db, category_code="SRT-WC")
        assert ids == [made["SRT-WC"].id] and not ambiguous and not unknown, ids
        ids, *_ = _ids_for(db, category_words=["SRT-WC"])
        assert ids == [made["SRT-WC"].id]


def test_ac_cp_6_a_word_matching_nothing_is_unknown():
    with blank_session() as db:
        _seed_categories(db)
        ids, _named, _amb, unknown = _ids_for(db, category_words=["zzqxnothing"])
        assert ids == [] and unknown == ["zzqxnothing"]


def test_ac_cp_6_the_class_does_not_leak_into_other_classes():
    with blank_session() as db:
        made = _seed_categories(db)
        ids, *_ = _ids_for(db, category_words=["Water Closet"])
        assert made["SRT-KS"].id not in ids and made["ZZMISC"].id not in ids


# ------------------------------------------------------------------------------------------------ D' language
def test_ac_cp_10_not_parsed_is_a_sentinel_and_keeps_todays_chain():
    assert language.NOT_PARSED is not None
    sv = {"reply_language": "zh"}
    assert language.for_turn("water clost?", sv, "ms", parsed=language.NOT_PARSED) == "zh"
    assert language.for_turn("ada stok", {}, "zh") == "ms"


def test_ac_cp_10_a_parsed_language_wins_even_over_cjk_and_the_conversation():
    sv = {"reply_language": "zh"}
    assert language.for_turn("water clost?", sv, "zh", parsed="en") == "en"
    assert sv["reply_language"] == "en"
    assert language.for_turn("马桶", {"reply_language": "en"}, "en", parsed="zh") == "zh"
    assert language.for_turn("ok", {}, None, parsed="ms") == "ms"


def test_ac_cp_10_parsed_none_falls_back_to_saved_then_conversation_then_en():
    assert language.for_turn("马桶", {"reply_language": "ms"}, "en", parsed=None) == "en"  # saved beats conversation
    assert language.for_turn("马桶", {"reply_language": "ms"}, None, parsed=None) == "ms"
    assert language.for_turn("马桶", {}, None, parsed=None) == "en"  # no detect on a parsed turn


def test_ac_cp_10_an_unknown_parsed_value_is_treated_as_none():
    assert language.for_turn("x", {"reply_language": "ms"}, None, parsed="fr") == "ms"


def test_ac_cp_10_turn_language_passes_the_parsed_value_through():
    user_turn = types.SimpleNamespace(own_text="water clost?")
    assert engine_mod._turn_language(user_turn, {"reply_language": "zh"}, None, parsed="en") == "en"
    assert engine_mod._turn_language(user_turn, {"reply_language": "zh"}, None, parsed=None) == "zh"
    assert engine_mod._turn_language(user_turn, {"reply_language": "zh"}, None) == "zh"


# ------------------------------------------------------------------------------------------------ D' base schema + turn
def test_ac_cp_9_a_non_closed_lists_template_with_the_language_sentence_sets_message_language(session_factory, monkeypatch):
    config = _config_for(session_factory, monkeypatch, "Rules {{current_date}}.\n" + parser_mod.LANGUAGE_ASK + "\n")
    assert config.message_language is True
    assert config.json_schema is None  # not a closed-lists prompt: the schema is the base one at parse time
    assert "message_language" in parser_mod._base_schema(config)["properties"]


def test_ac_cp_9_a_template_without_the_sentence_has_message_language_false(session_factory, monkeypatch):
    config = _config_for(session_factory, monkeypatch, "Rules {{current_date}}.\n")
    assert getattr(config, "message_language", "missing") is False
    assert "message_language" not in parser_mod._base_schema(config)["properties"]


def _bare_config(**kw):
    return parser_mod.ParserConfig(system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test",
                                   api_key="sk-test", **kw)


def test_ac_cp_9_base_schema_carries_message_language_iff_the_config_flag():
    on = parser_mod._base_schema(_bare_config(message_language=True))
    off = parser_mod._base_schema(_bare_config())
    assert "message_language" in on["properties"] and "message_language" in on["required"]
    assert "message_language" not in off["properties"] and "message_language" not in off["required"]


def _language_console(session_factory, monkeypatch, stub_access, phone, saved=None):
    from sqlalchemy import text

    from tests.chatbot._r9_engine_console import EngineConsole

    c = EngineConsole(session_factory, monkeypatch, stub_access, phone=phone)
    if saved:
        db = session_factory()
        db.execute(text("UPDATE respond_contacts SET chatbot_profile = CAST(:p AS jsonb)"),
                   {"p": '{"language": "%s"}' % saved})
        db.commit()
    monkeypatch.setattr(parser_mod, "resolve_config",
                        lambda db, *, current_date, override_version_id=None: _bare_config(message_language=True))
    return c


def test_ac_cp_10_turn_a_parsed_en_after_a_zh_conversation_replies_in_english(session_factory, monkeypatch, stub_access):
    from tests.chatbot._r9_engine_console import product, stock

    c = _language_console(session_factory, monkeypatch, stub_access, "+60000009401")
    c.say("SRTWC286-SH 有货吗", stock(product("SRTWC286-SH"), message_language="zh"))
    assert c.state["reply_language"] == "zh"
    c.say("SRTWC286-SH 2", stock(product("SRTWC286-SH", 2), message_language="en"))
    assert c.state["reply_language"] == "en"


def test_ac_cp_10_turn_a_parsed_null_keeps_the_saved_language_over_the_conversation(session_factory, monkeypatch, stub_access):
    from tests.chatbot._r9_engine_console import product, stock

    c = _language_console(session_factory, monkeypatch, stub_access, "+60000009402", saved="ms")
    c.say("SRTWC286-SH 有货吗", stock(product("SRTWC286-SH"), message_language="zh"))
    assert c.state["reply_language"] == "zh"
    c.say("SRTWC286-SH 2", stock(product("SRTWC286-SH", 2), message_language=None))
    assert c.state["reply_language"] == "ms"
