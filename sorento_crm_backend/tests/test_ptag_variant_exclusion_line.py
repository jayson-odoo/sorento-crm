"""PRICETAG-UPGRADE-VARIANTS BE tests 5 and 6: the line's `excluded_variant_ids` and the chooser lookup.

Written test-FIRST. Names fixed by the contract: field `excluded_variant_ids`, error code
`NOT_A_VARIANT` (422), staff route
`GET /api/v1/dealer-kit/price-tag-requests/variant-members/{product_id}`, portal route
`GET /lookups/variant-members/{product_id}` (also served under /my-requests), body
`{members: [{product_id, code, name, list_price, is_discontinued}], own_list_price}`.
"""
from __future__ import annotations

import uuid

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.error_handler import AppException

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests import _ptag_variant_seed as vseed
from tests._pg_fixture import blank_session
from tests.test_price_tag_combo_preview import _OUTSIDER_ID, api  # noqa: F401  (fixture)

CHOOSER = "/api/v1/dealer-kit/price-tag-requests/variant-members/{id}"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _submit(db, product, excluded=None):
    extra = {} if excluded is None else {"excluded_variant_ids": excluded}
    request = seed.submit_one(db, product, **extra)
    db.flush()
    return request


# --------------------------------------------------------------------------- BE 5


def test_be5_the_schemas_accept_the_field_and_default_to_empty():
    from app.schemas.price_tag import PriceTagRequestLineCreate

    ok = PriceTagRequestLineCreate(line_type="product", product_id=str(uuid.uuid4()),
                                   excluded_variant_ids=["a", "b"])
    assert ok.excluded_variant_ids == ["a", "b"]
    bare = PriceTagRequestLineCreate(line_type="product", product_id=str(uuid.uuid4()))
    assert bare.excluded_variant_ids == []


def test_be5_the_response_schema_declares_the_field():
    from app.schemas.price_tag import PriceTagRequestLineResponse

    assert "excluded_variant_ids" in PriceTagRequestLineResponse.model_fields


def test_be5_create_round_trips_and_deduplicates(db):
    fam = vseed.family(db)
    a, b = fam["SRTWC8354-SH-150"].id, fam["SRTWC8354-SH-UF-300"].id
    request = _submit(db, fam["SRTWC8354-SH"], [a, b, a])
    line = request.lines[0]
    assert sorted(line.excluded_variant_ids) == sorted([a, b])
    assert len(line.excluded_variant_ids) == 2


def test_be5_a_line_with_none_stores_an_empty_list(db):
    fam = vseed.family(db)
    assert _submit(db, fam["SRTWC8354-SH"]).lines[0].excluded_variant_ids == []


def test_be5_update_replaces_the_stored_list(db):
    from app.services.price_tag_request_service import PriceTagRequestService

    fam = vseed.family(db)
    request = _submit(db, fam["SRTWC8354-SH"], [fam["SRTWC8354-SH-150"].id])
    new = seed.line_dict(fam["SRTWC8354-SH"], excluded_variant_ids=[fam["SRTWC8354-SH-P"].id])
    PriceTagRequestService.replace_lines(db, request, [new])
    db.flush()
    db.expire_all()
    assert request.lines[0].excluded_variant_ids == [fam["SRTWC8354-SH-P"].id]


def test_be5_a_product_outside_the_tree_is_refused_with_not_a_variant(db):
    fam = vseed.family(db)
    stranger = seed.product(db, "ZZSTRANGER")
    with pytest.raises(AppException) as caught:
        _submit(db, fam["SRTWC8354-SH"], [stranger.id])
    assert caught.value.status_code == 422
    assert caught.value.code == "NOT_A_VARIANT"


def test_be5_a_sibling_branch_member_of_another_line_product_is_refused(db):
    fam = vseed.family(db)
    # -SH-150 is a member of -SH, not of -SH-UF.
    with pytest.raises(AppException) as caught:
        _submit(db, fam["SRTWC8354-SH-UF"], [fam["SRTWC8354-SH-150"].id])
    assert caught.value.code == "NOT_A_VARIANT"


def test_be5_the_line_product_itself_is_refused(db):
    fam = vseed.family(db)
    with pytest.raises(AppException) as caught:
        _submit(db, fam["SRTWC8354-SH"], [fam["SRTWC8354-SH"].id])
    assert caught.value.status_code == 422
    assert caught.value.code == "NOT_A_VARIANT"


def test_be5_update_also_refuses_a_non_member(db):
    from app.services.price_tag_request_service import PriceTagRequestService

    fam = vseed.family(db)
    request = _submit(db, fam["SRTWC8354-SH"])
    bad = seed.line_dict(fam["SRTWC8354-SH"], excluded_variant_ids=[str(uuid.uuid4())])
    with pytest.raises(AppException) as caught:
        PriceTagRequestService.replace_lines(db, request, [bad])
    assert caught.value.code == "NOT_A_VARIANT"


def test_be5_revise_schema_accepts_and_carries_the_field():
    from app.schemas.price_tag import PriceTagReviseLineIn
    from app.services.portal_revision_service import _convert_ptag_revise_line

    pid = str(uuid.uuid4())
    assert PriceTagReviseLineIn(product_id=pid, excluded_variant_ids=["x"]).excluded_variant_ids == ["x"]
    converted = _convert_ptag_revise_line({"product_id": pid, "quantity": 1, "excluded_variant_ids": ["x"]}, 0)
    assert converted["excluded_variant_ids"] == ["x"]
    absent = _convert_ptag_revise_line({"product_id": pid, "quantity": 1}, 0)
    assert "excluded_variant_ids" not in absent, "left off when not sent, so carry-over can tell cleared from absent"


# --------------------------------------------------------------------------- BE 6


def test_be6_staff_chooser_lists_members_with_prices_and_discontinued_flags(api):
    client, db, _as = api
    fam = vseed.family(db)
    fam["SRTWC8354-SH-P"].is_discontinued = True
    fam["SRTWC8354-SH-200"].is_active = False
    fam["SRTWC8354-SH-UF-300"].list_price = 1800
    db.commit()
    res = client.get(CHOOSER.format(id=fam["SRTWC8354-SH"].id))
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == {"members", "own_list_price"}
    assert float(body["own_list_price"]) == 1750.0
    by_code = {m["code"]: m for m in body["members"]}
    assert "SRTWC8354-SH-200" not in by_code, "inactive is left out"
    assert by_code["SRTWC8354-SH-P"]["is_discontinued"] is True, "discontinued is listed, flagged"
    assert by_code["SRTWC8354-SH-150"]["is_discontinued"] is False
    assert float(by_code["SRTWC8354-SH-UF-300"]["list_price"]) == 1800.0
    assert set(by_code["SRTWC8354-SH-150"]) == {"product_id", "code", "name", "list_price", "is_discontinued"}
    assert len(by_code) == 6


def test_be6_staff_chooser_for_a_leaf_is_empty(api):
    client, db, _as = api
    fam = vseed.family(db)
    db.commit()
    res = client.get(CHOOSER.format(id=fam["SRTWC8354-SH-150"].id))
    assert res.status_code == 200, res.text
    assert res.json()["members"] == []


def test_be6_staff_chooser_is_forbidden_without_the_permission(api):
    client, db, _as = api
    fam = vseed.family(db)
    db.commit()
    _as(_OUTSIDER_ID)
    res = client.get(CHOOSER.format(id=fam["SRTWC8354-SH"].id))
    assert res.status_code == 403, res.text


def test_be6_staff_chooser_rejects_a_malformed_product_id(api):
    client, _db, _as = api
    res = client.get(CHOOSER.format(id="not-a-uuid"))
    assert res.status_code in (404, 422), res.text
    # A routed refusal carries a structured body; the unrouted default is {"detail": "Not Found"}.
    assert res.json().get("detail") != "Not Found", "the route does not exist yet"


def test_be6_portal_chooser_answers_the_same_body(world):
    from tests import _portal_p4_support as s
    from tests._portal_p4_pt_support import LOOK

    fam = vseed.family(world.sc.db)
    world.sc.db.commit()
    res = s.ok(world.rep.me.call("GET", f"{LOOK}/variant-members/{fam['SRTWC8354-SH'].id}")).json()
    assert set(res) == {"members", "own_list_price"}
    assert len(res["members"]) == 7
    assert float(res["own_list_price"]) == 1750.0


def test_be6_portal_create_round_trips_the_unticked_ids(world):
    from tests import _portal_p4_support as s
    from tests._portal_p4_pt_support import SUB

    fam = vseed.family(world.sc.db)
    world.sc.db.commit()
    gone = fam["SRTWC8354-SH-UF-300"].id
    body = world.body(lines=[{"line_type": "product", "product_id": fam["SRTWC8354-SH"].id,
                              "quantity": 1, "excluded_variant_ids": [gone]}])
    made = s.ok(world.rep.me.call("POST", SUB, json=body), 201).json()
    assert made["lines"][0]["excluded_variant_ids"] == [gone]
    bad = world.body(lines=[{"line_type": "product", "product_id": fam["SRTWC8354-SH"].id,
                             "quantity": 1, "excluded_variant_ids": [fam["SRTWC8354-SH"].id]}])
    res = world.rep.me.call("POST", SUB, json=bad)
    assert res.status_code == 422, res.text
    assert "NOT_A_VARIANT" in res.text


from tests._portal_p4_pt_support import world  # noqa: E402,F401  (fixture)
from tests._portal_p4_support import scene  # noqa: E402,F401  (fixture)
