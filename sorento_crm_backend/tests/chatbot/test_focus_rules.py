"""The six focus rules, one class each, named after the rule (AC-950).

Growth r1 slice B3. `head/output_exchange.py` no longer contains owner ruling K rules 2
and 4, the `#6` switch-word override, `_query_brands_carried`, `_tier_carried` or the
executor's date / attribute / `is_active` carry arms; each is a named function in
`dialogue/focus.py` and each has its class here. The last class in the file is the grep
AC-950 asks for, so a rule sneaking back into `output_exchange` fails the suite rather
than a review.

**What the corpus proves and what this file proves.** The 1,875 captured emissions and the
87 graded worlds prove the MOVE was behaviour-preserving: they replay byte for byte with
these rules in charge. What they cannot show is a rule the corpus never exercises - the
TTL, `topic_reset`, `anaphora`, `confident=false` - because every capture predates them.
That is what this file is for.

Offline: pure functions over dicts, no database, no LLM, no turn.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.services.chatbot.dialogue import focus as fr


def _entity(raw: str, hint: str = "product", **extra: Any) -> dict[str, Any]:
    return {
        "raw": raw,
        "hint": hint,
        "canonical_code": raw,
        "current_message": True,
        "confident": True,
        **extra,
    }


def _turn(o: dict[str, Any], **kw: Any) -> fr.Turn:
    base = {"prev": {}, "turn_no": 5}
    base.update(kw)
    return fr.Turn(o=o, **base)  # type: ignore[arg-type]


def _slot(value: Any, *, turn: int = 4, source: str = "current_message") -> dict[str, Any]:
    return fr.slot(value, turn_no=turn, source=source)


# --------------------------------------------------------------------------- #
# 1. replace_same_axis
# --------------------------------------------------------------------------- #


class TestReplaceSameAxis:
    """A current-message entity replaces the slot of its own type, and only that one."""

    def test_a_new_product_replaces_the_product_and_leaves_the_customer(self) -> None:
        """AC-946: "for customer ABC instead" then "what about Y" changes one axis each."""
        focus = {
            "products": _slot([_entity("SRTWC8517")]),
            "customer": _slot(_entity("ABC", "customer")),
        }
        out = fr.Outputs(focus=focus)
        turn = _turn({"entities": [_entity("SRTKS6091")]})

        fr.replace_same_axis(focus, turn, out)

        assert [e["raw"] for e in fr.value_of(focus, "products")] == ["SRTKS6091"]
        assert fr.value_of(focus, "customer")["raw"] == "ABC"

    def test_a_new_customer_replaces_the_customer_and_leaves_the_product(self) -> None:
        focus = {
            "products": _slot([_entity("SRTWC8517")]),
            "customer": _slot(_entity("ABC", "customer")),
        }
        out = fr.Outputs(focus=focus)
        turn = _turn({"entities": [_entity("XYZ", "customer")]})

        fr.replace_same_axis(focus, turn, out)

        assert fr.value_of(focus, "customer")["raw"] == "XYZ"
        assert [e["raw"] for e in fr.value_of(focus, "products")] == ["SRTWC8517"]

    def test_a_carried_entity_is_not_a_current_message_entity(self) -> None:
        focus = {"products": _slot([_entity("SRTWC8517")])}
        out = fr.Outputs(focus=focus)
        turn = _turn({"entities": [_entity("SRTKS6091", current_message=False)]})

        fr.replace_same_axis(focus, turn, out)

        assert [e["raw"] for e in fr.value_of(focus, "products")] == ["SRTWC8517"]

    def test_every_replacement_writes_one_focus_trace_entry(self) -> None:
        """AC-971: the rule, the slot, the before and the after."""
        focus = {"products": _slot([_entity("SRTWC8517")])}
        out = fr.Outputs(focus=focus)

        fr.replace_same_axis(focus, _turn({"entities": [_entity("SRTKS6091")]}), out)

        assert len(out.entries) == 1
        entry = out.entries[0]
        assert entry["slot"] == "products"
        assert entry["rule"] == "replace_same_axis"
        assert entry["source"] == "current_message"
        assert [e["raw"] for e in entry["before"]] == ["SRTWC8517"]
        assert [e["raw"] for e in entry["after"]] == ["SRTKS6091"]

    def test_an_unconfident_entity_never_replaces_an_alive_slot(self) -> None:
        """AC-953. `confident=false` means the parser crammed more than one untyped
        concept into one `raw`; acting on that silently narrows the question."""
        focus = {"products": _slot([_entity("SRTWC8517")])}
        out = fr.Outputs(focus=focus)
        turn = _turn({"entities": [_entity("one siew srtkt72ss", confident=False)]})

        fr.replace_same_axis(focus, turn, out)

        assert [e["raw"] for e in fr.value_of(focus, "products")] == ["SRTWC8517"]
        assert out.entries == []

    def test_the_confident_half_of_a_mixed_turn_still_replaces(self) -> None:
        """PER ENTITY, not per turn. "SRTWC8517 and one siew srtkt72ss" is one clean code
        and one unsplittable phrase; dropping the whole replacement because of the second
        throws away the first as well, and the turn then answers about the PREVIOUS
        product - worse than either reading of this one."""
        focus = {"products": _slot([_entity("OLD-CODE")])}
        out = fr.Outputs(focus=focus)
        turn = _turn(
            {
                "entities": [
                    _entity("SRTWC8517"),
                    _entity("one siew srtkt72ss", confident=False),
                ]
            }
        )

        fr.replace_same_axis(focus, turn, out)

        assert [e["raw"] for e in fr.value_of(focus, "products")] == ["SRTWC8517"]

    def test_a_wholly_unconfident_turn_leaves_the_alive_slot_alone(self) -> None:
        focus = {"customer": _slot(_entity("ABC", "customer"))}
        out = fr.Outputs(focus=focus)
        turn = _turn({"entities": [_entity("something vague", "customer", confident=False)]})

        fr.replace_same_axis(focus, turn, out)

        assert fr.value_of(focus, "customer")["raw"] == "ABC"

    def test_an_unconfident_entity_does_fill_an_empty_slot(self) -> None:
        """There is nothing to lose, and a guess beats having no scope at all."""
        focus: dict[str, Any] = {}
        out = fr.Outputs(focus=focus)
        turn = _turn({"entities": [_entity("one siew srtkt72ss", confident=False)]})

        fr.replace_same_axis(focus, turn, out)

        assert fr.value_of(focus, "products") is not None

    def test_an_unconfident_entity_does_replace_through_a_picker(self) -> None:
        """The value came from rows we showed the customer, and they chose one."""
        focus = {"products": _slot([_entity("SRTWC8517")])}
        out = fr.Outputs(focus=focus)
        turn = _turn(
            {"entities": [_entity("SRTKS6091", confident=False)]}, has_picker=True
        )

        fr.replace_same_axis(focus, turn, out)

        assert [e["raw"] for e in fr.value_of(focus, "products")] == ["SRTKS6091"]


# --------------------------------------------------------------------------- #
# 2. reset_on_topic
# --------------------------------------------------------------------------- #


class TestResetOnTopic:
    """AC-943: "别的" clears product, customer, date and domain, and keeps tier and brands."""

    def _full_focus(self) -> dict[str, Any]:
        return {
            "products": _slot([_entity("SRTWC8517")]),
            "customer": _slot(_entity("ABC", "customer")),
            "date_window": _slot({"start": "2026-08-01", "end": "2026-08-31", "mode": None}),
            "domain": _slot("inventory"),
            "tier": _slot(["dealer"]),
            "brands": _slot(["sorento"]),
        }

    def test_topic_reset_clears_the_question_and_keeps_the_asker(self) -> None:
        focus = self._full_focus()
        out = fr.Outputs(focus=focus)
        turn = _turn({"entities": []}, signals={"topic_reset": True})

        fr.reset_on_topic(focus, turn, out)

        assert set(focus) == {"tier", "brands"}
        assert fr.value_of(focus, "tier") == ["dealer"]
        assert fr.value_of(focus, "brands") == ["sorento"]

    def test_a_slot_this_very_message_set_survives_the_reset(self) -> None:
        """"别的, show me SRTKS6091" resets the subject AND names the new one; clearing
        what `replace_same_axis` just wrote would answer nothing at all."""
        focus = self._full_focus()
        focus["products"] = _slot([_entity("SRTKS6091")], turn=5)
        out = fr.Outputs(focus=focus)
        turn = _turn({"entities": [_entity("SRTKS6091")]}, signals={"topic_reset": True})

        fr.reset_on_topic(focus, turn, out)

        assert [e["raw"] for e in fr.value_of(focus, "products")] == ["SRTKS6091"]
        assert "customer" not in focus

    def test_owner_ruling_k2_fires_on_an_explicit_new_domain_query(self) -> None:
        """H66: a customer named on an order turn kept scoping the promotion that followed."""
        focus = self._full_focus()
        out = fr.Outputs(focus=focus)
        turn = _turn(
            {"entities": [_entity("SRTKS6091")], "domain_hint": "promotion"},
            prev={"domain_hint": "order"},
            explicit=True,
            is_carried=lambda e: e.get("raw") == "carried",
        )

        fr.reset_on_topic(focus, turn, out)

        assert out.drop_carried_entities is True

    def test_a_turn_that_names_no_domain_is_a_continuation_not_a_change(self) -> None:
        """A pick, a date window and a bare code all arrive with `domain_hint: null`."""
        focus = self._full_focus()
        out = fr.Outputs(focus=focus)
        turn = _turn(
            {"entities": [_entity("SRTKS6091")], "domain_hint": None},
            prev={"domain_hint": "order"},
            explicit=True,
        )

        fr.reset_on_topic(focus, turn, out)

        assert out.drop_carried_entities is False
        assert set(focus) == set(self._full_focus())

    def test_a_guessed_domain_never_counts_as_the_customer_changing_the_subject(self) -> None:
        """`explicit` is the gate: a domain the model guessed off a bare token's shape
        reads as a change on exactly the turns that are not one."""
        focus = self._full_focus()
        out = fr.Outputs(focus=focus)
        turn = _turn(
            {"entities": [_entity("SRTKS6091")], "domain_hint": "promotion"},
            prev={"domain_hint": "order"},
            explicit=False,
        )

        fr.reset_on_topic(focus, turn, out)

        assert out.drop_carried_entities is False

    def test_the_drop_itself_names_what_it_removed(self) -> None:
        o = {
            "entities": [_entity("SRTKS6091"), _entity("M2609-0086", "customer_order")],
        }

        fr.drop_carried_entities_on_topic_change(
            o, is_carried=lambda e: e.get("hint") == "customer_order"
        )

        assert [e["raw"] for e in o["entities"]] == ["SRTKS6091"]
        assert o["entities_dropped_on_topic_change"] == ["customer_order:M2609-0086"]


# --------------------------------------------------------------------------- #
# 3. reuse_alive
# --------------------------------------------------------------------------- #


class TestATopicResetActuallySticks:
    """Item 5 of the 7 Sep review, tested through `apply` because that is where it broke.

    Each rule was right on its own: `reset_on_topic` cleared the domain slot and
    `_record_domain` recorded what the turn concluded. Run in order, the second wrote back
    the domain the first had just dropped - measured, "别的" ended with `inventory` alive -
    so the customer's "something else" reset nothing anybody could see.
    """

    def _focus(self) -> dict[str, Any]:
        return {
            "products": _slot([_entity("SRTWC8517")]),
            "customer": _slot(_entity("ABC", "customer")),
            "domain": _slot("inventory"),
            "tier": _slot(["dealer"]),
            "brands": _slot(["sorento"]),
        }

    def _reset_turn(self, **over: Any) -> fr.Turn:
        o = {
            "entities": [],
            "domain_hint": "inventory",
            "intent_hint": "check_stock",
            "message_type": "business_query",
            "entity_op_applied": "reuse",
        }
        o.update(over.pop("o", {}))
        kwargs: dict[str, Any] = {
            "prev": {"domain_hint": "inventory", "intent_hint": "check_stock"},
            "signals": {"topic_reset": True},
            "parser_raw": {"domain_hint": None},
        }
        kwargs.update(over)
        return _turn(o, **kwargs)

    def test_the_domain_is_gone_from_the_focus_after_apply(self) -> None:
        out = fr.apply(self._focus(), self._reset_turn())

        assert sorted(out.focus) == ["brands", "tier"]

    def test_the_domain_is_gone_from_the_emission_too(self) -> None:
        """The slot alone is not enough: the lane routes on `qf.domain_hint` and the next
        turn inherits it."""
        turn = self._reset_turn()

        fr.apply(self._focus(), turn)

        assert turn.o["domain_hint"] is None
        assert turn.o["intent_hint"] is None
        assert turn.o["domain_cleared_on_topic_reset"] is True

    def test_a_reset_that_names_its_own_domain_keeps_that_one(self) -> None:
        """"别的, any promotions?" is a reset AND a new subject."""
        turn = self._reset_turn(
            o={"domain_hint": "promotion", "intent_hint": "check_promotion"},
            parser_raw={"domain_hint": "promotion"},
        )

        out = fr.apply(self._focus(), turn)

        assert turn.o["domain_hint"] == "promotion"
        assert fr.value_of(out.focus, "domain") == "promotion"

    def test_owner_ruling_k2_never_clears_the_domain(self) -> None:
        """K2 fires on an EXPLICIT new-domain query, where the domain is the new one."""
        turn = _turn(
            {
                "entities": [_entity("SRTKS6091")],
                "domain_hint": "promotion",
                "message_type": "business_query",
            },
            prev={"domain_hint": "order"},
            explicit=True,
            is_carried=lambda e: False,
        )

        out = fr.apply(self._focus(), turn)

        assert turn.o["domain_hint"] == "promotion"
        assert out.topic_reset is False

    def test_a_topic_change_drop_is_never_relabelled_as_decay(self) -> None:
        """The two drops have different causes and different fixes when an operator reads
        the trace, so they must not be confused.

        `reset_on_topic` clears every slot, which leaves every carried entity looking like
        one whose slot aged out - so `_drop_dead_carried_entities` swept them first, wrote
        `entities_dropped_on_decay` with `rule: reuse_alive`, and left the deferred
        topic-change drop with nothing to stamp. The trace then said the bot had forgotten
        the scope rather than that the customer had moved off it.
        """
        carried = _entity("M2609-0086", "customer_order", current_message=False)
        stale_product = _entity("SRTWC8517", current_message=False)
        o = {
            "entities": [_entity("SRTKS6091"), carried, stale_product],
            "domain_hint": "promotion",
            "message_type": "business_query",
            "entity_op_applied": "reuse",
        }
        turn = _turn(
            o,
            prev={"domain_hint": "order"},
            explicit=True,
            is_carried=lambda e: e.get("current_message") is not True,
        )

        out = fr.apply(self._focus(), turn)
        # `_post_process` performs the deferred half after the domain blocklist; this is
        # the same two steps in the same order.
        assert out.drop_carried_entities is True
        assert "entities_dropped_on_decay" not in o
        fr.drop_carried_entities_on_topic_change(o, is_carried=turn.is_carried)

        assert o["entities_dropped_on_topic_change"] == [
            "customer_order:M2609-0086",
            "product:SRTWC8517",
        ]
        assert "entities_dropped_on_decay" not in o
        assert [e["raw"] for e in o["entities"]] == ["SRTKS6091"]
        assert not [e for e in out.entries if e["rule"] == "reuse_alive"]

    def test_a_plain_decayed_slot_is_still_labelled_decay(self) -> None:
        """The other side of the same line: with no reset, the sweep is the right label."""
        o = {
            "entities": [_entity("SRTWC8517", current_message=False)],
            "entity_op_applied": "reuse",
        }

        fr.apply({}, _turn(o))

        assert o["entities_dropped_on_decay"] == ["product:SRTWC8517"]
        assert "entities_dropped_on_topic_change" not in o

    def test_the_entityless_carry_stands_down_on_a_reset(self) -> None:
        """It runs inside the entity executor, before `reset_on_topic` is evaluated, so it
        takes the signal directly rather than carrying a domain about to be cleared."""
        o = {"message_type": "business_query", "domain_hint": None, "intent_hint": None}

        fired = fr.reuse_domain_entityless(
            o,
            prev={"domain_hint": "inventory", "intent_hint": "check_stock"},
            explicit=False,
            switch_domain=None,
            topic_reset=True,
        )

        assert fired is False
        assert o["domain_hint"] is None


class TestReuseAlive:
    """An axis this turn did not name takes the alive slot. A DEAD slot never reuses."""

    def test_a_continuation_inherits_the_attributes_it_did_not_restate(self) -> None:
        """exec 13951947: the PERSPECTIVE of the question is an axis the pick did not name."""
        focus = {"attributes": _slot(["quantity"])}
        out = fr.Outputs(focus=focus)
        o = {"entity_op_applied": "reuse", "requested_attributes": [], "entities": []}

        fr.reuse_alive(focus, _turn(o), out)

        assert o["requested_attributes"] == ["quantity"]

    def test_a_turn_that_names_its_own_attributes_keeps_them(self) -> None:
        focus = {"attributes": _slot(["quantity"])}
        out = fr.Outputs(focus=focus)
        o = {"entity_op_applied": "reuse", "requested_attributes": ["delivery"], "entities": []}

        fr.reuse_alive(focus, _turn(o), out)

        assert o["requested_attributes"] == ["delivery"]

    def test_a_dead_slot_never_reuses(self) -> None:
        """The whole point of slice B1: `decay` dropped it at intake, so it is not here,
        so there is nothing to reuse and the turn asks instead of guessing (AC-940)."""
        out = fr.Outputs(focus={})
        o = {"entity_op_applied": "reuse", "requested_attributes": [], "entities": []}

        fr.reuse_alive({}, _turn(o), out)

        assert o["requested_attributes"] == []

    def test_the_brand_travels_with_the_scope(self) -> None:
        """F7: the brand is part of the query scope, so it must travel with it or the
        brand half of the scope vanishes and re-opens a gate that already denied the turn."""
        focus = {"brands": _slot(["cabana"])}
        out = fr.Outputs(focus=focus)
        o = {"entity_op": "reuse", "query_brands": [], "access_levels": [], "entities": []}

        fr.reuse_alive(focus, _turn(o), out)

        assert o["query_brands"] == ["cabana"]
        assert o["_query_brands_carried"] is True

    def test_the_tier_travels_with_the_scope_and_is_a_separate_rule(self) -> None:
        """The two axes can legitimately disagree: new brand, same tier."""
        focus = {"tier": _slot(["dealer"]), "brands": _slot(["cabana"])}
        out = fr.Outputs(focus=focus)
        o = {
            "entity_op": "reuse",
            "query_brands": ["mocha"],
            "access_levels": [],
            "entities": [],
        }

        fr.reuse_alive(focus, _turn(o), out)

        assert o["query_brands"] == ["mocha"], "this turn named its own brand"
        assert o["access_levels"] == ["dealer"]
        assert o["_tier_carried"] is True

    def test_is_active_is_carried_only_when_this_turn_said_no_status_word(self) -> None:
        out = fr.Outputs(focus={})
        o = {"entity_op_applied": "reuse", "is_active": None, "entities": []}

        fr.reuse_alive({}, _turn(o, prev={"is_active": False}), out)

        assert o["is_active"] is False

    def test_is_active_stated_this_turn_wins(self) -> None:
        out = fr.Outputs(focus={})
        o = {"entity_op_applied": "reuse", "is_active": True, "entities": []}

        fr.reuse_alive({}, _turn(o, prev={"is_active": False}), out)

        assert o["is_active"] is True

    def test_the_entityless_domain_continuation_inherits_the_domain(self) -> None:
        """"and the price?" - the turn has no scope of its own but is the same question."""
        o = {"message_type": "business_query", "domain_hint": None, "intent_hint": None}

        fired = fr.reuse_domain_entityless(
            o,
            prev={"domain_hint": "inventory", "intent_hint": "check_stock"},
            explicit=False,
            switch_domain=None,
        )

        assert fired is True
        assert o["domain_hint"] == "inventory"
        assert o["intent_hint"] == "check_stock"
        assert o["domain_reused_entityless"] is True

    def test_a_decisive_domain_of_its_own_beats_the_carry(self) -> None:
        o = {"message_type": "business_query", "domain_hint": "promotion"}

        fired = fr.reuse_domain_entityless(
            o, prev={"domain_hint": "inventory"}, explicit=True, switch_domain=None
        )

        assert fired is False
        assert o["domain_hint"] == "promotion"

    def test_a_switch_word_beats_the_carry(self) -> None:
        o = {"message_type": "business_query", "domain_hint": None}

        fired = fr.reuse_domain_entityless(
            o, prev={"domain_hint": "inventory"}, explicit=False, switch_domain="incoming"
        )

        assert fired is False

    def test_a_request_for_help_is_not_a_continuation(self) -> None:
        o = {"message_type": "request_for_help", "domain_hint": None}

        assert (
            fr.reuse_domain_entityless(
                o, prev={"domain_hint": "inventory"}, explicit=False, switch_domain=None
            )
            is False
        )


# --------------------------------------------------------------------------- #
# 4. domain_from_switch_word
# --------------------------------------------------------------------------- #


class TestDomainFromSwitchWord:
    """AC-942: "incoming?" after a stock answer keeps the products and switches the domain."""

    def test_the_domain_moves_and_the_products_stay(self) -> None:
        focus = {"domain": _slot("inventory"), "products": _slot([_entity("SRTWC8517")])}
        out = fr.Outputs(focus=focus)
        o = {"domain_hint": "inventory", "intent_hint": "check_stock"}

        fr.domain_from_switch_word(focus, _turn(o, switch_domain="incoming"), out)

        assert o["domain_hint"] == "incoming"
        assert o["domain_switched_by_keyword"] == "incoming"
        assert [e["raw"] for e in fr.value_of(focus, "products")] == ["SRTWC8517"]

    def test_the_intent_is_nulled_so_downstream_rederives_it(self) -> None:
        """Keeping the old one routes a shipment question through the stock intent."""
        focus = {"domain": _slot("inventory")}
        out = fr.Outputs(focus=focus)
        o = {"domain_hint": "inventory", "intent_hint": "check_stock"}

        fr.domain_from_switch_word(focus, _turn(o, switch_domain="incoming"), out)

        assert o["intent_hint"] is None

    def test_no_switch_word_changes_nothing(self) -> None:
        focus = {"domain": _slot("inventory")}
        out = fr.Outputs(focus=focus)
        o = {"domain_hint": "inventory", "intent_hint": "check_stock"}

        fr.domain_from_switch_word(focus, _turn(o, switch_domain=None), out)

        assert o["domain_hint"] == "inventory"
        assert o["intent_hint"] == "check_stock"
        assert out.entries == []


# --------------------------------------------------------------------------- #
# 5. date_restated_only
# --------------------------------------------------------------------------- #


class TestDateRestatedOnly:
    """The window comes from THIS message, with one exception the executor always made."""

    def test_a_date_named_this_turn_sets_the_slot(self) -> None:
        focus: dict[str, Any] = {}
        out = fr.Outputs(focus=focus)
        o = {
            "date_filter_start": "2026-08-01",
            "date_filter_end": "2026-08-31",
            "date_mode": "overlap",
        }

        fr.date_restated_only(focus, _turn(o), out)

        assert fr.value_of(focus, "date_window") == {
            "start": "2026-08-01",
            "end": "2026-08-31",
            "mode": "overlap",
        }

    def test_a_scope_continuation_restores_the_window(self) -> None:
        """"and the quantity?" is still last month; without this it silently widens to
        all time."""
        focus = {"date_window": _slot({"start": "2026-08-01", "end": "2026-08-31", "mode": None})}
        out = fr.Outputs(focus=focus)
        o = {"entity_op_applied": "reuse", "date_filter_start": None, "date_filter_end": None}

        fr.date_restated_only(focus, _turn(o), out)

        assert o["date_filter_start"] == "2026-08-01"
        assert o["date_filter_end"] == "2026-08-31"

    def test_a_turn_that_is_not_a_continuation_gets_no_window(self) -> None:
        focus = {"date_window": _slot({"start": "2026-08-01", "end": "2026-08-31", "mode": None})}
        out = fr.Outputs(focus=focus)
        o = {"entity_op_applied": "replace_combine", "date_filter_start": None}

        fr.date_restated_only(focus, _turn(o), out)

        assert o.get("date_filter_start") is None

    def test_asking_for_all_dates_drops_the_window_rather_than_restoring_it(self) -> None:
        """Restoring it answers the opposite of what was asked."""
        focus = {"date_window": _slot({"start": "2026-08-01", "end": "2026-08-31", "mode": None})}
        out = fr.Outputs(focus=focus)
        o = {"entity_op_applied": "reuse", "broaden_axis": "date"}

        fr.date_restated_only(focus, _turn(o), out)

        assert o["date_filter_start"] is None
        assert o["date_filter_end"] is None
        assert "date_window" not in focus

    def test_a_date_widen_reattach_is_not_undone(self) -> None:
        focus = {"date_window": _slot({"start": "2026-08-01", "end": None, "mode": None})}
        out = fr.Outputs(focus=focus)
        o = {"entity_op_applied": "reuse", "date_filter_start": None}

        fr.date_restated_only(focus, _turn(o, date_widened=True), out)

        assert o["date_filter_start"] is None


# --------------------------------------------------------------------------- #
# 6. anaphora_reuses
# --------------------------------------------------------------------------- #


class TestAnaphoraReuses:
    """AC-941: "that one" resolves to the alive product slot, or asks which product."""

    def test_it_resolves_against_the_alive_product_slot(self) -> None:
        focus = {"products": _slot([_entity("SRTWC8517")])}
        out = fr.Outputs(focus=focus)
        o: dict[str, Any] = {"entities": []}

        fr.anaphora_reuses(focus, _turn(o, signals={"anaphora": True}), out)

        assert [e["raw"] for e in o["entities"]] == ["SRTWC8517"]
        assert o["entity_op"] == "reuse"
        assert o["anaphora_resolved"] is True

    def test_the_carried_entity_is_flagged_as_carried(self) -> None:
        """Every carried-entity rule downstream keys on `current_message: false`."""
        focus = {"products": _slot([_entity("SRTWC8517")])}
        out = fr.Outputs(focus=focus)
        o: dict[str, Any] = {"entities": []}

        fr.anaphora_reuses(focus, _turn(o, signals={"anaphora": True}), out)

        assert all(e["current_message"] is False for e in o["entities"])

    def test_a_dead_slot_leaves_the_turn_with_nothing_to_answer_about(self) -> None:
        """AC-941: the reply asks which product, rather than answering about a subject
        three topics ago."""
        out = fr.Outputs(focus={})
        o: dict[str, Any] = {"entities": []}

        fr.anaphora_reuses({}, _turn(o, signals={"anaphora": True}), out)

        assert o["entities"] == []
        assert o["anaphora_unresolved"] is True

    def test_a_message_that_names_its_own_value_is_not_anaphora(self) -> None:
        focus = {"products": _slot([_entity("SRTWC8517")])}
        out = fr.Outputs(focus=focus)
        o = {"entities": [_entity("SRTKS6091")]}

        fr.anaphora_reuses(focus, _turn(o, signals={"anaphora": True}), out)

        assert [e["raw"] for e in o["entities"]] == ["SRTKS6091"]

    def test_no_anaphora_signal_changes_nothing(self) -> None:
        """Prompt v1 and v2 never emit the key, so this lane is inert until v3 is promoted."""
        focus = {"products": _slot([_entity("SRTWC8517")])}
        out = fr.Outputs(focus=focus)
        o: dict[str, Any] = {"entities": []}

        fr.anaphora_reuses(focus, _turn(o, signals={}), out)

        assert o["entities"] == []
        assert "anaphora_unresolved" not in o


# --------------------------------------------------------------------------- #
# The order, the projection and the ageing
# --------------------------------------------------------------------------- #


class TestApplyRunsThemInThePlansOrder:
    def test_the_six_rules_run_and_in_this_order(self) -> None:
        """The order is load-bearing: `replace_same_axis` first so `reuse_alive` can ask a
        simple question, `reset_on_topic` before `reuse_alive` so a reset is not undone by
        the very next rule."""
        called: list[str] = []
        import app.services.chatbot.dialogue.focus as module

        originals = {}
        for name in (
            "replace_same_axis",
            "reset_on_topic",
            "reuse_alive",
            "domain_from_switch_word",
            "date_restated_only",
            "anaphora_reuses",
        ):
            originals[name] = getattr(module, name)

        def spy(name):
            def _f(focus, turn, out, _n=name):
                called.append(_n)
                return originals[_n](focus, turn, out)

            return _f

        try:
            for name in originals:
                setattr(module, name, spy(name))
            module.apply({}, _turn({"entities": []}))
        finally:
            for name, fn in originals.items():
                setattr(module, name, fn)

        assert called == [
            "replace_same_axis",
            "reset_on_topic",
            "reuse_alive",
            "domain_from_switch_word",
            "date_restated_only",
            "anaphora_reuses",
        ]


class TestFromSessionProjectsALegacySession:
    """Every live contact's session and every capture was written before `focus` existed."""

    def test_the_legacy_keys_become_slots_dated_to_the_turn_that_first_saw_them(self) -> None:
        projected = fr.from_session(
            {
                "entities": [_entity("SRTWC8517"), _entity("ABC", "customer")],
                "domain_hint": "inventory",
                "date_filter_start": "2026-08-01",
                "requested_attributes": ["quantity"],
                "access_levels": ["dealer"],
                "query_brands": ["cabana"],
            },
            turn_no=5,
        )

        assert set(projected) == {
            "products",
            "customer",
            "domain",
            "date_window",
            "attributes",
            "tier",
            "brands",
        }
        assert all(s["set_at_turn"] == 5 for s in projected.values()), (
            "dated to the turn that first SAW them: nobody can know when they were really "
            "set, so they get one full TTL from first sight"
        )
        assert all(s["source"] == "reuse" for s in projected.values())

    def test_an_EMPTY_focus_is_never_re_projected(self) -> None:
        """The defect this closes: `decay` writes `{}` when every slot ages out, and a
        projection that fell through on it rebuilt the slot from the legacy `entities` the
        tail is still writing - so the slot came back alive on the very turn it died and
        the TTL could never be reached."""
        assert (
            fr.from_session(
                {"focus": {}, "entities": [_entity("SRTWC8517")], "domain_hint": "inventory"},
                turn_no=9,
            )
            == {}
        )

    def test_a_focus_that_lost_ONE_slot_keeps_the_rest_and_projects_nothing(self) -> None:
        stored = {"domain": _slot("inventory", turn=8)}

        projected = fr.from_session(
            {"focus": stored, "entities": [_entity("SRTWC8517")]}, turn_no=9
        )

        assert set(projected) == {"domain"}, "the dead products slot is NOT rebuilt"

    def test_a_stored_focus_wins_over_the_projection(self) -> None:
        stored = {"products": _slot([_entity("SRTKS6091")], turn=9)}
        projected = fr.from_session(
            {"focus": stored, "entities": [_entity("SRTWC8517")]}, turn_no=10
        )

        assert [e["raw"] for e in fr.value_of(projected, "products")] == ["SRTKS6091"]

    def test_an_empty_session_projects_nothing(self) -> None:
        assert fr.from_session({}, turn_no=1) == {}
        assert fr.from_session(None, turn_no=1) == {}


class TestADeadSlotStopsTheEntityCarry:
    """AC-940's teeth: decay has to reach the ENTITY LIST or it changes nothing a customer
    can see. The executor's `reuse` arm carries the previous entities forward off the
    legacy session key, which the tail keeps writing whatever the focus says."""

    def test_a_carried_product_goes_when_its_slot_has_aged_out(self) -> None:
        out = fr.Outputs(focus={})
        o = {
            "entity_op_applied": "reuse",
            "entities": [_entity("SRTWC8517", current_message=False)],
        }

        fr.reuse_alive({}, _turn(o), out)

        assert o["entities"] == []
        assert o["entities_dropped_on_decay"] == ["product:SRTWC8517"]

    def test_the_drop_is_traced_against_the_slot_that_died(self) -> None:
        out = fr.Outputs(focus={})
        o = {
            "entity_op_applied": "reuse",
            "entities": [_entity("SRTWC8517", current_message=False)],
        }

        fr.reuse_alive({}, _turn(o), out)

        entry = next(e for e in out.entries if e["slot"] == "products")
        assert entry["rule"] == "reuse_alive"
        assert entry["before"] == ["SRTWC8517"]
        assert entry["after"] is None

    def test_an_alive_slot_keeps_its_carried_entity(self) -> None:
        focus = {"products": _slot([_entity("SRTWC8517")])}
        out = fr.Outputs(focus=focus)
        o = {
            "entity_op_applied": "reuse",
            "entities": [_entity("SRTWC8517", current_message=False)],
        }

        fr.reuse_alive(focus, _turn(o), out)

        assert [e["raw"] for e in o["entities"]] == ["SRTWC8517"]

    def test_an_entity_this_message_named_is_never_dropped(self) -> None:
        out = fr.Outputs(focus={})
        o = {"entity_op_applied": "replace_combine", "entities": [_entity("SRTWC8517")]}

        fr.reuse_alive({}, _turn(o), out)

        assert [e["raw"] for e in o["entities"]] == ["SRTWC8517"]

    def test_only_the_dead_axis_is_swept(self) -> None:
        focus = {"customer": _slot(_entity("ABC", "customer"))}
        out = fr.Outputs(focus=focus)
        o = {
            "entity_op_applied": "reuse",
            "entities": [
                _entity("SRTWC8517", current_message=False),
                _entity("ABC", "customer", current_message=False),
            ],
        }

        fr.reuse_alive(focus, _turn(o), out)

        assert [e["raw"] for e in o["entities"]] == ["ABC"]

    def test_an_axis_with_no_slot_of_its_own_is_left_alone(self) -> None:
        """An order number, a category, a flyer: nothing here knows when they go stale, so
        sweeping them up would be a guess dressed as a rule."""
        out = fr.Outputs(focus={})
        o = {
            "entity_op_applied": "reuse",
            "entities": [_entity("M2609-0086", "customer_order", current_message=False)],
        }

        fr.reuse_alive({}, _turn(o), out)

        assert [e["raw"] for e in o["entities"]] == ["M2609-0086"]


class TestAReuseNeverRefreshesTheClock:
    def test_reusing_a_slot_leaves_its_age_alone(self) -> None:
        """Otherwise the TTL is unreachable and the unbounded carry is back: a slot the
        customer keeps silently benefiting from is not one they keep restating."""
        focus = {"attributes": _slot(["quantity"], turn=1)}
        out = fr.Outputs(focus=focus)
        o = {"entity_op_applied": "reuse", "requested_attributes": [], "entities": []}

        fr.reuse_alive(focus, _turn(o, turn_no=3), out)

        assert focus["attributes"]["set_at_turn"] == 1
        assert focus["attributes"]["source"] == "reuse"


# --------------------------------------------------------------------------- #
# AC-950's grep, as a test
# --------------------------------------------------------------------------- #


_OUTPUT_EXCHANGE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "services"
    / "chatbot"
    / "head"
    / "output_exchange.py"
)


class TestTheRulesAreGoneFromOutputExchange:
    """AC-950 as a test rather than as a reviewer's memory.

    Each string below is a line of the DELETED rule body, not its diagnostic key: the
    diagnostics are deliberately still stamped, by the rule that took the decision over,
    which is what lets the corpus grade the move. A rule sneaking back in fails here.
    """

    @pytest.mark.parametrize(
        "gone",
        [
            # owner ruling K rule 4: the compatibility test and the retype
            'bare_type = BARE_ENTITY_TYPE_BY_DOMAIN.get(',
            'blocked_for_prev = set(DOMAIN_BLOCKED_HINTS.get(prev_dom, []))',
            # the `#6` switch-word override
            'o["domain_switched_by_keyword"] = switch_domain',
            # owner ruling K rule 2
            'tc_current = [e for e in o["entities"]',
            # `_query_brands_carried` / `_tier_carried`
            'o["_query_brands_carried"] = True',
            'o["_tier_carried"] = True',
            # the executor's carries
            'o["requested_attributes"] = prev_attrs',
            'o["domain_reused_entityless"] = True',
            'if jsc.truthy(jsc.get(pcs, "date_filter_start")):',
        ],
    )
    def test_the_rule_body_is_not_in_output_exchange(self, gone: str) -> None:
        assert gone not in _OUTPUT_EXCHANGE.read_text()

    @pytest.mark.parametrize(
        "rule",
        [
            "replace_same_axis",
            "reset_on_topic",
            "reuse_alive",
            "domain_from_switch_word",
            "date_restated_only",
            "anaphora_reuses",
        ],
    )
    def test_every_named_rule_the_plan_lists_exists(self, rule: str) -> None:
        assert callable(getattr(fr, rule))
