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


def _po_row(
    qty: Any,
    date: str | None,
    *,
    code: str = "SRTWC8517",
    po_number: str = "PO-1001",
    po_date: str | None = "2026-05-01",
    kind: str | None = "PO",
) -> dict:
    fields = [
        {"key": "po_number", "label": "PO Number", "value": po_number},
    ]
    if kind is not None:
        fields.append({"key": "kind", "label": "Source", "value": kind})
    fields += [
        {"key": "product_code", "label": "Product Code", "value": code},
        {"key": "outstanding_qty", "label": "Outstanding Qty", "value": qty},
    ]
    if po_date is not None:
        fields.append({"key": "po_date", "label": "PO Date", "value": po_date})
    if date is not None:
        fields.append({"key": "expected_date", "label": "Expected Date", "value": date})
    return {"fields": fields}


GRANTED = ["purchase_orders.placed"]


def _run(
    *,
    ladder: dict[str, list[str]] | None,
    incoming_response: dict,
    po_response: dict | None = None,
    code: str = "SRTWC8517",
    uuid: str = "prod-uuid-1",
    granted: list[str] | None = GRANTED,
    parser: dict | None = None,
) -> tuple[dict, list[tuple[str, dict]]]:
    calls: list[tuple[str, dict]] = []

    def mcp_probe(name: str, args: dict) -> dict:
        calls.append((name, args))
        if name in (_INCOMING_TOOL, _STOCK_TOOL):
            # the first probe: the OTHER domain's tool (incoming from a stock ask, stock
            # from an incoming ask) - `incoming_response` is its answer either way
            return incoming_response
        if name == _PO_TOOL:
            return po_response if po_response is not None else {"answers": [], "has_result": False}
        raise AssertionError(f"unexpected probe tool: {name}")

    services = AnswerServices(mcp_probe=mcp_probe, family_fetch=lambda q: {"data": []})
    result = run_crossdomain(
        _validator_result(),
        parser=parser or _PARSER,
        resolved=_resolved_for(code, uuid),
        session_block={"session_vars": {"variables": {}}},
        entities_names=None,
        services=services,
        contact_id="164838271",
        space_id="900001",
        crossdomain_ladder=ladder,
        granted=granted,
    )
    return result, calls


def _composed_text(result: dict, *, answered: bool = True, miss_offer: bool = False) -> str:
    """Run the tail's ONE offer writer (`crossdomain_compose`) over the lane's block, the
    way `engine.py` does, and return the customer-visible text."""
    from app.services.chatbot.tail.compose import crossdomain_compose

    miss = "Here's what you want:\n\u2022 product: SRTWC8517\n\nBut no inventory matched these."
    if miss_offer:
        miss += " Would you like me to escalate to warehouse team?"
    item = {
        "reply": {
            "session_patch": {
                "user_response": miss,
                "variables": {"last_result_set": [{"code": "SRTOTHER"}], "response": "Previous turn"},
            }
        }
    }
    out = crossdomain_compose(
        item, result={"result": {"xd": {"block": result["render"]["_xdBlock"]}}}, answered=answered
    )
    reply = out["reply"]
    return reply.get("text") or reply["session_patch"]["user_response"]


_LADDER_WITH_PO = {"inventory": ["incoming", "purchase_order"], "incoming": ["inventory"]}
_LADDER_NO_PO = {"inventory": ["incoming"], "incoming": ["inventory"]}
# D7 (migration 491): the shipped ladder climbs to PO from either side.
_LADDER_491 = {"inventory": ["incoming", "purchase_order"], "incoming": ["inventory", "purchase_order"]}
_STOCK_TOOL = "crm_inventory_stock_balance_list"
_INCOMING_PARSER = {**_PARSER, "intent_hint": "check_incoming", "domain_hint": "incoming",
                    "user_goal": "check incoming for SRTWC8517"}


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
        assert "but PO is placed" in block
        # Owner ruling (8 Sep 2026, D2): one heading per document, then its lines.
        assert "but PO is placed:\nPO PO-1001 dated 2026-05-01:\n50 pcs expected 2026-07-01" in block
        # The rung writes NO offer: `crossdomain_compose` is the one writer (turns
        # 0184d84d / 5f73ddb0 / 90a1637a carried the question twice).
        assert "escalate" not in block.lower()
        assert result["render"]["_xdBlock"]["team"] == "purchasing"
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
        # AC-922's own wording: "no PO", the customer's two letters and the same word the
        # question used - not `rung.replace("_", " ")`, which spelled it out (review, item 9).
        # Item 5 (8 Sep 2026): the rung reads PO lines AND unshipped SPO allocations, so
        # the three-way miss says "nothing on order" - the customer's question, not a
        # document type (was "no PO for").
        assert "No stock, no incoming and nothing on order for SRTWC8517." in block
        assert "no purchase order" not in block and "no PO for" not in block
        assert "escalate" not in block.lower()  # compose is the one offer writer


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


class TestOwner8SepTheOfferIsWrittenOnce:
    """Turns 0184d84d / 5f73ddb0 / 90a1637a (8 Sep 2026): "...27 pcs expected 2027-02-01
    Would you like me to escalate to purchasing team?\n\nWould you like me to escalate to
    purchasing team?" - the rung appended the offer into the block AND `crossdomain_compose`
    appended it again from `block["team"]`. Compose is the one writer, on every shape."""

    _PHRASE = "Would you like me to escalate"

    def test_rung_found(self) -> None:
        result, _ = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [_po_row(50, "2026-07-01")], "has_result": True},
        )
        text = _composed_text(result)
        assert text.count(self._PHRASE) == 1
        assert "escalate to purchasing team?" in text  # the rung's team, not the stock team

    def test_rung_nothing(self) -> None:
        result, _ = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [], "has_result": False},
        )
        text = _composed_text(result)
        assert text.count(self._PHRASE) == 1
        assert "No stock, no incoming and nothing on order for SRTWC8517." in text

    def test_first_probe_nothing(self) -> None:
        result, _ = _run(ladder=_LADDER_NO_PO, incoming_response={"answers": [], "has_result": False})
        text = _composed_text(result)
        assert text.count(self._PHRASE) == 1
        assert "escalate to warehouse team?" in text

    def test_total_miss_keeps_the_miss_sentence_own_offer(self) -> None:
        """The other compose branch: the miss sentence already carries the phrase and the
        block goes above it - still exactly one."""
        result, _ = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [_po_row(50, "2026-07-01")], "has_result": True},
        )
        text = _composed_text(result, answered=False, miss_offer=True)
        assert text.count(self._PHRASE) == 1


class TestOwner8SepThePORungLineCarriesTheDocumentDate:
    def test_expected_part_is_omitted_when_null(self) -> None:
        result, _ = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [_po_row(12, None)], "has_result": True},
        )
        block = result["render"]["_xdBlock"]["block"]
        assert "PO PO-1001 dated 2026-05-01:\n12 pcs" in block
        assert "expected" not in block

    def test_a_row_with_no_po_number_still_reads(self) -> None:
        row = _po_row(12, "2026-07-01", po_date=None)
        row["fields"] = [f for f in row["fields"] if f["key"] != "po_number"]
        result, _ = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [row], "has_result": True},
        )
        assert "PO:\n12 pcs expected 2026-07-01" in result["render"]["_xdBlock"]["block"]

    def test_dated_part_is_omitted_when_the_document_has_no_date(self) -> None:
        result, _ = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [_po_row(12, "2026-07-01", po_date=None)], "has_result": True},
        )
        block = result["render"]["_xdBlock"]["block"]
        assert "PO PO-1001:\n12 pcs expected 2026-07-01" in block


class TestOwner8SepThePORungIsPerContact:
    """On-order information is a per-contact reveal, key `purchase_orders.placed`. Without
    the grant the rung does not run at all: no probe, no PO lines, the pre-rung note and
    the single offer - byte-identical to the ladder-off shape."""

    def _off(self) -> dict:
        result, _ = _run(ladder=None, incoming_response={"answers": [], "has_result": False})
        return result["render"]["_xdBlock"]

    def test_with_the_grant_the_rung_runs(self) -> None:
        _, calls = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [_po_row(50, "2026-07-01")], "has_result": True},
            granted=["purchase_orders.placed", "inventory.sellable"],
        )
        assert [name for name, _ in calls] == [_INCOMING_TOOL, _PO_TOOL]

    def test_without_the_grant_no_probe_and_the_ladder_off_shape(self) -> None:
        for granted in ([], None, ["inventory.sellable"]):
            result, calls = _run(
                ladder=_LADDER_WITH_PO,
                incoming_response={"answers": [], "has_result": False},
                po_response={"answers": [_po_row(50, "2026-07-01")], "has_result": True},
                granted=granted,
            )
            assert [name for name, _ in calls] == [_INCOMING_TOOL], granted
            block = result["render"]["_xdBlock"]
            off = self._off()
            assert block["block"] == off["block"] and block["team"] == off["team"]
            assert "rung" not in block
            assert _composed_text(result).count("Would you like me to escalate") == 1


class TestItem5UnshippedSPOIsOnOrderFromTheSupplier:
    """Item 5 (8 Sep 2026): the PO placed tool now returns unshipped SPO allocations as
    rows of the same shape with `kind` = "spo"; the rung words them as stock on order from
    the supplier and picks its header by what the rows are."""

    def _block(self, rows: list[dict]) -> str:
        result, _ = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": rows, "has_result": True},
        )
        return result["render"]["_xdBlock"]["block"]

    def test_an_spo_row_reads_on_order_from_supplier(self) -> None:
        block = self._block([_po_row(7, "2026-10-05", po_number="SPO-2026/09-0001", po_date="2026-08-20", kind="SPO")])
        assert "but stock is on order from the supplier:" in block
        assert "SPO SPO-2026/09-0001 dated 2026-08-20 (on order from supplier):\n7 pcs expected 2026-10-05" in block
        assert "but PO is placed" not in block

    def test_spo_parts_are_omitted_when_null(self) -> None:
        block = self._block([_po_row(7, None, po_number="SPO-1", po_date=None, kind="SPO")])
        assert "SPO SPO-1 (on order from supplier):\n7 pcs" in block
        assert "dated" not in block and "expected" not in block

    def test_a_mixed_set_keeps_the_po_header_and_words_each_row_by_kind(self) -> None:
        block = self._block([
            _po_row(50, "2026-07-01", kind="PO"),
            _po_row(7, "2026-10-05", po_number="SPO-9", po_date="2026-08-20", kind="SPO"),
        ])
        assert "but PO is placed:" in block
        assert "PO PO-1001 dated 2026-05-01:\n50 pcs expected 2026-07-01" in block
        assert "SPO SPO-9 dated 2026-08-20 (on order from supplier):\n7 pcs expected 2026-10-05" in block

    def test_a_row_with_no_kind_is_read_as_a_po(self) -> None:
        """An older envelope (no `kind` field) is today's PO row."""
        block = self._block([_po_row(50, "2026-07-01", kind=None)])
        assert "but PO is placed:" in block
        assert "PO PO-1001 dated 2026-05-01:\n50 pcs expected 2026-07-01" in block


class TestThePORungGrantKey:
    """The backend half of the lane-gated key guardrail (review round 2 / PR #735 CI):
    the rung's grant key is pinned here from the backend's own tree, and matched against
    the PO ToolSpec's declaration only where the MCP package is importable (it is
    installed in the local venv; the backend CI image lacks it and skips that half)."""

    def test_the_rung_key_is_purchase_orders_placed(self) -> None:
        from app.services.chatbot.lanes.business.answer import _CROSSDOMAIN_RUNG_GRANT

        assert _CROSSDOMAIN_RUNG_GRANT == {"purchase_order": "purchase_orders.placed"}

    def test_the_key_is_declared_on_the_po_toolspec(self) -> None:
        import importlib.util
        import sys
        from pathlib import Path

        import pytest

        # The SIBLING tree first when this is the monorepo: the venv's editable install of
        # `sorento_crm_mcp` can point at another checkout (it does on the Mac mini), and a
        # stale catalog would grade the wrong declaration. Outside the monorepo (the
        # backend CI image) the package is absent and this half skips.
        sibling = Path(__file__).resolve().parents[3] / "sorento_crm_mcp"
        if sibling.is_dir() and str(sibling) not in sys.path:
            sys.path.insert(0, str(sibling))
            sys.modules.pop("sorento_crm_mcp", None)
            sys.modules.pop("sorento_crm_mcp.catalog", None)
        if importlib.util.find_spec("sorento_crm_mcp") is None:
            pytest.skip("sorento_crm_mcp not importable (backend CI image)")
        import sorento_crm_mcp.catalog as catalog

        from app.services.chatbot.lanes.business.answer import _CROSSDOMAIN_RUNG_GRANT, _CROSSDOMAIN_RUNG_TOOL

        specs = {spec.name: spec for spec in catalog.CATALOG}
        for rung, key in _CROSSDOMAIN_RUNG_GRANT.items():
            declared = dict(specs[_CROSSDOMAIN_RUNG_TOOL[rung]].restricted_fields)
            assert key in declared, f"{key} is not declared on {_CROSSDOMAIN_RUNG_TOOL[rung]}"


class TestD2OneHeadingPerDocument:
    """D2 (owner console pass, 8 Sep 2026): seven lines each repeating "on PO 202607-S0054
    dated 2026-07-17" - the rows are grouped by document, heading then lines."""

    def test_lines_of_one_po_sit_under_one_heading_in_tool_order(self) -> None:
        rows = [
            _po_row(42, "2026-07-13", po_number="202607-S0054", po_date="2026-07-17"),
            _po_row(12, "2026-07-31", po_number="202607-S0054", po_date="2026-07-17"),
            _po_row(7, "2026-10-05", po_number="SPO-9", po_date="2026-08-20", kind="SPO"),
            _po_row(3, None, po_number="202607-S0054", po_date="2026-07-17"),
        ]
        result, _ = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": rows, "has_result": True},
        )
        block = result["render"]["_xdBlock"]["block"]
        assert block == (
            "No stock and no incoming for SRTWC8517, but PO is placed:\n"
            "PO 202607-S0054 dated 2026-07-17:\n"
            "42 pcs expected 2026-07-13\n"
            "12 pcs expected 2026-07-31\n"
            "3 pcs\n"
            "SPO SPO-9 dated 2026-08-20 (on order from supplier):\n"
            "7 pcs expected 2026-10-05"
        )
        assert block.count("202607-S0054") == 1


class TestD7AnIncomingAskClimbsToThePORung:
    """D7 (owner ruling, 8 Sep 2026): stock -> incoming -> PO whichever domain the customer
    entered from. "hav incoming?" for a zero-stock code with an open PO line used to end
    at "No incoming and no stock for X." because the 489 ladder had no second rung on
    `incoming`; migration 491 adds it."""

    def test_from_incoming_the_po_rung_runs_and_the_wording_follows_the_climb(self) -> None:
        result, calls = _run(
            ladder=_LADDER_491,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [_po_row(42, "2026-07-13", po_number="202607-S0054", po_date="2026-07-17")], "has_result": True},
            parser=_INCOMING_PARSER,
        )
        assert [name for name, _ in calls] == [_STOCK_TOOL, _PO_TOOL]
        block = result["render"]["_xdBlock"]["block"]
        assert block.startswith("No incoming and no stock for SRTWC8517, but PO is placed:\nPO 202607-S0054 dated 2026-07-17:\n42 pcs expected 2026-07-13")
        assert result["render"]["_xdBlock"]["team"] == "purchasing"
        assert _composed_text(result).count("Would you like me to escalate") == 1

    def test_from_incoming_the_three_way_miss_reads_in_the_same_order(self) -> None:
        result, calls = _run(
            ladder=_LADDER_491,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [], "has_result": False},
            parser=_INCOMING_PARSER,
        )
        assert [name for name, _ in calls] == [_STOCK_TOOL, _PO_TOOL]
        assert "No incoming, no stock and nothing on order for SRTWC8517." in result["render"]["_xdBlock"]["block"]

    def test_from_incoming_the_spo_header_variant_holds(self) -> None:
        result, _ = _run(
            ladder=_LADDER_491,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [_po_row(7, "2026-10-05", po_number="SPO-9", po_date="2026-08-20", kind="SPO")], "has_result": True},
            parser=_INCOMING_PARSER,
        )
        assert "No incoming and no stock for SRTWC8517, but stock is on order from the supplier:" in result["render"]["_xdBlock"]["block"]

    def test_from_incoming_without_the_grant_no_probe_and_the_ladder_off_note(self) -> None:
        result, calls = _run(
            ladder=_LADDER_491,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [_po_row(42, "2026-07-13")], "has_result": True},
            parser=_INCOMING_PARSER,
            granted=[],
        )
        assert [name for name, _ in calls] == [_STOCK_TOOL]
        assert "No incoming and no stock for SRTWC8517." in result["render"]["_xdBlock"]["block"]
        assert "PO" not in result["render"]["_xdBlock"]["block"]

    def test_the_489_ladder_still_stops_at_stock_from_incoming(self) -> None:
        """A tenant that kept the 489 shape (custom or not yet migrated) is unchanged."""
        result, calls = _run(
            ladder=_LADDER_WITH_PO,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [_po_row(42, "2026-07-13")], "has_result": True},
            parser=_INCOMING_PARSER,
        )
        assert [name for name, _ in calls] == [_STOCK_TOOL]

    def test_from_inventory_the_wording_is_unchanged(self) -> None:
        result, _ = _run(
            ladder=_LADDER_491,
            incoming_response={"answers": [], "has_result": False},
            po_response={"answers": [], "has_result": False},
        )
        assert "No stock, no incoming and nothing on order for SRTWC8517." in result["render"]["_xdBlock"]["block"]
