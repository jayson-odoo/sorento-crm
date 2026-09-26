"""RED tests for RBAC on the cost-price lane (#1288, Lane A).

Covers AC-S1-16, AC-S1-25, AC-S2-14, AC-S2-19 (`cost-price-lane-a-test-list.md`).
Migration tests follow the `test_autocount_pull_sr1.py` / `test_migration_414_...` pattern:
`upgrade()` runs against a `blank_session()` connection through a `MigrationContext`, inside
the transaction the fixture rolls back, so nothing escapes to the shared schema.

TEST-FIRST: the migration file, the routes and the permission slugs do not exist yet.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from tests.fixtures.cost_price.taiyang_shapes import LETTERHEAD_TEXT, simple_price_list_workbook
from tests.support.cost_price_env import (
    PS_ADD_PERM,
    PS_DELETE_PERM,
    PS_EDIT_PERM,
    PS_VIEW_PERM,
    PURCHASING_SOURCE_PERM,
    UPLOAD_PERM,
    VERIFY_PERM,
    VIEW_PERM,
    cost_price_env,
)
from tests._pg_fixture import blank_session, unique_code

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "cpc1_supplier_cost_lists.py"
)


def _migration_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("zzt_migration_cpc1", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration(db, module, direction: str = "upgrade") -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _role(db, slug: str):
    from app.models.user import UserRole

    row = UserRole(
        id=str(uuid.uuid4()), slug=slug, name=slug, description="",
        is_protected=False, is_default=False,
    )
    db.add(row)
    db.flush()
    return row


def _permission(db, slug: str):
    from app.models.user import UserPermission

    row = db.query(UserPermission).filter_by(slug=slug).one_or_none()
    if row is None:
        row = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
        db.add(row)
        db.flush()
    return row


def _grant(db, role_id: str, permission_id: str):
    from app.models.user import UserRolePermission

    db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_id=permission_id))


def _role_slugs(db, role_id: str) -> set[str]:
    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT p.slug FROM user_role_permissions rp "
            "JOIN user_permissions p ON p.id = rp.permission_id WHERE rp.role_id = :r"
        ),
        {"r": role_id},
    ).all()
    return {r[0] for r in rows}


# --------------------------------------------------------------------------------- AC-S1-16


@pytest.mark.parametrize(
    "call,perms_needed",
    [
        ("probe", "upload"),
        ("upload", "upload"),
        ("patch_line", "upload"),
        ("discard", "upload"),
        ("apply", "upload"),
        ("list_sets", "view"),
        ("detail", "view"),
    ],
)
def test_routes_need_upload_or_view(cost_price_env, call, perms_needed):
    e = cost_price_env
    no_perm = e.user()
    e.as_user(no_perm)
    data = simple_price_list_workbook([("ZZCPC-RBAC-001", "cfg", 100)], letterhead=LETTERHEAD_TEXT)
    supplier_id = str(uuid.uuid4())
    set_id = str(uuid.uuid4())

    if call == "probe":
        r = e.probe(data)
    elif call == "upload":
        r = e.upload(data, supplier_id=supplier_id, currency="CNY")
    elif call == "patch_line":
        r = e.patch_line(set_id, str(uuid.uuid4()), {"skipped": True})
    elif call == "discard":
        r = e.discard(set_id)
    elif call == "apply":
        r = e.apply(set_id)
    elif call == "list_sets":
        r = e.list_sets()
    elif call == "detail":
        r = e.detail(set_id)
    else:
        raise AssertionError(call)

    assert r.status_code == 403, (call, r.text)


# --------------------------------------------------------------------------------- AC-S1-25 / AC-S2-19


def test_migration_file_has_the_pinned_revision_id():
    assert MIGRATION_PATH.exists(), f"missing {MIGRATION_PATH}"
    module = _migration_module()
    assert module.revision == "cpc1_supplier_cost_lists"
    assert len(module.revision) <= 32


def test_migration_grants_upload_view_verify_to_purchasing_roles_only():
    with blank_session() as db:
        source_perm = _permission(db, PURCHASING_SOURCE_PERM)

        purchasing_role = _role(db, unique_code("cpcpurch"))
        _grant(db, purchasing_role.id, source_perm.id)

        integration_role = _role(db, "integration_zzt_cpc")
        _grant(db, integration_role.id, source_perm.id)

        admin_role = _role(db, "admin")
        superadmin_role = _role(db, "superadmin")

        bystander_role = _role(db, unique_code("cpcbystander"))  # holds neither source perm
        db.commit()

        module = _migration_module()
        _run_migration(db, module, "upgrade")
        _run_migration(db, module, "upgrade")  # idempotent

        for role in (purchasing_role, admin_role, superadmin_role):
            slugs = _role_slugs(db, role.id)
            assert {UPLOAD_PERM, VIEW_PERM, VERIFY_PERM} <= slugs, (role.slug, slugs)

        integration_slugs = _role_slugs(db, integration_role.id)
        assert not (integration_slugs & {UPLOAD_PERM, VIEW_PERM, VERIFY_PERM}), integration_slugs

        bystander_slugs = _role_slugs(db, bystander_role.id)
        assert not (bystander_slugs & {UPLOAD_PERM, VIEW_PERM, VERIFY_PERM}), bystander_slugs

        from sqlalchemy import text

        dup = db.execute(
            text(
                "SELECT count(*) FROM user_role_permissions rp "
                "JOIN user_permissions p ON p.id = rp.permission_id "
                "WHERE rp.role_id = :r AND p.slug = :slug"
            ),
            {"r": purchasing_role.id, "slug": UPLOAD_PERM},
        ).scalar()
        assert dup == 1, "a second migration run must not duplicate the grant"


# --------------------------------------------------------------------------------- AC-S2-14


def test_product_supplier_crud_requires_permissions(cost_price_env):
    e = cost_price_env
    no_perm = e.user()
    e.as_user(no_perm)
    supplier = e.supplier()
    product = e.product()

    create = e.create_product_supplier({
        "product_id": str(product.id), "supplier_id": str(supplier.id),
        "standard_lead_time_days": 30,
    })
    assert create.status_code == 403, create.text

    link = e.link(product, supplier)

    update = e.update_product_supplier(str(link.id), {"standard_lead_time_days": 45})
    assert update.status_code == 403, update.text

    delete = e.delete_product_supplier(str(link.id))
    assert delete.status_code == 403, delete.text

    adder = e.user(PS_ADD_PERM)
    e.as_user(adder)
    created = e.create_product_supplier({
        "product_id": str(product.id), "supplier_id": str(e.supplier().id),
        "standard_lead_time_days": 30,
    })
    assert created.status_code == 201, created.text


def test_migration_sweeps_product_supplier_writes():
    with blank_session() as db:
        view_perm = _permission(db, PS_VIEW_PERM)
        source_perm = _permission(db, PURCHASING_SOURCE_PERM)

        view_holder_role = _role(db, unique_code("cpcview"))
        _grant(db, view_holder_role.id, view_perm.id)

        purchasing_role = _role(db, unique_code("cpcpurchps"))
        _grant(db, purchasing_role.id, source_perm.id)

        integration_role = _role(db, "integration_zzt_ps")
        _grant(db, integration_role.id, view_perm.id)
        db.commit()

        module = _migration_module()
        _run_migration(db, module, "upgrade")
        _run_migration(db, module, "upgrade")

        view_holder_slugs = _role_slugs(db, view_holder_role.id)
        assert {PS_ADD_PERM, PS_EDIT_PERM, PS_DELETE_PERM} <= view_holder_slugs

        purchasing_slugs = _role_slugs(db, purchasing_role.id)
        assert {PS_VIEW_PERM, PS_ADD_PERM, PS_EDIT_PERM, PS_DELETE_PERM} <= purchasing_slugs

        integration_slugs = _role_slugs(db, integration_role.id)
        assert not (integration_slugs & {PS_ADD_PERM, PS_EDIT_PERM, PS_DELETE_PERM})


# --------------------------------------------------------------------------------- AC-S2-19


def test_api_key_principal_cannot_decide_return_or_apply():
    """`verify` is a Sorento-staff-only permission (plan section 10): the legacy `system`
    API-key principal must never reach decide/decide-all/return/apply, so those four
    routes are pinned to depend on `get_current_user`, never `get_current_user_or_api_key`.
    """
    from app.dependencies import get_current_user_or_api_key
    from app.main import app

    watched_paths = {
        "/api/v1/procurement/cost-price-changes/{id}/lines/{line_id}/decision",
        "/api/v1/procurement/cost-price-changes/{id}/decide-all",
        "/api/v1/procurement/cost-price-changes/{id}/return",
        "/api/v1/procurement/cost-price-changes/{id}/apply",
    }
    found = 0
    for route in app.routes:
        path = getattr(route, "path", None)
        if path not in watched_paths:
            continue
        found += 1
        dependant = getattr(route, "dependant", None)
        callables = {dep.call for dep in (dependant.dependencies if dependant else [])}
        assert get_current_user_or_api_key not in callables, path

    assert found == len(watched_paths), (
        "the four verify-only routes are not mounted yet: "
        f"found {found} of {len(watched_paths)}"
    )
