"""Fix lane round 5 on PR #1302 (#1286): the record header card, 27 Sep.

F1 (backend half): the header shows how many products carry the specification and
when the catalogue was last read for it. `GET /spec-registry/coverage` already
answers the first; it now also answers the second, as `last_read`: per key, the
newest read (`updated_at`, else `created_at`) among the active products carrying it.
Kept off the registry payload on purpose - that payload is ETag-cached for the n8n
parser, and a time that moves on every re-read would break the cache for nothing.
"""
from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.main import app
from app.models.product_spec import ProductSpecifications
from tests.test_spec_registry_try_preview import (  # noqa: F401
    _BASE,
    _VIEWER,
    _key,
    _product,
    _spec,
    api,
)


def test_coverage_reports_when_each_key_was_last_read(api):
    db, _as = api
    _as(_VIEWER)
    _key(db, "zzt_r5_finish", data_type="enum", unit=None, allowed_values=["black"])

    older = _spec(db, _product(db, "MATT BLACK TAP"), {"zzt_r5_finish": {"value": "black"}})
    newer = _spec(db, _product(db, "BLACK BASIN"), {"zzt_r5_finish": {"value": "black"}})
    # Stamped in SQL with `updated_at` named explicitly, so the column's own
    # `onupdate=now()` does not overwrite the times under test.
    for row, created, updated in (
        (older, datetime(2026, 9, 20, 9, 0, 0), None),
        (newer, datetime(2026, 9, 21, 9, 0, 0), datetime(2026, 9, 26, 8, 15, 0)),
    ):
        db.execute(
            update(ProductSpecifications)
            .where(ProductSpecifications.id == row.id)
            .values(created_at=created, updated_at=updated)
        )
    db.flush()

    response = TestClient(app).get(f"{_BASE}/coverage")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["coverage"]["zzt_r5_finish"] == 2
    assert body["last_read"]["zzt_r5_finish"] == "2026-09-26T08:15:00"


def test_a_key_no_product_carries_has_no_last_read(api):
    db, _as = api
    _as(_VIEWER)
    _key(db, "zzt_r5_unread", data_type="enum", unit=None, allowed_values=["x"])

    body = TestClient(app).get(f"{_BASE}/coverage").json()

    assert "zzt_r5_unread" not in body["coverage"]
    assert "zzt_r5_unread" not in body["last_read"]
