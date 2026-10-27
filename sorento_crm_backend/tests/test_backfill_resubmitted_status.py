"""The Q5 backfill relabels ONLY rows whose data proves a resubmission, and --revert undoes it.

Plan: documentation/plans/forms/PLAN-resubmitted-status-27oct.md.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from tests._pg_fixture import blank_session

_SPEC = importlib.util.spec_from_file_location(
    "backfill_resubmitted_status",
    Path(__file__).resolve().parents[1] / "scripts" / "backfill_resubmitted_status.py",
)
backfill = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(backfill)


@pytest.fixture
def conn():
    with blank_session() as db:
        yield db.connection()


def _id() -> str:
    return str(uuid.uuid4())


def _audit(conn, entity_type: str, entity_id: str, old: str, new: str, when: datetime) -> None:
    conn.execute(
        text(
            "INSERT INTO audit_logs (id, entity_type, entity_id, action, changed_at, old_values, new_values) "
            "VALUES (:id, :et, :eid, 'UPDATE', :at, CAST(:old AS jsonb), CAST(:new AS jsonb))"
        ),
        {
            "id": _id(),
            "et": entity_type,
            "eid": entity_id,
            "at": when,
            "old": json.dumps({"status": old}),
            "new": json.dumps({"status": new}),
        },
    )


def _complaint(conn, status: str, rejected: bool) -> str:
    cid = _id()
    conn.execute(
        text(
            "INSERT INTO complaints (id, complaint_number, status, rejected_at) "
            "VALUES (:id, :no, :st, :rej)"
        ),
        {"id": cid, "no": "ZZT-" + cid[:6], "st": status, "rej": datetime.utcnow() if rejected else None},
    )
    return cid


def _request(conn, status: str, history: list[tuple[str, str]]) -> str:
    rid = _id()
    conn.execute(
        text(
            "INSERT INTO purchase_requests (id, request_type, request_number, status, source) "
            "VALUES (:id, 'purchase_request', :no, :st, 'portal')"
        ),
        {"id": rid, "no": "ZZT-" + rid[:6], "st": status},
    )
    start = datetime.utcnow() - timedelta(days=3)
    for step, (old, new) in enumerate(history):
        _audit(conn, "purchase_requests", rid, old, new, start + timedelta(hours=step))
    return rid


def _inquiry(conn, status: str, history: list[tuple[str, str]]) -> str:
    sid = _id()
    conn.execute(
        text("INSERT INTO stock_inquiries (id, inquiry_number, status) VALUES (:id, :no, :st)"),
        {"id": sid, "no": "ZZT-" + sid[:6], "st": status},
    )
    start = datetime.utcnow() - timedelta(days=3)
    for step, (old, new) in enumerate(history):
        _audit(conn, "stock_inquiries", sid, old, new, start + timedelta(hours=step))
    return sid


def _status(conn, table: str, row_id: str) -> str:
    return conn.execute(text(f"SELECT status FROM {table} WHERE id = :id"), {"id": row_id}).scalar()


def test_only_proven_resubmissions_are_candidates(conn):
    proven_c = _complaint(conn, "submitted", rejected=True)
    first_c = _complaint(conn, "submitted", rejected=False)
    proven_pr = _request(conn, "submitted", [("draft", "submitted"), ("submitted", "rejected"), ("rejected", "submitted")])
    first_pr = _request(conn, "submitted", [("draft", "submitted")])
    proven_si = _inquiry(
        conn,
        "pending_project_sales",
        [("draft", "pending_project_sales"), ("pending_project_sales", "rejected"), ("rejected", "pending_project_sales")],
    )
    first_si = _inquiry(conn, "pending_project_sales", [("draft", "pending_project_sales")])

    found = {form: {row_id for row_id, _ref in rows} for form, rows in backfill.candidates(conn).items()}

    assert proven_c in found["complaint"] and first_c not in found["complaint"]
    assert proven_pr in found["purchase_request"] and first_pr not in found["purchase_request"]
    assert proven_si in found["stock_inquiry"] and first_si not in found["stock_inquiry"]


def test_apply_relabels_and_revert_puts_them_back(conn):
    complaint = _complaint(conn, "submitted", rejected=True)
    inquiry = _inquiry(conn, "pending_project_sales", [("rejected", "pending_project_sales")])

    found = backfill.candidates(conn)
    found = {
        form: [row for row in rows if row[0] in (complaint, inquiry)] for form, rows in found.items()
    }
    record = backfill.apply(conn, found)

    assert _status(conn, "complaints", complaint) == "resubmitted"
    assert _status(conn, "stock_inquiries", inquiry) == "resubmitted"

    backfill.revert(conn, json.loads(json.dumps(record)))

    assert _status(conn, "complaints", complaint) == "submitted"
    assert _status(conn, "stock_inquiries", inquiry) == "pending_project_sales"


def test_revert_refuses_a_record_naming_a_column_the_script_never_writes(conn):
    with pytest.raises(SystemExit):
        backfill.revert(conn, {"x": {"table": "users", "column": "password", "from": "a", "to": "b", "ids": []}})
