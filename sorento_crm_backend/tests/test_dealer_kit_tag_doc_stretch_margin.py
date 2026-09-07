"""Image `stretch` fit + price badge `margin`/`showCurrency` (PLAN
tag-image-stretch-badge-margin, AC-4/AC-9/AC-16).

The tag-template CRUD route (`create_tag_template`/`update_tag_template`)
stores `doc` as an opaque dict - it does not run it through
`TagTemplateDocModel` at request time (measured: `app/schemas/price_tag.py`,
`TagTemplateCreate.doc: dict`). So a document round-trips through the API
unchanged regardless of shape, and the SCHEMA's own strictness - the same
contract `TagTemplateDocModel` enforces for the eight seeded layouts in
`test_tag_template_seed_docs.py` - is what refuses an unknown `fit`.

Auth-override pattern from test_dealer_kit_tag_template_versions.py.
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
            id=_EDITOR_ROLE, slug="zzt_stretch_editor", name="zzt_stretch_editor",
            description="", is_protected=False, is_default=False,
        )
    )
    db.add(User(id=_EDITOR_ID, email="zzt-stretch-editor@test.com", name="Editor", status="ACTIVE"))
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


def _doc_with_stretch_and_margin(**badge_overrides) -> dict:
    return {
        "layers": [
            {
                "id": "img1",
                "type": "image",
                "x_mm": 0,
                "y_mm": 0,
                "width_mm": 40,
                "height_mm": 60,
                "z_index": 1,
                "props": {"kind": "image", "source": None, "fit": "stretch"},
            },
            {
                "id": "badge1",
                "type": "price_badge",
                "x_mm": 0,
                "y_mm": 60,
                "width_mm": 40,
                "height_mm": 20,
                "z_index": 2,
                "props": {
                    "kind": "price_badge",
                    "variant": "list_only",
                    "fill": "#d32f2f",
                    "textColor": "#ffffff",
                    "cornerRadius": 2,
                    "showNett": True,
                    "margin": {"top": 2, "right": 2, "bottom": 2, "left": 2},
                    "padding": {"top": 1, "right": 1, "bottom": 1, "left": 1},
                    **badge_overrides,
                },
            },
        ],
        "width_mm": 85,
        "height_mm": 130,
    }


# ---------------------------------------------------------------------------
# AC-4 / AC-9: stretch + margin round-trip through the CRUD route unchanged
# ---------------------------------------------------------------------------


def test_a_stretch_fit_and_price_badge_margin_save_and_read_back_unchanged(api):
    with TestClient(app) as client:
        doc = _doc_with_stretch_and_margin()
        created = client.post(
            "/api/v1/dealer-kit/tag-templates",
            json={
                "name": unique_code("Tmpl"),
                "family": "toilet",
                "doc": doc,
                "print_size": {"width_mm": 85, "height_mm": 130},
            },
        )
        assert created.status_code == 201, created.text
        template_id = created.json()["id"]

        fetched = client.get(f"/api/v1/dealer-kit/tag-templates/{template_id}")

    assert fetched.status_code == 200, fetched.text
    saved_doc = fetched.json()["doc"]
    image_layer = next(l for l in saved_doc["layers"] if l["id"] == "img1")
    badge_layer = next(l for l in saved_doc["layers"] if l["id"] == "badge1")

    assert image_layer["props"]["fit"] == "stretch"
    assert badge_layer["props"]["margin"] == {"top": 2, "right": 2, "bottom": 2, "left": 2}
    assert badge_layer["props"]["padding"] == {"top": 1, "right": 1, "bottom": 1, "left": 1}

    # The schema itself agrees this is a valid document (the strictness
    # contract `TagTemplateDocModel` carries - see module docstring).
    TagTemplateDocModel.model_validate(saved_doc)


def test_a_price_badge_with_currency_off_saves_and_reads_back_unchanged(api):
    """AC-16: a template saved with `showCurrency: false` loads back with it off."""
    with TestClient(app) as client:
        doc = _doc_with_stretch_and_margin(showCurrency=False)
        created = client.post(
            "/api/v1/dealer-kit/tag-templates",
            json={
                "name": unique_code("Tmpl"),
                "family": "toilet",
                "doc": doc,
                "print_size": {"width_mm": 85, "height_mm": 130},
            },
        )
        assert created.status_code == 201, created.text
        template_id = created.json()["id"]

        fetched = client.get(f"/api/v1/dealer-kit/tag-templates/{template_id}")

    assert fetched.status_code == 200, fetched.text
    saved_doc = fetched.json()["doc"]
    badge_layer = next(l for l in saved_doc["layers"] if l["id"] == "badge1")
    assert badge_layer["props"]["showCurrency"] is False

    TagTemplateDocModel.model_validate(saved_doc)


# ---------------------------------------------------------------------------
# AC-4: an unknown fit value is refused by the schema (strict Literal intact)
# ---------------------------------------------------------------------------


def test_an_unknown_fit_value_is_refused_by_the_schema():
    doc = _doc_with_stretch_and_margin()
    doc["layers"][0]["props"]["fit"] = "squash"

    with pytest.raises(pydantic.ValidationError):
        TagTemplateDocModel.model_validate(doc)


def test_cover_and_contain_still_validate():
    """AC-5: existing fits are untouched by the Literal gaining `stretch`."""
    for fit in ("cover", "contain"):
        doc = _doc_with_stretch_and_margin()
        doc["layers"][0]["props"]["fit"] = fit
        TagTemplateDocModel.model_validate(doc)
