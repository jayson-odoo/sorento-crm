"""AC-1 / AC-2 (chatbot-warehouse-entity-and-last-in): warehouse survives the gate for
`inventory` and `spo_allocation`, and the entity-ids transformer turns a resolved warehouse
into `warehouse_ids`.

`documentation/plans/chatbot/PLAN-chatbot-warehouse-entity-and-last-in.md`;
`chatbot-warehouse-entity-and-last-in-acceptance-criteria.md` AC-1, AC-2.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot.lanes.business import fetch
from app.services.chatbot.lanes.business.gate import run_gate

PRODUCT_UUID = "11111111-1111-1111-1111-111111111111"
WAREHOUSE_UUID = "22222222-2222-2222-2222-222222222222"
CUSTOMER_UUID = "33333333-3333-3333-3333-333333333333"


def _match(uuid: str, entity_type: str, code: str) -> dict[str, Any]:
    return {"uuid": uuid, "entity_type": entity_type, "canonical_code": code}


def _resolver(*matches: dict[str, Any]) -> dict[str, Any]:
    return {
        "resolutions": [{"token": m["canonical_code"], "resolved": True, "matches": [m]} for m in matches],
    }


class TestGateKeepsWarehouse:
    def test_inventory_keeps_product_and_warehouse(self) -> None:
        resolver = _resolver(
            _match(PRODUCT_UUID, "product", "SRT62-GM"),
            _match(WAREHOUSE_UUID, "warehouse", "BRW"),
        )
        out = run_gate(
            dict(resolver),
            parser={"domain_hint": "inventory", "entities": []},
            resolver=resolver,
        )
        types = {e["entity_type"] for e in out["compatible_entities"]}
        assert types == {"product", "warehouse"}

    def test_spo_allocation_keeps_product_and_warehouse_and_drops_customer(self) -> None:
        resolver = _resolver(
            _match(PRODUCT_UUID, "product", "SRT62-GM"),
            _match(WAREHOUSE_UUID, "warehouse", "BRW"),
            _match(CUSTOMER_UUID, "customer", "ABC SDN BHD"),
        )
        out = run_gate(
            dict(resolver),
            parser={"domain_hint": "spo_allocation", "entities": []},
            resolver=resolver,
        )
        types = {e["entity_type"] for e in out["compatible_entities"]}
        assert types == {"product", "warehouse"}
        assert "customer" not in types


class TestZeroEntitySpoAllocationAsksInsteadOfFanningOut:
    """Follow-up ruling (8 Sep 2026, chatbot-warehouse-entity-and-last-in): with
    one-row-per-product semantics, an unscoped "last in" (no product, no warehouse - no
    entity at all) would otherwise fan out to a row for every product in the table. The
    gate must refuse it, and the miss lane must render a clarification instead of the
    turn ever reaching fetch."""

    def _empty_gate(self) -> dict[str, Any]:
        resolver: dict[str, Any] = {"resolutions": []}
        return run_gate(
            dict(resolver),
            parser={"domain_hint": "spo_allocation", "entities": []},
            resolver=resolver,
        )

    def test_gate_fails_with_no_entities(self) -> None:
        out = self._empty_gate()
        assert out["gate_passed"] is False
        assert "requires a scoping entity" in out["gate_reason"]

    def test_the_miss_branch_fires_not_the_continue_branch(self) -> None:
        """`if3_miss` is what `resolve_gate.run` checks BEFORE it would ever reach
        fetch - True here means the turn takes the clarification exit, not the
        continue-to-fetch one."""
        from app.services.chatbot.lanes.business.resolve_gate import if3_miss

        gate = self._empty_gate()
        ctx_resolved_ctx = {"gate": gate}
        assert if3_miss(ctx_resolved_ctx, parser={"domain_hint": "spo_allocation", "entities": []}) is True

    def test_a_clarification_is_rendered(self) -> None:
        from app.services.chatbot.lanes.business.answer import not_found_error_message

        parser = {
            "domain_hint": "spo_allocation",
            "entities": [],
            "routing": {"suggested_team": "procurement"},
            "access_levels": [],
        }
        resolved: dict[str, Any] = {"by_entity_type": {}, "tokens": [], "unresolved_tokens": []}
        gate = self._empty_gate()

        out = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        assert out.get("is_clarification") is True
        assert (out.get("escalate_message") or "").strip() != ""


class TestTransformerEmitsWarehouseIds:
    def test_warehouse_entity_becomes_warehouse_ids(self) -> None:
        trigger = {
            "entities": [
                {"entity_type": "product", "uuid": PRODUCT_UUID, "code": "SRT62-GM"},
                {"entity_type": "warehouse", "uuid": WAREHOUSE_UUID, "code": "BRW"},
            ],
            "tool": "crm_procurement_spo_allocations_last_receipt_list",
            "semantic_input": {"contact_id": "1", "space_id": "s"},
        }
        out = fetch.entity_ids_transformer(trigger)
        assert out["warehouse_ids"] == [WAREHOUSE_UUID]
        assert out["product_ids"] == [PRODUCT_UUID]
