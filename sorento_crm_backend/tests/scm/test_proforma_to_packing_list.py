"""F6 / F10 - what the packing list knows about the proforma invoices behind it.

TEST-FIRST: the cbm carry-over, the per-link quantity, the add-to-existing-draft option and
the "which packing list is this PI in" reads do not exist at the time this file is written,
so every test here is expected to be red until they land.

Postgres via `pg_session` (rolled back at teardown), same as the rest of this channel: the
reader resolves its header aliases from the alias table, so these suites also prove the
migrations were run rather than merely written. Nothing is borrowed from an existing table.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.procurement import InboundShipment, InboundShipmentLine
from app.models.scm import ProformaInvoiceShipmentLink
from app.services.error_handler import AppException
from app.services.scm import proforma_invoice_service as svc
from tests._pg_fixture import pg_session
from tests.scm.fixtures.proforma_shapes import (
    kailu_proforma_workbook,
    preloading_list_workbook,
)
from tests.scm.test_proforma_invoice_import import World, _invoices, _lines
from tests.scm.test_proforma_invoice_adjust import _seed_container_sizes


def _apply_preloading(db, w: World):
    data = preloading_list_workbook(
        {
            "SRTWC287A-RL-250": w.code("A"),
            "CWB242": w.code("B"),
            "SRTWC8357-RL-180": w.code("C"),
        }
    )
    svc.apply(db, data, supplier_id=str(w.supplier.id), actor="Ms Tee")
    return _invoices(db, w)


def _shipment_lines(db, shipment_id: str) -> list[InboundShipmentLine]:
    return (
        db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == str(shipment_id))
        .all()
    )


# --------------------------------------------------------------------------------- #
# AC-F1 - the volume survives the conversion
# --------------------------------------------------------------------------------- #


def test_converting_copies_each_lines_volume_onto_the_shipment_line():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        # Block 5 is 27.1 cbm, inside a 65 cbm 40HQ, so no override is needed.
        invoice = _apply_preloading(db, w)[4]
        matched = [ln for ln in _lines(db, invoice.id) if ln.product_id]

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        lines = _shipment_lines(db, out["shipment_id"])
        assert len(lines) == len(matched)
        by_product = {str(ln.product_id): ln for ln in lines}
        for pi_line in matched:
            shipment_line = by_product[str(pi_line.product_id)]
            assert float(shipment_line.cbm) == pytest.approx(float(pi_line.cbm_total))
            assert shipment_line.cartons_count == int(pi_line.cartons)


def test_an_unmeasured_invoice_leaves_the_shipment_line_volume_null():
    """AC-H3 - a PI without cbm converts as before. NULL, never 0: 0 cbm would be summed as
    a container that takes no room."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        svc.apply(db, kailu_proforma_workbook({"SRTWT7443": w.code("A")}),
                  supplier_id=str(w.supplier.id))
        invoice = _invoices(db, w)[0]

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        for line in _shipment_lines(db, out["shipment_id"]):
            assert line.cbm is None


def test_two_invoice_lines_of_one_product_add_their_volumes_up():
    """The convert groups by (product, supplier), so two lines naming the same model become
    one shipment line - and its volume is both of them, not the first one."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        # Kailu name SRTWT7443 on two lines. Volume is added to both of them here, since
        # their real document states none at all.
        svc.apply(db, kailu_proforma_workbook({"SRTWT7443": w.code("A")}),
                  supplier_id=str(w.supplier.id))
        invoice = _invoices(db, w)[0]
        pi_lines = [ln for ln in _lines(db, invoice.id) if str(ln.product_id or "") == str(w.product("A").id)]
        assert len(pi_lines) >= 2
        for i, line in enumerate(pi_lines, start=1):
            # Small enough that the two lines together still fit a 65 cbm 40HQ - this test
            # is about the arithmetic of the merge, not about the capacity guard.
            line.cbm_per_unit = 0.01
            line.cbm_total = 0.01 * float(line.qty)
            line.cartons = i
        db.flush()
        expected_cbm = sum(float(ln.cbm_total) for ln in pi_lines)
        expected_cartons = sum(int(ln.cartons) for ln in pi_lines)

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        line = next(
            ln for ln in _shipment_lines(db, out["shipment_id"])
            if str(ln.product_id) == str(w.product("A").id)
        )
        assert float(line.cbm) == pytest.approx(expected_cbm)
        assert line.cartons_count == expected_cartons
