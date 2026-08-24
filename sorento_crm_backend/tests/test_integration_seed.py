"""Slice 5 of AutoCount Group A - seeding integrations, principals and roles.

  AC-AC-09  the env key is seeded once so n8n and the MCP server keep working
  AC-AC-09a the MCP server gets its own integration
  AC-AC-05b principals are is_integration and cannot log in interactively

The seeding lives here rather than inside the migration so it can be tested
directly and re-run safely. The migration is a thin caller.

Idempotency is not decoration: this runs against a live database, and a
migration that half-applied then re-ran must not produce duplicate principals
or a second legacy key.
"""
import pytest

from app.models.integration import Integration, IntegrationApiKey
from app.models.user import (
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from app.services.integration_key_crypto import hash_api_key
from app.services.integration_seed import (
    LEGACY_KEY_OWNER,
    SEEDED_INTEGRATIONS,
    seed_integrations,
)
from tests._pg_fixture import pg_empty_schema

_TABLES = [
    User.__table__,
    UserRole.__table__,
    UserRoleAssignment.__table__,
    UserPermission.__table__,
    UserRolePermission.__table__,
    Integration.__table__,
    IntegrationApiKey.__table__,
]


@pytest.fixture()
def db():
    """An empty Postgres schema, not the live one.

    Seeding is the one thing here that genuinely needs a blank slate: migration
    297 has already run against the real database, so "creates one integration
    per entry" would be asserting against rows this test did not create. The
    tables are still emitted from the real model DDL -- only the data is empty.
    """
    with pg_empty_schema(_TABLES) as session:
        _seed_admin_role(session)
        yield session


def _seed_admin_role(db):
    """A minimal stand-in for the real Admin role and an existing act-as user."""
    admin = UserRole(id="role-admin", slug="admin", name="Admin")
    db.add(admin)
    for slug in ("master_data.products.view", "master_data.products.edit", "orders.view"):
        perm = UserPermission(slug=slug, name=slug)
        db.add(perm)
        db.flush()
        db.add(UserRolePermission(role_id=admin.id, permission_id=perm.id))

    legacy_user = User(id="legacy-act-as", email="na@example.com", name="MCP User", status="ACTIVE")
    db.add(legacy_user)
    db.flush()
    db.add(UserRoleAssignment(user_id=legacy_user.id, role_id=admin.id))
    db.commit()
    return admin, legacy_user


class TestPrincipals:
    def test_creates_a_user_for_each_seeded_integration(self, db):
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")

        for name in SEEDED_INTEGRATIONS:
            # Look up by email, not display name: the label differs from the
            # integration key ("sorento-mcp" is shown as "Sorento MCP").
            user = db.query(User).filter(User.email == f"{name}@integrations.local").first()
            assert user is not None, f"no principal created for {name}"

    def test_principals_are_flagged_as_integrations(self, db):
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        principals = db.query(User).filter(User.is_integration.is_(True)).all()
        assert len(principals) == len(SEEDED_INTEGRATIONS)

    def test_principals_have_no_password_so_cannot_log_in(self, db):
        # AC-AC-05b. Interactive login rejects a null-password user outright,
        # so this is what actually enforces "machine principals cannot log in".
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        for user in db.query(User).filter(User.is_integration.is_(True)).all():
            assert user.password is None

    def test_principals_are_not_marked_is_protected(self, db):
        # is_protected selects notification recipients in automation_service;
        # marking these would enrol every integration into automation email.
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        for user in db.query(User).filter(User.is_integration.is_(True)).all():
            assert user.is_protected is False


class TestRoles:
    def test_each_integration_gets_its_own_role(self, db):
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        roles = db.query(UserRole).filter(UserRole.slug.like("integration_%")).all()
        assert len(roles) == len(SEEDED_INTEGRATIONS)

    def test_roles_are_separate_from_admin_so_one_can_be_revoked_alone(self, db):
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        for role in db.query(UserRole).filter(UserRole.slug.like("integration_%")).all():
            assert role.id != "role-admin"

    def test_roles_carry_the_admin_permission_set(self, db):
        # Decision: seed at parity with today's access rather than least
        # privilege, so nothing regresses at cutover. Narrowing n8n and the MCP
        # server is tracked as follow-up work, not delivered here.
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        admin_perms = {
            p.permission_id
            for p in db.query(UserRolePermission).filter_by(role_id="role-admin").all()
        }
        for role in db.query(UserRole).filter(UserRole.slug.like("integration_%")).all():
            granted = {
                p.permission_id
                for p in db.query(UserRolePermission).filter_by(role_id=role.id).all()
            }
            assert granted == admin_perms

    def test_each_principal_is_assigned_its_role(self, db):
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        for user in db.query(User).filter(User.is_integration.is_(True)).all():
            assert db.query(UserRoleAssignment).filter_by(user_id=user.id).count() == 1


class TestIntegrationRows:
    def test_creates_one_row_per_seeded_integration_plus_legacy(self, db):
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        names = {i.name for i in db.query(Integration).all()}
        # No extra legacy row: the env key lands on the n8n integration itself.
        assert names == set(SEEDED_INTEGRATIONS)

    def test_mcp_gets_its_own_integration(self, db):
        # AC-AC-09a: n8n reaches read-only tools through the MCP server, so
        # omitting it would break that path once the shared key retires.
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        assert db.query(Integration).filter_by(name="sorento-mcp").first() is not None

    def test_each_integration_points_at_its_own_principal(self, db):
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        rows = db.query(Integration).all()
        principals = [r.act_as_user_id for r in rows]
        assert all(principals)
        assert len(set(principals)) == len(principals), "principals must not be shared"

    def test_new_integrations_have_no_keys_until_an_admin_issues_one(self, db):
        # The plaintext is shown exactly once, and a migration has nobody to
        # show it to. Keys are issued deliberately, through the UI.
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        for name in SEEDED_INTEGRATIONS:
            if name == LEGACY_KEY_OWNER:
                continue  # carries the existing env key
            row = db.query(Integration).filter_by(name=name).one()
            assert db.query(IntegrationApiKey).filter_by(integration_id=row.id).count() == 0


class TestLegacyKey:
    def test_seeds_the_existing_key_so_current_callers_keep_working(self, db):
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        owner = db.query(Integration).filter_by(name=LEGACY_KEY_OWNER).one()
        key = db.query(IntegrationApiKey).filter_by(integration_id=owner.id).one()
        assert key.key_hash == hash_api_key("sk_legacy")

    def test_env_key_owner_uses_its_own_principal(self, db):
        # n8n owns the carried-over key, so it is attributed as n8n rather
        # than as a shared legacy identity nobody can tell apart.
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        owner = db.query(Integration).filter_by(name=LEGACY_KEY_OWNER).one()
        principal = db.query(User).filter(User.id == owner.act_as_user_id).one()
        assert principal.email == "n8n@integrations.local"

    def test_absent_env_key_seeds_no_legacy_key_rather_than_an_empty_hash(self, db):
        # AC-AC-09. An empty or null hash that authenticated anyone would be
        # the worst possible outcome of a missing env var.
        seed_integrations(db, external_api_key=None, legacy_act_as_user_id="legacy-act-as")
        assert db.query(IntegrationApiKey).count() == 0

    def test_blank_env_key_seeds_no_legacy_key(self, db):
        seed_integrations(db, external_api_key="   ", legacy_act_as_user_id="legacy-act-as")
        assert db.query(IntegrationApiKey).count() == 0


class TestIdempotency:
    def test_running_twice_creates_nothing_extra(self, db):
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        counts = (
            db.query(Integration).count(),
            db.query(IntegrationApiKey).count(),
            db.query(User).filter(User.is_integration.is_(True)).count(),
            db.query(UserRole).filter(UserRole.slug.like("integration_%")).count(),
        )

        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")

        assert counts == (
            db.query(Integration).count(),
            db.query(IntegrationApiKey).count(),
            db.query(User).filter(User.is_integration.is_(True)).count(),
            db.query(UserRole).filter(UserRole.slug.like("integration_%")).count(),
        )

    def test_rerun_does_not_duplicate_role_grants(self, db):
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        before = db.query(UserRolePermission).count()
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        assert db.query(UserRolePermission).count() == before

    def test_rerun_does_not_reissue_the_legacy_key(self, db):
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        seed_integrations(db, external_api_key="sk_legacy", legacy_act_as_user_id="legacy-act-as")
        assert db.query(IntegrationApiKey).count() == 1
