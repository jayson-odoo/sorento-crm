"""FILTER-MULTISELECT PR4: a class label that itself contains a comma ("Sink, Undermount") filters exactly on the
spec registry's "Seen in products" read, picked alone and with another label, sent as a repeated param.
Red first. Postgres only; every row seeded here.
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

COMMA_CLASS = "Sink, Undermount"


@pytest.fixture
def seen(api):
    db, as_user = api
    as_user(_MERCHANDISER)
    _key(db, "zzt_finish")
    prov = {"zzt_finish": {"source": "derived"}}
    products = {}
    for key, cls in (("comma", COMMA_CLASS), ("tap", "Tap"), ("basin", "Basin")):
        p = _product(db)
        _spec(db, p, {"zzt_finish": {"value": "Chrome"}, "class": {"value": cls}}, prov)
        products[key] = p
    db.commit()
    return TestClient(app), products


def _codes(client, *pairs):
    resp = get(client, f"{_BASE}/zzt_finish/products", list(pairs))
    assert resp.status_code == 200, resp.text
    return {r["product_code"] for r in resp.json()["products"]}


def test_a_class_label_with_a_comma_filters_exactly_alone(seen):
    client, p = seen
    assert _codes(client, ("class_label", COMMA_CLASS)) == {p["comma"].product_code}


def test_a_class_label_with_a_comma_and_another_label_return_the_union(seen):
    client, p = seen
    got = _codes(client, ("class_label", COMMA_CLASS), ("class_label", "Tap"))
    assert got == {p["comma"].product_code, p["tap"].product_code}


def test_plain_class_labels_union_as_repeated_params(seen):
    client, p = seen
    want = {p["tap"].product_code, p["basin"].product_code}
    # Text values ride repeated params only (plan section 1): a comma inside one is part of the value.
    assert _codes(client, ("class_label", "Tap"), ("class_label", "Basin")) == want
