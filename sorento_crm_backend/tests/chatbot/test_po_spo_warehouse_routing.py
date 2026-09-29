"""RED tests - the word SPO routes to spo_allocation, incoming stays untouched.

`documentation/plans/chatbot/PLAN-po-spo-warehouse-29sep.md` section S1;
`documentation/plans/chatbot/po-spo-warehouse-29sep-acceptance-criteria.md` AC-1, AC-2.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import verdict


def _plan_for(document: list[str]):
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.policy import default_policy
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile(), turn_no=0)
    _state, plan = apply(state, verdict(document=document), default_policy())
    return plan


class TestSpoDocumentRoutesToSpoAllocation:
    def test_the_document_map_sends_spo_to_spo_allocation(self) -> None:
        from app.services.chatbot.turn.apply import DOMAIN_BY_DOCUMENT

        assert DOMAIN_BY_DOCUMENT["SPO"] == "spo_allocation"

    def test_the_other_documents_are_unchanged(self) -> None:
        from app.services.chatbot.turn.apply import DOMAIN_BY_DOCUMENT

        assert DOMAIN_BY_DOCUMENT["PO"] == "purchase_order"
        assert DOMAIN_BY_DOCUMENT["SO"] == "order"
        assert DOMAIN_BY_DOCUMENT["DO"] == "order"
        assert DOMAIN_BY_DOCUMENT["GRN"] == "goods_receive"

    def test_incoming_is_not_a_value_of_the_document_map(self) -> None:
        from app.services.chatbot.turn.apply import DOMAIN_BY_DOCUMENT

        assert "incoming" not in DOMAIN_BY_DOCUMENT.values()

    def test_apply_plans_spo_allocation_for_an_spo_document(self) -> None:
        plan = _plan_for(["SPO"])
        assert list(plan.domains) == ["spo_allocation"], plan.domains
        assert "domain_follows_document" in plan.trace.rules_fired

    def test_apply_plans_purchase_order_for_a_po_document(self) -> None:
        plan = _plan_for(["PO"])
        assert list(plan.domains) == ["purchase_order"], plan.domains
        assert "domain_follows_document" in plan.trace.rules_fired


class TestIncomingIsUntouched:
    """The `incoming` row of `turn/policy_rows.py`, pinned as literals (owner: "incoming
    stays as it is")."""

    def _row(self):
        from app.services.chatbot.turn.policy import default_policy

        row = default_policy().domain("incoming")
        assert row is not None
        return row

    def test_tools(self) -> None:
        assert tuple(self._row().tools) == (
            "crm_incoming_stock_list",
            "crm_incoming_stock_by_product",
            "crm_incoming_stock_shipments",
        )

    def test_switch_words(self) -> None:
        assert tuple(self._row().switch_words) == (
            "incoming", "eta", "shipment", "shipments", "arriving", "container", "containers",
        )

    def test_intents_label_and_team(self) -> None:
        row = self._row()
        assert tuple(row.intents) == ("check_incoming",)
        assert row.label == "incoming stock"
        assert row.escalation_team_code == "purchasing"

    def test_narrowing_and_ladder(self) -> None:
        row = self._row()
        assert dict(row.narrowing) == {"product": "narrow_to_code"}
        assert tuple(row.ladder) == ("inventory", "purchase_order")
        assert row.reveal_key is None
        assert row.supported is True

    def test_spo_allocation_keeps_its_spo_switch_word(self) -> None:
        from app.services.chatbot.turn.policy import default_policy

        row = default_policy().domain("spo_allocation")
        assert row is not None
        assert "spo" in row.switch_words
