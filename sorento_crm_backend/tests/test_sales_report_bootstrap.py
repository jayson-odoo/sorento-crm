"""S3 - `app.services.sales_report_bootstrap` (PLAN-chatbot-sales-report.md,
chatbot-sales-report-acceptance-criteria.md AC-1642).

Mirrors `test_outstanding_report_bootstrap.py` exactly, for the sibling module
`app.services.sales_report_bootstrap` (not yet written): appends `crm_sales_report`
to `AIAssistantConfig.enabled_tools` at startup, idempotently. Postgres only
(`tests/_pg_fixture.py`).

The module does not exist yet, so the import is guarded INSIDE each test (never at
module scope) - a bare top-level `from app.services.sales_report_bootstrap import
...` would turn every test in this file into one collection error instead of three
clearly-failing tests.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.ai_assistant import AIAssistantConfig
from tests._pg_fixture import blank_session


def _import_bootstrap():
    try:
        from app.services.sales_report_bootstrap import TOOL_NAME, run
    except ImportError as exc:  # pragma: no cover - the RED state itself
        pytest.fail(
            f"app.services.sales_report_bootstrap does not exist yet (AC-1642): {exc}"
        )
    return TOOL_NAME, run


def test_tool_absent_gains_it():
    tool_name, run = _import_bootstrap()
    with blank_session() as db:
        config = AIAssistantConfig(id=str(uuid.uuid4()), enabled_tools=["crm_order_management_orders_list"])
        db.add(config)
        db.commit()

        summary = run(db)

        assert summary["tool_added_to_ai_assistant_enabled_tools"] is True
        db.refresh(config)
        assert config.enabled_tools == ["crm_order_management_orders_list", tool_name]


def test_tool_present_is_untouched():
    tool_name, run = _import_bootstrap()
    with blank_session() as db:
        existing = ["crm_order_management_orders_list", tool_name, "crm_incoming_stock_by_product"]
        config = AIAssistantConfig(id=str(uuid.uuid4()), enabled_tools=list(existing))
        db.add(config)
        db.commit()

        summary = run(db)

        assert summary["tool_added_to_ai_assistant_enabled_tools"] is False
        db.refresh(config)
        # Untouched - not just "still contains the tool": no reorder, no dedupe, no prune.
        assert config.enabled_tools == existing


def test_no_config_row_is_a_no_op():
    _tool_name, run = _import_bootstrap()
    with blank_session() as db:
        summary = run(db)

        assert summary["tool_added_to_ai_assistant_enabled_tools"] is False
        assert db.query(AIAssistantConfig).count() == 0


def test_tool_name_is_crm_sales_report():
    """Pinned separately so a future rename of the constant is caught here rather
    than silently changing which tool the bootstrap enables."""
    tool_name, _run = _import_bootstrap()
    assert tool_name == "crm_sales_report", tool_name
