"""S1 - order inquiry rows follow the AutoCount book, through the PO to SPO chain,
closed or not.

UAC: `documentation/plans/scm/oi-follow-book-chain-acceptance-criteria.md`, Group A
(AC-FB-1 to AC-FB-12) plus the cascade half of Group B (AC-FB-20).
Plan: `documentation/plans/scm/PLAN-oi-follow-book-chain.md`, S1.

The seam under test is `ProjectOrderInquiryService.follow_book_for_rows`, which does
not exist yet - every RED state below is that missing method (AttributeError), except
AC-FB-11 which calls the EXISTING `auto_place_for_products` and asserts on the book's
own document being reached, something today's cascade cannot do at all (a closed line
is invisible to its `line_status == "open"` filter).

Substrate: `tests/_pg_fixture.py::blank_session`, Postgres only, every chain seeded by
hand - never a borrowed row. `set_company_scope(db, None)` is called once per test so
both companies seeded here (AC-FB-9) are visible to the test's own queries; it says
nothing about what the SERVICE itself scopes to, which is exactly what AC-FB-9 checks.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from ._pg_fixture import blank_session, unique_code

MARKER = "ZZTFB"


def _ref(stem: str) -> str:
    return f"{MARKER}:{stem}:{uuid.uuid4().hex[:8]}"


# --------------------------------------------------------------------------- fixture
@pytest.fixture
def ctx():
    with blank_session() as db:
        # UNSET (the fail-closed default) would hide company B's own rows from this
        # test's OWN assertions - AC-FB-9 needs both companies readable here, whatever
        # the service under test itself scopes to.
        set_company_scope(db, None)
        other = Company(
            id=str(uuid.uuid4()), name=f"{MARKER} company B", code=f"ZFB{uuid.uuid4().hex[:6]}"
        )
        db.add(other)
        db.flush()
        db.commit()
        yield SimpleNamespace(db=db, company_a=DEFAULT_COMPANY_ID, company_b=str(other.id))


# --------------------------------------------------------------------------- seeds
def _seed_product(db, *, company_id) -> Product:
    category = ProductCategory(
        company_id=company_id, category_code=unique_code(MARKER), category_name=f"{MARKER} category"
    )
    uom = UnitOfMeasure(
        company_id=company_id, uom_code=unique_code(MARKER), uom_name=f"{MARKER} unit"
    )
    db.add_all([category, uom])
    db.flush()
    product = Product(
        company_id=company_id,
        product_code=unique_code(MARKER),
        product_name=f"{MARKER} product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("10"),
    )
    db.add(product)
    db.flush()
    return product


def _seed_so_line(db, *, company_id, product_id, source_ref, qty="10"):
    """A sales order + one CORE line carrying `source_ref` - the ref a PO/SPO line's
    own `from_so_line_ref` joins against."""
    so = SalesOrder(
        company_id=company_id, so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}", status="open"
    )
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        company_id=company_id,
        sales_order_id=so.id,
        product_id=product_id,
        qty_ordered=Decimal(qty),
        source_ref=source_ref,
    )
    db.add(line)
    db.flush()
    return so, line


def _seed_po_line(
    db,
    *,
    company_id,
    product_id,
    from_so_line_ref=None,
    own_ref=None,
    qty_ordered="4",
    qty_received="0",
    header_status="open",
    line_status=None,
):
    """A purchase order + one line. `own_ref` is THIS line's own `source_ref` - the
    identity an SPO allocation's `from_po_line_ref` names to chain to it."""
    supplier = Supplier(
        company_id=company_id, supplier_code=unique_code(MARKER), supplier_name=f"{MARKER} supplier"
    )
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        company_id=company_id,
        po_number=f"{MARKER}-PO-{uuid.uuid4().hex[:8]}",
        supplier_id=supplier.id,
        status=header_status,
    )
    db.add(po)
    db.flush()
    ordered, received = Decimal(qty_ordered), Decimal(qty_received)
    if line_status is None:
        if header_status == "cancelled":
            line_status = "cancelled"
        elif ordered > 0 and received >= ordered:
            line_status = "closed"
        else:
            line_status = "open"
    line = PurchaseOrderLine(
        company_id=company_id,
        purchase_order_id=po.id,
        product_id=product_id,
        qty_ordered=ordered,
        qty_received=received,
        line_status=line_status,
        from_so_line_ref=from_so_line_ref,
        source_ref=own_ref or _ref("POL"),
    )
    db.add(line)
    db.flush()
    return po, line


def _seed_spo_line(
    db,
    *,
    company_id,
    product_id,
    from_so_line_ref=None,
    from_po_line_ref=None,
    from_po_number=None,
    allocated_quantity=2,
    quantity_received=0,
    retired_at=None,
    line_status="open",
):
    row = SPOAllocation(
        company_id=company_id,
        spo_number=f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}",
        spo_line_number=1,
        product_id=product_id,
        allocated_quantity=int(allocated_quantity),
        quantity_received=int(quantity_received),
        line_status=line_status,
        from_so_line_ref=from_so_line_ref,
        from_po_line_ref=from_po_line_ref,
        from_po_number=from_po_number,
        retired_at=retired_at,
    )
    db.add(row)
    db.flush()
    return row


def _seed_mirror(db, *, company_id, core_line, product_id, qty):
    """A project mirror of `core_line` (the reconciled shape `follow_book_for_rows`
    resolves a row's core sales-order line through), same seeding as
    `test_ingest_documents_v5_so_po_links.py::_mirror_row`."""
    so_number = db.execute(
        text("SELECT so_number FROM sales_orders WHERE id = :id"),
        {"id": core_line.sales_order_id},
    ).scalar()
    pso = ProjectSalesOrder(
        company_id=company_id,
        project_id=None,
        so_id=core_line.sales_order_id,
        provisional_ref=f"{MARKER}-PSO-{uuid.uuid4().hex[:8]}",
        autocount_doc_no=so_number,
        status="adopted",
    )
    db.add(pso)
    db.flush()
    mirror_line = ProjectSalesOrderLine(
        company_id=company_id,
        project_sales_order_id=pso.id,
        line_no=1,
        core_sales_order_line_id=core_line.id,
        product_id=product_id,
        description=f"{MARKER} mirror",
        qty=Decimal(str(qty)),
        uom="UNIT",
        unit_price=Decimal("10.00"),
        amount=Decimal("0"),
    )
    db.add(mirror_line)
    db.flush()
    inquiry = OrderInquiry(company_id=company_id, project_sales_order_id=pso.id)
    db.add(inquiry)
    db.flush()
    return pso, mirror_line, inquiry


def _seed_row(
    db,
    *,
    company_id,
    inquiry_id,
    so_line_id,
    qty,
    verb=IV_ORDER,
    state=INQUIRY_RAISED,
    ack_state=ACK_ACKNOWLEDGED,
    redirected_to_pool=False,
):
    row = OrderInquiryRow(
        company_id=company_id,
        order_inquiry_id=inquiry_id,
        so_line_id=so_line_id,
        qty=Decimal(str(qty)),
        verb=verb,
        state=state,
        ack_state=ack_state,
        redirected_to_pool=redirected_to_pool,
    )
    db.add(row)
    db.flush()
    return row


def _seed_row_and_mirror(db, *, company_id, core_line, product_id, qty, **row_kwargs):
    pso, mirror_line, inquiry = _seed_mirror(
        db, company_id=company_id, core_line=core_line, product_id=product_id, qty=qty
    )
    row = _seed_row(
        db,
        company_id=company_id,
        inquiry_id=inquiry.id,
        so_line_id=mirror_line.id,
        qty=qty,
        **row_kwargs,
    )
    return pso, mirror_line, inquiry, row


def _existing_link(
    db, *, company_id, row_id, document, qty, po_line_id=None, spo_allocation_id=None, auto=True
):
    link = OrderInquiryLink(
        company_id=company_id,
        row_id=row_id,
        po_line_id=po_line_id,
        spo_allocation_id=spo_allocation_id,
        document=document,
        qty=Decimal(str(qty)),
        auto=auto,
    )
    db.add(link)
    db.flush()
    return link


def _links_of(db, row_id):
    return db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row_id).all()


# ============================================================== Group A - the rule
class TestFollowBookForRows:
    def test_fb1_chain_links_spo_not_closed_po(self, ctx):
        """AC-FB-1 (the owner's case): the SPO the PO became takes the link, the
        closed PO line takes none of it."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="2"
        )
        po, po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_so_line_ref=ref,
            qty_ordered="2",
            qty_received="2",
        )
        assert po_line.line_status == "closed"
        spo = _seed_spo_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_po_line_ref=po_line.source_ref,
            from_po_number=po.po_number,
            allocated_quantity=2,
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="2"
        )
        db.commit()

        svc = ProjectOrderInquiryService(db)
        svc.follow_book_for_rows(
            [str(row.id)], trigger="autocount_ingest", company_id=ctx.company_a, actor_user_id=None
        )

        links = _links_of(db, row.id)
        assert len(links) == 1, links
        assert links[0].spo_allocation_id == spo.id
        assert links[0].po_line_id is None
        assert Decimal(str(links[0].qty)) == Decimal("2")
        assert links[0].auto is True
        db.refresh(row)
        assert "autocount" in (row.note or "").lower(), row.note
        assert row.state != INQUIRY_RAISED

    def test_fb2_direct_spo_ref(self, ctx):
        """AC-FB-2: an SPO line naming L directly (no PO in between) takes the link."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="3"
        )
        spo = _seed_spo_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_so_line_ref=ref,
            allocated_quantity=3,
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="3"
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row.id)], trigger="autocount_ingest", company_id=ctx.company_a, actor_user_id=None
        )

        links = _links_of(db, row.id)
        assert len(links) == 1, links
        assert links[0].spo_allocation_id == spo.id
        assert links[0].po_line_id is None

    def test_fb3_closed_received_po_no_spo(self, ctx):
        """AC-FB-3 (closed or not): a closed, fully received PO line with no shipping
        order behind it still takes the link, `received=true` where a reader can see it."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="5"
        )
        _po, po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_so_line_ref=ref,
            qty_ordered="5",
            qty_received="5",
        )
        assert po_line.line_status == "closed"
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="5"
        )
        db.commit()

        svc = ProjectOrderInquiryService(db)
        svc.follow_book_for_rows(
            [str(row.id)], trigger="autocount_ingest", company_id=ctx.company_a, actor_user_id=None
        )

        links = _links_of(db, row.id)
        assert len(links) == 1, links
        assert links[0].po_line_id == po_line.id
        assert Decimal(str(links[0].qty)) == Decimal("5")

        if hasattr(svc, "links_for_rows"):
            served = svc.links_for_rows([str(row.id)])
            entries = served.get(str(row.id)) or []
            assert entries, entries
            assert entries[0].get("received") is True, entries[0]

    def test_fb4_cancelled_po_line_and_retired_spo_ignored(self, ctx):
        """AC-FB-4: a cancelled PO line naming L, and a retired (not visible) SPO
        line naming a different L, both link nothing - the rows are untouched."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_a = _ref("SOL")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="2"
        )
        _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_so_line_ref=ref_a,
            qty_ordered="2",
            header_status="cancelled",
        )
        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="2"
        )

        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="2"
        )
        _seed_spo_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_so_line_ref=ref_b,
            allocated_quantity=2,
            quantity_received=0,
            retired_at=datetime.now(timezone.utc),
        )
        _pso_b, _mirror_b, _inquiry_b, row_b = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="2"
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_a.id), str(row_b.id)],
            trigger="autocount_ingest",
            company_id=ctx.company_a,
            actor_user_id=None,
        )

        assert _links_of(db, row_a.id) == []
        assert _links_of(db, row_b.id) == []
        db.refresh(row_a)
        db.refresh(row_b)
        assert row_a.state == INQUIRY_RAISED
        assert row_b.state == INQUIRY_RAISED

    def test_fb5_spo_first_po_remainder(self, ctx):
        """AC-FB-5 (no double count): a PO line of 10 naming L, of which an SPO line
        of 6 names that PO line: 6 lands on the SPO, 4 on the PO line, never 10+6."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="10"
        )
        po, po_line = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id, from_so_line_ref=ref, qty_ordered="10"
        )
        spo = _seed_spo_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_po_line_ref=po_line.source_ref,
            from_po_number=po.po_number,
            allocated_quantity=6,
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="10"
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row.id)], trigger="autocount_ingest", company_id=ctx.company_a, actor_user_id=None
        )

        links = _links_of(db, row.id)
        by_spo = {l.spo_allocation_id: Decimal(str(l.qty)) for l in links if l.spo_allocation_id}
        by_po = {l.po_line_id: Decimal(str(l.qty)) for l in links if l.po_line_id}
        assert by_spo.get(spo.id) == Decimal("6"), links
        assert by_po.get(po_line.id) == Decimal("4"), links
        assert sum(Decimal(str(l.qty)) for l in links) == Decimal("10")

    def test_fb6_same_line_sibling_holds_document(self, ctx):
        """AC-FB-6: another row of the SAME sales-order line already holds the whole
        document - a plain link, and a REDIRECTED row holding a fully received
        document - so the new row takes nothing and nothing is displaced."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        # Scenario A: an ordinary sibling link already holds the whole SPO line.
        ref_a = _ref("SOL")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="4"
        )
        spo_a = _seed_spo_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_so_line_ref=ref_a,
            allocated_quantity=2,
        )
        _pso_a, mirror_a, inquiry_a = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="2"
        )
        sibling_a = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_a.id, so_line_id=mirror_a.id, qty="2"
        )
        _existing_link(
            db,
            company_id=ctx.company_a,
            row_id=sibling_a.id,
            document=spo_a.spo_number,
            qty="2",
            spo_allocation_id=spo_a.id,
        )
        new_row_a = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_a.id, so_line_id=mirror_a.id, qty="2"
        )

        # Scenario B: the sibling is REDIRECTED, holding a FULLY RECEIVED PO line.
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="6"
        )
        po_b, po_line_b = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_so_line_ref=ref_b,
            qty_ordered="3",
            qty_received="3",
        )
        _pso_b, mirror_b, inquiry_b = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="3"
        )
        sibling_b = _seed_row(
            db,
            company_id=ctx.company_a,
            inquiry_id=inquiry_b.id,
            so_line_id=mirror_b.id,
            qty="3",
            redirected_to_pool=True,
        )
        _existing_link(
            db,
            company_id=ctx.company_a,
            row_id=sibling_b.id,
            document=po_b.po_number,
            qty="3",
            po_line_id=po_line_b.id,
        )
        new_row_b = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_b.id, so_line_id=mirror_b.id, qty="3"
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(new_row_a.id), str(new_row_b.id)],
            trigger="autocount_ingest",
            company_id=ctx.company_a,
            actor_user_id=None,
        )

        assert _links_of(db, new_row_a.id) == []
        assert _links_of(db, new_row_b.id) == []
        assert len(_links_of(db, sibling_a.id)) == 1
        assert len(_links_of(db, sibling_b.id)) == 1

    def test_fb7_ambiguous_ref_refused(self, ctx):
        """AC-FB-7: a ref that matches more than one sales-order line (the August
        ordinals) is refused - nothing is linked from it."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        shared_ref = _ref("AMB")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=shared_ref, qty="4"
        )
        _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=shared_ref, qty="4"
        )
        _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id, from_so_line_ref=shared_ref, qty_ordered="4"
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="4"
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row.id)], trigger="autocount_ingest", company_id=ctx.company_a, actor_user_id=None
        )

        assert _links_of(db, row.id) == []

    def test_fb8_other_product_ignored(self, ctx):
        """AC-FB-8: a document naming L but carrying a DIFFERENT product is ignored."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        other_product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="3"
        )
        _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=other_product.id,
            from_so_line_ref=ref,
            qty_ordered="3",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="3"
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row.id)], trigger="autocount_ingest", company_id=ctx.company_a, actor_user_id=None
        )

        assert _links_of(db, row.id) == []

    def test_fb9_other_company_ref(self, ctx):
        """AC-FB-9 [SEC]: the ref resolves only to a PO line whose OWN company is B -
        a cross-tenant data shape - while the row (and the pairing) is company A.
        Nothing is linked for A."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="3"
        )
        # Deliberately company_b, naming the ref and carrying company_a's product id -
        # a shape no honest push produces, which is exactly what proves the isolation
        # boundary rather than assuming it.
        _seed_po_line(
            db, company_id=ctx.company_b, product_id=product.id, from_so_line_ref=ref, qty_ordered="3"
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="3"
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row.id)], trigger="autocount_ingest", company_id=ctx.company_a, actor_user_id=None
        )

        assert _links_of(db, row.id) == []

    def test_fb10_not_linkable_row_untouched(self, ctx):
        """AC-FB-10: a row outside the cascade's own linkable predicate (here,
        state == 'cancelled') is left exactly as it is."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="3"
        )
        _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id, from_so_line_ref=ref, qty_ordered="3"
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db,
            company_id=ctx.company_a,
            core_line=core_line,
            product_id=product.id,
            qty="3",
            state=INQUIRY_CANCELLED,
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row.id)], trigger="autocount_ingest", company_id=ctx.company_a, actor_user_id=None
        )

        assert _links_of(db, row.id) == []
        db.refresh(row)
        assert row.state == INQUIRY_CANCELLED

    def test_fb11_cascade_deals_only_remainder(self, ctx):
        """AC-FB-11 + AC-FB-20: the book covers part of the need (a CLOSED PO line the
        ordinary cascade - `line_status == "open"` only - can never reach on its own);
        the cascade deals the rest against an unrelated, open document of the same
        product. Both lands from ONE `auto_place_for_products` call."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="5"
        )
        # The book names this line - closed, fully received.
        _book_po, book_po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_so_line_ref=ref,
            qty_ordered="2",
            qty_received="2",
        )
        assert book_po_line.line_status == "closed"
        # An UNRELATED, cascade-eligible OPEN PO line of the same product - what the
        # ordinary walk deals with today, with free capacity well past the remainder.
        _other_po, other_po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="20",
            header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="5"
        )
        db.commit()

        ProjectOrderInquiryService(db).auto_place_for_products(
            None, actor_user_id=None, trigger="zzt_fb11", row_ids=[str(row.id)]
        )

        links = _links_of(db, row.id)
        by_po = {l.po_line_id: Decimal(str(l.qty)) for l in links if l.po_line_id}
        assert by_po.get(book_po_line.id) == Decimal("2"), links
        assert by_po.get(other_po_line.id) == Decimal("3"), links
        assert sum(Decimal(str(l.qty)) for l in links) == Decimal("5")


# ===================================================== AC-FB-24, cascade caller
class TestCascadePathIsNotCapped:
    def test_cascade_path_is_not_capped(self, ctx, monkeypatch):
        """AC-FB-24's cap is a guard on the EXTERNAL INGEST surface (an ESB batch
        naming arbitrarily many moves/rows), not on the cascade - fix-round finding,
        19 Sep: a company-wide `auto_place_for_products` pass logged "capped at 200
        rows, skipped 4388 of 4588", so the book was honoured for an arbitrary 200
        of 4,588 eligible rows only, on every ordinary Confirm/Link now/board press.

        Each row's own target is a CLOSED, fully received PO line - invisible to
        the ordinary candidate walk (`line_status == 'open'` only, same premise as
        `test_fb11_cascade_deals_only_remainder`) - so a link landing here can only
        have come from the book pass inside `auto_place_for_products`, never the
        ordinary cascade finding it by coincidence. With the cap monkeypatched to
        1, today's code processes only 1 of the 3 named rows and drops the other 2
        - `test_fb24_cap_and_dropped_count` (the ingest route) must keep passing
        unchanged; this is the cascade's OWN caller, a different seam."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        rows = []
        for _ in range(3):
            ref = _ref("SOL")
            _so, core_line = _seed_so_line(
                db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="2"
            )
            _seed_po_line(
                db,
                company_id=ctx.company_a,
                product_id=product.id,
                from_so_line_ref=ref,
                qty_ordered="2",
                qty_received="2",
            )
            _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
                db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="2"
            )
            rows.append(row)
        db.commit()

        monkeypatch.setattr(ProjectOrderInquiryService, "FOLLOW_BOOK_FOR_ROWS_MAX_ROWS", 1)
        ProjectOrderInquiryService(db).auto_place_for_products(
            None,
            actor_user_id=None,
            trigger="zzt_cascade_uncapped",
            row_ids=[str(row.id) for row in rows],
        )

        linked_counts = [len(_links_of(db, row.id)) for row in rows]
        assert linked_counts == [1, 1, 1], linked_counts


# ============================================================ AC-FB-12, no new test
def test_fb12_importer_pairing_unchanged_baseline():
    """AC-FB-12: `_pair`'s own extraction into `pair_needs` must not move a single one
    of the importer's existing assertions. There is nothing new to assert HERE - the
    contract is that the files below, run as they are today, are green before this
    slice's code lands, and stay green after. Baseline recorded 19 Sep 2026, run
    against `sorento_oi_book_chain`:

        pytest tests/test_project_label_order_inquiry_import.py \\
               tests/test_project_order_inquiry_import_migration.py \\
               tests/test_project_order_inquiry_import_reader.py \\
               tests/test_oi_sheet_pairing_repair.py \\
               tests/test_oi_sheet_multi_product_cell.py \\
               tests/test_oi_sheet_date_follow_sheet.py

    155 passed, 0 failed. The coder re-runs this exact list after S1 lands - not a
    new fixture, the existing files, unedited (AC-FB-12's own wording).
    """
