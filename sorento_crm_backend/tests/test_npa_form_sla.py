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
