"""A3/A6 - `entity_ids_transformer` passes `order_status=so_outstanding`,
`group_by` and `top_n` through to the tools that take them (AC-905, AC-909, AC-910).

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A;
`documentation/plans/chatbot/chatbot-growth-r1-acceptance-criteria.md` section A.
"""
from __future__ import annotations

from app.services.chatbot.lanes.business import fetch


def test_so_outstanding_bucket_passed_through():
    trigger = {
        "entities": [],
        "tool": "crm_order_management_orders_list",
        "semantic_input": {"order_status": "so_outstanding", "contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert out["order_status"] == "so_outstanding"


def test_group_by_passed_through_for_orders_tool():
    trigger = {
        "entities": [],
        "tool": "crm_order_management_orders_list",
        "semantic_input": {"group_by": "transporter", "contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert out["group_by"] == "transporter"


def test_group_by_absent_when_not_asked():
    trigger = {
        "entities": [],
        "tool": "crm_order_management_orders_list",
        "semantic_input": {"contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert "group_by" not in out


def test_top_n_aliases_to_limit_for_orders_tool():
    trigger = {
        "entities": [],
        "tool": "crm_order_management_orders_list",
        "semantic_input": {"top_n": 3, "contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert out["limit"] == 3
    assert "top_n" not in out


def test_top_n_stays_top_n_for_spo_last_receipt_tool():
    trigger = {
        "entities": [],
        "tool": "crm_procurement_spo_allocations_last_receipt_list",
        "semantic_input": {"top_n": 3, "contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert out["top_n"] == 3
    assert "limit" not in out


def test_group_by_absent_for_a_tool_that_does_not_take_it():
    trigger = {
        "entities": [],
        "tool": "crm_master_products_list",
        "semantic_input": {"group_by": "customer", "contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert "group_by" not in out
