"""OI-WHOLE-SO-CANCEL, red tests: an AutoCount push that cancels a WHOLE sales order (or
removes its last open line), or an AutoCount SO delete, raises the planning-change
`cancelled` row for CS on the board.

UAC: documentation/plans/scm/oi-whole-so-cancel-acceptance-criteria.md (AC-WC-1..7).
Card: documentation/plans/scm/oi-whole-so-cancel-behaviour-card.md.

TEST-FIRST: written before any implementation, driven through the real HTTP ingest routes
(`env` fixture of tests/test_ingest_documents.py) so the fix can live in the service or in a
route hook.

Q1(b) (owner answer pending, recommended): AC-WC-6 tests assume the OI row stays live
(state, ack_state unchanged) until CS Confirms. If the owner picks (a) those two are revised.
They contradict the older test_fp_email_one_trigger_a_line_dropped_by_a_header_cancel_push_
is_still_flagged in tests/test_ac_removed_lines_ingest.py, which that lane must update.

Postgres only. Every test seeds its own chain. No real names, phones, emails or prices.
"""
from __future__ import annotations

from sqlalchemy import text

from app.models.audit import AuditLog
from app.models.planning_change import PlanningChangeRow
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
)

from .test_ac_removed_lines_ingest import (  # noqa: F401 - fixtures/helpers reused
    INGEST_SO,
    _captured_dispatches,
    _handover_calls,
    _push_so,
    _register,
    _row_snapshot,
    _so_mirror_row,
    _three_rows_on_x,
    env,
)

_MAIL = ("order_inquiry_handover", "order_inquiry_changed_with_links")


# --------------------------------------------------------------------------- helpers
def _cancelled_rows(env, core_line_id) -> list:
    env.db.expire_all()
    return (
        env.db.query(PlanningChangeRow)
        .filter(
            PlanningChangeRow.core_line_id == str(core_line_id),
            PlanningChangeRow.kind == "cancelled",
        )
        .all()
    )


def _header_cancel_push(env, record, y):
    res = env.post(INGEST_SO, [dict(record, status="cancelled", lines=[y])])
    assert res.status_code == 200, res.text
    env.db.expire_all()
    return res


def _delete_so(env, record):
    res = env.client.post(
        f"{INGEST_SO}/deletions",
        json={"companyCode": env.company_a_code, "source_refs": [record["source_ref"]]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] == "deactivated", res.text
    env.db.expire_all()
    return res


def _confirm_and_collect(env, monkeypatch, core_line_id):
    from app.services import planning_change_service
    from app.services.project_order_inquiry_service import mark_purchasing_email_trigger

    pending = _cancelled_rows(env, core_line_id)
    assert len(pending) == 1, "precondition: the cancel waits on the board"
    batch_id = pending[0].batch_id
    _register(None)
    calls = _captured_dispatches(monkeypatch)
    mark_purchasing_email_trigger(env.db)
    from .test_ingest_documents import _USER_ID

    planning_change_service.apply(env.db, str(batch_id), _USER_ID)
    env.db.commit()
    env.db.expire_all()
    return calls


def _assert_rows_cancelled_once_and_one_cancel_mail(env, rows, calls):
    for row_id in rows:
        snap = _row_snapshot(env, row_id)
        assert snap["state"] == INQUIRY_CANCELLED, (row_id, snap)
        audits = (
            env.db.query(AuditLog)
            .filter(AuditLog.entity_id == row_id, AuditLog.event == "OI_ROW_CANCELLED")
            .count()
        )
        assert audits == 1, (row_id, audits)
    matches = _handover_calls(calls)
    assert len(matches) == 1, [c["trigger_type"] for c in calls]
    lines = matches[0]["context"]["handover"]["lines"]
    assert lines and all("CANCEL" in line["remark"] for line in lines), lines


# ============================================================================ AC-WC-1
def test_ac_wc_1_a_header_cancel_push_raises_one_cancelled_row_for_the_line(env):
    """The SO 428043 case: the push cancels the whole header (line x left out, y carried),
    x carries a live OI row. Exactly one `cancelled` planning-change row for x."""
    record, header, line_x, y = _push_so(env)
    _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING)

    _header_cancel_push(env, record, y)

    assert len(_cancelled_rows(env, line_x["id"])) == 1


# ============================================================================ AC-WC-2
def test_ac_wc_2_removing_the_last_open_line_raises_the_cancelled_row(env):
    """Shape (header OPEN, so distinct from WC-1): two-line SO; y was fully cancelled by a
    Cancel SO document (line_status cancelled, cancelled_by_cancel_doc, qty_cancelled =
    qty_ordered, set directly as in test_ac_rl_30). The push keeps the header open and
    carries only y, so x is removed; y stays cancelled, hence the SO has no AFTER lines and
    the diff scope (derived from open lines) misses x."""
    record, header, line_x, y = _push_so(env)
    _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING)
    env.db.execute(
        text(
            "UPDATE sales_order_lines SET line_status = 'cancelled', "
            "cancelled_by_cancel_doc = true, qty_cancelled = qty_ordered "
            "WHERE sales_order_id = :h AND id <> :x"
        ),
        {"h": str(header["id"]), "x": str(line_x["id"])},
    )
    env.db.commit()

    res = env.post(INGEST_SO, [dict(record, status="open", lines=[y])])
    assert res.status_code == 200, res.text
    env.db.expire_all()

    assert len(_cancelled_rows(env, line_x["id"])) == 1


# ============================================================================ AC-WC-3
def test_ac_wc_3_an_so_delete_raises_a_cancelled_row_per_line_with_a_live_oi_row(env):
    """DELETE ingest of an SO that has dependents (the OI mirror) is cancelled, not removed;
    each line with a live OI row gets its `cancelled` row."""
    record, header, line_x, y = _push_so(env)
    _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING)

    _delete_so(env, record)

    assert len(_cancelled_rows(env, line_x["id"])) == 1


# ============================================================================ AC-WC-4
def test_ac_wc_4_confirming_a_header_cancel_cancels_the_rows_and_emails_cancel_once(
    env, monkeypatch
):
    record, header, line_x, y, rows = _three_rows_on_x(env)
    _header_cancel_push(env, record, y)

    calls = _confirm_and_collect(env, monkeypatch, line_x["id"])

    _assert_rows_cancelled_once_and_one_cancel_mail(env, rows, calls)


def test_ac_wc_4_confirming_an_so_delete_cancels_the_rows_and_emails_cancel_once(
    env, monkeypatch
):
    record, header, line_x, y, rows = _three_rows_on_x(env)
    _delete_so(env, record)

    calls = _confirm_and_collect(env, monkeypatch, line_x["id"])

    _assert_rows_cancelled_once_and_one_cancel_mail(env, rows, calls)


# ============================================================================ AC-WC-5
def test_ac_wc_5_the_header_cancel_push_emails_purchasing_nothing(env, monkeypatch):
    record, header, line_x, y = _push_so(env)
    _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING)
    _register(None)
    calls = _captured_dispatches(monkeypatch)

    _header_cancel_push(env, record, y)

    assert [c["trigger_type"] for c in calls if c["trigger_type"] in _MAIL] == []


def test_ac_wc_5_the_so_delete_emails_purchasing_nothing(env, monkeypatch):
    record, header, line_x, y = _push_so(env)
    _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING)
    _register(None)
    calls = _captured_dispatches(monkeypatch)

    _delete_so(env, record)

    assert [c["trigger_type"] for c in calls if c["trigger_type"] in _MAIL] == []


# ============================================================================ AC-WC-7
def test_ac_wc_7_re_pushing_the_same_cancelled_so_raises_no_second_row(env):
    record, header, line_x, y = _push_so(env)
    _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING)
    _header_cancel_push(env, record, y)
    first = len(_cancelled_rows(env, line_x["id"]))

    _header_cancel_push(env, record, y)

    assert first == 1, "precondition: the first push raised the row"
    assert len(_cancelled_rows(env, line_x["id"])) == 1


def test_ac_wc_7_a_cancelled_so_with_no_oi_row_raises_no_planning_change_row(env):
    record, header, line_x, y = _push_so(env)

    _header_cancel_push(env, record, y)

    assert _cancelled_rows(env, line_x["id"]) == []


# ============================================================================ AC-WC-8
def test_ac_wc_8_a_header_reopened_before_cs_decides_leaves_nothing_to_do(env, monkeypatch):
    """Q4: push with the header cancelled (raises the pending cancelled row), then push the
    header open with the line back, BEFORE any CS apply. "CS sees nothing to do" is asserted
    from the real columns: no cancelled row for that line is still `applied_state` "pending"
    (it is superseded or gone), and applying the batch cancels no OI row and sends no CANCEL."""
    record, header, line_x, y = _push_so(env)
    row_id, _ = _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING)
    _header_cancel_push(env, record, y)
    first = _cancelled_rows(env, line_x["id"])
    assert len(first) == 1 and first[0].applied_state == "pending", "precondition"
    batch_id = first[0].batch_id

    res = env.post(INGEST_SO, [dict(record, status="open")])
    assert res.status_code == 200, res.text
    env.db.expire_all()

    live = [r for r in _cancelled_rows(env, line_x["id"]) if r.applied_state == "pending"]
    assert live == [], [(r.applied_state, r.applied_reason) for r in live]

    from app.services import planning_change_service
    from .test_ingest_documents import _USER_ID

    _register(None)
    calls = _captured_dispatches(monkeypatch)
    try:
        planning_change_service.apply(env.db, str(batch_id), _USER_ID)
        env.db.commit()
    except Exception:  # nothing pending to apply is an acceptable refusal
        env.db.rollback()
    env.db.expire_all()
    assert _row_snapshot(env, row_id)["state"] != INQUIRY_CANCELLED
    assert _handover_calls(calls) == []


# ====================================================== Q1(b) section (owner answer pending)
# Q1(b): pending owner answer.
def test_ac_wc_6_q1b_a_header_cancel_push_leaves_the_oi_row_state_and_ack_alone(env):
    record, header, line_x, y = _push_so(env)
    row_id, _ = _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING)

    _header_cancel_push(env, record, y)

    snap = _row_snapshot(env, row_id)
    assert (snap["state"], snap["ack_state"]) == (INQUIRY_RAISED, ACK_AWAITING), snap
    assert snap["ack_state"] != ACK_ACKNOWLEDGED


# Q1(b): pending owner answer.
def test_ac_wc_6_q1b_an_so_delete_leaves_the_oi_row_state_and_ack_alone(env):
    record, header, line_x, y = _push_so(env)
    row_id, _ = _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING)

    _delete_so(env, record)

    snap = _row_snapshot(env, row_id)
    assert (snap["state"], snap["ack_state"]) == (INQUIRY_RAISED, ACK_AWAITING), snap




# ============================================================================ AC-WC-7 (failed record)
def test_ac_wc_7_a_failed_record_raises_no_cancelled_row(env, monkeypatch):
    """A header-cancel push whose record FAILS after the BEFORE capture ran (the last
    statement of `_apply`, `_record_hook_state`, raises) is rolled back and reported failed:
    it must raise no `cancelled` row, and the OI row stays unchanged."""
    from app.services.document_ingest_service import DocumentIngestService

    record, header, line_x, y = _push_so(env)
    row_id, _ = _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING)
    before = _row_snapshot(env, row_id)

    def _boom(self, *args, **kwargs):
        raise RuntimeError("ZZT injected failure")

    monkeypatch.setattr(DocumentIngestService, "_record_hook_state", _boom)

    res = env.post(INGEST_SO, [dict(record, status="cancelled", lines=[y])])
    env.db.rollback()
    env.db.expire_all()

    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] == "failed", res.text
    assert _cancelled_rows(env, line_x["id"]) == []
    assert _row_snapshot(env, row_id) == before
