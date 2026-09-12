"""Phase 2 RED tests - S4 lane wiring for the outstanding report.

`documentation/plans/chatbot/PLAN-chatbot-outstanding-report.md` "S4 on main" (13 numbered
wiring points) + "Tester's list"; `chatbot-outstanding-report-acceptance-criteria.md`
AC-1130 to AC-1142 (S4 slice). Written BEFORE any of the wiring exists - S1 to S3 (the
presenter, the route/service, the MCP tool) are already merged on this branch; this file is
about the CHATBOT LANE consuming them.

**Two ways a test in this file is red, both legitimate (see each class docstring for which
one it is):**

1. A literal/table assertion against code that already exists (`gate.ALLOWED["order"]`,
   `fetch.DATE_PARAMS`, the parser prompt text, `fetch.CHATBOT_READ_ONLY_TOOLS`) - fails
   because the entry is simply absent yet.
2. A behavioural assertion through `app.services.chatbot.lanes.business.run_fetch` (the
   real call site `engine.run_turn` uses for the fetch step) or through a full
   `engine.run_turn` turn with the parser/MCP/resolver seams faked, the same pattern
   `tests/chatbot/test_foundre_rung_end_to_end.py` and `test_pass4_item1a_team_clarify_
   consumed.py` already use for an analogous "the CRM decides, not n8n" mechanism. These
   fail today because `select_tool` always returns the domain's first-listed tool
   (`crm_order_management_orders_list`) regardless of `order_status`, so the fake MCP
   client below sees either the wrong tool name or no call at all.

**Tester's own choices, made explicit** (the plan/UAC describe the behaviour, not every
function name - same latitude `test_s6b_fetch_lane.py` took):

* The reply-composition tests (AC-1130, AC-1141) assert only the EXACT strings the plan
  itself pins verbatim in "The reply (contract for Phase 1)" / "Scope question (D2)" / S4
  point 12 - copy the CRM composes itself, independent of how the two-block REPORT text
  gets rendered (a question this file deliberately stays agnostic on: whether the MCP
  server renders it server-side via `view=render` + `present_response`, per S4 point 5, or
  the backend lane builds it - both are live readings of the current code, see
  `sorento_crm_mcp/sorento_crm_mcp/presenters.py`'s own module docstring above
  `_outstanding_report`). AC-1132/AC-1135/AC-1138 therefore assert on the MCP CALL ARGS and
  the SESSION STATE (`pending`, `selection_context`, `last_result_set`,
  `outstanding_filters`) - both unambiguous per the plan - and only require the reply text
  be non-empty.
* `outstanding_filters` (S4 point 4's own name) is assumed to be a new top-level session
  variable, written the same turn `pending` is (`tail/compile_state.py`), read back the
  next turn - the plan names it explicitly, this file just picks its shape (a dict with
  `product_code` / `date_filter_start` / `date_filter_end` / `customer_ids` /
  `warehouse_codes`).
* `services.resolve_warehouse_token(db, token)` (AC-1133) is a new function name this file
  proposes for "the warehouse resolver in `lanes/business/services.py`" the plan names but
  does not spell.
* `fetch.ORDER_STATUS_TO_SCOPE` (AC-1131's fetch half) is a new table name this file
  proposes for "fetch maps so_outstanding/do_outstanding/outstanding_both to scope
  so/do/both".

Postgres only (`session_factory`, blank schema). Every row seeded here.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.models.user import SystemSetting
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.lanes.business import fetch as fetch_mod
from app.services.chatbot.lanes.business import gate as gate_mod
from app.services.chatbot.lanes.business.services import (
    AnswerServices,
    FetchServices,
    ResolveGateServices,
)
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, seeded  # noqa: F401
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401

PRODUCT_UUID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PRODUCT_CODE = "SRTWT7445"
CUSTOMER_UUID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CUSTOMER_NAME = "Dealer A Sdn Bhd"


def _qf(**overrides: Any) -> dict[str, Any]:
    """`_parser_output`, defaulted to an "order" domain product ask."""
    base = dict(
        domain_hint="order",
        intent_hint="check_order",
        entities=[
            {
                "raw": PRODUCT_CODE,
                "hint": "product",
                "canonical_code": None,
                "current_message": True,
                "confident": True,
            }
        ],
    )
    base.update(overrides)
    return _parser_output(**base)


def _resolve_services(matches: dict[str, dict[str, Any]]) -> ResolveGateServices:
    """A `resolve_entity` seam that resolves EVERY raw token in `matches`, unconditionally -
    same simplification `test_foundre_rung_end_to_end.py::_bundle` makes (the real resolver
    is not under test here)."""

    def _resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "tokens": list(matches),
            "resolutions": [
                {"raw": raw, "token": raw, "matches": [match]}
                for raw, match in matches.items()
            ],
            "unresolved_tokens": [],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=_resolve_entity,
        probe=lambda **_: None,
    )


def _capturing_mcp(response: Any = None):
    """A fake `mcp_call(name, args)`. `captured` records every `(name, args)` call; a test
    asserting "no tool call happened" reads `captured == []`."""
    captured: list[tuple[str, dict[str, Any]]] = []

    def _call(name: str, args: dict[str, Any]) -> Any:
        captured.append((name, dict(args)))
        if response is not None:
            return response if isinstance(response, str) else json.dumps(response)
        return json.dumps({"has_result": False, "items": []})

    return _call, captured


def _enable_business_lane(session_factory) -> None:
    """`chatbot_business_lane_enabled` ON and `business_query` in `chatbot_completed_lanes`
    - same two-step switch `test_foundre_rung_end_to_end.py::_run_stock_turn` flips."""
    set_chatbot_switches(session_factory, business_lane=True)
    db = session_factory()
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    row.chatbot_completed_lanes = ["business_query"]
    db.commit()


def _wire_business_services(
    monkeypatch, *, resolve_services: ResolveGateServices, mcp_call
) -> None:
    monkeypatch.setattr(
        engine_mod.business_services, "production_services", lambda db, *, space_id=None: resolve_services
    )
    monkeypatch.setattr(
        engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=mcp_call)
    )
    monkeypatch.setattr(
        engine_mod.business_services,
        "answer_services_for",
        lambda session_factory: AnswerServices(
            mcp_probe=lambda name, args: {"data": []}, family_fetch=lambda query: {"data": []}
        ),
    )


def _session_of(session_factory) -> dict:
    db = session_factory()
    row = db.execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"),
        {"cid": CONTACT_ID},
    ).first()
    raw = row.session_vars if row is not None else {}
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def _seed_contact(session_factory, *, variables: dict[str, Any]) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000009", "sv": json.dumps({"variables": variables})},
    )
    db.commit()


def _run_turn(
    session_factory,
    monkeypatch,
    *,
    qf: dict[str, Any],
    text_body: str,
    msg_id: str,
    attributes: list[str] | None = None,
    matches: dict[str, dict[str, Any]] | None = None,
    mcp_response: Any = None,
):
    """One real `engine.run_turn`, business lane on, parser/access/resolver/MCP faked."""
    _enable_business_lane(session_factory)
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True,
            "decision": "allow",
            "agent_name": "General",
            "attributes": attributes or [],
            "all_attributes_allowed": None,
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")
    from app.services.chatbot.head import parser as parser_mod

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
        )

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: qf)

    call, captured = _capturing_mcp(mcp_response)
    _wire_business_services(
        monkeypatch, resolve_services=_resolve_services(matches or {}), mcp_call=call
    )

    envelope = _envelope()
    envelope.message["message"]["messageId"] = msg_id
    envelope.message["message"]["message"]["text"] = text_body
    result = engine_mod.run_turn(envelope, session_factory=session_factory)
    return result, captured


REPORT_HIT = {
    "product_code": PRODUCT_CODE,
    "customer_name": None,
    "warehouse_codes": [],
    "order_date_from": None,
    "order_date_to": None,
    "so": {
        "ordered_qty": 10, "transferred_qty": 3, "outstanding_qty": 7, "so_count": 1,
        "order_date_min": "2026-01-01", "order_date_max": "2026-01-01",
    },
    "do": None,
    "so_by_location": [], "so_by_customer": [], "do_by_location": [], "do_by_customer": [],
    "so_rows": [
        {
            "so_number": "SO1", "customer_name": CUSTOMER_NAME, "location": "BRW-IB",
            "ordered_qty": 10, "transferred_qty": 3, "outstanding_qty": 7, "order_date": "2026-01-01",
        }
    ],
    "do_rows": [],
}


# --------------------------------------------------------------------------- #
# AC-1131 - parser vocabulary + the fetch-side scope mapping
# --------------------------------------------------------------------------- #


class TestScopeWordsBind:
    def test_parser_prompt_names_do_outstanding_and_outstanding_both(self) -> None:
        from app.services import chatbot_parser_prompt as prompt_mod

        addendum = prompt_mod.GROWTH_R1_ADDENDUM
        assert "do_outstanding" in addendum, "the parser vocabulary must teach do_outstanding"
        assert "outstanding_both" in addendum, "the parser vocabulary must teach outstanding_both"

    def test_fetch_maps_order_status_to_scope(self) -> None:
        """S4 point 3: `so_outstanding` -> so, `do_outstanding` -> do, `outstanding_both`
        -> both. Tester's own name, see module docstring."""
        table = fetch_mod.ORDER_STATUS_TO_SCOPE
        assert table == {"so_outstanding": "so", "do_outstanding": "do", "outstanding_both": "both"}


# --------------------------------------------------------------------------- #
# AC-1133 - location token resolution (D5), reading the real `warehouses` table
# --------------------------------------------------------------------------- #


class TestLocationTokenResolution:
    """Tester's own function name (module docstring): `services.resolve_warehouse_token`."""

    def _seed_warehouses(self, db) -> None:
        from app.models.inventory import Warehouse

        db.add_all(
            [
                Warehouse(id=str(uuid.uuid4()), warehouse_code="ZZT-BRW-IB", warehouse_name="BRW IB", is_active=True),
                Warehouse(id=str(uuid.uuid4()), warehouse_code="ZZT-MWH-IB", warehouse_name="MWH IB", is_active=True),
                Warehouse(id=str(uuid.uuid4()), warehouse_code="ZZT-BRW-BB", warehouse_name="BRW BB", is_active=True),
            ]
        )
        db.commit()

    def test_exact_code_matches_only_itself(self, session_factory) -> None:
        from app.services.chatbot.lanes.business import services as business_services

        db = session_factory()
        self._seed_warehouses(db)
        assert business_services.resolve_warehouse_token(db, "ZZT-BRW-IB") == ["ZZT-BRW-IB"]

    def test_suffix_token_matches_every_code_ending_in_it(self, session_factory) -> None:
        from app.services.chatbot.lanes.business import services as business_services

        db = session_factory()
        self._seed_warehouses(db)
        assert set(business_services.resolve_warehouse_token(db, "IB")) == {"ZZT-BRW-IB", "ZZT-MWH-IB"}

    def test_unknown_token_resolves_to_nothing(self, session_factory) -> None:
        from app.services.chatbot.lanes.business import services as business_services

        db = session_factory()
        self._seed_warehouses(db)
        assert business_services.resolve_warehouse_token(db, "ZZZ-NO-SUCH-TOKEN") == []


class TestLocationTokenPipeline:
    """AC-1133's PIPELINE half, found by the coder after `services.resolve_warehouse_token`
    landed: the function above is correct in isolation, but nothing in the fetch pipeline
    ever calls it with the customer's own location word, so a live "... outstanding for
    IB" turn sends no `warehouse_codes` to `crm_outstanding_report` at all. Same fake-fetch
    style as `TestScopeAnswerRunsReportWithCarriedFilters` (AC-1132): a REAL `warehouses`
    table via `session_factory` (the location resolver is DB-backed and must not be
    faked), the product resolved through the same `_resolve_services` seam every other
    test in this file uses, and the tool call captured through the fake `mcp_call`."""

    def _seed_warehouses(self, session_factory) -> None:
        from app.models.inventory import Warehouse

        db = session_factory()
        db.add_all(
            [
                Warehouse(id=str(uuid.uuid4()), warehouse_code="BRW-IB", warehouse_name="BRW IB", is_active=True),
                Warehouse(id=str(uuid.uuid4()), warehouse_code="MWH-IB", warehouse_name="MWH IB", is_active=True),
                Warehouse(id=str(uuid.uuid4()), warehouse_code="BRW", warehouse_name="BRW", is_active=True),
            ]
        )
        db.commit()

    def test_location_token_in_message_reaches_tool_as_warehouse_codes(self, session_factory, monkeypatch) -> None:
        self._seed_warehouses(session_factory)
        _seed_contact(session_factory, variables={})
        result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(
                order_status="so_outstanding",
                entities=[
                    {
                        "raw": PRODUCT_CODE, "hint": "product", "canonical_code": None,
                        "current_message": True, "confident": True,
                    },
                    {
                        "raw": "IB", "hint": "warehouse", "canonical_code": None,
                        "current_message": True, "confident": True,
                    },
                ],
            ),
            text_body="SRTWT7445 sales order outstanding for IB",
            msg_id="ZZT-outstanding-location-ib-1",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_HIT,
        )
        assert captured, "the report must still be fetched"
        name, args = captured[0]
        assert name == "crm_outstanding_report", name
        assert set(args.get("warehouse_codes") or []) == {"BRW-IB", "MWH-IB"}, (
            f"the 'IB' suffix token must resolve to every warehouse code ending in it "
            f"and reach the tool as warehouse_codes: {args}"
        )
        reply = (result.reply or {}).get("text") or ""
        assert "Location: IB (BRW-IB, MWH-IB)" in reply, (
            f"the header must echo the token and what it resolved to (D5/AC-1105): {reply!r}"
        )

    def test_exact_code_token_in_message_reaches_tool(self, session_factory, monkeypatch) -> None:
        self._seed_warehouses(session_factory)
        _seed_contact(session_factory, variables={})
        _result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(
                order_status="so_outstanding",
                entities=[
                    {
                        "raw": PRODUCT_CODE, "hint": "product", "canonical_code": None,
                        "current_message": True, "confident": True,
                    },
                    {
                        "raw": "BRW", "hint": "warehouse", "canonical_code": None,
                        "current_message": True, "confident": True,
                    },
                ],
            ),
            text_body="SRTWT7445 sales order outstanding for BRW",
            msg_id="ZZT-outstanding-location-brw-1",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_HIT,
        )
        assert captured, "the report must still be fetched"
        _name, args = captured[0]
        assert args.get("warehouse_codes") == ["BRW"], (
            f"an exact warehouse-code token must resolve to itself only, no other code: {args}"
        )


# --------------------------------------------------------------------------- #
# AC-1134 - date params, order_date not actual_delivery_date
# --------------------------------------------------------------------------- #


class TestDateParams:
    def test_crm_outstanding_report_uses_order_date_params(self) -> None:
        assert fetch_mod.DATE_PARAMS.get("crm_outstanding_report") == (
            "order_date_from", "order_date_to",
        )


# --------------------------------------------------------------------------- #
# S4 point 7 - the gate admits a warehouse entity into the "order" domain
# --------------------------------------------------------------------------- #


class TestGateAdmitsWarehouseForOrder:
    def test_warehouse_is_an_allowed_type_for_order(self) -> None:
        assert "warehouse" in gate_mod.ALLOWED["order"], (
            f"S4 point 7: ALLOWED['order'] must admit a warehouse entity: {gate_mod.ALLOWED['order']}"
        )


# --------------------------------------------------------------------------- #
# S4 point 12 / AC-1142 - the reveal key exists on both sides
# --------------------------------------------------------------------------- #


class TestSoKeyListedInFieldRevealKeysAndCatalog:
    def test_so_key_listed_in_field_reveal_keys_and_catalog(self) -> None:
        import sys
        from pathlib import Path

        from app.services.contact_field_reveal_service import FIELD_REVEAL_KEYS

        pair = ("sales_orders.outstanding", "Sales order outstanding")
        assert pair in FIELD_REVEAL_KEYS, (
            f"FIELD_REVEAL_KEYS must carry {pair}, the key that gates AC-1140/AC-1141: "
            f"{FIELD_REVEAL_KEYS}"
        )

        repo_root = Path(__file__).resolve().parents[3]
        mcp_root = repo_root / "sorento_crm_mcp"
        if str(mcp_root) not in sys.path:
            sys.path.append(str(mcp_root))
        from sorento_crm_mcp.catalog import CATALOG

        spec = next(s for s in CATALOG if s.name == "crm_outstanding_report")
        restricted = getattr(spec, "restricted_fields", None) or ()
        assert pair in restricted, (
            f"crm_outstanding_report's ToolSpec.restricted_fields must carry {pair}: {restricted}"
        )


# --------------------------------------------------------------------------- #
# S4 point 2 - tool pick: domain "order" + product + an outstanding order_status
# --------------------------------------------------------------------------- #


class TestToolPick:
    """Through `run_fetch` directly - the real call site `run_until_exit`'s caller uses,
    not a hand-rolled re-implementation of the pick (module docstring)."""

    def _payload(self, *, order_status: str, entities: list[dict[str, Any]], attributes=None):
        return {
            "gate": {"compatible_entities": entities},
            "tier_gate": None,
            "ctx": {
                "parse": {"output": _qf(order_status=order_status, entities=[])},
                "contact": {"id": CONTACT_ID},
                "access": {"attributes": attributes or ["sales_orders.outstanding"]},
            },
        }

    def test_outstanding_with_product_picks_report_tool(self, session_factory) -> None:
        from app.services.chatbot.lanes.business import run_fetch

        call, captured = _capturing_mcp(REPORT_HIT)
        payload = self._payload(
            order_status="outstanding",
            entities=[{"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}],
        )
        run_fetch(payload, services=FetchServices(mcp_call=call))
        assert captured, "no MCP tool was ever called"
        name, _args = captured[0]
        assert name == "crm_outstanding_report", (
            f"domain=order + a resolved product + order_status=outstanding must pick "
            f"crm_outstanding_report, not {name!r} (S4 point 2)"
        )

    def test_outstanding_without_product_keeps_order_list(self, session_factory) -> None:
        """S4 point 2's own carve-out: no product -> the existing order-list path,
        untouched (a customer-only ask keeps today's so_outstanding bucket)."""
        from app.services.chatbot.lanes.business import run_fetch

        call, captured = _capturing_mcp()
        payload = self._payload(
            order_status="so_outstanding",
            entities=[{"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME}],
        )
        run_fetch(payload, services=FetchServices(mcp_call=call))
        assert captured, "no MCP tool was ever called"
        name, _args = captured[0]
        assert name == "crm_order_management_orders_list", (
            f"a customer-only outstanding ask (no product) must keep today's order-list "
            f"tool, not {name!r}"
        )


# --------------------------------------------------------------------------- #
# AC-1136 - a resolved customer entity becomes customer_ids on the report call
# --------------------------------------------------------------------------- #


class TestCustomerEntityBecomesCustomerIds:
    def test_customer_entity_becomes_customer_ids(self, session_factory) -> None:
        from app.services.chatbot.lanes.business import run_fetch

        call, captured = _capturing_mcp(REPORT_HIT)
        payload = {
            "gate": {
                "compatible_entities": [
                    {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE},
                    {"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME},
                ]
            },
            "tier_gate": None,
            "ctx": {
                "parse": {"output": _qf(order_status="outstanding", entities=[])},
                "contact": {"id": CONTACT_ID},
                "access": {"attributes": ["sales_orders.outstanding"]},
            },
        }
        run_fetch(payload, services=FetchServices(mcp_call=call))
        assert captured, "no MCP tool was ever called"
        name, args = captured[0]
        assert name == "crm_outstanding_report", name
        assert args.get("customer_ids") == [CUSTOMER_UUID], (
            f"the resolved customer must be sent as customer_ids (AC-1113b/AC-1136): {args}"
        )
        assert args.get("product_code") == PRODUCT_CODE, (
            f"crm_outstanding_report takes product_code (exact string), not product_ids "
            f"(the route's own contract - see PLAN 'Backend contract'): {args}"
        )


# --------------------------------------------------------------------------- #
# AC-1140 / AC-1141 - the sales_orders.outstanding gate, before any fetch
# --------------------------------------------------------------------------- #


class TestFieldRevealGateBeforeFetch:
    def _payload(self, *, order_status: str, attributes: list[str]):
        return {
            "gate": {
                "compatible_entities": [
                    {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE},
                ]
            },
            "tier_gate": None,
            "ctx": {
                "parse": {"output": _qf(order_status=order_status, entities=[])},
                "contact": {"id": CONTACT_ID},
                "access": {"attributes": attributes},
            },
        }

    def test_no_so_key_skips_question_and_runs_do_only(self, session_factory) -> None:
        """AC-1140: no `sales_orders.outstanding` -> bare 'outstanding' runs scope=do,
        no question, no SO query."""
        from app.services.chatbot.lanes.business import run_fetch

        call, captured = _capturing_mcp(REPORT_HIT)
        run_fetch(self._payload(order_status="outstanding", attributes=[]), services=FetchServices(mcp_call=call))
        assert captured, "the DO-only report must still run without the grant"
        name, args = captured[0]
        assert name == "crm_outstanding_report", name
        assert args.get("scope") == "do", (
            f"without the grant, scope must be forced to 'do': {args}"
        )
        assert "so" not in {k for k in args if k == "scope" and args[k] == "so"}

    def test_no_so_key_explicit_so_ask_refuses_then_do_block(self, session_factory, monkeypatch) -> None:
        """AC-1141: an EXPLICIT SO ask ('sales order outstanding') without the grant still
        runs (scope forced to do) and the customer-facing reply carries the refusal line
        BEFORE the DO block. Composition is a full-turn concern - see module docstring for
        why only this pinned line is asserted, not the DO block's own content."""
        _seed_contact(session_factory, variables={})
        result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(order_status="so_outstanding"),
            text_body="sales order outstanding for SRTWT7445",
            msg_id="ZZT-outstanding-so-refuse-1",
            attributes=[],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_HIT,
        )
        assert captured, "the DO block must still be fetched even when SO is refused"
        _name, args = captured[0]
        assert args.get("scope") == "do", (
            f"an explicit SO ask without the grant must still force scope=do: {args}"
        )
        reply = (result.reply or {}).get("text") or ""
        assert "Sales order figures are not enabled for your account." in reply, (
            f"D13's exact refusal line must be in the reply: {reply!r}"
        )


# --------------------------------------------------------------------------- #
# AC-1130 - bare "outstanding" + the SO key arms the scope question, no fetch
# --------------------------------------------------------------------------- #


class TestBareOutstandingWithKeyArmsScopeQuestion:
    def test_bare_outstanding_with_key_arms_scope_question(self, session_factory, monkeypatch) -> None:
        _seed_contact(session_factory, variables={})
        result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(order_status="outstanding"),
            text_body="SRTWT7445 outstanding",
            msg_id="ZZT-outstanding-scope-ask-1",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
        )
        assert captured == [], (
            f"no report/order tool may be called while the scope question is open: {captured}"
        )
        reply = (result.reply or {}).get("text") or ""
        assert "Outstanding for which document?" in reply, reply
        assert "1. Sales orders (not yet transferred to DO)" in reply, reply
        assert "2. Delivery orders (not yet delivered)" in reply, reply
        assert "3. Both" in reply, reply

        stored = _session_of(session_factory)["variables"]
        assert stored.get("selection_context") == "outstanding_scope", stored.get("selection_context")
        assert (stored.get("pending") or {}).get("kind") == "outstanding_scope", stored.get("pending")
        assert len(stored.get("last_result_set") or []) == 3, stored.get("last_result_set")
        assert stored.get("outstanding_filters", {}).get("product_code") == PRODUCT_CODE, (
            stored.get("outstanding_filters")
        )


# --------------------------------------------------------------------------- #
# AC-1132 - the scope answer restores the filters and runs the report
# --------------------------------------------------------------------------- #


def _seed_open_outstanding_scope(session_factory, *, filters: dict[str, Any] | None = None) -> None:
    _seed_contact(
        session_factory,
        variables={
            "message_type": "business_query",
            "domain_hint": "order",
            "entities": [],
            "selection_context": "outstanding_scope",
            "last_result_set": [
                {"idx": 1, "label": "Sales orders", "value": "so"},
                {"idx": 2, "label": "Delivery orders", "value": "do"},
                {"idx": 3, "label": "Both", "value": "both"},
            ],
            "outstanding_filters": filters
            or {
                "product_code": PRODUCT_CODE,
                "date_filter_start": None,
                "date_filter_end": None,
                "customer_ids": [CUSTOMER_UUID],
                "warehouse_codes": ["ZZT-BRW-IB"],
            },
            "pending": {"kind": "outstanding_scope"},
        },
    )


class TestScopeAnswerRunsReportWithCarriedFilters:
    def test_reply_2_picks_do_scope_and_restores_filters(self, session_factory, monkeypatch) -> None:
        _seed_open_outstanding_scope(session_factory)
        _result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="casual", intent_hint=None, domain_hint=None, entities=[],
                reference_positions=[2],
            ),
            text_body="2",
            msg_id="ZZT-outstanding-scope-answer-2",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_HIT,
        )
        assert captured, "the scope answer must run the report in the SAME turn (no re-parse)"
        name, args = captured[0]
        assert name == "crm_outstanding_report", name
        assert args.get("scope") == "do", f"'2' must resolve to scope=do: {args}"
        assert args.get("product_code") == PRODUCT_CODE, (
            f"the carried product_code must be restored, not re-parsed: {args}"
        )
        assert args.get("customer_ids") == [CUSTOMER_UUID], (
            f"the carried customer_ids must be restored: {args}"
        )

    def test_out_of_range_number_reasks(self, session_factory, monkeypatch) -> None:
        _seed_open_outstanding_scope(session_factory)
        result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="casual", intent_hint=None, domain_hint=None, entities=[],
                reference_positions=[9],
            ),
            text_body="9",
            msg_id="ZZT-outstanding-scope-oor-1",
            attributes=["sales_orders.outstanding"],
        )
        assert captured == [], f"an out-of-range pick must not run any report: {captured}"
        reply = (result.reply or {}).get("text") or ""
        assert "Outstanding for which document?" in reply, (
            f"an out-of-range pick must re-ask the same scope question: {reply!r}"
        )


# --------------------------------------------------------------------------- #
# AC-1135 - a hit arms the detail offer and suppresses the escalate offer
# --------------------------------------------------------------------------- #


class TestHitArmsOutstandingDetailAndNoEscalateOffer:
    def test_hit_arms_detail_offer_and_no_escalate_text(self, session_factory, monkeypatch) -> None:
        _seed_contact(session_factory, variables={})
        result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(order_status="so_outstanding"),
            text_body="SRTWT7445 sales order outstanding",
            msg_id="ZZT-outstanding-hit-1",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_HIT,
        )
        assert captured, "the SO report must be fetched"
        reply = (result.reply or {}).get("text") or ""
        assert reply.strip(), "a hit must produce a non-empty reply"
        assert "would you like me to escalate" not in reply.lower(), (
            f"a hit must never also offer to escalate: {reply!r}"
        )
        stored = _session_of(session_factory)["variables"]
        assert (stored.get("pending") or {}).get("kind") == "outstanding_detail", stored.get("pending")
        assert stored.get("selection_context") == "outstanding_detail", stored.get("selection_context")
        labels = {row.get("label") for row in (stored.get("last_result_set") or [])}
        assert "Sales order list" in labels, (
            f"only the SO scope was requested/present, so only its option is offered: {labels}"
        )


# --------------------------------------------------------------------------- #
# AC-1138 - the detail pick re-runs the SAME tool with detail=so|do
# --------------------------------------------------------------------------- #


def _seed_open_outstanding_detail(session_factory) -> None:
    _seed_contact(
        session_factory,
        variables={
            "message_type": "business_query",
            "domain_hint": "order",
            "entities": [],
            "selection_context": "outstanding_detail",
            "last_result_set": [
                {"idx": 1, "label": "Sales order list", "value": "so"},
                {"idx": 2, "label": "Delivery order list", "value": "do"},
            ],
            "outstanding_filters": {
                "product_code": PRODUCT_CODE,
                "date_filter_start": None,
                "date_filter_end": None,
                "customer_ids": [],
                "warehouse_codes": [],
            },
            "pending": {"kind": "outstanding_detail"},
        },
    )


class TestDetailPickRerunsToolWithDetail:
    def test_reply_1_reruns_with_detail_so(self, session_factory, monkeypatch) -> None:
        _seed_open_outstanding_detail(session_factory)
        _result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="casual", intent_hint=None, domain_hint=None, entities=[],
                reference_positions=[1],
            ),
            text_body="1",
            msg_id="ZZT-outstanding-detail-pick-1",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_HIT,
        )
        assert captured, "the detail pick must re-run the tool, not read a cached list"
        name, args = captured[0]
        assert name == "crm_outstanding_report", name
        assert args.get("detail") == "so", f"'1' must ask for the SO detail: {args}"
        assert args.get("product_code") == PRODUCT_CODE, args

    def test_reply_2_reruns_with_detail_do(self, session_factory, monkeypatch) -> None:
        _seed_open_outstanding_detail(session_factory)
        _result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="casual", intent_hint=None, domain_hint=None, entities=[],
                reference_positions=[2],
            ),
            text_body="2",
            msg_id="ZZT-outstanding-detail-pick-2",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_HIT,
        )
        assert captured, "the detail pick must re-run the tool"
        _name, args = captured[0]
        assert args.get("detail") == "do", f"'2' must ask for the DO detail: {args}"

    def test_a_new_product_code_drops_the_pending(self, session_factory, monkeypatch) -> None:
        _seed_open_outstanding_detail(session_factory)
        other_uuid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        _result, _captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(order_status=None, entities=[
                {"raw": "SRTWC999", "hint": "product", "canonical_code": None, "current_message": True, "confident": True},
            ]),
            text_body="SRTWC999",
            msg_id="ZZT-outstanding-detail-new-code-1",
            attributes=["sales_orders.outstanding"],
            matches={"SRTWC999": {"uuid": other_uuid, "entity_type": "product", "canonical_code": "SRTWC999"}},
        )
        stored = _session_of(session_factory)["variables"]
        assert (stored.get("pending") or {}).get("kind") != "outstanding_detail", (
            f"a new product code must drop the outstanding_detail pending, not answer it: {stored.get('pending')!r}"
        )
