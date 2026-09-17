"""Order inquiries: one header per SO, hide cancelled, Was/Now after a redirect, cascade
skips used rows, raised-by per row (`PLAN-oi-worklist-one-header.md`,
`oi-worklist-one-header-acceptance-criteria.md`).

TEST-FIRST (Phase 2): written against the UAC + the plan's own measured facts, with NO
implementation to look at. Every test below must fail today for a real reason - a missing
function/attribute, or an assertion on behaviour the plan says does not exist yet - never an
import typo or a fixture bug.

Fixtures are borrowed, not re-invented, from the two suites the plan itself names as the
seam:

* `tests.test_order_inquiry_handshake` / `tests.test_order_inquiry_draft_links` for S1
  (cascade), S3 (one header) and S4 (Was/Now after a redirect) - the real-database,
  rolled-back `world`/`api` harness `_redirected_fixture` already builds the exact
  SO314593 shape (a row `partly_linked` to a document already fully received).
* `tests.test_order_inquiry_worklist` for S2 (raised-by) and S5 (hide cancelled) - the
  `blank_session`-backed `api` harness that already seeds one authored + one adopted order
  for the cross-project worklist.

Postgres only (`tests/_pg_fixture.py`), every FK seeded here or borrowed from an existing
seeding helper - never `LIMIT 1` off a shared table.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    AMENDMENT_PUBLISHED,
    INQUIRY_CANCELLED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ADVANCE,
    IV_DELAY,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    SOAmendment,
    SOSupplyDecision,
)
from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services import project_order_inquiry_service as poi_service
from app.services.planning_change_service import _oi_demand_rows
from app.services.project_order_inquiry_engine import CHANGE_DATE_LATER
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.project_supply_service import ProjectSupplyService

from ._pg_fixture import blank_session
from .test_order_inquiry_draft_links import (
    REPLAN_DATE,
    _link_row_to,
    _received_spo,
    _redirected_fixture,
    _rows_for_line,
    _spo_line,
)
from .test_order_inquiry_handshake import (
    NOW,
    WAS,
    _confirm,
    _core_line,
    _core_so,
    _links_of,
    _open_po_line,
    _project_line,
    _project_so,
    _raise_one_row,
    _uid,
    _user,
    api,
    world,
)
from .test_order_inquiry_worklist import (
    LIST as WL_LIST,
    MARKER as WL_MARKER,
    READ_ONLY as WL_READ_ONLY,
    _client as _wl_client,
    _inquiry_for as _wl_inquiry_for,
    _restore as _wl_restore,
    _row as _wl_row,
    _seed as _wl_seed,
    _sorento as _wl_sorento,
)

__all__ = ["api", "world"]  # re-exported fixtures; keeps linters from calling them unused


# =============================================================================
# S1 (AC-OH-10..12): the auto-link cascade must skip a `redirected_to_pool` row
# =============================================================================


class TestCascadeSkipsUsedRows:
    def test_cascade_skips_redirected_row_AC_OH_10(self, api):
        """AC-OH-10: a released row (`redirected_to_pool`, `partly_linked`, an unlinked
        remainder) must gain no new link from an open SPO the cascade can otherwise see,
        and its own state/note must be untouched - the SO314593 defect verbatim (24 pcs of
        SPO-2026/09-0036 auto-linked onto the released 182 row)."""
        _client, world = api
        fixture = _redirected_fixture(api)
        row = fixture["redirected_row"]
        # An open SPO for the same product, with real capacity for the cascade to place -
        # today's query has no `redirected_to_pool` filter, so it reads this row's own
        # unlinked remainder (182 - 158 = 24) as a candidate.
        _spo_line(world, qty="50", warehouse=world.warehouse)
        before_links = len(_links_of(world, row))
        before_state = row.state
        before_note = row.note

        ProjectOrderInquiryService(world.db).auto_place_for_products(
            [str(world.product.id)],
            actor_user_id=world.cs_user,
            trigger="test-ac-oh-10",
            include_awaiting=True,
        )
        world.db.commit()

        world.db.refresh(row)
        assert len(_links_of(world, row)) == before_links, "no new link on the used row"
        assert row.state == before_state
        assert row.note == before_note

    def test_cascade_links_open_spo_to_fresh_row_not_used_AC_OH_11(self, api):
        """AC-OH-11: the same open SPO must land on the FRESH row the redirect raised,
        never on the used one."""
        _client, world = api
        fixture = _redirected_fixture(api)
        row = fixture["redirected_row"]
        new_row = fixture["new_row"]
        # 220, matching the fresh row's own unlinked need (REPLAN_QTY): the standing 8 Sep
        # 2026 cascade rule (`_cascade_take`, "slice D") takes NOTHING when the cascadable
        # candidates cannot cover the row's need in full, so a smaller open SPO would fail
        # this assertion for a reason that has nothing to do with AC-OH-11 (the fresh row
        # never got a chance to be offered a partial).
        open_alloc = _spo_line(world, qty="220", warehouse=world.warehouse)

        ProjectOrderInquiryService(world.db).auto_place_for_products(
            [str(world.product.id)],
            actor_user_id=world.cs_user,
            trigger="test-ac-oh-11",
            include_awaiting=True,
        )
        world.db.commit()

        world.db.refresh(new_row)
        world.db.refresh(row)
        new_links = _links_of(world, new_row)
        assert len(new_links) == 1, "the open SPO must land on the fresh row"
        assert new_links[0].spo_allocation_id == open_alloc.id
        used_links = _links_of(world, row)
        assert len(used_links) == 1, "the used row must not gain the open SPO"
        assert used_links[0].spo_allocation_id == fixture["received_allocation"].id

    def test_link_now_skips_redirected_row_AC_OH_12(self, api):
        """AC-OH-12: Link now / Auto link all (`link_now`) goes through the same seam and
        must skip the used row the same way."""
        _client, world = api
        fixture = _redirected_fixture(api)
        row = fixture["redirected_row"]
        new_row = fixture["new_row"]
        # 220, matching the fresh row's own unlinked need - see the AC-OH-11 comment above.
        open_alloc = _spo_line(world, qty="220", warehouse=world.warehouse)

        ProjectOrderInquiryService(world.db).link_now(
            [str(world.product.id)], actor_user_id=world.cs_user, link_horizon="none"
        )
        world.db.commit()

        world.db.refresh(row)
        world.db.refresh(new_row)
        used_links = _links_of(world, row)
        assert len(used_links) == 1, "link_now must skip the used row the same way"
        assert used_links[0].spo_allocation_id == fixture["received_allocation"].id
        new_links = _links_of(world, new_row)
        assert new_links and new_links[0].spo_allocation_id == open_alloc.id


# =============================================================================
# S2 (AC-OH-20..23): raised-by is the ROW's own person, not the header's latest
# =============================================================================


@pytest.fixture()
def rb_api():
    """A fresh company, one authored order (`test_order_inquiry_worklist._seed`'s own
    shape) and three named users this section's tests stamp onto rows/headers by hand -
    the worklist's `list`/`summary` routes are hit over HTTP exactly as the sibling suite
    does, so the wire's own `raised_by_name` field is what gets asserted."""
    from app.models.base import company_scope
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _wl_sorento(db)
        project_seed_service.run(db, company_id=company_id)
        confirmer = _user(db, f"{WL_MARKER} Confirmer Joey")
        migrator = _user(db, f"{WL_MARKER} Migrator Aina")
        reconfirmer = _user(db, f"{WL_MARKER} Reconfirmer Beng")
        user_id = _user(db, f"{WL_MARKER} Eling")
        seeded = _wl_seed(db, company_id, user_id)
        client, originals = _wl_client(db, user_id, WL_READ_ONLY)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, seeded, {
                    "confirmer": confirmer,
                    "migrator": migrator,
                    "reconfirmer": reconfirmer,
                }
        finally:
            _wl_restore(originals)


def _authored_inquiry(db, seeded) -> OrderInquiry:
    return (
        db.query(OrderInquiry)
        .filter(OrderInquiry.id == seeded["authored_row"].order_inquiry_id)
        .one()
    )


class TestRaisedByPerRow:
    def test_raised_by_is_decision_confirmer_AC_OH_20(self, rb_api):
        """AC-OH-20 (unchanged baseline): a row with `supply_decision_id` set reads the
        decision's own `confirmed_by`."""
        client, db, company_id, seeded, users = rb_api
        inquiry = _authored_inquiry(db, seeded)
        decision = SOSupplyDecision(
            id=_uid(),
            company_id=company_id,
            project_sales_order_id=seeded["authored"].id,
            revision_no=1,
            state="active",
            line_snapshots=[],
            confirmed_by=users["confirmer"],
            confirmed_at=datetime.utcnow(),
        )
        db.add(decision)
        db.flush()
        row = _wl_row(
            db,
            company_id,
            inquiry,
            item_code=f"{WL_MARKER}-decision-row",
            qty="12",
            supply_decision_id=decision.id,
        )
        db.commit()

        body = client.get(WL_LIST).json()
        item = next(r for r in body["data"] if r["id"] == row.id)
        assert item["raised_by_name"] == f"{WL_MARKER} Confirmer Joey"

    def test_migrated_row_keeps_migrator_after_header_restamp_AC_OH_21(self, rb_api):
        """AC-OH-21, the real defect: a migrated row (no decision, `acknowledged_by` the
        migrator) must keep reading as the migrator even after the header's own
        `raised_by` has been re-stamped by a LATER Confirm."""
        client, db, company_id, seeded, users = rb_api
        inquiry = _authored_inquiry(db, seeded)
        inquiry.raised_by = users["reconfirmer"]
        db.flush()
        row = _wl_row(
            db,
            company_id,
            inquiry,
            item_code=f"{WL_MARKER}-migrated-row",
            qty="7",
            acknowledged_by=users["migrator"],
        )
        db.commit()

        body = client.get(WL_LIST).json()
        item = next(r for r in body["data"] if r["id"] == row.id)
        assert item["raised_by_name"] == f"{WL_MARKER} Migrator Aina"

    def test_row_without_ack_falls_back_to_header_AC_OH_22(self, rb_api):
        """AC-OH-22 (unchanged): neither a decision nor an acknowledger falls back to the
        header's own `raised_by`."""
        client, db, company_id, seeded, users = rb_api
        inquiry = _authored_inquiry(db, seeded)
        inquiry.raised_by = users["reconfirmer"]
        db.flush()
        row = _wl_row(
            db, company_id, inquiry, item_code=f"{WL_MARKER}-plain-row", qty="5"
        )
        db.commit()

        body = client.get(WL_LIST).json()
        item = next(r for r in body["data"] if r["id"] == row.id)
        assert item["raised_by_name"] == f"{WL_MARKER} Reconfirmer Beng"

    def test_raised_by_filter_uses_row_person_AC_OH_23(self, rb_api):
        """AC-OH-23: the `raised_by` filter narrows on the ROW's own answer, not the
        header's."""
        client, db, company_id, seeded, users = rb_api
        inquiry = _authored_inquiry(db, seeded)
        inquiry.raised_by = users["reconfirmer"]
        db.flush()
        migrated_row = _wl_row(
            db,
            company_id,
            inquiry,
            item_code=f"{WL_MARKER}-migrated-filter-row",
            qty="9",
            acknowledged_by=users["migrator"],
        )
        db.commit()

        with_migrator = client.get(WL_LIST, params={"raised_by": users["migrator"]}).json()
        assert migrated_row.id in {r["id"] for r in with_migrator["data"]}

        with_reconfirmer = client.get(
            WL_LIST, params={"raised_by": users["reconfirmer"]}
        ).json()
        assert migrated_row.id not in {r["id"] for r in with_reconfirmer["data"]}


# =============================================================================
# S3 (AC-OH-30, 31, 33, 34): one header per SO for a planning-change reaction
# =============================================================================


def _book_change_row(line, product, *, qty, delivery_date) -> dict:
    return {
        "line_id": str(line.id),
        "product_id": str(product.id),
        "item_code": product.product_code,
        "qty": qty,
        "delivery_date": delivery_date,
        "stock_location": None,
        "change": CHANGE_DATE_LATER,
        "note": "Was 2026-08-25",
    }


class TestOneHeaderPerSO:
    def test_book_change_rows_land_on_existing_header_AC_OH_30(self, api):
        """AC-OH-30: a batch reaction lands on the order's EXISTING null-amendment
        header, and no second header is minted."""
        _client, world = api
        fixture = _raise_one_row(api, qty="50")
        order = fixture["order"]
        line = fixture["line"]
        existing_header_id = fixture["row"].order_inquiry_id

        service = ProjectOrderInquiryService(world.db)
        rows = [
            _book_change_row(line, world.product, qty="50", delivery_date=date(2027, 1, 1))
        ]
        inquiry = service.derive_for_book_change(
            order, rows, batch_id=_uid(), actor_user_id=world.cs_user
        )
        world.db.commit()

        assert inquiry is not None
        assert str(inquiry.id) == str(existing_header_id), (
            "a book-change reaction must reuse the order's existing amendment_id IS NULL "
            "header"
        )
        delay_row = (
            world.db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.order_inquiry_id == inquiry.id,
                OrderInquiryRow.verb == IV_DELAY,
            )
            .one()
        )
        assert str(delay_row.order_inquiry_id) == str(existing_header_id)

        header_count = (
            world.db.query(OrderInquiry)
            .filter(OrderInquiry.project_sales_order_id == order.id)
            .count()
        )
        assert header_count == 1

    def test_book_change_mints_single_null_header_when_absent_AC_OH_31(self, api):
        """AC-OH-31: an order with NO header yet gets exactly one, `amendment_id IS
        NULL`."""
        _client, world = api
        db = world.db
        core_so = _core_so(db, world.company_id)
        core_line = _core_line(
            db, core_so, world.product, world.warehouse, qty_ordered="30",
            required_date=WAS,
        )
        order = _project_so(
            db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
        )
        line = _project_line(
            db, order, line_no=1, product=world.product, core_line=core_line
        )
        db.commit()

        pre_existing = (
            db.query(OrderInquiry)
            .filter(OrderInquiry.project_sales_order_id == order.id)
            .count()
        )
        assert pre_existing == 0, (
            "the fixture must start with no header for this test to mean anything"
        )

        service = ProjectOrderInquiryService(db)
        rows = [
            _book_change_row(line, world.product, qty="30", delivery_date=date(2027, 1, 1))
        ]
        inquiry = service.derive_for_book_change(
            order, rows, batch_id=_uid(), actor_user_id=world.cs_user
        )
        db.commit()

        assert inquiry is not None
        assert inquiry.amendment_id is None
        header_count = (
            db.query(OrderInquiry)
            .filter(OrderInquiry.project_sales_order_id == order.id)
            .count()
        )
        assert header_count == 1

    def test_no_synthetic_planning_change_batch_amendment_AC_OH_33(self, api):
        """AC-OH-33: no `so_amendments` row with `from_version_kind =
        'planning_change_batch'` is written by the apply any more."""
        _client, world = api
        fixture = _raise_one_row(api, qty="50")
        order = fixture["order"]
        line = fixture["line"]

        service = ProjectOrderInquiryService(world.db)
        rows = [
            _book_change_row(line, world.product, qty="50", delivery_date=date(2027, 1, 1))
        ]
        service.derive_for_book_change(
            order, rows, batch_id=_uid(), actor_user_id=world.cs_user
        )
        world.db.commit()

        synthetic = (
            world.db.query(SOAmendment)
            .filter(
                SOAmendment.project_sales_order_id == order.id,
                SOAmendment.from_version_kind == "planning_change_batch",
            )
            .count()
        )
        assert synthetic == 0

    def test_migration_folds_planning_change_batch_headers_AC_OH_34(self, api):
        """AC-OH-34: the data migration (exercised here through the service-level helper
        the plan names, `fold_planning_change_batch_headers(db)` - the migration itself
        calls it, per the plan's own S3 design) moves a `planning_change_batch` header's
        rows onto the order's null header, keeps link `row_id`s untouched, deletes the
        emptied header and its synthetic amendment, and leaves the null header's own
        `raised_by` alone since it already existed.

        TEST-FIRST: `fold_planning_change_batch_headers` does not exist on
        `project_order_inquiry_service` yet, so this fails on `AttributeError` until the
        coder adds it - a real missing-function failure, not a fixture bug.
        """
        _client, world = api
        db = world.db
        fixture = _raise_one_row(api, qty="40")
        order = fixture["order"]
        line = fixture["line"]
        null_header = (
            db.query(OrderInquiry)
            .filter(
                OrderInquiry.project_sales_order_id == order.id,
                OrderInquiry.amendment_id.is_(None),
            )
            .one()
        )
        original_raised_by = null_header.raised_by
        assert original_raised_by is not None, "fixture sanity: the null header must be raised by somebody"

        other_user = _user(db, "ZZT Other Confirmer")
        amendment = SOAmendment(
            id=_uid(),
            company_id=order.company_id,
            project_sales_order_id=order.id,
            from_version_kind="planning_change_batch",
            from_version_id=_uid(),
            verb_summary={"DELAY": 1, "ADVANCE": 1},
            status=AMENDMENT_PUBLISHED,
            published_at=datetime.utcnow(),
        )
        db.add(amendment)
        db.flush()
        batch_header = OrderInquiry(
            id=_uid(),
            company_id=order.company_id,
            project_sales_order_id=order.id,
            amendment_id=amendment.id,
            state=INQUIRY_RAISED,
            raised_by=other_user,
        )
        db.add(batch_header)
        db.flush()

        row1 = OrderInquiryRow(
            id=_uid(),
            company_id=order.company_id,
            order_inquiry_id=batch_header.id,
            so_line_id=line.id,
            item_code=world.product.product_code,
            qty=Decimal("20"),
            delivery_date=date(2027, 1, 1),
            verb=IV_DELAY,
            state=INQUIRY_RAISED,
            ack_state=ACK_ACKNOWLEDGED,
            acknowledged_by=other_user,
            acknowledged_at=datetime.utcnow(),
        )
        row2 = OrderInquiryRow(
            id=_uid(),
            company_id=order.company_id,
            order_inquiry_id=batch_header.id,
            so_line_id=line.id,
            item_code=world.product.product_code,
            qty=Decimal("15"),
            delivery_date=date(2027, 2, 1),
            verb=IV_ADVANCE,
            state=INQUIRY_RAISED,
            ack_state=ACK_ACKNOWLEDGED,
            acknowledged_by=other_user,
            acknowledged_at=datetime.utcnow(),
        )
        db.add_all([row1, row2])
        db.flush()

        po, po_line = _open_po_line(world, qty="15")
        link = OrderInquiryLink(
            id=_uid(),
            company_id=order.company_id,
            row_id=row1.id,
            po_line_id=po_line.id,
            document=po.po_number,
            qty=Decimal("15"),
        )
        db.add(link)
        db.flush()
        db.commit()

        link_id_before = link.id
        row1_id_before = row1.id
        batch_header_id = batch_header.id
        amendment_id = amendment.id

        poi_service.fold_planning_change_batch_headers(db)
        db.commit()

        db.refresh(row1)
        db.refresh(row2)
        assert str(row1.order_inquiry_id) == str(null_header.id)
        assert str(row2.order_inquiry_id) == str(null_header.id)

        surviving_link = (
            db.query(OrderInquiryLink).filter(OrderInquiryLink.id == link_id_before).one()
        )
        assert str(surviving_link.row_id) == str(row1_id_before)

        assert db.query(OrderInquiry).filter(OrderInquiry.id == batch_header_id).first() is None
        assert db.query(SOAmendment).filter(SOAmendment.id == amendment_id).first() is None

        db.refresh(null_header)
        assert str(null_header.raised_by) == str(original_raised_by), (
            "the null header already existed, so its own raised_by must not be overwritten"
        )


# =============================================================================
# S4 (AC-OH-40..42): Was/Now on the fresh row raised after a redirect
# =============================================================================


def _settle_capturing_result(world, fixture, *, qty, required_date=NOW):
    """`test_order_inquiry_handshake._settle`, but returns the `confirm()` result too - S4
    (AC-OH-44) needs `result['settled_in_place']`, which the shared helper discards."""
    supply = ProjectSupplyService(world.db)
    body = ConfirmSupplyBody(
        lines=[
            ConfirmLine(
                project_line_id=str(fixture["line"].id),
                timely_spo_qty="0",
                reserve=[],
                borrow=[],
                buy_qty=str(qty),
            )
        ]
    )
    fixture["core_line"].qty_ordered = Decimal(str(qty))
    fixture["core_line"].required_date = required_date
    fixture["line"].qty = Decimal(str(qty))
    fixture["line"].delivery_date = required_date
    world.db.flush()
    result = supply.confirm(
        fixture["order"],
        body,
        actor_user_id=world.cs_user,
        settle_in_place_line_ids=[str(fixture["line"].id)],
    )
    world.db.commit()
    return result


class TestWasNowAfterRedirect:
    def test_fresh_row_after_redirect_carries_was_now_AC_OH_40(self, api):
        """AC-OH-40: the fresh ORDER row carries `previous_qty`/`previous_delivery_date`
        off the released row, and a note naming the quantity, the document and
        'received'."""
        _client, world = api
        fixture = _redirected_fixture(api)
        row = fixture["redirected_row"]
        new_row = fixture["new_row"]
        allocation = fixture["received_allocation"]

        assert row.redirected_to_pool is True
        assert new_row.previous_qty is not None, (
            "the fresh row must carry the released row's Was/Now"
        )
        assert Decimal(str(new_row.previous_qty)) == Decimal("182")
        assert new_row.previous_delivery_date == WAS
        note = new_row.note or ""
        assert "Replaces 182 used" in note
        assert allocation.spo_number in note
        assert "received" in note

    def test_later_reconfirm_does_not_restamp_AC_OH_41(self, api):
        """AC-OH-41: a later reconfirm of the same line, with no new redirect, must not
        keep re-stamping the earlier release's Was/Now onto the newest row."""
        _client, world = api
        fixture = _redirected_fixture(api)
        new_row = fixture["new_row"]
        assert new_row.previous_qty is not None and Decimal(str(new_row.previous_qty)) == Decimal("182"), (
            "sanity: the fresh row must carry the release's Was/Now for this test to "
            "mean anything"
        )

        _settle_capturing_result(world, fixture, qty="300", required_date=date(2027, 6, 1))

        world.db.refresh(new_row)
        assert Decimal(str(new_row.qty)) == Decimal("300")
        assert Decimal(str(new_row.previous_qty)) != Decimal("182"), (
            "a later reconfirm with no new redirect must not restamp the old release's "
            "Was/Now"
        )
        assert Decimal(str(new_row.previous_qty)) == Decimal("220"), (
            "the settle's own previous value, not the earlier redirect's"
        )

    def test_two_released_rows_sum_AC_OH_42(self, api):
        """AC-OH-42: two rows on the SAME line released in one decision sum their qty
        onto the fresh row's `previous_qty`, and the note names each document.

        Shaped as two separate still-owed ORDER rows on one line (mirroring
        `_settle_row_in_place`'s own "two still-owed rows" decline, which sends the line
        to the netting loop) rather than one row with two received links - the plan's own
        wording is "two released ROWS on the line", and today's only
        `_redirect_row_if_received` call site handles exactly one live row at a time, so
        catching both means the netting loop's own PARTLY_LINKED handling has to redirect
        each of them too.
        """
        _client, world = api
        fixture = _raise_one_row(api, qty="100")
        row1 = fixture["row"]
        line = fixture["line"]

        alloc1 = _received_spo(world, qty="90")
        _link_row_to(world, row1, qty="90", document=alloc1.spo_number, allocation=alloc1)
        world.db.refresh(row1)
        assert row1.state == INQUIRY_PARTLY_LINKED, "fixture sanity"

        row2 = OrderInquiryRow(
            id=_uid(),
            company_id=world.company_id,
            order_inquiry_id=row1.order_inquiry_id,
            so_line_id=line.id,
            item_code=row1.item_code,
            qty=Decimal("80"),
            delivery_date=row1.delivery_date + timedelta(days=3),
            verb=IV_ORDER,
            state=INQUIRY_RAISED,
            ack_state=ACK_ACKNOWLEDGED,
            acknowledged_by=world.cs_user,
            acknowledged_at=datetime.utcnow(),
        )
        world.db.add(row2)
        world.db.flush()
        alloc2 = _received_spo(world, qty="70")
        _link_row_to(world, row2, qty="70", document=alloc2.spo_number, allocation=alloc2)
        world.db.refresh(row2)
        assert row2.state == INQUIRY_PARTLY_LINKED, "fixture sanity"

        _settle_capturing_result(world, fixture, qty="300", required_date=date(2027, 4, 1))

        world.db.refresh(row1)
        world.db.refresh(row2)
        assert row1.redirected_to_pool is True
        assert row2.redirected_to_pool is True

        new_row = next(
            r
            for r in _rows_for_line(world, line)
            if str(r.id) not in {str(row1.id), str(row2.id)}
        )
        assert Decimal(str(new_row.previous_qty)) == Decimal("180")
        assert new_row.previous_delivery_date == row1.delivery_date
        note = new_row.note or ""
        assert alloc1.spo_number in note
        assert alloc2.spo_number in note


# =============================================================================
# R4 revised (AC-OH-44, 45): no DELAY/ADVANCE row for a line the confirm restated
# =============================================================================


class TestNoDelayRowWhenLineRestated:
    def test_no_delay_row_after_redirect_AC_OH_44(self, api):
        """AC-OH-44: a line whose confirm released a received row and raised a fresh
        ORDER row with Was/Now must get NO DELAY/ADVANCE row - the redirected line id has
        to join `settled_in_place`, the same list that already suppresses the reaction
        for a settle-in-place line (one seam, no new flag, per the plan)."""
        _client, world = api
        fixture = _raise_one_row(api, qty="182")
        row = fixture["row"]
        line = fixture["line"]
        allocation = _received_spo(world, qty="158")
        _link_row_to(world, row, qty="158", document=allocation.spo_number, allocation=allocation)
        world.db.refresh(row)
        assert row.state == INQUIRY_PARTLY_LINKED, "fixture sanity"

        result = _settle_capturing_result(world, fixture, qty="220", required_date=REPLAN_DATE)
        settled_in_place = list(result.get("settled_in_place") or [])
        assert str(line.id) in settled_in_place, (
            "a redirected line must join settled_in_place so the DELAY reaction is "
            "suppressed for it"
        )

        live_rows = [
            SimpleNamespace(
                kind="delayed",
                project_line_id=str(line.id),
                core_line_id=str(fixture["core_line"].id),
                item_code=world.product.product_code,
                from_json={"required_date": WAS.isoformat()},
                to_json={"required_date": REPLAN_DATE.isoformat(), "qty": "220"},
                held_json={},
            )
        ]
        demand_rows, counts = _oi_demand_rows(
            world.db, live_rows, fixture["core_so"].so_number, settled_in_place
        )
        assert demand_rows == [], "no DELAY/ADVANCE row for a line the confirm restated"
        assert "DELAY" not in counts and "ADVANCE" not in counts

        world.db.refresh(row)
        new_row = next(
            r for r in _rows_for_line(world, line) if str(r.id) != str(row.id)
        )
        assert new_row.verb == IV_ORDER
        assert new_row.previous_qty is not None, (
            "the ORDER row's own (i) is what now carries the date change (R4 revised)"
        )

    def test_delay_row_still_written_when_line_not_restated_AC_OH_45(self, api):
        """AC-OH-45 (guard): a line the confirm did NOT restate - here, a lone PLACED row
        with no link, which `_settle_row_in_place` declines - still gets its DELAY row,
        unchanged."""
        _client, world = api
        fixture = _raise_one_row(api, qty="50")
        row = fixture["row"]
        line = fixture["line"]
        row.state = INQUIRY_PLACED
        world.db.flush()
        world.db.commit()

        result = _settle_capturing_result(
            world, fixture, qty="50", required_date=date(2027, 5, 1)
        )
        settled_in_place = list(result.get("settled_in_place") or [])
        assert str(line.id) not in settled_in_place, (
            "sanity: a lone placed row with no link cannot be settled in place"
        )

        live_rows = [
            SimpleNamespace(
                kind="delayed",
                project_line_id=str(line.id),
                core_line_id=str(fixture["core_line"].id),
                item_code=world.product.product_code,
                from_json={"required_date": WAS.isoformat()},
                to_json={"required_date": "2027-05-01", "qty": "50"},
                held_json={},
            )
        ]
        demand_rows, counts = _oi_demand_rows(
            world.db, live_rows, fixture["core_so"].so_number, settled_in_place
        )
        assert len(demand_rows) == 1
        assert demand_rows[0]["change"] == CHANGE_DATE_LATER
        assert counts.get("DELAY") == 1


# =============================================================================
# S5 (AC-OH-50..52): hide cancelled by default
# =============================================================================


@pytest.fixture()
def oi_api():
    from app.models.base import company_scope
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _wl_sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user_id = _user(db, f"{WL_MARKER} Eling")
        seeded = _wl_seed(db, company_id, user_id)
        client, originals = _wl_client(db, user_id, WL_READ_ONLY)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, seeded
        finally:
            _wl_restore(originals)


class TestHideCancelledByDefault:
    def test_list_without_state_excludes_cancelled_AC_OH_50(self, oi_api):
        client, db, company_id, seeded = oi_api
        inquiry = _authored_inquiry(db, seeded)
        cancelled_row = _wl_row(
            db, company_id, inquiry, item_code=f"{WL_MARKER}-cancelled-row", qty="4",
            state=INQUIRY_CANCELLED,
        )
        db.commit()

        body = client.get(WL_LIST).json()
        ids = {row["id"] for row in body["data"]}
        assert cancelled_row.id not in ids

        summary = client.get(f"{WL_LIST}/summary").json()
        assert summary["total_rows"] == 3, (
            "cancelled must not count toward the visible total"
        )

    def test_state_cancelled_returns_only_cancelled_AC_OH_51(self, oi_api):
        client, db, company_id, seeded = oi_api
        inquiry = _authored_inquiry(db, seeded)
        cancelled_row = _wl_row(
            db, company_id, inquiry, item_code=f"{WL_MARKER}-cancelled-row-2", qty="4",
            state=INQUIRY_CANCELLED,
        )
        db.commit()

        body = client.get(WL_LIST, params={"state": INQUIRY_CANCELLED}).json()
        assert [row["id"] for row in body["data"]] == [cancelled_row.id]

    def test_facets_still_count_cancelled_AC_OH_52(self, oi_api):
        client, db, company_id, seeded = oi_api
        inquiry = _authored_inquiry(db, seeded)
        _wl_row(
            db, company_id, inquiry, item_code=f"{WL_MARKER}-cancelled-row-3", qty="4",
            state=INQUIRY_CANCELLED,
        )
        db.commit()

        summary = client.get(f"{WL_LIST}/summary").json()
        assert summary["by_state"]["cancelled"] == 1
