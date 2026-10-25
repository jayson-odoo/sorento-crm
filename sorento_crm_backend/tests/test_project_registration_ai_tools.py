"""PROJECT-REG-PORTAL R4: the AI read tools see approved projects only.

The MCP server (X-API-Key) and the analytics connector both read `GET /project-sales/projects/`
as a machine caller. A portal registration waiting for approval (or rejected) is not a project to
answer about, so for those callers the list behaves as `approved_only=true` whatever they send.
A staff session keeps seeing pending and rejected rows (R6), the control here.
"""
from __future__ import annotations

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_registration_support import (
    LIST,
    approve,
    as_user,
    pending,
    project,
    reject,
    world,  # noqa: F401  (fixture)
)


def _ids(world) -> set:
    res = world.c.get(LIST, params={"limit": 100})
    assert res.status_code == 200, res.text
    return {row["id"] for row in res.json()["data"]}


@pytest.fixture
def seeded(world):
    pend = pending(world, title="AI PENDING TOWER")
    rej = pending(world, title="AI REJECTED TOWER")
    assert reject(world, rej).status_code == 200
    ok = pending(world, title="AI APPROVED TOWER")
    assert approve(world, ok).status_code == 200
    staff_project = project(world.db, world.company_id, "AI STAFF TOWER", code="PRJ-ZZT-AI1")
    return {"pending": pend, "rejected": rej, "approved": ok, "staff": staff_project.id}


@pytest.mark.parametrize("auth_method", ["api_key", "integration_api_key", "connector"])
def test_a_machine_caller_lists_approved_and_staff_projects_only(world, seeded, auth_method):
    from app.dependencies import get_current_user_or_api_key

    as_user(world, world.staff)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {
        "id": world.staff,
        "email": f"{world.staff}@zzt.test",
        "auth_method": auth_method,
    }
    ids = _ids(world)
    assert {seeded["approved"], seeded["staff"]} <= ids
    assert seeded["pending"] not in ids and seeded["rejected"] not in ids


def test_a_machine_caller_cannot_ask_for_pending_rows(world, seeded):
    from app.dependencies import get_current_user_or_api_key

    app.dependency_overrides[get_current_user_or_api_key] = lambda: {
        "id": world.staff,
        "email": f"{world.staff}@zzt.test",
        "auth_method": "integration_api_key",
    }
    res = world.c.get(LIST, params={"approval_state": "pending", "limit": 100})
    assert res.status_code == 200, res.text
    assert res.json()["data"] == []


def test_a_staff_session_still_sees_pending_and_rejected(world, seeded):
    as_user(world, world.staff)
    ids = _ids(world)
    assert {seeded["pending"], seeded["rejected"], seeded["approved"], seeded["staff"]} <= ids
