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


def test_a_second_person_joins_and_is_counted_over_http(scene):
    s = scene
    with acting(s["db"], s["owner"], {VIEW}) as client:
        client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})
    with acting(s["db"], s["stranger"], {VIEW}) as client:
        joined = client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})

    assert joined.status_code in (200, 201), joined.text
    assert joined.json()["joined"] is True
    assert joined.json()["escalation"]["requester_count"] == 2
    assert len(trackers_for(s["db"], s["product"].id)) == 1


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


def test_the_assignee_resolves_and_every_requester_is_told_once(scene):
    s = scene
    tracker = _open_task(s)
    with acting(s["db"], s["stranger"], {VIEW}) as client:
        client.post(_url(s["version"].id, s["line"].id), json={"kind": "drawing"})
    with acting(s["db"], s["team"]["assignee"], {RESOLVE}) as client:
        response = client.post(f"{SLA_BASE}/{tracker.id}/media-resolve")

    assert response.status_code == 200, response.text
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
