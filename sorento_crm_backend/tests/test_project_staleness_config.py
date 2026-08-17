"""S5b configuration behaviour: forked thresholds and the notify recipient rule.

AC-H4 is really two rules that pull against each other: a fork must START from the defaults
(otherwise every template silently has no ladder) but must never be OVERWRITTEN by a later
default change (otherwise a deliberately tuned template gets reverted by an admin editing
something else). The way out is copy-at-fork plus an explicit reapply action, and both halves
need pinning or the next refactor will collapse them into "always propagate".
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.models.status import Status
from app.models.user import User, UserPermission, UserRole, UserRoleAssignment, UserRolePermission
from app.services import project_seed_service, status_service

from ._pg_fixture import blank_session

MARKER = "zzt-stalecfg"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _default(db, key: str) -> Status:
    return (
        db.query(Status)
        .filter(
            Status.entity_type == "project",
            Status.scope_id.is_(None),
            Status.key == key,
        )
        .first()
    )


def _forked(db, scope_id: str, key: str) -> Status:
    return (
        db.query(Status)
        .filter(
            Status.entity_type == "project",
            Status.scope_id == scope_id,
            Status.key == key,
        )
        .first()
    )


def test_forking_a_graph_copies_the_dials():
    """A fork with NULL dials has no ladder and no weighted pipeline, which reads as a bug
    in the forecast rather than as an unconfigured template."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        scope_id = _uid()

        status_service.fork_graph(db, "project", scope_id)

        for key in ("registered", "quoted", "tendering"):
            source = _default(db, key)
            clone = _forked(db, scope_id, key)
            assert clone is not None, f"{key} did not fork"
            assert clone.stale_after_days == source.stale_after_days
            assert clone.win_probability == source.win_probability


def test_a_default_change_does_not_propagate_to_a_fork():
    """AC-H4's whole point. Silent propagation is indistinguishable from data loss to the
    person who tuned the fork."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        scope_id = _uid()
        status_service.fork_graph(db, "project", scope_id)

        clone = _forked(db, scope_id, "quoted")
        clone.stale_after_days = 3
        db.flush()

        _default(db, "quoted").stale_after_days = 60
        db.flush()

        db.refresh(clone)
        assert clone.stale_after_days == 3


def test_reapply_defaults_is_the_explicit_way_back():
    """An admin who WANTS the defaults asks for them, by name, and gets a count back so the
    UI can say what changed rather than claiming success silently."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        scope_id = _uid()
        status_service.fork_graph(db, "project", scope_id)

        clone = _forked(db, scope_id, "quoted")
        clone.stale_after_days = 3
        clone.win_probability = 99
        db.flush()

        changed = status_service.reapply_default_dials(db, "project", scope_id)
        db.refresh(clone)

        source = _default(db, "quoted")
        assert clone.stale_after_days == source.stale_after_days
        assert clone.win_probability == source.win_probability
        assert changed >= 1
        # Second call changes nothing, so the button is safe to double-click.
        assert status_service.reapply_default_dials(db, "project", scope_id) == 0


def test_reapply_defaults_matches_rungs_by_key_not_by_position():
    """A fork that deleted a rung or re-ordered them must still be matched correctly --
    sort_order is cosmetic, `key` is the documented stable identity (grill finding G3)."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        scope_id = _uid()
        status_service.fork_graph(db, "project", scope_id)

        # Reorder the fork and drop a rung it does not use.
        tendering = _forked(db, scope_id, "tendering")
        tendering.sort_order = 0
        tendering.stale_after_days = None
        dormant = _forked(db, scope_id, "dormant")
        db.delete(dormant)
        db.flush()

        status_service.reapply_default_dials(db, "project", scope_id)
        db.refresh(tendering)
        assert tendering.stale_after_days == _default(db, "tendering").stale_after_days


def test_management_is_resolved_from_the_permission_not_a_list():
    """Grill finding G20: one definition of management. A newly-promoted manager must start
    receiving warnings without anybody editing a recipient screen."""
    from app.services import project_notify_service as notify

    with blank_session() as db:
        permission = UserPermission(
            id=_uid(),
            name=f"{MARKER} view all financials",
            slug=notify.MANAGEMENT_PERMISSION,
        )
        role = UserRole(id=_uid(), name=f"{MARKER} Sales Manager", slug=f"{MARKER}-mgr")
        db.add_all([permission, role])
        db.flush()
        db.add(UserRolePermission(id=_uid(), role_id=role.id, permission_id=permission.id))

        manager_id = _uid()
        plain_id = _uid()
        departed_id = _uid()
        db.add_all(
            [
                User(
                    id=manager_id,
                    email=f"{manager_id}@zzt.test",
                    name=f"{MARKER} Manager",
                    status="ACTIVE",
                ),
                User(
                    id=plain_id,
                    email=f"{plain_id}@zzt.test",
                    name=f"{MARKER} Salesperson",
                    status="ACTIVE",
                ),
                # Same role, but no longer with the company. A departed manager who keeps
                # receiving warnings about projects they cannot open is worse than nobody
                # receiving them, because somebody assumes it is covered.
                User(
                    id=departed_id,
                    email=f"{departed_id}@zzt.test",
                    name=f"{MARKER} Departed Manager",
                    status="INACTIVE",
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                UserRoleAssignment(id=_uid(), user_id=manager_id, role_id=role.id),
                UserRoleAssignment(id=_uid(), user_id=departed_id, role_id=role.id),
            ]
        )
        db.flush()

        recipients = notify.management_user_ids(db)
        assert manager_id in recipients
        assert plain_id not in recipients
        assert departed_id not in recipients


def test_the_recipient_query_runs_against_the_REAL_schema():
    """Regression: `users.status` is a Postgres ENUM (`UserStatus`), not a varchar.

    The blank test schema is built from the models, where `status` is a plain String, so
    `upper(users.status)` passed every test here and then blew up on the first real sweep:
    `function upper("UserStatus") does not exist`. Any query in this file that touches a
    legacy column type has to be exercised against the actual database at least once.

    Read-only, and rolled back: it asserts the SQL is VALID, not what the live data holds.
    """
    from app.database import SessionLocal
    from app.services import project_notify_service as notify

    db = SessionLocal()
    try:
        recipients = notify.management_user_ids(db)
        assert isinstance(recipients, list)
    finally:
        db.rollback()
        db.close()


def test_a_failing_notification_does_not_lose_the_ladder_state():
    """"Best-effort" has to survive a failing SQL statement, not just a Python exception.

    The first real sweep proved the difference: the recipient query raised inside the
    notification, which poisoned the session, and the sweep's own commit then failed with
    `InFailedSqlTransaction` -- so 40 correctly-identified stale projects were rolled back by
    a broken email. The ladder is now committed BEFORE any notification is attempted, and
    each attempt runs in its own savepoint.
    """
    import uuid as _uuid
    from datetime import datetime, timedelta

    from app.models.projects import Project
    from app.models.user import User
    from app.services import project_service as prj
    from app.services import project_staleness_service as svc

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner_id = str(_uuid.uuid4())
        db.add(User(id=owner_id, email=f"{owner_id}@zzt.test", name=f"{MARKER} Owner"))
        db.flush()

        project = prj.register_project(
            db,
            company_id=str(company_id),
            actor_user_id=owner_id,
            developer_party_id=None,
            title=f"{MARKER} notify blows up",
            owner_user_id=owner_id,
        )
        project.last_meaningful_activity_at = datetime.utcnow() - timedelta(days=400)
        db.flush()

        original = svc._notify
        svc._notify = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("mail is down"))
        try:
            summary = svc.sweep(db)
        finally:
            svc._notify = original

        db.expire_all()
        fresh = db.query(Project).filter(Project.id == project.id).first()
        assert fresh.stale_level == 3, "the ladder must survive a failed notification"
        assert summary["raised"] >= 1
        assert summary["notified"] == 0
