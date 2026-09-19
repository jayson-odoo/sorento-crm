"""R3 RED tests - `app/services/chatbot/turn/answer_bridge.py`'s `question_for` seam
(PLAN-chatbot-answer-half-reattach.md slice R3; UAC AC-1683, AC-1684, AC-1691's own
"no roster under two options" umbrella, AC-1694 pytest half, AC-1697/AC-1698's shape).

`answer_bridge.py` does not exist on this branch (measured: no such file under
`app/services/chatbot/turn/`). Every test below imports it lazily inside the test body
via `_bridge()` and asserts non-None first, so a missing module fails with a clean
`AssertionError` naming the gap rather than aborting collection for the whole file
(the R1/R2 tester convention this file follows).

**Pure, stubbed payloads.** No DB session anywhere in this file: `copy.fallback_copy()`
is the canned-copy object node replay itself grades against, and every payload below is
either hand-built in the shape the plan's own citations document, or produced by calling
the REAL production functions the plan names (`answer.access_level_choice_message`,
`pickers.annotate_customer`, `pickers.annotate_incoming`, `tail.outcome.escalate_catalog`,
`tail.outcome.build_outcome`, `tail.reply_ladder.compose_reply`) so the "expected" text in
every assertion is computed, never retyped by hand.

**MEASURED, flagged to the captain/coder, not resolved here:**

1. **Purity boundary conflict.** `tests/chatbot/test_rearch_s2_apply_is_pure.py::
   test_turn_package_imports_nothing_from_the_old_seams` is an EXISTING, already-green,
   parametrized test asserting NO file under `app/services/chatbot/turn/` imports from
   `chatbot.tail` (also `head`, `dialogue`, `engine`). The plan's own R3 design requires
   `turn/answer_bridge.py` to import `tail.outcome.escalate_catalog` and
   `tail.reply_ladder.compose_reply` verbatim. Writing `answer_bridge.py` at the path the
   captain's brief names, importing what the brief says it must, WILL fail that
   parametrized case for `forbidden_root == "tail"`. Not fixed here (out of a tester's
   remit and that file is not on this session's touch list) - the coder needs either a
   documented carve-out in that purity test or a different home for the bridge module
   (e.g. `lanes/business/answer_bridge.py`, which already imports `tail` freely via
   `lanes/business/__init__.py::complete_answer`).
2. **`resolve_gate.run`'s own `exit_kind="access_ask"` fires ONLY when the entry-gate's
   aggregate is EMPTY** (`tier_gate_out.get("name") == []`, i.e. the contact holds no
   access-type row at all) - `access_level_choice_message`'s OWN first branch
   ("You have no access levels configured..."), never the per-tier stamped picker
   AC-1697 wants. The stamped picker (non-empty `entitled_tiers`, `tier_last_result_set`)
   is only ever built once `fetch_mod.tier_probe_plan` + a probe per tier +
   `fetch_mod.tier_probe_collect` have run (today: `lanes/business/__init__.py`
   lines ~1026-1052, the "dead code" arm the plan's own Hazards section says R3
   "re-enables"). This file therefore does not try to derive an `access_ask` payload from
   a live `resolve_gate.run()` call - it hand-builds the tier_gate-shaped item the ALREADY
   PROBED lane item would carry (`name`, `entitled_tiers`, `tier_availability`), matching
   what `answer.access_level_choice_message` itself declares it reads. The engine-level
   file (`test_rearch_r3_bridge_engine.py`) documents this same gap again where it bites
   harder (a live promo ask has no route to a probed tier item yet).
3. **`if_incoming_picker(gate)` (`resolve_gate.py`) checks `gate_debug.domain ==
   "incoming"` literally** - `product_attachment` (the OTHER `REQUIRE_SPECIFIC_DOMAINS`
   member, AC-1701's own F6) never satisfies it, so a `product_attachment` roster falls
   through to the `not_found` exit today, not `offer`. `annotate_incoming`'s own suffix
   text is also hardcoded "- has incoming" / "- no incoming", never "- has Product
   Photos" / "- no Product Photos" (AC-1701's literal wording) for any domain. This file's
   "offer/product" case therefore pins the INCOMING domain specifically (the one
   `if_incoming_picker` + `annotate_incoming` actually implement today), not
   `product_attachment`/AC-1701's exact stamp text - a second gap between the plan's own
   claim ("R3 closes ... F6") and what the code can produce today, flagged rather than
   invented around.
"""
from __future__ import annotations

import importlib
from typing import Any

import pytest

from app.services.chatbot import copy as copy_mod
from app.services.chatbot import session_state
from app.services.chatbot.lanes.business import answer as answer_mod
from app.services.chatbot.lanes.business import pickers
from app.services.chatbot.tail import outcome as outcome_mod
from app.services.chatbot.tail import reply_ladder
from app.services.chatbot.turn import pending as pending_mod


def _bridge():
    """`app.services.chatbot.turn.answer_bridge`, or `None` if it does not exist yet."""
    try:
        return importlib.import_module("app.services.chatbot.turn.answer_bridge")
    except ModuleNotFoundError:
        return None


def _require_bridge():
    bridge = _bridge()
    assert bridge is not None, (
        "app.services.chatbot.turn.answer_bridge does not exist yet (R3 slice, "
        "PLAN-chatbot-answer-half-reattach.md)"
    )
    assert hasattr(bridge, "question_for"), (
        "answer_bridge module exists but has no question_for(payload, *, parser, ctx, "
        "canned, asked_at_turn) function yet"
    )
    return bridge


def _canned():
    return copy_mod.fallback_copy()


def _promo_parser(raw: str = "srtwc286") -> dict[str, Any]:
    return {
        "domain_hint": "promotion",
        "intent_hint": "check_promotion",
        "entities": [
            {"raw": raw, "hint": "product", "current_message": True, "confident": True}
        ],
    }


def _ctx_for(parser: dict[str, Any]) -> dict[str, Any]:
    return {"parse": {"output": parser}, "contact": {"id": "zzt-contact"}, "session": {}}


# --------------------------------------------------------------------------- #
# Arm 1 - access_ask (the promotion tier picker, AC-1697/AC-1698's shape)
# --------------------------------------------------------------------------- #


def _tier_item(entitled_tiers: list[str], *, names: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": names if names is not None else ["Sorento Office", "Sorento Dealer"],
        "entitled_tiers": entitled_tiers,
        "tier_ask": True,
    }


def _expected_access_ask(item: dict[str, Any], parser: dict[str, Any], *, availability: Any):
    """The byte-for-byte production chain the plan's Design section names, computed by
    calling the real functions - never retyped copy."""
    lane_item = {
        **answer_mod.access_level_choice_message(item, parser=parser, tier_availability=availability),
        "branch_kind": "access_choice",
    }
    ctx = _ctx_for(parser)
    canned = _canned()
    catalog = outcome_mod.escalate_catalog(lane_item, ctx, canned, access_choice=lane_item)
    built = outcome_mod.build_outcome([{"json": catalog}], {"escalate-catalog": catalog})
    text = reply_ladder.compose_reply(built[0]["json"]["outcome"])["text"]
    return text, lane_item


class TestAccessAskArm:
    """AC-1697's shape, AC-1683 (produced by escalate_catalog + compose_reply, not
    turn/compose), AC-1684 (a Pending minted by pending.ask), and the MEASURED TRAP:
    `tier_last_result_set` rows carry `entity_type: "access_tier"`
    (`answer.py:324`), which `apply._set_kind_field`/`_CODE_ONLY_FIELDS` does not
    recognise - only `"tier"` reaches `focus.tier` (`turn/apply.py:107`). Every option
    the bridge mints for this arm must carry `entity_type == "tier"`, not the row's own
    literal value.
    """

    @pytest.mark.parametrize(
        "availability,label",
        [
            ({"office": True, "dealer": True}, "all-has"),
            ({"office": True, "dealer": False}, "mixed"),
            (None, "none-measured"),
        ],
        ids=["all-has", "mixed", "none-measured"],
    )
    def test_text_matches_the_production_chain(self, availability, label) -> None:
        bridge = _require_bridge()
        item = _tier_item(["office", "dealer"])
        parser = _promo_parser()
        expected_text, _lane_item = _expected_access_ask(item, parser, availability=availability)

        payload = {**item, "_exit_kind": "access_ask"}
        answer = bridge.question_for(
            payload, parser=parser, ctx=_ctx_for(parser), canned=_canned(), asked_at_turn=7
        )
        assert answer is not None, "question_for returned None for an access_ask payload"
        assert answer.text == expected_text

    def test_pending_kind_is_tier_pick_minted_via_pending_ask(self, monkeypatch) -> None:
        bridge = _require_bridge()
        calls: list[tuple[str, list[dict[str, Any]]]] = []
        real_ask = pending_mod.ask

        def _spy_ask(kind, options, **kwargs):
            calls.append((kind, options))
            return real_ask(kind, options, **kwargs)

        monkeypatch.setattr(pending_mod, "ask", _spy_ask)
        # The bridge is documented to call `turn.pending.ask` directly (its own module
        # import), so the spy must patch the SAME symbol the bridge holds a reference
        # to - if the coder imports `from app.services.chatbot.turn.pending import ask`
        # into `answer_bridge`, patch that name too so the spy is not silently bypassed.
        if hasattr(bridge, "pending_ask"):
            monkeypatch.setattr(bridge, "pending_ask", _spy_ask)
        if hasattr(bridge, "ask"):
            monkeypatch.setattr(bridge, "ask", _spy_ask)

        item = _tier_item(["office", "dealer", "end_user"])
        parser = _promo_parser()
        payload = {**item, "_exit_kind": "access_ask"}
        answer = bridge.question_for(
            payload, parser=parser, ctx=_ctx_for(parser), canned=_canned(), asked_at_turn=11
        )
        assert answer is not None
        assert answer.question is not None, "an access_ask payload must raise a question"
        assert answer.question.kind == "tier_pick"
        assert answer.question.asked_at_turn == 11
        assert len(calls) >= 1, "pending.ask was never called for the access_ask arm"

    def test_options_are_in_tier_last_result_set_order_with_entity_type_tier(self) -> None:
        bridge = _require_bridge()
        item = _tier_item(["office", "dealer", "end_user"])
        parser = _promo_parser()
        payload = {**item, "_exit_kind": "access_ask"}
        answer = bridge.question_for(
            payload, parser=parser, ctx=_ctx_for(parser), canned=_canned(), asked_at_turn=1
        )
        assert answer is not None and answer.question is not None
        options = answer.question.options
        assert len(options) == 3, options
        # order: office, dealer, end_user (ASK_ORDER), matching `tier_last_result_set`
        assert [o["payload"].get("value") for o in options] == ["office", "dealer", "end_user"]
        assert [o.get("label") for o in options] == ["Office", "Dealer", "End user"]
        # THE TRAP: every option must carry entity_type == "tier", never the row's own
        # "access_tier" literal, or a pick never reaches focus.tier (apply.py:107/121).
        assert [o.get("entity_type") for o in options] == ["tier", "tier", "tier"], (
            "an option minted with entity_type == 'access_tier' (the row's own literal "
            "value from answer.py:324) never reaches focus.tier - apply._set_kind_field "
            "only recognises 'tier' (turn/apply.py's _CODE_ONLY_FIELDS)"
        )

    def test_no_roster_ever_asked_with_fewer_than_two_options(self) -> None:
        """AC-1691's umbrella, for this arm: a contact entitled to exactly one tier must
        not be asked to pick among one - `narrow_decide`/`must_narrow_one`'s own rule for
        every other roster kind. Documents the expectation; the bridge is free to settle
        the single tier outright and return a `hit`-shaped Answer with no question
        (out of R3's own two arms) rather than raising a one-option pick - either
        reading is acceptable as long as `question_for` never returns a one-option
        tier_pick."""
        bridge = _require_bridge()
        item = _tier_item(["office"])
        parser = _promo_parser()
        payload = {**item, "_exit_kind": "access_ask"}
        answer = bridge.question_for(
            payload, parser=parser, ctx=_ctx_for(parser), canned=_canned(), asked_at_turn=1
        )
        if answer is not None and answer.question is not None:
            assert len(answer.question.options) != 1, (
                "a one-tier entitlement must not be rendered as a one-option roster pick"
            )


# --------------------------------------------------------------------------- #
# Arm 2 - offer (the gate's own annotated pickers)
# --------------------------------------------------------------------------- #


def _customer_gate_payload() -> dict[str, Any]:
    """Hand-built in the shape `gate.run_gate`'s customer-picker arm documents
    (`gate.py:1024-1061`): `gate_clarification` is the bare numbered header (no stamps
    yet - `annotate_customer` adds those), `compatible_entities` carries one row per
    numbered line with the SAME rendered label as `title` (positional resolution), and
    `customer_probe_entities` is what made `if_customer_picker` take this exit in the
    first place. Company suffix "(MCH, SRT)" is baked into the label the same way
    `_rep_label(m) + _company_suffix(m)` builds it live."""
    labels = ["CHIN CHUN HARDWARE SDN BHD (MCH, SRT)", "CHIN CHUN HOMEMART (MCH)"]
    return {
        "gate_clarification": "Which customer do you mean? Please choose:\n"
        + "\n".join(f"{i + 1}. {label}" for i, label in enumerate(labels)),
        "compatible_entities": [
            {"uuid": f"cust-uuid-{i + 1}", "entity_type": "customer", "code": f"CUST{i + 1}", "title": label}
            for i, label in enumerate(labels)
        ],
        "customer_probe_entities": [
            {"uuid": f"cust-uuid-{i + 1}", "entity_type": "customer", "code": f"CUST{i + 1}"}
            for i in range(len(labels))
        ],
        "require_specific": False,
        "gate_debug": {"domain": "order"},
    }


def _expected_customer_offer(gate: dict[str, Any], parser: dict[str, Any], *, probe: Any):
    annotated = pickers.annotate_customer(dict(gate), probe=probe, parser=parser)
    lane_item = {**annotated, "branch_kind": "not_found"}
    ctx = _ctx_for(parser)
    canned = _canned()
    catalog = outcome_mod.escalate_catalog(lane_item, ctx, canned, incoming_picker=lane_item)
    built = outcome_mod.build_outcome([{"json": catalog}], {"escalate-catalog": catalog})
    text = reply_ladder.compose_reply(built[0]["json"]["outcome"])["text"]
    return text, lane_item


def _order_parser(raw: str = "srtwc286") -> dict[str, Any]:
    return {
        "domain_hint": "order",
        "intent_hint": "check_order",
        "entities": [
            {"raw": raw, "hint": "product", "current_message": True, "confident": True}
        ],
    }


class TestOfferArmCustomer:
    """AC-1694's pytest half: the customer picker, company suffix, has/no-DO stamp."""

    def test_text_matches_the_production_chain_no_do_for_one_of_two(self) -> None:
        bridge = _require_bridge()
        gate = _customer_gate_payload()
        parser = _order_parser()
        # `_row_has_do` reads the "Actual Delivery Date" field; one hit for the first
        # customer, none for the second - matches AC-1694's own worked example ("CHIN
        # CHUN HOMEMART reads 'no DO'").
        probe = {
            "answers": [
                {
                    "customer_name": "CHIN CHUN HARDWARE SDN BHD",
                    "fields": [{"label": "Actual Delivery Date", "value": "2026-09-01"}],
                }
            ]
        }
        expected_text, _lane_item = _expected_customer_offer(gate, parser, probe=probe)
        assert "has DO" in expected_text and "no DO" in expected_text, expected_text

        payload = {**gate, "_exit_kind": "offer"}
        answer = bridge.question_for(
            payload, parser=parser, ctx=_ctx_for(parser), canned=_canned(), asked_at_turn=3
        )
        assert answer is not None, "question_for returned None for a customer offer payload"
        assert answer.text == expected_text

    def test_pending_kind_customer_pick_options_in_printed_order(self) -> None:
        bridge = _require_bridge()
        gate = _customer_gate_payload()
        parser = _order_parser()
        payload = {**gate, "_exit_kind": "offer"}
        answer = bridge.question_for(
            payload, parser=parser, ctx=_ctx_for(parser), canned=_canned(), asked_at_turn=3
        )
        assert answer is not None and answer.question is not None
        assert answer.question.kind == "customer_pick"
        options = answer.question.options
        assert len(options) == 2, options
        assert [o.get("uuid") for o in options] == ["cust-uuid-1", "cust-uuid-2"]


def _incoming_gate_payload() -> dict[str, Any]:
    """Hand-built matching `if_incoming_picker`'s own exit (`resolve_gate.py:1081-1097`):
    `require_specific=True`, `gate_debug.domain == "incoming"`, `gate_clarification` the
    bare numbered header `run_gate`'s own product roster builds."""
    labels = ["SRTWC286-1", "SRTWC286-2"]
    return {
        "gate_clarification": (
            "incoming search needs to be more specific. Multiple matches found. Please "
            "choose:\n" + "\n".join(f"{i + 1}. {label}" for i, label in enumerate(labels))
        ),
        "compatible_entities": [
            {"uuid": f"prod-uuid-{i + 1}", "entity_type": "product", "code": label}
            for i, label in enumerate(labels)
        ],
        "require_specific": True,
        "gate_debug": {"domain": "incoming"},
    }


def _expected_incoming_offer(gate: dict[str, Any], parser: dict[str, Any], *, probe: Any):
    annotated = pickers.annotate_incoming(dict(gate), probe=probe)
    lane_item = {**annotated, "branch_kind": "not_found"}
    ctx = _ctx_for(parser)
    canned = _canned()
    catalog = outcome_mod.escalate_catalog(lane_item, ctx, canned, incoming_picker=lane_item)
    built = outcome_mod.build_outcome([{"json": catalog}], {"escalate-catalog": catalog})
    text = reply_ladder.compose_reply(built[0]["json"]["outcome"])["text"]
    return text, lane_item


class TestOfferArmIncomingProduct:
    """The product-roster half of the offer arm the plan can actually produce today
    (see module docstring point 3 for why this is `incoming`, not `product_attachment`
    /AC-1701's own text)."""

    def test_text_matches_the_production_chain(self) -> None:
        bridge = _require_bridge()
        gate = _incoming_gate_payload()
        parser = {
            "domain_hint": "incoming",
            "entities": [{"raw": "srtwc286", "hint": "product", "current_message": True}],
        }
        probe = {"answers": [{"title": "SRTWC286-1"}]}
        expected_text, _lane_item = _expected_incoming_offer(gate, parser, probe=probe)
        assert "has incoming" in expected_text and "no incoming" in expected_text, expected_text

        payload = {**gate, "_exit_kind": "offer"}
        answer = bridge.question_for(
            payload, parser=parser, ctx=_ctx_for(parser), canned=_canned(), asked_at_turn=2
        )
        assert answer is not None
        assert answer.text == expected_text

    def test_pending_kind_product_pick_option_count_matches_printed_lines(self) -> None:
        bridge = _require_bridge()
        gate = _incoming_gate_payload()
        parser = {
            "domain_hint": "incoming",
            "entities": [{"raw": "srtwc286", "hint": "product", "current_message": True}],
        }
        payload = {**gate, "_exit_kind": "offer"}
        answer = bridge.question_for(
            payload, parser=parser, ctx=_ctx_for(parser), canned=_canned(), asked_at_turn=2
        )
        assert answer is not None and answer.question is not None
        assert answer.question.kind == "product_pick"
        assert len(answer.question.options) == 2


# --------------------------------------------------------------------------- #
# question_for returns None outside its two arms (R4/R5's own territory)
# --------------------------------------------------------------------------- #


class TestQuestionForReturnsNoneOutsideItsTwoArms:
    @pytest.mark.parametrize("exit_kind", ["continue", "not_found"])
    def test_none_for_the_other_exit_kinds(self, exit_kind: str) -> None:
        bridge = _require_bridge()
        parser = _promo_parser()
        payload = {"_exit_kind": exit_kind, "gate": {}}
        answer = bridge.question_for(
            payload, parser=parser, ctx=_ctx_for(parser), canned=_canned(), asked_at_turn=1
        )
        assert answer is None, (
            f"question_for must return None for _exit_kind={exit_kind!r} (R4/R5's own arms)"
        )

    def test_none_for_a_null_payload(self) -> None:
        bridge = _require_bridge()
        parser = _promo_parser()
        answer = bridge.question_for(
            None, parser=parser, ctx=_ctx_for(parser), canned=_canned(), asked_at_turn=1
        )
        assert answer is None


# --------------------------------------------------------------------------- #
# AC-1684 - contract 36, a bridged roster stays sticky through with_answered_positions
# --------------------------------------------------------------------------- #


class TestStickyRosterContract36:
    def test_with_answered_positions_layers_onto_a_bridged_customer_pick(self) -> None:
        bridge = _require_bridge()
        gate = _customer_gate_payload()
        parser = _order_parser()
        payload = {**gate, "_exit_kind": "offer"}
        answer = bridge.question_for(
            payload, parser=parser, ctx=_ctx_for(parser), canned=_canned(), asked_at_turn=5
        )
        assert answer is not None and answer.question is not None
        pending = answer.question
        assert pending_mod.is_roster(pending.kind), (
            "customer_pick must be a contract-36 roster kind"
        )
        layered = pending_mod.with_answered_positions(pending, [1])
        assert layered.answered_positions == [1]
        layered_again = pending_mod.with_answered_positions(layered, [2])
        assert layered_again.answered_positions == [1, 2]
        # the roster's own options are untouched by layering an answered position
        assert layered_again.options == pending.options

    def test_tier_pick_is_not_a_roster_kind_by_contract_but_a_pick_is_still_a_pending(
        self,
    ) -> None:
        """`tier_pick` is NOT in `pending.ROSTER_KINDS` (contract 36 only names
        product/customer/kind picks) - documented here so a reader does not expect
        `answered_positions` to accumulate across a multi-turn tier conversation the
        way a roster's does. One turn's "1 and 2" is settled by `decision.positions`
        alone (AC-1698's multi-select), not by a carried `answered_positions` list."""
        assert pending_mod.is_roster("tier_pick") is False
