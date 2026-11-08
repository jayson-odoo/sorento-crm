"""PRICETAG-ACCESSORY-DESIGNER S1: per-list-row overrides {image_id, name, spec, remark}.

Plan: PLAN-pricetag-accessory-designer-07nov.md "List entries". Written test-FIRST: the entry body
fields and the `entry` block on the output do not exist yet.
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.company_scope import register_company_scope_listeners

from tests._pg_fixture import blank_session
from tests.test_accessories import (  # noqa: F401
    COMBO_LIST,
    EDIT,
    PRODUCT_LIST,
    VIEW,
    _accessory,
    _caller,
    _clear_overrides,
    _combo,
    _jpg_bytes,
    _name,
    _product,
    storage,
)

IMAGES = "/api/v1/master-data/accessories/{accessory_id}/images"


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


def _put(client, url, *entries):
    return client.put(url, json={"items": list(entries)})


@pytest.mark.parametrize("list_url,make_owner", [(PRODUCT_LIST, "product"), (COMBO_LIST, "combo")])
def test_overrides_round_trip_on_both_lists(db, monkeypatch, storage, list_url, make_owner):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZDES")
    owner = host if make_owner == "product" else _combo(db, host, "ZZT 1 tap")
    url = list_url.format(**({"product_id": owner.id} if make_owner == "product" else {"combo_id": owner.id}))
    colander = _accessory(db, _name("COLANDER"))
    _picture(client, colander.id, 1, colour_name="Black", colour_hex="#1f2937")
    grey = _picture(client, colander.id, 2, colour_name="Grey", colour_hex="#9ca3af")
    board = _accessory(db, _name("BOARD"))

    put = _put(
        client,
        url,
        {
            "accessory_id": colander.id,
            "image_id": grey["id"],
            "name": "Sink colander",
            "spec": "390x200x140",
            "remark": "Colour follows sink",
        },
        {"accessory_id": board.id},
    )
    assert put.status_code == 200, put.text
    first, second = put.json()["data"]
    assert first["entry"] == {
        "image_id": grey["id"],
        "name": "Sink colander",
        "spec": "390x200x140",
        "remark": "Colour follows sink",
    }
    assert second["entry"] == {"image_id": None, "name": None, "spec": None, "remark": None}

    got = client.get(url).json()["data"]
    assert [row["entry"] for row in got] == [first["entry"], second["entry"]]
    assert got[0]["id"] == colander.id and got[0]["name"] == colander.name, "the accessory itself is unchanged"


def test_blank_strings_are_no_override(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZDES")
    item = _accessory(db, _name("BLANKS"))
    url = PRODUCT_LIST.format(product_id=host.id)
    put = _put(client, url, {"accessory_id": item.id, "name": "   ", "spec": "", "remark": " \n "})
    assert put.status_code == 200, put.text
    assert put.json()["data"][0]["entry"] == {"image_id": None, "name": None, "spec": None, "remark": None}


def test_replacing_the_list_replaces_the_overrides(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZDES")
    item = _accessory(db, _name("REPLACED"))
    url = PRODUCT_LIST.format(product_id=host.id)
    _put(client, url, {"accessory_id": item.id, "name": "Own name"})
    again = _put(client, url, {"accessory_id": item.id})
    assert again.json()["data"][0]["entry"]["name"] is None


def test_an_image_of_another_accessory_is_422(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZDES")
    mine, other = _accessory(db, _name("MINE")), _accessory(db, _name("OTHER"))
    theirs = _picture(client, other.id, 1)
    for url in (
        PRODUCT_LIST.format(product_id=host.id),
        COMBO_LIST.format(combo_id=_combo(db, host, "ZZT 1 tap").id),
    ):
        response = _put(client, url, {"accessory_id": mine.id, "image_id": theirs["id"]})
        assert response.status_code == 422, response.text
        assert client.get(url).json()["data"] == []


def test_an_unknown_image_id_is_422(db, monkeypatch, storage):
    import uuid

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZDES")
    item = _accessory(db, _name("GHOST"))
    response = _put(
        client,
        PRODUCT_LIST.format(product_id=host.id),
        {"accessory_id": item.id, "image_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422, response.text


def test_an_image_id_on_a_product_entry_is_422(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZDES")
    waste = _product(db, "ZZWASTE")
    item = _accessory(db, _name("DONOR"))
    picture = _picture(client, item.id, 1)
    for url in (
        PRODUCT_LIST.format(product_id=host.id),
        COMBO_LIST.format(combo_id=_combo(db, host, "ZZT 1 tap").id),
    ):
        response = _put(client, url, {"product_id": waste.id, "image_id": picture["id"]})
        assert response.status_code == 422, response.text


def test_a_product_entry_keeps_name_spec_remark_overrides(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZDES")
    waste = _product(db, "ZZWASTE")
    url = PRODUCT_LIST.format(product_id=host.id)
    put = _put(
        client,
        url,
        {"product_id": waste.id, "name": "Pop-up waste 80mm, brass", "spec": "Brass", "remark": "FREE"},
    )
    assert put.status_code == 200, put.text
    (row,) = put.json()["data"]
    assert row["kind"] == "product"
    assert row["entry"] == {
        "image_id": None,
        "name": "Pop-up waste 80mm, brass",
        "spec": "Brass",
        "remark": "FREE",
    }


def test_override_text_is_sanitised(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZDES")
    item = _accessory(db, _name("DIRTYENTRY"))
    put = _put(
        client,
        PRODUCT_LIST.format(product_id=host.id),
        {"accessory_id": item.id, "spec": '<p onclick="x()">ok<script>alert(1)</script></p>'},
    )
    assert put.status_code == 200, put.text
    spec = put.json()["data"][0]["entry"]["spec"]
    assert "ok" in spec and "<script" not in spec and "onclick" not in spec


def test_view_only_cannot_put_overrides(db, monkeypatch, storage):
    client = _caller(db, {VIEW}, monkeypatch)
    host = _product(db, "ZZDES")
    item = _accessory(db, _name("VIEWONLY"))
    response = _put(client, PRODUCT_LIST.format(product_id=host.id), {"accessory_id": item.id, "name": "x"})
    assert response.status_code == 403
