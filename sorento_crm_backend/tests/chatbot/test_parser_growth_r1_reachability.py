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
`not_supported` list, and the tool search's own domain filter (`mcp_tools.chatbot_domain`
since 8 Sep 2026; `source_id LIKE '%<domain>%'` only as the fallback for a domain outside
`DOMAIN_SPEC`).

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
    LAST_COST_ADDENDUM,
    SEMANTIC_PARSER_PROMPT,
    SEMANTIC_PARSER_PROMPT_SLIM,
)

#: The corpus lives INSIDE the test package, and that is not tidiness (CI, 8 Sep 2026).
#: The backend image's build context is `./sorento_crm_backend` only, so nothing under the
#: repo's `documentation/` exists in it - and `parents[3]` from `tests/chatbot/` is one
#: level ABOVE the backend root, which inside the image resolves to `/`. The file read
#: below runs at COLLECTION (it feeds `@pytest.mark.parametrize`), so the in-image
#: `pytest --collect-only` gate died with
#: `FileNotFoundError: '/documentation/plans/chatbot/samples/parser-growth-r1-phrases.json'`
#: and exit code 2 before a single test ran. `Path(__file__).parent` cannot escape the
#: package, so it is right in the image, in a worktree and in a checkout alike.
#:
#: `documentation/plans/chatbot/samples/README.md` POINTS here rather than holding a second
#: copy: a corpus in two places is a corpus that disagrees with itself.
PHRASES_FILE = Path(__file__).parent / "fixtures" / "parser_growth_r1_phrases.json"

PO_TOOL = "crm_procurement_po_placed_list"
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
        FULL body and dev's is on the SLIM one.

        The strong `.endswith` form is restored (review S4, 12 Sep 2026) by stripping
        `LAST_COST_ADDENDUM` first: that one now stacks AFTER `GROWTH_R1_ADDENDUM` on
        both bodies, the same way this addendum itself stacked after the live text, so
        `GROWTH_R1_ADDENDUM` is still exactly the tail once the later addendum is off."""
        assert SEMANTIC_PARSER_PROMPT.removesuffix(LAST_COST_ADDENDUM).endswith(
            GROWTH_R1_ADDENDUM
        )
        assert SEMANTIC_PARSER_PROMPT_SLIM.removesuffix(LAST_COST_ADDENDUM).endswith(
            GROWTH_R1_ADDENDUM
        )

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
# PLAN-chatbot-outstanding-report.md S4 point 1 + the 13 Sep 2026 console check:
# the outstanding vocabulary and the location cue, TAUGHT and PUBLISHED.
# --------------------------------------------------------------------------- #


class TestTheOutstandingVocabularyIsTaught:
    @pytest.mark.parametrize("value", ["do_outstanding", "outstanding_both"])
    def test_both_bodies_name_the_two_new_buckets(self, value: str) -> None:
        for body in (SEMANTIC_PARSER_PROMPT, SEMANTIC_PARSER_PROMPT_SLIM):
            assert value in body, (
                f"{value} is a bucket the report lane reads, and the model can only emit "
                "what the published prompt teaches"
            )

    @pytest.mark.parametrize("token", ['"IB"', '"BB"', '"BRW"', '"BRW-IB"', '"MWH"'])
    def test_the_location_token_cue_names_the_real_codes(self, token: str) -> None:
        """Console check finding 1 (13 Sep 2026): the parser hinted "IB" in
        "Srtwt7443 sales order outstanding for IB" as a CUSTOMER, so the turn ended in
        the customer-disambiguation picker and never reached the report at all. The
        order domain has to teach that a short upper-case token beside a product is a
        location, the way `487_chatbot_warehouse_cue` taught the arrival cue."""
        assert token in GROWTH_R1_ADDENDUM, (
            f"{token} is not named as a location token anywhere in the prompt"
        )

    def test_the_cue_says_warehouse_and_rules_out_customer(self) -> None:
        assert 'hint "warehouse"' in GROWTH_R1_ADDENDUM
        assert "NEVER \"customer\"" in GROWTH_R1_ADDENDUM, (
            "the rule has to say what the token is NOT: 'customer' is the hint the model "
            "chose on its own, on both published prompt versions"
        )


def _alembic_heads_excluding(revision: str) -> set[str]:
    """The alembic head(s) of the real script directory, computed with `revision`'s own
    file taken out of the graph - which is what "the head this migration chains onto"
    means. Read from the scripts on disk (`ScriptDirectory`), never from a literal, so a
    re-parent onto a newer head keeps this test true."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    revisions = list(ScriptDirectory.from_config(cfg).walk_revisions())

    referenced: set[str] = set()
    for rev in revisions:
        if rev.revision == revision:
            continue
        down = rev.down_revision
        for parent in (down if isinstance(down, (tuple, list)) else [down]):
            if parent:
                referenced.add(parent)
    return {
        rev.revision
        for rev in revisions
        if rev.revision != revision and rev.revision not in referenced
    }


class TestTheOutstandingVocabularyIsPublished:
    """Console check finding 3: `ai_prompt_registry.render()` reads the PUBLISHED DB
    row, and none of the 12 `chatbot_semantic_parser` versions carried
    `do_outstanding` / `outstanding_both` - editing the Python constant reaches a live
    customer NOWHERE. Publishing is a migration, the way 475 / 480 / 487 / 490 / 513
    all do it."""

    def _module(self):
        import importlib.util

        path = (
            Path(__file__).resolve().parents[2]
            / "alembic"
            / "versions"
            / "514_chatbot_outstanding_vocab.py"
        )
        assert path.exists(), (
            "no migration publishes the outstanding vocabulary, so it reaches no live "
            "prompt version (console check finding 3)"
        )
        spec = importlib.util.spec_from_file_location("zzt_outstanding_vocab_migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_migration_publishes_both_bodies(self) -> None:
        module = self._module()
        assert callable(module.publish)
        for text in (module._full_text(), module._slim_text()):
            assert "do_outstanding" in text
            assert "outstanding_both" in text
            assert 'hint "warehouse"' in text

    def test_the_revision_chains_onto_the_current_head(self) -> None:
        """N3 (re-review): the head is READ, never spelled out. Pinning the literal meant
        the pre-PR re-parent (`scripts/alembic-reparent.sh`, which flips `down_revision`
        onto main's newest head) would fail this test for doing exactly its job - main
        has already merged the two 513 heads since this migration was written."""
        module = self._module()
        assert len(module.revision) <= 32, module.revision
        heads = _alembic_heads_excluding(module.revision)
        assert module.down_revision in heads, (
            f"the migration must chain onto a current head; down_revision="
            f"{module.down_revision!r}, heads without this migration = {sorted(heads)}"
        )


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
def test_every_domain_tool_is_in_the_read_only_pool(
    domain: str, tools: tuple[str, ...]
) -> None:
    """A domain's tools must be tools the chatbot may actually call. `select_tool` reads
    `tools[0]` and `ensure_read_only` gates the name at the egress, so a domain whose tool
    is off the allow-list answers nothing at all - this is still a real way for a domain to
    end up unable to answer.

    `goods_receive` and `ideate` are absent from `DOMAIN_TOOLS` on purpose: neither has a
    read-only tool at all, which is exactly why one is unsupported and the other is
    answered by its own lane rather than by a tool call.
    """
    for tool in tools:
        assert tool in CHATBOT_READ_ONLY_TOOLS, f"{tool!r} ({domain!r}) is not read-only"


def test_after_sync_every_domain_spec_tool_has_its_domain_stamped() -> None:
    """This is reachability's real gate now, replacing the name-substring assertion this
    test used to make (owner ruling, 8 Sep 2026, "I don't accept the leak" - the PO
    placed tool's OLD name contained "order" and leaked into every `order` pool under
    the old `source_id LIKE '%<domain_hint>%'` filter; it is also why that tool is now
    named `crm_procurement_po_placed_list`).
    The tool search narrowed a known domain's pool on `mcp_tools.chatbot_domain` instead,
    and that column is stamped by `mcp_tool_registry_service.sync_catalog` straight off
    `DOMAIN_SPEC[domain].tools` - so the property worth pinning is that a real sync lands
    the right value, not that a name happens to contain a substring. The search itself was
    dropped hours later (the lane reads `DOMAIN_SPEC[domain].tools[0]` outright), which
    makes reachability a table lookup rather than a query; the stamp stays, unread, until
    the next migration that touches `mcp_tools` carries its drop, and so does this
    assertion, which is what keeps the two data copies from drifting while it does.

    Runs a real sync against the shared database and rolls it back; skipped when
    `mcp_tools` is empty (CI's database has no seed data - LESSONS-LEARNT).
    """
    import sys
    from pathlib import Path

    from app.database import SessionLocal
    from app.models.access import McpTool
    from app.services.mcp_tool_registry_service import sync_catalog

    # The SIBLING tree first when this is the monorepo: the venv's editable install of
    # `sorento_crm_mcp` (which `sync_catalog` imports) can point at another checkout (it
    # does on the Mac mini), and a stale catalog would sync a stale set of tools -
    # measured here: without this, the SPO tool was absent from the stale catalog and
    # never got its `chatbot_domain` stamped. Same guard as
    # `test_crossdomain_ladder.py::test_the_key_is_declared_on_the_po_toolspec`.
    sibling = Path(__file__).resolve().parents[3] / "sorento_crm_mcp"
    if sibling.is_dir() and str(sibling) not in sys.path:
        sys.path.insert(0, str(sibling))
        for mod in ("sorento_crm_mcp", "sorento_crm_mcp.catalog", "sorento_crm_mcp.module_loader"):
            sys.modules.pop(mod, None)

    db = SessionLocal()
    try:
        if db.query(McpTool).count() == 0:
            pytest.skip("mcp_tools is empty (CI has no data)")
        sync_catalog(db)
        db.flush()
        for domain, tools in DOMAIN_TOOLS.items():
            for tool in tools:
                row = db.query(McpTool).filter(McpTool.tool_name == tool).one_or_none()
                if row is None:
                    continue  # not every fixture tool exists in this install's catalogue
                assert row.chatbot_domain == domain, (
                    f"{tool!r} synced with chatbot_domain={row.chatbot_domain!r}, "
                    f"expected {domain!r}"
                )
    finally:
        db.rollback()
        db.close()
