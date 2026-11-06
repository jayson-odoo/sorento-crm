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
from pathlib import Path

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


def _items(*accessory_ids, products=()) -> dict:
    """A PUT body: accessories by id, then products (`products` as (index, product_id) to place)."""
    items = [{"accessory_id": value} for value in accessory_ids]
    for index, product_id in products:
        items.insert(index, {"product_id": product_id})
    return {"items": items}


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

    put = client.put(url, json=_items(pullout.id, drainer.id))
    assert put.status_code == 200, put.text
    assert [row["id"] for row in put.json()["data"]] == [pullout.id, drainer.id]

    again = client.put(url, json=_items(board.id, pullout.id))
    assert [row["id"] for row in again.json()["data"]] == [board.id, pullout.id]
    assert [row["id"] for row in client.get(url).json()["data"]] == [board.id, pullout.id]

    assert client.put(url, json=_items()).json()["data"] == []


def test_a2_product_list_refuses_duplicates_and_unknown_ids(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZACC")
    item = _accessory(db, _name("ONE"))
    url = PRODUCT_LIST.format(product_id=host.id)
    assert client.put(url, json=_items(item.id, item.id)).status_code == 422
    assert client.put(url, json=_items(str(uuid.uuid4()))).status_code == 404


def test_a2_product_list_needs_edit(db, monkeypatch):
    client = _caller(db, {VIEW}, monkeypatch)
    host = _product(db, "ZZACC")
    assert client.get(PRODUCT_LIST.format(product_id=host.id)).status_code == 200
    put = client.put(PRODUCT_LIST.format(product_id=host.id), json=_items())
    assert put.status_code == 403


def test_a2_combo_list_is_independent_of_the_product_list(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZACC")
    combo = _combo(db, host, "ZZT 1 tap")
    drainer, pullout = _accessory(db, _name("DRAINER")), _accessory(db, _name("PULLOUT"))

    put = client.put(COMBO_LIST.format(combo_id=combo.id), json=_items(drainer.id, pullout.id))
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
        {
            "kind": "accessory", "id": drainer.id, "name": drainer.name,
            "spec": "390x300x140, Depth: 160mm", "image": None, "code": None, "list_price": None,
        },
        {
            "kind": "accessory", "id": board.id, "name": board.name,
            "spec": None, "image": None, "code": None, "list_price": None,
        },
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



# --------------------------------------------------------------------------- product entries
# Owner, 6 Nov ~10:45: a list entry is EITHER a library accessory OR a real catalogue product
# (combo SRTWB7065 with a FREE SRTW5000 popup waste). Product facts come live from the product.


def _waste(db):
    product = seed.product(db, "ZZWASTE", list_price="68.00")
    product.description = "Popup Waste 80mm (w/o Overflow) Brass"
    db.flush()
    return product


def test_p1_a_list_mixes_accessories_and_products_in_order(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZACC")
    waste = _waste(db)
    waste.company_id = host.company_id
    drainer = _accessory(db, _name("DRAINER"))
    url = PRODUCT_LIST.format(product_id=host.id)
    put = client.put(url, json=_items(drainer.id, products=[(0, waste.id)]))
    assert put.status_code == 200, put.text
    first, second = put.json()["data"]
    assert first["kind"] == "product" and first["id"] == waste.id
    assert first["code"] == waste.product_code
    assert first["name"] == "Popup Waste 80mm (w/o Overflow) Brass", "the description, not the code"
    assert float(first["list_price"]) == 68.0
    assert second["kind"] == "accessory" and second["id"] == drainer.id and second["code"] is None


def test_p1_a_product_cannot_list_itself(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZACC")
    put = client.put(PRODUCT_LIST.format(product_id=host.id), json=_items(products=[(0, host.id)]))
    assert put.status_code == 422, put.text


def test_p1_a_combo_part_cannot_also_be_its_free_item(db, monkeypatch):
    from tests.test_product_combos import _part

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZACC")
    tap = _product(db, "ZZTAP")
    combo = _combo(db, host, "ZZT 1 tap")
    _part(db, combo, tap)
    url = COMBO_LIST.format(combo_id=combo.id)
    assert client.put(url, json=_items(products=[(0, tap.id)])).status_code == 422
    assert client.put(url, json=_items(products=[(0, host.id)])).status_code == 422


def test_p1_the_same_product_twice_is_refused(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZACC")
    other = _product(db, "ZZOTHER")
    body = _items(products=[(0, other.id), (1, other.id)])
    assert client.put(PRODUCT_LIST.format(product_id=host.id), json=body).status_code == 422


def test_p1_an_entry_names_exactly_one_thing(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZACC")
    other = _product(db, "ZZOTHER")
    item = _accessory(db, _name("BOTH"))
    body = {"items": [{"accessory_id": item.id, "product_id": other.id}]}
    assert client.put(PRODUCT_LIST.format(product_id=host.id), json=body).status_code == 422
    assert client.put(PRODUCT_LIST.format(product_id=host.id), json={"items": [{}]}).status_code == 422


def test_p2_a_combo_line_prints_a_free_product_live(db, signed):
    host = seed.product(db, "ZZWB")
    cb = seed.combo(db, host, "ZZT basin + tap")
    waste = _waste(db)
    db.add(
        ProductComboAccessory(
            id=str(uuid.uuid4()), combo_id=cb.id, item_product_id=waste.id, sort_order=0
        )
    )
    db.flush()
    request = seed.submit_one(db, host, cb, [])
    db.flush()
    (row,) = seed.rows(db, request)
    (entry,) = row["accessories"]
    assert entry["kind"] == "product"
    assert entry["id"] == waste.id
    assert entry["code"] == waste.product_code
    assert entry["name"] == "Popup Waste 80mm (w/o Overflow) Brass"
    assert float(entry["list_price"]) == 68.0
    assert entry["spec"] is None
    assert row["included_accessories"] == f"{waste.product_code} Popup Waste 80mm (w/o Overflow) Brass"


def test_p2_a_library_entry_carries_kind_accessory(db, signed):
    from app.services.dealer_kit.tag_data_service import product_tag_data, staff_viewer

    host = seed.product(db, "ZZACC")
    board = _accessory(db, _name("BOARD"))
    _link_product(db, host, [board])
    (entry,) = product_tag_data(db, host, staff_viewer())["accessories"]
    assert entry["kind"] == "accessory" and entry["code"] is None and entry["list_price"] is None


# --------------------------------------------------------------------------- deferred delete


def test_a1_delete_is_a_deferred_record_action_on_the_products_edit_permission():
    import app.services.record_actions  # noqa: F401  (registers the actions)
    from app.api.v1.system.pending_actions import _PARK_SCOPED_MODELS
    from app.services.form_action_registry import get_action

    action = get_action("accessory.delete")
    assert action is not None
    assert action.entity_types == ("accessory",)
    assert action.permission == "master_data.products.edit"
    assert _PARK_SCOPED_MODELS["accessory.delete"] is Accessory


def test_a1_the_deferred_delete_removes_an_unused_accessory(db):
    from app.services.record_actions import _delete_accessory

    row = _accessory(db, _name("DEFERRED"))
    _delete_accessory(db, {"entity_id": row.id})
    db.expire_all()
    assert db.query(Accessory).filter(Accessory.id == row.id).first() is None


# --------------------------------------------------------------------------- review fix round 1


def test_s1_deleting_a_product_listed_as_a_free_item_is_a_409_naming_the_holder(db):
    from app.services.error_handler import AppException
    from app.services.product_service import ProductService

    host = seed.product(db, "ZZWB")
    cb = seed.combo(db, host, "ZZT basin + tap")
    waste = _waste(db)
    db.add(ProductComboAccessory(id=str(uuid.uuid4()), combo_id=cb.id, item_product_id=waste.id, sort_order=0))
    db.flush()
    with pytest.raises(AppException) as raised:
        ProductService(db).delete_product(waste.id)
    assert raised.value.status_code == 409
    assert host.product_code in raised.value.message and "ZZT basin + tap" in raised.value.message


def test_s1_deleting_a_product_on_another_products_list_is_a_409(db):
    from app.services.error_handler import AppException
    from app.services.product_service import ProductService

    host = seed.product(db, "ZZACC")
    waste = _waste(db)
    db.add(ProductAccessory(id=str(uuid.uuid4()), product_id=host.id, item_product_id=waste.id, sort_order=0))
    db.flush()
    with pytest.raises(AppException) as raised:
        ProductService(db).delete_product(waste.id)
    assert raised.value.status_code == 409 and host.product_code in raised.value.message


def test_s2_a_free_products_list_price_moving_is_a_reported_change(db, signed):
    from app.services.dealer_kit import tag_data_service

    host = seed.product(db, "ZZACC")
    waste = _waste(db)
    db.add(ProductAccessory(id=str(uuid.uuid4()), product_id=host.id, item_product_id=waste.id, sort_order=0))
    db.flush()
    request = seed.submit_one(db, host, None, [])
    db.flush()
    pinned = tag_data_service.pin_payload(tag_data_service.resolve_tags_live(db, request)[0])
    waste.list_price = 75
    db.flush()
    live = tag_data_service.resolve_tags_live(db, request)[0]
    assert tag_data_service.data_hash(live) != tag_data_service.data_hash(pinned)
    changes = tag_data_service.diff_pin_against_live(db, request.lines[0], pinned, live, None)
    (change,) = [c for c in changes if c["field"] == "accessories"]
    assert "68" in change["old"] and "75" in change["new"]


def test_s3_a_combo_pinned_before_lists_is_not_flagged_for_its_re_spelled_text(db, signed):
    from app.services.dealer_kit import tag_data_service

    host = seed.product(db, "ZZACC")
    cb = seed.combo(db, host, "ZZT 1 tap")
    a, b = _accessory(db, _name("A")), _accessory(db, _name("B"))
    _link_combo(db, cb, [a, b])
    request = seed.submit_one(db, host, cb, [])
    db.flush()
    live = tag_data_service.resolve_tags_live(db, request)[0]
    pinned = tag_data_service.pin_payload(live)
    # As a pre-lane pin looked: old free text with " + ", no lists anywhere.
    pinned.pop("accessories")
    pinned["combo"] = {k: v for k, v in pinned["combo"].items() if k != "accessories"}
    pinned["combo"]["free_items"] = f"{a.name} + {b.name}"
    changes = tag_data_service.diff_pin_against_live(db, request.lines[0], pinned, live, None)
    assert not [c for c in changes if c["field"].startswith("combo:free_items")], changes


def test_sec_the_storage_key_never_carries_the_client_filename(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("KEYED"))
    response = client.post(
        ACCESSORY_IMAGE.format(accessory_id=row.id),
        files={"file": ("..%2F..%2Fother%2Fvictim.jpg", _jpg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    (key,) = storage.objects
    assert key == f"accessory_image/{response.json()['attachment_id']}.jpg"


def test_sec_an_oversized_upload_is_refused(db, monkeypatch, storage):
    from app.services.accessory_service import MAX_IMAGE_BYTES

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("BIG"))
    response = client.post(
        ACCESSORY_IMAGE.format(accessory_id=row.id),
        files={"file": ("big.jpg", b"\xff" * (MAX_IMAGE_BYTES + 10), "image/jpeg")},
    )
    assert response.status_code == 422
    assert storage.objects == {}


def test_sec_write_routes_take_a_signed_in_user_not_an_api_key():
    from app.api.v1.master_data import accessories

    source = Path(accessories.__file__).read_text()
    assert "require_permission_with_api_key(EDIT)" not in source
    assert source.count("require_permission(EDIT)") == 7
