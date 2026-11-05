"""Feature icons (PRICETAG-DESIGNER-GAPS item 3), backend half.

Contract: documentation/plans/dealer-kit/pricetag-feature-icons-contract.md (B1-B6).
Red tests written before the implementation. Postgres only, own seed chain.
"""
from __future__ import annotations

import uuid

import pydantic
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.schemas.price_tag import TagTemplateDocModel
from tests._pg_fixture import blank_session, unique_code
from tests._ptag_r9_seed import seed_asset, seed_product

_SORENTO = "00000000-0000-0000-0000-000000000001"
_USER_ID = "6a2b3c4d-5e6f-5a1b-8c2d-3e4f5a6b7c92"
_ROLE_ID = "7b3c4d5e-6f7a-5b2c-9d3e-4f5a6b7c8da3"

BASE = "/api/v1/dealer-kit/assets"


def _seed_user(db: Session) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    slug = "dealer_kit.library.manage"
    perm_id = str(uuid.uuid4())
    db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
    db.flush()
    db.add(
        UserRole(
            id=_ROLE_ID, slug="zzt_icons_mgr", name="zzt_icons_mgr",
            description="", is_protected=False, is_default=False,
        )
    )
    db.add(User(id=_USER_ID, email="zzt-icons-mgr@test.com", name="Mgr", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_USER_ID, role_id=_ROLE_ID))
    db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=_ROLE_ID, permission_id=perm_id))
    db.commit()


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_user(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        principal = {"id": _USER_ID, "email": f"{_USER_ID}@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db

        app.dependency_overrides.clear()


@pytest.fixture
def client(api):
    return TestClient(app)


def _registry(db, *, allowed=None, active=True, data_type="enum") -> str:
    from app.models.product_spec import ProductSpecRegistry

    key = unique_code("fi", alpha=True).lower().replace("-", "_")
    db.add(
        ProductSpecRegistry(
            id=str(uuid.uuid4()),
            spec_key=key,
            label="ZZT feature",
            data_type=data_type,
            allowed_values=allowed if allowed is not None else [],
            is_active=active,
        )
    )
    db.flush()
    return key


def _put(client, asset_id, body):
    return client.put(f"{BASE}/{asset_id}/show-when", json=body)


# ---------------------------------------------------------------------------
# B3: the show-when route
# ---------------------------------------------------------------------------


def test_put_show_when_sets_the_rule_and_the_list_returns_it(api, client):
    key = _registry(api, allowed=["cold_only", "mixer"])
    icon = seed_asset(api, kind="icon")
    api.commit()

    res = _put(client, icon.id, {"spec_key": key, "values": ["mixer"]})
    assert res.status_code == 200, res.text
    assert res.json()["show_when_spec_key"] == key
    assert res.json()["show_when_values"] == ["mixer"]

    listed = client.get(BASE, params={"kind": "icon"})
    assert listed.status_code == 200, listed.text
    row = next(r for r in listed.json() if r["id"] == icon.id)
    assert row["show_when_spec_key"] == key
    assert row["show_when_values"] == ["mixer"]


def test_null_spec_key_clears_both_columns(api, client):
    key = _registry(api, allowed=["cold_only", "mixer"])
    icon = seed_asset(api, kind="icon")
    api.commit()
    assert _put(client, icon.id, {"spec_key": key, "values": ["mixer"]}).status_code == 200

    res = _put(client, icon.id, {"spec_key": None, "values": []})
    assert res.status_code == 200, res.text
    assert res.json()["show_when_spec_key"] is None
    assert res.json()["show_when_values"] is None


def test_a_badge_cannot_carry_a_rule(api, client):
    key = _registry(api, allowed=["mixer"])
    badge = seed_asset(api, kind="badge")
    api.commit()

    res = _put(client, badge.id, {"spec_key": key, "values": ["mixer"]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "NOT_AN_ICON"


def test_an_unknown_spec_key_is_refused(api, client):
    icon = seed_asset(api, kind="icon")
    api.commit()

    res = _put(client, icon.id, {"spec_key": "zzt_no_such_key", "values": ["x"]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "UNKNOWN_SPEC"


def test_an_inactive_spec_key_is_refused(api, client):
    key = _registry(api, allowed=["a"], active=False)
    icon = seed_asset(api, kind="icon")
    api.commit()

    res = _put(client, icon.id, {"spec_key": key, "values": ["a"]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "UNKNOWN_SPEC"


def test_a_value_outside_the_allowed_values_is_refused(api, client):
    key = _registry(api, allowed=["cold_only", "mixer"])
    icon = seed_asset(api, kind="icon")
    api.commit()

    res = _put(client, icon.id, {"spec_key": key, "values": ["mixer", "lava"]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "UNKNOWN_SPEC_VALUE"


def test_a_spec_key_with_no_values_is_refused(api, client):
    key = _registry(api, allowed=["cold_only", "mixer"])
    icon = seed_asset(api, kind="icon")
    api.commit()

    res = _put(client, icon.id, {"spec_key": key, "values": []})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "VALUES_REQUIRED"


def test_an_unknown_asset_is_404(api, client):
    res = _put(client, str(uuid.uuid4()), {"spec_key": None, "values": []})
    assert res.status_code == 404, res.text
    assert res.json()["code"] == "ASSET_NOT_FOUND"


def test_duplicate_values_are_removed_keeping_order(api, client):
    key = _registry(api, allowed=["a", "b", "c"])
    icon = seed_asset(api, kind="icon")
    api.commit()

    res = _put(client, icon.id, {"spec_key": key, "values": ["b", "a", "b", "c", "a"]})
    assert res.status_code == 200, res.text
    assert res.json()["show_when_values"] == ["b", "a", "c"]


def test_the_route_is_denied_without_the_library_permission(api, client):
    from app.dependencies import get_current_user

    key = _registry(api, allowed=["a"])
    icon = seed_asset(api, kind="icon")
    api.commit()

    nobody = "6a2b3c4d-5e6f-5a1b-8c2d-3e4f5a6b7caa"
    from app.models.user import User

    api.add(User(id=nobody, email="zzt-icons-nobody@test.com", name="Nobody", status="ACTIVE"))
    api.commit()
    app.dependency_overrides[get_current_user] = lambda: {"id": nobody, "email": "n@test.com"}

    res = _put(client, icon.id, {"spec_key": key, "values": ["a"]})
    assert res.status_code in (401, 403), res.text


# ---------------------------------------------------------------------------
# B1: the pair CHECK
# ---------------------------------------------------------------------------


def test_only_one_of_the_two_rule_columns_violates_the_check(api):
    icon = seed_asset(api, kind="icon")
    api.commit()

    icon.show_when_spec_key = "water_supply"
    icon.show_when_values = None
    with pytest.raises(IntegrityError):
        api.flush()
    api.rollback()


def test_only_the_values_column_violates_the_check(api):
    icon = seed_asset(api, kind="icon")
    api.commit()

    icon.show_when_spec_key = None
    icon.show_when_values = ["mixer"]
    with pytest.raises(IntegrityError):
        api.flush()
    api.rollback()


# ---------------------------------------------------------------------------
# B4: raw beside display
# ---------------------------------------------------------------------------


def test_product_specs_carry_the_raw_value_beside_the_display_one(api):
    from app.models.product_spec import ProductSpecifications
    from app.services.dealer_kit import tag_data_service

    key = _registry(api, allowed=["cold_only", "mixer"])
    product = seed_product(api)
    api.add(
        ProductSpecifications(
            id=str(uuid.uuid4()),
            product_id=product.id,
            values={key: "mixer"},
            provenance={},
            rendered_text="ZZT rendered",
        )
    )
    api.flush()

    specs = tag_data_service.product_specs(api, product)
    row = next(s for s in specs if s["key"] == key)
    assert row["raw"] == "mixer"
    assert row["value"] == "Mixer"


def test_a_wrapped_bool_raw_is_the_string_true(api):
    from app.models.product_spec import ProductSpecifications
    from app.services.dealer_kit import tag_data_service

    key = _registry(api, data_type="boolean")
    product = seed_product(api)
    api.add(
        ProductSpecifications(
            id=str(uuid.uuid4()),
            product_id=product.id,
            values={key: {"value": True}},
            provenance={},
            rendered_text="ZZT rendered",
        )
    )
    api.flush()

    row = next(s for s in tag_data_service.product_specs(api, product) if s["key"] == key)
    assert row["raw"] == "true"


# ---------------------------------------------------------------------------
# B5: design_media forwards ruled icons when the doc has a feature_icons layer
# ---------------------------------------------------------------------------


def _doc(with_icons_layer: bool) -> dict:
    layers = []
    if with_icons_layer:
        layers.append(
            {
                "id": "fi1",
                "type": "feature_icons",
                "x_mm": 2, "y_mm": 2, "width_mm": 40, "height_mm": 10, "z_index": 1,
                "props": {"kind": "feature_icons", "iconSize_mm": 8, "gap_mm": 1.5},
            }
        )
    return {"layers": layers, "width_mm": 85, "height_mm": 130}


def _ruled_icon(db, name: str, key: str, values: list[str]):
    icon = seed_asset(db, kind="icon")
    icon.name = name
    icon.show_when_spec_key = key
    icon.show_when_values = values
    db.flush()
    return icon


def test_design_media_lists_every_ruled_icon_name_ordered_and_signs_their_urls(api, monkeypatch):
    from app.services.dealer_kit import asset_service, tag_sheet_export_service

    key = _registry(api, allowed=["cold_only", "mixer"])
    b = _ruled_icon(api, "ZZT b hot", key, ["mixer"])
    a = _ruled_icon(api, "ZZT a cold", key, ["cold_only", "mixer"])
    plain = seed_asset(api, kind="icon")  # no rule: not listed

    seen: list[set[str]] = []

    def fake_urls(db, ids, **_kw):
        ids = set(ids)
        seen.append(ids)
        return {i: f"https://signed.test/{i}" for i in ids}

    monkeypatch.setattr(asset_service, "urls_for", fake_urls)

    _rows, media = tag_sheet_export_service.design_media(api, None, _doc(True), rows=[])

    mine = [i for i in media["feature_icons"] if i["id"] in {a.id, b.id}]
    assert [i["id"] for i in mine] == [a.id, b.id]
    assert mine[0] == {
        "id": a.id, "name": "ZZT a cold", "spec_key": key, "values": ["cold_only", "mixer"],
    }
    assert plain.id not in {i["id"] for i in media["feature_icons"]}
    assert a.id in media["assets"] and b.id in media["assets"]
    assert plain.id not in media["assets"]


def test_design_media_has_an_empty_feature_icons_list_without_the_layer(api, monkeypatch):
    from app.services.dealer_kit import asset_service, tag_sheet_export_service

    key = _registry(api, allowed=["mixer"])
    icon = _ruled_icon(api, "ZZT only", key, ["mixer"])

    monkeypatch.setattr(
        asset_service, "urls_for", lambda db, ids, **_kw: {i: f"https://s.test/{i}" for i in set(ids)}
    )

    _rows, media = tag_sheet_export_service.design_media(api, None, _doc(False), rows=[])

    assert media["feature_icons"] == []
    assert icon.id not in media["assets"]


# ---------------------------------------------------------------------------
# B6: the document contract
# ---------------------------------------------------------------------------


def _layer(**props) -> dict:
    base = {"kind": "feature_icons", "iconSize_mm": 8, "gap_mm": 1.5}
    base.update(props)
    return {
        "layers": [
            {
                "id": "fi", "type": "feature_icons",
                "x_mm": 1, "y_mm": 1, "width_mm": 40, "height_mm": 10, "z_index": 1,
                "props": base,
            }
        ],
        "width_mm": 85,
        "height_mm": 130,
    }


def test_the_document_accepts_a_feature_icons_layer():
    doc = TagTemplateDocModel.model_validate(
        _layer(align="center", order=["a1"], subjectPart=0, subjectSlot={"kind": "fixed", "index": 0})
    )
    assert doc.layers[0].type == "feature_icons"


def test_a_feature_icons_layer_defaults_to_left_aligned():
    doc = TagTemplateDocModel.model_validate(_layer())
    assert doc.layers[0].props.align == "left"
    assert doc.layers[0].props.order == []


def test_a_zero_icon_size_is_refused():
    with pytest.raises(pydantic.ValidationError) as exc:
        TagTemplateDocModel.model_validate(_layer(iconSize_mm=0))
    assert "iconSize_mm" in str(exc.value)


def test_an_unknown_align_is_refused():
    with pytest.raises(pydantic.ValidationError) as exc:
        TagTemplateDocModel.model_validate(_layer(align="justify"))
    assert "align" in str(exc.value)
