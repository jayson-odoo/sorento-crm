"""AC-921 / AC-922 through `run_turn`, not through `run_crossdomain` directly.

The console check of 7 Sep 2026 found Foundre's rule unreachable from a real turn while
every unit test of it was green, and the reason those tests could not see it is that they
all call `run_crossdomain` (or `crossdomain_render`) directly. This file drives the whole
turn - `engine.run_turn` against the Postgres blank-schema fixture, only the injectable
seams stubbed - so the question it answers is the owner's: "does a customer asking about a
product with no stock get told about the PO?"

The stock envelope is EMPTY on purpose (`has_result: false`, no items). That is the shape
the live turn produced for SRTWT7445-LV-NEW: the resolver found the product, the stock tool
answered with nothing, and the turn went to the miss half - which is where the cross-domain
block has to arrive.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.chatbot.lanes.business.services import (
    AnswerServices,
    FetchServices,
    ResolveGateServices,
)
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import (  # noqa: F401 - re-exported fixtures used by name
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)

#: The SUFFIXED shape, which the console check found never reaching the ladder on a live
#: turn. Measured 8 Sep 2026 against the real resolver: `SRTWT7445-LV-NEW`, `MSK11A-QT`,
#: `CWCX1009-SH`, `CB2904` and `SRTWB103` ALL come back as exactly one product match at
#: tier `exact`, under the Sorento-only scope and unscoped alike - so the suffix does not
#: change how a code resolves, and `crossdomain_zeroset` excludes no tier that these codes
#: land on. This file pins the other half: given that resolution, the suffixed code reaches
#: the rung exactly like the unsuffixed one. Whatever the live difference is, it is not the
#: code shape and not the tier.
CODE = "SRTWT7445-LV-NEW"
SUFFIXED_CODES = ("SRTWT7445-LV-NEW", "MSK11A-QT", "CWCX1009-SH")
PRODUCT_UUID = "11111111-1111-1111-1111-111111111111"
PO_TOOL = "crm_procurement_purchase_orders_placed_list"

EMPTY_STOCK = {
    "result_type": "stock",
    "intro": "No matching results found.",
    "items": [],
    "has_result": False,
}
NO_ROWS = {"answers": [], "has_result": False}
PO_ROWS = {
    "answers": [
        {
            "fields": [
                {"key": "product_code", "label": "Product Code", "value": CODE},
                {"key": "outstanding_qty", "label": "Outstanding Qty", "value": 1000},
                {"key": "expected_date", "label": "Expected Date", "value": "2026-06-01"},
                # The MCP envelope is UNFILTERED - the supplier is on the row. Whether the
                # customer ever sees it is what AC-921's negative assertion grades.
                {"key": "supplier", "label": "Supplier", "value": "GUANGDONG WORKS"},
            ]
        }
    ],
    "has_result": True,
}


def _bundle(code: str = CODE) -> ResolveGateServices:
    def _resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "tokens": [code],
            "resolutions": [
                {
                    "raw": code,
                    "token": code,
                    "matches": [
                        {
                            "uuid": PRODUCT_UUID,
                            "entity_type": "product",
                            "canonical_code": code,
                            # The tier the REAL resolver returns for every one of these
                            # codes, measured, not assumed.
                            "match_tier": "exact",
                        }
                    ],
                }
            ],
            "unresolved_tokens": [],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=_resolve_entity,
        probe=lambda **_: None,
    )


def _run_stock_turn(session_factory, monkeypatch, *, po_response, code: str = CODE):
    """A real stock turn for a product with NO stock, with the PO probe stubbed."""
    from app.models.user import SystemSetting
    from app.services.chatbot import engine as engine_mod

    set_chatbot_switches(session_factory, business_lane=True)
    db = session_factory()
    # EVERY row, not `.first()`: `system_settings` is a singleton in production, but the
    # fixtures can leave more than one in a blank schema and the engine reads its own.
    # Updating one and asserting on another is how this test first read "no ladder
    # configured" while the shipped default was right there.
    for row in db.query(SystemSetting).all():
        row.chatbot_completed_lanes = ["business_query"]
        # The 489 default, explicitly: the rung under test is what every tenant ships with.
        row.chatbot_crossdomain_ladder = {
            "inventory": ["incoming", "purchase_order"],
            "incoming": ["inventory"],
        }
    db.commit()

    probes: list[str] = []

    def _mcp_probe(name: str, args: dict) -> Any:
        probes.append(name)
        if name != PO_TOOL:
            return NO_ROWS
        # The probe answers about the code THIS turn asked about, so a parametrised run
        # cannot pass by echoing another case's rows.
        return {
            "answers": [
                {
                    "fields": [
                        {"key": "product_code", "label": "Product Code", "value": code},
                        *[f for f in (po_response["answers"][0]["fields"] if po_response.get("answers") else [])
                          if f.get("key") != "product_code"],
                    ]
                }
            ],
            "has_result": True,
        } if po_response.get("answers") else NO_ROWS

    bundle = _bundle(code)
    monkeypatch.setattr(
        engine_mod.business_services, "production_services", lambda db, *, space_id=None: bundle
    )
    monkeypatch.setattr(
        engine_mod.business_services,
        "fetch_services",
        lambda db: FetchServices(
            embed=lambda query: [0.0, 0.0, 0.0],
            tool_search=lambda embedding, *, query, domain: [
                {"name": "crm_inventory_stock_balance_list", "similarity": 0.9}
            ],
            mcp_call=lambda name, args: json.dumps(EMPTY_STOCK),
        ),
    )
    monkeypatch.setattr(
        engine_mod.business_services,
        "answer_services_for",
        lambda session_factory: AnswerServices(
            mcp_probe=_mcp_probe, family_fetch=lambda query: {"data": []}
        ),
    )

    result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
    said = "\n".join(
        [((result.reply or {}).get("text") or "")]
        + [a.get("text") or "" for a in (result.actions or []) if isinstance(a, dict)]
    )
    return result, said, probes


@pytest.fixture
def stock_parse(stub_parser, stub_access):
    stub_parser(
        _parser_output(
            intent_hint="check_stock",
            domain_hint="inventory",
            entities=[{"raw": CODE, "hint": "product", "current_message": True}],
        )
    )
    stub_access()


class TestAC921ThePORungReachesTheCustomer:
    def test_a_stock_miss_with_an_open_po_says_so(
        self, session_factory, seeded, stock_parse, system_settings_row, monkeypatch
    ) -> None:
        """Foundre's rule, the owner's named ask: no stock, no incoming, but a PO is
        placed. The unit tests of `run_crossdomain` were green while this was not, because
        they never asked whether the block reaches the REPLY."""
        result, said, probes = _run_stock_turn(
            session_factory, monkeypatch, po_response=PO_ROWS
        )
        assert result.status == "done", result.error
        assert PO_TOOL in probes, "the PO rung never ran on a real turn"
        assert "but a PO is placed" in said, said
        assert CODE in said
        assert "1000" in said and "2026" in said

    def test_the_supplier_is_never_in_the_rung_text(
        self, session_factory, seeded, stock_parse, system_settings_row, monkeypatch
    ) -> None:
        """AC-921's negative. The probe envelope CARRIES the supplier; the rung's line
        template has no slot for it, so it can never be rendered."""
        _, said, _ = _run_stock_turn(session_factory, monkeypatch, po_response=PO_ROWS)
        assert "GUANGDONG WORKS" not in said
        assert "supplier" not in said.lower()

    def test_the_escalate_offer_still_follows(
        self, session_factory, seeded, stock_parse, system_settings_row, monkeypatch
    ) -> None:
        _, said, _ = _run_stock_turn(session_factory, monkeypatch, po_response=PO_ROWS)
        assert "escalate" in said.lower()

    def test_the_rung_event_is_on_the_persisted_trace(
        self, session_factory, seeded, stock_parse, system_settings_row, monkeypatch
    ) -> None:
        """The console run could not tell whether the rung had run, because the events the
        LANE records were being dropped at the final write. AC-970's reader has to find
        them on a real turn or the turn-detail screen shows an empty crossdomain section
        for every business turn."""
        from app.models.chatbot_turn import ChatbotTurn

        result, _, _ = _run_stock_turn(session_factory, monkeypatch, po_response=PO_ROWS)
        row = (
            session_factory()
            .query(ChatbotTurn)
            .filter(ChatbotTurn.id == result.turn_id)
            .first()
        )
        events = [e for e in (row.trace or []) if isinstance(e, dict) and e.get("kind")]
        kinds = [e["kind"] for e in events]
        assert "tool" in kinds
        assert "crossdomain" in kinds, f"no crossdomain event persisted: {kinds}"
        rungs = [e.get("rung") for e in events if e["kind"] == "crossdomain"]
        assert "purchase_order" in rungs, rungs


class TestAC922NothingOnAnyRung:
    def test_no_stock_no_incoming_no_po_says_all_three(
        self, session_factory, seeded, stock_parse, system_settings_row, monkeypatch
    ) -> None:
        result, said, probes = _run_stock_turn(session_factory, monkeypatch, po_response=NO_ROWS)
        assert result.status == "done", result.error
        assert PO_TOOL in probes
        assert f"No stock, no incoming and no PO for {CODE}." in said, said
        assert "no purchase order" not in said
        assert "escalate" in said.lower()


class TestTheSuffixedCodeShapeReachesTheRung:
    """The console check's finding, pinned from the other end.

    Three hyphen-suffixed codes, the shape the live check found answering the bare miss
    with no cross-domain sentence at all. Measured against the REAL resolver, each comes
    back as exactly one product match at tier `exact` - the same as `CB2904` and
    `SRTWB103`, which do reach the rung live - so `crossdomain_zeroset` excludes no tier
    they land on, and there is no tier rule to widen. Given that resolution, each reaches
    the rung here.

    So the live difference is NOT the code shape and NOT the match tier. Whatever it is
    lives between the resolver and `crossdomain_zeroset`'s `returned_codes` / `missing` on
    those particular turns, and this class is what stops the next person spending the same
    hour on the tier again.
    """

    @pytest.mark.parametrize("code", SUFFIXED_CODES)
    def test_each_suffixed_code_gets_its_po_rung(
        self, code, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[{"raw": code, "hint": "product", "current_message": True}],
            )
        )
        stub_access()
        result, said, probes = _run_stock_turn(
            session_factory, monkeypatch, po_response=PO_ROWS, code=code
        )
        assert result.status == "done", result.error
        assert PO_TOOL in probes, f"{code}: the PO rung never ran"
        assert "but a PO is placed" in said, said
        assert code in said

    @pytest.mark.parametrize("code", SUFFIXED_CODES)
    def test_each_suffixed_code_gets_the_three_way_miss(
        self, code, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[{"raw": code, "hint": "product", "current_message": True}],
            )
        )
        stub_access()
        _, said, _ = _run_stock_turn(session_factory, monkeypatch, po_response=NO_ROWS, code=code)
        assert f"No stock, no incoming and no PO for {code}." in said, said
