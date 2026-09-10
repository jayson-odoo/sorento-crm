"""Countries master (S1, PLAN-local-supplier-oi-routing.md, UAC AC-2.1 - AC-2.7).

RED for Phase 2: none of `app.models.country`, `app.schemas.country`,
`app.services.country_service`, the `/api/v1/master-data/countries` router, the
`master_data.countries.*` permission slugs, the `510_countries` migration or the
`country.delete` deferred-action registration exist yet. Every test here fails on
collection (ImportError) or on a missing route/registry entry - never on a fixture bug.

Contract this file drives (not yet built, named here so the coder has one target):

* `app.models.country.Country(Base, CompanyScopedMixin)`, `__tablename__ = "countries"`,
  `__company_shared__ = True`, columns `code` (2 chars, unique case-insensitive), `name`,
  `is_active`.
* `app.schemas.country.CountryCreate/CountryUpdate/CountryResponse/CountrySelectItem`.
* `app.services.country_service.CountryService(db)`: `list_countries(page, limit, query,
  sort)`, `get_country(id)`, `create_country(CountryCreate)`, `update_country(id,
  CountryUpdate)`, `delete_country(id)` - the last two raising `AppException` (409 on a
  duplicate code / a country still referenced by a supplier).
* Routes mounted at `/api/v1/master-data/countries` (`GET /`, `GET /select`, `GET /{id}`,
  `POST /`, `PUT /{id}`, `DELETE /{id}`), gated by `master_data.countries.{view,add,edit,
  delete}` the same way `units_of_measure.py` gates on its own slugs.
* `alembic/versions/510_countries.py` exposing `ISO_COUNTRIES` (249 `(code, name)` pairs,
  `("MY", "Malaysia")` among them), `_seed_countries(bind)` (idempotent insert) and
  `_grant_countries_permissions(bind)` (idempotent: every role holding
  `master_data.units_of_measure.<action>` also granted `master_data.countries.<action>`) -
  named and shaped after `alembic/versions/445_autocount_grant_sweep.py`'s `apply()` /
  `_create_if_absent` pattern, since a seed this large cannot run through `create_all` and
  a blank scratch schema never sees a migration at all (`tests/_pg_fixture.py` docstring).
* `app.rbac.permission_registry.PERMISSION_REGISTRY` extended with the four
  `master_data.countries.*` slugs (`_crud("master_data", "countries", "Countries")`).
* `app.services.record_actions` registers `country.delete` (`app.services.
  form_action_registry`), `execute` calling `CountryService.delete_country`, same 409 guard
  as AC-2.4.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, text

from app.database import engine, get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.main import app
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.company_scope_resolver import apply_company_scope
from app.services.error_handler import AppException
from app.services.user_service import UserPermissionService

from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTCTY"
MIGRATION = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions" / "510_countries.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m510_countries", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()


# --------------------------------------------------------------------------- #
# AC-2.1: the migration seeds the full ISO list on an empty database
# --------------------------------------------------------------------------- #


def test_migration_seeds_iso_list():
    from app.models.country import Country

    module = _load_migration()
    with blank_session() as db:
        module._seed_countries(db.connection())
        db.flush()

        assert db.query(Country).count() == 249
        my = db.query(Country).filter(func.lower(Country.code) == "my").one()
        assert my.name == "Malaysia"

        # Idempotent: a second seed (what a re-run migration would do) may not duplicate.
        module._seed_countries(db.connection())
        db.flush()
        assert db.query(Country).count() == 249


# --------------------------------------------------------------------------- #
# AC-2.2: __company_shared__, visible to a scoped (non-admin) user of another company
# --------------------------------------------------------------------------- #


def test_company_shared_visible_to_scoped_user():
    from app.models.company import Company
    from app.models.country import Country
    from app.models.base import set_company_scope
    from app.services.country_service import CountryService

    module = _load_migration()
    with blank_session() as db:
        module._seed_countries(db.connection())
        db.flush()

        company_b = Company(id=_u(), name=f"{MARKER} B", code=unique_code(MARKER)[:10])
        db.add(company_b)
        db.flush()

        assert Country.__company_shared__ is True

        set_company_scope(db, frozenset({company_b.id}))
        rows = CountryService(db).list_countries(page=1, limit=10, query="Malaysia")
        codes = {row["code"] if isinstance(row, dict) else row.code for row in rows["data"]}
        assert "MY" in codes


# --------------------------------------------------------------------------- #
# AC-2.3: CRUD routes + permissions
# --------------------------------------------------------------------------- #

BASE = "/api/v1/master-data/countries"


@pytest.fixture
def api(monkeypatch):
    from fastapi.testclient import TestClient

    with blank_session() as db:
        module = _load_migration()
        module._seed_countries(db.connection())
        db.flush()

        actor = {"id": "zzt-countries-user", "email": "zzt-cty@zzt.test", "role": "user"}
        allow: set[str] = set()

        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: dict(actor)
        app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
        app.dependency_overrides[apply_company_scope] = lambda: None
        monkeypatch.setattr(
            UserPermissionService,
            "check_user_has_permission",
            lambda self, uid, slug: slug in allow,
        )
        client = TestClient(app)
        try:
            yield client, allow, db
        finally:
            app.dependency_overrides.clear()


def test_crud_routes_and_permissions(api):
    client, allow, db = api

    # LIST: denied without the view slug, then allowed.
    resp = client.get(BASE)
    assert resp.status_code == 403
    allow.add("master_data.countries.view")
    resp = client.get(BASE, params={"query": "malaysia"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["pagination"]["total"] >= 1

    # SELECT: same view slug.
    resp = client.get(f"{BASE}/select")
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["code"] == "MY")
    assert set(row) >= {"id", "code", "name"}

    # GET one.
    resp = client.get(f"{BASE}/{row['id']}")
    assert resp.status_code == 200, resp.text

    # CREATE: denied without .add.
    payload = {"code": unique_code(MARKER)[:2].upper(), "name": f"{MARKER} land"}
    resp = client.post(BASE, json=payload)
    assert resp.status_code == 403
    allow.add("master_data.countries.add")
    resp = client.post(BASE, json=payload)
    assert resp.status_code in (200, 201), resp.text
    new_id = resp.json()["id"]

    # UPDATE: denied without .edit.
    resp = client.put(f"{BASE}/{new_id}", json={"name": "Renamed"})
    assert resp.status_code == 403
    allow.add("master_data.countries.edit")
    resp = client.put(f"{BASE}/{new_id}", json={"name": "Renamed"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Renamed"

    # DELETE: denied without .delete.
    resp = client.delete(f"{BASE}/{new_id}")
    assert resp.status_code == 403
    allow.add("master_data.countries.delete")
    resp = client.delete(f"{BASE}/{new_id}")
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------- #
# AC-2.4: delete refused while a supplier references the country
# --------------------------------------------------------------------------- #


def test_delete_refused_while_referenced():
    from app.models.country import Country
    from app.models.procurement import Supplier
    from app.services.country_service import CountryService

    with blank_session() as db:
        country = Country(id=_u(), code=unique_code(MARKER)[:2].upper(), name=f"{MARKER} land")
        db.add(country)
        db.flush()
        supplier = Supplier(
            id=_u(), supplier_code=unique_code(MARKER)[:30], supplier_name=f"{MARKER} sup",
            country_id=country.id,
        )
        db.add(supplier)
        db.commit()

        with pytest.raises(AppException) as exc:
            CountryService(db).delete_country(country.id)
        assert exc.value.status_code == 409
        message = exc.value.detail.get("message", "") if isinstance(exc.value.detail, dict) else str(exc.value.detail)
        assert "1" in message and "supplier" in message.lower()

        db.expire_all()
        assert db.query(Country).filter(Country.id == country.id).first() is not None


# --------------------------------------------------------------------------- #
# AC-2.5: duplicate code, case-insensitive, on both create and update
# --------------------------------------------------------------------------- #


def test_duplicate_code_case_insensitive_409():
    from app.models.country import Country
    from app.schemas.country import CountryCreate, CountryUpdate
    from app.services.country_service import CountryService

    with blank_session() as db:
        existing = Country(id=_u(), code="MY", name="Malaysia")
        other = Country(id=_u(), code=unique_code(MARKER)[:2].upper(), name=f"{MARKER} other")
        db.add_all([existing, other])
        db.commit()

        svc = CountryService(db)
        with pytest.raises(AppException) as create_exc:
            svc.create_country(CountryCreate(code="my", name="Duplicate"))
        assert create_exc.value.status_code == 409
        assert db.query(Country).filter(func.lower(Country.code) == "my").count() == 1

        with pytest.raises(AppException) as update_exc:
            svc.update_country(other.id, CountryUpdate(code="my"))
        assert update_exc.value.status_code == 409
        db.expire_all()
        assert db.query(Country).filter(Country.id == other.id).one().code != "my"


# --------------------------------------------------------------------------- #
# AC-2.6: permission slugs registered + granted derived from units_of_measure
# --------------------------------------------------------------------------- #


def _permission_id(bind, slug: str):
    return bind.execute(
        text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
    ).scalar()


def _ensure_permission(bind, slug: str) -> str:
    existing = _permission_id(bind, slug)
    if existing is not None:
        return existing
    new_id = str(uuid.uuid4())
    bind.execute(
        text(
            "INSERT INTO user_permissions (id, slug, name, description, created_at) "
            "VALUES (:i, :s, :n, :d, now())"
        ),
        {"i": new_id, "s": slug, "n": slug, "d": f"{MARKER} seeded"},
    )
    return new_id


def _seed_role_holding(bind, *source_slugs: str) -> str:
    role_id = str(uuid.uuid4())
    suffix = uuid.uuid4().hex[:8]
    bind.execute(
        text(
            "INSERT INTO user_roles (id, slug, name, description, is_protected, is_default, is_trashed) "
            "VALUES (:i, :s, :n, :d, false, false, false)"
        ),
        {
            "i": role_id,
            "s": f"{MARKER.lower()}_{suffix}",
            "n": f"{MARKER} role {suffix}",
            "d": f"{MARKER} scratch role",
        },
    )
    for slug in source_slugs:
        bind.execute(
            text(
                "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
                "VALUES (:i, :r, :p, now())"
            ),
            {"i": str(uuid.uuid4()), "r": role_id, "p": _ensure_permission(bind, slug)},
        )
    return role_id


def _grant_count(bind, role_id: str, slug: str) -> int:
    return bind.execute(
        text(
            "SELECT count(*) FROM user_role_permissions rp "
            "JOIN user_permissions p ON p.id = rp.permission_id "
            "WHERE rp.role_id = :r AND p.slug = :s"
        ),
        {"r": role_id, "s": slug},
    ).scalar()


def test_permissions_registered_and_granted_like_uom():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {f"master_data.countries.{action}" for action in ("view", "add", "edit", "delete")}
    registry_slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert slugs <= registry_slugs, "the four master_data.countries.* slugs must be registered"

    module = _load_migration()
    connection = engine.connect()
    transaction = connection.begin()
    try:
        role_id = _seed_role_holding(
            connection,
            "master_data.units_of_measure.view",
            "master_data.units_of_measure.add",
            "master_data.units_of_measure.edit",
            "master_data.units_of_measure.delete",
        )
        for action in ("view", "add", "edit", "delete"):
            assert _grant_count(connection, role_id, f"master_data.countries.{action}") == 0

        module._grant_countries_permissions(connection)

        for action in ("view", "add", "edit", "delete"):
            assert _grant_count(connection, role_id, f"master_data.countries.{action}") == 1, action
    finally:
        transaction.rollback()
        connection.close()


# --------------------------------------------------------------------------- #
# AC-2.7: deferred-delete record action, same 409 guard as AC-2.4
# --------------------------------------------------------------------------- #


def test_deferred_delete_action_registered():
    from app.models.country import Country
    from app.models.procurement import Supplier
    from app.services.form_action_registry import get_action
    from app.services.form_action_grace import WINDOW_DESTRUCTIVE

    action = get_action("country.delete")
    assert action is not None
    assert action.permission == "master_data.countries.delete"
    assert action.window == WINDOW_DESTRUCTIVE

    with blank_session() as db:
        country = Country(id=_u(), code=unique_code(MARKER)[:2].upper(), name=f"{MARKER} land")
        db.add(country)
        db.flush()
        supplier = Supplier(
            id=_u(), supplier_code=unique_code(MARKER)[:30], supplier_name=f"{MARKER} sup",
            country_id=country.id,
        )
        db.add(supplier)
        db.commit()

        with pytest.raises(AppException) as exc:
            action.execute(db, {"entity_id": country.id})
        assert exc.value.status_code == 409
