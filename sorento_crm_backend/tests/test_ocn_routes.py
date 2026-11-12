"""OCN-ORDER-CHANGE-NOTICE red tests: the HTTP surface.

UAC B9 (revision fence), C3 (lockstep lists), C4 (SLA tab), D2-D4 (permissions, own scope,
company scope, handling lock), F1 (project panel), F2 (list filters and the limit cap).
Routes: `/api/v1/procurement/order-change-notices` and
`/api/v1/project-sales/projects/{project_id}/order-change-notices`.

Postgres only, real RBAC through real roles, every row seeded (tests/_ocn_support.py).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ._forms_chain_support import (  # noqa: F401
    SORENTO,
    grant,
    open_tracker,
    revision_config,
    settings_row,
    trackers,
    user,
    world,
)
from ._ocn_support import (  # noqa: F401  (fixtures)
    APPROVE,
    EDIT,
    KIND,
    OCN,
    PROJECT_PANEL,
    VIEW,
    VIEW_OWN,
    approved,
    create,
    get,
    load,
    move,
    ocn,
    ok,
    pending,
    rows_of,
    sla,
    submitted,
    uid,
)

BACKEND = Path(__file__).resolve().parents[1]
ROUTER = BACKEND / "app" / "api" / "v1" / "procurement" / "order_change_notices.py"


def _ids(res) -> list[str]:
    assert res.status_code == 200, res.text
    return [r["id"] for r in rows_of(res.json())]


# ================================================================== B9 revision fence

#: (path suffix, body, state the OCN must be in for the move to be legal)
_MOVES = [
    ("submit", None, "draft"),
    ("send-for-approval", None, "submitted"),
    ("reject-submitted", {"reason": "Add the PO copy"}, "submitted"),
    ("approval-decision", {"action": "approved", "comments": None}, "pending"),
    ("approval-decision", {"action": "rejected", "comments": "Wrong quantity"}, "pending"),
    ("done", {"cs_comment": None}, "approved"),
    ("void", {"reason": "Customer withdrew it"}, "submitted"),
    ("revise", {"reason": "Customer changed the dates"}, "approved"),
]


def _in_state(o, state):
    return {"draft": create, "submitted": submitted, "pending": pending, "approved": approved}[state](o)


def _actor_for(o, action):
    return {
        "submit": o.raiser,
        "send-for-approval": o.sales_admin,
        "reject-submitted": o.sales_admin,
        "approval-decision": o.manager,
        "done": o.cs,
        "void": o.sales_admin,
        "revise": o.sales_admin,
    }[action]


@pytest.mark.parametrize("action,body,state", _MOVES, ids=[f"{m[0]}-{m[2]}-{i}" for i, m in enumerate(_MOVES)])
def test_b9_a_stale_revision_number_is_refused_409_and_nothing_moves(ocn, action, body, state):
    revision_config(ocn.db, KIND, allowed_statuses=["approved"])
    d = _in_state(ocn, state)
    row = load(ocn, d["id"])
    row.revision_no = 1
    ocn.db.commit()
    before = (row.status, row.approval_status)

    res = move(ocn, d["id"], action, _actor_for(ocn, action), json=body, headers={"X-Revision-No": "0"})
    assert res.status_code == 409, res.text
    row = load(ocn, d["id"])
    assert (row.status, row.approval_status) == before


def test_b9_the_current_revision_number_passes_the_fence(ocn):
    revision_config(ocn.db, KIND, allowed_statuses=["approved"])
    d = create(ocn)
    res = move(ocn, d["id"], "submit", ocn.raiser, headers={"X-Revision-No": "0"})
    assert res.status_code == 200, res.text


def test_b9_every_move_route_mounts_the_ocn_fence():
    """Static: each move route in the router carries require_current_revision(order_change_notice)."""
    source = ROUTER.read_text()
    for suffix in ("submit", "send-for-approval", "reject-submitted", "approval-decision", "done",
                   "void", "revise"):
        decorator = re.search(
            r"@router\.post\(\s*\"/\{ocn_id\}/" + re.escape(suffix) + r"\"(?P<args>.*?)\)\s*\n\s*def ",
            source,
            re.DOTALL,
        )
        assert decorator, f"no POST /{{ocn_id}}/{suffix} route"
        assert 'require_current_revision("order_change_notice", "ocn_id")' in decorator.group("args"), suffix


def test_b9_the_fence_knows_the_ocn_target():
    from app.services import revision_fence

    assert "order_change_notice" in revision_fence._TARGETS
    assert revision_fence._LABELS["order_change_notice"] == "order change notice"


# ================================================================== C3 / C4 SLA


def test_c3_order_change_notice_is_in_every_lockstep_list():
    from app.api.v1.audit.audit_logs import _PER_RECORD_VIEW_PERMISSION
    from app.api.v1.sla.sla_tracking import SOURCE_TYPE_READERS
    from app.schemas.sla import _FORM_SLA_TYPES
    from app.services import form_sla_service as f

    assert KIND in f.FORM_SLA_TYPES
    assert KIND in _FORM_SLA_TYPES
    assert f._ENTITY_NUMBER_SOURCE[KIND] == ("projects.order_change_notices", "ocn_number", True)
    assert f._form_detail_link(KIND, "abc") == "/procurement-management/order-change-notices/abc"
    assert VIEW in SOURCE_TYPE_READERS[KIND]
    assert _PER_RECORD_VIEW_PERMISSION[KIND] == VIEW


def test_c3_the_approval_stage_and_default_approver_are_known_for_the_ocn():
    from types import SimpleNamespace

    from app.services.form_sla_service import FormSLAOrchestrator

    assert FormSLAOrchestrator._is_approval_stage(
        SimpleNamespace(source_entity_type=KIND, resolve_event="approved,approval_rejected,voided")
    )
    assert not FormSLAOrchestrator._is_approval_stage(
        SimpleNamespace(source_entity_type=KIND, resolve_event="resolved,voided")
    )


def test_c4_the_sla_tab_lists_this_ocns_stages_only(ocn, sla):
    first = submitted(ocn)
    second = submitted(ocn)
    url = "/api/v1/sla-management/conversation-sla-tracking/by-source"
    res = ocn.as_(ocn.viewer).get(url, params={"source_entity_type": KIND, "source_entity_id": first["id"]})
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 1
    assert all(str(r.get("source_entity_id")) == first["id"] for r in rows)
    assert second["id"] not in res.text
    res = ocn.as_(ocn.stranger).get(url, params={"source_entity_type": KIND, "source_entity_id": first["id"]})
    assert res.status_code == 403, res.text


# ================================================================== D2 view / view_own


def test_d2_without_view_or_view_own_list_and_detail_are_403(ocn):
    d = create(ocn)
    assert ocn.as_(ocn.stranger).get(OCN).status_code == 403
    assert get(ocn, d["id"], ocn.stranger).status_code == 403


def test_d2_view_reads_every_ocn(ocn):
    mine = create(ocn, user_id=ocn.raiser)
    theirs = create(ocn, user_id=ocn.sales_admin)
    assert {mine["id"], theirs["id"]} <= set(_ids(ocn.as_(ocn.viewer).get(OCN)))
    assert get(ocn, theirs["id"], ocn.viewer).status_code == 200


def test_d2_view_own_lists_raised_and_named_ocns_only(ocn):
    raised = create(ocn, user_id=ocn.own, sales_in_charge_user_id=None, cs_in_charge_user_id=None)
    as_sales = create(ocn, user_id=ocn.raiser, sales_in_charge_user_id=ocn.own, cs_in_charge_user_id=None)
    as_cs = create(ocn, user_id=ocn.raiser, sales_in_charge_user_id=None, cs_in_charge_user_id=ocn.own)
    other = create(ocn, user_id=ocn.raiser, sales_in_charge_user_id=ocn.sales_admin, cs_in_charge_user_id=ocn.cs)
    seen = set(_ids(ocn.as_(ocn.own).get(OCN)))
    assert {raised["id"], as_sales["id"], as_cs["id"]} <= seen
    assert other["id"] not in seen
    assert get(ocn, as_cs["id"], ocn.own).status_code == 200
    assert get(ocn, other["id"], ocn.own).status_code == 404


# ================================================================== D3 move permissions + handling lock


def test_d3_approve_and_reject_need_the_approve_permission(ocn):
    d = pending(ocn)
    for body in ({"action": "approved", "comments": None}, {"action": "rejected", "comments": "No"}):
        res = move(ocn, d["id"], "approval-decision", ocn.sales_admin, json=body)
        assert res.status_code == 403, res.text
    assert load(ocn, d["id"]).approval_status == "pending"


def test_d3_send_for_approval_and_send_back_need_edit(ocn):
    d = submitted(ocn)
    assert move(ocn, d["id"], "send-for-approval", ocn.manager).status_code == 403
    res = move(ocn, d["id"], "reject-submitted", ocn.manager, json={"reason": "No"})
    assert res.status_code == 403, res.text
    row = load(ocn, d["id"])
    assert (row.status, row.approval_status in (None, "", "draft")) == ("submitted", True)


def test_d3_done_needs_edit(ocn):
    d = approved(ocn)
    res = move(ocn, d["id"], "done", ocn.manager, json={"cs_comment": None})
    assert res.status_code == 403, res.text
    assert load(ocn, d["id"]).status == "approved"


def _escalate(o, ocn_id):
    tracker = open_tracker(o.db, KIND, ocn_id)
    tracker.escalated_at = datetime.utcnow()
    o.db.commit()
    return tracker


def test_d3_the_handling_lock_blocks_a_non_holder_approval(ocn, sla):
    settings_row(ocn.db, handling_lock_enabled_types=KIND)
    d = pending(ocn)
    _escalate(ocn, d["id"])
    res = move(ocn, d["id"], "approval-decision", ocn.manager, json={"action": "approved", "comments": None})
    assert res.status_code == 403, res.text
    assert load(ocn, d["id"]).approval_status == "pending"


def test_d3_the_handling_lock_blocks_a_non_holder_send_for_approval(ocn, sla):
    settings_row(ocn.db, handling_lock_enabled_types=KIND)
    d = submitted(ocn)
    _escalate(ocn, d["id"])
    res = move(ocn, d["id"], "send-for-approval", ocn.sales_admin)
    assert res.status_code == 403, res.text


def test_d3_the_lock_holder_may_act(ocn, sla):
    settings_row(ocn.db, handling_lock_enabled_types=KIND)
    d = pending(ocn)
    tracker = _escalate(ocn, d["id"])
    tracker.handled_by_id = ocn.manager
    ocn.db.commit()
    res = move(ocn, d["id"], "approval-decision", ocn.manager, json={"action": "approved", "comments": None})
    assert res.status_code == 200, res.text


# ================================================================== D4 company scope


def _other_company_ocn(o):
    from app.models.project_so import OrderChangeNotice

    from ._sample_request_seed import second_company

    from app.models.base import company_scope

    other = second_company(o.db)
    with company_scope(o.db, None):  # the all-companies principal writes company Y's row
        row = OrderChangeNotice(
            id=uid(), company_id=other, ocn_number="OCN26-0001", status="submitted", source="crm",
            customer_name="Customer B", created_by=o.raiser,
        )
        o.db.add(row)
        o.db.commit()
    return row


def test_d4_another_companys_ocn_is_never_listed_opened_or_moved(ocn):
    row = _other_company_ocn(ocn)
    assert row.id not in set(_ids(ocn.as_(ocn.viewer).get(OCN)))
    assert get(ocn, row.id, ocn.viewer).status_code == 404
    assert move(ocn, row.id, "send-for-approval", ocn.sales_admin).status_code == 404
    res = move(ocn, row.id, "void", ocn.sales_admin, json={"reason": "Not ours"})
    assert res.status_code == 404, res.text
    res = ocn.as_(ocn.sales_admin).put(f"{OCN}/{row.id}", json={"description": "x"})
    assert res.status_code == 404, res.text
    from app.models.base import company_scope

    with company_scope(ocn.db, None):
        assert load(ocn, row.id).status == "submitted"


# ================================================================== F1 project panel


def _age(o, ocn_id, days_ago):
    row = load(o, ocn_id)
    when = datetime(2026, 11, 1) - timedelta(days=days_ago)
    row.created_at = when
    row.ocn_date = when.date()
    o.db.commit()


def test_f1_the_project_panel_lists_that_projects_ocns_newest_first(ocn):
    older = create(ocn, project_id=ocn.project.id)
    newer = create(ocn, project_id=ocn.project.id)
    elsewhere = create(ocn, project_id=ocn.other_project.id)
    _age(ocn, older["id"], 10)
    _age(ocn, newer["id"], 1)
    _age(ocn, elsewhere["id"], 0)

    res = ocn.as_(ocn.viewer).get(PROJECT_PANEL.format(project_id=ocn.project.id))
    assert res.status_code == 200, res.text
    body = res.json()
    assert [r["id"] for r in body["data"]] == [newer["id"], older["id"]]
    assert body["pagination"]["total"] == 2
    assert body["empty"] is False
    first = body["data"][0]
    assert first["ocn_number"] and first["status"] == "draft"


def test_f1_an_empty_project_answers_the_empty_envelope(ocn):
    res = ocn.as_(ocn.viewer).get(PROJECT_PANEL.format(project_id=ocn.project.id))
    assert res.status_code == 200, res.text
    assert res.json()["data"] == [] and res.json()["empty"] is True


def test_f1_the_project_panel_needs_ocn_view(ocn):
    create(ocn, project_id=ocn.project.id)
    res = ocn.as_(ocn.stranger).get(PROJECT_PANEL.format(project_id=ocn.project.id))
    assert res.status_code == 403, res.text


# ================================================================== F2 filters and limit


def _set(o, ocn_id, **cols):
    row = load(o, ocn_id)
    for key, value in cols.items():
        setattr(row, key, value)
    o.db.commit()


def test_f2_status_filter_is_multi_select(ocn):
    a, b, c = create(ocn), create(ocn), create(ocn)
    _set(ocn, b["id"], status="submitted")
    _set(ocn, c["id"], status="approved", approval_status="approved")
    got = set(_ids(ocn.as_(ocn.viewer).get(OCN, params={"status": "draft,approved"})))
    assert got == {a["id"], c["id"]}
    got = set(_ids(ocn.as_(ocn.viewer).get(OCN, params=[("status", "draft"), ("status", "submitted")])))
    assert got == {a["id"], b["id"]}


def test_f2_change_type_filter_is_multi_select(ocn):
    delay = create(ocn, change_type_id=ocn.types.delay.id)
    advance = create(ocn, change_type_id=ocn.types.advance.id)
    cancel = create(ocn, change_type_id=ocn.types.cancellation.id)
    got = set(_ids(ocn.as_(ocn.viewer).get(
        OCN, params={"change_type_id": f"{ocn.types.delay.id},{ocn.types.cancellation.id}"})))
    assert got == {delay["id"], cancel["id"]}
    assert advance["id"] not in got


def test_f2_risk_filter_is_multi_select_and_combines_with_status(ocn):
    low = create(ocn, change_type_id=ocn.types.delay.id)
    high = create(ocn, change_type_id=ocn.types.exchange.id)
    highest = create(ocn, change_type_id=ocn.types.cancellation.id)
    got = set(_ids(ocn.as_(ocn.viewer).get(OCN, params={"risk_level": "High,Highest"})))
    assert got == {high["id"], highest["id"]}
    _set(ocn, high["id"], status="submitted")
    got = set(_ids(ocn.as_(ocn.viewer).get(OCN, params={"risk_level": "High,Highest", "status": "draft"})))
    assert got == {highest["id"]}
    assert low["id"] not in got


def test_f2_the_page_limit_is_capped(ocn):
    res = ocn.as_(ocn.viewer).get(OCN, params={"limit": 1001})
    assert res.status_code == 422, res.text


def test_f2_the_router_file_exists_where_the_wiring_test_reads_it():
    assert ROUTER.exists(), ROUTER
