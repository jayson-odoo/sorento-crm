"""R4 RED tests - ANSWERING a single-domain miss's open question
(PLAN-chatbot-answer-half-reattach.md; UAC AC-1700, AC-1703's tail, AC-1704).

`test_rearch_r4_bridge_miss.py` pins the WRITE side of the R4 bridge (`answer_bridge.
answer_for` does not exist on this branch yet - the bridge's miss arm is a later
coder slice). This file pins the ANSWERING side instead - `turn/apply.py::
_answer_pending` / `_answer_offer`, and the escalation lane call they feed - which is
GENERIC and already live regardless of who eventually mints the Pending. Every
scenario below therefore seeds the open question directly onto
`respond_contacts.session_vars.open_question` in the CURRENT five-key wire shape
(`session_state.FIVE_KEYS`), the same convention `test_r3_pending_end_to_end.py::
TestAnAbandonedMemberOfferStopsConfirming` uses for the same reason (composing a real
roster needs machinery this file is not about) - never the legacy nested `variables`
shape, which `session_state._legacy_option` cannot carry a `respond_user_id` through
at all (measured: it copies only `code`/`uuid`/`uuids`/`name`/`stamp` to the option and
`value`/`team` to its payload).

`member_offer` options are seeded in the EXACT shape `test_rearch_r4_bridge_miss.py::
TestMemberOfferPendingIsMintedByTheBridge` already pins for the bridge's own write side
(`label`, `payload.respond_user_id`) - a coder landing that write side later does not
have to reconcile two different option shapes for the same Pending kind.

Driven through `engine.run_turn` directly (`_stub_parser` + `_envelope`, both reused
from `test_r3_pending_end_to_end.py`) rather than the heavier `_run_turn` harness
(`test_outstanding_lane.py`) for the escalation-arm scenarios (1, 2, 4): answering an
ESCALATION_OFFER_KINDS pending (`_answer_offer`) short-circuits BEFORE any fetch, so no
resolver/fetch wiring is needed - only `engine_mod.run_escalation_lane` is monkeypatched
as a spy (the exact pattern `test_s5_escalation_seams.py` already uses for the same
seam), capturing `(ctx, item)` without needing the escalation lane's own DB-backed
round-robin/Team/AgentTeam machinery. Scenarios 3 and 5 exercise a REAL fetch and reuse
`test_outstanding_lane.py`'s own `_enable_business_lane` / `_wire_business_services` /
`_capturing_mcp` / `_resolve_services` helpers directly.

Postgres only (`session_factory`, blank schema). Every row seeded here.

**Measured facts (this session, 20 Sep 2026), each pinned below with its own citation**:

1. AC-1700 "position assigns that member": `turn/apply.py::_answer_offer` (~214-264)
   threads `option_payload.get("team") or pending.team` into `trace.team`, which
   `turn_runtime.lane_parse_output`'s own `accepted_team` chain carries into
   `ctx.parse.output.routing.suggested_team` - but NOTHING threads an assignee: the
   `Trace` dataclass (`turn/plan.py`) has no assignee field at all, and
   `lane_parse_output` never touches `ctx.parse.output.escalation.preferred_assignee_id`
   (main's own OLD mechanism, `head/output_exchange.py:~3626`, which
   `lanes/escalation.py::escalation_context:219` still reads and which the new engine
   never populates). RED.
2. AC-1700 "yes assigns automatically": the SAME `_answer_offer` accept path, with no
   `decision.positions` at all, leaves `option_payload` empty and threads only
   `pending.team` - already correct, no assignee is set. GREEN CONTROL.
3. AC-1700 "all dates re-runs for the same carried customer": measured live via a
   throwaway debug probe (written, run, deleted, never committed) - a plain
   `business_query` naming the order domain with NO new entities and NO date fields,
   while `focus.customers` already carries the customer and an UNRELATED `member_offer`
   is still open, runs `crm_order_management_orders_list` scoped to the SAME carried
   customer uuid and with no date args at all - the miss/offer machinery does not
   swallow it. GREEN CONTROL (the generic CARRY path already lets the message plan
   itself, per `turn/decide.py`'s own module docstring: "CARRY... the message runs as
   itself").
4. AC-1703 tail, accept: `turn/apply.py:604-614` (Item 8) ALREADY threads a bare "yes"
   over ANY pending whose `payload.escalate_offered is True` to the escalation lane with
   `pending.team`, regardless of pending.kind - so a did-you-mean ROSTER's own attached
   escalate offer already escalates correctly. GREEN CONTROL.
5. AC-1703 tail, decline: `test_sales_report_lane.py::TestDetailOfferLifecycle::
   test_a_decline_closes_it_with_the_offer_declined_copy` already documents that
   `turn/apply.py:617`'s decline branch sends a NON-roster offer kind (kind in
   `OFFER_KINDS`) to the generic `escalation_declined` lane ("Escalation declined."),
   never R22(a)'s specific `offer_declined` registry copy ("Okay, noted."). Measured
   here: a ROSTER kind (`product_pick`) is NEVER in `OFFER_KINDS` (`OFFER_KINDS =
   PENDING_KINDS - ROSTER_KINDS`), so a decline over THIS shape takes the OTHER branch
   at `turn/apply.py:629` (`return focus, None, None, False`) - no lane at all, not even
   the generic copy; the pending clears silently and the message is planned as itself.
   RED (production is expected to show SOME offer-declined acknowledgement).
6. AC-1704, continuing the original ask: measured via a throwaway debug probe (written,
   run, deleted). A POSITION answer over a `product_pick` roster whose `payload.domain`
   is seeded correctly ALREADY re-runs the fetch in the ORIGINAL domain, scoped to the
   picked option's own uuid (`turn/apply.py`'s contract-121 mechanism, lines ~581-602) -
   for the `incoming` domain. GREEN CONTROL. A TYPED CODE answer (the customer retypes
   the offered label instead of its number) over the SAME roster reaches
   `decide()`'s `_positions_by_label` match (so `decision.positions` IS populated, same
   as a position pick) - but the fetch that actually runs is scoped to NOTHING (the
   typed entity's own FRESH, uuid-less resolution attempt), never the roster's own
   already-resolved uuid: measured, the captured MCP call shows
   `skipped: [{"code": "SRTWT165-FTX", "reason": "missing_or_bad_uuid"}]` and the
   composed reply says "I could not find SRTWT165-FTX" even though the SAME product's
   real uuid sits right there on the answered option. RED. The `product_attachment`
   domain fails BOTH ways (position AND typed code): measured, `CAPTURED == []` (no
   fetch at all) and the reply RE-PRINTS the identical roster question
   ("product_attachment search needs to be more specific. Multiple matches found.
   Please choose:") instead of continuing - a domain-specific gap distinct from (and
   worse than) the `incoming`+code case. RED.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output
from tests.chatbot.test_r3_pending_end_to_end import _session_of, _stub_parser
from tests.chatbot.test_outstanding_lane import (
    _capturing_mcp,
    _enable_business_lane,
    _resolve_services,
    _wire_business_services,
)


def _write_session_vars(session_factory, sv: dict[str, Any]) -> None:
    db = session_factory()
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE respond_io_id = :cid"),
        {"cid": str(CONTACT_ID), "sv": json.dumps(sv)},
    )
    db.commit()


def _seed_bare_contact(session_factory) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": str(CONTACT_ID), "phone": "+60000000009", "sv": json.dumps({})},
    )
    db.commit()


def _member_option(
    position: int, *, label: str, uuid: str, respond_user_id: str, team: str | None = None
) -> dict[str, Any]:
    """The shape `test_rearch_r4_bridge_miss.py::TestMemberOfferPendingIsMintedByTheBridge`
    already pins for the bridge's own WRITE side (`label`, `payload.respond_user_id`)."""
    payload: dict[str, Any] = {"respond_user_id": respond_user_id}
    if team:
        payload["team"] = team
    return {
        "position": position,
        "label": label,
        "uuid": uuid,
        "entity_type": "member_offer",
        "payload": payload,
    }


def _seed_member_offer(
    session_factory,
    *,
    options: list[dict[str, Any]],
    team: str = "customer_service",
    domain: str = "order",
    asked_at_turn: int = 1,
) -> None:
    _write_session_vars(
        session_factory,
        {
            "open_question": {
                "kind": "member_offer",
                "expects": "pick",
                "options": options,
                "team": team,
                "asked_at_turn": asked_at_turn,
                "payload": {"domain": domain},
            }
        },
    )


def _fake_escalation_lane(calls: list[tuple[Any, Any]]):
    def fake_run_escalation_lane(ctx, item, *, dry_run=False, session_factory=None):
        calls.append((ctx, item))
        return {"arm": "assign", "actions": [], "pending": None}

    return fake_run_escalation_lane


def _run(session_factory, monkeypatch, *, qf: dict[str, Any], text_body: str, msg_id: str):
    _stub_parser(monkeypatch, qf)
    envelope = _envelope(is_test=False)
    envelope.message["message"]["messageId"] = msg_id
    envelope.message["message"]["message"]["text"] = text_body
    return engine_mod.run_turn(envelope, session_factory=session_factory)


# --------------------------------------------------------------------------- #
# AC-1700 - answering a member_offer miss
# --------------------------------------------------------------------------- #


class TestAC1700AnsweringAMemberOfferMiss:
    def test_a_position_assigns_that_member(self, session_factory, monkeypatch) -> None:
        _seed_bare_contact(session_factory)
        _seed_member_offer(
            session_factory,
            options=[
                _member_option(1, label="Ah Chong", uuid="u1", respond_user_id="ru1"),
                _member_option(2, label="Siti", uuid="u2", respond_user_id="ru2"),
            ],
        )
        calls: list[tuple[Any, Any]] = []
        monkeypatch.setattr(engine_mod, "run_escalation_lane", _fake_escalation_lane(calls))

        result = self._run_position(session_factory, monkeypatch, "1", "zzt-r4-member-position")

        assert result.branch_kind == "out_of_scope", (
            f"a position over an open member_offer must reach the escalation lane: "
            f"branch_kind={result.branch_kind!r} error={result.error!r}"
        )
        assert len(calls) == 1, f"the escalation lane must be called exactly once: {calls}"
        ctx, _item = calls[0]
        output = ((ctx.get("parse") or {}).get("output")) or {}
        assert (output.get("routing") or {}).get("suggested_team") == "customer_service", (
            output.get("routing")
        )
        assignee_id = (output.get("escalation") or {}).get("preferred_assignee_id")
        assert assignee_id == "ru1", (
            "AC-1700: a position over an open member_offer must assign THAT member "
            "(respond_user_id 'ru1' for Ah Chong, position 1) - the escalation call "
            f"carries no assignee at all today (escalation={output.get('escalation')!r}); "
            "turn/apply.py::_answer_offer only ever threads pending.team through, never "
            "the picked option's own payload.respond_user_id"
        )
        stored = _session_of(session_factory)
        assert (stored.get("open_question") or {}).get("kind") != "member_offer", (
            "the Pending must close once a position answers it"
        )

    def test_yes_assigns_automatically(self, session_factory, monkeypatch) -> None:
        """GREEN CONTROL: `_answer_offer`'s bare-yes accept path already threads only
        `pending.team`, never a specific assignee, since `option_payload` is empty when
        no position was picked."""
        _seed_bare_contact(session_factory)
        _seed_member_offer(
            session_factory,
            options=[
                _member_option(1, label="Ah Chong", uuid="u1", respond_user_id="ru1"),
                _member_option(2, label="Siti", uuid="u2", respond_user_id="ru2"),
            ],
        )
        calls: list[tuple[Any, Any]] = []
        monkeypatch.setattr(engine_mod, "run_escalation_lane", _fake_escalation_lane(calls))

        qf = _parser_output(
            message_type="casual", intent_hint=None, domain_hint=None, entities=[],
            is_affirmative=True,
        )
        result = self._run_qf(session_factory, monkeypatch, qf, "yes", "zzt-r4-member-yes")

        assert result.branch_kind == "out_of_scope", (
            f"a bare yes over an open member_offer must reach the escalation lane: "
            f"branch_kind={result.branch_kind!r} error={result.error!r}"
        )
        assert len(calls) == 1, f"the escalation lane must be called exactly once: {calls}"
        ctx, _item = calls[0]
        output = ((ctx.get("parse") or {}).get("output")) or {}
        assert (output.get("routing") or {}).get("suggested_team") == "customer_service"
        assignee_id = (output.get("escalation") or {}).get("preferred_assignee_id")
        assert assignee_id is None, (
            "AC-1700: a bare 'yes' must assign AUTOMATICALLY (round robin), never a "
            f"specific member - got preferred_assignee_id={assignee_id!r}"
        )
        stored = _session_of(session_factory)
        assert (stored.get("open_question") or {}).get("kind") != "member_offer"

    def test_all_dates_reruns_the_order_fetch_for_the_carried_customer(
        self, session_factory, monkeypatch
    ) -> None:
        """GREEN CONTROL, measured live (see module docstring point 3): a business_query
        naming no new entities and no date filter, over an UNRELATED open member_offer,
        with a customer already carried on focus, re-runs the order fetch scoped to that
        SAME carried customer with no date args - the offer never swallows it."""
        from app.services.chatbot.turn.state import Focus, focus_to_wire

        _seed_bare_contact(session_factory)
        customer_uuid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        focus = Focus(
            customers=[{"uuid": customer_uuid, "hint": "customer", "current_message": False}],
            domains=["order"],
        )
        _write_session_vars(
            session_factory,
            {
                "focus": focus_to_wire(focus),
                "open_question": {
                    "kind": "member_offer",
                    "expects": "pick",
                    "options": [
                        _member_option(1, label="Ah Chong", uuid="u1", respond_user_id="ru1"),
                    ],
                    "team": "customer_service",
                    "asked_at_turn": 1,
                    "payload": {"domain": "order"},
                },
            },
        )
        _enable_business_lane(session_factory)
        call, captured = _capturing_mcp({"has_result": False, "items": []})
        _wire_business_services(monkeypatch, resolve_services=_resolve_services({}), mcp_call=call)

        qf = _parser_output(
            message_type="business_query",
            intent_hint="check_order",
            domain_hint="order",
            entities=[],
            date_filter_start=None,
            date_filter_end=None,
            routing={
                "suggested_team": "customer_service",
                "suggested_agent": "order_enquiries",
                "team_source": "parser",
            },
        )
        result = self._run_qf(session_factory, monkeypatch, qf, "all dates", "zzt-r4-all-dates")

        assert result.error is None, result.error
        assert len(captured) == 1, (
            f"'all dates' must re-run the order fetch exactly once: {captured}"
        )
        name, args = captured[0]
        assert name == "crm_order_management_orders_list", (name, captured)
        assert args.get("customer_ids") == [customer_uuid], (
            "the re-run must stay scoped to the SAME carried customer, not swallowed "
            f"by the unrelated open member_offer: {args!r}"
        )
        assert not args.get("order_date_from") and not args.get("order_date_to"), (
            "'all dates' must clear the date window entirely: {args!r}".format(args=args)
        )

    def _run_position(self, session_factory, monkeypatch, position_text: str, msg_id: str):
        qf = _parser_output(
            message_type="casual", intent_hint=None, domain_hint=None, entities=[],
            reference_positions=[int(position_text)],
        )
        return self._run_qf(session_factory, monkeypatch, qf, position_text, msg_id)

    def _run_qf(self, session_factory, monkeypatch, qf, text_body, msg_id):
        return _run(session_factory, monkeypatch, qf=qf, text_body=text_body, msg_id=msg_id)


# --------------------------------------------------------------------------- #
# AC-1703 tail - escalating over a did-you-mean roster's own attached offer
# --------------------------------------------------------------------------- #


class TestAC1703EscalateOverARoster:
    """A did-you-mean `product_pick` roster with `payload.escalate_offered is True`.
    The accept half is a GREEN CONTROL (Item 8, `turn/apply.py:604-614`, already threads
    a bare 'yes' to the escalation lane with `pending.team` for ANY pending carrying that
    flag). The decline half is measured RED against `test_sales_report_lane.py::
    TestDetailOfferLifecycle::test_a_decline_closes_it_with_the_offer_declined_copy`'s
    own documented seam (see module docstring point 5)."""

    def _seed_roster(self, session_factory) -> None:
        _write_session_vars(
            session_factory,
            {
                "open_question": {
                    "kind": "product_pick",
                    "expects": "pick",
                    "options": [
                        {
                            "position": 1, "label": "SRTWT165-FTX", "uuid": "prod-dym-1",
                            "uuids": ["prod-dym-1"], "entity_type": "product", "payload": {},
                        },
                        {
                            "position": 2, "label": "SRTWT165-FTY", "uuid": "prod-dym-2",
                            "uuids": ["prod-dym-2"], "entity_type": "product", "payload": {},
                        },
                    ],
                    "team": "purchasing",
                    "asked_at_turn": 1,
                    "payload": {"domain": "incoming", "escalate_offered": True},
                }
            },
        )

    def test_a_yes_escalates_to_the_pending_team(self, session_factory, monkeypatch) -> None:
        _seed_bare_contact(session_factory)
        self._seed_roster(session_factory)
        calls: list[tuple[Any, Any]] = []
        monkeypatch.setattr(engine_mod, "run_escalation_lane", _fake_escalation_lane(calls))

        qf = _parser_output(
            message_type="casual", intent_hint=None, domain_hint=None, entities=[],
            is_affirmative=True,
        )
        result = _run(session_factory, monkeypatch, qf=qf, text_body="yes", msg_id="zzt-r4-roster-yes")

        assert result.branch_kind == "out_of_scope", (
            f"a yes over a did-you-mean roster's escalate offer must reach the "
            f"escalation lane: branch_kind={result.branch_kind!r} error={result.error!r}"
        )
        assert len(calls) == 1, calls
        ctx, _item = calls[0]
        output = ((ctx.get("parse") or {}).get("output")) or {}
        assert (output.get("routing") or {}).get("suggested_team") == "purchasing", (
            "the escalation must route to the ROSTER's own team (purchasing), "
            f"got {output.get('routing')!r}"
        )

    def test_a_decline_gets_the_offer_declined_copy_not_silence(
        self, session_factory, monkeypatch
    ) -> None:
        _seed_bare_contact(session_factory)
        self._seed_roster(session_factory)
        calls: list[tuple[Any, Any]] = []
        monkeypatch.setattr(engine_mod, "run_escalation_lane", _fake_escalation_lane(calls))

        qf = _parser_output(
            message_type="casual", intent_hint=None, domain_hint=None, entities=[],
            is_affirmative=False,
        )
        result = _run(
            session_factory, monkeypatch, qf=qf, text_body="no thanks", msg_id="zzt-r4-roster-decline"
        )

        assert calls == [], "a decline must never reach the escalation lane"
        stored = _session_of(session_factory)
        assert (stored.get("open_question") or {}).get("kind") != "product_pick", (
            "the Pending must close on a decline either way"
        )
        reply_text = (result.reply or {}).get("text") or ""
        assert reply_text.strip() == "Okay, noted.", (
            "AC-1703: declining a did-you-mean roster's attached escalate offer must "
            "close it with R22(a)'s own offer-declined registry copy ('Okay, noted.') - "
            "measured: turn/apply.py's decline branch (line ~617) only reaches the "
            "escalation_declined lane when pending.kind is in OFFER_KINDS, and a ROSTER "
            "kind (product_pick) is NEVER in OFFER_KINDS (OFFER_KINDS = PENDING_KINDS - "
            f"ROSTER_KINDS), so no lane at all is set and no acknowledgement is composed: "
            f"got branch_kind={result.branch_kind!r} reply={reply_text!r}"
        )


# --------------------------------------------------------------------------- #
# AC-1704 - continuing the ORIGINAL ask after a did-you-mean pick
# --------------------------------------------------------------------------- #


class TestAC1704ContinuingTheOriginalAsk:
    """A `product_pick` roster whose `payload.domain` is seeded correctly (bypassing
    the bridge's own write-side gap reported separately under item A5). Measured live
    (module docstring point 6): the POSITION path already works for `incoming`; the
    TYPED-CODE path loses the roster's own resolved uuid even for `incoming`; the
    `product_attachment` domain fails BOTH ways."""

    _OPTIONS = [
        {
            "position": 1, "label": "SRTWT165-FTX", "uuid": "11111111-1111-1111-1111-111111111111",
            "uuids": ["11111111-1111-1111-1111-111111111111"], "code": "SRTWT165-FTX",
            "entity_type": "product", "payload": {},
        },
        {
            "position": 2, "label": "SRTWT165-FTY", "uuid": "22222222-2222-2222-2222-222222222222",
            "uuids": ["22222222-2222-2222-2222-222222222222"], "code": "SRTWT165-FTY",
            "entity_type": "product", "payload": {},
        },
    ]

    def _seed(self, session_factory, *, domain: str) -> None:
        _seed_bare_contact(session_factory)
        _write_session_vars(
            session_factory,
            {
                "open_question": {
                    "kind": "product_pick",
                    "expects": "pick",
                    "options": self._OPTIONS,
                    "team": "purchasing",
                    "asked_at_turn": 1,
                    "payload": {"domain": domain, "escalate_offered": True},
                }
            },
        )
        _enable_business_lane(session_factory)

    def test_a_position_continues_the_original_incoming_ask_with_the_picked_uuid(
        self, session_factory, monkeypatch
    ) -> None:
        """GREEN CONTROL."""
        self._seed(session_factory, domain="incoming")
        call, captured = _capturing_mcp({"has_result": False, "items": []})
        _wire_business_services(monkeypatch, resolve_services=_resolve_services({}), mcp_call=call)

        qf = _parser_output(
            message_type="casual", intent_hint=None, domain_hint=None, entities=[],
            reference_positions=[1],
        )
        result = _run(session_factory, monkeypatch, qf=qf, text_body="1", msg_id="zzt-r4-ac1704-pos-incoming")

        assert result.error is None, result.error
        product_ids = {u for _name, args in captured for u in (args.get("product_ids") or [])}
        assert "11111111-1111-1111-1111-111111111111" in product_ids, (
            f"a position over the roster must continue the fetch scoped to THAT "
            f"option's own uuid: {captured!r}"
        )

    def test_a_typed_code_loses_the_rosters_own_resolved_uuid_on_incoming(
        self, session_factory, monkeypatch
    ) -> None:
        """RED. `decide()`'s `_positions_by_label` DOES recognise "SRTWT165-FTX" as
        answering position 1 (same as a bare "1" would) - but the fetch that then runs
        is scoped to the message's own FRESH, uuid-less resolution of the typed text,
        never to the roster's own already-resolved uuid sitting on the matched option."""
        self._seed(session_factory, domain="incoming")
        call, captured = _capturing_mcp({"has_result": False, "items": []})
        _wire_business_services(monkeypatch, resolve_services=_resolve_services({}), mcp_call=call)

        qf = _parser_output(
            message_type="business_query", intent_hint=None, domain_hint=None,
            entities=[
                {
                    "raw": "SRTWT165-FTX", "hint": "product", "canonical_code": "SRTWT165-FTX",
                    "current_message": True, "confident": True,
                }
            ],
        )
        result = _run(
            session_factory, monkeypatch, qf=qf, text_body="SRTWT165-FTX",
            msg_id="zzt-r4-ac1704-code-incoming",
        )

        assert result.error is None, result.error
        product_ids = {u for _name, args in captured for u in (args.get("product_ids") or [])}
        assert "11111111-1111-1111-1111-111111111111" in product_ids, (
            "AC-1704: replying with the OFFERED CODE must continue the original ask "
            "using that option's own already-resolved uuid, exactly like a position "
            f"pick does - instead the fetch ran with no matching product uuid at all "
            f"(captured={captured!r}, reply={(result.reply or {}).get('text')!r})"
        )

    @pytest.mark.parametrize("answer_mode", ["position", "code"])
    def test_product_attachment_domain_reasks_instead_of_continuing(
        self, session_factory, monkeypatch, answer_mode: str
    ) -> None:
        """RED, both ways. `product_attachment` never reaches a fetch at all - the SAME
        did-you-mean roster question is re-printed verbatim, matching R3's own measured
        finding that `if_incoming_picker` (and everything built on its exit) checks
        `gate_debug.domain == "incoming"` literally and falls through for every other
        domain, `product_attachment` included."""
        self._seed(session_factory, domain="product_attachment")
        call, captured = _capturing_mcp({"has_result": False, "items": []})
        _wire_business_services(monkeypatch, resolve_services=_resolve_services({}), mcp_call=call)

        if answer_mode == "position":
            qf = _parser_output(
                message_type="casual", intent_hint=None, domain_hint=None, entities=[],
                reference_positions=[1],
            )
            text_body = "1"
        else:
            qf = _parser_output(
                message_type="business_query", intent_hint=None, domain_hint=None,
                entities=[
                    {
                        "raw": "SRTWT165-FTX", "hint": "product", "canonical_code": "SRTWT165-FTX",
                        "current_message": True, "confident": True,
                    }
                ],
            )
            text_body = "SRTWT165-FTX"

        result = _run(
            session_factory, monkeypatch, qf=qf, text_body=text_body,
            msg_id=f"zzt-r4-ac1704-{answer_mode}-attachment",
        )

        assert result.error is None, result.error
        reply_text = (result.reply or {}).get("text") or ""
        assert captured, (
            f"AC-1704: answering the roster ({answer_mode}) must continue the ORIGINAL "
            f"product_attachment ask with a real fetch - instead nothing was called at "
            f"all and the same roster question was re-printed: {reply_text!r}"
        )
