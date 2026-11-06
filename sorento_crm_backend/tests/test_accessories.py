"""PRICETAG-ACCESSORIES: the accessories library, the product and combo lists, and the tag payload.

Plan + contract: `documentation/plans/dealer-kit/PLAN-pricetag-accessories-06nov.md`.
Card (rules A1-A12): `documentation/plans/dealer-kit/CARD-pricetag-accessories-06nov.md`.

Written test-FIRST (PRINCIPLES.md Phase 2): `app/models/accessory.py`, the routes and the tag
payload key do not exist yet, so the model import fails the whole file with one ImportError.

Harness: `tests/test_product_combos.py` (auth + company scope overrides, real FK chain per test)
and `tests/_ptag_combo_seed.py` (request lines). Synthetic names only.
"""
from __future__ import annotations

import uuid

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.company_scope import register_company_scope_listeners

# THE red import.
from app.models.accessory import (  # noqa: E402
    Accessory,
    ProductAccessory,
    ProductComboAccessory,
)

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests._fake_storage import FakeStorage
from tests._pg_fixture import blank_session, unique_code
from tests.test_product_combos import (  # noqa: F401  (fixtures + helpers reused as-is)
    EDIT,
    MOCHA,
    VIEW,
    _caller,
    _clear_overrides,
    _combo,
    _mocha,
    _product,
)

ACCESSORIES = "/api/v1/master-data/accessories"
ACCESSORY = "/api/v1/master-data/accessories/{accessory_id}"
ACCESSORY_IMAGE = "/api/v1/master-data/accessories/{accessory_id}/image"
PRODUCT_LIST = "/api/v1/master-data/products/{product_id}/accessories"
COMBO_LIST = "/api/v1/master-data/product-combos/{combo_id}/accessories"
COMBO = "/api/v1/master-data/product-combos/{combo_id}"
COMBOS = "/api/v1/master-data/products/{product_id}/combos"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture()
def storage(monkeypatch) -> FakeStorage:
    """Accessory pictures go through an in-process fake, never a real bucket."""
    from app.services import accessory_service, storage_router

    fake = FakeStorage()
    for module in (storage_router, accessory_service):
        monkeypatch.setattr(module, "default_provider", lambda: "s3")
        monkeypatch.setattr(module, "get_backend", lambda provider: fake)
        monkeypatch.setattr(module, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}")
    return fake


def _jpg_bytes() -> bytes:
    return bytes.fromhex("ffd8ffe000104a4649460001") + b"\x00" * 32 + bytes.fromhex("ffd9")


def _accessory(db, name: str, spec: str | None = None, *, company_id: str = seed.SORENTO) -> Accessory:
    row = Accessory(id=str(uuid.uuid4()), company_id=company_id, name=name, spec=spec)
    db.add(row)
    db.flush()
    return row


def _link_product(db, product, accessories):
    for index, item in enumerate(accessories):
        db.add(
            ProductAccessory(
                id=str(uuid.uuid4()), product_id=product.id, accessory_id=item.id, sort_order=index
            )
        )
    db.flush()


def _link_combo(db, combo, accessories):
    for index, item in enumerate(accessories):
        db.add(
            ProductComboAccessory(
                id=str(uuid.uuid4()), combo_id=combo.id, accessory_id=item.id, sort_order=index
            )
        )
    db.flush()


def _name(stem: str) -> str:
    return unique_code(f"ZZT {stem}").upper()


# --------------------------------------------------------------------------- A1 library


def test_a1_create_list_and_read_an_accessory(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    name = _name("DRAINER")
    response = client.post(ACCESSORIES, json={"name": f"  {name} ", "spec": "390x300x140, Depth: 160mm"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == name, "the name is stored trimmed"
    assert body["spec"] == "390x300x140, Depth: 160mm"
    assert body["image"] is None
    assert body["product_count"] == 0 and body["combo_count"] == 0

    listed = client.get(ACCESSORIES, params={"query": name})
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["data"]] == [body["id"]]
    assert listed.json()["pagination"]["total"] == 1

    one = client.get(ACCESSORY.format(accessory_id=body["id"]))
    assert one.status_code == 200 and one.json()["name"] == name


def test_a1_a_blank_name_is_refused(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    response = client.post(ACCESSORIES, json={"name": "   "})
    assert response.status_code == 422, response.text


def test_a1_a_duplicate_name_ignoring_case_is_409(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    name = _name("COLANDER")
    assert client.post(ACCESSORIES, json={"name": name}).status_code == 201
    again = client.post(ACCESSORIES, json={"name": name.lower()})
    assert again.status_code == 409, again.text
    assert "already" in again.json().get("message", again.text).lower()


def test_a1_renaming_onto_another_name_is_409_and_spec_edits(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    first = _accessory(db, _name("BOARD"))
    second = _accessory(db, _name("RACK"))
    clash = client.patch(ACCESSORY.format(accessory_id=second.id), json={"name": first.name.lower()})
    assert clash.status_code == 409, clash.text

    edit = client.patch(ACCESSORY.format(accessory_id=second.id), json={"spec": "Depth: 160mm"})
    assert edit.status_code == 200, edit.text
    assert edit.json()["spec"] == "Depth: 160mm"
    cleared = client.patch(ACCESSORY.format(accessory_id=second.id), json={"spec": "  "})
    assert cleared.json()["spec"] is None, "a blank spec is no spec"


def test_a1_view_only_cannot_write(db, monkeypatch):
    client = _caller(db, {VIEW}, monkeypatch)
    assert client.get(ACCESSORIES).status_code == 200
    assert client.post(ACCESSORIES, json={"name": _name("X")}).status_code == 403


def test_a1_another_companys_accessory_is_404(db, monkeypatch):
    _mocha(db)
    theirs = _accessory(db, _name("THEIRS"), company_id=MOCHA)
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    assert client.get(ACCESSORY.format(accessory_id=theirs.id)).status_code == 404


def test_a1_delete_an_unused_accessory(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("UNUSED"))
    response = client.delete(ACCESSORY.format(accessory_id=row.id))
    assert response.status_code == 204, response.text
    db.expire_all()
    assert db.query(Accessory).filter(Accessory.id == row.id).first() is None


def test_a1_delete_is_refused_while_listed_and_names_the_count(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("LISTED"))
    host = _product(db, "ZZACC")
    _link_product(db, host, [row])
    _link_combo(db, _combo(db, host, "ZZT 1 tap"), [row])
    response = client.delete(ACCESSORY.format(accessory_id=row.id))
    assert response.status_code == 409, response.text
    message = response.json().get("message", response.text)
    assert "1 product" in message and "1 combo" in message, message


def test_a1_list_counts_usage(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("COUNTED"))
    host = _product(db, "ZZACC")
    _link_product(db, host, [row])
    _link_combo(db, _combo(db, host, "ZZT a"), [row])
    _link_combo(db, _combo(db, host, "ZZT b"), [row])
    body = client.get(ACCESSORY.format(accessory_id=row.id)).json()
    assert (body["product_count"], body["combo_count"]) == (1, 2)


def test_a1_picture_upload_and_remove(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("PICTURED"))
    response = client.post(
        ACCESSORY_IMAGE.format(accessory_id=row.id),
        files={"file": ("drainer.jpg", _jpg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["url"]
    body = client.get(ACCESSORY.format(accessory_id=row.id)).json()
    assert body["image"] and body["image"]["attachment_id"] == response.json()["attachment_id"]

    svg = client.post(
        ACCESSORY_IMAGE.format(accessory_id=row.id),
        files={"file": ("x.svg", b"<svg/>", "image/svg+xml")},
    )
    assert svg.status_code == 422

    removed = client.delete(ACCESSORY_IMAGE.format(accessory_id=row.id))
    assert removed.status_code == 204
    assert client.get(ACCESSORY.format(accessory_id=row.id)).json()["image"] is None


# --------------------------------------------------------------------------- A2 lists


def test_a2_product_list_replaces_in_order(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZACC")
    drainer, pullout, board = (_accessory(db, _name(n)) for n in ("DRAINER", "PULLOUT", "BOARD"))
    url = PRODUCT_LIST.format(product_id=host.id)

    put = client.put(url, json={"accessory_ids": [pullout.id, drainer.id]})
    assert put.status_code == 200, put.text
    assert [row["id"] for row in put.json()["data"]] == [pullout.id, drainer.id]

    again = client.put(url, json={"accessory_ids": [board.id, pullout.id]})
    assert [row["id"] for row in again.json()["data"]] == [board.id, pullout.id]
    assert [row["id"] for row in client.get(url).json()["data"]] == [board.id, pullout.id]

    assert client.put(url, json={"accessory_ids": []}).json()["data"] == []


def test_a2_product_list_refuses_duplicates_and_unknown_ids(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZACC")
    item = _accessory(db, _name("ONE"))
    url = PRODUCT_LIST.format(product_id=host.id)
    assert client.put(url, json={"accessory_ids": [item.id, item.id]}).status_code == 422
    assert client.put(url, json={"accessory_ids": [str(uuid.uuid4())]}).status_code == 404


def test_a2_product_list_needs_edit(db, monkeypatch):
    client = _caller(db, {VIEW}, monkeypatch)
    host = _product(db, "ZZACC")
    assert client.get(PRODUCT_LIST.format(product_id=host.id)).status_code == 200
    put = client.put(PRODUCT_LIST.format(product_id=host.id), json={"accessory_ids": []})
    assert put.status_code == 403


def test_a2_combo_list_is_independent_of_the_product_list(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZACC")
    combo = _combo(db, host, "ZZT 1 tap")
    drainer, pullout = _accessory(db, _name("DRAINER")), _accessory(db, _name("PULLOUT"))

    put = client.put(COMBO_LIST.format(combo_id=combo.id), json={"accessory_ids": [drainer.id, pullout.id]})
    assert put.status_code == 200, put.text
    assert client.get(PRODUCT_LIST.format(product_id=host.id)).json()["data"] == []

    combos = client.get(COMBOS.format(product_id=host.id)).json()["data"]
    assert [row["name"] for row in combos[0]["accessories"]] == [drainer.name, pullout.name]


def test_a2_combo_patch_no_longer_writes_free_items(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    combo = _combo(db, _product(db, "ZZACC"), "ZZT 1 tap")
    response = client.patch(COMBO.format(combo_id=combo.id), json={"free_items": "Tap, waste"})
    assert response.status_code == 200, response.text
    db.refresh(combo)
    assert combo.free_items is None, "free text is retired: one source of truth (Q5)"


# --------------------------------------------------------------------------- tag payload


@pytest.fixture()
def signed(monkeypatch):
    monkeypatch.setattr(
        "app.services.dealer_kit.product_images.resolve_signed_url",
        lambda path, **_kwargs: f"https://signed.example.test/{path.rsplit('/', 1)[-1]}",
    )
    r9.block_respond(monkeypatch)


def test_a3_product_tag_data_carries_the_products_list(db, signed):
    from app.services.dealer_kit.tag_data_service import product_tag_data, staff_viewer

    host = seed.product(db, "ZZACC")
    drainer = _accessory(db, _name("DRAINER"), "390x300x140, Depth: 160mm")
    board = _accessory(db, _name("BOARD"))
    _link_product(db, host, [drainer, board])
    data = product_tag_data(db, host, staff_viewer())
    assert data["accessories"] == [
        {"id": drainer.id, "name": drainer.name, "spec": "390x300x140, Depth: 160mm", "image": None},
        {"id": board.id, "name": board.name, "spec": None, "image": None},
    ]


def test_a3_a_combo_line_shows_the_combos_list_never_the_products(db, signed):
    host = seed.product(db, "ZZACC")
    cb = seed.combo(db, host, "ZZT 1 tap")
    drainer, pullout, other = (_accessory(db, _name(n)) for n in ("DRAINER", "PULLOUT", "OTHER"))
    _link_combo(db, cb, [drainer, pullout])
    _link_product(db, host, [other])
    request = seed.submit_one(db, host, cb, [])
    db.flush()
    (row,) = seed.rows(db, request)
    assert [item["name"] for item in row["accessories"]] == [drainer.name, pullout.name]
    assert row["included_accessories"] == f"{drainer.name}, {pullout.name}"
    assert [item["name"] for item in row["combo"]["accessories"]] == [drainer.name, pullout.name]
    assert row["combo"]["free_items"] == f"{drainer.name}, {pullout.name}"


def test_a3_a_combo_with_no_list_does_not_inherit_the_products(db, signed):
    host = seed.product(db, "ZZACC")
    cb = seed.combo(db, host, "ZZT 1 tap")
    _link_product(db, host, [_accessory(db, _name("HOSTS"))])
    request = seed.submit_one(db, host, cb, [])
    db.flush()
    (row,) = seed.rows(db, request)
    assert row["accessories"] == []
    assert row["included_accessories"] == ""


def test_a3_an_ala_carte_line_shows_the_products_list(db, signed):
    host = seed.product(db, "ZZACC")
    board = _accessory(db, _name("BOARD"))
    _link_product(db, host, [board])
    request = seed.submit_one(db, host, None, [])
    db.flush()
    (row,) = seed.rows(db, request)
    assert [item["name"] for item in row["accessories"]] == [board.name]
    assert row["included_accessories"] == board.name


def test_a3_old_free_text_is_never_read(db, signed):
    host = seed.product(db, "ZZACC")
    cb = seed.combo(db, host, "ZZT 1 tap", free_items="Old tap, waste")
    request = seed.submit_one(db, host, cb, [], included_accessories="Old line text")
    db.flush()
    (row,) = seed.rows(db, request)
    assert row["included_accessories"] == ""
    assert row["accessories"] == []


def test_a3_a_picture_travels_signed(db, signed, storage):
    from app.services.accessory_service import AccessoryService
    from app.services.dealer_kit.tag_data_service import product_tag_data, staff_viewer

    host = seed.product(db, "ZZACC")
    item = _accessory(db, _name("PICTURED"))
    AccessoryService(db).upload_image(
        item.id, content=_jpg_bytes(), filename="drainer.jpg", content_type="image/jpeg", user_id=None
    )
    _link_product(db, host, [item])
    (entry,) = product_tag_data(db, host, staff_viewer())["accessories"]
    assert entry["image"]["attachment_id"] == item.image_attachment_id
    assert entry["image"]["url"].startswith("https://")


# --------------------------------------------------------------------------- A9 pins


def test_a9_a_pinned_row_keeps_its_list_until_re_pinned(db, signed):
    from app.services.dealer_kit import tag_data_service

    host = seed.product(db, "ZZACC")
    cb = seed.combo(db, host, "ZZT 1 tap")
    drainer = _accessory(db, _name("DRAINER"))
    _link_combo(db, cb, [drainer])
    request = seed.submit_one(db, host, cb, [])
    db.flush()
    live = tag_data_service.resolve_tags_live(db, request)[0]
    pinned = tag_data_service.pin_payload(live)

    drainer.name = _name("RENAMED")
    db.flush()
    line = request.lines[0]
    tag = line.tags[0]
    row = tag_data_service._row_from_pin(db, line, tag, pinned, "1a")
    assert [item["name"] for item in row["accessories"]] == [live["accessories"][0]["name"]]
    assert row["included_accessories"] == live["accessories"][0]["name"]


def test_a9_a_row_pinned_before_this_lane_reads_no_list_and_keeps_its_text(db, signed):
    from app.services.dealer_kit import tag_data_service

    host = seed.product(db, "ZZACC")
    cb = seed.combo(db, host, "ZZT 1 tap")
    request = seed.submit_one(db, host, cb, [])
    db.flush()
    live = tag_data_service.resolve_tags_live(db, request)[0]
    pinned = tag_data_service.pin_payload(live)
    pinned.pop("accessories")
    pinned["included_accessories"] = "Old pinned text"
    pinned["combo"] = {**(pinned.get("combo") or {}), "free_items": "Old pinned text"}
    pinned["combo"].pop("accessories", None)
    line = request.lines[0]
    row = tag_data_service._row_from_pin(db, line, line.tags[0], pinned, "1a")
    assert row["accessories"] == []
    assert row["included_accessories"] == "Old pinned text"


# --------------------------------------------------------------------------- data-change gate


def test_a9_the_hash_ignores_re_signed_picture_links(db, signed):
    from app.services.dealer_kit import tag_data_service

    host = seed.product(db, "ZZACC")
    cb = seed.combo(db, host, "ZZT 1 tap")
    item = _accessory(db, _name("DRAINER"))
    _link_combo(db, cb, [item])
    request = seed.submit_one(db, host, cb, [])
    db.flush()
    row = tag_data_service.resolve_tags_live(db, request)[0]
    moved = {
        **row,
        "accessories": [{**a, "image": {"attachment_id": "att", "url": "https://x/1"}} for a in row["accessories"]],
        "combo": {
            **row["combo"],
            "accessories": [{**a, "image": {"attachment_id": "att", "url": "https://x/1"}} for a in row["accessories"]],
        },
    }
    again = {
        **moved,
        "accessories": [{**a, "image": {"attachment_id": "att", "url": "https://x/2"}} for a in row["accessories"]],
        "combo": {
            **moved["combo"],
            "accessories": [{**a, "image": {"attachment_id": "att", "url": "https://x/2"}} for a in row["accessories"]],
        },
    }
    assert tag_data_service.data_hash(moved) == tag_data_service.data_hash(again)


def test_a9_an_ala_carte_list_change_moves_the_hash_and_names_the_change(db, signed):
    from app.services.dealer_kit import tag_data_service

    host = seed.product(db, "ZZACC")
    board = _accessory(db, _name("BOARD"))
    _link_product(db, host, [board])
    request = seed.submit_one(db, host, None, [])
    db.flush()
    pinned = tag_data_service.pin_payload(tag_data_service.resolve_tags_live(db, request)[0])

    db.query(ProductAccessory).filter(ProductAccessory.product_id == host.id).delete()
    db.flush()
    live = tag_data_service.resolve_tags_live(db, request)[0]
    assert tag_data_service.data_hash(live) != tag_data_service.data_hash(pinned)
    line = request.lines[0]
    changes = tag_data_service.diff_pin_against_live(db, line, pinned, live, None)
    assert any(change["field"] == "accessories" for change in changes), changes


def test_a9_a_row_with_no_list_hashes_as_before(db, signed):
    from app.services.dealer_kit import tag_data_service

    host = seed.product(db, "ZZACC")
    request = seed.submit_one(db, host, None, [])
    db.flush()
    row = tag_data_service.resolve_tags_live(db, request)[0]
    without_key = {k: v for k, v in row.items() if k != "accessories"}
    assert tag_data_service.data_hash(row) == tag_data_service.data_hash(without_key)
