"""S3b - `app.services.outstanding_report_bootstrap` (PLAN-chatbot-outstanding-report.md).

Mirrors `it_support_bootstrap._enable_tool_for_ai_assistant`: appends
`crm_outstanding_report` to `AIAssistantConfig.enabled_tools` at startup so the
in-app assistant's RAG selector can find it. Postgres only (`tests/_pg_fixture.py`).
"""
from __future__ import annotations

import uuid

from app.models.ai_assistant import AIAssistantConfig
from app.services.outstanding_report_bootstrap import TOOL_NAME, run
from tests._pg_fixture import blank_session


def test_tool_absent_gains_it():
    with blank_session() as db:
        config = AIAssistantConfig(id=str(uuid.uuid4()), enabled_tools=["crm_order_management_orders_list"])
        db.add(config)
        db.commit()

        summary = run(db)

        assert summary["tool_added_to_ai_assistant_enabled_tools"] is True
        db.refresh(config)
        assert config.enabled_tools == ["crm_order_management_orders_list", TOOL_NAME]


def test_tool_present_is_untouched():
    with blank_session() as db:
        existing = ["crm_order_management_orders_list", TOOL_NAME, "crm_incoming_stock_by_product"]
        config = AIAssistantConfig(id=str(uuid.uuid4()), enabled_tools=list(existing))
        db.add(config)
        db.commit()

        summary = run(db)

        assert summary["tool_added_to_ai_assistant_enabled_tools"] is False
        db.refresh(config)
        # Untouched - not just "still contains the tool": no reorder, no dedupe, no prune.
        assert config.enabled_tools == existing


def test_no_config_row_is_a_no_op():
    with blank_session() as db:
        summary = run(db)

        assert summary["tool_added_to_ai_assistant_enabled_tools"] is False
        assert db.query(AIAssistantConfig).count() == 0
