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


def test_bootstrap_replays_the_r4b_applier() -> None:
    text = (BACKEND / "scripts" / "bootstrap_env.py").read_text()
    assert "or_r4b_top_selling_off" in text


# ---- guards that stay green: the route, MCP tool and analytics connector keep the tool ----


def test_mcp_catalog_still_registers_the_tool() -> None:
    from sorento_crm_mcp import catalog

    names = {s["name"] if isinstance(s, dict) else getattr(s, "name", None) for s in catalog.TOOL_SPECS} \
        if hasattr(catalog, "TOOL_SPECS") else set()
    if not names:
        assert OLD_TOOL in Path(catalog.__file__).read_text()
    else:
        assert OLD_TOOL in names


def test_mcp_tool_domains_still_maps_the_tool() -> None:
    assert OLD_TOOL in (BACKEND / "app" / "services" / "mcp_tool_domains.py").read_text()


def test_analytics_connector_still_names_the_tool() -> None:
    assert OLD_TOOL in (BACKEND / "app" / "services" / "analytics_connector" / "reused_tools.py").read_text()
