"""Growth r1 Slice A: the three new answers are REACHABLE from a WhatsApp message.

AC-905 (SO outstanding bucket), AC-907 (PO placed), AC-908 (SPO last receipt),
AC-909 / AC-910 (`group_by` / `top_n`), AC-911 (`spo_allocation` unblocked).

Slice A's first pass built the tools, the routes and the presenters, and left the head
alone. That is a complete backend and an unreachable feature: the parser never emits the
`so_outstanding` bucket, never emits `purchase_order`, never emits an axis or a count, and
a `spo_allocation` turn could not even retrieve its own tool. This file grades the CHAIN a
customer's sentence travels, one link at a time, with no LLM anywhere:

    prompt vocabulary -> strict provider schema -> post-process -> semantic_input
    -> entity_ids_transformer -> the tool's own arguments

plus the two gates that can silently swallow a turn before any of it runs: the router's
`not_supported` list, and the `source_id LIKE '%<domain>%'` filter the tool search narrows
on.

Whether the MODEL obeys the new vocabulary is a different question and a different gate -
the shadow window (AC-952). What is pinned here is that if it obeys, the answer arrives.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.chatbot import contracts
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.head.route import DEFAULT_UNSUPPORTED_DOMAINS, decide
from app.services.chatbot.lanes.business import _fetch_semantic_input
from app.services.chatbot.lanes.business.fetch import (
    CHATBOT_READ_ONLY_TOOLS,
    entity_ids_transformer,
)
from app.services.chatbot_parser_prompt import (
    GROWTH_R1_ADDENDUM,
    SEMANTIC_PARSER_PROMPT,
    SEMANTIC_PARSER_PROMPT_SLIM,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES = REPO_ROOT / "documentation" / "plans" / "chatbot" / "samples"
PHRASES_FILE = SAMPLES / "parser-growth-r1-phrases.json"

PO_TOOL = "crm_procurement_purchase_orders_placed_list"
SPO_TOOL = "crm_procurement_spo_allocations_last_receipt_list"
ORDERS_TOOL = "crm_order_management_orders_list"

GROUP_BY_AXES = ("customer", "transporter", "date", "product", "warehouse", "supplier")


def _phrases() -> list[dict[str, Any]]:
    return json.loads(PHRASES_FILE.read_text(encoding="utf-8"))["phrases"]


def _parse_output(**overrides: Any) -> dict[str, Any]:
    """A post-processed parse output, in the shape `_fetch_semantic_input` reads."""
    base: dict[str, Any] = {
        "message_type": "business_query",
        "intent_hint": None,
        "domain_hint": None,
        "user_goal": None,
        "access_levels": [],
        "date_mode": None,
        "date_filter_start": None,
        "date_filter_end": None,
        "is_active": None,
        "order_status": None,
        "requested_attributes": [],
    }
    base.update(overrides)
    return base


def _tool_args(parse_output: dict[str, Any], *, tool: str, entities: list[dict] | None = None) -> dict:
    """The MCP arguments a turn with this parse would send, through both real steps."""
    semantic_input = _fetch_semantic_input(
        parse_output, tier_gate=None, contact_id="437264483", space_id=None
    )
    return entity_ids_transformer(
        {"tool": tool, "semantic_input": semantic_input, "entities": entities or []}
    )


# --------------------------------------------------------------------------- #
# The wire shape: two new keys, declared once, held to at the provider.
# --------------------------------------------------------------------------- #


class TestTheSchemaDeclaresTheTwoNewKeys:
    def test_group_by_and_top_n_are_properties_and_required(self) -> None:
        schema = parser_mod.PARSE_OUTPUT_JSON_SCHEMA
        for key in ("group_by", "top_n"):
            assert key in schema["properties"], f"{key} is not declared in the schema"
            assert key in schema["required"], (
                f"{key} is declared but not required - a strict json_schema only GUARANTEES "
                "a key the provider must emit, and an optional one is exactly the silent "
                "`None` the schema exists to prevent"
            )

    def test_group_by_is_the_six_axes_and_null(self) -> None:
        assert parser_mod.PARSE_OUTPUT_JSON_SCHEMA["properties"]["group_by"]["enum"] == [
            *GROUP_BY_AXES,
            None,
        ]

    def test_top_n_is_an_integer_or_null(self) -> None:
        assert parser_mod.PARSE_OUTPUT_JSON_SCHEMA["properties"]["top_n"] == {
            "type": ["integer", "null"]
        }

    def test_a_pre_growth_r1_emission_still_post_processes(self) -> None:
        """AC-910's compatibility half. Every captured raw emission predates these keys, so
        `_assert_emission` must not require them or the whole replay corpus dies at the
        first line of the post-processor."""
        from app.services.chatbot.head.output_exchange import _required_emission_keys

        required = _required_emission_keys()
        assert "group_by" not in required
        assert "top_n" not in required


# --------------------------------------------------------------------------- #
# The prompt: the vocabulary that makes the model emit them.
# --------------------------------------------------------------------------- #


class TestBothPublishedBodiesCarryTheVocabulary:
    def test_the_addendum_is_appended_to_both_bodies(self) -> None:
        """Migration 490 publishes BOTH texts because prod's `production` label is on the
        FULL body and dev's is on the SLIM one."""
        assert SEMANTIC_PARSER_PROMPT.endswith(GROWTH_R1_ADDENDUM)
        assert SEMANTIC_PARSER_PROMPT_SLIM.endswith(GROWTH_R1_ADDENDUM)

    @pytest.mark.parametrize("key", ["group_by", "top_n"])
    def test_the_output_block_declares_each_new_key(self, key: str) -> None:
        for body in (SEMANTIC_PARSER_PROMPT, SEMANTIC_PARSER_PROMPT_SLIM):
            assert f'"{key}"' in body

    @pytest.mark.parametrize("value", ["so_outstanding", "purchase_order", "check_po"])
    def test_the_new_enum_values_are_named(self, value: str) -> None:
        for body in (SEMANTIC_PARSER_PROMPT, SEMANTIC_PARSER_PROMPT_SLIM):
            assert value in body

    @pytest.mark.parametrize("sample", _phrases(), ids=lambda s: s["phrase"])
    def test_every_sample_cue_is_taught_by_the_prompt(self, sample: dict) -> None:
        """The cue is quoted in the addendum, so both published bodies teach it."""
        assert f'"{sample["cue"]}"' in GROWTH_R1_ADDENDUM, (
            f"{sample['phrase']!r} is a corpus sample whose cue {sample['cue']!r} no prompt "
            "body teaches - the model has no way to produce the expected parse"
        )

    @pytest.mark.parametrize("sample", _phrases(), ids=lambda s: s["phrase"])
    def test_every_sample_expects_declared_vocabulary(self, sample: dict) -> None:
        expect = sample["expect"]
        assert expect["domain_hint"] in contracts.DOMAIN_HINTS
        assert expect["intent_hint"] in contracts.INTENT_HINTS
        if "order_status" in expect:
            assert expect["order_status"] in ("outstanding", "delivered", "so_outstanding")
        if "group_by" in expect:
            assert expect["group_by"] in GROUP_BY_AXES
        if "top_n" in expect:
            assert isinstance(expect["top_n"], int) and expect["top_n"] > 0

    def test_the_samples_cover_every_capability_slice_a_added(self) -> None:
        buckets = {
            (s["expect"].get("order_status"), s["expect"]["domain_hint"]) for s in _phrases()
        }
        domains = {s["expect"]["domain_hint"] for s in _phrases()}
        assert ("so_outstanding", "order") in buckets
        assert {"purchase_order", "spo_allocation", "order"} <= domains
        assert {s["expect"].get("group_by") for s in _phrases()} >= {
            "customer",
            "transporter",
            "warehouse",
            "supplier",
        }
        assert {s["expect"].get("top_n") for s in _phrases()} >= {3, 5}


# --------------------------------------------------------------------------- #
# AC-905: the SO bucket reaches the orders tool.
# --------------------------------------------------------------------------- #


class TestSOOutstandingReachesTheOrdersTool:
    def test_the_bucket_lands_on_the_orders_tool_arguments(self) -> None:
        args = _tool_args(
            _parse_output(
                domain_hint="order", intent_hint="check_order", order_status="so_outstanding"
            ),
            tool=ORDERS_TOOL,
        )
        assert args["order_status"] == "so_outstanding"

    def test_group_by_lands_beside_it(self) -> None:
        args = _tool_args(
            _parse_output(
                domain_hint="order",
                intent_hint="check_order",
                order_status="so_outstanding",
                group_by="customer",
            ),
            tool=ORDERS_TOOL,
        )
        assert args["order_status"] == "so_outstanding"
        assert args["group_by"] == "customer"

    def test_a_parse_that_names_no_axis_sends_no_group_by(self) -> None:
        """The key is ABSENT, never null: the MCP payload of a plain DO list is unchanged."""
        args = _tool_args(
            _parse_output(
                domain_hint="order", intent_hint="check_order", order_status="outstanding"
            ),
            tool=ORDERS_TOOL,
        )
        assert "group_by" not in args
        assert "limit" not in args

    def test_top_n_becomes_limit_on_the_orders_tool(self) -> None:
        args = _tool_args(
            _parse_output(
                domain_hint="order", intent_hint="check_order", order_status="outstanding", top_n=5
            ),
            tool=ORDERS_TOOL,
        )
        assert args["limit"] == 5
        assert "top_n" not in args


# --------------------------------------------------------------------------- #
# AC-907: check_po reaches the PO tool.
# --------------------------------------------------------------------------- #


class TestCheckPoReachesThePurchaseOrderTool:
    def test_the_domain_and_intent_are_declared_vocabulary(self) -> None:
        assert "purchase_order" in contracts.DOMAIN_HINTS
        assert "check_po" in contracts.INTENT_HINTS

    def test_the_domain_survives_the_coercion_guard(self) -> None:
        """`coerce_domain_hint` nulls anything outside the enum, and a nulled domain drops
        the tool-search filter entirely (turn b5b19cec)."""
        assert contracts.coerce_domain_hint("purchase_order") == "purchase_order"

    def test_the_domain_is_supported_by_default(self) -> None:
        assert "purchase_order" not in DEFAULT_UNSUPPORTED_DOMAINS

    def test_a_po_turn_routes_to_the_business_lane_not_not_supported(self) -> None:
        branch, _ = decide(
            {
                "parse": {
                    "output": {
                        "message_type": "business_query",
                        "intent_hint": "check_po",
                        "domain_hint": "purchase_order",
                        "entities": [{"raw": "SRTWC8517", "hint": "product"}],
                        "escalation": {},
                    }
                },
                "access": {"allowed": True},
                "contact": {"custom_fields": []},
            }
        )
        assert branch == "business_query"

    def test_the_tool_is_callable_and_takes_the_product_entity(self) -> None:
        assert PO_TOOL in CHATBOT_READ_ONLY_TOOLS
        uuid = "11111111-2222-3333-4444-555555555555"
        args = _tool_args(
            _parse_output(domain_hint="purchase_order", intent_hint="check_po", group_by="supplier"),
            tool=PO_TOOL,
            entities=[{"entity_type": "product", "uuid": uuid, "code": "SRTWC8517"}],
        )
        assert args["product_ids"] == [uuid]
        assert args["group_by"] == "supplier"


# --------------------------------------------------------------------------- #
# AC-908 / AC-911: check_spo reaches the SPO last-receipt tool.
# --------------------------------------------------------------------------- #


class TestCheckSpoReachesTheLastReceiptTool:
    def test_the_domain_is_supported_and_goods_receive_still_is_not(self) -> None:
        assert "spo_allocation" not in DEFAULT_UNSUPPORTED_DOMAINS
        assert "goods_receive" in DEFAULT_UNSUPPORTED_DOMAINS

    def test_the_tool_is_callable(self) -> None:
        assert SPO_TOOL in CHATBOT_READ_ONLY_TOOLS

    def test_top_n_stays_top_n_on_this_tool(self) -> None:
        """The only tool with a `top_n` parameter of its own; every other list tool aliases
        the same parser key to `limit`."""
        uuid = "11111111-2222-3333-4444-555555555555"
        args = _tool_args(
            _parse_output(domain_hint="spo_allocation", intent_hint="check_spo", top_n=3),
            tool=SPO_TOOL,
            entities=[{"entity_type": "product", "uuid": uuid, "code": "SRTWC8517"}],
        )
        assert args["top_n"] == 3
        assert "limit" not in args
        assert args["product_ids"] == [uuid]

    def test_the_product_entity_is_not_blocked_by_the_domain(self) -> None:
        """A6 unblocked the domain; the blocklist still dropped the only thing that narrows
        the read, so "last in for SRTWC8517" answered about everything."""
        from app.services.chatbot.head.output_exchange import DOMAIN_BLOCKED_HINTS

        assert "product" not in DOMAIN_BLOCKED_HINTS["spo_allocation"]


# --------------------------------------------------------------------------- #
# The gate that silently swallows a turn before any of the above runs.
# --------------------------------------------------------------------------- #


DOMAIN_TOOLS: dict[str, tuple[str, ...]] = {
    "master_products": ("crm_master_products_list",),
    "product_attachment": ("crm_master_product_attachments_list",),
    "promotion": ("crm_marketing_promotions_list",),
    "forms": ("crm_forms_management_forms_list",),
    "inventory": ("crm_inventory_stock_balance_list",),
    "order": ("crm_order_management_orders_list",),
    "incoming": ("crm_incoming_stock_list",),
    "portal_link": ("crm_portal_link_get",),
    "resource_attachment": ("crm_resource_attachments_list",),
    "spo_allocation": (SPO_TOOL,),
    "purchase_order": (PO_TOOL,),
}


@pytest.mark.parametrize("domain,tools", sorted(DOMAIN_TOOLS.items()))
def test_every_domain_can_retrieve_at_least_one_of_its_own_tools(
    domain: str, tools: tuple[str, ...]
) -> None:
    """`EmbeddingReadService.search_tool_chunks` narrows the candidate pool with
    `source_id LIKE '%<domain_hint>%'` over `implemented::<tool name>`. That is a SUBSTRING
    match on the tool's NAME, not a mapping - `ToolSpec.domain` in the MCP catalogue is
    documentation and nothing reads it at retrieval time - so a domain whose tools do not
    contain its own name can never retrieve any of them and every turn in it ends
    `not_found` with no error anywhere.

    Both known instances of this failure are growth r1's: turn b5b19cec
    (`domain_hint: "purchasing"`, a team name, matching no tool) and A6's own
    `crm_procurement_spo_last_receipt_list`, which the `spo_allocation` filter could not
    match until it was renamed to `..._spo_allocations_last_receipt_list`.

    `goods_receive` and `ideate` are absent from the table on purpose: neither has a
    read-only tool at all, which is exactly why one is unsupported and the other is
    answered by its own lane rather than by a tool search.
    """
    assert any(domain in tool for tool in tools), (
        f"no tool listed for domain {domain!r} contains that string, so "
        f"search_tool_chunks' `source_id LIKE '%{domain}%'` filter matches none of them: "
        f"{tools}"
    )
    for tool in tools:
        assert tool in CHATBOT_READ_ONLY_TOOLS
