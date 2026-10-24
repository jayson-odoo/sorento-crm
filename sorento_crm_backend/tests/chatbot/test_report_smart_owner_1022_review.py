"""REPORT-SMART-L round S2, reviewer NOT READY on cc3ccfd1a5: five red tests.

1. the parser's State block never prints the held frame's internal `stale` flag;
2. AC-A1 code half: a stray entity equal to the channel value the same verdict set is not refused as a sales agent;
3. brand aliases reach every brand lookup (`exact_brand_rows` over `active_brands`);
4. D on the `crm_sales_report` path: a mixed code set asks which product, never names one;
5. the Known brands line keeps `Name (CODE)` for a brand whose code equals its name and has no alias.
Fake names and codes only.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    _e,
    _rank,
    console,
)
from tests.chatbot.test_report_smart_owner_1022_af import ALIAS, ZNAME, _seed_brand
from tests.chatbot.test_report_smart_step7 import THIS_YEAR, _state_on

SET_PRODUCT = [{"op": "set", "axis": "product", "position": None}]


# ---------------------------------------------------------------- 1: no `stale` in the State text

@pytest.mark.parametrize("shown", [
    {"group_by": "sales_agent", "rows": [{"name": "AGENT A", "keys": []}]},
    {"group_by": "customer", "rows": [{"name": "CUSTOMER A", "keys": []}]},
])
def test_1_the_rendered_state_never_prints_the_stale_flag(shown) -> None:
    from app.services.chatbot.turn import chat_state
    from app.services.chatbot.turn.state import Focus, State

    frame = {"group_by": shown["group_by"], "top_n": 3, "measure": "qty", "basis": "delivered", "sort": "desc",
             "date_from": "2026-01-01", "date_to": "2026-12-31", "shown": shown, "stale": True}
    focus = Focus(domains=["sales"], status="sales_ranking", sales_ranking_frame=frame)
    text = chat_state.render(chat_state.view(State(focus=focus, turn_no=4), None))
    assert text and shown["group_by"] in text, text
    assert "stale" not in text.casefold(), text


# ---------------------------------------------------------------- 2: the stray channel word is no sales agent

@pytest.mark.parametrize("channel,word,body", [
    ("project", "Project", "Project sales top 10 srt102-rg"),
    ("project", "project", "jualan project top 10 srt102-rg"),
    ("project", "PROJECT", "project 销售 前10 srt102-rg"),
    ("dealer", "Dealer", "Dealer sales top 10 srt102-rg"),
])
def test_2_a_stray_entity_equal_to_the_set_channel_runs_with_that_channel(console, channel, word, body) -> None:
    from tests._mc_lookup_seed import product

    ran = _state_on(console)
    db = console.session_factory()
    product(db, company_id=lane_company(), code="SRT102-RG")
    db.commit()
    db.close()
    text, calls = console.say(
        _rank(_e("SRT102-RG", "product"), _e(word, "sales_agent"), sales_channel=channel, top_n=10, measure="qty",
              basis="delivered", ranking_refine=False, state_changes=SET_PRODUCT, **THIS_YEAR),
        body,
    )
    assert ran, "harness: the State path never ran"
    assert "I don't know" not in text, text
    assert len(calls) == 1 and calls[0].get("channel") == channel, (text, calls)


def lane_company() -> str:
    from app.services.company_scope import DEFAULT_COMPANY_ID

    return DEFAULT_COMPANY_ID


@pytest.mark.parametrize("body", ["top 10 for ZZTNOBODY", "10 teratas ZZTNOBODY", "top 10 salesman ZZTNOBODY pls"])
def test_2_near_miss_an_unknown_sales_agent_word_with_no_channel_still_gets_the_line(console, body) -> None:
    ran = _state_on(console)
    text, calls = console.say(
        _rank(_e("ZZTNOBODY", "sales_agent"), top_n=10, measure="qty", basis="delivered", ranking_refine=False,
              state_changes=[{"op": "set", "axis": "customer", "position": None}], **THIS_YEAR),
        body,
    )
    assert ran, "harness: the State path never ran"
    assert calls == [] and "I don't know 'ZZTNOBODY' as a sales agent" in text, (text, calls)


# ---------------------------------------------------------------- 3: the alias reaches every brand lookup

@pytest.mark.parametrize("word", ["qzb", "QZB", " Qzb "])
def test_3_exact_brand_rows_matches_an_alias_from_the_brand_alias_set(session_factory, word) -> None:
    from app.models.product import Brand
    from app.services.chatbot import turn_runtime

    brand_id = _seed_brand(session_factory)
    db = session_factory()
    db.query(Brand.id).first()  # a fresh test session answers its first ORM read empty
    live = turn_runtime.active_brands(db)
    assert [r["id"] for r in turn_runtime.exact_brand_rows(live, word)] == [brand_id]
    entity = {"raw": word.strip(), "hint": "brand", "canonical_code": None, "current_message": True, "confident": True}
    assert [row["id"] for _e_, row in turn_runtime.brand_entity_rows([entity], live)] == [brand_id]


def test_3_near_miss_with_no_alias_set_the_word_names_no_brand_and_the_code_still_does(session_factory) -> None:
    from app.models.product import Brand
    from app.services.chatbot import turn_runtime

    brand_id = _seed_brand(session_factory, aliases=())
    db = session_factory()
    db.query(Brand.id).first()
    live = turn_runtime.active_brands(db)
    assert turn_runtime.exact_brand_rows(live, "qzb") == []
    assert [r["id"] for r in turn_runtime.exact_brand_rows(live, "zbrand")] == [brand_id]


# ---------------------------------------------------------------- 4: D on the crm_sales_report path

MIXED = [("XA1001", "11111111-1111-4111-8111-111111111111"), ("ZB2002", "22222222-2222-4222-8222-222222222222"),
         ("QC3003", "33333333-3333-4333-8333-333333333333")]


def _sales_report_turn(session_factory, monkeypatch, token: str, matches: list[tuple[str, str]], body: str, msg_id: str):
    from tests.chatbot.test_outstanding_lane import _run_turn, _seed_contact
    from tests.chatbot.test_sales_report_lane import SALES_REPORT_HIT, _family_resolve_services

    _seed_contact(session_factory, variables={})
    services = _family_resolve_services(
        token=token, matches=[{"entity_type": "product", "canonical_code": c, "uuid": u} for c, u in matches])
    return _run_turn(
        session_factory, monkeypatch,
        qf=_parser_output(domain_hint="order", intent_hint="check_order", order_status="sales_report", entities=[
            {"raw": token, "hint": "product", "canonical_code": None, "current_message": True, "confident": True}]),
        text_body=body, msg_id=msg_id, attributes=["sales_orders.sales_report"], resolve_services=services,
        mcp_response=SALES_REPORT_HIT,
    )


@pytest.mark.parametrize("body", ["sales report for zq6635", "销售报告 zq6635", "laporan jualan zq6635", "zq6635 sales lah"])
def test_4_a_mixed_code_set_on_the_sales_report_path_asks_which_product(session_factory, monkeypatch, body) -> None:
    result, captured = _sales_report_turn(session_factory, monkeypatch, "ZQ6635", MIXED, body, f"zzt-rev4-{abs(hash(body))}")
    reply = (result.reply or {}).get("text") or ""
    sent = [a for name, a in captured if name == "crm_sales_report"]
    assert not sent, ("ran on one unrelated code", [a.get("product_code") for a in sent])
    assert "?" in reply or "1." in reply, reply
    assert sum(code in reply for code, _u in MIXED) != 1, reply


def test_4_near_miss_a_shared_prefix_family_still_sends_the_prefix(session_factory, monkeypatch) -> None:
    family = [("ZYQ7001-A", "44444444-4444-4444-8444-444444444441"), ("ZYQ7001-B", "44444444-4444-4444-8444-444444444442")]
    _result, captured = _sales_report_turn(session_factory, monkeypatch, "ZYQ7001", family, "sales report for ZYQ7001", "zzt-rev4-fam")
    sent = [a for name, a in captured if name == "crm_sales_report"]
    assert sent and str(sent[0].get("product_code") or "").startswith("ZYQ7001"), captured


# ---------------------------------------------------------------- 5: Known brands, code equals name

def test_5_a_brand_whose_code_equals_its_name_with_no_alias_keeps_name_and_code() -> None:
    from app.services.chatbot.turn.context import known_brands_line

    rows = [{"brand_name": "SORENTOX", "brand_code": "SORENTOX", "aliases": []},
            {"brand_name": "Sorentox", "brand_code": "SORENTOX"}]
    assert known_brands_line(rows[:1]) == "Known brands: SORENTOX (SORENTOX)"
    assert known_brands_line(rows[1:]) == "Known brands: Sorentox (SORENTOX)"
    assert known_brands_line([{"brand_name": "sorentox", "brand_code": "SORENTOX", "aliases": []}]) == "Known brands: sorentox (SORENTOX)"


def test_5_near_miss_with_an_alias_the_equal_code_is_dropped() -> None:
    from app.services.chatbot.turn.context import known_brands_line

    assert known_brands_line([{"brand_name": "SORENTOX", "brand_code": "SORENTOX", "aliases": ["SRX"]}]) == "Known brands: SORENTOX (SRX)"
    assert known_brands_line([{"brand_name": "Zbrand Fake", "brand_code": "ZBRAND", "aliases": ["QZB"]}]) == "Known brands: Zbrand Fake (ZBRAND, QZB)"
