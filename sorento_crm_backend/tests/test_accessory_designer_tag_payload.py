"""PRICETAG-ACCESSORY-DESIGNER S1: the tag payload carries images, colours, remark and overrides.

Plan: PLAN-pricetag-accessory-designer-07nov.md "Tag payload". Written test-FIRST: `TagAccessory` has no
`remark` / `images` / `colours` yet and `_resign_accessories` re-signs only `image`.

Note for the coder: `tests/test_accessories.py::test_a3_product_tag_data_carries_the_products_list` asserts the
OLD exact dict and must be updated to the new key set in the same slice.
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.company_scope import register_company_scope_listeners

from tests import _ptag_combo_seed as seed
from tests._pg_fixture import blank_session
from tests.test_accessories import (  # noqa: F401
    COMBO_LIST,
    EDIT,
    PRODUCT_LIST,
    VIEW,
    _accessory,
    _caller,
    _clear_overrides,
    _jpg_bytes,
    _name,
    _product,
    signed,
    storage,
)

IMAGES = "/api/v1/master-data/accessories/{accessory_id}/images"
ACCESSORY = "/api/v1/master-data/accessories/{accessory_id}"

NEW_KEYS = {"kind", "id", "name", "spec", "remark", "image", "images", "colours", "code", "list_price"}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


def _picture(client, accessory_id, n=0, **form):
    response = client.post(
        IMAGES.format(accessory_id=accessory_id),
        files={"file": (f"p{n}.jpg", _jpg_bytes() + bytes([n]), "image/jpeg")},
        data=form,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _list(client, product, *entries):
    response = client.put(PRODUCT_LIST.format(product_id=product.id), json={"items": list(entries)})
    assert response.status_code == 200, response.text


def _colander(db, client):
    item = _accessory(db, _name("COLANDER"))
    black = _picture(client, item.id, 1, colour_name="Black", colour_hex="#1f2937")
    grey = _picture(client, item.id, 2, colour_name="Grey", colour_hex="#9ca3af")
    return item, black, grey


def _payload(db, product):
    from app.services.accessory_service import product_tag_accessories

    return product_tag_accessories(db, product.id)


def test_a_library_accessory_carries_the_full_key_set(db, monkeypatch, storage, signed):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPAY")
    item = _accessory(db, _name("BARE"))
    _list(client, host, {"accessory_id": item.id})
    (entry,) = _payload(db, host)
    assert NEW_KEYS <= set(entry)
    assert entry["images"] == [] and entry["colours"] == [] and entry["remark"] is None
    assert entry["image"] is None


def test_images_colours_and_the_default_first_picture(db, monkeypatch, storage, signed):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPAY")
    item, black, grey = _colander(db, client)
    _picture(client, item.id, 3, colour_name="Black again", colour_hex="#1f2937")
    _picture(client, item.id, 4)  # no colour
    _list(client, host, {"accessory_id": item.id})
    (entry,) = _payload(db, host)

    assert [image["attachment_id"] for image in entry["images"][:2]] == [
        black["attachment_id"],
        grey["attachment_id"],
    ]
    assert len(entry["images"]) == 4
    assert all(image["url"].startswith("https://") for image in entry["images"])
    assert {"attachment_id", "url", "colour_name", "colour_hex"} <= set(entry["images"][0])
    assert entry["image"]["attachment_id"] == black["attachment_id"], "no choice = the first"
    assert entry["colours"] == [
        {"name": "Black", "hex": "#1f2937"},
        {"name": "Grey", "hex": "#9ca3af"},
    ], "distinct by hex, in picture order, only pictures with a hex"


def test_the_entrys_chosen_picture_is_the_image(db, monkeypatch, storage, signed):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPAY")
    item, black, grey = _colander(db, client)
    _list(client, host, {"accessory_id": item.id, "image_id": grey["id"]})
    (entry,) = _payload(db, host)
    assert entry["image"]["attachment_id"] == grey["attachment_id"]
    assert entry["images"][0]["attachment_id"] == black["attachment_id"], "images keep picture order"
    assert [c["hex"] for c in entry["colours"]] == ["#1f2937", "#9ca3af"], "dots show all colours"


def test_a_deleted_chosen_picture_falls_back_to_the_first(db, monkeypatch, storage, signed):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPAY")
    item, black, grey = _colander(db, client)
    _list(client, host, {"accessory_id": item.id, "image_id": grey["id"]})
    assert client.delete(IMAGES.format(accessory_id=item.id) + f"/{grey['id']}").status_code == 204
    (entry,) = _payload(db, host)
    assert entry["image"]["attachment_id"] == black["attachment_id"]


def test_name_spec_remark_overrides_win_when_not_blank(db, monkeypatch, storage, signed):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPAY")
    item = _accessory(db, _name("OVERRIDDEN"), "390x200x140")
    client.patch(ACCESSORY.format(accessory_id=item.id), json={"remark": "Library remark"})
    other = _accessory(db, _name("INHERITS"), "Library spec")
    client.patch(ACCESSORY.format(accessory_id=other.id), json={"remark": "Other remark"})
    _list(
        client,
        host,
        {"accessory_id": item.id, "name": "Sink colander", "spec": "Depth: 160mm", "remark": "Use remark"},
        {"accessory_id": other.id, "name": " ", "spec": "", "remark": ""},
    )
    first, second = _payload(db, host)
    assert (first["name"], first["spec"], first["remark"]) == ("Sink colander", "Depth: 160mm", "Use remark")
    assert (second["name"], second["spec"], second["remark"]) == (other.name, "Library spec", "Other remark")


def test_a_combo_list_gets_the_same_payload(db, monkeypatch, storage, signed):
    from app.services.accessory_service import combo_tag_accessories

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPAY")
    cb = seed.combo(db, host, "ZZT 1 tap")
    item, black, grey = _colander(db, client)
    response = client.put(
        COMBO_LIST.format(combo_id=cb.id),
        json={"items": [{"accessory_id": item.id, "image_id": grey["id"], "name": "Combo colander"}]},
    )
    assert response.status_code == 200, response.text
    (entry,) = combo_tag_accessories(db, cb.id)
    assert entry["name"] == "Combo colander"
    assert entry["image"]["attachment_id"] == grey["attachment_id"]
    assert len(entry["images"]) == 2 and len(entry["colours"]) == 2


def test_a_product_entry_spec_is_the_price_tag_description_unless_overridden(db, monkeypatch, storage, signed):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPAY")
    waste = seed.product(db, "ZZWASTE", list_price="68.00")
    waste.description = "Popup Waste 80mm"
    waste.price_tag_description = "Brass, w/o overflow"
    db.flush()
    _list(client, host, {"product_id": waste.id})
    (entry,) = _payload(db, host)
    assert entry["kind"] == "product"
    assert entry["name"] == "Popup Waste 80mm", "name unchanged: description, else name"
    assert entry["spec"] == "Brass, w/o overflow"
    assert entry["remark"] is None
    assert entry["colours"] == []
    assert entry["images"] == [] and entry["image"] is None, "no lead photo seeded"
    assert entry["code"] == waste.product_code and float(entry["list_price"]) == 68.0

    _list(client, host, {"product_id": waste.id, "name": "Pop-up waste", "spec": "Own spec", "remark": "FREE"})
    (over,) = _payload(db, host)
    assert (over["name"], over["spec"], over["remark"]) == ("Pop-up waste", "Own spec", "FREE")


def test_a_product_without_a_price_tag_description_has_no_spec(db, monkeypatch, storage, signed):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPAY")
    waste = seed.product(db, "ZZWASTE")
    waste.price_tag_description = None
    db.flush()
    _list(client, host, {"product_id": waste.id})
    (entry,) = _payload(db, host)
    assert entry["spec"] is None


# --------------------------------------------------------------------------- pinned rows


def test_resign_refreshes_every_image_url_and_keeps_the_colours(db, monkeypatch, storage, signed):
    from app.services.dealer_kit.tag_data_service import _resign_accessories

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    item, black, grey = _colander(db, client)
    pinned = [
        {
            "kind": "accessory",
            "id": item.id,
            "name": "COLANDER",
            "spec": None,
            "remark": "Follows sink",
            "code": None,
            "list_price": None,
            "image": {"attachment_id": grey["attachment_id"], "url": "https://stale.test/old"},
            "images": [
                {
                    "attachment_id": black["attachment_id"],
                    "url": "https://stale.test/a",
                    "colour_name": "Black",
                    "colour_hex": "#1f2937",
                },
                {
                    "attachment_id": grey["attachment_id"],
                    "url": "https://stale.test/b",
                    "colour_name": "Grey",
                    "colour_hex": "#9ca3af",
                },
            ],
            "colours": [{"name": "Black", "hex": "#1f2937"}, {"name": "Grey", "hex": "#9ca3af"}],
        }
    ]
    (fresh,) = _resign_accessories(db, pinned)
    assert fresh["image"]["url"] != "https://stale.test/old" and fresh["image"]["url"].startswith("https://")
    assert [i["attachment_id"] for i in fresh["images"]] == [black["attachment_id"], grey["attachment_id"]]
    assert all("stale.test" not in i["url"] for i in fresh["images"])
    assert [i["colour_hex"] for i in fresh["images"]] == ["#1f2937", "#9ca3af"]
    assert [i["colour_name"] for i in fresh["images"]] == ["Black", "Grey"]
    assert fresh["colours"] == pinned[0]["colours"] and fresh["remark"] == "Follows sink"


def test_resign_drops_a_picture_whose_attachment_has_gone(db, monkeypatch, storage, signed):
    import uuid

    from app.services.dealer_kit.tag_data_service import _resign_accessories

    pinned = [
        {
            "kind": "accessory", "id": "a", "name": "X", "spec": None, "code": None, "list_price": None,
            "image": None,
            "images": [
                {"attachment_id": str(uuid.uuid4()), "url": "https://stale.test/x",
                 "colour_name": None, "colour_hex": None}
            ],
            "colours": [],
        }
    ]
    (fresh,) = _resign_accessories(db, pinned)
    assert fresh["images"] == [] and fresh["name"] == "X"


def test_a_row_pinned_before_this_lane_reads_empty_images_colours_and_no_remark(db, signed):
    from app.services.dealer_kit.tag_data_service import _resign_accessories

    old = [{"kind": "accessory", "id": "a", "name": "DRAINER", "spec": "s", "image": None,
            "code": None, "list_price": None}]
    (row,) = _resign_accessories(db, old)
    assert row["images"] == [] and row["colours"] == [] and row["remark"] is None


def test_a_pinned_request_row_keeps_the_new_keys_and_resigns(db, monkeypatch, storage, signed):
    from app.services.dealer_kit import tag_data_service

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPAY")
    item, black, grey = _colander(db, client)
    _list(client, host, {"accessory_id": item.id, "image_id": grey["id"], "remark": "Pinned remark"})
    request = seed.submit_one(db, host, None, [])
    db.flush()
    live = tag_data_service.resolve_tags_live(db, request)[0]
    pinned = tag_data_service.pin_payload(live)
    line = request.lines[0]
    row = tag_data_service._row_from_pin(db, line, line.tags[0], pinned, "1a")
    (entry,) = row["accessories"]
    assert entry["remark"] == "Pinned remark"
    assert entry["image"]["attachment_id"] == grey["attachment_id"]
    assert len(entry["images"]) == 2 and len(entry["colours"]) == 2


def test_a_picture_only_on_the_legacy_column_still_reaches_the_tag(db, monkeypatch, storage, signed):
    """Owner hand test 07/11: on a database where `ptag_0017`'s data copy never ran (a dev copy that
    converges through `create_all` or the crew SQL), an accessory's picture lives ONLY on
    `accessories.image_attachment_id`. The tag must still draw it (legacy boxes print as before, a card's
    picture element shows it): `image` and a one-entry `images`, no colour."""
    from app.models.accessory import AccessoryImage

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPAY")
    item = _accessory(db, _name("LEGACYPIC"))
    uploaded = _picture(client, item.id, 7)
    # The state before the copy step: the column holds the picture, no accessory_images row.
    db.query(AccessoryImage).filter(AccessoryImage.accessory_id == item.id).delete()
    item.image_attachment_id = uploaded["attachment_id"]
    db.commit()
    _list(client, host, {"accessory_id": item.id})

    (entry,) = _payload(db, host)
    assert entry["image"] is not None, "the legacy picture is dropped from the tag"
    assert entry["image"]["attachment_id"] == uploaded["attachment_id"]
    assert entry["image"]["url"].startswith("https://")
    assert [image["attachment_id"] for image in entry["images"]] == [uploaded["attachment_id"]]
    assert entry["images"][0]["colour_hex"] is None
    assert entry["colours"] == []
