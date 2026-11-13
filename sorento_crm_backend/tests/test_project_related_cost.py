"""PROJECT-RELATED-RECORDS fix round 2 (security B2): an NPA's Value on the Related tab is its cost
price, so it shows only to a reader with `products.cost.view`, on the tab and in the assistant's
rows. A request's value is not cost and always shows. Postgres only; fake values.
"""
from __future__ import annotations

import pytest

from tests._own_scope_support import acting, user

from .test_project_related_records import FULL, _get, scene  # noqa: F401  (fixture)

COST = "products.cost.view"


# ------------------------------------------------------------------ B2: NPA cost on the Related tab


def _npa_value(body) -> object:
    row = next(r for r in body["data"] if r["kind"] == "new_product_application")
    return row["value"]


def test_b2_npa_value_is_hidden_without_the_cost_permission(scene):  # noqa: F811
    db, p = scene["db"], scene["p"]
    with acting(db, user(db, "No cost"), FULL - {COST}) as client:
        body = _get(client, p.id)
    assert _npa_value(body) is None
    pr = next(r for r in body["data"] if r["kind"] == "purchase_request")
    assert pr["value"] is not None  # a request's value is not cost


def test_b2_npa_value_shows_with_the_cost_permission(scene):  # noqa: F811
    db, p = scene["db"], scene["p"]
    with acting(db, user(db, "Cost"), FULL | {COST}) as client:
        body = _get(client, p.id)
    assert str(_npa_value(body)) in ("300.00", "300.0", "300")


@pytest.mark.parametrize("with_cost", [False, True])
def test_b2_the_assistant_row_follows_the_same_rule(scene, with_cost):  # noqa: F811
    from app.services.assistant_registry.query import run_query

    db, p = scene["db"], scene["p"]
    viewer = user(db, "Assistant reader")
    perms = (FULL | {COST}) if with_cost else (FULL - {COST})
    with acting(db, viewer, perms):
        out = run_query(db, viewer, {
            "entity": "project_related_record",
            "fields": ["type", "value"],
            "filters": [{"field": "project_code", "op": "eq", "value": p.project_code}],
        })
    npa = [r for r in out["rows"] if r.get("type") == "New product application"]
    assert npa, out
    if with_cost:
        assert npa[0].get("value") not in (None, "", "-"), npa
    else:
        assert npa[0].get("value") in (None, "", "-"), npa
