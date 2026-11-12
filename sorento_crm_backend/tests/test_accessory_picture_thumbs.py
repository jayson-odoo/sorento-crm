"""PRICETAG-ACC-PICTURE-PICKER: each picture of a list entry carries its 320 px rendition.

Plan: documentation/plans/dealer-kit/PLAN-pricetag-acc-picture-picker-09nov.md. Written test-FIRST:
`thumb_url` is not on the picture yet. The rendition service is stubbed (the fake storage holds no
decodable image), so the test pins that the list asks THAT service, once per list, for "thumb".
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.company_scope import register_company_scope_listeners

from tests._pg_fixture import blank_session
from tests.test_accessories import (  # noqa: F401
    EDIT,
    PRODUCT_LIST,
    VIEW,
    _accessory,
    _caller,
    _name,
    _product,
    storage,
)
from tests.test_accessory_designer_entries import _picture, _put


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


def test_list_pictures_carry_the_thumb_rendition(db, monkeypatch, storage):
    from app.services import image_thumbnailer

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZTHUMB")
    colander = _accessory(db, _name("COLANDER"))
    first = _picture(client, colander.id, 1)
    second = _picture(client, colander.id, 2)
    board = _accessory(db, _name("BOARD"))
    _picture(client, board.id, 3)

    asked = []

    def fake_renditions(_db, attachment_ids, size, **_kw):
        ids = [a for a in attachment_ids if a]
        asked.append((sorted(ids), size))
        # The second picture's rendition is not ready: it is left out, as the real service does.
        return {a: f"https://cdn.test/{a}.thumb.jpg" for a in ids if a != second["attachment_id"]}

    monkeypatch.setattr(image_thumbnailer, "rendition_urls", fake_renditions)

    url = PRODUCT_LIST.format(product_id=host.id)
    put = _put(client, url, {"accessory_id": colander.id, "image_id": second["id"]}, {"accessory_id": board.id})
    assert put.status_code == 200, put.text

    asked.clear()
    rows = client.get(url).json()["data"]
    pictures = rows[0]["images"]
    assert [p["id"] for p in pictures] == [first["id"], second["id"]]
    assert pictures[0]["thumb_url"] == f"https://cdn.test/{first['attachment_id']}.thumb.jpg"
    assert pictures[1]["thumb_url"] is None, "not ready: no thumb, the caller falls back"
    assert pictures[0]["url"] == first["url"], "the original stays as it was"
    assert rows[1]["images"][0]["thumb_url"].endswith(".thumb.jpg")
    assert rows[0]["image"]["thumb_url"] == pictures[0]["thumb_url"], "a legacy-only picture reads `image`"
    assert len(asked) == 1 and asked[0][1] == "thumb", "one rendition call for the whole list"


def _png(colour: str) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (800, 600), colour).save(buf, "PNG")
    return buf.getvalue()


def test_an_upload_makes_its_thumb_and_a_delete_takes_it(db, monkeypatch, storage):
    """Renditions are made at upload, as on every other upload path, so a list never waits; the
    thumb goes with its original when the picture is removed."""
    from app.models.resources import Attachment
    from app.services.accessory_service import AccessoryService

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    colander = _accessory(db, _name("COLANDER"))
    response = client.post(
        f"/api/v1/master-data/accessories/{colander.id}/images",
        files={"file": ("blue.png", _png("#1d4ed8"), "image/png")},
    )
    assert response.status_code == 201, response.text
    picture = response.json()
    attachment = db.query(Attachment).filter(Attachment.id == picture["attachment_id"]).one()
    assert attachment.thumbnail_path, "the thumb is recorded on the attachment"
    thumbs = [key for key in storage.objects if key.endswith(".thumb.jpg")]
    assert len(thumbs) == 1 and any(key.endswith(".medium.jpg") for key in storage.objects)

    AccessoryService(db).delete_picture(colander.id, picture["id"])
    assert not [key for key in storage.objects if key.endswith(".thumb.jpg")], "the thumb went too"
