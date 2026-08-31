"""A badge on a price tag is a thing that names an asset.

Written BEFORE the fix (S3b slice 5).

``asset_service.referenced_asset_ids`` decides whether a piece of artwork is
safe to destroy, and it knew about exactly two namers: a ``page_version.doc``
binding an asset as a section BACKGROUND, and a ``flyer_reading.reading_json``
claiming it as a page banner. S3b added two more and told it about neither:

* a ``tag_template.doc`` - the eight seeded starter templates are almost
  nothing BUT badge layers, so every badge asset the seed uploads is named
  only from there;
* a ``page_version.doc`` holding a TAG SHEET rather than sections, which is a
  different shape entirely (``sheets -> tags -> layers``) and so slipped past
  the background containment test.

The failure mode is the bad direction. The guard answers "nothing references
this", the caller deletes the row and purges the bytes, and the next person to
open the WC template gets a tag with no warranty badges and no way to find out
why. So this file asserts the guard SEES both, in both layer shapes -
``props.source.assetId`` (an image layer) and ``props.assetId`` (a badge layer,
and an image layer saved before S3b).

Postgres only, on a blank scratch schema, storage faked in-process. Every row
is ZZT-prefixed.
"""
from __future__ import annotations

import io
import uuid

from PIL import Image

from app.models.dealer_kit import Asset, Page, PageVersion, TagTemplate
from app.services.dealer_kit import asset_service

from tests._fake_storage import patch_storage
from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"


def _png_bytes() -> bytes:
    """A real PNG - ``store_thumbnail`` decodes what it is given."""
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (68, 82, 53)).save(buffer, format="PNG")
    return buffer.getvalue()


def _asset(db) -> Asset:
    asset = asset_service.create_from_bytes(
        db,
        content=_png_bytes(),
        name=unique_code("ZZT badge"),
        mime="image/png",
        kind="badge",
        tags=["badge"],
    )
    db.flush()
    return asset


def _badge_layer(asset_id: str) -> dict:
    """What "Add badge" drops: the asset id sits directly on the props."""
    return {
        "id": str(uuid.uuid4()),
        "type": "badge",
        "x_mm": 4,
        "y_mm": 4,
        "width_mm": 12,
        "height_mm": 12,
        "rotation_deg": 0,
        "z_index": 1,
        "locked": False,
        "visible": True,
        "slot_binding": None,
        "text_override": None,
        "props": {"kind": "badge", "assetId": asset_id},
    }


def _image_layer(asset_id: str) -> dict:
    """An image layer pointing at the library: the id sits under ``source``."""
    return {
        "id": str(uuid.uuid4()),
        "type": "image",
        "x_mm": 20,
        "y_mm": 4,
        "width_mm": 30,
        "height_mm": 30,
        "rotation_deg": 0,
        "z_index": 2,
        "locked": False,
        "visible": True,
        "slot_binding": None,
        "text_override": None,
        "props": {
            "kind": "image",
            "source": {"type": "asset", "assetId": asset_id},
            "fit": "contain",
        },
    }


def _template(db, layers: list[dict]) -> TagTemplate:
    template = TagTemplate(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT template"),
        family="wc",
        doc={"layers": layers, "width_mm": 131.6, "height_mm": 92.1},
        print_size={"width_mm": 131.6, "height_mm": 92.1},
        company_id=SORENTO,
    )
    db.add(template)
    db.flush()
    return template


def _tag_sheet_version(db, layers: list[dict]) -> PageVersion:
    page = Page(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT sheet"),
        slug=unique_code("zzt-sheet").lower(),
        kind="tag_sheet",
        company_id=SORENTO,
    )
    db.add(page)
    db.flush()

    version = PageVersion(
        id=str(uuid.uuid4()),
        page_id=page.id,
        version=1,
        doc={
            "kind": "tag_sheet",
            "imposition": {
                "preset": "a4_3up",
                "page_width_mm": 210,
                "page_height_mm": 297,
                "bleed_mm": 3,
                "gap_mm": 2,
            },
            "sheets": [
                {
                    "id": str(uuid.uuid4()),
                    "tags": [
                        {
                            "id": str(uuid.uuid4()),
                            "template_id": str(uuid.uuid4()),
                            "request_line_id": str(uuid.uuid4()),
                            "x_mm": 0,
                            "y_mm": 0,
                            "width_mm": 125.9,
                            "height_mm": 88.6,
                            "layers": layers,
                        }
                    ],
                }
            ],
        },
    )
    db.add(version)
    db.flush()
    return version


# ---------------------------------------------------------------------------
# Tag templates
# ---------------------------------------------------------------------------


def test_a_badge_layer_in_a_tag_template_keeps_its_asset_alive(monkeypatch):
    with blank_session() as db:
        patch_storage(monkeypatch)
        asset = _asset(db)
        _template(db, [_badge_layer(asset.id)])

        assert asset_service.referenced_asset_ids(db, [asset.id]) == {asset.id}


def test_an_image_layer_in_a_tag_template_keeps_its_asset_alive(monkeypatch):
    with blank_session() as db:
        patch_storage(monkeypatch)
        asset = _asset(db)
        _template(db, [_image_layer(asset.id)])

        assert asset_service.referenced_asset_ids(db, [asset.id]) == {asset.id}


def test_a_template_naming_a_different_asset_does_not_protect_this_one(monkeypatch):
    """The guard has to stay a guard, not become "never delete anything"."""
    with blank_session() as db:
        patch_storage(monkeypatch)
        wanted = _asset(db)
        other = _asset(db)
        _template(db, [_badge_layer(other.id)])

        assert asset_service.referenced_asset_ids(db, [wanted.id]) == set()


def test_an_asset_nothing_names_is_deleted_with_its_bytes(monkeypatch):
    with blank_session() as db:
        storage = patch_storage(monkeypatch)
        asset = _asset(db)
        asset_id = asset.id

        objects = asset_service.delete_unreferenced(db, [asset_id])
        db.flush()

        assert objects, "the bytes should be handed back for purging"
        assert db.query(Asset).filter(Asset.id == asset_id).first() is None

        asset_service.purge_objects(objects)
        assert storage.objects == {}


def test_an_asset_a_template_names_is_not_deleted(monkeypatch):
    """The whole point: the seeded badges survive a delete sweep."""
    with blank_session() as db:
        patch_storage(monkeypatch)
        asset = _asset(db)
        _template(db, [_badge_layer(asset.id)])

        assert asset_service.delete_unreferenced(db, [asset.id]) == []
        assert db.query(Asset).filter(Asset.id == asset.id).first() is not None


# ---------------------------------------------------------------------------
# Tag sheets (page_version.doc, but nothing like a sectioned page)
# ---------------------------------------------------------------------------


def test_a_badge_on_a_placed_tag_keeps_its_asset_alive(monkeypatch):
    with blank_session() as db:
        patch_storage(monkeypatch)
        asset = _asset(db)
        _tag_sheet_version(db, [_badge_layer(asset.id)])

        assert asset_service.referenced_asset_ids(db, [asset.id]) == {asset.id}


def test_an_image_on_a_placed_tag_keeps_its_asset_alive(monkeypatch):
    with blank_session() as db:
        patch_storage(monkeypatch)
        asset = _asset(db)
        _tag_sheet_version(db, [_image_layer(asset.id)])

        assert asset_service.referenced_asset_ids(db, [asset.id]) == {asset.id}
