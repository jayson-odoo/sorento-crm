"""PRICETAG-COMBO-RENDER K5 / AC-C6: the portal combos lookup says which part is discontinued.

Written test-FIRST. `is_discontinued` is not on a lookup part yet; red as a missing key.
A part flag comes from `products.is_discontinued` of the PART product, not of the host.
"""
from __future__ import annotations

import os

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from tests import _ptag_shapes_seed as shapes
from tests.test_portal_price_tag_routes import client  # noqa: F401  (portal harness fixture)

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)


def _lookup(c, host):
    response = c.get(f"/api/v1/public/portal/lookups/product-combos/{host.id}")
    assert response.status_code == 200, response.text
    return response.json()["combos"]


def test_every_part_carries_the_flag_and_it_defaults_false(client):  # noqa: F811
    c, db, _contact = client
    s = shapes.s1(db)
    db.commit()
    (combo,) = _lookup(c, s["host"])
    assert combo["parts"], "the combo has parts"
    for part in combo["parts"]:
        assert part["is_discontinued"] is False


def test_a_discontinued_option_is_flagged_and_its_siblings_are_not(client):  # noqa: F811
    c, db, _contact = client
    s = shapes.s1(db)
    s["options"][2].is_discontinued = True  # SRTKT1871SS
    db.commit()
    (combo,) = _lookup(c, s["host"])
    flags = {part["code"]: part["is_discontinued"] for part in combo["parts"]}
    assert flags["SRTKT1871SS"] is True
    assert flags["SRTKT1862SS"] is False
    assert flags["SRTKT71SS"] is False


def test_a_discontinued_fixed_part_and_upgrade_are_flagged(client):  # noqa: F811
    c, db, _contact = client
    s = shapes.s4(db)
    s["fixed"][0].is_discontinued = True
    db.commit()
    (combo,) = _lookup(c, s["host"])
    flags = {part["code"]: part["is_discontinued"] for part in combo["parts"]}
    assert flags == {"SRTMCB8083-BL": True, "SRTWT6203-GM": False}


def test_a_discontinued_host_does_not_flag_its_parts(client):  # noqa: F811
    c, db, _contact = client
    s = shapes.s3(db)
    s["host"].is_discontinued = True
    db.commit()
    (combo,) = _lookup(c, s["host"])
    assert [part["is_discontinued"] for part in combo["parts"]] == [False, False]
