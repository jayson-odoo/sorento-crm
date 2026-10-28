"""Migration `pp4_0001_request_view_own` (lane PORTAL-P4-REQUESTS): P4-7.

Insert-only: 4 `view_own` slugs + the price tag `view_own`; role `salesperson` is granted those, the 4 `.add`,
and (v1.2) the sample request / NPA / sales opportunity / price tag create-side slugs.
CI builds the schema with create_all + stamp head, so the data migration never runs there: the
test executes upgrade/downgrade itself inside one rolled-back transaction (shape of
`test_migration_pp3_0001.py`).
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.database import engine
from app.rbac.permission_registry import PERMISSION_REGISTRY

VERSIONS = (Path(__file__).resolve().parent / ".." / "alembic" / "versions").resolve()
NAME = "pp4_0001_request_view_own"
VIEW_OWN = {
    "procurement.stock_inquiries.view_own",
    "complaint_management.complaints.view_own",
    "procurement.purchase_requests.view_own",
    "procurement.sponsorship_forms.view_own",
}
ADD = {
    "procurement.stock_inquiries.add",
    "complaint_management.complaints.add",
    "procurement.purchase_requests.add",
    "procurement.sponsorship_forms.add",
}
SUBMIT = "projects.registrations.submit"
# v1.2 (sign-off by the lead): the four extra kinds. The price tag view_own is NEW (created here);
# every other slug below predates pp4_0001 (pp2_0001 view_own, the kinds' own create / add / edit
# slugs, the Dealer Kit menu gate) and is only granted to the salesperson.
PT_VIEW_OWN = "dealer_kit.price_tag_requests.view_own"
EXTRA_GRANTED = {
    "projects.sample_requests.view_own",
    "projects.sample_requests.create",
    "procurement.new_product_applications.view_own",
    "procurement.new_product_applications.create",
    "sales.opportunities.view_own",
    "sales.opportunities.add",
    "sales.opportunities.edit",
    "dealer_kit.price_tag_requests.create",
}
CREATED = VIEW_OWN | {SUBMIT, PT_VIEW_OWN}  # slugs the migration inserts
PRIOR = "sales.customer_asks.view"


def _load():
    spec = importlib.util.spec_from_file_location(f"m_{NAME}", VERSIONS / f"{NAME}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    with Operations.context(MigrationContext.configure(conn)):
        fn()


def _role(conn, slug: str) -> str:
    existing = conn.execute(sa.text("SELECT id FROM user_roles WHERE slug = :s"), {"s": slug}).scalar()
    if existing:
        return existing
    rid = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, is_default) "
            "VALUES (:id, :s, :n, false, false, false)"
        ),
        {"id": rid, "s": slug, "n": f"{slug}-{rid[:6]}"},
    )
    return rid


def _perm(conn, slug: str) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO user_permissions (id, slug, name, description, created_at) "
            "SELECT gen_random_uuid()::text, :s, :s, :s, now() "
            "WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :s)"
        ),
        {"s": slug},
    )


def _grant(conn, role_id: str, slug: str) -> None:
    _perm(conn, slug)
    conn.execute(
        sa.text(
            "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
            "SELECT gen_random_uuid()::text, :r, p.id, now() FROM user_permissions p WHERE p.slug = :s "
            "ON CONFLICT (role_id, permission_id) DO NOTHING"
        ),
        {"r": role_id, "s": slug},
    )


def _held(conn, role_id: str) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            sa.text(
                "SELECT p.slug FROM user_role_permissions rp JOIN user_permissions p ON p.id = rp.permission_id "
                "WHERE rp.role_id = :r"
            ),
            {"r": role_id},
        )
    }


def _slug_exists(conn, slug: str) -> bool:
    return bool(conn.execute(sa.text("SELECT 1 FROM user_permissions WHERE slug = :s"), {"s": slug}).scalar())


def _clean(conn, role_id: str) -> None:
    """Start from a salesperson that holds none of the slugs (the dev copy may already)."""
    conn.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE role_id = :r AND permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = ANY(:s))"
        ),
        {"r": role_id, "s": list(CREATED | ADD | EXTRA_GRANTED)},
    )


def test_revision_fits_alembic_version_and_sits_on_pp3_0001():
    module = _load()
    assert module.revision == NAME
    assert len(module.revision) <= 32
    assert module.down_revision == "pp3_0001_salesperson_grants"
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(VERSIONS.parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(VERSIONS.parent))
    assert ScriptDirectory.from_config(cfg).get_heads() == [NAME]


def test_the_registry_and_the_migration_declare_the_same_six_slugs():
    registry = {e["slug"]: e for e in PERMISSION_REGISTRY if e["slug"] in CREATED}
    assert set(registry) == CREATED
    assert registry[SUBMIT]["name"] == "Submit project registrations"
    assert registry[PT_VIEW_OWN]["name"] == "View Own Price Tag Requests"
    migration = {slug: (name, descr) for slug, name, descr in _load()._PERMS}
    assert set(migration) == CREATED
    for slug, (name, descr) in migration.items():
        assert registry[slug]["name"] == name
        assert registry[slug]["description"] == descr


def test_p4_7_creates_six_slugs_grants_salesperson_the_forms_slugs_and_is_rerunnable():
    module = _load()
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            for slug in ADD | EXTRA_GRANTED | {PRIOR}:
                _perm(conn, slug)
            sales = _role(conn, "salesperson")
            admin = _role(conn, "admin")
            other = _role(conn, f"zzt_other_{uuid.uuid4().hex[:6]}")
            _clean(conn, sales)
            _grant(conn, sales, PRIOR)
            _grant(conn, other, "procurement.stock_inquiries.add")
            before_admin, before_other = _held(conn, admin), _held(conn, other)

            _run(conn, module.upgrade)
            _run(conn, module.upgrade)  # idempotent

            for slug in CREATED:
                assert _slug_exists(conn, slug), slug
            assert _held(conn, sales) == CREATED | ADD | EXTRA_GRANTED | {PRIOR}
            assert _held(conn, admin) == before_admin
            assert _held(conn, other) == before_other
        finally:
            outer.rollback()


def test_p4_7_downgrade_removes_the_view_own_slugs_and_the_add_grants_only():
    module = _load()
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            for slug in ADD | EXTRA_GRANTED | {PRIOR}:
                _perm(conn, slug)
            sales = _role(conn, "salesperson")
            other = _role(conn, f"zzt_other_{uuid.uuid4().hex[:6]}")
            _clean(conn, sales)
            _grant(conn, sales, PRIOR)
            _grant(conn, other, "procurement.stock_inquiries.add")
            _run(conn, module.upgrade)
            assert _held(conn, sales) >= CREATED | ADD | EXTRA_GRANTED

            _run(conn, module.downgrade)

            for slug in CREATED:
                assert not _slug_exists(conn, slug), slug
            assert _held(conn, sales) & (CREATED | ADD | EXTRA_GRANTED) == set()
            assert PRIOR in _held(conn, sales)
            for slug in ADD | EXTRA_GRANTED:  # the slugs that predate this revision are not ours to drop
                assert _slug_exists(conn, slug), slug
            assert "procurement.stock_inquiries.add" in _held(conn, other)
        finally:
            outer.rollback()
