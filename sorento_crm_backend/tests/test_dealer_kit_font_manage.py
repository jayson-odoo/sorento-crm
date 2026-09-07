"""Brand font management over HTTP: rename and delete.

Written BEFORE the implementation (PLAN-brand-font-manage.md).

A brand font is a ``dealer_kit.asset`` row with ``kind='font'``, but a text
layer stores the font by NAME (``props.fontFamily``), never by asset id -
``asset_service.referenced_asset_ids`` walks asset IDS, so it has nothing to
say about a font. The guard here is name-based: renaming a font rewrites
every doc that names the old family to the new one, and deleting one is
refused while any doc still names it.

Three documents can name a family: ``tag_template.doc`` (layers all the way
down), ``page_version.doc`` (a tag sheet: ``sheets[].tags[].layers[]``), and
``page.draft_doc`` (the same shape, unsaved).

Postgres only, on a blank scratch schema, with storage faked in-process.
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
_LIBRARIAN_ID = "9d83ad1f-584a-5cb9-ad44-b2bf42a9031a"
_LIBRARIAN_ROLE = "c3c62cdb-16f8-55db-86ba-4b0ce1bf2ea5"
_OUTSIDER_ID = "5efa1eac-18a4-50df-9185-a25bd80eb854"


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
            slug="zzt_font_librarian",
            name="ZZT Font Librarian",
            description="Manages the Dealer Kit library",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(
        User(
            id=_LIBRARIAN_ID,
            email="zzt-font-librarian@test.com",
            name="Librarian",
            status="ACTIVE",
        )
    )
    db.add(
        User(
            id=_OUTSIDER_ID,
            email="zzt-font-outsider@test.com",
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

    storage = patch_storage(monkeypatch)

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
        yield db, storage, _as

        app.dependency_overrides.clear()


def _upload_font(client, *, name: str, content: bytes = b"wOF2") -> dict:
    res = client.post(
        "/api/v1/dealer-kit/assets",
        data={"kind": "font", "name": name},
        files={"file": (f"{name}.woff2", content, "font/woff2")},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _upload_badge(client, *, name: str) -> dict:
    res = client.post(
        "/api/v1/dealer-kit/assets",
        data={"kind": "badge", "name": name},
        files={"file": (f"{name}.png", _png_bytes(), "image/png")},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _text_layer(font_name: str, layer_id: str = "layer-1") -> dict:
    return {
        "id": layer_id,
        "type": "text",
        "x_mm": 2,
        "y_mm": 2,
        "width_mm": 30,
        "height_mm": 8,
        "rotation_deg": 0,
        "z_index": 1,
        "locked": False,
        "visible": True,
        "slot_binding": None,
        "text_override": None,
        "props": {
            "kind": "text",
            "text": "Hello",
            "fontFamily": font_name,
            "fontSize": 12,
            "fontWeight": 400,
            "color": "#000000",
            "align": "left",
            "lineHeight": 1.2,
            "letterSpacing": 0,
        },
    }


def _badge_layer(asset_id: str, layer_id: str = "layer-badge") -> dict:
    return {
        "id": layer_id,
        "type": "badge",
        "x_mm": 2,
        "y_mm": 2,
        "width_mm": 10,
        "height_mm": 10,
        "rotation_deg": 0,
        "z_index": 1,
        "locked": False,
        "visible": True,
        "slot_binding": None,
        "text_override": None,
        "props": {"kind": "badge", "assetId": asset_id},
    }


def _template_doc(*layers: dict) -> dict:
    return {"width_mm": 70, "height_mm": 38, "layers": list(layers)}


def _tag_sheet_doc(*layers: dict) -> dict:
    return {
        "sheets": [
            {"id": "sheet-1", "tags": [{"id": "tag-1", "layers": list(layers)}]}
        ]
    }


def _make_template(db, *, name: str, doc: dict):
    from app.models.dealer_kit import TagTemplate

    template = TagTemplate(
        name=name,
        family=unique_code("family").lower(),
        doc=doc,
        print_size={"width_mm": 70, "height_mm": 38},
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def _make_tag_sheet_page(db, *, name: str, doc: dict, draft: bool = False):
    from app.models.dealer_kit import Page, PageVersion

    page = Page(
        name=name,
        slug=unique_code("tag-sheet").lower(),
        kind="tag_sheet",
    )
    if draft:
        page.draft_doc = doc
    db.add(page)
    db.flush()
    if not draft:
        version = PageVersion(page_id=page.id, version=1, doc=doc)
        db.add(version)
    db.commit()
    db.refresh(page)
    return page


def _make_template_version(db, template, *, doc: dict, version_no: int = 1):
    from app.models.dealer_kit import TagTemplateVersion

    version = TagTemplateVersion(
        template_id=template.id, version_no=version_no, doc=doc
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def _second_company(db) -> str:
    """A throwaway second company, so a rename/delete's own-company scope has
    someone else's identically-named font and template to leave alone."""
    from app.models.company import Company

    company = Company(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Company B"),
        code=f"ZB{uuid.uuid4().hex[:6]}",
    )
    db.add(company)
    db.flush()
    db.commit()
    return company.id


def _make_font_for_company(db, *, company_id: str, name: str) -> str:
    """A font asset created directly under ``company_id``, bypassing the
    request-scoped upload route (which always writes to the fixture's
    ambient company)."""
    from app.models.base import company_scope
    from app.services.dealer_kit import asset_service as svc

    with company_scope(db, frozenset({company_id})):
        asset = svc.create_from_bytes(
            db, content=b"wOF2", name=name, mime="font/woff2", kind=svc.FONT
        )
        db.flush()
    db.commit()
    return asset.id


def _make_template_for_company(db, *, company_id: str, name: str, doc: dict):
    from app.models.base import company_scope
    from app.models.dealer_kit import TagTemplate

    with company_scope(db, frozenset({company_id})):
        template = TagTemplate(
            name=name,
            family=unique_code("family").lower(),
            doc=doc,
            print_size={"width_mm": 70, "height_mm": 38},
        )
        db.add(template)
        db.flush()
    db.commit()
    db.refresh(template)
    return template


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


def test_rename_rewrites_a_template_a_tag_sheet_and_a_draft(api):
    db, _storage, _as = api

    with TestClient(app) as client:
        font = _upload_font(client, name=unique_code("ZZT Old"))
        old_name = font["name"]
        new_name = f"{old_name} Renamed"

        template = _make_template(
            db, name="Standard 70x38", doc=_template_doc(_text_layer(old_name))
        )
        published_sheet = _make_tag_sheet_page(
            db, name="Promo A6", doc=_tag_sheet_doc(_text_layer(old_name))
        )
        draft_sheet = _make_tag_sheet_page(
            db,
            name="Promo Draft",
            doc=_tag_sheet_doc(_text_layer(old_name)),
            draft=True,
        )

        res = client.patch(
            f"/api/v1/dealer-kit/assets/{font['id']}", json={"name": new_name}
        )

    assert res.status_code == 200, res.text
    assert res.json()["name"] == new_name

    db.refresh(template)
    assert template.doc["layers"][0]["props"]["fontFamily"] == new_name

    from app.models.dealer_kit import Page, PageVersion

    version = (
        db.query(PageVersion).filter(PageVersion.page_id == published_sheet.id).one()
    )
    assert (
        version.doc["sheets"][0]["tags"][0]["layers"][0]["props"]["fontFamily"]
        == new_name
    )

    draft = db.query(Page).filter(Page.id == draft_sheet.id).one()
    assert (
        draft.draft_doc["sheets"][0]["tags"][0]["layers"][0]["props"]["fontFamily"]
        == new_name
    )


def test_rename_to_an_existing_font_name_is_refused(api):
    db, _storage, _as = api

    with TestClient(app) as client:
        first = _upload_font(client, name=unique_code("ZZT First"))
        second = _upload_font(client, name=unique_code("ZZT Second"))

        res = client.patch(
            f"/api/v1/dealer-kit/assets/{second['id']}", json={"name": first["name"]}
        )

    assert res.status_code == 409, res.text
    assert res.json()["code"] == "FONT_NAME_TAKEN"

    from app.models.dealer_kit import Asset

    row = db.query(Asset).filter(Asset.id == second["id"]).one()
    assert row.name == second["name"]


def test_rename_a_non_font_asset_only_changes_the_row(api):
    db, _storage, _as = api

    with TestClient(app) as client:
        badge = _upload_badge(client, name=unique_code("ZZT Badge"))
        template = _make_template(
            db, name="Uses Badge", doc=_template_doc(_badge_layer(badge["id"]))
        )

        res = client.patch(
            f"/api/v1/dealer-kit/assets/{badge['id']}", json={"name": "Renamed Badge"}
        )

    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Renamed Badge"

    db.refresh(template)
    # The document holds the ID, not the name - nothing to rewrite (AC-D3/AC-12).
    assert template.doc["layers"][0]["props"]["assetId"] == badge["id"]


def test_rename_rewrites_a_published_template_version_doc(api):
    """Restore copies a version's doc back into the draft (S1 review, 7 Sep
    2026), so a font only an OLD version still names has to track a rename
    too, not just the live `tag_template.doc`."""
    db, _storage, _as = api

    with TestClient(app) as client:
        font = _upload_font(client, name=unique_code("ZZT Old"))
        old_name = font["name"]
        new_name = f"{old_name} Renamed"

        # The live doc does not name it any more; only the published snapshot does.
        template = _make_template(db, name="Standard 70x38", doc=_template_doc())
        version = _make_template_version(
            db, template, doc=_template_doc(_text_layer(old_name))
        )

        res = client.patch(
            f"/api/v1/dealer-kit/assets/{font['id']}", json={"name": new_name}
        )

    assert res.status_code == 200, res.text

    from app.models.dealer_kit import TagTemplateVersion

    db.refresh(version)
    row = (
        db.query(TagTemplateVersion)
        .filter(TagTemplateVersion.id == version.id)
        .one()
    )
    assert row.doc["layers"][0]["props"]["fontFamily"] == new_name


def test_rename_does_not_touch_another_companys_identically_named_font(api):
    """Two companies can each own a font of the same name (S1 review): a
    rename must scope to the ASSET's own company, never every company."""
    db, _storage, _as = api

    shared_name = unique_code("ZZT Shared")
    company_b = _second_company(db)

    with TestClient(app) as client:
        font_a = _upload_font(client, name=shared_name)

    font_b_id = _make_font_for_company(db, company_id=company_b, name=shared_name)
    template_b = _make_template_for_company(
        db,
        company_id=company_b,
        name="Company B Template",
        doc=_template_doc(_text_layer(shared_name)),
    )

    new_name = f"{shared_name} Renamed"
    with TestClient(app) as client:
        res = client.patch(
            f"/api/v1/dealer-kit/assets/{font_a['id']}", json={"name": new_name}
        )
    assert res.status_code == 200, res.text

    from app.models.base import company_scope
    from app.models.dealer_kit import TagTemplate
    from app.models.dealer_kit import Asset as AssetModel

    with company_scope(db, None):
        font_b = db.query(AssetModel).filter(AssetModel.id == font_b_id).one()
        db.refresh(template_b)
        template_b_row = (
            db.query(TagTemplate).filter(TagTemplate.id == template_b.id).one()
        )

    assert font_b.name == shared_name
    assert template_b_row.doc["layers"][0]["props"]["fontFamily"] == shared_name


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_an_unreferenced_font_removes_rows_and_bytes(api):
    db, storage, _as = api

    with TestClient(app) as client:
        font = _upload_font(client, name=unique_code("ZZT Unused"))
        from app.models.dealer_kit import Asset

        asset_row = db.query(Asset).filter(Asset.id == font["id"]).one()
        attachment_id = asset_row.attachment_id

        res = client.delete(f"/api/v1/dealer-kit/assets/{font['id']}")

    assert res.status_code == 204, res.text

    from app.models.dealer_kit import Asset
    from app.models.resources import Attachment

    assert db.query(Asset).filter(Asset.id == font["id"]).first() is None
    assert (
        db.query(Attachment).filter(Attachment.id == attachment_id).first() is None
    )
    assert storage.objects == {}


def test_delete_a_font_used_by_a_template_is_refused(api):
    db, storage, _as = api

    with TestClient(app) as client:
        font = _upload_font(client, name=unique_code("ZZT Used"))
        _make_template(
            db,
            name="Standard 70x38",
            doc=_template_doc(_text_layer(font["name"])),
        )

        res = client.delete(f"/api/v1/dealer-kit/assets/{font['id']}")

    assert res.status_code == 409, res.text
    body = res.json()
    assert body["code"] == "FONT_IN_USE"
    assert "Standard 70x38" in body["message"]

    from app.models.dealer_kit import Asset

    assert db.query(Asset).filter(Asset.id == font["id"]).first() is not None
    assert len(storage.objects) > 0


def test_delete_a_badge_referenced_by_a_template_is_refused(api):
    db, _storage, _as = api

    with TestClient(app) as client:
        badge = _upload_badge(client, name=unique_code("ZZT Badge"))
        _make_template(
            db, name="Uses Badge", doc=_template_doc(_badge_layer(badge["id"]))
        )

        res = client.delete(f"/api/v1/dealer-kit/assets/{badge['id']}")

    assert res.status_code == 409, res.text
    assert res.json()["code"] == "ASSET_IN_USE"


def test_delete_is_refused_when_only_a_version_names_the_font(api):
    """Restore brings an old version's doc straight back into the draft, so a
    font only that version still names is not safe to delete either."""
    db, storage, _as = api

    with TestClient(app) as client:
        font = _upload_font(client, name=unique_code("ZZT Used"))

        template = _make_template(db, name="Standard 70x38", doc=_template_doc())
        _make_template_version(
            db, template, doc=_template_doc(_text_layer(font["name"]))
        )

        res = client.delete(f"/api/v1/dealer-kit/assets/{font['id']}")

    assert res.status_code == 409, res.text
    body = res.json()
    assert body["code"] == "FONT_IN_USE"
    assert "Standard 70x38" in body["message"]

    from app.models.dealer_kit import Asset

    assert db.query(Asset).filter(Asset.id == font["id"]).first() is not None
    assert len(storage.objects) > 0


def test_delete_is_not_blocked_by_another_companys_template(api):
    """The delete guard scopes to the asset's own company the same way the
    rename does - a template in a DIFFERENT company naming the same family
    must not refuse a delete this company is entitled to make (S1 review)."""
    db, _storage, _as = api

    shared_name = unique_code("ZZT Shared")
    company_b = _second_company(db)
    _make_template_for_company(
        db,
        company_id=company_b,
        name="Company B Template",
        doc=_template_doc(_text_layer(shared_name)),
    )

    with TestClient(app) as client:
        font_a = _upload_font(client, name=shared_name)
        res = client.delete(f"/api/v1/dealer-kit/assets/{font_a['id']}")

    assert res.status_code == 204, res.text


# ---------------------------------------------------------------------------
# Guarding
# ---------------------------------------------------------------------------


def test_rename_and_delete_need_the_library_permission(api):
    _db, _storage, _as = api
    _as(_OUTSIDER_ID)

    with TestClient(app) as client:
        font_res = client.post(
            "/api/v1/dealer-kit/assets",
            data={"kind": "font", "name": "irrelevant"},
            files={"file": ("f.woff2", b"wOF2", "font/woff2")},
        )
        # The outsider cannot even upload one, so exercise both routes against
        # an id that plausibly does not resolve for them either way - a 403
        # must win before a 404 would.
        assert font_res.status_code == 403, font_res.text

        fake_id = str(uuid.uuid4())
        rename_res = client.patch(
            f"/api/v1/dealer-kit/assets/{fake_id}", json={"name": "New Name"}
        )
        delete_res = client.delete(f"/api/v1/dealer-kit/assets/{fake_id}")

    assert rename_res.status_code == 403, rename_res.text
    assert delete_res.status_code == 403, delete_res.text
