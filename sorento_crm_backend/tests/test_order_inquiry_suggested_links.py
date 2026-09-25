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

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.models.base import company_scope
from app.models.company import Company
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    ACK_REJECTED,
    OrderInquiry,
    OrderInquiryRow,
    OrderInquirySuggestedLink,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOSupplyDecision,
)
from app.models.scm import OrderLinkClaim
from app.models.user import User
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.scm import order_link_service

from tests.test_oi_follow_book_chain import (
    ctx,  # noqa: F401 - pytest fixture, imported for reuse
    MARKER,
    _existing_link,
    _links_of,
    _ref,
    _seed_po_line,
    _seed_product,
    _seed_row,
    _seed_row_and_mirror,
    _seed_so_line,
    _seed_spo_line,
)
from tests.test_order_inquiry_handshake import (
    ACK_URL,
    LINK_NOW,
    LIST,
    PURCHASING,
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
        """Review round 2 Should fix 9: through the REAL route now,
        `POST /scm/purchase-orders/bulk-confirm` (`purchase_order_service.py:1265`),
        not `PurchaseOrderService.bulk_confirm` called directly - the same seam
        `test_order_inquiry_draft_links.py::test_a_purchase_order_confirm_links_an_
        awaiting_row` already exercises for today's (real-link) behaviour."""
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

        with _as_purchasing(world, permissions=PURCHASING + ["scm.reorder.run"]) as buyer:
            response = buyer.post(
                "/api/v1/scm/purchase-orders/bulk-confirm", json={"ids": [str(po.id)]},
            )
        assert response.status_code == 200, response.text
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
        not a raw string handed to `auto_place_for_products`.

        Review round 2 Should fix 9 named this door too, alongside `po_confirm`, for a
        route-level test (`POST /planning-changes/{batch_id}/apply`) rather than the
        service called directly. Kept at the service level here: reaching this exact
        branch through the real route needs a genuine planning-change scenario that
        leaves headroom for the cascade fill after `build_batch`, `set_row_decision`
        and `apply` - the harness `test_planning_changes.py` owns - and this seam
        already proves the fact the AC states (`decision_confirm` suggests, never
        links), which `_apply_one_order`'s own call site (line 4696, unchanged by
        this round) shows is the only caller of this method."""
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

    def test_ac_lt_14_two_cited_rows_still_net_against_each_other(self, ctx):
        """Review round 5 Blocking 1, probe (a). CS routinely writes the SAME document
        onto several rows' `cited_document` (one SPO answering several inquiries). A
        `cited` candidate is not an exception to AC-LT-14: at `7e18a786`, `_cascade_take`
        skipped `held_by_others` netting for any `cited` candidate, so two rows citing
        the same 8-unit PO line were both suggested their full 6 (12 total, over the
        line). The fix nets a `cited` candidate exactly like an uncited shared-pool one -
        this differs from `test_ac_lt_14_two_rows_never_suggested_the_same_units` only in
        that both rows also cite the document."""
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
        row_a.cited_document = po.po_number

        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="6"
        )
        _pso_b, _mirror_b, _inquiry_b, row_b = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="6"
        )
        row_b.delivery_date = date(2026, 7, 20)
        row_b.cited_document = po.po_number
        db.commit()

        ProjectOrderInquiryService(db).auto_place_for_products(
            None,
            actor_user_id=None,
            trigger="raise",
            row_ids=[str(row_a.id), str(row_b.id)],
        )

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
        assert total_on_line == Decimal("8"), (
            "two rows citing the same document are never offered its units twice"
        )

    def test_ac_lt_14_two_rows_of_one_so_never_suggested_more_than_the_line(self, ctx):
        """Review round 5 Blocking 1, probe (b). Two order-inquiry rows of the SAME
        sales order (two lines of one order needing the same product) both hold
        `own_so_claim` on the same PO line, because `_reserved_for_netting` always
        skips the row's OWN SO's claim - so at `7e18a786` neither row's `remaining` was
        ever reduced for the other, and the `own_so_claim` exemption in `_cascade_take`
        let both take the line's full 100 units (200 total). Unlike the two-different-SO
        case, there is no other SO's claim to net through `_reserved_for_netting` here,
        so the two rows must net against EACH OTHER's suggestion the same way two
        unclaimed shared-pool rows already do.

        Built by hand rather than through `_seed_row_and_mirror` twice: that helper
        mints a NEW `ProjectSalesOrder` per call, and `uq_projects_so_core_order`
        allows only one mirror per core sales order. Two lines of ONE order is exactly
        the ordinary shape this bug needs - one core `SalesOrder`, one
        `ProjectSalesOrder` naming it, two `ProjectSalesOrderLine`s, one `OrderInquiry`
        (`uq_project_order_inquiry_per_sales_order` allows only one per PSO), two
        `OrderInquiryRow`s. The claim's `so_line_id` needs a REAL core line - a claim
        whose so_line_id resolves to nothing reads `outstanding == 0` and `own_so_claim`
        stays false whatever the claim row itself says, which would silently turn this
        into a no-claim scenario and never exercise the exemption at all."""
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        po, po_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="100",
            header_status="active",
        )

        ref_a = _ref("SOL")
        so, core_line_a = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_a, qty="60"
        )
        so_number = so.so_number

        pso = ProjectSalesOrder(
            company_id=ctx.company_a,
            project_id=None,
            so_id=so.id,
            provisional_ref=f"{MARKER}-PSO-{uuid.uuid4().hex[:8]}",
            autocount_doc_no=so_number,
            status="adopted",
        )
        db.add(pso)
        db.flush()
        mirror_a = ProjectSalesOrderLine(
            company_id=ctx.company_a,
            project_sales_order_id=pso.id,
            line_no=1,
            core_sales_order_line_id=core_line_a.id,
            product_id=product.id,
            description=f"{MARKER} mirror a",
            qty=Decimal("60"),
            uom="UNIT",
            unit_price=Decimal("10.00"),
            amount=Decimal("0"),
        )
        mirror_b = ProjectSalesOrderLine(
            company_id=ctx.company_a,
            project_sales_order_id=pso.id,
            line_no=2,
            product_id=product.id,
            description=f"{MARKER} mirror b",
            qty=Decimal("60"),
            uom="UNIT",
            unit_price=Decimal("10.00"),
            amount=Decimal("0"),
        )
        db.add_all([mirror_a, mirror_b])
        db.flush()
        inquiry = OrderInquiry(company_id=ctx.company_a, project_sales_order_id=pso.id)
        db.add(inquiry)
        db.flush()

        row_a = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry.id, so_line_id=mirror_a.id, qty="60",
        )
        row_a.delivery_date = date(2026, 7, 1)
        row_b = _seed_row(
            db, company_id=ctx.company_a, inquiry_id=inquiry.id, so_line_id=mirror_b.id, qty="60",
        )
        row_b.delivery_date = date(2026, 7, 1)
        db.commit()

        so_number, item_code, core_line_id = ProjectOrderInquiryService(db).claim_identity(row_a)
        order_link_service.claim_placed_on_po(
            db,
            company_id=ctx.company_a,
            so_number=so_number,
            po_number=po.po_number,
            item_code=item_code,
            so_line_id=core_line_id,
            po_line_id=po_line.id,
            source=order_link_service.SOURCE_CRM_SUPPLY,
        )
        db.commit()

        ProjectOrderInquiryService(db).auto_place_for_products(
            None,
            actor_user_id=None,
            trigger="raise",
            row_ids=[str(row_a.id), str(row_b.id)],
        )

        total_on_line = sum(
            Decimal(str(s.qty))
            for s in (
                db.query(OrderInquirySuggestedLink)
                .filter(OrderInquirySuggestedLink.po_line_id == po_line.id)
                .all()
            )
        )
        assert total_on_line <= Decimal("100"), (
            "two rows of one SO both claim-dedicated to this line must split it, "
            "never double-take it"
        )


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
        """Review round 2 Blocking 4: through `mark_rows`, the REAL writer purchasing's
        own bulk action calls - not a hand-set `state` plus a bare `_drop_suggested_
        links` call, which passed even before `mark_rows` itself was fixed to call it."""
        row = self._setup(ctx)

        ProjectOrderInquiryService(ctx.db).mark_rows(
            [str(row.id)], state=INQUIRY_CANCELLED, actor_user_id=None,
        )

        assert _suggested_of(ctx.db, row.id) == []

    def test_ac_lt_18_an_actioned_row_drops_its_suggestions(self, ctx):
        """Review round 2 Blocking 4: through `mark_rows`, the real writer."""
        row = self._setup(ctx)

        ProjectOrderInquiryService(ctx.db).mark_rows(
            [str(row.id)], state=INQUIRY_ACTIONED, actor_user_id=None,
        )

        assert _suggested_of(ctx.db, row.id) == []

    def test_ac_lt_18_a_rejected_row_drops_its_suggestions(self, ctx):
        """Review round 2 Blocking 4: through `reject_row`, the real writer - already
        correct before this round (`_stamp_rejected` calls `_drop_suggested_links`
        itself), kept on the real seam rather than the hand-set state it replaced."""
        row = self._setup(ctx)

        ProjectOrderInquiryService(ctx.db).reject_row(
            str(row.id), reason="ZZT no longer needed", actor_user_id=None,
        )

        assert _suggested_of(ctx.db, row.id) == []

    def test_ac_lt_18_a_row_redirected_to_pool_drops_its_suggestions(self, ctx):
        row = self._setup(ctx)
        row.redirected_to_pool = True
        ctx.db.commit()

        ProjectOrderInquiryService(ctx.db)._drop_suggested_links([row])

        assert _suggested_of(ctx.db, row.id) == []


# ================================== Review round 2 Blocking 4: the supersede's own shape
class TestACLT18SupersedeFreesTheRetiredRowsRoom:
    """Review round 2 Blocking 4, the reviewer's own probe. `refresh_for_decision`'s
    supersede loop and `_retire_uncovered_rows` both set a row's `state` DIRECTLY -
    never through `refresh_link_state` - so before this round a row they cancelled
    went on holding capacity through its own stale suggestion for good
    (`_suggested_totals_by_target` never filtered by row state at all). Proven here
    through the REAL writer, `refresh_for_decision` itself (`test_order_inquiry_
    number.py`'s own pattern for exercising it directly, service level, real FK
    rows), not a hand-set state: row X is suggested a PO line's whole room, its own
    line then drops out of the next confirmation and X is retired the board
    re-confirm's own way (`_retire_uncovered_rows`); row Y, competing for the SAME
    PO line, must draw its own full need rather than whatever X's stale suggestion
    would otherwise still be holding.
    """

    def test_a_retired_rows_suggestion_frees_its_full_room_for_the_next_row(self, ctx):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        _po, po_line = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id,
            qty_ordered="8", header_status="active",
        )
        order = ProjectSalesOrder(
            id=str(uuid.uuid4()), company_id=ctx.company_a, project_id=None,
            provisional_ref=f"ZZT-PSO-{uuid.uuid4().hex[:8]}", status="draft",
        )
        db.add(order)
        db.flush()
        line_x = ProjectSalesOrderLine(
            id=str(uuid.uuid4()), company_id=ctx.company_a, project_sales_order_id=order.id,
            line_no=1, product_id=product.id, description="ZZT line X", qty=Decimal("8"),
            uom="UNIT", unit_price=Decimal("10"), amount=Decimal("80"),
            delivery_date=date(2026, 9, 1),
        )
        line_y = ProjectSalesOrderLine(
            id=str(uuid.uuid4()), company_id=ctx.company_a, project_sales_order_id=order.id,
            line_no=2, product_id=product.id, description="ZZT line Y", qty=Decimal("5"),
            uom="UNIT", unit_price=Decimal("10"), amount=Decimal("50"),
            delivery_date=date(2026, 9, 1),
        )
        db.add_all([line_x, line_y])
        db.flush()

        svc = ProjectOrderInquiryService(db)
        decision_1 = SOSupplyDecision(
            id=str(uuid.uuid4()), company_id=ctx.company_a, project_sales_order_id=order.id,
            revision_no=1, state="active", line_snapshots=[{"line_no": 1}],
            confirmed_by=None, confirmed_at=datetime.utcnow(),
        )
        db.add(decision_1)
        db.flush()
        svc.refresh_for_decision(
            order, decision_1,
            [{"line": line_x, "line_no": 1, "item_code": product.product_code,
              "buy_qty": Decimal("8"), "required_date": line_x.delivery_date,
              "stock_location": None}],
            actor_user_id=None,
        )
        db.commit()
        row_x = (
            db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.so_line_id == line_x.id,
                OrderInquiryRow.state == INQUIRY_RAISED,
            )
            .one()
        )
        # The raise-time cascade: neither line carries a book match, so row X is only
        # ever SUGGESTED - the same seam `ProjectSupplyService.confirm` itself calls
        # right after `refresh_for_decision` (`_draft_links_for_decision`).
        svc.auto_place_for_products(
            [product.id], actor_user_id=None, trigger="raise", include_awaiting=True,
        )
        db.commit()
        suggested_x = _suggested_of(db, row_x.id)
        assert {s.po_line_id for s in suggested_x} == {po_line.id}
        assert sum(Decimal(str(s.qty)) for s in suggested_x) == Decimal("8"), (
            "row X takes the PO line's whole room - nothing is left for anyone else"
        )

        # Revision 2 drops line X out of the confirmation (CS took it back out) and
        # raises line Y instead - `_retire_uncovered_rows`'s own shape. The prior
        # decision supersedes first, the same way `ProjectSupplyService.confirm`
        # itself does, or the ACTIVE-per-order constraint refuses the insert below.
        decision_1.state = "superseded"
        decision_1.superseded_at = datetime.utcnow()
        db.flush()
        decision_2 = SOSupplyDecision(
            id=str(uuid.uuid4()), company_id=ctx.company_a, project_sales_order_id=order.id,
            revision_no=2, state="active", line_snapshots=[{"line_no": 2}],
            confirmed_by=None, confirmed_at=datetime.utcnow(),
        )
        db.add(decision_2)
        db.flush()
        svc.refresh_for_decision(
            order, decision_2,
            [{"line": line_y, "line_no": 2, "item_code": product.product_code,
              "buy_qty": Decimal("5"), "required_date": line_y.delivery_date,
              "stock_location": None}],
            actor_user_id=None,
        )
        db.commit()
        db.refresh(row_x)
        assert row_x.state == INQUIRY_CANCELLED, "line X dropped out of the confirmation"
        assert _suggested_of(db, row_x.id) == [], (
            "the retired row's own suggestion is gone, not left to hold room forever"
        )

        row_y = (
            db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.so_line_id == line_y.id,
                OrderInquiryRow.state == INQUIRY_RAISED,
            )
            .one()
        )
        svc.auto_place_for_products(
            [product.id], actor_user_id=None, trigger="raise", include_awaiting=True,
        )
        db.commit()
        suggested_y = _suggested_of(db, row_y.id)
        assert {s.po_line_id for s in suggested_y} == {po_line.id}
        assert sum(Decimal(str(s.qty)) for s in suggested_y) == Decimal("5"), (
            "row Y draws its FULL need - X's retired suggestion no longer holds any of it"
        )


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

    def test_ac_lt_19_a_closed_target_with_no_alternative_line_is_dropped_not_kept(self, ctx):
        """Review round 2 Blocking 5 (reversal of the old B1 reason, dated 25 Sep
        2026): a closed line and NO other line to offer instead - the walk finds no
        candidate at all, and the honest outcome is that the stale suggestion goes,
        not that it lingers because nothing replaced it (issue #1215 point 3's own
        defect: a closed PO still offered for a row).

        Review round 4 Should fix 1: this is the likeliest stale case on prod - a
        line closes with nothing else for the product - and Link selected's own
        call (`trigger="worklist", redeal_drafts=True, include_awaiting=True`) must
        report it in `changed_rows`, not "nothing changed", the same reporting fix
        round 3's B1 made for the emptied-takes branch.
        """
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
        db.commit()

        result = service.auto_place_for_products(
            None,
            actor_user_id=None,
            trigger="worklist",
            row_ids=[str(row.id)],
            redeal_drafts=True,
            include_awaiting=True,
        )

        assert _suggested_of(db, row.id) == []
        assert result["changed_rows"] == 1

    def test_ac_lt_19_remaining_lines_cannot_cover_in_full_drops_the_stale_suggestion(
        self, ctx
    ):
        """Review round 3 Blocking 1: `_cascade_take` returns `[]` under the
        all-or-nothing rule (the remaining candidates cannot cover `need` in full)
        exactly as it does when every candidate is used up by other rows' own
        suggestions - the walk's `if not takes: continue` branch used to leave the
        row's stale suggestion on the now-closed line standing, the same issue #1215
        point 3 defect the two no-candidate branches above were already fixed for.
        Link selected must also report the change (`changed_rows`), not "nothing
        changed", when it drops a suggestion this way."""
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
        _po_small, small_line = _seed_po_line(
            db,
            company_id=ctx.company_a,
            product_id=product.id,
            qty_ordered="1",
            header_status="active",
        )
        db.commit()

        result = service.auto_place_for_products(
            None,
            actor_user_id=None,
            trigger="worklist",
            row_ids=[str(row.id)],
            redeal_drafts=True,
            include_awaiting=True,
        )

        assert _suggested_of(db, row.id) == []
        assert result["changed_rows"] == 1

    def test_ac_lt_19_a_candidate_pushed_outside_the_window_is_dropped_and_counted(
        self, ctx
    ):
        """Review round 5 Nit 1: `15ffd552` added `changed_suggestion_row_ids.add` on
        BOTH no-candidate branches, but only the "no candidate at all" branch
        (`test_ac_lt_19_a_closed_target_with_no_alternative_line_is_dropped_not_kept`)
        got a test. This pins the sibling branch: `_candidates_for_row` still returns
        the line (it never closed), but `_within_window` filters it out once the row's
        OWN delivery date moves far enough out that the line arrives more than a lead
        time early - the same held suggestion must be dropped and Link selected's own
        call must report it in `changed_rows`, not "nothing changed"."""
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
        line.expected_date = date(2026, 10, 1)
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="3"
        )
        row.delivery_date = date(2026, 10, 1)
        db.commit()

        service = ProjectOrderInquiryService(db)
        service.auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )
        before = _suggested_of(db, row.id)
        assert len(before) == 1
        assert before[0].po_line_id == line.id

        # A full lead time (90 days, no product-specific override seeded) plus more
        # between the line's own expected date and this row's delivery date - the
        # line now arrives far too early for this row.
        row.delivery_date = date(2027, 6, 1)
        db.commit()

        result = service.auto_place_for_products(
            None,
            actor_user_id=None,
            trigger="worklist",
            row_ids=[str(row.id)],
            redeal_drafts=True,
            include_awaiting=True,
        )

        assert _suggested_of(db, row.id) == []
        assert result["changed_rows"] == 1


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

    def test_ac_lt_22_a_scoped_user_never_reads_another_companys_suggested_link_through_a_route(
        self, api
    ):
        """Review round 2 Should fix 9: the sibling ORM-level test above proves the
        MODEL is company scoped; this one proves it through an actual route
        (`GET /order-inquiries`, the worklist `api`/`world` harness), which is what
        AC-LT-22 itself says ("through any route")."""
        client, world = api
        db = world.db
        foreign = Company(
            id=str(uuid.uuid4()), name="ZZT foreign company", code=f"ZFT{uuid.uuid4().hex[:6]}",
        )
        db.add(foreign)
        db.flush()
        foreign_product = _seed_product(db, company_id=foreign.id)
        ref = _ref("SOL")
        _foreign_so, foreign_core_line = _seed_so_line(
            db, company_id=foreign.id, product_id=foreign_product.id, source_ref=ref, qty="5",
        )
        foreign_po, foreign_line = _seed_po_line(
            db, company_id=foreign.id, product_id=foreign_product.id,
            qty_ordered="10", header_status="active",
        )
        _pso, _mirror, _inquiry, foreign_row = _seed_row_and_mirror(
            db, company_id=foreign.id, core_line=foreign_core_line,
            product_id=foreign_product.id, qty="5",
        )
        db.commit()
        db.add(
            OrderInquirySuggestedLink(
                id=str(uuid.uuid4()), company_id=foreign.id, row_id=foreign_row.id,
                po_line_id=foreign_line.id, document=foreign_po.po_number, qty=Decimal("5"),
            )
        )
        db.commit()

        row = _raise_one_row(api, qty="10")["row"]

        body = client.get(LIST, params={"limit": 200}).json()

        assert str(foreign_row.id) not in {item["id"] for item in body["data"]}, (
            "a scoped user must never even see the foreign row"
        )
        every_suggested_document = {
            entry["document"]
            for item in body["data"]
            for entry in (item.get("suggested_links") or [])
        }
        assert foreign_po.po_number not in every_suggested_document, (
            "the foreign company's suggested link must never reach this wire"
        )
        assert row.id in {item["id"] for item in body["data"]}, (
            "the world's own row still lists normally"
        )


# ==================================================== Review round 3 Should fix 1
class TestReviewRound3RetiredRowsNeverShowAStaleSuggestion:
    def test_a_row_cancelled_by_retire_inquiry_rows_reads_no_suggestion(self, ctx):
        """`_retire_inquiry_rows` (`planning_change_service.py`, a closed line's row)
        cancels a RAISED row without calling `_drop_suggested_links` itself -
        `_shift_links_off_retired_lines` right after it also skips any row with no
        REAL link (`if not links: continue`), so a row holding only a suggestion is
        never refreshed either. The reader `suggested_links_for_rows` used to have no
        state filter at all, so the Suggested cell would keep showing a document for
        a row the buyer has been told is cancelled. Fixed at the reader, the same
        `_open_for_buying_clauses` every other suggestion reader already applies -
        covers this writer and any future one without a drop call of its own."""
        from app.services.planning_change_service import _retire_inquiry_rows

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
        _pso, mirror_line, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="3"
        )
        db.commit()

        service = ProjectOrderInquiryService(db)
        service.auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )
        assert _suggested_of(db, row.id), "the suggestion has to exist for the test to mean anything"

        cancelled = _retire_inquiry_rows(
            db, str(mirror_line.id), "The line was closed by a planning change batch."
        )
        db.commit()
        assert cancelled == [str(row.id)]

        assert service.suggested_links_for_rows([str(row.id)]) == {}


# ==================================================== Review round 3 Should fix 2
class TestReviewRound3CapacityFilterHasItsOwnGuard:
    def test_a_stale_suggestion_left_on_a_cancelled_row_holds_no_capacity(self, ctx):
        """Review round 2's Blocking 4 fix (`_open_for_buying_clauses`, netted into
        `_suggested_totals_by_target` and so into every row's `held_by_others`) had
        no test that reached it directly: every AC-LT-18 test goes through a writer
        that ALSO calls `_drop_suggested_links`, so a mutation that deleted the
        filter entirely (`_open_for_buying_clauses` -> `()`) left all 100 tests in
        this suite green. Here the cancelled row's state is set directly, with no
        drop call at all - the exact K2a gap - so only the capacity FILTER, not a
        drop, stands between it and blocking a second row's own suggestion."""
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
        db.commit()

        service = ProjectOrderInquiryService(db)
        service.auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row_a.id)],
        )
        assert sum(
            Decimal(str(s.qty)) for s in _suggested_of(db, row_a.id)
        ) == Decimal("6")

        # Cancelled with NO drop call - the row's suggestion is left standing in the
        # store, exactly the gap the reader-level fix (Should fix 1) and this test
        # both target from the capacity side.
        row_a.state = INQUIRY_CANCELLED
        db.commit()

        ref_b = _ref("SOL")
        _so_b, core_line_b = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_b, qty="8"
        )
        _pso_b, _mirror_b, _inquiry_b, row_b = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line_b, product_id=product.id, qty="8"
        )
        db.commit()

        service.auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row_b.id)],
        )

        suggested_b = _suggested_of(db, row_b.id)
        assert sum(Decimal(str(s.qty)) for s in suggested_b) == Decimal("8"), (
            "row B draws the line's FULL room - a cancelled row's stale suggestion "
            "must never hold capacity against it"
        )
