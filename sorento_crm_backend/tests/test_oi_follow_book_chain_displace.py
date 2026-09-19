"""S3 - order inquiry rows follow the AutoCount book: displacement (D3) and the
D4 lift of AC-RL-43 (a book MOVE now follows a fully received document too).

UAC: `documentation/plans/scm/oi-follow-book-chain-acceptance-criteria.md`, Group C
(AC-FB-30 to AC-FB-34).
Plan: `documentation/plans/scm/PLAN-oi-follow-book-chain.md`, S3 (section 4.1 step
4, section 3 D3/D4 rulings).

Two seams:

  - `ProjectOrderInquiryService.follow_book_for_rows` (AC-FB-30/31/32/33/6b/30b):
    today (S1) it calls `pair_needs` and writes only what is FREE - a target
    already fully held by another row's link is read as having zero capacity
    left and the book-named row gets nothing, no displacement attempted at all.
    D3 requires the book to win: remove the other line's link with a note, and
    give the row of L what AutoCount actually states. Every RED state below on
    this seam is that missing removal-and-note step.

  - `follow_book_repairing` / `_follow_one_move`, through the PO ingest ROUTE
    (AC-FB-34): `_is_target_received` makes a fully received document's ref move
    a no-op today (AC-RL-43, `PLAN-oi-replan-received-links.md`). D4 lifts this
    fully - the move must happen anyway. The RED state is that early return.

Substrate: `ProjectOrderInquiryService` tests reuse `ctx` and the seed helpers
from `tests/test_oi_follow_book_chain.py` (S1) by import, unedited, per the
tester brief. The one route test (`TestBookMoveLiftsReceivedGuard`) reuses `env`
/ `INGEST_PO` / `_po_line` / `_po_record` from `tests/test_ingest_documents.py`,
aliased to avoid colliding with the `ctx`-file's own `_ref`/`MARKER`, and defines
its own `_mirror_row` / `_seed_ref_only_so_line` - byte-for-byte copies of
`tests/test_ingest_documents_v5_so_po_links.py`'s helpers of the same name,
needed there (and here) because `_follow_one_move` places the moved quantity
through `place_on_po_allocations`, which DOES apply G7 dedication; a plain,
undelivered sales order line's own outstanding claim would otherwise contest
the mirror row's need for capacity the fixture never meant to contest (see that
file's own comment on `_seed_ref_only_so_line`).

AC-RL-43's existing guard, named in the report rather than edited here:
`tests/test_ingest_documents_v5_so_po_links.py::TestLinkFollowsBookPairing
::test_received_document_ref_move_changes_nothing`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation, Supplier
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from tests.test_oi_follow_book_chain import (
    ctx,  # noqa: F401 - pytest fixture, imported for reuse
    MARKER,
    _existing_link,
    _links_of,
    _ref,
    _seed_mirror,
    _seed_po_line,
    _seed_product,
    _seed_row,
    _seed_row_and_mirror,
    _seed_so_line,
    _seed_spo_line,
)
from tests._pg_fixture import unique_code
from tests.test_ingest_documents import (
    INGEST_PO,
    MARKER as DOC_MARKER,
    _po_line,
    _po_record,
    _ref as _doc_ref,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)

__all__ = ["ctx", "env"]


# ============================================================== AC-FB-30 / 31
class TestBookDisplacesOtherSalesOrderLine:
    def test_fb30_book_displaces_auto_link_of_other_so(self, ctx):
        """AC-FB-30: the book names document X for L (through its PO line). X is
        fully held by an AUTOMATIC link of a row on a DIFFERENT sales order line
        the book does not name for X - that link is removed with a note, the
        holder's link state is refreshed, and the row of L is linked."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_a = _ref("SOL")
        so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="81",
        )
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="81",
        )

        po, po_line = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, qty_ordered="81",
        )
        x = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_po_line_ref=po_line.source_ref, from_po_number=po.po_number,
            allocated_quantity=81,
        )

        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="81",
        )
        _pso_b, mirror_b, inquiry_b = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="81",
        )
        row_b = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_b.id, so_line_id=mirror_b.id,
            qty="81", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_b.id, document=x.spo_number,
            qty="81", spo_allocation_id=x.id, auto=True,
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_a.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        links_a = _links_of(db, row_a.id)
        links_b = _links_of(db, row_b.id)
        assert len(links_a) == 1, links_a
        assert links_a[0].spo_allocation_id == x.id
        assert Decimal(str(links_a[0].qty)) == Decimal("81")
        assert links_b == [], links_b

        db.refresh(row_b)
        assert row_b.state == INQUIRY_RAISED, row_b.state
        note = row_b.note or ""
        assert "AutoCount states" in note, note
        assert x.spo_number in note, note
        assert so_a.so_number in note, note

    def test_fb31_book_displaces_manual_link(self, ctx):
        """AC-FB-31: the same, but the holder's link is MANUAL (owner ruling 19
        Sep: "manual links follow too")."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_a = _ref("SOL")
        so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="81",
        )
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="81",
        )

        po, po_line = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, qty_ordered="81",
        )
        x = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_po_line_ref=po_line.source_ref, from_po_number=po.po_number,
            allocated_quantity=81,
        )

        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="81",
        )
        _pso_b, mirror_b, inquiry_b = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="81",
        )
        row_b = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_b.id, so_line_id=mirror_b.id,
            qty="81", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_b.id, document=x.spo_number,
            qty="81", spo_allocation_id=x.id, auto=False,
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_a.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        links_a = _links_of(db, row_a.id)
        links_b = _links_of(db, row_b.id)
        assert len(links_a) == 1, links_a
        assert links_a[0].spo_allocation_id == x.id
        assert links_b == [], links_b

        db.refresh(row_b)
        assert row_b.state == INQUIRY_RAISED, row_b.state
        note = row_b.note or ""
        assert "AutoCount states" in note, note
        assert x.spo_number in note, note
        assert so_a.so_number in note, note


# ============================================================== AC-FB-32
class TestReceivedHolderIsDisplacedToo:
    def test_fb32_received_holder_of_other_line_is_displaced(self, ctx):
        """AC-FB-32: the holder is a row of a DIFFERENT sales order line on a fully
        RECEIVED document (a closed PO line here, no SPO in between) - displaced
        like any other holder, with the note (D4: always follow)."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_a = _ref("SOL")
        so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="5",
        )
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="5",
        )

        po, po_line = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, qty_ordered="5", qty_received="5",
        )
        assert po_line.line_status == "closed"

        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="5",
        )
        _pso_b, mirror_b, inquiry_b = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="5",
        )
        row_b = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_b.id, so_line_id=mirror_b.id,
            qty="5", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_b.id, document=po.po_number,
            qty="5", po_line_id=po_line.id, auto=True,
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_a.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        links_a = _links_of(db, row_a.id)
        links_b = _links_of(db, row_b.id)
        assert len(links_a) == 1, links_a
        assert links_a[0].po_line_id == po_line.id
        assert links_b == [], links_b

        db.refresh(row_b)
        assert row_b.state == INQUIRY_RAISED, row_b.state
        note = row_b.note or ""
        assert "AutoCount states" in note, note
        assert po.po_number in note, note
        assert so_a.so_number in note, note


# ============================================================== AC-FB-6 (guard)
class TestSameLineNeverDisplaced:
    def test_fb6b_same_line_never_displaced(self, ctx):
        """Guard - a sibling row of the SAME sales order line holding X is never
        displaced (AC-FB-6). May already pass: this is the same shape as S1's own
        `test_fb6_same_line_sibling_holds_document`, restated here to prove it
        still holds once displacement lands, not touched by a different rule."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref_a = _ref("SOL")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="4",
        )
        x = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, allocated_quantity=2,
        )
        _pso, mirror, inquiry, sibling = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="2",
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=sibling.id, document=x.spo_number,
            qty="2", spo_allocation_id=x.id, auto=True,
        )
        new_row = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry.id, so_line_id=mirror.id, qty="2",
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(new_row.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        assert _links_of(db, new_row.id) == []
        assert len(_links_of(db, sibling.id)) == 1


# ============================================================== AC-FB-33
class TestBookNamesBothLines:
    def test_fb33_book_names_both_lines(self, ctx):
        """AC-FB-33: the book ALSO names X for the holder's own line (two shipping
        order lines, one per sales order line) - nothing is displaced, each row
        gets its own line."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref_a = _ref("SOL")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="3",
        )
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="3",
        )

        x1 = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, allocated_quantity=3,
        )
        x2 = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_b, allocated_quantity=3,
        )

        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="3",
        )
        _pso_b, mirror_b, inquiry_b = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="3",
        )
        row_b = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_b.id, so_line_id=mirror_b.id,
            qty="3", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_b.id, document=x2.spo_number,
            qty="3", spo_allocation_id=x2.id, auto=True,
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_a.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        links_a = _links_of(db, row_a.id)
        links_b = _links_of(db, row_b.id)
        assert len(links_a) == 1 and links_a[0].spo_allocation_id == x1.id, links_a
        assert len(links_b) == 1 and links_b[0].spo_allocation_id == x2.id, links_b


# ============================================================== AC-FB-30 (partial)
class TestPartialDisplacement:
    def test_fb30b_partial_displacement(self, ctx):
        """Partial quantity, UAC silent on the exact figure - written the way the
        rest of Group C reads (D3: "the book wins, always") and flagged in the
        report: X qty 10 named for L_A, row_A needs 4, row_B holds all 10 of X.
        Only 4 are taken from row_B; row_A gets 4."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref_a = _ref("SOL")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="4",
        )
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="10",
        )

        x = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, allocated_quantity=10,
        )

        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="4",
        )
        _pso_b, mirror_b, inquiry_b = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="10",
        )
        row_b = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_b.id, so_line_id=mirror_b.id,
            qty="10", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_b.id, document=x.spo_number,
            qty="10", spo_allocation_id=x.id, auto=True,
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_a.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        links_a = _links_of(db, row_a.id)
        links_b = _links_of(db, row_b.id)
        assert len(links_a) == 1 and links_a[0].spo_allocation_id == x.id, links_a
        assert Decimal(str(links_a[0].qty)) == Decimal("4"), links_a

        remaining_b = sum(
            Decimal(str(l.qty)) for l in links_b if l.spo_allocation_id == x.id
        )
        assert remaining_b == Decimal("6"), links_b

        db.refresh(row_b)
        assert row_b.state == INQUIRY_PARTLY_LINKED, row_b.state


# ============================================================== AC-FB-34 (D4)
def _seed_ref_only_so_line(env, *, so_number: str, product_id: str, source_ref: str):
    """Byte-for-byte copy of `test_ingest_documents_v5_so_po_links
    ._seed_ref_only_so_line` - fully delivered so the line's own outstanding
    claim never contests G7 dedication for the candidate row `_follow_one_move`
    places onto via `place_on_po_allocations`."""
    so, line = _seed_so_line_route(
        env, so_number=so_number, product_id=product_id, source_ref=source_ref,
    )
    line.qty_delivered = line.qty_ordered
    env.db.commit()
    return so, line


def _seed_so_line_route(env, *, so_number: str, product_id: str, source_ref: str, qty=10):
    so = SalesOrder(so_number=so_number, status="open", company_id=env.company_a)
    env.db.add(so)
    env.db.flush()
    line = SalesOrderLine(
        sales_order_id=so.id, product_id=product_id, qty_ordered=qty,
        source_ref=source_ref, company_id=env.company_a,
    )
    env.db.add(line)
    env.db.flush()
    env.db.commit()
    return so, line


def _mirror_row_route(env, *, core_line, product_id, qty: str, line_no: int = 1):
    """Byte-for-byte copy of `test_ingest_documents_v5_so_po_links._mirror_row`."""
    so_number = env.db.execute(
        text("SELECT so_number FROM sales_orders WHERE id = :id"),
        {"id": core_line.sales_order_id},
    ).scalar()
    pso = ProjectSalesOrder(
        id=str(uuid.uuid4()), company_id=env.company_a, project_id=None,
        so_id=core_line.sales_order_id, provisional_ref=f"{DOC_MARKER}-PSO-{uuid.uuid4().hex[:8]}",
        autocount_doc_no=so_number, status="adopted",
    )
    env.db.add(pso)
    env.db.flush()
    mirror_line = ProjectSalesOrderLine(
        id=str(uuid.uuid4()), company_id=env.company_a, project_sales_order_id=pso.id,
        line_no=line_no, core_sales_order_line_id=core_line.id, product_id=product_id,
        description=f"{DOC_MARKER} mirror", qty=Decimal(qty), uom="UNIT",
        unit_price=Decimal("10.00"), amount=Decimal("0"),
    )
    env.db.add(mirror_line)
    env.db.flush()
    inquiry = OrderInquiry(
        id=str(uuid.uuid4()), company_id=env.company_a, project_sales_order_id=pso.id,
    )
    env.db.add(inquiry)
    env.db.flush()
    row = OrderInquiryRow(
        id=str(uuid.uuid4()), company_id=env.company_a, order_inquiry_id=inquiry.id,
        so_line_id=mirror_line.id, qty=Decimal(qty), verb=IV_ORDER, state=INQUIRY_RAISED,
        ack_state=ACK_ACKNOWLEDGED,
    )
    env.db.add(row)
    env.db.flush()
    env.db.commit()
    return pso, mirror_line, inquiry, row


class TestBookMoveLiftsReceivedGuard:
    def test_fb34_move_follows_received_document(self, env):
        """AC-FB-34 (D4, retires AC-RL-43): a link on a FULLY RECEIVED PO line - a
        push that moves that line's `from_so_line_ref` to another sales order line
        moves the link too. Today `_is_target_received` makes this a no-op
        (AC-RL-43); D4 lifts it fully."""
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        ref_old = _doc_ref("SOLA")
        ref_new = _doc_ref("SOLB")
        _so_old, core_line_old = _seed_ref_only_so_line(
            env, so_number=f"{DOC_MARKER}-SOA-{uuid.uuid4().hex[:8]}", product_id=product_id,
            source_ref=ref_old,
        )
        _so_new, core_line_new = _seed_ref_only_so_line(
            env, so_number=f"{DOC_MARKER}-SOB-{uuid.uuid4().hex[:8]}", product_id=product_id,
            source_ref=ref_new,
        )

        _pso_old, _line_old, _inquiry_old, row_old = _mirror_row_route(
            env, core_line=core_line_old, product_id=product_id, qty="4",
        )
        _pso_new, _line_new, _inquiry_new, row_new = _mirror_row_route(
            env, core_line=core_line_new, product_id=product_id, qty="4",
        )

        line = _po_line(env, from_so_line_ref=ref_old, qty_ordered=4, qty_received=4)
        record = _po_record(env, lines=[line])
        res = env.post(INGEST_PO, [record])
        assert res.json()["records"][0]["outcome"] == "created", res.text
        header = env.header("purchase_orders", record["source_ref"])
        po_line = env.po_lines(header["id"])[0]
        assert po_line["line_status"] == "closed", "fixture must be genuinely received"

        env.db.add(OrderInquiryLink(
            id=str(uuid.uuid4()), company_id=env.company_a, row_id=row_old.id,
            po_line_id=po_line["id"], document=record["po_number"], qty=Decimal("4"), auto=True,
        ))
        env.db.commit()

        repush_line = _po_line(
            env, ref=line["source_ref"], from_so_line_ref=ref_new, qty_ordered=4, qty_received=4,
        )
        repush = dict(record, lines=[repush_line])
        res2 = env.post(INGEST_PO, [repush])
        assert res2.json()["records"][0]["outcome"] == "updated", res2.text

        env.db.expire_all()
        links_old = (
            env.db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row_old.id).all()
        )
        links_new = (
            env.db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row_new.id).all()
        )
        assert links_old == [], links_old
        row_old_db = (
            env.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_old.id).one()
        )
        note = row_old_db.note or ""
        assert "AutoCount moved" in note, note
        assert len(links_new) == 1, links_new
        assert str(links_new[0].po_line_id) == str(po_line["id"])


# ============================================================== AC-FB-30 (over-held)
class TestOverheldTargetDisplacement:
    def test_fb30c_overheld_target_is_freed_enough(self, ctx):
        """AC-FB-30, fix round finding 19 Sep: on the prod copy an SPO line of
        capacity 81 already carries TWO auto links of 81 each (a legacy over-link,
        162 held against 81) - both on rows of another sales order line. The book
        names it for row_A (need 81). Today `_displace_other_line_holders` stops
        the moment `freed >= amount_needed` (81), so it takes the FIRST 81-qty
        link and leaves the second sitting on the target - `pair_needs` then reads
        `capacity(81) - used(81) = 0` free and row_A gets nothing, exactly the
        symptom measured. The fix has to size the displacement off the shortfall
        against FREE capacity (which may already be negative), not off the book
        row's own need alone, so BOTH over-holding links come off: after the call
        the target holds no more than its own capacity, row_A has the document,
        and both displaced rows carry the note."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_a = _ref("SOL")
        so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="81",
        )
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="162",
        )

        x = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, allocated_quantity=81,
        )

        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="81",
        )

        _pso_b, mirror_b, inquiry_b = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="162",
        )
        row_b1 = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_b.id, so_line_id=mirror_b.id,
            qty="81", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        row_b2 = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_b.id, so_line_id=mirror_b.id,
            qty="81", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_b1.id, document=x.spo_number,
            qty="81", spo_allocation_id=x.id, auto=True,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_b2.id, document=x.spo_number,
            qty="81", spo_allocation_id=x.id, auto=True,
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_a.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        links_a = _links_of(db, row_a.id)
        assert len(links_a) == 1 and links_a[0].spo_allocation_id == x.id, links_a
        assert Decimal(str(links_a[0].qty)) == Decimal("81"), links_a

        all_links_on_x = (
            db.query(OrderInquiryLink)
            .filter(OrderInquiryLink.spo_allocation_id == x.id)
            .all()
        )
        total_on_x = sum(Decimal(str(l.qty)) for l in all_links_on_x)
        assert total_on_x <= Decimal("81"), all_links_on_x

        db.refresh(row_b1)
        db.refresh(row_b2)
        note_b1 = row_b1.note or ""
        note_b2 = row_b2.note or ""
        assert "AutoCount states" in note_b1, note_b1
        assert "AutoCount states" in note_b2, note_b2


# ============================================================== review round item 4 (B1)
class TestDisplacementReadsTheSameCapacityAsPairNeeds:
    def test_displace_po_line_netted_by_own_shipment(self, ctx):
        """Review round item 4 (security B1 / reviewer blocker 3): displacement
        must read the SAME capacity `pair_needs` reads (`_target_facts` +
        `_less_own_shipments`), never the PO line's RAW `qty_ordered`.

        PO line P (qty_ordered 10) names L_A. An SPO allocation S (6) is
        CHAINED off P (`from_po_line_ref`/`from_po_number`), so P's true
        remaining capacity is netted to 10 - 6 = 4. A row of ANOTHER sales
        order line holds 4 of P directly. Book row of L_A needs 10: it should
        end with 6 on S (free, no displacement needed) and 4 on P (displacing
        the other row's 4). `_displace_other_line_holders` reads P's capacity
        as the RAW 10, sees `capacity(10) - used(4) = 6` already free, and
        never displaces at all - so the book row ends short by 4 and the
        wrong-line holder keeps its 4 undisturbed.

        Invariant: total quantity displaced == quantity the book row gained
        from displaced capacity in this call (here, 4).
        """
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_a = _ref("SOL")
        so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="10",
        )
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="4",
        )

        po, po_line = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, qty_ordered="10",
        )
        s = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_po_line_ref=po_line.source_ref, from_po_number=po.po_number,
            allocated_quantity=6,
        )

        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="10",
        )
        _pso_b, mirror_b, inquiry_b = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="4",
        )
        row_b = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_b.id, so_line_id=mirror_b.id,
            qty="4", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_b.id, document=po.po_number,
            qty="4", po_line_id=po_line.id, auto=True,
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_a.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        links_a = _links_of(db, row_a.id)
        by_target_a = {(l.spo_allocation_id or l.po_line_id): Decimal(str(l.qty)) for l in links_a}
        gained_from_po_line = by_target_a.get(po_line.id, Decimal("0"))
        assert by_target_a.get(s.id) == Decimal("6"), links_a
        assert gained_from_po_line == Decimal("4"), links_a

        links_b = _links_of(db, row_b.id)
        displaced_from_b = Decimal("4") - sum(
            (Decimal(str(l.qty)) for l in links_b if l.po_line_id == po_line.id), Decimal("0")
        )
        assert displaced_from_b == gained_from_po_line, (displaced_from_b, gained_from_po_line)

    def test_no_strip_without_gain(self, ctx):
        """Review round item 4 (security S-B1): a target with NOTHING real left
        to hand out must never strip a holder anyway.

        PO line P (qty_ordered 10) names L1, fully shipped into allocation S
        (10, chained off P) - P's true remaining capacity is netted to 0. S is
        held by a row of L1 itself (protected, same core line as the book
        row). Row R2 of ANOTHER sales order line holds 10 directly on P. Book
        row R of L1 needs 10: since S is already fully (and legitimately)
        held by L1's own sibling, and P has nothing real left (0, once
        netted), R2's link must stay UNTOUCHED.

        `_displace_other_line_holders` reads P's capacity as the RAW 10, not
        the netted 0, computes `to_free = 10 - (10 - 10) = 10` and strips
        R2's link in full for a book row that can never actually be given
        anything from P - a stripped holder with zero gain.
        """
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_a = _ref("SOL")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="20",
        )
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="10",
        )

        po, po_line = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, qty_ordered="10",
        )
        s = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_po_line_ref=po_line.source_ref, from_po_number=po.po_number,
            allocated_quantity=10,
        )

        _pso_a, mirror_a, inquiry_a = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="20",
        )
        sibling_a = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_a.id, so_line_id=mirror_a.id,
            qty="10", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=sibling_a.id, document=s.spo_number,
            qty="10", spo_allocation_id=s.id, auto=True,
        )
        row_a = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_a.id, so_line_id=mirror_a.id,
            qty="10",
        )

        _pso_b, mirror_b, inquiry_b = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="10",
        )
        row_b = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_b.id, so_line_id=mirror_b.id,
            qty="10", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_b.id, document=po.po_number,
            qty="10", po_line_id=po_line.id, auto=True,
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_a.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        links_b = _links_of(db, row_b.id)
        assert len(links_b) == 1 and links_b[0].po_line_id == po_line.id, links_b
        assert Decimal(str(links_b[0].qty)) == Decimal("10"), links_b
        db.refresh(row_b)
        assert (row_b.note or "") == "", row_b.note

    def test_displace_with_a_protected_holder_is_atomic(self, ctx):
        """Review round item 4 (reviewer blocker 7): over-held target, one
        holder protected (same line as the book row), one not - either the
        book row gains what was displaced, or nothing is displaced. Never a
        stripped holder with zero gain.

        SPO S (capacity 10). holder_same (a sibling of the book row's OWN
        core line, protected) legitimately holds all 10. holder_other (a
        different line) illicitly ALSO holds 5 on top (over-held, 15 vs 10).
        Book row (a fresh row of the SAME core line as holder_same) needs 5.
        Since holder_same's 10 is protected and already saturates the target,
        there is nothing real to give the book row even after stripping
        holder_other - so holder_other must either keep its 5, or the book
        row must actually receive what was taken.
        """
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_same = _ref("SOL")
        _so_same, core_line_same = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_same, qty="15",
        )
        s = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_same, allocated_quantity=10,
        )

        _pso_same, mirror_same, inquiry_same = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_same, product_id=product.id, qty="15",
        )
        holder_same = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_same.id, so_line_id=mirror_same.id,
            qty="10", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=holder_same.id, document=s.spo_number,
            qty="10", spo_allocation_id=s.id, auto=True,
        )
        book_row = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_same.id, so_line_id=mirror_same.id,
            qty="5",
        )

        ref_other = _ref("SOL")
        _so_other, core_line_other = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_other, qty="5",
        )
        _pso_other, mirror_other, inquiry_other = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_other, product_id=product.id, qty="5",
        )
        holder_other = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_other.id, so_line_id=mirror_other.id,
            qty="5", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=holder_other.id, document=s.spo_number,
            qty="5", spo_allocation_id=s.id, auto=True,
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(book_row.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        links_book = _links_of(db, book_row.id)
        gained = sum((Decimal(str(l.qty)) for l in links_book if l.spo_allocation_id == s.id), Decimal("0"))

        links_other = _links_of(db, holder_other.id)
        remaining_other = sum(
            (Decimal(str(l.qty)) for l in links_other if l.spo_allocation_id == s.id), Decimal("0")
        )
        displaced_from_other = Decimal("5") - remaining_other

        assert displaced_from_other == Decimal("0") or gained == displaced_from_other, (
            gained, displaced_from_other,
        )


# ============================================================== review round item 5
class TestDisplacementDeterminismAndAmbiguity:
    def test_newest_link_displaced_first(self, ctx):
        """Review round item 5: with two displaceable holders and a partial
        need, the NEWEST link (`linked_at` desc, id tiebreak) is displaced
        first. `_displace_other_line_holders` reads its `links` query with NO
        `.order_by()` at all, so which holder loses the quantity is left to
        Postgres's own (unordered) scan, not the stated rule."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_a = _ref("SOL")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="5",
        )
        s = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, allocated_quantity=10,
        )

        ref_old = _ref("SOL")
        _so_old, core_line_old = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_old, qty="5",
        )
        _pso_old, mirror_old, inquiry_old = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_old, product_id=product.id, qty="5",
        )
        holder_old = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_old.id, so_line_id=mirror_old.id,
            qty="5", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )

        ref_new = _ref("SOL")
        _so_new, core_line_new = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_new, qty="5",
        )
        _pso_new, mirror_new, inquiry_new = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_new, product_id=product.id, qty="5",
        )
        holder_new = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_new.id, so_line_id=mirror_new.id,
            qty="5", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )

        now = datetime.utcnow()
        link_old = OrderInquiryLink(
            company_id=ctx.company_a, row_id=holder_old.id, spo_allocation_id=s.id,
            document=s.spo_number, qty=Decimal("5"), auto=True,
            linked_at=now - timedelta(days=2),
        )
        link_new = OrderInquiryLink(
            company_id=ctx.company_a, row_id=holder_new.id, spo_allocation_id=s.id,
            document=s.spo_number, qty=Decimal("5"), auto=True,
            linked_at=now - timedelta(days=1),
        )
        db.add_all([link_old, link_new])
        db.flush()

        _pso_a, _mirror_a, _inquiry_a, book_row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="5",
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(book_row.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        assert _links_of(db, book_row.id) != [], "book row must have gained the 5 it needed"
        assert _links_of(db, holder_old.id) != [], "the OLDER link must survive"
        assert _links_of(db, holder_new.id) == [], "the NEWEST link must be the one displaced"

    def test_book_names_target_ambiguity_refuses_to_guess(self, ctx):
        """Review round item 5: `_book_names_target_for_line`'s SPO-chained
        branch resolves the AC-FB-33 exemption via `PurchaseOrderLine.filter(
        PurchaseOrder.po_number == po_number, PurchaseOrderLine.source_ref ==
        po_line_ref).first()` - if TWO purchase order lines share
        `(po_number, source_ref)`, that `.first()` guesses one of them rather
        than refusing (treat as not named). A holder that is NOT actually
        exempt must still be displaced when the book names the target for
        the OTHER core line.
        """
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_book = _ref("SOL")
        _so_book, core_line_book = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_book, qty="5",
        )
        ref_holder = _ref("SOL")
        _so_holder, core_line_holder = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_holder, qty="5",
        )

        shared_source_ref = _ref("POL")
        shared_po_number = f"{MARKER}-PO-{uuid.uuid4().hex[:8]}"
        supplier = Supplier(
            company_id=ctx.company_a, supplier_code=unique_code(MARKER),
            supplier_name=f"{MARKER} supplier",
        )
        db.add(supplier)
        db.flush()
        po = PurchaseOrder(
            company_id=ctx.company_a, po_number=shared_po_number, supplier_id=supplier.id,
            status="open",
        )
        db.add(po)
        db.flush()
        # AMBIGUOUS: two live lines under the SAME po_number sharing the SAME
        # source_ref - one names the holder's own line (would wrongly exempt
        # it if `.first()` happens to return this row), the other does not.
        # Inserted in this order so an unordered `.first()` on a fresh table
        # is likely (not guaranteed) to hand back the matching row first.
        ambiguous_matching = PurchaseOrderLine(
            company_id=ctx.company_a, purchase_order_id=po.id, product_id=product.id,
            qty_ordered=5, qty_received=0, line_status="open",
            from_so_line_ref=ref_holder, source_ref=shared_source_ref,
        )
        ambiguous_other = PurchaseOrderLine(
            company_id=ctx.company_a, purchase_order_id=po.id, product_id=product.id,
            qty_ordered=5, qty_received=0, line_status="open",
            from_so_line_ref=None, source_ref=shared_source_ref,
        )
        db.add_all([ambiguous_matching, ambiguous_other])
        db.flush()

        s = SPOAllocation(
            company_id=ctx.company_a, spo_number=f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}",
            spo_line_number=1, product_id=product.id, allocated_quantity=5,
            quantity_received=0, line_status="open",
            from_po_line_ref=shared_source_ref, from_po_number=shared_po_number,
        )
        db.add(s)
        db.flush()

        _pso_holder, mirror_holder, inquiry_holder = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_holder, product_id=product.id, qty="5",
        )
        holder_row = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_holder.id, so_line_id=mirror_holder.id,
            qty="5", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=holder_row.id, document=s.spo_number,
            qty="5", spo_allocation_id=s.id, auto=True,
        )
        db.commit()

        # The book states S for `ref_book`'s line, not `ref_holder`'s - the
        # exemption's own inputs are `_seed_spo_line`-shaped: S's direct
        # `from_so_line_ref` is unset, forcing the po_line_ref/po_number branch.
        _pso_book, _mirror_book, _inquiry_book, book_row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_book, product_id=product.id, qty="5",
        )
        # Re-point S so the BOOK's own target resolution names it for
        # ref_book: chain it off a PO line of ref_book instead, distinct from
        # the ambiguous pair above (which exists purely to feed the
        # exemption check once `_displace_other_line_holders` is already
        # examining `holder_row`'s link on S).
        po2, po_line2 = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_book, qty_ordered="5",
        )
        s.from_po_line_ref = po_line2.source_ref
        s.from_po_number = po2.po_number
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(book_row.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        assert _links_of(db, holder_row.id) == [], (
            "ambiguous (po_number, source_ref) must refuse the exemption and "
            "still displace, not guess a match"
        )
        assert _links_of(db, book_row.id) != []


# ============================================================== review round item 7
class TestDisplacedRowsOfferedToCascadeOnceOnly:
    def test_book_step_entered_exactly_once_per_displacement(self, ctx, monkeypatch):
        """Review round item 7 (security S3 / reviewer blocker 8): a
        displaced holder is re-offered to the cascade ONCE, and that nested
        pass must not run the book step or displace again. Spied via a
        counting wrapper around `follow_book_for_rows` itself - a top-level
        call that displaces exactly one holder must enter this method
        exactly twice: once for the caller's own row, once for the nested
        `auto_place_for_products` call `follow_book_for_rows` makes for the
        displaced row."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_a = _ref("SOL")
        so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="5",
        )
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="5",
        )
        s = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, allocated_quantity=5,
        )
        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="5",
        )
        _pso_b, mirror_b, inquiry_b = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="5",
        )
        row_b = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_b.id, so_line_id=mirror_b.id,
            qty="5", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_b.id, document=s.spo_number,
            qty="5", spo_allocation_id=s.id, auto=True,
        )
        db.commit()

        svc = ProjectOrderInquiryService(db)
        calls = {"count": 0}
        original = ProjectOrderInquiryService.follow_book_for_rows

        def counting(self, *args, **kwargs):
            calls["count"] += 1
            return original(self, *args, **kwargs)

        monkeypatch.setattr(ProjectOrderInquiryService, "follow_book_for_rows", counting)

        svc.follow_book_for_rows(
            [str(row_a.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        assert calls["count"] == 2, calls

    def test_chained_displacement_two_levels_deep_never_recursion_errors(self, ctx):
        """Review round item 7: a CHAIN, not a simultaneous mutual pair - a
        true "both rows already fully linked to each other's wrong document"
        setup turns out to be untestable through this seam at all: `_unlinked
        _need(row)` reads remaining QUANTITY only, never whether the document
        held is the one the book actually names, so a row already fully
        linked (even to the wrong target) never even enters `needs` and the
        book step never looks at it (confirmed empirically: neither row in
        that shape moved at all). That is a real, separate gap from item 7's
        own ask, reported rather than bent into this test.

        What DOES exercise "a nested pass must not itself run away": row_A
        needs X, held (PARTIALLY, so it still has real unmet need) by
        row_C - a row whose OWN book-named target Z is, in turn, held by
        row_D. Displacing row_C off X is the FIRST-LEVEL displacement (offered
        back to the cascade once); the nested `follow_book_for_rows([row_C])`
        that runs for it discovers row_C's OWN shortfall against Z and
        displaces row_D - a SECOND-LEVEL displacement, itself offered to the
        cascade once more for row_D (whose own ref the book names nothing
        for, so that third level is a no-op). Two levels deep, self-
        terminating: no RecursionError, row_A ends on X, row_C ends on Z.
        """
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_a = _ref("SOL")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="5",
        )
        x = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, allocated_quantity=5,
        )

        ref_c = _ref("SOL")
        _so_c, core_line_c = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_c, qty="10",
        )
        z = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_c, allocated_quantity=10,
        )
        _pso_c, mirror_c, inquiry_c = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_c, product_id=product.id, qty="10",
        )
        row_c = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_c.id, so_line_id=mirror_c.id,
            qty="10", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        # row_c holds X (5, wrongly - not its own book target) - only PARTIAL
        # cover of its own qty (10), so its own unlinked need (5) is real and
        # the book still considers it once it is re-offered.
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_c.id, document=x.spo_number,
            qty="5", spo_allocation_id=x.id, auto=True,
        )

        ref_d = _ref("SOL")
        _so_d, core_line_d = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_d, qty="10",
        )
        _pso_d, mirror_d, inquiry_d = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_d, product_id=product.id, qty="10",
        )
        row_d = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_d.id, so_line_id=mirror_d.id,
            qty="10", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        # row_d holds Z (10, wrongly - Z is the book's target for ref_c, not
        # ref_d), fully covering row_d's own qty so it has no OWN book need.
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_d.id, document=z.spo_number,
            qty="10", spo_allocation_id=z.id, auto=True,
        )

        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="5",
        )
        db.commit()

        # Must not raise RecursionError - the assertion itself IS the guard;
        # a raised exception fails the test on its own.
        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_a.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        links_a = {l.spo_allocation_id for l in _links_of(db, row_a.id)}
        assert links_a == {x.id}, links_a

        links_c = {l.spo_allocation_id for l in _links_of(db, row_c.id)}
        assert z.id in links_c, links_c


# ============================================================== review round item 8
class TestLinkCacheInvalidatedOnPartialDisplacement:
    def test_cache_reflects_partial_displacement_on_same_instance(self, ctx):
        """Review round item 8: after a PARTIAL displacement (`link.qty`
        reduced rather than removed), the SAME service instance's own
        `_linked_by_target` memo must reflect the reduced quantity. The
        partial-reduce branch of `_displace_other_line_holders` (`link.qty =
        ... ; self.db.flush()`) calls no `_invalidate_link_cache()` at all -
        unlike the full-removal branch (`_remove_links`, which does) - so a
        cache already warmed on this instance before the call keeps
        answering with the PRE-displacement total.

        Direct unit test of `_displace_other_line_holders` alone (no
        re-pairing follow-on), so the target's total genuinely drops rather
        than being re-claimed by a re-paired book row on the same target -
        the only way to observe the stale total deterministically."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="10",
        )
        x = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            allocated_quantity=10,
        )
        _pso_b, _mirror_b, _inquiry_b, row_b = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="10",
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_b.id, document=x.spo_number,
            qty="10", spo_allocation_id=x.id, auto=True,
        )
        db.commit()

        svc = ProjectOrderInquiryService(db)
        _by_po_before, by_spo_before = svc._linked_by_target()
        assert by_spo_before.get(str(x.id)) == Decimal("10"), by_spo_before

        freed, displaced = svc._displace_other_line_holders(
            str(x.id), protect_core_line_id=str(uuid.uuid4()),
            amount_needed=Decimal("4"), note_so_number="TEST-SO",
        )
        assert freed == Decimal("4"), (freed, displaced)
        db.commit()

        actual_total = sum(
            (Decimal(str(l.qty)) for l in _links_of(db, row_b.id) if l.spo_allocation_id == x.id),
            Decimal("0"),
        )
        assert actual_total == Decimal("6"), actual_total

        _by_po_after, by_spo_after = svc._linked_by_target()
        assert by_spo_after.get(str(x.id)) == Decimal("6"), by_spo_after


# ============================================================== review round item 9
class TestDisplacementNoteNamesTheTrigger:
    def test_note_names_the_trigger_that_ran_the_displacement(self, ctx):
        """Review round item 9 (security S6): the displaced holder's note
        must name the TRIGGER as well as the document and SO number - today's
        fragment (`f"AutoCount states {document} is for {so_number}, {when}"`)
        never embeds it. Keeps the existing "AutoCount states" substring
        assertions (`test_fb30_book_displaces_auto_link_of_other_so` etc)
        valid; this only adds the trigger assertion on the same note."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_a = _ref("SOL")
        so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="5",
        )
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="5",
        )
        x = _seed_spo_line(
            db, company_id=ctx.company_a, product_id=product.id,
            from_so_line_ref=ref_a, allocated_quantity=5,
        )
        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="5",
        )
        _pso_b, mirror_b, inquiry_b = _seed_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="5",
        )
        row_b = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry_b.id, so_line_id=mirror_b.id,
            qty="5", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
        )
        _existing_link(
            db, company_id=ctx.company_a, row_id=row_b.id, document=x.spo_number,
            qty="5", spo_allocation_id=x.id, auto=True,
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_a.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        db.refresh(row_b)
        note = row_b.note or ""
        assert "AutoCount states" in note, note
        assert "autocount_ingest" in note, note
