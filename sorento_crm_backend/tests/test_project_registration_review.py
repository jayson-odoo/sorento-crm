"""PROJECT-REG-PORTAL CRM queue and review, red-first (UAC B1-B10, C4, E1, F2).

Route level on purpose: the UAC promises HTTP behaviour (codes, keys, 403 vs 409). The CRM
routes live at `/api/v1/project-sales/projects/registrations` (see the support module).
Expected red reasons now: no `app.models.project_registration`, and 404 / 405 for routes that
are not mounted yet.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_registration_support import (
    CRM,
    STAFF,
    SUB,
    approve_body,
    as_contact,
    as_user,
    create_draft,
    developer,
    legacy_rule,
    pending,
    ppf_code,
    project,
    project_type,
    registration,
    rule_next_value,
    submit,
    uid,
    world,  # noqa: F401  (fixture)
)


def _ids(res) -> list:
    assert res.status_code == 200, res.text
    return [r["id"] for r in res.json()["data"]]


def _set(world, rid, **cols):
    row = registration(world, rid)
    for key, value in cols.items():
        setattr(row, key, value)
    world.db.flush()
    return row


# ------------------------------------------------------------------ B1 permission


def test_b1_without_the_grant_every_route_is_403(world):
    rid = pending(world)
    c = as_user(world, world.staff)
    calls = [
        c.get(CRM),
        c.get(f"{CRM}/{rid}"),
        c.post(f"{CRM}/{rid}/approve", json=approve_body(world, rid)),
        c.post(f"{CRM}/{rid}/reject", json={"reason": "no"}),
    ]
    for res in calls:
        assert res.status_code == 403, (res.request.method, res.request.url, res.status_code, res.text)
    assert registration(world, rid).status == "pending"


def test_b1_the_grant_opens_them(world):
    rid = pending(world)
    c = as_user(world, world.approver)
    assert c.get(CRM).status_code == 200
    assert c.get(f"{CRM}/{rid}").status_code == 200


def test_b1_the_slug_is_in_the_permission_registry():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert "projects.registrations.approve" in {p["slug"] for p in PERMISSION_REGISTRY}


# ------------------------------------------------------------------ B2 list


def test_b2_default_is_pending_and_status_all_returns_every_status(world):
    p = pending(world, title="QUEUE PENDING ONE")
    approved = pending(world, title="QUEUE APPROVED ONE")
    rejected = pending(world, title="QUEUE REJECTED ONE")
    _set(world, approved, status="approved")
    _set(world, rejected, status="rejected", reject_reason="duplicate")

    c = as_user(world, world.approver)
    assert _ids(c.get(CRM)) == [p]
    assert _ids(c.get(CRM, params={"status": "pending"})) == [p]
    every = set(_ids(c.get(CRM, params={"status": "all", "limit": 50})))
    assert {p, approved, rejected} <= every
    assert _ids(c.get(CRM, params={"status": "rejected"})) == [rejected]


def test_b2_query_searches_title_developer_and_distributor(world):
    by_title = pending(world, title="MARIGOLD SQUARE", developer_name="Plain A", distributor_name="Plain A2")
    by_dev = pending(world, title="PLAIN B", developer_name="Camellia Holdings", distributor_name="Plain B2")
    by_dist = pending(world, title="PLAIN C", developer_name="Plain C1", distributor_name="Peony Trading")
    c = as_user(world, world.approver)
    assert _ids(c.get(CRM, params={"query": "marigold"})) == [by_title]
    assert _ids(c.get(CRM, params={"query": "camellia"})) == [by_dev]
    assert _ids(c.get(CRM, params={"query": "peony"})) == [by_dist]


def test_b2_paging_and_sorting_by_submitted_at(world):
    ids = [pending(world, title=f"PAGED TOWER {n}") for n in range(3)]
    base = datetime(2026, 3, 1, 9, 0, 0)
    for n, rid in enumerate(ids):
        _set(world, rid, submitted_at=base + timedelta(days=n))
    c = as_user(world, world.approver)

    asc = c.get(CRM, params={"sort": "submitted_at", "dir": "asc", "limit": 2, "page": 1})
    assert _ids(asc) == ids[:2]
    assert asc.json()["pagination"]["total"] == 3
    assert _ids(c.get(CRM, params={"sort": "submitted_at", "dir": "asc", "limit": 2, "page": 2})) == ids[2:]
    assert _ids(c.get(CRM, params={"sort": "submitted_at", "dir": "desc"})) == list(reversed(ids))


# ------------------------------------------------------------------ B3 row shape


def test_b3_a_row_carries_the_agents_name_and_possible_duplicates_with_ids(world):
    existing = project(world.db, world.company_id, "KILANG ALPHA LOT 9001 MUKIM TEBRAU", code="PRJ-ZZT-9001")
    rid = pending(
        world,
        title="CADANGAN PEMBINAAN GUDANG DI ATAS LOT 9001, MUKIM TEBRAU, JOHOR",
        mukim="Tebrau",
        state="Johor",
    )
    rows = as_user(world, world.approver).get(CRM).json()["data"]
    row = next(r for r in rows if r["id"] == rid)
    assert row["sales_agent_name"] == "Aminah Example"
    assert row["sales_agent_name"] != world.agent_a.sales_agent
    assert row["state"] == "Johor"
    assert row["status"] == "pending"
    assert row["developer_name"] == "Example Developer Sdn Bhd"
    assert row["title"].startswith("CADANGAN PEMBINAAN GUDANG")
    assert row["submitted_at"]
    assert row["project_id"] is None and row["project_code"] is None
    assert row["possible_duplicates"] == [
        {"project_id": existing.id, "project_code": existing.project_code, "title": existing.title}
    ]


def test_b3_no_duplicate_is_an_empty_list(world):
    rid = pending(world)
    row = next(r for r in as_user(world, world.approver).get(CRM).json()["data"] if r["id"] == rid)
    assert row["possible_duplicates"] == []


# ------------------------------------------------------------------ B4 prefill


def test_b4_detail_prefills_parties_and_type_ignoring_case_and_spaces(world):
    dev = developer(world.db, world.company_id, "EXAMPLE DEVELOPER SDN BHD")
    arch = developer(world.db, world.company_id, "example architects ", "architect")
    contractor = developer(world.db, world.company_id, "Example Builders Sdn Bhd", "main_contractor")
    kind = project_type(world.db, world.company_id, "Office")
    rid = pending(
        world,
        developer_name="  example developer sdn bhd ",
        architect_name="Example Architects",
        main_contractor_name=" EXAMPLE BUILDERS SDN BHD",
        type_of_building="office",
    )
    d = as_user(world, world.approver).get(f"{CRM}/{rid}").json()
    assert d["prefill"] == {
        "developer_party_id": dev.id,
        "architect_party_id": arch.id,
        "main_contractor_party_id": contractor.id,
        "type_id": kind.id,
    }
    assert d["sales_agent_name"] == "Aminah Example"
    assert d["status"] == "pending"
    assert d["applicant_user_id"] == world.applicant_user
    assert d["title"] and d["state"] == "Johor" and d["mukim"] == "Kulai"
    assert d["distributor_name"] and d["your_ref"] and d["customer_name"] is not None
    assert d["possible_duplicates"] == []
    assert d["project_id"] is None and d["reject_reason"] is None


def test_b4_no_match_or_a_party_of_the_wrong_type_is_null(world):
    developer(world.db, world.company_id, "Example Developer Sdn Bhd", "architect")
    rid = pending(world)
    prefill = as_user(world, world.approver).get(f"{CRM}/{rid}").json()["prefill"]
    assert prefill == {
        "developer_party_id": None,
        "architect_party_id": None,
        "main_contractor_party_id": None,
        "type_id": None,
    }


def test_b4_unknown_id_is_404_while_a_real_one_is_served(world):
    rid = pending(world)
    c = as_user(world, world.approver)
    assert c.get(f"{CRM}/{rid}").status_code == 200
    assert c.get(f"{CRM}/{uid()}").status_code == 404


# ------------------------------------------------------------------ B5 approve


def test_b5_approve_creates_the_project_with_a_ppf_code(world):
    from app.models.projects import Project, ProjectSalesProfile

    rid = pending(world, title="  CADANGAN   BLOK   BETA ")
    body = approve_body(world, rid, state="Johor", mukim="Kulai")
    res = as_user(world, world.approver).post(f"{CRM}/{rid}/approve", json=body)
    assert res.status_code == 200, res.text
    out = res.json()
    code = ppf_code(5)
    assert out["status"] == "approved"
    assert out["project_code"] == code
    assert out["project_id"]

    world.db.expire_all()
    made = world.db.get(Project, out["project_id"])
    assert made.project_code == code
    assert made.title == "CADANGAN BLOK BETA"
    assert made.developer_party_id == body["developer_party_id"]
    assert made.owner_user_id == world.owner
    assert made.outcome == "open"
    profile = world.db.get(ProjectSalesProfile, made.id)
    assert (profile.state, profile.mukim) == ("Johor", "Kulai")

    row = registration(world, rid)
    assert row.status == "approved"
    assert row.project_id == made.id
    assert row.decided_at is not None
    assert row.decided_by == world.approver

    portal = as_contact(world, world.a).get(f"{SUB}/{rid}").json()
    assert portal["status"] == "approved"
    assert portal["reference"] == code
    assert portal["is_draft"] is False
    assert rule_next_value(world.db, world.rule_id) == 6


def test_b5_the_detail_afterwards_names_the_project(world):
    rid = pending(world)
    as_user(world, world.approver).post(f"{CRM}/{rid}/approve", json=approve_body(world, rid))
    d = as_user(world, world.approver).get(f"{CRM}/{rid}").json()
    assert d["project_code"] == ppf_code(5)
    assert d["decided_by_name"]
    assert d["decided_at"]


# ------------------------------------------------------------------ B6 / B7 duplicates


def test_b6_a_blocking_spelling_clash_never_blocks_the_queue(world):
    from app.services.project_clash_service import find_clashes

    dev = developer(world.db, world.company_id, "Setia Example Group")
    existing = project(world.db, world.company_id, "Setia Alam Phase 3B", developer_party=dev)
    rid = pending(world, title="Setia Alam Ph 3B")
    body = approve_body(world, rid, developer_party_id=dev.id)
    # Guard: this really is a clash the staff route would refuse.
    clashes = find_clashes(world.db, company_id=world.company_id, developer_party_id=dev.id, title="Setia Alam Ph 3B")
    assert any(cand.blocks and cand.project_id == existing.id for cand in clashes)

    res = as_user(world, world.approver).post(f"{CRM}/{rid}/approve", json=body)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"


def test_b7_an_exact_same_developer_and_title_is_409_naming_the_project(world):
    from app.models.projects import Project

    dev = developer(world.db, world.company_id, "Setia Example Group")
    existing = project(world.db, world.company_id, "Setia Alam Phase 3B", developer_party=dev, code="PRJ-ZZT-EXACT")
    rid = pending(world, title="  SETIA ALAM   phase 3b ")
    before = world.db.query(Project).filter(Project.company_id == world.company_id).count()

    res = as_user(world, world.approver).post(
        f"{CRM}/{rid}/approve", json=approve_body(world, rid, developer_party_id=dev.id)
    )
    assert res.status_code == 409, res.text
    assert res.json()["code"] == "project_registration_exact_duplicate"
    assert existing.project_code in res.json()["message"]

    assert world.db.query(Project).filter(Project.company_id == world.company_id).count() == before
    row = registration(world, rid)
    assert row.status == "pending" and row.project_id is None
    assert rule_next_value(world.db, world.rule_id) == 5


def test_b7_the_registration_can_be_approved_after_the_title_changes(world):
    dev = developer(world.db, world.company_id, "Setia Example Group")
    project(world.db, world.company_id, "Setia Alam Phase 3B", developer_party=dev)
    rid = pending(world, title="Setia Alam Phase 3B")
    c = as_user(world, world.approver)
    first = c.post(f"{CRM}/{rid}/approve", json=approve_body(world, rid, developer_party_id=dev.id))
    assert first.status_code == 409
    second = c.post(
        f"{CRM}/{rid}/approve",
        json=approve_body(world, rid, developer_party_id=dev.id, title="Setia Alam Phase 3B (Block C)"),
    )
    assert second.status_code == 200, second.text
    assert second.json()["project_code"] == ppf_code(5)


# ------------------------------------------------------------------ B8 guards


def test_b8_approve_without_a_developer_is_422(world):
    rid = pending(world)
    body = approve_body(world, rid)
    del body["developer_party_id"]
    res = as_user(world, world.approver).post(f"{CRM}/{rid}/approve", json=body)
    assert res.status_code == 422, res.text
    assert registration(world, rid).status == "pending"


def test_b8_approve_or_reject_a_non_pending_registration_is_409(world):
    c = as_user(world, world.approver)
    done = pending(world)
    assert c.post(f"{CRM}/{done}/approve", json=approve_body(world, done)).status_code == 200
    rejected = pending(world)
    assert c.post(f"{CRM}/{rejected}/reject", json={"reason": "not ours"}).status_code == 200
    draft = create_draft(world)["id"]

    for rid in (done, rejected, draft):
        a = c.post(f"{CRM}/{rid}/approve", json=approve_body(world, rid))
        assert a.status_code == 409, (rid, a.text)
        assert a.json()["code"] == "project_registration_not_pending"
        r = c.post(f"{CRM}/{rid}/reject", json={"reason": "again"})
        assert r.status_code == 409, (rid, r.text)
        assert r.json()["code"] == "project_registration_not_pending"


# ------------------------------------------------------------------ B9 reject cycle


def test_b9_reject_needs_a_reason(world):
    rid = pending(world)
    c = as_user(world, world.approver)
    for reason in ("", "   "):
        res = c.post(f"{CRM}/{rid}/reject", json={"reason": reason})
        assert res.status_code == 422, (reason, res.text)
    assert c.post(f"{CRM}/{rid}/reject", json={}).status_code == 422
    assert registration(world, rid).status == "pending"


def test_b9_reject_then_the_contact_edits_and_resubmits(world):
    rid = pending(world)
    res = as_user(world, world.approver).post(f"{CRM}/{rid}/reject", json={"reason": "Already registered by Bakar"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "rejected"
    row = registration(world, rid)
    assert row.status == "rejected"
    assert row.reject_reason == "Already registered by Bakar"
    assert row.decided_at is not None and row.decided_by == world.approver

    c = as_contact(world, world.a)
    d = c.get(f"{SUB}/{rid}").json()
    assert d["status"] == "rejected"
    assert d["reject_reason"] == "Already registered by Bakar"
    assert d["is_draft"] is True

    edit = c.put(f"{SUB}/{rid}", json={"fields": {"title": "CADANGAN BLOK BETA FASA 2", "state": "Johor",
                                                  "developer_name": "Example Developer Sdn Bhd"}})
    assert edit.status_code == 200, edit.text
    again = submit(world, rid)
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "pending"
    row = registration(world, rid)
    assert row.status == "pending"
    assert row.reject_reason is None
    assert c.get(f"{SUB}/{rid}").json()["reject_reason"] is None
    assert _ids(as_user(world, world.approver).get(CRM)) == [rid]


# ------------------------------------------------------------------ B10 staff route unchanged


def test_b10_staff_direct_registration_still_refuses_a_blocking_clash(world):
    legacy_rule(world)
    dev = developer(world.db, world.company_id, "Setia Example Group")
    c = as_user(world, world.staff)
    first = c.post(f"{STAFF}/", json={"title": "Setia Alam Phase 3B", "developer_party_id": dev.id})
    assert first.status_code == 201, first.text
    second = c.post(f"{STAFF}/", json={"title": "setia alam ph 3b", "developer_party_id": dev.id})
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "project_already_registered"


def test_b10_skip_clash_check_is_opt_in_at_the_service(world):
    legacy_rule(world)
    import pytest

    from app.services.error_handler import AppException
    from app.services.project_service import register_project

    dev = developer(world.db, world.company_id, "Setia Example Group")
    kw = dict(company_id=world.company_id, actor_user_id=world.owner, developer_party_id=dev.id)
    register_project(world.db, title="Setia Alam Phase 3B", **kw)
    with pytest.raises(AppException) as exc:
        register_project(world.db, title="setia alam ph 3b", **kw)
    assert exc.value.status_code == 409
    made = register_project(world.db, title="setia alam ph 3b", skip_clash_check=True, **kw)
    assert made.project_code


# ------------------------------------------------------------------ C4 numbering


def test_c4_submitted_and_rejected_registrations_draw_no_number(world):
    create_draft(world)
    rid = pending(world)
    assert rule_next_value(world.db, world.rule_id) == 5
    as_user(world, world.approver).post(f"{CRM}/{rid}/reject", json={"reason": "no"})
    assert rule_next_value(world.db, world.rule_id) == 5
    assert registration(world, rid).project_id is None


# ------------------------------------------------------------------ E1 project fields


def test_e1_state_and_mukim_on_register_get_and_update(world):
    legacy_rule(world)
    c = as_user(world, world.staff)
    made = c.post(f"{STAFF}/", json={"title": "ZZT FIELDS TOWER", "state": "Selangor", "mukim": "Petaling"})
    assert made.status_code == 201, made.text
    assert (made.json()["state"], made.json()["mukim"]) == ("Selangor", "Petaling")
    pid = made.json()["id"]

    got = c.get(f"{STAFF}/{pid}").json()
    assert (got["state"], got["mukim"]) == ("Selangor", "Petaling")

    upd = c.put(f"{STAFF}/{pid}", json={"state": "Johor", "mukim": "Tebrau"})
    assert upd.status_code == 200, upd.text
    assert (upd.json()["state"], upd.json()["mukim"]) == ("Johor", "Tebrau")
    assert (c.get(f"{STAFF}/{pid}").json()["state"]) == "Johor"


def test_e1_a_project_without_them_returns_nulls(world):
    legacy_rule(world)
    c = as_user(world, world.staff)
    made = c.post(f"{STAFF}/", json={"title": "ZZT PLAIN TOWER"})
    assert made.status_code == 201, made.text
    body = made.json()
    assert "state" in body and body["state"] is None
    assert "mukim" in body and body["mukim"] is None


# ------------------------------------------------------------------ F2 decision notices


def test_f2_approve_and_reject_notify_the_linked_crm_user(world):
    c = as_user(world, world.approver)
    ok = pending(world)
    world.sent.clear()
    assert c.post(f"{CRM}/{ok}/approve", json=approve_body(world, ok)).status_code == 200
    assert {user for user, _t in world.sent} == {world.applicant_user}

    no = pending(world)
    world.sent.clear()
    assert c.post(f"{CRM}/{no}/reject", json={"reason": "not ours"}).status_code == 200
    assert {user for user, _t in world.sent} == {world.applicant_user}


def test_f2_no_linked_user_means_no_error_and_nobody_notified(world):
    c = as_user(world, world.approver)
    rid = pending(world, world.b)
    world.sent.clear()
    assert c.post(f"{CRM}/{rid}/approve", json=approve_body(world, rid)).status_code == 200
    other = pending(world, world.b)
    world.sent.clear()
    assert c.post(f"{CRM}/{other}/reject", json={"reason": "no"}).status_code == 200
    assert world.sent == []
