"""Feature icons, review fix round 1 (PRICETAG-DESIGNER-GAPS item 3).

Contract: documentation/plans/dealer-kit/pricetag-feature-icons-contract.md. Each block names the
review item it pins: B1 portal previews forward the icons, B3 pins made before `raw` existed,
B4 a tag SHEET document, S1 the dealer-kit spec vocabulary, S2 the request's own company, S3 the
show-when request limits. Postgres only, own seed chain.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._ptag_r9_seed import seed_asset
from tests.test_product_tag_templates import env  # noqa: F401  (fixture)
from tests.test_feature_icons import (  # noqa: F401  (fixtures)
    BASE,
    _put,
    _registry,
    _ruled_icon,
    api,
    client,
)

SORENTO = "00000000-0000-0000-0000-000000000001"


def _icons_layer(layer_id: str = "fi1") -> dict:
    return {
        "id": layer_id,
        "type": "feature_icons",
        "x_mm": 2, "y_mm": 2, "width_mm": 40, "height_mm": 10, "z_index": 1,
        "props": {"kind": "feature_icons", "iconSize_mm": 8, "gap_mm": 1.5},
    }


def _fake_urls(db, ids, **_kw):
    return {i: f"https://signed.test/{i}" for i in set(ids)}


# ---------------------------------------------------------------------------
# B1: the portal live preview (lines mode and saved-request mode) forwards the icons
# ---------------------------------------------------------------------------


class TestPortalPreviewForwardsFeatureIcons:
    @pytest.fixture
    def portal(self, env):
        from tests import test_product_tag_templates as ptt

        db, c, _as = env
        yield ptt, db, c

    def _template_with_icons_layer(self, ptt, db) -> str:
        from app.models.dealer_kit import TagTemplate, TagTemplateVersion

        template_id = ptt._template(db, "Icons")
        template = db.get(TagTemplate, template_id)
        version = db.get(TagTemplateVersion, template.published_version_id)
        version.doc = {**version.doc, "layers": [*version.doc["layers"], _icons_layer()]}
        db.flush()
        return template_id

    def test_lines_mode_answers_the_ruled_icons(self, portal, monkeypatch):
        from app.services.dealer_kit import asset_service

        ptt, db, c = portal
        monkeypatch.setattr(asset_service, "urls_for", _fake_urls)
        key = _registry(db, allowed=["mixer"])
        icon = _ruled_icon(db, "ZZT portal hot", key, ["mixer"])
        product = ptt._product(db, ptt._reference(db))
        ptt._link(db, product, self._template_with_icons_layer(ptt, db))

        res = c.post(
            f"{ptt.PORTAL}/lookups/tag-preview",
            json={"lines": [{"key": "k1", "line_type": "product", "product_id": product}]},
        )
        assert res.status_code == 200, res.text
        assert icon.id in {i["id"] for i in res.json()["feature_icons"]}
        assert icon.id in res.json()["assets"]

    def test_request_mode_answers_the_ruled_icons(self, portal, monkeypatch):
        from app.services.dealer_kit import asset_service

        ptt, db, c = portal
        monkeypatch.setattr(asset_service, "urls_for", _fake_urls)
        key = _registry(db, allowed=["mixer"])
        icon = _ruled_icon(db, "ZZT portal cold", key, ["mixer"])
        product = ptt._product(db, ptt._reference(db))
        template_id = self._template_with_icons_layer(ptt, db)
        ptt._link(db, product, template_id)
        body = ptt._draft(
            c, [{"line_type": "product", "product_id": product, "tag_template_id": template_id}]
        )

        res = c.post(f"{ptt.PORTAL}/lookups/tag-preview", json={"request_id": body["id"]})
        assert res.status_code == 200, res.text
        assert icon.id in {i["id"] for i in res.json()["feature_icons"]}


# ---------------------------------------------------------------------------
# B3: pins made before `raw` existed
# ---------------------------------------------------------------------------


def _spec_row(key: str, value: str, raw: str | None) -> dict:
    row = {"key": key, "label": "Water supply", "value": value, "unit": None}
    if raw is not None:
        row["raw"] = raw
    return row


def test_the_data_hash_ignores_raw_so_an_old_keep_still_matches():
    from app.services.dealer_kit.tag_data_service import data_hash

    base = {"code": "TAP", "name": "Tap", "list_price": 10, "images": [], "parts": []}
    old = {**base, "specs": [_spec_row("water_supply", "Mixer", None)]}
    new = {**base, "specs": [_spec_row("water_supply", "Mixer", "mixer")]}
    assert data_hash(old) == data_hash(new)
    # The display value still counts.
    moved = {**base, "specs": [_spec_row("water_supply", "Cold Only", "cold_only")]}
    assert data_hash(moved) != data_hash(old)


def test_an_old_shape_pin_resolves_with_raw_from_the_live_row():
    from app.models.product_spec import ProductSpecifications
    from app.services.dealer_kit import tag_data_service
    from tests import _ptag_r9_seed as seed
    from tests._pg_fixture import blank_session
    from tests.test_price_tag_data_pin import _designing_request, _tags

    with blank_session() as db:
        seed.seed_marketer(db)
        key = _registry(db, allowed=["cold_only", "mixer"])
        product = seed.seed_product(db)
        db.add(
            ProductSpecifications(
                id=str(uuid.uuid4()),
                product_id=product.id,
                values={key: "mixer"},
                provenance={},
                rendered_text="ZZT rendered",
            )
        )
        db.flush()
        request, _product, _contact = _designing_request(db, product=product)

        tag = _tags(db, request.id)[0]
        pinned = dict(tag.pinned_tag_data)
        assert any(s["key"] == key for s in pinned["specs"])
        # The pin as a deploy-day row stored it: no `raw` anywhere.
        pinned["specs"] = [
            {k: v for k, v in spec.items() if k != "raw"} for spec in pinned["specs"]
        ]
        tag.pinned_tag_data = pinned
        db.commit()

        rows = tag_data_service.resolve_request_line_data(db, request)
        spec = next(s for s in rows[0]["specs"] if s["key"] == key)
        assert spec["raw"] == "mixer"
        assert spec["value"] == "Mixer"
        # And stripping raw is not a product data change.
        assert rows[0]["data_changes"] == []


# ---------------------------------------------------------------------------
# B4: a tag SHEET document
# ---------------------------------------------------------------------------


def test_design_media_finds_a_feature_icons_layer_inside_a_tag_sheet(api, monkeypatch):
    from app.services.dealer_kit import asset_service, tag_sheet_export_service

    monkeypatch.setattr(asset_service, "urls_for", _fake_urls)
    key = _registry(api, allowed=["mixer"])
    icon = _ruled_icon(api, "ZZT sheet icon", key, ["mixer"])
    doc = {
        "kind": "tag_sheet",
        "sheets": [{"id": "s1", "tags": [{"id": "t1", "layers": [_icons_layer()]}]}],
    }

    assert asset_service.doc_has_feature_icons(doc)
    _rows, media = tag_sheet_export_service.design_media(api, None, doc, rows=[])
    assert icon.id in {i["id"] for i in media["feature_icons"]}
    assert icon.id in media["assets"]


# ---------------------------------------------------------------------------
# S2: a staff render is pinned to the request's own company
# ---------------------------------------------------------------------------


def test_design_media_lists_only_the_requests_own_companys_icons(api, monkeypatch):
    from app.models.base import company_scope
    from app.services.dealer_kit import asset_service, tag_sheet_export_service
    from tests._knowledge_seed import seed_company

    monkeypatch.setattr(asset_service, "urls_for", _fake_urls)
    other = seed_company(api)
    key = _registry(api, allowed=["mixer"])
    mine = _ruled_icon(api, "ZZT mine", key, ["mixer"])
    theirs = _ruled_icon(api, "ZZT theirs", key, ["mixer"])
    theirs.company_id = other
    api.flush()

    request = SimpleNamespace(company_id=SORENTO, lines=[])
    with company_scope(api, frozenset({SORENTO, other})):
        _rows, media = tag_sheet_export_service.design_media(
            api, request, {"layers": [_icons_layer()]}, rows=[]
        )
    ids = {i["id"] for i in media["feature_icons"]}
    assert mine.id in ids
    assert theirs.id not in ids
    assert theirs.id not in media["assets"]


# ---------------------------------------------------------------------------
# S1: the dealer-kit spec vocabulary carries what the Show when editor needs
# ---------------------------------------------------------------------------


def test_dealer_kit_spec_keys_carry_type_values_and_labels(api, client):
    from app.models.product_spec import ProductSpecRegistry

    key = _registry(api, allowed=["cold_only", "mixer"])
    row = api.query(ProductSpecRegistry).filter_by(spec_key=key).one()
    row.value_labels = {"cold_only": "Cold only"}
    api.flush()

    from app.models.user import UserPermission, UserRolePermission
    from tests.test_feature_icons import _ROLE_ID

    slug = "dealer_kit.tag_templates.view"
    perm = api.query(UserPermission).filter_by(slug=slug).first()
    if perm is None:
        perm = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
        api.add(perm)
        api.flush()
    api.add(UserRolePermission(id=str(uuid.uuid4()), role_id=_ROLE_ID, permission_id=perm.id))
    api.commit()

    res = client.get("/api/v1/dealer-kit/spec-keys")
    assert res.status_code == 200, res.text
    got = next(r for r in res.json() if r["key"] == key)
    assert got["data_type"] == "enum"
    assert got["allowed_values"] == ["cold_only", "mixer"]
    assert got["value_labels"] == {"cold_only": "Cold only"}


# ---------------------------------------------------------------------------
# S3: the show-when request limits
# ---------------------------------------------------------------------------


def test_a_malformed_asset_id_is_404(client):
    res = _put(client, "not-a-uuid", {"spec_key": None, "values": []})
    assert res.status_code == 404, res.text


def _body_error(res, field: str) -> bool:
    """A request-body validation refusal naming ``field`` (not a service-level code)."""
    return res.status_code == 422 and any(
        field in [str(part) for part in err.get("loc", [])] for err in res.json().get("detail", [])
    )


def test_a_spec_key_longer_than_64_is_refused(api, client):
    icon = seed_asset(api, kind="icon")
    api.commit()
    res = _put(client, icon.id, {"spec_key": "k" * 65, "values": ["a"]})
    assert _body_error(res, "spec_key"), res.text


def test_more_than_50_values_are_refused(api, client):
    many = [f"v{i}" for i in range(51)]
    key = _registry(api, allowed=many)
    icon = seed_asset(api, kind="icon")
    api.commit()
    res = _put(client, icon.id, {"spec_key": key, "values": many})
    assert _body_error(res, "values"), res.text


@pytest.mark.parametrize("value", ["", "x" * 101])
def test_a_value_outside_1_to_100_chars_is_refused(api, client, value):
    key = _registry(api, allowed=[value, "ok"])
    icon = seed_asset(api, kind="icon")
    api.commit()
    res = _put(client, icon.id, {"spec_key": key, "values": [value]})
    assert _body_error(res, "values"), res.text


def test_a_boolean_key_accepts_only_true_and_false(api, client):
    key = _registry(api, data_type="boolean")
    icon = seed_asset(api, kind="icon")
    api.commit()

    assert _put(client, icon.id, {"spec_key": key, "values": ["true"]}).status_code == 200
    res = _put(client, icon.id, {"spec_key": key, "values": ["yes"]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "UNKNOWN_SPEC_VALUE"


def test_a_key_with_no_fixed_values_cannot_carry_a_rule(api, client):
    key = _registry(api, allowed=[], data_type="text")
    icon = seed_asset(api, kind="icon")
    api.commit()

    res = _put(client, icon.id, {"spec_key": key, "values": ["anything"]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SPEC_NOT_RULEABLE"


# ---------------------------------------------------------------------------
# Crew pass 5 Nov: the Show when values read like the product screens
# ---------------------------------------------------------------------------


def _grant_tag_templates_view(api) -> None:
    from app.models.user import UserPermission, UserRolePermission
    from tests.test_feature_icons import _ROLE_ID

    slug = "dealer_kit.tag_templates.view"
    perm = api.query(UserPermission).filter_by(slug=slug).first()
    if perm is None:
        perm = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
        api.add(perm)
        api.flush()
    api.add(UserRolePermission(id=str(uuid.uuid4()), role_id=_ROLE_ID, permission_id=perm.id))
    api.commit()


def test_spec_key_value_options_use_the_shared_display_labels(api, client):
    """`display_spec_value(title_case=True)` is the one label source: the tag prints
    "Cold Only", so the Show when list says "Cold Only", not "cold_only"; a staff-typed
    label still wins."""
    from app.models.product_spec import ProductSpecRegistry
    from app.services.product_spec_registry import display_spec_value

    key = _registry(api, allowed=["cold_only", "mixer", "pvc_pipe"])
    row = api.query(ProductSpecRegistry).filter_by(spec_key=key).one()
    row.value_labels = {"mixer": "Hot and cold"}
    api.flush()
    _grant_tag_templates_view(api)

    res = client.get("/api/v1/dealer-kit/spec-keys")
    assert res.status_code == 200, res.text
    got = next(r for r in res.json() if r["key"] == key)
    assert got["value_options"] == [
        {"value": "cold_only", "label": "Cold Only"},
        {"value": "mixer", "label": "Hot and cold"},
        {"value": "pvc_pipe", "label": display_spec_value("pvc_pipe", None, title_case=True)},
    ]


def test_a_boolean_spec_key_offers_yes_and_no(api, client):
    key = _registry(api, allowed=[], data_type="boolean")
    _grant_tag_templates_view(api)

    res = client.get("/api/v1/dealer-kit/spec-keys")
    got = next(r for r in res.json() if r["key"] == key)
    assert got["value_options"] == [
        {"value": "true", "label": "Yes"},
        {"value": "false", "label": "No"},
    ]
