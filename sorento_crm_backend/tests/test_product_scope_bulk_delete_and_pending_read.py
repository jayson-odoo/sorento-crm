"""Product bulk delete and the pending-action read stay inside the caller's company.

Two holes, one rule:

* `DELETE /master-data/products/bulk` used a bulk `query(...).delete()`. The company
  scope filter (`app/services/company_scope.py`) applies to ORM SELECTs only, so the
  bulk DELETE reached every company's rows by id. Bulk delete now loads the rows
  through the scoped read and deletes each one with the guards a single delete runs.
* `GET /pending-actions/current` read `sla_form_actions` (no company column) by entity
  id alone, so any signed-in user could read another company's countdown and the
  `error_text` of its failed action. It now answers only for a row whose stored
  requester scope overlaps the reader's.

Postgres only, on the blank scratch schema, seeding its own chain.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.base import company_scope
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.sla import SlaFormAction
from app.services.form_action_service import FormActionService
from tests._pg_fixture import blank_session, unique_code

from app.services import record_actions  # noqa: F401  (registers the record actions)

_SORENTO = "00000000-0000-0000-0000-000000000001"
_ACTOR_ID = "3c4d5e6f-7a8b-4c9d-8e0f-1a2b3c4d5e6f"
_ROLE_ID = "4d5e6f7a-8b9c-4d0e-9f1a-2b3c4d5e6f7a"

BULK = "/api/v1/master-data/products/bulk"
CURRENT = "/api/v1/pending-actions/current"

_SLUGS = (
    "master_data.products.view",
    "master_data.products.bulk_delete",
    "master_data.brands.delete",
)


def _seed_actor(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_ROLE_ID,
            slug="zzt_product_scope",
            name="zzt_product_scope",
            description="",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(User(id=_ACTOR_ID, email="zzt-product-scope@test.com", name="Pat Scope", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_ACTOR_ID, role_id=_ROLE_ID))
    for slug in _SLUGS:
        permission_id = str(uuid.uuid4())
        db.add(UserPermission(id=permission_id, slug=slug, name=slug, description=""))
        db.flush()
        db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=_ROLE_ID, permission_id=permission_id))
    db.commit()


@pytest.fixture
def api():
    """One session, one signed-in user, and a switchable company scope (the request's
    and the session's together, so rows created after `_in_company` are stamped to it)."""
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_actor(db)
        other_company = str(uuid.uuid4())
        db.add(Company(id=other_company, name="ZZT other co", code=unique_code("ZZTC")))
        db.commit()

        here = {"company": _SORENTO}

        def _override_get_db():
            yield db

        async def _override_scope():
            scope = frozenset({here["company"]})
            set_company_scope(db, scope)
            return scope

        principal = {"id": _ACTOR_ID, "email": "zzt-product-scope@test.com"}
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def _in_company(company_id: str):
            here["company"] = company_id
            set_company_scope(db, frozenset({company_id}))

        yield db, _in_company, other_company

        app.dependency_overrides.clear()


def _product(db) -> str:
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="Category"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each")
    db.add_all([category, uom])
    db.flush()
    code = unique_code("ZZTP")
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=0,
        is_active=True,
    )
    db.add(row)
    db.commit()
    return row.id


def _exists(db, product_id: str) -> bool:
    db.expire_all()
    with company_scope(db, None):
        return db.query(Product).filter(Product.id == product_id).first() is not None


def _bulk_delete(client: TestClient, ids):
    return client.request("DELETE", BULK, json={"ids": ids})


# --------------------------------------------------------------------------- #
# Bulk delete                                                                 #
# --------------------------------------------------------------------------- #


def test_bulk_delete_leaves_another_companys_product_alone(api):
    db, _in_company, other = api
    _in_company(other)
    theirs = _product(db)
    _in_company(_SORENTO)

    with TestClient(app) as client:
        res = _bulk_delete(client, [theirs])
    assert res.status_code == 200, res.text
    assert res.json()["deleted_count"] == 0
    assert _exists(db, theirs)


def test_bulk_delete_of_a_mixed_list_deletes_only_own_company(api):
    db, _in_company, other = api
    _in_company(other)
    theirs = _product(db)
    _in_company(_SORENTO)
    mine = _product(db)

    with TestClient(app) as client:
        res = _bulk_delete(client, [mine, theirs])
    assert res.status_code == 200, res.text
    assert res.json()["deleted_count"] == 1
    assert not _exists(db, mine)
    assert _exists(db, theirs)


def test_bulk_delete_still_deletes_own_company_products(api):
    db, _in_company, _other = api
    a, b = _product(db), _product(db)

    with TestClient(app) as client:
        res = _bulk_delete(client, [a, b])
    assert res.status_code == 200, res.text
    assert res.json()["deleted_count"] == 2
    assert not _exists(db, a)
    assert not _exists(db, b)


def test_bulk_delete_runs_the_single_delete_guards_and_deletes_nothing(api):
    """A product a companion rule holds refuses with the single delete's 409, and the
    batch is all-or-nothing: the free product beside it is not deleted either."""
    from decimal import Decimal

    from app.models.product_companion import ProductCompanionRule, ProductCompanionRuleHost

    db, _in_company, _other = api
    companion, host, free = _product(db), _product(db), _product(db)
    rule = ProductCompanionRule(
        id=str(uuid.uuid4()),
        company_id=_SORENTO,
        companion_product_id=companion,
        supplier_id=None,
        ratio=Decimal("1"),
        is_active=True,
    )
    db.add(rule)
    db.flush()
    db.add(ProductCompanionRuleHost(rule_id=rule.id, host_product_id=host))
    db.commit()

    with TestClient(app) as client:
        res = _bulk_delete(client, [free, companion])
    assert res.status_code == 409, res.text
    assert _exists(db, free)
    assert _exists(db, companion)


# --------------------------------------------------------------------------- #
# GET /pending-actions/current                                                #
# --------------------------------------------------------------------------- #


def _brand(db) -> str:
    brand = Brand(id=str(uuid.uuid4()), brand_code=unique_code("ZZTB"), brand_name="ZZT brand")
    db.add(brand)
    db.commit()
    return brand.id


def _park_brand_delete(client: TestClient, brand_id: str) -> str:
    res = client.post(
        "/api/v1/pending-actions",
        json={"action_key": "brand.delete", "entity_type": "brand", "entity_id": brand_id, "payload": {}},
    )
    assert res.status_code == 202, res.text
    return res.json()["id"]


def _current(client: TestClient, brand_id: str) -> dict:
    res = client.get(CURRENT, params={"entity_type": "brand", "entity_id": brand_id})
    assert res.status_code == 200, res.text
    return res.json()


def test_current_hides_another_companys_pending_action(api):
    db, _in_company, other = api
    _in_company(other)
    theirs = _brand(db)
    with TestClient(app) as client:
        _park_brand_delete(client, theirs)
        _in_company(_SORENTO)
        body = _current(client, theirs)
    assert body["pending"] is None
    assert body["last_outcome"] is None


def test_current_hides_another_companys_failed_outcome(api):
    """The failure text of an action another company parked is not readable by id."""
    db, _in_company, other = api
    _in_company(other)
    theirs = _brand(db)
    with TestClient(app) as client:
        action_id = _park_brand_delete(client, theirs)
    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"status": "failed", "error_text": "ZZT secret reason", "resolved_at": datetime.utcnow()},
        synchronize_session=False,
    )
    db.commit()

    _in_company(_SORENTO)
    with TestClient(app) as client:
        body = _current(client, theirs)
    assert body["pending"] is None
    assert body["last_outcome"] is None


def test_current_still_shows_own_companys_pending_and_outcome(api):
    db, _in_company, _other = api
    mine = _brand(db)
    with TestClient(app) as client:
        action_id = _park_brand_delete(client, mine)
        body = _current(client, mine)
        assert body["pending"] is not None
        assert body["pending"]["id"] == action_id

        db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
            {"commit_at": datetime.utcnow() - timedelta(seconds=1)}, synchronize_session=False
        )
        db.commit()
        body = _current(client, mine)
    assert body["pending"] is None
    assert body["last_outcome"] is not None
    assert body["last_outcome"]["id"] == action_id
    assert body["last_outcome"]["status"] == "committed"


def test_current_shows_every_company_to_an_all_companies_reader(api):
    db, _in_company, other = api
    _in_company(other)
    theirs = _brand(db)
    with TestClient(app) as client:
        action_id = _park_brand_delete(client, theirs)

    from app.services.company_scope_resolver import apply_company_scope
    from app.models.base import set_company_scope

    async def _all_companies():
        set_company_scope(db, None)
        return None

    app.dependency_overrides[apply_company_scope] = _all_companies
    with TestClient(app) as client:
        body = _current(client, theirs)
    assert body["pending"] is not None
    assert body["pending"]["id"] == action_id


def _grant(db, user_id: str, company_id: str) -> None:
    from app.models.company import UserCompany

    db.add(UserCompany(user_id=user_id, company_id=company_id))
    db.commit()


def test_current_hides_a_keyless_row_whose_requester_is_granted_another_company(api):
    """A row without a stored scope (an immediate action, or one parked before the key
    existed) falls back to its requester's explicit company grants."""
    from app.models.user import User

    db, _in_company, other = api
    stranger = str(uuid.uuid4())
    db.add(User(id=stranger, email=f"{stranger}@zzt.test", name="Other Co", status="ACTIVE"))
    db.commit()
    _grant(db, stranger, other)
    _grant(db, _ACTOR_ID, _SORENTO)

    brand_id = _brand(db)
    row = SlaFormAction(
        action_key="brand.delete",
        source_entity_type="brand",
        source_entity_id=brand_id,
        payload_json={},
        requested_by_id=stranger,
        status="failed",
        error_text="ZZT keyless reason",
        resolved_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()

    with TestClient(app) as client:
        assert _current(client, brand_id)["last_outcome"] is None

    row.requested_by_id = _ACTOR_ID
    db.commit()
    with TestClient(app) as client:
        assert _current(client, brand_id)["last_outcome"]["id"] == row.id


def test_parking_on_another_companys_counting_down_record_does_not_echo_it(api):
    """A same-key park on a record another company is counting down does not answer with
    that company's action id and timing. Since the park-time visibility check
    (tests/test_bulk_delete_company_scope.py) the record itself is not found."""
    db, _in_company, other = api
    _in_company(other)
    theirs = _brand(db)
    with TestClient(app) as client:
        their_action = _park_brand_delete(client, theirs)
        _in_company(_SORENTO)
        res = client.post(
            "/api/v1/pending-actions",
            json={"action_key": "brand.delete", "entity_type": "brand", "entity_id": theirs, "payload": {}},
        )
    assert res.status_code == 404, res.text
    assert their_action not in res.text
