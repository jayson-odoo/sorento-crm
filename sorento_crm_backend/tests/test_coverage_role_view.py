"""Unit tests for coverage_role_view — the shared role-explicit projection + summary.

The summary must bind each name to its role with hardcoded verbs so any reader
(LLM page snapshot, screen reader) can't swap "covers for" with "assigned by".
"""
from datetime import datetime

from app.services.coverage_subscription_service import coverage_role_view


def test_hod_assigned_auto_assign_with_expiry():
    v = coverage_role_view(
        coverer_name="Sandy Lim",
        covers_for_name="Emily",
        assigned_by_name="Ms Tan",
        expires_at=datetime(2026, 7, 3),
        redirect_assignments=True,
    )
    assert v["coverer_name"] == "Sandy Lim"
    assert v["covers_for_name"] == "Emily"
    assert v["assigned_by_name"] == "Ms Tan"
    assert v["coverage_mode"] == "auto-assign"
    assert v["summary"] == (
        "Sandy Lim covers for Emily, who is away. Assigned by Ms Tan. "
        "Active until 03 Jul 2026 (auto-assign)."
    )


def test_self_subscribed_no_expiry_notify_only():
    v = coverage_role_view(
        coverer_name="Sandy Lim",
        covers_for_name="Emily",
        assigned_by_name=None,
        expires_at=None,
        redirect_assignments=False,
    )
    assert v["coverage_mode"] == "notify-only"
    # No "Assigned by" when self-subscribed; no expiry.
    assert "Assigned by" not in v["summary"]
    assert v["summary"] == (
        "Sandy Lim covers for Emily, who is away. Self-subscribed. "
        "No end date (notify-only)."
    )


def test_summary_orders_coverer_before_covered():
    """Coverer must precede 'covers for', covered must follow it — the bug was the
    reader treating the assigner as the covered person."""
    v = coverage_role_view(
        coverer_name="A",
        covers_for_name="B",
        assigned_by_name="C",
        expires_at=None,
        redirect_assignments=False,
    )
    s = v["summary"]
    assert s.index("A covers for B") < s.index("Assigned by C")
