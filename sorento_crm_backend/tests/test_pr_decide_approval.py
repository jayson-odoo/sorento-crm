"""In-system approve/reject (decide_approval) guards + delegation.

The form's Approve/Reject buttons must behave like the public approval link: they
funnel through the shared _apply_approval_decision. decide_approval only adds the
authenticated guard (must be pending approval) and skips the one-time token.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.procurement_service import PurchaseRequestService
from app.services.error_handler import AppException


def _svc(header):
    s = PurchaseRequestService.__new__(PurchaseRequestService)
    s.db = MagicMock()
    s.get_request = MagicMock(return_value=header)  # type: ignore[attr-defined]
    return s


def test_decide_approval_pending_delegates_to_shared_apply():
    header = SimpleNamespace(id="pr1", approval_status="pending")
    svc = _svc(header)
    with patch.object(PurchaseRequestService, "_apply_approval_decision", return_value=header) as apply:
        svc.decide_approval("pr1", action="approved", approved_by="Jane")
    apply.assert_called_once()
    # delegates with the resolved header + action + approver, no token involved.
    assert apply.call_args.args[0] is header
    assert apply.call_args.args[1] == "approved"
    assert apply.call_args.kwargs["approved_by"] == "Jane"


def test_decide_approval_already_approved_conflicts():
    header = SimpleNamespace(id="pr1", approval_status="approved")
    svc = _svc(header)
    with patch.object(PurchaseRequestService, "_apply_approval_decision") as apply:
        with pytest.raises(AppException):
            svc.decide_approval("pr1", action="approved")
        apply.assert_not_called()


def test_decide_approval_not_pending_conflicts():
    header = SimpleNamespace(id="pr1", approval_status="")  # never sent for approval
    svc = _svc(header)
    with patch.object(PurchaseRequestService, "_apply_approval_decision") as apply:
        with pytest.raises(AppException):
            svc.decide_approval("pr1", action="rejected", approval_comments="no")
        apply.assert_not_called()
