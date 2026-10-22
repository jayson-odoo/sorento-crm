"""REPORT-SMART-L round S2, A' / F' (plan section "A' / F'"): values from the closed-list index.

A'. A "Sales channels" line (the code's channel source) is ALWAYS on, in Block and Index mode
alike (owner ruling: no index matching); a channel value / any entity whose hint is not an entity
kind never reaches the resolver or a kind pick.
F'. Brand aliases as data: lookup set `brand_alias` (option value = brand_code, keywords = short
forms). The Known brands line prints the short forms in the parentheses, `Name (ALIAS, ...)`, in
both modes; `resolve_brand_token` takes an alias as an exact match. F code half: a brand + promotion kind
flyer ask sends the kind and the brand to the promotions tool even when the State holds products.

Fake names and codes only (brand ZBRAND, alias QZB: the alias is NOT a substring of the code or
name, so a line showing it proves the alias reader ran).
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.models.lookup import LookupOption, LookupOptionKeyword, LookupSet
from app.models.product import Brand
from app.services import ai_prompt_registry
from app.services import chatbot_prompt_vars as pv
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_index_mode import _lines, _quiet, _seed_world, _set_mode, _turns
from tests.chatbot.test_engine import _parser_output, seeded, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import _e, _rank, _refine, console  # noqa: F401
from tests.chatbot.test_report_smart_step7 import KEEP, THIS_YEAR, _state_on

ALIAS = "QZB"
BRAND_CODE = "ZBRAND"


@pytest.fixture(autouse=True)
def _fresh_caches():
    ai_prompt_registry.bust_cache()
    pv.clear_cache()
    yield
    ai_prompt_registry.bust_cache()
    pv.clear_cache()


# ---------------------------------------------------------------- A' always-on line, both modes

@pytest.mark.parametrize("body", ["zzqwerty", "top 5 salesppl this year", "前5 销售员", "5 jurujual teratas"])
@pytest.mark.parametrize("mode", ["block", "index"])
def test_a1_the_user_turn_carries_the_full_sales_channels_line_in_both_modes(session_factory, seeded, stub_access, monkeypatch, mode, body):
    from app.services.chatbot.head.parser import PARSE_OUTPUT_JSON_SCHEMA

    _seed_world(session_factory)
    _set_mode(session_factory, mode)
    [(_system, block, _r)] = _turns(session_factory, stub_access, monkeypatch, [(body, _quiet())])
    lines = _lines(block, "Sales channels")
    assert len(lines) == 1, block
    joined = lines[0].casefold()
    channels = [v for v in PARSE_OUTPUT_JSON_SCHEMA["properties"]["sales_channel"]["enum"] if v]
    assert channels, "harness: the schema lists no sales channel"
    for value in channels:
        assert value.casefold() in joined, (value, lines)
    assert "retail" not in joined, lines  # the SCM demand class is not a sales channel


# ---------------------------------------------------------------- A' (3) the guard

def _seed_project_rows(console) -> None:
    from tests._mc_lookup_seed import customer, warehouse

    db = console.session_factory()
    customer(db, company_id=DEFAULT_COMPANY_ID, name="PROJECT ALPHA SDN BHD")
    customer(db, company_id=DEFAULT_COMPANY_ID, name="PROJECT BETA SDN BHD")
    w = warehouse(db, company_id=DEFAULT_COMPANY_ID, code="PROJECT")
    w.warehouse_name = "Project"
    db.commit()
    db.close()


@pytest.mark.parametrize("body", ["Project is channel", "channel is Project", "Project is the channel lah", "Project 是渠道 channel"])
def test_a3_an_entity_whose_hint_is_not_an_entity_kind_never_arms_a_kind_pick(console, body) -> None:
    ran = _state_on(console)
    _seed_project_rows(console)
    text_, calls = console.say(
        _rank(top_n=3, measure="qty", basis="delivered", state_changes=list(KEEP), **THIS_YEAR), "top 3 salesppl this year")
    assert len(calls) == 1, ("setup: the ranking did not run", text_)
    text_, calls = console.say(
        _refine(entities=[_e("Project", "sales_channel")], state_changes=[{"op": "set", "axis": "channel", "position": None}]),
        body,
    )
    assert ran, "harness: the State path never ran"
    assert "Which one" not in text_ and "(customer)" not in text_ and "(warehouse)" not in text_, text_
    assert "kind_pick" not in json.dumps(console.session_vars, default=str), console.session_vars


def test_a3_near_miss_a_real_sales_agent_word_with_its_hint_still_resolves(console) -> None:
    ran = _state_on(console)
    text_, calls = console.say(
        _rank(_e("AGENT A", "sales_agent"), group_by="product", state_changes=list(KEEP)), "top 3 products of agent A")
    assert ran, "harness: the State path never ran"
    (args,) = calls
    assert args["sales_agent_ids"] == [console.ids["agent"]], args


# ---------------------------------------------------------------- F' brand alias as data

PLAIN_NAME, PLAIN_CODE = "Plainco Fake", "PLNCO"
ZNAME = "Zbrand Fake"
SAME_NAME, SAME_ALIAS = "SORENTOX", "SRX"  # a brand whose code equals its name


def _seed_brand(session_factory, *, aliases: tuple[str, ...] = (ALIAS,)) -> str:
    db = session_factory()
    brand = Brand(id=str(uuid.uuid4()), brand_code=BRAND_CODE, brand_name=ZNAME, company_id=DEFAULT_COMPANY_ID)
    db.add_all([brand, Brand(id=str(uuid.uuid4()), brand_code=PLAIN_CODE, brand_name=PLAIN_NAME, company_id=DEFAULT_COMPANY_ID),
                Brand(id=str(uuid.uuid4()), brand_code=SAME_NAME, brand_name=SAME_NAME, company_id=DEFAULT_COMPANY_ID)])
    if aliases:
        s = LookupSet(id=str(uuid.uuid4()), set_key="brand_alias", name="Brand Alias", is_active=True)
        db.add(s)
        db.flush()
        o = LookupOption(id=str(uuid.uuid4()), set_id=s.id, value=BRAND_CODE, label=BRAND_CODE, sort_order=0, is_active=True)
        db.add(o)
        db.flush()
        for word in aliases:
            db.add(LookupOptionKeyword(id=str(uuid.uuid4()), option_id=o.id, keyword=word))
        o2 = LookupOption(id=str(uuid.uuid4()), set_id=s.id, value=SAME_NAME, label=SAME_NAME, sort_order=1, is_active=True)
        db.add(o2)
        db.flush()
        db.add(LookupOptionKeyword(id=str(uuid.uuid4()), option_id=o2.id, keyword=SAME_ALIAS))
    db.commit()
    return str(brand.id)


def _known_line(block: str) -> str:
    lines = _lines(block, "Known brands:")
    assert lines, block
    return lines[0]


@pytest.mark.parametrize("mode", ["block", "index"])
def test_f1_the_known_brands_line_prints_the_short_form_in_the_parentheses(session_factory, seeded, stub_access, monkeypatch, mode):
    _seed_world(session_factory)
    _seed_brand(session_factory)
    _set_mode(session_factory, mode)
    [(_system, block, _r)] = _turns(session_factory, stub_access, monkeypatch, [("zzqwerty", _quiet())])
    line = _known_line(block)
    assert f"{ZNAME} ({BRAND_CODE}, {ALIAS})" in line, line  # code and alias, comma separated
    assert f"{SAME_NAME} ({SAME_ALIAS})" in line, line  # an entry equal to the name is dropped
    assert f"{PLAIN_NAME} ({PLAIN_CODE})" in line, line  # a brand with no alias prints as today


@pytest.mark.parametrize("mode", ["block", "index"])
def test_f1_with_several_aliases_all_of_them_print(session_factory, seeded, stub_access, monkeypatch, mode):
    _seed_world(session_factory)
    _seed_brand(session_factory, aliases=(ALIAS, "QZC"))
    _set_mode(session_factory, mode)
    [(_system, block, _r)] = _turns(session_factory, stub_access, monkeypatch, [("zzqwerty", _quiet())])
    line = _known_line(block)
    assert ALIAS in line and "QZC" in line, line
    assert f"{ZNAME} ({BRAND_CODE}, {ALIAS}, QZC)" in line, line


@pytest.mark.parametrize("word", ["qzb", "QZB", " Qzb "])
@pytest.mark.parametrize("exact_only", [False, True])
def test_f2_resolve_brand_token_takes_the_alias_as_an_exact_match(session_factory, word, exact_only) -> None:
    from app.services.chatbot.lanes.business import services as business_services

    brand_id = _seed_brand(session_factory)
    db = session_factory()
    db.query(Brand.id).first()  # a fresh test session answers its first ORM read empty
    assert business_services.resolve_brand_token(db, word, exact_only=exact_only) == [(brand_id, ZNAME)]


def test_f2_the_brand_code_and_name_still_resolve(session_factory) -> None:
    from app.services.chatbot.lanes.business import services as business_services

    brand_id = _seed_brand(session_factory)
    db = session_factory()
    db.query(Brand.id).first()
    assert business_services.resolve_brand_token(db, BRAND_CODE, exact_only=True) == [(brand_id, ZNAME)]
    assert business_services.resolve_brand_token(db, ZNAME, exact_only=True) == [(brand_id, ZNAME)]


def test_f2_near_miss_with_no_brand_alias_set_the_line_and_the_resolver_are_as_today(session_factory, seeded, stub_access, monkeypatch) -> None:
    from app.services.chatbot.lanes.business import services as business_services

    _seed_world(session_factory)
    brand_id = _seed_brand(session_factory, aliases=())
    [(_system, block, _r)] = _turns(session_factory, stub_access, monkeypatch, [("zzqwerty", _quiet())])
    line = _known_line(block)
    assert f"{ZNAME} ({BRAND_CODE})" in line and ALIAS not in line.upper(), line
    db = session_factory()
    db.query(Brand.id).first()
    assert business_services.resolve_brand_token(db, "qzb") == []
    assert business_services.resolve_brand_token(db, BRAND_CODE) == [(brand_id, ZNAME)]


# ---------------------------------------------------------------- F code half: kind + brand, products held

HELD_CODES = ("ZZTMHELD1", "ZZTMHELD2")
FLYER_BODIES = ["Sorento a3 flyer", "Sorento A3 传单", "flyer a3 Sorento ada?", "sorento a3 flyer boleh"]


def _held_world(session_factory, monkeypatch):
    """The promotions world (`test_promo_brand_flyer_ask._world`) with the two held products moved
    to the Sorento brand and held in the State under the promotion domain (the live turn 13)."""
    from app.models.product import Product
    from app.services.chatbot.head import parser as parser_mod
    from tests.chatbot.test_outstanding_lane import CONTACT_ID, _session_of
    from tests.chatbot.test_promo_brand_category import _mcp
    from tests.chatbot.test_promo_brand_flyer_ask import _brand_flyer_qf, _turn, _world

    ids = _world(session_factory)
    db = session_factory()
    db.query(Product.id).first()  # a fresh test session answers its first ORM read empty
    rows = db.query(Product).filter(Product.product_code.in_(HELD_CODES)).all()
    assert len(rows) == 2, rows
    for row in rows:
        row.brand_id = ids["srt"]
    db.commit()
    held = [{"raw": p.product_code, "hint": "product", "canonical_code": p.product_code, "uuid": str(p.id),
             "current_message": False, "confident": True} for p in rows]
    captured = _mcp(monkeypatch, session_factory)
    from app.services.ai_assistant_service import MCPRuntimeClient

    # Any tool the flyer path calls beside the promotions list is answered empty, never the real server.
    monkeypatch.setattr(MCPRuntimeClient, "call_tool",
                        lambda self, name, args: captured.append((name, dict(args))) or json.dumps({"ok": True, "items": []}))
    real = parser_mod.ParserConfig
    monkeypatch.setattr(parser_mod, "ParserConfig", lambda **kw: real(**{**kw, "closed_lists": True, "state_block": True}))
    _turn(session_factory, monkeypatch, _brand_flyer_qf(state_changes=list(KEEP)), "hello", "zzt-af-seed")
    sv = _session_of(session_factory)
    sv["focus"]["products"], sv["focus"]["domains"] = held, ["promotion"]
    other = session_factory()
    other.execute(text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE respond_io_id = :cid"),
                  {"sv": json.dumps(sv), "cid": str(CONTACT_ID)})
    other.commit()
    return ids, captured


@pytest.mark.parametrize("body", FLYER_BODIES)
def test_f5_a_brand_kind_flyer_ask_sends_the_kind_and_brand_not_the_held_products(session_factory, monkeypatch, body) -> None:
    from tests.chatbot.test_promo_kind_subject import PROMO_TOOL
    from tests.chatbot.test_promo_brand_flyer_ask import _assert_brand_kind_calls, _brand_flyer_qf, _turn

    ids, captured = _held_world(session_factory, monkeypatch)
    n = len(captured)
    _turn(session_factory, monkeypatch, _brand_flyer_qf(state_changes=list(KEEP)), body, f"zzt-af-{abs(hash(body))}")
    _assert_brand_kind_calls([a for name, a in captured[n:] if name == PROMO_TOOL], ids)


def test_f5_near_miss_a_flyer_ask_typing_a_product_code_this_message_looks_up_that_product(session_factory, monkeypatch) -> None:
    from tests.chatbot.test_promo_kind_subject import PROMO_TOOL
    from tests.chatbot.test_promo_brand_flyer_ask import _brand_flyer_qf, _turn

    _ids, captured = _held_world(session_factory, monkeypatch)
    n = len(captured)
    qf = _brand_flyer_qf(state_changes=list(KEEP))
    qf["entities"] = [*qf["entities"], {"raw": HELD_CODES[0], "hint": "product", "canonical_code": HELD_CODES[0],
                                         "current_message": True, "confident": True}]
    _turn(session_factory, monkeypatch, qf, f"Sorento a3 flyer {HELD_CODES[0]}", "zzt-af-typed")
    calls = [a for name, a in captured[n:] if name == PROMO_TOOL]
    assert calls and all(a.get("product_ids") for a in calls), calls
