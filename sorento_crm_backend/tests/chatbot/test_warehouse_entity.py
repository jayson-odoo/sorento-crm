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
