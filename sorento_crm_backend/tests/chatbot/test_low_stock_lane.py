"""S6 RED tests - the chatbot lane consuming the low stock report (#892).

`documentation/plans/scm/PLAN-low-stock-report.md` section S6;
`low-stock-report-acceptance-criteria.md` AC-62 to AC-66.

Mirrors `tests/chatbot/test_outstanding_lane.py`'s own classes wherever there is an
equivalent - `TestSoKeyListedInFieldRevealKeysAndCatalog`, `TestDateParams`, `TestToolPick`,
`TestFieldRevealGateBeforeFetch` - and reuses that file's helpers rather than inventing new
ones, so the two lanes are wired the same way and a reader who knows one knows the other.

Two ways a test here is red, both legitimate:

1. A literal/table assertion against code that already exists (`DOMAIN_SPEC["inventory"]`,
   `fetch.DATE_PARAMS`, `FIELD_REVEAL_KEYS`, `CHATBOT_TOOL_DOMAINS`) - red because the row
   is simply absent.
2. A behavioural assertion through `lanes.business.run_fetch`, the real call site the
   engine's fetch step uses. Red because `select_tool` returns the inventory domain's
   first-listed tool (`crm_inventory_stock_balance_list`) for every inventory ask, and
   there is no `low_stock_report` intent for it to override on.

**Deliberately NOT here:** full-turn composition tests. The low stock reply is one or two
lines the presenter already renders (AC-61, pinned in the MCP suite), so a turn-level test
would re-pin the same string through five more seams. The lane's own job - pick the tool,
gate it, shape the args, pass the attachments through - is what this file asserts.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from app.services.chatbot import contracts
from app.services.chatbot.lanes.business import fetch as fetch_mod
from app.services.chatbot.lanes.business.services import FetchServices
from tests.chatbot.test_engine import CONTACT_ID, _parser_output, seeded  # noqa: F401
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_outstanding_lane import _capturing_mcp

TOOL = "crm_low_stock_report"
GRANT_KEY = "scm.low_stock_report"
REVEAL_PAIR = (GRANT_KEY, "Low stock report over chat")
REFUSAL = "Low stock report is not enabled for your account."

WAREHOUSE_UUID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
WAREHOUSE_CODE = "BRW"
PRODUCT_UUID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
PRODUCT_CODE = "SRTWT7408"

#: What the route answers and the MCP presenter renders (AC-43/AC-61) - the shape the lane
#: actually receives, never the raw route body (the `_capturing_mcp` docstring's rule).
READY_ENVELOPE = {
    "result_type": "low_stock_report",
    "response": "Low stock report - as of 10/09/2026\nLow: 12 of 340 planned products",
    "has_result": True,
    "attachments": [{
        "url": "https://cdn.example.com/exports/low-stock/x/low-stock-10092026.xlsx",
        "filename": "low-stock-10092026.xlsx",
        "mimeType": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        "attachmentType": "file",
    }],
}


def _qf(**overrides: Any) -> dict[str, Any]:
    """`_parser_output`, defaulted to the low stock ask: inventory domain, the new intent,
    and a location word the resolver will turn into a warehouse entity."""
    base = dict(
        domain_hint="inventory",
        intent_hint="low_stock_report",
        entities=[
            {
                "raw": WAREHOUSE_CODE,
                "hint": "warehouse",
                "canonical_code": None,
                "current_message": True,
                "confident": True,
            }
        ],
    )
    base.update(overrides)
    return _parser_output(**base)


def _payload(*, attributes: list[str], entities: list[dict[str, Any]] | None = None):
    """The resolve+gate output `run_fetch` takes - the same shape
    `test_outstanding_lane.py::TestToolPick._payload` builds."""
    return {
        "gate": {
            "compatible_entities": entities if entities is not None else [
                {
                    "uuid": WAREHOUSE_UUID,
                    "entity_type": "warehouse",
                    "canonical_code": WAREHOUSE_CODE,
                },
            ]
        },
        "tier_gate": None,
        "ctx": {
            "parse": {"output": _qf(entities=[])},
            "contact": {"id": CONTACT_ID},
            "access": {"attributes": attributes},
        },
    }


# --------------------------------------------------------------------------- #
# AC-63 - the reveal key exists on both sides
# --------------------------------------------------------------------------- #


class TestLowStockKeyListedInFieldRevealKeysAndCatalog:
    """Mirrors `TestSoKeyListedInFieldRevealKeysAndCatalog`. The backend's frozen literal
    is what the admin Field reveals card lists and what `granted_keys` is checked against;
    the catalog's `restricted_fields` is what `sync_catalog` copies into `mcp_tools`. They
    have to agree or the key is grantable in one place and invisible in the other."""

    def test_low_stock_key_listed_in_field_reveal_keys_and_catalog(self) -> None:
        from app.services.contact_field_reveal_service import FIELD_REVEAL_KEYS

        assert REVEAL_PAIR in FIELD_REVEAL_KEYS, (
            f"FIELD_REVEAL_KEYS must carry {REVEAL_PAIR}, the key that gates AC-64: "
            f"{FIELD_REVEAL_KEYS}"
        )

        repo_root = Path(__file__).resolve().parents[3]
        mcp_root = repo_root / "sorento_crm_mcp"
        if str(mcp_root) not in sys.path:
            sys.path.append(str(mcp_root))
        try:
            from sorento_crm_mcp.catalog import CATALOG
        except ImportError:  # pragma: no cover - the backend container has no copy
            pytest.skip("sorento_crm_mcp is not importable in this environment")

        spec = next(s for s in CATALOG if s.name == TOOL)
        restricted = getattr(spec, "restricted_fields", None) or ()
        assert REVEAL_PAIR in restricted, (
            f"{TOOL}'s ToolSpec.restricted_fields must carry {REVEAL_PAIR}: {restricted}"
        )


# --------------------------------------------------------------------------- #
# AC-62 - the four tables that must all name the tool
# --------------------------------------------------------------------------- #


class TestDomainWiring:
    def test_tool_domain_is_inventory(self) -> None:
        from app.services.mcp_tool_domains import CHATBOT_TOOL_DOMAINS

        assert CHATBOT_TOOL_DOMAINS.get(TOOL) == "inventory", (
            f"CHATBOT_TOOL_DOMAINS must map {TOOL} to inventory: "
            f"{CHATBOT_TOOL_DOMAINS.get(TOOL)!r}"
        )

    def test_inventory_domain_spec_lists_the_tool_but_not_first(self) -> None:
        """AC-62's own emphasis: `tools += (...)`, NOT `tools[0]`. `select_tool` falls back
        to the first-listed tool for a domain, so putting this one in front would send
        every plain stock ask ("how many CB100 in BRW") into a full reorder run."""
        spec = contracts.DOMAIN_SPEC["inventory"]
        assert TOOL in spec.tools, f"inventory's tool pool must include {TOOL}: {spec.tools}"
        assert spec.tools[0] != TOOL, (
            f"{TOOL} must not be inventory's default tool - a plain stock ask would run a "
            f"plan: {spec.tools}"
        )

    def test_inventory_domain_spec_carries_the_intent_and_switch_words(self) -> None:
        spec = contracts.DOMAIN_SPEC["inventory"]
        assert "low_stock_report" in spec.intents, (
            f"inventory's intents must include low_stock_report: {spec.intents}"
        )
        for word in ("low stock", "reorder report", "below level"):
            assert word in spec.switch_words, (
                f"inventory's switch_words must include {word!r}: {spec.switch_words}"
            )

    def test_tool_is_on_the_chatbot_read_only_list(self) -> None:
        """AC-62: `read_only` follows the `crm_portal_link_get` precedent - a tool that
        mints an artefact and is still safe for automated selection. The backend carries
        the names as a frozen set because the deployed image has no copy of the MCP
        package, so this is the backend-side half of that agreement."""
        assert TOOL in fetch_mod.CHATBOT_READ_ONLY_TOOLS, (
            f"{TOOL} must be on the chatbot's frozen read-only list: it is selectable"
        )

    def test_domain_claimed_tools_lists_the_tool(self) -> None:
        assert TOOL in contracts.DOMAIN_CLAIMED_TOOLS, (
            f"DOMAIN_CLAIMED_TOOLS must claim {TOOL} or the pinned-set CI test fails"
        )


# --------------------------------------------------------------------------- #
# AC-64 - the gate refuses BEFORE any fetch
# --------------------------------------------------------------------------- #


class TestFieldRevealGateBeforeFetch:
    """Mirrors `test_outstanding_lane.py::TestFieldRevealGateBeforeFetch`. The point of
    "before fetch" is that a refused contact must not cause a reorder run to be created -
    this tool's fetch has a side effect, unlike every other tool on the read list."""

    def test_gate_refuses_before_fetch_without_key(self, session_factory) -> None:
        from app.services.chatbot.lanes.business import run_fetch

        call, captured = _capturing_mcp(READY_ENVELOPE)
        result = run_fetch(_payload(attributes=[]), services=FetchServices(mcp_call=call))

        assert captured == [], (
            f"a contact without {GRANT_KEY} must not reach the tool at all - the fetch "
            f"CREATES A RUN: {captured}"
        )
        reply = (result or {}).get("response") or ""
        assert reply.startswith(REFUSAL), (
            f"the refusal line must open the reply, verbatim: {reply!r}"
        )
        assert (result or {}).get("escalate") or (result or {}).get("team_options") or (
            "team" in reply.lower()
        ), (
            "the refusal ends with the existing team picker, the same shape "
            f"SO_NOT_ENABLED_MESSAGE's own path uses: {result!r}"
        )

    def test_gate_passes_with_key_and_picks_the_tool(self, session_factory) -> None:
        """AC-64's other half, and AC-62's `tools[0]` rule seen from the pick: with the
        grant, the low stock intent selects THIS tool - not the inventory domain's
        first-listed `crm_inventory_stock_balance_list`, which is what a pick that reads
        only the domain returns today."""
        from app.services.chatbot.lanes.business import run_fetch

        call, captured = _capturing_mcp(READY_ENVELOPE)
        run_fetch(_payload(attributes=[GRANT_KEY]), services=FetchServices(mcp_call=call))

        assert captured, "no MCP tool was ever called"
        name, _args = captured[0]
        assert name == TOOL, (
            f"intent low_stock_report + the grant must pick {TOOL}, not {name!r}"
        )


# --------------------------------------------------------------------------- #
# AC-66 / AC-71 - the arguments the lane builds
# --------------------------------------------------------------------------- #


class TestDateParams:
    def test_crm_low_stock_report_uses_date_from_to(self) -> None:
        assert fetch_mod.DATE_PARAMS.get(TOOL) == ("date_from", "date_to"), (
            f"AC-71: {TOOL} maps to date_from/date_to: {fetch_mod.DATE_PARAMS.get(TOOL)!r}"
        )


class TestTransformer:
    def _trigger(self) -> dict[str, Any]:
        """A warehouse entity and a product entity, each carrying its canonical code, AND
        `low_stock_warehouse_codes` on `semantic_input`.

        Both are supplied on purpose: the plan builds `warehouse_codes` from
        `semantic_input["low_stock_warehouse_codes"]` (set in `lanes/business/__init__.py`
        after the existing token resolution, the way `outstanding_warehouse_codes` is) and
        `product_codes` from the product entities' own codes. A test that supplied only
        one of the two would pin an implementation detail the plan leaves open.
        """
        return {
            "tool": TOOL,
            "entities": [
                {
                    "uuid": WAREHOUSE_UUID,
                    "entity_type": "warehouse",
                    "canonical_code": WAREHOUSE_CODE,
                    "code": WAREHOUSE_CODE,
                },
                {
                    "uuid": PRODUCT_UUID,
                    "entity_type": "product",
                    "canonical_code": PRODUCT_CODE,
                    "code": PRODUCT_CODE,
                },
            ],
            "semantic_input": {
                "contact_id": CONTACT_ID,
                "space_id": "ZZTLSL-SPACE",
                "date_filter_start": "2026-09-01",
                "date_filter_end": "2026-11-30",
                "low_stock_warehouse_codes": [WAREHOUSE_CODE],
            },
        }

    def test_transformer_fills_warehouse_codes_product_codes_and_dates(self) -> None:
        """AC-66/AC-71: the tool's own contract is CODES, not the generic UUID-list shape
        every other inventory tool takes - the route resolves codes, and a UUID would
        silently match nothing. So the UUID params must be removed, not merely ignored:
        `warehouse_ids` / `product_ids` on the wire would be dropped by FastMCP anyway
        (they are not in the tool's signature), and leaving them in the args makes a
        replay diff unreadable.
        """
        out = fetch_mod.entity_ids_transformer(self._trigger(), space_id="ZZTLSL-SPACE")

        assert out.get("warehouse_codes") == [WAREHOUSE_CODE], out
        assert out.get("product_codes") == [PRODUCT_CODE], out
        assert out.get("date_from") == "2026-09-01", out
        assert out.get("date_to") == "2026-11-30", out
        assert out.get("contact_id") == CONTACT_ID, out
        assert out.get("space_id") == "ZZTLSL-SPACE", out
        assert out.get("view") == "render", (
            "the lane always asks for the render envelope, or the presenter never runs"
        )
        assert "warehouse_ids" not in out, (
            f"the UUID param must be popped for this tool: {out}"
        )
        assert "product_ids" not in out, (
            f"the UUID param must be popped for this tool: {out}"
        )


class TestOutputStructurer:
    def test_output_structurer_populates_attachments_from_envelope(self) -> None:
        """AC-66: `engine._attachments_src` is what turns a non-empty `attachments` into a
        `send_attachments` action, and that is the whole delivery mechanism for the
        in-turn path (AC-43). The generic envelope path returns `attachments: []`, so this
        tool needs its own branch - the same shape `_outstanding_report_output` has.

        The reply text is the presenter's, used VERBATIM: one writer, one wording (the
        rule `_outstanding_report_output`'s docstring states).
        """
        out = fetch_mod.output_structurer(READY_ENVELOPE, {"tool": TOOL})

        assert out.get("attachments") == READY_ENVELOPE["attachments"], (
            f"the envelope's attachments must reach the structured output: {out}"
        )
        assert out.get("attachments"), "an empty list emits no send_attachments action"
        assert out.get("response") == READY_ENVELOPE["response"], (
            f"the presenter's text is used verbatim: {out.get('response')!r}"
        )
        assert out.get("has_result") is True, out
