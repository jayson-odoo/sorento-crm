"""Who may read and post a project's activity feed (self-review finding, 2026-07-28).

The project activities adapter shipped with `can_view=None`. The generic gate treats that as
"no opinion" and returns immediately, so ANY holder of `projects.projects.view` could read and
post on ANY project id -- including one belonging to another company, because `activity_events`
is not company-scoped and nothing in the path ever loaded the project.

The ticket adapter supplies `can_view` for exactly this reason. Two consequences without it:

* a Mocha user reads Sorento's internal notes by pasting a project id;
* posting against an id that the caller cannot see (or that does not exist) writes an orphan
  activity row, and -- because a human post resets the staleness clock -- silently clears
  another company's Unattended badge.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-actacc"


def _uid() -> str:
    return str(uuid.uuid4())


def _company(db, code: str, name: str) -> str:
    """A second company, so cross-company access is a real question and not a hypothetical."""
    company_id = _uid()
    db.execute(
        text(
            "insert into companies (id, name, code, is_active) "
            "values (:i, :n, :c, true)"
        ),
        {"i": company_id, "n": name, "c": code},
    )
    db.flush()
    return company_id


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


@pytest.fixture()
def two_companies():
    from app.models.base import company_scope
    from app.services.project_service import register_project

    with blank_session() as db:
        sorento = db.execute(text("select id from companies where code = 'SRT'")).scalar()
        project_seed_service.run(db, company_id=sorento)
        mocha = _company(db, f"Z{uuid.uuid4().hex[:3].upper()}", f"{MARKER} Mocha")

        ali = _user(db, f"{MARKER} Ali (Sorento)")
        siti = _user(db, f"{MARKER} Siti (Mocha)")

        with company_scope(db, frozenset({str(sorento)})):
            srt_project = register_project(
                db,
                company_id=str(sorento),
                actor_user_id=ali,
                developer_party_id=None,
                title=f"{MARKER} Sorento Residensi",
                owner_user_id=ali,
            )
            db.flush()

        yield {
            "db": db,
            "sorento": str(sorento),
            "mocha": str(mocha),
            "ali": ali,
            "siti": siti,
            "srt_project": srt_project,
        }


def test_the_adapter_declares_a_visibility_gate():
    """Structural, because the gate is opt-IN: an adapter that forgets `can_view` is wide open
    and nothing anywhere else notices."""
    import app.main  # noqa: F401  -- registers the adapters
    from app.services.activities_registry import get_adapter

    adapter = get_adapter("project")
    assert adapter.can_view is not None, "project activities have no visibility gate"


def test_a_user_from_another_company_cannot_read_a_projects_activities(two_companies):
    """The behaviour that matters: the check resolves the project through the SCOPED session,
    so a project outside the caller's company simply does not exist to them."""
    import app.main  # noqa: F401
    from app.models.base import company_scope
    from app.services.activities_registry import get_adapter

    ctx = two_companies
    db = ctx["db"]
    adapter = get_adapter("project")
    project_id = str(ctx["srt_project"].id)

    with company_scope(db, frozenset({ctx["sorento"]})):
        assert adapter.can_view(db, project_id, {"id": ctx["ali"]}) is True

    with company_scope(db, frozenset({ctx["mocha"]})):
        assert adapter.can_view(db, project_id, {"id": ctx["siti"]}) is False


def test_an_unknown_project_id_is_not_viewable(two_companies):
    """Otherwise a post against a typo'd id writes an orphan activity row that no page will
    ever show and no cleanup will ever find."""
    import app.main  # noqa: F401
    from app.models.base import company_scope
    from app.services.activities_registry import get_adapter

    ctx = two_companies
    adapter = get_adapter("project")
    with company_scope(ctx["db"], frozenset({ctx["sorento"]})):
        assert adapter.can_view(ctx["db"], _uid(), {"id": ctx["ali"]}) is False


def test_posting_on_an_invisible_project_does_not_touch_its_staleness_clock(two_companies):
    """`note_user_activity` resets `stale_level` to 0. Reached with a foreign project id it
    would clear another company's Unattended badge -- the one signal that project is being
    neglected."""
    from app.models.base import company_scope
    from app.services import project_activity_service as activity

    ctx = two_companies
    db = ctx["db"]
    project = ctx["srt_project"]
    project.stale_level = 3
    db.flush()

    with company_scope(db, frozenset({ctx["mocha"]})):
        activity.note_user_activity(db, project_id=str(project.id), actor_id=ctx["siti"])
        db.flush()

    db.expire_all()
    from app.models.projects import Project

    with company_scope(db, frozenset({ctx["sorento"]})):
        fresh = db.query(Project).filter(Project.id == str(project.id)).first()
        assert int(fresh.stale_level or 0) == 3, (
            "a foreign post cleared the ladder on a project it cannot even see"
        )


def test_a_malformed_project_id_is_a_no_and_leaves_the_session_usable(two_companies):
    """The generic gate catches whatever `can_view` raises and answers 404, so a junk id looked
    handled -- but comparing a non-uuid to a uuid column raises INSIDE Postgres, which ABORTS
    the transaction. The 404 is then correct and the session is poisoned: the next statement in
    that request fails for a reason that has nothing to do with what the caller asked for.
    """
    import app.main  # noqa: F401
    from app.models.base import company_scope
    from app.models.projects import Project
    from app.services.activities_registry import get_adapter

    ctx = two_companies
    db = ctx["db"]
    adapter = get_adapter("project")

    with company_scope(db, frozenset({ctx["sorento"]})):
        assert adapter.can_view(db, "not-a-uuid", {"id": ctx["ali"]}) is False
        assert adapter.can_view(db, "", {"id": ctx["ali"]}) is False
        # The session still works, which is the half the 404 was hiding.
        assert (
            db.query(Project).filter(Project.id == str(ctx["srt_project"].id)).first()
            is not None
        )
