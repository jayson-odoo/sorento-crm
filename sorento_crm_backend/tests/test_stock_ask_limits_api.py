"""S1 (PLAN-chatbot-stock-ask-v2-24sep.md) - the four X/Y columns, the migration's
permission slugs + grant sweep, and the category/product PUT+GET contract that gates
editing them behind `master_data.chatbot_stock_limits.edit`.

Harness copied from `tests/test_product_exclude_from_planning.py` (the closest existing
"a new scalar column reaches Response on GET/PUT" pin) for the TestClient/dependency-
override idiom, and from `tests/test_migration_414_product_set_grant_sweep.py` for the
"load the migration module by path, run its upgrade() against a blank Postgres schema
inside a rolled-back transaction" idiom used for the sweep assertions - the AC-SA104
target migration (`sa2_0001_xy_columns`) is only ever exercised as CODE here, never
assumed to already be stamped on whatever database CI happens to be pointed at.

Postgres only (`tests/_pg_fixture.py`); every row is a fresh, marker-prefixed insert -
CI's database starts empty.

AC-SA103 to AC-SA108.
"""
from __future__ import annotations

import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    get_db,
    get_external_api_user,
)
from app.main import app
from app.models.base import set_company_scope
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import User, UserRole, UserRoleAssignment, UserPermission, UserRolePermission
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.company_scope_resolver import apply_company_scope
from tests._pg_fixture import blank_session, unique_code
from tests.scm.conftest import requires_pg  # noqa: F401 - pytest fixture import

pytestmark = requires_pg

SORENTO_ID = DEFAULT_COMPANY_ID
STEM = "ZZTSAL"

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions" / "sa2_0001_xy_columns.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_sa2_0001", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration(db, direction: str = "upgrade") -> None:
    """Run the migration body against this session's own connection, inside the
    transaction `blank_session` rolls back - mirrors
    `test_migration_414_product_set_grant_sweep.py::_run`."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        yield session


@pytest.fixture
def world(db):
    uom_id = str(uuid.uuid4())
    cat_id = str(uuid.uuid4())
    db.add(UnitOfMeasure(id=uom_id, uom_code=unique_code("U")[:20], uom_name="Each"))
    db.add(ProductCategory(id=cat_id, category_code=unique_code("C")[:50], category_name="ZZT Category"))
    db.flush()

    pid = str(uuid.uuid4())
    db.add(
        Product(
            id=pid, product_code=unique_code("P"), product_name="ZZT Product",
            category_id=cat_id, base_uom_id=uom_id, list_price=Decimal("10.00"),
            is_active=True, company_id=SORENTO_ID,
        )
    )
    db.commit()
    return {"uom_id": uom_id, "cat_id": cat_id, "pid": pid}


@pytest.fixture
def api(db):
    """A TestClient whose principal is switchable per-call via the returned dict's
    ``user_id`` key - several tests in this file need more than one caller against the
    same seeded world."""
    state = {"user_id": None}

    def _override_get_db():
        yield db

    def _current_user():
        return {"id": state["user_id"], "email": "zzt-stock-limits@test.com"}

    async def _override_scope():
        scope = frozenset({SORENTO_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_current_user_or_api_key] = _current_user
    app.dependency_overrides[get_external_api_user] = _current_user
    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        with TestClient(app) as client:
            yield client, state
    finally:
        app.dependency_overrides.clear()


# --- RBAC seeding helpers (tests/test_migration_414_product_set_grant_sweep.py shape) --

def _permission(db, slug: str) -> str:
    row = db.query(UserPermission).filter_by(slug=slug).first()
    if row is None:
        row = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
        db.add(row)
        db.flush()
    return row.id


def _role(db, slug: str) -> str:
    row = UserRole(
        id=str(uuid.uuid4()), slug=slug, name=slug, description="",
        is_protected=False, is_default=False,
    )
    db.add(row)
    db.flush()
    return row.id


def _grant(db, role_id: str, slug: str) -> None:
    db.add(
        UserRolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_id=_permission(db, slug))
    )
    db.flush()


def _slugs_for(db, role_id: str) -> set[str]:
    rows = db.execute(
        text(
            "SELECT p.slug FROM user_role_permissions rp "
            "JOIN user_permissions p ON p.id = rp.permission_id WHERE rp.role_id = :role"
        ),
        {"role": role_id},
    ).all()
    return {row[0] for row in rows}


def _user_with_role(db, role_id: str | None) -> str:
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{unique_code('u').lower()}@test.com", status="ACTIVE"))
    db.flush()
    if role_id is not None:
        db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=uid, role_id=role_id))
        db.flush()
    return uid


# --- AC-SA103: columns exist, nullable, negative rejected by the DB CHECK -------------

def test_migration_adds_the_four_nullable_columns(db):
    _run_migration(db)

    rows = db.execute(
        text(
            "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND column_name IN ('chatbot_max_qty', 'chatbot_eta_offset_days') "
            "AND table_name IN ('product_categories', 'products')"
        )
    ).all()
    found = {(r.table_name, r.column_name) for r in rows}
    assert found == {
        ("product_categories", "chatbot_max_qty"),
        ("product_categories", "chatbot_eta_offset_days"),
        ("products", "chatbot_max_qty"),
        ("products", "chatbot_eta_offset_days"),
    }
    assert all(r.is_nullable == "YES" for r in rows)


def test_negative_chatbot_max_qty_rejected_on_product_categories(db):
    _run_migration(db)

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO product_categories (id, company_id, category_code, category_name, chatbot_max_qty) "
                "VALUES (:id, :company_id, :code, :name, -1)"
            ),
            {"id": str(uuid.uuid4()), "company_id": SORENTO_ID, "code": unique_code(f"{STEM}-NEGCAT"), "name": "Neg"},
        )
        db.flush()


def test_negative_chatbot_eta_offset_days_rejected_on_products(db):
    _run_migration(db)
    uom_id = str(uuid.uuid4())
    cat_id = str(uuid.uuid4())
    db.add(UnitOfMeasure(id=uom_id, uom_code=unique_code("U")[:20], uom_name="Each"))
    db.add(ProductCategory(id=cat_id, category_code=unique_code("C")[:50], category_name="ZZT Neg Cat"))
    db.flush()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO products (id, company_id, product_code, product_name, category_id, "
                "base_uom_id, list_price, chatbot_eta_offset_days) "
                "VALUES (:id, :company_id, :code, :name, :cat, :uom, 10.00, -1)"
            ),
            {
                "id": str(uuid.uuid4()), "company_id": SORENTO_ID,
                "code": unique_code(f"{STEM}-NEGPRD"), "name": "Neg Product",
                "cat": cat_id, "uom": uom_id,
            },
        )
        db.flush()


# --- Should fix 1 (reviewer pass round 2, PR #1221, 99d9670c): the model's own -------
# --- CheckConstraint, not just the migration's ---------------------------------------

# The two negative-value tests above call `_run_migration(db)` first, so they pass
# whether or not `ProductCategory`/`Product` declare the CHECK themselves - the
# migration's own `duplicate_object` DO block adds it either way (kill test 4, round 2
# reviewer pass). `bootstrap_env`, every cloud lane and every `blank_session`-based test
# fixture in this suite build the schema via `Base.metadata.create_all`, which never
# runs that migration body, so a CHECK declared only there is invisible on `db` here.
# These four insert straight into the `create_all` schema with no migration run at all,
# pinning that the model's `__table_args__` CheckConstraint is what actually enforces it.

def test_negative_chatbot_max_qty_rejected_on_product_categories_without_migration(db):
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO product_categories (id, company_id, category_code, category_name, chatbot_max_qty) "
                "VALUES (:id, :company_id, :code, :name, -1)"
            ),
            {"id": str(uuid.uuid4()), "company_id": SORENTO_ID, "code": unique_code(f"{STEM}-NOMIGCAT-X"), "name": "Neg"},
        )
        db.flush()


def test_negative_chatbot_eta_offset_days_rejected_on_product_categories_without_migration(db):
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO product_categories (id, company_id, category_code, category_name, chatbot_eta_offset_days) "
                "VALUES (:id, :company_id, :code, :name, -1)"
            ),
            {"id": str(uuid.uuid4()), "company_id": SORENTO_ID, "code": unique_code(f"{STEM}-NOMIGCAT-Y"), "name": "Neg"},
        )
        db.flush()


def test_negative_chatbot_max_qty_rejected_on_products_without_migration(db):
    uom_id = str(uuid.uuid4())
    cat_id = str(uuid.uuid4())
    db.add(UnitOfMeasure(id=uom_id, uom_code=unique_code("U")[:20], uom_name="Each"))
    db.add(ProductCategory(id=cat_id, category_code=unique_code("C")[:50], category_name="ZZT Neg Cat"))
    db.flush()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO products (id, company_id, product_code, product_name, category_id, "
                "base_uom_id, list_price, chatbot_max_qty) "
                "VALUES (:id, :company_id, :code, :name, :cat, :uom, 10.00, -1)"
            ),
            {
                "id": str(uuid.uuid4()), "company_id": SORENTO_ID,
                "code": unique_code(f"{STEM}-NOMIGPRD-X"), "name": "Neg Product",
                "cat": cat_id, "uom": uom_id,
            },
        )
        db.flush()


def test_negative_chatbot_eta_offset_days_rejected_on_products_without_migration(db):
    uom_id = str(uuid.uuid4())
    cat_id = str(uuid.uuid4())
    db.add(UnitOfMeasure(id=uom_id, uom_code=unique_code("U")[:20], uom_name="Each"))
    db.add(ProductCategory(id=cat_id, category_code=unique_code("C")[:50], category_name="ZZT Neg Cat"))
    db.flush()

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO products (id, company_id, product_code, product_name, category_id, "
                "base_uom_id, list_price, chatbot_eta_offset_days) "
                "VALUES (:id, :company_id, :code, :name, :cat, :uom, 10.00, -1)"
            ),
            {
                "id": str(uuid.uuid4()), "company_id": SORENTO_ID,
                "code": unique_code(f"{STEM}-NOMIGPRD-Y"), "name": "Neg Product",
                "cat": cat_id, "uom": uom_id,
            },
        )
        db.flush()


# --- AC-SA104: permission slugs seeded, sweep onto products.edit + admin, ------------
# --- integration_* excluded -----------------------------------------------------------

_SLUGS = (
    "master_data.chatbot_stock_limits.view",
    "master_data.chatbot_stock_limits.add",
    "master_data.chatbot_stock_limits.edit",
    "master_data.chatbot_stock_limits.delete",
)


def test_migration_inserts_the_four_permission_slugs(db):
    _run_migration(db)

    slugs = {
        row[0]
        for row in db.execute(
            text("SELECT slug FROM user_permissions WHERE slug LIKE 'master_data.chatbot_stock_limits.%'")
        ).all()
    }
    assert set(_SLUGS) <= slugs


def test_migration_sweeps_view_and_edit_onto_a_products_edit_role(db):
    role = _role(db, "zzt_products_editor")
    _grant(db, role, "master_data.products.edit")

    _run_migration(db)

    slugs = _slugs_for(db, role)
    assert "master_data.chatbot_stock_limits.view" in slugs
    assert "master_data.chatbot_stock_limits.edit" in slugs


def test_migration_grants_admin_view_and_edit(db):
    role = _role(db, "admin")

    _run_migration(db)

    slugs = _slugs_for(db, role)
    assert "master_data.chatbot_stock_limits.view" in slugs
    assert "master_data.chatbot_stock_limits.edit" in slugs


def test_migration_excludes_integration_roles_from_the_sweep(db):
    role = _role(db, "integration_zzt_autocount")
    _grant(db, role, "master_data.products.edit")

    _run_migration(db)

    slugs = _slugs_for(db, role)
    assert "master_data.chatbot_stock_limits.view" not in slugs
    assert "master_data.chatbot_stock_limits.edit" not in slugs


# --- AC-SA105/106/107: PUT category, with and without .edit --------------------------

def test_put_category_with_edit_persists_and_response_carries_both(api, world, db):
    role = _role(db, "zzt_cat_full")
    _grant(db, role, "master_data.product_categories.edit")
    _grant(db, role, "master_data.chatbot_stock_limits.edit")
    user_id = _user_with_role(db, role)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.put(
        f"/api/v1/master-data/product-categories/{world['cat_id']}",
        json={"chatbot_max_qty": 200, "chatbot_eta_offset_days": 7},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("chatbot_max_qty") == 200
    assert body.get("chatbot_eta_offset_days") == 7


def test_put_category_without_edit_changing_value_is_403_naming_the_permission(api, world, db):
    role = _role(db, "zzt_cat_limited")
    _grant(db, role, "master_data.product_categories.edit")
    user_id = _user_with_role(db, role)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.put(
        f"/api/v1/master-data/product-categories/{world['cat_id']}",
        json={"chatbot_max_qty": 200},
    )
    assert res.status_code == 403, res.text
    assert "master_data.chatbot_stock_limits.edit" in res.text


def test_put_category_without_edit_unchanged_value_still_saves(api, world, db):
    # Pre-set the row's stored X directly (the API cannot do this yet), so the PUT
    # below sends back the value the row ALREADY holds - AC-SA106's "an ordinary form
    # re-save must not break" case.
    db.execute(
        text("UPDATE product_categories SET chatbot_max_qty = 200 WHERE id = :id"),
        {"id": world["cat_id"]},
    )
    db.commit()

    role = _role(db, "zzt_cat_limited_unchanged")
    _grant(db, role, "master_data.product_categories.edit")
    user_id = _user_with_role(db, role)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.put(
        f"/api/v1/master-data/product-categories/{world['cat_id']}",
        json={"chatbot_max_qty": 200, "category_name": "ZZT Category Renamed"},
    )
    assert res.status_code == 200, res.text
    assert res.json().get("category_name") == "ZZT Category Renamed"


# --- AC-SA107: same three, for PUT product (route has no permission dependency) ------

def test_put_product_with_edit_persists_and_response_carries_both(api, world, db):
    role = _role(db, "zzt_prod_full")
    _grant(db, role, "master_data.chatbot_stock_limits.edit")
    user_id = _user_with_role(db, role)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.put(
        f"/api/v1/master-data/products/{world['pid']}",
        json={"chatbot_max_qty": 150, "chatbot_eta_offset_days": 3},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("chatbot_max_qty") == 150
    assert body.get("chatbot_eta_offset_days") == 3


def test_put_product_without_edit_changing_value_is_403_naming_the_permission(api, world, db):
    user_id = _user_with_role(db, None)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.put(
        f"/api/v1/master-data/products/{world['pid']}",
        json={"chatbot_max_qty": 150},
    )
    assert res.status_code == 403, res.text
    assert "master_data.chatbot_stock_limits.edit" in res.text


def test_put_product_without_edit_unchanged_value_still_saves(api, world, db):
    db.execute(
        text("UPDATE products SET chatbot_max_qty = 150 WHERE id = :id"),
        {"id": world["pid"]},
    )
    db.commit()

    user_id = _user_with_role(db, None)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.put(
        f"/api/v1/master-data/products/{world['pid']}",
        json={"chatbot_max_qty": 150, "product_name": "ZZT Product Renamed"},
    )
    assert res.status_code == 200, res.text
    assert res.json().get("product_name") == "ZZT Product Renamed"


# --- AC-SA108: negative at the API is 422 ---------------------------------------------

def test_put_category_negative_max_qty_is_422(api, world, db):
    role = _role(db, "zzt_cat_422")
    _grant(db, role, "master_data.product_categories.edit")
    _grant(db, role, "master_data.chatbot_stock_limits.edit")
    user_id = _user_with_role(db, role)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.put(
        f"/api/v1/master-data/product-categories/{world['cat_id']}",
        json={"chatbot_max_qty": -1},
    )
    assert res.status_code == 422, res.text


def test_put_product_negative_eta_offset_is_422(api, world, db):
    role = _role(db, "zzt_prod_422")
    _grant(db, role, "master_data.chatbot_stock_limits.edit")
    user_id = _user_with_role(db, role)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.put(
        f"/api/v1/master-data/products/{world['pid']}",
        json={"chatbot_eta_offset_days": -1},
    )
    assert res.status_code == 422, res.text


# --- AC-SA108: GET carries both fields (response_model can silently drop a field) ----

def test_get_category_carries_both_fields(api, world, db):
    role = _role(db, "zzt_cat_view")
    _grant(db, role, "master_data.product_categories.view")
    user_id = _user_with_role(db, role)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.get(f"/api/v1/master-data/product-categories/{world['cat_id']}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "chatbot_max_qty" in body
    assert "chatbot_eta_offset_days" in body


def test_get_product_carries_both_fields(api, world, db):
    user_id = _user_with_role(db, None)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.get(f"/api/v1/master-data/products/{world['pid']}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "chatbot_max_qty" in body
    assert "chatbot_eta_offset_days" in body


# --- Should fix 1 (reviewer pass, PR #1221, 85c2e9e7): X/Y on CREATE, without .edit --
# The create routes never called guard_chatbot_limits_edit, so a
# product_categories.add / products.add holder without .edit could opt a brand-new
# category or product in through the create body alone (a live path - the Phase 1
# browser walk used the Create Category modal). Guarded against a NULL baseline, the
# same "current" a create has: no stored value yet, so ANY X/Y in the body is a change.

def test_post_category_with_edit_persists_chatbot_limits(api, db):
    role = _role(db, "zzt_cat_create_full")
    _grant(db, role, "master_data.product_categories.add")
    _grant(db, role, "master_data.chatbot_stock_limits.edit")
    user_id = _user_with_role(db, role)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.post(
        "/api/v1/master-data/product-categories/",
        json={
            "category_code": unique_code(f"{STEM}-CREATECAT"),
            "category_name": "ZZT Create Category",
            "chatbot_max_qty": 40,
            "chatbot_eta_offset_days": 5,
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body.get("chatbot_max_qty") == 40
    assert body.get("chatbot_eta_offset_days") == 5


def test_post_category_without_edit_setting_chatbot_limits_is_403(api, db):
    role = _role(db, "zzt_cat_create_limited")
    _grant(db, role, "master_data.product_categories.add")
    user_id = _user_with_role(db, role)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.post(
        "/api/v1/master-data/product-categories/",
        json={
            "category_code": unique_code(f"{STEM}-CREATECAT403"),
            "category_name": "ZZT Create Category No Edit",
            "chatbot_max_qty": 40,
        },
    )
    assert res.status_code == 403, res.text
    assert "master_data.chatbot_stock_limits.edit" in res.text


def test_post_category_without_edit_and_no_chatbot_limits_in_body_still_creates(api, db):
    role = _role(db, "zzt_cat_create_plain")
    _grant(db, role, "master_data.product_categories.add")
    user_id = _user_with_role(db, role)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.post(
        "/api/v1/master-data/product-categories/",
        json={
            "category_code": unique_code(f"{STEM}-CREATECATPLAIN"),
            "category_name": "ZZT Create Category Plain",
        },
    )
    assert res.status_code == 201, res.text
    assert res.json().get("chatbot_max_qty") is None


def test_post_product_with_edit_persists_chatbot_limits(api, world, db):
    role = _role(db, "zzt_prod_create_full")
    _grant(db, role, "master_data.chatbot_stock_limits.edit")
    user_id = _user_with_role(db, role)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.post(
        "/api/v1/master-data/products/",
        json={
            "product_code": unique_code(f"{STEM}-CREATEPRD"),
            "product_name": "ZZT Create Product",
            "category_id": world["cat_id"],
            "base_uom_id": world["uom_id"],
            "list_price": "10.00",
            "chatbot_max_qty": 60,
            "chatbot_eta_offset_days": 4,
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body.get("chatbot_max_qty") == 60
    assert body.get("chatbot_eta_offset_days") == 4


def test_post_product_without_edit_setting_chatbot_limits_is_403(api, world, db):
    user_id = _user_with_role(db, None)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.post(
        "/api/v1/master-data/products/",
        json={
            "product_code": unique_code(f"{STEM}-CREATEPRD403"),
            "product_name": "ZZT Create Product No Edit",
            "category_id": world["cat_id"],
            "base_uom_id": world["uom_id"],
            "list_price": "10.00",
            "chatbot_max_qty": 60,
        },
    )
    assert res.status_code == 403, res.text
    assert "master_data.chatbot_stock_limits.edit" in res.text


def test_post_product_without_edit_and_no_chatbot_limits_in_body_still_creates(api, world, db):
    user_id = _user_with_role(db, None)
    db.commit()

    client, state = api
    state["user_id"] = user_id

    res = client.post(
        "/api/v1/master-data/products/",
        json={
            "product_code": unique_code(f"{STEM}-CREATEPRDPLAIN"),
            "product_name": "ZZT Create Product Plain",
            "category_id": world["cat_id"],
            "base_uom_id": world["uom_id"],
            "list_price": "10.00",
        },
    )
    assert res.status_code == 201, res.text
    assert res.json().get("chatbot_max_qty") is None
