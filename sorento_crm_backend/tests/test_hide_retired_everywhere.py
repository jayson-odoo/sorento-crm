"""RED tests for AC-E1 to AC-E13 (PLAN-hide-retired-everywhere).

UAC: documentation/plans/autocount/hide-retired-everywhere-acceptance-criteria.md
PLAN: documentation/plans/autocount/PLAN-hide-retired-everywhere.md

Follows #753 / `tests/test_hide_retired_spo_lines.py`, which pinned
`spo_supply.visible_line_clauses()` and applied it to the five original readers. This
suite applies the SAME one predicate (R7: a retired line with no receipt is hidden; R2: a
retired line carrying a receipt stays visible) to eleven more display/chatbot readers plus
one arithmetic reader (AC-E7). AC-E3 (the embedding trio) lives in its own file,
`test_hide_retired_everywhere_embedding.py`, because it needs a different substrate (a
real, non-scratch-schema Postgres session so the worker's own `SessionLocal()` sees the
seeded rows). AC-E14 is a comment-only decision with no test.

Written test-first per the tester brief, from three inputs: the UAC, the PLAN's
`spo_supply.visible_line_clauses()` contract, and the captain's own priority ordering
(E1, E2, E4, E11, E3, then the rest). NOTE for whoever reads the run output: by the time
this suite ran, the coder had already landed and COMMITTED fixes for every AC here
(commits 6134bd1dc, c72faa922, c5307e7fa, ef53fd10b - the last, AC-E7's
`coverage_service._supply_events_many` fix, landed WHILE this suite was being written) -
so every test passed on first run, pinning the contract rather than reproducing a live
bug. Each assertion was traced by hand against the actual diff hunk that introduced
`spo_supply.visible_line_clauses()` (or the equivalent new logic) before or immediately
after being written, and for AC-E1/AC-E7 additionally against the PRE-FIX version of the
file (`git show <commit>^:path`, read-only) to confirm the old code would have produced
the values these assertions now forbid. See the tester's final report to the captain for
the per-AC breakdown.

AC-E9 has two readers (module docstring's own reason the second is not a call into the
first): `project_order_inquiry_service.links_for_rows` (`TestAcE9LinksForRowsHidesRetired`)
and `spo_conversion_service._project_coverage`'s own `taken_by`
(`TestAcE9ProjectCoverageHidesRetired`, built off the real `svc.create` + `World` fixture
`tests.scm.test_spo_conversion` already uses for a project ORDER BACK row, per the
captain's steer rather than a hand-built demand-row fixture).
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import OrderInquiryLink, ProjectSalesOrder
from app.services.scm.spo_conversion_service import SOURCE_SYSTEM

from tests._pg_fixture import blank_session, pg_session, unique_code
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg, scm_app  # noqa: F401
from tests.scm.test_spo_allocation_documents import (
    _chain,
    _client,
    _grant,
    _product,
    _shipment as _scm_shipment,
    _supplier,
    _u,
)
from tests.test_hide_retired_spo_lines import _alloc, _now
from tests.test_order_inquiry_worklist import _customer, _inquiry_for, _row, _sorento, _uid

pytestmark = requires_pg

MARKER = "zzt-hide-everywhere"


# =================================================================================== #
# AC-E1: order_inquiry_worklist_service.get_spo_detail
# =================================================================================== #

SPO_DETAIL_URL = "/api/v1/project-sales/order-inquiries/spo"


class TestAcE1GetSpoDetailHidesRetiredLines:
    def test_only_visible_lines_returned_and_header_derives_from_them(self, scm_app):
        app, db, gcu, gcuk = scm_app
        client, db = _client(scm_app)
        uid = app.dependency_overrides[gcu]()["id"]
        _grant(db, uid, "projects.projects.view")

        chain = _chain(db)
        doc = unique_code("SPO-E1")
        supplier_visible = _supplier(db, name=f"{MARKER} visible supplier")
        supplier_retired = _supplier(db, name=f"{MARKER} retired supplier")
        product_visible = _product(db, chain)
        product_hidden = _product(db, chain)
        product_r2 = _product(db, chain)

        visible = _alloc(
            db, spo_number=doc, line_no=1, product=product_visible, allocated=10,
            received=0, supplier_id=supplier_visible.id,
        )
        visible.expected_date = date(2026, 12, 1)
        hidden = _alloc(
            db, spo_number=doc, line_no=2, product=product_hidden, allocated=5, received=0,
            line_status="closed", retired_at=_now(), supplier_id=supplier_retired.id,
        )
        hidden.expected_date = date(2026, 1, 1)  # earlier - would win the header if included
        retired_with_receipt = _alloc(
            db, spo_number=doc, line_no=3, product=product_r2, allocated=8, received=3,
            line_status="closed", retired_at=_now(),
        )
        db.flush()

        r = client.get(f"{SPO_DETAIL_URL}/{doc}")
        assert r.status_code == 200, r.text
        body = r.json()

        skus = {line["sku"] for line in body["lines"]}
        assert skus == {product_visible.product_code, product_r2.product_code}, skus
        assert hidden.product_id not in [
            product_visible.id, product_r2.id,
        ]  # sanity: distinct products
        # The header's eta is derived from the VISIBLE lines only - the hidden line's
        # earlier date must not win.
        assert body["eta"] == "2026-12-01", body["eta"]
        assert body["supplier_name"] == supplier_visible.supplier_name, body["supplier_name"]


# =================================================================================== #
# AC-E2: purchase_order_service._unshipped_spo_query / purchase_orders_placed_rows
# =================================================================================== #


class TestAcE2UnshippedSpoQueryHidesRetiredLines:
    def test_excludes_hidden_rows_from_both_rows_and_the_summed_quantity(self):
        from app.services.purchase_order_service import (
            _unshipped_spo_query,
            purchase_orders_placed_rows,
        )

        with blank_session() as db:
            chain = _chain(db)
            product = _product(db, chain)

            visible = _alloc(
                db, spo_number=unique_code("SPO-E2A"), line_no=1, product=product,
                allocated=10, received=0,
            )
            hidden = _alloc(
                db, spo_number=unique_code("SPO-E2B"), line_no=1, product=product,
                allocated=7, received=0, line_status="closed", retired_at=_now(),
            )
            retired_with_receipt = _alloc(
                db, spo_number=unique_code("SPO-E2C"), line_no=1, product=product,
                allocated=9, received=4, line_status="closed", retired_at=_now(),
            )
            db.commit()

            ids = {row[0].id for row in _unshipped_spo_query(db, product_ids=[product.id]).all()}
            assert ids == {visible.id, retired_with_receipt.id}, ids

            rows = purchase_orders_placed_rows(db, product_ids=[product.id])
            spo_rows = [r for r in rows if r["kind"] == "spo"]
            numbers = {r["po_number"] for r in spo_rows}
            assert hidden.spo_number not in numbers, numbers
            assert visible.spo_number in numbers, numbers
            assert retired_with_receipt.spo_number in numbers, numbers
            total = sum(r["outstanding_qty"] for r in spo_rows)
            assert total == 10 + 5, total  # 10 (visible) + (9-4) (retired-with-receipt)


# =================================================================================== #
# AC-E4: entity_resolver._probe_spo / _prefix_probe_spo
# =================================================================================== #


class TestAcE4EntityResolverSpoProbesHideRetired:
    def test_resolves_to_a_visible_sibling_and_never_to_an_all_retired_number(self):
        from app.services import entity_resolver as er

        with blank_session() as db:
            chain = _chain(db)
            product = _product(db, chain)

            # Number 1: one visible line + one hidden line sharing the SAME spo_number.
            shared = unique_code("SPOE4SHARED")
            visible = _alloc(db, spo_number=shared, line_no=1, product=product, allocated=10, received=0)
            _alloc(
                db, spo_number=shared, line_no=2, product=product, allocated=5, received=0,
                line_status="closed", retired_at=_now(),
            )

            # Number 2: EVERY line retired with zero receipt - must not resolve at all.
            all_retired = unique_code("SPOE4GONE")
            _alloc(
                db, spo_number=all_retired, line_no=1, product=product, allocated=3, received=0,
                line_status="closed", retired_at=_now(),
            )

            # Number 3 (R2): retired but carrying a receipt - stays resolvable.
            retired_with_receipt_number = unique_code("SPOE4R2")
            retired_with_receipt = _alloc(
                db, spo_number=retired_with_receipt_number, line_no=1, product=product,
                allocated=6, received=2, line_status="closed", retired_at=_now(),
            )
            db.commit()

            exact = er._probe_spo(db, [shared, all_retired, retired_with_receipt_number])
            assert {e.uuid for e in exact[shared]} == {visible.id}, exact[shared]
            assert exact[all_retired] == [], exact[all_retired]
            assert {e.uuid for e in exact[retired_with_receipt_number]} == {
                retired_with_receipt.id
            }, exact[retired_with_receipt_number]

            prefix_shared = er._prefix_probe_spo(db, shared[:10])
            assert visible.id in {e.uuid for e in prefix_shared}, prefix_shared
            hidden_ids = {
                a.id for a in db.query(SPOAllocation.id).filter(
                    SPOAllocation.spo_number == shared, SPOAllocation.retired_at.isnot(None)
                ).all()
            }
            assert not hidden_ids & {e.uuid for e in prefix_shared}, prefix_shared

            prefix_gone = er._prefix_probe_spo(db, all_retired[:10])
            assert prefix_gone == [], prefix_gone


# =================================================================================== #
# AC-E5: scm/spo_supply.spo_history_for_product
# =================================================================================== #


class TestAcE5SpoHistoryForProductHidesRetired:
    def test_open_and_history_legs_both_omit_retired_lines(self):
        from tests.scm._revamp_fixtures import category_and_uom, product as _revamp_product
        from tests.scm._revamp_fixtures import recommendation, run, supplier as _revamp_supplier
        from tests.scm._revamp_fixtures import warehouse as _revamp_warehouse
        from app.models.base import company_scope
        from app.services.scm import spo_supply

        with pg_session() as db:
            with company_scope(db, frozenset({SORENTO_COMPANY_ID})):
                cat, uom = category_and_uom(db)
                prod = _revamp_product(db, cat, uom)
                sup = _revamp_supplier(db, f"{MARKER} spo history supplier")
                pool = _revamp_warehouse(db, segment="dealer")
                plan = run(db)
                recommendation(db, plan, prod, pool)

                open_visible = SPOAllocation(
                    id=_u(), spo_number=unique_code("SPOE5OPEN"), spo_line_number=1,
                    warehouse_id=pool.id, product_id=prod.id, allocated_quantity=100,
                    quantity_received=0, supplier_id=sup.id, expected_date=date(2026, 9, 30),
                )
                hidden_open = SPOAllocation(
                    id=_u(), spo_number=unique_code("SPOE5HIDDENOPEN"), spo_line_number=1,
                    warehouse_id=pool.id, product_id=prod.id, allocated_quantity=999,
                    quantity_received=0, supplier_id=sup.id, expected_date=date(2026, 9, 30),
                    retired_at=_now(),
                )
                # R2: retired, `line_status` left `open` (nothing enforces retired implies
                # closed) but carrying a receipt - stays visible, and lands in "open" since
                # allocated (20) still exceeds received (5).
                retired_with_receipt = SPOAllocation(
                    id=_u(), spo_number=unique_code("SPOE5R2"), spo_line_number=1,
                    warehouse_id=pool.id, product_id=prod.id, allocated_quantity=20,
                    quantity_received=5, supplier_id=sup.id, expected_date=date(2026, 9, 30),
                    retired_at=_now(),
                )
                hidden_history = SPOAllocation(
                    id=_u(), spo_number=unique_code("SPOE5HIDDENHIST"), spo_line_number=1,
                    warehouse_id=pool.id, product_id=prod.id, allocated_quantity=40,
                    quantity_received=0, supplier_id=sup.id, expected_date=date(2026, 1, 1),
                    receipt_status="fully_received", line_status="closed", retired_at=_now(),
                )
                db.add_all([open_visible, hidden_open, retired_with_receipt, hidden_history])
                db.flush()

                out = spo_supply.spo_history_for_product(db, str(plan.id), str(prod.id))
                open_numbers = {r["spo_number"] for r in out["open"]}
                history_numbers = {r["spo_number"] for r in out["history"]}

                assert hidden_open.spo_number not in open_numbers, open_numbers
                assert hidden_history.spo_number not in history_numbers, history_numbers
                assert open_visible.spo_number in open_numbers, open_numbers
                assert retired_with_receipt.spo_number in open_numbers, open_numbers


# =================================================================================== #
# AC-E6: scm/purchase_order_service._spo_takes_of
# =================================================================================== #


class TestAcE6SpoTakesOfHidesRetiredLanding:
    def test_a_retired_landing_is_dropped_from_the_source_lines_takes(self):
        from app.services.scm.purchase_order_service import PurchaseOrderService

        with blank_session() as db:
            chain = _chain(db)
            product = _product(db, chain)
            warehouse = Warehouse(
                id=_u(), warehouse_code=unique_code("WH")[:20], warehouse_name=unique_code("wh"),
            )
            supplier = Supplier(id=_u(), supplier_code=unique_code("SUP"), supplier_name=unique_code("sup"))
            db.add_all([warehouse, supplier])
            db.flush()

            source_po = PurchaseOrder(id=_u(), po_number=unique_code("PO-E6SRC"), supplier_id=supplier.id)
            db.add(source_po)
            db.flush()
            source_line = PurchaseOrderLine(
                id=_u(), purchase_order_id=source_po.id, product_id=product.id,
                qty_ordered=30, qty_received=0, line_status="open",
            )
            db.add(source_line)
            db.flush()

            spo_header = PurchaseOrder(id=_u(), po_number=unique_code("SPO-E6"), supplier_id=supplier.id)
            db.add(spo_header)
            db.flush()
            spo_line = PurchaseOrderLine(
                id=_u(), purchase_order_id=spo_header.id, product_id=product.id,
                qty_ordered=30, qty_received=0, line_status="open",
                source_system=SOURCE_SYSTEM,
                source_ref=json.dumps({"pulls": [{"po_line_id": str(source_line.id), "qty": 30}]}),
            )
            db.add(spo_line)
            db.flush()

            hidden_landing = SPOAllocation(
                id=_u(), spo_number=spo_header.po_number, product_id=product.id,
                warehouse_id=warehouse.id, allocated_quantity=30, quantity_received=0,
                po_line_id=spo_line.id, line_status="closed", retired_at=_now(),
            )
            db.add(hidden_landing)
            db.flush()

            out = PurchaseOrderService(db)._spo_takes_of([source_line.id])
            takes = out.get(source_line.id, [])
            assert len(takes) == 1, takes
            assert takes[0]["warehouses"] == [], takes[0]  # the retired landing names nowhere


# =================================================================================== #
# AC-E7: scm/coverage_service._supply_events_many (shipment leg) - S4, NOT yet fixed
# =================================================================================== #


class TestAcE7CoverageServiceShipmentLegHidesRetired:
    def test_no_cover_is_credited_from_a_retired_only_allocation_and_the_shortfall_grows(self):
        """AC-E7. A shipment line with 100 units outstanding whose ONLY allocation is a
        retired, zero-receipt row must not credit the pool with cover: the in-transit
        timeline event must not appear, and `unattributed_in_transit_qty` (the shortfall a
        buyer sees) must read the full 100, not 0.

        RED today: `coverage_service.py`'s `ship_rows` query outer-joins `SPOAllocation`
        with no visibility filter, so the retired-only row is still summed into
        `entry["allocated"]`/`entry["here"]`, producing a 100-unit SUPPLY_IN_TRANSIT event
        and an `unattributed_in_transit_qty` of 0 - cover credited from a line AutoCount
        deleted, and the shortfall it should have surfaced instead reads as covered.
        """
        from app.services.scm.coverage_service import CoverageService
        from app.services.scm.coverage_timeline import SUPPLY_IN_TRANSIT

        with pg_session() as db:
            cat = ProductCategory(id=_u(), category_code=unique_code("CAT")[:40], category_name=unique_code("cat"))
            uom = UnitOfMeasure(id=_u(), uom_name=unique_code("uom"), uom_code=unique_code("U")[:20])
            db.add_all([cat, uom])
            db.flush()
            product = Product(
                id=_u(), product_code=unique_code("SKU"), product_name="ZZT E7 product",
                category_id=cat.id, base_uom_id=uom.id, list_price=0,
            )
            pool = Warehouse(
                id=_u(), warehouse_code=unique_code("POOLE7"), warehouse_name="ZZT E7 pool",
                is_active=True, counts_as_available=True,
            )
            db.add_all([product, pool])
            db.flush()
            pool.pool_warehouse_id = pool.id
            db.flush()

            sup = Supplier(id=_u(), supplier_code=unique_code("S"), supplier_name="ZZT E7 supplier")
            db.add(sup)
            db.flush()
            ship = InboundShipment(
                id=_u(), shipment_number=unique_code("SHE7")[:50], supplier_id=sup.id,
                shipment_date=date(2026, 1, 1), estimated_arrival_date=date(2026, 10, 1),
                shipment_status="in_transit",
            )
            db.add(ship)
            db.flush()
            db.add(InboundShipmentLine(
                id=_u(), shipment_id=ship.id, product_id=product.id,
                quantity_shipped=100, quantity_received=0, line_status="in_transit",
            ))
            db.flush()
            db.add(SPOAllocation(
                id=_u(), spo_number=unique_code("SPOE7"), inbound_shipment_id=ship.id,
                product_id=product.id, warehouse_id=pool.id, allocated_quantity=100,
                quantity_received=0, line_status="closed", retired_at=_now(),
            ))
            db.flush()

            svc = CoverageService(db)
            cov = svc.coverage_for(product.id, pool_id=pool.id)
            in_transit_rows = [
                r for r in cov.timeline.rows if r.event.supply_stage == SUPPLY_IN_TRANSIT
            ]
            assert in_transit_rows == [], in_transit_rows
            assert cov.unattributed_in_transit_qty == 100.0, cov.unattributed_in_transit_qty


# =================================================================================== #
# AC-E8: procurement_service.InboundShipmentService.list_shipments spo_allocations_count
# =================================================================================== #


class TestAcE8ListShipmentsSpoCountHidesRetired:
    def test_spo_allocations_count_is_visible_only_and_agrees_with_the_grouped_listing(self):
        from app.services.procurement_service import InboundShipmentService, PickingHeaderService

        with blank_session() as db:
            chain = _chain(db)
            product = _product(db, chain)
            ship = InboundShipment(
                id=_u(), shipment_number=unique_code("SHE8")[:50],
                shipment_date=date(2026, 1, 1), shipment_status="in_transit",
            )
            db.add(ship)
            db.flush()
            db.add(InboundShipmentLine(
                id=_u(), shipment_id=ship.id, product_id=product.id, quantity_shipped=10,
            ))
            visible = _alloc(
                db, spo_number=unique_code("SPOE8A"), line_no=1, product=product, allocated=5, received=0,
            )
            visible.inbound_shipment_id = ship.id
            hidden = _alloc(
                db, spo_number=unique_code("SPOE8B"), line_no=1, product=product, allocated=5, received=0,
                line_status="closed", retired_at=_now(),
            )
            hidden.inbound_shipment_id = ship.id
            db.commit()

            result = InboundShipmentService(db).list_shipments(query=ship.shipment_number, limit=10)
            rows = result["data"]
            assert len(rows) == 1, rows
            assert rows[0].spo_allocations_count == 1, rows[0].spo_allocations_count

            grouped = PickingHeaderService(db).list_allocations_grouped_by_shipment(
                page=1, limit=10, query=ship.shipment_number,
            ) if hasattr(PickingHeaderService(db), "list_allocations_grouped_by_shipment") else None
            if grouped is not None:
                grouped_row = next(
                    (g for g in grouped["data"] if g.get("shipment_id") == ship.id), None
                )
                if grouped_row is not None:
                    assert grouped_row["line_count"] == rows[0].spo_allocations_count


# =================================================================================== #
# AC-E9: project_order_inquiry_service.links_for_rows
# =================================================================================== #


class TestAcE9LinksForRowsHidesRetired:
    def test_the_linked_to_reader_omits_a_retired_lines_number(self):
        from app.services.project_order_inquiry_service import ProjectOrderInquiryService

        with blank_session() as db:
            company_id = _sorento(db)
            chain = _chain(db)
            product = _product(db, chain)
            customer = _customer(db, company_id, f"{MARKER} customer")
            core = SalesOrder(
                id=_uid(), company_id=company_id, so_number=unique_code("SO")[:30],
                customer_id=customer.id, order_date=date(2026, 1, 1),
            )
            db.add(core)
            db.flush()
            adopted = ProjectSalesOrder(
                id=_uid(), company_id=company_id, project_id=None, so_id=core.id,
                provisional_ref=core.so_number, autocount_doc_no=core.so_number, status="adopted",
            )
            db.add(adopted)
            db.flush()
            inquiry = _inquiry_for(db, company_id, adopted)
            row = _row(db, company_id, inquiry, item_code=product.product_code, qty="10")

            visible = _alloc(
                db, spo_number=unique_code("SPOE9A"), line_no=1, product=product, allocated=10, received=0,
            )
            hidden = _alloc(
                db, spo_number=unique_code("SPOE9B"), line_no=1, product=product, allocated=10, received=0,
                line_status="closed", retired_at=_now(),
            )
            db.add(OrderInquiryLink(
                id=_uid(), company_id=company_id, row_id=row.id, spo_allocation_id=visible.id,
                document=visible.spo_number, qty="10",
            ))
            hidden_row = _row(db, company_id, inquiry, item_code=product.product_code, qty="10")
            db.add(OrderInquiryLink(
                id=_uid(), company_id=company_id, row_id=hidden_row.id, spo_allocation_id=hidden.id,
                document=hidden.spo_number, qty="10",
            ))
            db.commit()

            out = ProjectOrderInquiryService(db).links_for_rows([row.id, hidden_row.id])
            visible_docs = {link["document"] for link in out.get(row.id, [])}
            hidden_docs = {link["document"] for link in out.get(hidden_row.id, [])}
            assert visible.spo_number in visible_docs, visible_docs
            assert hidden.spo_number not in hidden_docs, hidden_docs


class TestAcE9ProjectCoverageHidesRetired:
    """AC-E9's other half: `spo_conversion_service._project_coverage`'s own `taken_by` -
    the same "Linked to" fact, read locally by the SPO-create screen rather than through
    `ProjectOrderInquiryService` (module docstring's own reason not to import it).

    Built off `svc.create` + the `World` fixture from `tests.scm.test_spo_conversion`
    (the same shape `test_unwind_deletes_the_order_inquiry_link_before_the_allocation_it_
    points_at` there seeds for a project ORDER BACK row) rather than hand-built demand
    rows: it is the cheapest path to a REAL `spo_allocations` row a project row's link
    resolves through, and reuses the SPO number `_project_coverage` itself has to look up
    in `taken_by` - a hand-built `source_ref`/link pair would only prove the query filters
    correctly, not that a real "Create SPO" write still resolves the same way.
    """

    def test_taken_by_omits_a_retired_lines_number_once_the_spo_that_named_it_is_retired(self):
        from decimal import Decimal

        from app.models.project_so import (
            INQUIRY_RAISED,
            IV_ORDER_BACK,
            OrderInquiry,
            OrderInquiryRow,
            ProjectSalesOrderLine,
            SO_STATUS_DRAFT,
        )
        from app.models.projects import Project
        from app.services.scm import spo_conversion_service as svc
        from tests.scm.test_spo_conversion import World

        with pg_session() as db:
            w = World(db)
            supplier = w.supplier()
            wh = w.warehouse()
            w.po("A", supplier, [("A", 100, 0)])
            shipment, lines = w.shipment([("A", 40, supplier)])
            product = w.product("A")

            title = f"{MARKER} e9 project"
            project = Project(
                id=_u(), title=title, normalised_title=title.lower(),
                project_code=f"{MARKER}-E9-{uuid.uuid4().hex[:8]}",
            )
            db.add(project)
            db.flush()
            pso = ProjectSalesOrder(
                id=_u(), project_id=project.id, area_group="TOWER",
                provisional_ref=f"{MARKER}-E9-PSO-{uuid.uuid4().hex[:6]}",
                autocount_doc_no=f"{MARKER}-E9-SI-{uuid.uuid4().hex[:6]}",
                status=SO_STATUS_DRAFT, grouping_origin="area",
                published_at=datetime(2026, 1, 2, 9, 0),
            )
            db.add(pso)
            db.flush()
            pso_line = ProjectSalesOrderLine(
                id=_u(), project_sales_order_id=pso.id, line_no=1,
                product_id=product.id, description=f"{MARKER} e9 line",
                qty=Decimal("40"), uom="UNIT", unit_price=Decimal("10.00"),
                amount=Decimal("400"), delivery_date=date(2026, 9, 10),
            )
            db.add(pso_line)
            db.flush()
            inquiry = OrderInquiry(id=_u(), project_sales_order_id=pso.id, state=INQUIRY_RAISED)
            db.add(inquiry)
            db.flush()
            row = OrderInquiryRow(
                id=_u(), order_inquiry_id=inquiry.id, so_line_id=pso_line.id,
                item_code=product.product_code, qty=Decimal("40"),
                delivery_date=date(2026, 9, 10), verb=IV_ORDER_BACK, state=INQUIRY_RAISED,
            )
            db.add(row)
            db.flush()

            created = svc.create(
                db, str(shipment.id),
                [{
                    "shipment_line_id": str(lines[0].id), "qty": 40, "include": True,
                    "location_splits": [{"warehouse_id": str(wh.id), "qty": 40}],
                    "so_takes": [{"key": f"project:{row.id}", "qty": 40}],
                }],
            )
            spo_number = created["created_spos"][0]["po_number"]

            key = f"project:{row.id}"
            before = svc._project_coverage(db, str(product.id))
            before_row = next(r for r in before if r["key"] == key)
            assert spo_number in before_row["taken_by"], before_row

            # Retire every allocation this SPO wrote - the leftover sweep's own shape.
            db.query(SPOAllocation).filter(SPOAllocation.spo_number == spo_number).update(
                {"retired_at": _now(), "line_status": "closed"}, synchronize_session=False
            )
            db.flush()

            after = svc._project_coverage(db, str(product.id))
            after_row = next(r for r in after if r["key"] == key)
            assert spo_number not in after_row["taken_by"], after_row


# =================================================================================== #
# AC-E10: scm/spo_conversion_service.coverage_for_so_lines and _own_state
#
# AC-E10's own `_own_state` half is REVISED by AC-E16 (round 2, security review):
# `_own_state` stays unfiltered (a writer's view, read by the SPO edit SAVE as well as
# the planner display), and the filter moves to `planner_state`'s own display copy. See
# `TestAcE16OwnStateIsAWritersViewNeverFiltered` below.
# =================================================================================== #


class TestAcE10CoverageForSoLinesHidesRetired:
    def test_coverage_for_so_lines_omits_a_retired_only_landing(self):
        from app.services.scm import spo_conversion_service as svc
        from app.services.scm.demand import demand_qty  # noqa: F401 - import smoke, used indirectly
        from tests.scm.test_spo_conversion import World
        from tests.scm.test_spo_planner_selection import _confirm, _retail_demand

        with pg_session() as db:
            w = World(db)
            supplier = w.supplier()
            wh = w.warehouse()
            w.po("A", supplier, [("A", 100, 0)])
            retail, so = _retail_demand(
                db, w, "A", wh, qty=30, required=date(2026, 9, 1),
            )
            shipment, lines = w.shipment([("A", 30, supplier)])
            created = svc.create(
                db, str(shipment.id),
                [_confirm(
                    lines[0], 30,
                    location_splits=[{"warehouse_id": str(wh.id), "qty": 30}],
                    so_takes=[{"key": f"retail:{retail.id}", "qty": 30}],
                )],
            )
            spo_number = created["created_spos"][0]["po_number"]

            before = svc.coverage_for_so_lines(db, [str(retail.id)])
            before_numbers = {e["document"] for e in before.get(str(retail.id), [])}
            assert spo_number in before_numbers, before_numbers

            # Retire every allocation this SPO wrote (the leftover sweep's own shape:
            # retired_at set, receipt stays zero).
            db.query(SPOAllocation).filter(SPOAllocation.spo_number == spo_number).update(
                {"retired_at": _now(), "line_status": "closed"}, synchronize_session=False
            )
            db.flush()

            after = svc.coverage_for_so_lines(db, [str(retail.id)])
            after_numbers = {e["document"] for e in after.get(str(retail.id), [])}
            assert spo_number not in after_numbers, after_numbers


class TestAcE16OwnStateIsAWritersViewNeverFiltered:
    """AC-E16 (round 2, revises AC-E10's `_own_state` half). `_own_state` feeds the SPO
    edit SAVE (`revise`) as well as `planner_state` (the display) - a save that could not
    see a hidden allocation would neither update nor delete it and would insert a SECOND
    row for the same (shipment line, warehouse). So `_own_state` itself stays UNFILTERED
    (R7 amended: a user-facing READ takes the clause, a read a WRITE depends on never
    does); the filter moves to `planner_state`'s own DISPLAY copy of the same state.

    Two tests, matching the UAC's "assert both halves": the writer's own read (direct
    call, cheap - `_own_state`'s `po` argument is unused, so a `SimpleNamespace` link
    stands in for the real `ShipmentLineSpoLink` row) still contains the hidden
    allocation, and the planner DISPLAY (`planner_state`, built off a real `svc.create` +
    `World` write - the same fixture `TestAcE10CoverageForSoLinesHidesRetired` uses, for
    the same reason: a hand-built `po_line_id` only proves the query filters correctly,
    not that a real "Create SPO" edit-mode reopen still hides it) omits it.
    """

    def test_own_state_itself_keeps_the_hidden_allocation_the_writer_needs(self):
        from types import SimpleNamespace

        from app.services.scm.spo_conversion_service import _own_state

        with blank_session() as db:
            chain = _chain(db)
            product = _product(db, chain)
            po = PurchaseOrder(id=_u(), po_number=unique_code("PO-E16OWN"))
            db.add(po)
            db.flush()
            po_line = PurchaseOrderLine(
                id=_u(), purchase_order_id=po.id, product_id=product.id,
                qty_ordered=50, qty_received=0, line_status="open",
            )
            db.add(po_line)
            db.flush()

            visible = SPOAllocation(
                id=_u(), spo_number=unique_code("SPOE16"), product_id=product.id,
                allocated_quantity=20, quantity_received=5, po_line_id=po_line.id,
            )
            hidden = SPOAllocation(
                id=_u(), spo_number=unique_code("SPOE16H"), product_id=product.id,
                allocated_quantity=999, quantity_received=0, po_line_id=po_line.id,
                line_status="closed", retired_at=_now(),
            )
            db.add_all([visible, hidden])
            db.flush()

            links = {"shipment-line-1": SimpleNamespace(purchase_order_line_id=po_line.id)}
            out = _own_state(db, None, links)
            held = out["shipment-line-1"]
            alloc_ids = {a.id for a in held["allocations"]}
            # UNFILTERED: both rows, so a save can find - and update or delete - the
            # hidden one instead of inserting a duplicate for its (line, warehouse).
            assert alloc_ids == {visible.id, hidden.id}, alloc_ids
            assert held["received"] == 5.0, held["received"]

    def test_planner_display_omits_the_hidden_allocation(self):
        from app.services.scm import spo_conversion_service as svc
        from tests.scm.test_spo_conversion import World
        from tests.scm.test_spo_planner_selection import _confirm, _retail_demand

        with pg_session() as db:
            w = World(db)
            supplier = w.supplier()
            wh = w.warehouse()
            w.po("A", supplier, [("A", 100, 0)])
            retail, so = _retail_demand(
                db, w, "A", wh, qty=30, required=date(2026, 9, 1),
            )
            shipment, lines = w.shipment([("A", 30, supplier)])
            created = svc.create(
                db, str(shipment.id),
                [_confirm(
                    lines[0], 30,
                    location_splits=[{"warehouse_id": str(wh.id), "qty": 30}],
                    so_takes=[{"key": f"retail:{retail.id}", "qty": 30}],
                )],
            )
            spo_number = created["created_spos"][0]["po_number"]
            spo_po_id = created["created_spos"][0]["purchase_order_id"]

            # Retire every allocation this SPO wrote - hidden, but still on file for
            # `_own_state`'s own writer read (pinned in the sibling test above).
            db.query(SPOAllocation).filter(SPOAllocation.spo_number == spo_number).update(
                {"retired_at": _now(), "line_status": "closed"}, synchronize_session=False
            )
            db.flush()

            state = svc.planner_state(db, str(shipment.id), spo_po_id)
            line = next(ln for ln in state["lines"] if ln["shipment_line_id"] == str(lines[0].id))
            # The one allocation this SPO wrote (30 units at `wh`) is now hidden - the
            # split editor's own table must not show it, or an operator reopening this
            # SPO would see a location the document no longer names.
            assert line["location_splits"] == [], line["location_splits"]


# =================================================================================== #
# AC-E17 (round 3, reviewer): _spo_cover_by_so_line and coverage_for_so_lines - one
# answer per line. They share the same row scan (`_spo_so_coverage_rows`) but only
# `coverage_for_so_lines` (AC-E10) took the clause; `_spo_cover_by_so_line` fed the
# planner's own `taken_by` a name the sales order's "Linked to" column already hid,
# contradicting the module's own docstring that the two can never disagree.
# =================================================================================== #


class TestAcE17PlannerAndLinkedToAgree:
    def test_taken_by_and_linked_to_agree_once_the_only_allocation_is_retired(self):
        from app.services.scm import spo_conversion_service as svc
        from tests.scm.test_spo_conversion import World
        from tests.scm.test_spo_planner_selection import _confirm, _retail_demand

        with pg_session() as db:
            w = World(db)
            supplier = w.supplier()
            wh = w.warehouse()
            w.po("A", supplier, [("A", 100, 0)])
            retail, so = _retail_demand(
                db, w, "A", wh, qty=30, required=date(2026, 9, 1),
            )
            shipment, lines = w.shipment([("A", 30, supplier)])
            created = svc.create(
                db, str(shipment.id),
                [_confirm(
                    lines[0], 30,
                    location_splits=[{"warehouse_id": str(wh.id), "qty": 30}],
                    so_takes=[{"key": f"retail:{retail.id}", "qty": 30}],
                )],
            )
            spo_number = created["created_spos"][0]["po_number"]
            product = w.product("A")

            def _readers():
                cover = svc.coverage_for_so_lines(db, [str(retail.id)])
                cover_numbers = {e["document"] for e in cover.get(str(retail.id), [])}
                taken_by = svc._spo_cover_by_so_line(db, str(product.id))
                taken_numbers = {e["spo_number"] for e in taken_by.get(str(retail.id), [])}
                return cover_numbers, taken_numbers

            # Sanity: before retiring, both readers name the same SPO for this line.
            cover_before, taken_before = _readers()
            assert spo_number in cover_before, cover_before
            assert spo_number in taken_before, taken_before
            assert cover_before == taken_before, (cover_before, taken_before)

            # Retire the only allocation this SPO wrote.
            db.query(SPOAllocation).filter(SPOAllocation.spo_number == spo_number).update(
                {"retired_at": _now(), "line_status": "closed"}, synchronize_session=False
            )
            db.flush()

            cover_after, taken_after = _readers()
            assert spo_number not in cover_after, cover_after
            assert spo_number not in taken_after, taken_after
            assert cover_after == taken_after, (cover_after, taken_after)


# =================================================================================== #
# AC-E11: spo_last_receipt_service.last_receipt_rows
# =================================================================================== #


class TestAcE11LastReceiptRowsHidesRetired:
    def test_omits_a_retired_line_marked_fully_received_with_a_zeroed_receipt(self):
        from app.services.spo_last_receipt_service import last_receipt_rows

        with blank_session() as db:
            chain = _chain(db)
            product = _product(db, chain)

            visible = _alloc(
                db, spo_number=unique_code("SPOE11A"), line_no=1, product=product,
                allocated=20, received=20, receipt_status="fully_received",
            )
            hidden = _alloc(
                db, spo_number=unique_code("SPOE11B"), line_no=1, product=product,
                allocated=15, received=0, receipt_status="fully_received",
                line_status="closed", retired_at=_now(),
            )
            retired_with_receipt = _alloc(
                db, spo_number=unique_code("SPOE11C"), line_no=1, product=product,
                allocated=9, received=9, receipt_status="fully_received",
                line_status="closed", retired_at=_now(),
            )
            db.commit()

            rows = last_receipt_rows(db, product_ids=[product.id], top_n=10)
            numbers = {r["spo_number"] for r in rows}
            assert hidden.spo_number not in numbers, numbers
            assert visible.spo_number in numbers, numbers
            assert retired_with_receipt.spo_number in numbers, numbers


# =================================================================================== #
# AC-E12: scm/stock_debt_service._holds
# =================================================================================== #


class TestAcE12StockDebtHoldsHidesRetired:
    def test_holds_omits_a_hold_whose_spo_side_names_a_retired_line(self):
        from app.models.project_so import (
            INQUIRY_RAISED,
            IV_ORDER,
            OrderInquiry,
            OrderInquiryRow,
            ProjectSalesOrderLine,
        )
        from app.services.scm.stock_debt_service import StockDebtService

        with blank_session() as db:
            company_id = _sorento(db)
            chain = _chain(db)
            product = _product(db, chain)
            customer = _customer(db, company_id, f"{MARKER} e12 customer")
            core = SalesOrder(
                id=_uid(), company_id=company_id, so_number=unique_code("SO")[:30],
                customer_id=customer.id, order_date=date(2026, 1, 1),
            )
            db.add(core)
            db.flush()
            adopted = ProjectSalesOrder(
                id=_uid(), company_id=company_id, project_id=None, so_id=core.id,
                provisional_ref=core.so_number, autocount_doc_no=core.so_number, status="adopted",
            )
            db.add(adopted)
            db.flush()
            core_line = SalesOrderLine(
                id=_uid(), company_id=company_id, sales_order_id=core.id,
                product_id=product.id, qty_ordered="10",
            )
            db.add(core_line)
            db.flush()
            core_line_id = core_line.id
            project_line = ProjectSalesOrderLine(
                id=_uid(), company_id=company_id, project_sales_order_id=adopted.id,
                line_no=1, product_id=product.id, description="e12 line", qty="10",
                uom="UNIT", unit_price="1.00", amount="10.00",
                core_sales_order_line_id=core_line_id,
            )
            db.add(project_line)
            db.flush()
            inquiry = OrderInquiry(
                id=_uid(), company_id=company_id, project_sales_order_id=adopted.id,
                inquiry_no=unique_code("OI")[:20],
            )
            db.add(inquiry)
            db.flush()

            hidden = _alloc(
                db, spo_number=unique_code("SPOE12"), line_no=1, product=product, allocated=10,
                received=0, line_status="closed", retired_at=_now(),
            )
            row = OrderInquiryRow(
                id=_uid(), company_id=company_id, order_inquiry_id=inquiry.id,
                so_line_id=project_line.id, qty="10", verb=IV_ORDER, state=INQUIRY_RAISED,
            )
            db.add(row)
            db.flush()
            db.add(OrderInquiryLink(
                id=_uid(), company_id=company_id, row_id=row.id, spo_allocation_id=hidden.id,
                document=hidden.spo_number, qty="10",
            ))
            db.commit()

            holds = StockDebtService(db)._holds([], {core_line_id})
            assert holds == [], holds


# =================================================================================== #
# AC-E13: scm/order_link_service._purchase_side
# =================================================================================== #


class TestAcE13PurchaseSideNeverResolvesToARetiredLine:
    def test_resolves_to_a_visible_sibling_and_leaves_an_all_retired_number_unresolved(self):
        from app.services.scm.order_link_service import _purchase_side

        with blank_session() as db:
            chain = _chain(db)
            product = _product(db, chain)

            # `doc_family()` (`order_link_service`) classifies by NUMBER PREFIX - "SPO-" -
            # so the marker has to sit after that prefix, not before it, or the number
            # resolves as a plain PO and the SPO-side query is never reached at all.
            shared = f"SPO-{unique_code('E13SHARED')}"
            visible = _alloc(db, spo_number=shared, line_no=1, product=product, allocated=10, received=0)
            _alloc(
                db, spo_number=shared, line_no=2, product=product, allocated=5, received=0,
                line_status="closed", retired_at=_now(),
            )
            all_retired = f"SPO-{unique_code('E13GONE')}"
            _alloc(
                db, spo_number=all_retired, line_no=1, product=product, allocated=3, received=0,
                line_status="closed", retired_at=_now(),
            )
            db.commit()

            by_key, by_number = _purchase_side(db, {shared, all_retired})
            assert by_number[shared] == ("spo_allocation_id", visible.id), by_number[shared]
            assert all_retired not in by_number, by_number
