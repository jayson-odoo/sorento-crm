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

from app.services.chatbot.lanes.business import answer as answer_mod
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
PO_TOOL = "crm_procurement_po_placed_list"

EMPTY_STOCK = {
    "result_type": "stock",
    "intro": "No matching results found.",
    "items": [],
    "has_result": False,
}
NO_ROWS = {"answers": [], "has_result": False}
EMPTY_INCOMING = {
    "result_type": "incoming",
    "intro": "No matching results found.",
    "items": [],
    "has_result": False,
}
PO_ROWS = {
    "answers": [
        {
            "fields": [
                {"key": "product_code", "label": "Product Code", "value": CODE},
                {"key": "ordered_qty", "label": "Ordered Qty", "value": 1000},
                {"key": "outstanding_qty", "label": "Outstanding Qty", "value": 1000},
                {"key": "location", "label": "Location", "value": "KL-WH"},
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


def _run_stock_turn(session_factory, monkeypatch, *, po_response, code: str = CODE, origin: str = "inventory"):
    """A real stock turn for a product with NO stock, with the PO probe stubbed. D7:
    `origin="incoming"` drives the same code from an incoming ask (the fetch answers with
    the empty incoming envelope; the stock probe finds nothing; the PO probe answers)."""
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
        # The 491 default, explicitly: the rung under test is what every tenant ships with
        # (D7: PO from either side).
        row.chatbot_crossdomain_ladder = {
            "inventory": ["incoming", "purchase_order"],
            "incoming": ["inventory", "purchase_order"],
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
        # The tool is not stubbed: the parse below carries `domain_hint` = `origin`, and
        # `select_tool` reads that domain's own tool off `DOMAIN_SPEC`
        # (`incoming` -> `crm_incoming_stock_list`, `inventory` ->
        # `crm_inventory_stock_balance_list`) - the two names this used to hand back.
        lambda db: FetchServices(
            mcp_call=lambda name, args: json.dumps(EMPTY_INCOMING if origin == "incoming" else EMPTY_STOCK),
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
    # The PO rung is per contact (8 Sep 2026): on-order info needs `purchase_orders.placed`.
    stub_access(attributes=["purchase_orders.placed"])


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
        assert "but PO is placed" in said, said
        assert CODE in said
        # Owner ruling, 11 Sep 2026: the structured field block - PO_ROWS carries no
        # `po_date`, so that line is omitted, but Ordered/Outstanding/Location print.
        assert "Ordered: 1000" in said and "Outstanding: 1000" in said
        assert "Location: KL-WH" in said
        assert "PO date" not in said

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
        assert f"No stock, no incoming and nothing on order for {CODE}." in said, said
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
        stub_access(attributes=["purchase_orders.placed"])  # the rung is per contact
        result, said, probes = _run_stock_turn(
            session_factory, monkeypatch, po_response=PO_ROWS, code=code
        )
        assert result.status == "done", result.error
        assert PO_TOOL in probes, f"{code}: the PO rung never ran"
        assert "but PO is placed" in said, said
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
        stub_access(attributes=["purchase_orders.placed"])  # the rung is per contact
        _, said, _ = _run_stock_turn(session_factory, monkeypatch, po_response=NO_ROWS, code=code)
        assert f"No stock, no incoming and nothing on order for {code}." in said, said


class TestIssue736SeparatorInsensitiveRequestedSet:
    """The one line that had Foundre's rule off for most of the catalogue (#736).

    `crossdomain_zeroset` builds its `requested` set by testing each resolved match's
    `canonical_code` for membership in the RESOLVER's token set. The resolver strips dashes
    and spaces from a product token before resolving it, so "SRTWT7445-LV-NEW" arrives as
    the token `SRTWT7445LVNEW` while the match it resolved to carries the hyphenated
    `canonical_code`. That test used `_norm_code` (strip + upper) on both sides, so it
    could never be true for a code with a separator: `requested` empty, `missing` empty,
    `active` False, `run_crossdomain` returning before it probed anything.

    Measured on two live turns whose traces are otherwise identical field for field
    (console-check-1788789839): `CB2904` - whose token and canonical code are the same
    string - got both rungs; `SRTWT7445-LV-NEW` got no cross-domain event at all.

    This class drives the ZEROSET with the resolver shape those live turns actually
    carried (an `intersection`, no `resolutions`, the token separator-stripped), which is
    the shape the rest of the file's stubs do not produce - and is therefore the shape that
    let the defect live.
    """

    @staticmethod
    def _zeroset_for(token: str, canonical_code: str):
        return answer_mod.crossdomain_zeroset(
            {"answers": [], "has_result": False},
            parser={
                "message_type": "business_query",
                "intent_hint": "check_stock",
                "domain_hint": "inventory",
                "access_levels": [],
            },
            resolved={
                # No `resolutions` key: the live gate stores its result as `tokens` +
                # `intersection`, which is the branch the defect was in.
                "tokens": [token],
                "intersection": [
                    {
                        "entity_type": "product",
                        "canonical_code": canonical_code,
                        "uuid": "9e1dc720-ab0b-4296-8852-1afcc77290a2",
                    }
                ],
            },
            session_block={"session_vars": {"variables": {}}},
        )

    @pytest.mark.parametrize(
        "token,code",
        [
            ("SRTWT7445LVNEW", "SRTWT7445-LV-NEW"),
            ("MSK11AQT", "MSK11A-QT"),
            ("CWCX1009SH", "CWCX1009-SH"),
            ("SRT 2405 CR", "SRT2405-CR"),
        ],
        ids=["srtwt7445", "msk11a", "cwcx1009", "spaced-token"],
    )
    def test_a_separator_stripped_token_still_matches_its_canonical_code(
        self, token, code
    ) -> None:
        xd = self._zeroset_for(token, code)["_xd"]
        assert xd["active"] is True, f"{code}: zeroset inactive, so no probe can run"
        assert xd["requested"] == [code]
        assert [m["code"] for m in xd["missing"]] == [code]

    def test_an_unseparated_code_is_unchanged(self) -> None:
        """`CB2904` is the control: it worked before this fix and must still work."""
        xd = self._zeroset_for("CB2904", "CB2904")["_xd"]
        assert xd["active"] is True
        assert xd["requested"] == ["CB2904"]

    def test_a_token_that_is_a_different_product_still_does_not_match(self) -> None:
        """The test is separator-insensitive, NOT fuzzy: a genuinely different code must
        still fail the membership test, or the zeroset would start declaring absences
        about products the customer never named (H62)."""
        xd = self._zeroset_for("SRTWT7445LVNEW", "SRTWB103")["_xd"]
        assert xd["active"] is False
        assert xd["requested"] == []


class TestOwner8SepTheRungIsPerContactAndOffersOnce:
    """Turns 0184d84d / 5f73ddb0 / 90a1637a (8 Sep 2026): the escalate question was said
    twice; and on-order information is a per-contact reveal (`purchase_orders.placed`)."""

    def test_with_the_grant_the_reply_carries_the_document_date_and_one_offer(
        self, session_factory, seeded, stock_parse, system_settings_row, monkeypatch
    ) -> None:
        po_row = {
            "fields": [
                {"key": "po_number", "label": "PO Number", "value": "202607-S0031"},
                {"key": "product_code", "label": "Product Code", "value": CODE},
                {"key": "ordered_qty", "label": "Ordered Qty", "value": 27},
                {"key": "outstanding_qty", "label": "Outstanding Qty", "value": 27},
                {"key": "po_date", "label": "PO Date", "value": "2026-06-30"},
            ]
        }
        result, said, probes = _run_stock_turn(
            session_factory, monkeypatch, po_response={"answers": [po_row], "has_result": True}
        )
        assert result.status == "done", result.error
        assert PO_TOOL in probes
        # Owner ruling, 11 Sep 2026: the structured field block, no per-document heading.
        assert (
            "but PO is placed:\n"
            "Product Code: SRTWT7445-LV-NEW\nOrdered: 27\nOutstanding: 27\nPO date: 2026-06-30"
        ) in said, said
        assert "Location" not in said  # po_row carries no location
        assert "pcs" not in said and "expected" not in said and "202607-S0031" not in said
        # `said` joins the reply with every send action's copy of it; the count is on the
        # reply text alone.
        text = (result.reply or {}).get("text") or ""
        assert text.count("Would you like me to escalate") == 1, text
        assert "escalate to purchasing team" in text

    def test_without_the_grant_no_probe_and_the_ladder_off_note(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[{"raw": CODE, "hint": "product", "current_message": True}],
            )
        )
        stub_access()  # no grants at all
        result, said, probes = _run_stock_turn(
            session_factory, monkeypatch, po_response={"answers": [{"fields": []}], "has_result": True}
        )
        assert result.status == "done", result.error
        assert PO_TOOL not in probes, "the PO rung must not probe without purchase_orders.placed"
        assert f"No stock and no incoming for {CODE}." in said, said
        assert "PO" not in said.replace("No stock and no incoming", "")
        text = (result.reply or {}).get("text") or ""
        assert text.count("Would you like me to escalate") == 1, text


class TestD7AnIncomingAskReachesThePORung:
    """D7 (owner ruling, 8 Sep 2026): "hav incoming?" on a zero-stock code with an open PO
    line climbs stock -> PO like a stock ask does, and the wording follows the climb."""

    def test_an_incoming_ask_on_a_zero_stock_code_gets_the_po_lines(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        stub_parser(
            _parser_output(
                intent_hint="check_incoming",
                domain_hint="incoming",
                entities=[{"raw": CODE, "hint": "product", "current_message": True}],
            )
        )
        stub_access(attributes=["purchase_orders.placed"])
        result, said, probes = _run_stock_turn(session_factory, monkeypatch, po_response=PO_ROWS, origin="incoming")
        assert result.status == "done", result.error
        # the incoming lane's own picker probe may sit beside them; the climb is what matters
        assert probes.index("crm_inventory_stock_balance_list") < probes.index(PO_TOOL)
        assert f"No incoming and no stock for {CODE}, but PO is placed:" in said, said
        # Owner ruling, 11 Sep 2026: PO_ROWS carries no `po_date`, so that line is omitted;
        # Ordered/Outstanding/Location still print, and the (irrelevant) expected date
        # never renders either way.
        assert (
            "but PO is placed:\n"
            f"Product Code: {CODE}\nOrdered: 1000\nOutstanding: 1000\nLocation: KL-WH"
        ) in said
        assert "PO date" not in said
        assert "expected" not in said and "2026-06-01" not in said
        assert "GUANGDONG" not in said
        text = (result.reply or {}).get("text") or ""
        assert text.count("Would you like me to escalate") == 1
