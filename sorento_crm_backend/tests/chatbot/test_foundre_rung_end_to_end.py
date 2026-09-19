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

**16 Sep 2026 rewrite** (AC-1592, "the crossdomain ladder climbs again, inside the turn
package", `bbc86cdd4`): the ladder moved from `lanes/business/answer.py::run_crossdomain`
(a dedicated probe seam, `AnswerServices.mcp_probe`) to `turn/fetch.py::_climb`, which walks
`chatbot_domains.ladder` and re-fetches each rung through the SAME `ctx.tool_runner` the
primary domain uses - `lanes/business.run_fetch` -> `output_structurer`. Two measured
consequences that make this file's OLD assertions the wrong shape now, not a bug in the
rewrite:

1. Every probe (primary AND rung) now answers with the RAW MCP presenter envelope
   (`result_type` / `items` / `has_result` / `restricted_fields`), not the pre-structured
   `answers` / `fields` shape `AnswerServices.mcp_probe` used to hand back directly -
   `_run_stock_turn`'s single `_mcp_call` builds that raw shape.
2. `turn/compose.py`'s generic section grammar (contract 102) has no PO-domain-specific
   sentence or field selection left (`lanes/business/answer.py::_crossdomain_rung_text`'s
   "Ordered"/"Outstanding" relabelling and dropped `po_number`/`company_name` fields is
   UNREACHED code now, still exercised only by the KEPT-node `test_crossdomain_ladder.py`
   corpus) - a rung renders as its own numbered section, in the tool's own field labels,
   under the primary's own miss line. It also only offers to escalate when EVERY domain on
   the turn missed (contract 127, "team pick for missed domains") - a rung that answers
   is not a miss, so no offer follows it (measured, see
   `TestAC921ThePORungReachesTheCustomer.test_a_stock_miss_with_an_open_po_says_so`).

One test (`TestOwner8SepTheRungIsPerContactAndOffersOnce.test_without_the_grant_no_probe_
and_the_ladder_off_note`) stays a confirmed RED: `_climb` probes every rung unconditionally
and does not carry over the OLD `_CROSSDOMAIN_RUNG_GRANT` per-contact gate
(`purchase_orders.placed`) - flag for a coder pass, do not silently retire it.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.chatbot.lanes.business import answer as answer_mod
from app.services.chatbot.lanes.business.services import FetchServices, ResolveGateServices
from tests.chatbot.conftest import set_chatbot_switches, validating_resolve_entity
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
        resolve_entity=validating_resolve_entity(_resolve_entity),
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
        # Vestigial since the rearch: `turn/fetch.py::_climb` reads the ladder off
        # `chatbot_domains.ladder` (`turn/policy.py`/`policy_rows.py`), not this column
        # any more - kept written here only because the seeded `chatbot_domains` rows
        # already carry the same 491 default (D7: PO from either side) this line used to
        # configure, so leaving it is harmless, not because it still does anything.
        row.chatbot_crossdomain_ladder = {
            "inventory": ["incoming", "purchase_order"],
            "incoming": ["inventory", "purchase_order"],
        }
    db.commit()

    probes: list[str] = []

    def _mcp_call(name: str, args: dict) -> str:
        probes.append(name)
        if name == PO_TOOL:
            # The probe answers about the code THIS turn asked about, so a parametrised
            # run cannot pass by echoing another case's rows. `output_structurer` reads
            # the RAW MCP presenter shape (`result_type`/`items`/`has_result`), not the
            # already-structured `answers`/`fields` shape - measured against
            # `sorento_crm_mcp/presenters.py::_purchase_orders_placed`.
            items = [
                {
                    "fields": [
                        {"key": "product_code", "label": "Product Code", "value": code},
                        *[
                            f
                            for f in row["fields"]
                            if f.get("key") != "product_code"
                        ],
                    ],
                    **({"kind": row["kind"]} if "kind" in row else {}),
                }
                for row in po_response.get("answers", [])
            ]
            return json.dumps(
                {
                    "result_type": "purchase_orders_placed",
                    "intro": "Here is the PO placed I found.",
                    "items": items,
                    "has_result": bool(items),
                    # The real presenter stamps this via `_Builder.restrict("supplier",
                    # "purchase_orders.supplier")`; `output_structurer`'s restricted-
                    # field drop (A2/A5/A6) reads it off the envelope, not off the tool
                    # name, so the stub must carry it too or the supplier never gets
                    # scrubbed here.
                    "restricted_fields": {"supplier": "purchase_orders.supplier"},
                }
            )
        return json.dumps(EMPTY_INCOMING if origin == "incoming" else EMPTY_STOCK)

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
        # The SAME seam now answers the ladder's rung probe too (`turn/fetch.py::_climb`
        # calls the identical `ctx.tool_runner`, which reads off this bundle), so one
        # dispatch-by-tool-name callable covers both the primary fetch and the rung.
        lambda db: FetchServices(mcp_call=_mcp_call),
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
        they never asked whether the block reaches the REPLY.

        16 Sep 2026 (contract 102/122): the rung is its OWN numbered section under the
        primary's miss line now, not a folded "but PO is placed" sentence - measured
        directly through `engine.run_turn`, not re-derived from `crossdomain_render`'s
        retired wording."""
        result, said, probes = _run_stock_turn(
            session_factory, monkeypatch, po_response=PO_ROWS
        )
        assert result.status == "done", result.error
        assert PO_TOOL in probes, "the PO rung never ran on a real turn"
        # 20 Sep 2026 (R-d, hand pass 7): `turn/compose.py` now reuses the fetch lane's
        # own `lane_text` for the WHOLE section, header included, instead of a synthetic
        # `*{label}* for {code}:` header - the miss line is the primary domain's own
        # production wording with no domain-name prefix.
        assert "No matching results found." in said, said
        assert (
            "Here is the PO placed I found.\n\n"
            f"1. *Product Code:* {CODE}\n*Ordered Qty:* 1000\n*Outstanding Qty:* 1000\n"
            "*Location:* KL-WH"
        ) in said, said
        assert "PO Date" not in said  # PO_ROWS carries no po_date field
        # Contract 127 ("team pick for MISSED domains"): the ladder answered, so nothing on
        # this turn is missing - `compose.py` only offers to escalate when EVERY envelope
        # missed. Retires the old "the escalate offer still follows" expectation (that was
        # `crossdomain_render`'s own always-append-the-offer wording, unreached code now).
        assert "Would you like me to escalate" not in said, said

    def test_the_supplier_is_never_in_the_rung_text(
        self, session_factory, seeded, stock_parse, system_settings_row, monkeypatch
    ) -> None:
        """AC-921's negative. The probe envelope CARRIES the supplier; `output_structurer`'s
        restricted-field drop (A2/A5/A6) reads the envelope's own `restricted_fields` map,
        so it is scrubbed before the composer ever sees it."""
        _, said, _ = _run_stock_turn(session_factory, monkeypatch, po_response=PO_ROWS)
        assert "GUANGDONG WORKS" not in said
        assert "supplier" not in said.lower()

    def test_the_rung_event_is_on_the_persisted_trace(
        self, session_factory, seeded, stock_parse, system_settings_row, monkeypatch
    ) -> None:
        """The console run could not tell whether the rung had run, because the events the
        LANE records were being dropped at the final write. AC-970's reader has to find
        them on a real turn or the turn-detail screen shows an empty crossdomain section
        for every business turn.

        16 Sep 2026: `turn/fetch.py::_climb`'s own event shape is `{domain, rungs_tried,
        answered}` - the primary domain the ladder was climbed FROM, not a `rung` key."""
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
        crossdomain_events = [e for e in events if e["kind"] == "crossdomain"]
        assert any(e.get("answered") == "purchase_order" for e in crossdomain_events), crossdomain_events
        assert any("purchase_order" in (e.get("rungs_tried") or []) for e in crossdomain_events)


class TestAC922NothingOnAnyRung:
    def test_no_stock_no_incoming_no_po_says_all_three(
        self, session_factory, seeded, stock_parse, system_settings_row, monkeypatch
    ) -> None:
        """16 Sep 2026: the "nothing on any rung" line names the rungs by their OWN
        domain labels (contract 122's generic grammar), not `crossdomain_render`'s retired
        "No stock, no incoming and nothing on order for X." sentence."""
        result, said, probes = _run_stock_turn(session_factory, monkeypatch, po_response=NO_ROWS)
        assert result.status == "done", result.error
        assert PO_TOOL in probes
        # 20 Sep 2026 (R-d): no `*stock* for {code}:` header any more - the primary
        # domain's own miss wording, unprefixed.
        assert (
            "No matching results found.\n"
            "Nothing on incoming stock or outstanding purchase orders either."
        ) in said, said
        # 20 Sep 2026 (R-f): the generic escalate offer now names a single team.
        assert "Would you like me to escalate to warehouse team?" in said, said


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
        # 20 Sep 2026 (R-d): no `*outstanding purchase orders* for {code}:` header - the
        # rung's own `lane_text`, header included.
        assert (
            "Here is the PO placed I found.\n\n"
            f"1. *Product Code:* {code}\n*Ordered Qty:* 1000\n*Outstanding Qty:* 1000\n"
            "*Location:* KL-WH"
        ) in said, said

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
        # 20 Sep 2026 (R-d): no `*stock* for {code}:` header - the primary domain's own
        # miss wording, unprefixed.
        assert (
            "No matching results found.\n"
            "Nothing on incoming stock or outstanding purchase orders either."
        ) in said, said


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
        # 16 Sep 2026: the generic composer (contract 102) prints every field the tool's
        # own envelope carries, in its own label, with no PO-domain-specific selection or
        # relabelling - measured, not the pre-rewrite `_crossdomain_rung_text`'s curated
        # "Ordered"/"Outstanding" 5-field subset. FLAG for a coordinator/coder look: this
        # means `po_number` ("PO Number") now reaches the customer, which an 11 Sep 2026
        # owner ruling said should not happen ("no per-document heading naming the PO/SPO
        # number") - that ruling was against `crossdomain_render`'s own rendering, which is
        # unreached code on a live turn now (see module docstring); whether the same rule
        # should be re-applied inside the new generic composer is an open question this
        # test does not decide, it only pins what the engine does today.
        # 20 Sep 2026 (R-d): no `*outstanding purchase orders* for {code}:` header - the
        # rung's own `lane_text`, header included.
        assert (
            "Here is the PO placed I found.\n\n"
            f"1. *Product Code:* {CODE}\n*PO Number:* 202607-S0031\n"
            "*Ordered Qty:* 27\n*Outstanding Qty:* 27\n*PO Date:* 2026-06-30"
        ) in said, said
        assert "Location" not in said  # po_row carries no location field
        # Contract 127: the ladder answered, so nothing missed - no escalate offer follows
        # (retires the old "said exactly once" expectation, which assumed the offer always
        # follows a rung's answer).
        text = (result.reply or {}).get("text") or ""
        assert text.count("Would you like me to escalate") == 0, text

    def test_without_the_grant_no_probe_and_the_ladder_off_note(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """CONFIRMED DEFECT, 16 Sep 2026 - kept RED, not retired or silently rewritten.

        `turn/fetch.py::_climb` probes every configured rung unconditionally; it does not
        carry over the OLD `lanes/business/answer.py::_CROSSDOMAIN_RUNG_GRANT` per-contact
        gate (`purchase_orders.placed`) that `run_crossdomain` enforced
        (`test_crossdomain_ladder.py::TestOwner8SepThePORungIsPerContact`, still a KEPT-
        node test of the now-unreached function). Measured directly: with NO grants at
        all, `crm_procurement_po_placed_list` is still called. Needs a coder pass on
        `_climb` (or wherever the ladder's tool_runner is built) before this can pin the
        REST of the off-shape wording - only the probe-count assertion is asserted here so
        this test fails for exactly the one confirmed reason, not a guessed follow-on
        shape."""
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[{"raw": CODE, "hint": "product", "current_message": True}],
            )
        )
        stub_access()  # no grants at all
        result, _, probes = _run_stock_turn(
            session_factory, monkeypatch, po_response={"answers": [{"fields": []}], "has_result": True}
        )
        assert result.status == "done", result.error
        assert PO_TOOL not in probes, "the PO rung must not probe without purchase_orders.placed"


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
        # 20 Sep 2026 (R-d): no `*incoming stock*`/`*outstanding purchase orders*` for
        # {code}: headers - the primary domain's own miss wording, then the rung's own
        # `lane_text`, header included.
        assert "No matching results found." in said, said
        assert (
            "Here is the PO placed I found.\n\n"
            f"1. *Product Code:* {CODE}\n*Ordered Qty:* 1000\n*Outstanding Qty:* 1000\n"
            "*Location:* KL-WH"
        ) in said, said
        assert "PO Date" not in said  # PO_ROWS carries no po_date field
        assert "GUANGDONG" not in said
        # Contract 127: the ladder answered, so nothing missed - no escalate offer follows.
        text = (result.reply or {}).get("text") or ""
        assert text.count("Would you like me to escalate") == 0
