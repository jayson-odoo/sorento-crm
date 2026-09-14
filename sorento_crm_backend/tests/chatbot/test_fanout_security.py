"""Lane 2 fan-out - SECURITY reds (external-ingest grant/narrowing bypass).

The single-domain fetch body (`run_fetch`, lines ~1166-1245) applies three refusals BEFORE
it calls a tool: the `sales_orders.outstanding` field-reveal gate (D13), the
`ENTITY_FILTER_REQUIRED_TOOLS` unfiltered-listing refusal, and its `PRODUCT_ID_REQUIRED_TOOLS`
narrowing of that bar. The fan read `_fetch_one_domain` applies ONLY
`DOMAIN_GRANT_REQUIRED`; it passes `semantic_input` (which carries `order_status`) straight
to `entity_ids_transformer` and calls the tool with no narrowing check. So a two-domain ask
that routes one of its sections through a gated tool reaches that tool ungated - the same
data the single-domain path refuses.

Every test drives a real fan turn through `engine.run_turn` with a recording MCP (the
`_drive` harness in `test_fanout_worlds.py`) and asserts on the ARGS the tool was actually
called with. RED today: the fan calls the tool ungated.
"""
from __future__ import annotations

import json
from typing import Any


from app.services.chatbot.contracts import DOMAIN_SPEC
from app.services.chatbot.lanes import business
from app.services.chatbot.lanes.business.services import FetchServices
from app.services.chatbot.trace import TurnTrace
from tests.chatbot.test_engine import (  # noqa: F401 - fixtures used by name
    seeded,
    stub_access,
    stub_parser,
)
from tests.chatbot.test_fanout_worlds import (  # noqa: F401 - harness reused by name
    _INVENTORY_TOOL,
    _ORDER_TOOL,
    _ask,
    _drive,
    _found,
    _one_match,
    _uuid_for,
    _v3_business,
)

_RESOURCE_TOOL = DOMAIN_SPEC["resource_attachment"].tools[0]  # crm_resource_attachments_list
_COST_TOOL = DOMAIN_SPEC["purchase_cost"].tools[0]  # crm_procurement_po_last_cost_list

# Every entity-id param `entity_ids_transformer` can emit - one of these present is what
# `has_narrowing_filter` reads as "the customer named something we could scope to".
_ENTITY_ID_KEYS = {
    "product_ids",
    "promotion_ids",
    "order_ids",
    "customer_ids",
    "transporter_ids",
    "form_ids",
    "shipment_ids",
    "attachment_type_ids",
    "attachment_ids",
    "certificate_ids",
}


# --------------------------------------------------------------------------- #
# SB1 - the sales_orders.outstanding gate applies per fanned domain
# --------------------------------------------------------------------------- #


def test_so_outstanding_grant_applies_per_fanned_domain(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """SB1: a contact WITHOUT `sales_orders.outstanding` fans an order ask carrying
    `order_status = so_outstanding` alongside a stock ask. The single-domain body redirects
    the SO scope to the DO bucket (`order_status -> outstanding`, `so_bucket_refused`), so no
    per-SO outstanding quantity reaches the customer (test_outstanding_lane.py's own
    `test_no_so_key_customer_only_so_ask_falls_to_do_bucket`).

    RED: `_fetch_one_domain` never runs that gate, so the order section calls
    `crm_order_management_orders_list` with `order_status = so_outstanding` straight through -
    the exact per-SO figure D13 exists to withhold, leaked through the fan.
    """
    code = "SRTWT2634"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business(
            [_ask("order", code), _ask("inventory", code)],
            intent_hint="check_order",
            order_status="so_outstanding",
        ),
        matches_by_code={code: _one_match(code)},
        tool_responses={_ORDER_TOOL: _found(code), _INVENTORY_TOOL: _found(code)},
        grants=[],  # sales_orders.outstanding is NOT held
    )
    assert turn.result.status == "done", turn.result.error
    order_args = turn.call_args(_ORDER_TOOL)
    assert order_args is not None, "the order section must read (the DO bucket still runs)"
    assert order_args.get("order_status") != "so_outstanding", (
        "without the grant the SO scope must be refused before the read - the fan leaked "
        f"the per-SO outstanding bucket: {order_args!r}"
    )


# --------------------------------------------------------------------------- #
# The run_fetch fan driver for SB2/SS3.
#
# Driven at `run_fetch` (the fan seam) rather than through the whole engine so the gated
# section has GENUINELY no narrowing entity: `gate.compatible_entities` is empty, so no
# `*_ids` filter can be built for it - the exact "nothing resolved" shape the single-domain
# refusal test `test_s6b_fetch_lane.py::...never_ships_unfiltered` feeds. Driving it through
# the whole engine instead lets an unbound ask fall through to "read every resolved entity"
# (`_codes_bound_to` returns None for an ask with no entities), which would narrow the
# section with the OTHER ask's product and hide the leak.
# --------------------------------------------------------------------------- #


def _run_fanned_read(
    gated_domain: str, *, grants: list[str]
) -> list[tuple[str, dict[str, Any]]]:
    """Fan `[gated_domain, inventory]` with NOTHING resolved, and return the recorded calls.

    Both sections read over an empty entity set. `inventory` is the second domain purely so
    `len(fan_domains) >= 2` and the fan path runs; the assertion is about the GATED tool.
    """
    trace = TurnTrace()
    trace.start()
    calls: list[tuple[str, dict[str, Any]]] = []

    def _rec(name: str, args: dict[str, Any]) -> str:
        calls.append((name, dict(args)))
        return json.dumps(_found("X"))

    asks = [
        {"domain": gated_domain, "entities": []},
        {"domain": "inventory", "entities": []},
    ]
    payload = {
        "_exit_kind": "continue",
        "gate": {"compatible_entities": []},  # nothing resolved -> no filter can be built
        "ctx": {
            "parse": {
                "output": {"domain_hint": gated_domain, "asks": asks},
                "_focus": {"domains": {"value": [gated_domain, "inventory"]}},
            },
            "access": {"attributes": list(grants)},
            "contact": {"id": "ZZT-fanout-sec-contact"},
        },
    }
    business.run_fetch(
        payload, services=FetchServices(mcp_call=_rec), dry_run=False, trace=trace
    )
    return calls


def _args_for(calls: list[tuple[str, dict[str, Any]]], tool: str) -> dict[str, Any] | None:
    for name, args in calls:
        if name == tool:
            return args
    return None


# --------------------------------------------------------------------------- #
# SB2 - an ENTITY_FILTER_REQUIRED tool is refused, never listed unfiltered
# --------------------------------------------------------------------------- #


def test_entity_filter_required_tool_is_refused_in_a_fanned_section() -> None:
    """SB2: a fan section over `resource_attachment` (`crm_resource_attachments_list`, an
    `ENTITY_FILTER_REQUIRED_TOOLS` tool) with NO narrowing filter. The single-domain body
    refuses it as `not_found` ("never a listing of every file the contact may see").

    RED: `_fetch_one_domain` has no such check, so the fan calls the tool with only
    `view`/`contact_id`/`space_id` - an unfiltered listing of every attachment the contact
    may read.
    """
    calls = _run_fanned_read("resource_attachment", grants=[])
    att_args = _args_for(calls, _RESOURCE_TOOL)
    assert att_args is None or (_ENTITY_ID_KEYS & set(att_args)), (
        "crm_resource_attachments_list must be refused (not called) when nothing narrows it "
        f"- the fan called it unfiltered: {att_args!r}"
    )


# --------------------------------------------------------------------------- #
# SS3 - PRODUCT_ID narrowing applies in a fanned purchase_cost section
# --------------------------------------------------------------------------- #


def test_product_id_required_narrowing_in_a_fanned_section() -> None:
    """SS3 (lower severity): a GRANTED contact fans `purchase_cost`
    (`crm_procurement_po_last_cost_list`, a `PRODUCT_ID_REQUIRED_TOOLS` tool) with no product
    filter. The single-domain body refuses it unless `product_ids` is present (SF6: the
    unscoped branch is a plain top-N over every product, an unnamed-product leak).

    RED: `_fetch_one_domain` calls it with no `product_ids` - the unscoped top-N.
    """
    calls = _run_fanned_read("purchase_cost", grants=["purchase_orders.cost"])
    cost_args = _args_for(calls, _COST_TOOL)
    assert cost_args is None or cost_args.get("product_ids"), (
        "crm_procurement_po_last_cost_list must be refused (not called) with no product_ids "
        f"- the fan called it unscoped (top-N over every product): {cost_args!r}"
    )
