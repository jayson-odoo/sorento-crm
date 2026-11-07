"""PRICETAG-COMBO-FORMAT crew browser pass fixes (rulings R17 and R18).

Contract: pricetag-combo-format-contract.md, R17 (combo image payload) and R18 (staff
`POST /api/v1/dealer-kit/tag-preview`). Written test-FIRST, tests only.

R17 reuses the combo harness and the fake storage of `tests/test_product_combos.py`; R18 reuses the
staff + portal `env` harness of `tests/test_product_tag_templates.py`, so the staff route and the
portal `/lookups/tag-preview` can be called with the SAME body and compared.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from tests import _ptag_combo_seed as seed
from tests.test_price_tag_lpsp_templates import _foreign_combo  # noqa: F401
from tests.test_product_combos import (  # noqa: F401  (db, storage, _clear_overrides are fixtures)
    COMBO_IMAGE,
    COMBOS,
    EDIT,
    VIEW,
    _caller,
    _clear_overrides,
    _combo,
    _jpg_bytes,
    _product,
    db,
    storage,
)
from tests.test_product_tag_templates import (  # noqa: F401  (env is a fixture)
    DK,
    PORTAL,
    VIEWER_ID,
    _reference,
    _template,
    env,
)
from tests.test_product_tag_templates import _product as _plain_product

DESCRIPTION = "<p><strong>SRTBF11416</strong> (CABINET)</p>"
STAFF_PREVIEW = f"{DK}/tag-preview"
PORTAL_PREVIEW = f"{PORTAL}/lookups/tag-preview"


# --------------------------------------------------------------------------- R17
def test_r17_the_combo_image_payload_carries_the_file_name_and_mime_type(db, monkeypatch, storage):
    """R17: `{attachment_id, url, file_name, mime_type}` (Attachment.original_filename / mime_type), so
    the preview modal can tell a jpg from a pdf by the real extension."""
    host = _product(db, "SRTBF11416")
    combo = _combo(db, host, "3 in 1")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    up = client.post(
        COMBO_IMAGE.format(combo_id=combo.id),
        files={"file": ("cabinet.jpg", _jpg_bytes(), "image/jpeg")},
    )
    assert up.status_code in (200, 201), up.text

    listed = client.get(COMBOS.format(product_id=host.id)).json()["data"]
    image = next(row for row in listed if row["id"] == combo.id)["image"]
    assert image["attachment_id"] and image["url"]
    assert image["file_name"] == "cabinet.jpg"
    assert image["mime_type"] == "image/jpeg"


def test_r17_the_patch_response_carries_them_too(db, monkeypatch, storage):
    host = _product(db, "SRTBF11417")
    combo = _combo(db, host, "2 in 1")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    client.post(
        COMBO_IMAGE.format(combo_id=combo.id),
        files={"file": ("front.png", _jpg_bytes(), "image/png")},
    )
    res = client.patch(f"/api/v1/master-data/product-combos/{combo.id}", json={"name": "2 in 1 renamed"})
    assert res.status_code == 200, res.text
    image = res.json()["image"]
    assert image["file_name"] == "front.png"
    assert image["mime_type"] == "image/png"


# --------------------------------------------------------------------------- R18 seeds
_DOC = {
    "width_mm": 80,
    "height_mm": 50,
    "layers": [
        {
            "id": "desc",
            "type": "text",
            "x_mm": 0, "y_mm": 0, "width_mm": 60, "height_mm": 20,
            "rotation": 0, "z_index": 0,
            "slot_binding": "combo_description",
            "props": {"kind": "text", "text": "x", "fontFamily": "Jost", "fontSize": 10,
                      "fontWeight": 400, "color": "#000", "align": "left", "lineHeight": 1.2,
                      "letterSpacing": 0},
        },
        {
            "id": "badge",
            "type": "price_badge",
            "x_mm": 0, "y_mm": 30, "width_mm": 40, "height_mm": 20,
            "rotation": 0, "z_index": 1,
            "props": {"kind": "price_badge", "variant": "promo", "fill": "#d32f2f",
                      "textColor": "#ffffff", "cornerRadius": 2},
        },
    ],
}


def _world(db):
    """Host + combo (LP 730 / SP 459) + a published template linked to the combo."""
    from app.models.dealer_kit import ComboTagTemplate, TagTemplate

    host = seed.product(db, "ZZR18HOST", list_price="1000.00")
    combo = seed.combo(
        db, host, "ZZT R18 combo",
        description=DESCRIPTION, list_price=Decimal("730.00"), sell_price=Decimal("459.00"),
    )
    template_id = _template(db, "R18")
    template = db.get(TagTemplate, template_id)
    template.published_version.doc = _DOC
    template.doc = _DOC
    db.add(ComboTagTemplate(combo_id=combo.id, template_id=template_id))
    db.flush()
    return host, combo, template_id


def _body(host, combo, template_id, **line):
    return {
        "price_mode": "list",
        "lines": [
            {"key": "k", "line_type": "product", "product_id": host.id, "combo_id": combo.id,
             "tag_template_id": template_id, "price_type": "selling", **line}
        ],
    }


# --------------------------------------------------------------------------- R18 (a)
def test_r18_a_user_without_the_view_permission_is_403(env):
    db, c, as_ = env
    host, combo, template_id = _world(db)
    as_(str(uuid.uuid4()))  # holds no dealer-kit permission
    res = c.post(STAFF_PREVIEW, json=_body(host, combo, template_id))
    assert res.status_code == 403, res.text


def test_r18_a_viewer_may_preview(env):
    db, c, as_ = env
    host, combo, template_id = _world(db)
    as_(VIEWER_ID)
    res = c.post(STAFF_PREVIEW, json=_body(host, combo, template_id))
    assert res.status_code == 200, res.text


# --------------------------------------------------------------------------- R18 (b)
def test_r18_the_staff_preview_returns_the_template_and_the_combo_line(env):
    db, c, _ = env
    host, combo, template_id = _world(db)

    res = c.post(STAFF_PREVIEW, json=_body(host, combo, template_id))
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["templates"]["k"]["id"] == template_id
    (line,) = out["lines"]
    assert line["line_id"] == "k"
    assert line["combo"]["description"] == DESCRIPTION
    assert line["list_price"] == 730
    assert line["sell_price"] == 459
    assert line["show_promo_price"] is True, "an SP line draws the promo badge"


def test_r18_a_list_line_does_not_show_the_promo_price(env):
    db, c, _ = env
    host, combo, template_id = _world(db)
    out = c.post(STAFF_PREVIEW, json=_body(host, combo, template_id, price_type="list")).json()
    assert out["lines"][0]["show_promo_price"] is False
    assert out["lines"][0]["list_price"] == 730


def test_r18_the_staff_route_answers_exactly_what_the_portal_preview_answers(env):
    """One pipeline: the same body through `/lookups/tag-preview` and the staff route."""
    db, c, _ = env
    host, combo, template_id = _world(db)
    body = _body(host, combo, template_id)

    staff = c.post(STAFF_PREVIEW, json=body)
    portal = c.post(PORTAL_PREVIEW, json=body)
    assert staff.status_code == 200, staff.text
    assert portal.status_code == 200, portal.text
    s, p = staff.json(), portal.json()
    assert s["templates"]["k"]["id"] == p["templates"]["k"]["id"] == template_id
    for field in ("line_id", "combo", "list_price", "sell_price", "show_promo_price", "code"):
        assert s["lines"][0][field] == p["lines"][0][field], field


# --------------------------------------------------------------------------- R18 (c)
def test_r18_a_combo_of_another_company_leaks_nothing(env):
    """The host of the foreign combo belongs to company 2; the caller is scoped to Sorento."""
    db, c, _ = env
    foreign_host, foreign_combo = _foreign_combo(db)
    own_host, _own_combo, template_id = _world(db)

    # (1) the foreign host itself
    res = c.post(
        STAFF_PREVIEW,
        json={"lines": [{"key": "k", "line_type": "product", "product_id": foreign_host,
                         "combo_id": foreign_combo.id, "price_type": "selling"}]},
    )
    assert res.status_code in (200, 404), res.text
    if res.status_code == 200:
        assert res.json()["lines"] == [] and res.json()["templates"] == {}

    # (2) an own host naming the foreign combo: the combo must not appear
    res = c.post(
        STAFF_PREVIEW,
        json={"lines": [{"key": "k", "line_type": "product", "product_id": own_host.id,
                         "combo_id": foreign_combo.id, "tag_template_id": template_id,
                         "price_type": "selling"}]},
    )
    assert res.status_code in (200, 404), res.text
    if res.status_code == 200:
        for line in res.json()["lines"]:
            assert line["combo"] is None, "the other company's combo must not be resolved"
            assert foreign_combo.name not in str(line)


# --------------------------------------------------------------------------- R18 security round
def test_r18_a_part_with_more_than_50_candidates_is_422(env):
    """Security review: one part listing every product id would force a full product resolution
    per id in one synchronous request. A choice group's options are a handful; 50 is the ceiling."""
    db, c, _ = env
    host, combo, template_id = _world(db)
    body = _body(host, combo, template_id)
    body["lines"][0]["parts"] = [
        {"product_id": None, "role": "Tap", "candidates": [str(uuid.uuid4()) for _ in range(51)]}
    ]
    res = c.post(STAFF_PREVIEW, json=body)
    assert res.status_code == 422, res.text

    body["lines"][0]["parts"][0]["candidates"] = [str(uuid.uuid4()) for _ in range(50)]
    assert c.post(STAFF_PREVIEW, json=body).status_code == 200


def test_r18_the_staff_route_refuses_a_request_id(env):
    """The staff route previews unsaved lines only; a request_id would need the per-request
    permission check the portal route does, so it is refused rather than silently ignored."""
    db, c, _ = env
    host, combo, template_id = _world(db)
    body = _body(host, combo, template_id)
    body["request_id"] = str(uuid.uuid4())
    res = c.post(STAFF_PREVIEW, json=body)
    assert res.status_code == 422, res.text
    assert "lines" not in res.json() or not res.json().get("lines")
