"""PRICETAG-DESIGNER-FEEDBACK B2, AC-3.1 to AC-3.3: an accessory photo per main product list row.

UAC: documentation/plans/dealer-kit/pricetag-designer-feedback-b-acceptance-criteria.md AC-3.

- AC-3.1 `product_accessories.photo_attachment_id`: nullable, FK attachments.id, ON DELETE SET NULL.
- AC-3.2 `PUT /api/v1/master-data/products/{product_id}/accessories` takes `photo_attachment_id` on
  both kinds of row (null clears it); the list GET returns it in the row's `entry`. An attachment
  the caller cannot see (another company's, or none at all) is a 404.
- AC-3.3 the tag payload prints that photo as `image` and `images[0]` for both kinds of row, ahead
  of the row's `image_id` and the product's lead photo; cleared, it falls back as today.

Written test-FIRST (Postgres, blank schema, every row seeded here).
"""
from __future__ import annotations

import uuid

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.company_scope import register_company_scope_listeners

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests._pg_fixture import blank_session
from tests.test_accessories import (  # noqa: F401
    EDIT,
    PRODUCT_LIST,
    VIEW,
    _accessory,
    _caller,
    _clear_overrides,
    _jpg_bytes,
    _name,
    storage,
)
from tests.test_product_combos import MOCHA, _mocha

IMAGES = "/api/v1/master-data/accessories/{accessory_id}/images"
MISSING = "<key missing>"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture()
def signed(monkeypatch):
    """Every signing path answers a stable URL named after the stored file."""

    def sign(path, **_kwargs):
        return f"https://signed.example.test/{str(path).rsplit('/', 1)[-1]}"

    monkeypatch.setattr("app.services.dealer_kit.product_images.resolve_signed_url", sign)
    monkeypatch.setattr("app.services.accessory_service.resolve_signed_url", sign)
    r9.block_respond(monkeypatch)


def _picture(client, accessory_id, n=0):
    response = client.post(
        IMAGES.format(accessory_id=accessory_id),
        files={"file": (f"p{n}.jpg", _jpg_bytes() + bytes([n]), "image/jpeg")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _attachment(db, *, company_id=seed.SORENTO):
    """A bare image attachment (what a kit asset or an upload resolves to)."""
    from app.models.resources import Attachment

    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename="zzt-photo.jpg",
        stored_filename="zzt-photo.jpg",
        file_path=f"https://cdn.example.test/zzt/{uuid.uuid4().hex}.jpg",
        mime_type="image/jpeg",
        storage_provider="s3",
        company_id=company_id,
        is_deleted=False,
    )
    db.add(row)
    db.flush()
    return row


def _put(client, host, *entries):
    return client.put(PRODUCT_LIST.format(product_id=host.id), json={"items": list(entries)})


def _photo_of(row):
    return (row.get("entry") or {}).get("photo_attachment_id", MISSING)


def _payload(db, host):
    from app.services.accessory_service import product_tag_accessories

    return product_tag_accessories(db, host.id)


# --------------------------------------------------------------------------- AC-3.1


def test_ac31_the_column_is_a_nullable_fk_to_attachments_set_null():
    from app.models.accessory import ProductAccessory

    columns = ProductAccessory.__table__.c
    assert "photo_attachment_id" in columns, "product_accessories.photo_attachment_id"
    column = columns["photo_attachment_id"]
    assert column.nullable is True
    (fk,) = list(column.foreign_keys)
    assert fk.target_fullname.endswith("attachments.id")
    assert (fk.ondelete or "").upper() == "SET NULL"


def test_ac31_a_migration_adds_the_column():
    from pathlib import Path

    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    hits = [p.name for p in versions.glob("*.py") if "photo_attachment_id" in p.read_text(encoding="utf-8")]
    assert hits, "an alembic revision adds product_accessories.photo_attachment_id"


# --------------------------------------------------------------------------- AC-3.2


def test_ac32_round_trip_on_both_kinds_of_row_and_clear(db, monkeypatch, storage, signed):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPHO")
    item = _accessory(db, _name("COLANDER"))
    other = seed.product(db, "ZZPHI")
    asset = r9.seed_asset(db)
    shot = r9.seed_product_photo(db, other, is_primary=False)

    put = _put(
        client,
        host,
        {"accessory_id": item.id, "photo_attachment_id": asset.attachment_id},
        {"product_id": other.id, "photo_attachment_id": shot.id},
    )
    assert put.status_code == 200, put.text
    assert [_photo_of(row) for row in put.json()["data"]] == [asset.attachment_id, shot.id]

    got = client.get(PRODUCT_LIST.format(product_id=host.id))
    assert got.status_code == 200, got.text
    assert [_photo_of(row) for row in got.json()["data"]] == [asset.attachment_id, shot.id]

    cleared = _put(
        client,
        host,
        {"accessory_id": item.id, "photo_attachment_id": None},
        {"product_id": other.id},
    )
    assert cleared.status_code == 200, cleared.text
    again = client.get(PRODUCT_LIST.format(product_id=host.id)).json()["data"]
    assert [_photo_of(row) for row in again] == [None, None]


@pytest.mark.parametrize("kind", ["accessory", "product"])
def test_ac32_another_companys_attachment_is_404(db, monkeypatch, storage, signed, kind):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    _mocha(db)
    theirs = _attachment(db, company_id=MOCHA)
    host = seed.product(db, "ZZPHO")
    row = (
        {"accessory_id": _accessory(db, _name("HIDDEN")).id}
        if kind == "accessory"
        else {"product_id": seed.product(db, "ZZPHI").id}
    )
    response = _put(client, host, {**row, "photo_attachment_id": theirs.id})
    assert response.status_code == 404, response.text
    assert client.get(PRODUCT_LIST.format(product_id=host.id)).json()["data"] == [], "nothing saved"


def test_ac32_an_unknown_attachment_is_404(db, monkeypatch, storage, signed):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPHO")
    item = _accessory(db, _name("GHOST"))
    response = _put(client, host, {"accessory_id": item.id, "photo_attachment_id": str(uuid.uuid4())})
    assert response.status_code == 404, response.text


def test_ac31_deleting_the_attachment_clears_the_row(db, monkeypatch, storage, signed):
    from app.models.accessory import ProductAccessory
    from app.models.resources import Attachment

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPHO")
    item = _accessory(db, _name("GONE"))
    photo = _attachment(db)
    assert _put(client, host, {"accessory_id": item.id, "photo_attachment_id": photo.id}).status_code == 200
    db.expire_all()
    db.query(Attachment).filter(Attachment.id == photo.id).delete(synchronize_session=False)
    db.flush()
    db.expire_all()
    link = db.query(ProductAccessory).filter(ProductAccessory.product_id == host.id).one()
    assert getattr(link, "photo_attachment_id", MISSING) is None


# --------------------------------------------------------------------------- AC-3.3


def test_ac33_a_library_row_prints_the_override_ahead_of_its_chosen_picture(db, monkeypatch, storage, signed):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPHO")
    item = _accessory(db, _name("DRAINER"))
    _picture(client, item.id, 1)
    grey = _picture(client, item.id, 2)
    photo = r9.seed_asset(db)

    assert _put(
        client, host, {"accessory_id": item.id, "image_id": grey["id"], "photo_attachment_id": photo.attachment_id}
    ).status_code == 200
    (entry,) = _payload(db, host)
    assert entry["image"] is not None
    assert entry["image"]["attachment_id"] == photo.attachment_id
    assert entry["image"]["url"].startswith("https://")
    assert entry["images"][0]["attachment_id"] == photo.attachment_id
    # The designer reads this to offer "Reset to product photo" (AC-3.4).
    assert entry.get("photo_attachment_id", MISSING) == photo.attachment_id

    # Cleared: exactly today's rule (the row's chosen picture leads `image`).
    assert _put(client, host, {"accessory_id": item.id, "image_id": grey["id"]}).status_code == 200
    (entry,) = _payload(db, host)
    assert entry["image"]["attachment_id"] == grey["attachment_id"]
    assert photo.attachment_id not in [image["attachment_id"] for image in entry["images"]]
    assert entry.get("photo_attachment_id", MISSING) is None


def test_ac33_a_product_row_prints_the_override_ahead_of_its_lead_photo(db, monkeypatch, storage, signed):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPHO")
    other = seed.product(db, "ZZPHI")
    lead = r9.seed_product_photo(db, other, is_primary=True)
    side = r9.seed_product_photo(db, other, is_primary=False)

    assert _put(client, host, {"product_id": other.id, "photo_attachment_id": side.id}).status_code == 200
    (entry,) = _payload(db, host)
    assert entry["kind"] == "product"
    assert entry["image"] is not None and entry["image"]["attachment_id"] == side.id
    assert entry["images"][0]["attachment_id"] == side.id

    assert _put(client, host, {"product_id": other.id}).status_code == 200
    (entry,) = _payload(db, host)
    assert entry["image"]["attachment_id"] == lead.id, "cleared: the product's lead photo, as today"
    assert entry["images"][0]["attachment_id"] == lead.id


def test_ac33_the_override_reaches_product_tag_data(db, monkeypatch, storage, signed):
    """The tag data the designer and the print page read, not just the list helper."""
    from app.services.dealer_kit.tag_data_service import product_tag_data, staff_viewer

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = seed.product(db, "ZZPHO")
    item = _accessory(db, _name("BOARD"))
    photo = r9.seed_asset(db)
    assert _put(client, host, {"accessory_id": item.id, "photo_attachment_id": photo.attachment_id}).status_code == 200
    data = product_tag_data(db, host, staff_viewer())
    (entry,) = data["accessories"]
    assert entry["image"] is not None and entry["image"]["attachment_id"] == photo.attachment_id
