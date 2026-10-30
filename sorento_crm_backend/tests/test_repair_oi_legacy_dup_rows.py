"""OI-LEGACY-DUP-REPAIR: legacy sheet rows squatting another sales order line.

Contract: `documentation/plans/scm/oi-legacy-dup-repair-acceptance-criteria.md`, AC-1 to
AC-10, one test (or two) per criterion, named for it. Plan:
`documentation/plans/scm/PLAN-oi-legacy-dup-repair-30oct.md`.

The shape on the 28 Oct prod copy (OI-2609-0676 / M9713SS): the 2026 book's OCT 26 tab
stated the same SO / item / 2 / 2026-10-07 twice (sheet rows 630 and 662). Row 630 took
the matching line; row 662 fell through to a line of 26 due 2027-04-07. The 2027 book's
APR 27 row 166 (26 / 2027-04-07, that line's own instruction) was then skipped
`already_raised`. Every scenario here is seeded directly - sales order lines, inquiry
rows, import jobs and their job rows - because CI's database is empty and the importer
that produced this shape (the pre-22-Sep five-pass pick) no longer exists.

Postgres only (`tests/_pg_fixture.py`). The script is loaded from its file, as
`tests/test_oi_stale_link_state_repair.py` loads its sibling.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.audit import AuditLog
from app.models.base import company_scope
from app.models.job import ImportJob, ImportJobRow
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiryLink,
    OrderInquiryReserveRequest,
    OrderInquiryReserveRequestRow,
    OrderInquiryRow,
    ProjectSalesOrderLine,
)
from app.services import project_seed_service

from ._pg_fixture import blank_session
from .test_order_inquiry_place_on_po import _po_line, _seed_world, _sorento, _user

STAMP_2026 = "Migrated from order inquiry sheet JAN - DEC 2026 ORDERabc.xlsx"
STAMP_2027 = "Migrated from order inquiry sheet JAN - DEC ORDER 2027.xlsx"
OCT = date(2026, 10, 7)
APR = date(2027, 4, 7)
T0 = datetime(2026, 9, 20, 3, 18, 30)


def _uid() -> str:
    return str(uuid.uuid4())


def _script():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "repair_oi_legacy_dup_rows.py",
    )
    spec = importlib.util.spec_from_file_location("_repair_oi_legacy_dup_rows", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _world():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user_id = _user(db, "zzt-oildr ops")
        w = _seed_world(db, company_id, user_id)
        w["user_id"] = user_id
        w["doc_no"] = w["order"].autocount_doc_no
        w["item"] = w["product"].product_code
        w["line_no"] = 0
        with company_scope(db, frozenset({company_id})):
            yield db, w


def _line(db, w, qty, due) -> ProjectSalesOrderLine:
    w["line_no"] += 1
    line = ProjectSalesOrderLine(
        id=_uid(), company_id=w["company_id"], project_sales_order_id=w["order"].id,
        line_no=w["line_no"], product_id=w["product"].id, qty=Decimal(str(qty)),
        delivery_date=due,
    )
    db.add(line)
    db.flush()
    return line


def _job(db, w, *, filename, at) -> ImportJob:
    job = ImportJob(
        id=uuid.uuid4(), job_id=f"zzt-oildr-{_uid()[:12]}", job_type="order_inquiry_import",
        status="finished", user_id=w["user_id"], company_id=w["company_id"],
        source_filename=filename, created_at=at,
    )
    db.add(job)
    db.flush()
    return job


def _identity(w, sheet, qty, due) -> dict:
    return {
        "doc_no": w["doc_no"], "item_code": w["item"], "sheet": sheet,
        "qty": str(qty), "delivery_date": due.isoformat(),
    }


def _created(db, w, job, line, *, sheet, sheet_row, qty, due, stamp=STAMP_2026,
             state=INQUIRY_RAISED, ack_state=ACK_ACKNOWLEDGED) -> OrderInquiryRow:
    """One inquiry row the importer CREATED from one sheet row, with its job row."""
    row = OrderInquiryRow(
        id=_uid(), company_id=w["company_id"], order_inquiry_id=w["inquiry"].id,
        so_line_id=line.id, item_code=w["item"], qty=Decimal(str(qty)), delivery_date=due,
        verb=IV_ORDER, state=state, ack_state=ack_state, note=stamp, created_at=job.created_at,
    )
    db.add(row)
    db.flush()
    db.add(ImportJobRow(
        import_job_id=job.id, row_number=sheet_row, outcome="created", code="created",
        message="Created", identity=_identity(w, sheet, qty, due),
        entity_type="order_inquiry_row", entity_id=str(row.id),
    ))
    db.flush()
    return row


def _skipped(db, w, job, *, sheet, sheet_row, qty, due) -> None:
    db.add(ImportJobRow(
        import_job_id=job.id, row_number=sheet_row, outcome="skipped", code="already_raised",
        message="Left alone: this line already carries an order inquiry",
        identity=_identity(w, sheet, qty, due),
    ))
    db.flush()


def _m9713ss(db, w, *, copy_state=INQUIRY_RAISED, copy_ack=ACK_ACKNOWLEDGED, skipped=True):
    """The prod shape: returns (sibling, copy, copy's line)."""
    oct_line = _line(db, w, 2, OCT)
    apr_line = _line(db, w, 26, APR)
    book_2026 = _job(db, w, filename="JAN - DEC 2026 ORDERabc.xlsx", at=T0)
    sibling = _created(db, w, book_2026, oct_line, sheet="OCT 26", sheet_row=630, qty=2, due=OCT)
    copy = _created(db, w, book_2026, apr_line, sheet="OCT 26", sheet_row=662, qty=2, due=OCT,
                    state=copy_state, ack_state=copy_ack)
    if skipped:
        book_2027 = _job(db, w, filename="JAN - DEC ORDER 2027.xlsx", at=T0 + timedelta(minutes=4))
        _skipped(db, w, book_2027, sheet="APR 27", sheet_row=166, qty=26, due=APR)
    db.commit()
    return sibling, copy, apr_line


def _found(db, w):
    return _script().find_squatters(db, inquiry_id=w["inquiry"].id)


def _run(db, w, **kwargs):
    return _script().run(db, inquiry_id=w["inquiry"].id, **kwargs)


# --------------------------------------------------------------------------- detector


def test_ac_1_a_duplicate_squatting_a_line_whose_own_row_was_skipped_is_found():
    with _world() as (db, w):
        sibling, copy, apr_line = _m9713ss(db, w)

        found = _found(db, w)

        assert [f.row_id for f in found] == [str(copy.id)]
        hit = found[0]
        assert hit.sibling_row_id == str(sibling.id)
        assert (hit.sheet, hit.sheet_row, hit.sibling_sheet_row) == ("OCT 26", 662, 630)
        assert (hit.skipped_sheet, hit.skipped_sheet_row) == ("APR 27", 166)
        assert (hit.restate_qty, hit.restate_date) == (Decimal("26"), APR)
        assert hit.verdict == "restate"


def test_ac_2_a_per_line_repeat_whose_qty_matches_its_line_is_not_found():
    """A tab stating 372 once per 372 line: only the date drifts. Even with a skipped row
    naming the second line, this is not a squatter."""
    with _world() as (db, w):
        mar, jun = date(2026, 3, 1), date(2026, 6, 1)
        on_date = _line(db, w, 372, mar)
        other = _line(db, w, 372, jun)
        job = _job(db, w, filename="JAN - DEC 2026 ORDERabc.xlsx", at=T0)
        _created(db, w, job, on_date, sheet="MAR 26", sheet_row=276, qty=372, due=mar)
        _created(db, w, job, other, sheet="MAR 26", sheet_row=277, qty=372, due=mar)
        _skipped(db, w, _job(db, w, filename="x.xlsx", at=T0 + timedelta(minutes=1)),
                 sheet="JUN 26", sheet_row=9, qty=372, due=jun)
        db.commit()

        assert _found(db, w) == []


def test_ac_3b_a_duplicate_whose_twin_is_not_on_the_sheets_line_is_not_found():
    """Nothing proves which of the two is the copy when neither sits on the line the
    sheet names, so neither is reported."""
    with _world() as (db, w):
        nov_line = _line(db, w, 3, date(2026, 11, 7))
        apr_line = _line(db, w, 26, APR)
        job = _job(db, w, filename="JAN - DEC 2026 ORDERabc.xlsx", at=T0)
        _created(db, w, job, nov_line, sheet="OCT 26", sheet_row=630, qty=2, due=OCT)
        _created(db, w, job, apr_line, sheet="OCT 26", sheet_row=662, qty=2, due=OCT)
        later = _job(db, w, filename="JAN - DEC ORDER 2027.xlsx", at=T0 + timedelta(minutes=4))
        _skipped(db, w, later, sheet="APR 27", sheet_row=166, qty=26, due=APR)
        db.commit()

        assert _found(db, w) == []


def test_ac_3c_two_rows_from_the_same_sheet_row_are_not_twins():
    """Plan 2.2: the twin comes from ANOTHER sheet row. One sheet row that created two rows
    is not the tab stating the instruction twice."""
    with _world() as (db, w):
        oct_line = _line(db, w, 2, OCT)
        apr_line = _line(db, w, 26, APR)
        job = _job(db, w, filename="JAN - DEC 2026 ORDERabc.xlsx", at=T0)
        _created(db, w, job, oct_line, sheet="OCT 26", sheet_row=630, qty=2, due=OCT)
        _created(db, w, job, apr_line, sheet="OCT 26", sheet_row=630, qty=2, due=OCT)
        later = _job(db, w, filename="JAN - DEC ORDER 2027.xlsx", at=T0 + timedelta(minutes=4))
        _skipped(db, w, later, sheet="APR 27", sheet_row=166, qty=26, due=APR)
        db.commit()

        assert _found(db, w) == []


def test_ac_3_a_duplicate_with_no_skipped_row_for_its_line_is_not_found():
    with _world() as (db, w):
        _m9713ss(db, w, skipped=False)

        assert _found(db, w) == []


def test_ac_4_a_skipped_row_naming_another_qty_is_not_evidence():
    with _world() as (db, w):
        _m9713ss(db, w, skipped=False)
        later = _job(db, w, filename="JAN - DEC ORDER 2027.xlsx", at=T0 + timedelta(minutes=4))
        _skipped(db, w, later, sheet="APR 27", sheet_row=166, qty=20, due=APR)
        db.commit()

        assert _found(db, w) == []


def test_ac_4b_a_skipped_row_older_than_the_duplicate_is_not_evidence():
    """Only a sheet row read AFTER the duplicate was raised can have been blocked by it."""
    with _world() as (db, w):
        _m9713ss(db, w, skipped=False)
        earlier = _job(db, w, filename="JAN - DEC ORDER 2027.xlsx", at=T0 - timedelta(days=1))
        _skipped(db, w, earlier, sheet="APR 27", sheet_row=166, qty=26, due=APR)
        db.commit()

        assert _found(db, w) == []


# --------------------------------------------------------------------------- repair


def test_ac_5_apply_restates_the_copy_to_its_lines_own_instruction():
    with _world() as (db, w):
        sibling, copy, apr_line = _m9713ss(db, w)

        result = _run(db, w, apply=True, expect=1)
        db.commit()

        assert result["restated"] == 1
        db.refresh(copy)
        db.refresh(sibling)
        assert copy.qty == Decimal("26")
        assert copy.delivery_date == APR
        assert str(copy.so_line_id) == str(apr_line.id)
        assert copy.previous_qty == Decimal("2")
        assert copy.previous_delivery_date == OCT
        assert copy.ack_state == ACK_CHANGED
        assert copy.changed_at is not None
        assert copy.state == INQUIRY_RAISED
        assert copy.note.startswith(STAMP_2026)
        assert "APR 27 row 166" in copy.note and "OCT 26 row 630" in copy.note
        # OI-AUTO-CONFIRM (#1986): the refresh re-derives the inquiry's rows by the rule, and
        # an unlinked buy row nobody confirmed by hand is To order (`awaiting`), not Done.
        assert (sibling.qty, sibling.delivery_date, sibling.ack_state) == (
            Decimal("2"), OCT, ACK_AWAITING,
        )
        assert sibling.previous_qty is None


def test_ac_5b_an_awaiting_copy_stays_awaiting():
    with _world() as (db, w):
        _sibling, copy, _line_ = _m9713ss(db, w, copy_ack=ACK_AWAITING)

        _run(db, w, apply=True, expect=1)
        db.commit()

        db.refresh(copy)
        assert copy.qty == Decimal("26")
        assert copy.ack_state == ACK_AWAITING
        assert copy.changed_at is None


@pytest.mark.parametrize(
    "state, reason",
    [(INQUIRY_CANCELLED, "cancelled"), (INQUIRY_ACTIONED, "actioned")],
)
def test_ac_6_a_cancelled_or_actioned_copy_is_held(state, reason):
    with _world() as (db, w):
        _sibling, copy, _line_ = _m9713ss(db, w, copy_state=state)

        found = _found(db, w)
        result = _run(db, w, apply=True, expect=0)
        db.commit()

        assert [(f.row_id, f.verdict) for f in found] == [(str(copy.id), reason)]
        assert result["restated"] == 0
        db.refresh(copy)
        assert (copy.qty, copy.delivery_date, copy.previous_qty) == (Decimal("2"), OCT, None)


def test_ac_6b_a_linked_copy_is_held():
    with _world() as (db, w):
        _sibling, copy, _line_ = _m9713ss(db, w, copy_state=INQUIRY_PLACED)
        po_line = _po_line(db, w["company_id"], w["po"], w["product"], w["warehouse"], qty_ordered="2")
        db.add(OrderInquiryLink(
            id=_uid(), company_id=w["company_id"], row_id=copy.id, po_line_id=po_line.id,
            document="ZZT-PO", qty=Decimal("2"),
        ))
        db.commit()

        found = _found(db, w)
        result = _run(db, w, apply=True, expect=0)
        db.commit()

        assert [(f.row_id, f.verdict) for f in found] == [(str(copy.id), "linked")]
        assert result["restated"] == 0
        db.refresh(copy)
        assert copy.qty == Decimal("2")


def test_ac_6c_a_copy_sharing_its_line_with_another_live_row_is_held():
    """Review blocker (PR #1996): restating would put a second full instruction on the line."""
    with _world() as (db, w):
        _sibling, copy, apr_line = _m9713ss(db, w)
        other = OrderInquiryRow(
            id=_uid(), company_id=w["company_id"], order_inquiry_id=w["inquiry"].id,
            so_line_id=apr_line.id, item_code=w["item"], qty=Decimal("24"), delivery_date=APR,
            verb=IV_ORDER, state=INQUIRY_RAISED, ack_state=ACK_ACKNOWLEDGED,
        )
        db.add(other)
        db.commit()

        found = _found(db, w)
        result = _run(db, w, apply=True, expect=0)
        db.commit()

        assert [(f.row_id, f.verdict) for f in found] == [(str(copy.id), "line carries other rows")]
        assert result["restated"] == 0
        db.refresh(copy)
        assert copy.qty == Decimal("2")


def test_ac_6d_two_copies_on_one_line_are_both_held():
    """Review blocker (PR #1996): a tab stating the row three times puts copies 2 and 3 on
    the same line, and both match the one skipped row. Restating both would put 52 on a
    26 line."""
    with _world() as (db, w):
        oct_line = _line(db, w, 2, OCT)
        apr_line = _line(db, w, 26, APR)
        job = _job(db, w, filename="JAN - DEC 2026 ORDERabc.xlsx", at=T0)
        _created(db, w, job, oct_line, sheet="OCT 26", sheet_row=630, qty=2, due=OCT)
        a = _created(db, w, job, apr_line, sheet="OCT 26", sheet_row=662, qty=2, due=OCT)
        b = _created(db, w, job, apr_line, sheet="OCT 26", sheet_row=694, qty=2, due=OCT)
        later = _job(db, w, filename="JAN - DEC ORDER 2027.xlsx", at=T0 + timedelta(minutes=4))
        _skipped(db, w, later, sheet="APR 27", sheet_row=166, qty=26, due=APR)
        db.commit()

        found = _found(db, w)
        result = _run(db, w, apply=True, expect=0)
        db.commit()

        assert sorted((f.row_id, f.verdict) for f in found) == sorted(
            [(str(a.id), "line carries other rows"), (str(b.id), "line carries other rows")]
        )
        assert result["restated"] == 0


def test_ac_6e_a_copy_edited_since_import_is_held():
    """The prod M3155 shape: someone already changed the copy's qty after the import."""
    with _world() as (db, w):
        _sibling, copy, _line_ = _m9713ss(db, w)
        copy.qty = Decimal("3")
        db.commit()

        found = _found(db, w)

        assert [(f.row_id, f.verdict) for f in found] == [(str(copy.id), "edited since import")]


def test_ac_6f_a_copy_named_on_a_reserve_request_is_held():
    with _world() as (db, w):
        _sibling, copy, _line_ = _m9713ss(db, w)
        request = OrderInquiryReserveRequest(
            id=_uid(), company_id=w["company_id"], order_inquiry_id=w["inquiry"].id, ordinal=1,
        )
        db.add(request)
        db.flush()
        db.add(OrderInquiryReserveRequestRow(
            id=_uid(), company_id=w["company_id"], request_id=request.id, row_id=copy.id,
            qty_requested=Decimal("2"),
        ))
        db.commit()

        found = _found(db, w)

        assert [(f.row_id, f.verdict) for f in found] == [(str(copy.id), "reserve request")]


def test_ac_6g_a_copy_other_rows_are_bundled_with_is_held():
    with _world() as (db, w):
        _sibling, copy, _line_ = _m9713ss(db, w)
        db.add(OrderInquiryRow(
            id=_uid(), company_id=w["company_id"], order_inquiry_id=w["inquiry"].id,
            item_code="ZZT-COMPANION", qty=Decimal("2"), verb=IV_ORDER, state=INQUIRY_RAISED,
            ack_state=ACK_ACKNOWLEDGED, bundled_qty=Decimal("2"), bundled_with_row_id=copy.id,
        ))
        db.commit()

        found = _found(db, w)

        assert [(f.row_id, f.verdict) for f in found] == [(str(copy.id), "bundled")]


def test_ac_6h_owner_ruling_a_the_m3155_shape_is_held_and_its_date_not_restated():
    """Owner ruling (a), 30 Oct: every held row stays as it is, including the prod M3155
    shape - placed, qty already set to the line's, reserved against a link, only the date
    still the sheet's. The script reports it and writes nothing to it."""
    with _world() as (db, w):
        _sibling, copy, _line_ = _m9713ss(db, w, copy_state=INQUIRY_PLACED)
        copy.qty = Decimal("26")
        po_line = _po_line(db, w["company_id"], w["po"], w["product"], w["warehouse"], qty_ordered="26")
        db.add(OrderInquiryLink(
            id=_uid(), company_id=w["company_id"], row_id=copy.id, po_line_id=po_line.id,
            document="Reserved @ BRW", qty=Decimal("26"),
        ))
        db.commit()

        found = _found(db, w)
        result = _run(db, w, apply=True, expect=0)
        db.commit()

        assert [(f.row_id, f.verdict) for f in found] == [(str(copy.id), "linked")]
        assert (result["found"], result["restate"], result["held"], result["restated"]) == (1, 0, 1, 0)
        db.refresh(copy)
        assert (copy.qty, copy.delivery_date, copy.state) == (Decimal("26"), OCT, INQUIRY_PLACED)
        assert copy.previous_qty is None and copy.previous_delivery_date is None


def test_ac_7_dry_run_writes_nothing():
    with _world() as (db, w):
        _sibling, copy, _line_ = _m9713ss(db, w)

        result = _run(db, w, apply=False, expect=None)
        db.commit()

        assert result["restate"] == 1
        assert result["restated"] == 0
        db.refresh(copy)
        assert (copy.qty, copy.delivery_date, copy.ack_state) == (Decimal("2"), OCT, ACK_ACKNOWLEDGED)


@pytest.mark.parametrize("expect", [None, 0, 2])
def test_ac_8_apply_refuses_when_the_count_differs_from_the_dry_run(expect):
    script = _script()
    with _world() as (db, w):
        _sibling, copy, _line_ = _m9713ss(db, w)

        with pytest.raises(script.CountMismatch):
            script.run(db, inquiry_id=w["inquiry"].id, apply=True, expect=expect)
        db.commit()

        db.refresh(copy)
        assert (copy.qty, copy.delivery_date) == (Decimal("2"), OCT)


def test_ac_9_a_second_apply_restates_nothing():
    with _world() as (db, w):
        _sibling, copy, _line_ = _m9713ss(db, w)
        _run(db, w, apply=True, expect=1)
        db.commit()

        again = _run(db, w, apply=True, expect=0)
        db.commit()

        assert again["restate"] == 0
        assert again["restated"] == 0
        assert [f.verdict for f in _found(db, w)] == ["already restated"]
        db.refresh(copy)
        assert copy.previous_qty == Decimal("2")


def test_ac_10_each_restated_row_gets_one_audit_event():
    with _world() as (db, w):
        _sibling, copy, _line_ = _m9713ss(db, w)

        _run(db, w, apply=True, expect=1)
        db.commit()

        events = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "project_order_inquiry_rows",
                    AuditLog.entity_id == str(copy.id))
            .all()
        )
        assert len(events) == 1
        assert events[0].event == "OI_ROW_LEGACY_DUP_RESTATED"
        assert events[0].old_values["qty"] == 2 and events[0].new_values["qty"] == 26
        assert events[0].old_values["delivery_date"] == "2026-10-07"
        assert events[0].new_values["delivery_date"] == "2027-04-07"
