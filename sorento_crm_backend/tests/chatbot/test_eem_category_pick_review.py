"""EEM-CATEGORY-PICK #1917 review round: no two-class widening, non-searchable kept, grouping gated by the prompt,
fallback-lane language, call-site coverage of the parsed language, case-insensitive grouping. Stubs only."""
from __future__ import annotations

import dataclasses
import uuid
from unittest import mock

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.base import set_company_scope
from app.models.product import ProductCategory
from app.services import product_class_signal
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.lanes import business as business_pkg
from app.services.chatbot.lanes.business import services as business_services
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import blank_session
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import stub_access  # noqa: F401
from tests.chatbot.test_lookup_lists_engine import _fresh_caches  # noqa: F401

CLASS = "Water Closet"


def _cat(code, *, label=None, syn=(), searchable=True, name=None):
    return ProductCategory(id=str(uuid.uuid4()), category_code=code, category_name=name or code, class_label=label,
                           search_synonyms=list(syn), is_searchable=searchable, company_id=DEFAULT_COMPANY_ID)


def _world(db, extra=()):
    set_company_scope(db, None)
    rows = [_cat(c, label=CLASS, syn=["wc"]) for c in ("BRT-WC", "SRT-WC")]
    rows.append(_cat("SRT-KS", label="Kitchen Sink", syn=["sink"]))
    rows.extend(extra)
    db.add_all(rows)
    db.flush()
    return {r.category_code: r for r in rows}


# ---- 1 BLOCKER: a class-less hit the vocabulary maps to two classes stays exact
def test_review_1_a_classless_code_with_two_classes_stays_its_own_id():
    with blank_session() as db:
        made = _world(db, [_cat("ZZPOT")])
        for cls in ("Water Closet", "Kitchen Sink"):  # the word "zzpot" names both classes
            row = db.query(ProductCategory).filter_by(class_label=cls).first()
            row.search_synonyms = [*row.search_synonyms, "zzpot"]
        db.flush()
        ids, _named, ambiguous, unknown = business_pkg._top_selling_category_ids({"category_words": ["ZZPOT"]}, db=db)
        assert ids == [made["ZZPOT"].id] and not ambiguous and not unknown, (ids, ambiguous, unknown)


# ---- 2: a classed, non-searchable category of the class is still in the class
def test_review_2_a_non_searchable_classed_category_is_in_the_class_ids():
    with blank_session() as db:
        made = _world(db, [_cat("ZZ-WCOLD", label=CLASS, searchable=False)])
        ids = business_services.class_member_ids(db, [CLASS])
        assert made["ZZ-WCOLD"].id in ids and made["BRT-WC"].id in ids, ids


def test_review_2_the_class_report_includes_it_too():
    with blank_session() as db:
        made = _world(db, [_cat("ZZ-WCOLD", label=CLASS, searchable=False)])
        ids, *_ = business_pkg._top_selling_category_ids({"category_words": ["Water Closet"]}, db=db)
        assert made["ZZ-WCOLD"].id in ids, ids


# ---- 3: load_rows reads the vocabulary only when asked to group
def test_review_3_load_rows_without_grouping_never_reads_the_vocabulary(monkeypatch):
    with blank_session() as db:
        _world(db, [_cat("WC")])
        boom = mock.Mock(side_effect=AssertionError("vocabulary read without group_categories"))
        monkeypatch.setattr(product_class_signal, "ClassVocabulary", boom)
        monkeypatch.setattr(product_class_signal, "resolve_classes_for_term", boom)
        monkeypatch.setattr(product_class_signal, "category_class", boom)
        rows = ll.load_rows(db, group_categories=False)
        assert rows and all(r.group is None for r in rows if r.list_name == "category"), "grouped without being asked"
        boom.assert_not_called()


def test_review_3_load_rows_with_grouping_sets_the_group():
    with blank_session() as db:
        made = _world(db, [_cat("WC")])
        rows = {r.key: r for r in ll.load_rows(db, group_categories=True)}
        assert rows[made["WC"].id].group == CLASS and rows[made["BRT-WC"].id].group == CLASS


def test_review_3_a_vocabulary_failure_without_grouping_keeps_the_block(monkeypatch):
    with blank_session() as db:
        made = _world(db, [_cat("WC")])
        monkeypatch.setattr(product_class_signal, "ClassVocabulary", mock.Mock(side_effect=RuntimeError("zz")))
        keys = {r.key for r in ll.load_rows(db, group_categories=False)}
        assert made["BRT-WC"].id in keys


def test_review_3_the_engine_passes_group_categories_only_with_category_pick(session_factory, monkeypatch):
    monkeypatch.setattr(ll, "EMBED", None)
    seen = []

    def load_rows(*a, **k):
        seen.append(k.get("group_categories"))
        return []

    monkeypatch.setattr(ll, "load_rows", load_rows)
    db = session_factory()
    import types

    for on in (True, False, None):
        cfg = None if on is None else types.SimpleNamespace(category_pick=on)
        engine_mod._lookup_lines(db, "wc", cfg, frozenset(), "ZZ-no-contact", None)
    assert seen == [True, False, False], seen


# ---- 6 nits
def _h(label, group):
    return ll.Hit(ll.LookupRow("category", label, label, (label,), group), label, 1.0, 0.0)


def test_review_6_grouping_is_case_insensitive_and_prints_the_class_spelling():
    lines = ll.render({"category": [_h("Water closet", "Water closet"), _h("Water Closet", "Water Closet"),
                                    _h("BRT-WC", "Water Closet")]}, group_categories=True)
    assert lines == [ll.header("category"), "- Water Closet: BRT-WC"], lines


def test_review_6_a_blank_class_label_counts_as_class_less():
    with blank_session() as db:
        made = _world(db, [_cat("ZZ-BLANK", label="  ")])
        assert business_services.unclassed_ids(db, [made["ZZ-BLANK"].id]) is True


# ---- 4 fallback-lane language, 5 call-site coverage
def _msg_lang_config(on=True):
    return lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
        system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
        message_language=on)


from tests.chatbot.test_memory_s4_fallback_replay import lane  # noqa: E402,F401


@pytest.mark.parametrize("flag,expected", [(True, "ms"), (False, "en")])
def test_review_4_the_fallback_lane_uses_the_parsed_language(session_factory, stub_access, lane, monkeypatch, flag, expected):
    from tests.chatbot._turn_helpers import verdict as verdict_defaults
    from tests.chatbot.test_engine import CONTACT_ID, _envelope
    from tests.chatbot.test_memory_s4_fallback_replay import _seed_contact

    _seed_contact(session_factory, {}, level="full")
    stub_access()
    out = verdict_defaults(message_type="casual", message_language="ms")
    monkeypatch.setattr(parser_mod, "resolve_config", _msg_lang_config(flag))
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: out)
    env = _envelope(is_test=True, ingress="console")
    env.message["message"]["messageId"] = f"ZZT-rv-{uuid.uuid4().hex[:8]}"
    env.message["message"]["message"]["text"] = "please check this for me"  # detect() reads English
    result = engine_mod.run_turn(env, session_factory=session_factory)
    assert result.error is None, result.error
    assert result.session_patch["reply_language"] == expected, result.session_patch


def test_review_5_a_non_business_turn_after_zh_replies_in_the_parsed_language(session_factory, monkeypatch, stub_access):
    from tests.chatbot._r9_engine_console import EngineConsole, product, stock
    from tests.chatbot._turn_helpers import verdict

    c = EngineConsole(session_factory, monkeypatch, stub_access, phone="+60000009411")
    monkeypatch.setattr(parser_mod, "resolve_config", _msg_lang_config())
    c.say("SRTWC286-SH 有货吗", stock(product("SRTWC286-SH"), message_language="zh"))
    assert c.state["reply_language"] == "zh"
    c.say("thanks", verdict(message_type="casual", message_language="en"))
    assert c.state["reply_language"] == "en"


def test_review_5_a_reset_turn_acks_in_the_parsed_language(turn_factory):
    t, words, emission = turn_factory
    result = t.say({**_stored_zh(), }, {**emission, "message_language": "en"}, words)
    from tests.chatbot.test_reset_turn_seam import ACK

    assert (result.reply or {}).get("text") == ACK["en"], (result.reply or {}).get("text")


def _stored_zh():
    from tests.chatbot.test_reset_turn_seam import _stored

    return {**_stored("nothing_open"), "reply_language": "zh"}


@pytest.fixture()
def turn_factory(session_factory, monkeypatch, stub_access, _stub_casual_llm):
    from tests.chatbot.test_reset_turn_seam import OLD, Turn, _clear_all

    class Flagged(Turn):
        def say(self, session_vars, emission, words="clear all"):
            real = monkeypatch.setattr

            def patched(obj, name, value=None, *a, **k):
                if name == "resolve_config" and callable(value):
                    inner = value
                    value = lambda *x, **kw: dataclasses.replace(inner(*x, **kw), message_language=True)  # noqa: E731
                return real(obj, name, value, *a, **k)

            self.monkeypatch = type("P", (), {"setattr": staticmethod(patched)})()
            return super().say(session_vars, emission, words)

    t = Flagged(session_factory, monkeypatch, stub_access, _stub_casual_llm, gate=False)
    return t, "clear all", _clear_all("nothing_open", OLD[0])


def test_review_5_an_opportunity_turn_after_zh_replies_in_the_parsed_language(session_factory, monkeypatch):
    from tests.chatbot import test_opportunity_lane as opp

    opp._salesperson(session_factory)
    opp._install(monkeypatch, options={"Bath Idea": opp._options(opp.BATH)})
    real = opp._stub_config
    monkeypatch.setattr(opp, "_stub_config", lambda *a, **k: dataclasses.replace(real(*a, **k), message_language=True))
    zh = {"focus": None, "open_question": None, "reply_language": "zh"}
    q = {**opp._all_four(), "message_language": "ms"}
    turn = opp._say(session_factory, monkeypatch, q, "log an opportunity: Bath Idea, condo job Taman X, RM 40k, closing mid Dec",
                    dry_run=True, state=zh)
    assert turn.result.error is None, turn.result.error
    assert turn.result.session_patch["reply_language"] == "ms", turn.result.session_patch
