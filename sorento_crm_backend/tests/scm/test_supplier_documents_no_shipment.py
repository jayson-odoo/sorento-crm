"""S3 - one birth for our packing list (`scm-supplier-documents-pi-first-acceptance-
criteria.md`, section C).

TEST-FIRST (Phase 2): AC-C1 says `supplier_document_service.apply` must never create an
`inbound_shipments` row any more - `packing_list_service.apply`, `_match_prices` and the
R14 link-writing path are DELETED from that call path. Today they are still very much
present (`test_supplier_document_service.py::test_apply_writes_two_invoices_two_shipments_
and_links_the_shared_codes` is the regression guard for the CURRENT behaviour this slice
deletes), so `test_c1_...` below is expected to be RED for the opposite reason to most of
this lane's other red tests: it fails today because a shipment IS created, not because
something is missing.

AC-C5's second half ("one PI packing set") depends on S2's new `proforma_invoice_packing_
line` table, which does not exist yet either - so `test_c5_...` is red for a second,
independent reason (`ImportError`) until S2 lands. Per the slice order (S3 -> S1 -> S2 ->
S4 -> S5) this file's C5 half is expected to stay red through the S3 slice and go green
only once S2 ships; that is intentional, not a fixture bug - noted so the coder is not
confused mid-slice.

Postgres via `blank_session`, same fixtures and seeding as `test_supplier_document_
service.py` (imported directly rather than re-typed, so a change to either drifts loudly).
"""
from __future__ import annotations

from app.models.procurement import InboundShipment
from tests._pg_fixture import blank_session
from tests.scm.test_supplier_document_service import (
    World,
    _pi_bytes,
    _pl_bytes,
    _seed_aliases,
    _seed_world,
)
from app.services.scm import supplier_document_service as svc


def test_c1_uploading_a_pi_and_its_packing_list_together_creates_zero_shipments():
    """Today: the Jiexia pair creates TWO `inbound_shipments` rows (one per container
    block) - see `test_apply_writes_two_invoices_two_shipments_and_links_the_shared_
    codes` in `test_supplier_document_service.py`. AC-C1 deletes that write entirely."""
    with blank_session() as db:
        _seed_aliases(db)
        w = _seed_world(db)

        before = db.query(InboundShipment).count()

        out = svc.apply(
            db,
            [
                ("发票 SORENTO-2026.7.26.xls", _pi_bytes(), None),
                ("装箱单 SORENTO-2026.7.26.xls", _pl_bytes(), None),
            ],
            supplier_id=str(w.supplier.id),
            currency="RMB",
        )
        db.commit()

        after = db.query(InboundShipment).count()

        assert out["shipment_ids"] == []
        assert after == before, "supplier_document_service.apply must create zero shipments"
        # The two proforma invoices are still written - only the shipment birth is gone.
        assert len(out["proforma_invoice_ids"]) == 2


def test_c1_a_packing_list_uploaded_alone_still_creates_no_shipment():
    with blank_session() as db:
        _seed_aliases(db)
        w = World(db)
        for code in ["SRTWCX8840-S-RL", "SRTWCX8840-P-RL", "SRTWCY8840", "8840"]:
            w.product(code)

        before = db.query(InboundShipment).count()

        out = svc.apply(
            db, [("装箱单 SORENTO-2026.7.26.xls", _pl_bytes(), None)],
            supplier_id=str(w.supplier.id), currency="RMB",
        )
        db.commit()

        assert out["shipment_ids"] == []
        assert db.query(InboundShipment).count() == before


def test_c5_the_upload_writes_one_pi_packing_set_instead_of_a_shipment():
    """AC-C5: "uploading a packing list through /supplier-documents/apply creates zero
    shipments and one PI packing set." The packing set is S2's `scm.proforma_invoice_
    packing_line` table (AC-B1) - imported here by its expected name; a different name
    is a legitimate reason for this single assertion to need updating in the same slice
    that adds the table, without touching the C1 assertions above."""
    from app.models.scm import ProformaInvoicePackingLine

    with blank_session() as db:
        _seed_aliases(db)
        w = _seed_world(db)

        out = svc.apply(
            db,
            [
                ("发票 SORENTO-2026.7.26.xls", _pi_bytes(), None),
                ("装箱单 SORENTO-2026.7.26.xls", _pl_bytes(), None),
            ],
            supplier_id=str(w.supplier.id),
            currency="RMB",
        )
        db.commit()

        assert out["shipment_ids"] == []
        rows = (
            db.query(ProformaInvoicePackingLine)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id.in_(out["proforma_invoice_ids"]))
            .all()
        )
        assert len(rows) > 0, "the packing rows must land on the PI, not nowhere"
