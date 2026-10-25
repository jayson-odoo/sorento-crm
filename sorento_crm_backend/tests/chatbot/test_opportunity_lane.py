"""Phase 2 RED tests - log a sales opportunity over the chat (lane SALES-TARGET-CHAT, slice 2).

`documentation/plans/sales/sales-opportunity-chat-25oct-acceptance-criteria.md` O6-1 to O6-11 and
O4-2, and PLAN-sales-opportunity-chat-25oct.md "Design (fixed for the tests)": MCP and Chat lane.
Written BEFORE any wiring exists.

Every engine test drives the REAL `engine.run_turn` (the harness `test_outstanding_lane._run_turn`
builds: business lane on, access, resolver and the business fetch faked), with:

* the parser verdict faked per turn (`order_status` "log_opportunity", the flag-gated `opportunity`
  key {title, amount_rm, close_date}, customer entities, `open_question_answer` for a slot answer,
  a pick or a yes / no, `reference_positions` for "2");
* the lane's own MCP seam faked: `app.services.chatbot.lanes.opportunity.call_opportunity_tool(
  tool_name, arguments) -> dict`, mirroring `lanes/ideate.call_ideation_tool`. The lane calls it
  through its module global (as ideate does), so a monkeypatch on the module wins. It returns
  the decoded tool result; a non-2xx route answer is the MCP `http_error_body` dict (the route's
  AppException body - `message`, `detail`, `code` - plus `status_code`, `error`, `http_error`,
  `path`, `method`), the shape a non-presenter tool hands back.

Multi-turn tests run consecutive turns for the SAME contact, so the required-fields slot and the
yes/no read-back persist in `respond_contacts.session_vars` exactly as they do live. The dry-run
test carries state the way the console does (`session_patch` -> `previous_conversation_state`).

Postgres only (`session_factory`, a blank schema). Every row seeded here.
"""
from __future__ import annotations

import dataclasses
import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_chat_report_asker_revoke import _sales_agent_link, _salesperson_user
from tests.chatbot.test_customer_scope_lane import OWN_A, _give_access_type, _link_customers
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output
from tests.chatbot.test_outstanding_lane import (
    _SPACE_ID,
    _capturing_mcp,
    _enable_business_lane,
    _resolve_services,
    _seed_contact,
    _session_of,
    _wire_business_services,
)
from tests.chatbot.test_sales_domain_routing import _normalised

OPTIONS_TOOL = "crm_sales_opportunity_customer_options"
LOG_TOOL = "crm_sales_opportunity_log"
LANE_MODULE = "app.services.chatbot.lanes.opportunity"
SEAM = "call_opportunity_tool"

#: The prompt line that switches the parser key on (plan "Parser"). The stub config carries it.
OPPORTUNITY_LINE = '== LOG OPPORTUNITY: order_status "log_opportunity", domain_hint "order" =='

# The plan's exact lines.
NOT_SALESPERSON = "Logging an opportunity is for salespeople only."
NOT_ENABLED = "Logging an opportunity is not enabled for your account."
NOT_YOURS = "That customer is not one of yours."
COULD_NOT_SAVE = "I couldn't save that. Nothing was recorded."
NOT_SAVED = "Not saved."
TEST_RUN = "Test run: nothing was saved."
ASK_CUSTOMER = "Which customer is it for?"
ASK_TITLE = "What is the opportunity? A short title, please."
ASK_AMOUNT = "What is the expected amount in RM?"
ASK_CLOSE = "When do you expect it to close?"

BATH = {
    "customer_id": "0b5e0f5a-1111-4c1a-9a11-000000000001",
    "code": "300-B0001",
    "name": "BATH IDEA BATHROOM & KITCHEN MARKETING SDN BHD",
    "label": "A/C I",
}
BKIN_I = {
    "customer_id": "0b5e0f5a-2222-4c1a-9a11-000000000002",
    "code": "300-B0101",
    "name": "BKIN ELECTRICAL SDN BHD",
    "label": "A/C I",
}
BKIN_III = {
    "customer_id": "0b5e0f5a-3333-4c1a-9a11-000000000003",
    "code": "300-B0103",
    "name": "BKIN ELECTRICAL SDN BHD",
    "label": "A/C III",
}

READ_BACK = [
    "Save this opportunity?",
    "Customer: BATH IDEA BATHROOM & KITCHEN MARKETING SDN BHD [A/C I]",
    "Title: condo job Taman X",
    "Amount: RM 40,000.00",
    "Close by: 15 Dec 2026",
    "Reply YES to save.",
]

PIPELINE = {"target_end_date": "2026-12-31", "pipeline_value": "40000.00"}


# --------------------------------------------------------------------------- #
# Verdicts (what the parser emits under the B4 test-copy prompt)
# --------------------------------------------------------------------------- #


def _no_answer() -> dict[str, Any]:
    return {"mode": None, "picked": [], "items": [], "qty_for_all": None}


def _answer(mode: str, picked: list[int] | None = None) -> dict[str, Any]:
    return {"mode": mode, "picked": list(picked or []), "items": [], "qty_for_all": None}


def _customer(raw: str) -> dict[str, Any]:
    return {"raw": raw, "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}


def _opp(title: str | None = None, amount: float | None = None, close: str | None = None) -> dict[str, Any]:
    return {"title": title, "amount_rm": amount, "close_date": close}


def _log(
    *,
    customer: str | None = None,
    title: str | None = None,
    amount: float | None = None,
    close: str | None = None,
    answer: dict[str, Any] | None = None,
    positions: list[int] | None = None,
) -> dict[str, Any]:
    """A "log_opportunity" turn: a new ask (answer None) or an answer to the open slot."""
    return _parser_output(
        message_type="business_query",
        domain_hint="order",
        intent_hint="check_order",
        order_status="log_opportunity",
        entities=[_customer(customer)] if customer else [],
        opportunity=_opp(title, amount, close),
        open_question_answer=answer or _no_answer(),
        reference_positions=list(positions or []),
    )


def _all_four() -> dict[str, Any]:
    """"log an opportunity: Bath Idea, condo job Taman X, RM 40k, closing mid Dec"."""
    return _log(customer="Bath Idea", title="condo job Taman X", amount=40000, close="2026-12-15")


def _yes() -> dict[str, Any]:
    """A bare "yes" to the read-back: the open question's yes answer, never a new ask."""
    return _parser_output(
        message_type="casual",
        domain_hint=None,
        intent_hint=None,
        entities=[],
        is_affirmative=True,
        opportunity=_opp(),
        open_question_answer=_answer("yes"),
    )


def _no(mode: str = "no") -> dict[str, Any]:
    return _parser_output(
        message_type="casual",
        domain_hint=None,
        intent_hint=None,
        entities=[],
        is_affirmative=False if mode == "no" else None,
        opportunity=_opp(),
        open_question_answer=_answer(mode),
    )


# --------------------------------------------------------------------------- #
# The lane's MCP seam, faked
# --------------------------------------------------------------------------- #


def _route_error(status: int, code: str | None, *, tool: str) -> dict[str, Any]:
    """What the MCP layer hands back for a non-2xx route answer (`http_client.http_error_body`
    over the route's AppException body)."""
    path = (
        "/api/v1/external/sales-opportunities/customer-options"
        if tool == OPTIONS_TOOL
        else "/api/v1/external/sales-opportunities"
    )
    method = "GET" if tool == OPTIONS_TOOL else "POST"
    if code is None:
        body: dict[str, Any] = {"message": "Internal server error"}
        reason = "Internal server error"
    else:
        body = {"message": f"ZZT route refusal {code}", "detail": None, "code": code}
        reason = code
    summary = f"{method} {path} returned HTTP {status}: {reason}"
    return {**body, "error": summary, "http_error": summary, "status_code": status, "path": path, "method": method}


def _saved(*, number: str = "OPP-000123", pipeline: dict[str, Any] | None = PIPELINE, dry_run: bool = False,
           customer: dict[str, Any] | None = BATH, prospect: str | None = None, amount: str = "40000.00") -> dict[str, Any]:
    """The create route's 201 body (plan contract)."""
    return {
        "opportunity_no": None if dry_run else number,
        "stage": "New",
        "customer": None if customer is None else {k: customer[k] for k in ("code", "name", "label")},
        "prospect_name": prospect,
        "title": "condo job Taman X",
        "expected_amount": amount,
        "expected_close_date": "2026-12-15",
        "pipeline": pipeline,
        "dry_run": dry_run,
    }


class _Seam:
    """`call_opportunity_tool(tool_name, arguments)`: records every call, answers per tool.

    `options` maps the lower-cased `q` to the options body (or a route error dict); an unknown
    `q` is a prospect. `log` is the create route's answer (a body or a route error dict)."""

    def __init__(self, *, options: dict[str, Any] | None = None, log: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.options = {k.lower(): v for k, v in (options or {}).items()}
        self.log = log if log is not None else _saved()

    def __call__(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, dict(arguments)))
        if tool_name == OPTIONS_TOOL:
            q = str(arguments.get("q") or "").strip().lower()
            return json.loads(json.dumps(self.options.get(q, {"items": [], "prospect": True, "blocked": False})))
        if tool_name == LOG_TOOL:
            return json.loads(json.dumps(self.log))
        raise AssertionError(f"the opportunity seam was called with an unknown tool {tool_name!r}")

    def named(self, tool: str) -> list[dict[str, Any]]:
        return [args for name, args in self.calls if name == tool]


def _install(monkeypatch, **kw: Any) -> _Seam:
    """Fake the lane's seam. Imports the lane module, so this is the line that is red until the
    lane exists (ModuleNotFoundError: app.services.chatbot.lanes.opportunity)."""
    import importlib

    lane = importlib.import_module(LANE_MODULE)
    seam = _Seam(**kw)
    monkeypatch.setattr(lane, SEAM, seam)
    return seam


def _options(*items: dict[str, Any], prospect: bool = False, blocked: bool = False) -> dict[str, Any]:
    return {"items": [dict(i) for i in items], "prospect": prospect, "blocked": blocked}


# --------------------------------------------------------------------------- #
# Contacts
# --------------------------------------------------------------------------- #


def _salesperson(session_factory) -> None:
    """A salesperson by the one asker rule: an ACTIVE user holding role `salesperson`, linked to
    the contact, plus an active sales agent linked to the contact."""
    _seed_contact(session_factory, variables={})
    _salesperson_user(session_factory)
    _sales_agent_link(session_factory)


def _dealer(session_factory) -> None:
    _seed_contact(session_factory, variables={})
    _link_customers(session_factory, OWN_A)


def _staff(session_factory) -> None:
    _seed_contact(session_factory, variables={})
    _give_access_type(session_factory, "Sorento Office")


def _unlinked(session_factory) -> None:
    _seed_contact(session_factory, variables={})


# --------------------------------------------------------------------------- #
# One real engine turn
# --------------------------------------------------------------------------- #


def _stub_config(db, *, current_date, override_version_id=None):
    config = parser_mod.ParserConfig(
        system_prompt=f"stub\n{OPPORTUNITY_LINE}\n",
        prompt_version=1,
        provider="openai",
        model="gpt-test",
        api_key="sk-test",
    )
    # The flag-gated key: on when the template carries the LOG OPPORTUNITY line. Set when the
    # field exists, so this harness neither depends on it nor breaks once it lands.
    if "opportunity" in {f.name for f in dataclasses.fields(config)}:
        config = dataclasses.replace(config, opportunity=True)
    return config


class _Turn:
    def __init__(self, result: Any, captured: list[tuple[str, dict[str, Any]]]) -> None:
        self.result = result
        self.captured = captured
        self.text = ((result.reply or {}).get("text") or "").strip()
        self.lines = [line.strip() for line in self.text.splitlines() if line.strip()]


def _say(
    session_factory,
    monkeypatch,
    qf: dict[str, Any],
    body: str,
    *,
    attributes: tuple[str, ...] = (),
    mcp_response: Any = None,
    dry_run: bool = False,
    state: dict[str, Any] | None = None,
) -> _Turn:
    """One `engine.run_turn` for the seeded contact. `captured` is the BUSINESS lane's tool calls
    (the opportunity seam records its own). `dry_run` sends a console test turn carrying
    `state` as `previous_conversation_state`, the console's own carry."""
    _enable_business_lane(session_factory)
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True,
            "decision": "allow",
            "agent_name": "General",
            "attributes": list(attributes),
            "all_attributes_allowed": None,
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: _SPACE_ID)
    monkeypatch.setattr(parser_mod, "resolve_config", _stub_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: qf)
    call, captured = _capturing_mcp(mcp_response)
    _wire_business_services(monkeypatch, resolve_services=_resolve_services({}), mcp_call=call)

    overrides: dict[str, Any] = {}
    if dry_run:
        overrides = {"is_test": True, "previous_conversation_state": state}
    envelope = _envelope(**overrides)
    envelope.message["message"]["messageId"] = f"ZZT-opp-{uuid.uuid4().hex[:12]}"
    envelope.message["message"]["message"]["text"] = body
    result = engine_mod.run_turn(envelope, session_factory=session_factory)
    return _Turn(result, captured)


def _assert_payload(args: dict[str, Any], *, customer_id: str | None, title: str, amount: float, close: str,
                    prospect: str | None = None, dry_run: bool = False) -> None:
    assert args.get("contact_id") == str(CONTACT_ID), args
    assert args.get("space_id") == _SPACE_ID, args
    assert args.get("customer_id") == customer_id, args
    assert (args.get("prospect_name") or None) == prospect, args
    assert args.get("title") == title, args
    assert float(args.get("expected_amount")) == float(amount), args
    assert args.get("expected_close_date") == close, args
    assert bool(args.get("dry_run")) is dry_run, args


# --------------------------------------------------------------------------- #
# O6-1 - all four fields in one message: the read-back, no write
# --------------------------------------------------------------------------- #


class TestAllFieldsReadsBack:
    def test_the_status_is_the_sales_domain(self) -> None:
        """Plan: turn_runtime maps `log_opportunity` to the `sales` domain (slice 1 seam)."""
        for prior in ("order", "master_products", None):
            assert _normalised(domain_hint=prior, order_status="log_opportunity")["domain_hint"] == "sales"

    def test_all_fields_reads_back(self, session_factory, monkeypatch) -> None:
        _salesperson(session_factory)
        seam = _install(monkeypatch, options={"Bath Idea": _options(BATH)})

        turn = _say(
            session_factory, monkeypatch, _all_four(),
            "log an opportunity: Bath Idea, condo job Taman X, RM 40k, closing mid Dec",
        )

        assert turn.result.error is None, turn.result.error
        assert turn.result.branch_kind == "log_opportunity", turn.result.branch_kind
        assert turn.lines == READ_BACK, turn.text
        assert [name for name, _ in seam.calls] == [OPTIONS_TOOL], seam.calls
        (args,) = seam.named(OPTIONS_TOOL)
        assert args.get("q") == "Bath Idea", args
        assert args.get("contact_id") == str(CONTACT_ID), args
        assert args.get("space_id") == _SPACE_ID, args
        assert turn.captured == [], f"no business-lane read on an opportunity turn: {turn.captured}"


# --------------------------------------------------------------------------- #
# O6-2 - missing fields asked one per turn, in order, values survive
# --------------------------------------------------------------------------- #


class TestMissingFieldsAskedOneAtATime:
    def test_missing_fields_asked_one_at_a_time(self, session_factory, monkeypatch) -> None:
        _salesperson(session_factory)
        seam = _install(monkeypatch, options={"Bath Idea": _options(BATH)})

        first = _say(session_factory, monkeypatch, _log(), "log an opportunity")
        assert first.lines == [ASK_CUSTOMER], first.text
        assert seam.calls == [], seam.calls

        customer = _say(
            session_factory, monkeypatch, _log(customer="Bath Idea", answer=_answer("fill")), "Bath Idea",
        )
        assert customer.lines == [ASK_TITLE], customer.text
        assert [a.get("q") for a in seam.named(OPTIONS_TOOL)] == ["Bath Idea"], seam.calls

        title = _say(
            session_factory, monkeypatch, _log(title="condo job Taman X", answer=_answer("fill")), "condo job Taman X",
        )
        assert title.lines == [ASK_AMOUNT], title.text

        amount = _say(session_factory, monkeypatch, _log(amount=40000, answer=_answer("fill")), "40k")
        assert amount.lines == [ASK_CLOSE], amount.text

        close = _say(session_factory, monkeypatch, _log(close="2026-12-15", answer=_answer("fill")), "mid Dec")
        assert close.lines == READ_BACK, close.text

        assert seam.named(LOG_TOOL) == [], "nothing is saved before YES"
        assert len(seam.named(OPTIONS_TOOL)) == 1, f"the customer was settled once and carried: {seam.calls}"


# --------------------------------------------------------------------------- #
# O6-3 - several own accounts: a numbered pick, "2" picks the second
# --------------------------------------------------------------------------- #


class TestCustomerNumberedPick:
    def test_customer_numbered_pick(self, session_factory, monkeypatch) -> None:
        _salesperson(session_factory)
        seam = _install(monkeypatch, options={"BKIN": _options(BKIN_I, BKIN_III)})

        ask = _say(
            session_factory, monkeypatch,
            _log(customer="BKIN", title="condo job Taman X", amount=40000, close="2026-12-15"),
            "new opportunity for BKIN, condo job Taman X, RM 40k, close mid Dec",
        )
        assert ask.lines == [
            "Which account?",
            "1. BKIN ELECTRICAL SDN BHD [A/C I]",
            "2. BKIN ELECTRICAL SDN BHD [A/C III]",
        ], ask.text
        assert seam.named(LOG_TOOL) == []

        picked = _say(
            session_factory, monkeypatch, _log(answer=_answer("pick", [2]), positions=[2]), "2",
        )
        assert picked.lines == [
            "Save this opportunity?",
            "Customer: BKIN ELECTRICAL SDN BHD [A/C III]",
            "Title: condo job Taman X",
            "Amount: RM 40,000.00",
            "Close by: 15 Dec 2026",
            "Reply YES to save.",
        ], picked.text
        assert seam.named(LOG_TOOL) == []

        seam.log = _saved(customer=BKIN_III)
        _say(session_factory, monkeypatch, _yes(), "yes")
        (args,) = seam.named(LOG_TOOL)
        _assert_payload(args, customer_id=BKIN_III["customer_id"], title="condo job Taman X", amount=40000,
                        close="2026-12-15")


# --------------------------------------------------------------------------- #
# O6-4 - blocked ends the flow; no item and not blocked is a prospect
# --------------------------------------------------------------------------- #


class TestBlockedAndProspectLines:
    def test_blocked_and_prospect_lines(self, session_factory, monkeypatch) -> None:
        """Both halves in one test (the UAC names one): blocked first, then a prospect."""
        _salesperson(session_factory)
        seam = _install(
            monkeypatch,
            options={
                "Hanlim": _options(blocked=True),
                "Ahmad Renovation": _options(prospect=True),
            },
        )

        blocked = _say(
            session_factory, monkeypatch,
            _log(customer="Hanlim", title="condo job Taman X", amount=40000, close="2026-12-15"),
            "log opportunity Hanlim, condo job Taman X, RM 40k, close mid Dec",
        )
        assert blocked.lines == [NOT_YOURS], blocked.text

        # The flow ended: a later YES has nothing to save.
        _say(session_factory, monkeypatch, _yes(), "yes")
        assert seam.named(LOG_TOOL) == [], seam.calls

        prospect = _say(
            session_factory, monkeypatch,
            _log(customer="Ahmad Renovation", title="kitchen job", amount=15000, close="2026-11-30"),
            "log opportunity Ahmad Renovation, kitchen job, RM 15k, close end Nov",
        )
        assert prospect.lines == [
            "Save this opportunity?",
            "Prospect: Ahmad Renovation",
            "Title: kitchen job",
            "Amount: RM 15,000.00",
            "Close by: 30 Nov 2026",
            "Reply YES to save.",
        ], prospect.text

        seam.log = _saved(customer=None, prospect="Ahmad Renovation", amount="15000.00")
        _say(session_factory, monkeypatch, _yes(), "yes")
        (args,) = seam.named(LOG_TOOL)
        _assert_payload(args, customer_id=None, prospect="Ahmad Renovation", title="kitchen job", amount=15000,
                        close="2026-11-30")


# --------------------------------------------------------------------------- #
# O6-5 - YES saves once
# --------------------------------------------------------------------------- #


class TestYesSavesOnce:
    @pytest.mark.parametrize(
        "pipeline,lines",
        [
            (PIPELINE, ["Saved OPP-000123, stage New.", "Open opportunities closing by 31 Dec: RM 40,000.00."]),
            (None, ["Saved OPP-000123, stage New."]),
        ],
        ids=["with-pipeline", "no-current-target"],
    )
    def test_yes_saves_once(self, session_factory, monkeypatch, pipeline, lines) -> None:
        _salesperson(session_factory)
        seam = _install(monkeypatch, options={"Bath Idea": _options(BATH)}, log=_saved(pipeline=pipeline))

        read_back = _say(session_factory, monkeypatch, _all_four(), "log an opportunity: Bath Idea, ...")
        assert read_back.lines == READ_BACK, read_back.text

        saved = _say(session_factory, monkeypatch, _yes(), "yes")
        assert saved.result.error is None, saved.result.error
        assert saved.lines == lines, saved.text
        (args,) = seam.named(LOG_TOOL)
        _assert_payload(args, customer_id=BATH["customer_id"], title="condo job Taman X", amount=40000,
                        close="2026-12-15")

        # Saved once: the read-back is closed, a second YES saves nothing more.
        _say(session_factory, monkeypatch, _yes(), "yes")
        assert len(seam.named(LOG_TOOL)) == 1, seam.calls


# --------------------------------------------------------------------------- #
# O6-6 - NO / cancel / another ask save nothing
# --------------------------------------------------------------------------- #

TARGET_GRANT = "sales.sales_target"
TARGET_TEXT = (
    "Sales target Q4 2026 (1 Oct to 31 Dec)\nCounts: A/C I\n"
    "Achieved: RM 17,414.05 (provisional, incl. tax, to 23 Oct)"
)
TARGET_ANSWER = json.dumps({"result_type": "sales_target", "response": TARGET_TEXT, "has_result": True})


def _target_ask() -> dict[str, Any]:
    return _parser_output(
        domain_hint="order",
        intent_hint="check_order",
        order_status="sales_target",
        entities=[],
        self_reference=True,
        opportunity=_opp(),
    )


class TestNoAndOtherAskSaveNothing:
    @pytest.mark.parametrize("mode,body", [("no", "no"), ("cancel", "cancel")])
    def test_no_and_cancel_say_not_saved(self, session_factory, monkeypatch, mode, body) -> None:
        _salesperson(session_factory)
        seam = _install(monkeypatch, options={"Bath Idea": _options(BATH)})

        _say(session_factory, monkeypatch, _all_four(), "log an opportunity: Bath Idea, ...")
        declined = _say(session_factory, monkeypatch, _no(mode), body)

        assert declined.lines == [NOT_SAVED], declined.text
        assert seam.named(LOG_TOOL) == [], seam.calls
        # Dropped: a later YES saves nothing.
        _say(session_factory, monkeypatch, _yes(), "yes")
        assert seam.named(LOG_TOOL) == [], seam.calls

    def test_no_and_other_ask_save_nothing(self, session_factory, monkeypatch) -> None:
        """A different ask while the read-back is open drops it and is answered as usual."""
        _salesperson(session_factory)
        seam = _install(monkeypatch, options={"Bath Idea": _options(BATH)})

        _say(session_factory, monkeypatch, _all_four(), "log an opportunity: Bath Idea, ...")
        other = _say(
            session_factory, monkeypatch, _target_ask(), "how is my target this quarter?",
            attributes=(TARGET_GRANT,), mcp_response=TARGET_ANSWER,
        )

        assert [name for name, _ in other.captured] == ["crm_sales_target_progress"], other.captured
        assert "Sales target Q4 2026" in other.text, other.text
        assert "Save this opportunity?" not in other.text and NOT_SAVED not in other.text, other.text
        assert seam.named(LOG_TOOL) == [], seam.calls

        # The read-back went with the other ask: a YES now saves nothing.
        _say(session_factory, monkeypatch, _yes(), "yes")
        assert seam.named(LOG_TOOL) == [], seam.calls


# --------------------------------------------------------------------------- #
# O6-7 - a field given while the read-back is open updates it and reads back again
# --------------------------------------------------------------------------- #


class TestCorrectionReadsBackAgain:
    def test_correction_reads_back_again(self, session_factory, monkeypatch) -> None:
        _salesperson(session_factory)
        seam = _install(monkeypatch, options={"Bath Idea": _options(BATH)}, log=_saved(amount="50000.00"))

        _say(session_factory, monkeypatch, _all_four(), "log an opportunity: Bath Idea, ...")
        corrected = _say(session_factory, monkeypatch, _log(amount=50000), "make it 50k")

        assert corrected.lines == [
            "Save this opportunity?",
            "Customer: BATH IDEA BATHROOM & KITCHEN MARKETING SDN BHD [A/C I]",
            "Title: condo job Taman X",
            "Amount: RM 50,000.00",
            "Close by: 15 Dec 2026",
            "Reply YES to save.",
        ], corrected.text
        assert seam.named(LOG_TOOL) == [], seam.calls

        _say(session_factory, monkeypatch, _yes(), "yes")
        (args,) = seam.named(LOG_TOOL)
        _assert_payload(args, customer_id=BATH["customer_id"], title="condo job Taman X", amount=50000,
                        close="2026-12-15")


# --------------------------------------------------------------------------- #
# O6-8 - a dealer, staff or unlinked contact is refused in one line, no MCP call
# --------------------------------------------------------------------------- #


class TestNonSalespersonRefusedInLane:
    @pytest.mark.parametrize("seed", [_dealer, _staff, _unlinked], ids=["dealer", "staff", "unlinked"])
    def test_non_salesperson_refused_in_lane(self, session_factory, monkeypatch, seed) -> None:
        seed(session_factory)
        seam = _install(monkeypatch, options={"Bath Idea": _options(BATH)})

        turn = _say(
            session_factory, monkeypatch,
            _log(title="condo job Taman X", amount=40000, close="2026-12-15"),
            "log an opportunity: condo job Taman X, RM 40k, closing mid Dec",
        )

        assert turn.lines == [NOT_SALESPERSON], turn.text
        assert seam.calls == [], seam.calls
        assert turn.captured == [], turn.captured


# --------------------------------------------------------------------------- #
# O6-9 - route errors worded, never raw
# --------------------------------------------------------------------------- #


class TestRouteErrorsWorded:
    @pytest.mark.parametrize(
        "status,code,line",
        [
            (403, "not_a_salesperson", NOT_ENABLED),
            (403, "opportunity_not_enabled", NOT_ENABLED),
            (422, "CUSTOMER_NOT_YOURS", NOT_YOURS),
            (422, "amount_required", COULD_NOT_SAVE),
            (500, None, COULD_NOT_SAVE),
        ],
        ids=["403-not-salesperson", "403-not-enabled", "422-not-yours", "422-other", "500"],
    )
    def test_route_errors_worded(self, session_factory, monkeypatch, status, code, line) -> None:
        _salesperson(session_factory)
        seam = _install(
            monkeypatch, options={"Bath Idea": _options(BATH)}, log=_route_error(status, code, tool=LOG_TOOL),
        )

        _say(session_factory, monkeypatch, _all_four(), "log an opportunity: Bath Idea, ...")
        answered = _say(session_factory, monkeypatch, _yes(), "yes")

        assert len(seam.named(LOG_TOOL)) == 1, seam.calls
        assert answered.lines == [line], answered.text

    def test_options_route_refusal_worded(self, session_factory, monkeypatch) -> None:
        """The gate runs on both routes: the first call of the flow (the options read) can be the
        one refused."""
        _salesperson(session_factory)
        seam = _install(
            monkeypatch,
            options={"Bath Idea": _route_error(403, "opportunity_not_enabled", tool=OPTIONS_TOOL)},
        )

        turn = _say(session_factory, monkeypatch, _all_four(), "log an opportunity: Bath Idea, ...")

        assert turn.lines == [NOT_ENABLED], turn.text
        assert seam.named(LOG_TOOL) == [], seam.calls


# --------------------------------------------------------------------------- #
# O6-10 - a console dry run: same reads, same read-back, write sent with dry_run
# --------------------------------------------------------------------------- #


class TestDryRunTurnSavesNothing:
    def test_dry_run_turn_saves_nothing(self, session_factory, monkeypatch) -> None:
        _salesperson(session_factory)
        seam = _install(monkeypatch, options={"Bath Idea": _options(BATH)}, log=_saved(dry_run=True))
        before = _session_of(session_factory)

        first = _say(
            session_factory, monkeypatch, _all_four(), "log an opportunity: Bath Idea, ...", dry_run=True, state=None,
        )
        assert first.result.error is None, first.result.error
        assert first.lines == READ_BACK, first.text
        assert [a.get("q") for a in seam.named(OPTIONS_TOOL)] == ["Bath Idea"], seam.calls

        second = _say(
            session_factory, monkeypatch, _yes(), "yes", dry_run=True, state=first.result.session_patch,
        )
        assert second.result.error is None, second.result.error
        (args,) = seam.named(LOG_TOOL)
        _assert_payload(args, customer_id=BATH["customer_id"], title="condo job Taman X", amount=40000,
                        close="2026-12-15", dry_run=True)
        assert TEST_RUN in second.lines, second.text
        assert "Saved OPP" not in second.text, second.text
        assert _session_of(session_factory) == before, "a dry run writes nothing to the contact's session"


# --------------------------------------------------------------------------- #
# O6-11 - any other status behaves exactly as before
# --------------------------------------------------------------------------- #


class TestOtherStatusesUntouched:
    def test_other_statuses_untouched(self, session_factory, monkeypatch) -> None:
        """A salesperson's sales target ask still reaches the target tool, even with the B4 key
        present (all null); the opportunity seam is never called."""
        _salesperson(session_factory)
        seam = _install(monkeypatch, options={"Bath Idea": _options(BATH)})

        turn = _say(
            session_factory, monkeypatch, _target_ask(), "how is my target this quarter?",
            attributes=(TARGET_GRANT,), mcp_response=TARGET_ANSWER,
        )

        assert [name for name, _ in turn.captured] == ["crm_sales_target_progress"], turn.captured
        assert turn.result.branch_kind != "log_opportunity", turn.result.branch_kind
        assert seam.calls == [], seam.calls

    def test_a_product_ask_never_reaches_the_lane(self, session_factory, monkeypatch) -> None:
        _salesperson(session_factory)
        seam = _install(monkeypatch, options={"Bath Idea": _options(BATH)})

        turn = _say(session_factory, monkeypatch, _parser_output(opportunity=_opp()), "price for SRTWC8517")

        assert turn.result.branch_kind == "business_query", turn.result.branch_kind
        assert seam.calls == [], seam.calls
        assert "Save this opportunity?" not in turn.text, turn.text


# --------------------------------------------------------------------------- #
# O4-2 - the write tool is never on the read-only path; only the lane's seam calls it
# --------------------------------------------------------------------------- #


class TestLogToolNotInReadOnlyPool:
    def test_log_tool_not_in_read_only_pool(self) -> None:
        from app.services.chatbot.lanes.business.fetch import (
            CHATBOT_READ_ONLY_TOOLS,
            ToolNotAllowed,
            ensure_read_only,
        )

        assert LOG_TOOL not in CHATBOT_READ_ONLY_TOOLS
        with pytest.raises(ToolNotAllowed):
            ensure_read_only(LOG_TOOL)
        # The options read is the one tool of the two the allow-list holds (a GET in the catalogue).
        assert OPTIONS_TOOL in CHATBOT_READ_ONLY_TOOLS

    def test_log_tool_is_a_write_for_the_in_app_assistant(self) -> None:
        """Its name ends in no write verb, so the assistant's confirm gate needs it by name."""
        from app.services.ai_assistant_service import _is_write_tool

        assert _is_write_tool(LOG_TOOL) is True
        assert _is_write_tool(OPTIONS_TOOL) is False

    def test_the_seam_calls_the_mcp_client_directly(self, monkeypatch) -> None:
        """`call_opportunity_tool` reaches `MCPRuntimeClient.call_tool` itself (the ideate seam's
        shape), never `fetch.call_tool`, whose allow-list would refuse the write."""
        import importlib

        from app.services.ai_assistant_service import MCPRuntimeClient

        lane = importlib.import_module(LANE_MODULE)
        sent: list[tuple[str, dict[str, Any]]] = []

        def _fake(self, name: str, arguments: dict[str, Any]) -> str:
            sent.append((name, dict(arguments)))
            return json.dumps(_saved())

        monkeypatch.setattr(MCPRuntimeClient, "call_tool", _fake)
        payload = {"contact_id": str(CONTACT_ID), "space_id": _SPACE_ID, "title": "condo job Taman X"}

        out = getattr(lane, SEAM)(LOG_TOOL, payload)

        assert sent == [(LOG_TOOL, payload)], sent
        assert out["opportunity_no"] == "OPP-000123", out

    def test_the_write_tool_is_named_only_in_the_opportunity_lane(self) -> None:
        """No chatbot module but the lane names (so calls) the write tool. The one exception is
        its `contracts.BRAND_SCOPE_TREATMENT` entry, which `test_brand_scope_contract` requires of
        every catalogue tool: a treatment entry is not a call (lead sign-off, plan 5e98596457)."""
        from app.services.chatbot import contracts

        root = Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"
        lane = root / "lanes" / "opportunity.py"
        assert lane.exists(), f"{lane} is missing"
        naming = sorted(
            str(p.relative_to(root)) for p in root.rglob("*.py") if LOG_TOOL in p.read_text(encoding="utf-8")
        )
        assert "lanes/opportunity.py" in naming, naming
        assert set(naming) <= {"lanes/opportunity.py", "contracts.py"}, naming
        if "contracts.py" in naming:
            # The treatment entry and nothing else: one mention, and it is that dict's key.
            assert (root / "contracts.py").read_text(encoding="utf-8").count(LOG_TOOL) == 1
            assert LOG_TOOL in contracts.BRAND_SCOPE_TREATMENT
