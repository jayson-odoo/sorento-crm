"""PRICETAG-ACCESSORY-DESIGNER S1: several coloured pictures per accessory, remark, sanitised rich spec.

Plan: documentation/plans/dealer-kit/PLAN-pricetag-accessory-designer-07nov.md (S1 Backend contract,
"Accessory pictures"). Written test-FIRST: `/accessories/{id}/images` does not exist yet (404/405), and
`AccessoryOut` has no `images` / `remark`.

Harness copied from `tests/test_accessories.py` (auth + company scope overrides, FakeStorage).
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.company_scope import register_company_scope_listeners

from tests._pg_fixture import blank_session
from tests.test_accessories import (  # noqa: F401  (fixtures + helpers reused as-is)
    ACCESSORIES,
    ACCESSORY,
    ACCESSORY_IMAGE,
    EDIT,
    MOCHA,
    VIEW,
    _accessory,
    _caller,
    _clear_overrides,
    _jpg_bytes,
    _mocha,
    _name,
    storage,
)

IMAGES = "/api/v1/master-data/accessories/{accessory_id}/images"
IMAGE = "/api/v1/master-data/accessories/{accessory_id}/images/{image_id}"
ORDER = "/api/v1/master-data/accessories/{accessory_id}/images/order"

BLACK = {"colour_name": "Black", "colour_hex": "#1f2937"}
GREY = {"colour_name": "Grey", "colour_hex": "#9ca3af"}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


def _jpg(n: int = 0) -> bytes:
    return _jpg_bytes() + bytes([n % 250])


def _add(client, accessory_id, n=0, **form):
    return client.post(
        IMAGES.format(accessory_id=accessory_id),
        files={"file": (f"p{n}.jpg", _jpg(n), "image/jpeg")},
        data=form,
    )


def _get(client, accessory_id):
    response = client.get(ACCESSORY.format(accessory_id=accessory_id))
    assert response.status_code == 200, response.text
    return response.json()


def test_post_appends_an_image_and_a_colour_form_field_is_ignored(db, monkeypatch, storage):
    """S7: a picture carries no colour; the colours are their own list."""
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("COLANDER"))
    first = _add(client, row.id, 1, **BLACK)
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["colour_name"] is None and body["colour_hex"] is None
    assert body["id"] and body["attachment_id"] and body["url"]
    second = _add(client, row.id, 2, **GREY)
    assert second.status_code == 201, second.text

    out = _get(client, row.id)
    assert [image["id"] for image in out["images"]] == [body["id"], second.json()["id"]]
    assert [image["colour_hex"] for image in out["images"]] == [None, None]
    assert out["colours"] == [], "no colours came from the pictures"
    assert out["image"]["attachment_id"] == body["attachment_id"], "image = the first picture"


def test_post_without_a_colour_is_allowed(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("PLAIN"))
    response = _add(client, row.id, 1)
    assert response.status_code == 201, response.text
    assert response.json()["colour_hex"] is None and response.json()["colour_name"] is None


def test_post_refuses_a_non_image(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("BADHEX"))
    svg = client.post(
        IMAGES.format(accessory_id=row.id), files={"file": ("x.svg", b"<svg/>", "image/svg+xml")}
    )
    assert svg.status_code == 422
    assert _get(client, row.id)["images"] == []


def test_view_only_cannot_add_change_or_remove_an_image(db, monkeypatch, storage):
    writer = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("VIEWONLY"))
    image = _add(writer, row.id, 1).json()
    viewer = _caller(db, {VIEW}, monkeypatch)
    assert _add(viewer, row.id, 2).status_code == 403
    url = IMAGE.format(accessory_id=row.id, image_id=image["id"])
    assert viewer.patch(url, json={"colour_name": "X"}).status_code == 403
    assert viewer.delete(url).status_code == 403
    assert viewer.put(ORDER.format(accessory_id=row.id), json={"ids": [image["id"]]}).status_code == 403


def test_the_13th_image_is_422(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("MANY"))
    for n in range(12):
        assert _add(client, row.id, n).status_code == 201
    over = _add(client, row.id, 99)
    assert over.status_code == 422, over.text
    assert len(_get(client, row.id)["images"]) == 12


def test_patch_ignores_colour_fields_whatever_they_hold(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("PATCHED"))
    image = _add(client, row.id, 1).json()
    url = IMAGE.format(accessory_id=row.id, image_id=image["id"])
    for body in ({"colour_name": "Gold", "colour_hex": "#D4AF37"}, {"colour_hex": "#fff"}, {}):
        response = client.patch(url, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["colour_hex"] is None and response.json()["colour_name"] is None
    assert _get(client, row.id)["images"][0]["colour_hex"] is None


def test_an_image_of_another_accessory_is_404_on_patch_and_delete(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    mine = _accessory(db, _name("MINE"))
    other = _accessory(db, _name("OTHER"))
    theirs = _add(client, other.id, 1, **BLACK).json()
    url = IMAGE.format(accessory_id=mine.id, image_id=theirs["id"])
    assert client.patch(url, json={"colour_name": "Stolen"}).status_code == 404
    assert client.delete(url).status_code == 404
    assert len(_get(client, other.id)["images"]) == 1


def test_delete_removes_one_image_and_the_next_becomes_the_default(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("DELETED"))
    a = _add(client, row.id, 1, **BLACK).json()
    b = _add(client, row.id, 2, **GREY).json()
    response = client.delete(IMAGE.format(accessory_id=row.id, image_id=a["id"]))
    assert response.status_code == 204, response.text
    out = _get(client, row.id)
    assert [image["id"] for image in out["images"]] == [b["id"]]
    assert out["image"]["attachment_id"] == b["attachment_id"]


def test_order_reorders_and_image_follows_the_first(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("ORDERED"))
    a = _add(client, row.id, 1, **BLACK).json()
    b = _add(client, row.id, 2, **GREY).json()
    c = _add(client, row.id, 3).json()
    response = client.put(ORDER.format(accessory_id=row.id), json={"ids": [c["id"], a["id"], b["id"]]})
    assert response.status_code == 200, response.text
    assert [image["id"] for image in response.json()] == [c["id"], a["id"], b["id"]]
    out = _get(client, row.id)
    assert [image["id"] for image in out["images"]] == [c["id"], a["id"], b["id"]]
    assert out["image"]["attachment_id"] == c["attachment_id"]


def test_order_must_be_exactly_the_current_set(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("ORDERBAD"))
    other = _accessory(db, _name("ORDEROTHER"))
    a = _add(client, row.id, 1).json()
    b = _add(client, row.id, 2).json()
    foreign = _add(client, other.id, 3).json()
    url = ORDER.format(accessory_id=row.id)
    assert client.put(url, json={"ids": [a["id"]]}).status_code == 422, "missing one"
    assert client.put(url, json={"ids": [a["id"], b["id"], foreign["id"]]}).status_code == 422, "extra"
    assert client.put(url, json={"ids": [a["id"], a["id"]]}).status_code == 422, "duplicate"
    assert [i["id"] for i in _get(client, row.id)["images"]] == [a["id"], b["id"]]


def test_the_old_image_routes_still_work_on_image_one(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("OLDROUTE"))
    old = client.post(
        ACCESSORY_IMAGE.format(accessory_id=row.id),
        files={"file": ("a.jpg", _jpg(1), "image/jpeg")},
    )
    assert old.status_code == 200, old.text
    images = _get(client, row.id)["images"]
    assert len(images) == 1 and images[0]["attachment_id"] == old.json()["attachment_id"]
    assert client.delete(ACCESSORY_IMAGE.format(accessory_id=row.id)).status_code == 204
    out = _get(client, row.id)
    assert out["images"] == [] and out["image"] is None


def test_a_new_accessory_has_no_images_and_no_remark(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    body = client.post(ACCESSORIES, json={"name": _name("FRESH")}).json()
    assert body["images"] == [] and body["image"] is None and body["remark"] is None


def test_remark_round_trips_on_post_and_patch(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    created = client.post(ACCESSORIES, json={"name": _name("REMARKED"), "remark": "Colour follows sink"})
    assert created.status_code == 201, created.text
    assert created.json()["remark"] == "Colour follows sink"
    url = ACCESSORY.format(accessory_id=created.json()["id"])
    edited = client.patch(url, json={"remark": "Other"})
    assert edited.status_code == 200 and edited.json()["remark"] == "Other"
    assert client.get(url).json()["remark"] == "Other"
    untouched = client.patch(url, json={"spec": "x"})
    assert untouched.json()["remark"] == "Other", "omitted = left alone"
    cleared = client.patch(url, json={"remark": "  "})
    assert cleared.json()["remark"] is None


def test_spec_and_remark_are_sanitised(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    dirty = '<p onclick="steal()">Safe <b>bold</b><script>alert(1)</script><a href="http://x.test">link</a></p>'
    created = client.post(ACCESSORIES, json={"name": _name("DIRTY"), "spec": dirty, "remark": dirty})
    assert created.status_code == 201, created.text
    for field in ("spec", "remark"):
        value = created.json()[field]
        assert "Safe" in value and "bold" in value
        assert "<script" not in value and "alert(1)" not in value
        assert "onclick" not in value
        assert "href" not in value
    url = ACCESSORY.format(accessory_id=created.json()["id"])
    patched = client.patch(url, json={"spec": dirty, "remark": dirty}).json()
    for field in ("spec", "remark"):
        assert "<script" not in patched[field] and "onclick" not in patched[field]


def test_spec_may_be_longer_than_the_old_200_characters(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    spec = "Depth: 160mm. " * 40  # 560 characters
    created = client.post(ACCESSORIES, json={"name": _name("LONGSPEC"), "spec": spec})
    assert created.status_code == 201, created.text
    assert created.json()["spec"].startswith("Depth: 160mm.")
    assert len(created.json()["spec"]) > 200


def test_another_companys_images_are_404(db, monkeypatch, storage):
    _mocha(db)
    theirs = _accessory(db, _name("THEIRS"), company_id=MOCHA)
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    mine = _accessory(db, _name("MINE"))
    assert _add(client, mine.id, 1).status_code == 201, "the route exists for my own accessory"
    assert _add(client, theirs.id, 1).status_code == 404
    assert client.put(ORDER.format(accessory_id=theirs.id), json={"ids": []}).status_code == 404
