"""Regression guards for the security review of ingest-parity-standardisation
S3 (shipping orders) and its D17 warehouse-adoption rule, 2026-09-06.

Each test pins ONE defect the review found, named `test_sec_<n>_...` to match
the review report:

  sec 1  (blocker 1) `ShippingOrderIngestService._adopt_lines` never ran
         `received_guard` at all - a legacy xlsx-era row with a real receipt
         could be adopted by an incoming line whose `qty_received` regresses
         below it, erasing the receipt (`receipt_status` back to `pending`,
         supply re-enters `scm.on_order_v`).
  sec 2  (blocker 2) the GRN forward-match sweep ran INSIDE
         `ShippingOrderIngestService.ingest()`, before the route's own
         `db.commit()` - `forward_match_grn_lines_for_spo` commits on success
         and rolls back on failure, so one exception mid-batch discarded
         every not-yet-committed record while the route still answered 200.
  sec 3  (should-fix 3) `relink_allocations_for_container` had no company
         filter - a container shared by two companies could relink company
         B's allocations to company A's shipment.
  sec 4  (should-fix 4) `WarehouseService.create_warehouse` silently ADOPTED
         a case/whitespace variant, overwriting every `WarehouseBase` default
         on the existing row while still answering 201.

Substrate: `tests._pg_fixture.blank_session()`, same as the S3 file - a real
Postgres schema built from the live models, freshly created and rolled back
per test.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.procurement import InboundShipment, SPOAllocation
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.schemas.inventory import WarehouseCreate
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.master_ingest_service import IngestOutcome
from app.services.shipping_order_ingest_service import ShippingOrderIngestService

from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTSEC"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _code(stem: str) -> str:
    return unique_code(f"{MARKER}{stem}")[:30]


def _seed_product(db) -> tuple[str, str]:
    """A product plus its ESB integration reference. Returns (product_id, ref)."""
    from app.services.integration_reference_service import IntegrationReferenceService

    category = ProductCategory(category_code=_code("CAT"), category_name="Cat")
    uom = UnitOfMeasure(uom_code=_code("UOM"), uom_name="Each")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        product_code=_code("PRD"), product_name="Item",
        category_id=category.id, base_uom_id=uom.id, list_price=0,
    )
    db.add(product)
    db.flush()
    ref = f"DK-{product.product_code}"
    IntegrationReferenceService(db).link(
        entity_type="products", entity_id=product.id, source_ref=ref
    )
    return str(product.id), ref


def _shipping_order_svc(db, company_id=DEFAULT_COMPANY_ID) -> ShippingOrderIngestService:
    return ShippingOrderIngestService(db, integration_id=None, company_id=company_id)


class TestSec1AdoptionPathReceivedGuard:
    """Blocker 1: adoption (`_adopt_lines` -> `_claim`) now runs the same
    `received_guard` the by-ref update path already ran, AND `_write_row`
    clamps `quantity_received` to `max(stored, incoming)` on every path as a
    second, independent line of defence."""

    def test_sec_1_adoption_path_never_erases_a_received_quantity(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        _product_id, product_ref = _seed_product(db)
        spo_number = _code("SPO")

        # A ref-less, xlsx-era pool row: allocated 10, already received 5 -
        # via a GRN this test does not need to run to prove the point.
        row = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID,
            spo_number=spo_number,
            spo_line_number=1,
            product_id=_product_id,
            allocated_quantity=10,
            quantity_received=5,
            receipt_status="pending",
            line_status="open",
        )
        db.add(row)
        db.flush()

        svc = _shipping_order_svc(db)
        # The ESB's first-ever push naming this SPO number: a ref-less line
        # (no existing row carries this source_ref yet, so it goes through
        # adoption, not the by-ref path) that would erase the receipt if
        # nothing guarded it - allocated STAYS at 10 (never shrinks), only
        # `qty_received` regresses to 0.
        result = svc.ingest(
            "shipping_orders",
            [
                {
                    "source_ref": f"DK-{spo_number}",
                    "spo_number": spo_number,
                    "status": "open",
                    "lines": [
                        {
                            "source_ref": f"DK-{spo_number}-L1",
                            "product_ref": product_ref,
                            "qty_ordered": "10",
                            "qty_received": "0",
                        }
                    ],
                }
            ],
        )
        record = result.records[0]
        assert record.outcome is IngestOutcome.UPDATED, record.errors
        assert "received_locked" in record.warnings, record.warnings

        db.flush()
        stored = db.execute(
            text(
                "SELECT allocated_quantity, quantity_received FROM spo_allocations "
                "WHERE id = :id"
            ),
            {"id": row.id},
        ).first()
        assert stored == (10, 5), (
            "a received-locked adoption candidate must be left unchanged, not "
            "adopted with the incoming qty_received"
        )


class TestSec2ForwardMatchIsPostCommit:
    """Blocker 2: the forward-match sweep is a post-commit route hook now, and
    a failure inside it must never discard the batch's already-committed
    rows or change the verdict already returned to the caller."""

    def test_sec_2_a_raising_forward_match_leaves_the_batch_committed_and_the_verdict_unchanged(
        self, db, monkeypatch
    ):
        import app.services.grn_spo_matching as grn_spo_matching
        from app.api.v1.external.ingest import _run_document_hooks

        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        _product_id, product_ref = _seed_product(db)
        spo_number = _code("SPO")
        svc = _shipping_order_svc(db)

        result = svc.ingest(
            "shipping_orders",
            [
                {
                    "source_ref": f"DK-{spo_number}",
                    "spo_number": spo_number,
                    "status": "open",
                    "lines": [
                        {
                            "source_ref": f"DK-{spo_number}-L1",
                            "product_ref": product_ref,
                            "qty_ordered": "5",
                        }
                    ],
                }
            ],
        )
        assert result.records[0].outcome is IngestOutcome.CREATED, result.records[0].errors
        verdict_before = result.as_dict()

        # The route's own commit - everything up to here has landed exactly
        # as it would through the real endpoint.
        db.commit()

        def _boom(*a, **kw):
            raise RuntimeError("boom: simulated forward-match failure")

        monkeypatch.setattr(
            grn_spo_matching, "forward_match_grn_lines_for_spo_best_effort", _boom
        )

        # Must not raise - the hook's own try/except is the point of this test.
        _run_document_hooks(db, "shipping_orders", svc, actor=None)

        # The verdict already returned to the ESB is untouched by a hook that
        # runs strictly after it was computed.
        assert result.as_dict() == verdict_before

        # And the batch's own commit stands - a NEW read (this session, past
        # the hook's own rollback of ITS OWN failed attempt) still finds the
        # row the batch wrote.
        row = db.execute(
            text("SELECT allocated_quantity FROM spo_allocations WHERE spo_number = :n"),
            {"n": spo_number},
        ).first()
        assert row == (5,), (
            "the batch's own commit must survive a forward-match failure that "
            "runs strictly after it"
        )


class TestSec3RelinkIsCompanyScoped:
    """Should-fix 3: a container number is not globally unique - relinking
    from one company's shipment must never touch another company's
    allocations, even under the `X-API-Key` principal's all-companies scope."""

    def test_sec_3_relink_from_company_a_never_touches_company_bs_allocation(self, db):
        from app.models.company import Company
        from app.services.rules import shipping_order_rules

        company_a = Company(id=str(uuid.uuid4()), name=f"{MARKER} A", code=_code("COA"))
        company_b = Company(id=str(uuid.uuid4()), name=f"{MARKER} B", code=_code("COB"))
        db.add_all([company_a, company_b])
        db.flush()

        # One product both companies' allocations can point at - the FK is
        # required (NOT NULL) and which company happens to own the catalogue
        # row is irrelevant to what this test is proving.
        set_company_scope(db, frozenset({company_a.id}))
        product_id, _ref = _seed_product(db)

        container = "TRHU4104785"
        # A's own shipment names the shared container.
        shipment_a = InboundShipment(
            id=str(uuid.uuid4()), company_id=company_a.id,
            shipment_date=date.today(), shipping_container_number=container,
        )
        db.add(shipment_a)
        db.flush()

        set_company_scope(db, frozenset({company_a.id, company_b.id}))
        alloc_a = SPOAllocation(
            id=str(uuid.uuid4()), company_id=company_a.id,
            spo_number=_code("SPOA"), spo_line_number=1,
            product_id=product_id, allocated_quantity=5, quantity_received=0,
            receipt_status="pending", line_status="open",
            container_number=container,
        )
        alloc_b = SPOAllocation(
            id=str(uuid.uuid4()), company_id=company_b.id,
            spo_number=_code("SPOB"), spo_line_number=1,
            product_id=product_id, allocated_quantity=7, quantity_received=0,
            receipt_status="pending", line_status="open",
            container_number=container,
        )
        db.add_all([alloc_a, alloc_b])
        db.flush()

        relinked = shipping_order_rules.relink_allocations_for_container(
            db, container, company_id=company_a.id
        )
        db.flush()

        assert relinked == 1, "must relink exactly company A's own allocation"
        rows = db.execute(
            text(
                "SELECT company_id, inbound_shipment_id FROM spo_allocations "
                "WHERE id IN (:a, :b)"
            ),
            {"a": alloc_a.id, "b": alloc_b.id},
        ).mappings().all()
        by_company = {str(r["company_id"]): r["inbound_shipment_id"] for r in rows}
        assert str(by_company[str(company_a.id)]) == str(shipment_a.id)
        assert by_company[str(company_b.id)] is None, (
            "company B's allocation must never be linked to company A's shipment"
        )


class TestSec4WarehouseManualCreateRefusesAdoption:
    """Should-fix 4: a case/whitespace variant on the MANUAL create path is a
    409 conflict now, not a silent adoption that overwrote every
    `WarehouseBase` default on the existing row while still answering 201."""

    def test_sec_4_manual_create_of_a_case_variant_is_refused_not_adopted(self, db):
        from app.models.inventory import Warehouse
        from app.services.error_handler import AppException
        from app.services.inventory_service import WarehouseService

        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = _code("BRW")
        db.add(
            Warehouse(
                warehouse_code=code, warehouse_name="Main",
                is_active=False, counts_as_available=False,
            )
        )
        db.flush()

        with pytest.raises(AppException) as exc_info:
            WarehouseService(db).create_warehouse(
                WarehouseCreate(warehouse_code=f" {code.lower()} ", warehouse_name="Duplicate")
            )
        assert exc_info.value.status_code == 409

        row = db.execute(
            text(
                "SELECT is_active, counts_as_available FROM warehouses "
                "WHERE warehouse_code = :c"
            ),
            {"c": code},
        ).first()
        assert row == (False, False), (
            "a refused create must never have touched the existing row's own defaults"
        )
