"""RED tests for hiding retired SPO allocation lines (AC-H1..AC-H6, AC-H8, AC-H10).

UAC: documentation/plans/autocount/hide-retired-spo-lines-acceptance-criteria.md
PLAN: documentation/plans/autocount/PLAN-hide-retired-spo-lines.md

Written test-first (Phase 2), before `spo_supply.visible_line_clauses()` exists.
Contract this suite pins:

- `app.services.scm.spo_supply.visible_line_clauses()` - one predicate: a line is
  VISIBLE unless `retired_at IS NOT NULL AND coalesce(quantity_received, 0) = 0`
  (R1/R2). A retired line that carries a receipt (R2) or a line closed for any
  other reason (fully received, R1) stays visible.
- Every DISPLAY reader in `app.services.procurement_service` applies it:
  `list_allocations`, `list_documents` (+ its `total_allocated`/`total_received`
  rollups), `get_document` (+ its own rollups) (R4, R6).
- A read that resolves an allocation BY ITS OWN ID - here, a GRN's picking line
  pointing at a retired allocation - is NOT filtered (R3).
- Line balance follows outstanding status, hidden or not: a line that is not
  outstanding reads `balance == 0` (R5), so the grid can never disagree with the
  document header again.

Substrate reused from `tests.scm.test_spo_allocation_documents` (the `scm_app`
Postgres-savepoint fixture, its `_client`/`_chain`/`_product` catalogue helpers
and `DOCUMENTS_URL`) rather than re-copied, per the tester brief. Allocation rows
here carry `retired_at`/`source_system`, which that module's own `_line` helper
does not accept, so this file adds its own `_alloc`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.procurement import PickingHeader, PickingLine, SPOAllocation
from app.models.product import Product

from tests._pg_fixture import unique_code
from tests.scm.test_spo_allocation_documents import (
    DOCUMENTS_URL,
    _chain,
    _client,
    _product,
    _u,
)

# This suite lives in `tests/` rather than `tests/scm/`, so the SCM conftest is not
# auto-loaded for it - `scm_app` is imported by name (same pattern as
# `tests/test_project_order_inquiry_import_cs_handover.py` and
# `tests/test_incoming_stock_draft_exclusion.py`) rather than a second savepoint
# fixture maintained twice.
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401

pytestmark = requires_pg

LIST_URL = "/api/v1/procurement/spo-allocations/"
GRN_URL = "/api/v1/procurement/grn"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _alloc(
    db: Session,
    *,
    spo_number: str,
    line_no: int,
    product: Product,
    allocated: int = 10,
    received: int = 0,
    receipt_status: str = "pending",
    line_status: str = "open",
    retired_at: datetime | None = None,
    source_system: str | None = "autocount",
    stated_received: int | None = None,
) -> SPOAllocation:
    """One `spo_allocations` row, extended with `retired_at`/`source_system`/
    `stated_received` - columns `test_spo_allocation_documents._line` does not
    carry. `source_system="autocount"` by default so `list_allocations`'
    GRN-computed-receipt recompute (`_receipt_is_computed`, triggered for
    `source_system in {None, 'scm_spo_history'}`) never overwrites the seeded
    `quantity_received` out from under an assertion here.
    """
    allocation = SPOAllocation(
        id=_u(),
        spo_number=spo_number,
        spo_line_number=line_no,
        product_id=product.id,
        allocated_quantity=allocated,
        quantity_received=received,
        receipt_status=receipt_status,
        line_status=line_status,
        retired_at=retired_at,
        source_system=source_system,
        stated_received=stated_received,
    )
    db.add(allocation)
    db.flush()
    return allocation


# =================================================================================== #
# AC-H1 (R1): a retired line with no receipt is hidden
# =================================================================================== #


class TestAcH1HidesRetiredLineWithNoReceipt:
    def test_document_hides_the_retired_zero_receipt_line(self, scm_app):
        """AC-H1. One open line + one retired line (received 0): `get_document`
        returns only the open line; `total_allocated` counts the open line only;
        Balance is unchanged.

        RED today: `get_document` applies no retirement filter at all, so both
        lines come back, `len(lines) == 1` fails, and `total_allocated` reads 15
        (10 + 5) instead of 10.
        """
        client, db = _client(scm_app)
        chain = _chain(db)
        product = _product(db, chain)
        doc = unique_code("SPO-H1")

        open_line = _alloc(db, spo_number=doc, line_no=1, product=product, allocated=10, received=0)
        _alloc(
            db, spo_number=doc, line_no=2, product=product, allocated=5, received=0,
            line_status="closed", retired_at=_now(),
        )

        r = client.get(f"{DOCUMENTS_URL}/{doc}")
        assert r.status_code == 200, r.text
        body = r.json()

        line_ids = {line["id"] for line in body["lines"]}
        assert line_ids == {open_line.id}, line_ids
        assert body["total_allocated"] == 10, body["total_allocated"]
        assert body["balance"] == 10, body["balance"]


# =================================================================================== #
# AC-H2 (R1): merely closed (not retired) never disappears
# =================================================================================== #


class TestAcH2ClosedButNotRetiredStaysVisible:
    def test_fully_received_closed_line_with_no_retired_at_is_still_returned(self, scm_app):
        """AC-H2. A line closed with `receipt_status = 'fully_received'` and
        `retired_at` NULL is still returned, and still counts in
        `total_allocated`/`total_received` - seeded beside an open line so an
        over-broad implementation that hides every `line_status == 'closed'` row
        (ignoring `retired_at` entirely) fails this guard the moment it lands,
        rather than only R1's own line disappearing silently.
        """
        client, db = _client(scm_app)
        chain = _chain(db)
        product = _product(db, chain)
        doc = unique_code("SPO-H2")

        open_line = _alloc(db, spo_number=doc, line_no=1, product=product, allocated=10, received=0)
        closed_line = _alloc(
            db, spo_number=doc, line_no=2, product=product, allocated=10, received=10,
            receipt_status="fully_received", line_status="closed", retired_at=None,
        )

        r = client.get(f"{DOCUMENTS_URL}/{doc}")
        assert r.status_code == 200, r.text
        body = r.json()

        line_ids = {line["id"] for line in body["lines"]}
        assert line_ids == {open_line.id, closed_line.id}, line_ids
        assert body["total_allocated"] == 20, body["total_allocated"]
        assert body["total_received"] == 10, body["total_received"]


# =================================================================================== #
# AC-H3 (R2): a retired line carrying a receipt stays visible, balance 0
# =================================================================================== #


class TestAcH3RetiredLineWithReceiptStaysVisible:
    def test_retired_line_with_a_receipt_is_returned_counted_and_reads_balance_zero(
        self, scm_app
    ):
        """AC-H3. A line with `retired_at` set AND `quantity_received > 0` is
        still returned, counts in `total_received`, and reads `balance 0`.

        RED today at the balance assertion: `get_document` computes
        `balance = max(allocated - received, 0)` unconditionally (R5's bug), so
        this retired-but-received line reports balance 6 (10 - 4), not 0.
        """
        client, db = _client(scm_app)
        chain = _chain(db)
        product = _product(db, chain)
        doc = unique_code("SPO-H3")

        retired_with_receipt = _alloc(
            db, spo_number=doc, line_no=1, product=product, allocated=10, received=4,
            line_status="closed", retired_at=_now(),
        )

        r = client.get(f"{DOCUMENTS_URL}/{doc}")
        assert r.status_code == 200, r.text
        body = r.json()

        line_ids = {line["id"] for line in body["lines"]}
        assert line_ids == {retired_with_receipt.id}, line_ids
        assert body["total_received"] == 4, body["total_received"]
        line = body["lines"][0]
        assert line["balance"] == 0, line["balance"]


# =================================================================================== #
# AC-H4 (R5): a non-outstanding line always reads balance 0
# =================================================================================== #


class TestAcH4NonOutstandingLineBalanceIsZero:
    def test_every_non_outstanding_returned_line_reads_balance_zero_and_lines_foot_the_header(
        self, scm_app
    ):
        """AC-H4. Every returned line that is not outstanding reads `balance 0`;
        the sum of the returned lines' balances equals the document's Balance.

        Seeded: one open/outstanding line (balance 10), one retired line with a
        partial receipt (not outstanding - must read 0, not 6), one ordinary
        fully-received closed line (not outstanding, already 0 by arithmetic).

        RED today: the retired-partial line's `balance` computes to 6
        (`max(10 - 4, 0)`) instead of 0, so both the per-line assertion and the
        footing assertion (16 != 10) fail.
        """
        client, db = _client(scm_app)
        chain = _chain(db)
        product = _product(db, chain)
        doc = unique_code("SPO-H4")

        _alloc(db, spo_number=doc, line_no=1, product=product, allocated=10, received=0)
        _alloc(
            db, spo_number=doc, line_no=2, product=product, allocated=10, received=4,
            line_status="closed", retired_at=_now(),
        )
        _alloc(
            db, spo_number=doc, line_no=3, product=product, allocated=10, received=10,
            receipt_status="fully_received", line_status="closed",
        )

        r = client.get(f"{DOCUMENTS_URL}/{doc}")
        assert r.status_code == 200, r.text
        body = r.json()

        for line in body["lines"]:
            if not line["outstanding"]:
                assert line["balance"] == 0, line

        assert sum(line["balance"] for line in body["lines"]) == body["balance"], body


# =================================================================================== #
# AC-H5 (R3): an id-resolved read is NOT filtered
# =================================================================================== #


class TestAcH5GrnStillResolvesARetiredAllocationById:
    def test_grn_detail_still_renders_the_picking_line_s_retired_allocation(self, scm_app):
        """AC-H5. A GRN whose picking line points at a hidden (retired, zero
        receipt) allocation still renders that allocation in the GRN detail
        response - the allocation is reachable by id.

        This is a guard against overreach (R3), not a reproduction of a live
        bug: nothing filters `PickingHeaderService.get_grn`'s `spo_allocation`
        joinedload today, so it already passes. It exists so a later change
        that broadens `visible_line_clauses()` into a blanket
        `with_loader_criteria` cannot silently break it.
        """
        client, db = _client(scm_app)
        chain = _chain(db)
        product = _product(db, chain)
        doc = unique_code("SPO-H5")

        hidden = _alloc(
            db, spo_number=doc, line_no=1, product=product, allocated=7, received=0,
            line_status="closed", retired_at=_now(),
        )

        header = PickingHeader(
            id=_u(),
            picking_number=unique_code("GRN-H5"),
            picking_type="goods_received",
            picking_status="approved",
        )
        db.add(header)
        db.flush()
        picking_line = PickingLine(
            id=_u(),
            picking_header_id=header.id,
            spo_allocation_id=hidden.id,
            product_id=product.id,
            quantity_expected=7,
            quantity_picked=0,
        )
        db.add(picking_line)
        db.flush()

        r = client.get(f"{GRN_URL}/{header.id}")
        assert r.status_code == 200, r.text
        body = r.json()
        lines = body["picking_lines"] or []
        assert len(lines) == 1, lines
        allocation = lines[0]["spo_allocation"]
        assert allocation is not None, lines[0]
        assert allocation["id"] == hidden.id, allocation


# =================================================================================== #
# AC-H6 (R6): one predicate, one place - the grid, the list, the detail agree
# =================================================================================== #


class TestAcH6OnePredicateOnePlace:
    def _seed_document(self, db, chain):
        product = _product(db, chain)
        doc = unique_code("SPO-H6")
        open_line = _alloc(db, spo_number=doc, line_no=1, product=product, allocated=10, received=0)
        hidden_line = _alloc(
            db, spo_number=doc, line_no=2, product=product, allocated=7, received=0,
            line_status="closed", retired_at=_now(),
        )
        retired_with_receipt = _alloc(
            db, spo_number=doc, line_no=3, product=product, allocated=5, received=3,
            line_status="closed", retired_at=_now(),
        )
        fully_received = _alloc(
            db, spo_number=doc, line_no=4, product=product, allocated=10, received=10,
            receipt_status="fully_received", line_status="closed",
        )
        return doc, {
            "open": open_line,
            "hidden": hidden_line,
            "retired_with_receipt": retired_with_receipt,
            "fully_received": fully_received,
        }

    def test_visible_line_clauses_is_the_one_predicate_queried_directly(self, scm_app):
        """`spo_supply.visible_line_clauses()` is importable and usable as an
        AND-able clause tuple that, applied directly to `SPOAllocation`, keeps
        exactly the three non-hidden seeded rows.

        RED today: `app.services.scm.spo_supply` has no `visible_line_clauses`
        attribute yet.
        """
        from app.services.scm import spo_supply

        _, db = _client(scm_app)
        chain = _chain(db)
        doc, lines = self._seed_document(db, chain)

        visible_ids = {
            row.id
            for row in db.query(SPOAllocation)
            .filter(SPOAllocation.spo_number == doc)
            .filter(and_(*spo_supply.visible_line_clauses()))
            .all()
        }
        assert visible_ids == {
            lines["open"].id, lines["retired_with_receipt"].id, lines["fully_received"].id,
        }, visible_ids

    def test_grid_list_and_detail_all_agree_on_the_same_visible_set(self, scm_app):
        """AC-H6. `list_allocations`, `list_documents` and `get_document` all
        read the same visible set for one seeded document.

        RED today: none of the three readers filters on `retired_at` at all, so
        each includes the hidden line - the explicit expected-set assertions
        below fail (not merely the three-way equality, which a fully unfiltered
        implementation would also - wrongly - satisfy).
        """
        client, db = _client(scm_app)
        chain = _chain(db)
        doc, lines = self._seed_document(db, chain)
        expected_visible_ids = {
            lines["open"].id, lines["retired_with_receipt"].id, lines["fully_received"].id,
        }
        expected_total_allocated = 10 + 5 + 10  # excludes the hidden line's 7

        grid = client.get(LIST_URL, params={"query": doc, "limit": 100})
        assert grid.status_code == 200, grid.text
        grid_ids = {row["id"] for row in grid.json()["data"]}
        assert grid_ids == expected_visible_ids, grid_ids

        detail = client.get(f"{DOCUMENTS_URL}/{doc}")
        assert detail.status_code == 200, detail.text
        detail_body = detail.json()
        detail_ids = {line["id"] for line in detail_body["lines"]}
        assert detail_ids == expected_visible_ids, detail_ids
        assert detail_body["total_allocated"] == expected_total_allocated, detail_body["total_allocated"]

        doc_list = client.get(DOCUMENTS_URL, params={"state": "all", "query": doc, "limit": 100})
        assert doc_list.status_code == 200, doc_list.text
        doc_row = next(row for row in doc_list.json()["data"] if row["spo_number"] == doc)
        assert doc_row["total_allocated"] == expected_total_allocated, doc_row["total_allocated"]
        assert doc_row["total_allocated"] == detail_body["total_allocated"]


# =================================================================================== #
# AC-H8: document rollup shape on a seeded document (not production data)
# =================================================================================== #


class TestAcH8DocumentTotalExcludesTheRetiredLine:
    def test_total_allocated_excludes_the_retired_line_and_line_count_matches(self, scm_app):
        """AC-H8, adapted to a seeded document rather than production data
        (SPO-2026/09-0036 is not reachable from a Postgres-savepoint test):
        three open lines summing to a known total, plus one retired line with
        no receipt, prove `get_document`'s `total_allocated` and `line_count`
        both exclude the retired line.

        RED today: `total_allocated` sums all four lines (650), not the three
        open ones (600), and `line_count` reads 4, not 3.
        """
        client, db = _client(scm_app)
        chain = _chain(db)
        product = _product(db, chain)
        doc = unique_code("SPO-H8")

        open_ids = set()
        for line_no, qty in ((1, 100), (2, 200), (3, 300)):
            row = _alloc(db, spo_number=doc, line_no=line_no, product=product, allocated=qty, received=0)
            open_ids.add(row.id)
        retired_line = _alloc(
            db, spo_number=doc, line_no=4, product=product, allocated=50, received=0,
            line_status="closed", retired_at=_now(),
        )

        r = client.get(f"{DOCUMENTS_URL}/{doc}")
        assert r.status_code == 200, r.text
        body = r.json()

        line_ids = {line["id"] for line in body["lines"]}
        assert line_ids == open_ids, line_ids
        assert retired_line.id not in line_ids
        assert body["total_allocated"] == 600, body["total_allocated"]
        assert body["line_count"] == 3, body["line_count"]


# =================================================================================== #
# AC-H10 (B2, round 2): a receipt approved AFTER retirement still reaches the row
# =================================================================================== #


class TestAcH10ReceiptAfterRetirement:
    def test_a_grn_approved_after_retirement_still_writes_the_allocation_s_receipt(
        self, scm_app
    ):
        """AC-H10, first half. A retired allocation (received 0) plus an
        approved goods-received note whose picking line draws 5 against it:
        after `sync_grn_received_to_spo`, the allocation reads
        `quantity_received 5`, is still returned by the document detail (R2:
        `retired_at` set AND `quantity_received > 0` stays visible), and
        counts in `total_received`.

        RED today: `_sync_received_for_allocations` still `continue`s on a
        retired autocount row without writing anything, so
        `quantity_received` stays 0 - and at 0 the row is also hidden
        (R2 requires `> 0`), so both the DB-level and the document-detail
        assertions fail.
        """
        from app.services.procurement_service import PickingHeaderService

        client, db = _client(scm_app)
        chain = _chain(db)
        product = _product(db, chain)
        doc = unique_code("SPO-H10A")

        retired = _alloc(
            db, spo_number=doc, line_no=1, product=product, allocated=47, received=0,
            line_status="closed", retired_at=_now(),
        )

        header = PickingHeader(
            id=_u(),
            picking_number=unique_code("GRN-H10A"),
            picking_type="goods_received",
            picking_status="approved",
            spo_number=doc,
        )
        db.add(header)
        db.flush()
        db.add(
            PickingLine(
                id=_u(),
                picking_header_id=header.id,
                spo_allocation_id=retired.id,
                product_id=product.id,
                quantity_expected=5,
                quantity_picked=5,
            )
        )
        db.flush()
        db.commit()

        PickingHeaderService(db).sync_grn_received_to_spo(header.id)

        db.expire_all()
        stored = db.query(SPOAllocation).filter(SPOAllocation.id == retired.id).one()
        assert stored.quantity_received == 5, stored.quantity_received

        r = client.get(f"{DOCUMENTS_URL}/{doc}")
        assert r.status_code == 200, r.text
        body = r.json()
        line_ids = {line["id"] for line in body["lines"]}
        assert retired.id in line_ids, line_ids
        assert body["total_received"] == 5, body["total_received"]

    def test_a_retired_line_s_stated_receipt_survives_the_grn_that_proved_it_being_deleted(
        self, scm_app
    ):
        """AC-H10, second half - the AC-X40 shape
        (`tests/test_spo_xlsx_supersede.py::TestAcX40...`), but seeded with
        `retired_at` set directly rather than reached through the ingest's
        own leftover sweep: a retired allocation with `stated_received 29`
        and `quantity_received 29` (closed BY the GRN that proved it) whose
        GRN is then deleted still reads 29 and stays closed - the D28c
        floor (`max(stated_received, its own approved picking total)`)
        covers the deletion, so a retired line is never demand again just
        because the receipt that closed it went away.

        This is a guard, not a reproduction of a live bug: on the
        PRE-B2 tree the assertions below already pass BY INERTIA (a retired
        row is never touched by `_sync_received_for_allocations` at all, in
        either direction, so `quantity_received` simply never moves off 29).
        `test_a_grn_approved_after_retirement...` above is what actually
        pins the new write path being red today; this one exists so that
        once that write path lands, nobody drops the `max(stated_received,
        ...)` floor and silently zeroes a retired line's receipt the moment
        its GRN is deleted (AC-X40's own regression, one row over).
        """
        from app.services.procurement_service import PickingHeaderService

        client, db = _client(scm_app)
        chain = _chain(db)
        product = _product(db, chain)
        doc = unique_code("SPO-H10B")

        retired = _alloc(
            db, spo_number=doc, line_no=1, product=product, allocated=29, received=29,
            receipt_status="fully_received", line_status="closed", retired_at=_now(),
            stated_received=29,
        )

        header = PickingHeader(
            id=_u(),
            picking_number=unique_code("GRN-H10B"),
            picking_type="goods_received",
            picking_status="approved",
            spo_number=doc,
        )
        db.add(header)
        db.flush()
        db.add(
            PickingLine(
                id=_u(),
                picking_header_id=header.id,
                spo_allocation_id=retired.id,
                product_id=product.id,
                quantity_expected=29,
                quantity_picked=29,
            )
        )
        db.flush()
        db.commit()

        PickingHeaderService(db).delete_grn(header.id)

        db.expire_all()
        stored = db.query(SPOAllocation).filter(SPOAllocation.id == retired.id).one()
        assert stored.quantity_received == 29, stored.quantity_received
        assert stored.line_status == "closed", stored.line_status
        assert stored.receipt_status == "fully_received", stored.receipt_status
