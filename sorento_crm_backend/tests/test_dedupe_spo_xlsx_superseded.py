"""RED tests for AC-X10, AC-X20, AC-X21, AC-X26 and AC-X27:
`scripts/dedupe_spo_xlsx_superseded.py`.

UAC: documentation/plans/autocount/spo-xlsx-supersede-acceptance-criteria.md
     AC-X10, AC-X20, AC-X21, AC-X26, AC-X27.
PLAN: documentation/plans/autocount/PLAN-spo-xlsx-supersede.md D29 (+ amended),
      D27a.

Contract: `run(db, company_id, since=None, dry_run=True) -> summary dict` -
shares the same `_supersede_xlsx_rows` algorithm the ingest service uses for
D25/D26/D27, applied to a company's already-appended ref rows (the existing
`spo_line_number` order standing in for "incoming" line order) against its
remaining ref-less xlsx-era rows.

Round 2 (2026-09-07) amends D29 - the dedupe's "incoming" side must be the
NEWEST `source_doc_ref`'s ref rows only, never a retired DocKey's - and adds
D27a (shipment line-status refresh, same as every other allocation writer).

The module does not exist yet, so every import of it is done INSIDE the test
body, not at module scope - collection of the rest of the suite must not fail
just because this one script is still unbuilt.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.procurement import InboundShipment, PickingHeader, PickingLine, SPOAllocation
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
)
from app.models.scm import OrderLinkClaim
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTDEDUPE"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _seed_product(db) -> Product:
    category = ProductCategory(category_code=unique_code(MARKER), category_name="Cat")
    uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name="Each")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        product_code=unique_code(MARKER),
        product_name="Item",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("0"),
    )
    db.add(product)
    db.flush()
    return product


def _seed_warehouse(db) -> Warehouse:
    warehouse = Warehouse(
        warehouse_code=f"{MARKER}WH{uuid.uuid4().hex[:6]}", warehouse_name="Main"
    )
    db.add(warehouse)
    db.flush()
    return warehouse


class TestAcX10DedupeScript:
    def test_dry_run_writes_nothing_then_apply_supersedes_and_a_second_apply_is_a_no_op(
        self, db
    ):
        """AC-X10. A company holds SPO N with the AC-X1 xlsx row AND two ref
        rows already appended (line 17 qty 29, line 18 qty 18, both received
        0, open, `created_at` later than the xlsx row). `--dry-run` (here:
        `run(..., dry_run=True)`) prints/reports the plan and writes
        nothing; a non-dry run leaves two rows received 29 / 18 closed with
        the xlsx row's links moved to line 17 and the xlsx row deleted; a
        second non-dry run reports zero documents touched.

        RED today at the import line: `scripts/dedupe_spo_xlsx_superseded`
        does not exist.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        warehouse = _seed_warehouse(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"

        xlsx_row = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID,
            spo_number=spo_number,
            spo_line_number=1,
            product_id=product.id,
            location_code=warehouse.warehouse_code,
            allocated_quantity=47,
            quantity_received=47,
            line_status="closed",
            receipt_status="fully_received",
            source_system="scm_upload",
        )
        db.add(xlsx_row)
        db.flush()

        # AC-X10 amendment (2026-09-07): a dependant on the xlsx row itself,
        # so the repoint half of the algorithm is actually exercised here -
        # the original seed had none.
        header = PickingHeader(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID,
            picking_number=unique_code(MARKER), picking_type="goods_received",
            picking_status="approved",
        )
        db.add(header)
        db.flush()
        picking_line = PickingLine(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID,
            picking_header_id=header.id, spo_allocation_id=xlsx_row.id,
            product_id=product.id, quantity_expected=47, quantity_picked=47,
        )
        db.add(picking_line)
        db.flush()

        doc_ref = f"{MARKER}:SPO:{uuid.uuid4().hex[:8]}"
        ref_17 = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID,
            spo_number=spo_number,
            spo_line_number=17,
            product_id=product.id,
            warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code,
            allocated_quantity=29,
            quantity_received=0,
            line_status="open",
            receipt_status="pending",
            source_system="autocount",
            source_ref=f"{MARKER}:SPOL17:{uuid.uuid4().hex[:8]}",
            source_doc_ref=doc_ref,
        )
        ref_18 = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID,
            spo_number=spo_number,
            spo_line_number=18,
            product_id=product.id,
            warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code,
            allocated_quantity=18,
            quantity_received=0,
            line_status="open",
            receipt_status="pending",
            source_system="autocount",
            source_ref=f"{MARKER}:SPOL18:{uuid.uuid4().hex[:8]}",
            source_doc_ref=doc_ref,
        )
        db.add_all([ref_17, ref_18])
        db.flush()
        db.commit()

        from scripts.dedupe_spo_xlsx_superseded import run  # noqa: PLC0415 - module not built yet

        summary = run(db, DEFAULT_COMPANY_ID, dry_run=True)

        db.expire_all()
        rows_after_dry = (
            db.execute(
                text(
                    "SELECT id FROM spo_allocations WHERE spo_number = :n ORDER BY spo_line_number"
                ),
                {"n": spo_number},
            )
            .mappings()
            .all()
        )
        assert len(rows_after_dry) == 3, "a dry run must write nothing"
        assert str(xlsx_row.id) in {str(r["id"]) for r in rows_after_dry}
        assert summary.get("documents", 0) >= 1, summary

        summary2 = run(db, DEFAULT_COMPANY_ID, dry_run=False)

        db.expire_all()
        rows_after_apply = (
            db.execute(
                text(
                    "SELECT id, allocated_quantity, quantity_received, line_status "
                    "FROM spo_allocations WHERE spo_number = :n ORDER BY allocated_quantity"
                ),
                {"n": spo_number},
            )
            .mappings()
            .all()
        )
        assert len(rows_after_apply) == 2, rows_after_apply
        assert str(xlsx_row.id) not in {str(r["id"]) for r in rows_after_apply}
        by_qty = {r["allocated_quantity"]: r for r in rows_after_apply}
        assert by_qty[29]["quantity_received"] == 29
        assert by_qty[29]["line_status"] == "closed"
        assert by_qty[18]["quantity_received"] == 18
        assert by_qty[18]["line_status"] == "closed"

        # AC-X10 amendment: the picking line that pointed at the xlsx row
        # must now point at the first ref row (line 17, allocated 29) - the
        # repoint half of D27, untested by the original seed.
        picking_line_alloc = db.execute(
            text("SELECT spo_allocation_id FROM picking_lines WHERE id = :id"),
            {"id": picking_line.id},
        ).scalar()
        assert picking_line_alloc is not None and str(picking_line_alloc) == str(
            by_qty[29]["id"]
        ), picking_line_alloc

        summary3 = run(db, DEFAULT_COMPANY_ID, dry_run=False)
        assert summary3.get("documents") == 0, summary3


class TestAcX20DedupeRepointsOnlyTheNewestDocKey:
    def test_the_dedupe_repoints_and_carries_onto_the_newest_dockeys_first_row_only(self, db):
        """AC-X20 (D29 amended). SPO N holds an OLD DocKey's closed ref
        rows (retired) sharing the SAME (product, location) as the xlsx
        row, and a NEWER DocKey's ref rows (17, 18) for that same group,
        plus the xlsx row. The dedupe must repoint and carry onto the
        NEWER DocKey's first row only; the retired old-DocKey row is left
        exactly as it was.

        RED today: `_apply_document` treats EVERY ref row of the
        `spo_number` as the "incoming" side, regardless of
        `source_doc_ref` - the old, retired row (allocated 10, received 3)
        is folded into the SAME group as the newer DocKey's rows and its
        own `quantity_received` gets overwritten by the redistributed
        carry, not left untouched at 3.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        warehouse = _seed_warehouse(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"

        xlsx_row = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=1, product_id=product.id, location_code=warehouse.warehouse_code,
            allocated_quantity=10, quantity_received=10, line_status="closed",
            receipt_status="fully_received", source_system="scm_upload",
            created_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        db.add(xlsx_row)
        db.flush()

        old_row = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=5, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=10,
            quantity_received=3, line_status="closed", receipt_status="pending",
            source_system="autocount", source_ref=f"{MARKER}:OLDREF:{uuid.uuid4().hex[:8]}",
            source_doc_ref=f"{MARKER}:OLDDOC:{uuid.uuid4().hex[:8]}",
            created_at=datetime(2026, 2, 1, 0, 0, 0),
        )
        db.add(old_row)
        db.flush()

        new_doc_ref = f"{MARKER}:NEWDOC:{uuid.uuid4().hex[:8]}"
        new_17 = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=17, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=6,
            quantity_received=0, line_status="open", receipt_status="pending",
            source_system="autocount", source_ref=f"{MARKER}:NEWREF17:{uuid.uuid4().hex[:8]}",
            source_doc_ref=new_doc_ref, created_at=datetime(2026, 9, 7, 6, 0, 0),
        )
        new_18 = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=18, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=4,
            quantity_received=0, line_status="open", receipt_status="pending",
            source_system="autocount", source_ref=f"{MARKER}:NEWREF18:{uuid.uuid4().hex[:8]}",
            source_doc_ref=new_doc_ref, created_at=datetime(2026, 9, 7, 6, 0, 0),
        )
        db.add_all([new_17, new_18])
        db.flush()
        db.commit()

        from scripts.dedupe_spo_xlsx_superseded import run

        run(db, DEFAULT_COMPANY_ID, dry_run=False)

        db.expire_all()
        old_after = (
            db.execute(
                text(
                    "SELECT quantity_received, line_status FROM spo_allocations WHERE id = :id"
                ),
                {"id": old_row.id},
            )
            .mappings()
            .first()
        )
        assert old_after["quantity_received"] == 3, (
            "the retired old-DocKey row must be left exactly as it was", old_after
        )
        assert old_after["line_status"] == "closed"

        new_after = (
            db.execute(
                text(
                    "SELECT id, allocated_quantity, quantity_received, line_status "
                    "FROM spo_allocations WHERE spo_number = :n AND source_doc_ref = :d "
                    "ORDER BY allocated_quantity"
                ),
                {"n": spo_number, "d": new_doc_ref},
            )
            .mappings()
            .all()
        )
        assert len(new_after) == 2, new_after
        by_qty = {r["allocated_quantity"]: r for r in new_after}
        assert by_qty[6]["quantity_received"] == 6
        assert by_qty[6]["line_status"] == "closed"
        assert by_qty[4]["quantity_received"] == 4
        assert by_qty[4]["line_status"] == "closed"

        xlsx_after = db.execute(
            text("SELECT id FROM spo_allocations WHERE id = :id"), {"id": xlsx_row.id}
        ).first()
        assert xlsx_after is None, "the xlsx row must be superseded (deleted)"

    def test_since_accepts_a_naive_timestamp_and_rejects_a_tz_aware_one_before_any_write(
        self, db
    ):
        """AC-X20 (--since, D29 amended). `--since '2026-09-07 05:15'`
        (naive) is accepted the same way `main()` parses it
        (`datetime.fromisoformat(args.since)`); `--since
        '2026-09-07T05:15:00Z'` must be REJECTED with a clear message
        before any write - not merely raise deep inside the sweep.

        RED today: `main()`'s own parsing line has NO validation at all -
        Python 3.11+ `datetime.fromisoformat` happily parses the trailing
        'Z' into a TIMEZONE-AWARE datetime, which then reaches
        `_apply_document`'s `row.created_at >= since` comparison against a
        NAIVE `DateTime(timezone=False)` column and raises an unhandled
        `TypeError: can't compare offset-naive and offset-aware datetimes`
        - a crash, not "rejected with a clear message before any write".
        Exercised through `run()` (the same entry point AC-X10's own test
        uses) with the string parsed exactly the way `main()` parses it,
        rather than driving `main()`'s own argparse/SessionLocal plumbing.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        warehouse = _seed_warehouse(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        xlsx_row = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=1, product_id=product.id, location_code=warehouse.warehouse_code,
            allocated_quantity=10, quantity_received=10, line_status="closed",
            receipt_status="fully_received", source_system="scm_upload",
        )
        db.add(xlsx_row)
        db.flush()
        ref_row = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=17, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=10,
            quantity_received=0, line_status="open", receipt_status="pending",
            source_system="autocount", source_ref=f"{MARKER}:REF17:{uuid.uuid4().hex[:8]}",
            source_doc_ref=f"{MARKER}:DOC:{uuid.uuid4().hex[:8]}",
            created_at=datetime(2026, 9, 7, 6, 0, 0),
        )
        db.add(ref_row)
        db.flush()
        db.commit()

        from scripts import dedupe_spo_xlsx_superseded as dedupe_module

        naive_since = dedupe_module.datetime.fromisoformat("2026-09-07 05:15")
        summary_naive = dedupe_module.run(
            db, DEFAULT_COMPANY_ID, since=naive_since, dry_run=True
        )
        assert summary_naive.get("documents", 0) >= 1, (
            "a naive --since must be accepted and find the in-scope document",
            summary_naive,
        )

        before = db.execute(
            text("SELECT quantity_received FROM spo_allocations WHERE id = :id"),
            {"id": ref_row.id},
        ).scalar()

        parsed_aware = dedupe_module.datetime.fromisoformat("2026-09-07T05:15:00Z")
        rejected_cleanly = False
        try:
            dedupe_module.run(db, DEFAULT_COMPANY_ID, since=parsed_aware, dry_run=False)
        except ValueError as exc:
            rejected_cleanly = True
            assert "naive" in str(exc).lower() or "timezone" in str(exc).lower(), exc
        except TypeError:
            # Today's actual (wrong) behaviour: an unhandled crash deep in
            # the comparison, not a clean, documented rejection.
            pass

        assert rejected_cleanly, (
            "a tz-aware --since must be rejected with a CLEAR message (a "
            "ValueError naming the reason), not left to crash with a raw "
            "TypeError from a naive/aware datetime comparison"
        )

        db.expire_all()
        after = db.execute(
            text("SELECT quantity_received FROM spo_allocations WHERE id = :id"),
            {"id": ref_row.id},
        ).scalar()
        assert after == before, "no row may change before the since value is validated"


class TestAcX21DedupeRepointsTheFullDependantSetAndStaysCompanyScoped:
    def test_apply_repoints_all_three_dependants_and_leaves_company_b_untouched(self, db):
        """AC-X21 (S10). The xlsx row carries a picking line, an
        `order_link_claim` and an `order_inquiry_link`; after `--apply` all
        three must point at the first ref row (line 17, allocated 29). A
        company-B xlsx row sharing the SAME `spo_number` must be untouched.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        warehouse = _seed_warehouse(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"

        xlsx_row = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=1, product_id=product.id, location_code=warehouse.warehouse_code,
            allocated_quantity=47, quantity_received=47, line_status="closed",
            receipt_status="fully_received", source_system="scm_upload",
        )
        db.add(xlsx_row)
        db.flush()

        header = PickingHeader(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID,
            picking_number=unique_code(MARKER), picking_type="goods_received",
            picking_status="approved",
        )
        db.add(header)
        db.flush()
        picking_line = PickingLine(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID,
            picking_header_id=header.id, spo_allocation_id=xlsx_row.id,
            product_id=product.id, quantity_expected=47, quantity_picked=47,
        )
        db.add(picking_line)
        db.flush()

        claim = OrderLinkClaim(
            company_id=DEFAULT_COMPANY_ID, so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
            po_number=spo_number, source="autocount", spo_allocation_id=xlsx_row.id,
        )
        db.add(claim)
        db.flush()

        pso = ProjectSalesOrder(
            id=str(uuid.uuid4()), provisional_ref=f"{MARKER}-PSO-{uuid.uuid4().hex[:8]}",
            company_id=DEFAULT_COMPANY_ID,
        )
        db.add(pso)
        db.flush()
        inquiry = OrderInquiry(
            id=str(uuid.uuid4()), project_sales_order_id=pso.id, company_id=DEFAULT_COMPANY_ID
        )
        db.add(inquiry)
        db.flush()
        oi_row = OrderInquiryRow(
            id=str(uuid.uuid4()), order_inquiry_id=inquiry.id, qty=Decimal("47"),
            verb=IV_ORDER_BACK, company_id=DEFAULT_COMPANY_ID,
        )
        db.add(oi_row)
        db.flush()
        link = OrderInquiryLink(
            id=str(uuid.uuid4()), row_id=oi_row.id, spo_allocation_id=xlsx_row.id,
            qty=Decimal("47"), company_id=DEFAULT_COMPANY_ID,
        )
        db.add(link)
        db.flush()

        doc_ref = f"{MARKER}:SPO:{uuid.uuid4().hex[:8]}"
        ref_17 = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=17, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=29,
            quantity_received=0, line_status="open", receipt_status="pending",
            source_system="autocount", source_ref=f"{MARKER}:SPOL17:{uuid.uuid4().hex[:8]}",
            source_doc_ref=doc_ref,
        )
        ref_18 = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=18, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=18,
            quantity_received=0, line_status="open", receipt_status="pending",
            source_system="autocount", source_ref=f"{MARKER}:SPOL18:{uuid.uuid4().hex[:8]}",
            source_doc_ref=doc_ref,
        )
        db.add_all([ref_17, ref_18])
        db.flush()

        # Company B: its OWN xlsx row on the SAME spo_number - must be
        # untouched by a dedupe run scoped to the anchor company.
        other = Company(
            id=str(uuid.uuid4()), name=f"{MARKER} B {uuid.uuid4().hex[:6]}",
            code=unique_code(MARKER)[:10],
        )
        db.add(other)
        db.flush()
        company_b = str(other.id)
        b_xlsx_row = SPOAllocation(
            id=str(uuid.uuid4()), company_id=company_b, spo_number=spo_number,
            spo_line_number=1, product_id=product.id, allocated_quantity=5,
            quantity_received=5, line_status="closed", receipt_status="fully_received",
            source_system="scm_upload",
        )
        db.add(b_xlsx_row)
        db.flush()
        db.commit()

        from scripts.dedupe_spo_xlsx_superseded import run

        run(db, DEFAULT_COMPANY_ID, dry_run=False)

        db.expire_all()
        rows = (
            db.execute(
                text(
                    "SELECT id, allocated_quantity FROM spo_allocations "
                    "WHERE company_id = :c AND spo_number = :n"
                ),
                {"c": DEFAULT_COMPANY_ID, "n": spo_number},
            )
            .mappings()
            .all()
        )
        target_id = str(next(r["id"] for r in rows if r["allocated_quantity"] == 29))

        picking_alloc = db.execute(
            text("SELECT spo_allocation_id FROM picking_lines WHERE id = :id"),
            {"id": picking_line.id},
        ).scalar()
        claim_alloc = db.execute(
            text("SELECT spo_allocation_id FROM order_link_claim WHERE id = :id"),
            {"id": claim.id},
        ).scalar()
        link_alloc = db.execute(
            text("SELECT spo_allocation_id FROM order_inquiry_links WHERE id = :id"),
            {"id": link.id},
        ).scalar()

        assert picking_alloc is not None and str(picking_alloc) == target_id, picking_alloc
        assert claim_alloc is not None and str(claim_alloc) == target_id, claim_alloc
        assert link_alloc is not None and str(link_alloc) == target_id, link_alloc

        b_after = (
            db.execute(
                text(
                    "SELECT quantity_received, line_status FROM spo_allocations WHERE id = :id"
                ),
                {"id": b_xlsx_row.id},
            )
            .mappings()
            .first()
        )
        assert b_after["quantity_received"] == 5
        assert b_after["line_status"] == "closed"


class TestAcX26DedupeRefreshesShipmentLineStatuses:
    def test_apply_refreshes_the_linked_shipments_line_status_once(self, db, monkeypatch):
        """AC-X26 (D27a, dedupe side). The dedupe must call
        `InboundShipmentService.refresh_shipment_line_statuses` once for the
        shipment the superseded xlsx row was linked to - same as every
        other allocation writer, and same as the ingest side of D27a.

        RED today: `scripts/dedupe_spo_xlsx_superseded.py` never calls it
        at all.
        """
        import app.services.procurement_service as procurement_service

        calls: list[str] = []
        real = procurement_service.InboundShipmentService.refresh_shipment_line_statuses

        def _spy(self, shipment_id):
            calls.append(str(shipment_id))
            return real(self, shipment_id)

        monkeypatch.setattr(
            procurement_service.InboundShipmentService, "refresh_shipment_line_statuses", _spy
        )

        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        warehouse = _seed_warehouse(db)
        shipment = InboundShipment(
            id=str(uuid.uuid4()), shipment_number=f"{MARKER}-SH-{uuid.uuid4().hex[:6]}",
            shipping_container_number=f"{MARKER}-CT-{uuid.uuid4().hex[:6]}",
            shipment_date=datetime(2026, 1, 1).date(), shipment_status="pending",
        )
        db.add(shipment)
        db.flush()

        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        xlsx_row = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=1, product_id=product.id, location_code=warehouse.warehouse_code,
            allocated_quantity=47, quantity_received=47, line_status="closed",
            receipt_status="fully_received", source_system="scm_upload",
            inbound_shipment_id=shipment.id,
        )
        db.add(xlsx_row)
        db.flush()

        doc_ref = f"{MARKER}:SPO:{uuid.uuid4().hex[:8]}"
        ref_17 = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=17, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=29,
            quantity_received=0, line_status="open", receipt_status="pending",
            source_system="autocount", source_ref=f"{MARKER}:SPOL17:{uuid.uuid4().hex[:8]}",
            source_doc_ref=doc_ref,
        )
        ref_18 = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=18, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=18,
            quantity_received=0, line_status="open", receipt_status="pending",
            source_system="autocount", source_ref=f"{MARKER}:SPOL18:{uuid.uuid4().hex[:8]}",
            source_doc_ref=doc_ref,
        )
        db.add_all([ref_17, ref_18])
        db.flush()
        db.commit()

        from scripts.dedupe_spo_xlsx_superseded import run

        run(db, DEFAULT_COMPANY_ID, dry_run=False)

        assert str(shipment.id) in calls, (
            "the dedupe must refresh the linked shipment's line statuses, "
            f"same as every other allocation writer - calls: {calls}"
        )


class TestAcX27DedupeReportsGroupsAndDryRunRollsBack:
    def test_kept_ref_less_rows_from_one_group_count_as_one_group_not_two_rows(self, db):
        """AC-X27 (part 1). Two ref-less rows sharing ONE (product,
        location) key that the ref rows never name - a single KEPT group -
        must be reported as `groups_kept == 1`, not `2` (one per row).

        RED today: `plan_xlsx_supersede.kept_row_ids` is a flat list of ROW
        ids, and the script's own `counts["groups_kept"] = len(plan.
        kept_row_ids)` counts its LENGTH - i.e. rows, not groups.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product_p = _seed_product(db)
        product_q = _seed_product(db)
        warehouse = _seed_warehouse(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"

        # P's group: TWO ref-less rows sharing one (product, location) key,
        # named by NO ref line - one KEPT group, two rows.
        kept_1 = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=1, product_id=product_p.id, location_code=warehouse.warehouse_code,
            allocated_quantity=5, quantity_received=5, line_status="closed",
            receipt_status="fully_received", source_system="scm_upload",
        )
        kept_2 = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=2, product_id=product_p.id, location_code=warehouse.warehouse_code,
            allocated_quantity=3, quantity_received=3, line_status="closed",
            receipt_status="fully_received", source_system="scm_upload",
        )
        db.add_all([kept_1, kept_2])
        db.flush()

        # Q's group: a supersede target, so the document has SOMETHING to
        # apply (a document with every group kept returns None / is
        # skipped entirely - not what this test is pinning).
        q_xlsx = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=3, product_id=product_q.id, location_code=f"{warehouse.warehouse_code}-Q",
            allocated_quantity=10, quantity_received=10, line_status="closed",
            receipt_status="fully_received", source_system="scm_upload",
        )
        db.add(q_xlsx)
        db.flush()
        ref_q = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=17, product_id=product_q.id,
            location_code=f"{warehouse.warehouse_code}-Q", allocated_quantity=10,
            quantity_received=0, line_status="open", receipt_status="pending",
            source_system="autocount", source_ref=f"{MARKER}:QREF:{uuid.uuid4().hex[:8]}",
            source_doc_ref=f"{MARKER}:QDOC:{uuid.uuid4().hex[:8]}",
        )
        db.add(ref_q)
        db.flush()
        db.commit()

        from scripts.dedupe_spo_xlsx_superseded import run

        summary = run(db, DEFAULT_COMPANY_ID, dry_run=True)

        assert summary.get("groups_kept") == 1, (
            "P's group is ONE kept group (two rows sharing one key), not two",
            summary,
        )

    def test_a_dry_run_ends_with_the_session_rolled_back(self, db, monkeypatch):
        """AC-X27 (part 2). A dry run must end with `db.rollback()` called,
        so no transaction/read state survives the sweep.

        RED today: `run()`'s dry-run path never calls `db.rollback()` at
        all - only `_apply_document`'s own `if not dry_run: db.commit()`
        exists, with nothing on the other branch.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        warehouse = _seed_warehouse(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        xlsx_row = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=1, product_id=product.id, location_code=warehouse.warehouse_code,
            allocated_quantity=10, quantity_received=10, line_status="closed",
            receipt_status="fully_received", source_system="scm_upload",
        )
        db.add(xlsx_row)
        db.flush()
        ref_row = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=17, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=10,
            quantity_received=0, line_status="open", receipt_status="pending",
            source_system="autocount", source_ref=f"{MARKER}:REF17:{uuid.uuid4().hex[:8]}",
            source_doc_ref=f"{MARKER}:DOC:{uuid.uuid4().hex[:8]}",
        )
        db.add(ref_row)
        db.flush()
        db.commit()

        calls: list[bool] = []
        real_rollback = db.rollback

        def _spy_rollback():
            calls.append(True)
            return real_rollback()

        monkeypatch.setattr(db, "rollback", _spy_rollback)

        from scripts.dedupe_spo_xlsx_superseded import run

        run(db, DEFAULT_COMPANY_ID, dry_run=True)

        assert calls, "a dry run must call db.rollback() before returning"


class TestAcX51DedupeAppliesTheSpo0028Shape:
    def test_a_null_source_warehouse_only_row_beside_autocount_refs_is_deduplicated(self, db):
        """AC-X51 (D25c, D29). The SPO-2026/09-0028 shape: a NULL-source
        CLOSED ref-less row with `warehouse_id` set and NO `location_code`
        (the Procurement Upload SPO / n8n packing-list writers), beside
        `autocount` ref rows whose `location_code` equals that warehouse's
        own code (and which also carry `warehouse_id`, matching production:
        "every AutoCount row has one"). `--apply` (`run(..., dry_run=False)`)
        must remove the ref-less row, carry its receipt onto the ref rows,
        move its dependants; a second run reports 0 documents.

        RED today: `is_xlsx_era_row` still excludes `source_system IS
        NULL` - this row is never gathered as a supersede candidate at
        all, so the document is skipped exactly as SPO-2026/09-0028 was in
        production, and `rows_after_apply` still holds 3 rows (the
        NULL-source row untouched) instead of 2.
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        warehouse = _seed_warehouse(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"

        null_source_row = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=1, product_id=product.id, location_code=None,
            warehouse_id=warehouse.id, allocated_quantity=47, quantity_received=47,
            line_status="closed", receipt_status="fully_received", source_system=None,
        )
        db.add(null_source_row)
        db.flush()

        doc_ref = f"{MARKER}:SPO0028:{uuid.uuid4().hex[:8]}"
        ref_17 = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=17, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=29,
            quantity_received=0, line_status="open", receipt_status="pending",
            source_system="autocount", source_ref=f"{MARKER}:SPOL17:{uuid.uuid4().hex[:8]}",
            source_doc_ref=doc_ref,
        )
        ref_18 = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=18, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=18,
            quantity_received=0, line_status="open", receipt_status="pending",
            source_system="autocount", source_ref=f"{MARKER}:SPOL18:{uuid.uuid4().hex[:8]}",
            source_doc_ref=doc_ref,
        )
        db.add_all([ref_17, ref_18])
        db.flush()
        db.commit()

        from scripts.dedupe_spo_xlsx_superseded import run

        run(db, DEFAULT_COMPANY_ID, dry_run=True)

        db.expire_all()
        rows_after_dry = (
            db.execute(
                text(
                    "SELECT id FROM spo_allocations WHERE spo_number = :n ORDER BY spo_line_number"
                ),
                {"n": spo_number},
            )
            .mappings()
            .all()
        )
        assert len(rows_after_dry) == 3, "a dry run must write nothing"
        assert str(null_source_row.id) in {str(r["id"]) for r in rows_after_dry}

        run(db, DEFAULT_COMPANY_ID, dry_run=False)

        db.expire_all()
        rows_after_apply = (
            db.execute(
                text(
                    "SELECT id, allocated_quantity, quantity_received, line_status "
                    "FROM spo_allocations WHERE spo_number = :n ORDER BY allocated_quantity"
                ),
                {"n": spo_number},
            )
            .mappings()
            .all()
        )
        assert len(rows_after_apply) == 2, (
            "the NULL-source row (SPO-0028 shape) must be removed by --apply", rows_after_apply
        )
        assert str(null_source_row.id) not in {str(r["id"]) for r in rows_after_apply}
        by_qty = {r["allocated_quantity"]: r for r in rows_after_apply}
        assert by_qty[29]["quantity_received"] == 29, by_qty
        assert by_qty[29]["line_status"] == "closed", by_qty
        assert by_qty[18]["quantity_received"] == 18, by_qty
        assert by_qty[18]["line_status"] == "closed", by_qty

        summary_second_run = run(db, DEFAULT_COMPANY_ID, dry_run=False)
        assert summary_second_run.get("documents") == 0, (
            "a second run over the same company must be idempotent - a "
            f"no-op reporting zero documents - got {summary_second_run}"
        )


class TestAcX54aIdempotentCarryNeverDoublesRejectedOrNotes:
    def test_running_the_dedupe_twice_never_doubles_quantity_rejected_or_duplicates_notes(
        self, db
    ):
        """AC-X54a (idempotent carry, D26 packing-list columns). A document
        whose Excel row already carries `quantity_rejected 2` and
        `allocation_notes 'damaged carton'`, beside `autocount` ref rows
        whose FIRST line ALREADY carries `quantity_rejected 2` and notes
        containing `'damaged carton'` (the SAME carry, as if already
        applied once). Running `run(..., dry_run=False)` TWICE must leave
        the first line at `quantity_rejected 2` (never 4) and `'damaged
        carton'` appearing exactly ONCE in its notes; the second run is a
        no-op (the Excel row is gone after the first).

        RED today: the writer does `row.quantity_rejected = int(row.
        quantity_rejected or 0) + group.rejected_total` - a PLAIN
        addition, never a max rule - so the very first run already
        doubles an already-carried rejected total to 4 (2 already on the
        ref row's own line, plus 2 more from the still-present Excel
        row's own total).
        """
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        product = _seed_product(db)
        warehouse = _seed_warehouse(db)
        spo_number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        doc_ref = f"{MARKER}:DOC:{uuid.uuid4().hex[:8]}"

        xlsx_row = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=1, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=47,
            quantity_received=47, quantity_rejected=2, line_status="closed",
            receipt_status="fully_received", source_system="scm_upload",
            allocation_notes="damaged carton",
        )
        db.add(xlsx_row)
        db.flush()

        ref_17 = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=17, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=29,
            quantity_received=29, quantity_rejected=2, line_status="closed",
            receipt_status="fully_received", source_system="autocount",
            source_ref=f"{MARKER}:REF17:{uuid.uuid4().hex[:8]}", source_doc_ref=doc_ref,
            allocation_notes="damaged carton",
        )
        ref_18 = SPOAllocation(
            id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, spo_number=spo_number,
            spo_line_number=18, product_id=product.id, warehouse_id=warehouse.id,
            location_code=warehouse.warehouse_code, allocated_quantity=18,
            quantity_received=18, quantity_rejected=0, line_status="closed",
            receipt_status="fully_received", source_system="autocount",
            source_ref=f"{MARKER}:REF18:{uuid.uuid4().hex[:8]}", source_doc_ref=doc_ref,
        )
        db.add_all([ref_17, ref_18])
        db.flush()
        db.commit()

        from scripts.dedupe_spo_xlsx_superseded import run

        run(db, DEFAULT_COMPANY_ID, dry_run=False)

        db.expire_all()
        first_line = db.execute(
            text(
                "SELECT quantity_rejected, allocation_notes FROM spo_allocations "
                "WHERE id = :id"
            ),
            {"id": ref_17.id},
        ).mappings().first()
        assert first_line["quantity_rejected"] == 2, (
            f"a group already carrying 2 must never be doubled to 4 - got {first_line}"
        )
        assert (first_line["allocation_notes"] or "").count("damaged carton") == 1, first_line

        summary_second_run = run(db, DEFAULT_COMPANY_ID, dry_run=False)

        db.expire_all()
        first_line_again = db.execute(
            text(
                "SELECT quantity_rejected, allocation_notes FROM spo_allocations "
                "WHERE id = :id"
            ),
            {"id": ref_17.id},
        ).mappings().first()
        assert first_line_again["quantity_rejected"] == 2, first_line_again
        assert (first_line_again["allocation_notes"] or "").count("damaged carton") == 1, (
            first_line_again
        )
        assert summary_second_run.get("documents") == 0, summary_second_run
