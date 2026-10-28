"""PROJECT-REGISTER-V2 UAC D8: a salesperson (view_own + projects.registrations.submit, no
projects.projects.view) can run the Check, register interest and search reference parties, and
sees no facts about other people's projects."""
from __future__ import annotations

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_register_v2_support import (  # noqa: F401
    STAFF,
    approved_project,
    as_user,
    developer,
    project,
    title,
    v2,
)

PREVIEW = f"{STAFF}/clash-preview"
ONLY = {"project_id", "project_code", "title", "blocks"}
REASON = "Found this project at the site briefing last week."


def test_d8_the_check_works_for_the_submit_slug_and_candidates_carry_only_four_keys(v2):
    ttl = title("Residensi")
    dev = developer(v2.db, v2.company_id, "CONTOH Developer Sdn Bhd")
    approved_project(v2, ttl=ttl, dev=dev)
    res = as_user(v2, v2.sub_a).post(PREVIEW, json={"title": ttl})
    assert res.status_code == 200, res.text
    candidates = res.json()["candidates"]
    assert candidates
    for c in candidates:
        assert set(c) == ONLY, set(c)
    assert any(c["blocks"] for c in candidates)


def test_d8_a_user_with_neither_view_nor_submit_is_still_403_on_the_check(v2):
    res = as_user(v2, v2.nobody).post(PREVIEW, json={"title": title()})
    assert res.status_code == 403, res.text


def test_d8_a_submit_slug_user_registers_interest_and_gets_the_request_only(v2):
    row = approved_project(v2)
    res = as_user(v2, v2.sub_a).post(
        f"{STAFF}/{row.id}/takeover-requests", json={"kind": "dispute", "reason": REASON}
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "dispute" and body["status"] == "pending"
    for fact in ("project_code", "project_title"):
        assert not body.get(fact), body


def test_d8_interest_is_refused_on_an_unapproved_or_other_company_project(v2):
    from app.models.projects import ProjectTakeoverRequest

    pending = project(v2.db, v2.company_id, title("Pending"), approval_state="pending", owner=v2.owner)
    res = as_user(v2, v2.sub_a).post(
        f"{STAFF}/{pending.id}/takeover-requests", json={"kind": "dispute", "reason": REASON}
    )
    assert res.status_code in (404, 409), res.text

    from app.models.base import company_scope

    with company_scope(v2.db, frozenset({v2.other_company})):
        foreign = project(v2.db, v2.other_company, title("Foreign"), owner=v2.owner)
    res = as_user(v2, v2.sub_a).post(
        f"{STAFF}/{foreign.id}/takeover-requests", json={"kind": "dispute", "reason": REASON}
    )
    assert res.status_code in (403, 404), res.text
    v2.db.expire_all()
    assert v2.db.query(ProjectTakeoverRequest).filter(
        ProjectTakeoverRequest.requester_user_id == v2.sub_a
    ).count() == 0


def test_d8_party_search_is_open_to_the_submit_slug(v2):
    res = as_user(v2, v2.sub_a).get(
        "/api/v1/project-sales/parties/", params={"party_type": "architect", "query": "x"}
    )
    assert res.status_code == 200, res.text
