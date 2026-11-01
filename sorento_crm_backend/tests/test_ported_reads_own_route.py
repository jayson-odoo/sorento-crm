"""AGENTIC-UNIFY PR 4, slice 1: the projects route narrows a `.view_own` panel user to their own rows (AC-2).

The panel's read is the shared key plus `X-Staff-User: <user id>` (`tests/test_staff_read_identity.py`). The
shared key's act-as user here is a superadmin, the case where a route that did NOT run as the staff member would
show every project. Real app, real route, real RBAC rows, real session; every row is seeded here.

This pins existing route behaviour (projects `view_own` narrowing) so the tool's `own_permission` rests on a
measured fact. It is expected to pass before the coder starts.
"""
from __future__ import annotations

import uuid

from app.models.projects import Project
from tests.test_staff_read_identity import SORENTO, env, mk_user  # noqa: F401  (env is a fixture)

PROJECTS = "/api/v1/project-sales/projects/"
VIEW = "projects.projects.view"
VIEW_OWN = "projects.projects.view_own"


def _project(db, owner: str, tag: str) -> str:
    code = f"ZZT-OWN-{tag}-{uuid.uuid4().hex[:6]}"
    db.add(
        Project(
            id=str(uuid.uuid4()),
            company_id=SORENTO,
            project_code=code,
            title=f"ZZT Project {code}",
            normalised_title=f"zzt project {code.lower()}",
            owner_user_id=owner,
        )
    )
    db.flush()
    return code


def _codes(resp) -> set[str]:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["data"] if isinstance(body, dict) else body
    return {r["project_code"] for r in rows}


def test_AC2_a_view_own_staff_member_gets_only_their_own_projects_through_the_real_route(env):
    db = env.db
    own_user = mk_user(db, "own", perms=[VIEW_OWN], companies=(SORENTO,), last_active=SORENTO)
    other_user = mk_user(db, "other", perms=[VIEW_OWN], companies=(SORENTO,), last_active=SORENTO)
    mine = _project(db, own_user, "MINE")
    theirs = _project(db, other_user, "THEIRS")
    db.flush()

    got = _codes(env.client.get(PROJECTS, headers=env.ident(own_user)))
    assert mine in got
    assert theirs not in got, "a view_own staff member read another user's project"


def test_AC2_control_a_view_holder_through_the_same_route_sees_both(env):
    db = env.db
    viewer = mk_user(db, "viewer", perms=[VIEW], companies=(SORENTO,), last_active=SORENTO)
    owner_a = mk_user(db, "a", perms=[VIEW_OWN], companies=(SORENTO,), last_active=SORENTO)
    owner_b = mk_user(db, "b", perms=[VIEW_OWN], companies=(SORENTO,), last_active=SORENTO)
    first = _project(db, owner_a, "A")
    second = _project(db, owner_b, "B")
    db.flush()

    got = _codes(env.client.get(PROJECTS, headers=env.ident(viewer)))
    assert {first, second} <= got
