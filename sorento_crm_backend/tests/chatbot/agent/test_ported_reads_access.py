"""AGENTIC-UNIFY PR 4, slice 1 (red): who is offered the twelve ported reads, and who is refused (AC-1, AC-2, AC-3).

Real role and permission rows on the blank Postgres schema: `check_user_has_permission` passes every admin
and a patched check hid a real leak before, so nothing here patches it. Every user is a non-admin holding
exactly the slugs a test names, through one private role. A fake `call` records whether the route was reached.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.agent import tools as agent_tools
from app.services.chatbot.agent.access import permitted_tools
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_user
from tests.chatbot.agent._ported_reads_support import (
    AC1,
    CAPABILITIES,
    OWN_ROWS,
    PORTED,
    UNRELATED,
    Recorder,
    dispatch,
    make_ctx,
    panel_turn,
    ported_reads,
    tool,
)


@pytest.fixture(scope="module")
def db():
    """One blank schema for the module; every test seeds its own uniquely named users."""
    with blank_session() as session:
        yield session


def user_with(db, *slugs) -> str:
    return seed_user(db, contact_pk=None, slugs=slugs)


# ------------------------------------------------------------------ AC-1: the slug opens it, nothing else does


@pytest.mark.parametrize("name,slug,own", AC1, ids=[r[0] for r in AC1])
def test_AC1_a_user_holding_the_slug_is_offered_the_tool_and_may_call_it(db, name, slug, own):
    ctx = make_ctx(user_with(db, slug))
    row = tool(name)
    assert agent_tools.user_may_use(db, ctx, row) is True
    assert name in [t.name for t in permitted_tools(db, ctx)]
    rec = Recorder()
    out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "ok", (out.status, out.message)
    assert [c[0] for c in rec.calls] == [name]


@pytest.mark.parametrize("name,slug,own", AC1, ids=[r[0] for r in AC1])
def test_AC1_a_user_without_the_slug_is_not_offered_the_tool_and_is_refused_at_dispatch(db, name, slug, own):
    ctx = make_ctx(user_with(db, UNRELATED))
    row = tool(name)
    assert agent_tools.user_may_use(db, ctx, row) is False
    assert name not in [t.name for t in permitted_tools(db, ctx)]
    rec = Recorder()
    out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert "outside this user's access" in out.message
    assert rec.calls == [], "the route was reached for a user without the slug"


@pytest.mark.parametrize("name,slug,own", AC1, ids=[r[0] for r in AC1])
def test_AC1_a_user_holding_no_role_at_all_is_refused(db, name, slug, own):
    ctx = make_ctx(user_with(db))
    rec = Recorder()
    out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == []


@pytest.mark.parametrize("name,slug,own", AC1, ids=[r[0] for r in AC1])
def test_AC1_the_slug_is_checked_at_call_time_not_only_at_exposure(db, name, slug, own):
    """Offered while the role holds the slug, refused once it is taken away."""
    user_id = user_with(db, slug)
    ctx = make_ctx(user_id)
    assert name in [t.name for t in permitted_tools(db, ctx)]
    from app.models.user import UserRoleAssignment, UserRolePermission

    role_ids = [a.role_id for a in db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id)]
    assert role_ids
    db.query(UserRolePermission).filter(UserRolePermission.role_id.in_(role_ids)).delete(synchronize_session=False)
    db.flush()
    from app.services.user_service import invalidate_rbac_cache

    invalidate_rbac_cache(user_id)
    rec = Recorder()
    out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == []


def test_AC1_capabilities_summary_is_open_to_any_signed_in_staff_user(db):
    ctx = make_ctx(user_with(db))
    row = tool(CAPABILITIES)
    assert agent_tools.user_may_use(db, ctx, row) is True
    assert CAPABILITIES in [t.name for t in permitted_tools(db, ctx)]
    rec = Recorder()
    out = dispatch(db, ctx, CAPABILITIES, rec=rec)
    assert out.status == "ok", (out.status, out.message)
    assert [c[0] for c in rec.calls] == [CAPABILITIES]


def test_AC1_the_slugs_are_the_tables_not_the_orders_one_by_accident(db):
    """A holder of only the complaints slug does not open the projects, SLA, order or find reads."""
    ctx = make_ctx(user_with(db, "complaint_management.complaints.view"))
    offered = {t.name for t in permitted_tools(db, ctx)}
    assert {"crm_complaints_list", "crm_complaint_analytics"} <= offered
    for name, _slug, _own in AC1:
        if name not in ("crm_complaints_list", "crm_complaint_analytics"):
            assert name not in offered, f"{name} was offered to a complaints-only user"


def test_AC1_ported_reads_is_the_ac1_set_less_find_and_capabilities():
    assert ported_reads() == frozenset(r[0] for r in PORTED)
    assert "crm_find" not in ported_reads() and CAPABILITIES not in ported_reads()


def test_AC1_every_ported_read_is_a_non_render_tool_and_find_alone_renders():
    for name, _slug, _own in AC1:
        assert tool(name).render is (name == "crm_find"), name
    assert tool(CAPABILITIES).render is False


# ------------------------------------------------------------------ AC-2: view_own counts on a panel turn only


@pytest.mark.parametrize("name,slug,own", OWN_ROWS, ids=[r[0] for r in OWN_ROWS])
def test_AC2_view_own_alone_is_offered_and_called_on_a_panel_turn(db, name, slug, own):
    user_id = user_with(db, own)
    ctx = make_ctx(user_id)
    rec = Recorder()
    with panel_turn(user_id):
        assert agent_tools.user_may_use(db, ctx, tool(name)) is True
        assert name in [t.name for t in permitted_tools(db, ctx)]
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "ok", (out.status, out.message)
    assert [c[0] for c in rec.calls] == [name]


@pytest.mark.parametrize("name,slug,own", OWN_ROWS, ids=[r[0] for r in OWN_ROWS])
def test_AC2_view_own_alone_is_not_offered_and_is_refused_on_a_console_or_whatsapp_turn(db, name, slug, own):
    """No staff principal: the read runs as the shared key's user, whom the route does not narrow to this one."""
    ctx = make_ctx(user_with(db, own))
    assert agent_tools.user_may_use(db, ctx, tool(name)) is False
    assert name not in [t.name for t in permitted_tools(db, ctx)]
    rec = Recorder()
    out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == []


@pytest.mark.parametrize("name,slug,own", OWN_ROWS, ids=[r[0] for r in OWN_ROWS])
def test_AC2_a_panel_user_with_neither_slug_is_still_refused(db, name, slug, own):
    user_id = user_with(db, UNRELATED)
    ctx = make_ctx(user_id)
    rec = Recorder()
    with panel_turn(user_id):
        assert agent_tools.user_may_use(db, ctx, tool(name)) is False
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == []


@pytest.mark.parametrize("name,slug,own", OWN_ROWS, ids=[r[0] for r in OWN_ROWS])
def test_AC2_the_full_slug_works_on_both_kinds_of_turn(db, name, slug, own):
    user_id = user_with(db, slug)
    ctx = make_ctx(user_id)
    with panel_turn(user_id):
        assert dispatch(db, ctx, name, rec=Recorder()).status == "ok"
    assert dispatch(db, ctx, name, rec=Recorder()).status == "ok"


@pytest.mark.parametrize(
    "name,other",
    [
        ("crm_complaint_analytics", "complaint_management.complaints.view_own"),
        ("crm_project_forecast", "projects.projects.view_own"),
    ],
)
def test_AC2_a_read_with_no_own_slug_is_closed_to_view_own_on_the_panel_too(db, name, other):
    """Forecast and complaint analytics have no own scope in the route: a `.view_own` holder gets neither."""
    user_id = user_with(db, other)
    ctx = make_ctx(user_id)
    rec = Recorder()
    with panel_turn(user_id):
        assert agent_tools.user_may_use(db, ctx, tool(name)) is False
        assert name not in [t.name for t in permitted_tools(db, ctx)]
        on_panel = dispatch(db, ctx, name, rec=rec)
    off_panel = dispatch(db, ctx, name, rec=rec)
    assert on_panel.status == "denied", (on_panel.status, on_panel.message)
    assert off_panel.status == "denied", (off_panel.status, off_panel.message)
    assert rec.calls == []


def test_AC2_own_permission_is_declared_on_exactly_the_four_reads_that_take_one():
    declared = {n: getattr(tool(n), "own_permission", "MISSING") for n, _s, _o in AC1}
    assert declared == {
        "crm_complaints_list": "complaint_management.complaints.view_own",
        "crm_complaint_analytics": None,
        "crm_sla_conversation_tracking_dashboard": None,
        "crm_sla_conversation_tracking_list": None,
        "crm_sla_conversation_event_logs_list": None,
        "crm_projects_list": "projects.projects.view_own",
        "crm_project_detail": "projects.projects.view_own",
        "crm_project_quotations_list": "projects.projects.view_own",
        "crm_project_forecast": None,
        "crm_order_analytics": None,
        "crm_find": None,
    }


# ------------------------------------------------------------------ AC-3: a console operator must hold the slug too


@pytest.mark.parametrize("name,slug,own", PORTED, ids=[r[0] for r in PORTED])
def test_AC3_an_operator_without_the_slug_is_refused_though_the_linked_user_holds_it(db, name, slug, own):
    linked = user_with(db, slug)
    operator = user_with(db, UNRELATED)
    ctx = make_ctx(linked, operator=operator)
    rec = Recorder()
    out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == [], "the route was reached for an operator without the slug"
    assert agent_tools.user_may_use(db, ctx, tool(name)) is False


@pytest.mark.parametrize("name,slug,own", PORTED, ids=[r[0] for r in PORTED])
def test_AC3_an_operator_holding_the_slug_passes(db, name, slug, own):
    linked = user_with(db, slug)
    operator = user_with(db, slug)
    ctx = make_ctx(linked, operator=operator)
    rec = Recorder()
    out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "ok", (out.status, out.message)
    assert [c[0] for c in rec.calls] == [name]


@pytest.mark.parametrize("name,slug,own", [r for r in PORTED if r[2]], ids=[r[0] for r in PORTED if r[2]])
def test_AC3_an_operators_view_own_does_not_open_the_read_either(db, name, slug, own):
    linked = user_with(db, slug)
    operator = user_with(db, own)
    ctx = make_ctx(linked, operator=operator)
    rec = Recorder()
    out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == []
