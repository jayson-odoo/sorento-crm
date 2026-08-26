"""Migration 422: the report_views table and the two new permission slugs (AC-B9).

The migration's own ``upgrade()`` runs here against a blank schema inside a transaction that
is rolled back, so what is under test is the CODE rather than whatever the local database
happens to hold. CI's database is empty and every role here is seeded by the test.

The grant sweep is the half that matters (PRINCIPLES.md DoD gate 3). A permission granted to
nobody is indistinguishable from a broken feature: whoever may already SEE a sponsorship form
gets the report, and whoever may EDIT one gets to publish a view for everybody else.

Run: pytest tests/test_migration_422_report_views.py -q
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

VIEW = "procurement.sponsorship_forms.view"
EDIT = "procurement.sponsorship_forms.edit"
REPORT = "procurement.sponsorship_forms.report"
PUBLISH = "reports.views.publish"

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "422_report_views_and_perms.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("zzt_migration_422", _MIGRATION)
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
        session.execute(text("DROP TABLE IF EXISTS report_views CASCADE"))
        for slug in (VIEW, EDIT):
            _permission(session, slug)
        yield session


# ------------------------------------------------------------------------- the table


def test_the_table_is_created(db):
    _run(db)
    assert db.execute(text("SELECT count(*) FROM report_views")).scalar() == 0


def _insert(db, *, report_key="sponsorship", owner=None, name="A view", is_default=False):
    from app.models.user import User

    owner_id = owner
    if owner_id is None:
        owner_id = str(uuid.uuid4())
        db.add(User(id=owner_id, email=f"{owner_id}@zzt.test", name="Owner", status="ACTIVE"))
        db.flush()
    db.execute(
        text(
            """
            INSERT INTO report_views
                (id, report_key, owner_user_id, name, view, is_shared, is_default)
            VALUES (gen_random_uuid(), :k, :o, :n, '{}'::jsonb, :d, :d)
            """
        ),
        {"k": report_key, "o": owner_id, "n": name, "d": is_default},
    )
    db.flush()
    return owner_id


def test_one_owner_cannot_repeat_a_view_name_within_a_report(db):
    _run(db)
    owner = _insert(db, name="Management default")
    with pytest.raises(IntegrityError):
        _insert(db, owner=owner, name="Management default")


def test_the_same_name_is_free_under_another_report(db):
    _run(db)
    owner = _insert(db, report_key="sponsorship", name="Mine")
    _insert(db, report_key="something_else", owner=owner, name="Mine")


def test_only_one_view_can_be_the_default_for_a_report(db):
    _run(db)
    _insert(db, name="First", is_default=True)
    with pytest.raises(IntegrityError):
        _insert(db, name="Second", is_default=True)


def test_two_reports_may_each_have_their_own_default(db):
    _run(db)
    _insert(db, report_key="sponsorship", name="First", is_default=True)
    _insert(db, report_key="something_else", name="First", is_default=True)


# -------------------------------------------------------------------- the permissions


def test_both_slugs_are_seeded(db):
    _run(db)
    slugs = {
        row[0]
        for row in db.execute(
            text("SELECT slug FROM user_permissions WHERE slug IN (:a, :b)"),
            {"a": REPORT, "b": PUBLISH},
        ).all()
    }
    assert slugs == {REPORT, PUBLISH}


def test_both_slugs_are_also_declared_in_the_permission_registry():
    """A create_all database (CI, bootstrap_env) never runs a migration body.

    A slug that lives only in the migration therefore does not exist there, and every report
    route answers 403 on a fresh install. Same gap the Dealer Kit and SCM blocks were added
    to close.
    """
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert REPORT in slugs
    assert PUBLISH in slugs


def test_a_sponsorship_viewer_gains_the_report(db):
    role = _role(db, "zzt_report_viewer")
    _grant(db, role, VIEW)

    _run(db)

    assert REPORT in _slugs_for(db, role)
    assert PUBLISH not in _slugs_for(db, role)


def test_a_sponsorship_editor_gains_the_publish_grant(db):
    role = _role(db, "zzt_report_editor")
    _grant(db, role, EDIT)

    _run(db)

    assert PUBLISH in _slugs_for(db, role)


def test_a_role_holding_neither_gains_nothing(db):
    role = _role(db, "zzt_report_outsider")

    _run(db)

    assert _slugs_for(db, role) == set()


def test_running_it_twice_changes_nothing(db):
    role = _role(db, "zzt_report_idempotent")
    _grant(db, role, VIEW)

    _run(db)
    first = _slugs_for(db, role)
    _run(db)

    assert _slugs_for(db, role) == first
    count = db.execute(
        text("SELECT count(*) FROM user_role_permissions WHERE role_id = :role"),
        {"role": role},
    ).scalar()
    assert count == len(first)


def test_downgrade_takes_the_grants_and_the_table_back(db):
    role = _role(db, "zzt_report_reversible")
    _grant(db, role, VIEW)
    _run(db)

    _run(db, "downgrade")

    assert REPORT not in _slugs_for(db, role)
    assert (
        db.execute(
            text("SELECT count(*) FROM user_permissions WHERE slug IN (:a, :b)"),
            {"a": REPORT, "b": PUBLISH},
        ).scalar()
        == 0
    )
    # The source slugs predate this migration; taking them would delete what it never made.
    assert VIEW in _slugs_for(db, role)
    assert (
        db.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = 'report_views'"
            )
        ).scalar()
        == 0
    )


def test_the_revision_chains_onto_the_current_head(db):
    module = _module()
    assert module.down_revision == "421_merge_closeconvo_searchable"
    assert len(module.revision) <= 32  # alembic_version.version_num is varchar(32)
