"""S5 - the escalation lane (`branch_kind == out_of_scope`). AC-501 to AC-507.

RED, written before `app/services/chatbot/lanes/escalation.py` exists (Phase 2, test-first).
Everything below fails today with `ModuleNotFoundError: No module named
'app.services.chatbot.lanes'` (or, for the engine test, `AttributeError` from
`monkeypatch.setattr` naming an attribute `engine.py` does not have yet) - the right reason,
per the brief.

Ported nodes (source: `sorento_crm_n8n/n8n-workflows-init/export/sub-escalation-live/` and
`export/live-sub-human-intervention/`, read-only): `escalation-input` (item carrier, folded
into the `item` parameter below - trivial, not separately ported), `fresh-entity-gate`,
`escalation-context` (89-line six-rank precedence ladder), `clarify-team-gate` /
`clarify-team-reply`, `clarify-company-gate` / `clarify-company-reply`, `escalation-result`,
and the assignment path inside `sub-human-intervention` (`get-round-robin-assignee` ->
`if-conversation-unassigned` -> `Assign or unassign a Conversation1` ->
`conversation-sla-tracking-create` -> `Call 'sub-add-comment-respond'` ->
`sorento-sub-respond-sendmsg-respond-routed-to-pic`, with
`sorento-sub-respond-sendmsg-respond-routed-to-pic2` sent FIRST, before the round-robin call).

**This file PINS a contract the plan states only at the `run()` level. The exact function
names below are this tester's design decision, made explicit here so the coder implements
against them rather than guessing:**

    app/services/chatbot/lanes/escalation.py
        escalation_context(item, *, ctx, gate) -> dict         # port of escalation-context.js
        clarify_team_reply(item) -> dict                       # port of clarify-team-reply.js
        clarify_company_reply(item, *, ctx, gate) -> dict       # port of clarify-company-reply.js
        escalation_result(*, clarify_team, clarify_company) -> dict   # port of escalation-result.js
        run(ctx, item, *, services, dry_run=False) -> dict
            -> {"arm": "clarify" | "human-intervention", "clarify": dict | None,
                "actions": list[dict], "pending": dict | None}

    `services` is a duck-typed namespace (see `_services()` below) with four callables:
    `resolve_and_gate(ctx, item)`, `next_assignee(body)`, `sla_create(body)`, `team_members(...)`.
    None of them is called when `dry_run` is True (H37: the dry-run check runs BEFORE any of
    them, never after).

    `app/services/chatbot/engine.py` imports `run` under the name `run_escalation_lane`
    (the same "import the function by name into engine's namespace so a test can monkeypatch
    `engine_mod.<name>`" pattern the file already uses for `check_access` / `default_space_id` /
    `post_process` / `suggest_follow_up`) and calls it when `branch_kind == "out_of_scope"`,
    after adding `"out_of_scope"` to `contracts.CRM_COMPLETED_BRANCH_KINDS`.

`pending` is a plain dict, not yet required to validate against `contracts.Pending` (that
model gains whatever fields S5 needs - e.g. a `companies` list for the company-clarify case -
as part of the implementation; this suite only pins `pending["kind"]`).

Nothing here reaches an LLM, n8n, respond.io, or a real MCP server.
"""
from __future__ import annotations

import re
from typing import Any
from unittest.mock import Mock

import pytest

from tests.chatbot import _corpus

# --------------------------------------------------------------------------- #
# Shared builders
# --------------------------------------------------------------------------- #


def _ctx(
    *,
    routing: dict | None = None,
    escalation: dict | None = None,
    query_brands: list | None = None,
    entities: list | None = None,
    prev_variables: dict | None = None,
    contact_phone: str = "+60123450099",
    contact_id: str = "ZZT-esc-1",
    current_assignee: str | None = None,
) -> dict:
    """The six-key hub shape `build_ctx` produces, filled in with what the escalation lane
    reads: `ctx.parse.output.{routing,escalation,query_brands,entities}` and
    `ctx.session.session_vars.variables` (the ladder's `prev`)."""
    contact: dict[str, Any] = {"id": contact_id, "phone": contact_phone}
    if current_assignee is not None:
        contact["assignee"] = {"id": current_assignee}
    return {
        "contact": contact,
        "text": {
            "message": {"messageId": "ZZT-esc-msg-1", "message": {"type": "text", "text": "help"}}
        },
        "session": {"session_vars": {"variables": prev_variables or {}}},
        "parse": {
            "output": {
                "routing": routing or {"suggested_team": None, "suggested_agent": None},
                "escalation": escalation or {"is_escalation_confirmation": True, "company_pick": None},
                "query_brands": query_brands or [],
                "entities": entities or [],
            }
        },
        "access": {"allowed": True, "decision": "allow"},
        "media": None,
    }


def _item(*, branch_kind: str = "out_of_scope", **overrides: Any) -> dict:
    """`route-turn`'s output item for `out_of_scope` - `{**access, branch_kind}` (it is
    NOT a tag-only arm), which is also `escalation-input`'s own output verbatim."""
    base = {
        "allowed": True,
        "decision": "allow",
        "agent_name": "General Enquiries",
        "attributes": None,
        "all_attributes_allowed": None,
        "branch_kind": branch_kind,
    }
    base.update(overrides)
    return base


def _services(
    *,
    gate: dict | None = None,
    assignee: dict | None = None,
    sla: dict | None = None,
    members: list | None = None,
):
    """A `services` seam with recorded calls, never touching a database or the network."""
    default_assignee = {
        "assignee_id": "usr-pic-1",
        "assignee_email": "pic@sorento.example",
        "assignee_name": "PIC One",
        "assignee_respond_user_id": "respond-usr-1",
        "team_set_code": "CS",
        "brand_code": None,
        "company_id": None,
        "is_already_assigned": False,
    }
    default_sla = {
        "id": "sla-row-1",
        "initiated_at": "2026-09-05T04:00:00+00:00",
        "due_at": "2026-09-05T08:00:00+00:00",
        "due_at_resolution": "2026-09-06T04:00:00+00:00",
    }
    return type(
        "Services",
        (),
        {
            "resolve_and_gate": Mock(return_value=gate),
            "next_assignee": Mock(return_value={**default_assignee, **(assignee or {})}),
            "sla_create": Mock(return_value={**default_sla, **(sla or {})}),
            "team_members": Mock(return_value=members or []),
        },
    )()


# --------------------------------------------------------------------------- #
# AC-501: escalation-context's six-rank precedence ladder (H26, H27)
# --------------------------------------------------------------------------- #


def _rank_case(case_id: str):
    """`(item, ctx_kwargs, gate, expected)` for one rung of the ladder."""
    if case_id == "picked_member":
        prev = {
            "last_result_set": [
                {"uuid": "member-9", "company_id": "c-sorento", "company_name": "Sorento", "brand_code": "sorento"}
            ]
        }
        escalation = {"is_escalation_confirmation": True, "preferred_assignee_id": "member-9", "company_pick": None}
        ctx_kwargs = dict(prev_variables=prev, escalation=escalation, routing={"suggested_team": "customer_service"})
        gate = None
        expected = {"brand_code": "sorento", "company_id": "c-sorento", "company_name": "Sorento", "routing_source": "picked_member"}
    elif case_id == "company_pick_name":
        prev = {
            "routing_roster_plan": [
                {"company_id": "c-mocha", "company_name": "Mocha", "brand_code": "mch"},
                {"company_id": "c-cabana", "company_name": "Cabana", "brand_code": "cbn"},
            ]
        }
        escalation = {"is_escalation_confirmation": True, "company_pick": "Mocha"}
        ctx_kwargs = dict(prev_variables=prev, escalation=escalation, routing={"suggested_team": "customer_service"})
        gate = None
        expected = {"brand_code": "mch", "company_id": "c-mocha", "company_name": "Mocha", "routing_source": "company_pick"}
    elif case_id == "company_pick_id":
        prev = {"routing_companies": [{"company_id": "c-cabana", "company_name": "Cabana", "brand_code": "cbn"}]}
        escalation = {"is_escalation_confirmation": True, "company_pick": "C-CABANA"}
        ctx_kwargs = dict(prev_variables=prev, escalation=escalation, routing={"suggested_team": "customer_service"})
        gate = None
        expected = {"brand_code": "cbn", "company_id": "c-cabana", "company_name": "Cabana", "routing_source": "company_pick"}
    elif case_id == "company_pick_code":
        prev = {"routing_companies": [{"company_id": "c-mocha", "company_name": "Mocha", "brand_code": "mch", "company_code": "MCH2"}]}
        escalation = {"is_escalation_confirmation": True, "company_pick": "mch2"}
        ctx_kwargs = dict(prev_variables=prev, escalation=escalation, routing={"suggested_team": "customer_service"})
        gate = None
        expected = {"brand_code": "mch", "company_id": "c-mocha", "company_name": "Mocha", "routing_source": "company_pick"}
    elif case_id == "company_pick_alias":
        prev = {"routing_companies": [{"company_id": "c-sorento", "company_name": "Sorento", "brand_code": "sorento"}]}
        escalation = {"is_escalation_confirmation": True, "company_pick": "srt"}
        ctx_kwargs = dict(prev_variables=prev, escalation=escalation, routing={"suggested_team": "customer_service"})
        gate = None
        expected = {"brand_code": "sorento", "company_id": "c-sorento", "company_name": "Sorento", "routing_source": "company_pick"}
    elif case_id == "resolved_entity":
        gate = {"routing_companies": [{"company_id": "c-cabana", "company_name": "Cabana"}], "routing_company": "c-cabana", "routing_brand": "cbn"}
        ctx_kwargs = dict(entities=[{"raw": "widget", "hint": "product", "current_message": True}], routing={"suggested_team": "customer_service"})
        expected = {"brand_code": "cbn", "company_id": "c-cabana", "company_name": "Cabana", "routing_source": "resolved_entity"}
    elif case_id == "multi_company_unpicked":
        gate = {"routing_companies": [{"company_id": "c-a", "company_name": "A"}, {"company_id": "c-b", "company_name": "B"}]}
        ctx_kwargs = dict(entities=[{"raw": "widget", "hint": "product", "current_message": True}], routing={"suggested_team": "customer_service"})
        expected = {"brand_code": None, "company_id": None, "company_name": None, "routing_source": "multi_company_unpicked"}
    elif case_id == "sameTeam_prior_state":
        prev = {"routing": {"suggested_team": "marketing_product"}, "routing_roster_plan": [{"company_id": "c-zeta", "company_name": "Zeta", "brand_code": "z"}]}
        ctx_kwargs = dict(prev_variables=prev, routing={"suggested_team": "marketing_product"})
        gate = None
        expected = {"brand_code": "z", "company_id": "c-zeta", "company_name": "Zeta", "routing_source": "prior_state"}
    elif case_id == "none":
        ctx_kwargs = dict(routing={"suggested_team": "customer_service"}, query_brands=[])
        gate = None
        expected = {"brand_code": None, "company_id": None, "company_name": None, "routing_source": "none"}
    else:  # pragma: no cover - guarded by the parametrize ids below
        raise ValueError(case_id)
    return ctx_kwargs, gate, expected


RANK_IDS = [
    "picked_member",
    "company_pick_name",
    "company_pick_id",
    "company_pick_code",
    "company_pick_alias",
    "resolved_entity",
    "multi_company_unpicked",
    "sameTeam_prior_state",
    "none",
]


@pytest.mark.parametrize("case_id", RANK_IDS)
def test_escalation_context_ladder(case_id: str) -> None:
    """AC-501: `brand_code` / `company_id` / `company_name` / `routing_source` match
    `escalation-context.js`'s six-rank precedence exactly, over the pool-identity variants
    (company_pick by name / id / code / alias) that rank shares."""
    from app.services.chatbot.lanes.escalation import escalation_context

    ctx_kwargs, gate, expected = _rank_case(case_id)
    ctx = _ctx(**ctx_kwargs)
    item = _item()

    out = escalation_context(item, ctx=ctx, gate=gate)

    for key, value in expected.items():
        assert out[key] == value, f"{case_id}: {key} = {out.get(key)!r}, expected {value!r}"
    # The item is SPREAD, never replaced (escalation-context.js: `...$input.first().json`).
    assert out["branch_kind"] == "out_of_scope"
    assert out["allowed"] is True


def test_no_hard_default_team() -> None:
    """AC-501 / H27: with no explicit team, no prior offer and no inference, the LANE asks -
    it never falls back to a hard-coded team (the deleted `?? 'customer_service'` literal)."""
    from app.services.chatbot.lanes.escalation import run

    ctx = _ctx(routing={"suggested_team": None, "suggested_agent": None})
    item = _item()
    services = _services()

    result = run(ctx, item, services=services)

    assert result["arm"] == "clarify"
    assert result["pending"] is not None
    assert result["pending"]["kind"] == "team_clarify"
    assert result["clarify"]["clarify_team"] is True
    assert "customer_service" not in str(result["clarify"].get("team", ""))
    services.next_assignee.assert_not_called()
    services.team_members.assert_not_called()


def test_clarify_company_ask_always_in_reply() -> None:
    """AC-505 / H2: the multi-company-unpicked case is ALWAYS answered with the clarify ask,
    in the SAME synchronous call that decided it needed one - the race cannot exist because
    there is no separate later step that could still be composing it."""
    from app.services.chatbot.lanes.escalation import run

    ctx = _ctx(
        routing={"suggested_team": "customer_service"},
        prev_variables={
            "selection_context": "member_offer",
            "last_result_set": [{"uuid": "m1"}],
            "routing_roster_plan": [
                {"company_id": "c-mocha", "company_name": "Mocha"},
                {"company_id": "c-sorento", "company_name": "Sorento"},
            ],
        },
    )
    item = _item(brand_code=None, company_id=None, company_name=None, routing_source="multi_company_unpicked", team="customer_service")
    services = _services()

    result = run(ctx, item, services=services)

    assert result["arm"] == "clarify"
    assert result["pending"]["kind"] == "company_clarify"
    assert result["clarify"]["clarify_text"] == (
        "Both *Mocha* and *Sorento* teams are listed - reply a number, a name, or the "
        "company (*Mocha* / *Sorento*) and I'll assign automatically."
    )
    assert [a["kind"] for a in result["actions"]] == []
    services.next_assignee.assert_not_called()


# --------------------------------------------------------------------------- #
# AC-502: the assignment path, in order
# --------------------------------------------------------------------------- #


def _assignment_ctx_and_item() -> tuple[dict, dict]:
    ctx = _ctx(routing={"suggested_team": "customer_service", "suggested_agent": "general_enquiries"})
    item = _item(brand_code=None, company_id=None, company_name=None, routing_source="none", team="customer_service")
    return ctx, item


def test_assignment_actions_in_order() -> None:
    """AC-502: the four actions, in the order the caller must execute them, plus the
    out-of-scope acknowledgement text (`escalate-catalog`'s `includeResponse: false` state
    text, 'Informed the user that request is out of scope...') is NOT one of them - that
    text belongs to the S2 tail's session bookkeeping, not to anything the S5 lane sends."""
    from app.services.chatbot.lanes.escalation import run

    ctx, item = _assignment_ctx_and_item()
    services = _services(assignee={"assignee_respond_user_id": "respond-usr-7", "assignee_id": "usr-7", "is_already_assigned": False})

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention"
    assert result["clarify"] is None
    kinds = [a["kind"] for a in result["actions"]]
    assert kinds == ["send_message", "assign_conversation", "add_comment", "send_message"]

    first_send, assign, comment, second_send = result["actions"]
    assert "out of the scope" in first_send["text"].lower()
    assert assign["respond_user_id"] == "respond-usr-7"
    assert comment["mention_user_ids"] == ["usr-7"]
    assert comment["text"]
    assert "routed" in second_send["text"].lower() and "customer service" in second_send["text"].lower()

    for action in result["actions"]:
        assert "Informed the user that request is out of scope" not in str(action)

    services.next_assignee.assert_called_once()
    body = services.next_assignee.call_args[0][0]
    assert set(body) == {
        "agent_code",
        "team_code",
        "contact_phone_number",
        "policy_code",
        "preferred_assignee_id",
        "tier",
        "brand_code",
        "company_id",
    }
    assert body["team_code"] == "customer_service"
    assert body["agent_code"] == "general_enquiries"
    assert body["contact_phone_number"] == ctx["contact"]["phone"]
    assert body["policy_code"] == "NORMAL"
    assert body["tier"] == 1

    services.sla_create.assert_called_once()
    sla_body = services.sla_create.call_args[0][0]
    assert isinstance(sla_body, dict)
    assert sla_body.get("contact_phone_number") == ctx["contact"]["phone"]


def test_conversation_already_assigned_skips_assign() -> None:
    """AC-502: `if-conversation-unassigned`'s false leg - already assigned in respond.io,
    so no `assign_conversation`, but the SLA clock still starts."""
    from app.services.chatbot.lanes.escalation import run

    ctx, item = _assignment_ctx_and_item()
    services = _services(assignee={"is_already_assigned": True})

    result = run(ctx, item, services=services)

    kinds = [a["kind"] for a in result["actions"]]
    assert "assign_conversation" not in kinds
    assert kinds == ["send_message", "add_comment", "send_message"]
    services.sla_create.assert_called_once()


# --------------------------------------------------------------------------- #
# AC-503 / H37: dry run never reaches a side-effecting seam
# --------------------------------------------------------------------------- #


def test_dry_run_never_reaches_next_assignee(session_factory) -> None:
    """D14 evaluated FIRST (H37: n8n called next-assignee and guarded afterwards). Row
    counts on the real (blank) Postgres schema are the second net: even if the coder's
    `run()` bypassed the injected `services` and called a real production function
    directly, that would show up here as a nonzero count, where a call-count assertion on
    the mock alone would not catch it."""
    from app.models.access import AgentTeamRoundRobinCursor
    from app.models.sla import ConversationSLATracking
    from app.services.chatbot.lanes.escalation import run

    ctx, item = _assignment_ctx_and_item()
    services = _services()

    result = run(ctx, item, services=services, dry_run=True)

    services.next_assignee.assert_not_called()
    services.sla_create.assert_not_called()
    assert result["actions"]
    assert all(a.get("dry_run") is True for a in result["actions"])

    db = session_factory()
    assert db.query(AgentTeamRoundRobinCursor).count() == 0
    assert db.query(ConversationSLATracking).count() == 0


# --------------------------------------------------------------------------- #
# AC-504: node replay against the captured n8n executions
# --------------------------------------------------------------------------- #

_corpus.NODE_SLUGS.setdefault("escalation-context", ("sub-escalation", "sub-escalation-rs"))
_corpus.NODE_SLUGS.setdefault("clarify-team-reply", ("sub-escalation", "sub-escalation-rs"))
_corpus.NODE_SLUGS.setdefault("clarify-company-reply", ("sub-escalation", "sub-escalation-rs"))
_corpus.NODE_SLUGS.setdefault("escalation-result", ("sub-escalation", "sub-escalation-rs"))


def _fixture_gate(fixture: _corpus.Fixture) -> dict | None:
    if fixture.upstream("Call 'sub-resolve-and-gate'"):
        return (fixture.first("Call 'sub-resolve-and-gate'") or {}).get("gate")
    return None


def _run_escalation_context(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.escalation import escalation_context

    item = (fixture.input[0] or {}).get("json") or {}
    ctx = fixture.first("build-ctx")["ctx"]
    return [{"json": escalation_context(item, ctx=ctx, gate=_fixture_gate(fixture))}]


def _run_clarify_team_reply(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.escalation import clarify_team_reply

    item = (fixture.input[0] or {}).get("json") or {}
    return [{"json": clarify_team_reply(item)}]


def _run_clarify_company_reply(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.escalation import clarify_company_reply

    item = (fixture.input[0] or {}).get("json") or {}
    ctx = fixture.first("build-ctx")["ctx"]
    return [{"json": clarify_company_reply(item, ctx=ctx, gate=_fixture_gate(fixture))}]


def _run_escalation_result(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.escalation import escalation_result

    clarify_team = fixture.first("clarify-team-reply") if fixture.upstream("clarify-team-reply") else None
    clarify_company = fixture.first("clarify-company-reply") if fixture.upstream("clarify-company-reply") else None
    return [{"json": escalation_result(clarify_team=clarify_team, clarify_company=clarify_company)}]


_S5_RUNNERS = {
    "escalation-context": _run_escalation_context,
    "clarify-team-reply": _run_clarify_team_reply,
    "clarify-company-reply": _run_clarify_company_reply,
    "escalation-result": _run_escalation_result,
}


def _s5_fixtures() -> list[_corpus.Fixture]:
    out: list[_corpus.Fixture] = []
    for node in _S5_RUNNERS:
        out.extend(_corpus.vendored(node))
        out.extend(_corpus.full_corpus(node))
    return out


@pytest.mark.parametrize(
    "fixture", _corpus.graded(_s5_fixtures()), ids=lambda f: f"{f.node}/{f.name}"
)
def test_replay(fixture: _corpus.Fixture) -> None:
    """AC-504: every real capture for the four S5 nodes, byte-equal after a JSON round
    trip - the same grading rule `test_replay.py` uses (only `runData` fails the suite;
    `reasoned` fixtures are exercised separately below, never as a gate)."""
    actual = _corpus.json_round_trip(_S5_RUNNERS[fixture.node](fixture))
    expected = _corpus.json_round_trip(fixture.expected)
    assert actual == expected, (
        f"{fixture.node}/{fixture.name} diverges from the captured n8n output\n"
        f"fixture: {fixture.path}"
    )


def test_reasoned_fixtures_are_replayed_and_reported(capsys) -> None:
    rows = _corpus.reasoned(_s5_fixtures())
    if not rows:
        pytest.skip("no `reasoned` fixtures for the S5 nodes on this corpus")
    agree, differ = [], []
    for fixture in rows:
        actual = _corpus.json_round_trip(_S5_RUNNERS[fixture.node](fixture))
        expected = _corpus.json_round_trip(fixture.expected)
        (agree if actual == expected else differ).append(f"{fixture.node}/{fixture.name}")
    with capsys.disabled():
        print(f"\n  S5 reasoned fixtures: {len(rows)} replayed, {len(agree)} agree, {len(differ)} differ")


# --------------------------------------------------------------------------- #
# fresh-entity-gate (H26 port)
# --------------------------------------------------------------------------- #


def test_fresh_entity_gate_calls_resolve() -> None:
    """AC-501: `fresh-entity-gate`'s own predicate, `entities.some(e => e.current_message
    === true)`. A fresh entity on THIS turn resolves and gates before the ladder runs; a
    bare confirmation (no fresh entity) never calls the resolver at all."""
    from app.services.chatbot.lanes.escalation import run

    ctx_with_entity = _ctx(
        routing={"suggested_team": "customer_service"},
        entities=[{"raw": "widget", "hint": "product", "current_message": True}],
    )
    services = _services(gate=None)
    run(ctx_with_entity, _item(), services=services)
    services.resolve_and_gate.assert_called_once()

    ctx_without_entity = _ctx(routing={"suggested_team": "customer_service"}, entities=[])
    services2 = _services(gate=None)
    run(ctx_without_entity, _item(), services=services2)
    services2.resolve_and_gate.assert_not_called()


# --------------------------------------------------------------------------- #
# R3: the pending marker replaces the frozen-string read
# --------------------------------------------------------------------------- #


def test_pending_marker_written_for_clarify_kinds() -> None:
    from app.services.chatbot.lanes.escalation import run

    team_ctx = _ctx(routing={"suggested_team": None, "suggested_agent": None})
    team_result = run(team_ctx, _item(), services=_services())
    assert team_result["pending"] == {"kind": "team_clarify"} or (
        isinstance(team_result["pending"], dict) and team_result["pending"]["kind"] == "team_clarify"
    )

    company_ctx = _ctx(
        routing={"suggested_team": "customer_service"},
        prev_variables={
            "selection_context": "member_offer",
            "last_result_set": [{"uuid": "m1"}],
            "routing_roster_plan": [
                {"company_id": "c-mocha", "company_name": "Mocha"},
                {"company_id": "c-sorento", "company_name": "Sorento"},
            ],
        },
    )
    company_item = _item(brand_code=None, company_id=None, company_name=None, routing_source="multi_company_unpicked", team="customer_service")
    company_result = run(company_ctx, company_item, services=_services())
    assert company_result["pending"]["kind"] == "company_clarify"

    assignment_ctx, assignment_item = _assignment_ctx_and_item()
    assignment_result = run(assignment_ctx, assignment_item, services=_services())
    assert assignment_result["pending"] is None


# --------------------------------------------------------------------------- #
# D11: semantic in, deterministic processing - no regex over the raw envelope
# --------------------------------------------------------------------------- #


def test_no_raw_text_regex_in_lane() -> None:
    """D11: everything after the parser works on STRUCTURED state. `_CO_ALIASES` may exist
    (it does in the JS - a stopgap company-code/alias map) but it is applied to
    `escalation.company_pick`, the parser's OWN output, never to `ctx.text` / `ctx['text']`,
    the customer's raw message."""
    import inspect

    import app.services.chatbot.lanes.escalation as escalation_mod

    source = inspect.getsource(escalation_mod)
    for banned in ('ctx["text"]', "ctx['text']", '.get("text")', ".get('text')"):
        assert banned not in source, f"lane reads the raw envelope directly via {banned!r}"

    for lineno, line in enumerate(source.splitlines(), start=1):
        if re.search(r"\bre\.(match|search|findall|sub|compile)\(", line):
            assert "text" not in line.lower() or "clarify_text" in line, (
                f"line {lineno} looks like a regex touching raw text: {line.strip()!r}"
            )


# --------------------------------------------------------------------------- #
# Engine wiring: out_of_scope finishes the turn, delegate is None
# --------------------------------------------------------------------------- #


def test_out_of_scope_finishes_in_turn(session_factory, monkeypatch) -> None:
    """`out_of_scope` moves from `DELEGATED_BRANCH_KINDS` to `CRM_COMPLETED_BRANCH_KINDS`
    (S5's whole point): the head's own stages (received/understood/access/routed) are
    unchanged, then the engine calls the lane at `looked_up` and composes the reply at
    `replied`; delegate becomes null and the row closes `done`.

    A seam failure fails the turn at `looked_up` with today's generic error reply and NO
    partial assignment - the lane's actions are either the complete set (assign + SLA
    together) or absent entirely, never assign without SLA, because a lane that raises
    partway through never returns an action list at all.

    Assumption pinned by this test: `engine.py` imports the lane's `run` function under the
    name `run_escalation_lane` (see the module docstring) - if `monkeypatch.setattr` here
    raises `AttributeError` naming a DIFFERENT missing attribute than that, the coder should
    rename the import to match rather than treat this as a design objection; the name itself
    is not part of any AC.
    """
    import json as _json

    from sqlalchemy import text

    from app.models.chatbot_turn import ChatbotTurn
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.contracts import Envelope
    from app.services.chatbot.head import parser as parser_mod

    contact_id = "ZZT-esc-engine-1"
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": contact_id, "phone": "+60000000099", "sv": _json.dumps({"variables": {}})},
    )
    db.commit()

    def fake_resolve_config(db, *, current_date):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test"
        )

    escalation_qf = {
        "message_type": "request_for_help",
        "intent_hint": "check_product",
        "domain_hint": "master_products",
        "scope_intent": "specific",
        "is_affirmative": None,
        "user_goal": "wants a human",
        "access_levels": [],
        "broaden_axis": None,
        "date_mode": None,
        "date_filter_start": None,
        "date_filter_end": None,
        "match_mode": "and",
        "demand_qty": None,
        "entities": [],
        "entity_op": "replace_combine",
        "scope_exclusive": False,
        "requested_attributes": [],
        "contains_flyer": False,
        "reference_positions": [],
        "reference_target": None,
        "person_mention": None,
        "is_active": None,
        "order_status": None,
        "correction": False,
        "routing": {"suggested_team": "customer_service", "suggested_agent": "general_enquiries", "team_source": "inferred"},
        "escalation": {"is_escalation_confirmation": True, "company_pick": None},
    }

    def fake_parse(config, user_block):
        return escalation_qf

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", fake_parse)
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True,
            "decision": "allow",
            "agent_name": "General Enquiries",
            "attributes": None,
            "all_attributes_allowed": None,
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")

    lane_actions = [
        {"kind": "send_message", "text": "Your request is out of scope...", "dry_run": False},
        {"kind": "assign_conversation", "respond_user_id": "respond-usr-1", "dry_run": False},
        {"kind": "add_comment", "text": "Team: customer_service", "mention_user_ids": ["usr-1"], "dry_run": False},
        {"kind": "send_message", "text": "This inquiry has been routed...", "dry_run": False},
    ]

    def fake_run_escalation_lane(ctx, item, *, dry_run=False):
        return {"arm": "human-intervention", "clarify": None, "actions": lane_actions, "pending": None}

    monkeypatch.setattr(engine_mod, "run_escalation_lane", fake_run_escalation_lane)

    envelope = Envelope(
        contact={"id": contact_id, "phone": "+60000000099", "custom_fields": []},
        message={
            "event_type": "message.received",
            "contact": {"id": contact_id},
            "message": {
                "messageId": "ZZT-esc-engine-msg-1",
                "contactId": contact_id,
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": "I need to speak to a human"},
            },
        },
    )

    result = engine_mod.run_turn(envelope, session_factory=session_factory)

    assert result.branch_kind == "out_of_scope"
    assert result.delegate is None
    assert result.status == "done"
    assert result.actions == lane_actions

    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
    assert row.status == "done", row.error
    assert row.stage == "replied"
    stages = [r["stage"] for r in row.trace]
    assert stages == ["received", "understood", "access", "routed", "looked_up", "replied"]
    assert all(r["status"] == "ok" for r in row.trace)


def test_out_of_scope_seam_failure_fails_at_looked_up_with_no_partial_assignment(
    session_factory, monkeypatch
) -> None:
    import json as _json

    from sqlalchemy import text

    from app.models.chatbot_turn import ChatbotTurn
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.contracts import Envelope
    from app.services.chatbot.head import parser as parser_mod

    contact_id = "ZZT-esc-engine-fail-1"
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": contact_id, "phone": "+60000000098", "sv": _json.dumps({"variables": {}})},
    )
    db.commit()

    def fake_resolve_config(db, *, current_date):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test"
        )

    escalation_qf = {
        "message_type": "request_for_help",
        "intent_hint": "check_product",
        "domain_hint": "master_products",
        "scope_intent": "specific",
        "is_affirmative": None,
        "user_goal": "wants a human",
        "access_levels": [],
        "broaden_axis": None,
        "date_mode": None,
        "date_filter_start": None,
        "date_filter_end": None,
        "match_mode": "and",
        "demand_qty": None,
        "entities": [],
        "entity_op": "replace_combine",
        "scope_exclusive": False,
        "requested_attributes": [],
        "contains_flyer": False,
        "reference_positions": [],
        "reference_target": None,
        "person_mention": None,
        "is_active": None,
        "order_status": None,
        "correction": False,
        "routing": {"suggested_team": "customer_service", "suggested_agent": "general_enquiries", "team_source": "inferred"},
        "escalation": {"is_escalation_confirmation": True, "company_pick": None},
    }

    def fake_parse(config, user_block):
        return escalation_qf

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", fake_parse)
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True,
            "decision": "allow",
            "agent_name": "General Enquiries",
            "attributes": None,
            "all_attributes_allowed": None,
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")

    def fake_run_escalation_lane_boom(ctx, item, *, dry_run=False):
        raise RuntimeError("next-assignee is unreachable")

    monkeypatch.setattr(engine_mod, "run_escalation_lane", fake_run_escalation_lane_boom)

    envelope = Envelope(
        contact={"id": contact_id, "phone": "+60000000098", "custom_fields": []},
        message={
            "event_type": "message.received",
            "contact": {"id": contact_id},
            "message": {
                "messageId": "ZZT-esc-engine-fail-msg-1",
                "contactId": contact_id,
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": "I need to speak to a human"},
            },
        },
    )

    result = engine_mod.run_turn(envelope, session_factory=session_factory)

    assert result.status == "failed"
    assert result.reply["text"] == parser_mod.PARSER_ERROR_REPLY
    assert all(a["kind"] != "assign_conversation" for a in result.actions)
    assert all(a["kind"] != "add_comment" for a in result.actions)

    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
    assert row.status == "failed"
    assert row.stage == "looked_up"
    assert "next-assignee is unreachable" in row.error
