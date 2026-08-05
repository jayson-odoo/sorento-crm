"""Triage and the approver decision are separate permissions.

`procurement.purchase_requests.send_for_approval` used to gate the in-system
Approve/Reject decision AND Reject-at-submitted, while change-to-pending was open to
any authenticated user. Granting the slug so a sales admin could reject a submitted
request therefore also made them an approver of anything already pending.

The split:

    send_for_approval -> triage a SUBMITTED request (change to pending, or reject)
    approve           -> approver decision on a PENDING APPROVAL request

Checked structurally, off the route table and the registry, so no database or HTTP
round-trip is needed and the assertions can't drift from what FastAPI actually wires.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.procurement.purchase_requests import router as pr_router
from app.rbac.permission_registry import PERMISSION_REGISTRY
from app.services.ai_assistant_service import AIAssistantChatService

TRIAGE = "procurement.purchase_requests.send_for_approval"
APPROVE = "procurement.purchase_requests.approve"

_PROBE_APP = FastAPI()
_PROBE_APP.include_router(pr_router, prefix="/api/v1/procurement/purchase-requests")


def _permission_slugs_for(path_suffix: str) -> set[str]:
    """Every permission slug the route's dependency tree enforces.

    `require_permission_with_api_key(slug)` closes over `slug`, so recover it from the
    closure of each dependency callable rather than trusting a name convention.
    """
    slugs: set[str] = set()
    for route in _PROBE_APP.routes:
        if not getattr(route, "path", "").endswith(path_suffix):
            continue
        dependant = getattr(route, "dependant", None)
        stack = [dependant] if dependant else []
        while stack:
            node = stack.pop()
            call = getattr(node, "call", None)
            for cell in getattr(call, "__closure__", None) or ():
                value = cell.cell_contents
                if isinstance(value, str) and value.startswith("procurement."):
                    slugs.add(value)
            stack.extend(getattr(node, "dependencies", []) or [])
    return slugs


class TestRouteGates:
    def test_the_routes_under_test_exist(self):
        """Guards the assertions below against silently passing on an empty set."""
        paths = {getattr(r, "path", "") for r in _PROBE_APP.routes}
        for suffix in ("/set-pending-approval", "/reject-submitted", "/approval-decision"):
            assert any(p.endswith(suffix) for p in paths), f"route {suffix} not mounted"

    def test_change_to_pending_requires_triage(self):
        """Was open to ANY authenticated user - anyone who could view a request could
        push it into the approval queue."""
        assert TRIAGE in _permission_slugs_for("/set-pending-approval")

    def test_reject_submitted_requires_triage(self):
        assert TRIAGE in _permission_slugs_for("/reject-submitted")

    def test_approval_decision_requires_the_decision_permission(self):
        assert APPROVE in _permission_slugs_for("/approval-decision")

    def test_approval_decision_is_not_reachable_with_triage_alone(self):
        """The whole point of the split: triage must not confer the decision."""
        assert TRIAGE not in _permission_slugs_for("/approval-decision")

    def test_triage_routes_do_not_require_the_decision_permission(self):
        """...and the reverse, so a sales admin isn't blocked from triaging."""
        assert APPROVE not in _permission_slugs_for("/set-pending-approval")
        assert APPROVE not in _permission_slugs_for("/reject-submitted")


class TestRegistry:
    def test_both_permissions_are_registered(self):
        """`sync_permissions` seeds from the registry at startup; an unregistered slug
        can never be granted in the UI."""
        slugs = {p["slug"] for p in PERMISSION_REGISTRY}
        assert TRIAGE in slugs
        assert APPROVE in slugs


class TestAssistantIsNotABypass:
    def test_assistant_approve_and_reject_take_the_decision_permission(self):
        """`crm_purchase_request_approve` / `_reject` both POST to /approval-decision.
        Left on the triage slug they would let a triage-only user approve through the
        assistant, defeating the split at the endpoint."""
        mapping = AIAssistantChatService._WRITE_TOOL_PERMISSIONS
        assert mapping["crm_purchase_request_approve"] == APPROVE
        assert mapping["crm_purchase_request_reject"] == APPROVE
