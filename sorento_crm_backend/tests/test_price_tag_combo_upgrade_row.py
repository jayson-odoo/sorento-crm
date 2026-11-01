"""PRICETAG-COMBO AC-3.5: upgrades reach the portal line as an open row, never a fixed part.

The lookup must say which parts are upgrades, and a missing upgrade is never named in a
`Missing:` warning.
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests._pg_fixture import blank_session
from tests.test_portal_price_tag_routes import client  # noqa: F401  (portal harness fixture)

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)


def test_the_combos_lookup_marks_an_upgrade_part(client):  # noqa: F811
    c, db, _contact = client
    host = seed.product(db, "ZZUHOST")
    mirror = seed.product(db, "ZZUMIR")
    stone = seed.product(db, "ZZUSTONE")
    seed.combo(
        db,
        host,
        "ZZT upgrade pack",
        parts=[{"product": mirror}, {"product": stone, "is_upgrade": True}],
    )
    db.commit()

    response = c.get(f"/api/v1/public/portal/lookups/product-combos/{host.id}")
    assert response.status_code == 200, response.text
    (combo,) = response.json()["combos"]
    flags = {part["code"]: part["is_upgrade"] for part in combo["parts"]}
    assert flags == {mirror.product_code: False, stone.product_code: True}


def test_a_missing_upgrade_is_never_named_in_a_missing_warning():
    from app.models.product import ProductCategory

    with blank_session() as db:
        host = seed.product(db, "ZZUGUARD")
        category = db.query(ProductCategory).filter(ProductCategory.id == host.category_id).one()
        category.class_label = "Bathroom Furniture"
        mirror = seed.product(db, "ZZUMIR")
        stone = seed.product(db, "ZZUSTONE")
        cover = r9.seed_product_photo(db, host)
        cb = seed.combo(
            db,
            host,
            "ZZT upgrade pack",
            parts=[{"product": mirror}, {"product": stone, "is_upgrade": True}],
            description="Cabinet and mirror",
            image_attachment_id=cover.id,
        )
        request = seed.submit_one(db, host, cb, [{"product_id": mirror.id}])
        db.flush()
        assert request.lines[0].package_warning is None, request.lines[0].package_warning
