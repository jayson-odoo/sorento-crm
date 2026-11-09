"""SPEC-ICON-COMBINED: a price-tag icon on one spec value may carry an AND list of conditions on
OTHER spec keys (owner rulings 9 Nov; plan documentation/plans/dealer-kit/PLAN-spec-icon-combined-09nov.md).

Storage: `product_spec_registry.value_icon_conditions` = `{value: {icon_id: [{spec_key, value}]}}`.
Wire: each feature icon gains `conditions: [{spec_key, value}]` (default `[]`), emitted at the HOST
value's slot. Postgres only, every test seeds its own chain.

Known knock-on for the coder: `test_feature_icons_spec_value.py` compares whole rule dicts without
a `conditions` key (`test_mixer_maps_to_hot_and_cold_in_the_admins_order`, the route test); once
`conditions: []` is emitted those two expectations need the new key.
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from tests.test_feature_icons_spec_value import (  # noqa: F401  (fixture)
    _icon,
    _patch,
    _rules_for,
    _spec_key,
    reg,
)
from tests.test_feature_icons_spec_value_fixround import two_companies  # noqa: F401  (fixture)
from tests.test_product_tag_templates import env  # noqa: F401  (fixture)
from tests.test_spec_registry_pr2_routes import (
    _ADMIN_ROLE,
    _BASE,
    _MERCHANDISER,
    _grant,
    _key,
)


def _cond(spec_key: str, value: str) -> dict:
    return {"spec_key": spec_key, "value": value}


def _stored(db, key):
    from app.models.product_spec import ProductSpecRegistry

    db.expire_all()
    return db.query(ProductSpecRegistry).filter_by(spec_key=key).one()


def _patch_both(client, key: str, value_icons: dict, conditions: dict):
    return client.patch(
        f"{_BASE}/{key}", json={"value_icons": value_icons, "value_icon_conditions": conditions}
    )


def _world(db):
    """Host enum key with two values, an enum partner (trap type) and a numeric partner."""
    host, trap, length = _spec_key(), _spec_key(), _spec_key()
    hot, cold = _icon(db, "ZZT hot"), _icon(db, "ZZT cold")
    _key(db, host, data_type="enum", allowed_values=["cold_only", "mixer"], label="ZZT host")
    _key(db, trap, data_type="enum", allowed_values=["s_trap", "p_trap"], label="ZZT trap")
    _key(db, length, data_type="numeric", unit="mm", label="ZZT length")
    db.commit()
    return host, trap, length, hot, cold


# ---------------------------------------------------------------------------
# B1: feature_icon_rules
# ---------------------------------------------------------------------------


def test_B1_rules_emit_conditions_for_a_conditioned_icon_and_empty_for_a_plain_one(reg):
    db, _as, _client = reg
    host, trap = _spec_key(), _spec_key()
    hot, cold = _icon(db, "ZZT hot"), _icon(db, "ZZT cold")
    _key(db, trap, data_type="enum", allowed_values=["s_trap", "p_trap"])
    _key(
        db, host, data_type="enum", allowed_values=["cold_only", "mixer"],
        value_icons={"mixer": [hot.id, cold.id], "cold_only": [cold.id]},
        value_icon_conditions={"mixer": {hot.id: [_cond(trap, "s_trap")]}},
    )
    db.flush()

    assert _rules_for(db, host) == [
        {"id": cold.id, "name": "ZZT cold", "spec_key": host, "values": ["cold_only"], "conditions": []},
        {"id": hot.id, "name": "ZZT hot", "spec_key": host, "values": ["mixer"],
         "conditions": [_cond(trap, "s_trap")]},
        {"id": cold.id, "name": "ZZT cold", "spec_key": host, "values": ["mixer"], "conditions": []},
    ]


def test_B1_the_conditioned_icon_keeps_the_host_values_slot_between_keys(reg):
    db, _as, _client = reg
    first, second, trap = _spec_key(), _spec_key(), _spec_key()
    a, b = _icon(db, "ZZT a"), _icon(db, "ZZT b")
    _key(db, trap, data_type="enum", allowed_values=["s_trap"])
    _key(db, first, data_type="enum", allowed_values=["x"], icon_order=1, value_icons={"x": [a.id]})
    _key(
        db, second, data_type="enum", allowed_values=["y"], icon_order=2,
        value_icons={"y": [b.id]}, value_icon_conditions={"y": {b.id: [_cond(trap, "s_trap")]}},
    )
    db.flush()
    from app.services.dealer_kit import asset_service

    mine = [r for r in asset_service.feature_icon_rules(db) if r["spec_key"] in (first, second)]
    assert [(r["spec_key"], r["id"], r["conditions"]) for r in mine] == [
        (first, a.id, []),
        (second, b.id, [_cond(trap, "s_trap")]),
    ]


def test_B1_the_feature_icons_route_carries_conditions(reg, monkeypatch):
    from app.services.dealer_kit import asset_service

    db, _as, client = reg
    monkeypatch.setattr(
        asset_service, "urls_for", lambda db, ids, **_kw: {i: f"https://s.test/{i}" for i in set(ids)}
    )
    _grant(db, _ADMIN_ROLE, ["dealer_kit.tag_templates.view"])
    host, trap = _spec_key(), _spec_key()
    icon = _icon(db, "ZZT route")
    _key(db, trap, data_type="enum", allowed_values=["s_trap"])
    _key(
        db, host, data_type="enum", allowed_values=["a"], value_icons={"a": [icon.id]},
        value_icon_conditions={"a": {icon.id: [_cond(trap, "s_trap")]}},
    )
    db.commit()

    res = client.get("/api/v1/dealer-kit/feature-icons")
    assert res.status_code == 200, res.text
    mine = [r for r in res.json() if r["spec_key"] == host]
    assert [r["conditions"] for r in mine] == [[_cond(trap, "s_trap")]]


# ---------------------------------------------------------------------------
# B2: PATCH saves, GET returns, numeric partner normalised
# ---------------------------------------------------------------------------


def test_B2_patch_saves_conditions_and_the_list_reads_them_back(reg):
    db, _as, client = reg
    host, trap, _length, hot, cold = _world(db)
    conditions = {"mixer": {hot.id: [_cond(trap, "s_trap")]}}

    res = _patch_both(client, host, {"mixer": [hot.id, cold.id]}, conditions)
    assert res.status_code == 200, res.text
    assert res.json()["value_icon_conditions"] == conditions

    _as(_MERCHANDISER)
    listed = {k["spec_key"]: k for k in client.get(_BASE).json()["keys"]}
    assert listed[host]["value_icon_conditions"] == conditions
    # A key that never had any reads an empty dict.
    assert listed[trap]["value_icon_conditions"] == {}


def test_B2_a_numeric_partner_value_is_stored_normalised(reg):
    db, _as, client = reg
    host, _trap, length, hot, _cold = _world(db)

    res = _patch_both(client, host, {"mixer": [hot.id]}, {"mixer": {hot.id: [_cond(length, "150.0")]}})
    assert res.status_code == 200, res.text
    assert res.json()["value_icon_conditions"] == {"mixer": {hot.id: [_cond(length, "150")]}}
    assert _stored(db, host).value_icon_conditions == {"mixer": {hot.id: [_cond(length, "150")]}}


def test_B2_several_partners_keep_their_order(reg):
    db, _as, client = reg
    host, trap, length, hot, _cold = _world(db)
    wanted = [_cond(length, "150"), _cond(trap, "s_trap")]
    res = _patch_both(client, host, {"mixer": [hot.id]}, {"mixer": {hot.id: wanted}})
    assert res.status_code == 200, res.text
    assert res.json()["value_icon_conditions"] == {"mixer": {hot.id: wanted}}


def test_B2_the_read_hides_another_companys_icon_conditions_but_the_row_keeps_them(two_companies):
    db, _as, client, other, as_company = two_companies
    host, trap = _spec_key(), _spec_key()
    mine, theirs = _icon(db, "ZZT mine"), _icon(db, "ZZT theirs")
    theirs.company_id = other
    _key(db, trap, data_type="enum", allowed_values=["s_trap"])
    _key(
        db, host, data_type="enum", allowed_values=["a"],
        value_icons={"a": [mine.id, theirs.id]},
        value_icon_conditions={"a": {mine.id: [_cond(trap, "s_trap")], theirs.id: [_cond(trap, "s_trap")]}},
    )
    db.commit()
    _as(_MERCHANDISER)

    listed = {k["spec_key"]: k for k in client.get(_BASE).json()["keys"]}
    assert listed[host]["value_icon_conditions"] == {"a": {mine.id: [_cond(trap, "s_trap")]}}

    # Company B saves its own icon; company A's stored conditions stay on the row.
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from tests.test_spec_registry_pr2_routes import _REGISTRY_ADMIN

    principal = {"id": _REGISTRY_ADMIN, "email": "x@test.com"}
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    as_company(other)
    res = _patch_both(client, host, {"a": [theirs.id]}, {"a": {theirs.id: [_cond(trap, "s_trap")]}})
    assert res.status_code == 200, res.text
    assert _stored(db, host).value_icon_conditions["a"][mine.id] == [_cond(trap, "s_trap")]


# ---------------------------------------------------------------------------
# B3: refusals (4xx, nothing stored)
# ---------------------------------------------------------------------------


def _refused(client, db, host, value_icons, conditions):
    res = _patch_both(client, host, value_icons, conditions)
    assert 400 <= res.status_code < 500, res.text
    assert _stored(db, host).value_icon_conditions in ({}, None)
    return res


def test_B3_partner_equal_to_the_host_key_is_refused(reg):
    db, _as, client = reg
    host, _trap, _length, hot, _cold = _world(db)
    _refused(client, db, host, {"mixer": [hot.id]}, {"mixer": {hot.id: [_cond(host, "cold_only")]}})


def test_B3_an_unknown_partner_key_is_refused(reg):
    db, _as, client = reg
    host, _trap, _length, hot, _cold = _world(db)
    _refused(client, db, host, {"mixer": [hot.id]}, {"mixer": {hot.id: [_cond("zzv_no_such_key", "x")]}})


def test_B3_an_inactive_partner_key_is_refused(reg):
    db, _as, client = reg
    host, _trap, _length, hot, _cold = _world(db)
    off = _spec_key()
    _key(db, off, data_type="enum", allowed_values=["x"], is_active=False)
    db.commit()
    _refused(client, db, host, {"mixer": [hot.id]}, {"mixer": {hot.id: [_cond(off, "x")]}})


def test_B3_an_enum_value_outside_the_partners_vocabulary_is_refused(reg):
    db, _as, client = reg
    host, trap, _length, hot, _cold = _world(db)
    _refused(client, db, host, {"mixer": [hot.id]}, {"mixer": {hot.id: [_cond(trap, "z_trap")]}})


def test_B3_a_non_number_for_a_numeric_partner_is_refused(reg):
    db, _as, client = reg
    host, _trap, length, hot, _cold = _world(db)
    _refused(client, db, host, {"mixer": [hot.id]}, {"mixer": {hot.id: [_cond(length, "long")]}})


def test_B3_the_same_partner_twice_on_one_icon_is_refused(reg):
    db, _as, client = reg
    host, trap, _length, hot, _cold = _world(db)
    _refused(
        client, db, host, {"mixer": [hot.id]},
        {"mixer": {hot.id: [_cond(trap, "s_trap"), _cond(trap, "p_trap")]}},
    )


def test_B3_more_than_five_conditions_on_one_icon_are_refused(reg):
    db, _as, client = reg
    host, _trap, _length, hot, _cold = _world(db)
    partners = []
    for _ in range(6):
        k = _spec_key()
        _key(db, k, data_type="enum", allowed_values=["x"])
        partners.append(_cond(k, "x"))
    db.commit()
    _refused(client, db, host, {"mixer": [hot.id]}, {"mixer": {hot.id: partners}})


def test_B3_exactly_five_conditions_are_accepted(reg):
    db, _as, client = reg
    host, _trap, _length, hot, _cold = _world(db)
    partners = []
    for _ in range(5):
        k = _spec_key()
        _key(db, k, data_type="enum", allowed_values=["x"])
        partners.append(_cond(k, "x"))
    db.commit()
    res = _patch_both(client, host, {"mixer": [hot.id]}, {"mixer": {hot.id: partners}})
    assert res.status_code == 200, res.text
    assert res.json()["value_icon_conditions"] == {"mixer": {hot.id: partners}}


def test_B3_a_condition_for_an_icon_not_on_that_value_is_refused(reg):
    db, _as, client = reg
    host, trap, _length, hot, cold = _world(db)
    # cold is on cold_only, hot is on mixer: a condition for cold under mixer is orphaned.
    _refused(
        client, db, host, {"mixer": [hot.id], "cold_only": [cold.id]},
        {"mixer": {cold.id: [_cond(trap, "s_trap")]}},
    )
    # ...and so is a condition for a value that has no icons at all.
    _refused(client, db, host, {"mixer": [hot.id]}, {"cold_only": {hot.id: [_cond(trap, "s_trap")]}})


# ---------------------------------------------------------------------------
# B4: conditions die with their icon / value
# ---------------------------------------------------------------------------


def _with_conditions(client, db):
    host, trap, _length, hot, cold = _world(db)
    conditions = {"mixer": {hot.id: [_cond(trap, "s_trap")]}, "cold_only": {cold.id: [_cond(trap, "p_trap")]}}
    res = _patch_both(client, host, {"mixer": [hot.id, cold.id], "cold_only": [cold.id]}, conditions)
    assert res.status_code == 200, res.text
    return host, trap, hot, cold


def test_B4_removing_the_icon_from_the_value_drops_its_conditions(reg):
    db, _as, client = reg
    host, trap, hot, cold = _with_conditions(client, db)

    res = _patch(client, host, {"mixer": [cold.id], "cold_only": [cold.id]})
    assert res.status_code == 200, res.text
    assert _stored(db, host).value_icon_conditions == {"cold_only": {cold.id: [_cond(trap, "p_trap")]}}
    assert res.json()["value_icon_conditions"] == {"cold_only": {cold.id: [_cond(trap, "p_trap")]}}


def test_B4_a_value_icons_only_save_keeps_the_conditions_of_icons_that_stay(reg):
    db, _as, client = reg
    host, trap, hot, cold = _with_conditions(client, db)

    res = _patch(client, host, {"mixer": [cold.id, hot.id], "cold_only": [cold.id]})
    assert res.status_code == 200, res.text
    assert _stored(db, host).value_icon_conditions == {
        "mixer": {hot.id: [_cond(trap, "s_trap")]},
        "cold_only": {cold.id: [_cond(trap, "p_trap")]},
    }


def test_B4_removing_a_value_drops_its_conditions(reg):
    from app.services.product_spec_registry import remove_value

    db, _as, client = reg
    host, trap, _length, hot, cold = _world(db)
    row = _stored(db, host)
    row.source = "seed"
    db.commit()
    res = _patch_both(
        client, host, {"mixer": [hot.id], "cold_only": [cold.id]},
        {"mixer": {hot.id: [_cond(trap, "s_trap")]}, "cold_only": {cold.id: [_cond(trap, "p_trap")]}},
    )
    assert res.status_code == 200, res.text

    remove_value(db, host, "cold_only")
    assert _stored(db, host).value_icon_conditions == {"mixer": {hot.id: [_cond(trap, "s_trap")]}}


def test_B4_suppressing_a_value_drops_its_conditions(reg):
    db, _as, client = reg
    host, _trap, _length, hot, cold = _world(db)
    row = _stored(db, host)
    row.source = "seed"
    row.synonyms = {"cold_only": ["cold only"], "mixer": ["mixer"]}
    db.commit()
    host, trap, hot, cold = host, _trap, hot, cold
    res = _patch_both(
        client, host, {"mixer": [hot.id], "cold_only": [cold.id]},
        {"mixer": {hot.id: [_cond(trap, "s_trap")]}, "cold_only": {cold.id: [_cond(trap, "p_trap")]}},
    )
    assert res.status_code == 200, res.text

    res = client.patch(f"{_BASE}/{host}", json={"suppressed_values": ["cold_only"]})
    assert res.status_code == 200, res.text
    assert _stored(db, host).value_icon_conditions == {"mixer": {hot.id: [_cond(trap, "s_trap")]}}


# ---------------------------------------------------------------------------
# B5: the Dealer Kit library gate
# ---------------------------------------------------------------------------


def _registry_only_user(db):
    from app.models.user import UserRole, UserRoleAssignment

    role = UserRole(id="2c7f5b94-9ea3-5068-d4f2-0b3c8e6a1d99", slug="zzt_reg_only", name="zzt_reg_only",
                    description="", is_protected=False, is_default=False)
    db.add(role)
    db.flush()
    _grant(db, role.id, ["master_data.spec_registry.edit", "master_data.products.edit"])
    db.add(UserRoleAssignment(user_id=_MERCHANDISER, role_id=role.id))
    db.commit()


def test_B5_conditions_without_dealer_kit_library_manage_are_403(reg):
    db, _as, client = reg
    host, trap, _length, hot, _cold = _world(db)
    _registry_only_user(db)
    _as(_MERCHANDISER)

    res = _patch_both(client, host, {"mixer": [hot.id]}, {"mixer": {hot.id: [_cond(trap, "s_trap")]}})
    assert res.status_code == 403, res.text
    assert _stored(db, host).value_icon_conditions in ({}, None)


def test_B5_a_conditions_only_patch_without_the_library_grant_is_403(reg):
    db, _as, client = reg
    host, trap, _length, hot, _cold = _world(db)
    assert _patch(client, host, {"mixer": [hot.id]}).status_code == 200
    _registry_only_user(db)
    _as(_MERCHANDISER)

    res = client.patch(f"{_BASE}/{host}", json={"value_icon_conditions": {"mixer": {hot.id: [_cond(trap, "s_trap")]}}})
    assert res.status_code == 403, res.text


def test_B5_a_merchandiser_without_registry_edit_is_403(reg):
    db, _as, client = reg
    host, trap, _length, hot, _cold = _world(db)
    _as(_MERCHANDISER)
    res = _patch_both(client, host, {"mixer": [hot.id]}, {"mixer": {hot.id: [_cond(trap, "s_trap")]}})
    assert res.status_code == 403, res.text


# ---------------------------------------------------------------------------
# B6: single-value links unchanged
# ---------------------------------------------------------------------------


def test_B6_a_value_icons_only_patch_leaves_the_rules_as_before_with_empty_conditions(reg):
    db, _as, client = reg
    host, _trap, _length, hot, cold = _world(db)

    res = _patch(client, host, {"mixer": [hot.id, cold.id], "cold_only": [cold.id]})
    assert res.status_code == 200, res.text
    assert res.json()["value_icon_conditions"] == {}
    assert _rules_for(db, host) == [
        {"id": cold.id, "name": "ZZT cold", "spec_key": host, "values": ["cold_only"], "conditions": []},
        {"id": hot.id, "name": "ZZT hot", "spec_key": host, "values": ["mixer"], "conditions": []},
        {"id": cold.id, "name": "ZZT cold", "spec_key": host, "values": ["mixer"], "conditions": []},
    ]
    assert _stored(db, host).value_icon_conditions in ({}, None)


def test_B4_a_stale_stored_condition_does_not_block_the_next_save(reg):
    """Round 1, finding 2: the partner's value was suppressed after the condition was saved."""
    db, _as, client = reg
    host, trap, _length, hot, cold = _world(db)
    partner = _stored(db, trap)
    partner.source = "seed"
    partner.synonyms = {"s_trap": ["s trap"], "p_trap": ["p trap"]}
    db.commit()
    stale = _cond(trap, "s_trap")
    res = _patch_both(
        client, host, {"mixer": [hot.id, cold.id]}, {"mixer": {hot.id: [stale]}}
    )
    assert res.status_code == 200, res.text
    gone = client.patch(f"{_BASE}/{trap}", json={"suppressed_values": ["s_trap"]})
    assert gone.status_code == 200, gone.text

    fresh = _cond(trap, "p_trap")
    res = _patch_both(
        client, host, {"mixer": [hot.id, cold.id]},
        {"mixer": {hot.id: [stale], cold.id: [fresh]}},
    )
    assert res.status_code == 200, res.text
    # The stale condition stays: dropping it would widen the icon to every product on this value.
    assert _stored(db, host).value_icon_conditions == {"mixer": {hot.id: [stale], cold.id: [fresh]}}
    assert [r["conditions"] for r in _rules_for(db, host) if r["id"] == hot.id] == [[stale]]

    # A NEW condition on a value the partner no longer offers is still refused.
    res = _patch_both(
        client, host, {"mixer": [hot.id, cold.id]},
        {"mixer": {hot.id: [stale], cold.id: [stale]}},
    )
    assert res.status_code == 422, res.text


def test_B4_a_condition_on_a_deactivated_partner_key_is_kept(reg):
    """Round 3: a partner key switched off after the condition was saved keeps the icon narrow."""
    db, _as, client = reg
    host, trap, _length, hot, cold = _world(db)
    stale = _cond(trap, "s_trap")
    res = _patch_both(client, host, {"mixer": [hot.id, cold.id]}, {"mixer": {hot.id: [stale]}})
    assert res.status_code == 200, res.text
    _stored(db, trap).is_active = False
    db.commit()

    other = _cond(_world(db)[1], "s_trap")  # an unrelated active key, for the NEW condition on Cold
    res = _patch_both(
        client, host, {"mixer": [hot.id, cold.id]},
        {"mixer": {hot.id: [stale], cold.id: [other]}},
    )
    assert res.status_code == 200, res.text
    assert _stored(db, host).value_icon_conditions["mixer"][hot.id] == [stale]
    assert [r["conditions"] for r in _rules_for(db, host) if r["id"] == hot.id] == [[stale]]

    # The same gone key sent as NEW on another icon is refused.
    res = _patch_both(
        client, host, {"mixer": [hot.id, cold.id]},
        {"mixer": {hot.id: [stale], cold.id: [stale]}},
    )
    assert res.status_code == 422, res.text


# ---------------------------------------------------------------------------
# FU F4: the staff tag preview forwards the feature icon rules (with conditions)
# ---------------------------------------------------------------------------


def test_FU_F4_the_staff_tag_preview_answers_the_feature_icon_rules_with_conditions(env, monkeypatch):
    from app.models.dealer_kit import TagTemplate, TagTemplateVersion
    from app.services.dealer_kit import asset_service
    from tests import test_product_tag_templates as ptt
    from tests.test_feature_icons import _ruled_icon
    from tests.test_feature_icons_fixround1 import _fake_urls, _icons_layer

    db, c, _as = env
    monkeypatch.setattr(asset_service, "urls_for", _fake_urls)
    host, trap = _spec_key(), _spec_key()
    _key(db, trap, data_type="enum", allowed_values=["s_trap"])
    _key(db, host, data_type="enum", allowed_values=["a"])
    icon = _ruled_icon(db, "ZZT staff", host, ["a"])
    row = _stored(db, host)
    row.value_icon_conditions = {"a": {icon.id: [_cond(trap, "s_trap")]}}
    template_id = ptt._template(db, "Icons")
    version = db.get(TagTemplateVersion, db.get(TagTemplate, template_id).published_version_id)
    version.doc = {**version.doc, "layers": [*version.doc["layers"], _icons_layer()]}
    product = ptt._product(db, ptt._reference(db))
    ptt._link(db, product, template_id)
    db.flush()

    res = c.post(
        f"{ptt.DK}/tag-preview",
        json={"lines": [{"key": "k1", "line_type": "product", "product_id": product}]},
    )
    assert res.status_code == 200, res.text
    mine = [r for r in res.json()["feature_icons"] if r["id"] == icon.id]
    assert [r["conditions"] for r in mine] == [[_cond(trap, "s_trap")]]
