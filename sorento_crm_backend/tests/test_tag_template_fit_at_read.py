"""PRICETAG-COMBO-RENDER M1b: a template that does not fit a combo never draws it.

Written test-FIRST. A leftover `combo_tag_template` link to a template that prints fewer fixed
parts than the combo has used to be drawn anyway (preview, line save). Every read now drops it
(`line_links`), and the combo link save refuses it with the reason.
"""
from __future__ import annotations

from tests import _ptag_shapes_seed as shapes
from tests.test_price_tag_lpsp_templates import PTAG, _combo_link, _draft
from tests.test_product_tag_templates import DK, PORTAL, env  # noqa: F401  (env is a fixture)
from tests.test_template_needs_in_lists import _doc, _published

ONE_FIXED = ({"kind": "fixed", "index": 0},)
TWO_FIXED = ({"kind": "fixed", "index": 0}, {"kind": "fixed", "index": 1})


def _world(db):
    s = shapes.s4(db)  # a combo with two fixed parts
    short = _published(db, "ZZT one fixed", _doc(*ONE_FIXED))
    fits = _published(db, "ZZT two fixed", _doc(*TWO_FIXED))
    return s, short, fits


def _preview(c, s):
    out = c.post(
        f"{PORTAL}/lookups/tag-preview",
        json={"lines": [{"key": "k", "line_type": "product", "product_id": s["host"].id,
                         "combo_id": s["combo"].id}]},
    )
    assert out.status_code == 200, out.text
    return out.json()


def test_a_leftover_non_fitting_link_draws_nothing_in_the_preview(env):  # noqa: F811
    db, c, _ = env
    s, short, _fits = _world(db)
    _combo_link(db, s["combo"].id, short)
    assert "k" not in _preview(c, s)["templates"]


def test_a_fitting_link_still_draws(env):  # noqa: F811
    db, c, _ = env
    s, short, fits = _world(db)
    _combo_link(db, s["combo"].id, short, fits)
    assert _preview(c, s)["templates"]["k"]["id"] == fits


def test_the_saved_request_preview_and_the_line_lookup_drop_it_too(env):  # noqa: F811
    db, c, _ = env
    s, short, fits = _world(db)
    _combo_link(db, s["combo"].id, short)
    body = _draft(c, [{"line_type": "product", "product_id": s["host"].id, "combo_id": s["combo"].id}])
    assert body["lines"][0]["tag_template_id"] is None
    out = c.post(f"{PORTAL}/lookups/tag-preview", json={"request_id": body["id"]}).json()
    assert out["templates"] == {}
    res = c.get(f"{PORTAL}/lookups/product-tag-templates/{s['host'].id}", params={"combo_id": s["combo"].id})
    assert res.json() == []
    _combo_link(db, s["combo"].id, fits)
    res = c.get(f"{PORTAL}/lookups/product-tag-templates/{s['host'].id}", params={"combo_id": s["combo"].id})
    assert [row["id"] for row in res.json()] == [fits]


def test_the_combo_link_save_refuses_a_non_fitting_template(env):  # noqa: F811
    db, c, _ = env
    s, short, fits = _world(db)
    res = c.put(f"{DK}/combos/{s['combo'].id}/tag-templates", json={"template_ids": [short]})
    assert res.status_code == 422, res.text
    assert "Prints 1 of this combo's 2 fixed parts" in res.text
    ok = c.put(f"{DK}/combos/{s['combo'].id}/tag-templates", json={"template_ids": [fits]})
    assert ok.status_code == 200, ok.text
