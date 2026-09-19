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
from decimal import Decimal

from sqlalchemy import text

from app.models.order import SalesOrder, SalesOrderLine
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
