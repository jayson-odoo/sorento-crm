"""Top X hot selling S4: the parser keys and the lane wiring (#1171).

`documentation/plans/chatbot/PLAN-chatbot-top-x-hot-selling-24sep.md` "Parser (S4)",
"Lane wiring (S4)" and the UAC's AC-1950 onward, as amended by the owner's rulings
folded on PR #1258 and PR #1263:

* no paging ever; the header states the full count;
* no N named: the bot states the total and asks how many (no length rule, n8n chunks
  long messages), except a single row, which is sent;
* the ranked list is a sticky pick list (`top_selling_pick`, the roster mechanism);
* rows show the code only;
* `rank_by` required (asked when absent), basis delivered | ordered, group item |
  category (asked when unclear);
* a dealer caller is forced to its own customers by the route and a named other
  customer gets the refusal line;
* no date = the current calendar year, set by the route and stated in the header.

Every turn below is one real `engine.run_turn` through the SAME harness the sales
report lane uses (`tests/chatbot/test_outstanding_lane.py::_run_turn`): parser,
access and resolver faked, the MCP call answered by `_fake_route` below, which builds
the route's own body (`TopSellingResponse`, as built on PR #1263) from the lane's args
and renders it through the REAL presenter, the way `view=render` does in production.

Postgres only (`session_factory`, blank schema). Every row seeded here.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot.lanes.business.services import FetchServices
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot import test_outstanding_lane as outstanding_lane
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_outstanding_lane import (
    CUSTOMER_NAME,
    CUSTOMER_UUID,
    HANLIM_UUID_1,
    _all_pick_parser_output,
    _ambiguous_hanlim_resolve_services,
    _present_response,
    _run_turn,
    _seed_contact,
    _session_of,
)

TOOL = "crm_top_selling_report"
GRANT = "sales_orders.sales_report"
DENIAL = "Sales report is not enabled for your account."
ASK_METRIC = "By quantity or by amount?"
ASK_GROUP = "Do you want the top items inside one category, or the categories ranked against each other?"
ASK_BASIS = "Delivered (transferred to DO) or ordered?"
REFUSED = "Sorry, I can only share sales figures for your own account."
ITEM_OFFER = "Reply with a rank number to see that item's customers and months."

ITEM_CODES = ["SRTWT7445", "SRTKT39SS", "SRTBS1020", "SRTSH2201", "SRTWC5501", "SRTWT7446", "SRTWT8120"]
CATEGORY_CODES = ["KS", "WC", "BM"]


def _rows(codes: list[str]) -> list[dict[str, Any]]:
    return [
        {"rank": i, "code": code, "name": f"Name of {code}", "quantity": 100 - i, "amount": 1000.0 - i}
        for i, code in enumerate(codes, start=1)
    ]


def _fake_route(args: dict[str, Any], *, codes: list[str] | None = None, refuse: str | None = None) -> dict:
    """The body `GET /api/v1/order-management/top-selling` answers `args` with, in
    the shape PR #1263 ships. `refuse` answers with the AppException body instead."""
    if refuse:
        return {"message": "refused", "detail": None, "code": refuse}
    group = args.get("group") or "item"
    all_rows = _rows(CATEGORY_CODES if group == "category" else (ITEM_CODES if codes is None else codes))
    body: dict[str, Any] = {
        "rank_by": args.get("rank_by"),
        "basis": args.get("basis") or "delivered",
        "group": group,
        "n": None,
        "date_from": args.get("date_from") or "2026-01-01",
        "date_to": args.get("date_to") or "2026-12-31",
        "filters": {
            "customer_name": CUSTOMER_NAME if args.get("customer_ids") else None,
            "category_name": "KITCHEN SINK" if args.get("category_ids") else None,
            "sales_agent": None,
            "channel": args.get("channel"),
            "dealer_scoped": False,
        },
        "total_count": len(all_rows),
        "rows": all_rows,
        "totals": {"quantity": sum(r["quantity"] for r in all_rows), "amount": sum(r["amount"] for r in all_rows)},
        "sales_agent_fill_rate": None,
        "detail": None,
    }
    if args.get("detail_code"):
        hit = [r for r in all_rows if r["code"] == args["detail_code"]]
        body["rows"] = [{**r, "rank": 1} for r in hit]
        body["total_count"] = len(hit)
        body["detail"] = (
            {
                "code": hit[0]["code"],
                "name": hit[0]["name"],
                "by_customer": [{"customer_name": CUSTOMER_NAME, "quantity": 5, "amount": 50.0}],
                "by_month": [{"month": "2026-03", "quantity": 5, "amount": 50.0}],
            }
            if hit
            else None
        )
    elif args.get("count_only") in (True, "true"):
        if len(all_rows) > 1:
            body["rows"] = []
    elif args.get("n"):
        body["n"] = int(args["n"])
        body["rows"] = all_rows[: int(args["n"])]
    return body


@pytest.fixture
def route(monkeypatch):
    """Swap the harness's MCP double for one that answers `crm_top_selling_report` with
    `_fake_route` rendered through the real presenter. `route.codes` / `route.refuse`
    shape the next answer; each turn gets its own `(name, args)` capture list."""

    class _Route:
        codes: list[str] | None = None
        refuse: str | None = None
        captured: list[tuple[str, dict[str, Any]]] = []

    state = _Route()
    state.captured = []
    present = _present_response()

    def _factory(_response: Any = None):
        captured: list[tuple[str, dict[str, Any]]] = []
        state.captured = captured

        def _call(name: str, args: dict[str, Any]) -> Any:
            captured.append((name, dict(args)))
            if name != TOOL:
                return json.dumps({"has_result": False, "items": []})
            return present(name, json.dumps(_fake_route(args, codes=state.codes, refuse=state.refuse)))

        return _call, captured

    monkeypatch.setattr(outstanding_lane, "_capturing_mcp", _factory)
    return state


def _ts(**overrides: Any) -> dict[str, Any]:
    """A top selling ask as the parser emits it (S4 keys: `rank_by`, `basis`,
    `rank_group`; `top_n` unchanged)."""
    base: dict[str, Any] = dict(
        domain_hint="order",
        intent_hint="check_order",
        order_status="top_selling",
        entities=[],
        rank_by="quantity",
        basis=None,
        rank_group=None,
        top_n=5,
    )
    base.update(overrides)
    return _parser_output(**base)


def _pick(position: int) -> dict[str, Any]:
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entities=[],
        reference_positions=[position], order_status=None,
    )


def _turn(session_factory, monkeypatch, qf, body: str, *, attributes=(GRANT,), **kw):
    result, captured = _run_turn(
        session_factory, monkeypatch, qf=qf, text_body=body,
        msg_id=f"ZZT-top-selling-{uuid.uuid4().hex[:10]}", attributes=list(attributes), **kw,
    )
    return (result.reply or {}).get("text") or "", captured


def _calls(captured) -> list[dict[str, Any]]:
    return [args for name, args in captured if name == TOOL]


def _open_question(session_factory) -> dict[str, Any]:
    return _session_of(session_factory).get("open_question") or {}


# --------------------------------------------------------------------------- #
# AC-1950 - tool pick
# --------------------------------------------------------------------------- #


class TestToolPick:
    def _payload(self, *, order_status: str, entities: list[dict[str, Any]]):
        return {
            "gate": {"compatible_entities": entities},
            "tier_gate": None,
            "ctx": {
                "parse": {
                    "output": _parser_output(
                        domain_hint="order", intent_hint="check_order", order_status=order_status,
                        entities=[], top_selling={"rank_by": "quantity", "top_n": 5},
                    )
                },
                "contact": {"id": 437264483},
                "access": {"attributes": [GRANT]},
            },
        }

    @pytest.mark.parametrize(
        "entities",
        [[], [{"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME}]],
        ids=["no_subject", "customer"],
    )
    def test_tool_pick_top_selling_vs_reports(self, session_factory, entities) -> None:
        """AC-1950: domain `order` + `order_status: "top_selling"` picks the ranking
        with or without a resolved subject."""
        from app.services.chatbot.lanes.business import run_fetch

        calls: list[tuple[str, dict[str, Any]]] = []

        def _call(name, args):
            calls.append((name, args))
            return json.dumps({"has_result": False, "response": "x", "result_set": []})

        run_fetch(self._payload(order_status="top_selling", entities=entities), services=FetchServices(mcp_call=_call))
        assert [name for name, _ in calls] == [TOOL]

    def test_sales_report_still_picks_the_sales_report(self, session_factory) -> None:
        from app.services.chatbot.lanes.business import run_fetch

        calls: list[str] = []
        run_fetch(
            self._payload(
                order_status="sales_report",
                entities=[{"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME}],
            ),
            services=FetchServices(mcp_call=lambda name, args: calls.append(name) or json.dumps({})),
        )
        assert calls == ["crm_sales_report"]

    def test_the_tool_is_a_date_param_tool(self) -> None:
        from app.services.chatbot.lanes.business import fetch as fetch_mod

        assert fetch_mod.DATE_PARAMS[TOOL] == ("date_from", "date_to")


# --------------------------------------------------------------------------- #
# AC-1951 - no grant: the denial line, before any fetch and before any picker
# --------------------------------------------------------------------------- #


class TestNoGrant:
    def test_no_grant_denies_before_fetch_and_picker(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(session_factory, monkeypatch, _ts(), "top 5 selling items by quantity", attributes=())
        assert reply.strip() == DENIAL
        assert _calls(captured) == []
        assert _open_question(session_factory).get("kind") != "top_selling_pick"

    def test_no_grant_never_renders_the_customer_picker(self, session_factory, monkeypatch, route) -> None:
        probed: list[Any] = []
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(
            session_factory, monkeypatch,
            _ts(entities=[{"raw": "hanlim", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}]),
            "top 5 for hanlim by quantity", attributes=(),
            resolve_services=_ambiguous_hanlim_resolve_services(lambda **kw: probed.append(kw)),
        )
        assert reply.strip() == DENIAL
        assert "Which customer" not in reply
        assert _calls(captured) == []


# --------------------------------------------------------------------------- #
# AC-1952 / AC-1953 - the args, off the parser's own fields only
# --------------------------------------------------------------------------- #


class TestArgs:
    def test_rank_by_and_top_n_from_parser_only(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(session_factory, monkeypatch, _ts(rank_by="amount", top_n=3), "top 3 by quantity")
        (args,) = _calls(captured)
        # the parser said amount; the message text says quantity and is never read
        assert args["rank_by"] == "amount"
        assert args["n"] == 3
        assert "count_only" not in args
        assert reply.startswith("*Top 3 selling items*\nRanked by: Amount\n")
        assert "\n1. SRTWT7445: Qty 99, RM 999.00\n" in reply
        assert "Name of" not in reply, "rows print the code only"
        assert reply.endswith(ITEM_OFFER)

    def test_named_n_above_one_hundred_is_capped(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        _reply, captured = _turn(session_factory, monkeypatch, _ts(top_n=250), "top 250 by quantity")
        assert _calls(captured)[0]["n"] == 100

    def test_param_mapping_and_date_default(self, session_factory, monkeypatch, route) -> None:
        """AC-1953 as built: dates, the resolved customer, the channel, the basis and the
        contact identity (review N2: always both ids) all travel; no date sends none (the
        ROUTE defaults to the current calendar year and echoes it into the header)."""
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(
            session_factory, monkeypatch,
            _ts(
                entities=[{"raw": "dealer a", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
                date_filter_start="2026-03-01", date_filter_end="2026-03-31",
                sales_channel="project", basis="ordered",
            ),
            "top 5 for dealer a in march, project, ordered, by quantity",
            matches={"dealer a": {"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME}},
        )
        (args,) = _calls(captured)
        assert args["customer_ids"] == [CUSTOMER_UUID]
        assert args["date_from"] == "2026-03-01" and args["date_to"] == "2026-03-31"
        assert args["channel"] == "project"
        assert args["basis"] == "ordered"
        assert args["contact_id"] and args["space_id"]
        assert "product_ids" not in args and "warehouse_ids" not in args
        assert "Basis: Ordered" in reply

        _seed_contact_again(session_factory)
        reply, captured = _turn(session_factory, monkeypatch, _ts(), "top 5 by quantity")
        (args,) = _calls(captured)
        assert "date_from" not in args and "date_to" not in args
        assert "\nDelivery date: 01/01/2026 to 31/12/2026\n" in reply
        assert "basis" not in args, "no basis word = the route's default (delivered)"


def _seed_contact_again(session_factory) -> None:
    """A fresh conversation for the second half of a test: the same contact, no memory."""
    db = session_factory()
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb)"),
        {"sv": json.dumps({"variables": {}})},
    )
    db.commit()


# --------------------------------------------------------------------------- #
# AC-1954 - a category word under `order` is a category, never a customer
# --------------------------------------------------------------------------- #


class TestCategory:
    def _seed_category(self, session_factory) -> str:
        from app.models.product import ProductCategory

        db = session_factory()
        row = ProductCategory(category_code="KS", category_name="KITCHEN SINK", company_id=DEFAULT_COMPANY_ID)
        db.add(row)
        db.commit()
        return str(row.id)

    def test_category_entity_resolves_under_order(self, session_factory, monkeypatch, route) -> None:
        category_id = self._seed_category(session_factory)
        asked: list[list[str]] = []
        services = outstanding_lane._resolve_services({})
        inner = services.resolve_entity

        def _spy(body):
            asked.append(list(body.get("tokens") or []))
            return inner(body)

        services = services.__class__(access_types=services.access_types, resolve_entity=_spy, probe=services.probe)
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(
            session_factory, monkeypatch,
            _ts(
                top_n=3,
                entities=[{"raw": "kitchen sink", "hint": "category", "canonical_code": None, "current_message": True, "confident": True, "hint_confident": True}],
            ),
            "top 3 kitchen sinks by quantity", resolve_services=services,
        )
        (args,) = _calls(captured)
        assert args["category_ids"] == [category_id]
        assert "customer_ids" not in args
        assert all("kitchen sink" not in tokens for tokens in asked), (
            f"the generic resolver re-types a category token under `order` as a customer "
            f"(_DOMAIN_HINT_EXPANSIONS); it must never be asked about it: {asked}"
        )
        assert "Which customer" not in reply
        assert "Category: KITCHEN SINK" in reply


# --------------------------------------------------------------------------- #
# AC-1955 - an ambiguous customer takes the existing picker, and the pick continues
# --------------------------------------------------------------------------- #


class TestCustomerPicker:
    def test_customer_picker_continues_ask(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(
            session_factory, monkeypatch,
            _ts(
                rank_by="amount", top_n=4, sales_channel="dealer",
                entities=[{"raw": "hanlim", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
            ),
            "top 4 for hanlim dealer by amount",
            resolve_services=_ambiguous_hanlim_resolve_services(lambda **_: {"items": [], "has_result": False}),
        )
        assert _calls(captured) == []
        assert "Which customer do you mean?" in reply
        assert " - has DO" not in reply and " - no DO" not in reply

        reply, captured = _turn(
            session_factory, monkeypatch,
            _parser_output(
                message_type="casual", intent_hint=None, domain_hint=None, entities=[],
                reference_positions=[1], reference_target="dym", entity_op="reuse", order_status=None,
            ),
            "1",
        )
        (args,) = _calls(captured)
        assert args["customer_ids"] == [HANLIM_UUID_1]
        assert args["rank_by"] == "amount" and args["n"] == 4
        assert args["channel"] == "dealer"

    def test_pick_all_continues_ask(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        _turn(
            session_factory, monkeypatch,
            _ts(entities=[{"raw": "hanlim", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}]),
            "top 5 for hanlim by quantity",
            resolve_services=_ambiguous_hanlim_resolve_services(lambda **_: {"items": [], "has_result": False}),
        )
        _reply, captured = _turn(session_factory, monkeypatch, _all_pick_parser_output(), "all")
        (args,) = _calls(captured)
        assert len(args["customer_ids"]) == 2
        assert args["rank_by"] == "quantity" and args["n"] == 5


# --------------------------------------------------------------------------- #
# AC-1956 - a follow-up that only changes the metric keeps the filters
# --------------------------------------------------------------------------- #


class TestFollowUp:
    def test_follow_up_by_amount_keeps_filters(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        matches = {"dealer a": {"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME}}
        _turn(
            session_factory, monkeypatch,
            _ts(
                entities=[{"raw": "dealer a", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
                date_filter_start="2026-03-01", date_filter_end="2026-03-31",
            ),
            "top 5 for dealer a in march by quantity", matches=matches,
        )
        reply, captured = _turn(
            session_factory, monkeypatch,
            _ts(rank_by="amount", top_n=None, domain_hint=None, message_type="business_query"),
            "by amount",
        )
        (args,) = _calls(captured)
        assert args["rank_by"] == "amount"
        assert args["n"] == 5, "the carried N stays"
        assert args["customer_ids"] == [CUSTOMER_UUID]
        assert args["date_from"] == "2026-03-01"
        assert "Ranked by: Amount" in reply

    def test_ordered_follow_up_reruns_on_the_ordered_basis(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        _turn(session_factory, monkeypatch, _ts(), "top 5 by quantity")
        reply, captured = _turn(
            session_factory, monkeypatch,
            _ts(rank_by=None, top_n=None, basis="ordered"),
            "ordered",
        )
        (args,) = _calls(captured)
        assert args["basis"] == "ordered"
        assert args["rank_by"] == "quantity" and args["n"] == 5
        assert "Basis: Ordered" in reply

    def test_a_new_top_selling_ask_does_not_inherit_the_old_metric(self, session_factory, monkeypatch, route) -> None:
        """A fresh ask states its own metric: the carried one only answers a question
        the bot asked, or a follow-up that names no ask of its own."""
        _seed_contact(session_factory, variables={})
        _turn(session_factory, monkeypatch, _ts(rank_by="amount"), "top 5 by amount")
        reply, captured = _turn(
            session_factory, monkeypatch, _ts(rank_by=None, top_n=10, domain_in_message=True), "top 10 selling items",
        )
        assert _calls(captured) == []
        assert reply.strip() == ASK_METRIC

    def test_a_fresh_ask_after_a_single_row_reply_drops_the_old_category(
        self, session_factory, monkeypatch, route
    ) -> None:
        """Reviewer B2 (a), PR #1273: a single row is sent as is and asks nothing, so the
        next ask that names the ranking itself is FRESH. It must not rank inside the
        category the last ask named (owner: never assume a filter nobody named)."""
        from app.models.product import ProductCategory

        db = session_factory()
        db.add(ProductCategory(category_code="KS", category_name="KITCHEN SINK", company_id=DEFAULT_COMPANY_ID))
        db.commit()
        route.codes = ["SRTWT7445"]
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(
            session_factory, monkeypatch,
            _ts(
                top_n=None,
                entities=[{"raw": "kitchen sinks", "hint": "category", "canonical_code": None, "current_message": True, "confident": True, "hint_confident": True}],
            ),
            "top selling kitchen sinks by quantity",
        )
        (args,) = _calls(captured)
        assert args["category_ids"], "the first ask is inside the category"
        assert "How many" not in reply

        reply, captured = _turn(
            session_factory, monkeypatch,
            _ts(rank_by="amount", top_n=5, domain_in_message=True),
            "top 5 selling items by amount",
        )
        (args,) = _calls(captured)
        assert "category_ids" not in args or not args["category_ids"]
        assert args["rank_by"] == "amount" and args["n"] == 5
        assert "\nCategory: all\n" in reply

    def test_a_fresh_ask_after_an_unanswered_how_many_asks_the_metric(
        self, session_factory, monkeypatch, route
    ) -> None:
        """Reviewer B2 (b), PR #1273: the how-many reply is left unanswered and the
        customer asks the ranking again with no metric. That is a fresh ask, so the
        metric is asked (owner: metric required, no default), never carried."""
        _seed_contact(session_factory, variables={})
        reply, _captured = _turn(session_factory, monkeypatch, _ts(top_n=None), "top selling items by quantity")
        assert "How many items do you want to see?" in reply

        reply, captured = _turn(
            session_factory, monkeypatch, _ts(rank_by=None, top_n=10, domain_in_message=True), "top 10 selling items",
        )
        assert _calls(captured) == []
        assert reply.strip() == ASK_METRIC

    def test_a_fresh_ask_after_a_single_row_reply_drops_the_old_customer(
        self, session_factory, monkeypatch, route
    ) -> None:
        """B2, the customer axis: a fresh ask that names no customer ranks every
        customer the contact may see, never the one the last ask named."""
        route.codes = ["SRTWT7445"]
        _seed_contact(session_factory, variables={})
        matches = {"dealer a": {"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME}}
        _turn(
            session_factory, monkeypatch,
            _ts(
                top_n=None,
                entities=[{"raw": "dealer a", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
            ),
            "top selling for dealer a by quantity", matches=matches,
        )
        reply, captured = _turn(
            session_factory, monkeypatch,
            _ts(rank_by="amount", top_n=5, domain_in_message=True),
            "top 5 selling items by amount",
        )
        (args,) = _calls(captured)
        assert "customer_ids" not in args or not args["customer_ids"]
        assert "\nCustomer: all\n" in reply

    def test_the_metric_answer_restating_the_ask_completes_it(self, session_factory, monkeypatch, route) -> None:
        """The other side of B2: the bot asked the metric, and "top 5 by amount" names
        the ranking AND answers the question. It completes the asked ask (its
        category stays) rather than starting over."""
        from app.models.product import ProductCategory

        db = session_factory()
        db.add(ProductCategory(category_code="KS", category_name="KITCHEN SINK", company_id=DEFAULT_COMPANY_ID))
        db.commit()
        _seed_contact(session_factory, variables={})
        reply, _captured = _turn(
            session_factory, monkeypatch,
            _ts(
                rank_by=None, top_n=5,
                entities=[{"raw": "kitchen sink", "hint": "category", "canonical_code": None, "current_message": True, "confident": True, "hint_confident": True}],
            ),
            "top 5 kitchen sink",
        )
        assert reply.strip() == ASK_METRIC
        _reply, captured = _turn(
            session_factory, monkeypatch, _ts(rank_by="amount", top_n=5, domain_in_message=True), "top 5 by amount",
        )
        (args,) = _calls(captured)
        assert args["rank_by"] == "amount"
        assert args["category_ids"]

    def test_another_domain_leaves_the_ranking(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        _turn(session_factory, monkeypatch, _ts(), "top 5 by quantity")
        _reply, captured = _turn(
            session_factory, monkeypatch,
            _parser_output(
                domain_hint="inventory", intent_hint="check_stock", domain_in_message=True,
                entities=[{"raw": "SRTWT7445", "hint": "product", "canonical_code": None, "current_message": True, "confident": True}],
            ),
            "stock for SRTWT7445",
            matches={"SRTWT7445": {"uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "entity_type": "product", "canonical_code": "SRTWT7445"}},
        )
        assert _calls(captured) == []
        focus = _session_of(session_factory).get("focus") or {}
        assert focus.get("status") != "top_selling"


# --------------------------------------------------------------------------- #
# AC-1957 / AC-1958 - miss and header
# --------------------------------------------------------------------------- #


class TestMissAndHeader:
    def test_miss_takes_not_found_path(self, session_factory, monkeypatch, route) -> None:
        route.codes = []
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(session_factory, monkeypatch, _ts(), "top 5 by quantity")
        assert _calls(captured)
        assert "No sales found." in reply
        assert "escalate" in reply.lower()
        assert _open_question(session_factory).get("kind") != "top_selling_pick"

    def test_header_skipped(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        reply, _captured = _turn(session_factory, monkeypatch, _ts(), "top 5 by quantity")
        assert reply.startswith("*Top 5 selling items*\n"), reply
        assert "Dates: all dates" not in reply


# --------------------------------------------------------------------------- #
# AC-1961 / AC-1962 - clarify seams, no fetch, then the answer runs the carried ask
# --------------------------------------------------------------------------- #


class TestClarify:
    def test_metric_clarify_then_answer(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        matches = {"dealer a": {"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME}}
        reply, captured = _turn(
            session_factory, monkeypatch,
            _ts(
                rank_by=None, top_n=5,
                entities=[{"raw": "dealer a", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
            ),
            "top 5 selling items for dealer a", matches=matches,
        )
        assert reply.strip() == ASK_METRIC
        assert _calls(captured) == []

        reply, captured = _turn(session_factory, monkeypatch, _ts(rank_by="amount", top_n=None), "amount")
        (args,) = _calls(captured)
        assert args["rank_by"] == "amount"
        assert args["n"] == 5
        assert args["customer_ids"] == [CUSTOMER_UUID]
        assert reply.startswith("*Top 5 selling items*\nRanked by: Amount\n")

    def test_group_clarify_then_answer(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(session_factory, monkeypatch, _ts(rank_group="unclear", top_n=3), "top selling by category")
        assert reply.strip() == ASK_GROUP
        assert _calls(captured) == []

        reply, captured = _turn(
            session_factory, monkeypatch, _ts(rank_group="category", rank_by=None, top_n=None), "the categories",
        )
        (args,) = _calls(captured)
        assert args["group"] == "category"
        assert args["n"] == 3
        assert reply.startswith("*Top 3 selling categories*\n")
        assert "\n1. KS: Qty 99, RM 999.00\n" in reply

    def test_basis_clarify(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(session_factory, monkeypatch, _ts(basis="unclear"), "top orders")
        assert reply.strip() == ASK_BASIS
        assert _calls(captured) == []
        _reply, captured = _turn(session_factory, monkeypatch, _ts(basis="delivered", rank_by=None, top_n=None), "delivered")
        (args,) = _calls(captured)
        assert args["basis"] == "delivered" and args["rank_by"] == "quantity" and args["n"] == 5

    def test_the_fixed_lines_are_the_presenters_own(self) -> None:
        """One literal each (plan, "The reply"): the backend carries its own copy because
        the backend container does not ship `sorento_crm_mcp`, and this pins the two."""
        from app.services.chatbot.lanes.business import (
            TOP_SELLING_ASK_BASIS,
            TOP_SELLING_ASK_GROUP,
            TOP_SELLING_ASK_METRIC,
        )

        _present_response()
        from sorento_crm_mcp import presenters

        assert TOP_SELLING_ASK_METRIC == presenters.TOP_SELLING_ASK_METRIC
        assert TOP_SELLING_ASK_GROUP == presenters.TOP_SELLING_ASK_GROUP
        assert TOP_SELLING_ASK_BASIS == presenters.TOP_SELLING_ASK_BASIS


# --------------------------------------------------------------------------- #
# AC-1963 - a dealer naming another customer is refused
# --------------------------------------------------------------------------- #


class TestDealer:
    def test_dealer_other_customer_refused(self, session_factory, monkeypatch, route) -> None:
        """The route forces a dealer contact to its own ledgers and answers 403
        `customer_not_permitted` for any other customer (and for a name that matches
        nobody, so it is no name oracle). The reply is the refusal line and no figures."""
        route.refuse = "customer_not_permitted"
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(
            session_factory, monkeypatch,
            _ts(entities=[{"raw": "dealer a", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}]),
            "top 5 for dealer a by quantity",
            matches={"dealer a": {"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME}},
        )
        assert _calls(captured), "the route is the check"
        assert reply.strip() == REFUSED
        assert "escalate" not in reply.lower()
        assert _open_question(session_factory).get("kind") != "top_selling_pick"


# --------------------------------------------------------------------------- #
# AC-1964 / AC-1966 - the ranked list is a sticky pick list
# --------------------------------------------------------------------------- #


class TestPickList:
    def test_rank_number_opens_detail(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        _turn(session_factory, monkeypatch, _ts(sales_channel="dealer"), "top 5 dealer by quantity")
        question = _open_question(session_factory)
        assert question.get("kind") == "top_selling_pick"
        assert [o.get("label") for o in question.get("options") or []] == ITEM_CODES[:5]

        reply, captured = _turn(session_factory, monkeypatch, _pick(2), "2")
        (args,) = _calls(captured)
        assert args["detail_code"] == "SRTKT39SS"
        assert args["rank_by"] == "quantity" and args["channel"] == "dealer"
        assert "n" not in args and "count_only" not in args
        assert reply.startswith("*SRTKT39SS: customers and months*\n")
        assert "*_By customer_*" in reply and "*_By month_*" in reply

        # sticky: the list stays open, and a later number answers against it
        question = _open_question(session_factory)
        assert question.get("kind") == "top_selling_pick"
        reply, captured = _turn(session_factory, monkeypatch, _pick(4), "4")
        (args,) = _calls(captured)
        assert args["detail_code"] == "SRTSH2201"

        # the detail is one shot: a follow-up re-runs the ranking itself
        _reply, captured = _turn(session_factory, monkeypatch, _ts(rank_by="amount", top_n=None), "by amount")
        (args,) = _calls(captured)
        assert "detail_code" not in args
        assert args["rank_by"] == "amount" and args["n"] == 5

    def test_typed_code_opens_detail(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        _turn(session_factory, monkeypatch, _ts(), "top 5 by quantity")
        _reply, captured = _turn(
            session_factory, monkeypatch,
            _parser_output(
                message_type="business_query", intent_hint=None, domain_hint=None, order_status=None,
                entities=[{"raw": "srtbs1020", "hint": "product", "canonical_code": None, "current_message": True, "confident": True}],
            ),
            "srtbs1020",
        )
        (args,) = _calls(captured)
        assert args["detail_code"] == "SRTBS1020"

    def test_number_past_the_last_row_fetches_nothing(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        _turn(session_factory, monkeypatch, _ts(), "top 5 by quantity")
        _reply, captured = _turn(session_factory, monkeypatch, _pick(9), "9")
        assert _calls(captured) == []
        assert _open_question(session_factory).get("kind") == "top_selling_pick"

    def test_category_pick_runs_that_categorys_items(self, session_factory, monkeypatch, route) -> None:
        from app.models.product import ProductCategory

        db = session_factory()
        category = ProductCategory(category_code="WC", category_name="WATER CLOSET", company_id=DEFAULT_COMPANY_ID)
        db.add(category)
        db.commit()
        _seed_contact(session_factory, variables={})
        _turn(session_factory, monkeypatch, _ts(rank_group="category", top_n=3), "which category sells most by quantity")
        assert [o.get("label") for o in _open_question(session_factory).get("options") or []] == CATEGORY_CODES

        _reply, captured = _turn(session_factory, monkeypatch, _pick(2), "2")
        (args,) = _calls(captured)
        assert args.get("group") in (None, "item")
        assert args["category_ids"] == [str(category.id)]
        assert "detail_code" not in args


# --------------------------------------------------------------------------- #
# AC-1965 - no N named: state the total and ask how many; the number runs it
# --------------------------------------------------------------------------- #


class TestHowMany:
    def test_how_many_then_number(self, session_factory, monkeypatch, route) -> None:
        _seed_contact(session_factory, variables={})
        reply, captured = _turn(session_factory, monkeypatch, _ts(top_n=None), "top selling items by quantity")
        (args,) = _calls(captured)
        assert args["count_only"] is True
        assert "n" not in args
        assert "\nItems with sales: 7\n" in reply
        assert reply.endswith("How many items do you want to see? Reply with a number from 1 to 7.")
        assert _open_question(session_factory).get("kind") != "top_selling_pick"

        reply, captured = _turn(session_factory, monkeypatch, _ts(top_n=4, rank_by=None), "4")
        (args,) = _calls(captured)
        assert args["n"] == 4 and args["rank_by"] == "quantity"
        assert "count_only" not in args
        assert reply.startswith("*Top 4 selling items*\n")

    def test_a_bare_number_under_the_how_many_question_is_the_count(self, session_factory, monkeypatch, route) -> None:
        """The parser may read a bare "20" as a position. With no list open and the bot
        waiting on how many, the number is the N (the deterministic side reads the
        parser's own `reference_positions`, never the text)."""
        _seed_contact(session_factory, variables={})
        _turn(session_factory, monkeypatch, _ts(top_n=None), "top selling items by quantity")
        _reply, captured = _turn(session_factory, monkeypatch, _pick(6), "6")
        (args,) = _calls(captured)
        assert args["n"] == 6

    def test_one_row_is_sent_as_is(self, session_factory, monkeypatch, route) -> None:
        route.codes = ["SRTWT7445"]
        _seed_contact(session_factory, variables={})
        reply, _captured = _turn(session_factory, monkeypatch, _ts(top_n=None), "top selling items by quantity")
        assert "\n1. SRTWT7445: Qty 99, RM 999.00\n" in reply
        assert "How many" not in reply


# --------------------------------------------------------------------------- #
# AC-1959 - the parser keys and the prompt
# --------------------------------------------------------------------------- #


class TestParser:
    @pytest.mark.parametrize("key", ["rank_by", "basis", "rank_group"])
    def test_parser_schema_key(self, key: str) -> None:
        from app.services.chatbot.head import parser as parser_mod

        schema = parser_mod.PARSE_OUTPUT_JSON_SCHEMA
        assert key in schema["properties"]
        assert key in schema["required"], "strict mode rejects a property absent from required"
        assert key in parser_mod.TOLERATED_ABSENT, "recorded emissions predate the key"

    def test_parser_enums(self) -> None:
        from app.services.chatbot.head import parser as parser_mod

        props = parser_mod.PARSE_OUTPUT_JSON_SCHEMA["properties"]
        assert props["rank_by"]["enum"] == ["quantity", "amount", None]
        assert props["basis"]["enum"] == ["delivered", "ordered", "unclear", None]
        assert props["rank_group"]["enum"] == ["item", "category", "unclear", None]

    def test_parser_prompt_teaches_top_selling(self) -> None:
        from app.services import chatbot_parser_prompt as prompt_mod

        text = prompt_mod.TOP_SELLING_ADDENDUM
        for needle in ('order_status "top_selling"', '"rank_by"', '"basis"', '"rank_group"', "top_n"):
            assert needle in text, needle
        assert prompt_mod.SEMANTIC_PARSER_PROMPT.endswith(text)
        for banned in (chr(0x2014), chr(0x2013)):
            assert banned not in text

    def test_the_migration_publishes_the_prompt(self) -> None:
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "chatbot_top_selling_vocab.py"
        spec = importlib.util.spec_from_file_location("chatbot_top_selling_vocab", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT

        assert module._full_text() == SEMANTIC_PARSER_PROMPT
        assert module.down_revision == "chatbot_top_selling_tool"
        assert len(module.revision) <= 32

    def test_focus_carries_the_top_selling_slot(self) -> None:
        from app.services.chatbot import contracts as contracts_mod
        from app.services.chatbot.turn.state import Focus, focus_from_wire, focus_to_wire

        assert "top_selling" in contracts_mod.Focus.model_fields
        focus = Focus(status="top_selling", top_selling={"rank_by": "amount", "top_n": 5})
        assert focus_from_wire(focus_to_wire(focus)).top_selling == {"rank_by": "amount", "top_n": 5}
