"""The tag canvas's artwork: the asset library over HTTP, and brand fonts.

Written BEFORE the implementation (S3b slice 3, AC-L.6 / L.7).

Until now ``dealer_kit.asset`` rows were only ever created by the flyer reader.
The tag editor needs the other half - a designer choosing a badge, uploading a
new one, and uploading the brand's own font - so the library grows a list and an
upload endpoint over the SAME service. No second file store: bytes still go
through ``asset_service`` and the storage router, exactly as a flyer banner does.

Fonts are the reason ``kind`` needs a new value rather than a new table. A font
is a file in the library with a name, and both the editor and the print page
load it through ``@font-face`` from a signed URL. What it is NOT is an image, so
the upload validates by extension: a JPEG uploaded as a font would reach the
print page as a broken ``@font-face`` and silently fall back to a system font on
a tag somebody prints 500 of.
"""
from __future__ import annotations

import io
import os
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._fake_storage import patch_storage
from tests._pg_fixture import blank_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

_SORENTO = "00000000-0000-0000-0000-000000000001"
_LIBRARIAN_ID = "6e1b9d47-2f83-5c05-b46a-8d3f1c7e9052"
_LIBRARIAN_ROLE = "2b5f8c31-9d47-5a26-8e13-0c7b4f9a6d58"
_OUTSIDER_ID = "7d3a1f68-5c92-5b40-a17e-4f8d2b6c0e35"


def _png_bytes() -> bytes:
    """A real PNG: ``store_thumbnail`` decodes whatever it is handed."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def _seed(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_LIBRARIAN_ROLE,
            slug="zzt_kit_librarian",
            name="ZZT Kit Librarian",
            description="Manages the Dealer Kit library",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(
        User(
            id=_LIBRARIAN_ID,
            email="zzt-kit-librarian@test.com",
            name="Librarian",
            status="ACTIVE",
        )
    )
    db.add(
        User(
            id=_OUTSIDER_ID,
            email="zzt-kit-outsider@test.com",
            name="Outsider",
            status="ACTIVE",
        )
    )
    db.flush()
    db.add(UserRoleAssignment(user_id=_LIBRARIAN_ID, role_id=_LIBRARIAN_ROLE))

    perm_id = str(uuid.uuid4())
    db.add(
        UserPermission(
            id=perm_id,
            slug="dealer_kit.library.manage",
            name="dealer_kit.library.manage",
            description="",
        )
    )
    db.flush()
    db.add(
        UserRolePermission(
            id=str(uuid.uuid4()), role_id=_LIBRARIAN_ROLE, permission_id=perm_id
        )
    )
    db.commit()


@pytest.fixture
def api(monkeypatch):
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    patch_storage(monkeypatch)

    with blank_session() as db:
        _seed(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        _as(_LIBRARIAN_ID)
        yield db, _as

        app.dependency_overrides.clear()


def _upload(client, *, filename, content, kind, name=None, tags=None, mime=None):
    data = {"kind": kind}
    if name:
        data["name"] = name
    if tags:
        data["tags"] = tags
    return client.post(
        "/api/v1/dealer-kit/assets",
        data=data,
        files={"file": (filename, content, mime or "application/octet-stream")},
    )


# ---------------------------------------------------------------------------
# Upload (AC-L.6, AC-L.7)
# ---------------------------------------------------------------------------


def test_a_badge_image_lands_in_the_library(api):
    _db, _as = api

    with TestClient(app) as client:
        res = _upload(
            client,
            filename="zzt-badge.png",
            content=_png_bytes(),
            kind="badge",
            name="ZZT Free Gift",
            tags="badge,promo",
            mime="image/png",
        )

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["name"] == "ZZT Free Gift"
    assert body["kind"] == "badge"
    assert body["tags"] == ["badge", "promo"]
    assert body["url"].startswith("https://")


def test_a_woff2_is_accepted_as_a_font(api):
    _db, _as = api

    with TestClient(app) as client:
        res = _upload(
            client,
            filename="ZZTBrand.woff2",
            content=b"wOF2 not really a font, but the right extension",
            kind="font",
            name="ZZT Brand",
        )

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "font"
    assert body["name"] == "ZZT Brand"
    assert body["url"].startswith("https://")


def test_a_jpeg_uploaded_as_a_font_is_refused(api):
    _db, _as = api

    with TestClient(app) as client:
        res = _upload(
            client,
            filename="not-a-font.jpg",
            content=_png_bytes(),
            kind="font",
            mime="image/jpeg",
        )

    assert res.status_code == 422, res.text
    assert "woff2" in res.text


def test_a_font_uploaded_as_a_badge_is_refused(api):
    _db, _as = api

    with TestClient(app) as client:
        res = _upload(
            client,
            filename="ZZTBrand.woff2",
            content=b"wOF2",
            kind="badge",
        )

    assert res.status_code == 422, res.text


def test_an_unknown_kind_is_refused(api):
    _db, _as = api

    with TestClient(app) as client:
        res = _upload(
            client,
            filename="zzt.png",
            content=_png_bytes(),
            kind="wallpaper",
            mime="image/png",
        )

    assert res.status_code == 422, res.text


def test_upload_needs_the_library_permission(api):
    _db, _as = api
    _as(_OUTSIDER_ID)

    with TestClient(app) as client:
        res = _upload(
            client,
            filename="zzt.png",
            content=_png_bytes(),
            kind="badge",
            mime="image/png",
        )

    assert res.status_code == 403, res.text


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_the_list_filters_by_kind_and_tag(api):
    _db, _as = api

    with TestClient(app) as client:
        _upload(
            client,
            filename="zzt-badge.png",
            content=_png_bytes(),
            kind="badge",
            name="ZZT Badge",
            tags="badge",
            mime="image/png",
        )
        _upload(
            client,
            filename="zzt-icon.png",
            content=_png_bytes(),
            kind="icon",
            name="ZZT Icon",
            tags="icon",
            mime="image/png",
        )
        _upload(
            client,
            filename="ZZTBrand.woff2",
            content=b"wOF2",
            kind="font",
            name="ZZT Brand",
        )

        everything = client.get("/api/v1/dealer-kit/assets").json()
        badges = client.get(
            "/api/v1/dealer-kit/assets", params={"kind": "badge"}
        ).json()
        tagged = client.get("/api/v1/dealer-kit/assets", params={"tag": "icon"}).json()
        searched = client.get("/api/v1/dealer-kit/assets", params={"q": "Brand"}).json()

    assert len(everything) == 3
    assert [a["name"] for a in badges] == ["ZZT Badge"]
    assert [a["name"] for a in tagged] == ["ZZT Icon"]
    assert [a["name"] for a in searched] == ["ZZT Brand"]


def test_every_listed_field_survives_the_response_model(api):
    _db, _as = api

    with TestClient(app) as client:
        _upload(
            client,
            filename="zzt-badge.png",
            content=_png_bytes(),
            kind="badge",
            name="ZZT Badge",
            tags="badge",
            mime="image/png",
        )
        rows = client.get("/api/v1/dealer-kit/assets").json()

    assert set(rows[0]) == {"id", "name", "kind", "tags", "url", "mime_type"}


# ---------------------------------------------------------------------------
# The print payload (AC-L.7)
# ---------------------------------------------------------------------------


def _tag_sheet_download(db, *, doc) -> str:
    """A tag sheet page, a version holding ``doc``, and an export of it."""
    from app.models.dealer_kit import ExportRequest, Page, PageVersion
    from app.models.download import DownloadStatus, UserDownload

    stem = unique_code("zzttag").lower()
    page = Page(
        name=f"ZZT tags {stem}",
        slug=f"zzt-tags-{stem}",
        kind="tag_sheet",
        company_id=_SORENTO,
    )
    db.add(page)
    db.flush()

    version = PageVersion(page_id=page.id, version=1, doc=doc)
    db.add(version)
    db.flush()

    download = UserDownload(
        user_id=_LIBRARIAN_ID,
        kind="dealer_kit_tag_sheet_pdf",
        source_entity_type="price_tag_request",
        source_entity_id=str(uuid.uuid4()),
        status=DownloadStatus.PENDING.value,
        filename="zzt-tags.pdf",
    )
    db.add(download)
    db.flush()

    db.add(
        ExportRequest(
            download_id=download.id,
            page_id=page.id,
            page_version_id=version.id,
            audience="staff",
            show_invoice_price=False,
            requested_by=_LIBRARIAN_ID,
        )
    )
    db.commit()
    return download.id


def test_the_print_payload_carries_fonts_and_the_assets_the_doc_names(api):
    db, _as = api
    from app.services.dealer_kit.tag_sheet_export_service import (
        resolve_tag_sheet_print_payload,
    )

    with TestClient(app) as client:
        badge = _upload(
            client,
            filename="zzt-badge.png",
            content=_png_bytes(),
            kind="badge",
            name="ZZT Badge",
            mime="image/png",
        ).json()
        unused = _upload(
            client,
            filename="zzt-unused.png",
            content=_png_bytes(),
            kind="decorative",
            name="ZZT Unused",
            mime="image/png",
        ).json()
        font = _upload(
            client,
            filename="ZZTBrand.woff2",
            content=b"wOF2",
            kind="font",
            name="ZZT Brand",
        ).json()

    doc = {
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
                "id": "s1",
                "tags": [
                    {
                        "id": "t1",
                        "template_id": str(uuid.uuid4()),
                        "request_line_id": str(uuid.uuid4()),
                        "x_mm": 5,
                        "y_mm": 5,
                        "width_mm": 95,
                        "height_mm": 130,
                        "layers": [
                            {
                                "id": "l1",
                                "type": "badge",
                                "props": {"kind": "badge", "assetId": badge["id"]},
                            },
                            {
                                "id": "l2",
                                "type": "image",
                                "props": {
                                    "kind": "image",
                                    "source": {
                                        "type": "asset",
                                        "assetId": badge["id"],
                                    },
                                    "fit": "contain",
                                },
                            },
                        ],
                    }
                ],
            }
        ],
    }

    download_id = _tag_sheet_download(db, doc=doc)
    payload = resolve_tag_sheet_print_payload(db, download_id)

    # Only what the document names. An asset nobody placed is not signed.
    assert badge["id"] in payload["assets"]
    assert unused["id"] not in payload["assets"]
    assert payload["assets"][badge["id"]].startswith("https://")

    # Every font the company has, whether or not a layer names it: a text layer
    # carries a family NAME, not an asset id, so the page cannot know which
    # fonts it needs until the browser tries to lay the text out.
    assert [f["family"] for f in payload["fonts"]] == ["ZZT Brand"]
    assert payload["fonts"][0]["url"].startswith("https://")


def test_asset_ids_are_read_off_the_document(api):
    """Both layer shapes, including a document saved before S3b."""
    _db, _as = api
    from app.services.dealer_kit import asset_service

    doc = {
        "sheets": [
            {
                "tags": [
                    {
                        "layers": [
                            {"props": {"kind": "badge", "assetId": "a1"}},
                            {
                                "props": {
                                    "kind": "image",
                                    "source": {"type": "asset", "assetId": "a2"},
                                }
                            },
                            # Legacy: an image layer from before the source
                            # discriminator existed.
                            {"props": {"kind": "image", "assetId": "a3"}},
                            # A product photo is not a library asset.
                            {
                                "props": {
                                    "kind": "image",
                                    "source": {
                                        "type": "product_attachment",
                                        "attachmentId": "att1",
                                    },
                                }
                            },
                        ]
                    }
                ]
            }
        ]
    }

    assert asset_service.tag_sheet_asset_ids(doc) == {"a1", "a2", "a3"}
