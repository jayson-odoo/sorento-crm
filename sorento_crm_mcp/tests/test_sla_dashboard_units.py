"""PR 4 round 3 G2 (red): the SLA dashboard tool's catalog text names its units.

The averages are hours and escalation_rate is a percent (sla_service.get_dashboard_metrics); the model
called them minutes. Plan: documentation/plans/chatbot/PLAN-agentic-unify-tools-1nov.md, round 3, G2.
"""
from __future__ import annotations

from sorento_crm_mcp.catalog import CATALOG


def test_G2_sla_dashboard_description_names_hours_and_percent():
    spec = next(s for s in CATALOG if s.name == "crm_sla_conversation_tracking_dashboard")
    text = spec.description.lower()
    assert "hours" in text, spec.description
    assert "percent" in text, spec.description
