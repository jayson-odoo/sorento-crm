"""PRICETAG-UPGRADE-VARIANTS review fix round 1: items 3, 4, 5b, 6, 7 and 8.

3. Icons on a numeric value no product holds any more survive the next save.
4. One normaliser: a legacy "150.0" string on a numeric key reads raw "150".
5b. A pinned row keeps its `variants` and its upgrade `topup_amount` (AC-U10, AC-F2c).
6. The numeric value read narrows by the GIN-indexed `?|` before `jsonb_each`.
7. The variant walk stops at MAX_MEMBERS and reads member specs in one query.
8. An unticked id longer than a UUID is a 422, never a database error.
Postgres only, own seed chain.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import event

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


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)
    monkeypatch.setattr(
        "app.services.dealer_kit.product_images.resolve_signed_url",
        lambda path, **_kwargs: f"https://signed.example.test/{path.rsplit('/', 1)[-1]}",
    )


def _product_with(db, **values):
    item = seed.product(db, "ZZNUM")
    vseed.set_specs(db, item, **values)
    return item


# --------------------------------------------------------------------------- 3


def test_3_icons_on_a_value_no_product_holds_any_more_are_kept(db):
    from app.services.dealer_kit.asset_service import clean_value_icons, feature_icon_rules, prune_value_icons

    reg = vseed.registry(db)["trap_length"]
    _product_with(db, trap_length=150)
    six, twelve = seed_asset(db, kind="icon"), seed_asset(db, kind="icon")
    reg.value_icons = {"300": [twelve.id]}  # set while a 300 mm product existed
    db.flush()

    saved = clean_value_icons(db, reg, {"150": [six.id], "300": [twelve.id]})
    assert saved == {"150": [six.id], "300": [twelve.id]}

    reg.value_icons = saved
    db.flush()
    assert {r["values"][0] for r in feature_icon_rules(db) if r["spec_key"] == "trap_length"} == {"150", "300"}
    prune_value_icons(reg)
    assert "300" in (reg.value_icons or {})


def test_3_the_registry_list_shows_the_stored_value_beside_the_held_ones(db):
    from app.services.dealer_kit.asset_service import numeric_value_keys

    reg = vseed.registry(db)["trap_length"]
    _product_with(db, trap_length=200)
    _product_with(db, trap_length=150)
    reg.value_icons = {"300": [seed_asset(db, kind="icon").id]}
    db.flush()
    assert numeric_value_keys(reg) == ["150", "200", "300"]


# --------------------------------------------------------------------------- 4


def test_4_a_legacy_string_on_a_numeric_key_reads_the_normalised_raw(db):
    from app.services.dealer_kit import tag_data_service
    from app.services.dealer_kit.asset_service import _numeric_text

    vseed.registry(db)
    item = _product_with(db, trap_length="150.0", trap_type="s_trap")
    specs = {s["key"]: s for s in tag_data_service.product_specs(db, item)}
    assert specs["trap_length"]["raw"] == "150" == _numeric_text("150.0")
    assert specs["trap_type"]["raw"] == "s_trap", "an enum value is read as stored"
    assert tag_data_service._spec_raw_text(True) == "true"


def test_4_the_two_normalisers_agree():
    from app.services.dealer_kit.asset_service import _numeric_text
    from app.services.dealer_kit.tag_data_service import _spec_raw_text

    for value in (150, 150.0, 300.0, 150.5, 0.25, 1000):
        assert _spec_raw_text(value) == _numeric_text(value)


# --------------------------------------------------------------------------- 5b


def test_5b_a_pinned_row_keeps_its_variants_and_upgrade_topup(db):
    from app.services.dealer_kit import tag_data_service

    fam = vseed.family(db)
    request = seed.submit_one(db, fam["SRTWC8354-SH"])
    db.flush()
    first = tag_data_service.resolve_request_line_data(db, request)[0]  # pins on first read
    assert len(first["variants"]) == 7

    fam["SRTWC8354-SH-UF-300"].is_discontinued = True
    db.flush()
    again = tag_data_service.resolve_request_line_data(db, request)[0]
    assert sorted(v["code"] for v in again["variants"]) == vseed.MEMBER_CODES, "the pin froze the members"


def test_5b_a_pinned_upgrade_row_keeps_its_topup(db):
    from app.services.dealer_kit import tag_data_service

    s = vseed.sink_combo(db)
    request = seed.submit_one(db, s["host"], s["combo"], [{"product_id": s["fixed"].id}])
    db.flush()
    (up,) = tag_data_service.resolve_request_line_data(db, request)[0]["slots"]["upgrades"]
    assert float(up["topup_amount"]) == 150.0

    for part in s["combo"].parts:
        if part.is_upgrade:
            part.topup_amount = Decimal("175.00")
    db.flush()
    (up,) = tag_data_service.resolve_request_line_data(db, request)[0]["slots"]["upgrades"]
    assert float(up["topup_amount"]) == 150.0, "a top-up edit reaches a pinned tag only on re-pin"


# --------------------------------------------------------------------------- 6


def test_6_the_numeric_read_narrows_by_the_indexed_key_test(db):
    from app.services.dealer_kit.asset_service import numeric_spec_values_by_key

    vseed.registry(db)
    _product_with(db, trap_length=150)
    statements: list[str] = []

    def spy(conn, cursor, statement, *args):
        statements.append(statement)

    engine = db.get_bind().engine
    event.listen(engine, "before_cursor_execute", spy)
    try:
        assert numeric_spec_values_by_key(db, ["trap_length", "seat_height"]) == {"trap_length": ["150"]}
    finally:
        event.remove(engine, "before_cursor_execute", spy)
    (sql,) = [s for s in statements if "jsonb_each" in s]
    assert "?|" in sql and sql.index("?|") < sql.index("k.key = ANY")


# --------------------------------------------------------------------------- 7


def test_7_the_walk_stops_at_the_member_cap(db, monkeypatch):
    from app.services.dealer_kit import variant_service

    fam = vseed.family(db)
    monkeypatch.setattr(variant_service, "MAX_MEMBERS", 3)
    assert len(variant_service.variant_members(db, fam["SRTWC8354-SH"].id)) == 3


def test_7_member_specs_are_read_in_one_query(db):
    from app.services.dealer_kit import variant_service

    fam = vseed.family(db)
    db.flush()
    statements: list[str] = []

    def spy(conn, cursor, statement, *args):
        statements.append(statement)

    engine = db.get_bind().engine
    event.listen(engine, "before_cursor_execute", spy)
    try:
        got = variant_service.tag_variants(db, fam["SRTWC8354-SH"].id)
    finally:
        event.remove(engine, "before_cursor_execute", spy)
    assert len(got) == 7
    # Table names arrive schema-qualified, so a statement is told apart by its selected columns.
    assert sum("AS product_specifications_values" in s for s in statements) == 1
    assert sum("AS product_spec_registry_spec_key" in s for s in statements) == 1


# --------------------------------------------------------------------------- 8


def test_8_an_overlong_id_is_refused_by_the_schemas():
    from app.schemas.price_tag import PriceTagRequestLineCreate, PriceTagReviseLineIn, TagPreviewLineIn

    long_id = "x" * 37
    with pytest.raises(ValidationError):
        PriceTagRequestLineCreate(line_type="product", product_id="p", excluded_variant_ids=[long_id])
    with pytest.raises(ValidationError):
        PriceTagReviseLineIn(product_id="p", excluded_variant_ids=[long_id])
    with pytest.raises(ValidationError):
        TagPreviewLineIn(key="k", line_type="product", product_id="p", excluded_variant_ids=[long_id])


def test_8_an_overlong_id_in_a_revise_is_a_422():
    from app.services.error_handler import AppException
    from app.services.portal_revision_service import _convert_ptag_revise_line

    with pytest.raises(AppException) as caught:
        _convert_ptag_revise_line({"product_id": "p", "quantity": 1, "excluded_variant_ids": ["x" * 37]}, 0)
    assert caught.value.status_code == 422
