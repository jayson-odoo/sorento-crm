"""REPORT-SMART-L one ranking, round R4b (AC-OR4): crm_top_selling_report leaves the chatbot POLICY.

The route, the MCP tool and the analytics connector stay; the chatbot's frozen seed, allow-list and key
maps stop naming the tool, and `crm_report_ask` joins the sales row. Fake names only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

OLD_TOOL = "crm_top_selling_report"
ASK = "crm_report_ask"
BACKEND = Path(__file__).resolve().parents[2]


def _rows():
    from app.services.chatbot.turn import policy_rows

    return policy_rows


def test_seed_rows_do_not_name_the_old_tool() -> None:
    offenders = [r["name"] for r in _rows().DEFAULT_DOMAIN_ROWS if OLD_TOOL in (r.get("tools") or [])]
    assert offenders == []


def test_date_param_tools_drop_the_old_tool() -> None:
    assert OLD_TOOL not in _rows().DATE_PARAM_TOOLS


def test_sales_row_gains_report_ask_and_order_row_keeps_it() -> None:
    by_name = {r["name"]: r for r in _rows().DEFAULT_DOMAIN_ROWS}
    assert ASK in by_name["sales"]["tools"]
    assert ASK in by_name["order"]["tools"]


def test_allow_list_and_customer_scope_exclude_the_old_tool() -> None:
    from app.services.chatbot.lanes.business import fetch

    assert OLD_TOOL not in fetch.CHATBOT_READ_ONLY_TOOLS
    assert OLD_TOOL not in fetch.CUSTOMER_SCOPED_TOOLS
    assert ASK in fetch.CHATBOT_READ_ONLY_TOOLS


def test_fetch_refuses_the_old_tool_as_not_allowed() -> None:
    from app.services.chatbot.lanes.business import fetch

    with pytest.raises(fetch.ToolNotAllowed):
        fetch.ensure_read_only(OLD_TOOL)
    with pytest.raises(fetch.ToolNotAllowed):
        fetch.call_tool(OLD_TOOL, {}, mcp=object())


def test_contract_key_maps_do_not_name_the_old_tool() -> None:
    from app.services.chatbot import contracts

    maps = [v for v in vars(contracts).values() if isinstance(v, dict)]
    holders = [m for m in maps if OLD_TOOL in m]
    assert holders == []


def test_bootstrap_replays_the_r4b_applier(monkeypatch) -> None:
    """Behavioural: the bootstrap's chatbot policy seed, replayed on a blank schema inside a rolled-back
    transaction (its `engine.begin()` blocks are pointed at the session's connection), ends with no
    chatbot_domains row listing the old tool and `crm_report_ask` on the sales row."""
    from contextlib import contextmanager

    import sqlalchemy as sa

    import app.database
    from scripts import bootstrap_env
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        conn = db.connection()

        class _Engine:
            @contextmanager
            def begin(self):
                yield conn

        monkeypatch.setattr(app.database, "engine", _Engine())
        bootstrap_env.seed_chatbot_policy()
        rows = dict(db.execute(sa.text("SELECT name, tools FROM chatbot_domains")).all())
    assert [n for n, t in rows.items() if OLD_TOOL in t] == []
    assert "crm_report_ask" in rows["sales"], rows["sales"]


# ---- REPORT-UNIFY (Q1): the route stays; the MCP tool, its domain row and the analytics connector entry are gone ----


def test_mcp_catalog_no_longer_registers_the_tool() -> None:
    from sorento_crm_mcp import catalog

    assert OLD_TOOL not in {spec.name for spec in catalog.CATALOG}


def test_mcp_tool_domains_no_longer_maps_the_tool() -> None:
    assert OLD_TOOL not in (BACKEND / "app" / "services" / "mcp_tool_domains.py").read_text()


def test_analytics_connector_no_longer_names_the_tool() -> None:
    assert OLD_TOOL not in (BACKEND / "app" / "services" / "analytics_connector" / "reused_tools.py").read_text()
