"""AGENTIC-UNIFY PR 4: who is offered the twelve ported reads on a PANEL turn, and who is refused (AC-1, AC-2).

After the security review (crew ruling, 2 Nov) the reads exist only on a panel turn (AC-0, pinned in
`test_ported_panel_only.py`), where the route runs as the user. So every case here runs inside `panel_turn`.

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
    LOCAL_PORTED,
    CAPABILITIES,
    ESCALATION_LOGS_VIEW,
    ORDERS_VIEW,
    OWN_ROWS,
    PORTED,
    PRODUCTS_VIEW,
    SALES_REPORT_KEY,
    SALES_REPORT_SLUG,
    SLA_VIEW,
    STOCK_VIEW,
    UNRELATED,
    Recorder,
    catalog,
    dispatch,
    panel_ctx,
    panel_turn,
    ported_reads,
    slugs_for,
    tool,
)


@pytest.fixture(scope="module")
def db():
    """One blank schema for the module; every test seeds its own uniquely named users."""
    with blank_session() as session:
        yield session


EVERY = tuple(slug for _n, slug, _o in AC1) + ("sales.reports.view",)


def user_with(db, *slugs) -> str:
    return seed_user(db, contact_pk=None, slugs=slugs)


# ------------------------------------------------------------------ AC-1: the slug opens it, nothing else does


@pytest.mark.parametrize("name,slug,own", AC1, ids=[r[0] for r in AC1])
def test_AC1_a_panel_user_holding_the_slug_is_offered_the_tool_and_may_call_it(db, name, slug, own):
    user_id = user_with(db, *slugs_for(name, slug))
    ctx = panel_ctx(db, user_id)
    row = tool(name)
    rec = Recorder()
    with panel_turn(user_id):
        assert agent_tools.user_may_use(db, ctx, row) is True
        assert agent_tools.contact_allows(ctx, row) is True
        assert name in [t.name for t in permitted_tools(db, ctx)]
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "ok", (out.status, out.message)
    assert [c[0] for c in rec.calls] == [name]


@pytest.mark.parametrize("name,slug,own", AC1, ids=[r[0] for r in AC1])
def test_AC1_a_panel_user_without_the_slug_is_not_offered_the_tool_and_is_refused_at_dispatch(db, name, slug, own):
    user_id = user_with(db, UNRELATED)
    ctx = panel_ctx(db, user_id)
    row = tool(name)
    rec = Recorder()
    with panel_turn(user_id):
        assert agent_tools.user_may_use(db, ctx, row) is False
        assert name not in [t.name for t in permitted_tools(db, ctx)]
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert "outside this user's access" in out.message
    assert rec.calls == [], "the route was reached for a user without the slug"


@pytest.mark.parametrize("name,slug,own", AC1, ids=[r[0] for r in AC1])
def test_AC1_a_panel_user_holding_no_role_at_all_is_refused(db, name, slug, own):
    user_id = user_with(db)
    ctx = panel_ctx(db, user_id)
    rec = Recorder()
    with panel_turn(user_id):
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == []


@pytest.mark.parametrize("name,slug,own", AC1, ids=[r[0] for r in AC1])
def test_AC1_the_slug_is_checked_at_call_time_not_only_at_exposure(db, name, slug, own):
    """Offered while the role holds the slug, refused once it is taken away."""
    user_id = user_with(db, *slugs_for(name, slug))
    ctx = panel_ctx(db, user_id)
    with panel_turn(user_id):
        assert name in [t.name for t in permitted_tools(db, ctx)]
    from app.models.user import UserRoleAssignment, UserRolePermission

    role_ids = [a.role_id for a in db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id)]
    assert role_ids
    db.query(UserRolePermission).filter(UserRolePermission.role_id.in_(role_ids)).delete(synchronize_session=False)
    db.flush()
    from app.services.user_service import invalidate_rbac_cache

    invalidate_rbac_cache(user_id)
    rec = Recorder()
    with panel_turn(user_id):
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == []


def test_AC1_capabilities_summary_is_dropped_from_the_registry_and_offered_on_no_turn(db):
    """Its route loads the MCP catalog from a path the deployed backend image does not hold."""
    assert CAPABILITIES not in agent_tools.REGISTRY
    assert CAPABILITIES not in agent_tools.TOOL_LABELS
    user_id = user_with(db, *EVERY)
    ctx = panel_ctx(db, user_id)
    with panel_turn(user_id):
        assert CAPABILITIES not in [t.name for t in permitted_tools(db, ctx)]
        out = agent_tools.dispatch(
            db, ctx, CAPABILITIES, {}, call=Recorder(), catalog=catalog(), timeout=5.0
        )
    assert out.status == "denied", (out.status, out.message)


def test_AC1_the_slugs_are_the_tables_not_the_orders_one_by_accident(db):
    """A holder of only the complaints slug does not open the projects, SLA, order or find reads."""
    user_id = user_with(db, "complaint_management.complaints.view")
    ctx = panel_ctx(db, user_id)
    with panel_turn(user_id):
        offered = {t.name for t in permitted_tools(db, ctx)}
    assert {"crm_complaints_list", "crm_complaint_analytics"} <= offered
    for name, _slug, _own in AC1:
        if name not in ("crm_complaints_list", "crm_complaint_analytics"):
            assert name not in offered, f"{name} was offered to a complaints-only user"


def test_AC1_ported_reads_is_the_ac1_set_less_find_and_capabilities():
    assert ported_reads() == frozenset(r[0] for r in PORTED) | frozenset(LOCAL_PORTED)
    assert "crm_find" not in ported_reads()


def test_AC1_every_ported_read_is_a_non_render_tool_and_find_alone_renders():
    for name, _slug, _own in AC1:
        assert tool(name).render is (name == "crm_find"), name


# ------------------------------------------------------------------ AC-1 findings: the route's own slug


def test_AC1_event_logs_unfiltered_needs_the_escalation_logs_slug_not_the_tracking_one(db):
    """The route's rule for an unfiltered read (`sla_tracking.py` `_require_event_log_reader`)."""
    name = "crm_sla_conversation_event_logs_list"
    tracking_only = user_with(db, SLA_VIEW)
    ctx = panel_ctx(db, tracking_only)
    rec = Recorder()
    with panel_turn(tracking_only):
        assert agent_tools.user_may_use(db, ctx, tool(name)) is False
        assert name not in [t.name for t in permitted_tools(db, ctx)]
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == [], "the event logs were read for a user holding only the tracking slug"


def test_AC1_event_logs_unfiltered_is_offered_to_a_holder_of_the_escalation_logs_slug(db):
    name = "crm_sla_conversation_event_logs_list"
    holder = user_with(db, ESCALATION_LOGS_VIEW)
    ctx = panel_ctx(db, holder)
    rec = Recorder()
    with panel_turn(holder):
        assert name in [t.name for t in permitted_tools(db, ctx)]
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "ok", (out.status, out.message)
    assert [c[0] for c in rec.calls] == [name]


def test_AC1_the_other_sla_reads_stay_on_the_tracking_slug(db):
    tracking_only = user_with(db, SLA_VIEW)
    ctx = panel_ctx(db, tracking_only)
    with panel_turn(tracking_only):
        offered = {t.name for t in permitted_tools(db, ctx)}
    assert {"crm_sla_conversation_tracking_dashboard", "crm_sla_conversation_tracking_list"} <= offered


def test_AC1_find_needs_the_stock_slug_because_every_answer_carries_stock(db):
    products_only = user_with(db, PRODUCTS_VIEW)
    ctx = panel_ctx(db, products_only)
    rec = Recorder()
    with panel_turn(products_only):
        assert agent_tools.user_may_use(db, ctx, tool("crm_find")) is False
        assert "crm_find" not in [t.name for t in permitted_tools(db, ctx)]
        out = dispatch(db, ctx, "crm_find", rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == [], "crm_find reached the route for a user without the stock slug"


def test_AC1_find_is_offered_to_a_holder_of_the_stock_slug(db):
    holder = user_with(db, STOCK_VIEW)
    ctx = panel_ctx(db, holder)
    rec = Recorder()
    with panel_turn(holder):
        assert "crm_find" in [t.name for t in permitted_tools(db, ctx)]
        out = dispatch(db, ctx, "crm_find", rec=rec)
    assert out.status == "ok", (out.status, out.message)
    assert [c[0] for c in rec.calls] == ["crm_find"]


# ------------------------------------------------------------------ AC-1 findings: order analytics and the sales reveal


def test_AC1_order_analytics_needs_the_sales_reveal_as_well_as_the_orders_slug(db):
    name = "crm_order_analytics"
    orders_only = user_with(db, ORDERS_VIEW)
    ctx = panel_ctx(db, orders_only)
    assert SALES_REPORT_KEY not in ctx.grants, "fixture: the user holds no sales reveal"
    rec = Recorder()
    with panel_turn(orders_only):
        assert name not in [t.name for t in permitted_tools(db, ctx)]
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == [], "order totals were read for a user without the sales reveal"


def test_AC1_order_analytics_is_allowed_with_the_sales_reveal(db):
    name = "crm_order_analytics"
    holder = user_with(db, ORDERS_VIEW, SALES_REPORT_SLUG)
    ctx = panel_ctx(db, holder)
    assert SALES_REPORT_KEY in ctx.grants, "fixture: the staff slug answers the sales reveal"
    rec = Recorder()
    with panel_turn(holder):
        assert name in [t.name for t in permitted_tools(db, ctx)]
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "ok", (out.status, out.message)
    assert [c[0] for c in rec.calls] == [name]


def test_AC1_the_reveal_alone_without_the_orders_slug_opens_nothing(db):
    reveal_only = user_with(db, SALES_REPORT_SLUG)
    ctx = panel_ctx(db, reveal_only)
    rec = Recorder()
    with panel_turn(reveal_only):
        out = dispatch(db, ctx, "crm_order_analytics", rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == []


def test_AC1_a_refused_sales_read_stays_refused_for_the_turn_for_order_analytics(db):
    """`crm_report_ask` on a sales basis refused by the route (403) puts `sales` in the turn's denied domains;
    the order totals are the same figures, so they are refused too, without reaching the route."""
    holder = user_with(db, ORDERS_VIEW, SALES_REPORT_SLUG)
    ctx = panel_ctx(db, holder)
    domains: set[str] = set()
    refusing = Recorder(exc=RuntimeError("returned HTTP 403: sales report not enabled"))
    analytics = Recorder()
    cat = {**catalog(), "crm_report_ask": {
        "description": "r", "inputSchema": {"type": "object", "properties": {"basis": {"type": "string"}}}}}
    with panel_turn(holder):
        first = agent_tools.dispatch(
            db, ctx, "crm_report_ask", {"basis": "invoiced"}, call=refusing, catalog=cat, timeout=5.0,
            denied_domains=domains,
        )
        assert first.status == "denied", (first.status, first.message)
        second = agent_tools.dispatch(
            db, ctx, "crm_order_analytics", {}, call=analytics, catalog=cat, timeout=5.0, denied_domains=domains,
        )
    assert second.status == "denied", (second.status, second.message)
    assert "refused earlier in this turn" in second.message
    assert analytics.calls == [], "order totals were read after a refused sales read in the same turn"


def test_AC1_order_analytics_is_in_the_sales_data_domain():
    assert agent_tools.data_domain("crm_order_analytics", {}) == "sales"


# ------------------------------------------------------------------ AC-2: view_own counts on a panel turn


@pytest.mark.parametrize("name,slug,own", OWN_ROWS, ids=[r[0] for r in OWN_ROWS])
def test_AC2_view_own_alone_is_offered_and_called_on_a_panel_turn(db, name, slug, own):
    user_id = user_with(db, own)
    ctx = panel_ctx(db, user_id)
    rec = Recorder()
    with panel_turn(user_id):
        assert agent_tools.user_may_use(db, ctx, tool(name)) is True
        assert name in [t.name for t in permitted_tools(db, ctx)]
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "ok", (out.status, out.message)
    assert [c[0] for c in rec.calls] == [name]


@pytest.mark.parametrize("name,slug,own", OWN_ROWS, ids=[r[0] for r in OWN_ROWS])
def test_AC2_a_panel_user_with_neither_slug_is_still_refused(db, name, slug, own):
    user_id = user_with(db, UNRELATED)
    ctx = panel_ctx(db, user_id)
    rec = Recorder()
    with panel_turn(user_id):
        assert agent_tools.user_may_use(db, ctx, tool(name)) is False
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == []


@pytest.mark.parametrize("name,slug,own", OWN_ROWS, ids=[r[0] for r in OWN_ROWS])
def test_AC2_the_full_slug_works_on_the_panel(db, name, slug, own):
    user_id = user_with(db, slug)
    ctx = panel_ctx(db, user_id)
    with panel_turn(user_id):
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
    ctx = panel_ctx(db, user_id)
    rec = Recorder()
    with panel_turn(user_id):
        assert agent_tools.user_may_use(db, ctx, tool(name)) is False
        assert name not in [t.name for t in permitted_tools(db, ctx)]
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == []
