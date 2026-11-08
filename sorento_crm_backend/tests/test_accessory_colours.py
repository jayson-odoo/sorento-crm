"""PRICETAG-ACCESSORY-DESIGNER S7: an accessory's colours are an ordered list of their own.

Plan: "S7 Pictures and colours are independent". Written test-FIRST. Invented: `AccessoryOut.colours:
[{id, name, hex}]`, `PUT /accessories/{id}/colours {"colours": [{name?, hex}]}` (replaces the ordered list; 422 bad
hex, more than 12, duplicate hex ignoring case, name over 40; 404 other company; 403 view-only), the picture PATCH
ignores colour fields, and the tag payload's `colours` = that list (`{name, hex}`) even with ONE picture, while
`images[]` keep `colour_name` / `colour_hex` keys as null.
"""
from __future__ import annotations

import uuid

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.company_scope import register_company_scope_listeners

from tests import _ptag_combo_seed as seed
from tests._pg_fixture import blank_session
from tests.test_accessories import (  # noqa: F401
    ACCESSORY,
    COMBO_LIST,
    EDIT,
    MOCHA,
    PRODUCT_LIST,
    VIEW,
    _accessory,
    _caller,
    _clear_overrides,
    _jpg_bytes,
    _mocha,
    _name,
    signed,
    storage,
)

COLOURS = "/api/v1/master-data/accessories/{accessory_id}/colours"
IMAGES = "/api/v1/master-data/accessories/{accessory_id}/images"
IMAGE = "/api/v1/master-data/accessories/{accessory_id}/images/{image_id}"
TAG_DATA = "/api/v1/dealer-kit/products/{id}/tag-data"

BLACK = {"name": "Black", "hex": "#1f2937"}
GREY = {"name": "Grey", "hex": "#9ca3af"}


class _Everything(set):
    def __contains__(self, item):
        return True


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


def _put(client, accessory_id, colours):
    return client.put(COLOURS.format(accessory_id=accessory_id), json={"colours": colours})


def _out(client, accessory_id):
    response = client.get(ACCESSORY.format(accessory_id=accessory_id))
    assert response.status_code == 200, response.text
    return response.json()


def _picture(client, accessory_id, n=0):
    response = client.post(
        IMAGES.format(accessory_id=accessory_id),
        files={"file": (f"p{n}.jpg", _jpg_bytes() + bytes([n]), "image/jpeg")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _pairs(rows):
    return [(row["name"], row["hex"].lower()) for row in rows]


# --------------------------------------------------------------------------- the list


def test_a_new_accessory_has_no_colours(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    assert _out(client, _accessory(db, _name("FRESH")).id)["colours"] == []


def test_put_sets_the_ordered_list_and_accessory_out_carries_it(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("COLOURED"))
    response = _put(client, row.id, [BLACK, GREY])
    assert response.status_code == 200, response.text
    colours = _out(client, row.id)["colours"]
    assert _pairs(colours) == [("Black", "#1f2937"), ("Grey", "#9ca3af")]
    assert all(c["id"] for c in colours)
    assert set(colours[0]) >= {"id", "name", "hex"}


def test_put_replaces_the_whole_list_and_can_empty_it(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("REPLACED"))
    _put(client, row.id, [BLACK, GREY])
    assert _put(client, row.id, [GREY]).status_code == 200
    assert _pairs(_out(client, row.id)["colours"]) == [("Grey", "#9ca3af")]
    reorder = _put(client, row.id, [GREY, BLACK])
    assert reorder.status_code == 200
    assert _pairs(_out(client, row.id)["colours"]) == [("Grey", "#9ca3af"), ("Black", "#1f2937")]
    assert _put(client, row.id, []).status_code == 200
    assert _out(client, row.id)["colours"] == []


def test_a_name_is_optional_and_blank_is_none(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("UNNAMED"))
    assert _put(client, row.id, [{"hex": "#c0c0c0"}, {"name": "  ", "hex": "#d4af37"}]).status_code == 200
    assert _pairs(_out(client, row.id)["colours"]) == [(None, "#c0c0c0"), (None, "#d4af37")]


@pytest.mark.parametrize("bad", ["red", "#12345", "1f2937", "#gggggg", "#1f29371", ""])
def test_a_bad_hex_is_422_and_changes_nothing(db, monkeypatch, bad):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("BADHEX"))
    _put(client, row.id, [BLACK])
    assert _put(client, row.id, [GREY, {"name": "Bad", "hex": bad}]).status_code == 422
    assert _pairs(_out(client, row.id)["colours"]) == [("Black", "#1f2937")]


def test_more_than_12_colours_is_422_and_12_is_fine(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("MANY"))
    twelve = [{"name": f"C{n}", "hex": f"#0000{n:02x}"} for n in range(12)]
    assert _put(client, row.id, twelve).status_code == 200
    assert len(_out(client, row.id)["colours"]) == 12
    thirteen = twelve + [{"name": "C12", "hex": "#00000c"}]
    assert _put(client, row.id, thirteen).status_code == 422
    assert len(_out(client, row.id)["colours"]) == 12


def test_a_duplicate_hex_ignoring_case_is_422(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("DUPLICATE"))
    response = _put(client, row.id, [BLACK, {"name": "Again", "hex": "#1F2937"}])
    assert response.status_code == 422, response.text
    assert _out(client, row.id)["colours"] == []


def test_a_name_over_40_characters_is_422(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("LONGNAME"))
    assert _put(client, row.id, [{"name": "x" * 41, "hex": "#1f2937"}]).status_code == 422
    assert _put(client, row.id, [{"name": "x" * 40, "hex": "#1f2937"}]).status_code == 200


def test_another_companys_accessory_is_404(db, monkeypatch):
    _mocha(db)
    theirs = _accessory(db, _name("THEIRS"), company_id=MOCHA)
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    mine = _accessory(db, _name("MINE"))
    assert _put(client, mine.id, [BLACK]).status_code == 200, "the route exists for my own accessory"
    assert _put(client, theirs.id, [BLACK]).status_code == 404
    assert _put(client, str(uuid.uuid4()), [BLACK]).status_code == 404


def test_view_only_cannot_put_colours(db, monkeypatch):
    writer = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("VIEWONLY"))
    assert _put(writer, row.id, [BLACK]).status_code == 200
    viewer = _caller(db, {VIEW}, monkeypatch)
    assert _put(viewer, row.id, [GREY]).status_code == 403
    assert _pairs(_out(viewer, row.id)["colours"]) == [("Black", "#1f2937")]


def test_deleting_the_accessory_removes_its_colours(db, monkeypatch):
    from app.models.accessory import AccessoryColour

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("GONE"))
    _put(client, row.id, [BLACK, GREY])
    assert client.delete(ACCESSORY.format(accessory_id=row.id)).status_code == 204
    db.expire_all()
    assert db.query(AccessoryColour).filter(AccessoryColour.accessory_id == row.id).count() == 0


# --------------------------------------------------------------------------- pictures no longer carry colour


def test_the_picture_patch_ignores_colour_fields(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("PATCHED"))
    picture = _picture(client, row.id, 1)
    response = client.patch(
        IMAGE.format(accessory_id=row.id, image_id=picture["id"]),
        json={"colour_name": "Gold", "colour_hex": "#d4af37"},
    )
    assert response.status_code in (200, 422), response.text
    out = _out(client, row.id)
    assert out["images"][0].get("colour_hex") is None and out["images"][0].get("colour_name") is None
    assert out["colours"] == []


def test_a_picture_comes_back_without_a_colour(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("PLAINPIC"))
    _picture(client, row.id, 1)
    (image,) = _out(client, row.id)["images"]
    assert image.get("colour_name") is None and image.get("colour_hex") is None


# --------------------------------------------------------------------------- tag payload


def _list_product(client, product, *entries):
    response = client.put(PRODUCT_LIST.format(product_id=product.id), json={"items": list(entries)})
    assert response.status_code == 200, response.text


def test_one_picture_and_two_colours_give_two_colours_in_the_payload(db, monkeypatch, storage, signed):
    from app.services.accessory_service import product_tag_accessories

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZCOL")
    item = _accessory(db, _name("COLANDER"))
    _picture(client, item.id, 1)
    _put(client, item.id, [BLACK, GREY])
    _list_product(client, host, {"accessory_id": item.id})
    (entry,) = product_tag_accessories(db, host.id)
    assert len(entry["images"]) == 1
    assert entry["colours"] == [BLACK, GREY]
    assert entry["images"][0]["colour_name"] is None and entry["images"][0]["colour_hex"] is None
    assert {"attachment_id", "url", "colour_name", "colour_hex"} <= set(entry["images"][0])


def test_colours_travel_with_no_picture_at_all(db, monkeypatch, signed):
    from app.services.accessory_service import product_tag_accessories

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZCOL")
    item = _accessory(db, _name("NOPIC"))
    _put(client, item.id, [GREY])
    _list_product(client, host, {"accessory_id": item.id})
    (entry,) = product_tag_accessories(db, host.id)
    assert entry["images"] == [] and entry["colours"] == [GREY]


def test_colours_are_no_longer_derived_from_pictures(db, monkeypatch, storage, signed):
    from app.models.accessory import AccessoryImage
    from app.services.accessory_service import product_tag_accessories

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZCOL")
    item = _accessory(db, _name("OLDCOUPLING"))
    _picture(client, item.id, 1)
    db.query(AccessoryImage).filter(AccessoryImage.accessory_id == item.id).update(
        {"colour_name": "Gold", "colour_hex": "#d4af37"}
    )
    db.flush()
    _list_product(client, host, {"accessory_id": item.id})
    (entry,) = product_tag_accessories(db, host.id)
    assert entry["colours"] == [], "a colour left on a picture row is not a dot"
    assert entry["images"][0]["colour_hex"] is None


def test_a_combo_list_carries_the_colours_too(db, monkeypatch, storage, signed):
    from app.services.accessory_service import combo_tag_accessories

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZCOL")
    cb = seed.combo(db, host, "ZZT 1 tap")
    item = _accessory(db, _name("COMBOCOL"))
    _picture(client, item.id, 1)
    _put(client, item.id, [BLACK, GREY])
    response = client.put(COMBO_LIST.format(combo_id=cb.id), json={"items": [{"accessory_id": item.id}]})
    assert response.status_code == 200, response.text
    (entry,) = combo_tag_accessories(db, cb.id)
    assert entry["colours"] == [BLACK, GREY]


def test_the_tag_data_route_returns_colours_and_null_picture_colours(db, monkeypatch, storage, signed):
    client = _caller(db, _Everything(), monkeypatch)
    host = seed.product(db, "ZZCOL")
    item = _accessory(db, _name("HTTPCOL"))
    _picture(client, item.id, 1)
    _put(client, item.id, [BLACK, GREY])
    _list_product(client, host, {"accessory_id": item.id})
    response = client.get(TAG_DATA.format(id=host.id))
    assert response.status_code == 200, response.text
    (entry,) = response.json()["accessories"]
    assert entry["colours"] == [BLACK, GREY], "response_model must declare and keep the list"
    assert len(entry["images"]) == 1
    assert entry["images"][0]["colour_name"] is None and entry["images"][0]["colour_hex"] is None


def test_the_colours_list_is_part_of_what_a_pin_freezes(db, monkeypatch, storage, signed):
    from app.services.dealer_kit import tag_data_service

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZCOL")
    item = _accessory(db, _name("PINNED"))
    _put(client, item.id, [BLACK, GREY])
    _list_product(client, host, {"accessory_id": item.id})
    request = seed.submit_one(db, host, None, [])
    db.flush()
    pinned = tag_data_service.pin_payload(tag_data_service.resolve_tags_live(db, request)[0])
    _put(client, item.id, [{"name": "Gold", "hex": "#d4af37"}])
    line = request.lines[0]
    row = tag_data_service._row_from_pin(db, line, line.tags[0], pinned, "1a")
    (entry,) = row["accessories"]
    assert entry["colours"] == [BLACK, GREY]
