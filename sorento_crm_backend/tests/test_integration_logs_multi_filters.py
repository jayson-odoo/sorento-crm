"""FILTER-MULTISELECT PR2: Integration logs (status, channel, table) and Smart linkage (status,
channel) read the same route, and each filter takes several values (OR within, AND across). Red first;
Postgres only; rows seeded here into a blank schema.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.integration import IntegrationLog
from tests._multi_filter_client import get, ok_ids, open_client
from tests._pg_fixture import blank_session, unique_code

LOGS = "/api/v1/integrations/logs/"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _log(db, channel, table, status):
    row = IntegrationLog(
        id=str(uuid.uuid4()), integration_channel=channel, business_table=table,
        business_id=str(uuid.uuid4()), direction="outbound", endpoint="/x", http_method="POST",
        status=status,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def seeded(db):
    ch = [unique_code(f"ch{i}") for i in range(3)]
    tb = [unique_code(f"tb{i}") for i in range(3)]
    a = _log(db, ch[0], tb[0], "success")
    b = _log(db, ch[1], tb[1], "failed")
    c = _log(db, ch[2], tb[2], "pending")
    d = _log(db, ch[0], tb[1], "failed")
    return dict(ch=ch, tb=tb, a=a, b=b, c=c, d=d)


def _ids(client, pairs):
    return ok_ids(get(client, LOGS, [("limit", 200), *pairs]))


def test_status_union(client, seeded):
    s = seeded
    assert _ids(client, [("status", "success,pending")]) == {s["a"].id, s["c"].id}


def test_status_single_and_repeated(client, seeded):
    s = seeded
    assert _ids(client, [("status", "failed")]) == {s["b"].id, s["d"].id}
    assert _ids(client, [("status", "success"), ("status", "pending")]) == {s["a"].id, s["c"].id}


def test_channel_union(client, seeded):
    s = seeded
    got = _ids(client, [("integration_channel", f"{s['ch'][1]},{s['ch'][2]}")])
    assert got == {s["b"].id, s["c"].id}


def test_channel_single_and_repeated(client, seeded):
    s = seeded
    assert _ids(client, [("integration_channel", s["ch"][0])]) == {s["a"].id, s["d"].id}
    got = _ids(client, [("integration_channel", s["ch"][1]), ("integration_channel", s["ch"][2])])
    assert got == {s["b"].id, s["c"].id}


def test_table_union(client, seeded):
    s = seeded
    got = _ids(client, [("business_table", f"{s['tb'][0]},{s['tb'][2]}")])
    assert got == {s["a"].id, s["c"].id}


def test_table_single_and_repeated(client, seeded):
    s = seeded
    assert _ids(client, [("business_table", s["tb"][1])]) == {s["b"].id, s["d"].id}
    got = _ids(client, [("business_table", s["tb"][0]), ("business_table", s["tb"][2])])
    assert got == {s["a"].id, s["c"].id}


def test_filters_and_across_each_other(client, seeded):
    s = seeded
    got = _ids(client, [("status", "failed,pending"), ("integration_channel", f"{s['ch'][0]},{s['ch'][2]}"),
                        ("business_table", f"{s['tb'][1]},{s['tb'][2]}")])
    assert got == {s["c"].id, s["d"].id}


def test_the_integration_management_mount_reads_the_same_filters(client, seeded):
    s = seeded
    resp = get(client, "/api/v1/integration-management/integration-logs/",
               [("limit", 200), ("status", "success,pending")])
    assert ok_ids(resp) == {s["a"].id, s["c"].id}
