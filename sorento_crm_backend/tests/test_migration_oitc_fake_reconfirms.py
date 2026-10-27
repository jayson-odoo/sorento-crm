"""`oitc_0001_fake_reconfirms` (lane OI-TRAIL-CLEANUP,
`documentation/plans/scm/PLAN-oi-trail-cleanup-27oct.md`).

The fixture rebuilds the 20 Sep 2026 shape with the code that produced it, not a hand-typed
result: a sheet-imported header and rows stamped with the +8 h shifted clock, then the real
`523_oi_monthly_no_raises.backfill_raises`, which writes the fake `reconfirmed` row. The
cleanup then runs and the decision trail is read through `DecisionTrailService`.

Postgres only, via `tests/_pg_fixture.py`'s `blank_session`.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

from app.models.project_so import (
    OI_RAISE_RECONFIRMED,
    OrderInquiry,
    OrderInquiryRaise,
    OrderInquiryRow,
)
from app.services.decision_trail_service import DecisionTrailService

from ._pg_fixture import blank_session
from .test_decision_trail import _core_line, _mirror_line
from .test_order_inquiry_raise_event import _raise
from .test_order_inquiry_worklist_raised_by import (
    MARKER,
    _adopted_order,
    _inquiry,
    _product,
    _row,
    _sorento,
    _uid,
    _user,
)

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"

#: The real instant of the first 20 Sep upload (naive UTC) and the value the import wrote.
REAL = datetime(2026, 9, 20, 3, 19, 23, 552179)
SHIFTED = REAL + timedelta(hours=8)
#: The second upload, three minutes later.
REAL_2 = datetime(2026, 9, 20, 3, 22, 40, 118000)
SHIFTED_2 = REAL_2 + timedelta(hours=8)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"zzt_{name}", _VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cleanup():
    return _load("oitc_0001_fake_reconfirms")


def _backfill_523():
    return _load("523_oi_monthly_no_raises")


def _sheet_order(db, company_id, uploader, *, real, shifted, qty_rows=2):
    """One order the sheet import created: header + rows stamped with the shifted clock,
    rows born at the real instant (server `now()`), notes carrying the sheet stamp."""
    project_order = _adopted_order(db, company_id, f"ZZTSO{_uid()[:8]}")
    product = _product(db, f"ZZT-{_uid()[:6]}")
    core_line = _core_line(db, project_order.so_id, product.id)
    mirror = _mirror_line(db, company_id, project_order, core_line)
    header = _inquiry(db, company_id, project_order, raised_by=uploader, raised_at=shifted)
    rows = []
    for i in range(qty_rows):
        row = _row(db, company_id, header, mirror, f"{MARKER}-OITC-{i}")
        row.note = f"Migrated from order inquiry sheet JAN - DEC 2026 ORDER.xlsx, row {i + 1}"
        row.created_at = real
        row.ack_state = "acknowledged"
        row.acknowledged_by = uploader
        row.acknowledged_at = shifted
        rows.append(row)
    db.flush()
    return header, rows, core_line


def _kinds(db, header_id):
    return sorted(
        (r.kind, r.raised_at, r.raised_by)
        for r in db.query(OrderInquiryRaise).filter(
            OrderInquiryRaise.order_inquiry_id == header_id
        )
    )


def _trail_kinds(db, core_line_id):
    return [e["kind"] for e in DecisionTrailService(db).for_core_line(str(core_line_id))]


def test_fake_reconfirm_is_removed_and_acknowledged_time_is_the_real_import_time():
    with blank_session() as db:
        company_id = _sorento(db)
        uploader = _user(db, f"{MARKER} Uploader", f"up.{_uid()[:8]}@zzt.test").id
        header, rows, core_line = _sheet_order(
            db, company_id, uploader, real=REAL, shifted=SHIFTED
        )
        header_2, rows_2, core_line_2 = _sheet_order(
            db, company_id, uploader, real=REAL_2, shifted=SHIFTED_2
        )
        db.commit()
        _backfill_523().backfill_raises(db.connection())
        db.commit()
        db.expire_all()
        # The defect, reproduced: 523 wrote a reconfirm at the shifted stamp.
        assert "reconfirmed" in _trail_kinds(db, core_line.id)
        assert "reconfirmed" in _trail_kinds(db, core_line_2.id)

        counts = _cleanup().clean_fake_reconfirms(db.connection())
        db.commit()
        db.expire_all()

        assert counts["reconfirms_deleted"] == 2
        assert counts["rows_acknowledged_at"] == 4
        assert "reconfirmed" not in _trail_kinds(db, core_line.id)
        assert "reconfirmed" not in _trail_kinds(db, core_line_2.id)
        for row in rows:
            assert db.get(OrderInquiryRow, row.id).acknowledged_at == REAL
        for row in rows_2:
            assert db.get(OrderInquiryRow, row.id).acknowledged_at == REAL_2
        # The first raise keeps its real time and gets the uploader's name back.
        assert _kinds(db, header.id) == [("raised", REAL, uploader)]
        assert _kinds(db, header_2.id) == [("raised", REAL_2, uploader)]
        assert db.get(OrderInquiry, header.id).raised_at == REAL


def test_a_genuine_reconfirm_by_the_same_uploader_survives():
    """The trail test's own B3 shape (`test_decision_trail.py`): a real reconfirm hours after
    a sheet migration, stamped by `_record_raise`, never on the import's own value."""
    with blank_session() as db:
        company_id = _sorento(db)
        uploader = _user(db, f"{MARKER} Uploader", f"up.{_uid()[:8]}@zzt.test").id
        header, rows, core_line = _sheet_order(
            db, company_id, uploader, real=REAL, shifted=SHIFTED
        )
        db.commit()
        _backfill_523().backfill_raises(db.connection())
        genuine_at = SHIFTED + timedelta(hours=2, microseconds=17)
        _raise(db, company_id, header, kind=OI_RAISE_RECONFIRMED,
               raised_by=uploader, raised_at=genuine_at)
        # A plain (non-sheet) inquiry reconfirmed ~8 h after its row by the same person.
        plain, plain_rows, plain_line = _sheet_order(
            db, company_id, uploader, real=REAL, shifted=REAL
        )
        for row in plain_rows:
            row.note = "Raised from the board"
        _raise(db, company_id, plain, kind=OI_RAISE_RECONFIRMED,
               raised_by=uploader, raised_at=REAL + timedelta(hours=8, seconds=5))
        db.commit()

        _cleanup().clean_fake_reconfirms(db.connection())
        db.commit()
        db.expire_all()

        assert ("reconfirmed", genuine_at, uploader) in _kinds(db, header.id)
        assert ("reconfirmed", SHIFTED, uploader) not in _kinds(db, header.id)
        assert [k for k, _, _ in _kinds(db, plain.id)].count("reconfirmed") == 1
        for row in plain_rows:
            assert db.get(OrderInquiryRow, row.id).acknowledged_at == REAL


def test_a_stamp_match_alone_is_not_provenance_note_and_window_guards():
    """Defence in depth past the microsecond match: a reconfirm sharing a row's exact
    acknowledged stamp is still kept when that row is not a sheet row, or when the gap
    from the row's birth is not the import's ~8 h shift."""
    with blank_session() as db:
        company_id = _sorento(db)
        user = _user(db, f"{MARKER} Planner", f"pl.{_uid()[:8]}@zzt.test").id
        stamp = REAL + timedelta(hours=8, seconds=5)
        # Not a sheet row: board-raised, acknowledged at exactly the reconfirm's stamp.
        board, board_rows, _ = _sheet_order(db, company_id, user, real=REAL, shifted=stamp)
        for row in board_rows:
            row.note = "Raised from the board"
        _raise(db, company_id, board, kind=OI_RAISE_RECONFIRMED,
               raised_by=user, raised_at=stamp)
        # A sheet row, but acknowledged two days after its birth, not eight hours.
        late_stamp = REAL + timedelta(days=2)
        late, late_rows, _ = _sheet_order(db, company_id, user, real=REAL, shifted=late_stamp)
        _raise(db, company_id, late, kind=OI_RAISE_RECONFIRMED,
               raised_by=user, raised_at=late_stamp)
        db.commit()

        counts = _cleanup().clean_fake_reconfirms(db.connection())
        db.commit()
        db.expire_all()

        assert counts["reconfirms_deleted"] == 0
        assert ("reconfirmed", stamp, user) in _kinds(db, board.id)
        assert ("reconfirmed", late_stamp, user) in _kinds(db, late.id)
        assert db.get(OrderInquiryRow, board_rows[0].id).acknowledged_at == stamp
        assert db.get(OrderInquiryRow, late_rows[0].id).acknowledged_at == late_stamp


def test_other_rows_stamped_by_the_same_upload_are_shifted_others_are_not():
    with blank_session() as db:
        company_id = _sorento(db)
        uploader = _user(db, f"{MARKER} Uploader", f"up.{_uid()[:8]}@zzt.test").id
        header, rows, _ = _sheet_order(db, company_id, uploader, real=REAL, shifted=SHIFTED)
        # Closed as history / settled by the same run: same `now`.
        rows[0].actioned_at = SHIFTED
        rows[1].changed_at = SHIFTED
        # A board-raised inquiry (no fake reconfirm of its own).
        board, board_rows, _ = _sheet_order(
            db, company_id, uploader, real=REAL - timedelta(days=3),
            shifted=REAL - timedelta(days=3),
        )
        board_rows[0].acknowledged_at = SHIFTED
        # Born weeks later, carrying the acknowledgement forward with its stamp (a split
        # or a revision copies `acknowledged_at`, `project_order_inquiry_service.py:7364`).
        board_rows[0].created_at = REAL + timedelta(days=12)
        board_rows[0].note = "Superseded by revision 2"
        untouched_at = SHIFTED + timedelta(microseconds=1)
        board_rows[1].acknowledged_at = untouched_at
        db.commit()
        _backfill_523().backfill_raises(db.connection())
        db.commit()

        _cleanup().clean_fake_reconfirms(db.connection())
        db.commit()
        db.expire_all()

        assert db.get(OrderInquiryRow, rows[0].id).actioned_at == REAL
        assert db.get(OrderInquiryRow, rows[1].id).changed_at == REAL
        assert db.get(OrderInquiryRow, board_rows[0].id).acknowledged_at == REAL
        assert db.get(OrderInquiryRow, board_rows[1].id).acknowledged_at == untouched_at


def test_second_run_is_a_no_op_and_523_backfill_cannot_recreate_it():
    with blank_session() as db:
        company_id = _sorento(db)
        uploader = _user(db, f"{MARKER} Uploader", f"up.{_uid()[:8]}@zzt.test").id
        header, rows, core_line = _sheet_order(
            db, company_id, uploader, real=REAL, shifted=SHIFTED
        )
        db.commit()
        backfill = _backfill_523()
        backfill.backfill_raises(db.connection())
        cleanup = _cleanup()
        cleanup.clean_fake_reconfirms(db.connection())
        db.commit()
        before = _kinds(db, header.id)

        again = cleanup.clean_fake_reconfirms(db.connection())
        backfill.backfill_raises(db.connection())
        db.commit()
        db.expire_all()

        assert all(v == 0 for v in again.values()), again
        assert _kinds(db, header.id) == before
        assert db.get(OrderInquiryRow, rows[0].id).acknowledged_at == REAL
        assert "reconfirmed" not in _trail_kinds(db, core_line.id)
