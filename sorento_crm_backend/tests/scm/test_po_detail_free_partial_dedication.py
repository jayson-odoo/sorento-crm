"""AC-6.16 (G14/D3, captain 2 Sep 2026), the PARTIAL half of the Allocated-to panel's
arithmetic the coder's own `test_the_allocated_to_panel_nets_a_dedication_out_of_free_and_
names_it` (`tests/scm/test_write_time_supply_claim.py`) does not cover: that test's line
is either wholly dedicated (Free 0) or wholly settled (block gone). Real lines sit in
between - part already placed for the row's OWN sales order, part still reserved by
ANOTHER order's claim that has not placed anything yet - and `Free` has to net both at
once: `Free = outstanding - own_links - other_claims_unplaced`.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.services.scm import order_link_service
from app.services.scm.purchase_order_service import PurchaseOrderService
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg

pytestmark = requires_pg

MARKER = "ZZTPOFREE"

SOON = date.today() + timedelta(days=45)


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    from app.models.base import company_scope
    from tests.scm.conftest import SORENTO_COMPANY_ID, ensure_reference_data

    with pg_session() as session:
        ensure_reference_data(session)
        with company_scope(session, frozenset({SORENTO_COMPANY_ID})):
            yield session


def _project_bin(db, code: str) -> str:
    wid = _u()
    db.execute(
        text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "segment, created_at, updated_at) "
            "VALUES (:i, :c, :c, true, 'project', now(), now())"
        ),
        {"i": wid, "c": code},
    )
    db.flush()
    return wid


def _open_line(db, *, product_id, warehouse_id, qty) -> tuple:
    po_id = _u()
    db.execute(
        text(
            "INSERT INTO purchase_orders (id, po_number, status, issue_date, "
            "currency, source_system) "
            "VALUES (:i, :n, 'active', :d, 'MYR', 'scm_upload')"
        ),
        {"i": po_id, "n": f"{MARKER}-{uuid.uuid4().hex[:8].upper()}", "d": date(2026, 8, 1)},
    )
    line_id = _u()
    db.execute(
        text(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
            "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status, "
            "expected_date) VALUES (:i, :po, :p, :w, :q, 0, 10, 'MYR', 'open', :e)"
        ),
        {"i": line_id, "po": po_id, "p": product_id, "w": warehouse_id, "q": qty,
         "e": SOON},
    )
    db.flush()
    return po_id, line_id


def test_ac_6_16_free_nets_both_an_own_placement_and_another_sos_unplaced_reservation(db):
    """PO line 100 at a project bin: the row's OWN sales order has already placed 30 of
    it (an ordinary link), and a DIFFERENT sales order's claim reserves 50 more that
    nothing has placed yet. Free is neither 100-30=70 (ignoring the reservation, the G14
    defect) nor 100-30-50-more (double-subtracting the 30 as if it were also a
    reservation) - it is 20, and the block names the 50 as the other order's, unplaced.
    """
    from tests.scm.test_channel_read_model import _confirmed_leg, _core_so_line
    from tests.scm.test_m3_run import _mk_product
    from app.models.procurement import PurchaseOrder

    bin_id = _project_bin(db, f"{MARKER}-IB-{uuid.uuid4().hex[:6].upper()}")
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")
    po_id, line_id = _open_line(db, product_id=pid, warehouse_id=bin_id, qty=100)

    # The row's OWN sales order: 30 already PLACED on this line (an ordinary link, no
    # claim needed for the panel to count it in `allocated`).
    own = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=30)
    from app.models.project_so import OrderInquiryLink

    db.add(OrderInquiryLink(
        id=_u(), row_id=own["inquiry_row"].id, po_line_id=line_id,
        document=f"{MARKER}-doc", qty=30, auto=True,
    ))
    db.flush()

    # A DIFFERENT sales order's claim: 50 reserved, nothing placed under it yet.
    claiming_so, claiming_line = _core_so_line(
        db, product_id=pid, warehouse_id=bin_id, qty=50, demand_class="project",
    )
    order_link_service.claim_placed_on_po(
        db, company_id=None, so_number=claiming_so.so_number, po_number=f"{MARKER}-x",
        item_code=None, so_line_id=str(claiming_line.id), po_line_id=line_id,
        source=order_link_service.SOURCE_PO_UPLOAD,
    )
    db.flush()

    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one()
    block = next(
        b for b in PurchaseOrderService(db)._allocations_for(po) if b["line_id"] == line_id
    )
    assert block["outstanding"] == 100.0
    assert block["allocated"] == 30.0
    assert block["free"] == 20.0, (
        "Free must net BOTH the row's own 30 placed and the other order's 50 "
        "reserved-but-unplaced, not either alone"
    )
    assert [d["so_number"] for d in block["dedicated_to"]] == [claiming_so.so_number]
    assert block["dedicated_to"][0]["reserved"] == 50.0
    assert block["dedicated_to"][0]["unplaced"] == 50.0, (
        "nothing has been linked under this claim yet"
    )
