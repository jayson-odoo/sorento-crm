"""PRICETAG-UPGRADE-VARIANTS BE tests 3 and 4: `variant_members` and the tag payload `variants`.

Written test-FIRST. Chosen module: `app/services/dealer_kit/variant_service.py` with
`variant_members(db, product_id) -> list[dict]`. Payload key: `variants: [{product_id, code, specs}]`
on a request line row and on `product_tag_data` (designer preview). Postgres only, own seed chain.
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.company import Company
from app.models.base import set_company_scope

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests import _ptag_variant_seed as vseed
from tests._pg_fixture import blank_session, unique_code

MOCHA = "00000000-0000-0000-0000-000000000002"


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


def _members(db, product):
    from app.services.dealer_kit import variant_service

    return variant_service.variant_members(db, product.id)


# --------------------------------------------------------------------------- BE 3


def test_be3_the_whole_family_comes_back_ordered_by_code(db):
    fam = vseed.family(db)
    got = _members(db, fam["SRTWC8354-SH"])
    assert [m["code"] for m in got] == vseed.MEMBER_CODES
    assert len(got) == 7


def test_be3_each_member_carries_the_contract_fields(db):
    fam = vseed.family(db)
    fam["SRTWC8354-SH-P"].is_discontinued = True
    fam["SRTWC8354-SH-200"].is_active = False
    db.flush()
    by_code = {m["code"]: m for m in _members(db, fam["SRTWC8354-SH"])}
    member = by_code["SRTWC8354-SH-150"]
    assert set(member) >= {"product_id", "code", "name", "list_price", "is_discontinued", "is_active"}
    assert member["product_id"] == fam["SRTWC8354-SH-150"].id
    assert float(member["list_price"]) == 1750.0
    assert by_code["SRTWC8354-SH-P"]["is_discontinued"] is True
    assert by_code["SRTWC8354-SH-200"]["is_active"] is False


def test_be3_a_variant_line_lists_its_whole_family_but_itself(db):
    fam = vseed.family(db)
    got = [m["code"] for m in _members(db, fam["SRTWC8354-SH-UF"])]
    assert got == sorted(code for code in vseed.FAMILY if code != "SRTWC8354-SH-UF")


def test_be3_a_leaf_variant_lists_its_family_siblings(db):
    fam = vseed.family(db)
    got = [m["code"] for m in _members(db, fam["SRTWC8354-SH-150"])]
    assert "SRTWC8354-SH" in got and "SRTWC8354-SH-150" not in got
    assert len(got) == 7


def test_be3_a_product_with_no_family_has_no_members(db):
    vseed.family(db)
    lone = vseed.shapes.prod(db, "NOFAMILY-X", list_price="10.00")  # no digit before the dash: no family
    db.flush()
    assert lone.family_code is None
    assert _members(db, lone) == []


def test_be3_a_variant_link_outside_the_family_is_not_a_member(db):
    fam = vseed.family(db)
    linked = vseed.shapes.prod(db, "SRTBA9999-LINKED", list_price="10.00")
    linked.variant_of_id = fam["SRTWC8354-SH"].id
    db.flush()
    assert "SRTBA9999-LINKED" not in [m["code"] for m in _members(db, fam["SRTWC8354-SH"])]


def test_be3_a_hand_set_family_groups_too(db):
    fam = vseed.family(db)
    odd = vseed.shapes.prod(db, "SRTWC9999-ODD", list_price="10.00")
    odd.family_code = "SRTWC8354"
    odd.family_code_manual = True
    db.flush()
    assert "SRTWC9999-ODD" in [m["code"] for m in _members(db, fam["SRTWC8354-SH"])]


def test_be3_another_companys_product_never_appears(db):
    db.add(Company(id=MOCHA, name="ZZT Mocha", code=unique_code("MCH")[:20], is_active=True))
    db.flush()
    fam = vseed.family(db)
    vseed.shapes.prod(db, "SRTWC8354-SH-THEIRS", list_price="10.00", company_id=MOCHA)
    db.flush()
    set_company_scope(db, frozenset({vseed.SORENTO}))
    codes = [m["code"] for m in _members(db, fam["SRTWC8354-SH"])]
    assert "SRTWC8354-SH-THEIRS" not in codes
    assert len(codes) == 7


# --------------------------------------------------------------------------- BE 4


def _line_row(db, base, excluded=None):
    request = seed.submit_one(db, base)
    db.flush()
    if excluded is not None:
        line = request.lines[0]
        line.excluded_variant_ids = excluded
        db.flush()
    return seed.rows(db, request)[0]


def test_be4_a_line_row_lists_every_live_member_with_specs_and_raw(db):
    fam = vseed.family(db)
    row = _line_row(db, fam["SRTWC8354-SH"])
    assert "variants" in row, "the tag row has no `variants` key"
    assert sorted(v["code"] for v in row["variants"]) == vseed.MEMBER_CODES
    uf300 = next(v for v in row["variants"] if v["code"] == "SRTWC8354-SH-UF-300")
    assert uf300["product_id"] == fam["SRTWC8354-SH-UF-300"].id
    by_key = {s["key"]: s for s in uf300["specs"]}
    assert by_key["trap_length"]["raw"] == "300"
    assert by_key["trap_type"]["raw"] == "s_trap"
    assert by_key["seat_material"]["raw"] == "uf"


def test_be4_discontinued_and_inactive_members_are_left_out(db):
    fam = vseed.family(db)
    fam["SRTWC8354-SH-P"].is_discontinued = True
    fam["SRTWC8354-SH-200"].is_active = False
    db.flush()
    codes = [v["code"] for v in _line_row(db, fam["SRTWC8354-SH"])["variants"]]
    assert "SRTWC8354-SH-P" not in codes
    assert "SRTWC8354-SH-200" not in codes
    assert len(codes) == 5


def test_be4_excluded_variant_ids_are_left_out_on_a_line(db):
    fam = vseed.family(db)
    gone = fam["SRTWC8354-SH-UF-300"].id
    codes = [v["code"] for v in _line_row(db, fam["SRTWC8354-SH"], [gone])["variants"]]
    assert "SRTWC8354-SH-UF-300" not in codes
    assert len(codes) == 6


def test_be4_a_leaf_line_carries_its_family_siblings(db):
    fam = vseed.family(db)
    codes = sorted(v["code"] for v in _line_row(db, fam["SRTWC8354-SH-150"])["variants"])
    assert codes == sorted(code for code in vseed.FAMILY if code != "SRTWC8354-SH-150")


def test_be4_the_designer_preview_data_carries_variants_without_any_exclusion(db):
    from app.services.dealer_kit import tag_data_service

    fam = vseed.family(db)
    fam["SRTWC8354-SH-P"].is_discontinued = True
    db.flush()
    data = tag_data_service.product_tag_data(db, fam["SRTWC8354-SH"], tag_data_service.staff_viewer())
    assert "variants" in data
    codes = sorted(v["code"] for v in data["variants"])
    assert codes == [c for c in vseed.MEMBER_CODES if c != "SRTWC8354-SH-P"]
    assert all(any(s["key"] == "trap_length" and "raw" in s for s in v["specs"]) for v in data["variants"])
