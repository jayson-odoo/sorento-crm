"""Port of `test_warehouse_entity.py::TestAWarehouseIsNotADocumentFilter` (AC-1592).

Review S1 (8 Sep 2026), live exec 11818957: a warehouse code (`HOLD`, `DISPLAY`,
`REPAIR` - ordinary-looking words) must not filter a document-list fetch
(`crm_resource_attachments_list` has no warehouse parameter at all), the same class of
defect as a brand/category entity leaking into a tool with no matching parameter. The
old `head/output_exchange.py` dropped the entity in post-process
(`out["broaden_dropped"] == ["warehouse:hold"]`); that module is deleted.

Grepped the whole `app/services/chatbot/` tree for `broaden_dropped` this session:
zero hits anywhere, including `lanes/business/fetch.py` and `gate.py` (both kept).
Probed the gate directly (the seam `test_warehouse_entity.py`'s OTHER four classes
already exercise for the same domain, `TestGateKeepsWarehouse`) with a
`resource_attachment` domain and a warehouse-only entity: `gate_reason` reads
"domain 'resource_attachment' not in matrix; passing through unscoped" and
`compatible_entities` still carries the warehouse untouched - the gate does not
reproduce the old drop either. No seam in the new pipeline currently enforces this
rule. RED for that real reason, not a fixture bug. Reported to the captain; not the
tester's fix to make (LESSONS: "do not chase further as tester").
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot.lanes.business.gate import run_gate

WAREHOUSE_UUID = "22222222-2222-2222-2222-222222222222"


def _match(uuid: str, entity_type: str, code: str) -> dict[str, Any]:
    return {"uuid": uuid, "entity_type": entity_type, "canonical_code": code}


def _resolver(*matches: dict[str, Any]) -> dict[str, Any]:
    return {
        "resolutions": [{"token": m["canonical_code"], "resolved": True, "matches": [m]} for m in matches],
    }


class TestWarehouseDroppedOnADocumentTurn:
    def test_a_warehouse_entity_does_not_reach_a_document_fetch_as_compatible(self) -> None:
        resolver = _resolver(_match(WAREHOUSE_UUID, "warehouse", "HOLD"))

        out = run_gate(
            dict(resolver),
            parser={"domain_hint": "resource_attachment", "entities": []},
            resolver=resolver,
        )

        types = {e["entity_type"] for e in out["compatible_entities"]}
        assert "warehouse" not in types, (
            "a warehouse code (HOLD/DISPLAY/REPAIR read like ordinary words) must not "
            "reach a document-list fetch as a filter - crm_resource_attachments_list "
            "has no warehouse parameter at all (review S1, live exec 11818957); got "
            f"compatible_entities entity types {types!r}. The old head/output_exchange.py "
            "dropped this in post-process (broaden_dropped); no equivalent exists in "
            "gate.run_gate or lanes/business/fetch.py today (grepped both, zero hits "
            "for broaden_dropped)."
        )

    def test_the_two_domains_whose_tools_take_warehouse_ids_still_keep_it(self) -> None:
        """Guard, green today: the negative that keeps the finding above narrow -
        `warehouse` is the whole point of the entity on `inventory`/`spo_allocation`,
        already proven by this file's sibling `TestGateKeepsWarehouse`."""
        for domain in ("inventory", "spo_allocation"):
            resolver = _resolver(_match(WAREHOUSE_UUID, "warehouse", "BRW"))
            out = run_gate(
                dict(resolver),
                parser={"domain_hint": domain, "entities": []},
                resolver=resolver,
            )
            types = {e["entity_type"] for e in out["compatible_entities"]}
            assert "warehouse" in types, (domain, types)
