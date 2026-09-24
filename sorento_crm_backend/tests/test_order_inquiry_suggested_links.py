"""S3 - the store, and the cascade writes suggested links, never real ones.

UAC: `documentation/plans/scm/oi-links-autocount-truth-24sep-acceptance-criteria.md`,
Group S3, AC-LT-10 to AC-LT-22.
Plan: `documentation/plans/scm/PLAN-oi-links-autocount-truth-24sep.md`, section 3.3/3.4.

RED at this slice, on purpose: `OrderInquirySuggestedLink` does not exist yet, so the
`app.models.project_so` import below is the FIRST thing every test in this file hits,
and every one of them fails at COLLECTION with the same `ImportError` - not a typo, not
a fixture bug, the missing model and table the coder builds next (migration, model,
`_write_suggested_links`, the trim-on-real-link, the drop-on-cover-or-state-change).
Once that lands this file becomes an ordinary suite.

Two harnesses, reused rather than reinvented, per the tester brief's "Testing seams":

* `ctx` / `_seed_*` from `tests.test_oi_follow_book_chain` - one blank Postgres schema
  per test (`tests/_pg_fixture.py::blank_session`), its own `company_a` (the seeded
  default company) and `company_b` (a fresh one), for every SERVICE-level test that
  calls `auto_place_for_products` / `follow_book_for_rows` / `place_on_po_allocations`
  / `refresh_link_state` directly.
* `api` / `world` / `_raise_one_row` / `_open_po_line` / `_as_purchasing` from
  `tests.test_order_inquiry_handshake` - the real (rolled-back) database, for AC-LT-11's
  doors that only exist as HTTP routes or as a distinct wrapping service method
  (`worklist`, `link_now`, `acknowledge`, `po_confirm`, `decision_confirm`), so each is
  exercised through its OWN real caller rather than `auto_place_for_products` called
  directly with a hand-picked trigger string.

Every AC seeds its own company, product, sales order line, PO line, SPO line and
inquiry row (UAC note at the top of Group S3) - nothing here borrows another test's row.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from app.models.base import company_scope
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    ACK_REJECTED,
    OrderInquiryRow,
    OrderInquirySuggestedLink,
)
from app.models.scm import OrderLinkClaim
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from tests.test_oi_follow_book_chain import (
    ctx,  # noqa: F401 - pytest fixture, imported for reuse
    _existing_link,
    _links_of,
    _ref,
    _seed_po_line,
    _seed_product,
    _seed_row_and_mirror,
    _seed_so_line,
    _seed_spo_line,
)
from tests.test_order_inquiry_handshake import (
    ACK_URL,
    LINK_NOW,
    LIST,
    _as_purchasing,
    _links_of as _hs_links_of,
    _open_po_line,
    _raise_one_row,
    _supplier as _hs_supplier,
    _uid as _hs_uid,
    api,  # noqa: F401 - pytest fixture, imported for reuse
    world,  # noqa: F401 - pytest fixture, imported for reuse
)

__all__ = ["ctx", "api", "world"]

AUTO_PLACE = f"{LIST}/auto-place"


# ---------------------------------------------------------------------------
# helpers this file owns
# ---------------------------------------------------------------------------


def _suggested_of(db, row_id):
    return (
        db.query(OrderInquirySuggestedLink)
        .filter(OrderInquirySuggestedLink.row_id == row_id)
        .order_by(OrderInquirySuggestedLink.suggested_at.asc())
        .all()
    )


def _seed_suggested(
    db,
    *,
    company_id,
    row_id,
    document,
    qty,
    po_line_id=None,
    spo_allocation_id=None,
    trigger="raise",
    suggested_at=None,
):
    row = OrderInquirySuggestedLink(
        company_id=company_id,
        row_id=row_id,
        po_line_id=po_line_id,
        spo_allocation_id=spo_allocation_id,
        document=document,
        qty=Decimal(str(qty)),
        trigger=trigger,
        suggested_at=suggested_at or datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row


# ============================================================== AC-LT-10
class TestACLT10RaiseSuggestsNeverLinks:
    def test_ac_lt_10_a_raise_time_cascade_suggests_never_links(self, ctx):
        """AC-LT-10: no book match, one open PO line - the walk writes ONE suggested
        link of the row's need, no `order_inquiry_links` row, the row stays `raised`,
        `po_ref`/`spo_ref` stay null."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="2"
        )
        _po, po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="10",
            header_status="active",
        )
        assert po_line.from_so_line_ref is None, "the book must have nothing to say here"
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="2"
        )
        db.commit()

        ProjectOrderInquiryService(db).auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )

        assert _links_of(db, row.id) == []
        suggested = _suggested_of(db, row.id)
        assert len(suggested) == 1
        assert suggested[0].po_line_id == po_line.id
        assert suggested[0].qty == Decimal("2")
        assert suggested[0].trigger == "raise"
        assert row.state == INQUIRY_RAISED
        assert row.po_ref is None
        assert row.spo_ref is None


# ============================================================== AC-LT-11
class TestACLT11EveryCascadeDoorSuggestsNeverLinks:
    """AC-LT-11: the same shape as AC-LT-10, proven at each of the seven doors through
    its OWN real caller - the route or wrapping service method that stamps the trigger
    today, never `auto_place_for_products` called directly with a made-up string."""

    def test_ac_lt_11_worklist_auto_link_all_suggests(self, api):
        _client, world = api
        row = _raise_one_row(api, qty="10")["row"]
        assert _hs_links_of(world, row) == [], "nothing to find yet - the PO opens after"
        _po, po_line = _open_po_line(world, qty=10)

        with _as_purchasing(world) as buyer:
            response = buyer.post(AUTO_PLACE, json={})
        assert response.status_code == 200, response.text
        world.db.commit()

        assert _hs_links_of(world, row) == []
        suggested = _suggested_of(world.db, row.id)
        assert len(suggested) == 1
        assert suggested[0].po_line_id == po_line.id
        assert suggested[0].trigger == "worklist"

    def test_ac_lt_11_link_now_suggests(self, api):
        _client, world = api
        row = _raise_one_row(api, qty="10")["row"]
        assert _hs_links_of(world, row) == []
        _po, po_line = _open_po_line(world, qty=10)

        with _as_purchasing(world) as buyer:
            response = buyer.post(LINK_NOW, json={})
        assert response.status_code == 200, response.text
        world.db.commit()

        assert _hs_links_of(world, row) == []
        suggested = _suggested_of(world.db, row.id)
        assert len(suggested) == 1
        assert suggested[0].po_line_id == po_line.id
        assert suggested[0].trigger == "link_now"

    def test_ac_lt_11_acknowledge_suggests(self, api):
        _client, world = api
        row = _raise_one_row(api, qty="10")["row"]
        assert _hs_links_of(world, row) == []
        _po, po_line = _open_po_line(world, qty=10)

        with _as_purchasing(world) as buyer:
            response = buyer.post(ACK_URL, json={"row_ids": [str(row.id)]})
        assert response.status_code == 200, response.text
        world.db.commit()

        assert _hs_links_of(world, row) == []
        suggested = _suggested_of(world.db, row.id)
        assert len(suggested) == 1
        assert suggested[0].po_line_id == po_line.id
        assert suggested[0].trigger == "acknowledge"

    def test_ac_lt_11_purchase_order_confirm_suggests(self, api):
        """`PurchaseOrderService.bulk_confirm` is the real `po_confirm` caller
        (`purchase_order_service.py:1265`), the same seam
        `test_order_inquiry_draft_links.py::test_a_purchase_order_confirm_links_an_
        awaiting_row` already exercises for today's (real-link) behaviour."""
        from app.services.scm.purchase_order_service import PurchaseOrderService

        _client, world = api
        row = _raise_one_row(api, qty="10")["row"]
        assert _hs_links_of(world, row) == []

        supplier = _hs_supplier(world)
        po = PurchaseOrder(
            id=_hs_uid(),
            company_id=world.company_id,
            po_number=f"ZZT-DRAFT-{_hs_uid()[:8]}",
            supplier_id=supplier.id,
            status="draft_recommendation",
        )
        world.db.add(po)
        world.db.flush()
        po_line = PurchaseOrderLine(
            id=_hs_uid(),
            company_id=world.company_id,
            purchase_order_id=po.id,
            product_id=world.product.id,
            warehouse_id=world.warehouse.id,
            qty_ordered=Decimal("50"),
            qty_received=Decimal("0"),
            expected_date=date(2026, 8, 10),
            line_status="open",
        )
        world.db.add(po_line)
        world.db.commit()

        PurchaseOrderService(world.db).bulk_confirm([str(po.id)], actor=world.buyer)
        world.db.expire_all()

        row = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
        assert _hs_links_of(world, row) == []
        suggested = _suggested_of(world.db, row.id)
        assert len(suggested) == 1
        assert suggested[0].po_line_id == po_line.id
        assert suggested[0].trigger == "po_confirm"

    def test_ac_lt_11_decision_confirm_suggests(self, api):
        """`ProjectSupplyService.auto_place_for_confirmed_products` is the real
        `decision_confirm` caller - the planning-change apply's own deferred pass
        (`planning_change_service.py:4696`), a distinct method wrapping the trigger,
        not a raw string handed to `auto_place_for_products`."""
        from app.services.project_supply_service import ProjectSupplyService

        _client, world = api
        row = _raise_one_row(api, qty="10")["row"]
        assert _hs_links_of(world, row) == []
        _po, po_line = _open_po_line(world, qty=10)

        ProjectSupplyService(world.db).auto_place_for_confirmed_products(
            [str(world.product.id)], actor_user_id=world.buyer,
        )
        world.db.commit()

        assert _hs_links_of(world, row) == []
        suggested = _suggested_of(world.db, row.id)
        assert len(suggested) == 1
        assert suggested[0].po_line_id == po_line.id
        assert suggested[0].trigger == "decision_confirm"

    def test_ac_lt_11_the_displaced_holder_re_offer_suggests_never_links(self, ctx):
        """The seventh door: `follow_book_for_rows`'s own D3 displacement re-offers the
        holder it just took a document from to `auto_place_for_products` under the SAME
        trigger (`:2724`). Row Z holds a MANUAL real link on the line the book now names
        for row Y - displacement takes it exactly like an automatic one (owner ruling
        19 Sep) - and the re-offer must give Z a SUGGESTED link on the next open line,
        never hand it back a real one."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_y = _ref("SOL")
        _so_y, core_line_y = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_y, qty="10"
        )
        po_a, line_a = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_so_line_ref=ref_y,
            qty_ordered="10",
            header_status="active",
        )

        ref_z = _ref("SOL")
        _so_z, core_line_z = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_z, qty="10"
        )
        _pso_z, _mirror_z, _inquiry_z, row_z = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_z, product_id=product.id, qty="10"
        )
        _existing_link(
            db,
            company_id=ctx.company_a,
            row_id=row_z.id,
            document=po_a.po_number,
            qty="10",
            po_line_id=line_a.id,
            auto=False,
        )

        _po_other, line_other = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="10",
            header_status="active",
        )

        _pso_y, _mirror_y, _inquiry_y, row_y = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_y, product_id=product.id, qty="10"
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_y.id)], trigger="worklist", company_id=ctx.company_a, actor_user_id=None,
        )

        y_links = _links_of(db, row_y.id)
        assert [l.po_line_id for l in y_links] == [line_a.id]
        assert y_links[0].auto is True

        assert _links_of(db, row_z.id) == [], "the manual real link was displaced"
        suggested_z = _suggested_of(db, row_z.id)
        assert len(suggested_z) == 1
        assert suggested_z[0].po_line_id == line_other.id
        assert suggested_z[0].qty == Decimal("10")
        assert suggested_z[0].trigger == "worklist"


# ============================================================== AC-LT-12/13
class TestACLT12BookStepStillWritesARealLink:
    def test_ac_lt_12_the_book_step_still_links_for_real(self, ctx):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="4"
        )
        _po, po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_so_line_ref=ref,
            qty_ordered="4",
            header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="4"
        )
        db.commit()

        ProjectOrderInquiryService(db).auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )

        links = _links_of(db, row.id)
        assert len(links) == 1
        assert links[0].po_line_id == po_line.id
        assert links[0].auto is True
        assert _suggested_of(db, row.id) == []
        assert row.state == INQUIRY_PLACED


class TestACLT13BookLinkRealWhateverTheLineState:
    def _run(self, ctx, *, qty_received):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="4"
        )
        _po, po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_so_line_ref=ref,
            qty_ordered="4",
            qty_received=qty_received,
            header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="4"
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        links = _links_of(db, row.id)
        assert len(links) == 1
        assert links[0].auto is True
        assert links[0].po_line_id == po_line.id
        assert _suggested_of(db, row.id) == []
        return po_line

    def test_ac_lt_13_an_open_book_named_line_links_for_real(self, ctx):
        po_line = self._run(ctx, qty_received="0")
        assert po_line.line_status == "open"

    def test_ac_lt_13_a_received_and_closed_book_named_line_still_links_for_real(self, ctx):
        """G10 (owner ruling 18 Sep): AutoCount named it - `received` already tells
        purchasing the goods have landed, the link stays real."""
        po_line = self._run(ctx, qty_received="4")
        assert po_line.line_status == "closed"


# ============================================================== AC-LT-14 / G2
class TestACLT14CapacityIsDealtInPriorityOrder:
    def test_ac_lt_14_two_rows_never_suggested_the_same_units(self, ctx):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        _po, po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="8",
            header_status="active",
        )

        ref_a = _ref("SOL")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="6"
        )
        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="6"
        )
        row_a.delivery_date = date(2026, 7, 1)

        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="6"
        )
        _pso_b, _mirror_b, _inquiry_b, row_b = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="6"
        )
        row_b.delivery_date = date(2026, 7, 20)
        db.commit()

        ProjectOrderInquiryService(db).auto_place_for_products(
            None,
            actor_user_id=None,
            trigger="raise",
            row_ids=[str(row_a.id), str(row_b.id)],
        )

        assert _links_of(db, row_a.id) == []
        assert _links_of(db, row_b.id) == []
        suggested_a = _suggested_of(db, row_a.id)
        suggested_b = _suggested_of(db, row_b.id)
        assert sum(Decimal(str(s.qty)) for s in suggested_a) == Decimal("6")
        assert sum(Decimal(str(s.qty)) for s in suggested_b) == Decimal("2")
        total_on_line = sum(
            Decimal(str(s.qty))
            for s in (
                db.query(OrderInquirySuggestedLink)
                .filter(OrderInquirySuggestedLink.po_line_id == po_line.id)
                .all()
            )
        )
        assert total_on_line == Decimal("8"), "never exceeds qty_ordered - qty_received"


# ============================================================== AC-LT-15 / G2
class TestACLT15ARealLinkTrimsSuggestedLinksFirst:
    def test_ac_lt_15_a_real_link_trims_the_lowest_priority_suggestion_first(self, ctx):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        po, po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="8",
            header_status="active",
        )

        ref_a = _ref("SOL")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="6"
        )
        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="6"
        )
        row_a.delivery_date = date(2026, 7, 1)

        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="2"
        )
        _pso_b, _mirror_b, _inquiry_b, row_b = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="2"
        )
        row_b.delivery_date = date(2026, 7, 20)

        ref_c = _ref("SOL")
        _so_c, core_line_c = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_c, qty="5"
        )
        _pso_c, _mirror_c, _inquiry_c, row_c = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_c, product_id=product.id, qty="5"
        )
        db.flush()

        _seed_suggested(
            db, company_id=ctx.company_a, row_id=row_a.id, po_line_id=po_line.id,
            document=po.po_number, qty="6",
            suggested_at=datetime.utcnow() - timedelta(hours=2),
        )
        _seed_suggested(
            db, company_id=ctx.company_a, row_id=row_b.id, po_line_id=po_line.id,
            document=po.po_number, qty="2",
            suggested_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.commit()

        ProjectOrderInquiryService(db).place_on_po_allocations(
            str(row_c.id), [{"po_line_id": str(po_line.id), "qty": "5"}], actor_user_id=None,
        )

        assert _suggested_of(db, row_b.id) == [], "B (later, lower priority) goes first"
        remaining_a = _suggested_of(db, row_a.id)
        assert len(remaining_a) == 1
        assert remaining_a[0].qty == Decimal("3"), "A keeps only what is left"
        c_links = _links_of(db, row_c.id)
        assert len(c_links) == 1
        assert c_links[0].qty == Decimal("5"), "the real link was never refused"

    def test_ac_lt_15_a_book_named_real_link_trims_suggestions_too(self, ctx):
        """AC-LT-15 says "book or manual" - fix round, 24 Sep: `_write_link` is the
        ONE choke point every real-link writer reaches (`place_on_po_allocations`'s
        own loop AND `follow_book_for_rows`'s), so a BOOK-named real link trims the
        same way the test above proves a manual one does. The earlier build only
        trimmed from `place_on_po_allocations`, which the book never calls - this is
        the exact same fixture shape, the real link just arrives through the book."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)

        ref_c = _ref("SOL")
        _so_c, core_line_c = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_c, qty="5"
        )
        po, po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            from_so_line_ref=ref_c,
            qty_ordered="8",
            header_status="active",
        )

        ref_a = _ref("SOL")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="6"
        )
        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product.id, qty="6"
        )
        row_a.delivery_date = date(2026, 7, 1)

        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="2"
        )
        _pso_b, _mirror_b, _inquiry_b, row_b = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="2"
        )
        row_b.delivery_date = date(2026, 7, 20)

        _pso_c, _mirror_c, _inquiry_c, row_c = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_c, product_id=product.id, qty="5"
        )
        db.flush()

        _seed_suggested(
            db, company_id=ctx.company_a, row_id=row_a.id, po_line_id=po_line.id,
            document=po.po_number, qty="6",
            suggested_at=datetime.utcnow() - timedelta(hours=2),
        )
        _seed_suggested(
            db, company_id=ctx.company_a, row_id=row_b.id, po_line_id=po_line.id,
            document=po.po_number, qty="2",
            suggested_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.commit()

        ProjectOrderInquiryService(db).follow_book_for_rows(
            [str(row_c.id)], trigger="autocount_ingest", company_id=ctx.company_a,
            actor_user_id=None,
        )

        c_links = _links_of(db, row_c.id)
        assert len(c_links) == 1
        assert c_links[0].po_line_id == po_line.id
        assert c_links[0].qty == Decimal("5"), "the book's own real link was never refused"

        assert _suggested_of(db, row_b.id) == [], "B (later, lower priority) goes first"
        remaining_a = _suggested_of(db, row_a.id)
        assert len(remaining_a) == 1
        assert remaining_a[0].qty == Decimal("3"), "A keeps only what is left"


# ============================================================== AC-LT-16
class TestACLT16IdempotentReplace:
    def test_ac_lt_16_a_repeated_pass_leaves_an_unchanged_answer_alone(self, ctx):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="4"
        )
        _po, _po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="10",
            header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="4"
        )
        db.commit()

        service = ProjectOrderInquiryService(db)
        service.auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )
        first = _suggested_of(db, row.id)
        assert len(first) == 1
        first_id, first_suggested_at = first[0].id, first[0].suggested_at

        service.auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )
        second = _suggested_of(db, row.id)

        assert len(second) == 1
        assert second[0].id == first_id, "not deleted and rewritten for an identical answer"
        assert second[0].suggested_at == first_suggested_at

    def test_ac_lt_16_a_changed_answer_replaces_the_old_suggestion(self, ctx):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="4"
        )
        _po_far, far_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="10",
            header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="4"
        )
        db.commit()

        service = ProjectOrderInquiryService(db)
        service.auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )
        before = _suggested_of(db, row.id)
        assert len(before) == 1
        assert before[0].po_line_id == far_line.id

        far_line.line_status = "closed"
        _po_near, near_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="10",
            header_status="active",
        )
        db.commit()

        service.auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )
        after = _suggested_of(db, row.id)

        assert len(after) == 1
        assert after[0].po_line_id == near_line.id
        assert after[0].id != before[0].id


# ============================================================== AC-LT-17
class TestACLT17FullRealCoverageDropsSuggestions:
    def test_ac_lt_17_a_row_fully_covered_by_a_real_link_drops_its_suggestions(self, ctx):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="5"
        )
        _po_guess, _guess_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="10",
            header_status="active",
        )
        _po_real, real_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="10",
            header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="5"
        )
        db.commit()

        service = ProjectOrderInquiryService(db)
        service.auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )
        assert len(_suggested_of(db, row.id)) == 1, "the guess has to exist to mean anything"

        service.place_on_po_allocations(
            str(row.id), [{"po_line_id": str(real_line.id), "qty": "5"}], actor_user_id=None,
        )

        assert _suggested_of(db, row.id) == []
        assert row.state == INQUIRY_PLACED


# ============================================================== AC-LT-18
class TestACLT18ARowMovedOffActiveDropsSuggestions:
    def _setup(self, ctx):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="3"
        )
        po, po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="10",
            header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="3"
        )
        db.commit()
        _seed_suggested(
            db, company_id=ctx.company_a, row_id=row.id, po_line_id=po_line.id,
            document=po.po_number, qty="3",
        )
        db.commit()
        return row

    def test_ac_lt_18_a_cancelled_row_drops_its_suggestions(self, ctx):
        row = self._setup(ctx)
        row.state = INQUIRY_CANCELLED
        ctx.db.commit()

        ProjectOrderInquiryService(ctx.db)._drop_suggested_links([row])

        assert _suggested_of(ctx.db, row.id) == []

    def test_ac_lt_18_an_actioned_row_drops_its_suggestions(self, ctx):
        row = self._setup(ctx)
        row.state = INQUIRY_ACTIONED
        ctx.db.commit()

        ProjectOrderInquiryService(ctx.db)._drop_suggested_links([row])

        assert _suggested_of(ctx.db, row.id) == []

    def test_ac_lt_18_a_rejected_row_drops_its_suggestions(self, ctx):
        row = self._setup(ctx)
        row.ack_state = ACK_REJECTED
        ctx.db.commit()

        ProjectOrderInquiryService(ctx.db)._drop_suggested_links([row])

        assert _suggested_of(ctx.db, row.id) == []

    def test_ac_lt_18_a_row_redirected_to_pool_drops_its_suggestions(self, ctx):
        row = self._setup(ctx)
        row.redirected_to_pool = True
        ctx.db.commit()

        ProjectOrderInquiryService(ctx.db)._drop_suggested_links([row])

        assert _suggested_of(ctx.db, row.id) == []


# ============================================================== AC-LT-19
class TestACLT19TargetGoesAwayDropsAndReplaces:
    def test_ac_lt_19_a_closed_target_is_dropped_and_replaced_by_another_line(self, ctx):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="3"
        )
        _po, line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="10",
            header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="3"
        )
        db.commit()

        service = ProjectOrderInquiryService(db)
        service.auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )
        before = _suggested_of(db, row.id)
        assert len(before) == 1
        assert before[0].po_line_id == line.id

        line.line_status = "closed"
        _po_open, open_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="10",
            header_status="active",
        )
        db.commit()

        service.auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )
        after = _suggested_of(db, row.id)

        assert len(after) == 1
        assert after[0].po_line_id == open_line.id
        assert after[0].id != before[0].id


# ============================================================== AC-LT-20 / G2
class TestACLT20NoClaimForASuggestion:
    def test_ac_lt_20_a_suggested_link_writes_no_claim_and_frees_none_on_delete(self, ctx):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="3"
        )
        po, _po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="10",
            header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="3"
        )
        db.commit()

        ProjectOrderInquiryService(db).auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )
        suggested = _suggested_of(db, row.id)
        assert len(suggested) == 1

        claims_before = (
            db.query(OrderLinkClaim)
            .filter(OrderLinkClaim.po_number == po.po_number)
            .count()
        )
        assert claims_before == 0

        db.delete(suggested[0])
        db.commit()

        claims_after = (
            db.query(OrderLinkClaim)
            .filter(OrderLinkClaim.po_number == po.po_number)
            .count()
        )
        assert claims_after == 0


# ============================================================== AC-LT-21
class TestACLT21OnlySuggestedReadsRaised:
    def test_ac_lt_21_a_row_with_only_a_suggestion_reads_raised(self, ctx):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="3"
        )
        po, po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="10",
            header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="3"
        )
        db.commit()
        _seed_suggested(
            db, company_id=ctx.company_a, row_id=row.id, po_line_id=po_line.id,
            document=po.po_number, qty="3",
        )
        db.commit()

        ProjectOrderInquiryService(db).refresh_link_state([row])

        assert row.state == INQUIRY_RAISED


# ============================================================== AC-LT-22
class TestACLT22CompanyScoped:
    def test_ac_lt_22_company_b_never_reads_company_as_suggested_links(self, ctx):
        db = ctx.db
        product_a = _seed_product(db, company_id=ctx.company_a)
        ref_a = _ref("SOL")
        _so_a, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product_a.id, source_ref=ref_a, qty="3"
        )
        po_a, line_a = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product_a.id,
            qty_ordered="10",
            header_status="active",
        )
        _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_a, product_id=product_a.id, qty="3"
        )
        db.commit()
        suggestion_a = _seed_suggested(
            db, company_id=ctx.company_a, row_id=row_a.id, po_line_id=line_a.id,
            document=po_a.po_number, qty="3",
        )

        product_b = _seed_product(db, company_id=ctx.company_b)
        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_b, product_id=product_b.id, source_ref=ref_b, qty="4"
        )
        po_b, line_b = _seed_po_line(
            db,
            company_id=ctx.company_b,
            product_id=product_b.id,
            qty_ordered="10",
            header_status="active",
        )
        _pso_b, _mirror_b, _inquiry_b, row_b = _seed_row_and_mirror(
            db, company_id=ctx.company_b, core_line=core_line_b, product_id=product_b.id, qty="4"
        )
        db.commit()
        suggestion_b = _seed_suggested(
            db, company_id=ctx.company_b, row_id=row_b.id, po_line_id=line_b.id,
            document=po_b.po_number, qty="4",
        )
        db.commit()

        with company_scope(db, frozenset({ctx.company_b})):
            visible_b = db.query(OrderInquirySuggestedLink).all()
        assert {row.id for row in visible_b} == {suggestion_b.id}

        with company_scope(db, frozenset({ctx.company_a})):
            visible_a = db.query(OrderInquirySuggestedLink).all()
        assert {row.id for row in visible_a} == {suggestion_a.id}
