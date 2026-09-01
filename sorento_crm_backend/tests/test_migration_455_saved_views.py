"""Migration 455: the saved_views table and the publish permission slug (AC-4.3, G9).

Mirrors `tests/test_migration_422_report_views.py` (`saved_views` generalises
`report_views` for S4, PLAN-scm-reorder-oi-feedback-1sep.md). The migration's own
`upgrade()` runs here against a blank schema inside a transaction that is rolled back, so
what is under test is the CODE rather than whatever the local database happens to hold.
CI's database is empty and every role here is seeded by the test.

The grant sweep is the half that matters (PRINCIPLES.md DoD gate 3): a permission granted
to nobody is indistinguishable from a broken feature, so whoever already holds
`scm.recommendation.manage` (the reorder plan grid is the first consumer) inherits
`list_query.saved_views.publish`.

Run: pytest tests/test_migration_455_saved_views.py -q
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.user import UserPermission, UserRole, UserRolePermission

from tests._pg_fixture import blank_session

SOURCE = "scm.recommendation.manage"
PUBLISH = "list_query.saved_views.publish"

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "455_saved_views_and_perms.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("zzt_migration_455", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str = "upgrade") -> None:
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(_module(), direction)()


def _permission(db, slug: str) -> str:
    row = db.query(UserPermission).filter_by(slug=slug).first()
    if row is None:
        row = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
        db.add(row)
        db.flush()
    return row.id


def _role(db, slug: str) -> str:
    row = UserRole(id=str(uuid.uuid4()), slug=slug, name=slug, description="", is_protected=False)
    db.add(row)
    db.flush()
    return row.id


def _grant(db, role_id: str, slug: str) -> None:
    db.add(
        UserRolePermission(
            id=str(uuid.uuid4()), role_id=role_id, permission_id=_permission(db, slug)
        )
    )
    db.flush()


def _slugs_for(db, role_id: str) -> set:
    rows = db.execute(
        text(
            """
            SELECT p.slug FROM user_role_permissions rp
            JOIN user_permissions p ON p.id = rp.permission_id
            WHERE rp.role_id = :role
            """
        ),
        {"role": role_id},
    ).all()
    return {row[0] for row in rows}


@pytest.fixture
def db():
    with blank_session() as session:
        # The blank schema is built from the models, so the table the migration creates is
        # already there. Drop it, so the DDL under test is what puts it back.
        session.execute(text("DROP TABLE IF EXISTS saved_views CASCADE"))
        _permission(session, SOURCE)
        yield session


# ------------------------------------------------------------------------- the table


def test_the_table_is_created(db):
    _run(db)
    assert db.execute(text("SELECT count(*) FROM saved_views")).scalar() == 0
    assert db.execute(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'saved_views' "
            "AND column_name = 'company_id'"
        )
    ).scalar() == 1


def test_an_existing_table_without_company_id_gets_it_added_and_backfilled(db):
    """S1 (PR #489 review round): the ADD-COLUMN branch this migration takes when
    `saved_views` predates `company_id` - the shared local database's shape before
    this change (`sorento_crm_backend/CLAUDE.md`)."""
    db.execute(
        text(
            """
            CREATE TABLE saved_views (
                id uuid PRIMARY KEY,
                listing_key text NOT NULL,
                owner_user_id varchar NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name text NOT NULL,
                view jsonb NOT NULL,
                is_shared boolean NOT NULL DEFAULT false,
                is_default boolean NOT NULL DEFAULT false,
                created_at timestamp NOT NULL DEFAULT now(),
                updated_at timestamp NOT NULL DEFAULT now()
            )
            """
        )
    )
    owner = str(uuid.uuid4())
    from app.models.user import User

    db.add(User(id=owner, email=f"{owner}@zzt.test", name="Pre-existing", status="ACTIVE"))
    db.flush()
    db.execute(
        text(
            """
            INSERT INTO saved_views (id, listing_key, owner_user_id, name, view)
            VALUES (gen_random_uuid(), 'zzt.dashboard.view::pre-existing', :o, 'Untouched', '{}'::jsonb)
            """
        ),
        {"o": owner},
    )
    db.flush()

    _run(db)

    assert db.execute(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'saved_views' "
            "AND column_name = 'company_id'"
        )
    ).scalar() == 1
    company_id = db.execute(
        text("SELECT company_id FROM saved_views WHERE name = 'Untouched'")
    ).scalar()
    assert str(company_id) == "00000000-0000-0000-0000-000000000001"


def _insert(db, *, listing_key="zzt.dashboard.view::reorder-plan-lines", owner=None, name="A view", is_default=False):
    from app.models.user import User

    owner_id = owner
    if owner_id is None:
        owner_id = str(uuid.uuid4())
        db.add(User(id=owner_id, email=f"{owner_id}@zzt.test", name="Owner", status="ACTIVE"))
        db.flush()
    db.execute(
        text(
            """
            INSERT INTO saved_views
                (id, listing_key, owner_user_id, name, view, is_shared, is_default)
            VALUES (gen_random_uuid(), :k, :o, :n, '{}'::jsonb, :d, :d)
            """
        ),
        {"k": listing_key, "o": owner_id, "n": name, "d": is_default},
    )
    db.flush()
    return owner_id


def test_one_owner_cannot_repeat_a_view_name_within_a_listing(db):
    _run(db)
    owner = _insert(db, name="My segment")
    with pytest.raises(IntegrityError):
        _insert(db, owner=owner, name="My segment")


def test_the_same_name_is_free_under_another_listing_key(db):
    _run(db)
    owner = _insert(db, listing_key="zzt.dashboard.view::reorder-plan-lines", name="Mine")
    _insert(db, listing_key="zzt.dashboard.view::something-else", owner=owner, name="Mine")


def test_only_one_view_can_be_the_default_for_a_listing_key(db):
    _run(db)
    _insert(db, name="First", is_default=True)
    with pytest.raises(IntegrityError):
        _insert(db, name="Second", is_default=True)


def test_two_listing_keys_may_each_have_their_own_default(db):
    _run(db)
    _insert(db, listing_key="zzt.dashboard.view::reorder-plan-lines", name="First", is_default=True)
    _insert(db, listing_key="zzt.dashboard.view::something-else", name="First", is_default=True)


# -------------------------------------------------------------------- the permissions


def test_the_slug_is_seeded(db):
    _run(db)
    slug = db.execute(
        text("SELECT slug FROM user_permissions WHERE slug = :s"), {"s": PUBLISH}
    ).scalar()
    assert slug == PUBLISH


def test_the_slug_is_also_declared_in_the_permission_registry():
    """A create_all database (CI bootstrap_env, a fresh install) never runs a migration
    body. A slug that lives only in the migration therefore does not exist there, and
    every publish/set-default route answers 403 on a fresh install - the same gap
    `test_migration_422_report_views.py` guards `reports.views.publish` against."""
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert PUBLISH in slugs


def test_a_recommendation_manager_gains_the_publish_grant(db):
    role = _role(db, "zzt_recommendation_manager")
    _grant(db, role, SOURCE)

    _run(db)

    assert PUBLISH in _slugs_for(db, role)


def test_a_role_holding_neither_gains_nothing(db):
    role = _role(db, "zzt_saved_views_outsider")

    _run(db)

    assert _slugs_for(db, role) == set()


def test_running_it_twice_changes_nothing(db):
    role = _role(db, "zzt_saved_views_idempotent")
    _grant(db, role, SOURCE)

    _run(db)
    first = _slugs_for(db, role)
    _run(db)

    assert _slugs_for(db, role) == first
    count = db.execute(
        text("SELECT count(*) FROM user_role_permissions WHERE role_id = :role"),
        {"role": role},
    ).scalar()
    assert count == len(first)


def test_downgrade_takes_the_grant_and_the_table_back(db):
    role = _role(db, "zzt_saved_views_reversible")
    _grant(db, role, SOURCE)
    _run(db)

    _run(db, "downgrade")

    assert PUBLISH not in _slugs_for(db, role)
    assert (
        db.execute(
            text("SELECT count(*) FROM user_permissions WHERE slug = :s"), {"s": PUBLISH}
        ).scalar()
        == 0
    )
    # The source slug predates this migration; taking it would delete what it never made.
    assert SOURCE in _slugs_for(db, role)
    assert (
        db.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = 'saved_views'"
            )
        ).scalar()
        == 0
    )


def test_the_revision_chains_onto_454_order_inquiry_born_ack(db):
    """PR #471 (order-inquiry auto-acknowledge, also chained on 453_shared_brand_attach)
    is declared to merge first in the 1 Sep batch order, so this revision was renumbered
    454 -> 455 and rechained to avoid two heads on main the moment both land - see this
    migration's own docstring and the PR #489 body."""
    module = _module()
    assert module.down_revision == "454_order_inquiry_born_ack"
    assert len(module.revision) <= 32  # alembic_version.version_num is varchar(32)
