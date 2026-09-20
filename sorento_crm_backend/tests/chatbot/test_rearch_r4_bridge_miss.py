"""R4 RED tests - the MISS half of the production answer half
(PLAN-chatbot-answer-half-reattach.md slice R4; UAC AC-1680, AC-1681 (one raw_fragment
seam), AC-1683, AC-1684, AC-1699 to AC-1705's pytest-reachable subset).

**Contract pinned by the captain's brief, 20 Sep 2026** (measured against this branch's
head, before R4 lands):

1. `turn_runtime.make_tool_runner`'s `runner(domain, spec)` must carry the UNTOUCHED
   `business.run_fetch` fragment through `turn_runtime.envelope_of` under a new key
   `"raw_fragment"`. MEASURED TODAY: `envelope_of` (`turn_runtime.py:1751`) builds a
   REDUCED dict (`domain`, `denied`, `entities`, `figures`, `files`, `miss`, `has_result`,
   `unresolved`, `tool_has_result`, `error`, `lane_text`, `header_override`, `lane_ask`,
   ...) and has no `raw_fragment` key at all - `TestRawFragmentMissingToday` pins this as
   the RED starting point.
2. `app.services.chatbot.answer_bridge.answer_for(payload, *, envelope, parser, ctx,
   canned, services, db, asked_at_turn, roster_caps=None) -> turn.compose.Answer | None`
   (this tester's own name, `answer_for`, chosen to sit beside R3's `question_for` on the
   SAME module - `answer_bridge.py`, outside `turn/`, per R3's own captain ruling on the
   purity guard). Two miss triggers, both measured off `lanes/business/__init__.py::
   complete_answer:1650`:
     (a) `payload["_exit_kind"] == "not_found"` (the resolver's own exit - nothing
         resolved at all), `fetch=None`.
     (b) `envelope["raw_fragment"]` is the error arm business.run_fetch mints via
         `_error_fragment(..., outcome="not_found")` (`__init__.py:701-723`: `{"kind":
         "error", "_fetch_arm": "error", "error": ..., "fetch": item, "outcome":
         "not_found"}`) - a genuine absence (H11's zero-tool case), not an infrastructure
         failure. `payload` handed to the miss chain is `{**payload, "fetch": fetch_item}`,
         mirroring `complete_answer`'s own `delegate_payload` shape.
   Both computed via calling the REAL production chain
   (`answer.not_found_error_message` -> `miss_suggest.run_miss_lane` -> `tail.outcome.
   escalate_catalog` -> `tail.outcome.build_outcome` -> `tail.reply_ladder.compose_reply`),
   never retyped copy - `_expected_miss_text` below is that chain, reusable by every test
   in this file.
   `answer_for` returns `None` for: a hit-shaped envelope (R5's own arm), an
   `access_denied` error arm (that refusal path is unchanged - `_error_fragment(...,
   outcome="access_denied")` / `DOMAIN_GRANT_REQUIRED`), and an infrastructure error arm
   (`outcome` neither `not_found` nor `access_denied` - `complete_answer:1631` RAISES on
   this arm today; a caller reaching it here must not render it as a miss). Multi-domain
   plans are a CALLER-side decision (the turn engine never calls the bridge for those,
   per the plan's Hazards section) and are graded at the engine level
   (`test_rearch_r4_miss_engine.py::AC-1708`), not inside this function's own unit tests.
3. `app.services.chatbot.tail.reply.compose_from_fragments(item, ctx, canned, values, *,
   db) -> dict` is the ONE function `engine.run_tail`'s own lines 3176-3201 already are
   (measured verbatim below in `_manual_compose_from_fragments`, this test file's own copy
   of that exact sequence: `CARRIER_FIELDS` -> `escalate_catalog` -> `cs_offer_gate` ->
   `cs_roster_plan` -> `fetch_rosters` -> `build_cs_member_offer` -> `build_outcome` ->
   `compose_reply`) - extracted so BOTH `engine.run_tail` (canned lanes) and the bridge
   (business misses) call the SAME code. Pinned by: the function exists with this
   signature; it is called from `engine.run_tail` (spy); it is called from the bridge for
   a member-offer-worthy miss (spy); `test_replay.py` stays untouched and green (never
   edited here, never run destructively - only imported by reference in this docstring).
4. `turn.pending.ask` mints every question the bridge raises (AC-1684): a did-you-mean /
   attachment roster becomes a `product_pick` (contract-36 roster, `answered_positions`
   sticks), a CS member offer becomes `member_offer` (already in `PENDING_KINDS`, read
   side only today - `TestMemberOfferPendingIsMintedByTheBridge` is the write side), and
   `payload["domain"]` / `payload["escalate_offered"]` carry the axes AC-1699/AC-1704 need.

**Purity boundary**: this file imports `answer_bridge`, `tail.outcome`, `tail.reply_ladder`,
`tail.member_offer`, `lanes.business.answer`, `lanes.business.miss_suggest` and
`lanes.business.services` - never anything under `turn/` that the module itself may not
import (that direction is `test_rearch_r3_answer_bridge.py::TestTurnPackagePurity`'s own
guard, not duplicated here).

**Pure, stubbed payloads only** - no DB session, no real MCP call, matching R3's own
convention (`test_rearch_r3_answer_bridge.py`). Every "expected" value below is computed by
calling the real production function chain the plan names, never a retyped string.
"""
from __future__ import annotations

import importlib
import inspect
from typing import Any

import pytest

from app.services.chatbot import copy as copy_mod
from app.services.chatbot import turn_runtime
from app.services.chatbot.lanes.business import answer as answer_mod
from app.services.chatbot.lanes.business import miss_suggest as miss_mod
from app.services.chatbot.lanes.business.services import AnswerServices
from app.services.chatbot.tail import outcome as outcome_mod
from app.services.chatbot.tail import reply_ladder
from app.services.chatbot.turn import pending as pending_mod
from app.services.chatbot.turn.plan import FetchSpec
from app.services.chatbot.turn.state import Focus


def _bridge():
    try:
        return importlib.import_module("app.services.chatbot.answer_bridge")
    except ModuleNotFoundError:
        return None


def _require_answer_for():
    bridge = _bridge()
    assert bridge is not None, (
        "app.services.chatbot.answer_bridge does not exist yet (R4 needs it beside R3's "
        "own question_for)"
    )
    assert hasattr(bridge, "answer_for"), (
        "answer_bridge exists but has no answer_for(payload, *, envelope, parser, ctx, "
        "canned, services, db, asked_at_turn, roster_caps=None) function yet - the R4 miss "
        "arm (this tester's own name, answer_for)"
    )
    return bridge


def _canned():
    return copy_mod.fallback_copy()


def _ctx_for(parser: dict[str, Any]) -> dict[str, Any]:
    return {"parse": {"output": parser}, "contact": {"id": "zzt-r4-contact"}, "session": {}}


def _services(mcp_probe=None, family_fetch=None) -> AnswerServices:
    return AnswerServices(
        mcp_probe=mcp_probe or (lambda name, args: {"has_result": False, "answers": []}),
        family_fetch=family_fetch or (lambda query: {"data": []}),
    )


def _expected_miss_text(
    payload: dict[str, Any],
    *,
    parser: dict[str, Any],
    resolved: dict[str, Any],
    gate: dict[str, Any],
    services: AnswerServices,
    build_result: Any = None,
    contact_id: str = "zzt-r4-contact",
    execution_id: str = "zzt-r4-turn",
) -> tuple[str, dict[str, Any]]:
    """`_run_miss_half`'s own chain (`lanes/business/__init__.py:1868-1911`), computed via
    the REAL production functions, plus the tail's own text ladder
    (`escalate_catalog` + `build_outcome` + `compose_reply`) - never retyped copy."""
    not_found = answer_mod.not_found_error_message(
        payload, parser=parser, resolved=resolved, gate=gate
    )
    offer = miss_mod.run_miss_lane(
        not_found,
        parser=parser,
        resolved=resolved,
        gate=gate,
        services=services,
        build_result=build_result,
        contact_id=contact_id,
        space_id=None,
        execution_id=execution_id,
        dry_run=True,
    )
    lane_item = {**offer, "branch_kind": "not_found"}
    ctx = _ctx_for(parser)
    canned = _canned()
    catalog = outcome_mod.escalate_catalog(lane_item, ctx, canned, suggest_offer=offer, gate=gate)
    # `engine.run_tail`'s own CARRIER_FIELDS always puts `values["suggest_offer"]` (this
    # lane's `offer`) on the outcome map under "build-suggest-offer" - `compose_reply`'s
    # own precedence prefers ITS `suggest_response` over escalate-catalog's `response`
    # whenever `offer.suggest_offer is True` (the did-you-mean / sibling-family arms).
    built = outcome_mod.build_outcome(
        [{"json": catalog}], {"escalate-catalog": catalog, "build-suggest-offer": offer}
    )
    text = reply_ladder.compose_reply(built[0]["json"]["outcome"])["text"]
    return text, offer


def _order_parser(raw: str = "STWC26") -> dict[str, Any]:
    return {
        "domain_hint": "order",
        "intent_hint": "check_order",
        "message_type": "business_query",
        "entities": [{"raw": raw, "hint": "product", "current_message": True, "confident": True}],
        "routing": {"suggested_team": "customer_service", "suggested_agent": "general_enquiries"},
        "access_levels": [],
    }


def _resolved_nothing(raw: str) -> dict[str, Any]:
    return {"resolutions": [{"token": raw, "matches": []}], "unresolved_tokens": [raw], "tokens": [raw]}


def _gate_passed_no_scope() -> dict[str, Any]:
    return {"gate_passed": True, "compatible_entities": [], "gate_debug": {"domain": "order"}}


# --------------------------------------------------------------------------- #
# Contract item 1 - raw_fragment survives the tool runner
# --------------------------------------------------------------------------- #


class TestRawFragmentMissingToday:
    """RED starting point: `envelope_of` builds a reduced dict with no `raw_fragment` key.
    Documents the gap `TestMakeToolRunnerCarriesTheRawFragment` below closes."""

    def test_envelope_of_has_no_raw_fragment_key_today(self) -> None:
        fragment = {"kind": "result", "_fetch_arm": "result", "fetch": {"has_result": False}}
        spec = FetchSpec(domain="order", entities=[], filters={}, date_window=None)
        envelope = turn_runtime.envelope_of(fragment, spec, [])
        assert "raw_fragment" not in envelope, (
            "measured-today assertion failed: envelope_of already carries raw_fragment - "
            "re-check the module docstring's own measured fact"
        )


class TestMakeToolRunnerCarriesTheRawFragment:
    def test_runner_envelope_carries_the_untouched_business_run_fetch_fragment(
        self, monkeypatch
    ) -> None:
        from app.services.chatbot.lanes import business

        sentinel_fragment = {
            "kind": "result",
            "_fetch_arm": "result",
            "fetch": {"has_result": False, "response": "zzt sentinel"},
            "_zzt_marker": "unique-r4-sentinel",
        }
        calls: list[dict[str, Any]] = []

        def stub_run_fetch(payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            calls.append(payload)
            return dict(sentinel_fragment)

        monkeypatch.setattr(business, "run_fetch", stub_run_fetch)

        runner = turn_runtime.make_tool_runner(
            object(),
            ctx={"parse": {"output": {}}},
            verdict={"access_levels": []},
            focus=Focus(),
            compatible_entities=[
                {"raw": "STWC26", "entity_type": "product", "canonical_code": "STWC26"}
            ],
            predicate=None,
            unplaced={},
            space_id=None,
            dry_run=True,
            turn_trace=None,
        )
        spec = FetchSpec(domain="order", entities=[], filters={}, date_window=None)
        result = runner("order", spec)

        assert len(calls) == 1, (
            f"business.run_fetch must be called exactly once per runner invocation: {calls}"
        )
        assert result.get("raw_fragment") == sentinel_fragment, (
            "the runner's envelope must carry the UNTOUCHED business.run_fetch fragment "
            f"under raw_fragment: got {result.get('raw_fragment')!r}"
        )


# --------------------------------------------------------------------------- #
# Contract item 2 - answer_bridge.answer_for, the miss arm
# --------------------------------------------------------------------------- #


class TestMissArmViaResolverNotFoundExit:
    """Trigger (a): `payload["_exit_kind"] == "not_found"`, `fetch=None`."""

    def test_text_matches_the_production_miss_chain(self) -> None:
        bridge = _require_answer_for()
        parser = _order_parser()
        resolved = _resolved_nothing("STWC26")
        gate = _gate_passed_no_scope()
        services = _services()
        payload = {"resolved": resolved, "gate": gate, "_exit_kind": "not_found"}

        expected_text, _offer = _expected_miss_text(
            payload, parser=parser, resolved=resolved, gate=gate, services=services
        )
        answer = bridge.answer_for(
            payload,
            envelope=None,
            parser=parser,
            ctx=_ctx_for(parser),
            canned=_canned(),
            services=services,
            db=None,
            asked_at_turn=9,
        )
        assert answer is not None, "answer_for returned None for a resolver not_found exit"
        assert answer.text == expected_text


class TestMissArmViaErrorFetchArmNotFound:
    """Trigger (b): `envelope['raw_fragment']` is `business._error_fragment(...,
    outcome='not_found')` - a genuine absence (H11's zero-tool case)."""

    def test_text_matches_the_production_miss_chain(self) -> None:
        from app.services.chatbot.lanes import business as business_mod

        bridge = _require_answer_for()
        parser = _order_parser()
        resolved = {"resolutions": [], "unresolved_tokens": [], "tokens": []}
        gate = {"gate_passed": True, "compatible_entities": []}
        services = _services()

        error_fragment = business_mod._error_fragment(
            "no MCP tool matched this question", outcome="not_found"
        )
        fetch_item = error_fragment["fetch"]
        payload = {"resolved": resolved, "gate": gate, "_exit_kind": "continue"}
        envelope = {"raw_fragment": error_fragment}

        expected_text, _offer = _expected_miss_text(
            {**payload, "fetch": fetch_item},
            parser=parser,
            resolved=resolved,
            gate=gate,
            services=services,
        )
        answer = bridge.answer_for(
            payload,
            envelope=envelope,
            parser=parser,
            ctx=_ctx_for(parser),
            canned=_canned(),
            services=services,
            db=None,
            asked_at_turn=1,
        )
        assert answer is not None, (
            "answer_for returned None for an error-fetch-arm outcome='not_found' envelope"
        )
        assert answer.text == expected_text


class TestMissArmReturnsNoneOutsideItsOwnTerritory:
    def test_none_for_a_hit_shaped_envelope(self) -> None:
        """R5's own arm - out of scope here. A hit-shaped raw_fragment (a real result,
        has_result True) must not be rendered as a miss."""
        bridge = _require_answer_for()
        parser = _order_parser()
        payload = {"_exit_kind": "continue"}
        envelope = {
            "raw_fragment": {
                "kind": "result",
                "_fetch_arm": "result",
                "fetch": {
                    "has_result": True,
                    "answers": [{"fields": [{"label": "Product Code", "value": "STWC26"}]}],
                },
            }
        }
        answer = bridge.answer_for(
            payload,
            envelope=envelope,
            parser=parser,
            ctx=_ctx_for(parser),
            canned=_canned(),
            services=_services(),
            db=None,
            asked_at_turn=1,
        )
        assert answer is None, "a hit-shaped envelope must not be rendered by the miss arm"

    def test_none_for_access_denied_error_arm(self) -> None:
        from app.services.chatbot.lanes import business as business_mod

        bridge = _require_answer_for()
        parser = _order_parser()
        error_fragment = business_mod._error_fragment(
            "purchase_order needs the purchase_orders.placed grant, which this contact "
            "does not hold",
            outcome="access_denied",
        )
        payload = {"_exit_kind": "continue"}
        envelope = {"raw_fragment": error_fragment}
        answer = bridge.answer_for(
            payload,
            envelope=envelope,
            parser=parser,
            ctx=_ctx_for(parser),
            canned=_canned(),
            services=_services(),
            db=None,
            asked_at_turn=1,
        )
        assert answer is None, (
            "an access_denied error arm keeps its own refusal path unchanged - the miss "
            "arm must not render it"
        )

    def test_none_for_an_infrastructure_error_arm(self) -> None:
        """`outcome` neither `not_found` nor `access_denied` - `complete_answer:1631`
        RAISES on this arm today (an infrastructure failure, not an absence). The bridge
        must not quietly render it as a miss either."""
        from app.services.chatbot.lanes import business as business_mod

        bridge = _require_answer_for()
        parser = _order_parser()
        error_fragment = business_mod._error_fragment("the MCP call raised: timeout")
        payload = {"_exit_kind": "continue"}
        envelope = {"raw_fragment": error_fragment}
        answer = bridge.answer_for(
            payload,
            envelope=envelope,
            parser=parser,
            ctx=_ctx_for(parser),
            canned=_canned(),
            services=_services(),
            db=None,
            asked_at_turn=1,
        )
        assert answer is None, (
            "an infrastructure error (no outcome key) must not be rendered as a miss - "
            f"got {answer!r}"
        )


# --------------------------------------------------------------------------- #
# Contract item 3 - the shared text ladder, tail/reply.py::compose_from_fragments
# --------------------------------------------------------------------------- #


def _manual_compose_from_fragments(
    item: dict[str, Any], ctx: dict[str, Any], canned: Any, values: dict[str, Any], *, db: Any = None
) -> dict[str, Any]:
    """`engine.run_tail`'s own lines 3176-3201, copied verbatim as this test's ground
    truth - the exact sequence `compose_from_fragments` must reproduce."""
    from app.services.chatbot.tail import member_offer as member_mod

    producers: dict[str, Any] = {}
    for name, field in outcome_mod.CARRIER_FIELDS.items():
        if values.get(field) is not None:
            producers[name] = values[field]

    outcome_input: dict[str, Any] = dict(item)
    if str(item.get("branch_kind") or "") != "":
        catalog = outcome_mod.escalate_catalog(
            item,
            ctx,
            canned,
            not_found=values.get("not_found"),
            incoming_picker=values.get("incoming_picker"),
            access_choice=values.get("access_choice"),
            suggest_offer=values.get("suggest_offer"),
            gate=values.get("gate"),
            offer_hold=values.get("offer_hold"),
        )
        producers["escalate-catalog"] = catalog
        outcome_input = catalog
        if outcome_mod.cs_offer_gate(catalog, ctx, values.get("gate")):
            plan = member_mod.cs_roster_plan(values.get("gate"))
            rosters = member_mod.fetch_rosters(db, plan, ctx)
            offer = member_mod.build_cs_member_offer(catalog, plan, rosters)
            producers["cs-roster-plan"] = plan
            producers["build-cs-member-offer"] = offer
            outcome_input = offer

    outcome_items = outcome_mod.build_outcome([{"json": outcome_input}], producers)
    outcome = outcome_items[0]["json"].get("outcome") or {}
    composed = reply_ladder.compose_reply(outcome)
    return {
        "text": composed.get("text"),
        "quick_replies": composed.get("quick_replies"),
        "result_set": composed.get("result_set") or [],
    }


class TestComposeFromFragmentsExists:
    def _module(self):
        try:
            return importlib.import_module("app.services.chatbot.tail.reply")
        except ModuleNotFoundError:
            pytest.fail(
                "app.services.chatbot.tail.reply does not exist yet - R4 needs "
                "compose_from_fragments(item, ctx, canned, values, *, db) extracted out "
                "of engine.run_tail's own lines 3176-3201"
            )

    def test_module_and_signature(self) -> None:
        mod = self._module()
        assert hasattr(mod, "compose_from_fragments"), (
            "tail.reply exists but has no compose_from_fragments function yet"
        )
        sig = inspect.signature(mod.compose_from_fragments)
        for name in ("item", "ctx", "canned", "values", "db"):
            assert name in sig.parameters, (
                f"compose_from_fragments is missing the {name!r} parameter: {sig}"
            )

    def test_matches_the_manual_chain_for_a_plain_miss_with_no_member_offer(self) -> None:
        mod = self._module()
        parser = _order_parser()
        parser["routing"] = {"suggested_team": "warehouse", "suggested_agent": "stock_enquiries"}
        gate = _gate_passed_no_scope()
        resolved = _resolved_nothing("STWC26")
        not_found = answer_mod.not_found_error_message(
            {}, parser=parser, resolved=resolved, gate=gate
        )
        item = {**not_found, "branch_kind": "not_found"}
        ctx = _ctx_for(parser)
        canned = _canned()
        values = {
            "not_found": not_found,
            "incoming_picker": None,
            "access_choice": None,
            "suggest_offer": not_found,
            "gate": gate,
            "offer_hold": None,
        }
        expected = _manual_compose_from_fragments(item, ctx, canned, values, db=None)
        got = mod.compose_from_fragments(item, ctx, canned, values, db=None)
        assert got.get("text") == expected["text"], (got.get("text"), expected["text"])
        assert got.get("result_set") == expected["result_set"]

    def test_matches_the_manual_chain_including_the_cs_member_offer(self, monkeypatch) -> None:
        """`cs_offer_gate` fires: routing names customer_service/order_enquiries, and the
        gate carries no require_specific. `fetch_rosters` is monkeypatched (this is a pure
        unit test, no DB session)."""
        from app.services.chatbot.tail import member_offer as member_mod

        mod = self._module()
        parser = _order_parser()  # already customer_service / general_enquiries
        parser["routing"] = {"suggested_team": "customer_service", "suggested_agent": "order_enquiries"}
        gate = _gate_passed_no_scope()
        resolved = _resolved_nothing("STWC26")
        not_found = answer_mod.not_found_error_message(
            {}, parser=parser, resolved=resolved, gate=gate
        )
        item = {**not_found, "branch_kind": "not_found"}
        ctx = _ctx_for(parser)
        canned = _canned()
        values = {
            "not_found": not_found,
            "incoming_picker": None,
            "access_choice": None,
            "suggest_offer": not_found,
            "gate": gate,
            "offer_hold": None,
        }

        def stub_fetch_rosters(db, plan, ctx):
            return [{"body": [{"user_id": "u1", "respond_user_id": "ru1", "name": "Ah Chong"}]}]

        monkeypatch.setattr(member_mod, "fetch_rosters", stub_fetch_rosters)
        expected = _manual_compose_from_fragments(item, ctx, canned, values, db=None)
        got = mod.compose_from_fragments(item, ctx, canned, values, db=None)
        assert "Ah Chong" in (expected["text"] or ""), (
            "test setup sanity: the manual chain itself must show the CS member offer"
        )
        assert got.get("text") == expected["text"], (got.get("text"), expected["text"])


class TestBridgeCallsComposeFromFragments:
    def test_bridge_calls_it_exactly_once_for_a_member_offer_miss(self, monkeypatch) -> None:
        mod = self._reply_mod()
        calls: list[Any] = []
        real = mod.compose_from_fragments

        def _spy(item, ctx, canned, values, *, db=None):
            calls.append((item, values))
            return real(item, ctx, canned, values, db=db)

        monkeypatch.setattr(mod, "compose_from_fragments", _spy)

        bridge = _require_answer_for()
        parser = _order_parser()
        parser["routing"] = {"suggested_team": "customer_service", "suggested_agent": "order_enquiries"}
        resolved = _resolved_nothing("STWC26")
        gate = _gate_passed_no_scope()
        services = _services()
        payload = {"resolved": resolved, "gate": gate, "_exit_kind": "not_found"}
        bridge.answer_for(
            payload,
            envelope=None,
            parser=parser,
            ctx=_ctx_for(parser),
            canned=_canned(),
            services=services,
            db=None,
            asked_at_turn=1,
        )
        assert len(calls) == 1, (
            f"the bridge must produce its miss text via tail.reply.compose_from_fragments "
            f"exactly once: {len(calls)} calls"
        )

    def _reply_mod(self):
        return importlib.import_module("app.services.chatbot.tail.reply")


# --------------------------------------------------------------------------- #
# Contract item 4 - Pending minted via turn.pending.ask
# --------------------------------------------------------------------------- #


def _dym_incoming_scenario() -> tuple[dict[str, Any], dict[str, Any], AnswerServices]:
    """A did-you-mean over an unplaced hyphenated code, domain incoming (F8's own shape,
    AC-1703/AC-1704): one candidate answers "has incoming", the other does not.

    MEASURED (this tester's own defect adjudication, 20 Sep 2026): `canonical_code` here
    must be uuid-shaped, with a `display` name, matching a REAL resolver candidate's own
    shape for an entity whose canonical identity is the row id (`miss_suggest.human_label`
    / `answer.py::build_suggest_offer`'s own `any_uuid` branch, line ~4161: "any uuid-coded
    (promotion) candidate means number buttons plus human names in the message text").
    A bare product CODE string (the original `SRTWT165-FTX`/`-FTY` here) takes the OTHER
    branch (code mode), which renders the numbered/stamped form only when the dym-probe's
    own `dym-annotate` node actually populated `outcome_fragment["dym-annotate"]` for these
    candidates - a wiring this fixture's simple `mcp_probe` does not reach on this call
    path (measured: `_expected_miss_text` on the ORIGINAL fixture produced the INLINE
    sentence, 'Did you mean SRTWT165-FTX, or SRTWT165-FTY?', zero numbered lines - the
    test's own `assert numbered` failed before `answer_bridge.answer_for` was ever called).
    uuid-shaped candidates take the unconditional numbered-with-human-label branch instead,
    which is what this test (and AC-1703's own stamped-roster shape) actually needs."""
    raw = "SRTWT165-FT"
    parser = {
        "domain_hint": "incoming",
        "intent_hint": "check_incoming",
        "message_type": "business_query",
        "entities": [{"raw": raw, "hint": "product", "current_message": True, "confident": True}],
        "routing": {"suggested_team": "purchasing", "suggested_agent": "certification"},
        "access_levels": [],
    }
    resolved = {
        "resolutions": [
            {
                "token": raw,
                "matches": [],
                "alternatives": [
                    {
                        "canonical_code": "11111111-1111-4111-8111-111111111111",
                        "entity_type": "product",
                        "uuid": "11111111-1111-4111-8111-111111111111",
                        "display": {"product_name": "SRTWT165-FTX"},
                        "match_tier": "fuzzy",
                    },
                    {
                        "canonical_code": "22222222-2222-4222-8222-222222222222",
                        "entity_type": "product",
                        "uuid": "22222222-2222-4222-8222-222222222222",
                        "display": {"product_name": "SRTWT165-FTY"},
                        "match_tier": "fuzzy",
                    },
                ],
            }
        ],
        "unresolved_tokens": [raw],
        "tokens": [raw],
    }
    gate = {"gate_passed": True, "compatible_entities": [], "gate_debug": {"domain": "incoming"}}

    def mcp_probe(name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "has_result": True,
            "answers": [
                {
                    "fields": [
                        {"label": "Product Code", "value": "SRTWT165-FTX"},
                        {"label": "Quantity On Hand", "value": 5},
                    ]
                },
                {
                    "fields": [
                        {"label": "Product Code", "value": "SRTWT165-FTY"},
                        {"label": "Quantity On Hand", "value": 0},
                    ]
                },
            ],
        }

    services = _services(mcp_probe=mcp_probe)
    return parser, resolved, {"gate": gate, "services": services}


class TestDidYouMeanRosterMintsAProductPick:
    def test_pending_kind_product_pick_domain_and_escalate_offered_carried(self) -> None:
        bridge = _require_answer_for()
        parser, resolved, extra = _dym_incoming_scenario()
        gate = extra["gate"]
        services = extra["services"]
        payload = {"resolved": resolved, "gate": gate, "_exit_kind": "not_found"}

        expected_text, offer = _expected_miss_text(
            payload, parser=parser, resolved=resolved, gate=gate, services=services
        )
        assert offer.get("suggest_last_result_set"), (
            "test setup sanity: the production chain must produce a did-you-mean roster "
            f"for this fixture: {offer}"
        )
        answer = bridge.answer_for(
            payload,
            envelope=None,
            parser=parser,
            ctx=_ctx_for(parser),
            canned=_canned(),
            services=services,
            db=None,
            asked_at_turn=3,
        )
        assert answer is not None
        assert answer.text == expected_text
        assert answer.question is not None, "a did-you-mean offer must raise a Pending"
        pending = answer.question
        assert pending.kind == "product_pick", pending.kind
        assert pending_mod.is_roster(pending.kind) is True
        assert len(pending.options) == len(offer["suggest_last_result_set"])
        assert pending.payload.get("domain") == "incoming", (
            "AC-1704: the pick must continue the ORIGINAL ask's domain"
        )
        assert pending.payload.get("escalate_offered") is True
        assert pending.team == "purchasing"

    def test_options_carry_the_production_stamp(self) -> None:
        """The printed line's own has/no suffix (computed off the SAME roster the offer
        text prints), carried on each option as `stamp` - AC-1703/AC-1701's own shape.

        DEFECT ADJUDICATION (tester 31, 20 Sep 2026, coder 28's own report): coder 28
        reported this test failing inside `_expected_miss_text` (the fixture's bare-code
        `canonical_code` values are not uuid-shaped, so `any_uuid` is False and production
        falls into the inline "Did you mean A, or B?" sentence, never a numbered list) -
        MEASURED and UPHELD (`assert numbered` failed with `[]` on the original fixture).
        Fixed per the brief's own suggested remedy: `_dym_incoming_scenario`'s alternatives
        are now uuid-shaped `canonical_code`s with a `display.product_name`, which routes
        production into the unconditional numbered/human-label branch
        (`answer.py::build_suggest_offer`'s `if any_uuid:` arm). Still RED after the fix,
        for a DIFFERENT, real, confirmed reason: that branch never bakes a has/no stamp
        into the rendered text at all (it is the promotion-style "numbered mode", not the
        product has/no-incoming "code mode" `dym-annotate` wires stamps onto) -
        `_stamps_by_position` correctly finds nothing to read back. This matches this same
        session's own LIVE measurement against `:8081` (`parity-f8-did-you-mean-and-continue.json`):
        a real "SRTWT165-FT CERT" ask today ALSO answers with the unstamped inline sentence,
        never a stamped numbered roster - stamps on a did-you-mean roster are a genuinely
        unimplemented feature today, not a fixture artifact. Left RED on purpose."""
        bridge = _require_answer_for()
        parser, resolved, extra = _dym_incoming_scenario()
        gate = extra["gate"]
        services = extra["services"]
        payload = {"resolved": resolved, "gate": gate, "_exit_kind": "not_found"}

        expected_text, offer = _expected_miss_text(
            payload, parser=parser, resolved=resolved, gate=gate, services=services
        )
        # The printed lines carry the stamp; derive the expected per-option stamp from
        # the SAME text the production chain produced, never a hand-typed guess.
        printed_lines = [line.strip() for line in expected_text.split("\n") if line.strip()]
        numbered = [line for line in printed_lines if line[:1].isdigit()]
        assert numbered, f"no numbered did-you-mean lines in the production text: {expected_text!r}"

        answer = bridge.answer_for(
            payload,
            envelope=None,
            parser=parser,
            ctx=_ctx_for(parser),
            canned=_canned(),
            services=services,
            db=None,
            asked_at_turn=3,
        )
        assert answer is not None and answer.question is not None
        stamps = [o.get("stamp") for o in answer.question.options]
        assert any(s for s in stamps), (
            f"at least one option must carry the production has/no stamp: {answer.question.options}"
        )
        for option, line in zip(answer.question.options, numbered):
            if option.get("stamp"):
                assert option["stamp"] in line, (option, line)


class TestMemberOfferPendingIsMintedByTheBridge:
    """`member_offer` already exists in `PENDING_KINDS` (read side only, per the plan's
    own measured fact) - this pins the WRITE side: the bridge mints one via `pending.ask`
    when the CS roster read comes back non-empty."""

    def test_pending_kind_member_offer_options_from_cs_last_result_set(self, monkeypatch) -> None:
        from app.services.chatbot.tail import member_offer as member_mod

        bridge = _require_answer_for()
        parser = _order_parser()
        parser["routing"] = {"suggested_team": "customer_service", "suggested_agent": "order_enquiries"}
        resolved = _resolved_nothing("STWC26")
        gate = _gate_passed_no_scope()
        services = _services()

        def stub_fetch_rosters(db, plan, ctx):
            return [
                {
                    "body": [
                        {"user_id": "u1", "respond_user_id": "ru1", "name": "Ah Chong"},
                        {"user_id": "u2", "respond_user_id": "ru2", "name": "Siti"},
                    ]
                }
            ]

        monkeypatch.setattr(member_mod, "fetch_rosters", stub_fetch_rosters)

        payload = {"resolved": resolved, "gate": gate, "_exit_kind": "not_found"}
        answer = bridge.answer_for(
            payload,
            envelope=None,
            parser=parser,
            ctx=_ctx_for(parser),
            canned=_canned(),
            services=services,
            db=None,
            asked_at_turn=4,
        )
        assert answer is not None and answer.question is not None, (
            "a non-empty CS roster read must raise a member_offer Pending"
        )
        pending = answer.question
        assert pending.kind == "member_offer", pending.kind
        assert [o.get("label") for o in pending.options] == ["Ah Chong", "Siti"]
        assert [o.get("payload", {}).get("respond_user_id") for o in pending.options] == [
            "ru1",
            "ru2",
        ]

    def test_minted_via_pending_ask(self, monkeypatch) -> None:
        from app.services.chatbot.tail import member_offer as member_mod

        bridge = _require_answer_for()
        calls: list[tuple[str, list]] = []
        real_ask = pending_mod.ask

        def _spy_ask(kind, options, **kwargs):
            calls.append((kind, options))
            return real_ask(kind, options, **kwargs)

        monkeypatch.setattr(pending_mod, "ask", _spy_ask)
        if hasattr(bridge, "pending_ask"):
            monkeypatch.setattr(bridge, "pending_ask", _spy_ask)
        if hasattr(bridge, "ask"):
            monkeypatch.setattr(bridge, "ask", _spy_ask)

        parser = _order_parser()
        parser["routing"] = {"suggested_team": "customer_service", "suggested_agent": "order_enquiries"}
        resolved = _resolved_nothing("STWC26")
        gate = _gate_passed_no_scope()
        services = _services()

        def stub_fetch_rosters(db, plan, ctx):
            return [{"body": [{"user_id": "u1", "respond_user_id": "ru1", "name": "Ah Chong"}]}]

        monkeypatch.setattr(member_mod, "fetch_rosters", stub_fetch_rosters)
        payload = {"resolved": resolved, "gate": gate, "_exit_kind": "not_found"}
        bridge.answer_for(
            payload,
            envelope=None,
            parser=parser,
            ctx=_ctx_for(parser),
            canned=_canned(),
            services=services,
            db=None,
            asked_at_turn=1,
        )
        assert any(kind == "member_offer" for kind, _ in calls), (
            f"pending.ask was never called with kind='member_offer': {calls}"
        )
