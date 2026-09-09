""""Supplied with" companion rule CRUD (PLAN-scm-supplied-with-companions.md S3/S4).

UAC group A: `documentation/plans/scm/scm-supplied-with-companions-acceptance-criteria.md`.

Written test-FIRST (PRINCIPLES.md Phase 2, `/feature` step order): neither
`app/models/product_companion.py` nor `app/services/product_companion_service.py` exist yet, so
importing the model below fails the WHOLE FILE with one `ImportError` at collection - every case
here is red for that one reason until S3/S4 land, not for thirty unrelated ones.

Route contract (frontend already mocks it, Phase 1, committed - top of
`sorento_crm_frontend/.../products/services/productCompanionService.ts`):

    GET    /api/v1/master-data/product-companion-rules?companion_product_id={id}
    GET    /api/v1/master-data/product-companion-rules?host_product_id={id}
    POST   /api/v1/master-data/product-companion-rules   body ProductCompanionRuleWrite -> row (201)
    DELETE /api/v1/master-data/product-companion-rules/{id} -> 204

Gated on `master_data.products.view` (read) / `master_data.products.edit` (write) - the products
permission, per the plan's S4 and the FE contract comment - never a dedicated
`master_data.product_companions.*` slug, since the rule lives on the product page.

Auth pattern borrowed from `test_brands_select_company_filter.py` (monkeypatched
`UserPermissionService`, no role tables to seed).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.procurement import Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import User, UserStatus
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.user_service import UserPermissionService

# THE red import. Everything below fails to collect until `app/models/product_companion.py`
# exists with these two names (PLAN section 3.1).
from app.models.product_companion import (  # noqa: E402
    ProductCompanionRule,
    ProductCompanionRuleHost,
)

from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/master-data/product-companion-rules"
SORENTO = DEFAULT_COMPANY_ID
VIEW = "master_data.products.view"
EDIT = "master_data.products.edit"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _product(db, stem: str, company_id: str = SORENTO) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("u")[:20], uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=unique_code("cat")[:50], category_name="ZZT companion cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        company_id=company_id,
        product_code=unique_code(stem),
        product_name=f"ZZT {stem}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("10.00"),
    )
    db.add(row)
    db.flush()
    return row


def _supplier(db, company_id: str = SORENTO) -> Supplier:
    row = Supplier(
        id=_uid(),
        company_id=company_id,
        supplier_code=unique_code("sup"),
        supplier_name="ZZT supplier",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _rule(db, company_id, companion, hosts, *, supplier_id=None, ratio="1", is_active=True):
    """A rule seeded straight through the model, for the tests that read state the API
    already wrote rather than exercising the write path a second time (A1, A5, A6, A7)."""
    rule = ProductCompanionRule(
        id=_uid(),
        company_id=company_id,
        companion_product_id=companion.id,
        supplier_id=supplier_id,
        ratio=Decimal(ratio),
        is_active=is_active,
    )
    db.add(rule)
    db.flush()
    for host in hosts:
        db.add(ProductCompanionRuleHost(rule_id=rule.id, host_product_id=host.id))
    db.flush()
    return rule


def _install_overrides(db, caller: dict, company_id):
    def _override_db():
        yield db

    def _override_scope(_db=Depends(get_db)):
        scope = frozenset({company_id}) if company_id else None
        set_company_scope(_db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[get_current_user_or_api_key] = lambda: caller
    app.dependency_overrides[apply_company_scope] = _override_scope


def _clear_overrides():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_or_api_key, None)
    app.dependency_overrides.pop(apply_company_scope, None)


def _caller(db, allow: set[str], monkeypatch, *, company_id=SORENTO) -> TestClient:
    user = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('companion-caller')}@zzt.test",
        name="ZZT Companion Caller",
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    db.flush()
    caller = {"id": str(user.id), "email": user.email}

    _install_overrides(db, caller, company_id)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    return TestClient(app)


@pytest.fixture()
def world(db):
    """The UAC fixture sheet: company C (Sorento, the blank schema's default), supplier S1,
    products CKS1050 (host) and CKSW015 (companion)."""
    host = _product(db, "CKS1050")
    companion = _product(db, "CKSW015")
    supplier = _supplier(db)
    return {"host": host, "companion": companion, "supplier": supplier}


# --------------------------------------------------------------------------- A1, A5 - list


def test_a1_the_companions_own_list_names_its_hosts_supplier_and_ratio(db, world, monkeypatch):
    _rule(
        db, SORENTO, world["companion"], [world["host"]],
        supplier_id=world["supplier"].id, ratio="1.5000",
    )
    client = _caller(db, {VIEW}, monkeypatch)

    response = client.get(BASE, params={"companion_product_id": world["companion"].id})
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert len(rows) == 1
    row = rows[0]
    assert row["companion_product_id"] == world["companion"].id
    assert row["companion_item_code"] == world["companion"].product_code
    assert row["supplier_id"] == world["supplier"].id
    assert row["supplier_code"] == world["supplier"].supplier_code
    assert float(row["ratio"]) == 1.5
    assert [h["product_id"] for h in row["hosts"]] == [world["host"].id]
    assert row["hosts"][0]["item_code"] == world["host"].product_code


def test_a5_the_hosts_own_list_names_every_companion_riding_on_it(db, world, monkeypatch):
    """A rule with two hosts must be returned by BOTH hosts' own queries, each time
    naming every host on it - not only the one that was asked about."""
    second_host = _product(db, "Y")
    _rule(db, SORENTO, world["companion"], [world["host"], second_host])
    client = _caller(db, {VIEW}, monkeypatch)

    for host in (world["host"], second_host):
        response = client.get(BASE, params={"host_product_id": host.id})
        assert response.status_code == 200, response.text
        rows = response.json()["data"]
        assert len(rows) == 1
        host_ids = {h["product_id"] for h in rows[0]["hosts"]}
        assert host_ids == {world["host"].id, second_host.id}, (
            "asking from EITHER host must name the pair, not only the one asked about"
        )


# --------------------------------------------------------------------------- A2 - create


def test_a2_create_with_one_host_saves_and_reads_back(db, world, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    response = client.post(
        BASE,
        json={
            "companion_product_id": world["companion"].id,
            "host_product_ids": [world["host"].id],
            "supplier_id": None,
            "ratio": 1,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["supplier_id"] is None
    assert [h["product_id"] for h in body["hosts"]] == [world["host"].id]

    listed = client.get(BASE, params={"companion_product_id": world["companion"].id}).json()
    assert [row["id"] for row in listed["data"]] == [body["id"]], (
        "the list reflects the write without needing a reload"
    )


def test_a2_create_with_two_hosts_and_a_fractional_ratio(db, world, monkeypatch):
    second_host = _product(db, "Y")
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    response = client.post(
        BASE,
        json={
            "companion_product_id": world["companion"].id,
            "host_product_ids": [world["host"].id, second_host.id],
            "supplier_id": world["supplier"].id,
            "ratio": 0.5,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert float(body["ratio"]) == 0.5
    assert {h["product_id"] for h in body["hosts"]} == {world["host"].id, second_host.id}


# --------------------------------------------------------------------------- A3 - delete


def test_a3_delete_is_a_hard_delete(db, world, monkeypatch):
    rule = _rule(db, SORENTO, world["companion"], [world["host"]])
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    response = client.delete(f"{BASE}/{rule.id}")
    assert response.status_code == 204, response.text

    listed = client.get(BASE, params={"companion_product_id": world["companion"].id}).json()
    assert listed["data"] == []


# --------------------------------------------------------------------------- A4 - duplicate


def test_a4_the_same_companion_and_supplier_twice_is_409_naming_the_existing_rule(
    db, world, monkeypatch
):
    existing = _rule(
        db, SORENTO, world["companion"], [world["host"]], supplier_id=world["supplier"].id
    )
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    response = client.post(
        BASE,
        json={
            "companion_product_id": world["companion"].id,
            "host_product_ids": [world["host"].id],
            "supplier_id": world["supplier"].id,
            "ratio": 1,
        },
    )
    assert response.status_code == 409, response.text
    message = response.json()["detail"]["message"]
    assert world["host"].product_code in message or existing.id in message, (
        "the 409 must NAME the existing rule, not just refuse silently"
    )


def test_a4_a_null_supplier_conflicts_with_another_null_supplier_rule(db, world, monkeypatch):
    """NULL is a value here (the "any supplier" scope), so two NULL rules for the same
    companion collide exactly like two matching supplier ids would."""
    _rule(db, SORENTO, world["companion"], [world["host"]], supplier_id=None)
    client = _caller(db, {VIEW, EDIT}, monkeypatch)

    response = client.post(
        BASE,
        json={
            "companion_product_id": world["companion"].id,
            "host_product_ids": [world["host"].id],
            "supplier_id": None,
            "ratio": 1,
        },
    )
    assert response.status_code == 409, response.text


# --------------------------------------------------------------------------- A6 - RESTRICT


def test_a6_deleting_a_product_named_as_companion_is_refused(db, world, monkeypatch):
    from app.services.error_handler import AppException
    from app.services.product_service import ProductService

    rule = _rule(db, SORENTO, world["companion"], [world["host"]])

    with pytest.raises(AppException) as excinfo:
        ProductService(db).delete_product(world["companion"].id)
    assert excinfo.value.status_code == 409
    message = str(excinfo.value.detail)
    assert rule.id in message or world["host"].product_code in message, (
        "the refusal must NAME the rule, not just fail"
    )


def test_a6_deleting_a_product_named_as_host_is_refused(db, world, monkeypatch):
    from app.services.error_handler import AppException
    from app.services.product_service import ProductService

    _rule(db, SORENTO, world["companion"], [world["host"]])

    with pytest.raises(AppException) as excinfo:
        ProductService(db).delete_product(world["host"].id)
    assert excinfo.value.status_code == 409


# --------------------------------------------------------------------------- A7 - company scope


def test_a7_a_different_company_sees_none_of_these_rules(db, world, monkeypatch):
    other_company = Company(id=_uid(), name="ZZT Other Co", code=unique_code("CO")[:20])
    db.add(other_company)
    db.flush()
    _rule(db, SORENTO, world["companion"], [world["host"]])

    client = _caller(db, {VIEW}, monkeypatch, company_id=other_company.id)

    response = client.get(BASE, params={"companion_product_id": world["companion"].id})
    assert response.status_code == 200, response.text
    assert response.json()["data"] == [], (
        "company D must see none of company C's rules, whatever id it is asked about"
    )


# --------------------------------------------------------------------------- auth denial


def test_a_caller_with_neither_products_permission_is_refused_read_and_write(
    db, world, monkeypatch
):
    client = _caller(db, set(), monkeypatch)

    assert (
        client.get(BASE, params={"companion_product_id": world["companion"].id}).status_code
        == 403
    )
    assert (
        client.post(
            BASE,
            json={
                "companion_product_id": world["companion"].id,
                "host_product_ids": [world["host"].id],
                "supplier_id": None,
                "ratio": 1,
            },
        ).status_code
        == 403
    )


def test_a_view_only_caller_may_read_but_not_write(db, world, monkeypatch):
    """The write half is gated on `products.edit`, distinct from the read grant - a
    merchandiser who can only look must not be able to add a rule."""
    client = _caller(db, {VIEW}, monkeypatch)

    assert (
        client.get(BASE, params={"companion_product_id": world["companion"].id}).status_code
        == 200
    )
    response = client.post(
        BASE,
        json={
            "companion_product_id": world["companion"].id,
            "host_product_ids": [world["host"].id],
            "supplier_id": None,
            "ratio": 1,
        },
    )
    assert response.status_code == 403, response.text
