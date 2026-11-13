"""AFTER-SALES-P1 round 4 (R4-2): technician list filters, server side, each alone, combined, either-of-two."""
from __future__ import annotations

import pytest

from ._pg_fixture import unique_code
from ._service_jobs_p1_support import TECHS, api, env, make_tech  # noqa: F401


@pytest.fixture
def world(env):
    tag = unique_code("TF", alpha=True)
    rows = {
        "emp_on": make_tech(env, f"{tag} a", active=True, kind="employee"),
        "emp_off": make_tech(env, f"{tag} b", active=False, kind="employee"),
        "con_on": make_tech(env, f"{tag} c", active=True, kind="contractor"),
        "con_off": make_tech(env, f"{tag} d", active=False, kind="contractor"),
    }
    return tag, {k: v.id for k, v in rows.items()}


def _ids(env, tag, params):
    with api(env) as client:
        r = client.get(TECHS, params=[("query", tag), ("limit", 50), *params])
    assert r.status_code == 200, r.text
    return {x["id"] for x in r.json()["data"]}


def test_type_filter_alone(env, world):
    tag, w = world
    assert _ids(env, tag, [("employment_type", "contractor")]) == {w["con_on"], w["con_off"]}


def test_status_filter_alone(env, world):
    tag, w = world
    assert _ids(env, tag, [("is_active", "false")]) == {w["emp_off"], w["con_off"]}
    assert _ids(env, tag, [("is_active", "true")]) == {w["emp_on"], w["con_on"]}


def test_filters_combine(env, world):
    tag, w = world
    assert _ids(env, tag, [("employment_type", "employee"), ("is_active", "false")]) == {w["emp_off"]}


def test_both_values_of_one_filter_means_either(env, world):
    tag, w = world
    everyone = set(w.values())
    assert _ids(env, tag, [("employment_type", "employee"), ("employment_type", "contractor")]) == everyone
    assert _ids(env, tag, [("employment_type", "employee,contractor")]) == everyone
    assert _ids(env, tag, [("is_active", "true"), ("is_active", "false")]) == everyone
    assert _ids(env, tag, [("is_active", "true,false")]) == everyone
