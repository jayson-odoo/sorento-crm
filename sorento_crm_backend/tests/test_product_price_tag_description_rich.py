"""PRICETAG-COMBO-FORMAT S2: `products.price_tag_description` is sanitised on write.

UAC: documentation/plans/dealer-kit/pricetag-combo-format-acceptance-criteria.md, AC-9, AC-10.

Written test-FIRST (PRINCIPLES.md Phase 2). Harness reused from
`tests/test_product_price_tag_description.py` (master-data PUT through the real routes).
"""
from __future__ import annotations

from tests.test_product_price_tag_description import (  # noqa: F401  (fixtures)
    STEM,
    _scope_listeners,
    api,
    db,
    world,
)


def _put(api, pid, text):
    return api.put(f"/api/v1/master-data/products/{pid}", json={"price_tag_description": text})


def test_a_script_in_the_price_tag_description_is_not_stored(api, world, db):
    """AC-9."""
    pid = world["product"](f"{STEM}-RICH1")
    db.commit()

    res = _put(api, pid, "<p>Solid brass<script>alert(1)</script></p>")
    assert res.status_code == 200, res.text
    assert res.json()["price_tag_description"] == "<p>Solid brass</p>"
    detail = api.get(f"/api/v1/master-data/products/{pid}")
    assert detail.json()["price_tag_description"] == "<p>Solid brass</p>"


def test_a_merge_field_inside_bold_survives_sanitising(api, world, db):
    """AC-9: `{{spec.width}}` is plain text to the sanitiser and must reach the tag intact."""
    pid = world["product"](f"{STEM}-RICH2")
    db.commit()

    html = "<p><strong>{{spec.width}}</strong> wide</p>"
    res = _put(api, pid, html)
    assert res.status_code == 200, res.text
    assert res.json()["price_tag_description"] == html


def test_empty_markup_clears_the_description(api, world, db):
    """AC-10."""
    pid = world["product"](f"{STEM}-RICH3", price_tag_description="<p>old</p>")
    db.commit()

    res = _put(api, pid, "<p></p>")
    assert res.status_code == 200, res.text
    assert res.json()["price_tag_description"] is None
