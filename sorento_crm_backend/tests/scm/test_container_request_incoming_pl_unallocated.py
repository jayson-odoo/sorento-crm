"""AC-N2 / AC-N2b - Incoming PL is the unallocated part of a packing list, everywhere shown.

`PLAN-scm-loading-plan-lines-feedback-12sep.md`, item 2 ("SPO and Incoming PL double-count").
Row 1 on the captain's own plan showed SPO 10,000 AND Incoming PL 10,000 for the SAME
container: the packing list already has its SPO. `incoming_pl` (the cell), the shipment list
behind it and the Incoming PL lightbox (`container_request_drill`, kind `incoming_pl`) used to
read `PL_REMAINING_SQL` - the whole unreceived quantity, including the part already turned
into an SPO. This file pins the fix: every one of the three reads `PL_UNALLOCATED_SQL`
instead, and a shipment fully allocated to an SPO is ABSENT from the shipments list, not
present at zero.

Postgres, marker-prefixed, every chain seeded here (CI's database is empty).
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.procurement import InboundShipment, InboundShipmentLine
from app.services.scm import container_request_drill as drill_svc
from app.services.scm import container_request_service as build_svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg
from tests.scm.test_plan_owned_statement import World, _retail_need, _row

pytestmark = requires_pg

MARKER = "ZZPLU"


def _packing_line(
    db,
    w: World,
    key: str,
    *,
    shipped: float,
    spo_allocated: float,
    received: float = 0,
) -> InboundShipment:
    """One packing-list line, not yet arrived - the Incoming PL reference (AC-N2)."""
    ship = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=f"{MARKER}-PL-{uuid.uuid4().hex[:8]}",
        supplier_id=w.supplier.id,
        shipment_date=date(2026, 1, 1),
        estimated_arrival_date=date(2026, 9, 30),
        actual_arrival_date=None,
        shipment_status="in_transit",
    )
    db.add(ship)
    db.flush()
    db.add(
        InboundShipmentLine(
            id=str(uuid.uuid4()),
            shipment_id=ship.id,
            product_id=w.product(key).id,
            supplier_id=w.supplier.id,
            quantity_shipped=shipped,
            spo_allocated_quantity=spo_allocated,
            quantity_received=received,
        )
    )
    db.flush()
    return ship


def _on_file(db, w: World, plan, key: str, *, need: float = 10) -> None:
    """A row the universe rule keeps under EITHER rule - on the plan's stock list AND
    linked - so this file's assertions are about the Incoming PL figure, not the universe."""
    w.stock_row(key, packed=0, plan_id=str(plan.id))
    w.link(key)
    _retail_need(db, w, key, need)


def test_a_shipment_fully_allocated_to_an_spo_is_not_shown_as_incoming_pl():
    """AC-N2. 10,000 shipped, 10,000 already on an SPO, none received: nothing left to ask
    Incoming PL for - the SPO cell already carries it."""
    with pg_session() as db:
        w = World(db)
        plan = w.plan("stock_list")
        _on_file(db, w, plan, "FULL")
        _packing_line(db, w, "FULL", shipped=10000, spo_allocated=10000, received=0)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)

        row = _row(out, w.code("FULL"))
        assert row["incoming_pl"] == 0
        assert row["incoming_pl_unallocated"] == 0
        assert row["incoming_pl_shipments"] == []


def test_a_partly_allocated_shipment_shows_only_the_unallocated_part():
    """AC-N2. 100 shipped, 40 already on an SPO: 60 left to ask Incoming PL for."""
    with pg_session() as db:
        w = World(db)
        plan = w.plan("stock_list")
        _on_file(db, w, plan, "PART")
        _packing_line(db, w, "PART", shipped=100, spo_allocated=40, received=0)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)

        row = _row(out, w.code("PART"))
        assert row["incoming_pl"] == 60
        assert row["incoming_pl_unallocated"] == 60
        assert [s["qty"] for s in row["incoming_pl_shipments"]] == [60]


def test_the_incoming_pl_lightbox_lists_the_same_figure_as_the_cell():
    """AC-N2b. The drill's rows sum to the cell (the AC-G3 rule); a fully allocated shipment
    lists nothing, exactly like the cell."""
    with pg_session() as db:
        w = World(db)
        plan = w.plan("stock_list")
        _on_file(db, w, plan, "PART")
        _on_file(db, w, plan, "FULL")
        _packing_line(db, w, "PART", shipped=100, spo_allocated=40, received=0)
        _packing_line(db, w, "FULL", shipped=10000, spo_allocated=10000, received=0)

        part_drill = drill_svc.drill(
            db, supplier_id=str(w.supplier.id), product_id=str(w.product("PART").id),
            kind="incoming_pl",
        )
        full_drill = drill_svc.drill(
            db, supplier_id=str(w.supplier.id), product_id=str(w.product("FULL").id),
            kind="incoming_pl",
        )

        assert part_drill["total"] == 60
        assert [r["qty"] for r in part_drill["rows"]] == [60]
        assert full_drill["total"] == 0
        assert full_drill["rows"] == []
