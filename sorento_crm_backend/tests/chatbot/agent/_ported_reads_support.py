"""Shared table and helpers for the AGENTIC-UNIFY PR 4 ported-read tests (not a test module).

After the security review (crew ruling, 2 Nov) every tool of PR 4 is offered on a panel turn only, so the slug
tests run inside `panel_turn` and the reveal keys of a panel ctx come from `staff_reveal_keys` (`panel_ctx`).

Nothing here imports a name the coder has yet to build at module load: `PORTED_READS`, `ToolDef.own_permission`
and the new `REGISTRY` rows are all reached inside a function, so a missing one fails the test that needs it.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

from app.services.chatbot import principal as staff_principal
from app.services.chatbot.agent import tools as agent_tools
from app.services.chatbot.agent.access import AgentContext

COMPLAINTS_VIEW = "complaint_management.complaints.view"
COMPLAINTS_VIEW_OWN = "complaint_management.complaints.view_own"
SLA_VIEW = "sla_management.conversation_sla_tracking.view"
PROJECTS_VIEW = "projects.projects.view"
PROJECTS_VIEW_OWN = "projects.projects.view_own"
ORDERS_VIEW = "order_management.orders.view"
PRODUCTS_VIEW = "master_data.products.view"
STOCK_VIEW = "inventory.stock.view"
ESCALATION_LOGS_VIEW = "sla_management.escalation_logs.view"
#: The staff slug that answers the `sales_orders.sales_report` reveal key (`_STAFF_REVEAL_SLUGS`).
SALES_REPORT_SLUG = "sales.reports.view"
SALES_REPORT_KEY = "sales_orders.sales_report"

#: AC-1: (tool, slug, own slug a panel turn also accepts or None).
AC1 = [
    ("crm_complaints_list", COMPLAINTS_VIEW, COMPLAINTS_VIEW_OWN),
    ("crm_complaint_analytics", COMPLAINTS_VIEW, None),
    ("crm_sla_conversation_tracking_dashboard", SLA_VIEW, None),
    ("crm_sla_conversation_tracking_list", SLA_VIEW, None),
    ("crm_sla_conversation_event_logs_list", ESCALATION_LOGS_VIEW, None),
    ("crm_projects_list", PROJECTS_VIEW, PROJECTS_VIEW_OWN),
    ("crm_project_detail", PROJECTS_VIEW, PROJECTS_VIEW_OWN),
    ("crm_project_quotations_list", PROJECTS_VIEW, PROJECTS_VIEW_OWN),
    ("crm_project_forecast", PROJECTS_VIEW, None),
    ("crm_order_analytics", ORDERS_VIEW, None),
    ("crm_find", STOCK_VIEW, None),
]
#: Slugs a tool needs beyond its row's slug (the order analytics also asks the sales reveal).
EXTRA_SLUGS = {"crm_order_analytics": (SALES_REPORT_SLUG,)}
CAPABILITIES = "crm_system_tool_capabilities_summary"
FIND = "crm_find"
#: `crm_system_tool_capabilities_summary` is dropped (its route reads a catalog path the deployed image lacks):
#: it is in no list here, and `test_ported_reads_access.py` pins that it is in no registry, label or turn.
AC1_NAMES = [row[0] for row in AC1]
#: AGENT-QUOTE-COMPARE: a panel-only read that runs in process (no MCP route), so it is in none of the AC-1 route tables.
LOCAL_PORTED = ["crm_project_quotation_lines"]
#: The tools Jev is told about and whose operator is checked (AC-8): AC-1 less `crm_find`.
PORTED = [row for row in AC1 if row[0] != FIND]
PORTED_NAMES = [row[0] for row in PORTED]
OWN_ROWS = [row for row in AC1 if row[2]]
NO_OWN_ROWS = [row for row in AC1 if not row[2]]

#: A slug that opens none of the above.
UNRELATED = "master_data.brands.view"

#: What a route answers (render envelope for crm_find, the raw body for every other read).
GOOD_BODY = {"data": [{"ref": "ZZT-1"}], "total": 1}
GOOD_ENVELOPE = {"result_type": "find", "response": "Code: ZZT-1\nStock: 5", "has_result": True}


def good_body(name: str) -> dict:
    return dict(GOOD_ENVELOPE) if name == FIND else {**GOOD_BODY}


def catalog() -> dict[str, dict]:
    """A catalogue entry per AC-1 name, with the guard pair and the params the agent may send."""
    props = {k: {"type": "string"} for k in ("contact_id", "space_id", "query", "page", "limit", "project_id")}
    return {name: {"description": name, "inputSchema": {"type": "object", "properties": dict(props)}} for name in AC1_NAMES}


def slugs_for(name: str, slug: str) -> tuple[str, ...]:
    """What a user needs to hold for `name`: the row's slug and any extra the tool asks."""
    return (slug, *EXTRA_SLUGS.get(name, ()))


def make_ctx(user_id: str, *, operator: str | None = None, grants=frozenset()) -> AgentContext:
    return AgentContext(
        contact_pk="zzt-pk",
        contact_respond_id="ZZT-RESPOND-1",
        space_id="364817",
        user_id=user_id,
        user_name="ZZT User",
        grants=frozenset(grants),
        operator_user_id=operator,
    )


def panel_ctx(db, user_id: str) -> AgentContext:
    """The ctx a panel turn builds for the user: the reveal keys are the staff member's own permissions."""
    from app.services.contact_field_reveal_service import staff_reveal_keys

    return make_ctx(user_id, grants=staff_reveal_keys(db, user_id))


@contextmanager
def panel_turn(user_id: str):
    """`staff_principal` set for the turn, as `run_turn` does for a panel message."""
    principal = staff_principal.StaffPrincipal(user_id=user_id, conversation_id=str(uuid.uuid4()))
    with staff_principal.acting_as(principal):
        yield principal


class Recorder:
    """A fake `call(name, args)` that records every invocation."""

    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        if self.exc is not None:
            raise self.exc
        return self.result if self.result is not None else good_body(name)


def dispatch(db, ctx, name, args=None, *, rec):
    tool(name)  # a refusal of a tool that is not registered yet must not pass for the right reason
    return agent_tools.dispatch(db, ctx, name, dict(args or {}), call=rec, catalog=catalog(), timeout=5.0)


def tool(name: str):
    """The REGISTRY row, or a failed assertion naming the missing tool (the red reason)."""
    row = agent_tools.REGISTRY.get(name)
    assert row is not None, f"{name} is not in REGISTRY"
    return row


def ported_reads() -> frozenset[str]:
    names = getattr(agent_tools, "PORTED_READS", None)
    assert names is not None, "tools.PORTED_READS does not exist"
    return names
