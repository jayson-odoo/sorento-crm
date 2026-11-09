"""PRICETAG-UPGRADE-VARIANTS BE tests 7 and 8 (AC-F3): numeric spec values carry icons.

Written test-FIRST. `spec_value_keys(row)` keeps its signature; for a `numeric` key it reads the
products' distinct values through `sqlalchemy.orm.object_session(row)`, normalised (150, 150.0 and
"150" -> "150"), sorted numerically. `_spec_raw_text` prints a whole number without ".0".
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests import _ptag_variant_seed as vseed
from tests._pg_fixture import blank_session
from tests._ptag_r9_seed import seed_asset


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _product_with(db, **values):
    item = seed.product(db, "ZZNUM")
    vseed.set_specs(db, item, **values)
    return item


# --------------------------------------------------------------------------- BE 7


def test_be7_numeric_key_offers_the_distinct_normalised_values_sorted_numerically(db):
    from app.services.dealer_kit.asset_service import spec_value_keys

    reg = vseed.registry(db)["trap_length"]
    _product_with(db, trap_length=250)
    _product_with(db, trap_length=150.0)
    _product_with(db, trap_length="150")
    _product_with(db, trap_length={"value": 200, "unit": "mm"})
    _product_with(db, trap_length=1000)
    assert spec_value_keys(reg) == ["150", "200", "250", "1000"]


def test_be7_numeric_key_with_no_products_offers_nothing(db):
    from app.services.dealer_kit.asset_service import spec_value_keys

    reg = vseed.registry(db)["trap_length"]
    assert spec_value_keys(reg) == []


def test_be7_the_other_key_kinds_are_unchanged(db):
    from app.services.dealer_kit.asset_service import spec_value_keys

    reg = vseed.registry(db)
    assert spec_value_keys(reg["trap_type"]) == ["s_trap", "p_trap"]


def test_be7_clean_value_icons_accepts_a_numeric_value(db):
    from app.services.dealer_kit.asset_service import clean_value_icons

    reg = vseed.registry(db)["trap_length"]
    _product_with(db, trap_length=150.0)
    icon = seed_asset(db, kind="icon")
    db.flush()
    assert clean_value_icons(db, reg, {"150": [icon.id]}) == {"150": [icon.id]}


def test_be7_a_numeric_value_no_product_holds_is_still_refused(db):
    from app.services.error_handler import AppException
    from app.services.dealer_kit.asset_service import clean_value_icons

    reg = vseed.registry(db)["trap_length"]
    _product_with(db, trap_length=150)
    icon = seed_asset(db, kind="icon")
    db.flush()
    with pytest.raises(AppException) as caught:
        clean_value_icons(db, reg, {"999": [icon.id]})
    assert caught.value.status_code == 422


def test_be7_the_rules_feed_lists_the_icon_on_the_normalised_value(db):
    from app.services.dealer_kit.asset_service import feature_icon_rules

    reg = vseed.registry(db)["trap_length"]
    _product_with(db, trap_length=150.0)
    icon = seed_asset(db, kind="icon")
    icon.name = "ZZT 6in"
    reg.value_icons = {"150": [icon.id]}
    db.flush()
    mine = [r for r in feature_icon_rules(db) if r["spec_key"] == "trap_length"]
    assert mine == [{"id": icon.id, "name": "ZZT 6in", "spec_key": "trap_length", "values": ["150"]}]


def _client_as(db, user_id):
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    set_company_scope(db, frozenset({vseed.SORENTO}))

    async def _scope():
        set_company_scope(db, frozenset({vseed.SORENTO}))
        return frozenset({vseed.SORENTO})

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[apply_company_scope] = _scope
    principal = {"id": user_id, "email": f"{user_id}@test.com"}
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    return TestClient(app)


def test_be7_the_registry_patch_accepts_value_icons_for_a_numeric_key(db):
    from tests.test_spec_registry_pr2_routes import _ADMIN_ROLE, _BASE, _REGISTRY_ADMIN, _grant, _seed

    _seed(db)
    _grant(db, _ADMIN_ROLE, ["dealer_kit.library.manage"])
    reg = vseed.registry(db)["trap_length"]
    _product_with(db, trap_length=150.0)
    icon = seed_asset(db, kind="icon")
    db.commit()
    try:
        res = _client_as(db, _REGISTRY_ADMIN).patch(f"{_BASE}/{reg.spec_key}", json={"value_icons": {"150": [icon.id]}})
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200, res.text
    assert res.json()["value_icons"] == {"150": [icon.id]}


def test_be7_the_registry_list_names_the_numeric_values_for_the_screen(db):
    """Chosen wire name: each numeric key row carries `numeric_values: ["150", "200", ...]` (sorted,
    normalised) so the Values and words tab can list them; other keys carry none or an empty list."""
    from tests.test_spec_registry_pr2_routes import _BASE, _MERCHANDISER, _seed

    _seed(db)
    reg = vseed.registry(db)
    _product_with(db, trap_length=200)
    _product_with(db, trap_length=150.0)
    db.commit()
    try:
        res = _client_as(db, _MERCHANDISER).get(_BASE)
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200, res.text
    listed = {k["spec_key"]: k for k in res.json()["keys"]}
    assert listed["trap_length"]["numeric_values"] == ["150", "200"]
    assert not listed["trap_type"].get("numeric_values")


# --------------------------------------------------------------------------- BE 8


def test_be8_a_whole_float_prints_without_the_point_zero():
    from app.services.dealer_kit.tag_data_service import _spec_raw_text

    assert _spec_raw_text(150.0) == "150"
    assert _spec_raw_text(150) == "150"
    assert _spec_raw_text(300.0) == "300"


def test_be8_other_numbers_print_with_str():
    from app.services.dealer_kit.tag_data_service import _spec_raw_text

    assert _spec_raw_text(150.5) == "150.5"
    assert _spec_raw_text(0.25) == "0.25"


def test_be8_booleans_and_text_are_unchanged():
    from app.services.dealer_kit.tag_data_service import _spec_raw_text

    assert _spec_raw_text(True) == "true"
    assert _spec_raw_text(False) == "false"
    assert _spec_raw_text("s_trap") == "s_trap"


def test_be8_a_stored_float_reaches_the_payload_raw_as_a_whole_number(db):
    from app.services.dealer_kit import tag_data_service

    vseed.registry(db)
    item = _product_with(db, trap_length=150.0)
    specs = tag_data_service.product_specs(db, item)
    assert next(s for s in specs if s["key"] == "trap_length")["raw"] == "150"
