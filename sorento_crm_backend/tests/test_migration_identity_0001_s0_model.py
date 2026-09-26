"""Migration `identity_0001_s0_model` (#1280 S0): up/down against the REAL schema.

`documentation/plans/identity/s0-contract.md` section 1. The module does not exist
yet, so `_load()` raises `FileNotFoundError` and every test below fails on that -
a missing migration file, not a fixture bug. Once it exists, this exercises the
real DDL (email nullable + check constraint, the two unique indexes, the two new
columns, the seeded roles) and the pre-flight / link-backfill logic, inside ONE
rolled-back transaction on the real connection (`tests/test_migration_*.py` runs
serially, outside xdist - LESSONS-LEARNT 97).

By the time this migration exists, `scripts.bootstrap_env` builds the CI database
from the (by-then updated) ORM models, so the schema this test's outer transaction
starts from already IS the post-migration shape. `_downgrade()` strips it back
inside the transaction, the test seeds its own scenario, `_upgrade(concurrently=False)`
replays the real logic, and the whole thing rolls back at teardown either way.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.database import engine

MODULE_NAME = "identity_0001_s0_model"
VERSIONS = (Path(__file__).resolve().parent / ".." / "alembic" / "versions").resolve()
PREFIX = "ZZT-mig-identity"


def _load():
    path = VERSIONS / f"{MODULE_NAME}.py"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist yet - alembic/versions/{MODULE_NAME}.py is S0's deliverable"
        )
    spec = importlib.util.spec_from_file_location(f"m_{MODULE_NAME}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _current_other_head() -> str:
    """The single alembic head of the graph WITHOUT this migration (computed, never
    hard-coded). Once this migration exists it IS the head, so `get_heads()` minus
    itself is empty; the head it must sit on is the one left when it is removed."""
    cfg = Config(str(Path(__file__).resolve().parent / ".." / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    others = [r for r in script.walk_revisions() if r.revision != MODULE_NAME]
    pointed_at: set[str] = set()
    for rev in others:
        down = rev.down_revision
        if down is None:
            continue
        pointed_at.update(down if isinstance(down, (tuple, list)) else (down,))
    heads = [r.revision for r in others if r.revision not in pointed_at]
    assert len(heads) == 1, f"expected exactly one other head, found {heads}"
    return heads[0]


def _run(conn, fn):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        fn()


def _mk_id() -> str:
    return str(uuid.uuid4())


def test_revision_id_fits_alembic_version_and_sits_on_the_current_head():
    module = _load()
    assert len(module.revision) <= 32
    assert module.down_revision == _current_other_head()


def test_preflight_blocks_on_case_duplicate_emails_names_users_no_ids():
    module = _load()
    with engine.connect() as raw:
        outer = raw.begin()
        try:
            # The CI schema is already post-migration: strip it first, or
            # uq_users_email_lower refuses the case-duplicate this test seeds.
            _run(raw, module._downgrade)
            nested = raw.begin_nested()
            a_id, b_id = _mk_id(), _mk_id()
            stem = f"{PREFIX}-dup-{uuid.uuid4().hex[:6]}"
            raw.execute(
                sa.text(
                    "INSERT INTO users (id, email, name, status, is_trashed, is_protected, "
                    "respond_synced, daily_sla_summary_subscribed) VALUES "
                    "(:a_id, :email_a, :name_a, 'ACTIVE', false, false, 'pending', true), "
                    "(:b_id, :email_b, :name_b, 'ACTIVE', false, false, 'pending', true)"
                ),
                {
                    "a_id": a_id,
                    "email_a": f"{stem}@example.com",
                    "name_a": f"{PREFIX} Alice",
                    "b_id": b_id,
                    "email_b": f"{stem}@EXAMPLE.COM",
                    "name_b": f"{PREFIX} Bob",
                },
            )
            with pytest.raises(RuntimeError) as excinfo:
                _run(raw, lambda: module._upgrade(concurrently=False))
            message = str(excinfo.value)
            assert f"{PREFIX} Alice" in message
            assert f"{PREFIX} Bob" in message
            assert a_id not in message
            assert b_id not in message
            nested.rollback()
        finally:
            outer.rollback()


def test_upgrade_backfills_links_seeds_roles_and_is_idempotent():
    module = _load()
    with engine.connect() as raw:
        outer = raw.begin()
        try:
            _run(raw, module._downgrade)

            stem = f"{PREFIX}-{uuid.uuid4().hex[:8]}"
            phone_a, phone_b, phone_trashed, phone_integration = (
                f"+6011{uuid.uuid4().int % 10_000_000:07d}" for _ in range(4)
            )
            c1 = _mk_id()
            raw.execute(
                sa.text(
                    "INSERT INTO respond_contacts (id, phone_number, name) VALUES (:id, :phone, :name)"
                ),
                {"id": c1, "phone": phone_a, "name": f"{stem} Contact One"},
            )
            c_held = _mk_id()
            raw.execute(
                sa.text(
                    "INSERT INTO respond_contacts (id, phone_number, name) VALUES (:id, :phone, :name)"
                ),
                {"id": c_held, "phone": phone_b, "name": f"{stem} Contact Held"},
            )
            # users.contact_number is unique (uq_users_contact_number), so the trashed and
            # the integration user each get their OWN phone, matching their own unique,
            # unclaimed contact: the only reason left for not linking them is the rule.
            for phone, label in ((phone_trashed, "Trashed"), (phone_integration, "Integration")):
                raw.execute(
                    sa.text(
                        "INSERT INTO respond_contacts (id, phone_number, name) VALUES (:id, :phone, :name)"
                    ),
                    {"id": _mk_id(), "phone": phone, "name": f"{stem} Contact {label}"},
                )

            user_a = _mk_id()  # unlinked, phone matches c1 uniquely -> gets linked
            user_d = _mk_id()  # already holds c_held
            user_b = _mk_id()  # phone matches c_held, but c_held is claimed -> stays unlinked
            user_trashed = _mk_id()  # trashed, phone matches its own free contact -> stays unlinked
            user_integration = _mk_id()  # is_integration, same -> stays unlinked
            raw.execute(
                sa.text(
                    "INSERT INTO users (id, email, name, status, contact_number, respond_contact_id, "
                    "is_trashed, is_integration, is_protected, respond_synced, "
                    "daily_sla_summary_subscribed) VALUES "
                    "(:user_a, :e_a, :n_a, 'ACTIVE', :phone_a, NULL, false, false, false, 'pending', true),"
                    "(:user_d, :e_d, :n_d, 'ACTIVE', NULL, :c_held, false, false, false, 'pending', true),"
                    "(:user_b, :e_b, :n_b, 'ACTIVE', :phone_b, NULL, false, false, false, 'pending', true),"
                    "(:user_trashed, :e_t, :n_t, 'ACTIVE', :phone_t, NULL, true, false, false, 'pending', true),"
                    "(:user_integration, :e_i, :n_i, 'ACTIVE', :phone_i, NULL, false, true, false, 'pending', true)"
                ),
                {
                    "user_a": user_a, "e_a": f"{stem}-a@example.com", "n_a": f"{stem} A", "phone_a": phone_a,
                    "user_d": user_d, "e_d": f"{stem}-d@example.com", "n_d": f"{stem} D", "c_held": c_held,
                    "user_b": user_b, "e_b": f"{stem}-b@example.com", "n_b": f"{stem} B", "phone_b": phone_b,
                    "user_trashed": user_trashed, "e_t": f"{stem}-t@example.com", "n_t": f"{stem} T",
                    "phone_t": phone_trashed,
                    "user_integration": user_integration, "e_i": f"{stem}-i@example.com", "n_i": f"{stem} I",
                    "phone_i": phone_integration,
                },
            )

            users_before = raw.execute(sa.text("SELECT count(*) FROM users")).scalar()
            assignments_before = raw.execute(
                sa.text("SELECT count(*) FROM user_role_assignments")
            ).scalar()

            _run(raw, lambda: module._upgrade(concurrently=False))

            def _contact_of(uid: str):
                return raw.execute(
                    sa.text("SELECT respond_contact_id FROM users WHERE id = :id"), {"id": uid}
                ).scalar()

            assert _contact_of(user_a) == c1, "unique unclaimed phone match must be linked"
            assert _contact_of(user_d) == c_held
            assert _contact_of(user_b) is None, "already-claimed contact must not be double-linked"
            assert _contact_of(user_trashed) is None, "a trashed user must not be backfilled"
            assert _contact_of(user_integration) is None, "an integration user must not be backfilled"

            audit_rows = raw.execute(
                sa.text(
                    "SELECT old_values, new_values, action, description FROM audit_logs "
                    "WHERE entity_type = 'users' AND entity_id = :id AND actor_type = 'system'"
                ),
                {"id": user_a},
            ).mappings().all()
            assert len(audit_rows) == 1
            row = audit_rows[0]
            assert row["action"] == "UPDATE"
            assert row["old_values"].get("respond_contact_id") is None
            assert row["new_values"].get("respond_contact_id") == c1
            assert MODULE_NAME in (row["description"] or "")

            users_after = raw.execute(sa.text("SELECT count(*) FROM users")).scalar()
            assignments_after = raw.execute(
                sa.text("SELECT count(*) FROM user_role_assignments")
            ).scalar()
            assert users_after == users_before
            assert assignments_after == assignments_before

            for slug in ("salesperson", "portal_user"):
                role = raw.execute(
                    sa.text(
                        "SELECT id, is_protected, is_default FROM user_roles WHERE slug = :slug"
                    ),
                    {"slug": slug},
                ).mappings().first()
                assert role is not None, f"migration must seed the {slug!r} role"
                assert role["is_protected"] is True
                assert role["is_default"] is False
                perm_count = raw.execute(
                    sa.text("SELECT count(*) FROM user_role_permissions WHERE role_id = :rid"),
                    {"rid": role["id"]},
                ).scalar()
                assert perm_count == 0

            insp = sa.inspect(raw)
            cols = {c["name"] for c in insp.get_columns("users")}
            assert "phone_verified_at" in cols
            users_email_col = next(c for c in insp.get_columns("users") if c["name"] == "email")
            assert users_email_col["nullable"] is True

            constraint_names = {
                r[0]
                for r in raw.execute(
                    sa.text(
                        "SELECT conname FROM pg_constraint WHERE conrelid = 'users'::regclass"
                    )
                )
            }
            assert "ck_users_email_or_phone" in constraint_names

            index_names = {
                r[0]
                for r in raw.execute(
                    sa.text("SELECT indexname FROM pg_indexes WHERE tablename = 'users'")
                )
            }
            assert "uq_users_email_lower" in index_names
            assert "uq_users_respond_contact_id" in index_names

            session_cols = {c["name"] for c in insp.get_columns("user_sessions")}
            assert "auth_method" in session_cols

            audit_cols = {c["name"] for c in insp.get_columns("audit_logs")}
            for col in (
                "actor_type", "real_user_id", "auth_method", "session_id",
                "integration_id", "job_id", "user_agent",
            ):
                assert col in audit_cols

            # Re-running the backfill logic must be a true no-op: no new link, no
            # duplicate audit row for the user already linked above.
            _run(raw, lambda: module._upgrade(concurrently=False))
            assert _contact_of(user_a) == c1
            audit_rows_again = raw.execute(
                sa.text(
                    "SELECT count(*) FROM audit_logs WHERE entity_type = 'users' "
                    "AND entity_id = :id AND actor_type = 'system'"
                ),
                {"id": user_a},
            ).scalar()
            assert audit_rows_again == 1, "re-running the backfill must not duplicate the audit row"
        finally:
            outer.rollback()


# --------------------------------------------------------------------------- #
# Security review round: INVALID indexes from an interrupted CONCURRENTLY      #
# build, and blank phone numbers in the backfill.                              #
# --------------------------------------------------------------------------- #
def _index_valid(conn, name: str):
    return conn.execute(
        sa.text(
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE c.relname = :name"
        ),
        {"name": name},
    ).scalar()


def test_upgrade_drops_and_rebuilds_an_invalid_unique_index():
    """A failed CREATE INDEX CONCURRENTLY leaves an INVALID index that `IF NOT EXISTS`
    would silently keep. The real path is reproduced by marking the index invalid in
    pg_index (the CI role is a superuser), inside the rolled-back transaction."""
    module = _load()
    with engine.connect() as raw:
        outer = raw.begin()
        try:
            for name in ("uq_users_email_lower", "uq_users_respond_contact_id"):
                raw.execute(
                    sa.text("UPDATE pg_index SET indisvalid = false WHERE indexrelid = to_regclass(:name)"),
                    {"name": name},
                )
                assert _index_valid(raw, name) is False

            _run(raw, lambda: module._upgrade(concurrently=False))

            for name in ("uq_users_email_lower", "uq_users_respond_contact_id"):
                assert _index_valid(raw, name) is True, f"{name} was left INVALID"
        finally:
            outer.rollback()


def test_ensure_index_raises_naming_the_index_when_the_rebuild_stays_invalid():
    """The give-up path, against a fake bind: the index reads INVALID before and after
    the rebuild, so the migration stops and names it rather than carrying on."""
    module = _load()
    executed: list[str] = []

    class _Result:
        def scalar(self):
            return False  # indisvalid = false, every time

    class _FakeBind:
        def execute(self, statement, params=None):
            executed.append(str(statement))
            return _Result()

    with pytest.raises(RuntimeError) as excinfo:
        module._ensure_index(
            _FakeBind(),
            "uq_users_email_lower",
            "CREATE UNIQUE INDEX {c} IF NOT EXISTS uq_users_email_lower ON users (lower(email))",
            concurrently=False,
        )
    assert "uq_users_email_lower" in str(excinfo.value)
    assert any("DROP INDEX" in s for s in executed), "an INVALID index must be dropped before the rebuild"


def test_backfill_never_matches_a_blank_phone_number():
    module = _load()
    with engine.connect() as raw:
        outer = raw.begin()
        try:
            stem = f"{PREFIX}-blank-{uuid.uuid4().hex[:8]}"
            contact_id = _mk_id()
            raw.execute(
                sa.text("INSERT INTO respond_contacts (id, phone_number, name) VALUES (:id, '', :name)"),
                {"id": contact_id, "name": f"{stem} Blank Contact"},
            )
            user_id = _mk_id()
            raw.execute(
                sa.text(
                    "INSERT INTO users (id, email, name, status, contact_number, is_trashed, is_integration, "
                    "is_protected, respond_synced, daily_sla_summary_subscribed) VALUES "
                    "(:id, :email, :name, 'ACTIVE', '', false, false, false, 'pending', true)"
                ),
                {"id": user_id, "email": f"{stem}@example.com".lower(), "name": f"{stem} Blank"},
            )

            _run(raw, lambda: module._upgrade(concurrently=False))

            linked = raw.execute(
                sa.text("SELECT respond_contact_id FROM users WHERE id = :id"), {"id": user_id}
            ).scalar()
            assert linked is None, "a blank phone must never be linked to a blank-phone contact"
        finally:
            outer.rollback()
