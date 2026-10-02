"""Phase 2 RED tests - REPORT-ENGINE slice 1b: the `sales_ranking` lane and its engine seam.

`documentation/plans/chatbot/PLAN-report-engine.md` section 11 (binding) and the UAC
refinements AC-RE-18a to 18d.

Full console turns, the way `test_low_stock_filter_ask.py` drives them: the REAL engine, lane and
MCP presenter; only the parser and the MCP transport are doubles. `Console.say` returns the reply
text and every `crm_report_ask` call that turn made, so "nothing runs before the period and the
number are settled" is pinned as "no `crm_report_ask` call on that turn".

Ambiguities the tester did NOT resolve by guessing (flagged to the captain):
* the exact reply after a MISS on `top_n` / `period` (the helper's own `I don't know '<word>' as a
  <noun>.` line has a noun section 11 does not name): only "no call and the question is asked
  again" is pinned for a first miss, and the exact give-up line for the second;
* a route refusal arrives from the MCP as the http error envelope (`status_code` 403, the route's
  own `message` / `code`); the reply must be that `message`.
"""
from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_engine import CONTACT_ID, _parser_output
from tests.chatbot.test_outstanding_lane import (
    AnswerServices,
    FetchServices,
    _present_response,
    _seed_contact,
)
from tests.chatbot.test_top_selling_round6 import _seed_borrowable_envelope

TOOL = "crm_report_ask"
GRANT = "sales_orders.sales_report"
DENIAL = "Sales report is not enabled for your account."
PERIOD_Q = "Which period? For example this month, September, 2026, or 1 to 15 Sep."
TOPN_Q = "How many? For example top 5."
CANCELLED = "Sales ranking cancelled."
CATALOGUE_LINE = (
    "I can rank sales by customer, product, brand, category, sales agent, location, channel or month."
)
GIVE_UP = (
    "I still can't read '{word}'. Ask again with the period and how many, "
    "e.g. top 5 sales agents for Sorento this month."
)
DIMENSION_REFUSAL = "That breakdown is not available for your account."
_SNAKE = re.compile(r"\b[a-z]+_[a-z0-9_]+\b")
SEP = {"date_filter_start": "2026-09-01", "date_filter_end": "2026-09-30"}
PRODUCT_CODE = "SRTWT7408"
CUSTOMER_NAME = "ZZT RANK CUSTOMER SDN BHD"


def _e(raw: str, hint: str) -> dict[str, Any]:
    return {"raw": raw, "hint": hint, "canonical_code": None, "current_message": True, "confident": True}


def _rank(*entities: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """The parser's reading of "top 3 salesman for Sorento brand last month" (section 11)."""
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking",
        entities=list(entities), group_by="sales_agent", top_n=3,
        rank_direction="top", rank_by=None, basis=None, **SEP,
    )
    base.update(overrides)
    return _parser_output(**base)


def _reply(**overrides: Any) -> dict[str, Any]:
    """The parser's reading of a short reply: whatever it makes of the bare words."""
    base: dict[str, Any] = dict(
        message_type="business_query", domain_hint="master_products", intent_hint="check_product", entities=[],
    )
    base.update(overrides)
    return _parser_output(**base)


def _fake_body(args: dict[str, Any]) -> dict[str, Any]:
    """The route's own body (`ReportAskResponse`) for the lane's args."""
    group_by = args.get("group_by")
    rows = [{"rank": 1, "name": "FANNY", "qty": 30, "amount": 1200.0}] if group_by else []
    return {
        "status": "ok", "message": None,
        "basis": args.get("basis", "delivered"),
        "basis_label": "ordered sales" if args.get("basis") == "ordered" else "delivered sales",
        "measure": args.get("measure", "amount"), "sort": args.get("sort", "desc"),
        "group_by": group_by, "group_label": (group_by or "").replace("_", " ").title() or None,
        "date_from": args.get("date_from"), "date_to": args.get("date_to"),
        "filters": [], "rows": rows, "more": 0, "total_count": len(rows),
        "total": {"qty": 30, "amount": 1200.0},
    }


class Console:
    def __init__(self, session_factory, monkeypatch) -> None:
        self.session_factory, self.monkeypatch = session_factory, monkeypatch
        self.session_vars: dict[str, Any] = {}
        self.refuse: dict[str, Any] | None = None

    def say(self, qf: dict[str, Any], body: str) -> tuple[str, list[dict[str, Any]]]:
        from app.services.chatbot import console_service
        from app.services.chatbot.head import parser as parser_mod

        self.monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: qf)
        captured: list[tuple[str, dict[str, Any]]] = []
        present = _present_response()

        def _mcp(name: str, args: dict[str, Any]) -> Any:
            captured.append((name, dict(args)))
            if name != TOOL:
                return json.dumps({"has_result": False, "items": []})
            if self.refuse is not None:
                from sorento_crm_mcp.http_client import http_error_body

                raw = http_error_body(
                    json.dumps(self.refuse), status_code=403,
                    path="/api/v1/order-management/report-ask", method="GET",
                )
                return present(name, raw)
            return present(name, json.dumps(_fake_body(args)))

        self.monkeypatch.setattr(engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=_mcp))
        self.monkeypatch.setattr(
            engine_mod.business_services,
            "answer_services_for",
            lambda session_factory: AnswerServices(
                mcp_probe=lambda name, args: {"data": []}, family_fetch=lambda query: {"data": []}
            ),
        )
        db = self.session_factory()
        try:
            result = console_service.run_console_turn(
                db, contact_respond_id=str(CONTACT_ID), text=body,
                session_vars=copy.deepcopy(self.session_vars), run_id="zzt-report-ask-lane",
            )
        finally:
            db.close()
        self.session_vars = result.session_vars or {}
        text = result.reply_text or ""
        assert not _SNAKE.search(text), (body, text)
        assert chr(0x2014) not in text and chr(0x2013) not in text, body
        return text, [args for name, args in captured if name == TOOL]


def _seed(session_factory) -> dict[str, str]:
    from app.models.product import Brand, ProductCategory
    from app.models.sales_agent import SalesAgent
    from tests._mc_lookup_seed import customer, product, warehouse

    db = session_factory()
    try:
        ids: dict[str, str] = {}
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZTSOR", brand_name="Sorento", company_id=DEFAULT_COMPANY_ID)
        agent = SalesAgent(id=str(uuid.uuid4()), sales_agent="FANNY", company_id=DEFAULT_COMPANY_ID)
        category = ProductCategory(
            id=str(uuid.uuid4()), category_code="ZZTCAT", category_name="ZZT CATEGORY", company_id=DEFAULT_COMPANY_ID
        )
        db.add_all([brand, agent, category])
        db.flush()
        ids.update(brand=brand.id, agent=agent.id, category=category.id)
        ids["product"] = product(db, company_id=DEFAULT_COMPANY_ID, code=PRODUCT_CODE).id
        ids["customer"] = customer(db, company_id=DEFAULT_COMPANY_ID, name=CUSTOMER_NAME).id
        warehouse(db, company_id=DEFAULT_COMPANY_ID, code="BRW")
        db.commit()
        return {k: str(v) for k, v in ids.items()}
    finally:
        db.close()


def _console(session_factory, monkeypatch, *, grants: list[str]) -> Console:
    from app.services.chatbot import console_service
    from app.services.chatbot.head import parser as parser_mod

    _seed_contact(session_factory, variables={})
    _seed_borrowable_envelope(session_factory)
    console = Console(session_factory, monkeypatch)
    console.ids = _seed(session_factory)
    monkeypatch.setattr(console_service, "SessionLocal", session_factory)
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True, "decision": "allow", "agent_name": "General",
            "attributes": grants, "all_attributes_allowed": None,
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")
    monkeypatch.setattr(
        parser_mod,
        "resolve_config",
        lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=39, provider="openai", model="gpt-test", api_key="sk-test",
        ),
    )
    return console


@pytest.fixture
def console(session_factory, monkeypatch):
    return _console(session_factory, monkeypatch, grants=[GRANT])


@pytest.fixture
def console_no_grant(session_factory, monkeypatch):
    return _console(session_factory, monkeypatch, grants=[])


# --------------------------------------------------------------------------- #
# Grant
# --------------------------------------------------------------------------- #


def test_no_grant_says_the_sales_report_is_not_enabled_and_calls_nothing(console_no_grant) -> None:
    text, calls = console_no_grant.say(_rank(_e("Sorento", "brand")), "top 3 salesman for Sorento brand last month")
    assert text.strip() == DENIAL, text
    assert calls == []


# --------------------------------------------------------------------------- #
# Args: the fresh ask runs at once
# --------------------------------------------------------------------------- #


def test_the_owner_example_runs_crm_report_ask_with_the_resolved_args(console) -> None:
    text, calls = console.say(_rank(_e("Sorento", "brand")), "top 3 salesman for Sorento brand last month")
    (args,) = calls
    assert args["group_by"] == "sales_agent", args
    assert args["top_n"] == 3, args
    assert args["sort"] == "desc" and args["measure"] == "amount" and args["basis"] == "delivered", args
    assert args["brand_ids"] == [console.ids["brand"]], args
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args
    assert args["contact_id"] and args["space_id"], args
    assert "FANNY" in text, text
    assert PERIOD_Q not in text and TOPN_Q not in text


def test_bottom_is_sort_asc(console) -> None:
    _text, calls = console.say(_rank(_e("Sorento", "brand"), rank_direction="bottom"), "bottom 3 salesman for Sorento")
    (args,) = calls
    assert args["sort"] == "asc", args


def test_rank_by_quantity_is_measure_qty(console) -> None:
    _text, calls = console.say(_rank(_e("Sorento", "brand"), rank_by="quantity"), "top 3 salesman by qty for Sorento")
    (args,) = calls
    assert args["measure"] == "qty", args


def test_basis_ordered_passes_through(console) -> None:
    _text, calls = console.say(_rank(_e("Sorento", "brand"), basis="ordered"), "top 3 salesman ordered for Sorento")
    (args,) = calls
    assert args["basis"] == "ordered", args


def test_an_unclear_basis_is_delivered(console) -> None:
    _text, calls = console.say(_rank(_e("Sorento", "brand"), basis="unclear"), "top 3 salesman for Sorento")
    (args,) = calls
    assert args["basis"] == "delivered", args


def test_group_by_warehouse_is_location(console) -> None:
    _text, calls = console.say(_rank(_e("Sorento", "brand"), group_by="warehouse"), "top 3 locations for Sorento")
    (args,) = calls
    assert args["group_by"] == "location", args


@pytest.mark.parametrize("group_by", ["customer", "product", "brand", "category", "channel"])
def test_the_other_catalogue_dimensions_pass_through(console, group_by) -> None:
    _text, calls = console.say(_rank(group_by=group_by), f"top 3 {group_by}")
    (args,) = calls
    assert args["group_by"] == group_by, args


def test_a_product_entity_becomes_product_ids(console) -> None:
    _text, calls = console.say(_rank(_e(PRODUCT_CODE, "product")), f"top 3 salesman for {PRODUCT_CODE}")
    (args,) = calls
    assert args["product_ids"] == [console.ids["product"]], args


def test_a_customer_entity_becomes_customer_ids(console) -> None:
    _text, calls = console.say(
        _rank(_e(CUSTOMER_NAME, "customer"), group_by="product"), f"top 3 products for {CUSTOMER_NAME}"
    )
    (args,) = calls
    assert args["customer_ids"] == [console.ids["customer"]], args


def test_a_warehouse_entity_becomes_warehouse_codes(console) -> None:
    _text, calls = console.say(_rank(_e("BRW", "warehouse")), "top 3 salesman in BRW")
    (args,) = calls
    assert args["warehouse_codes"] == ["BRW"], args


def test_a_sales_agent_and_a_category_word_become_ids(console) -> None:
    _text, calls = console.say(
        _rank(_e("FANNY", "sales_agent"), _e("ZZT CATEGORY", "category"), group_by="month"),
        "sales by month for FANNY ZZT CATEGORY",
    )
    (args,) = calls
    assert args["sales_agent_ids"] == [console.ids["agent"]], args
    assert args["category_ids"] == [console.ids["category"]], args


def test_no_group_by_is_a_total_that_runs_without_top_n(console) -> None:
    _text, calls = console.say(_rank(_e("Sorento", "brand"), group_by=None, top_n=None), "how much did we sell of Sorento")
    (args,) = calls
    assert not args.get("group_by") and "top_n" not in args, args
    assert args["date_from"] == "2026-09-01", args


# --------------------------------------------------------------------------- #
# Words that name nothing, dimensions outside the catalogue
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "hint, noun", [("brand", "brand"), ("sales_agent", "sales agent"), ("category", "category")]
)
def test_an_unknown_word_is_said_and_nothing_runs(console, hint, noun) -> None:
    text, calls = console.say(_rank(_e("Zzz", hint)), f"top 3 salesman for Zzz {noun}")
    assert calls == []
    assert text.strip() == f"I don't know 'Zzz' as a {noun}.", text


def test_group_by_date_is_outside_the_catalogue(console) -> None:
    text, calls = console.say(_rank(_e("Sorento", "brand"), group_by="date"), "top 3 days for Sorento")
    assert calls == []
    assert text.strip() == CATALOGUE_LINE, text


# --------------------------------------------------------------------------- #
# Asking back (AC-RE-18a to 18d)
# --------------------------------------------------------------------------- #


def test_ac_re_18a_no_period_asks_which_period_then_the_reply_runs_the_first_ask(console) -> None:
    text, calls = console.say(
        _rank(_e("Sorento", "brand"), date_filter_start=None, date_filter_end=None), "top 3 salesman for Sorento"
    )
    assert text.strip() == PERIOD_Q, text
    assert calls == []
    text, calls = console.say(_reply(**SEP), "last month")
    (args,) = calls
    assert args["brand_ids"] == [console.ids["brand"]], args
    assert args["group_by"] == "sales_agent" and args["top_n"] == 3, args
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args
    assert "FANNY" in text, text


def test_ac_re_18a_a_period_reply_without_a_date_is_a_miss_and_asks_again(console) -> None:
    console.say(_rank(date_filter_start=None, date_filter_end=None), "top 3 salesman")
    text, calls = console.say(_reply(), "whenever")
    assert calls == []
    assert PERIOD_Q in text, text


def test_ac_re_18b_no_number_asks_how_many_then_the_reply_runs(console) -> None:
    text, calls = console.say(_rank(_e("Sorento", "brand"), top_n=None), "top salesman for Sorento last month")
    assert text.strip() == TOPN_Q, text
    assert calls == []
    _text, calls = console.say(_reply(), "5")
    (args,) = calls
    assert args["top_n"] == 5, args
    assert args["brand_ids"] == [console.ids["brand"]], args
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args


def test_ac_re_18b_a_non_number_reply_is_a_miss_and_a_second_miss_gives_up(console) -> None:
    console.say(_rank(top_n=None), "top salesman last month")
    text, calls = console.say(_reply(), "lots")
    assert calls == []
    assert TOPN_Q in text, text
    text, calls = console.say(_reply(), "plenty")
    assert calls == []
    assert text.strip() == GIVE_UP.format(word="plenty"), text


def test_ac_re_18b_a_number_outside_1_to_100_is_a_miss(console) -> None:
    console.say(_rank(top_n=None), "top salesman last month")
    text, calls = console.say(_reply(), "500")
    assert calls == []
    assert TOPN_Q in text, text


def test_ac_re_18c_neither_asks_the_period_first_then_how_many_then_runs(console) -> None:
    text, calls = console.say(
        _rank(_e("Sorento", "brand"), top_n=None, date_filter_start=None, date_filter_end=None), "top salesman for Sorento"
    )
    assert text.strip() == PERIOD_Q and calls == [], text
    text, calls = console.say(_reply(**SEP), "last month")
    assert text.strip() == TOPN_Q and calls == [], text
    _text, calls = console.say(_reply(), "5")
    (args,) = calls
    assert args["top_n"] == 5 and args["date_from"] == "2026-09-01", args
    assert args["brand_ids"] == [console.ids["brand"]], args


def test_ac_re_18d_cancel(console) -> None:
    console.say(_rank(date_filter_start=None, date_filter_end=None), "top 3 salesman")
    text, calls = console.say(_reply(message_type="casual", intent_hint=None), "cancel")
    assert text.strip() == CANCELLED, text
    assert calls == []


# --------------------------------------------------------------------------- #
# Route refusals are said as the route's own message
# --------------------------------------------------------------------------- #


def test_a_route_refusal_is_said_as_its_message(console) -> None:
    console.refuse = {"message": DIMENSION_REFUSAL, "detail": None, "code": "report_dimension_not_allowed"}
    text, calls = console.say(_rank(_e("Sorento", "brand")), "top 3 salesman for Sorento")
    assert calls, "the route is the audience check"
    assert text.strip() == DIMENSION_REFUSAL, text


# --------------------------------------------------------------------------- #
# Engine seam: report_ask.take_words and ENGINE_KEYS
# --------------------------------------------------------------------------- #


def test_take_words_moves_brand_agent_category_onto_report_ask_words() -> None:
    from app.services.chatbot.lanes.business import report_ask

    verdict = _rank(
        _e("Sorento", "brand"), _e("FANNY", "sales_agent"), _e("water tap", "category"),
        _e(PRODUCT_CODE, "product"), _e(CUSTOMER_NAME, "customer"), _e("BRW", "warehouse"),
    )
    out = report_ask.take_words(verdict, "top 3 salesman for Sorento")
    assert out["report_ask_words"] == {"brand": ["Sorento"], "sales_agent": ["FANNY"], "category": ["water tap"]}, out
    assert [e["hint"] for e in out["entities"]] == ["product", "customer", "warehouse"], out["entities"]


def test_take_words_leaves_other_asks_alone() -> None:
    from app.services.chatbot.lanes.business import report_ask

    verdict = _parser_output(domain_hint="order", intent_hint="check_order", order_status="sales_report",
                             entities=[_e("Sorento", "brand")])
    assert report_ask.take_words(verdict, "sales report for Sorento") == verdict


def test_report_ask_words_is_an_engine_key() -> None:
    from app.services.chatbot import required_fields as rf

    assert "report_ask_words" in rf.ENGINE_KEYS


def test_a_forged_report_ask_words_from_the_parser_is_stripped(console) -> None:
    """The parser can never forge the engine's own key: a forged unknown brand word must not
    stop the run, and must not become a brand filter."""
    forged = _rank(report_ask_words={"brand": ["Zzz"], "sales_agent": [], "category": []})
    text, calls = console.say(forged, "top 3 salesman last month")
    (args,) = calls
    assert not args.get("brand_ids"), args
    assert "I don't know" not in text, text


# --------------------------------------------------------------------------- #
# 1b security fix round: F1 (a dealer never probes agent or location words), F2
# --------------------------------------------------------------------------- #

from sqlalchemy import text as _sql  # noqa: E402


def _link_dealer(console, name: str = "ZZT OWN DEALER SDN BHD") -> str:
    """Link the harness contact to one customer of its own: a customer-scoped (dealer) contact."""
    from tests._mc_lookup_seed import customer

    db = console.session_factory()
    try:
        own = customer(db, company_id=DEFAULT_COMPANY_ID, name=name)
        db.execute(
            _sql(
                "INSERT INTO respond_contact_customers (id, contact_id, customer_id, company_id) "
                "SELECT gen_random_uuid(), id, :cust, :company FROM respond_contacts WHERE respond_io_id = :cid"
            ),
            {"cust": str(own.id), "company": DEFAULT_COMPANY_ID, "cid": str(CONTACT_ID)},
        )
        db.commit()
        return str(own.id)
    finally:
        db.close()


def _other_customer(console, name: str = "ZZT OTHER DEALER SDN BHD") -> str:
    from tests._mc_lookup_seed import customer

    db = console.session_factory()
    try:
        row = customer(db, company_id=DEFAULT_COMPANY_ID, name=name)
        db.commit()
        return str(row.id)
    finally:
        db.close()


@pytest.fixture
def dealer(console):
    console.own_customer = _link_dealer(console)
    return console


@pytest.mark.parametrize("word", ["Zzz", "FANNY"], ids=["names_no_agent", "names_an_agent"])
def test_f1_a_dealer_naming_a_sales_agent_gets_the_refusal_and_no_probe(dealer, word) -> None:
    text, calls = dealer.say(_rank(_e(word, "sales_agent"), group_by="product"), f"top products for agent {word}")
    assert text.strip() == DIMENSION_REFUSAL, text
    assert calls == []


def test_f1_a_dealer_naming_a_location_gets_the_refusal(dealer) -> None:
    text, calls = dealer.say(_rank(_e("BRW", "warehouse"), group_by="product"), "top products in BRW")
    assert text.strip() == DIMENSION_REFUSAL, text
    assert calls == []


def test_f1_a_dealer_naming_an_unknown_location_gets_the_refusal_not_a_probe(dealer) -> None:
    text, calls = dealer.say(_rank(_e("ZZTNOWHERE", "warehouse"), group_by="product"), "top products in ZZTNOWHERE")
    assert text.strip() == DIMENSION_REFUSAL, text
    assert calls == []


def test_f1_a_dealer_grouping_by_sales_agent_gets_the_refusal(dealer) -> None:
    text, calls = dealer.say(_rank(group_by="sales_agent"), "top 3 salesman")
    assert text.strip() == DIMENSION_REFUSAL, text
    assert calls == []


def test_f1_a_dealer_with_an_unknown_brand_still_gets_the_unknown_word_line(dealer) -> None:
    text, calls = dealer.say(_rank(_e("Zzz", "brand"), group_by="product"), "top products for Zzz brand")
    assert text.strip() == "I don't know 'Zzz' as a brand.", text
    assert calls == []


def test_f1_a_dealer_with_a_known_brand_runs(dealer) -> None:
    _text, calls = dealer.say(_rank(_e("Sorento", "brand"), group_by="product"), "top products for Sorento")
    (args,) = calls
    assert args["brand_ids"] == [dealer.ids["brand"]], args


def test_f2a_a_dealer_naming_another_customer_never_sends_that_customer(dealer) -> None:
    other = _other_customer(dealer)
    _text, calls = dealer.say(
        _rank(_e("ZZT OTHER DEALER SDN BHD", "customer"), group_by="product"), "top products for ZZT OTHER DEALER SDN BHD"
    )
    for args in calls:
        assert other not in (args.get("customer_ids") or []), args


def test_f2b_an_answering_turn_runs_only_the_carried_args(console) -> None:
    """A customer or sales agent entity on the reply turn never reaches the request."""
    other = _other_customer(console)
    console.say(
        _rank(_e("Sorento", "brand"), date_filter_start=None, date_filter_end=None), "top 3 salesman for Sorento"
    )
    _text, calls = console.say(
        _reply(entities=[_e("ZZT OTHER DEALER SDN BHD", "customer"), _e("FANNY", "sales_agent")], **SEP),
        "last month",
    )
    (args,) = calls
    assert args["brand_ids"] == [console.ids["brand"]], args
    assert other not in (args.get("customer_ids") or []), args
    assert not args.get("customer_ids"), args
    assert not args.get("sales_agent_ids"), args


def _forge(node: Any, forged: dict[str, Any]) -> int:
    """Put `forged` into every open `sales_ranking` slot found in `node` (its extras, and the
    args map inside them if any). Returns how many slots were found."""
    found = 0
    if isinstance(node, dict):
        if node.get("ask") == "sales_ranking":
            extras = node.setdefault("extras", {})
            extras.update(forged)
            for key in ("args", "route_args"):
                if isinstance(extras.get(key), dict):
                    extras[key].update(forged)
            found += 1
        for value in list(node.values()):
            found += _forge(value, forged)
    elif isinstance(node, list):
        for value in node:
            found += _forge(value, forged)
    return found


def test_f2c_the_request_uses_the_turns_own_contact_not_the_carried_one(console) -> None:
    console.say(
        _rank(_e("Sorento", "brand"), date_filter_start=None, date_filter_end=None), "top 3 salesman for Sorento"
    )
    forged = {"contact_id": "ZZT-FORGED-CONTACT", "space_id": "ZZT-FORGED-SPACE"}
    assert _forge(console.session_vars, forged) >= 1, "the open sales_ranking slot was not found in the session"
    _text, calls = console.say(_reply(**SEP), "last month")
    (args,) = calls
    assert args["contact_id"] and args["space_id"], args
    assert args["contact_id"] != "ZZT-FORGED-CONTACT" and args["space_id"] != "ZZT-FORGED-SPACE", args
