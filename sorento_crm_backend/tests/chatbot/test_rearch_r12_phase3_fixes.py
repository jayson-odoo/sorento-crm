"""Phase 3 hand pass 12 fix-round RED tests (tester 55), from the reviewer's and the
security reviewer's own findings on PR #952, all verified against the code before this
file was written. One class per finding (P1-P9 below, captain's numbering). P1-P7 are
expected RED for the reason the finding names; P8-P9 are GREEN guards (a parity pin and
a kill-test-gap guard the reviewer asked for), documented as guards in their own
docstrings so a future reader does not mistake a green result here for a skipped item.

Harness conventions, all copied rather than invented:

* P1 is a direct unit test of `turn/compose.py::compose_question`/`_subject_line` -
  no DB, no engine. MEASURED first (this pass): a full-engine replay of the
  captain's own suggested scenario ("pick a customer, then an ambiguous PRODUCT
  raises a new roster") never reaches `compose_question` at all - `turn/narrow.py`'s
  own `decide()` hands EVERY product roster to `gate.py` unconditionally
  (`if kind == "product": return NarrowOutcome(None, [], ...)`, AC-1690, "a product
  roster is gate.py's own job now ... for ANY domain"), and an unconfident entity's
  did-you-mean is production's OWN miss chain (`apply.py`'s own comment: "A did-you-
  mean is PRODUCTION's now... `_did_you_mean` used to run here... [deleted]"),
  neither of which is `compose_question`. Pinning the finding at the function
  `_subject_line` itself is what a full-engine test could not reliably reach without
  inventing an engine-level scenario the finding's own code pointers do not actually
  describe.
* P2 reuses `test_rearch_s3_roster_from_resolver.py` / `test_rearch_s3_attribute_
  first.py` / `test_rearch_s3_team_pick_and_866.py`'s own convention - `stub_parser`/
  `stub_access` (`test_engine.py`) plus `_envelope()` driving the REAL, undoubled
  `engine.run_turn`, because the finding is specifically about behaviour that only
  shows up once the escalation lane's own `/external/next-assignee` handler actually
  runs - a stubbed seam would hide the exact defect under test.
* P3, P9 reuse `test_rearch_r5_production_decides.py::_mcp_double`/`_seed_contact_and_
  get` + `test_rearch_r6_review_round.py::_run_turn_engine` + `test_rearch_r12_
  handpass12.py`'s own `_focus`/`_seed_state`/`_said`/`_unknown_envelope`/`_stock_hit`
  - the SAME convention every hand pass 12 file already uses (the REAL resolver/gate/
  narrower over seeded Postgres rows, only `FetchServices.mcp_call` doubled).
* P4, P5, P6 are direct unit tests of the pure functions the findings name
  (`lanes/business/answer.py::_token_requests`, `turn/apply.py::_roster_is_about`,
  `turn_runtime.py::_drop_focus_entities`) - no DB, no engine, the same level `test_
  crossdomain_ladder.py` and the S2 apply-is-pure suite already test these modules at.
* P7 calls `answer_bridge._miss_question` directly, the SAME level `test_rearch_r6_
  review_round.py::TestMissArmRosterHasNoMinimumTwoGuard` already tests it at (an
  internal helper of `answer_for`, never `answer_for` itself).
* P8 is a source-scan pin (`inspect.getsource`), the same technique `test_rearch_r4_
  deletions_and_cap.py::test_escalate_to_team_phrase_is_scoped_to_compose_not_compose_
  question` already uses for a call-order/scope guard.

Postgres only (`session_factory`, blank schema). Every row seeded fresh per test; no
row is borrowed from another test or from any live/clone data.
"""
from __future__ import annotations

import inspect
import json
import uuid
from typing import Any

from app.models.user import User
from app.services.chatbot import answer_bridge
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests.chatbot._escalation_seed import seed_team_for_code
from tests.chatbot.test_engine import _envelope, _parser_output, stub_access, stub_parser
from tests.chatbot.test_engine_company_scope import _seed_product
from tests.chatbot.test_rearch_r5_production_decides import _mcp_double, _seed_contact_and_get
from tests.chatbot.test_rearch_r6_review_round import _run_turn_engine
from tests.chatbot.test_rearch_r12_handpass12 import (
    INCOMING_TOOL,
    STOCK_TOOL,
    _focus,
    _said,
    _seed_state,
    _state_of,
    _stock_hit,
    _unknown_envelope,
)


# --------------------------------------------------------------------------- #
# P1 (reviewer M1) - `turn/compose.py::_subject_line` prints a customer CODE, never
# the ledger names, once a DIFFERENT axis raises a fresh roster after a multi-ledger
# customer pick.
# --------------------------------------------------------------------------- #


class TestP1SubjectLineReadsDisplayNameNotJustCanonicalCode:
    """P1 (reviewer M1): `turn/apply.py:621` stamps `entity["name"]` only when
    `len(uuids) <= 1` - a multi-ledger `customer_pick` option's own built focus rows
    carry NO name at all, only the option's ROLLUP `canonical_code` shared by every
    row. `turn/compose.py:483`'s own `_subject_line` reads `name or canonical_code or
    raw`, never `display_name` - the ONE field a DB-backed caller already knows how
    to fill for exactly this row shape (`turn/apply.py:621`'s own comment: "Left
    absent, `turn_runtime.fill_customer_names` (DB access, which this pure module
    may not have) fills each row's OWN name by its uuid" - `turn_runtime.
    fill_customer_names` writes `display_name`, never `name`, per its own docstring
    a few screens below that comment). `engine.py`'s HIT-arm scope block
    (~2158-2166) already builds a `display_name`-filled COPY this exact way, but
    explicitly never writes it back onto `state_out.focus` (that call site's own
    comment: "never written back onto `state_out.focus` itself"), and
    `compose_question(plan.ask, state_out)` (engine.py ~2316, the NEW-ASK arm every
    OTHER roster question composes through) fills nothing at all before calling
    `_subject_line` on `state_out` directly.

    MEASURED (this pass): the captain's own suggested engine-level scenario ("pick a
    customer, then an ambiguous PRODUCT raises a new roster") never reaches
    `compose_question` - `turn/narrow.py::decide()` hands EVERY product roster to
    `gate.py` unconditionally, for any domain, any policy value (`if kind ==
    "product": return NarrowOutcome(None, [], ...)`, AC-1690), and an unconfident
    entity's did-you-mean is production's OWN miss chain, not `compose_question`
    either (`apply.py`'s own comment: "`_did_you_mean`... [deleted]"). Pinned
    directly at the function instead: WHATEVER a fix does on the caller side to fill
    `display_name` before calling `compose_question` (mirroring the HIT-arm's own
    already-working fill), `_subject_line` itself must actually READ that field once
    it is there - today it does not, so even a caller that DOES fill it still prints
    the rollup code.
    """

    def test_subject_line_prefers_display_name_over_the_rollup_code(self) -> None:
        from app.services.chatbot.turn.compose import compose_question
        from app.services.chatbot.turn.pending import ask
        from app.services.chatbot.turn.state import Focus, State

        rollup_code = "ZZT-P1ROLLUP"
        names = ["ZZT P1 LEDGER ONE", "ZZT P1 LEDGER TWO", "ZZT P1 LEDGER THREE"]
        # The EXACT shape a DB-backed name-fill (`turn_runtime.fill_customer_names`)
        # produces on top of `turn/apply.py::_answer_pending`'s own rollup-code-only
        # row (Hand pass 12, Group F rule: no `name` for a multi-uuid option) - each
        # row keeps its own uuid and the shared rollup `canonical_code`, gaining ONLY
        # `display_name`.
        focus = Focus(
            domains=["order"],
            customers=[
                {
                    "raw": rollup_code,
                    "hint": "customer",
                    "canonical_code": rollup_code,
                    "uuid": f"u{i}",
                    "display_name": names[i],
                    "current_message": True,
                    "confident": True,
                }
                for i in range(3)
            ],
        )
        state = State(focus=focus)
        pending = ask(
            "product_pick",
            options=[
                {
                    "position": 1,
                    "label": "SRTWC286-SH",
                    "code": "SRTWC286-SH",
                    "entity_type": "product",
                },
                {
                    "position": 2,
                    "label": "SRTWC286-SH-200",
                    "code": "SRTWC286-SH-200",
                    "entity_type": "product",
                },
            ],
            payload={"domain": "order"},
        )

        answer = compose_question(pending, state)

        for name in names:
            assert name in answer.text, (
                f"a fresh roster over a DIFFERENT axis must still name every "
                f"carried ledger by its own DB-filled display_name: {answer.text!r}"
            )
        assert rollup_code not in answer.text, (
            f"no customer ROLLUP code must ever reach the subject line: "
            f"{answer.text!r}"
        )


# --------------------------------------------------------------------------- #
# P2 (security M2) - a member position pick sends the respond.io user id where
# `users.id` is expected, matched against `TeamMember.user_id`.
# --------------------------------------------------------------------------- #


class TestP2MemberPickAssigneeIdMustBeUsersIdNotRespondId:
    """P2 (security M2): `answer_bridge.member_option` puts `payload.respond_user_id`;
    `turn/apply.py:290` (`_answer_offer`'s own `answer_pending_accept` arm) stamps
    `trace.assignee = option_payload.get("respond_user_id")`, which `turn_runtime.py:
    577-582` carries onto `output.escalation.preferred_assignee_id`; `lanes/
    escalation.py::_next_assignee_body` sends THAT straight to `POST /external/
    next-assignee`'s own `preferred_assignee_id` body key, and `user_service.
    get_member_assignee` filters `TeamMember.user_id == preferred_id` - a real CRM
    user id, never a respond.io id. `lanes/escalation.py::escalation_context` (line
    ~219) has the SAME bug one rung up: it matches `preferred_assignee_id` against a
    roster row's own `uuid` (also a `users.id`, never a respond id).

    Every EXISTING hand pass 12 test for this exact pick (`test_rearch_r12_
    handpass12_b.py::TestGroupB2CDCustomerServiceEscalationAlwaysShowsTheMemberPicker
    .test_b_number_pick_over_member_offer_escalates_to_that_specific_member`) doubles
    the WHOLE escalation lane (`_escalation_lane_spy` replaces `engine_mod.
    run_escalation_lane` entirely) and pins the respond_user_id as `preferred_
    assignee_id` as "EXISTING, correct behaviour" - which is exactly the shape that
    404s once it reaches the REAL `/external/next-assignee` handler. THIS test does
    NOT double the escalation lane's own next-assignee seam: it reuses `tests/
    chatbot/_escalation_seed.py::seed_team_for_code` (the SAME real-seam fixture
    `test_rearch_s3_team_pick_and_866.py::TestPort866AsRunTurnCases` already uses to
    reach `post_next_assignee` in-process, undoubled) to seed a REAL `Team`/
    `AgentTeam`/`TeamMember`/`User` chain, seeds a `member_offer` pending whose
    option carries the member's own real `uuid` (`users.id`) AND that SAME member's
    own real `respond_user_id` on its payload (two genuinely different strings - a
    UUID vs. a random 10-digit id, never interchangeable), and drives the position
    pick through the REAL, undoubled `engine_mod.run_turn` -> `lanes.escalation.run`
    -> `escalation_services.build` -> `post_next_assignee` chain, a LIVE (non-dry)
    turn against the isolated blank schema `session_factory` hands this test - the
    SAME convention `TestPort866AsRunTurnCases` already uses for this class of test.

    Doubled here (only): the PARSER (`stub_parser`) and `check_access`/`default_
    space_id` (`stub_access`) - the same two seams `test_rearch_s3_team_pick_and_
    866.py`'s OWN `#866` cases double, never the escalation lane itself.
    """

    def test_position_pick_over_member_offer_assigns_the_picked_member_no_404(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed_contact_and_get(session_factory)
        seeded = seed_team_for_code(
            session_factory, "customer_service", agent_code="general_enquiries"
        )
        user_id = seeded["user_id"]
        db = session_factory()
        real_respond_id = db.query(User).filter(User.id == user_id).first().respond_user_id
        assert real_respond_id, "seed_team_for_code must seed a member with a respond_user_id"

        options = [
            {
                "position": 1,
                "label": "Zzt Escalation Agent",
                "entity_type": "member",
                # THE FIX'S OWN TARGET SHAPE: `uuid` is the real `users.id` -
                # `get_member_assignee` matches `TeamMember.user_id` against it.
                "uuid": user_id,
                "payload": {"respond_user_id": real_respond_id},
            },
        ]
        _seed_state(
            session_factory,
            focus=_focus(),
            open_question={
                "kind": "member_offer",
                "team": "customer_service",
                "expects": None,
                "options": options,
                "payload": {},
                "asked_at_turn": 1,
            },
        )

        v = _parser_output(
            message_type="casual",
            intent_hint=None,
            domain_hint=None,
            domain_in_message=False,
            entities=[],
            entity_op="reuse",
            reference_target="result",
            reference_positions=[1],
            document=[],
            status=None,
            order_status=None,
            routing={
                "suggested_team": None,
                "suggested_agent": "general_enquiries",
                "team_source": None,
            },
        )
        stub_parser(v)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.status == "done", (
            f"the picked member must resolve without a 404 - `preferred_assignee_id` "
            f"must be the option's own uuid (a real users.id), not its "
            f"respond_user_id: status={result.status!r} error={result.error!r}"
        )
        assign_actions = [
            a for a in (result.actions or []) if a.get("kind") == "assign_conversation"
        ]
        assert assign_actions, f"no assign_conversation action was produced: {result.actions!r}"
        assert assign_actions[0].get("respond_user_id") == real_respond_id, (
            f"the assignment must land on the picked member's own respond id: "
            f"{assign_actions!r}"
        )


# --------------------------------------------------------------------------- #
# P3 (reviewer S1) - the record-key rerun bypasses the `would_be_unfiltered` guard:
# it fires even when the KEPT entity carries no uuid at all.
# --------------------------------------------------------------------------- #


class TestP3RerunNeverFiresWithoutAKeptUuid:
    """P3 (reviewer S1): `turn_runtime.py`'s `would_be_unfiltered` guard is computed
    once, before the FIRST `run_fetch` call, and is never consulted again for the
    record-key rerun a few lines below it (~1545-1558) - that rerun fires whenever
    `_record_key_rerun_split` returns a non-None split, with no check that the KEPT
    entity actually carries a uuid. Scenario (reviewer measured): an incoming focus
    carries a PLACED product; this message types a token that reads as the domain's
    own record key (`inbound_shipment`) but resolves to NOTHING (no such shipment
    exists) - `_record_key_rerun_split`'s own `keep` carries a shipment-kind entity
    with no uuid, `drop` carries the product, and the rerun fires anyway with zero
    uuids passed. Expected: no second tool call at all when no KEPT row carries a
    uuid - there is nothing real to rerun on.
    """

    def test_no_second_tool_call_when_the_kept_record_key_entity_has_no_uuid(
        self, session_factory, monkeypatch
    ) -> None:
        _seed_contact_and_get(session_factory)
        code = unique_code("P3PROD")
        product_id = _seed_product(session_factory, company_id=DEFAULT_COMPANY_ID, code=code)
        # Deliberately NOT seeded as a real InboundShipment - this token must resolve
        # to NOTHING at all (the finding's own scenario), not merely to the wrong kind.
        bogus_container = f"ZZTP3{uuid.uuid4().hex[:10].upper()}"

        _seed_state(
            session_factory,
            focus=_focus(
                domains=["incoming"],
                products=[
                    {
                        "raw": code,
                        "hint": "product",
                        "uuid": product_id,
                        "company_name": "Sorento",
                        "canonical_code": code,
                    }
                ],
            ),
        )

        verdict = _parser_output(
            message_type="business_query",
            intent_hint="check_incoming",
            domain_hint="incoming",
            domain_in_message=False,
            continuation=False,
            entity_op="replace_combine",
            entities=[
                {
                    "raw": bogus_container,
                    "hint": "inbound_shipment",
                    "canonical_code": None,
                    "hint_confident": True,
                    "current_message": True,
                    "confident": True,
                }
            ],
            document=[],
            status=None,
            order_status=None,
            routing={
                "suggested_team": "purchasing",
                "suggested_agent": "incoming_stock_enquiries",
                "team_source": None,
            },
        )

        mcp_call, fetch_calls = _mcp_double(other=lambda name, args: _unknown_envelope())
        result = _run_turn_engine(
            session_factory,
            monkeypatch,
            qf=verdict,
            text_body=bogus_container,
            msg_id="zzt-p3-no-uuid-rerun",
            mcp_call=mcp_call,
        )
        assert result.status == "done", result.error

        incoming_calls = [args for name, args in fetch_calls if name == INCOMING_TOOL]
        assert len(incoming_calls) == 1, (
            f"a record-key rerun must never fire when the KEPT entity carries no "
            f"uuid at all (nothing real to rerun on) - a bogus, unresolved token "
            f"must not still trigger a second, zero-uuid tool call: {fetch_calls!r}"
        )


# --------------------------------------------------------------------------- #
# P4 (reviewer S2) - `lanes/business/answer.py::_token_requests`'s exact-token
# refusal is GLOBAL across the whole candidate pool, not scoped to the exact match's
# own family.
# --------------------------------------------------------------------------- #


class TestP4TokenRequestsExactRefusalIsScopedNotGlobal:
    """P4 (reviewer S2): `_token_requests`'s `if tokens & all_norm_codes: return
    False` refuses the prefix half for EVERY candidate the moment ANY token in this
    ask names ANY real code exactly, anywhere in the whole pool - not just within the
    exact match's own family. `_token_requests("srtwt6236bl", {"mfg6661",
    "srtwt6236"}, {"mfg6661","srtwt6236bl","srtwt6236wh"})` must be True (D4's prefix
    rule must still cross the SRTWT6236 family when a DIFFERENT, unrelated token
    happens to be an exact code elsewhere in the pool)."""

    def test_an_unrelated_exact_token_must_not_refuse_a_different_familys_prefix_match(
        self,
    ) -> None:
        from app.services.chatbot.lanes.business.answer import _token_requests

        assert (
            _token_requests(
                "srtwt6236bl",
                {"mfg6661", "srtwt6236"},
                {"mfg6661", "srtwt6236bl", "srtwt6236wh"},
            )
            is True
        ), (
            "an unrelated token (mfg6661) being an exact code elsewhere in the pool "
            "must not refuse a DIFFERENT token's own prefix match against a "
            "different family (srtwt6236 -> srtwt6236bl)"
        )

    def test_m2_rule_still_refuses_when_nothing_typed_is_this_familys_own_prefix(self) -> None:
        """GUARD (M2's own original rule, unaffected by the P4 fix): no token in this
        ask is even a prefix of srtwt6236bl's own family, so it stays refused."""
        from app.services.chatbot.lanes.business.answer import _token_requests

        assert (
            _token_requests(
                "srtwt6236bl",
                {"mfg6661"},
                {"mfg6661", "srtwt6236bl", "srtwt6236wh"},
            )
            is False
        )

    def test_a_genuine_family_prefix_still_requests_it(self) -> None:
        """GUARD: the typed token IS this family's own prefix (no other token names a
        real code exactly), so the prefix rule fires exactly as D4 intends."""
        from app.services.chatbot.lanes.business.answer import _token_requests

        assert (
            _token_requests(
                "srtwt6236bl",
                {"srtwt6236"},
                {"mfg6661", "srtwt6236bl", "srtwt6236wh"},
            )
            is True
        )


# --------------------------------------------------------------------------- #
# P5 (reviewer S3) - `turn/apply.py::_kind_field` does not apply `EXTRA_KIND_ALIASES`,
# so a `customer_order_pick`'s own roster reads an empty bucket after the pick wrote
# to a DIFFERENT (aliased) bucket.
# --------------------------------------------------------------------------- #


class TestP5RosterIsAboutReadsTheAliasedExtraBucket:
    """P5 (reviewer S3): `_set_kind_field` (the WRITE side) applies `EXTRA_KIND_
    ALIASES.get(kind, kind)` before writing - a `customer_order` pick's own built
    entities land on `focus.extra["order"]`, never `focus.extra["customer_order"]`.
    `_kind_field` (the READ side, used by `_roster_is_about`, ~line 1600) does NOT
    apply the same alias - it reads `focus.extra.get("customer_order", [])`, always
    empty, so a `customer_order_pick` pending is wrongly judged "not about" a focus
    that in fact still carries its own pick (on `focus.extra["order"]`), and the next
    NEW ASK closes a roster contract 36 says must survive."""

    def test_roster_is_about_true_after_a_customer_order_pick_wrote_the_order_bucket(
        self,
    ) -> None:
        from app.services.chatbot.turn.apply import _roster_is_about
        from app.services.chatbot.turn.pending import ask
        from app.services.chatbot.turn.state import Focus

        focus = Focus(
            extra={
                "order": [{"canonical_code": "PS202609-0320", "raw": "PS202609-0320"}],
                "customer_order": [],
            }
        )
        pending = ask(
            "customer_order_pick",
            options=[
                {
                    "position": 1,
                    "label": "PS202609-0320",
                    "code": "PS202609-0320",
                    "entity_type": "customer_order",
                }
            ],
            payload={"domain": "order"},
        )

        assert _roster_is_about(pending, focus) is True, (
            "a customer_order_pick roster must still read as 'about' the focus once "
            "the pick's own entity landed on the ALIASED extra bucket (focus.extra."
            "order), the same bucket `_set_kind_field` actually wrote to"
        )


# --------------------------------------------------------------------------- #
# P6 (reviewer S6) - `turn_runtime._drop_focus_entities` silently skips every
# extra-bucket kind (`order`, `inbound_shipment`, ...).
# --------------------------------------------------------------------------- #


class TestP6DropFocusEntitiesHandlesExtraBucketKinds:
    """P6 (reviewer S6): `_drop_focus_entities` only clears `Focus.products`/
    `.customers`/`.warehouse`/`.brands` (`KIND_FIELD_MAP`'s own four plural fields) -
    `KIND_FIELD_MAP.get(kind)` is `None` for `order` or `inbound_shipment`, and the
    loop `continue`s past them with no fallback to `focus.extra`, so a rerun that
    drops an `order`-kind carried entity (Group C's own dropped-filter rerun,
    hand pass 12 round 2) never actually removes it from `focus.extra["order"]` -
    the dropped row rides straight into the next turn."""

    def test_a_dropped_order_kind_entity_is_removed_from_the_extra_bucket(self) -> None:
        from app.services.chatbot.turn_runtime import _drop_focus_entities
        from app.services.chatbot.turn.state import Focus

        focus = Focus(
            extra={
                "order": [{"canonical_code": "PS202609-0374", "raw": "PS202609-0374"}],
                "inbound_shipment": [],
            }
        )
        dropped = [
            {
                "entity_type": "order",
                "canonical_code": "PS202609-0374",
                "raw": "PS202609-0374",
            }
        ]

        _drop_focus_entities(focus, dropped)

        assert focus.extra["order"] == [], (
            f"a dropped order-kind carried entity must be removed from focus.extra."
            f"order, the same as a dropped product/customer already is from its own "
            f"plural field: {focus.extra!r}"
        )


# --------------------------------------------------------------------------- #
# P7 (security L1) - a combined roster + member offer can assign two options the
# same position when a roster row is skipped.
# --------------------------------------------------------------------------- #


class TestP7CombinedPendingPositionsNeverCollide:
    """P7 (security L1): `answer_bridge.py::_miss_question`'s combined-pending arm
    (~line 938) computes `offset = len(roster_options)` - a bare COUNT - while each
    roster option's own position is `int(row.get("idx") or position)`
    (`_roster_option`). A roster row that `_stamped_roster_options` SKIPS (a
    non-dict row, `_roster_option`'s own refusal) shrinks `len(roster_options)`
    without shrinking the highest `idx` a SURVIVING row still carries, so
    `offset + i + 1` for the first member option can collide with a real roster
    row's own already-taken position."""

    def test_a_skipped_roster_row_does_not_collide_a_member_position(self) -> None:
        offer = {
            "suggest_last_result_set": [
                {"idx": 1, "uuid": "u1", "code": "X1", "entity_type": "product"},
                {"idx": 2, "uuid": "u2", "code": "X2", "entity_type": "product"},
                # A row `_roster_option` refuses outright (not a dict) - the live
                # shape of "row 3 was skipped upstream", per the finding.
                "not-a-row",
                {"idx": 4, "uuid": "u4", "code": "X4", "entity_type": "product"},
            ]
        }
        combined_member_rows = [
            {"user_id": "m1", "uuid": "m1", "respond_user_id": "r-1", "name": "Zzt Amy"},
            {"user_id": "m2", "uuid": "m2", "respond_user_id": "r-2", "name": "Zzt Ben"},
        ]

        result = answer_bridge._miss_question(
            offer,
            {},
            gate=None,
            parser={"routing": {}, "domain_hint": "incoming"},
            asked_at_turn=1,
            text="1. X1\n2. X2\n4. X4",
            combined_member_rows=combined_member_rows,
        )

        assert result is not None, "the combined pending must be minted"
        positions = [o.get("position") for o in result.options]
        assert len(positions) == len(set(positions)), (
            f"every option's own position must be unique - a skipped roster row "
            f"must not let a member option collide with a real row's own idx: "
            f"{result.options!r}"
        )
        member_positions = [
            o.get("position") for o in result.options if o.get("entity_type") == "member"
        ]
        assert member_positions and min(member_positions) == 5, (
            f"members must start AFTER the roster's own HIGHEST position (4), not "
            f"after a bare COUNT of surviving options (3): {result.options!r}"
        )


# --------------------------------------------------------------------------- #
# P8 (reviewer S5) - GUARD: `scripts/bootstrap_env.py::seed_chatbot_policy`'s own
# call order.
# --------------------------------------------------------------------------- #


class TestP8SeedChatbotPolicyCallOrderGuard:
    """GUARD, not a target - reviewer S5's own parity pin, GREEN today.
    `seed_chatbot_policy` must call `s4.publish_policy_blocks` before
    `s11.apply_narrowing` before `s12.apply_narrowing` before `s12.
    republish_and_promote`, in that relative order (source-scan, no migration/DB
    run) - keeps this call order from silently reordering under a future edit."""

    def test_publish_then_narrowing_then_republish_in_order(self) -> None:
        from scripts import bootstrap_env

        source = inspect.getsource(bootstrap_env.seed_chatbot_policy)
        markers = [
            "s4.publish_policy_blocks",
            "s11.apply_narrowing",
            "s12.apply_narrowing",
            "s12.republish_and_promote",
        ]
        positions = [source.index(marker) for marker in markers]
        assert positions == sorted(positions), (
            f"seed_chatbot_policy must call these, in this relative order, "
            f"{markers!r}: found at character offsets {positions!r} in its own "
            f"source"
        )


# --------------------------------------------------------------------------- #
# P9 (reviewer kill-test gap) - GUARD: the `would_be_unfiltered` guard must not fire
# when ANY entity in the ask placed.
# --------------------------------------------------------------------------- #


class TestP9GuardStockToolStillCalledWhenOneEntityPlaces:
    """GUARD, not a target - GREEN today. An inventory ask naming one unplaceable
    word AND one placeable product filter must still call the stock tool with that
    product's own uuid - the `would_be_unfiltered` guard (`turn_runtime.py`, `all(
    _entity_token_key(e) in unplaced for e in entities)`) must not fire the moment
    ANY entity in the ask placed, only when NONE of them did."""

    def test_one_unplaced_word_plus_one_placed_product_still_calls_stock_tool(
        self, session_factory, monkeypatch
    ) -> None:
        _seed_contact_and_get(session_factory)
        code = unique_code("P9PROD")
        product_id = _seed_product(session_factory, company_id=DEFAULT_COMPANY_ID, code=code)
        bogus_word = f"zzt-p9-nonexistent-{uuid.uuid4().hex[:8]}"

        verdict = _parser_output(
            intent_hint="check_stock",
            domain_hint="inventory",
            domain_in_message=True,
            entities=[
                {
                    "raw": code,
                    "hint": "product",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                },
                {
                    "raw": bogus_word,
                    "hint": "product",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                },
            ],
            routing={
                "suggested_team": "warehouse",
                "suggested_agent": "general_enquiries",
                "team_source": None,
            },
            document=[],
            status=None,
            order_status=None,
        )

        def _call(name: str, args: dict[str, Any]) -> str:
            if name == STOCK_TOOL:
                return json.dumps(_stock_hit(code))
            return _unknown_envelope()

        mcp_call, fetch_calls = _mcp_double(other=_call)
        result = _run_turn_engine(
            session_factory,
            monkeypatch,
            qf=verdict,
            text_body=f"{code} {bogus_word} stock",
            msg_id="zzt-p9-guard",
            mcp_call=mcp_call,
        )
        assert result.status == "done", result.error

        stock_calls = [args for name, args in fetch_calls if name == STOCK_TOOL]
        assert stock_calls, (
            f"a partially-unplaced ask (one word resolves, one does not) must "
            f"still call the stock tool with the PLACED product's own uuid - the "
            f"guard must scope to 'nothing placed at all', not 'anything "
            f"unplaced': {fetch_calls!r}"
        )
        assert product_id in (stock_calls[0].get("product_ids") or []), stock_calls[0]
