"""Tag designer gaps (PRICETAG-DESIGNER-GAPS items 1 and 4).

Item 1: an image layer's `flipX` / `flipY` are part of the document contract
(`TagTemplateDocModel`) and round-trip through the CRUD route.
Item 4: a template's name, family and print size can be edited after create
through the existing PUT, without touching its draft layers, its versions or
its live pointer; an empty name is refused.

Auth-override pattern from test_dealer_kit_tag_doc_stretch_margin.py.
"""
from __future__ import annotations

import uuid

import pydantic
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.schemas.price_tag import TagTemplateDocModel
from tests._pg_fixture import blank_session, unique_code

_SORENTO = "00000000-0000-0000-0000-000000000001"

_EDITOR_ID = "6a2b3c4d-5e6f-5a1b-8c2d-3e4f5a6b7c91"
_EDITOR_ROLE = "7b3c4d5e-6f7a-5b2c-9d3e-4f5a6b7c8da2"


def _seed_roles(db: Session) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    slugs = ("dealer_kit.tag_templates.view", "dealer_kit.tag_templates.manage")
    perm_ids: dict[str, str] = {}
    for slug in slugs:
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        perm_ids[slug] = perm_id
    db.flush()

    db.add(
        UserRole(
            id=_EDITOR_ROLE, slug="zzt_gaps_editor", name="zzt_gaps_editor",
            description="", is_protected=False, is_default=False,
        )
    )
    db.add(User(id=_EDITOR_ID, email="zzt-gaps-editor@test.com", name="Editor", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_EDITOR_ID, role_id=_EDITOR_ROLE))
    for slug in slugs:
        db.add(
            UserRolePermission(
                id=str(uuid.uuid4()), role_id=_EDITOR_ROLE, permission_id=perm_ids[slug]
            )
        )
    db.commit()


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        principal = {"id": _EDITOR_ID, "email": f"{_EDITOR_ID}@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db

        app.dependency_overrides.clear()



BASE = "/api/v1/dealer-kit/tag-templates"


def _image_doc(**image_overrides) -> dict:
    return {
        "layers": [
            {
                "id": "tap",
                "type": "image",
                "x_mm": 5,
                "y_mm": 5,
                "width_mm": 30,
                "height_mm": 30,
                "z_index": 1,
                "props": {
                    "kind": "image",
                    "source": {"type": "asset", "assetId": "a1"},
                    "fit": "contain",
                    **image_overrides,
                },
            }
        ],
        "width_mm": 85,
        "height_mm": 130,
    }


def _create(client: TestClient, doc: dict | None = None) -> dict:
    created = client.post(
        BASE,
        json={
            "name": unique_code("Tmpl"),
            "family": "sink_combo",
            "doc": doc or _image_doc(),
            "print_size": {"width_mm": 85, "height_mm": 130},
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


# ---------------------------------------------------------------------------
# Item 1: image flip
# ---------------------------------------------------------------------------


def test_the_document_schema_accepts_an_image_flip():
    TagTemplateDocModel.model_validate(_image_doc(flipX=True, flipY=False))
    TagTemplateDocModel.model_validate(_image_doc(flipY=True))


def test_the_document_schema_still_accepts_an_image_with_no_flip():
    TagTemplateDocModel.model_validate(_image_doc())


def test_the_document_schema_refuses_a_flip_that_is_not_a_yes_no():
    with pytest.raises(pydantic.ValidationError):
        TagTemplateDocModel.model_validate(_image_doc(flipX={"angle": 90}))


def test_a_flipped_image_saves_and_reads_back_unchanged(api):
    with TestClient(app) as client:
        template = _create(client, _image_doc(flipX=True))
        fetched = client.get(f"{BASE}/{template['id']}")

    assert fetched.status_code == 200, fetched.text
    props = fetched.json()["doc"]["layers"][0]["props"]
    assert props["flipX"] is True
    TagTemplateDocModel.model_validate(fetched.json()["doc"])


# ---------------------------------------------------------------------------
# Item 4: edit template settings after create
# ---------------------------------------------------------------------------


def test_renaming_and_changing_family_keeps_layers_and_size(api):
    with TestClient(app) as client:
        template = _create(client)
        new_name = unique_code("Renamed")
        updated = client.put(
            f"{BASE}/{template['id']}",
            json={"name": new_name, "family": "art_basin"},
        )

    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["name"] == new_name
    assert body["family"] == "art_basin"
    assert body["doc"] == template["doc"]
    assert body["print_size"] == template["print_size"]


def test_settings_edit_keeps_the_live_version_and_its_number(api):
    with TestClient(app) as client:
        template = _create(client)
        published = client.post(f"{BASE}/{template['id']}/publish", json={})
        assert published.status_code == 200, published.text
        assert published.json()["published_version_no"] == 1

        updated = client.put(f"{BASE}/{template['id']}", json={"name": unique_code("Live")})
        versions = client.get(f"{BASE}/{template['id']}/versions")

    assert updated.status_code == 200, updated.text
    assert updated.json()["published_version_id"] == published.json()["published_version_id"]
    assert updated.json()["published_version_no"] == 1
    assert versions.status_code == 200
    assert len(versions.json()) == 1


def test_resizing_the_draft_leaves_the_live_version_size_alone(api):
    with TestClient(app) as client:
        template = _create(client)
        client.post(f"{BASE}/{template['id']}/publish", json={})
        doc = {**template["doc"], "width_mm": 100, "height_mm": 70}
        updated = client.put(
            f"{BASE}/{template['id']}",
            json={"doc": doc, "print_size": {"width_mm": 100, "height_mm": 70}},
        )
        live = client.get(BASE, params={"published": 1})

    assert updated.status_code == 200, updated.text
    assert updated.json()["print_size"] == {"width_mm": 100, "height_mm": 70}
    assert updated.json()["doc"]["layers"] == template["doc"]["layers"]
    row = next(t for t in live.json() if t["id"] == template["id"])
    assert row["print_size"] == {"width_mm": 85, "height_mm": 130}


@pytest.mark.parametrize("name", ["", "   "])
def test_a_blank_name_is_refused(api, name):
    with TestClient(app) as client:
        template = _create(client)
        updated = client.put(f"{BASE}/{template['id']}", json={"name": name})
        fetched = client.get(f"{BASE}/{template['id']}")

    assert updated.status_code == 422, updated.text
    assert fetched.json()["name"] == template["name"]


def test_a_blank_family_is_refused(api):
    with TestClient(app) as client:
        template = _create(client)
        updated = client.put(f"{BASE}/{template['id']}", json={"family": ""})

    assert updated.status_code == 422, updated.text
