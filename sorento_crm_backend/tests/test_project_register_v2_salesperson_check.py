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


# ------------------------------------------------------------------ round 2: the out-of-scope path


def _dispute(w, user, project_id):
    return as_user(w, user).post(
        f"{STAFF}/{project_id}/takeover-requests", json={"kind": "dispute", "reason": REASON}
    )


def _leaks(text: str, *needles) -> list:
    return [n for n in (*needles, "Awaiting approval", "Rejected") if n and n in text]


def test_r2_a_view_own_user_without_the_submit_slug_gets_404_on_anothers_approved_project(v2):
    row = approved_project(v2)
    res = _dispute(v2, v2.viewer_own, row.id)
    assert res.status_code == 404, res.text


def test_r2_a_submit_user_gets_404_on_a_pending_or_rejected_project_without_any_facts(v2):
    for state in ("pending", "rejected"):
        ttl = title(f"Secret {state}")
        row = project(v2.db, v2.company_id, ttl, approval_state=state, owner=v2.owner)
        res = _dispute(v2, v2.sub_a, row.id)
        assert res.status_code == 404, (state, res.text)
        assert _leaks(res.text, ttl, row.project_code) == [], (state, res.text)


def test_r2_a_second_dispute_is_refused_without_the_project_code_or_title(v2):
    row = approved_project(v2)
    assert _dispute(v2, v2.sub_a, row.id).status_code == 201
    again = _dispute(v2, v2.sub_a, row.id)
    assert again.status_code in (404, 409, 422), again.text
    assert _leaks(again.text, row.title, row.project_code) == [], again.text


def test_r2_the_first_dispute_on_an_approved_project_is_201_with_no_project_facts(v2):
    row = approved_project(v2)
    res = _dispute(v2, v2.sub_a, row.id)
    assert res.status_code == 201, res.text
    assert row.title not in res.text and (row.project_code or "zzt-none") not in res.text


# ------------------------------------------------------------------ round 2: reference parties


FULL = {"phone", "email", "address", "notes", "registration_no", "customer_id"}


def _seed_architect(w):
    from app.models.projects import ProjectParty

    from ._project_register_v2_support import uid

    row = ProjectParty(
        id=uid(), company_id=w.company_id, party_type="architect", name="CONTOH Architect Full",
        phone="+60123456789", email="a@example.test", address="1 Jalan Contoh",
        notes="private note", registration_no="REG-ZZT-1",
    )
    w.db.add(row)
    w.db.flush()
    return row


def test_r2_party_search_for_a_caller_without_parties_view_returns_only_id_name_type(v2):
    _seed_architect(v2)
    res = as_user(v2, v2.sub_a).get(
        "/api/v1/project-sales/parties/", params={"party_type": "architect", "query": "Full"}
    )
    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    assert [r["name"] for r in rows] == ["CONTOH Architect Full"]
    assert set(rows[0]) == {"id", "name", "party_type"}, set(rows[0])
    assert not FULL & set(rows[0])
    assert "project_count" not in rows[0] and "projects_count" not in rows[0]


def test_r2_a_parties_view_holder_still_gets_the_full_row(v2):
    _seed_architect(v2)
    res = as_user(v2, v2.owner).get(
        "/api/v1/project-sales/parties/", params={"party_type": "architect", "query": "Full"}
    )
    assert res.status_code == 200, res.text
    row = res.json()["data"][0]
    assert FULL <= set(row)
    assert row["phone"] == "+60123456789" and row["registration_no"] == "REG-ZZT-1"
