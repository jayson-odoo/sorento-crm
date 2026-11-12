"""Feature icons from the SPEC VALUE (owner ruling 5 Nov 20:35, addition 20:4x).

Each spec value carries its own ordered list of Dealer Kit icons on the registry row
(`product_spec_registry.value_icons`, `{value: [asset id, ...]}`), set on Master Data > Product
Specifications > a spec > Values and words. The designer's Feature icons layer pulls the icons for
the product's values: `feature_icon_rules` emits one entry per (key, value, icon), specs by their
Icon order (blank last, ties by label then spec_key), values in the key's value order, icons in
the order the admin set on the value. Postgres only, own seed chain.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session, unique_code
from tests._ptag_r9_seed import seed_asset
from tests.test_spec_registry_pr2_routes import (
    _ADMIN_ROLE,
    _BASE,
    _MERCHANDISER,
    _OUTSIDER,
    _REGISTRY_ADMIN,
    _grant,
    _key,
    _seed,
)

SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def reg():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed(db)
        # Saving value_icons also needs the Dealer Kit library (review S2, fix round).
        _grant(db, _ADMIN_ROLE, ["dealer_kit.library.manage"])
        db.commit()
        set_company_scope(db, frozenset({SORENTO}))

        def _override_get_db():
            yield db

        async def _override_scope():
            scope = frozenset({SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        _as(_REGISTRY_ADMIN)
        try:
            yield db, _as, TestClient(app)
        finally:
            app.dependency_overrides.clear()


def _spec_key() -> str:
    return unique_code("zzv", alpha=True).lower().replace("-", "_")


def _icon(db, name: str, kind: str = "icon"):
    asset = seed_asset(db, kind=kind)
    asset.name = name
    db.flush()
    return asset


def _patch(client, key: str, value_icons: dict):
    return client.patch(f"{_BASE}/{key}", json={"value_icons": value_icons})


# ---------------------------------------------------------------------------
# The PATCH: accept and validate
# ---------------------------------------------------------------------------


def test_value_icons_are_saved_in_order_and_read_back_on_the_list(reg):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["cold_only", "mixer"])
    hot, cold = _icon(db, "ZZT hot"), _icon(db, "ZZT cold")
    db.commit()

    res = _patch(client, key, {"mixer": [hot.id, cold.id, hot.id], "cold_only": [cold.id]})
    assert res.status_code == 200, res.text
    # Deduplicated, the admin's order kept.
    assert res.json()["value_icons"] == {"mixer": [hot.id, cold.id], "cold_only": [cold.id]}

    _as(_MERCHANDISER)  # the list read is the product page's (`master_data.products.view`)
    listed = {k["spec_key"]: k for k in client.get(_BASE).json()["keys"]}
    assert listed[key]["value_icons"] == {"mixer": [hot.id, cold.id], "cold_only": [cold.id]}


def test_the_list_read_names_each_icon_so_no_id_is_shown(reg):
    """The spec screen shows an icon by NAME (no UUIDs in the UI), and a master-data user
    need not hold the Dealer Kit library permission to read it."""
    db, _as, client = reg
    key = _spec_key()
    icon = _icon(db, "ZZT named")
    _key(db, key, data_type="enum", allowed_values=["a"], value_icons={"a": [icon.id]})
    db.commit()
    _as(_MERCHANDISER)
    listed = {k["spec_key"]: k for k in client.get(_BASE).json()["keys"]}
    assert listed[key]["value_icon_names"] == {icon.id: "ZZT named"}


def test_a_new_key_reads_an_empty_value_icons_dict(reg):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a"])
    db.commit()
    _as(_MERCHANDISER)
    listed = {k["spec_key"]: k for k in client.get(_BASE).json()["keys"]}
    assert listed[key]["value_icons"] == {}


def test_an_empty_list_removes_the_values_entry(reg):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a", "b"])
    icon = _icon(db, "ZZT i")
    db.commit()
    assert _patch(client, key, {"a": [icon.id], "b": [icon.id]}).status_code == 200

    res = _patch(client, key, {"a": [], "b": [icon.id]})
    assert res.status_code == 200, res.text
    assert res.json()["value_icons"] == {"b": [icon.id]}


def test_a_non_icon_asset_is_refused(reg):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a"])
    badge = _icon(db, "ZZT badge", kind="badge")
    db.commit()

    res = _patch(client, key, {"a": [badge.id]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "spec_registry_icon_not_an_icon"


def test_an_unknown_asset_is_refused(reg):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a"])
    db.commit()

    res = _patch(client, key, {"a": [str(uuid.uuid4())]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "spec_registry_icon_not_an_icon"


def test_an_unknown_value_is_refused(reg):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a"])
    icon = _icon(db, "ZZT i")
    db.commit()

    res = _patch(client, key, {"lava": [icon.id]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "spec_registry_icon_unknown_value"


def test_more_than_ten_icons_on_one_value_are_refused(reg):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a"])
    icons = [_icon(db, f"ZZT {i}") for i in range(11)]
    db.commit()

    res = _patch(client, key, {"a": [i.id for i in icons]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "spec_registry_icon_too_many"


def test_a_boolean_key_maps_true_and_false(reg):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="boolean")
    icon = _icon(db, "ZZT yes")
    db.commit()

    res = _patch(client, key, {"true": [icon.id]})
    assert res.status_code == 200, res.text
    assert _patch(client, key, {"yes": [icon.id]}).json()["code"] == "spec_registry_icon_unknown_value"


def test_a_merchandiser_cannot_set_value_icons(reg):
    """Treated like `value_labels`: outside the vocabulary-only fields, so the stricter
    `master_data.spec_registry.edit` grant is required."""
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a"])
    icon = _icon(db, "ZZT i")
    db.commit()
    _as(_MERCHANDISER)

    assert _patch(client, key, {"a": [icon.id]}).status_code == 403


def test_seed_repair_leaves_value_icons_alone(reg):
    from app.services.product_spec_registry import SPEC_REGISTRY_SEED, seed_spec_registry

    db, _as, _client = reg
    entry = SPEC_REGISTRY_SEED[0]
    row = _key(
        db,
        entry["spec_key"],
        label="Drifted label",
        data_type=entry["data_type"],
        source="seed",
        value_icons={"pp": ["some-icon"]},
    )
    db.commit()

    seed_spec_registry(db, commit=True)
    db.refresh(row)

    assert row.value_icons == {"pp": ["some-icon"]}
    assert row.label == entry["label"]  # the repair ran


# ---------------------------------------------------------------------------
# feature_icon_rules: derived from the registry
# ---------------------------------------------------------------------------


def _rules_for(db, key: str, **kw) -> list[dict]:
    from app.services.dealer_kit import asset_service

    return [r for r in asset_service.feature_icon_rules(db, **kw) if r["spec_key"] == key]


def test_mixer_maps_to_hot_and_cold_in_the_admins_order(reg):
    db, _as, _client = reg
    key = _spec_key()
    hot, cold = _icon(db, "ZZT hot"), _icon(db, "ZZT cold")
    _key(
        db, key, data_type="enum", allowed_values=["cold_only", "mixer"],
        value_icons={"mixer": [hot.id, cold.id], "cold_only": [cold.id]},
    )

    assert _rules_for(db, key) == [
        {"id": cold.id, "name": "ZZT cold", "spec_key": key, "values": ["cold_only"], "conditions": []},
        {"id": hot.id, "name": "ZZT hot", "spec_key": key, "values": ["mixer"], "conditions": []},
        {"id": cold.id, "name": "ZZT cold", "spec_key": key, "values": ["mixer"], "conditions": []},
    ]


def test_mixer_mapped_to_one_combined_icon_yields_only_that_icon(reg):
    """Owner (20:4x): Mixer -> ONE red-blue icon, Cold Only -> a blue one. A mixer product
    reads exactly the combined icon; a cold-only product the blue one only."""
    db, _as, _client = reg
    key = _spec_key()
    combined, blue = _icon(db, "ZZT red-blue"), _icon(db, "ZZT blue")
    _key(
        db, key, data_type="enum", allowed_values=["cold_only", "mixer"],
        value_icons={"mixer": [combined.id], "cold_only": [blue.id]},
    )

    rules = _rules_for(db, key)
    for_mixer = [r["id"] for r in rules if "mixer" in r["values"]]
    for_cold = [r["id"] for r in rules if "cold_only" in r["values"]]
    assert for_mixer == [combined.id]
    assert for_cold == [blue.id]


def test_rules_skip_a_non_icon_a_deleted_asset_and_an_inactive_key(reg):
    from app.models.resources import Attachment

    db, _as, _client = reg
    key, off = _spec_key(), _spec_key()
    icon, badge, gone = _icon(db, "ZZT ok"), _icon(db, "ZZT badge", kind="badge"), _icon(db, "ZZT gone")
    db.get(Attachment, gone.attachment_id).is_deleted = True
    _key(db, key, data_type="enum", allowed_values=["a"], value_icons={"a": [badge.id, gone.id, icon.id]})
    _key(db, off, data_type="enum", allowed_values=["a"], value_icons={"a": [icon.id]}, is_active=False)
    db.flush()

    assert [r["id"] for r in _rules_for(db, key)] == [icon.id]
    assert _rules_for(db, off) == []


def test_rules_are_pinned_to_one_company_when_asked(reg):
    from app.models.base import company_scope
    from tests._knowledge_seed import seed_company

    db, _as, _client = reg
    other = seed_company(db)
    key = _spec_key()
    mine, theirs = _icon(db, "ZZT mine"), _icon(db, "ZZT theirs")
    theirs.company_id = other
    _key(db, key, data_type="enum", allowed_values=["a"], value_icons={"a": [theirs.id, mine.id]})
    db.flush()

    with company_scope(db, frozenset({SORENTO, other})):
        assert [r["id"] for r in _rules_for(db, key, company_id=SORENTO)] == [mine.id]


def test_design_media_reads_the_registry_for_a_request(reg, monkeypatch):
    from app.services.dealer_kit import asset_service, tag_sheet_export_service

    db, _as, _client = reg
    monkeypatch.setattr(
        asset_service, "urls_for", lambda db, ids, **_kw: {i: f"https://s.test/{i}" for i in set(ids)}
    )
    key = _spec_key()
    icon = _icon(db, "ZZT rq")
    _key(db, key, data_type="enum", allowed_values=["a"], value_icons={"a": [icon.id]})
    db.flush()
    layer = {
        "id": "fi", "type": "feature_icons", "x_mm": 0, "y_mm": 0, "width_mm": 40,
        "height_mm": 10, "z_index": 1,
        "props": {"kind": "feature_icons", "iconSize_mm": 8, "gap_mm": 1},
    }

    _rows, media = tag_sheet_export_service.design_media(
        db, SimpleNamespace(company_id=SORENTO, lines=[]), {"layers": [layer]}, rows=[]
    )
    assert icon.id in {r["id"] for r in media["feature_icons"]}
    assert icon.id in media["assets"]


# ---------------------------------------------------------------------------
# The canvas's source: GET /dealer-kit/feature-icons, behind the editor's own gate
# ---------------------------------------------------------------------------


def test_the_dealer_kit_feature_icons_route_lists_rules_with_urls(reg, monkeypatch):
    from app.services.dealer_kit import asset_service

    db, _as, client = reg
    monkeypatch.setattr(
        asset_service, "urls_for", lambda db, ids, **_kw: {i: f"https://s.test/{i}" for i in set(ids)}
    )
    _grant(db, _ADMIN_ROLE, ["dealer_kit.tag_templates.view"])
    key = _spec_key()
    icon = _icon(db, "ZZT route")
    _key(db, key, data_type="enum", allowed_values=["a"], value_icons={"a": [icon.id]})
    db.commit()

    res = client.get("/api/v1/dealer-kit/feature-icons")
    assert res.status_code == 200, res.text
    mine = [r for r in res.json() if r["spec_key"] == key]
    assert mine == [
        {"id": icon.id, "name": "ZZT route", "spec_key": key, "values": ["a"], "conditions": [],
         "url": f"https://s.test/{icon.id}"},
    ]


def test_the_feature_icons_route_needs_the_editor_permission(reg):
    db, _as, client = reg
    db.commit()
    _as(_OUTSIDER)
    assert client.get("/api/v1/dealer-kit/feature-icons").status_code == 403


# ---------------------------------------------------------------------------
# Owner 21:0x: each SPEC has an "Icon order"; ONE global sequence
# ---------------------------------------------------------------------------


def _for_product(rules: list[dict], holds: dict[str, str]) -> list[str]:
    """What a product holding `holds` ({spec_key: raw value}) shows: the FE rule, in input
    order, each asset once at its first position."""
    out: list[str] = []
    for rule in rules:
        if holds.get(rule["spec_key"]) in rule["values"] and rule["id"] not in out:
            out.append(rule["id"])
    return out


def _ordered_world(db, *, pull_order=1, water_order=2, combined=False):
    pull_key, water_key = _spec_key(), _spec_key()
    pull = _icon(db, "ZZT pull-out")
    hot, cold = _icon(db, "ZZT hot"), _icon(db, "ZZT cold")
    combo = _icon(db, "ZZT red-blue")
    _key(db, pull_key, label="Pull-out", data_type="boolean", icon_order=pull_order,
         value_icons={"true": [pull.id]})
    _key(db, water_key, label="Water supply", data_type="enum", icon_order=water_order,
         allowed_values=["cold_only", "mixer"],
         value_icons={"mixer": [combo.id] if combined else [hot.id, cold.id], "cold_only": [cold.id]})
    db.flush()
    return pull_key, water_key, SimpleNamespace(pull=pull, hot=hot, cold=cold, combo=combo)


def _rules(db, *keys):
    from app.services.dealer_kit import asset_service

    return [r for r in asset_service.feature_icon_rules(db) if r["spec_key"] in keys]


def test_pull_out_then_water_supply_by_icon_order(reg):
    db, _as, _client = reg
    pull_key, water_key, i = _ordered_world(db)
    rules = _rules(db, pull_key, water_key)
    assert _for_product(rules, {pull_key: "true", water_key: "mixer"}) == [i.pull.id, i.hot.id, i.cold.id]
    assert _for_product(rules, {water_key: "mixer"}) == [i.hot.id, i.cold.id]


def test_a_combined_mixer_icon_shows_alone(reg):
    db, _as, _client = reg
    pull_key, water_key, i = _ordered_world(db, combined=True)
    rules = _rules(db, pull_key, water_key)
    assert _for_product(rules, {water_key: "mixer"}) == [i.combo.id]
    assert _for_product(rules, {water_key: "cold_only"}) == [i.cold.id]


def test_the_icon_order_beats_the_spec_key(reg):
    """Water supply (1) before Pull-out (2) once the numbers say so, whatever the keys."""
    db, _as, _client = reg
    pull_key, water_key, i = _ordered_world(db, pull_order=2, water_order=1)
    rules = _rules(db, pull_key, water_key)
    assert _for_product(rules, {pull_key: "true", water_key: "mixer"}) == [i.hot.id, i.cold.id, i.pull.id]


def test_a_spec_with_no_icon_order_goes_last(reg):
    db, _as, _client = reg
    pull_key, water_key, i = _ordered_world(db, pull_order=None, water_order=5)
    rules = _rules(db, pull_key, water_key)
    assert _for_product(rules, {pull_key: "true", water_key: "mixer"}) == [i.hot.id, i.cold.id, i.pull.id]


def test_ties_fall_back_to_the_spec_label(reg):
    db, _as, _client = reg
    # Same order: "Pull-out" < "Water supply" by label.
    pull_key, water_key, i = _ordered_world(db, pull_order=3, water_order=3)
    rules = _rules(db, pull_key, water_key)
    assert _for_product(rules, {pull_key: "true", water_key: "mixer"}) == [i.pull.id, i.hot.id, i.cold.id]


def test_icon_order_is_saved_read_back_and_cleared(reg):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a"])
    db.commit()

    res = client.patch(f"{_BASE}/{key}", json={"icon_order": 2})
    assert res.status_code == 200, res.text
    assert res.json()["icon_order"] == 2
    _as(_MERCHANDISER)
    listed = {k["spec_key"]: k for k in client.get(_BASE).json()["keys"]}
    assert listed[key]["icon_order"] == 2

    _as(_REGISTRY_ADMIN)
    res = client.patch(f"{_BASE}/{key}", json={"icon_order": None})
    assert res.status_code == 200, res.text
    assert res.json()["icon_order"] is None


@pytest.mark.parametrize("bad", [0, 1000, -1])
def test_icon_order_outside_1_to_999_is_refused(reg, bad):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a"])
    db.commit()
    assert client.patch(f"{_BASE}/{key}", json={"icon_order": bad}).status_code == 422


def test_a_merchandiser_cannot_set_icon_order(reg):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a"])
    db.commit()
    _as(_MERCHANDISER)
    assert client.patch(f"{_BASE}/{key}", json={"icon_order": 1}).status_code == 403


def test_seed_repair_leaves_icon_order_alone(reg):
    from app.services.product_spec_registry import SPEC_REGISTRY_SEED, seed_spec_registry

    db, _as, _client = reg
    entry = SPEC_REGISTRY_SEED[0]
    row = _key(db, entry["spec_key"], label="Drifted", data_type=entry["data_type"],
               source="seed", icon_order=7)
    db.commit()
    seed_spec_registry(db, commit=True)
    db.refresh(row)
    assert row.icon_order == 7
    assert row.label == entry["label"]
