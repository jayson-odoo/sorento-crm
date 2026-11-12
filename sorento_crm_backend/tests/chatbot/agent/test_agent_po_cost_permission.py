"""SUPPLIER-COST-ACCESS (#2319): the agent's last-PO-cost tool answers to the same cost permission as the screens.

Moved from tests/test_supplier_cost_access.py (MAIN-RED-11NOV): it reads the chatbot package's `agent.tools`
registry, which only tests under tests/chatbot/ may import (tests/chatbot/test_import_boundary.py).
"""
from __future__ import annotations

COST_PERM = "products.cost.view"


def test_po_cost_reveals_answer_to_the_cost_permission():
    from app.services.chatbot.agent import tools
    from app.services.contact_field_reveal_service import _STAFF_REVEAL_SLUGS

    assert _STAFF_REVEAL_SLUGS["purchase_orders.cost"] == COST_PERM
    assert tools.REGISTRY["crm_procurement_po_last_cost_list"].user_permission == COST_PERM
