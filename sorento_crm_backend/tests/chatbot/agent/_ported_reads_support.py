"""Shared table and helpers for the AGENTIC-UNIFY PR 4 ported-read tests (not a test module).

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

#: AC-1: (tool, slug, own slug a panel turn also accepts or None).
AC1 = [
    ("crm_complaints_list", COMPLAINTS_VIEW, COMPLAINTS_VIEW_OWN),
    ("crm_complaint_analytics", COMPLAINTS_VIEW, None),
    ("crm_sla_conversation_tracking_dashboard", SLA_VIEW, None),
    ("crm_sla_conversation_tracking_list", SLA_VIEW, None),
    ("crm_sla_conversation_event_logs_list", SLA_VIEW, None),
    ("crm_projects_list", PROJECTS_VIEW, PROJECTS_VIEW_OWN),
    ("crm_project_detail", PROJECTS_VIEW, PROJECTS_VIEW_OWN),
    ("crm_project_quotations_list", PROJECTS_VIEW, PROJECTS_VIEW_OWN),
    ("crm_project_forecast", PROJECTS_VIEW, None),
    ("crm_order_analytics", ORDERS_VIEW, None),
    ("crm_find", PRODUCTS_VIEW, None),
]
CAPABILITIES = "crm_system_tool_capabilities_summary"
FIND = "crm_find"
AC1_NAMES = [row[0] for row in AC1] + [CAPABILITIES]
#: The tools Jev is told about and whose operator is checked (AC-3, AC-8): AC-1 less find and capabilities.
PORTED = [row for row in AC1 if row[0] != FIND]
PORTED_NAMES = [row[0] for row in PORTED]
OWN_ROWS = [row for row in AC1 if row[2]]
NO_OWN_ROWS = [row for row in AC1 if not row[2]]

#: A slug that opens none of the above.
UNRELATED = "inventory.stock.view"

#: What a route answers (render envelope for crm_find, the raw body for every other read).
GOOD_BODY = {"data": [{"ref": "ZZT-1"}], "total": 1}
GOOD_ENVELOPE = {"has_result": True, "items": [{"ref": "ZZT-1"}]}


def good_body(name: str) -> dict:
    return dict(GOOD_ENVELOPE) if name == FIND else {**GOOD_BODY}


def catalog() -> dict[str, dict]:
    """A catalogue entry per AC-1 name, with the guard pair and the params the agent may send."""
    props = {k: {"type": "string"} for k in ("contact_id", "space_id", "query", "page", "limit", "project_id")}
    return {name: {"description": name, "inputSchema": {"type": "object", "properties": dict(props)}} for name in AC1_NAMES}


def make_ctx(user_id: str, *, operator: str | None = None) -> AgentContext:
    return AgentContext(
        contact_pk="zzt-pk",
        contact_respond_id="ZZT-RESPOND-1",
        space_id="364817",
        user_id=user_id,
        user_name="ZZT User",
        grants=frozenset(),
        operator_user_id=operator,
    )


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
