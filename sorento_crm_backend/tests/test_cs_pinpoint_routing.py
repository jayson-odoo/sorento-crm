"""Per-salesman → CS PIC pin-point routing + procurement CS handoff finalize.

Covers (PLAN-procurement-cs-handoff-and-pinpoint-routing.md):
  - FormSLAOrchestrator._resolve_pinned_assignee branches (D1–D6): not-pinnable
    use_case, no contact, no pin, stale pin (non-member), inactive user, valid pin.
  - CsRoutingService.upsert validation (D4/D5): use_case + team-membership.
  - PurchaseRequestService finalize (D9): status guard, idempotency, happy path
    emits 'resolved' for the right source_entity_type.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.access import RespondContactCsRouting, TeamMember
from app.models.user import User
from app.services.cs_routing_service import CsRoutingService
from app.services.form_sla_service import FormSLAOrchestrator
from app.services.procurement_service import PurchaseRequestService


# ---- resolver -------------------------------------------------------------

def _orch(query_map):
    """FormSLAOrchestrator whose db.query(Model) returns query_map[Model] from .first()."""
    db = MagicMock()

    def _query(model):
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = query_map.get(model)
        return q

    db.query.side_effect = _query
    return FormSLAOrchestrator(db)


def test_resolver_ignores_non_pinnable_use_case():
    # complaint never reads the pin table -> round-robin.
    orch = _orch({})
    assert orch._resolve_pinned_assignee("complaint", "c1", "team1") is None


def test_resolver_no_contact_returns_none():
    orch = _orch({})
    assert orch._resolve_pinned_assignee("purchase_request", None, "team1") is None


def test_resolver_no_pin_returns_none():
    orch = _orch({RespondContactCsRouting: None})
    assert orch._resolve_pinned_assignee("purchase_request", "c1", "team1") is None


def test_resolver_stale_pin_non_member_falls_back():
    pin = SimpleNamespace(cs_pic_user_id="u1")
    orch = _orch({RespondContactCsRouting: pin, TeamMember: None})
    assert orch._resolve_pinned_assignee("purchase_request", "c1", "team1") is None


def test_resolver_inactive_user_falls_back():
    pin = SimpleNamespace(cs_pic_user_id="u1")
    member = SimpleNamespace(user_id="u1", team_id="team1")
    user = SimpleNamespace(id="u1", email="a@b.com", name="Aishah", status="INACTIVE", respond_user_id="r1")
    orch = _orch({RespondContactCsRouting: pin, TeamMember: member, User: user})
    assert orch._resolve_pinned_assignee("purchase_request", "c1", "team1") is None


def test_resolver_valid_pin_returns_assignee():
    pin = SimpleNamespace(cs_pic_user_id="u1")
    member = SimpleNamespace(user_id="u1", team_id="team1")
    user = SimpleNamespace(id="u1", email="a@b.com", name="Aishah", status="ACTIVE", respond_user_id="r1")
    orch = _orch({RespondContactCsRouting: pin, TeamMember: member, User: user})
    assert orch._resolve_pinned_assignee("sponsorship_form", "c1", "team1") == {
        "id": "u1",
        "email": "a@b.com",
        "name": "Aishah",
        "respond_user_id": "r1",
    }


# ---- CsRoutingService validation -----------------------------------------

def _routing_svc():
    svc = CsRoutingService(MagicMock())
    svc._require_contact = MagicMock()
    return svc


def test_upsert_rejects_invalid_use_case():
    svc = _routing_svc()
    with pytest.raises(Exception):
        svc.upsert("c1", "complaint", "u1")


def test_upsert_rejects_non_team_member():
    svc = _routing_svc()
    svc.list_candidates = MagicMock(return_value=[{"id": "u2"}])
    with pytest.raises(Exception):
        svc.upsert("c1", "purchase_request", "u1")


# ---- procurement CS finalize ---------------------------------------------

def _pr_service(header):
    svc = PurchaseRequestService(MagicMock())
    svc.get_request = MagicMock(return_value=header)
    return svc


def test_finalize_rejects_non_approved():
    header = SimpleNamespace(id="r1", status="submitted", request_type="purchase_request")
    with pytest.raises(Exception):
        _pr_service(header).mark_processed_by_cs("r1")


def test_finalize_is_idempotent_when_already_in_target():
    header = SimpleNamespace(id="r1", status="processed_by_cs", request_type="purchase_request")
    svc = _pr_service(header)
    assert svc.mark_processed_by_cs("r1") is header


def test_close_sets_status_and_emits_resolved_for_sponsorship():
    header = SimpleNamespace(
        id="r1",
        status="approved",
        request_type="sponsorship_form",
        request_number="SF-1",
        contact_id="c1",
    )
    svc = _pr_service(header)
    svc._build_request_view_url = MagicMock(return_value="http://x/view")
    svc._send_purchase_request_contact_message = MagicMock()
    with patch("app.services.form_sla_service.emit_form_event") as emit:
        out = svc.close_request("r1", note="done")
    assert out.status == "closed"
    svc._send_purchase_request_contact_message.assert_called_once()
    emit.assert_called_once()
    args = emit.call_args.args
    assert args[1] == "sponsorship_form"  # source_entity_type
    assert args[3] == "resolved"  # event closes the CS stage
