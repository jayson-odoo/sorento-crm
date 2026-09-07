"""AC-X53 (writers stamp) - spo-xlsx-supersede round 7, security round 6, PLAN D25c amended.

`spo_conversion_service._write_allocations` and `allocation_suggestion_service`'s accept
path (`approve`) each raise ONE `spo_allocations` row per purchase-order line - never an
Excel aggregate - and must stamp `source_system = 'crm_spo'` so the first-push supersede's
`is_xlsx_era_row` guard (AC-X52) leaves them alone regardless of `po_line_id`.
`SPOAllocationCreate.source_system` is optional so this is additive, not a breaking change
to any other caller's shape.

Postgres only (`pg_session`), marker-prefixed, every test seeds its own chain. Fixtures
reused wholesale from the two services' own test files (`tests/scm/test_spo_conversion.py`,
`tests/scm/test_allocation_suggestion.py`) per the tester brief - imported, not copied.
"""
from __future__ import annotations

from datetime import date

from app.models.procurement import SPOAllocation
from app.services.scm import allocation_suggestion_service as suggestion_svc
from app.services.scm import spo_conversion_service as conversion_svc
from tests._pg_fixture import pg_session
from tests.scm.test_allocation_suggestion import World as SuggestionWorld
from tests.scm.test_spo_conversion import World as ConversionWorld


def test_spo_conversion_create_stamps_source_system_crm_spo_on_every_allocation():
    """AC-X53. `spo_conversion_service.create` (which reaches `_write_allocations`) must
    stamp `source_system = 'crm_spo'` on every SPOAllocation row it writes.

    RED today: `_write_allocations` never passes `source_system` to `SPOAllocationCreate`
    at all - every row it writes has NULL, which the D25c predicate cannot distinguish
    from a genuine Excel aggregate (the exact AC-X52 hazard: superseding a PO-linked row
    would sever the PO -> SPO -> GRN chain silently).
    """
    with pg_session() as db:
        w = ConversionWorld(db)
        warehouse = w.warehouse("SELLABLE")
        supplier = w.supplier()
        w.po("1", supplier, [("A", 40, 0)])
        shipment, lines = w.shipment([("A", 40, supplier)])

        # A confirm line writes an allocation only when it names a location
        # to land in (B4, review round 1 - the link a confirm writes hangs
        # off an allocation, so a bare qty/include pair with no
        # `location_splits` writes an SPO line but no allocation at all).
        conversion_svc.create(
            db, str(shipment.id),
            [{
                "shipment_line_id": str(lines[0].id), "qty": 40, "include": True,
                "location_splits": [{"warehouse_id": str(warehouse.id), "qty": 40}],
            }],
            actor="tester",
        )

        allocations = (
            db.query(SPOAllocation)
            .filter(SPOAllocation.inbound_shipment_id == shipment.id)
            .all()
        )
        assert allocations, "the conversion must have written at least one allocation"
        for allocation in allocations:
            assert allocation.source_system == "crm_spo", (
                "every spo_conversion_service-written allocation must be stamped "
                f"crm_spo - got {allocation.source_system!r} on {allocation.id}"
            )


def test_allocation_suggestion_approve_stamps_source_system_crm_spo():
    """AC-X53, `allocation_suggestion_service`'s accept path. `approve` must stamp the
    same `crm_spo` marker on the SPOAllocation row it writes - the IDENTICAL write
    `spo_conversion_service._write_allocations` uses (`SPOAllocationService.
    create_allocation`), so the two writers can never disagree about what stamps a row
    as "one line, one PO line, never an aggregate".

    RED today: `approve` builds `SPOAllocationCreate` with no `source_system` at all.
    """
    with pg_session() as db:
        w = SuggestionWorld(db)
        w.po("1", [("A", 10, 0, "BRW")], issue_date=date(2026, 1, 1))
        shipment = w.shipment([("A", 10)])
        suggestion = suggestion_svc.suggest(db, str(shipment.id))["lines"][0]

        suggestion_svc.approve(db, str(shipment.id), [
            {
                "shipment_line_id": suggestion["shipment_line_id"],
                "splits": [{
                    "po_line_id": suggestion["suggestion"]["po_line_id"],
                    "warehouse_id": suggestion["suggestion"]["warehouse_id"],
                    "qty": 10,
                }],
            }
        ])

        allocation = (
            db.query(SPOAllocation)
            .filter(SPOAllocation.inbound_shipment_id == shipment.id)
            .one()
        )
        assert allocation.source_system == "crm_spo", (
            "allocation_suggestion_service.approve must stamp crm_spo - got "
            f"{allocation.source_system!r}"
        )
