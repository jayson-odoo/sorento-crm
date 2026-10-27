"""``attached_count`` on a catalogue reading, so the Attach step reads as done after a reload.

``counts`` stays the five keys the review tabs and the Attach button read; ``attached_count`` is
beside it, because the existing API tests pin ``counts`` to exactly those five.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app  # noqa: F401  (first app import, as the sibling suite)
from tests.test_catalogue_photo_readings_api import (  # noqa: F401  (fixtures + helpers)
    PREFIX,
    _detail,
    _photo_type,
    _read,
    _seed_catalogue_products,
    api,
)


def test_attached_count_is_zero_until_attach_then_counts_attached_rows(api) -> None:
    _photo_type(api.db)
    _seed_catalogue_products(api.db)
    with TestClient(app) as client:
        reading_id = _read(api, client)
        before = _detail(client, reading_id)
        assert client.post(f"{PREFIX}/{reading_id}/attach").status_code == 200
        after = _detail(client, reading_id)

    assert before["attached_count"] == 0
    assert after["attached_count"] == 2
    assert after["counts"]["to_attach"] == 0
