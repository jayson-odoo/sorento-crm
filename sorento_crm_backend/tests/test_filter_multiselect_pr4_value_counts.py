"""FILTER-MULTISELECT PR4: on the spec registry's "Seen in products" read, the Value counts (`by_value`) follow the
search box `q` (as they did before this lane) while ignoring the Value filter itself. Postgres only; seeded here.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests._multi_filter_client import get
from tests.test_spec_registry_pr2_routes import (  # noqa: F401  (`api` is a pytest fixture)
    _BASE,
    _MERCHANDISER,
    _key,
    _product,
    _spec,
    api,
)


@pytest.fixture
def seen(api):
    db, as_user = api
    as_user(_MERCHANDISER)
    _key(db, "zzt_finish")
    prov = {"zzt_finish": {"source": "derived"}}
    a, b = _product(db), _product(db)
    a.description = "ZZTQNEEDLE alpha product"
    b.description = "plain beta product"
    _spec(db, a, {"zzt_finish": {"value": "Alpha"}}, prov)
    _spec(db, b, {"zzt_finish": {"value": "Beta"}}, prov)
    db.commit()
    return TestClient(app)


def _by_value(client, *pairs):
    resp = get(client, f"{_BASE}/zzt_finish/products", list(pairs))
    assert resp.status_code == 200, resp.text
    return {row["value"] for row in resp.json()["by_value"]}


def test_value_counts_follow_the_search_box(seen):
    assert _by_value(seen, ("q", "ZZTQNEEDLE")) == {"Alpha"}


def test_value_counts_ignore_the_value_filter_itself(seen):
    assert _by_value(seen, ("value", "Alpha")) == {"Alpha", "Beta"}


def test_search_and_value_filter_together_count_by_search_only(seen):
    # q keeps only Alpha's product; picking Beta does not widen or empty the options.
    assert _by_value(seen, ("q", "ZZTQNEEDLE"), ("value", "Beta")) == {"Alpha"}


def test_no_filters_lists_every_value(seen):
    assert _by_value(seen) == {"Alpha", "Beta"}
