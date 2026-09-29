"""RED tests - the sort rides the focus like the date window.

`documentation/plans/chatbot/PLAN-po-spo-warehouse-29sep.md` section S5;
`documentation/plans/chatbot/po-spo-warehouse-29sep-acceptance-criteria.md` AC-6, AC-7, AC-8.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import entity, verdict

SORT = {"by": "quantity", "dir": "desc"}


def _state(focus):
    from app.services.chatbot.turn.state import Profile, State

    return State(focus=focus, pending=None, profile=Profile(), turn_no=1)


def _apply(focus, v):
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.policy import default_policy

    return apply(_state(focus), v, default_policy())


def _po_focus(**extra):
    from app.services.chatbot.turn.state import Focus

    focus = Focus(domains=["purchase_order"], **extra)
    # Set after construction: `Focus(sort=...)` is a TypeError until the field exists, which
    # would fail every test below on the constructor instead of on its own behaviour.
    focus.sort = dict(SORT)
    return focus


# --------------------------------------------------------------------------- #
# AC-6 - the wire
# --------------------------------------------------------------------------- #


class TestFocusSortWire:
    def test_a_fresh_focus_has_no_sort(self) -> None:
        from app.services.chatbot.turn.state import Focus

        assert getattr(Focus(), "sort", "missing") is None

    def test_focus_to_wire_writes_sort(self) -> None:
        from app.services.chatbot.turn.state import Focus, focus_to_wire

        wire = focus_to_wire(Focus(sort={"by": "quantity", "dir": "desc"}))
        assert wire.get("sort") == {"by": "quantity", "dir": "desc"}

    def test_focus_from_wire_round_trips_sort(self) -> None:
        from app.services.chatbot.turn.state import Focus, focus_from_wire, focus_to_wire

        wire = focus_to_wire(Focus(sort={"by": "date", "dir": None}))
        assert focus_from_wire(wire).sort == {"by": "date", "dir": None}

    def test_an_old_wire_without_the_key_reads_none(self) -> None:
        from app.services.chatbot.turn.state import Focus, focus_from_wire, focus_to_wire

        wire = focus_to_wire(Focus())
        wire.pop("sort", None)
        assert getattr(focus_from_wire(wire), "sort", "missing") is None


# --------------------------------------------------------------------------- #
# AC-7 - apply()
# --------------------------------------------------------------------------- #


class TestSortCarriesLikeTheDateWindow:
    def test_a_verdict_naming_a_sort_writes_it_on_the_focus(self) -> None:
        from app.services.chatbot.turn.state import Focus

        v = verdict(
            domain_hint="purchase_order", intent_hint="check_po",
            document=["PO"], sort_by="quantity", sort_dir="desc",
        )
        state2, _plan = _apply(Focus(), v)
        assert getattr(state2.focus, "sort", None) == {"by": "quantity", "dir": "desc"}

    def test_a_sort_only_message_plans_a_purchase_order_fetch_and_replaces_the_sort(self) -> None:
        v = verdict(
            message_type="business_query", domain_hint=None, entities=[],
            domain_in_message=False, sort_by="date", sort_dir=None,
        )
        state2, plan = _apply(_po_focus(), v)
        assert list(plan.domains) == ["purchase_order"], plan.domains
        assert getattr(state2.focus, "sort", None) == {"by": "date", "dir": None}

    def test_a_new_ask_that_names_no_sort_drops_it(self) -> None:
        v = verdict(
            domain_hint="order", intent_hint="check_order", domain_in_message=True,
            entities=[entity("ABC", "customer")],
        )
        state2, plan = _apply(_po_focus(), v)
        assert getattr(state2.focus, "sort", "missing") is None
        assert "new_ask_drops_sort" in plan.trace.rules_fired, plan.trace.rules_fired

    def test_a_refinement_keeps_the_sort(self) -> None:
        v = verdict(
            entities=[entity("SRT79-SS", "product")], domain_in_message=False,
        )
        state2, plan = _apply(_po_focus(), v)
        assert getattr(state2.focus, "sort", None) == SORT
        assert "new_ask_drops_sort" not in plan.trace.rules_fired

    def test_a_topic_reset_clears_the_sort(self) -> None:
        v = verdict(topic_reset=True, entities=[])
        state2, _plan = _apply(_po_focus(), v)
        assert getattr(state2.focus, "sort", "missing") is None


# --------------------------------------------------------------------------- #
# AC-8 - lane_parse_output projects the carried sort
# --------------------------------------------------------------------------- #


class TestLaneParseOutputProjectsTheSort:
    def _out(self, v, focus):
        from app.services.chatbot import turn_runtime

        return turn_runtime.lane_parse_output(v, focus=focus, domain="purchase_order")

    def test_the_focus_sort_fills_a_verdict_that_names_none(self) -> None:
        out = self._out(verdict(), _po_focus())
        assert out.get("sort_by") == "quantity"
        assert out.get("sort_dir") == "desc"

    def test_the_verdicts_own_sort_wins(self) -> None:
        out = self._out(verdict(sort_by="supplier", sort_dir="asc"), _po_focus())
        assert out["sort_by"] == "supplier"
        assert out["sort_dir"] == "asc"

    def test_no_focus_sort_leaves_the_keys_unset(self) -> None:
        from app.services.chatbot.turn.state import Focus

        out = self._out(verdict(), Focus(domains=["purchase_order"]))
        assert not out.get("sort_by")
