"""TRACE-ENTITY-TOOL, end to end: a stock check on a typed product code (turn #8322's shape,
"srtwc286") stores a `resolve` event and the drawer names the stock tool with its ms.

Harness copied from `test_rearch_r5_production_decides.py` (real resolver over seeded rows, only
`FetchServices.mcp_call` doubled). Postgres only.
"""
from __future__ import annotations

import json
from typing import Any

from app.models.chatbot_turn import ChatbotTurn
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.chatbot.trace_detail import compose_trace_detail
from tests._pg_fixture import unique_code
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_engine_company_scope import _seed_product
from tests.chatbot.test_rearch_r5_production_decides import (
    _mcp_double,
    _run_turn_with_mcp_call,
    _seed_contact_and_get,
)
from tests.chatbot.test_outstanding_lane import _present_response

STOCK_TOOL = "crm_inventory_stock_balance_list"


def test_stock_check_trace_names_the_tool_and_the_matched_code(session_factory, monkeypatch) -> None:
    _seed_contact_and_get(session_factory)
    code = unique_code("ZZTTET")
    _seed_product(session_factory, company_id=DEFAULT_COMPANY_ID, code=code)
    qf = _parser_output(
        domain_hint="inventory",
        intent_hint="check_stock",
        entities=[{"raw": code.lower(), "hint": "product", "canonical_code": None, "current_message": True,
                   "confident": True}],
    )

    def _other(name: str, args: dict[str, Any]) -> str:
        if name == STOCK_TOOL:
            row = {"product_code": code, "total_qty": 5, "outstanding_qty": 0,
                   "warehouse_allocations": [{"warehouse_code": "ZZT-WH", "qty": 5}]}
            return _present_response()(name, json.dumps({"data": [row]}))
        return json.dumps({"has_result": False, "items": []})

    mcp_call, captured = _mcp_double(other=_other)
    _run_turn_with_mcp_call(
        session_factory, monkeypatch, qf=qf, text_body=code.lower(), msg_id="zzt-trace-entity-tool",
        mcp_call=mcp_call,
    )
    assert any(name == STOCK_TOOL for name, _ in captured), captured

    db = session_factory()
    try:
        row = db.query(ChatbotTurn).order_by(ChatbotTurn.created_at.desc()).first()
        records = [r for r in (row.trace or []) if isinstance(r, dict)]
        resolve = [r for r in records if r.get("kind") == "resolve"]
        assert len(resolve) == 1, [r.get("kind") for r in records if r.get("kind")]
        words = resolve[0]["words"]
        assert any(code in w["codes"] for w in words), words
        assert all(w["tiers"] for w in words if w["codes"]), words

        detail = compose_trace_detail(row, db)
        assert detail["tool"] is not None, [r for r in records if r.get("kind") == "tool"]
        assert detail["tool"]["name"] == STOCK_TOOL
        assert isinstance(detail["tool"]["ms"], int)
        assert detail["entity_match"]["words"]
    finally:
        db.close()
