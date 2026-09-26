"""Shared HTTP-route test harness for the cost-price-from-supplier lane (#1288, Lane A).

Same shape as `test_autocount_pull_sr1.py`'s `_Env`/`env` fixture: a `TestClient(app)` over
`blank_session()` (a throwaway Postgres schema built from whatever is on `Base.metadata`),
with `get_db`, `get_current_user(_or_api_key)` and `apply_company_scope` overridden so a
test drives the real routes without a real login.

NOTHING under `app/models/cost_price.py`, `app/services/procurement/cost_price_change_service.py`
etc. exists yet (this file is written test-FIRST, per PRINCIPLES.md Phase 2) - so every
seeding helper that touches one of those tables imports it INSIDE the method body, never at
module load, and every route call is a plain HTTP request through `self.client`: a missing
route 404s, a missing table's insert raises inside the specific test that needed it. Nothing
here imports a not-yet-existing name at collection time.

Every seeded row carries the `MARKER` prefix (`ZZCPC`) - CI's database has no data, and the
shared local Postgres this also runs against during development has real rows, so an
unprefixed `LIMIT 1` borrow is the lesson this harness is built to avoid.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards (repo convention, see test_ingest_deletions.py,
# test_autocount_pull_sr1.py).
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session

MARKER = "ZZCPC"

BASE = "/api/v1/procurement/cost-price-changes"
COST_LISTS_URL = "/api/v1/procurement/suppliers/{supplier_id}/cost-lists"
PS_URL = "/api/v1/procurement/product-suppliers"
PS_BY_PRODUCT_URL = "/api/v1/procurement/product-suppliers/product/{product_id}"
PS_COSTS_URL = "/api/v1/procurement/product-suppliers/{link_id}/costs"
SETTINGS_URL = "/api/v1/user-management/settings/"
SETTINGS_GENERAL_URL = "/api/v1/user-management/settings/general"

UPLOAD_PERM = "procurement.cost_price_changes.upload"
VIEW_PERM = "procurement.cost_price_changes.view"
VERIFY_PERM = "procurement.cost_price_changes.verify"
PS_VIEW_PERM = "procurement.product_suppliers.view"
PS_ADD_PERM = "procurement.product_suppliers.add"
PS_EDIT_PERM = "procurement.product_suppliers.edit"
PS_DELETE_PERM = "procurement.product_suppliers.delete"
PRICE_LINK_PERM = "procurement.suppliers.price_link"
SETTINGS_VIEW_PERM = "user_management.settings.view"
SETTINGS_EDIT_PERM = "user_management.settings.edit"

#: The permission every purchasing role holds today (plan section 10, AC-S1-25's
#: "purchasing roles" definition) - the migration sweep's source permission.
PURCHASING_SOURCE_PERM = "scm.proforma_invoice.upload"

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _u() -> str:
    return str(uuid.uuid4())


class CostPriceEnv:
    """One test's own company, users, catalogue and authenticated `TestClient`."""

    def __init__(self, db):
        self.db = db
        from app.models.company import Company
        from app.services.company_scope import DEFAULT_COMPANY_ID

        # `company_a` is the INCUMBENT Sorento company, not a fresh one: tests/conftest.py's
        # `after_begin` listener defaults an unset session scope to `DEFAULT_COMPANY_ID`
        # (see that file), so anything seeded before the first request that sets a real
        # scope (a `CostPriceEnv` fixture body, run before `e.as_user(...)`) lands there
        # regardless of what `self.scope` is later set to. A fresh `company_a` here meant
        # every such row was invisible the moment a request scoped to it - the harness
        # hid its own seed data. `company_b` stays a genuinely different company, since
        # AC-S1-17's multi-company refusal needs two real ones.
        self.company_a = DEFAULT_COMPANY_ID
        tag = uuid.uuid4().hex[:8]
        other = Company(
            id=_u(), name=f"{MARKER} co B {tag}", code=f"ZB{tag}"[:50], is_active=True
        )
        db.add(other)
        db.flush()
        self.company_b = str(other.id)

        self.client: TestClient | None = None
        self.principal: dict | None = None
        # The REAL user during an `.as_impersonated(...)` session, else None (matches
        # `_maybe_apply_impersonation`'s "same as current_user outside impersonation").
        self.principal_real: dict | None = None
        self.scope = frozenset({self.company_a})

    # ------------------------------------------------------------- principals
    def user(self, *perm_slugs: str, name: str = "U") -> dict:
        """A user holding EXACTLY the given permission slugs, through a role this test
        owns - never a borrowed/seeded role, since CI's database carries no role/grant
        rows until the migration's sweep has actually run (and even then, "whatever
        holds X today" is an assertion about the environment this suite must not
        depend on)."""
        from app.models.user import (
            User,
            UserPermission,
            UserRole,
            UserRoleAssignment,
            UserRolePermission,
        )

        uid = _u()
        role_id = _u()
        self.db.add(
            User(id=uid, email=f"{MARKER.lower()}-{uid[:8]}@test.com", name=name, status="ACTIVE")
        )
        self.db.add(
            UserRole(
                id=role_id, slug=f"{MARKER.lower()}-role-{uid[:8]}",
                name=f"{MARKER} role {uid[:8]}", description="",
                is_protected=False, is_default=False,
            )
        )
        self.db.flush()
        self.db.add(UserRoleAssignment(id=_u(), user_id=uid, role_id=role_id))
        for slug in perm_slugs:
            perm = self.db.query(UserPermission).filter_by(slug=slug).one_or_none()
            if perm is None:
                perm = UserPermission(id=_u(), slug=slug, name=slug, description="")
                self.db.add(perm)
                self.db.flush()
            self.db.add(
                UserRolePermission(id=_u(), role_id=role_id, permission_id=perm.id)
            )
        self.db.commit()
        return {"id": uid, "email": f"{MARKER.lower()}-{uid[:8]}@test.com", "name": name}

    def superadmin(self, name: str = "Admin") -> dict:
        """A user whose ROLE SLUG is literally `superadmin` - the RBAC bypass every
        permission check recognises (`UserPermissionService.SUPERADMIN_ROLE_SLUG`), not a
        user merely granted every slug. AC-S2-03 needs this exact shape: even the
        four-eyes bypass a superadmin gets everywhere else must not let them verify a
        set they uploaded themselves."""
        from app.models.user import User, UserRole, UserRoleAssignment

        uid = _u()
        role_id = _u()
        self.db.add(
            User(id=uid, email=f"{MARKER.lower()}-{uid[:8]}@test.com", name=name, status="ACTIVE")
        )
        self.db.add(
            UserRole(
                id=role_id, slug="superadmin", name="Superadmin", description="",
                is_protected=True, is_default=False,
            )
        )
        self.db.flush()
        self.db.add(UserRoleAssignment(id=_u(), user_id=uid, role_id=role_id))
        self.db.commit()
        return {"id": uid, "email": f"{MARKER.lower()}-{uid[:8]}@test.com", "name": name}

    def grant(self, user: dict, *perm_slugs: str) -> None:
        """Adds more permissions to a user already created by `.user(...)`, through a
        second role (roles are cheap and test-owned, so this never touches the first)."""
        from app.models.user import (
            UserPermission,
            UserRole,
            UserRoleAssignment,
            UserRolePermission,
        )

        role_id = _u()
        self.db.add(
            UserRole(
                id=role_id, slug=f"{MARKER.lower()}-role2-{user['id'][:8]}-{_u()[:6]}",
                name=f"{MARKER} extra role", description="",
                is_protected=False, is_default=False,
            )
        )
        self.db.flush()
        self.db.add(UserRoleAssignment(id=_u(), user_id=user["id"], role_id=role_id))
        for slug in perm_slugs:
            perm = self.db.query(UserPermission).filter_by(slug=slug).one_or_none()
            if perm is None:
                perm = UserPermission(id=_u(), slug=slug, name=slug, description="")
                self.db.add(perm)
                self.db.flush()
            self.db.add(
                UserRolePermission(id=_u(), role_id=role_id, permission_id=perm.id)
            )
        self.db.commit()

    def as_user(self, principal: dict | None, *, scope=None) -> None:
        self.principal = principal
        self.principal_real = None
        self.scope = scope if scope is not None else frozenset({self.company_a})

    def as_impersonated(self, real_principal: dict, effective_principal: dict, *, scope=None) -> None:
        """Simulates an admin (`real_principal`) impersonating `effective_principal` (B2):
        every route sees `current_user` == `effective_principal`, and
        `request.state.real_user` (set by `_wire_overrides`' `get_current_user`
        override, mirroring `_maybe_apply_impersonation`) carries the real principal
        - so `app.dependencies.get_actor_user_id` resolves `real_principal`, exactly
        as it would through a genuine `X-Impersonate-User-Id` session."""
        self.principal = effective_principal
        self.principal_real = real_principal
        self.scope = scope if scope is not None else frozenset({self.company_a})

    # ---------------------------------------------------------------- catalogue
    def supplier(self, *, name: str = "XIAMEN TAIYANG TECHNOLOGY", code: str | None = None,
                 active: bool = True):
        from app.models.procurement import Supplier

        tag = uuid.uuid4().hex[:8].upper()
        s = Supplier(
            id=_u(), supplier_code=code or f"{MARKER}-S-{tag}", supplier_name=name,
            is_active=active,
        )
        self.db.add(s)
        self.db.flush()
        return s

    def product(self, code: str | None = None, *, description: str = "A product"):
        from app.models.product import Product, ProductCategory, UnitOfMeasure

        cat = self.db.query(ProductCategory).filter_by(category_code=f"{MARKER}-CAT").one_or_none()
        if cat is None:
            cat = ProductCategory(
                id=_u(), category_code=f"{MARKER}-CAT", category_name=f"{MARKER} category"
            )
            self.db.add(cat)
            self.db.flush()
        uom = self.db.query(UnitOfMeasure).filter_by(uom_code=f"{MARKER}-U").one_or_none()
        if uom is None:
            uom = UnitOfMeasure(id=_u(), uom_code=f"{MARKER}-U", uom_name="pcs")
            self.db.add(uom)
            self.db.flush()
        tag = uuid.uuid4().hex[:8].upper()
        p = Product(
            id=_u(), product_code=code or f"{MARKER}-{tag}", product_name=description,
            category_id=cat.id, base_uom_id=uom.id, list_price=0,
            is_active=True, is_discontinued=False,
        )
        self.db.add(p)
        self.db.flush()
        return p

    def product_in_company(self, company_id: str, code: str | None = None, *, description: str = "A product"):
        """A product stamped with `company_id`, not the test's own `company_a` (B1: cross-
        company product references). Switches the session's company scope for one insert,
        then restores it - a direct ORM seed, not a request, so `self.scope` (read only by
        the `apply_company_scope` override on the NEXT request) is untouched either way."""
        from app.models.base import set_company_scope

        set_company_scope(self.db, frozenset({company_id}))
        try:
            return self.product(code=code, description=description)
        finally:
            set_company_scope(self.db, self.scope)

    def link(self, product, supplier, *, unit_cost=None, currency=None, lead_time_days=30):
        from app.models.procurement import ProductSupplier

        ps = ProductSupplier(
            id=_u(), product_id=product.id, supplier_id=supplier.id,
            standard_lead_time_days=lead_time_days, unit_cost=unit_cost, currency=currency,
        )
        self.db.add(ps)
        self.db.flush()
        return ps

    def seed_settings(self, **overrides):
        from app.models.user import SystemSetting

        existing = self.db.query(SystemSetting).first()
        if existing is not None:
            for k, v in overrides.items():
                setattr(existing, k, v)
            self.db.commit()
            return existing
        row = SystemSetting(id=_u(), name=f"{MARKER} settings", **overrides)
        self.db.add(row)
        self.db.commit()
        return row

    # --------------------------------------------------------------------- HTTP
    def probe(self, data: bytes, filename: str = "taiyang.xlsx"):
        return self.client.post(f"{BASE}/probe", files={"file": (filename, data, _XLSX)})

    def upload(self, data: bytes, *, supplier_id: str, currency: str | None = "CNY",
               start_date: str | None = None, end_date: str | None = None,
               filename: str = "taiyang.xlsx"):
        form = {"supplier_id": supplier_id}
        if currency is not None:
            form["currency"] = currency
        if start_date is not None:
            form["start_date"] = start_date
        if end_date is not None:
            form["end_date"] = end_date
        return self.client.post(BASE, files={"file": (filename, data, _XLSX)}, data=form)

    def list_sets(self, **params):
        return self.client.get(BASE, params=params)

    def detail(self, set_id):
        return self.client.get(f"{BASE}/{set_id}")

    def lines(self, set_id):
        return self.client.get(f"{BASE}/{set_id}/lines")

    def patch_line(self, set_id, line_id, body: dict):
        return self.client.patch(f"{BASE}/{set_id}/lines/{line_id}", json=body)

    def submit(self, set_id):
        return self.client.post(f"{BASE}/{set_id}/submit")

    def decide(self, set_id, line_id, body: dict):
        return self.client.patch(f"{BASE}/{set_id}/lines/{line_id}/decision", json=body)

    def decide_all(self, set_id, decision: str):
        return self.client.post(f"{BASE}/{set_id}/decide-all", json={"decision": decision})

    def return_set(self, set_id, reason: str):
        return self.client.post(f"{BASE}/{set_id}/return", json={"reason": reason})

    def apply(self, set_id):
        return self.client.post(f"{BASE}/{set_id}/apply")

    def discard(self, set_id):
        return self.client.delete(f"{BASE}/{set_id}")

    def source_file(self, set_id):
        return self.client.get(f"{BASE}/{set_id}/source-file")

    def history(self, set_id):
        return self.client.get(f"{BASE}/{set_id}/history")

    def cost_lists(self, supplier_id, **params):
        return self.client.get(COST_LISTS_URL.format(supplier_id=supplier_id), params=params)

    def product_suppliers_by_product(self, product_id):
        return self.client.get(PS_BY_PRODUCT_URL.format(product_id=product_id))

    def create_product_supplier(self, body: dict):
        return self.client.post(f"{PS_URL}/", json=body)

    def update_product_supplier(self, link_id, body: dict):
        return self.client.put(f"{PS_URL}/{link_id}", json=body)

    def delete_product_supplier(self, link_id):
        return self.client.delete(f"{PS_URL}/{link_id}")

    def post_cost(self, link_id, body: dict):
        return self.client.post(PS_COSTS_URL.format(link_id=link_id), json=body)

    def put_cost(self, link_id, cost_id, body: dict):
        return self.client.put(f"{PS_COSTS_URL.format(link_id=link_id)}/{cost_id}", json=body)

    def delete_cost(self, link_id, cost_id):
        return self.client.delete(f"{PS_COSTS_URL.format(link_id=link_id)}/{cost_id}")

    def get_settings(self):
        return self.client.get(SETTINGS_URL)

    def put_settings(self, body: dict):
        return self.client.put(SETTINGS_GENERAL_URL, json=body)


def _wire_overrides(e: "CostPriceEnv", db) -> None:
    """The dependency-override wiring both fixtures below share: same `get_db`,
    `get_current_user(_or_api_key)` and `apply_company_scope` overrides, whatever the
    substrate under `db` (a scratch schema or the live database)."""
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    def _override_get_db():
        yield db

    def _override_get_current_user(request: Request):
        # Mirrors `app.dependencies._maybe_apply_impersonation`: stash the REAL
        # user on `request.state.real_user` regardless, so `get_actor_user_id`
        # resolves it the same way a real impersonation session would (B2).
        #
        # `Request` MUST be imported at MODULE level (see the top of this file),
        # not inside this function/`_wire_overrides`: FastAPI's dependency-override
        # mechanism rebuilds the dependant from the OVERRIDE callable's own type
        # hints (`get_dependant` -> `get_typed_signature` -> `typing.get_type_hints`,
        # which reads off `call.__globals__` - the DEFINING MODULE's globals, even
        # for a function nested inside another). With `from __future__ import
        # annotations` active in this file, `request: Request` is a deferred string
        # annotation; if `Request` were only a NAME LOCAL to `_wire_overrides` (a
        # local `from fastapi import Request`), `get_type_hints` cannot resolve it
        # against the module's globals, FastAPI falls back to treating `request` as
        # an ordinary field, and every route through this harness 422s with
        # "Field required: query.request" - the exact failure the previous attempt
        # at this hit.
        request.state.real_user = e.principal_real or e.principal
        return e.principal

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[get_current_user_or_api_key] = _override_get_current_user

    async def _override_scope():
        set_company_scope(db, e.scope)
        return e.scope

    app.dependency_overrides[apply_company_scope] = _override_scope


@pytest.fixture
def cost_price_env():
    with blank_session() as db:
        e = CostPriceEnv(db)
        _wire_overrides(e, db)
        e.client = TestClient(app)
        try:
            yield e
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def cost_price_env_live():
    """Same `CostPriceEnv`/`TestClient` wiring as `cost_price_env`, but over a REAL
    connection to the live database (rolled back at teardown, `tests/scm/conftest.py`'s
    `scm_app` pattern) instead of a `blank_session()` scratch schema.

    Needed for exactly one seam: `supplier_code_matcher._remember` (the auto-alias write
    at Apply, AC-S1-12) does `INSERT INTO scm.supplier_product_code_alias ...` with the
    schema HARDCODED in the SQL text, so it never goes through `blank_session()`'s
    `schema_translate_map` - it always lands on the REAL `scm.supplier_product_code_alias`
    table, whose `supplier_id` FK was bound at CREATE TIME to the real `public.suppliers`,
    not a scratch schema's copy. A supplier seeded in a scratch schema is therefore never
    "present in table suppliers" from that constraint's point of view, and the insert 500s
    with a `ForeignKeyViolation` - not a bug in the test, a real substrate mismatch this
    ONE seam has and the rest of the suite does not (same reasoning
    `tests/scm/test_supplier_code_matcher.py` documents for using `pg_session` instead of a
    sqlite/scratch fixture: the ladder's normalisation and this alias write are real SQL
    against real schema-qualified tables).

    The new cost_price_* tables already exist for real on the CI/dev database this points
    at (`alembic upgrade head` has run there - confirmed by querying
    `information_schema.tables` directly), so nothing here needs `create_all`.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import sessionmaker

    from app.database import engine

    connection = engine.connect()
    trans = connection.begin()
    Session = sessionmaker(bind=connection)
    db = Session()
    db.begin_nested()

    @event.listens_for(db, "after_transaction_end")
    def _restart_savepoint(session, transaction):  # noqa: ANN001
        if transaction.nested and not transaction._parent.nested:
            session.begin_nested()

    e = CostPriceEnv(db)
    _wire_overrides(e, db)
    e.client = TestClient(app)
    try:
        yield e
    finally:
        app.dependency_overrides.clear()
        event.remove(db, "after_transaction_end", _restart_savepoint)
        db.close()
        trans.rollback()
        connection.close()
