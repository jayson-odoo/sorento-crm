"""QUOTE-DRAWING-ESCALATE Phase 2 red tests: the three routes.

- ``POST /api/v1/project-sales/quotation-versions/{version_id}/lines/{line_id}/drawing-escalation``
  (``projects.projects.view`` or ``view_own``; the own-scope guard anchors on ``version_id``)
- ``POST /api/v1/sla-management/form-sla-tracking/{tracking_id}/drawing-respond``
- ``POST /api/v1/sla-management/form-sla-tracking/{tracking_id}/drawing-resolve``
  (``get_current_user`` plus the existing SLA actor rule)

Written BEFORE the routes exist, so every case is red until the coder adds them. Happy path,
auth denial, 404 and 409 for each, plus the own-scope pin. Postgres only, via ``blank_session``;
the chain (quotation, team, step, assignee) is seeded in ``test_product_drawing_request``.

The path ids are plain strings checked with ``validate_uuid_path`` in this router family, so a
malformed id answers 404 (the convention of the sibling line routes), not 422: the route takes
no body and no query, so there is nothing for FastAPI to refuse with a 422.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.models.base import company_scope
from app.models.notification import Notification
from app.models.sla import ConversationSLATracking

from ._own_scope_support import acting
from ._pg_fixture import blank_session
from .test_portal_p2_own_scope_projects import _gate_slugs
from .test_product_drawing_request import (
    FORM_SLA_NOTE_SOURCE,
    SOURCE,
    actor,
    channels,
    notes_for,
    quoted_product,
    seed_drawing_team,
    sent,  # noqa: F401  (a pytest fixture: nothing leaves the process)
    trackers_for,
)
from .test_product_drawing_request import _drawing
from .test_project_quotation_images import _setup, _user

BASE = "/api/v1/project-sales"
SLA_BASE = "/api/v1/sla-management/form-sla-tracking"
VIEW = "projects.projects.view"
VIEW_OWN = "projects.projects.view_own"
EDIT = "projects.projects.edit"
ESCALATE_PATH = "/quotation-versions/{version_id}/lines/{line_id}/drawing-escalation"


def _uid() -> str:
    return str(uuid.uuid4())


def _url(version_id, line_id) -> str:
    return f"{BASE}/quotation-versions/{version_id}/lines/{line_id}/drawing-escalation"


@pytest.fixture
def scene(sent):
    """A project owned by ``owner``, one saved quotation line on a product with no drawing, and
    the configured drawing team. ``stranger`` owns nothing and collaborates on nothing."""
    with blank_session() as db:
        env = _setup(db)
        with company_scope(db, frozenset({env["company_id"]})):
            team = seed_drawing_team(db)
            product, version, line = quoted_product(db, env)
            stranger = _user(db, "zzt Stranger")
            db.commit()
            yield {
                "db": db,
                "env": env,
                "team": team,
                "product": product,
                "version": version,
                "line": line,
                "owner": env["owner"],
                "stranger": stranger,
            }


def _assert_registered(path_suffix: str) -> None:
    """A 404 test passes on a MISSING route too, so each one first proves the route exists."""
    from app.main import app

    assert any(
        isinstance(r, APIRoute) and r.path.endswith(path_suffix) and "POST" in r.methods
        for r in app.routes
    ), f"POST ...{path_suffix} is not registered"


# ------------------------------------------------------------------ escalate: the happy path


def test_escalate_opens_a_task_and_answers_joined_false_with_the_state(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW}) as client:
        response = client.post(_url(s["version"].id, s["line"].id))

    assert response.status_code in (200, 201), response.text
    body = response.json()
    assert body["joined"] is False
    assert body["escalation"]["requester_count"] == 1
    assert body["escalation"]["tracking_id"]
    assert len(trackers_for(s["db"], s["product"].id)) == 1


def test_a_second_click_answers_joined_true_and_opens_nothing_new(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW}) as client:
        client.post(_url(s["version"].id, s["line"].id))
        again = client.post(_url(s["version"].id, s["line"].id))

    assert again.status_code in (200, 201), again.text
    assert again.json()["joined"] is True
    assert again.json()["escalation"]["requester_count"] == 1
    assert len(trackers_for(s["db"], s["product"].id)) == 1


def test_a_second_person_joins_and_is_counted_over_http(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW}) as client:
        client.post(_url(s["version"].id, s["line"].id))
    with acting(s["db"], s["stranger"], {VIEW}) as client:
        joined = client.post(_url(s["version"].id, s["line"].id))

    assert joined.status_code in (200, 201), joined.text
    assert joined.json()["joined"] is True
    assert joined.json()["escalation"]["requester_count"] == 2
    assert len(trackers_for(s["db"], s["product"].id)) == 1


def test_the_line_read_then_carries_the_escalation_state(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW}) as client:
        client.post(_url(s["version"].id, s["line"].id))
        lines = client.get(f"{BASE}/quotation-versions/{s['version'].id}/lines")

    assert lines.status_code == 200, lines.text
    cell = next(r for r in lines.json()["data"] if r["id"] == str(s["line"].id))["technical_drawing"]
    assert cell["escalation"] is not None
    assert cell["escalation"]["requester_count"] == 1


# ------------------------------------------------------------------ escalate: who may call it


def test_view_alone_opens_it(scene):
    s = scene
    with acting(s["db"], s["stranger"], {VIEW}) as client:
        assert client.post(_url(s["version"].id, s["line"].id)).status_code in (200, 201)


def test_view_own_opens_it_for_the_owner_of_the_project(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW_OWN}) as client:
        assert client.post(_url(s["version"].id, s["line"].id)).status_code in (200, 201)


def test_view_own_is_a_404_for_a_quotation_outside_their_own_projects(scene):
    s = scene
    _assert_registered("/drawing-escalation")
    with acting(s["db"], s["stranger"], {VIEW_OWN}) as client:
        response = client.post(_url(s["version"].id, s["line"].id))

    assert response.status_code == 404, response.text
    assert trackers_for(s["db"], s["product"].id) == []


@pytest.mark.parametrize("held", [set(), {EDIT}, {"projects.projects.delete"}])
def test_without_view_or_view_own_it_is_a_403_and_creates_nothing(scene, held):
    s = scene
    with acting(s["db"], s["owner"], held) as client:
        response = client.post(_url(s["version"].id, s["line"].id))

    assert response.status_code == 403, response.text
    assert trackers_for(s["db"], s["product"].id) == []


def test_it_needs_a_signed_in_user(scene):
    from fastapi.testclient import TestClient

    from app.main import app

    s = scene
    app.dependency_overrides.clear()
    response = TestClient(app).post(_url(s["version"].id, s["line"].id))

    assert response.status_code in (401, 403), response.text
    assert trackers_for(s["db"], s["product"].id) == []


# ------------------------------------------------------------------ escalate: 404 and 409


def test_a_line_that_is_not_on_this_version_is_a_404(scene):
    s = scene
    _assert_registered("/drawing-escalation")
    with acting(s["db"], s["owner"], {VIEW}) as client:
        assert client.post(_url(s["version"].id, _uid())).status_code == 404
        assert client.post(_url(_uid(), s["line"].id)).status_code == 404
    assert trackers_for(s["db"], s["product"].id) == []


def test_a_malformed_id_is_a_404_not_a_server_error(scene):
    s = scene
    _assert_registered("/drawing-escalation")
    with acting(s["db"], s["owner"], {VIEW}) as client:
        assert client.post(_url("not-a-uuid", s["line"].id)).status_code == 404
        assert client.post(_url(s["version"].id, "not-a-uuid")).status_code == 404


def test_a_product_with_a_drawing_is_a_409_with_its_code(scene):
    s = scene
    _drawing(s["db"], s["env"], s["product"], "d.pdf", mime="application/pdf")
    s["db"].commit()
    with acting(s["db"], s["owner"], {VIEW}) as client:
        response = client.post(_url(s["version"].id, s["line"].id))

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "product_has_drawing"
    assert trackers_for(s["db"], s["product"].id) == []


def test_no_configured_step_is_a_409_with_the_plain_message(scene):
    s = scene
    from app.models.sla import FormSLAConfig

    s["db"].query(FormSLAConfig).filter(FormSLAConfig.source_entity_type == SOURCE).delete()
    s["db"].commit()
    with acting(s["db"], s["owner"], {VIEW}) as client:
        response = client.post(_url(s["version"].id, s["line"].id))

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "drawing_requests_not_set_up"
    assert "No team is set up for drawing requests" in response.text
    assert trackers_for(s["db"], s["product"].id) == []


# ------------------------------------------------------------------ the own-scope pin


def _route():
    from app.main import app

    return [
        r
        for r in app.routes
        if isinstance(r, APIRoute)
        and r.path_format == BASE + ESCALATE_PATH
        and "POST" in r.methods
    ]


def test_the_route_exists_takes_view_or_view_own_and_the_guard_lets_a_limited_user_through():
    from app.api.v1.projects import _own_scope

    routes = _route()
    assert len(routes) == 1, "POST .../lines/{line_id}/drawing-escalation is not registered"
    assert {VIEW, VIEW_OWN} <= _gate_slugs(routes[0])
    assert _own_scope.classify("POST", routes[0].path_format) is not None, (
        "the own-scope guard refuses it: line_id must be a trusted nested name under the "
        "quotation-versions anchor"
    )


def test_the_route_is_pinned_in_the_allowed_routes_file():
    pinned = (Path(__file__).parent / "portal_p2_allowed_routes.txt").read_text().split("\n")
    assert "POST /quotation-versions/{version_id}/lines/{line_id}/drawing-escalation" in pinned


# ------------------------------------------------------------------ respond and resolve


def _open_task(s):
    """Escalate once as the owner and return the tracker."""
    with acting(s["db"], s["owner"], {VIEW}) as client:
        client.post(_url(s["version"].id, s["line"].id))
    (tracker,) = trackers_for(s["db"], s["product"].id)
    return tracker


def test_the_assignee_responds_and_the_task_reads_responded(scene):
    s = scene
    tracker = _open_task(s)
    with acting(s["db"], s["team"]["assignee"], set()) as client:
        response = client.post(f"{SLA_BASE}/{tracker.id}/drawing-respond")

    assert response.status_code == 200, response.text
    s["db"].refresh(tracker)
    assert tracker.is_responded is True and tracker.is_resolved is False


def test_the_assignee_resolves_and_every_requester_is_told_once(scene):
    s = scene
    tracker = _open_task(s)
    with acting(s["db"], s["stranger"], {VIEW}) as client:
        client.post(_url(s["version"].id, s["line"].id))
    with acting(s["db"], s["team"]["assignee"], set()) as client:
        response = client.post(f"{SLA_BASE}/{tracker.id}/drawing-resolve")

    assert response.status_code == 200, response.text
    s["db"].refresh(tracker)
    assert tracker.is_resolved is True
    title = f"Drawing request for {s['product'].product_code} resolved"
    for requester in (s["owner"], s["stranger"]):
        told = [n for n in notes_for(s["db"], requester) if n.title == title]
        assert len(told) == 1, requester
        assert "in_app" in channels(s["db"], told[0])


def test_someone_who_is_not_the_assignee_gets_404_and_the_task_stays_open(scene):
    s = scene
    tracker = _open_task(s)
    for action in ("drawing-respond", "drawing-resolve"):
        with acting(s["db"], s["stranger"], {VIEW}) as client:
            response = client.post(f"{SLA_BASE}/{tracker.id}/{action}")
        assert response.status_code in (400, 404), (action, response.text)
    s["db"].refresh(tracker)
    assert tracker.is_responded is False and tracker.is_resolved is False


@pytest.mark.parametrize("action", ["drawing-respond", "drawing-resolve"])
def test_an_unknown_tracker_is_a_404(scene, action):
    s = scene
    _assert_registered(f"/{action}")
    with acting(s["db"], s["team"]["assignee"], set()) as client:
        assert client.post(f"{SLA_BASE}/{_uid()}/{action}").status_code == 404


@pytest.mark.parametrize("action", ["drawing-respond", "drawing-resolve"])
def test_a_task_of_another_type_is_a_409(scene, action):
    from datetime import datetime, timedelta

    s = scene
    other = ConversationSLATracking(
        id=_uid(),
        policy_id=s["team"]["policy_id"],
        current_tier=1,
        initiated_at=datetime.utcnow(),
        current_tier_started_at=datetime.utcnow(),
        due_at=datetime.utcnow() + timedelta(hours=4),
        due_at_resolution=datetime.utcnow() + timedelta(hours=24),
        is_resolved=False,
        source_entity_type="complaint",
        source_entity_id=_uid(),
        agent_id=s["team"]["agent_id"],
        assigned_to_id=s["team"]["assignee"],
    )
    s["db"].add(other)
    s["db"].commit()
    with acting(s["db"], s["team"]["assignee"], set()) as client:
        response = client.post(f"{SLA_BASE}/{other.id}/{action}")

    assert response.status_code == 409, response.text
    s["db"].refresh(other)
    assert other.is_resolved is False and other.is_responded is False


@pytest.mark.parametrize("action", ["drawing-respond", "drawing-resolve"])
def test_respond_and_resolve_need_a_signed_in_user(scene, action):
    from fastapi.testclient import TestClient

    from app.main import app

    s = scene
    tracker = _open_task(s)
    app.dependency_overrides.clear()
    response = TestClient(app).post(f"{SLA_BASE}/{tracker.id}/{action}")

    assert response.status_code in (401, 403), response.text
    s["db"].refresh(tracker)
    assert tracker.is_responded is False and tracker.is_resolved is False


def test_the_hand_off_notice_rows_exist_for_the_task_the_route_opened(scene):
    """Rule 10 end to end over HTTP: the assignee was told when the click opened the task."""
    s = scene
    tracker = _open_task(s)
    notes = [
        n
        for n in notes_for(s["db"], s["team"]["assignee"])
        if n.source_entity_type == FORM_SLA_NOTE_SOURCE and str(n.source_entity_id) == str(tracker.id)
    ]
    assert len(notes) == 1
    assert isinstance(notes[0], Notification)
    assert "in_app" in channels(s["db"], notes[0])
