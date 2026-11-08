"""NPA-FORM-SLA, red-first: the New Product Application's approval and purchasing run through
Form SLA config like the Stock Inquiry (documentation/plans/procurement/PLAN-npa-form-sla-08nov.md).

Route level, Postgres only. Reuses the NEW-PRODUCT-APP harness (real role grants for the broadcast
fallback, permission checks swapped per caller) and the forms-chain SLA seed (real agent, team
sets, tier teams, policy), so the engine under test is the SI's own `FormSLAOrchestrator`.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from ._forms_chain_support import open_tracker, settings_row, sla_chain, trackers
from .test_new_product_application import (  # noqa: F401  (fixtures)
    APPROVE,
    NPA,
    OPEN_CODE,
    VIEW,
    _act,
    _draft,
    _get,
    _to,
    sent,
    world,
)

KIND = "new_product_application"
ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "npasla_0001_seed_configs"


def _stages(db):
    """The two NPA rows the seed ships (card stage map), on a seeded agent + team sets."""
    chain = sla_chain(
        db,
        KIND,
        [
            {"start_event": "submitted,resubmitted", "resolve_event": "approved,rejected"},
            {
                "start_event": "approved",
                "respond_event": "purchasing_respond",
                "resolve_event": "completed,rejected",
            },
        ],
    )
    # The seed links nothing: purchasing starts on its own event, as the SI's purchasing row.
    for stage in chain.stages:
        stage.config.next_config_id = None
    db.commit()
    approval, purchasing = chain.stages
    return SimpleNamespace(approval=approval, purchasing=purchasing)


@pytest.fixture()
def sla(world):
    return _stages(world.db)


def _form_sla_to(w, user_id):
    return [t for (u, t, _e) in w.sent if u == user_id and t == "form_sla"]


def _submitted(w):
    d = _draft(w)
    res = _act(w, d["id"], "submit", w.sales)
    assert res.status_code == 200, res.text
    return res.json()


def _approved(w):
    d = _submitted(w)
    res = _act(w, d["id"], "approve", w.manager)
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------------ the type is a form SLA type


def test_npa_is_a_form_sla_type_in_every_list_that_must_match():
    from app.api.v1.sla.sla_tracking import SOURCE_TYPE_READERS
    from app.schemas.sla import _FORM_SLA_TYPES
    from app.services import form_sla_service as f

    assert KIND in f.FORM_SLA_TYPES
    assert KIND in _FORM_SLA_TYPES
    assert f._ENTITY_NUMBER_SOURCE[KIND] == ("new_product_applications", "application_no", False)
    assert f._form_detail_link(KIND, "abc") == "/procurement-management/new-product-applications/abc"
    assert f._stage_action_verb(KIND, "project_sales", "resolution") == "approve or reject"
    assert f._stage_action_verb(KIND, "purchasing", "response") == "send the purchasing response"
    assert set(SOURCE_TYPE_READERS[KIND]) == {VIEW, APPROVE, OPEN_CODE}


def test_a_config_row_for_npa_validates():
    from app.schemas.sla import FormSLAConfigBase

    row = FormSLAConfigBase(
        source_entity_type=KIND,
        stage_code="npa_approval",
        policy_id="00000000-0000-0000-0000-000000000000",
        agent_code="lead_time_enquiries",
        start_event="submitted",
    )
    assert row.source_entity_type == KIND


# ------------------------------------------------------------------ approval stage


def test_submit_starts_the_approval_stage_and_tells_only_its_assignee(world, sla):
    d = _submitted(world)
    tracker = open_tracker(world.db, KIND, d["id"])
    assert tracker.team_set_code == sla.approval.team_set
    assert tracker.assigned_to_id == sla.approval.tier1
    assert _form_sla_to(world, sla.approval.tier1)
    # The broadcast to every approver is gone.
    assert not _to(world, d["id"], "new_product_application_submitted")


def test_approve_resolves_approval_and_starts_purchasing_for_its_assignee_only(world, sla):
    d = _approved(world)
    rows = trackers(world.db, KIND, d["id"])
    approval = [t for t in rows if t.team_set_code == sla.approval.team_set]
    assert len(approval) == 1 and approval[0].is_resolved
    tracker = open_tracker(world.db, KIND, d["id"])
    assert tracker.team_set_code == sla.purchasing.team_set
    assert tracker.assigned_to_id == sla.purchasing.tier1
    assert _form_sla_to(world, sla.purchasing.tier1)
    assert not _to(world, d["id"], "new_product_application_approved")


def test_reject_resolves_approval_starts_nothing_and_still_tells_the_applicant(world, sla):
    d = _submitted(world)
    res = _act(world, d["id"], "reject", world.manager, reason="Not a product we sell")
    assert res.status_code == 200, res.text
    rows = trackers(world.db, KIND, d["id"])
    assert len(rows) == 1 and rows[0].is_resolved
    assert _to(world, d["id"], "new_product_application_rejected") == {world.sales}


def test_resubmit_after_reject_starts_a_fresh_approval_stage(world, sla):
    d = _submitted(world)
    assert _act(world, d["id"], "reject", world.manager, reason="Add the finish").status_code == 200
    res = _act(world, d["id"], "submit", world.sales)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "resubmitted"
    tracker = open_tracker(world.db, KIND, d["id"])
    assert tracker.team_set_code == sla.approval.team_set
    assert len(trackers(world.db, KIND, d["id"])) == 2


# ------------------------------------------------------------------ purchasing stage


def test_a_purchasing_response_save_stops_the_response_clock_only(world, sla):
    d = _approved(world)
    res = world.api.as_(world.buyer).put(
        f"{NPA}/{d['id']}/purchasing-response", json={"purchasing_response": "Supplier quoting"}
    )
    assert res.status_code == 200, res.text
    tracker = open_tracker(world.db, KIND, d["id"])
    assert tracker.is_responded and not tracker.is_resolved
    assert str(tracker.responded_by) == world.buyer


def test_completing_resolves_purchasing_and_tells_the_applicant(world, sla):
    d = _approved(world)
    res = world.api.as_(world.buyer).put(
        f"{NPA}/{d['id']}/purchasing-response",
        json={"outcome": "link", "product_id": world.product.id, "purchasing_response": "Opened"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "completed"
    assert not trackers(world.db, KIND, d["id"], open_only=True)
    assert _to(world, d["id"], "new_product_application_completed") == {world.sales}


def test_purchasing_reject_resolves_the_purchasing_stage(world, sla):
    d = _approved(world)
    res = _act(world, d["id"], "purchasing-reject", world.buyer, reason="Supplier cannot make it")
    assert res.status_code == 200, res.text
    assert not trackers(world.db, KIND, d["id"], open_only=True)
    purchasing = [t for t in trackers(world.db, KIND, d["id"]) if t.team_set_code == sla.purchasing.team_set]
    assert len(purchasing) == 1 and purchasing[0].is_resolved


# ------------------------------------------------------------------ revise / cancel void, never resolve


def test_revise_voids_the_approval_stage_and_tells_only_its_assignee(world, sla):
    d = _submitted(world)
    res = _act(world, d["id"], "revise", world.sales, reason="Wrong finish")
    assert res.status_code == 200, res.text
    (row,) = trackers(world.db, KIND, d["id"])
    assert row.voided_at is not None and not row.is_resolved
    assert _to(world, d["id"], "new_product_application_withdrawn") == {sla.approval.tier1}


def test_cancel_voids_the_open_purchasing_stage(world, sla):
    d = _approved(world)
    res = _act(world, d["id"], "cancel", world.sales, reason="Customer dropped it")
    assert res.status_code == 200, res.text
    purchasing = [t for t in trackers(world.db, KIND, d["id"]) if t.team_set_code == sla.purchasing.team_set]
    assert len(purchasing) == 1
    assert purchasing[0].voided_at is not None and not purchasing[0].is_resolved


# ------------------------------------------------------------------ no stage row: nothing, as the SI


_BROADCASTS = (
    "new_product_application_submitted",
    "new_product_application_resubmitted",
    "new_product_application_approved",
    "new_product_application_withdrawn",
)


def test_without_npa_stage_rows_no_permission_holder_hears_a_move(world):
    """Owner 8 Nov 21:45 (Q2 b): like the SI, no active stage row starts no stage and sends no
    stage notice; the old broadcast to every .approve / .open_code holder is gone."""
    d = _submitted(world)
    assert not trackers(world.db, KIND, d["id"])
    assert _act(world, d["id"], "revise", world.sales, reason="Wrong finish").status_code == 200
    assert _act(world, d["id"], "submit", world.sales).status_code == 200
    assert _act(world, d["id"], "approve", world.manager).status_code == 200
    assert not [t for (_u, t, e) in world.sent if e == d["id"] and t in _BROADCASTS]
    assert not [t for (_u, t, _e) in world.sent if t == "form_sla"]


def test_an_inactive_stage_row_starts_nothing_and_tells_nobody(world, sla):
    sla.approval.config.is_active = False
    world.db.commit()
    d = _submitted(world)
    assert not trackers(world.db, KIND, d["id"])
    assert not [t for (_u, t, _e) in world.sent if t == "form_sla"]
    assert not _to(world, d["id"], "new_product_application_submitted")


# ------------------------------------------------------------------ handling lock gate


def _escalate(w, aid):
    tracker = open_tracker(w.db, KIND, aid)
    tracker.escalated_at = datetime.utcnow()
    w.db.commit()
    return tracker


def test_an_escalated_stage_with_the_lock_on_blocks_a_non_holder_approve(world, sla):
    settings_row(world.db, handling_lock_enabled_types=KIND)
    d = _submitted(world)
    _escalate(world, d["id"])
    res = _act(world, d["id"], "approve", world.manager)
    assert res.status_code == 403, res.text
    assert _get(world, d["id"])["status"] == "submitted"


def test_the_lock_holder_may_approve(world, sla):
    settings_row(world.db, handling_lock_enabled_types=KIND)
    d = _submitted(world)
    tracker = _escalate(world, d["id"])
    tracker.handled_by_id = world.manager
    world.db.commit()
    res = _act(world, d["id"], "approve", world.manager)
    assert res.status_code == 200, res.text


def test_an_escalated_purchasing_stage_blocks_a_non_holder_purchasing_save(world, sla):
    settings_row(world.db, handling_lock_enabled_types=KIND)
    d = _approved(world)
    _escalate(world, d["id"])
    res = world.api.as_(world.buyer).put(
        f"{NPA}/{d['id']}/purchasing-response", json={"purchasing_response": "Quoting"}
    )
    assert res.status_code == 403, res.text


def test_the_lock_flag_off_keeps_todays_behaviour(world, sla):
    settings_row(world.db, handling_lock_enabled_types="")
    d = _submitted(world)
    _escalate(world, d["id"])
    assert _act(world, d["id"], "approve", world.manager).status_code == 200


# ------------------------------------------------------------------ the SLA tab reads


def test_the_sla_tab_reads_npa_trackers_with_the_npa_view_slug(world, sla):
    d = _submitted(world)
    url = "/api/v1/sla-management/conversation-sla-tracking/by-source"
    res = world.api.as_(world.viewer).get(url, params={"source_entity_type": KIND, "source_entity_id": d["id"]})
    assert res.status_code == 200, res.text
    assert len(res.json()) == 1
    res = world.api.as_(world.stranger).get(url, params={"source_entity_type": KIND, "source_entity_id": d["id"]})
    assert res.status_code == 403


def test_the_npa_view_slug_does_not_read_stock_inquiry_trackers(world):
    url = "/api/v1/sla-management/conversation-sla-tracking/by-source"
    res = world.api.as_(world.viewer).get(
        url, params={"source_entity_type": "stock_inquiry", "source_entity_id": world.inquiry.id}
    )
    assert res.status_code == 403


# ------------------------------------------------------------------ the seed


def _load_migration():
    path = ROOT / "alembic" / "versions" / f"{MIGRATION}.py"
    spec = importlib.util.spec_from_file_location(MIGRATION, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_seed_revision_fits_and_alembic_has_one_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    module = _load_migration()
    assert module.revision == MIGRATION and len(module.revision) <= 32
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, heads
    assert MIGRATION in {r.revision for r in script.walk_revisions("base", heads[0])}


def test_the_seed_is_data_only():
    module = _load_migration()
    for statement in module.SEED:
        upper = " ".join(statement.split()).upper()
        assert upper.startswith("INSERT INTO FORM_SLA_CONFIGS"), statement
        assert "WHERE NOT EXISTS" in upper or "AND NOT EXISTS" in upper, statement


def _si_rows(db):
    """The SI's two stages as dev carries them (crew evidence 8 Nov), on a seeded chain."""
    chain = sla_chain(
        db,
        "stock_inquiry",
        [
            {"team_set_code": "project_sales", "start_event": "submit",
             "resolve_event": "project_sales_approve,project_sales_reject,voided"},
            {"team_set_code": "purchasing", "start_event": "project_sales_approve",
             "respond_event": "purchasing_respond"},
        ],
    )
    chain.stages[0].config.next_config_id = None
    chain.stages[0].config.notify_on_escalation = False
    db.commit()
    return chain


def _npa_rows(db):
    return db.execute(
        text(
            "SELECT stage_code, policy_id, agent_code, team_set_code, start_event, respond_event, "
            "resolve_event, is_active, notify_assignee, notify_on_escalation, next_config_id "
            "FROM form_sla_configs WHERE source_entity_type = :k ORDER BY team_set_code"
        ),
        {"k": KIND},
    ).mappings().all()


def test_the_seed_copies_the_si_teams_tiers_and_policy_into_npa_rows_once(world):
    chain = _si_rows(world.db)
    module = _load_migration()
    for _ in range(2):  # idempotent: the second run adds nothing
        for statement in module.SEED:
            world.db.execute(text(statement))
        world.db.commit()
    rows = _npa_rows(world.db)
    assert [r["team_set_code"] for r in rows] == ["project_sales", "purchasing"]
    approval, purchasing = rows
    si_approval, si_purchasing = chain.stages
    assert approval["agent_code"] == si_approval.config.agent_code
    assert str(approval["policy_id"]) == str(si_approval.config.policy_id)
    assert (approval["start_event"], approval["respond_event"], approval["resolve_event"]) == (
        "submitted,resubmitted", None, "approved,rejected",
    )
    assert approval["notify_on_escalation"] is False  # copied from the SI row
    assert str(purchasing["policy_id"]) == str(si_purchasing.config.policy_id)
    assert (purchasing["start_event"], purchasing["respond_event"], purchasing["resolve_event"]) == (
        "approved", "purchasing_respond", "completed,rejected",
    )
    assert all(r["next_config_id"] is None for r in rows)
    assert {r["stage_code"] for r in rows} == {"npa_approval", "npa_purchasing"}


def test_the_seed_is_a_no_op_without_si_rows(world):
    module = _load_migration()
    for statement in module.SEED:
        world.db.execute(text(statement))
    world.db.commit()
    assert _npa_rows(world.db) == []


def test_the_seed_leaves_an_existing_npa_row_alone(world, sla):
    _si_rows(world.db)
    module = _load_migration()
    for statement in module.SEED:
        world.db.execute(text(statement))
    world.db.commit()
    # `sla` already holds one NPA row per (random) team set; the seed adds the two SI team sets.
    rows = _npa_rows(world.db)
    assert len([r for r in rows if r["team_set_code"] in ("project_sales", "purchasing")]) == 2
    for statement in module.SEED:
        world.db.execute(text(statement))
    world.db.commit()
    assert len(_npa_rows(world.db)) == len(rows)


# ------------------------------------------------------------------ the SI's team notice (owner Q2 b)


def _si_agent_teams(w):
    """The SI's own team notice targets: agent `lead_time_enquiries`, team sets project_sales and
    purchasing, one member each (the same agent and team sets the seeded stage rows use)."""
    from app.models.access import AccessAgent, AgentTeam, Team, TeamMember

    from ._forms_chain_support import SORENTO, uid as _uid, user as _user

    db = w.db
    agent = db.query(AccessAgent).filter(AccessAgent.code == "lead_time_enquiries").first()
    if agent is None:
        agent = AccessAgent(id=_uid(), code="lead_time_enquiries", name="ZZT lead time enquiries")
        db.add(agent)
        db.flush()
    members = {}
    for code in ("project_sales", "purchasing"):
        team_id = _uid()
        db.add(Team(id=team_id, name=f"ZZT {code} {team_id[:6]}", company_id=SORENTO))
        db.add(AgentTeam(id=_uid(), agent_id=agent.id, code=code, team_id=team_id, tier=2, company_id=SORENTO))
        db.flush()
        member = _user(db, f"{code} team member")
        db.add(TeamMember(id=_uid(), team_id=team_id, user_id=member, sort_order=0))
        members[code] = member
    db.commit()
    return SimpleNamespace(**members)


def _team_notices(w, aid):
    from app.models.notification import Notification

    w.db.expire_all()
    rows = (
        w.db.query(Notification)
        .filter(Notification.source_entity_type == KIND, Notification.source_entity_id == aid)
        .all()
    )
    return {(r.user_id, r.event_type) for r in rows if r.type == "stock_inquiry_notification"}


def test_submit_sends_the_si_team_notice_to_the_project_sales_team(world):
    teams = _si_agent_teams(world)
    d = _submitted(world)
    assert _team_notices(world, d["id"]) == {(teams.project_sales, "new_product_application_submitted")}


def test_resubmit_sends_the_appealed_team_notice(world):
    teams = _si_agent_teams(world)
    d = _submitted(world)
    assert _act(world, d["id"], "reject", world.manager, reason="Add the finish").status_code == 200
    assert _act(world, d["id"], "submit", world.sales).status_code == 200
    assert (teams.project_sales, "new_product_application_resubmitted") in _team_notices(world, d["id"])


def test_approve_sends_the_si_team_notice_to_the_purchasing_team(world):
    teams = _si_agent_teams(world)
    d = _approved(world)
    notices = _team_notices(world, d["id"])
    assert (teams.purchasing, "new_product_application_approved") in notices
    assert (teams.project_sales, "new_product_application_approved") not in notices


def test_the_team_notice_goes_with_a_stage_row_too_like_the_si(world, sla):
    teams = _si_agent_teams(world)
    d = _submitted(world)
    assert (teams.project_sales, "new_product_application_submitted") in _team_notices(world, d["id"])
    assert _form_sla_to(world, sla.approval.tier1)


def test_the_team_notice_links_the_npa_not_a_stock_inquiry(world, monkeypatch):
    from app.services.procurement_service import StockInquiryService

    seen = []
    monkeypatch.setattr(
        StockInquiryService, "_notify_team_stock_inquiry", lambda self, **kw: seen.append(kw)
    )
    d = _submitted(world)
    (kw,) = seen
    assert kw["source_entity_type"] == KIND
    assert kw["inquiry_id"] == d["id"]
    assert kw["agent_code"] == "lead_time_enquiries" and kw["team_assignment_code"] == "project_sales"
    assert kw["view_url"].endswith(f"/procurement-management/new-product-applications/{d['id']}")
    assert kw["company_id"] == str(world.company_id)
    assert kw["button_label"] == "Open new product application"
    assert d["application_no"] in kw["title"]


def test_without_the_team_nobody_gets_a_team_notice(world):
    d = _submitted(world)
    assert _team_notices(world, d["id"]) == set()


# ------------------------------------------------------------------ the NPA's own company routes it (security B1)


def test_the_stage_routes_by_the_npas_own_company_not_its_contact(world, sla):
    """The SI takes its company from its contact (it has no company column); the NPA carries one,
    and its stage, team and lock eligibility must follow it, contact or none."""
    from app.models.access import AgentTeam, Team, TeamMember
    from app.models.new_product_application import NewProductApplication

    from ._forms_chain_support import uid as _uid, user as _user
    from ._sample_request_seed import second_company

    db = world.db
    other = second_company(db)
    member = _user(db, "other company approver")
    for tier in (1, 2):
        team_id = _uid()
        db.add(Team(id=team_id, name=f"ZZT other co t{tier} {team_id[:6]}", company_id=other))
        db.add(AgentTeam(id=_uid(), agent_id=sla.approval.config and _agent_id(db, sla), code=sla.approval.team_set,
                         team_id=team_id, tier=tier, company_id=other))
        db.flush()
        db.add(TeamMember(id=_uid(), team_id=team_id, user_id=member, sort_order=0))
    d = _draft(world)
    row = db.get(NewProductApplication, d["id"])
    row.company_id = other
    row.status = "submitted"
    db.commit()

    from app.services import new_product_application_service as svc

    svc.notify(db, row, "submitted")
    tracker = open_tracker(db, KIND, d["id"])
    assert str(tracker.company_id) == str(other)
    assert tracker.assigned_to_id == member


def _agent_id(db, sla):
    from app.models.access import AccessAgent

    return db.query(AccessAgent.id).filter(AccessAgent.code == sla.approval.config.agent_code).scalar()


# ------------------------------------------------------------------ tracker reads follow the NPA's own read (security S1, S2)


def _moved_to_other_company(w):
    """A submitted NPA with its stage open, then moved to another company: the caller's scope
    (Sorento) can no longer open the NPA, so it must not read its trackers either."""
    from app.models.new_product_application import NewProductApplication

    from ._sample_request_seed import second_company

    d = _submitted(w)
    tracker = open_tracker(w.db, KIND, d["id"])
    row = w.db.get(NewProductApplication, d["id"])
    row.company_id = second_company(w.db)
    w.db.commit()
    return d["id"], str(tracker.id)


def test_by_source_hides_another_companys_npa_trackers(world, sla):
    aid, _tid = _moved_to_other_company(world)
    res = world.api.as_(world.viewer).get(
        "/api/v1/sla-management/conversation-sla-tracking/by-source",
        params={"source_entity_type": KIND, "source_entity_id": aid},
    )
    assert res.status_code == 404, res.text


def test_one_tracker_read_hides_another_companys_npa(world, sla):
    _aid, tid = _moved_to_other_company(world)
    res = world.api.as_(world.viewer).get(f"/api/v1/sla-management/conversation-sla-tracking/{tid}")
    assert res.status_code == 404, res.text


def test_the_handling_tracker_read_needs_an_npa_reader_slug(world, sla):
    d = _submitted(world)
    url = "/api/v1/sla-management/form-sla-tracking"
    params = {"source_entity_type": KIND, "source_entity_id": d["id"]}
    assert world.api.as_(world.stranger).get(url, params=params).status_code == 403
    res = world.api.as_(world.viewer).get(url, params=params)
    assert res.status_code == 200, res.text
    assert len(res.json()["data"]) == 1


def test_the_handling_tracker_read_hides_another_companys_npa(world, sla):
    aid, _tid = _moved_to_other_company(world)
    res = world.api.as_(world.viewer).get(
        "/api/v1/sla-management/form-sla-tracking", params={"source_entity_type": KIND, "source_entity_id": aid}
    )
    assert res.status_code == 404, res.text


# ------------------------------------------------------------------ every stage move is gated (review B1)

#: (stage it runs in, method, path after the application id, body); a body may name the first line.
_GATED_MOVES = [
    ("approval", "post", "reject", {"reason": "No"}),
    ("approval", "post", "approve", None),
    ("purchasing", "post", "purchasing-reject", {"reason": "No"}),
    ("purchasing", "put", "purchasing-response", {"purchasing_response": "Quoting"}),
    ("purchasing", "post", "purchasing-response/reply", {"purchasing_response": "Quoting"}),
    ("purchasing", "put", "feedback", {"lead_time": "4 weeks"}),
    ("purchasing", "post", "new-code/link", {"product_id": "PRODUCT"}),
    ("purchasing", "post", "new-code/close", {"reason": "Not opening"}),
    ("purchasing", "post", "new-code/undo", None),
    ("purchasing", "post", "lines/LINE/link", {"product_id": "PRODUCT"}),
    ("purchasing", "post", "lines/LINE/close", {"reason": "Not opening"}),
    ("purchasing", "post", "lines/LINE/undo", None),
]


@pytest.mark.parametrize(
    "stage,method,path,body", _GATED_MOVES, ids=[f"{m} {p}" for _s, m, p, _b in _GATED_MOVES]
)
def test_every_approver_and_purchasing_move_is_gated_by_the_lock(world, sla, stage, method, path, body):
    settings_row(world.db, handling_lock_enabled_types=KIND)
    d = _submitted(world) if stage == "approval" else _approved(world)
    _escalate(world, d["id"])
    user = world.manager if stage == "approval" else world.buyer
    path = path.replace("LINE", d["lines"][0]["id"])
    if body and body.get("product_id") == "PRODUCT":
        body = {"product_id": world.product.id}
    call = getattr(world.api.as_(user), method)
    res = call(f"{NPA}/{d['id']}/{path}", json=body) if body is not None else call(f"{NPA}/{d['id']}/{path}")
    assert res.status_code == 403, (path, res.status_code, res.text)
    assert "escalated" in res.text or "handled by" in res.text
    assert _get(world, d["id"])["status"] == ("submitted" if stage == "approval" else "approved")


def test_the_applicants_own_moves_are_not_stage_work(world, sla):
    """Submit / revise / cancel are the applicant's, never blocked by a lock they cannot claim."""
    settings_row(world.db, handling_lock_enabled_types=KIND)
    d = _submitted(world)
    _escalate(world, d["id"])
    assert _act(world, d["id"], "revise", world.sales, reason="Wrong finish").status_code == 200


# ------------------------------------------------------------------ review S2 and S4


def test_the_assignment_whatsapp_link_opens_the_npa(world, sla, monkeypatch):
    """`_FE_RECORD_ROUTES` (must match MyPendingSLAWidget.ENTITY_ROUTES): an NPA task opens the
    NPA, never `/?ticket=<tracker id>`."""
    from app.services.notification_service import NotificationService

    seen = []
    monkeypatch.setattr(
        NotificationService, "create_with_channel_preferences", lambda self, **kw: seen.append(kw)
    )
    d = _submitted(world)
    (assigned,) = [kw for kw in seen if kw.get("type") == "form_sla"]
    form_url = assigned["data"]["whatsapp_context_vars"]["form_url"]
    assert form_url.endswith(f"/procurement-management/new-product-applications/{d['id']}")
    assert assigned["data"]["whatsapp_context_vars"]["entity_number"] == d["application_no"]


def test_revising_an_approved_npa_tells_the_purchasing_assignee(world, sla):
    d = _approved(world)
    res = _act(world, d["id"], "revise", world.sales, reason="Customer changed the size")
    assert res.status_code == 200, res.text
    purchasing = [t for t in trackers(world.db, KIND, d["id"]) if t.team_set_code == sla.purchasing.team_set]
    assert len(purchasing) == 1 and purchasing[0].voided_at is not None
    assert _to(world, d["id"], "new_product_application_withdrawn") == {sla.purchasing.tier1}


# ------------------------------------------------------------------ review S1: the seeded team-notice email row


def _template_row(db, layout_json):
    db.execute(
        text(
            "INSERT INTO email_templates (id, code, name, subject, body_html, is_active, layout_json, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'stock_inquiry_created', 'Stock inquiry team notice', '{{ heading }}', '', true, "
            "CAST(:l AS jsonb), now(), now())"
        ),
        {"l": layout_json},
    )
    db.commit()


def test_the_seeded_team_notice_row_names_the_npa_button(world):
    from app.services.email_template_service import EmailTemplateService

    module = _load_migration()
    db = world.db
    db.execute(text("DELETE FROM email_templates WHERE code = 'stock_inquiry_created'"))
    _template_row(db, module.SEEDED_LAYOUT)
    db.execute(text(module.TEMPLATE_UPDATE), {"new": module.LABELLED_LAYOUT, "old": module.SEEDED_LAYOUT})
    db.commit()
    ctx = {"heading": "H", "intro": "I", "view_url": "https://crm.example.com/x"}
    npa = EmailTemplateService(db).render_code("stock_inquiry_created", {**ctx, "button_label": "Open new product application"})
    si = EmailTemplateService(db).render_code("stock_inquiry_created", {**ctx, "button_label": "Open stock inquiry"})
    assert "Open new product application" in npa["body_html"]
    assert "Open stock inquiry" in si["body_html"]


def test_an_admin_edited_team_notice_row_is_left_alone(world):
    module = _load_migration()
    db = world.db
    db.execute(text("DELETE FROM email_templates WHERE code = 'stock_inquiry_created'"))
    edited = module._team_notice_layout("See the request")
    _template_row(db, edited)
    db.execute(text(module.TEMPLATE_UPDATE), {"new": module.LABELLED_LAYOUT, "old": module.SEEDED_LAYOUT})
    db.commit()
    layout = db.execute(
        text("SELECT layout_json FROM email_templates WHERE code = 'stock_inquiry_created'")
    ).scalar()
    assert layout["blocks"][3]["label"] == "See the request"


def test_upgrade_runs_the_seed_and_the_template_update(world, monkeypatch):
    """The wiring, not only the statements: `upgrade()` itself seeds the NPA rows from the SI's and
    relabels the seeded team-notice row (review nit 1)."""
    module = _load_migration()
    db = world.db
    _si_rows(db)
    db.execute(text("DELETE FROM email_templates WHERE code = 'stock_inquiry_created'"))
    _template_row(db, module.SEEDED_LAYOUT)

    class _Op:
        @staticmethod
        def execute(statement):
            db.execute(statement)

        @staticmethod
        def get_bind():
            return db

    monkeypatch.setattr(module, "op", _Op)
    module.upgrade()
    db.commit()
    assert [r["team_set_code"] for r in _npa_rows(db)] == ["project_sales", "purchasing"]
    layout = db.execute(
        text("SELECT layout_json FROM email_templates WHERE code = 'stock_inquiry_created'")
    ).scalar()
    assert layout["blocks"][3]["label"] == "{{ button_label or 'Open stock inquiry' }}"


def test_my_pending_names_the_npa_number(world, sla):
    """Crew pass 8 Nov: the assignee's My Pending row read "New product application" with no number;
    an SI / PR row shows its number."""
    from app.services.sla_service import ConversationSLATrackingService

    d = _submitted(world)
    tracker = open_tracker(world.db, KIND, d["id"])
    refs = ConversationSLATrackingService(world.db)._resolve_my_pending_references([tracker])
    assert refs[str(tracker.id)] == d["application_no"]


# ------------------------------------------------------------------ crew pass item 1: the SI's actors may act on the NPA


def _role_with(db, *slugs):
    from app.models.user import UserPermission, UserRole, UserRolePermission

    from ._forms_chain_support import uid as _uid

    role = UserRole(id=_uid(), slug=f"zzt-npasla-{_uid()[:8]}", name=f"ZZT npasla role {_uid()[:8]}")
    db.add(role)
    db.flush()
    for slug in slugs:
        perm = db.query(UserPermission).filter(UserPermission.slug == slug).first()
        if perm is None:
            perm = UserPermission(id=_uid(), slug=slug, name=slug)
            db.add(perm)
            db.flush()
        db.add(UserRolePermission(id=_uid(), role_id=role.id, permission_id=perm.id))
    db.flush()
    return role.id


def _role_slugs(db, role_id):
    return {
        r[0]
        for r in db.execute(
            text(
                "SELECT p.slug FROM user_role_permissions urp JOIN user_permissions p ON p.id = urp.permission_id "
                "WHERE urp.role_id = :r"
            ),
            {"r": role_id},
        )
    }


def test_the_si_stage_actors_get_the_npa_grants_once(world):
    db = world.db
    for slug in (VIEW, APPROVE, OPEN_CODE):
        _role_with(db, slug)  # make sure the NPA permission rows exist in this schema
    psm = _role_with(db, "procurement.stock_inquiries.view", "procurement.stock_inquiries.project_sales_approve")
    buyer = _role_with(db, "procurement.stock_inquiries.purchasing_reject")
    other = _role_with(db, "procurement.stock_inquiries.view")
    db.commit()
    module = _load_migration()
    for _ in range(2):  # idempotent
        for statement in module.GRANTS:
            db.execute(text(statement))
        db.commit()
    assert {VIEW, APPROVE} <= _role_slugs(db, psm) and OPEN_CODE not in _role_slugs(db, psm)
    assert {VIEW, OPEN_CODE} <= _role_slugs(db, buyer) and APPROVE not in _role_slugs(db, buyer)
    assert not _role_slugs(db, other) & {VIEW, APPROVE, OPEN_CODE}
    dupes = db.execute(
        text(
            "SELECT count(*) FROM (SELECT role_id, permission_id FROM user_role_permissions "
            "GROUP BY 1, 2 HAVING count(*) > 1) d"
        )
    ).scalar()
    assert dupes == 0


def test_the_grants_are_additive_inserts_only():
    module = _load_migration()
    for statement in module.GRANTS:
        upper = " ".join(statement.split()).upper()
        assert upper.startswith("INSERT INTO USER_ROLE_PERMISSIONS"), statement
        assert "NOT EXISTS" in upper


def _real_slugs(db):
    """The user's grants as the tables hold them (the harness swaps permission checks per caller)."""

    def slugs(self, user_id):
        return {
            r[0]
            for r in db.execute(
                text(
                    "SELECT p.slug FROM user_role_assignments a "
                    "JOIN user_role_permissions urp ON urp.role_id = a.role_id "
                    "JOIN user_permissions p ON p.id = urp.permission_id WHERE a.user_id = :u"
                ),
                {"u": user_id},
            )
        }

    return slugs


def test_after_the_migration_the_si_stage_actors_open_and_work_the_npa(world):
    """Owner ruling (a): the Project Sales Manager (SI project_sales_approve) and the purchasing
    member (SI purchasing_reject) open the NPA and do their stage's move once the migration ran."""
    from app.services.user_service import UserPermissionService

    from ._sample_request_seed import MARKER, make_user
    from .test_new_product_application import _grant

    db = world.db
    for slug in (VIEW, APPROVE, OPEN_CODE):
        _role_with(db, slug)
    psm = make_user(db, f"{MARKER} project sales manager")
    buyer = make_user(db, f"{MARKER} purchasing product")
    _grant(db, psm, {"procurement.stock_inquiries.view", "procurement.stock_inquiries.project_sales_approve"}, world.company_id)
    _grant(db, buyer, {"procurement.stock_inquiries.purchasing_reject"}, world.company_id)
    db.commit()
    # Restored here, not by `monkeypatch`: its teardown runs AFTER the world's, and would put the
    # harness's per-test fake back on the class for every later test in the process.
    harness_slugs = UserPermissionService.get_user_permission_slugs
    UserPermissionService.get_user_permission_slugs = _real_slugs(db)
    try:
        d = _submitted(world)
        assert world.api.as_(psm).get(f"{NPA}/{d['id']}").status_code == 403
        assert world.api.as_(buyer).get(f"{NPA}/{d['id']}").status_code == 403

        module = _load_migration()
        for statement in module.GRANTS:
            db.execute(text(statement))
        db.commit()

        assert world.api.as_(psm).get(f"{NPA}/{d['id']}").status_code == 200
        assert _act(world, d["id"], "approve", psm).status_code == 200
        assert world.api.as_(buyer).get(f"{NPA}/{d['id']}").status_code == 200
        res = world.api.as_(buyer).put(
            f"{NPA}/{d['id']}/purchasing-response", json={"purchasing_response": "Quoting"}
        )
        assert res.status_code == 200, res.text
    finally:
        UserPermissionService.get_user_permission_slugs = harness_slugs


def test_the_downgrade_removes_only_the_grants_it_added(world, monkeypatch):
    db = world.db
    for slug in (VIEW, APPROVE, OPEN_CODE):
        _role_with(db, slug)
    # A role an admin already gave NPA view by hand keeps it after the downgrade.
    by_hand = _role_with(db, "procurement.stock_inquiries.project_sales_approve", VIEW)
    fresh = _role_with(db, "procurement.stock_inquiries.purchasing_reject")
    db.commit()
    module = _load_migration()
    for _ in range(2):
        for statement in module.GRANTS:
            db.execute(text(statement))
    db.commit()
    assert {VIEW, APPROVE} <= _role_slugs(db, by_hand)
    assert {VIEW, OPEN_CODE} <= _role_slugs(db, fresh)
    db.execute(text(module.UNGRANT))
    db.commit()
    assert VIEW in _role_slugs(db, by_hand) and APPROVE not in _role_slugs(db, by_hand)
    assert not _role_slugs(db, fresh) & {VIEW, OPEN_CODE}


# ------------------------------------------------------------------ owner hand test 9 Nov: no product rows, SI list columns


def test_a_standalone_npa_submits_without_product_rows_when_remark_says_what_is_wanted(world):
    d = world.api.as_(world.sales).post(NPA, json={"remark": "Kitchen sink, nanograin finish, 600x400"}).json()
    res = _act(world, d["id"], "submit", world.sales)
    assert res.status_code == 200, res.text


def test_a_standalone_npa_with_no_rows_and_no_remark_asks_for_the_remark(world):
    d = world.api.as_(world.sales).post(NPA, json={}).json()
    res = _act(world, d["id"], "submit", world.sales)
    assert res.status_code == 422
    assert "REMARK" in res.text


def test_the_list_carries_the_si_columns_salesperson_assigned_to_handled_by(world, sla):
    d = _submitted(world)
    tracker = open_tracker(world.db, KIND, d["id"])
    tracker.handled_by_id = world.manager
    world.db.commit()
    res = world.api.as_(world.admin).get(NPA, params={"limit": 100})
    assert res.status_code == 200, res.text
    (row,) = [r for r in res.json()["items"] if r["id"] == d["id"]]
    assert row["salesperson"] == row["applicant_name"] and row["salesperson"]
    assert row["assigned_to_name"]  # the approval stage's tier-1 member
    assert row["handled_by_name"]
    for gone in ("first_line", "lines_total", "lines_done"):
        assert gone not in row


@pytest.mark.parametrize("sort", ["assigned_to_name", "handled_by_name", "salesperson"])
def test_the_new_list_columns_sort(world, sla, sort):
    _submitted(world)
    _draft(world)
    for direction in ("asc", "desc"):
        res = world.api.as_(world.admin).get(NPA, params={"sort": sort, "dir": direction})
        assert res.status_code == 200, res.text


# ------------------------------------------------------------------ owner hand test 9 Nov: Rev and Print Count, the SI way


def _row(w, aid, user=None):
    res = w.api.as_(user or w.admin).get(NPA, params={"limit": 100})
    assert res.status_code == 200, res.text
    (row,) = [r for r in res.json()["items"] if r["id"] == aid]
    return row


def test_each_revise_counts_one_revision_and_the_list_shows_it(world):
    d = _submitted(world)
    assert _row(world, d["id"])["revision_no"] == 0
    assert _act(world, d["id"], "revise", world.sales, reason="Wrong finish").status_code == 200
    assert _act(world, d["id"], "submit", world.sales).status_code == 200
    assert _act(world, d["id"], "revise", world.sales, reason="Wrong size").status_code == 200
    assert _row(world, d["id"])["revision_no"] == 2
    assert _get(world, d["id"])["revision_no"] == 2


def test_export_xlsx_queues_a_my_downloads_row_and_print_count_counts_it(world, monkeypatch):
    import app.services.queue_service as queue_service

    queued = []
    monkeypatch.setattr(queue_service, "enqueue_job", lambda fn, *a, **kw: queued.append((fn.__name__, a, kw)))
    d = _submitted(world)
    for _ in range(2):
        res = world.api.as_(world.viewer).post(f"{NPA}/{d['id']}/export/xlsx")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["kind"] == "new_product_application_xlsx" and body["status"] == "pending"
    assert [q[0] for q in queued] == ["generate_new_product_application_xlsx"] * 2
    assert queued[0][1][1] == d["id"]
    assert _row(world, d["id"], world.viewer)["print_count"] == 2
    assert _row(world, d["id"], world.admin)["print_count"] == 0  # the viewer's own, as the SI


def test_export_xlsx_is_refused_to_a_caller_who_cannot_view(world, monkeypatch):
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **kw: None)
    d = _submitted(world)
    assert world.api.as_(world.stranger).post(f"{NPA}/{d['id']}/export/xlsx").status_code in (403, 404)


def test_the_print_count_column_sorts(world, monkeypatch):
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **kw: None)
    first, second = _submitted(world), _submitted(world)
    world.api.as_(world.admin).post(f"{NPA}/{second['id']}/export/xlsx")
    res = world.api.as_(world.admin).get(NPA, params={"sort": "print_count", "dir": "desc", "limit": 100})
    ids = [r["id"] for r in res.json()["items"]]
    assert ids.index(second["id"]) < ids.index(first["id"])


def test_the_worker_stores_the_workbook_and_marks_the_download_ready(world, monkeypatch):
    import app.services.queue_service as queue_service
    import app.tasks.export_tasks as export_tasks
    from app.models.download import UserDownload

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **kw: None)
    d = _submitted(world)
    did = world.api.as_(world.viewer).post(f"{NPA}/{d['id']}/export/xlsx").json()["id"]

    stored = {}

    class _Backend:
        def upload_file(self, *, file_content, file_path, content_type):
            stored.update(key=file_path, size=len(file_content), type=content_type)
            return file_path, "signed"

    class _Session:
        """The test's session, never closed by the task."""

        def __getattr__(self, name):
            return getattr(world.db, name)

        def close(self):
            pass

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _Session())
    monkeypatch.setattr(export_tasks, "set_company_scope", lambda db, scope: None)
    monkeypatch.setattr(export_tasks, "get_backend", lambda provider: _Backend())
    out = export_tasks.generate_new_product_application_xlsx(did, d["id"], world.viewer)
    assert out["status"] == "ready", out
    row = world.db.get(UserDownload, did)
    world.db.refresh(row)
    assert row.status == "ready" and row.storage_key == stored["key"]
    assert stored["key"].startswith(f"exports/new-product-application-xlsx/{did}/") and stored["size"] > 0
