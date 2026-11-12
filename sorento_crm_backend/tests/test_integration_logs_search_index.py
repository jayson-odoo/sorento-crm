"""INTLOG-SPEED-2: the Integration Log search box is served by one trigram index.

Crew pass on 086a3235 (dev copy, ~1.2M rows): an 8-character Business ID search took 19.5-28 s.
The search was an OR of seven ``ILIKE '%term%'`` (one on ``business_id::text``); no index serves
that, so a term that matches few rows read the whole table. The fix: one search expression over
the columns, one GIN ``gin_trgm_ops`` index on exactly that expression
(``online_index.INTEGRATION_LOG_SEARCH_INDEXES``), built online by
``il_0002_integration_log_search``, and the list's search matches against the same expression.

These tests pin the contract the speed depends on: the SQL the route runs for a search can use
that index (EXPLAIN with sequential scans priced out), for the 8-character Business ID the grid
shows, a full UUID, and a word. Postgres only; blank schema, the index built in it the way the
migration builds it.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event

from app.database import engine

from app.models.integration import IntegrationLog
from app.utils import online_index
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session

LOGS = "/api/v1/integrations/logs/"
BASE = datetime(2026, 11, 1, 8, 0)
BACKEND = Path(__file__).resolve().parents[1]
REVISION = "il_0002_integration_log_search"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _index_def():
    [(table, name, columns)] = online_index.INTEGRATION_LOG_SEARCH_INDEXES
    return table, name, columns


def _seed(db, n=40):
    rows = []
    for i in range(n):
        row = IntegrationLog(
            id=str(uuid.uuid4()),
            integration_channel="n8n",
            business_table="attachments",
            business_id=str(uuid.uuid4()),
            direction="outbound",
            endpoint=f"/webhook/default/{i}",
            http_method="POST",
            status="success",
            external_reference=f"REF-{i:05d}",
            created_at=BASE + timedelta(minutes=i),
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def _search_plans(client, db, term):
    """EXPLAIN every integration_log SELECT the route runs for `term`, so the plan shows whether
    the search predicate CAN use the trigram index."""
    table, name, columns = _index_def()
    conn = db.connection()
    conn.exec_driver_sql(f"CREATE INDEX {name} ON {table} {columns}")
    seen = []

    def capture(_conn, _cursor, statement, parameters, _context, _many):
        if "integration_log" in statement and statement.lstrip().upper().startswith("SELECT"):
            seen.append((statement, parameters))

    event.listen(conn, "before_cursor_execute", capture)
    try:
        resp = get(client, LOGS, [("query", term), ("limit", 50)])
    finally:
        event.remove(conn, "before_cursor_execute", capture)
    assert resp.status_code == 200, resp.text
    # Price out every plan that does not need the search predicate's own index: a sequential
    # scan, and a plain index walk (created_at) that filters row by row. What is left is a bitmap
    # scan, which only an index matching the predicate can drive.
    conn.exec_driver_sql("SET LOCAL enable_seqscan = off")
    conn.exec_driver_sql("SET LOCAL enable_indexscan = off")
    plans = []
    for statement, parameters in seen:
        rows = conn.exec_driver_sql("EXPLAIN " + statement, parameters).fetchall()
        plans.append("\n".join(r[0] for r in rows))
    conn.exec_driver_sql("SET LOCAL enable_seqscan = on")
    conn.exec_driver_sql("SET LOCAL enable_indexscan = on")
    return resp.json(), plans


def test_the_index_is_a_gin_trigram_index_on_integration_log():
    table, name, columns = _index_def()
    assert table == "integration_log"
    assert name == "ix_integration_log_search_trgm"
    assert columns.startswith("USING gin (") and columns.rstrip().endswith("gin_trgm_ops)")


@pytest.mark.parametrize("kind", ["business_id_prefix", "full_uuid", "word"])
def test_a_search_can_use_the_trigram_index(client, db, kind):
    rows = _seed(db)
    hit = rows[7]
    term = {
        "business_id_prefix": hit.business_id[:8],
        "full_uuid": hit.business_id.upper(),
        "word": "REF-00007",
    }[kind]
    body, plans = _search_plans(client, db, term)
    assert [r["id"] for r in body["data"]] == [hit.id]
    assert plans, "the route ran no integration_log SELECT"
    for plan in plans:
        assert "ix_integration_log_search_trgm" in plan, plan


def test_the_migration_builds_it_online_and_the_retry_passes_it(monkeypatch):
    from scripts import ensure_goods_chain_indexes as retry

    path = BACKEND / "alembic" / "versions" / f"{REVISION}.py"
    spec = importlib.util.spec_from_file_location(REVISION, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == REVISION and len(REVISION) <= 32

    captured = []

    def spy(_bind, indexes):
        captured.append(tuple(indexes))
        return True

    monkeypatch.setattr(online_index, "ensure_indexes_online", spy)
    assert retry.run(engine) is True
    assert online_index.INTEGRATION_LOG_SEARCH_INDEXES[0] in captured[-1]


def _scratch_with_log_table():
    """A committed scratch schema holding an integration_log shaped like the real one, on an
    AUTOCOMMIT connection with search_path pinned to it (ANALYZE cannot run in the test's
    rolled-back transaction and must not touch the shared table)."""
    import os
    from contextlib import contextmanager

    @contextmanager
    def scratch():
        schema = f"zzs_il2_{os.getpid()}_{uuid.uuid4().hex[:6]}"
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            try:
                conn.exec_driver_sql(f'SET search_path TO "{schema}", public')
                conn.exec_driver_sql(
                    "CREATE TABLE integration_log (LIKE public.integration_log INCLUDING DEFAULTS)"
                )
                conn.exec_driver_sql(
                    "INSERT INTO integration_log (id, integration_channel, business_table, business_id, "
                    "direction, endpoint, http_method, status, retry_count, max_retry_allowed, created_at, updated_at) "
                    "SELECT gen_random_uuid(), 'n8n', 'attachments', gen_random_uuid(), 'outbound', "
                    "'/webhook/' || g, 'POST', 'success', 0, 3, now(), now() FROM generate_series(1, 200) g"
                )
                table, name, columns = _index_def()
                conn.exec_driver_sql(f"CREATE INDEX {name} ON {table} {columns}")
                yield schema, conn, name
            finally:
                conn.exec_driver_sql("RESET search_path")
                conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')

    return scratch()


def _expression_stats(conn, schema, name):
    return conn.exec_driver_sql(
        "SELECT count(*) FROM pg_statistic s JOIN pg_class c ON c.oid = s.starelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %(s)s AND c.relname = %(n)s",
        {"s": schema, "n": name},
    ).scalar()


def test_a_fresh_build_is_followed_by_statistics_on_the_search_expression():
    """Without them the planner guesses ~100 matches for any term and sends a common one (216k of
    1.3M rows) through the index and a full sort: 3-4 s instead of 70-160 ms (sandbox timing)."""
    with _scratch_with_log_table() as (schema, conn, name):
        assert _expression_stats(conn, schema, name) == 0
        online_index.analyze_after_search_index_build(conn, None)
        assert _expression_stats(conn, schema, name) > 0


def test_an_index_that_was_already_valid_is_not_analyzed_again():
    with _scratch_with_log_table() as (schema, conn, name):
        online_index.analyze_after_search_index_build(conn, True)
        assert _expression_stats(conn, schema, name) == 0
