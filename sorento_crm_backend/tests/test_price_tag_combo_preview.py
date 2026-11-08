"""PRICETAG-COMBO: the designer's Preview combo routes.

UAC: `documentation/plans/dealer-kit/price-tag-combo-template-fields-acceptance-criteria.md`
(AC-5.2, AC-5.3).

Written test-FIRST (PRINCIPLES.md Phase 2). `GET /api/v1/dealer-kit/tag-data/combos` and the
`combo_id` query on the product tag-data route do not exist; the cases are red as 404 /
missing `combo` key. Every field is asserted ON THE WIRE because `response_model` drops what
it does not declare. Auth pattern from `tests/test_dealer_kit_tag_data_routes.py`.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.company import Company

from tests import _ptag_combo_seed as seed
from tests._pg_fixture import blank_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)

SORENTO = seed.SORENTO
MOCHA = "00000000-0000-0000-0000-000000000002"
COMBOS_URL = "/api/v1/dealer-kit/tag-data/combos"
PRODUCT_URL = "/api/v1/dealer-kit/products/{id}/tag-data"

_DESIGNER_ID = "9f2c4b18-6d35-5e70-a91c-3b8e0d5f7a26"
_DESIGNER_ROLE = "4a8d6e02-7c19-5b43-8f26-1d9c5a3e0b74"
_OUTSIDER_ID = "1c7e3a95-4b28-5d61-9e03-6f2a8c4d5b19"


class _SigningBackend:
    def get_signed_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://cdn.test.invalid/{key}?Signature=stub"


@pytest.fixture(autouse=True)
def _signing_works(monkeypatch):
    from app.services import storage_router

    monkeypatch.setattr(storage_router, "get_backend", lambda provider: _SigningBackend())


def _seed_principals(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_DESIGNER_ROLE,
            slug="zzt_combo_preview_designer",
            name="ZZT Combo Preview Designer",
            description="Designs price tags",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(User(id=_DESIGNER_ID, email="zzt-combo-designer@test.com", name="Designer", status="ACTIVE"))
    db.add(User(id=_OUTSIDER_ID, email="zzt-combo-outsider@test.com", name="Outsider", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_DESIGNER_ID, role_id=_DESIGNER_ROLE))
    for slug in ("dealer_kit.tag_templates.view", "dealer_kit.price_tag_requests.view"):
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=_DESIGNER_ROLE, permission_id=perm_id))
    db.commit()


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_principals(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        _as(_DESIGNER_ID)
        with TestClient(app) as client:
            yield client, db, _as
        app.dependency_overrides.clear()


def _host_with_combo(db, name, *, stem="ZZPV", company_id=SORENTO, **fields):
    host = seed.product(db, stem, list_price="1000.00", company_id=company_id)
    part = seed.product(db, "ZZPVP", list_price="200.00", company_id=company_id)
    cb = seed.combo(db, host, name, parts=[{"product": part}], **fields)
    return host, cb


# --------------------------------------------------------------------------- AC-5.2


def test_ac_5_2_the_list_answers_name_and_host_code_without_ids_beyond_the_contract(api):
    client, db, _ = api
    host, cb = _host_with_combo(db, "ZZT Alpha pack")
    db.commit()

    response = client.get(COMBOS_URL, params={"query": "Alpha"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"data"}
    assert body["data"] == [
        {
            "combo_id": cb.id,
            "name": "ZZT Alpha pack",
            "host_product_id": host.id,
            "host_code": host.product_code,
        }
    ]


def test_ac_5_2_it_searches_by_host_code_too_case_insensitively(api):
    client, db, _ = api
    host, cb = _host_with_combo(db, "ZZT Beta pack", stem="ZZPVHOSTCODE")
    _host_with_combo(db, "ZZT Gamma pack")
    db.commit()

    response = client.get(COMBOS_URL, params={"query": host.product_code.lower()})
    assert response.status_code == 200, response.text
    assert [row["combo_id"] for row in response.json()["data"]] == [cb.id]


def test_ac_5_2_it_is_bounded_by_limit(api):
    client, db, _ = api
    for index in range(4):
        _host_with_combo(db, f"ZZT Bounded {index}")
    db.commit()

    response = client.get(COMBOS_URL, params={"query": "ZZT Bounded", "limit": 2})
    assert response.status_code == 200, response.text
    assert len(response.json()["data"]) == 2

    assert client.get(COMBOS_URL, params={"limit": 0}).status_code == 422
    assert client.get(COMBOS_URL, params={"limit": 101}).status_code == 422


def test_ac_5_2_an_empty_query_lists_combos_up_to_the_default_limit(api):
    client, db, _ = api
    _host_with_combo(db, "ZZT Listed")
    db.commit()
    response = client.get(COMBOS_URL)
    assert response.status_code == 200, response.text
    assert "ZZT Listed" in [row["name"] for row in response.json()["data"]]


def test_ac_5_2_another_companys_combo_is_not_returned(api):
    client, db, _ = api
    db.add(Company(id=MOCHA, name="ZZT Mocha", code=unique_code("MCH")[:20], is_active=True))
    db.flush()
    _host_with_combo(db, "ZZT Mine pack")
    _host_with_combo(db, "ZZT Theirs pack", company_id=MOCHA)
    db.commit()

    names = [row["name"] for row in client.get(COMBOS_URL, params={"query": "ZZT"}).json()["data"]]
    assert "ZZT Mine pack" in names
    assert "ZZT Theirs pack" not in names


def test_ac_5_2_a_caller_without_the_permission_is_refused(api):
    client, db, as_user = api
    _host_with_combo(db, "ZZT Hidden pack")
    db.commit()
    as_user(_OUTSIDER_ID)
    response = client.get(COMBOS_URL, params={"query": "Hidden"})
    assert response.status_code == 403, response.text


# --------------------------------------------------------------------------- AC-5.3


def _list_on_combo(db, combo, names):
    import uuid

    from app.models.accessory import Accessory, ProductComboAccessory

    for index, name in enumerate(names):
        item = Accessory(id=str(uuid.uuid4()), name=f"{name}", company_id=seed.SORENTO)
        db.add(item)
        db.flush()
        db.add(ProductComboAccessory(combo_id=combo.id, accessory_id=item.id, sort_order=index))
    db.flush()


def test_ac_5_3_a_combo_id_adds_the_same_combo_object_as_the_tag_data(api):
    client, db, _ = api
    host, cb = _host_with_combo(
        db, "ZZT Preview pack", description="Preview text"
    )
    _list_on_combo(db, cb, ["ZZT TAP", "ZZT WASTE"])
    db.commit()

    response = client.get(PRODUCT_URL.format(id=host.id), params={"combo_id": cb.id})
    assert response.status_code == 200, response.text
    combo = response.json()["combo"]
    assert combo is not None
    assert set(combo) == {"id", "name", "description", "free_items", "accessories", "accessory_box_style", "choices", "upgrades"}
    assert combo["id"] == cb.id
    assert combo["name"] == "ZZT Preview pack"
    assert combo["description"] == "Preview text"
    # PRICETAG-ACCESSORIES: free items are the combo's accessory list; the text is built from it.
    assert combo["free_items"] == "ZZT TAP, ZZT WASTE"
    assert [item["name"] for item in combo["accessories"]] == ["ZZT TAP", "ZZT WASTE"]


def test_ac_5_3_the_preview_lists_options_with_nothing_picked(api):
    client, db, _ = api
    host = seed.product(db, "ZZPVH", list_price="1000.00")
    white = seed.product(db, "ZZPVW", list_price="300.00")
    black = seed.product(db, "ZZPVB", list_price="400.00")
    cb = seed.combo(
        db,
        host,
        "ZZT Choice pack",
        parts=[
            {"product": white, "group": "Basin", "sell_price": Decimal("280.00")},
            {"product": black, "group": "Basin"},
        ],
    )
    db.commit()

    combo = client.get(PRODUCT_URL.format(id=host.id), params={"combo_id": cb.id}).json()["combo"]
    (group,) = combo["choices"]
    assert group["role"] == "Basin"
    by_code = {o["code"]: o for o in group["options"]}
    assert by_code[white.product_code]["sell_price"] == 280.0
    assert by_code[white.product_code]["list_price"] == 300.0
    assert by_code[black.product_code]["sell_price"] is None
    assert not any(o["picked"] for o in group["options"])


def test_ac_5_3_omitting_combo_id_answers_today_plus_combo_null(api):
    client, db, _ = api
    host, _cb = _host_with_combo(db, "ZZT Omitted pack")
    db.commit()
    response = client.get(PRODUCT_URL.format(id=host.id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert "combo" in body
    assert body["combo"] is None
    assert body["code"] == host.product_code


def test_ac_5_3_a_combo_of_another_product_answers_404(api):
    client, db, _ = api
    host, _cb = _host_with_combo(db, "ZZT One pack")
    _other_host, other_cb = _host_with_combo(db, "ZZT Two pack")
    db.commit()
    response = client.get(PRODUCT_URL.format(id=host.id), params={"combo_id": other_cb.id})
    assert response.status_code == 404, response.text


def test_ac_5_3_an_unknown_combo_id_answers_404(api):
    client, db, _ = api
    host, _cb = _host_with_combo(db, "ZZT Three pack")
    db.commit()
    response = client.get(PRODUCT_URL.format(id=host.id), params={"combo_id": str(uuid.uuid4())})
    assert response.status_code == 404, response.text


def test_ac_5_3_a_malformed_combo_id_answers_404(api):
    client, db, _ = api
    host, _cb = _host_with_combo(db, "ZZT Four pack")
    db.commit()
    response = client.get(PRODUCT_URL.format(id=host.id), params={"combo_id": "not-a-uuid"})
    assert response.status_code == 404, response.text


def test_ac_5_3_another_companys_combo_id_answers_404(api):
    client, db, _ = api
    db.add(Company(id=MOCHA, name="ZZT Mocha", code=unique_code("MCH")[:20], is_active=True))
    db.flush()
    host, _cb = _host_with_combo(db, "ZZT Mine pack")
    _theirs_host, theirs = _host_with_combo(db, "ZZT Theirs pack", company_id=MOCHA)
    db.commit()
    response = client.get(PRODUCT_URL.format(id=host.id), params={"combo_id": theirs.id})
    assert response.status_code == 404, response.text


def test_ac_5_3_the_preview_carries_the_combos_own_list_and_sell_price(api):
    client, db, _ = api
    host, cb = _host_with_combo(
        db, "ZZT Priced pack", list_price=Decimal("2000.00"), sell_price=Decimal("1500.00")
    )
    db.commit()
    body = client.get(PRODUCT_URL.format(id=host.id), params={"combo_id": cb.id}).json()
    assert body["list_price"] == 2000.0
    assert body["offer_price"] == 1500.0
    plain = client.get(PRODUCT_URL.format(id=host.id)).json()
    assert plain["list_price"] == 1000.0, "without a combo the host price is unchanged"
