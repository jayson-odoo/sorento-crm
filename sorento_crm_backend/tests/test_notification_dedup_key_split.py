"""notifications.source_entity_id split into a uuid entity ref + a text dedup_key.

`source_entity_id` used to be overloaded - a real entity uuid for entity
notifications, or a synthetic idempotency key with no entity behind it
(`alert:...`, `digest:<date>`, `{type}_{batch}`) for batched/periodic ones. That
overload forced the column to be text. It now holds only a uuid (or NULL), and
the idempotency scope lives in its own `dedup_key` column.

These tests pin the contract that made the split safe to do transparently:
  * the dedup scope still de-duplicates exactly as before, whether the caller
    passes a uuid or a synthetic string;
  * a synthetic value never lands in the uuid `source_entity_id` column;
  * a real uuid is kept in `source_entity_id` AND used as the default dedup key.

Run: pytest tests/test_notification_dedup_key_split.py -v
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.models.notification import Notification, NotificationDelivery
from app.services.notification_service import (
    NotificationService,
    _split_entity_and_dedup,
)
from tests._pg_fixture import blank_session


# --------------------------------------------------------------------------- #
# The pure helper - the crux of why the split is transparent to callers.
# --------------------------------------------------------------------------- #
def test_split_uuid_source_populates_both():
    u = str(uuid.uuid4())
    entity, dedup = _split_entity_and_dedup(u, None)
    assert entity == u, "a real uuid stays in source_entity_id"
    assert dedup == u, "and doubles as the default dedup scope (old behaviour)"


# Two of these values embed a fresh uuid4, generated at COLLECTION time. Without
# explicit ids pytest names those cases after the value itself, so every xdist
# worker collects a different node id for them and the run aborts with
# "Different tests were collected between gw0 and gwN" before a single test
# executes. The ids below are stable, so the workers agree; the values stay
# random on purpose, since the point is that the helper reads the SHAPE of the
# key rather than recognising particular strings.
@pytest.mark.parametrize(
    "synthetic",
    [
        "alert:integration_spike:2026-07-13T08:24:10",
        "digest:2026-07-13",
        f"{uuid.uuid4()}_{uuid.uuid4().hex[:16]}",
        f"{uuid.uuid4()}:2026-06-20",
    ],
    ids=["alert_scope", "digest_date", "uuid_underscore_suffix", "uuid_colon_date"],
)
def test_split_synthetic_source_never_enters_uuid_column(synthetic):
    entity, dedup = _split_entity_and_dedup(synthetic, None)
    assert entity is None, "a synthetic key must not land in the uuid column"
    assert dedup == synthetic, "but must still be the dedup scope so idempotency holds"


def test_split_explicit_dedup_key_wins():
    u = str(uuid.uuid4())
    entity, dedup = _split_entity_and_dedup(u, "custom-scope")
    assert entity == u
    assert dedup == "custom-scope"


def test_split_none_is_none():
    assert _split_entity_and_dedup(None, None) == (None, None)


# --------------------------------------------------------------------------- #
# End-to-end through create(): idempotency preserved, columns populated right.
# --------------------------------------------------------------------------- #
@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture(autouse=True)
def _no_queue():
    # create() enqueues async deliveries; keep the test off Redis.
    with patch("app.services.queue_service.enqueue_job", return_value=None):
        yield


def test_create_dedups_on_a_synthetic_key(db):
    """Two health-alert-style creates with the same synthetic key → one row."""
    svc = NotificationService(db)
    key = "alert:integration_spike:2026-07-13T08:24:10"
    a = svc.create(
        user_id="u1", type="health_alert", title="A",
        source_entity_type="system_health", source_entity_id=key,
        event_type="health_alert",
    )
    b = svc.create(
        user_id="u1", type="health_alert", title="A again",
        source_entity_type="system_health", source_entity_id=key,
        event_type="health_alert",
    )
    assert a.id == b.id, "second create must be idempotent on the dedup key"
    assert db.query(Notification).count() == 1
    row = db.query(Notification).first()
    assert row.source_entity_id is None, "synthetic key must not fill the uuid column"
    assert row.dedup_key == key


def test_create_keeps_a_real_uuid_and_dedups_on_it(db):
    svc = NotificationService(db)
    ent = str(uuid.uuid4())
    a = svc.create(
        user_id="u1", type="complaint_update", title="C",
        source_entity_type="complaint", source_entity_id=ent,
        event_type="responded",
    )
    b = svc.create(
        user_id="u1", type="complaint_update", title="C again",
        source_entity_type="complaint", source_entity_id=ent,
        event_type="responded",
    )
    assert a.id == b.id
    assert db.query(Notification).count() == 1
    row = db.query(Notification).first()
    assert row.source_entity_id == ent, "real entity uuid is preserved"
    assert row.dedup_key == ent, "and is the default dedup scope"


def test_different_dedup_keys_are_not_merged(db):
    """Two periods of the same digest must produce two notifications."""
    svc = NotificationService(db)
    for day in ("digest:2026-07-13", "digest:2026-07-14"):
        svc.create(
            user_id="u1", type="digest", title="D",
            source_entity_type="system_health", source_entity_id=day,
            event_type="health_digest",
        )
    assert db.query(Notification).count() == 2
    assert {r.source_entity_id for r in db.query(Notification).all()} == {None}
