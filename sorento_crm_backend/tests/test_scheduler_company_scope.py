"""S1 / AC-F2, AC-F4 - background ticks must opt out of the company-scope filter.

Every session defaults to ``UNSET``, which the filter treats as zero rows (fail
closed). Correct for an unauthenticated request; wrong for a scheduler tick, which
has no principal but must still see every company's work. The failure mode is
silent: the overdue-SLA scan reads zero teams, escalates nothing, and logs nothing.

This is the test that stops a future refactor reintroducing a bare SessionLocal().
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from app.models.base import UNSET, get_company_scope, set_company_scope
from app.models.inventory import Warehouse
from app.scheduler.task_scheduler import scheduler_session
from tests._pg_fixture import blank_session, unique_code


SCHEDULER_SRC = Path(__file__).resolve().parents[1] / "app" / "scheduler" / "task_scheduler.py"


def test_scheduler_session_is_scoped_to_all_companies():
    """AC-F2 - None means 'no predicate', i.e. every company."""
    with scheduler_session() as db:
        assert get_company_scope(db) is None


def test_scheduler_session_closes_even_when_the_body_raises():
    """A leaked session per failing tick would exhaust the pool over days of ticks."""
    closed = []

    with pytest.raises(RuntimeError):
        with scheduler_session() as db:
            original_close = db.close
            db.close = lambda: (closed.append(True), original_close())[1]
            raise RuntimeError("tick blew up")

    assert closed == [True]


def test_no_bare_session_local_remains_in_the_scheduler():
    """AC-F2 - a 5th SessionLocal() added later would silently fail closed again."""
    source = SCHEDULER_SRC.read_text()
    # Strip the import line and the helper's own single legitimate use.
    bare = [
        line.strip()
        for line in source.splitlines()
        if re.search(r"(?<!def )\bSessionLocal\(\)", line)
    ]
    assert len(bare) == 1, (
        "SessionLocal() should only be called inside scheduler_session(); "
        f"found {len(bare)}: {bare}"
    )


def test_unset_scope_really_does_hide_rows(monkeypatch):
    """The premise of the whole slice, pinned so it cannot be assumed away."""
    with blank_session() as db:
        db.add(
            Warehouse(
                id=str(uuid.uuid4()),
                warehouse_code=unique_code("WH"),
                warehouse_name="ZZT scope probe",
                company_id="00000000-0000-0000-0000-000000000001",
            )
        )
        db.flush()

        set_company_scope(db, None)
        assert db.query(Warehouse).filter(Warehouse.warehouse_name == "ZZT scope probe").count() == 1

        set_company_scope(db, UNSET)
        assert db.query(Warehouse).filter(Warehouse.warehouse_name == "ZZT scope probe").count() == 0
