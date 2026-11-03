"""INTLOG-SEARCH: the Integration Log search box filters on the server.

The list sent ``query`` (``integrationLogService.ts``) and the route had no such parameter, so the
box did nothing. Postgres only; rows seeded into a blank schema.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.integration import IntegrationLog
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

LOGS = "/api/v1/integrations/logs/"
BASE = datetime(2026, 11, 1, 8, 0)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _log(db, i, **over):
    fields = dict(
        id=str(uuid.uuid4()),
        integration_channel="n8n",
        business_table="attachments",
        business_id=str(uuid.uuid4()),
        direction="outbound",
        endpoint="/webhook/default",
        http_method="POST",
        status="success",
        created_at=BASE + timedelta(minutes=i),
    )
    fields.update(over)
    row = IntegrationLog(**fields)
    db.add(row)
    db.flush()
    return row


def _ids(client, *pairs):
    resp = get(client, LOGS, [("limit", 100), *pairs])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return [r["id"] for r in body["data"]], body["pagination"]["total"]


def test_search_matches_channel_case_insensitively(client, db):
    tag = unique_code("chan", alpha=True)
    hit = _log(db, 1, integration_channel=tag)
    _log(db, 2)
    ids, total = _ids(client, ("query", tag.lower()))
    assert ids == [hit.id] and total == 1


@pytest.mark.parametrize(
    "field", ["business_table", "endpoint", "external_reference", "error_message"]
)
def test_search_matches_each_text_column(client, db, field):
    tag = unique_code("txt", alpha=True)
    hit = _log(db, 1, **{field: f"before {tag} after"})
    _log(db, 2)
    ids, total = _ids(client, ("query", tag))
    assert ids == [hit.id] and total == 1


def test_search_matches_the_business_id_prefix_the_grid_shows(client, db):
    """The grid shows the first 8 characters of business_id; pasting them finds the row."""
    hit = _log(db, 1)
    _log(db, 2)
    ids, total = _ids(client, ("query", str(hit.business_id)[:8]))
    assert ids == [hit.id] and total == 1


@pytest.mark.parametrize("column", ["id", "business_id", "correlation_id"])
def test_search_with_a_full_uuid_matches_exactly(client, db, column):
    value = str(uuid.uuid4())
    over = {} if column == "id" else {column: value}
    hit = _log(db, 1, **({"id": value} if column == "id" else over))
    _log(db, 2)
    ids, total = _ids(client, ("query", value.upper()))
    assert ids == [hit.id] and total == 1


def test_search_combines_with_filters(client, db):
    tag = unique_code("both", alpha=True)
    failed = _log(db, 1, endpoint=f"/x/{tag}", status="failed")
    _log(db, 2, endpoint=f"/x/{tag}", status="success")
    ids, total = _ids(client, ("query", tag), ("status", "failed"))
    assert ids == [failed.id] and total == 1


def test_like_wildcards_in_the_term_are_literal(client, db):
    tag = unique_code("wild", alpha=True)
    literal = _log(db, 1, endpoint=f"/x/{tag}%_done")
    _log(db, 2, endpoint=f"/x/{tag}AAdone")
    ids, _ = _ids(client, ("query", f"{tag}%_"))
    assert ids == [literal.id]


def test_blank_search_is_ignored(client, db):
    a = _log(db, 1)
    b = _log(db, 2)
    ids, total = _ids(client, ("query", "   "))
    assert ids == [b.id, a.id] and total == 2
