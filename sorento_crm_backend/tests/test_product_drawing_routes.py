"""QUOTE-DRAWING-ESCALATE rework red tests: the three routes, for both kinds.

- ``POST /api/v1/project-sales/quotation-versions/{version_id}/lines/{line_id}/media-escalation``
  body ``{"kind": "drawing" | "photo"}`` (``projects.projects.view`` or ``view_own``; the
  own-scope guard anchors on ``version_id``). Replaces ``media-escalation``.
- ``POST /api/v1/sla-management/form-sla-tracking/{tracking_id}/media-respond``
- ``POST /api/v1/sla-management/form-sla-tracking/{tracking_id}/media-resolve``
  (``get_current_user`` plus the existing SLA actor rule; resolve also needs
  ``sla_management.conversation_sla_tracking.resolve``). Both kinds.

Written BEFORE the routes exist, so every case is red until the coder adds them. Happy path,
auth denial, 404 and 409 for each, plus the own-scope pin. Postgres only, via ``blank_session``;
the chain (quotation, team, step, assignee) is seeded in ``test_product_drawing_request``.

The path ids are plain strings checked with ``validate_uuid_path`` in this router family, so a
malformed id answers 404 (the convention of the sibling line routes). The body is validated: a
missing or unknown ``kind`` is a 422.
"""
from __future__ import annotations

import re
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
from .test_product_drawing_request import _drawing, _photo
from .test_project_quotation_images import _setup, _user

BASE = "/api/v1/project-sales"
SLA_BASE = "/api/v1/sla-management/form-sla-tracking"
VIEW = "projects.projects.view"
VIEW_OWN = "projects.projects.view_own"
EDIT = "projects.projects.edit"
RESOLVE = "sla_management.conversation_sla_tracking.resolve"
ESCALATE_PATH = "/quotation-versions/{version_id}/lines/{line_id}/media-escalation"


def _uid() -> str:
    return str(uuid.uuid4())


def _url(version_id, line_id) -> str:
    return f"{BASE}/quotation-versions/{version_id}/lines/{line_id}/media-escalation"


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
        response = client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})

    assert response.status_code in (200, 201), response.text
    body = response.json()
    assert body["joined"] is False
    assert body["escalation"]["requester_count"] == 1
    assert body["escalation"]["tracking_id"]
    assert len(trackers_for(s["db"], s["product"].id)) == 1


def test_a_second_click_answers_joined_true_and_opens_nothing_new(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW}) as client:
        client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})
        again = client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})

    assert again.status_code in (200, 201), again.text
    assert again.json()["joined"] is True
    assert again.json()["escalation"]["requester_count"] == 1
    assert len(trackers_for(s["db"], s["product"].id)) == 1


def test_a_second_person_gets_their_own_ticket_over_http(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW}) as client:
        client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})
    with acting(s["db"], s["stranger"], {VIEW}) as client:
        joined = client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})

    assert joined.status_code in (200, 201), joined.text
    assert joined.json()["joined"] is False
    assert joined.json()["escalation"]["requester_count"] == 1
    assert len(trackers_for(s["db"], s["product"].id)) == 2


def test_the_line_read_then_carries_the_escalation_state(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW}) as client:
        client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})
        lines = client.get(f"{BASE}/quotation-versions/{s['version'].id}/lines")

    assert lines.status_code == 200, lines.text
    cell = next(r for r in lines.json()["data"] if r["id"] == str(s["line"].id))["technical_drawing"]
    assert cell["escalation"] is not None
    assert cell["escalation"]["requester_count"] == 1


# ------------------------------------------------------------------ escalate: who may call it


def test_view_alone_opens_it(scene):
    s = scene
    with acting(s["db"], s["stranger"], {VIEW}) as client:
        assert client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"}).status_code in (200, 201)


def test_view_own_opens_it_for_the_owner_of_the_project(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW_OWN}) as client:
        assert client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"}).status_code in (200, 201)


def test_view_own_is_a_404_for_a_quotation_outside_their_own_projects(scene):
    s = scene
    _assert_registered("/media-escalation")
    with acting(s["db"], s["stranger"], {VIEW_OWN}) as client:
        response = client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})

    assert response.status_code == 404, response.text
    assert trackers_for(s["db"], s["product"].id) == []


@pytest.mark.parametrize("held", [set(), {EDIT}, {"projects.projects.delete"}])
def test_without_view_or_view_own_it_is_a_403_and_creates_nothing(scene, held):
    s = scene
    with acting(s["db"], s["owner"], held) as client:
        response = client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})

    assert response.status_code == 403, response.text
    assert trackers_for(s["db"], s["product"].id) == []


def test_it_needs_a_signed_in_user(scene):
    from fastapi.testclient import TestClient

    from app.main import app

    s = scene
    app.dependency_overrides.clear()
    response = TestClient(app).post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})

    assert response.status_code in (401, 403), response.text
    assert trackers_for(s["db"], s["product"].id) == []


# ------------------------------------------------------------------ escalate: 404 and 409


def test_a_line_that_is_not_on_this_version_is_a_404(scene):
    s = scene
    _assert_registered("/media-escalation")
    with acting(s["db"], s["owner"], {VIEW}) as client:
        assert client.post(_url(s["version"].id, _uid()), json={"kind": "drawing"}).status_code == 404
        assert client.post(_url(_uid(), s["line"].id), json={"kind": "drawing"}).status_code == 404
    assert trackers_for(s["db"], s["product"].id) == []


def test_a_malformed_id_is_a_404_not_a_server_error(scene):
    s = scene
    _assert_registered("/media-escalation")
    with acting(s["db"], s["owner"], {VIEW}) as client:
        assert client.post(_url("not-a-uuid", s["line"].id), json={"kind": "drawing"}).status_code == 404
        assert client.post(_url(s["version"].id, "not-a-uuid"), json={"kind": "drawing"}).status_code == 404


def test_a_product_with_a_drawing_is_a_409_with_its_code(scene):
    s = scene
    _drawing(s["db"], s["env"], s["product"], "d.pdf", mime="application/pdf")
    s["db"].commit()
    with acting(s["db"], s["owner"], {VIEW}) as client:
        response = client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "product_has_drawing"
    assert trackers_for(s["db"], s["product"].id) == []


def test_a_missing_marketing_team_is_a_409_with_the_plain_message(scene):
    s = scene
    from app.models.chatbot_policy import ChatbotDomain

    s["db"].query(ChatbotDomain).filter(ChatbotDomain.name == "product_attachment").delete()
    s["db"].commit()
    with acting(s["db"], s["owner"], {VIEW}) as client:
        response = client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "marketing_team_not_set_up"
    assert "The marketing product team is not set up for this company" in response.text
    assert s["team"]["team_set_code"] not in response.text
    assert s["team"]["agent_id"] not in response.text
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
    assert len(routes) == 1, "POST .../lines/{line_id}/media-escalation is not registered"
    assert {VIEW, VIEW_OWN} <= _gate_slugs(routes[0])
    assert _own_scope.classify("POST", routes[0].path_format) is not None, (
        "the own-scope guard refuses it: line_id must be a trusted nested name under the "
        "quotation-versions anchor"
    )


def test_the_route_is_pinned_in_the_allowed_routes_file():
    pinned = (Path(__file__).parent / "portal_p2_allowed_routes.txt").read_text().split("\n")
    assert "POST /quotation-versions/{version_id}/lines/{line_id}/media-escalation" in pinned


# ------------------------------------------------------------------ respond and resolve


def _open_task(s):
    """Escalate once as the owner and return the tracker."""
    with acting(s["db"], s["owner"], {VIEW}) as client:
        client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})
    (tracker,) = trackers_for(s["db"], s["product"].id)
    return tracker


def test_the_assignee_responds_and_the_task_reads_responded(scene):
    s = scene
    tracker = _open_task(s)
    with acting(s["db"], s["team"]["assignee"], set()) as client:
        response = client.post(f"{SLA_BASE}/{tracker.id}/media-respond")

    assert response.status_code == 200, response.text
    s["db"].refresh(tracker)
    assert tracker.is_responded is True and tracker.is_resolved is False


def test_the_assignee_resolves_each_ticket_and_each_requester_is_told_once(scene):
    s = scene
    tracker = _open_task(s)
    with acting(s["db"], s["stranger"], {VIEW}) as client:
        client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})
    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        responses = [client.post(f"{SLA_BASE}/{t.id}/media-resolve") for t in trackers_for(s["db"], s["product"].id)]

    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    s["db"].refresh(tracker)
    assert tracker.is_resolved is True
    title = f"Product drawing request for {s['product'].product_code} resolved"
    for requester in (s["owner"], s["stranger"]):
        told = [n for n in notes_for(s["db"], requester) if n.title == title]
        assert len(told) == 1, requester
        assert "in_app" in channels(s["db"], told[0])


def test_someone_who_is_not_the_assignee_gets_404_and_the_task_stays_open(scene):
    s = scene
    tracker = _open_task(s)
    for action in ("media-respond", "media-resolve"):
        with acting(s["db"], s["stranger"], {VIEW, RESOLVE}) as client:
            response = client.post(f"{SLA_BASE}/{tracker.id}/{action}")
        assert response.status_code in (400, 404), (action, response.text)
    s["db"].refresh(tracker)
    assert tracker.is_responded is False and tracker.is_resolved is False


@pytest.mark.parametrize("action", ["media-respond", "media-resolve"])
def test_an_unknown_tracker_is_a_404(scene, action):
    s = scene
    _assert_registered(f"/{action}")
    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        assert client.post(f"{SLA_BASE}/{_uid()}/{action}").status_code == 404


@pytest.mark.parametrize("action", ["media-respond", "media-resolve"])
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
    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        response = client.post(f"{SLA_BASE}/{other.id}/{action}")

    assert response.status_code == 409, response.text
    s["db"].refresh(other)
    assert other.is_resolved is False and other.is_responded is False


def test_resolve_needs_the_sla_resolve_permission_even_for_the_assignee(scene):
    """Like the conversation resolve route: the actor rule is not enough, the slug is required."""
    s = scene
    tracker = _open_task(s)
    with acting(s["db"], s["team"]["assignee"], set()) as client:
        response = client.post(f"{SLA_BASE}/{tracker.id}/media-resolve")

    assert response.status_code == 403, response.text
    s["db"].refresh(tracker)
    assert tracker.is_resolved is False


@pytest.mark.parametrize("action", ["media-respond", "media-resolve"])
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


# =============================================================================================
# REWORK: the same routes for the photo kind, and the body check.
# =============================================================================================

KINDS = ["drawing", "photo"]
LABELS = {"drawing": "Product drawing", "photo": "Product photo"}


def _post(client, s, kind):
    return client.post(_url(s["version"].id, s["line"].id), json={"kind": kind})


@pytest.mark.parametrize("kind", KINDS)
def test_escalate_opens_a_task_of_the_kind_and_joins_on_a_second_click(scene, kind):
    s = scene
    with acting(s["db"], s["owner"], {VIEW}) as client:
        first = _post(client, s, kind)
        again = _post(client, s, kind)

    assert first.status_code in (200, 201), first.text
    assert first.json()["joined"] is False
    assert first.json()["escalation"]["requester_count"] == 1
    assert again.status_code in (200, 201), again.text
    assert again.json()["joined"] is True
    assert len(trackers_for(s["db"], s["product"].id, kind)) == 1
    other = "photo" if kind == "drawing" else "drawing"
    assert trackers_for(s["db"], s["product"].id, other) == []


def test_a_drawing_and_a_photo_click_open_two_tasks_over_http(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW}) as client:
        drawing = _post(client, s, "drawing")
        photo = _post(client, s, "photo")

    assert drawing.json()["joined"] is False and photo.json()["joined"] is False
    assert drawing.json()["escalation"]["tracking_id"] != photo.json()["escalation"]["tracking_id"]


def test_the_line_read_carries_each_kinds_escalation_on_its_own_cell(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW}) as client:
        _post(client, s, "photo")
        lines = client.get(f"{BASE}/quotation-versions/{s['version'].id}/lines")

    assert lines.status_code == 200, lines.text
    row = next(r for r in lines.json()["data"] if r["id"] == str(s["line"].id))
    assert row["product_image"]["state"] == "no_photos"
    assert row["product_image"]["escalation"]["requester_count"] == 1
    assert row["technical_drawing"]["escalation"] is None


@pytest.mark.parametrize("body", [None, {}, {"kind": "datasheet"}, {"kind": None}, {"kind": 3}])
def test_a_missing_or_unknown_kind_is_a_422_and_creates_nothing(scene, body):
    s = scene
    _assert_registered("/media-escalation")
    with acting(s["db"], s["owner"], {VIEW}) as client:
        response = client.post(_url(s["version"].id, s["line"].id), json=body)

    assert response.status_code == 422, response.text
    assert trackers_for(s["db"], s["product"].id, "drawing") == []
    assert trackers_for(s["db"], s["product"].id, "photo") == []


def test_the_retired_drawing_escalation_route_is_gone(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW}) as client:
        response = client.post(
            f"{BASE}/quotation-versions/{s['version'].id}/lines/{s['line'].id}/drawing-escalation",
            json={"kind": "drawing"},
        )
    assert response.status_code in (404, 405), response.text


@pytest.mark.parametrize("old", ["drawing-respond", "drawing-resolve"])
def test_the_retired_drawing_respond_and_resolve_routes_are_gone(scene, old):
    s = scene
    tracker = _open_task(s)
    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        response = client.post(f"{SLA_BASE}/{tracker.id}/{old}")
    assert response.status_code in (404, 405), response.text
    s["db"].refresh(tracker)
    assert tracker.is_responded is False and tracker.is_resolved is False


def test_a_product_with_a_photo_is_a_409_product_has_photo(scene):
    s = scene
    _photo(s["db"], s["env"], s["product"], "p1.jpg")
    s["db"].commit()
    with acting(s["db"], s["owner"], {VIEW}) as client:
        response = _post(client, s, "photo")

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "product_has_photo"
    assert trackers_for(s["db"], s["product"].id, "photo") == []


def test_a_photo_does_not_stop_a_drawing_escalation_over_http(scene):
    s = scene
    _photo(s["db"], s["env"], s["product"], "p1.jpg")
    s["db"].commit()
    with acting(s["db"], s["owner"], {VIEW}) as client:
        response = _post(client, s, "drawing")

    assert response.status_code in (200, 201), response.text


@pytest.mark.parametrize("kind", KINDS)
def test_view_own_is_a_404_for_a_quotation_outside_their_own_projects_for_both_kinds(scene, kind):
    s = scene
    _assert_registered("/media-escalation")
    with acting(s["db"], s["stranger"], {VIEW_OWN}) as client:
        response = _post(client, s, kind)

    assert response.status_code == 404, response.text
    assert trackers_for(s["db"], s["product"].id, kind) == []


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("held", [set(), {EDIT}])
def test_without_view_or_view_own_both_kinds_are_a_403(scene, held, kind):
    s = scene
    with acting(s["db"], s["owner"], held) as client:
        response = _post(client, s, kind)

    assert response.status_code == 403, response.text
    assert trackers_for(s["db"], s["product"].id, kind) == []


@pytest.mark.parametrize("kind", KINDS)
def test_a_missing_marketing_team_is_a_409_for_both_kinds(scene, kind):
    from app.models.access import AgentTeam

    s = scene
    s["db"].query(AgentTeam).filter(AgentTeam.agent_id == s["team"]["agent_id"]).delete()
    s["db"].commit()
    with acting(s["db"], s["owner"], {VIEW}) as client:
        response = _post(client, s, kind)

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "marketing_team_not_set_up"
    assert trackers_for(s["db"], s["product"].id, kind) == []


def _open_media_task(s, kind):
    with acting(s["db"], s["owner"], {VIEW}) as client:
        _post(client, s, kind)
    (tracker,) = trackers_for(s["db"], s["product"].id, kind)
    return tracker


@pytest.mark.parametrize("kind", KINDS)
def test_the_assignee_responds_and_resolves_either_kind_and_requesters_are_told(scene, kind):
    s = scene
    tracker = _open_media_task(s, kind)
    with acting(s["db"], s["team"]["assignee"], set()) as client:
        responded = client.post(f"{SLA_BASE}/{tracker.id}/media-respond")
    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        resolved = client.post(f"{SLA_BASE}/{tracker.id}/media-resolve")

    assert responded.status_code == 200, responded.text
    assert resolved.status_code == 200, resolved.text
    s["db"].refresh(tracker)
    assert tracker.is_responded is True and tracker.is_resolved is True
    title = f"{LABELS[kind]} request for {s['product'].product_code} resolved"
    told = [n for n in notes_for(s["db"], s["owner"]) if n.title == title]
    assert len(told) == 1 and "in_app" in channels(s["db"], told[0])


@pytest.mark.parametrize("kind", KINDS)
def test_media_resolve_needs_the_sla_resolve_permission_even_for_the_assignee(scene, kind):
    s = scene
    tracker = _open_media_task(s, kind)
    with acting(s["db"], s["team"]["assignee"], set()) as client:
        response = client.post(f"{SLA_BASE}/{tracker.id}/media-resolve")

    assert response.status_code == 403, response.text
    s["db"].refresh(tracker)
    assert tracker.is_resolved is False


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("action", ["media-respond", "media-resolve"])
def test_a_stranger_cannot_act_on_either_kind(scene, kind, action):
    s = scene
    tracker = _open_media_task(s, kind)
    with acting(s["db"], s["stranger"], {VIEW, RESOLVE}) as client:
        response = client.post(f"{SLA_BASE}/{tracker.id}/{action}")

    assert response.status_code in (400, 404), response.text
    s["db"].refresh(tracker)
    assert tracker.is_responded is False and tracker.is_resolved is False


# =============================================================================================
# OWNER HAND TEST ROUND 2: the side panel reads one task (GET .../media-request).
# =============================================================================================

DETAIL = "media-request"


def _escalate_as(s, user_id, version, line, kind="drawing"):
    with acting(s["db"], user_id, {VIEW}) as client:
        r = client.post(_url(version.id, line.id), json={"kind": kind})
    assert r.status_code in (200, 201), r.text


def _second_quotation(s):
    """A second quotation (and its line) of the same product, in the same project."""
    from app.services import project_quotation_service as quotes

    from .test_project_quotation_images import _priced_line
    from .test_quotation_lines_grid import _scope

    _document, scope = _scope(s["db"], s["env"])
    line = _priced_line(s["db"], s["env"], scope, s["product"])
    version = quotes.current_version(s["db"], scope.id)
    s["db"].commit()
    return version, line, scope


def test_the_detail_describes_a_ticket_raised_from_two_quotations(scene):
    s = scene
    version_b, line_b, scope_b = _second_quotation(s)
    _escalate_as(s, s["owner"], s["version"], s["line"])
    _escalate_as(s, s["owner"], version_b, line_b)
    (tracker,) = trackers_for(s["db"], s["product"].id)

    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        response = client.get(f"{SLA_BASE}/{tracker.id}/{DETAIL}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tracking_id"] == str(tracker.id)
    assert body["kind"] == "drawing"
    assert body["product_id"] == str(s["product"].id)
    assert body["product_code"] == s["product"].product_code
    assert body["product_name"] == s["product"].product_name
    assert body["product_href"] == f"/master-data-management/products/{s['product'].id}"
    assert body["resources_href"] == "/resource-management/attachment-directories"
    assert body["is_assignee"] is True and body["can_resolve"] is True
    assert body["is_responded"] is False and body["is_resolved"] is False
    assert body["current_tier"] == 1 and body["assignee_name"]
    assert body["assignee_team_id"] in {str(t) for t in s["team"]["team_ids"].values()}
    assert body["due_at"] and body["due_at_resolution"] and body["due_at"].endswith(("Z", "+00:00"))
    assert {"responded_at", "resolved_at", "escalated_at", "extension_count"} <= set(body)
    hrefs = {q["href"] for q in body["quotations"]}
    assert len(body["quotations"]) == 2 and len(hrefs) == 2
    for q in body["quotations"]:
        assert q["href"] == f"/project-sales/{q['project_id']}/quotations/{q['quotation_id']}"


def test_a_quotation_label_is_a_reference_never_a_uuid(scene):
    s = scene
    _escalate_as(s, s["owner"], s["version"], s["line"])
    (tracker,) = trackers_for(s["db"], s["product"].id)

    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        body = client.get(f"{SLA_BASE}/{tracker.id}/{DETAIL}").json()

    (quotation,) = body["quotations"]
    assert quotation["label"]
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", quotation["label"])


def test_the_detail_is_a_404_for_someone_who_cannot_see_the_task(scene):
    s = scene
    from app.main import app

    assert any(
        isinstance(r, APIRoute) and r.path.endswith(f"/{DETAIL}") and "GET" in r.methods for r in app.routes
    ), "GET ...media-request is not registered"
    _escalate_as(s, s["owner"], s["version"], s["line"])
    (tracker,) = trackers_for(s["db"], s["product"].id)

    with acting(s["db"], s["stranger"], {VIEW}) as client:
        response = client.get(f"{SLA_BASE}/{tracker.id}/{DETAIL}")

    assert response.status_code == 404, response.text


def test_the_detail_admits_a_teammate_of_the_assignee_without_any_slug(scene):
    # REL10-FIX-SECURITY: the panel's read gate is the task's visibility (My Team), the same
    # `can_user_act_on_tracking` rule as the drawer reads (/takeover-state, /media). A teammate
    # holding no slug at all reads it; nothing about the SLA module slugs widens or narrows it.
    from app.models.access import TeamMember

    s = scene
    _escalate_as(s, s["owner"], s["version"], s["line"])
    (tracker,) = trackers_for(s["db"], s["product"].id)
    mate = _user(s["db"], "zzt Teammate")
    s["db"].add(TeamMember(id=_uid(), team_id=s["team"]["team_ids"][1], user_id=mate))
    s["db"].commit()

    with acting(s["db"], mate, set()) as client:
        response = client.get(f"{SLA_BASE}/{tracker.id}/{DETAIL}")

    assert response.status_code == 200, response.text
    assert response.json()["is_assignee"] is False and response.json()["can_resolve"] is False


@pytest.mark.parametrize(
    "perms",
    [
        set(),
        {RESOLVE, "sla_management.conversation_sla_tracking.view", "sla_management.escalation_logs.view"},
        {"master_data.products.view", VIEW},
    ],
    ids=["no-slug", "sla-module-slugs", "product-and-project-slugs"],
)
def test_the_detail_is_a_404_for_the_requester_and_for_any_slug_off_the_task(scene, perms):
    # The requester is told on resolve (in-app, linking to the quotation); the panel itself is
    # the assignee's and their team chain's. Holding the SLA or product slugs does not open
    # someone else's task: 404, never 403, so the id is not confirmed.
    s = scene
    _escalate_as(s, s["owner"], s["version"], s["line"])
    (tracker,) = trackers_for(s["db"], s["product"].id)

    for viewer in (s["owner"], s["stranger"]):
        with acting(s["db"], viewer, perms) as client:
            response = client.get(f"{SLA_BASE}/{tracker.id}/{DETAIL}")
        assert response.status_code == 404, response.text


def test_the_detail_is_session_only():
    # `get_current_user`, never `get_current_user_or_api_key`: an integration key opens nothing.
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app

    (route,) = [
        r for r in app.routes
        if isinstance(r, APIRoute) and r.path == f"{SLA_BASE}/{{tracking_id}}/{DETAIL}" and "GET" in r.methods
    ]
    calls = set()

    def walk(dependant):
        for dep in dependant.dependencies:
            calls.add(dep.call)
            walk(dep)

    walk(route.dependant)
    assert get_current_user in calls
    assert get_current_user_or_api_key not in calls


def test_the_detail_of_a_non_media_task_is_a_409(scene):
    from datetime import datetime, timedelta

    s = scene
    other = ConversationSLATracking(
        id=_uid(), policy_id=s["team"]["policy_id"], current_tier=1,
        initiated_at=datetime.utcnow(), current_tier_started_at=datetime.utcnow(),
        due_at=datetime.utcnow() + timedelta(hours=4), due_at_resolution=datetime.utcnow() + timedelta(hours=24),
        is_resolved=False, source_entity_type="complaint", source_entity_id=_uid(),
        agent_id=s["team"]["agent_id"], assigned_to_id=s["team"]["assignee"],
    )
    s["db"].add(other)
    s["db"].commit()

    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        response = client.get(f"{SLA_BASE}/{other.id}/{DETAIL}")

    assert response.status_code == 409, response.text


def test_can_resolve_needs_the_assignee_and_the_resolve_permission(scene):
    s = scene
    _escalate_as(s, s["owner"], s["version"], s["line"])
    (tracker,) = trackers_for(s["db"], s["product"].id)

    with acting(s["db"], s["team"]["assignee"], set()) as client:
        no_permission = client.get(f"{SLA_BASE}/{tracker.id}/{DETAIL}").json()
    # An admin-like viewer who can see the task but is not its assignee.
    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        with_permission = client.get(f"{SLA_BASE}/{tracker.id}/{DETAIL}").json()

    assert no_permission["is_assignee"] is True and no_permission["can_resolve"] is False
    assert with_permission["can_resolve"] is True


def test_can_resolve_is_false_for_a_viewer_who_is_not_the_assignee(scene):
    from app.services.sla_service import ConversationSLATrackingService

    s = scene
    _escalate_as(s, s["owner"], s["version"], s["line"])
    (tracker,) = trackers_for(s["db"], s["product"].id)
    s["db"].query(ConversationSLATracking).filter(ConversationSLATracking.id == tracker.id).update(
        {"assigned_to_id": s["stranger"]}
    )
    s["db"].commit()
    original = ConversationSLATrackingService.can_user_act_on_tracking
    ConversationSLATrackingService.can_user_act_on_tracking = lambda self, uid_, t: True
    try:
        with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
            body = client.get(f"{SLA_BASE}/{tracker.id}/{DETAIL}").json()
    finally:
        ConversationSLATrackingService.can_user_act_on_tracking = original

    assert body["is_assignee"] is False
    assert body["can_resolve"] is False


# --------------------------------------------- the H3 notice through the Resources link route


def test_linking_a_drawing_through_the_product_attachments_route_notifies_the_assignee(scene):
    """Resources > Files links the uploaded file with POST /master-data/product-attachments."""
    from app.models.product import ProductAttachment  # noqa: F401
    from .test_product_drawing_request import DRAWINGS, _file

    s = scene
    _escalate_as(s, s["owner"], s["version"], s["line"])
    (tracker,) = trackers_for(s["db"], s["product"].id)
    attachment = _file(s["db"], s["env"]["company_id"], DRAWINGS, "from-resources.png")
    s["db"].commit()

    with acting(s["db"], s["owner"], {"master_data.product_attachments.edit"}) as client:
        paths = [r.path for r in client.app.routes if getattr(r, "path", "").endswith("/product-attachments/")]
        assert paths, "the product attachments create route is not mounted"
        response = client.post(
            paths[0],
            json={"product_id": str(s["product"].id), "attachment_id": str(attachment.id)},
        )

    assert response.status_code in (200, 201), response.text
    s["db"].refresh(tracker)
    assert tracker.is_resolved is False
    added = [
        n for n in notes_for(s["db"], s["team"]["assignee"])
        if "Drawing added" in f"{n.title} {n.body or ''}"
    ]
    assert len(added) == 1


# =============================================================================================
# QUOTE-MEDIA-CHAT: the PIC works a media ticket through the chat ticket endpoints, resolve does a
# chat resolve, and the quotation tile is per viewer.
# =============================================================================================

TICKET_BASE = "/api/v1/sla-management/conversation-sla-tracking"


class _FakeRespond:
    """No network. One class stands in for ``RespondClient`` (constructor and ``for_identifier``);
    every text send is recorded on ``sent_texts``."""

    api_key = "x"
    sent_texts: list = []

    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def for_identifier(cls, db, identifier):
        return cls()

    def list_messages(self, identifier, limit=50, cursor=None):
        return {"items": []}

    def send_message(self, identifier, text):
        type(self).sent_texts.append((identifier, text))
        return {"id": "m-text"}


@pytest.fixture
def respond_doubles(monkeypatch):
    """The Respond HTTP client and the window are patched, as the chat ticket route tests do."""
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    _FakeRespond.sent_texts = []
    monkeypatch.setattr("app.services.integration_service.RespondClient", _FakeRespond)
    monkeypatch.setattr(
        "app.services.respond_messaging_service.get_window_state",
        lambda *a, **k: {"open": True, "last_incoming_at": None, "checked_at": "", "source": "x"},
    )
    return _FakeRespond


@pytest.fixture
def chat_scene(respond_doubles):
    """Like ``scene``, but the owner is linked to a WhatsApp contact and the Respond sender is
    the fake above (``scene`` itself fails any test that reaches a real send)."""
    from app.models.access import RespondContact
    from app.models.user import User

    with blank_session() as db:
        env = _setup(db)
        with company_scope(db, frozenset({env["company_id"]})):
            team = seed_drawing_team(db)
            product, version, line = quoted_product(db, env)
            contact = RespondContact(
                id=_uid(),
                phone_number=f"+6011{uuid.uuid4().int % 10**8:08d}",
                name="ZZT Sales WhatsApp",
                respond_io_id=f"zzt-rio-{uuid.uuid4().hex[:8]}",
                session_vars={},
            )
            db.add(contact)
            db.flush()
            db.query(User).filter(User.id == env["owner"]).update({"respond_contact_id": contact.id})
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
                "contact": contact,
            }


def _no_ack(monkeypatch):
    monkeypatch.setattr(
        "app.services.product_drawing_request_service.enqueue_request_ack",
        lambda contact_id, text, tracking_id=None: None,
        raising=False,
    )


# ------------------------------------------------------------------ B4: the chat ticket endpoints


def test_b4_ticket_detail_conversation_and_send_accept_a_media_ticket_with_a_contact(chat_scene, monkeypatch):
    _no_ack(monkeypatch)
    s = chat_scene
    tracker = _open_task(s)
    assert tracker.respond_contact_id == s["contact"].id
    assignee = s["team"]["assignee"]

    with acting(s["db"], assignee, set()) as client:
        detail = client.get(f"{TICKET_BASE}/{tracker.id}/ticket")
        conversation = client.get(f"{TICKET_BASE}/{tracker.id}/conversation")
        sent = client.post(f"{TICKET_BASE}/{tracker.id}/ticket/send", json={"text": "Drawing is on its way"})

    assert detail.status_code == 200, detail.text
    assert detail.json()["id"] == str(tracker.id)
    assert conversation.status_code == 200, conversation.text
    assert sent.status_code == 200, sent.text
    assert sent.json()["sent_as"] == "text"
    assert _FakeRespond.sent_texts == [(s["contact"].respond_io_id, "Drawing is on its way")]
    s["db"].refresh(tracker)
    assert tracker.is_responded is True, "a reply is the Respond"
    assert str(tracker.responded_by) == str(assignee)
    assert tracker.is_resolved is False


def test_b4_the_media_detail_says_it_has_a_conversation(chat_scene, monkeypatch):
    _no_ack(monkeypatch)
    s = chat_scene
    tracker = _open_task(s)

    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        body = client.get(f"{SLA_BASE}/{tracker.id}/{DETAIL}").json()

    assert body["has_conversation"] is True


def test_b4_without_a_contact_the_chat_ticket_endpoints_still_refuse(scene):
    s = scene
    tracker = _open_task(s)
    assert tracker.respond_contact_id is None

    with acting(s["db"], s["team"]["assignee"], set()) as client:
        detail = client.get(f"{TICKET_BASE}/{tracker.id}/ticket")
        sent = client.post(f"{TICKET_BASE}/{tracker.id}/ticket/send", json={"text": "hello"})
        media = client.get(f"{SLA_BASE}/{tracker.id}/{DETAIL}")

    assert detail.status_code == 404, detail.text
    assert sent.status_code in (400, 422), sent.text
    s["db"].refresh(tracker)
    assert tracker.is_responded is False
    assert media.json()["has_conversation"] is False


# ------------------------------------------------------------------------------- B6: resolve


def _spy_resolve_helpers(monkeypatch):
    from app.services.sla_service import ConversationSLATrackingService

    calls = {"message": [], "close": []}
    monkeypatch.setattr(
        ConversationSLATrackingService,
        "_enqueue_ticket_resolved_message_best_effort",
        lambda self, tracking: calls["message"].append(str(tracking.id)),
    )
    monkeypatch.setattr(
        ConversationSLATrackingService,
        "_close_respond_conversation_best_effort",
        lambda self, tracking: calls["close"].append(str(tracking.id)),
    )
    return calls


def test_b6_resolving_a_media_ticket_with_a_contact_queues_the_closing_message_and_the_close(
    chat_scene, monkeypatch
):
    _no_ack(monkeypatch)
    s = chat_scene
    tracker = _open_task(s)
    calls = _spy_resolve_helpers(monkeypatch)

    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        response = client.post(f"{SLA_BASE}/{tracker.id}/media-resolve")

    assert response.status_code == 200, response.text
    assert calls == {"message": [str(tracker.id)], "close": [str(tracker.id)]}


def test_b6_resolving_a_media_ticket_without_a_contact_queues_neither(scene, monkeypatch):
    s = scene
    tracker = _open_task(s)
    calls = _spy_resolve_helpers(monkeypatch)

    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        response = client.post(f"{SLA_BASE}/{tracker.id}/media-resolve")

    assert response.status_code == 200, response.text
    s["db"].refresh(tracker)
    assert tracker.is_resolved is True
    assert calls == {"message": [], "close": []}


# -------------------------------------------------------------------- B8: the tile is per viewer


def _drawing_cell(s, user_id):
    with acting(s["db"], user_id, {VIEW}) as client:
        lines = client.get(f"{BASE}/quotation-versions/{s['version'].id}/lines")
    assert lines.status_code == 200, lines.text
    return next(r for r in lines.json()["data"] if r["id"] == str(s["line"].id))["technical_drawing"]


def test_b8_the_quotation_tile_shows_the_viewers_own_ticket_not_a_colleagues(scene):
    s = scene
    tracker = _open_task(s)  # the owner's

    mine = _drawing_cell(s, s["owner"])
    colleague = _drawing_cell(s, s["stranger"])

    assert mine["escalation"] is not None and mine["escalation"]["tracking_id"] == str(tracker.id)
    assert colleague["escalation"] is None, "a colleague's open ticket must not hide Escalate"

    with acting(s["db"], s["stranger"], {VIEW}) as client:
        own = client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})
    assert own.json()["joined"] is False
    assert own.json()["escalation"]["tracking_id"] != str(tracker.id)
    assert _drawing_cell(s, s["stranger"])["escalation"]["tracking_id"] == own.json()["escalation"]["tracking_id"]
    assert _drawing_cell(s, s["owner"])["escalation"]["tracking_id"] == str(tracker.id)


# =============================================================================================
# QUOTE-MEDIA-CHAT fix round 1: a media ticket with a contact is reachable through the chat ticket
# endpoints, so every read and send on it is scoped to the assignee's teams (S1, S2); the Respond
# close waits for every other open row on the contact (N1); the panel names the requester (B5).
# =============================================================================================

SLA_TRACKING_VIEW = "sla_management.conversation_sla_tracking.view"
#: A stranger who can read trackers and resolve, but is outside the assignee's teams.
STRANGER_PERMS = {SLA_TRACKING_VIEW, RESOLVE}


def test_s2_a_stranger_with_reader_and_resolve_permissions_cannot_read_or_send_on_a_media_ticket(
    chat_scene, monkeypatch
):
    _no_ack(monkeypatch)
    s = chat_scene
    tracker = _open_task(s)
    assert tracker.respond_contact_id == s["contact"].id

    with acting(s["db"], s["stranger"], STRANGER_PERMS) as client:
        responses = {
            "ticket": client.get(f"{TICKET_BASE}/{tracker.id}/ticket"),
            "conversation": client.get(f"{TICKET_BASE}/{tracker.id}/conversation"),
            "page": client.get(f"{TICKET_BASE}/{tracker.id}/conversation/page"),
            "media": client.get(
                f"{TICKET_BASE}/{tracker.id}/media", params={"url": "https://example.com/a.jpg"}
            ),
            "comments": client.get(f"{TICKET_BASE}/{tracker.id}/comments"),
            "send": client.post(f"{TICKET_BASE}/{tracker.id}/ticket/send", json={"text": "hello"}),
        }

    assert {name: r.status_code for name, r in responses.items()} == {name: 404 for name in responses}, {
        name: r.text for name, r in responses.items()
    }
    assert _FakeRespond.sent_texts == []
    s["db"].refresh(tracker)
    assert tracker.is_responded is False


def test_s1_a_stranger_cannot_send_on_a_media_ticket_through_the_reply_or_chat_template_routes(
    chat_scene, monkeypatch
):
    _no_ack(monkeypatch)
    s = chat_scene
    tracker = _open_task(s)
    reached: list = []
    monkeypatch.setattr(
        "app.services.respond_chat_template_service.precheck_manual_template",
        lambda *a, **k: reached.append("template") or {"template_name": "t", "rendered_body": "b"},
    )
    monkeypatch.setattr(
        "app.services.respond_chat_template_service.deliver_manual_template_now",
        lambda *a, **k: reached.append("deliver") or {"response": {}},
    )
    monkeypatch.setattr(
        "app.services.respond_chat_template_service.precheck_chat_send",
        lambda *a, **k: reached.append("chat") or {"sent_as": "text"},
    )

    with acting(s["db"], s["stranger"], STRANGER_PERMS) as client:
        reply = client.post(f"{TICKET_BASE}/{tracker.id}/conversation/reply", json={"message": "hello"})
        chat = client.post(f"{TICKET_BASE}/{tracker.id}/conversation/send-message", json={"text": "hello"})
        template = client.post(
            f"{TICKET_BASE}/{tracker.id}/conversation/template-message",
            json={"template_id": "tpl-1", "params": {}, "tracking_id": str(tracker.id)},
        )

    assert [reply.status_code, chat.status_code, template.status_code] == [404, 404, 404], [
        reply.text,
        chat.text,
        template.text,
    ]
    assert reached == [], "a refused sender must not reach the send machinery"
    assert _FakeRespond.sent_texts == []
    s["db"].refresh(tracker)
    assert tracker.is_responded is False


def test_s1_the_assignee_still_sends_through_the_reply_route(chat_scene, monkeypatch):
    _no_ack(monkeypatch)
    s = chat_scene
    tracker = _open_task(s)

    with acting(s["db"], s["team"]["assignee"], set()) as client:
        reply = client.post(f"{TICKET_BASE}/{tracker.id}/conversation/reply", json={"message": "on it"})

    assert reply.status_code == 200, reply.text
    assert _FakeRespond.sent_texts == [(s["contact"].respond_io_id, "on it")]


def test_n1_resolve_keeps_the_conversation_open_while_another_form_row_shares_the_contact(
    chat_scene, monkeypatch
):
    _no_ack(monkeypatch)
    s = chat_scene
    tracker = _open_task(s)
    # Another open form-SLA row (a complaint stage) on the same WhatsApp contact.
    sibling = ConversationSLATracking(
        policy_id=tracker.policy_id,
        current_tier=1,
        due_at=tracker.due_at,
        is_responded=False,
        is_resolved=False,
        company_id=tracker.company_id,
        source_entity_type="complaint",
        source_entity_id=_uid(),
        respond_contact_id=s["contact"].id,
    )
    s["db"].add(sibling)
    s["db"].commit()
    calls = _spy_resolve_helpers(monkeypatch)

    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        response = client.post(f"{SLA_BASE}/{tracker.id}/media-resolve")

    assert response.status_code == 200, response.text
    assert calls == {"message": [str(tracker.id)], "close": []}


def test_b5_the_media_detail_names_the_requester(chat_scene, monkeypatch):
    from app.models.user import User

    _no_ack(monkeypatch)
    s = chat_scene
    tracker = _open_task(s)
    owner = s["db"].query(User).filter(User.id == s["owner"]).one()

    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        body = client.get(f"{SLA_BASE}/{tracker.id}/{DETAIL}").json()

    assert body["requester_name"] == (owner.name or owner.email)
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", body["requester_name"])


# ------------------------------------------------- R1: one close rule, in both directions


def _chat_ticket_on(s, tracker, *, assignee):
    """An open chat ticket (no source entity) on the same WhatsApp contact."""
    row = ConversationSLATracking(
        policy_id=tracker.policy_id,
        current_tier=1,
        due_at=tracker.due_at,
        is_responded=False,
        is_resolved=False,
        company_id=tracker.company_id,
        respond_contact_id=s["contact"].id,
        assigned_to_id=assignee,
    )
    s["db"].add(row)
    s["db"].commit()
    return row


def test_r1_k3_a_media_resolve_keeps_the_conversation_open_while_a_chat_ticket_shares_the_contact(
    chat_scene, monkeypatch
):
    _no_ack(monkeypatch)
    s = chat_scene
    tracker = _open_task(s)
    _chat_ticket_on(s, tracker, assignee=s["team"]["assignee"])
    calls = _spy_resolve_helpers(monkeypatch)

    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        response = client.post(f"{SLA_BASE}/{tracker.id}/media-resolve")

    assert response.status_code == 200, response.text
    assert calls == {"message": [str(tracker.id)], "close": []}


def test_r1_a_chat_resolve_keeps_the_conversation_open_while_a_media_request_shares_the_contact(
    chat_scene, monkeypatch
):
    from app.schemas.sla import ConversationSLATrackingUpdate
    from app.services.sla_service import ConversationSLATrackingService

    _no_ack(monkeypatch)
    s = chat_scene
    media = _open_task(s)
    chat = _chat_ticket_on(s, media, assignee=s["team"]["assignee"])
    calls = _spy_resolve_helpers(monkeypatch)

    ConversationSLATrackingService(s["db"]).update_tracking(
        str(chat.id),
        ConversationSLATrackingUpdate(is_resolved=True, resolved_by=str(s["team"]["assignee"])),
    )

    assert calls == {"message": [str(chat.id)], "close": []}


def test_r1_a_chat_resolve_with_nothing_else_open_on_the_contact_still_closes(chat_scene, monkeypatch):
    from app.schemas.sla import ConversationSLATrackingUpdate
    from app.services.sla_service import ConversationSLATrackingService

    _no_ack(monkeypatch)
    s = chat_scene
    media = _open_task(s)
    chat = _chat_ticket_on(s, media, assignee=s["team"]["assignee"])
    media.is_resolved = True
    s["db"].commit()
    calls = _spy_resolve_helpers(monkeypatch)

    ConversationSLATrackingService(s["db"]).update_tracking(
        str(chat.id),
        ConversationSLATrackingUpdate(is_resolved=True, resolved_by=str(s["team"]["assignee"])),
    )

    assert calls == {"message": [str(chat.id)], "close": [str(chat.id)]}


# ---------------------------------------------------- R5 K1/K2: the assignee works the ticket


def test_k1_the_assignee_lists_and_writes_comments_on_a_media_ticket(chat_scene, monkeypatch):
    _no_ack(monkeypatch)
    monkeypatch.setattr(
        "app.services.ticket_comment_service.mirror_comment_to_respond", lambda *a, **k: None
    )
    s = chat_scene
    tracker = _open_task(s)

    with acting(s["db"], s["team"]["assignee"], set()) as client:
        created = client.post(f"{TICKET_BASE}/{tracker.id}/comments", json={"body": "Asked the factory"})
        listed = client.get(f"{TICKET_BASE}/{tracker.id}/comments")

    assert created.status_code == 201, created.text
    assert listed.status_code == 200, listed.text
    assert [c["body"] for c in listed.json()] == ["Asked the factory"]


def test_k2_the_assignee_reads_the_page_the_search_and_the_media_proxy(chat_scene, monkeypatch):
    from starlette.responses import Response

    import app.services.media_proxy_service as media_proxy_service

    _no_ack(monkeypatch)

    async def _stream(url):
        return Response(content=b"img", media_type="image/jpeg")

    monkeypatch.setattr(media_proxy_service, "stream", _stream)
    s = chat_scene
    tracker = _open_task(s)

    with acting(s["db"], s["team"]["assignee"], set()) as client:
        page = client.get(f"{TICKET_BASE}/{tracker.id}/conversation/page")
        search = client.get(f"{TICKET_BASE}/{tracker.id}/conversation/search", params={"q": "drawing"})
        media = client.get(f"{TICKET_BASE}/{tracker.id}/media", params={"url": "https://example.com/a.jpg"})

    assert [page.status_code, search.status_code, media.status_code] == [200, 200, 200], [
        page.text,
        search.text,
        media.text,
    ]
    assert media.content == b"img"


# --------------------------------------------- R2: the acknowledgement job, in the window


class _NoCloseSession:
    def __init__(self, inner):
        self._inner = inner

    def close(self):
        return None

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_r2_the_ack_job_sends_the_exact_text_in_window_and_logs_against_the_ticket(chat_scene, monkeypatch):
    import app.database as database_module
    import app.services.crm_chat_outbound_webhook as outbound
    import app.services.respond_messaging_service as messaging
    from app.models.chat_history import ChatHistory
    from app.models.integration import IntegrationLog
    from app.tasks.respond_io_tasks import send_media_request_ack

    _no_ack(monkeypatch)
    s = chat_scene
    tracker = _open_task(s)
    text = "Your project request: technical drawing for X (Q). Routed to your PIC, they will reply shortly."
    sent: list = []
    templated: list = []
    webhooks: list = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        def send_message(self, identifier, body):
            sent.append((identifier, body))
            return {"messageId": 1_787_640_441_538_999}

    monkeypatch.setattr("app.services.integration_service.RespondClient", _Client)
    monkeypatch.setattr(
        messaging, "render_in_window_text", lambda *a, **k: templated.append(k) or "TEMPLATE BODY"
    )
    monkeypatch.setattr(outbound, "enqueue_crm_chat_outbound_webhook", lambda *a, **k: webhooks.append(k))
    monkeypatch.setattr(database_module, "SessionLocal", lambda: _NoCloseSession(s["db"]))

    result = send_media_request_ack(str(s["contact"].id), text, str(tracker.id))

    assert result["status"] == "success" and result["sent_as"] == "text"
    assert sent == [(s["contact"].respond_io_id, text)], "in-window: the exact text, no template"
    assert templated == []
    assert webhooks == [], "the CRM speaking is not a human answer"
    logs = (
        s["db"]
        .query(IntegrationLog)
        .filter(
            IntegrationLog.integration_channel == "respond_io",
            IntegrationLog.business_table == "conversation_sla_tracking",
            IntegrationLog.business_id == str(tracker.id),
        )
        .all()
    )
    assert [log.status for log in logs] == ["success"]
    thread = s["db"].query(ChatHistory).filter(ChatHistory.contact_id == s["contact"].respond_io_id).all()
    assert [(r.type, r.message) for r in thread] == [("outgoing", text)], "the PIC sees it at once"
