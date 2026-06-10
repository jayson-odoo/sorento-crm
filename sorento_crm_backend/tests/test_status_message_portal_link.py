"""Customer status messages link to the submission portal, not the read-only view.

PortalService.submission_link mints/reuses a portal token and returns
/portal/c/{slug}?token=…&type=…; it returns None (→ caller falls back to the view
link) when contact/space are missing or anything fails. The complaint helper prefers
the portal link and falls back to the view link.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.portal_service import PortalService


def test_submission_link_none_without_contact():
    svc = PortalService(MagicMock())
    assert svc.submission_link(None, "complaint", "e1") is None
    assert svc.submission_link("", "complaint", "e1") is None


def test_submission_link_swallows_errors_and_returns_none():
    svc = PortalService(MagicMock())
    # _resolve_contact raising must degrade to None (caller uses view link).
    with patch.object(svc, "_resolve_contact", side_effect=RuntimeError("boom")):
        assert svc.submission_link("c1", "complaint", "e1") is None


def test_submission_link_builds_entity_deep_link_path():
    svc = PortalService(MagicMock())
    contact = SimpleNamespace(id="c1")
    with patch.object(svc, "_resolve_contact", return_value=contact), \
         patch.object(svc, "get_or_create_slug", return_value="67C70ASV59"), \
         patch("app.services.portal_service.settings") as s:
        s.frontend_base_url = "http://localhost:3000"
        link = svc.submission_link("c1", "complaint", "aa8e531a")
    assert link == "http://localhost:3000/portal/c/67C70ASV59/complaint/aa8e531a"


def test_complaint_link_part_falls_back_to_view_when_no_portal():
    from app.services.complaints_service import ComplaintService

    svc = ComplaintService(MagicMock())
    complaint = SimpleNamespace(contact_id="c1", space_id="364817")
    with patch.object(svc, "_complaint_public_view_links_enabled", return_value=True), \
         patch("app.services.portal_service.PortalService.submission_link", return_value=None), \
         patch.object(svc, "_build_complaint_view_url", return_value="https://x/view/complaint?token=abc"):
        part = svc._complaint_status_link_part(complaint, "cmp1")
    assert part == " https://x/view/complaint?token=abc"


def test_complaint_link_part_prefers_portal_link():
    from app.services.complaints_service import ComplaintService

    svc = ComplaintService(MagicMock())
    complaint = SimpleNamespace(contact_id="c1", space_id="364817")
    portal = "https://x/portal/c/SLUG?token=tok&type=complaint"
    with patch.object(svc, "_complaint_public_view_links_enabled", return_value=True), \
         patch("app.services.portal_service.PortalService.submission_link", return_value=portal), \
         patch.object(svc, "_build_complaint_view_url", return_value="https://x/view") as view_spy:
        part = svc._complaint_status_link_part(complaint, "cmp1")
    assert part == f" {portal}"
    view_spy.assert_not_called()  # portal preferred; view builder never invoked


def test_complaint_link_part_empty_when_public_links_disabled():
    from app.services.complaints_service import ComplaintService

    svc = ComplaintService(MagicMock())
    complaint = SimpleNamespace(contact_id="c1", space_id="364817")
    with patch.object(svc, "_complaint_public_view_links_enabled", return_value=False):
        assert svc._complaint_status_link_part(complaint, "cmp1") == ""
