"""FILTER-MULTISELECT PR4: a class label containing a comma ("Sink, Undermount") filters exactly on the spec
verification worklist, alone and with another label, sent as a repeated param. Red first. Postgres only; every
row seeded here.
"""
from __future__ import annotations

from app.models.product_spec import ProductSpecifications
from tests._multi_filter_client import get
from tests._pg_fixture import unique_code
from tests.test_product_spec_verification_routes import (  # noqa: F401  (fixtures)
    ENDPOINT,
    VIEW,
    _product,
    api,
    db,
)

COMMA_CLASS = "Sink, Undermount"


def _seed(db):
    out = {}
    for key, cls in (("comma", COMMA_CLASS), ("tap", "Tap"), ("basin", "Basin")):
        code = unique_code(f"VR-CC-{key}")
        p = _product(db, code)
        db.add(ProductSpecifications(product_id=p.id, values={"class": {"value": cls}}, provenance={}, status="derived"))
        out[key] = code
    db.commit()
    return out


def _codes(client, *pairs):
    resp = get(client, f"{ENDPOINT}/verification/worklist", [("limit", 100), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["product_code"] for r in resp.json()["data"]}


def test_a_class_label_with_a_comma_filters_exactly_alone(api, db):
    client, allow = api
    allow.add(VIEW)
    c = _seed(db)
    assert _codes(client, ("class_label", COMMA_CLASS)) & set(c.values()) == {c["comma"]}


def test_a_class_label_with_a_comma_and_another_label_return_the_union(api, db):
    client, allow = api
    allow.add(VIEW)
    c = _seed(db)
    got = _codes(client, ("class_label", COMMA_CLASS), ("class_label", "Tap")) & set(c.values())
    assert got == {c["comma"], c["tap"]}


def test_plain_class_labels_still_union_comma_joined_and_repeated(api, db):
    client, allow = api
    allow.add(VIEW)
    c = _seed(db)
    want = {c["tap"], c["basin"]}
    assert _codes(client, ("class_label", "Tap,Basin")) & set(c.values()) == want
    assert _codes(client, ("class_label", "Tap"), ("class_label", "Basin")) & set(c.values()) == want
