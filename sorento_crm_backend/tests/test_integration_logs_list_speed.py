"""INTLOG-SPEED: the Integration Log list never counts the whole table, sorts every column on the
server, and its default page reads ``ix_integration_log_created_at`` backward.

Plan: ``documentation/plans/infra/PLAN-intlog-speed-03nov.md``. Crew measured the prod clone
(1.2M rows): the exact ``count()`` with the list's ORDER BY still attached took 1.5-9.7 s per page
load. Postgres only; rows seeded into a blank schema; the cap is shrunk so a handful of rows can
cross it.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, text

from app.models.integration import IntegrationLog
from app.services import integration_service
from app.services.integration_service import IntegrationLogService
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

LOGS = "/api/v1/integrations/logs/"
BASE = datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _log(db, i, *, channel="n8n", table=None, status="success", retry=0, processed=None):
    row = IntegrationLog(
        id=str(uuid.uuid4()),
        integration_channel=channel,
        business_table=table or unique_code("tb"),
        business_id=str(uuid.uuid4()),
        direction="outbound",
        endpoint="/x",
        http_method="POST",
        status=status,
        retry_count=retry,
        created_at=BASE + timedelta(minutes=i),
        processed_at=processed,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def seven(db):
    """Seven rows, created a minute apart: rows[6] is the newest."""
    return [_log(db, i) for i in range(7)]


def _page(client, **params):
    resp = get(client, LOGS, list(params.items()))
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- capped count --------------------------------------------------------------------------


def test_total_is_exact_and_not_capped_under_the_cap(client, seven):
    body = _page(client, page=1, limit=3)
    assert body["pagination"]["total"] == 7
    assert body["pagination"]["total_capped"] is False


def test_total_is_capped_and_flagged_over_the_cap(client, seven, monkeypatch):
    monkeypatch.setattr(integration_service, "INTEGRATION_LOG_COUNT_CAP", 4)
    body = _page(client, page=1, limit=2)
    assert body["pagination"]["total"] == 4
    assert body["pagination"]["total_capped"] is True
    assert [r["id"] for r in body["data"]] == [seven[6].id, seven[5].id]


def test_exactly_at_the_cap_is_not_capped(client, seven, monkeypatch):
    monkeypatch.setattr(integration_service, "INTEGRATION_LOG_COUNT_CAP", 7)
    body = _page(client, page=1, limit=2)
    assert body["pagination"]["total"] == 7
    assert body["pagination"]["total_capped"] is False


def test_cap_window_grows_with_the_offset(client, seven, monkeypatch):
    """Page 2 of limit 2 sits at offset 2, so the window is 2 + 4 = 6 rows, under the 7 there are."""
    monkeypatch.setattr(integration_service, "INTEGRATION_LOG_COUNT_CAP", 4)
    body = _page(client, page=2, limit=2)
    assert body["pagination"]["total"] == 6
    assert body["pagination"]["total_capped"] is True
    assert [r["id"] for r in body["data"]] == [seven[4].id, seven[3].id]
    # Offset 4: window 8 covers all 7 rows, so the total turns exact and the pager finds its end.
    body = _page(client, page=3, limit=2)
    assert body["pagination"]["total"] == 7
    assert body["pagination"]["total_capped"] is False


def test_last_page_holds_the_remainder(client, seven):
    body = _page(client, page=3, limit=3)
    assert [r["id"] for r in body["data"]] == [seven[0].id]
    assert body["pagination"] == {"total": 7, "page": 3, "limit": 3, "total_capped": False}


def test_filtered_total_is_exact_under_the_cap(client, db, seven):
    channel = unique_code("ch")
    a = _log(db, 20, channel=channel, status="failed")
    b = _log(db, 21, channel=channel, status="pending")
    _log(db, 22, channel=channel, status="success")
    body = _page(client, integration_channel=channel, status="failed,pending", limit=50)
    assert body["pagination"]["total"] == 2
    assert body["pagination"]["total_capped"] is False
    assert [r["id"] for r in body["data"]] == [b.id, a.id]


def test_empty_result(client, db):
    body = _page(client, integration_channel=unique_code("none"))
    assert body["pagination"]["total"] == 0
    assert body["pagination"]["total_capped"] is False
    assert body["empty"] is True


def test_count_statement_has_no_order_by_and_is_bounded(db, seven):
    """The 1.2M-row disk sort came from the list's ORDER BY riding into the count."""
    seen: list[str] = []

    def _capture(_conn, _cursor, statement, _params, _context, _many):
        seen.append(statement)

    bind = db.connection()
    event.listen(bind, "before_cursor_execute", _capture)
    try:
        IntegrationLogService(db).list_integration_logs(page=1, limit=2)
    finally:
        event.remove(bind, "before_cursor_execute", _capture)
    counts = [s for s in seen if "count(" in s.lower()]
    assert len(counts) == 1, seen
    count_sql = counts[0].upper()
    assert "ORDER BY" not in count_sql
    assert "LIMIT" in count_sql


# --- server-side sort ----------------------------------------------------------------------


@pytest.fixture
def sortable(db):
    tag = unique_code("srt")
    return [
        _log(db, 1, channel=f"{tag}-b", table="t-c", status="pending", retry=2,
             processed=BASE + timedelta(hours=3)),
        _log(db, 2, channel=f"{tag}-c", table="t-a", status="failed", retry=0,
             processed=BASE + timedelta(hours=1)),
        _log(db, 3, channel=f"{tag}-a", table="t-b", status="success", retry=1,
             processed=BASE + timedelta(hours=2)),
    ]


@pytest.mark.parametrize(
    "column,asc_order",
    [
        ("integration_channel", [2, 0, 1]),
        ("business_table", [1, 2, 0]),
        ("status", [1, 0, 2]),
        ("retry_count", [1, 2, 0]),
        ("created_at", [0, 1, 2]),
        ("processed_at", [1, 2, 0]),
    ],
)
def test_every_column_sorts_server_side(client, sortable, column, asc_order):
    channels = ",".join(r.integration_channel for r in sortable)
    asc = _page(client, integration_channel=channels, sort=column, dir="asc")
    assert [r["id"] for r in asc["data"]] == [sortable[i].id for i in asc_order]
    desc = _page(client, integration_channel=channels, sort=column, dir="desc")
    assert [r["id"] for r in desc["data"]] == [sortable[i].id for i in reversed(asc_order)]


def test_business_id_sorts_server_side(client, sortable):
    channels = ",".join(r.integration_channel for r in sortable)
    asc = _page(client, integration_channel=channels, sort="business_id", dir="asc")
    want = sorted(sortable, key=lambda r: uuid.UUID(str(r.business_id)))
    assert [r["id"] for r in asc["data"]] == [r.id for r in want]


def test_unknown_sort_falls_back_to_newest_first(client, sortable):
    channels = ",".join(r.integration_channel for r in sortable)
    body = _page(client, integration_channel=channels, sort="request_payload", dir="asc")
    assert [r["id"] for r in body["data"]] == [sortable[2].id, sortable[1].id, sortable[0].id]


# --- the default page uses the created_at index --------------------------------------------


def test_default_page_query_reads_created_at_index_backward(db, seven):
    """EXPLAIN the exact SQL the default page sends.

    A blank schema holds a handful of rows, where a seq scan is cheapest, so the planner is told
    to avoid one; what this proves is that the statement's shape lets Postgres serve
    ``ORDER BY created_at DESC LIMIT n`` from ``ix_integration_log_created_at`` without a
    full sort - which is what makes page 1 a 3 ms read on the 1.2M-row clone.
    """
    seen: list[tuple[str, object]] = []

    def _capture(_conn, _cursor, statement, params, _context, _many):
        seen.append((statement, params))

    bind = db.connection()
    event.listen(bind, "before_cursor_execute", _capture)
    try:
        IntegrationLogService(db).list_integration_logs(page=1, limit=50)
    finally:
        event.remove(bind, "before_cursor_execute", _capture)
    page_sql = [(s, p) for s, p in seen if "ORDER BY" in s.upper() and "count(" not in s.lower()]
    assert len(page_sql) == 1, seen
    statement, params = page_sql[0]

    raw = bind.connection.dbapi_connection.cursor()
    try:
        raw.execute("SET LOCAL enable_seqscan = off")
        raw.execute("SET LOCAL enable_bitmapscan = off")
        raw.execute("EXPLAIN " + statement, params)
        plan = "\n".join(row[0] for row in raw.fetchall())
    finally:
        raw.execute("RESET enable_seqscan")
        raw.execute("RESET enable_bitmapscan")
        raw.close()
    assert "Index Scan Backward using ix_integration_log_created_at" in plan, plan
    # Only an Incremental Sort (the id tiebreaker within equal timestamps) may sit above it,
    # never a full Sort of every row.
    assert not re.search(r"(^|->)\s*Sort\s+\(", plan, re.MULTILINE), plan


def test_created_at_index_exists_on_the_model():
    names = {ix.name for ix in IntegrationLog.__table__.indexes}
    assert "ix_integration_log_created_at" in names


def test_explain_helper_sees_the_index_in_the_blank_schema(db):
    found = db.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = 'ix_integration_log_created_at'")
    ).first()
    assert found is not None


# --- ties: paging a sort group with equal values neither repeats nor skips a row ------------


@pytest.mark.parametrize("column", ["status", "created_at"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_ties_page_without_repeats_or_gaps(client, db, column, direction):
    channel = unique_code("tie")
    rows = []
    for _ in range(5):
        row = _log(db, 0, channel=channel, status="success")  # same status AND created_at
        rows.append(row)
    seen = []
    for page in range(1, 6):
        body = _page(client, integration_channel=channel, sort=column, dir=direction,
                     page=page, limit=1)
        seen.extend(r["id"] for r in body["data"])
    assert sorted(seen) == sorted(r.id for r in rows)
    want = sorted((r.id for r in rows), reverse=direction == "desc")
    assert seen == want


def test_status_desc_has_no_nulls_clause(db):
    """A NOT NULL column sorted DESC must not carry NULLS LAST, or Postgres cannot read its
    ascending index backward and sorts the whole table instead."""
    seen: list[str] = []

    def _capture(_conn, _cursor, statement, _params, _context, _many):
        seen.append(statement)

    bind = db.connection()
    event.listen(bind, "before_cursor_execute", _capture)
    try:
        IntegrationLogService(db).list_integration_logs(sort="status", sort_dir="desc")
        IntegrationLogService(db).list_integration_logs(sort="processed_at", sort_dir="desc")
    finally:
        event.remove(bind, "before_cursor_execute", _capture)
    pages = [s.upper() for s in seen if "ORDER BY" in s.upper()]
    assert "NULLS LAST" not in pages[0]
    assert "NULLS LAST" in pages[1]


def test_capped_count_without_any_filter_counts_rows(db, seven):
    """With no WHERE at all the count still reads FROM the table (it once compiled to a bare
    SELECT 1, which always counts one)."""
    total, capped = IntegrationLogService._capped_count(db.query(IntegrationLog), 0)
    assert (total, capped) == (7, False)
