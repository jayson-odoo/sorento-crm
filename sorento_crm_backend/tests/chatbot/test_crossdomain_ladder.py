"""A7 - cross-domain ladder (AC-920 to AC-924).

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A;
`documentation/plans/chatbot/chatbot-growth-r1-acceptance-criteria.md` section B.

`run_crossdomain`'s existing inventory<->incoming hard pair is unchanged (AC-920); this
file covers what happens AFTER it finds nothing for a code - the new purchase_order rung,
gated by `system_settings.chatbot_crossdomain_ladder` (a plain dict here, never a DB
session; see `answer.py`'s own "no session held" rule).
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot.lanes.business.answer import run_crossdomain
from app.services.chatbot.lanes.business.services import AnswerServices

_PO_TOOL = "crm_procurement_purchase_orders_placed_list"
_INCOMING_TOOL = "crm_incoming_stock_list"

_PARSER = {
    "message_type": "business_query",
    "intent_hint": "check_stock",
    "domain_hint": "inventory",
    "user_goal": "check stock for SRTWC8517",
    "access_levels": [],
}


def _resolved_for(code: str, uuid: str) -> dict:
    return {
        "resolutions": [
            {
                "token": code,
                "matches": [
                    {
                        "entity_type": "product",
                        "canonical_code": code,
                        "uuid": uuid,
                        "match_tier": "exact",
                    }
                ],
            }
        ]
    }


def _validator_result(other_code: str = "SRTOTHER") -> dict:
    """A stock reply that never mentions the code under test - `crossdomain_zeroset`
    reads this as "asked for but not returned"."""
    return {
        "answers": [{"fields": [{"label": "Product Code", "value": other_code}]}],
        "response": "Some other stock line.",
    }


def _po_row(qty: Any, date: str, *, code: str = "SRTWC8517") -> dict:
    return {
        "fields": [
            {"key": "product_code", "label": "Product Code", "value": code},
            {"key": "outstanding_qty", "label": "Outstanding Qty", "value": qty},
            {"key": "expected_date", "label": "Expected Date", "value": date},
        ]
    }


def _run(
    *,
    ladder: dict[str, list[str]] | None,
    incoming_response: dict,
    po_response: dict | None = None,
    code: str = "SRTWC8517",
    uuid: str = "prod-uuid-1",
) -> tuple[dict, list[tuple[str, dict]]]:
    calls: list[tuple[str, dict]] = []

    def mcp_probe(name: str, args: dict) -> dict:
        calls.append((name, args))
        if name == _INCOMING_TOOL:
            return incoming_response
        if name == _PO_TOOL:
            return po_response if po_response is not None else {"answers": [], "has_result": False}
        raise AssertionError(f"unexpected probe tool: {name}")

    services = AnswerServices(mcp_probe=mcp_probe, family_fetch=lambda q: {"data": []})
    result = run_crossdomain(
        _validator_result(),
        parser=_PARSER,
        resolved=_resolved_for(code, uuid),
        session_block={"session_vars": {"variables": {}}},
        entities_names=None,
        services=services,
        contact_id="164838271",
        space_id="900001",
        crossdomain_ladder=ladder,
    )
    return result, calls


_LADDER_WITH_PO = {"inventory": ["incoming", "purchase_order"], "incoming": ["inventory"]}
_LADDER_NO_PO = {"inventory": ["incoming"], "incoming": ["inventory"]}


class TestAC920IncomingHasRowsUnchanged:
    def test_incoming_answers_no_po_probe_at_all(self) -> None:
        result, calls = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={
                "answers": [
                    {"fields": [
                        {"key": "product_code", "label": "Product Code", "value": "SRTWC8517"},
                        {"key": "estimated_arrival_date", "label": "ETA", "value": "2026-09-15"},
                    ]}
                ],
                "has_result": True,
            },
        )
        tool_names = [name for name, _ in calls]
        assert _PO_TOOL not in tool_names, "incoming answered - the PO rung must never run"
        block = result["render"]["_xdBlock"]["block"]
        assert "SRTWC8517" in block and "2026-09-15" in block


class TestAC921StockMissIncomingMissPOPlaced:
    def test_po_rung_renders_the_placed_line_and_escalate_offer(self) -> None:
        result, calls = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [_po_row(50, "2026-07-01")], "has_result": True},
        )
        tool_names = [name for name, _ in calls]
        assert tool_names == [_INCOMING_TOOL, _PO_TOOL]
        block = result["render"]["_xdBlock"]["block"]
        assert "No stock and no incoming for SRTWC8517" in block
        assert "but a PO is placed" in block
        assert "50" in block and "2026-07-01" in block
        assert "escalate" in block.lower()
        # AC-921: never the supplier, dealer or not - the PO rung's own template has no
        # supplier slot at all (see `_crossdomain_rung_rows`).
        assert "supplier" not in block.lower()
        assert "acme" not in block.lower()


class TestAC922StockMissIncomingMissPOMiss:
    def test_no_po_either_renders_the_three_way_miss(self) -> None:
        result, calls = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [], "has_result": False},
        )
        tool_names = [name for name, _ in calls]
        assert tool_names == [_INCOMING_TOOL, _PO_TOOL]
        block = result["render"]["_xdBlock"]["block"]
        assert "No stock, no incoming and no purchase order for SRTWC8517." in block
        assert "escalate" in block.lower()


class TestAC923LadderReadFromSetting:
    def test_tenant_ladder_with_no_po_rung_never_probes_po(self) -> None:
        result, calls = _run(
            ladder=_LADDER_NO_PO,
            incoming_response={"answers": [], "has_result": False},
        )
        tool_names = [name for name, _ in calls]
        assert tool_names == [_INCOMING_TOOL]
        block = result["render"]["_xdBlock"]["block"]
        # The pre-A7 wording, unchanged: no PO rung configured, no PO rung run.
        assert "No stock and no incoming for SRTWC8517." in block

    def test_no_ladder_at_all_is_the_pre_a7_single_probe(self) -> None:
        """`crossdomain_ladder=None` (a caller that never read the setting) behaves
        exactly as before A7 - one probe, the existing wording."""
        result, calls = _run(ladder=None, incoming_response={"answers": [], "has_result": False})
        tool_names = [name for name, _ in calls]
        assert tool_names == [_INCOMING_TOOL]
        assert "No stock and no incoming for SRTWC8517." in result["render"]["_xdBlock"]["block"]


class TestAC924ThirdCodeNeverDeclaredAbsentWithoutBeingAsked:
    def test_a_code_the_probe_never_asked_about_is_not_named(self) -> None:
        """H62 kept: `nothing` only ever names a code that HAD a uuid (was actually
        probed). A code with no uuid at all must never appear in the PO rung's message
        either - the rung reads `nothing_missing`, which `crossdomain_render` already
        filters the same way."""
        from app.services.chatbot.lanes.business.answer import crossdomain_render

        out = crossdomain_render(
            {"items": [], "has_result": True},
            zeroset={
                "active": True,
                "origin_domain": "inventory",
                "team": "warehouse",
                "missing": [
                    {"code": "SRTWC8517", "_n": "SRTWC8517", "uuid": "u1"},
                    # no uuid at all - never probed, must never be named as "nothing"
                    {"code": "UNPROBED-CODE", "_n": "UNPROBED-CODE", "uuid": None},
                ],
            },
            validator={},
        )
        assert out["_xdBlock"]["nothing_codes"] == ["SRTWC8517"]
        assert "UNPROBED-CODE" not in out["_xdBlock"]["block"]


class TestAC911SPOAllocationDomainNoLongerUnsupported:
    def test_spo_allocation_removed_goods_receive_stays(self) -> None:
        """AC-911: `spo_allocation` is no longer in `DEFAULT_UNSUPPORTED_DOMAINS`;
        `goods_receive` still is - `crm_procurement_spo_allocations_last_receipt_list` (A6)
        answers "last in" now, nothing in this plan reads GRN data."""
        from app.services.chatbot.head.route import DEFAULT_UNSUPPORTED_DOMAINS

        assert "spo_allocation" not in DEFAULT_UNSUPPORTED_DOMAINS
        assert "goods_receive" in DEFAULT_UNSUPPORTED_DOMAINS
