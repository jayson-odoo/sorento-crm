"""S4 - readers, Link selected, and the pages wired to the real API.

UAC: `documentation/plans/scm/oi-links-autocount-truth-24sep-acceptance-criteria.md`,
Group S4, AC-LT-30 to AC-LT-39 (AC-LT-40 is FE, a frontend pass covers it separately -
not in this file).
Plan: `documentation/plans/scm/PLAN-oi-links-autocount-truth-24sep.md`, sections 3.5-3.7.

Kept SEPARATE from `test_order_inquiry_suggested_links.py` (S3's own file) so the two
slices stay traceable, even though several helpers are reused wholesale from it and from
its own two harnesses:

* `ctx` / the `_seed_*` helpers from `tests.test_oi_follow_book_chain` - one blank
  Postgres schema per test, for every test that does not need `scm.committed_v` (a view
  the blank schema does not carry) or an HTTP round trip.
* `api` / `world` / `_as_purchasing` from `tests.test_order_inquiry_handshake` - the real
  (rolled-back) database, for `scm.committed_v` and for every route seam
  (`GET /order-inquiries`, the OI detail route, the PO/SPO lightboxes, `auto-place`, the
  new `link-suggested`). Rows are seeded DIRECTLY against `world.db` with the same
  `_seed_*` helpers `ctx`-based tests use (never through the board-confirm HTTP flow,
  whose own raise-time cascade would race the deterministic setup these tests need) -
  `world.db` is an ordinary SQLAlchemy session the seed helpers do not care where it
  came from.
* `_seed_suggested` / `_suggested_of` from `test_order_inquiry_suggested_links.py`
  (S3's own file) - writing a suggested link directly, and reading a row's own suggested
  links back, without going through a cascade pass.

Every AC seeds its own company, product, sales order line, PO line and inquiry row
(UAC note at the top of Group S3, carried into S4) - nothing here borrows another
test's row, and this suite runs on Postgres only, never sqlite.

RED-vs-PIN, read this before treating a green result as a bug in the test:

* AC-LT-33 through AC-LT-37 and AC-LT-39 exercise SURFACE THIS SLICE ADDS (the
  `suggested_links` wire field, the `link-suggested` route, `auto-place`'s new counts,
  the export's Suggested column) - every one of these is expected RED today, failing on
  a missing field, a missing route (404 instead of 200/403), or a missing heading.
* AC-LT-30, AC-LT-31, AC-LT-32 and AC-LT-38 PIN existing readers that the plan says get
  NO code change in this lane (`scm.committed_v`, `StockDebtService._holds`, the
  worklist summary's cards, the SCM sales-order detail, the fulfilment board's
  `documents`, the PO page's placements, the handover email context) - S3 already made
  every one of them true by construction (they only ever read `order_inquiry_links`,
  never `order_inquiry_suggested_links`), so these are expected GREEN already. That is
  not a mistake in the test: it is the pin the UAC asks for.
"""
from __future__ import annotations

import io
import json
from datetime import date
from decimal import Decimal

from app.models.project_so import (
    INQUIRY_RAISED,
    OrderInquiryLink,
    OrderInquiryRow,
    OrderInquirySuggestedLink,
)
from app.services.project_order_inquiry_service import (
    _HANDOVER_PENDING_KEY,
    ProjectOrderInquiryService,
    _build_handover_context,
)

from tests.test_oi_follow_book_chain import (
    ctx,  # noqa: F401 - pytest fixture, imported for reuse
    _existing_link,
    _links_of,
    _ref,
    _seed_po_line,
    _seed_product,
    _seed_row_and_mirror,
    _seed_so_line,
)
from tests.test_order_inquiry_handshake import (
    ACKNOWLEDGE,
    BASE,
    LIST,
    VIEW,
    _as_purchasing,
    _links_of as _hs_links_of,
    _open_po_line,
    _project_committed,
    _raise_one_row,
    _uid,
    api,  # noqa: F401 - pytest fixture, imported for reuse
    world,  # noqa: F401 - pytest fixture, imported for reuse
)
from tests.test_order_inquiry_suggested_links import _seed_suggested, _suggested_of

__all__ = ["ctx", "api", "world"]

AUTO_PLACE = f"{LIST}/auto-place"
LINK_SUGGESTED = f"{LIST}/link-suggested"


# =============================================================================
# AC-LT-30: `scm.committed_v` still counts a suggested-only row's demand (PIN)
# =============================================================================


def test_ac_lt_30_committed_v_still_counts_a_suggested_only_row_as_demand(api):
    """AC-LT-30 (G6). A row with need 4 holding ONE suggested link of 4 and no real
    link still nets the SAME as a row with nothing suggested: `scm.committed_v` reads
    `projects.order_inquiry_links` only (confirmed at `app/services/scm/demand.py`,
    `COMMITTED_V_SQL`), never `order_inquiry_suggested_links` - no view change, this
    test pins it.

    Seeded through the real board-confirm flow (`_raise_one_row`), not the bare
    `_seed_row_and_mirror` chain the other tests in this file use directly against
    `world.db`: `committed_v`'s CONFIRMED leg keys off an ACTIVE `so_supply_decisions`
    row, which only the real confirm route writes - the PO line is opened AFTER the
    raise, exactly as `test_order_inquiry_suggested_links.py`'s own
    `test_ac_lt_11_worklist_auto_link_all_suggests` does, so raising itself finds
    nothing to link and the cascade below is the only writer.
    """
    _client, world = api
    fixture = _raise_one_row(api, qty="4")
    row = fixture["row"]
    world.db.commit()
    assert _hs_links_of(world, row) == []
    assert _suggested_of(world.db, row.id) == []

    _open_po_line(world, qty=10)
    ProjectOrderInquiryService(world.db).auto_place_for_products(
        None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        include_awaiting=True,
    )
    world.db.commit()

    assert _hs_links_of(world, row) == [], "no real link should exist yet"
    assert len(_suggested_of(world.db, row.id)) == 1, "the suggestion has to exist to mean anything"
    assert row.state == INQUIRY_RAISED

    committed = _project_committed(world, planned=False)
    assert committed == Decimal("4")


# =============================================================================
# AC-LT-31: StockDebtService._holds pins no document to a line off a suggestion (PIN)
# =============================================================================


class TestACLT31StockDebtHoldsRealOnly:
    def test_ac_lt_31_no_hold_pins_the_suggested_document_to_the_line(self, ctx):
        """AC-LT-31 (G6). `StockDebtService._holds` reads `OrderInquiryLink` directly
        (`app/services/scm/stock_debt_service.py:637`) and never joins
        `order_inquiry_suggested_links` - this pins that a suggested-only row holds
        NOTHING (no on-hand supply is seeded either, so an empty list is the whole
        answer)."""
        from app.services.scm.stock_debt_service import StockDebtService

        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="4"
        )
        _po, _po_line = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id,
            qty_ordered="10", header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="4"
        )
        db.commit()

        ProjectOrderInquiryService(db).auto_place_for_products(
            None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
        )
        db.commit()
        assert _links_of(db, row.id) == []
        assert len(_suggested_of(db, row.id)) == 1

        holds = StockDebtService(db)._holds([str(product.id)], {str(core_line.id)})
        assert holds == [], holds


# =============================================================================
# AC-LT-32: the worklist summary counts a suggested-only row in Buy, not
# Purchased or Incoming (PIN)
# =============================================================================


def test_ac_lt_32_worklist_summary_counts_a_suggested_only_row_in_buy(api):
    """AC-LT-32 (G6). `_kinds`' `po`/`spo` legs read `_PO_LINKED_QTY`/`_SPO_LINKED_QTY`,
    both built off `OrderInquiryLink` (`order_inquiry_worklist_service.py:391-392`) -
    never the suggested table, so a suggested-only row's whole quantity stays in Buy."""
    _client, world = api
    product = _seed_product(world.db, company_id=world.company_id)
    ref = _ref("SOL")
    so, core_line = _seed_so_line(
        world.db, company_id=world.company_id, product_id=product.id, source_ref=ref, qty="4"
    )
    _po, _po_line = _seed_po_line(
        world.db, company_id=world.company_id, product_id=product.id,
        qty_ordered="10", header_status="active",
    )
    _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
        world.db, company_id=world.company_id, core_line=core_line, product_id=product.id,
        qty="4",
    )
    world.db.commit()

    ProjectOrderInquiryService(world.db).auto_place_for_products(
        None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
    )
    world.db.commit()
    assert len(_suggested_of(world.db, row.id)) == 1

    body = _client.get(f"{LIST}/summary", params={"query": so.so_number}).json()

    kinds = body["kinds"]
    assert kinds["buy"] == "4", kinds
    assert kinds["po"] == "0", kinds
    assert kinds["spo"] == "0", kinds


# =============================================================================
# AC-LT-33: `suggested_links` on the wire, on both the worklist and the OI
# detail rows - `links` stays real-only (RED: missing field)
# =============================================================================


def test_ac_lt_33_suggested_links_on_the_worklist_and_detail_rows(api):
    client, world = api
    product = _seed_product(world.db, company_id=world.company_id)
    ref = _ref("SOL")
    so, core_line = _seed_so_line(
        world.db, company_id=world.company_id, product_id=product.id, source_ref=ref, qty="4"
    )
    po, po_line = _seed_po_line(
        world.db, company_id=world.company_id, product_id=product.id,
        qty_ordered="10", header_status="active",
    )
    pso, _mirror, _inquiry, row = _seed_row_and_mirror(
        world.db, company_id=world.company_id, core_line=core_line, product_id=product.id,
        qty="4",
    )
    world.db.commit()

    ProjectOrderInquiryService(world.db).auto_place_for_products(
        None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
    )
    world.db.commit()
    assert len(_suggested_of(world.db, row.id)) == 1

    listed = client.get(LIST, params={"query": so.so_number, "limit": 200}).json()
    wire_row = next(item for item in listed["data"] if item["id"] == str(row.id))

    assert "suggested_links" in wire_row, (
        "GET /order-inquiries must carry suggested_links on the wire (response_model)"
    )
    entries = wire_row["suggested_links"]
    assert len(entries) == 1, entries
    entry = entries[0]
    assert entry["kind"] == "po"
    assert entry["document"] == po.po_number
    assert entry["po_line_id"] == str(po_line.id)
    assert Decimal(entry["qty"]) == Decimal("4")
    assert wire_row.get("links") == [], "links must carry nothing suggested"

    detail = client.get(f"{BASE}/sales-orders/{pso.id}/order-inquiry").json()
    detail_row = next(item for item in detail["rows"] if item["id"] == str(row.id))
    assert "suggested_links" in detail_row, (
        "the OI detail route must carry suggested_links on the wire too"
    )
    assert len(detail_row["suggested_links"]) == 1
    assert detail_row.get("links") == []


# =============================================================================
# AC-LT-34: the PO lightbox - allocations real only, suggested_links its own
# panel (RED: missing field)
# =============================================================================


def test_ac_lt_34_po_lightbox_allocations_real_only_suggested_in_own_panel(api):
    client, world = api
    product = _seed_product(world.db, company_id=world.company_id)

    ref_real = _ref("SOL")
    _so_real, core_line_real = _seed_so_line(
        world.db, company_id=world.company_id, product_id=product.id, source_ref=ref_real,
        qty="4",
    )
    po_real, real_line = _seed_po_line(
        world.db, company_id=world.company_id, product_id=product.id,
        from_so_line_ref=ref_real, qty_ordered="4", header_status="active",
    )
    _pso_real, _mirror_real, _inquiry_real, row_real = _seed_row_and_mirror(
        world.db, company_id=world.company_id, core_line=core_line_real, product_id=product.id,
        qty="4",
    )

    ref_suggest = _ref("SOL")
    _so_suggest, core_line_suggest = _seed_so_line(
        world.db, company_id=world.company_id, product_id=product.id, source_ref=ref_suggest,
        qty="6",
    )
    po_suggest, suggest_line = _seed_po_line(
        world.db, company_id=world.company_id, product_id=product.id,
        qty_ordered="10", header_status="active",
    )
    _pso_suggest, _mirror_suggest, _inquiry_suggest, row_suggest = _seed_row_and_mirror(
        world.db, company_id=world.company_id, core_line=core_line_suggest,
        product_id=product.id, qty="6",
    )
    world.db.commit()

    service = ProjectOrderInquiryService(world.db)
    service.follow_book_for_rows(
        [str(row_real.id)], trigger="autocount_ingest", company_id=world.company_id,
        actor_user_id=None,
    )
    world.db.commit()
    assert _hs_links_of(world, row_real) != [], "the book must have named the real target"

    _seed_suggested(
        world.db, company_id=world.company_id, row_id=row_suggest.id,
        po_line_id=suggest_line.id, document=po_suggest.po_number, qty="6",
    )
    world.db.commit()

    real_body = client.get(f"{LIST}/po/{po_real.id}").json()
    assert real_body["allocations"], "the real link must show in Allocated to"
    assert all(a["po_line_id"] == str(real_line.id) for a in real_body["allocations"])

    suggest_body = client.get(f"{LIST}/po/{po_suggest.id}").json()
    assert "suggested_links" in suggest_body, (
        "the lightbox must carry a Suggested for panel"
    )
    entries = suggest_body["suggested_links"]
    assert len(entries) == 1, entries
    entry = entries[0]
    assert entry.get("item_code") == product.product_code
    assert Decimal(entry["qty"]) == Decimal("6")
    assert suggest_body.get("allocations") == [], "no real link sits on the suggested-only PO"


# =============================================================================
# R18 (owner ruling from the hand test on stack C, 25 Sep 2026, supersedes G1's
# "Link selected writes what is suggested as a real link"): "the user should always
# go to autocount to do linking, the link selected is to recalculate with autocount
# linkage in case of mistake in the automation." Link selected never turns a
# suggestion into a real link. `POST .../link-suggested` is gone; the worklist and
# the OI detail both post `POST .../auto-place` with `row_ids` naming exactly the
# ticked rows - the SAME route `auto-place_for_products` already exposes, scoped
# down. That call already writes real links ONLY from the book step (AutoCount's own
# name, `auto=True`), then suggests the rest - so pointing "Link selected" at it is
# the whole fix; there is nothing left in this file to write for real.
# =============================================================================


def test_r18_link_suggested_route_is_gone(api):
    """The route `link-suggested` used to expose is retired outright - not merely
    denied, GONE - so a stale client still calling it gets a 404, never a silent
    200 that used to write a real link."""
    _client, world = api
    dummy_row_id = _uid()

    with _as_purchasing(world) as buyer:
        response = buyer.post(LINK_SUGGESTED, json={"row_ids": [dummy_row_id]})
    assert response.status_code == 404, response.text


def test_r18_link_selected_never_promotes_a_suggestion_with_no_book_named_target(api):
    """The core of R18: a row whose only candidate is a pool PO AutoCount has not
    tied to this sales order line (no `from_so_line_ref`) gets a SUGGESTION from the
    cascade, never a real link - pressing "Link selected" (now `auto-place` scoped
    to the ticked row) recalculates that suggestion and still never writes it for
    real, because nothing here is AutoCount's own answer."""
    client, world = api
    product = _seed_product(world.db, company_id=world.company_id)
    ref = _ref("SOL")
    _so, core_line = _seed_so_line(
        world.db, company_id=world.company_id, product_id=product.id, source_ref=ref, qty="4"
    )
    _po, po_line = _seed_po_line(
        world.db, company_id=world.company_id, product_id=product.id,
        qty_ordered="10", header_status="active",
    )
    _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
        world.db, company_id=world.company_id, core_line=core_line, product_id=product.id,
        qty="4",
    )
    world.db.commit()

    ProjectOrderInquiryService(world.db).auto_place_for_products(
        None, actor_user_id=None, trigger="raise", row_ids=[str(row.id)],
    )
    world.db.commit()
    assert _hs_links_of(world, row) == [], "no book-named target - nothing real yet"
    assert len(_suggested_of(world.db, row.id)) == 1

    with _as_purchasing(world) as buyer:
        response = buyer.post(AUTO_PLACE, json={"row_ids": [str(row.id)]})
    assert response.status_code == 200, response.text
    world.db.commit()
    world.db.expire_all()

    assert _hs_links_of(world, row) == [], (
        "Link selected never turns a suggestion into a link on its own (R18)"
    )
    suggestions = _suggested_of(world.db, row.id)
    assert len(suggestions) == 1, "the suggestion is recalculated, not deleted"
    assert suggestions[0].po_line_id == po_line.id

    body = response.json()
    assert body["book_linked_rows"] == 0, body
    assert body["suggested_rows"] == 1, body
    # Same answer as the pre-press suggestion - a straight re-run of the identical
    # cascade counts as nothing changed, which is the "no mistake found" case R18's
    # own wording describes.
    assert body["changed_rows"] == 0, body


def test_r18_link_selected_links_only_what_the_book_names_for_the_ticked_rows(api):
    """The book-named half: a row whose PO line DOES carry `from_so_line_ref` for
    this sales order line is linked for real by the book step, `auto=True` -
    AutoCount's own answer, never a person's pick (`_write_link` always records the
    session's actor for the audit trail regardless of who or what triggered it, the
    same way every other automatic writer in this file does - `auto` is the field
    that tells a book link apart from a manual one, not `linked_by`)."""
    client, world = api
    product = _seed_product(world.db, company_id=world.company_id)
    ref = _ref("SOL")
    _so, core_line = _seed_so_line(
        world.db, company_id=world.company_id, product_id=product.id, source_ref=ref, qty="4"
    )
    _po, po_line = _seed_po_line(
        world.db, company_id=world.company_id, product_id=product.id,
        from_so_line_ref=ref, qty_ordered="4", header_status="active",
    )
    _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
        world.db, company_id=world.company_id, core_line=core_line, product_id=product.id,
        qty="4",
    )
    world.db.commit()

    with _as_purchasing(world) as buyer:
        response = buyer.post(AUTO_PLACE, json={"row_ids": [str(row.id)]})
    assert response.status_code == 200, response.text
    world.db.commit()
    world.db.expire_all()

    real_links = _hs_links_of(world, row)
    assert len(real_links) == 1, real_links
    assert real_links[0].po_line_id == po_line.id
    assert real_links[0].auto is True, "the book named it - AutoCount's own answer, never a pick"
    assert _suggested_of(world.db, row.id) == []

    body = response.json()
    assert body["book_linked_rows"] == 1, body
    assert body["changed_rows"] == 1, body


def test_r18_link_selected_reuses_the_auto_place_grant(api):
    """R18: no new permission - the ticked-rows call goes through the SAME
    `auto-place` route, which already requires `projects.order_inquiry.action`. A
    user holding only VIEW and ACKNOWLEDGE is refused."""
    _client, world = api
    dummy_row_id = _uid()

    with _as_purchasing(world, permissions=[VIEW, ACKNOWLEDGE]) as viewer:
        response = viewer.post(AUTO_PLACE, json={"row_ids": [dummy_row_id]})
    assert response.status_code == 403, response.text


# =============================================================================
# AC-LT-37: `auto-place`'s response gains `book_linked_rows` and
# `suggested_rows` beside `after_horizon` (RED: missing fields)
# =============================================================================


def test_ac_lt_37_auto_place_response_gains_book_and_suggested_counts(api):
    client, world = api
    product_book = _seed_product(world.db, company_id=world.company_id)
    ref = _ref("SOL")
    _so_a, core_line_a = _seed_so_line(
        world.db, company_id=world.company_id, product_id=product_book.id, source_ref=ref,
        qty="4",
    )
    _po_a, _po_line_a = _seed_po_line(
        world.db, company_id=world.company_id, product_id=product_book.id,
        from_so_line_ref=ref, qty_ordered="4", header_status="active",
    )
    _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
        world.db, company_id=world.company_id, core_line=core_line_a,
        product_id=product_book.id, qty="4",
    )

    product_cascade = _seed_product(world.db, company_id=world.company_id)
    ref_b = _ref("SOL")
    _so_b, core_line_b = _seed_so_line(
        world.db, company_id=world.company_id, product_id=product_cascade.id,
        source_ref=ref_b, qty="6",
    )
    _po_b, _po_line_b = _seed_po_line(
        world.db, company_id=world.company_id, product_id=product_cascade.id,
        qty_ordered="10", header_status="active",
    )
    _pso_b, _mirror_b, _inquiry_b, row_b = _seed_row_and_mirror(
        world.db, company_id=world.company_id, core_line=core_line_b,
        product_id=product_cascade.id, qty="6",
    )
    world.db.commit()

    with _as_purchasing(world) as buyer:
        response = buyer.post(
            AUTO_PLACE, json={"row_ids": [str(row_a.id), str(row_b.id)]},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    world.db.commit()

    assert _hs_links_of(world, row_a) != [], "the book step should have linked row A for real"
    assert _suggested_of(world.db, row_b.id), "the cascade should have suggested for row B"

    assert body.get("after_horizon") == 0, body
    assert body["book_linked_rows"] == 1, body
    assert body["suggested_rows"] == 1, body
    # R18: both rows moved this pass - row A was book-linked, row B went from
    # nothing to a fresh suggestion - so `changed_rows` counts both.
    assert body["changed_rows"] == 2, body

    # A second, identical press finds nothing new: row A is already book-linked (it
    # drops out of the book step's own before/after diff) and row B's cascade answer
    # is unchanged, so `changed_rows` is 0 - "Link selected" pressed twice in a row
    # with nothing having moved in AutoCount reports no mistake to fix.
    with _as_purchasing(world) as buyer:
        again = buyer.post(
            AUTO_PLACE, json={"row_ids": [str(row_a.id), str(row_b.id)]},
        )
    assert again.status_code == 200, again.text
    again_body = again.json()
    assert again_body["book_linked_rows"] == 0, again_body
    assert again_body["changed_rows"] == 0, again_body


# =============================================================================
# AC-LT-38: the SCM SO detail, the board, the PO page and the handover email
# read real links only (PIN)
# =============================================================================


class TestACLT38ReadersStayRealLinksOnly:
    """One shared seed: a row with ONE real link (book-named) and a SEPARATE row
    holding ONE suggested link on a DIFFERENT purchase order, so every assertion
    below can check the suggested document's own identity never leaks into a
    reader the plan says gets no code change in this lane."""

    def _seed(self, ctx):
        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="5"
        )
        po_real, real_line = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id,
            qty_ordered="10", header_status="active",
        )
        po_suggest, suggest_line = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id,
            qty_ordered="10", header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="5"
        )
        db.commit()

        service = ProjectOrderInquiryService(db)
        service.place_on_po_allocations(
            str(row.id), [{"po_line_id": str(real_line.id), "qty": "5"}], actor_user_id=None,
        )
        _seed_suggested(
            db, company_id=ctx.company_a, row_id=row.id, po_line_id=suggest_line.id,
            document=po_suggest.po_number, qty="5",
        )
        db.commit()
        return db, so, core_line, po_real, real_line, po_suggest, suggest_line, row

    def test_ac_lt_38_sales_order_detail_line_links_real_only(self, ctx):
        from app.services.scm.sales_order_service import SalesOrderService

        db, so, core_line, po_real, real_line, po_suggest, _suggest_line, _row = (
            self._seed(ctx)
        )

        entries = SalesOrderService(db)._line_links(so)
        docs = [entry["document"] for entry in entries.get(str(core_line.id), [])]
        assert docs == [po_real.po_number], docs
        assert po_suggest.po_number not in docs

    def test_ac_lt_38_board_documents_real_only(self, ctx):
        from app.services.project_fulfilment_board_service import FulfilmentBoardService

        db, _so, core_line, po_real, _real_line, po_suggest, _suggest_line, _row = (
            self._seed(ctx)
        )

        entries = FulfilmentBoardService(db)._order_inquiries([str(core_line.id)])
        entry = entries[str(core_line.id)]
        docs = [item["document"] for item in entry["documents"]]
        assert docs == [po_real.po_number], docs
        assert po_suggest.po_number not in docs

    def test_ac_lt_38_po_page_placements_real_only(self, ctx):
        from app.services.scm.purchase_order_service import PurchaseOrderService

        db, _so, _core_line, po_real, real_line, _po_suggest, suggest_line, _row = (
            self._seed(ctx)
        )

        blocks = PurchaseOrderService(db)._allocations_for(po_real)
        line_ids = {block["line_id"] for block in blocks}
        assert str(real_line.id) in line_ids
        assert str(suggest_line.id) not in line_ids, (
            "a line carrying only a suggested link is never a placement block"
        )

    def test_ac_lt_38_handover_email_context_real_only(self, ctx):
        db, _so, _core_line, _po_real, _real_line, po_suggest, _suggest_line, row = (
            self._seed(ctx)
        )

        service = ProjectOrderInquiryService(db)
        service._record_handover(row, kind="raised", actor_user_id=None)
        pending = db.info.get(_HANDOVER_PENDING_KEY)
        assert pending, "the seeded write should have queued a handover line"
        context, _source_id = _build_handover_context(pending)

        blob = json.dumps(context, default=str)
        assert po_suggest.po_number not in blob, (
            "a suggested link must never reach the handover email"
        )


# =============================================================================
# AC-LT-39: the Excel export gets a Suggested column; PO/SPO stay real-only
# (RED: missing heading)
# =============================================================================


class TestACLT39ExcelExportGetsASuggestedColumn:
    def test_ac_lt_39_export_carries_a_suggested_column_and_po_stays_real_only(self, ctx):
        import openpyxl

        from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

        db = ctx.db
        product = _seed_product(db, company_id=ctx.company_a)
        ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="5"
        )
        po_real, real_line = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id,
            qty_ordered="10", header_status="active",
        )
        po_suggest, suggest_line = _seed_po_line(
            db, company_id=ctx.company_a, product_id=product.id,
            qty_ordered="10", header_status="active",
        )
        _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
            db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="5"
        )
        db.commit()
        row.delivery_date = date(2026, 8, 1)
        db.commit()

        service = ProjectOrderInquiryService(db)
        service.place_on_po_allocations(
            str(row.id), [{"po_line_id": str(real_line.id), "qty": "5"}], actor_user_id=None,
        )
        _seed_suggested(
            db, company_id=ctx.company_a, row_id=row.id, po_line_id=suggest_line.id,
            document=po_suggest.po_number, qty="5",
        )
        db.commit()

        _filename, content = OrderInquiryWorklistService(db).export_xlsx()
        workbook = openpyxl.load_workbook(io.BytesIO(content))
        sheet = workbook[workbook.sheetnames[0]]
        headings = [str(cell.value).strip().upper() for cell in sheet[2] if cell.value]

        assert "SUGGESTED" in headings, headings
