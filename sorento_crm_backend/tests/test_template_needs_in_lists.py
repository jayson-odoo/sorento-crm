"""PRICETAG-COMBO-RENDER K4 / AC-B1: every template list the app reads carries `needs`.

Written test-FIRST. `needs` is on none of: the product's links, the combo's links, the portal
line lookup, the tag template list. Red as a missing key. `needs` comes from the PUBLISHED
document, never the draft sitting beside it.

Decision: for a template that was never published the value is not asserted (it has no
published document); only published templates are covered.
"""
from __future__ import annotations

import pytest

from tests import _ptag_shapes_seed as shapes
from tests.test_product_tag_templates import (  # noqa: F401  (env is a fixture)
    DK,
    PORTAL,
    _link,
    _product,
    _reference,
    _template,
    env,
)

from tests.test_price_tag_lpsp_templates import _combo_link

NEEDS_S1 = {"fixed": 0, "groups": [3], "upgrades": 1}


def _layer(layer_id, slot):
    return {
        "id": layer_id,
        "type": "text",
        "x_mm": 0,
        "y_mm": 0,
        "width_mm": 10,
        "height_mm": 10,
        "z_index": 1,
        "props": {"kind": "text", "subjectSlot": slot},
    }


def _doc(*slots):
    return {
        "layers": [_layer(f"l{i}", slot) for i, slot in enumerate(slots)],
        "width_mm": 105,
        "height_mm": 148,
    }


S1_SLOTS = (
    {"kind": "main"},
    {"kind": "pick", "group": 0, "index": 2},
    {"kind": "upgrade", "index": 0},
)


def _published(db, name, doc, draft=None):
    """A published template whose published document is `doc`; the draft may differ."""
    from app.models.dealer_kit import TagTemplate

    template_id = _template(db, name)
    template = db.get(TagTemplate, template_id)
    template.published_version.doc = doc
    template.doc = draft if draft is not None else doc
    db.flush()
    return template_id


def _by_id(items):
    return {row["id"]: row for row in items}


def test_the_products_links_carry_needs(env):  # noqa: F811
    db, c, _ = env
    product = _product(db, _reference(db))
    tid = _published(db, "A", _doc(*S1_SLOTS))
    _link(db, product, tid)
    res = c.get(f"{DK}/products/{product}/tag-templates")
    assert res.status_code == 200, res.text
    assert _by_id(res.json())[tid]["needs"] == NEEDS_S1


def test_needs_follow_the_published_doc_not_the_draft(env):  # noqa: F811
    db, c, _ = env
    product = _product(db, _reference(db))
    draft = _doc({"kind": "fixed", "index": 4})
    tid = _published(db, "B", _doc({"kind": "main"}), draft=draft)
    _link(db, product, tid)
    row = _by_id(c.get(f"{DK}/products/{product}/tag-templates").json())[tid]
    assert row["needs"] == {"fixed": 0, "groups": [], "upgrades": 0}


def test_put_answers_needs_too(env):  # noqa: F811
    db, c, _ = env
    product = _product(db, _reference(db))
    tid = _published(db, "C", _doc({"kind": "fixed", "index": 1}))
    res = c.put(f"{DK}/products/{product}/tag-templates", json={"template_ids": [tid]})
    assert res.status_code == 200, res.text
    assert res.json()[0]["needs"] == {"fixed": 2, "groups": [], "upgrades": 0}


def test_the_combos_links_carry_needs(env):  # noqa: F811
    db, c, _ = env
    s = shapes.s3(db)
    tid = _published(db, "D", _doc({"kind": "pick", "group": 0, "index": 1}))
    _combo_link(db, s["combo"].id, tid)
    res = c.get(f"{DK}/combos/{s['combo'].id}/tag-templates")
    assert res.status_code == 200, res.text
    assert _by_id(res.json())[tid]["needs"] == {"fixed": 0, "groups": [2], "upgrades": 0}


def test_the_portal_line_lookup_carries_needs(env):  # noqa: F811
    db, c, _ = env
    product = _product(db, _reference(db))
    tid = _published(db, "E", _doc(*S1_SLOTS))
    _link(db, product, tid)
    res = c.get(f"{PORTAL}/lookups/product-tag-templates/{product}")
    assert res.status_code == 200, res.text
    assert _by_id(res.json())[tid]["needs"] == NEEDS_S1


def test_the_portal_line_lookup_with_a_combo_carries_needs(env):  # noqa: F811
    db, c, _ = env
    s = shapes.s4(db)
    tid = _published(db, "F", _doc({"kind": "fixed", "index": 1}))
    _combo_link(db, s["combo"].id, tid)
    res = c.get(
        f"{PORTAL}/lookups/product-tag-templates/{s['host'].id}",
        params={"combo_id": s["combo"].id},
    )
    assert res.status_code == 200, res.text
    assert _by_id(res.json())[tid]["needs"] == {"fixed": 2, "groups": [], "upgrades": 0}


@pytest.mark.parametrize("published_only", [False, True])
def test_the_tag_template_list_carries_needs(env, published_only):  # noqa: F811
    db, c, _ = env
    tid = _published(db, "G", _doc(*S1_SLOTS), draft=_doc({"kind": "main"}))
    res = c.get(f"{DK}/tag-templates", params={"published": published_only})
    assert res.status_code == 200, res.text
    row = _by_id(res.json())[tid]
    assert "needs" in row, "response_model dropped `needs`"
    assert row["needs"] == NEEDS_S1
