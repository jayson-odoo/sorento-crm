"""AC-65 - `app.services.low_stock_report_bootstrap` (PLAN-low-stock-report.md, S6's
last bullet).

`outstanding_report_bootstrap.py` with the new name: runs after `sync_catalog` so the
`crm_low_stock_report` row exists in `mcp_tools`, then appends the tool name to
`AIAssistantConfig.enabled_tools` so the in-app assistant's RAG selector
(`ai_assistant_service._rag_select_tools`, which filters candidates by that list) can find
it. Without it, a tool sitting in the code catalog is invisible to that selector.

Mirrors `tests/test_outstanding_report_bootstrap.py` case for case, because the module is
the same module under a different name and the three things worth pinning about it are the
same three: it appends, it is idempotent, and it does not raise when there is nothing to
append to.

Postgres only (`tests/_pg_fixture.py::blank_session`).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.ai_assistant import AIAssistantConfig
from tests._pg_fixture import blank_session


def _bootstrap():
    """Imported inside the tests so a missing module is three readable failures rather
    than a collection error."""
    from app.services import low_stock_report_bootstrap

    return low_stock_report_bootstrap


def test_tool_name_is_the_catalog_name() -> None:
    """The constant has to be the catalog's own name or the append is a no-op the RAG
    selector will never match."""
    assert _bootstrap().TOOL_NAME == "crm_low_stock_report"


def test_tool_absent_gains_it() -> None:
    mod = _bootstrap()
    with blank_session() as db:
        config = AIAssistantConfig(
            id=str(uuid.uuid4()), enabled_tools=["crm_inventory_stock_balance_list"]
        )
        db.add(config)
        db.commit()

        summary = mod.run(db)

        assert summary["tool_added_to_ai_assistant_enabled_tools"] is True
        db.refresh(config)
        assert config.enabled_tools == [
            "crm_inventory_stock_balance_list", mod.TOOL_NAME,
        ]


def test_tool_present_is_untouched() -> None:
    """Idempotent on the second startup - and untouched, not merely "still contains it":
    the list is shared with every other module's tools, so a reorder or a dedupe here
    would silently change which tool another feature's selector reaches first."""
    mod = _bootstrap()
    with blank_session() as db:
        existing = [
            "crm_inventory_stock_balance_list", mod.TOOL_NAME, "crm_outstanding_report",
        ]
        config = AIAssistantConfig(id=str(uuid.uuid4()), enabled_tools=list(existing))
        db.add(config)
        db.commit()

        summary = mod.run(db)

        assert summary["tool_added_to_ai_assistant_enabled_tools"] is False
        db.refresh(config)
        assert config.enabled_tools == existing


def test_no_config_row_is_a_no_op() -> None:
    """A fresh install has no `AIAssistantConfig` row yet. The bootstrap runs at STARTUP,
    so raising here takes the whole API process down over a row the next startup would
    have found."""
    mod = _bootstrap()
    with blank_session() as db:
        summary = mod.run(db)

        assert summary["tool_added_to_ai_assistant_enabled_tools"] is False
        assert db.query(AIAssistantConfig).count() == 0


def test_a_failure_is_swallowed_not_raised() -> None:
    """Same posture as its twin: the bootstrap logs and returns rather than letting a
    transient DB error abort startup. Driven by handing it a session whose query blows
    up, which is the only failure mode the module actually guards."""
    mod = _bootstrap()

    class _Boom:
        def query(self, *a, **k):
            raise RuntimeError("database is away")

        def rollback(self):
            return None

    summary = mod.run(_Boom())
    assert summary["tool_added_to_ai_assistant_enabled_tools"] is False
