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

import copy
import json
import sys
import uuid
from pathlib import Path
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
from app.services.company_scope import DEFAULT_COMPANY_ID
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


def _present_response():
    """The REAL MCP presenter, imported the way
    `tests/chatbot/test_field_reveal_keys_pinned_to_catalog.py` imports the catalogue:
    append the `sorento_crm_mcp` that sits beside THIS checkout's backend, so a stale
    editable install in the shared venv cannot win (the "lane backend imports primary
    MCP catalog" gotcha). Skipped, never failed, where the package is absent - the
    backend container legitimately does not carry it."""
    repo_root = Path(__file__).resolve().parents[3]
    mcp_root = repo_root / "sorento_crm_mcp"
    if str(mcp_root) not in sys.path:
        sys.path.append(str(mcp_root))
    try:
        from sorento_crm_mcp.presenters import present_response
    except ImportError:  # pragma: no cover - only where the package is not on disk
        pytest.skip("sorento_crm_mcp is not importable in this environment")
    return present_response


def _report_route_body(report: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """The body `GET /api/v1/order-management/outstanding-report` returns for `args`.

    The route drops the block of a scope that was not asked (AC-1117), and ECHOES the
    caller's own `warehouse_codes` / `location_token` / `so_refused` / `detail` onto the
    body so the presenter can render the header, the refusal line and the detail swap
    from the response alone. Reproduced here rather than hand-writing a fixture per
    test, so this double stays the route's shape as the route grows."""
    body = copy.deepcopy(report)
    scope = str(args.get("scope") or "both")
    if scope not in ("so", "both"):
        body.pop("so", None)
        body["so_by_location"] = []
        body["so_by_customer"] = []
        body["so_rows"] = []
    if scope not in ("do", "both"):
        body.pop("do", None)
        body["do_by_location"] = []
        body["do_by_customer"] = []
        body["do_rows"] = []
    body["warehouse_codes"] = list(args.get("warehouse_codes") or [])
    body["location_token"] = args.get("location_token")
    body["so_refused"] = bool(args.get("so_refused"))
    if args.get("detail") in ("so", "do"):
        body["detail"] = args["detail"]
    return body


def _capturing_mcp(response: Any = None):
    """A fake `mcp_call(name, args)`. `captured` records every `(name, args)` call; a test
    asserting "no tool call happened" reads `captured == []`.

    **The production path, not a shortcut** (review S4/S5, 13 Sep 2026): the lane always
    sends `view=render` (`fetch.entity_ids_transformer`), so what comes back from
    `crm_outstanding_report` is what `sorento_crm_mcp.presenters.present_response`
    rendered from the route body - never the route body itself. A double that handed the
    lane a dict fed the reply composer a shape production never produces, and that is
    what hid six user-visible defects behind 33 green tests. So a dict `response` here is
    treated as the ROUTE's payload and pushed through the real presenter; a string is
    returned verbatim (a caller that wants to pin an exact rendering)."""
    captured: list[tuple[str, dict[str, Any]]] = []

    def _call(name: str, args: dict[str, Any]) -> Any:
        captured.append((name, dict(args)))
        if response is None:
            return json.dumps({"has_result": False, "items": []})
        if isinstance(response, str):
            return response
        if name == "crm_outstanding_report":
            return _present_response()(name, json.dumps(_report_route_body(response, args)))
        return json.dumps(response)

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


#: `_run_turn` monkeypatches `engine_mod.default_space_id` to this literal, and
#: `_contact_company_scope` resolves the company scope from `(contact_respond_id,
#: default_space_id(db))` - `resolve_contact_id`'s Respond.io-id branch JOINS
#: `respond_workspaces` on `space_id` when one is given, so the seeded workspace
#: below must carry this SAME value or the join (and so the scope) finds nothing.
_SPACE_ID = "364817"


def _seed_contact(session_factory, *, variables: dict[str, Any]) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_workspaces (id, space_id, name, api_key_ciphertext) "
            "VALUES (gen_random_uuid(), :sid, 'ZZT outstanding-report workspace', 'ZZT-cipher') "
            "ON CONFLICT DO NOTHING"
        ),
        {"sid": _SPACE_ID},
    )
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, workspace_id) "
            "VALUES ("
            "  gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb),"
            "  (SELECT id FROM respond_workspaces WHERE space_id = :sid LIMIT 1)"
            ")"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000009", "sv": json.dumps({"variables": variables}), "sid": _SPACE_ID},
    )
    # S1 (security review, 13 Sep 2026): bound to Sorento so a REAL company-scoped
    # DB read this contact's turn makes (`crm_outstanding_report`'s warehouse
    # lookup, AC-1133's pipeline half - `resolve_warehouse_token` reads on the
    # engine's own per-contact-scoped session, same as every other owned read the
    # turn makes) sees the SAME company `TestLocationTokenPipeline`'s own seeded
    # warehouses land in. A contact with no `respond_contact_companies` row
    # legitimately resolves to zero owned rows everywhere (AC-F3, fail-closed) -
    # every OTHER test in this file never exercises a real DB read on this
    # contact's session at all, so this insert is a no-op for them.
    db.execute(
        text(
            "INSERT INTO respond_contact_companies (id, respond_contact_id, company_id) "
            "SELECT gen_random_uuid(), id, :company_id FROM respond_contacts WHERE respond_io_id = :cid"
        ),
        {"cid": CONTACT_ID, "company_id": DEFAULT_COMPANY_ID},
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


#: The ROUTE's own body for a product that HAS both an SO backlog and a DO pending
#: (the shape `OutstandingReportResponse` declares). `_capturing_mcp` renders it through
#: the real presenter and drops the block of whichever scope was not asked, exactly as
#: the route does - so a `scope=so` turn in a test sees the same one-block report a
#: `scope=so` turn sees in production.
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
    "do": {
        "do_qty": 12, "delivered_qty": 5, "pending_qty": 7, "do_count": 1,
        "do_date_min": "2026-02-03", "do_date_max": "2026-02-03",
    },
    "so_by_location": [{"code": "BRW-IB", "ordered_qty": 10, "outstanding_qty": 7}],
    "so_by_customer": [{"customer_name": CUSTOMER_NAME, "ordered_qty": 10, "outstanding_qty": 7}],
    "do_by_location": [{"code": "BRW-IB", "do_qty": 12, "pending_qty": 7}],
    "do_by_customer": [{"customer_name": CUSTOMER_NAME, "do_qty": 12, "pending_qty": 7}],
    "so_rows": [
        {
            "so_number": "SO1", "customer_name": CUSTOMER_NAME, "location": "BRW-IB",
            "ordered_qty": 10, "transferred_qty": 3, "outstanding_qty": 7, "order_date": "2026-01-01",
        }
    ],
    "do_rows": [
        {
            "do_number": "DO1", "customer_name": CUSTOMER_NAME, "location": "BRW-IB",
            "do_qty": 12, "delivered_qty": 5, "pending_qty": 7, "do_date": "2026-02-03",
        }
    ],
}

#: The same body for a product with NOTHING open on either side (AC-1107): both blocks
#: present, every count zero - the route's answer to a real miss, not an error.
REPORT_MISS = {
    **REPORT_HIT,
    "so": {
        "ordered_qty": 0, "transferred_qty": 0, "outstanding_qty": 0, "so_count": 0,
        "order_date_min": None, "order_date_max": None,
    },
    "do": {
        "do_qty": 0, "delivered_qty": 0, "pending_qty": 0, "do_count": 0,
        "do_date_min": None, "do_date_max": None,
    },
    "so_by_location": [], "so_by_customer": [], "do_by_location": [], "do_by_customer": [],
    "so_rows": [], "do_rows": [],
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
# S4 point 7 - a warehouse entity on a PLAIN order ask (no outstanding word)
# --------------------------------------------------------------------------- #


class TestWarehouseOnAPlainOrderAsk:
    def test_warehouse_entity_becomes_warehouse_codes_on_the_order_list(
        self, session_factory
    ) -> None:
        """`ALLOWED["order"]` admits a warehouse entity (S4 point 7), and
        `TYPE_TO_PARAM` maps it to `warehouse_ids` - which neither order-list tool
        declares, so the MCP dropped it silently and the answer was presented as though
        it had been scoped to that warehouse. Both tools DO take `warehouse_codes`
        (S3), so the resolved code is what travels."""
        from app.services.chatbot.lanes.business import run_fetch

        call, captured = _capturing_mcp({"data": [], "has_result": False})
        payload = {
            "gate": {
                "compatible_entities": [
                    {"uuid": PRODUCT_UUID, "entity_type": "product", "code": PRODUCT_CODE},
                    {
                        "uuid": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                        "entity_type": "warehouse",
                        "code": "BRW",
                    },
                ]
            },
            "tier_gate": None,
            "ctx": {
                "parse": {"output": _qf(order_status=None, entities=[])},
                "contact": {"id": CONTACT_ID},
                "access": {"attributes": []},
            },
        }
        run_fetch(payload, services=FetchServices(mcp_call=call))
        assert captured, "no MCP tool was ever called"
        name, args = captured[0]
        assert name == "crm_order_management_orders_list", name
        assert args.get("warehouse_codes") == ["BRW"], (
            f"the resolved warehouse must reach the order list as warehouse_codes: {args}"
        )
        assert "warehouse_ids" not in args, (
            f"warehouse_ids is not a param either order-list tool declares - sending it "
            f"is a silent drop, and the answer then claims a scope it never had: {args}"
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
        # AC-1141 / S4 point 11 (review round, 13 Sep 2026): PLACEMENT, not mere
        # presence. The line belongs AFTER the four header lines and BEFORE the DO
        # block - opening the whole reply with it reads as a refusal of the question
        # the customer asked, rather than a note about the half that is withheld.
        lines = reply.splitlines()
        refusal_at = lines.index("Sales order figures are not enabled for your account.")
        header_at = [i for i, line in enumerate(lines) if line.startswith("Order date:")]
        do_block_at = [i for i, line in enumerate(lines) if line == "*Delivery order pending*"]
        assert header_at and refusal_at > header_at[0], (
            f"the refusal must come after the header's four lines: {reply!r}"
        )
        assert do_block_at and refusal_at < do_block_at[0], (
            f"the refusal must come before the Delivery order pending block: {reply!r}"
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

    def test_a_new_bare_outstanding_ask_after_a_hit_asks_the_scope_question(
        self, session_factory, monkeypatch
    ) -> None:
        """D2 one-turn life, console run 3 (13 Sep 2026): a report HIT leaves
        `pending.kind = "outstanding_detail"` for the next turn's "1"/"2". A LATER bare
        "outstanding" ask is a NEW ask, not an answer to that offer, so it must ask the
        scope question - it ran the full report instead, because the stale pending
        suppressed the scope-ask signal. Resetting the session made the question fire,
        which is what named the pending as the cause."""
        _seed_contact(session_factory, variables={})
        _r1, captured1 = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(order_status="so_outstanding"),
            text_body="SRTWT7445 sales order outstanding",
            msg_id="ZZT-outstanding-stale-pending-1",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_HIT,
        )
        assert captured1 and captured1[0][0] == "crm_outstanding_report", captured1
        assert (_session_of(session_factory)["variables"].get("pending") or {}).get(
            "kind"
        ) == "outstanding_detail"

        result, captured2 = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(order_status="outstanding"),
            text_body="SRTWT7445 outstanding",
            msg_id="ZZT-outstanding-stale-pending-2",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_HIT,
        )
        assert captured2 == [], (
            f"a new bare-word ask must ask the scope question first, not fetch: {captured2}"
        )
        reply = (result.reply or {}).get("text") or ""
        assert "Outstanding for which document?" in reply, reply
        stored = _session_of(session_factory)["variables"]
        assert (stored.get("pending") or {}).get("kind") == "outstanding_scope", stored.get("pending")


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
                "warehouse_codes": ["ZZT-BRW-IB", "ZZT-MWH-IB"],
                "location_token": "IB",
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
        # AC-1132 / AC-1138 (review round, 13 Sep 2026): the LOCATION is part of the
        # filter set. Dropping it re-ran the report over every warehouse and printed
        # `Location: all` under a question the customer asked about one location, so
        # the answering turn quietly answered a wider question than the one asked.
        assert args.get("warehouse_codes") == ["ZZT-BRW-IB", "ZZT-MWH-IB"], (
            f"the carried warehouse_codes must be restored: {args}"
        )
        assert args.get("location_token") == "IB", (
            f"the carried location token must be restored so the header still echoes it: {args}"
        )
        reply = (_result.reply or {}).get("text") or ""
        assert "Location: IB (ZZT-BRW-IB, ZZT-MWH-IB)" in reply, (
            f"the answering turn must print the SAME location header as the asking turn: {reply!r}"
        )

    def test_a_new_ask_during_the_scope_question_is_not_hijacked(
        self, session_factory, monkeypatch
    ) -> None:
        """D2's one-turn life, review round 13 Sep 2026: a message that brings its OWN
        question - a domain word, or a new product code - is a NEW ASK while an
        `outstanding_scope` question is open. The carve-out existed for
        `outstanding_detail` only, so "stock for SRTWC8517" was rewritten into the
        carried outstanding ask and answered with the scope question AGAIN: the customer
        could not leave the question except by answering it."""
        _seed_open_outstanding_scope(session_factory)
        other_uuid = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
        result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[
                    {
                        "raw": "SRTWC8517", "hint": "product", "canonical_code": None,
                        "current_message": True, "confident": True,
                    },
                ],
            ),
            text_body="stock for SRTWC8517",
            msg_id="ZZT-outstanding-scope-hijack-1",
            attributes=["sales_orders.outstanding"],
            matches={"SRTWC8517": {"uuid": other_uuid, "entity_type": "product", "canonical_code": "SRTWC8517"}},
            mcp_response={
                "items": [
                    {
                        "title": "SRTWC8517",
                        "fields": [{"key": "product_code", "label": "Product", "value": "SRTWC8517"}],
                    }
                ],
                "has_result": True,
                "intro": "Here are the results.",
            },
        )
        assert captured, "the new ask must be answered, not swallowed by the open question"
        name, _args = captured[0]
        assert name != "crm_outstanding_report", (
            f"a stock ask must not be rewritten into the carried outstanding ask: {name}"
        )
        reply = (result.reply or {}).get("text") or ""
        assert "Outstanding for which document?" not in reply, (
            f"the open scope question must be DROPPED by a new ask, never re-asked: {reply!r}"
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


    def test_report_skips_search_scope_header(self, session_factory, monkeypatch) -> None:
        """AC-1139 / S4 point 10 (never written until the review round): the generic
        delivery-order search-scope header ("Customer: ... / Product: ... / Dates: ...")
        must NOT print above a report that carries its own Product / Customer / Location
        / Order date lines. The console check read both, one under the other."""
        _seed_contact(session_factory, variables={})
        result, _captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(order_status="so_outstanding"),
            text_body="SRTWT7445 sales order outstanding",
            msg_id="ZZT-outstanding-header-skip-1",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_HIT,
        )
        reply = (result.reply or {}).get("text") or ""
        assert reply.startswith(f"Product: {PRODUCT_CODE}"), (
            f"the report's own header must be the first thing in the reply: {reply!r}"
        )
        assert "Dates: all dates" not in reply, (
            f"the generic search-scope header must not print above the report: {reply!r}"
        )
        assert "Customer: all customers" not in reply, (
            f"the generic search-scope header must not print above the report: {reply!r}"
        )

    def test_scope_question_skips_search_scope_header(self, session_factory, monkeypatch) -> None:
        """The same on the ASKING turn (the journey says the question carries nothing
        else): the scope question is three lines and a product, not a search summary."""
        _seed_contact(session_factory, variables={})
        result, _captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(order_status="outstanding"),
            text_body="SRTWT7445 outstanding",
            msg_id="ZZT-outstanding-header-skip-2",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
        )
        reply = (result.reply or {}).get("text") or ""
        assert reply.startswith(f"Product: {PRODUCT_CODE}"), reply
        assert "Dates: all dates" not in reply, (
            f"the scope question must carry nothing but itself: {reply!r}"
        )


# --------------------------------------------------------------------------- #
# AC-1107 - a TOTAL miss escalates, on the rendered-text path
# --------------------------------------------------------------------------- #


class TestTotalMissEscalates:
    def test_empty_report_offers_the_escalation(self, session_factory, monkeypatch) -> None:
        """AC-1107: both requested scopes empty is an ABSENCE, so the existing escalate
        offer + team picker follow. On the rendered path the reply text is never empty
        (the header always renders), so `has_result` cannot be read off the text - the
        presenter's envelope has to carry it, or every miss reads as a hit and the
        customer is left with "No open sales order." and no way forward."""
        _seed_contact(session_factory, variables={})
        result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(order_status="outstanding_both"),
            text_body="SRTWT7445 outstanding both",
            msg_id="ZZT-outstanding-miss-1",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_MISS,
        )
        assert captured, "the report must still have been fetched"
        reply = (result.reply or {}).get("text") or ""
        assert "escalate" in reply.lower(), (
            f"a total miss must reach the existing escalate offer: {reply!r}"
        )
        stored = _session_of(session_factory)["variables"]
        assert (stored.get("pending") or {}).get("kind") != "outstanding_detail", (
            f"a miss offers no detail list: {stored.get('pending')!r}"
        )

    def test_total_miss_keeps_the_report_block_lines_then_offers_escalation(
        self, session_factory, monkeypatch
    ) -> None:
        """AC-1107 in full (owner's approved miss mock on the lavish page): the reply is
        the REPORT's own header and block lines, then the escalate offer - not the
        generic miss lane's `Customer / Product / Dates` header and "Here's what you
        want" bullets, which say nothing about sales orders or delivery orders and drop
        the two lines the owner signed off on."""
        _seed_contact(session_factory, variables={})
        result, _captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(order_status="outstanding_both"),
            text_body="SRTWT7445 outstanding both",
            msg_id="ZZT-outstanding-miss-2",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_MISS,
        )
        reply = (result.reply or {}).get("text") or ""
        assert "*Sales order outstanding*\nNo open sales order." in reply, reply
        assert "*Delivery order pending*\nNo pending delivery order." in reply, reply
        offer_at = reply.index("Would you like me to escalate")
        assert reply.index("No open sales order.") < offer_at, reply
        assert reply.index("No pending delivery order.") < offer_at, reply
        assert reply.startswith(f"Product: {PRODUCT_CODE}"), (
            f"the report's own header opens the miss, not the generic one: {reply!r}"
        )
        assert "Here's what you want:" not in reply, (
            f"the generic miss bullets must not print over the report's own lines: {reply!r}"
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

    def test_a_real_hit_arms_the_pending_and_the_next_1_reruns_with_detail_so(
        self, session_factory, monkeypatch
    ) -> None:
        """AC-1135 + AC-1138 end to end, two turns, no hand-seeded pending (the gap the
        console check found): turn 1 is a genuine report hit, turn 2 is "1". The
        previously-passing pair seeded `pending.kind = outstanding_detail` directly, so
        a hit that never armed it still looked green."""
        _seed_contact(session_factory, variables={})
        _result1, captured1 = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(order_status="outstanding_both"),
            text_body="SRTWT7445 outstanding both",
            msg_id="ZZT-outstanding-live-hit-1",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_HIT,
        )
        assert captured1 and captured1[0][0] == "crm_outstanding_report", captured1
        stored = _session_of(session_factory)["variables"]
        assert (stored.get("pending") or {}).get("kind") == "outstanding_detail", (
            f"a real hit must arm the detail pending the next turn reads: {stored.get('pending')!r}"
        )
        assert stored.get("outstanding_filters", {}).get("product_code") == PRODUCT_CODE, (
            f"the hit must carry its own filters forward: {stored.get('outstanding_filters')!r}"
        )

        _result2, captured2 = _run_turn(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="casual", intent_hint=None, domain_hint=None, entities=[],
                reference_positions=[1],
            ),
            text_body="1",
            msg_id="ZZT-outstanding-live-hit-2",
            attributes=["sales_orders.outstanding"],
            matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}},
            mcp_response=REPORT_HIT,
        )
        assert captured2, "the detail pick must re-run the tool"
        name, args = captured2[0]
        assert name == "crm_outstanding_report", name
        assert args.get("detail") == "so", f"'1' must ask for the SO detail: {args}"
        reply = (_result2.reply or {}).get("text") or ""
        assert "*SO Number:* SO1" in reply, (
            f"the reply must be the numbered SO detail list (AC-1106): {reply!r}"
        )

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


# --------------------------------------------------------------------------- #
# S2 (security review, 13 Sep 2026) - the legacy so_outstanding bucket, gated
# --------------------------------------------------------------------------- #


class TestNoSoKeyCustomerOnlySoAskFallsToDoBucket:
    """A customer-only ask ("outstanding SO for Dealer A", no product) never reaches
    the outstanding-report override above (it requires a resolved product) and picks
    the LEGACY `crm_order_management_orders_list?order_status=so_outstanding` bucket
    instead - the SAME per-SO outstanding quantities D13 gates on `crm_outstanding_
    report`. Without `sales_orders.outstanding`, the lane must redirect to
    `order_status=outstanding` (the DO bucket), never call the SO bucket, strip
    `include_pipeline`, and prefix the reply."""

    def test_no_so_key_customer_only_so_ask_falls_to_do_bucket(self, session_factory, monkeypatch) -> None:
        _seed_contact(session_factory, variables={})
        result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(
                order_status="so_outstanding",
                requested_attributes=["quantity"],
                entities=[
                    {
                        "raw": CUSTOMER_NAME, "hint": "customer", "canonical_code": None,
                        "current_message": True, "confident": True,
                    },
                ],
            ),
            text_body="outstanding SO for Dealer A",
            msg_id="ZZT-so-bucket-gate-1",
            attributes=[],
            matches={CUSTOMER_NAME: {"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME}},
            mcp_response={
                "items": [{"title": "DO1", "fields": [{"key": "do_number", "label": "DO Number", "value": "DO1"}]}],
                "has_result": True,
                "intro": "Here are the results.",
            },
        )
        assert captured, "the DO bucket must still be fetched, never nothing"
        name, args = captured[0]
        assert name == "crm_order_management_orders_list", name
        assert args.get("order_status") == "outstanding", (
            f"without the grant, so_outstanding must redirect to the DO bucket: {args}"
        )
        assert "include_pipeline" not in args, (
            f"include_pipeline (carries so_outstanding_qty) must be stripped: {args}"
        )
        reply = (result.reply or {}).get("text") or ""
        assert "Sales order figures are not enabled for your account." in reply, reply

    def test_with_the_grant_the_so_bucket_runs_unredirected(self, session_factory, monkeypatch) -> None:
        """The grant is the ONLY thing the gate reads - same ask, held key, no redirect."""
        _seed_contact(session_factory, variables={})
        _result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(
                order_status="so_outstanding",
                entities=[
                    {
                        "raw": CUSTOMER_NAME, "hint": "customer", "canonical_code": None,
                        "current_message": True, "confident": True,
                    },
                ],
            ),
            text_body="outstanding SO for Dealer A",
            msg_id="ZZT-so-bucket-gate-2",
            attributes=["sales_orders.outstanding"],
            matches={CUSTOMER_NAME: {"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": CUSTOMER_NAME}},
            mcp_response={"data": [], "has_result": False},
        )
        assert captured, "the SO bucket must still be fetched"
        name, args = captured[0]
        assert name == "crm_order_management_orders_list", name
        assert args.get("order_status") == "so_outstanding", (
            f"with the grant, so_outstanding must reach the tool unredirected: {args}"
        )


# --------------------------------------------------------------------------- #
# N4 (security review, 13 Sep 2026) - outstanding_filters does not outlive its turn
# --------------------------------------------------------------------------- #


class TestOutstandingFiltersDoNotOutliveTheAnsweringTurn:
    def test_a_later_unrelated_turn_clears_outstanding_filters(self, session_factory, monkeypatch) -> None:
        """`outstanding_filters` used to fall back to `prev.outstanding_filters`
        unconditionally whenever this turn armed no NEW outstanding ask - so a scope
        or detail ask that MISSED (no `outstanding_ask` re-armed) left the customer's
        resolved product/customer/location sitting in session state forever, since
        nothing ever wrote over or cleared it again. `pending` for
        `outstanding_scope`/`outstanding_detail` is already one-turn-life
        (`compile_state._offer_carry`'s own exclusion); `outstanding_filters` must
        share that lifetime - carried only across the ONE turn that answers an open
        ask, gone on any turn after."""
        _seed_contact(
            session_factory,
            variables={
                "outstanding_filters": {
                    "product_code": PRODUCT_CODE, "date_filter_start": None, "date_filter_end": None,
                    "customer_ids": [], "warehouse_codes": [],
                },
                # The answering turn already ran and moved on - no open outstanding
                # ask survives it, same as after any other one-turn pending.
                "pending": None,
                "selection_context": None,
            },
        )
        other_uuid = "dddddddd-dddd-dddd-dddd-dddddddddddd"
        _run_turn(
            session_factory,
            monkeypatch,
            qf=_qf(
                order_status=None,
                entities=[
                    {
                        "raw": "SRTWC999", "hint": "product", "canonical_code": None,
                        "current_message": True, "confident": True,
                    },
                ],
            ),
            text_body="stock for SRTWC999",
            msg_id="ZZT-outstanding-filters-clear-1",
            matches={"SRTWC999": {"uuid": other_uuid, "entity_type": "product", "canonical_code": "SRTWC999"}},
            mcp_response={
                "items": [{"title": "SRTWC999", "fields": [{"key": "product_code", "label": "Product", "value": "SRTWC999"}]}],
                "has_result": True,
                "intro": "Here are the results.",
            },
        )
        stored = _session_of(session_factory)["variables"]
        assert "outstanding_filters" not in stored, (
            f"outstanding_filters must not survive past the one turn that answers "
            f"an open scope/detail ask: {stored}"
        )
