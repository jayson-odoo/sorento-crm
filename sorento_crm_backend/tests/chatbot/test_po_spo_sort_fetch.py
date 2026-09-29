"""RED tests - the fetch transformer maps sort per tool and defaults the SPO list.

`documentation/plans/chatbot/PLAN-po-spo-warehouse-29sep.md` sections S6, S7 (sort table);
`documentation/plans/chatbot/po-spo-warehouse-29sep-acceptance-criteria.md` AC-9, AC-10.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.chatbot.lanes.business import fetch

PO_TOOL = "crm_procurement_po_placed_list"
SPO_TOOL = "crm_procurement_spo_allocations_last_receipt_list"
PRODUCT_UUID = "11111111-1111-1111-1111-111111111111"
WAREHOUSE_UUID = "22222222-2222-2222-2222-222222222222"


def _args(tool: str, *, entities: list[dict] | None = None, **semantic: Any) -> dict[str, Any]:
    return fetch.entity_ids_transformer(
        {
            "entities": entities or [],
            "tool": tool,
            "semantic_input": {"contact_id": "1", "space_id": "s", **semantic},
        }
    )


def _product() -> dict[str, str]:
    return {"uuid": PRODUCT_UUID, "entity_type": "product", "code": "SRT79-SS"}


def _warehouse() -> dict[str, str]:
    return {"uuid": WAREHOUSE_UUID, "entity_type": "warehouse", "code": "BRW"}


class TestSortMapsPerTool:
    @pytest.mark.parametrize(
        ("sort_by", "sort", "dir_"),
        [
            ("date", "po_date", "desc"),
            ("expected_date", "expected_date", "asc"),
            ("quantity", "ordered_qty", "desc"),
            ("outstanding", "outstanding_qty", "desc"),
            ("product", "product", "asc"),
            # "supplier" is a RESTRICTED sort: `TestARestrictedSortNeedsTheGrant` below.
        ],
    )
    def test_po_tool_key_and_default_direction(self, sort_by: str, sort: str, dir_: str) -> None:
        out = _args(PO_TOOL, sort_by=sort_by)
        assert out.get("sort") == sort, out
        assert out.get("dir") == dir_, out

    @pytest.mark.parametrize(
        ("sort_by", "sort", "dir_"),
        [
            ("date", "spo_date", "desc"),
            ("expected_date", "spo_date", "asc"),
            ("quantity", "spo_quantity", "desc"),
            ("received_date", "gr_date", "desc"),
            ("received_quantity", "gr_quantity", "desc"),
        ],
    )
    def test_spo_tool_key_and_default_direction(self, sort_by: str, sort: str, dir_: str) -> None:
        out = _args(SPO_TOOL, sort_by=sort_by)
        assert out.get("sort") == sort, out
        assert out.get("dir") == dir_, out

    def test_a_parser_direction_wins_over_the_default(self) -> None:
        po = _args(PO_TOOL, sort_by="quantity", sort_dir="asc")
        assert po.get("sort") == "ordered_qty" and po.get("dir") == "asc", po
        spo = _args(SPO_TOOL, sort_by="date", sort_dir="asc")
        assert spo.get("sort") == "spo_date" and spo.get("dir") == "asc", spo

    def test_supplier_is_unmapped_on_the_spo_tool(self) -> None:
        out = _args(SPO_TOOL, sort_by="supplier")
        assert "sort" not in out and "dir" not in out, out

    def test_received_date_is_unmapped_on_the_po_tool(self) -> None:
        out = _args(PO_TOOL, sort_by="received_date")
        assert "sort" not in out and "dir" not in out, out

    def test_no_sort_asked_sends_neither(self) -> None:
        for tool in (PO_TOOL, SPO_TOOL):
            out = _args(tool)
            assert "sort" not in out and "dir" not in out, (tool, out)

    def test_another_tool_never_gets_sort_or_dir(self) -> None:
        out = _args("crm_inventory_stock_balance_list", sort_by="quantity", sort_dir="desc")
        assert "sort" not in out and "dir" not in out, out

    def test_the_maps_are_named_module_constants(self) -> None:
        assert hasattr(fetch, "SORT_KEY_BY_TOOL")
        assert hasattr(fetch, "SORT_DEFAULT_DIR")


class TestWarehouseAndListDefault:
    def test_a_warehouse_entity_becomes_warehouse_ids_on_the_po_tool(self) -> None:
        out = _args(PO_TOOL, entities=[_warehouse()])
        assert out.get("warehouse_ids") == [WAREHOUSE_UUID], out

    def test_no_lane_side_list_default_exists(self) -> None:
        """Owner ruling 29 Sep 2026, verbatim: "for SPO question with no product name, keep
        it as it is" - the tool's own one-row unscoped default answers, so the lane
        declares no row constant of its own (PLAN S7)."""
        assert not hasattr(fetch, "SPO_LIST_ROWS")

    def test_a_warehouse_only_spo_ask_sends_no_top_n(self) -> None:
        out = _args(SPO_TOOL, entities=[_warehouse()])
        assert out.get("warehouse_ids") == [WAREHOUSE_UUID], out
        assert "top_n" not in out, out

    def test_a_named_top_n_still_travels(self) -> None:
        out = _args(SPO_TOOL, entities=[_warehouse()], top_n=3)
        assert out.get("top_n") == 3, out

    def test_a_product_scoped_spo_ask_keeps_the_tool_default(self) -> None:
        out = _args(SPO_TOOL, entities=[_product()])
        assert out.get("product_ids") == [PRODUCT_UUID], out
        assert "top_n" not in out, out

    def test_a_product_and_warehouse_ask_adds_no_default_either(self) -> None:
        out = _args(SPO_TOOL, entities=[_product(), _warehouse()])
        assert "top_n" not in out, out


class TestARestrictedSortNeedsTheGrant:
    """Security review on PR #1373, finding 1: `sort_by "supplier"` orders a dealer's PO rows
    by a field they may not see (the same side channel the restricted-field drop refuses
    for `group_by=supplier`), so the sort is not sent without `purchase_orders.supplier`."""

    def _trigger(self, attributes: list[str]) -> dict[str, Any]:
        return {
            "entities": [],
            "tool": PO_TOOL,
            "semantic_input": {"contact_id": "1", "space_id": "s", "sort_by": "supplier"},
            "access": {"attributes": attributes},
        }

    def test_without_the_grant_no_sort_is_sent(self) -> None:
        out = fetch.entity_ids_transformer(self._trigger([]))
        assert "sort" not in out and "dir" not in out, out

    def test_with_the_grant_the_supplier_sort_is_sent(self) -> None:
        out = fetch.entity_ids_transformer(self._trigger(["purchase_orders.supplier"]))
        assert out.get("sort") == "supplier" and out.get("dir") == "asc", out

    def test_an_unrestricted_sort_needs_no_grant(self) -> None:
        trigger = self._trigger([])
        trigger["semantic_input"]["sort_by"] = "date"
        out = fetch.entity_ids_transformer(trigger)
        assert out.get("sort") == "po_date", out

    def test_the_map_names_the_presenters_own_key(self) -> None:
        assert fetch.RESTRICTED_SORT_KEYS == {PO_TOOL: {"supplier": "purchase_orders.supplier"}}


class TestTheSortReachesTheFetchOnALiveTurn:
    """Reviewer blocker 1 on PR #1373: `lanes/business._fetch_semantic_input` builds the
    fetch's input from a FIXED key list, and without `sort_by` / `sort_dir` on it the
    transformer read None on every live turn while the hand-built tests above stayed
    green. Goes through the builder, exactly as `test_parser_growth_r1_reachability` does
    for `group_by` / `top_n`."""

    def test_the_two_keys_are_on_the_fetch_semantic_input(self) -> None:
        from app.services.chatbot.lanes.business import _fetch_semantic_input

        semantic = _fetch_semantic_input(
            {"domain_hint": "purchase_order", "sort_by": "quantity", "sort_dir": "desc"},
            tier_gate=None,
            contact_id="1",
            space_id="s",
        )
        assert semantic.get("sort_by") == "quantity" and semantic.get("sort_dir") == "desc", semantic
        out = fetch.entity_ids_transformer(
            {"entities": [], "tool": PO_TOOL, "semantic_input": semantic}
        )
        assert out.get("sort") == "ordered_qty" and out.get("dir") == "desc", out
