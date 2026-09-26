"""Fix round for the order inquiries header lane - security fixes, a raise-history gap
on two writers, the import clock convention, migration re-run/downgrade safety, and the
deferred Unlink for OI lines (`PLAN-oi-header-list-detail.md`,
`oi-header-list-detail-acceptance-criteria.md`).

TEST-FIRST, written against the captain's own fix-round test list, with the coder idle.
Every test below must fail today for a REAL reason - a missing raise-history row, a wrong
month, an `AttributeError` on a function the migration only has inline, an unknown
action key, a missing `max_length`, or a 200 where a 404/422 belongs - never an import
typo or a fixture bug.

Seeding reuses the lane's own helpers rather than inventing a second approach:
`tests/test_oi_header_list.py` (`_header`, `_client`, HTTP fixtures), `tests/
test_oi_monthly_number_and_raises.py` (imported as `monthno`: `_header`/`_pso`/`_user`/
`_sorento`/`_migration_module`, the lightweight PSO-only seed and the migration loader),
`tests/test_project_order_inquiry_import_migration.py` (`world`/`sheet`/`D_OCT`, the
Excel-import harness) and `tests/test_oi_sheet_pairing_repair.py` (`_apply`, `importer.
apply` with a file name). Postgres only, via `tests/_pg_fixture.py`'s `blank_session` -
an EMPTY scratch schema, never the shared prod-copy database - every FK seeded here,
`zzt-oi-fixround`-prefixed.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

import pytest

from app.models.base import company_scope
from app.models.project_so import (
    INQUIRY_RAISED,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRaise,
    ProjectSalesOrder,
    SOAmendment,
    SO_STATUS_PUBLISHED,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from ._pg_fixture import blank_session
from . import test_oi_monthly_number_and_raises as monthno
from .test_oi_header_list import (
    BASE,
    HEADERS,
    MARKER as HL_MARKER,
    VIEW,
    _agent,
    _client,
    _customer,
    _header,
    _restore,
    _sorento,
    _uid,
    _user,
    api as list_api,
)
from .test_oi_sheet_pairing_repair import _apply
from .test_project_order_inquiry import (
    _line as _amend_line,
    _product as _amend_product,
    _project as _amend_project,
    _sales_order as _amend_sales_order,
    _user as _amend_user,
)
from .test_project_order_inquiry_import_migration import D_OCT, sheet, world

MARKER = "zzt-oi-fixround"
MY_TZ = ZoneInfo("Asia/Kuala_Lumpur")
ACTION = "projects.order_inquiry.action"


def _sorento_pg(db) -> str:
    from sqlalchemy import text

    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


# =============================================================================
# S4a - an amendment-raised header gets a raise-history row too
# =============================================================================


def test_amendment_derived_header_gets_one_raised_row_AC_S4a():
    """`_write` mints the header directly (`inquiry is None` branch) when it is reached
    through `derive_for_amendment` - unlike `ensure_inquiry`, it never calls
    `_record_raise`. So this header's `order_inquiry_raises` is empty today; the plan (S1)
    says every raise/reconfirm, amendment path included, adds exactly one row."""
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento_pg(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _amend_user(db, f"{MARKER} Amend Owner")
        project = _amend_project(db, company_id, owner)
        order = _amend_sales_order(
            db, project, status=SO_STATUS_PUBLISHED, doc_no=f"{MARKER}-SO-AMEND"
        )
        product = _amend_product(db, f"{MARKER}-AMEND")
        line = _amend_line(db, order, product, "10", date(2027, 1, 7))
        amendment = SOAmendment(
            id=_uid(),
            company_id=company_id,
            project_sales_order_id=order.id,
            delta_json={
                "rows": [
                    {
                        "so_line_id": line.id,
                        "product_id": product.id,
                        "product_code": product.product_code,
                        "verb": "DELAY",
                        "from_value": "2026-07-01",
                        "to_value": "2027-01-07",
                        "qty": "10",
                    }
                ]
            },
        )
        db.add(amendment)
        db.flush()

        inquiry = ProjectOrderInquiryService(db).derive_for_amendment(
            amendment, actor_user_id=owner
        )
        db.commit()

        rows = (
            db.query(OrderInquiryRaise)
            .filter(OrderInquiryRaise.order_inquiry_id == inquiry.id)
            .all()
        )
        assert len(rows) == 1, (
            "an amendment-derived header must gain a raise-history row too "
            f"(found {len(rows)})"
        )
        assert rows[0].kind == "raised"
        assert rows[0].raised_by == owner


# =============================================================================
# S4b - an import-created header gets a raise-history row too
# =============================================================================


def test_import_created_header_gets_one_raised_row_AC_S4b():
    """`_Raiser._inquiry` (the sheet import's own header minter) also writes the
    `OrderInquiry` directly, never through `ensure_inquiry`/`_record_raise` - so an
    import-raised header's raise history is empty today too."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="30")
        data = sheet(
            [(order.so_number, w.product.product_code, 20, D_OCT, w.warehouse.warehouse_code, "")]
        )
        result = _apply(w, data, file_name=f"{MARKER}-s4b.xlsx")
        assert result["rows_raised"] == 1, result

        mirror = w.mirror_of(line)
        header = (
            w.db.query(OrderInquiry)
            .filter(OrderInquiry.project_sales_order_id == mirror.project_sales_order_id)
            .one()
        )
        rows = (
            w.db.query(OrderInquiryRaise)
            .filter(OrderInquiryRaise.order_inquiry_id == header.id)
            .all()
        )
        assert len(rows) == 1, (
            "the sheet import's own header must gain a raise-history row too "
            f"(found {len(rows)})"
        )
        assert rows[0].kind == "raised"


# =============================================================================
# S5a - the import's own clock convention (naive MYT stored, then double-shifted)
# =============================================================================


def test_import_header_at_2000_myt_numbers_under_september_not_october_AC_S5a():
    """The import stamps `raised_at = to_naive_datetime(datetime.now(MALAYSIA_TZ))` - a
    naive MYT WALL CLOCK - while `_stamp_inquiry_no` (`app/models/project_so.py`) treats
    a naive value as UTC and adds +8 to reach MYT for the month. Freezing the import's
    own clock to 2026-09-30 20:00 MYT (still firmly September on the wall) must not
    number the header under October - which is what happens today once that value is
    treated as UTC and shifted forward another 8 hours."""
    frozen_myt_naive = datetime(2026, 9, 30, 20, 0)
    with mock.patch(
        "app.services.project_order_inquiry_import_service._now",
        return_value=frozen_myt_naive,
    ):
        with world() as w:
            order = w.order()
            line = w.line(order, qty_ordered="30")
            data = sheet(
                [(order.so_number, w.product.product_code, 20, D_OCT, w.warehouse.warehouse_code, "")]
            )
            result = _apply(w, data, file_name=f"{MARKER}-s5a.xlsx")
            assert result["rows_raised"] == 1, result

            mirror = w.mirror_of(line)
            header = (
                w.db.query(OrderInquiry)
                .filter(OrderInquiry.project_sales_order_id == mirror.project_sales_order_id)
                .one()
            )
            assert header.inquiry_no.startswith("OI-2609-"), (
                f"20:00 MYT on 30 Sep must still number under September, got "
                f"{header.inquiry_no!r}"
            )


def test_import_and_board_headers_agree_on_the_naive_utc_convention_AC_S5a():
    """One clock convention for `raised_at`: naive UTC, the convention every other writer
    on this table uses (`OrderInquiry.raised_at`'s own server default `func.now()`, and
    `OrderInquiryLink.linked_at` beside it). An import header and a board-raised header
    created at the SAME real instant must therefore store the identical value - today the
    import stores the MYT wall clock instead, eight hours off."""
    utc_instant = datetime(2026, 9, 30, 12, 0)  # naive UTC - the module's own convention
    myt_wall_clock_at_that_instant = (
        utc_instant.replace(tzinfo=timezone.utc).astimezone(MY_TZ).replace(tzinfo=None)
    )
    with mock.patch(
        "app.services.project_order_inquiry_import_service._now",
        return_value=myt_wall_clock_at_that_instant,
    ):
        with world() as w:
            order = w.order()
            line = w.line(order, qty_ordered="30")
            data = sheet(
                [(order.so_number, w.product.product_code, 20, D_OCT, w.warehouse.warehouse_code, "")]
            )
            result = _apply(w, data, file_name=f"{MARKER}-s5a-equal.xlsx")
            assert result["rows_raised"] == 1, result

            mirror = w.mirror_of(line)
            import_header = (
                w.db.query(OrderInquiry)
                .filter(OrderInquiry.project_sales_order_id == mirror.project_sales_order_id)
                .one()
            )

            board_pso = ProjectSalesOrder(
                id=_uid(),
                company_id=w.company_id,
                provisional_ref=f"{MARKER}-PSO-BOARD-{_uid()[:8]}",
                status="draft",
            )
            w.db.add(board_pso)
            w.db.flush()
            board_header = OrderInquiry(
                id=_uid(),
                company_id=w.company_id,
                project_sales_order_id=board_pso.id,
                state=INQUIRY_RAISED,
                raised_at=utc_instant,
            )
            w.db.add(board_header)
            w.db.commit()
            w.db.refresh(import_header)

            assert import_header.raised_at == board_header.raised_at, (
                "one clock convention (naive UTC) for every writer: the import stores "
                f"{import_header.raised_at} (a naive MYT wall clock) instead of "
                f"{board_header.raised_at} (naive UTC, the board writer's own value)"
            )


# =============================================================================
# S5b - the migration's own month boundary, on naive-UTC legacy rows
# =============================================================================


def test_renumber_inquiries_month_boundary_reads_myt_off_naive_utc_AC_S5b():
    """`renumber_inquiries`'s own SQL converts `raised_at AT TIME ZONE 'UTC' AT TIME ZONE
    'Asia/Kuala_Lumpur'` - the SAME single conversion `_stamp_inquiry_no` uses for a
    live insert. A legacy header stored (correctly, naive UTC) at 2026-09-30 17:30 is
    2026-10-01 01:30 MYT and must number under October; one at 2026-09-30 15:00 UTC is
    2026-09-30 23:00 MYT and must stay September. Written to guard the ONE correct
    conversion against a coder who "fixes" S5a's double-shift bug in this function
    instead of at the import's own write site, which would then under-shift these."""
    with blank_session() as db:
        company_id = monthno._sorento(db)
        late = monthno._header(
            db, company_id, inquiry_no="OI-000060", raised_at=datetime(2026, 9, 30, 17, 30)
        )
        early = monthno._header(
            db, company_id, inquiry_no="OI-000061", raised_at=datetime(2026, 9, 30, 15, 0)
        )
        db.commit()

        module = monthno._migration_module()
        module.renumber_inquiries(db.connection())
        db.commit()
        db.expire_all()

        refreshed_late = db.query(OrderInquiry).filter(OrderInquiry.id == late.id).one()
        refreshed_early = db.query(OrderInquiry).filter(OrderInquiry.id == early.id).one()
        assert refreshed_late.inquiry_no.startswith("OI-2610-"), refreshed_late.inquiry_no
        assert refreshed_early.inquiry_no.startswith("OI-2609-"), refreshed_early.inquiry_no


# =============================================================================
# S2 - renumber_inquiries is re-runnable after new (dated) headers exist
# =============================================================================


def test_renumber_inquiries_is_re_runnable_after_a_new_header_exists_AC_S2():
    """A second run, after a genuinely NEW header (born through the ORM insert
    listener, dated format, `legacy_inquiry_no` NULL) exists alongside already-renumbered
    legacy ones, must not raise and must not touch or duplicate anything. Today's
    `WHERE legacy_inquiry_no IS NULL` catches that new header on its own (nothing else
    still qualifies), assigns it rank 1 of its own one-row partition, and drives it
    through the SAME `OI-2609-0001` an already-renumbered header now holds - a real
    collision on `uq_project_order_inquiry_no`."""
    with blank_session() as db:
        company_id = monthno._sorento(db)
        for i, legacy in enumerate(["OI-000070", "OI-000071", "OI-000072"]):
            monthno._header(
                db, company_id, inquiry_no=legacy, raised_at=datetime(2026, 9, 1) + timedelta(days=i)
            )
        db.commit()

        module = monthno._migration_module()
        module.renumber_inquiries(db.connection())
        db.commit()
        db.expire_all()

        fresh = monthno._header(db, company_id, raised_at=datetime(2026, 9, 20))
        db.commit()
        assert fresh.inquiry_no.startswith("OI-2609-"), fresh.inquiry_no
        assert fresh.legacy_inquiry_no is None

        # Must not raise (IntegrityError on the unique constraint) and must not corrupt
        # the fresh header's own already-dated number.
        module.renumber_inquiries(db.connection())
        db.commit()
        db.expire_all()

        headers = (
            db.query(OrderInquiry)
            .filter(OrderInquiry.company_id == company_id)
            .order_by(OrderInquiry.raised_at.asc())
            .all()
        )
        numbers = [h.inquiry_no for h in headers]
        assert len(numbers) == len(set(numbers)), f"duplicate OI numbers: {numbers}"
        refreshed_fresh = db.query(OrderInquiry).filter(OrderInquiry.id == fresh.id).one()
        assert refreshed_fresh.inquiry_no == fresh.inquiry_no, (
            "a second run must not renumber an already-dated header"
        )


# =============================================================================
# S3 - downgrade safety: restoring legacy numbers must stay unique
# =============================================================================


def test_downgrade_restore_legacy_numbers_keeps_every_number_unique_AC_S3():
    """`downgrade()` restores old numbers with an inline `UPDATE ... WHERE
    legacy_inquiry_no IS NOT NULL` today - no module-level function a test can drive, so
    this fails on `AttributeError` before any of the assertions below run. Once exposed
    as `restore_legacy_numbers(bind)`: every restored legacy header gets its own old
    number back, no two headers of the company share a number afterwards, and the ONE
    header born AFTER the migration (never held a legacy number) lands on a legacy-style
    number strictly PAST the highest restored one - the old minter's own rule was MAX+1,
    so anything at or below the restored max is a number it could hand out again."""
    with blank_session() as db:
        company_id = monthno._sorento(db)
        for i, legacy in enumerate(["OI-000080", "OI-000081", "OI-000082"]):
            monthno._header(
                db, company_id, inquiry_no=legacy, raised_at=datetime(2026, 9, 1) + timedelta(days=i)
            )
        db.commit()

        module = monthno._migration_module()
        module.backfill_raises(db.connection())
        module.renumber_inquiries(db.connection())
        db.commit()
        db.expire_all()

        post_migration = monthno._header(db, company_id, raised_at=datetime(2026, 9, 20))
        db.commit()

        module.restore_legacy_numbers(db.connection())
        db.commit()
        db.expire_all()

        headers = db.query(OrderInquiry).filter(OrderInquiry.company_id == company_id).all()
        numbers = [h.inquiry_no for h in headers]
        assert len(numbers) == len(set(numbers)), f"duplicate inquiry_no after restore: {numbers}"

        legacy_headers = [h for h in headers if h.id != post_migration.id]
        assert sorted(h.inquiry_no for h in legacy_headers) == [
            "OI-000080",
            "OI-000081",
            "OI-000082",
        ]

        restored_tails = [80, 81, 82]
        refreshed_post = db.query(OrderInquiry).filter(OrderInquiry.id == post_migration.id).one()
        assert refreshed_post.inquiry_no.startswith("OI-"), refreshed_post.inquiry_no
        post_tail = int(refreshed_post.inquiry_no.rsplit("-", 1)[-1])
        assert post_tail > max(restored_tails), (
            f"the post-migration header's restored number {refreshed_post.inquiry_no!r} "
            "must sit past the highest legacy number, or the old MAX+1 minter would "
            "reissue it to a brand new header"
        )


# =============================================================================
# N3 - raised_by / agent are unbounded query params today (422 missing)
# =============================================================================


def test_raised_by_over_200_chars_is_422_AC_N3(list_api):
    client, _db, _company_id = list_api
    response = client.get(HEADERS, params={"raised_by": "x" * 201})
    assert response.status_code == 422, response.text


def test_agent_over_200_chars_is_422_AC_N3(list_api):
    client, _db, _company_id = list_api
    response = client.get(HEADERS, params={"agent": "x" * 201})
    assert response.status_code == 422, response.text


# =============================================================================
# N2 - related-documents 404 boundary (today: 200 with empty lists)
# =============================================================================


def test_related_documents_unknown_id_is_404_AC_N2(list_api):
    client, _db, _company_id = list_api
    response = client.get(f"{HEADERS}/{_uid()}/related-documents")
    assert response.status_code == 404, response.text


def test_related_documents_another_companys_header_is_404_AC_N2(list_api):
    from app.models.company import Company

    client, db, company_id = list_api
    other = Company(id=_uid(), name=f"{HL_MARKER} Other Co", code=f"ZZT{_uid()[:6]}")
    db.add(other)
    db.flush()
    theirs = _header(db, other.id)

    response = client.get(f"{HEADERS}/{theirs['inquiry'].id}/related-documents")
    assert response.status_code == 404, response.text


# =============================================================================
# UL - server-deferred Unlink for OI lines (AC-DP-06)
# =============================================================================

UNLINK_KEY = "order_inquiry_row.unlink"
PENDING_BASE = "/api/v1/pending-actions"


def _po_line_for_link(db, company_id: str):
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
    from .test_oi_header_list import _product

    supplier = Supplier(
        id=_uid(), company_id=company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} Supplier",
    )
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        id=_uid(), company_id=company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id, issue_date=date(2026, 6, 1), status="active",
    )
    db.add(po)
    db.flush()
    product = _product(db)
    line = PurchaseOrderLine(
        id=_uid(), company_id=company_id, purchase_order_id=po.id, product_id=product.id,
        qty_ordered=Decimal("50"), qty_received=Decimal("0"), line_status="open",
    )
    db.add(line)
    db.flush()
    return line


def _link_row(db, row, po_line, *, qty="5"):
    link = OrderInquiryLink(
        id=_uid(), company_id=row.company_id, row_id=row.id, po_line_id=po_line.id,
        document=f"{MARKER}-doc", qty=Decimal(str(qty)),
    )
    db.add(link)
    db.flush()
    return link


def _seed_two_linked_rows(db, company_id: str):
    """A header with two rows, each linked to its own PO line - Unlink selected ticks
    ONE row and must leave the other's links untouched."""
    seeded = _header(
        db, company_id, rows=[{"item_code": f"{MARKER}-A"}, {"item_code": f"{MARKER}-B"}]
    )
    po_line_a = _po_line_for_link(db, company_id)
    po_line_b = _po_line_for_link(db, company_id)
    link_a = _link_row(db, seeded["rows"][0], po_line_a)
    link_b = _link_row(db, seeded["rows"][1], po_line_b)
    db.commit()
    return seeded, link_a, link_b


def _park(client, action_key, entity_type, entity_id, **payload):
    return client.post(
        PENDING_BASE,
        json={
            "action_key": action_key,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
        },
    )


def _lapse(db, action_id: str) -> None:
    from app.models.sla import SlaFormAction

    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)},
        synchronize_session=False,
    )
    db.commit()


def _sweep(db) -> dict:
    from app.services.form_action_service import FormActionService

    with company_scope(db, None):
        return FormActionService(db).commit_due()


def _links_of(db, row_id: str) -> list:
    return (
        db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row_id).all()
    )


def test_park_order_inquiry_row_unlink_is_accepted_not_unknown_action_UL(list_api):
    """The mechanism is generic (`/api/v1/pending-actions`), but no `order_inquiry_row.
    unlink` action is registered in `app/services/record_actions.py` yet - today this
    404/400s as "Unknown action", not 202."""
    _view_client, db, company_id = list_api
    seeded, link_a, _link_b = _seed_two_linked_rows(db, company_id)
    action_client, originals = _client(db, _user(db, f"{MARKER} Buyer"), [VIEW, ACTION])
    try:
        parked = _park(
            action_client, UNLINK_KEY, "order_inquiry_row", str(seeded["rows"][0].id)
        )
        assert parked.status_code == 202, parked.text
    finally:
        _restore(originals)


def test_committing_unlink_removes_only_the_ticked_rows_links_UL(list_api):
    _view_client, db, company_id = list_api
    seeded, link_a, link_b = _seed_two_linked_rows(db, company_id)
    row_a, row_b = seeded["rows"]
    action_client, originals = _client(db, _user(db, f"{MARKER} Buyer"), [VIEW, ACTION])
    try:
        parked = _park(action_client, UNLINK_KEY, "order_inquiry_row", str(row_a.id))
        assert parked.status_code == 202, parked.text
        _lapse(db, parked.json()["id"])
        outcome = _sweep(db)
        assert outcome.get("committed") == 1, outcome

        db.expire_all()
        assert _links_of(db, row_a.id) == [], "the ticked row's link must be gone"
        assert len(_links_of(db, row_b.id)) == 1, "a second row's link must be untouched"
    finally:
        _restore(originals)


def test_cancelling_unlink_leaves_links_intact_UL(list_api):
    _view_client, db, company_id = list_api
    seeded, link_a, _link_b = _seed_two_linked_rows(db, company_id)
    row_a = seeded["rows"][0]
    action_client, originals = _client(db, _user(db, f"{MARKER} Buyer"), [VIEW, ACTION])
    try:
        parked = _park(action_client, UNLINK_KEY, "order_inquiry_row", str(row_a.id))
        assert parked.status_code == 202, parked.text
        cancelled = action_client.post(f"{PENDING_BASE}/{parked.json()['id']}/cancel")
        assert cancelled.status_code == 200, cancelled.text

        db.expire_all()
        assert len(_links_of(db, row_a.id)) == 1, "cancelling must leave the link in place"
    finally:
        _restore(originals)


def test_unlink_requires_order_inquiry_action_permission_UL(list_api):
    _view_client, db, company_id = list_api
    seeded, _link_a, _link_b = _seed_two_linked_rows(db, company_id)
    row_a = seeded["rows"][0]
    # VIEW only - no ACTION grant.
    no_action_client, originals = _client(db, _user(db, f"{MARKER} Viewer"), [VIEW])
    try:
        parked = _park(no_action_client, UNLINK_KEY, "order_inquiry_row", str(row_a.id))
        assert parked.status_code == 403, parked.text
    finally:
        _restore(originals)


def test_unlink_of_another_companys_row_is_refused_UL(list_api):
    from app.models.company import Company

    _view_client, db, company_id = list_api
    other = Company(id=_uid(), name=f"{MARKER} Other Co", code=f"ZZT{_uid()[:6]}")
    db.add(other)
    db.flush()
    seeded, link_a, _link_b = _seed_two_linked_rows(db, other.id)
    row_a = seeded["rows"][0]

    action_client, originals = _client(db, _user(db, f"{MARKER} Buyer"), [VIEW, ACTION])
    try:
        with company_scope(db, frozenset({company_id})):
            parked = _park(action_client, UNLINK_KEY, "order_inquiry_row", str(row_a.id))
            assert parked.status_code == 202, parked.text
            _lapse(db, parked.json()["id"])
            _sweep(db)

        db.expire_all()
        with company_scope(db, frozenset({other.id})):
            assert len(_links_of(db, row_a.id)) == 1, (
                "a company-A requester must not be able to unlink a company-B row"
            )
    finally:
        _restore(originals)
