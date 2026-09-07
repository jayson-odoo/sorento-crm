"""The review findings on `feat/chatbot-growth-data`, one test class each.

Every one of these is a defect the unit tests of the feature passed straight over, because
each lives in the SECOND rendering of the same data: the grouped shape carries the rows a
second time, the ladder carries the absence a second time, and the summary carries the
filter a second time. That is the shape worth remembering more than any individual fix.

  blocker 1  the restricted-field drop ran over `items` only, so `group_by` rendered the
             supplier a dealer must never see - and `group_by=supplier` put it in the
             SECTION HEADING, where no field filter could ever reach it (AC-907, D4).
  blocker 2  the ladder read `nothing_codes` without `can_state_absence`, so a stock turn
             that printed a warehouse breakdown could get "no stock and no incoming, but a
             PO is placed" appended underneath the stock it had just shown.
  should-fix 4  a grouped answer renumbered the rows on screen and left `answers` flat, so
             a positional pick resolved to a different record than the one numbered.
  should-fix 9  AC-922 asks for "no PO", the code said "no purchase order".

Blocker 3 (company scope on the two new ToolSpecs) is graded where the other scoped tools
are: `sorento_crm_mcp/tests/test_company_scope_params.py`.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.lanes.business import answer as answer_mod
from app.services.chatbot.lanes.business import fetch
from app.services.chatbot.lanes.business.services import AnswerServices

SUPPLIER_PERM = "purchase_orders.supplier"


# --------------------------------------------------------------------------- #
# Blocker 1 - the restricted field, through the GROUPED shape.
# --------------------------------------------------------------------------- #


def _po_row(po: str, product: str, supplier: str) -> dict:
    return {
        "title": po,
        "fields": [
            {"key": "po_number", "label": "PO Number", "value": po},
            {"key": "product_code", "label": "Product Code", "value": product},
            {"key": "outstanding_qty", "label": "Outstanding Qty", "value": 100},
            {"key": "supplier", "label": "Supplier", "value": supplier},
        ],
    }


def _po_envelope(*, group_by: str | None, with_summary: bool = False) -> dict:
    rows = [
        _po_row("PO-1", "C-FH14", "GUANGDONG WORKS"),
        _po_row("PO-2", "C-FH14", "FOSHAN METALS"),
    ]
    envelope: dict = {
        "result_type": "purchase_orders_placed",
        "intro": "Here is the PO placed I found.",
        "items": rows,
        "restricted_fields": {"supplier": SUPPLIER_PERM},
        "has_result": True,
    }
    if with_summary:
        # `summary_items` switches the renderer to SUMMARY-ONLY (a quantity ask prints no
        # rows), so it is opt-in here: every other case in this class needs the rows.
        envelope["summary_items"] = [
            {
                "title": "Summary",
                "fields": [
                    {"key": "po_placed_qty", "label": "PO placed", "value": 200},
                    {"key": "supplier", "label": "Supplier", "value": "GUANGDONG WORKS"},
                ],
            }
        ]
    if group_by == "supplier":
        envelope["groups"] = [
            {"key": "GUANGDONG WORKS", "label": "GUANGDONG WORKS", "items": [rows[0]]},
            {"key": "FOSHAN METALS", "label": "FOSHAN METALS", "items": [rows[1]]},
        ]
    elif group_by == "product":
        envelope["groups"] = [{"key": "C-FH14", "label": "C-FH14", "items": list(rows)}]
    return envelope


def _ctx(*, group_by: str | None = None, granted: list[str] | None = None) -> dict:
    semantic_input: dict = {}
    if group_by:
        semantic_input["group_by"] = group_by
    return {
        "semantic_input": semantic_input,
        "access": {"attributes": granted},
    }


class TestBlocker1SupplierNeverLeaksThroughGroupBy:
    def test_a_dealer_grouping_by_product_sees_no_supplier(self) -> None:
        """The grouped rows are a SECOND copy of the same fields, and the first cut
        filtered only the flat `items` - so every dealer grouping a PO answer read every
        supplier."""
        out = fetch.output_structurer(_po_envelope(group_by="product"), _ctx(group_by="product"))
        assert "GUANGDONG WORKS" not in out["response"]
        assert "FOSHAN METALS" not in out["response"]
        assert "PO-1" in out["response"] and "C-FH14" in out["response"]

    def test_a_dealer_grouping_by_supplier_gets_an_ungrouped_answer(self) -> None:
        """The heading IS the restricted value, so redacting fields cannot help: the axis
        is refused and the answer rendered flat."""
        envelope = _po_envelope(group_by="supplier")
        out = fetch.output_structurer(envelope, _ctx(group_by="supplier"))
        assert "GUANGDONG WORKS" not in out["response"]
        assert "FOSHAN METALS" not in out["response"]
        assert "PO-1" in out["response"] and "PO-2" in out["response"]
        assert envelope["group_by_dropped"] == "supplier"
        assert envelope["groups"] == []

    def test_the_summary_item_is_filtered_too(self) -> None:
        out = fetch.output_structurer(_po_envelope(group_by=None, with_summary=True), _ctx())
        assert "GUANGDONG WORKS" not in out["response"]
        assert "PO placed" in out["response"]

    def test_a_granted_contact_sees_the_supplier_and_keeps_the_grouping(self) -> None:
        """The other half of the gate: with the grant, both the field and the axis come
        back. A rule that only ever hides is not a gate, it is a deletion."""
        envelope = _po_envelope(group_by="supplier")
        out = fetch.output_structurer(
            envelope, _ctx(group_by="supplier", granted=[SUPPLIER_PERM])
        )
        assert "GUANGDONG WORKS" in out["response"]
        assert "FOSHAN METALS" in out["response"]
        assert "group_by_dropped" not in envelope
        assert len(envelope["groups"]) == 2

    def test_a_granted_contact_grouping_by_product_sees_the_supplier_field(self) -> None:
        out = fetch.output_structurer(
            _po_envelope(group_by="product"), _ctx(group_by="product", granted=[SUPPLIER_PERM])
        )
        assert "GUANGDONG WORKS" in out["response"]

    def test_an_unrestricted_axis_is_never_refused(self) -> None:
        """`group_by=product` is not in `restricted_fields`, so the axis stands whatever
        the grant is - the refusal keys on the restriction, never on grouping itself."""
        envelope = _po_envelope(group_by="product")
        fetch.output_structurer(envelope, _ctx(group_by="product"))
        assert "group_by_dropped" not in envelope
        assert len(envelope["groups"]) == 1


# --------------------------------------------------------------------------- #
# should-fix 4 - a positional pick after a grouped answer.
# --------------------------------------------------------------------------- #


class TestShouldFix4GroupedAnswersMatchTheNumbering:
    def test_answers_are_in_the_order_the_message_numbered_them(self) -> None:
        """Rows A, B, A grouped by product renumber as A, A, B on screen. `answers` is what
        a positional pick resolves against, so "2" must be the SECOND ROW PRINTED."""
        def _row(po: str, product: str) -> dict:
            return {
                "title": po,
                "fields": [
                    {"key": "po_number", "label": "PO Number", "value": po},
                    {"key": "product_code", "label": "Product Code", "value": product},
                ],
            }

        a1, b1, a2 = _row("PO-1", "AAA"), _row("PO-2", "BBB"), _row("PO-3", "AAA")
        envelope = {
            "result_type": "purchase_orders_placed",
            "intro": "Here is the PO placed I found.",
            "items": [a1, b1, a2],
            "groups": [
                {"key": "AAA", "label": "AAA", "items": [a1, a2]},
                {"key": "BBB", "label": "BBB", "items": [b1]},
            ],
            "has_result": True,
        }
        out = fetch.output_structurer(envelope, _ctx(group_by="product"))
        assert [a["title"] for a in out["answers"]] == ["PO-1", "PO-3", "PO-2"]
        # And that really is the printed order, not just a list we like the look of.
        response = out["response"]
        assert response.index("PO-1") < response.index("PO-3") < response.index("PO-2")

    def test_an_ungrouped_answer_is_untouched(self) -> None:
        rows = [_po_row("PO-1", "C-FH14", "X"), _po_row("PO-2", "C-FH14", "Y")]
        envelope = {
            "result_type": "purchase_orders_placed",
            "intro": "Here is the PO placed I found.",
            "items": rows,
            "has_result": True,
        }
        out = fetch.output_structurer(envelope, _ctx())
        assert out["answers"] is envelope["items"]


# --------------------------------------------------------------------------- #
# Blocker 2 - the ladder and `can_state_absence`.
# --------------------------------------------------------------------------- #

DEFAULT_LADDER = {"inventory": ["incoming", "purchase_order"], "incoming": ["inventory"]}
NO_PO_LADDER = {"inventory": ["incoming"], "incoming": ["inventory"]}
PO_TOOL = "crm_procurement_purchase_orders_placed_list"
INCOMING_TOOL = "crm_incoming_stock_list"

PARSER = {
    "message_type": "business_query",
    "intent_hint": "check_stock",
    "domain_hint": "inventory",
    "user_goal": "check stock for SRTWT7445-LV-NEW",
    "access_levels": [],
    "routing": {"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
}
CODE = "SRTWT7445-LV-NEW"
UUID = "11111111-1111-1111-1111-111111111111"

WAREHOUSE_BREAKDOWN = {
    # The render `can_state_absence` exists for: it ANSWERED (has rows, `has_result`), and
    # it named warehouses rather than the product code. "The render did not echo this code"
    # is therefore NOT the same statement as "this code has nothing".
    "answers": [
        {"fields": [{"label": "Warehouse", "value": "MAIN"}, {"label": "Quantity On Hand", "value": 40}]},
        {"fields": [{"label": "Warehouse", "value": "KL2"}, {"label": "Quantity On Hand", "value": 12}]},
    ],
    "has_result": True,
    "response": "MAIN: 40\nKL2: 12",
}
TOTAL_MISS = {
    # Nothing came back at all, so absence IS statable.
    "answers": [{"fields": [{"label": "Product Code", "value": "SRTOTHER"}]}],
    "response": "Some other stock line.",
}
PO_ROWS = {
    "answers": [
        {
            "fields": [
                {"key": "product_code", "label": "Product Code", "value": CODE},
                {"key": "outstanding_qty", "label": "Outstanding Qty", "value": 1000},
                {"key": "expected_date", "label": "Expected Date", "value": "2026-06-01"},
            ]
        }
    ],
    "has_result": True,
}
NO_ROWS = {"answers": [], "has_result": False}


def _run_ladder(*, validator, ladder, po_response=NO_ROWS, parser=None):
    """`run_crossdomain` end to end, the same seam `test_crossdomain_ladder.py` uses.

    Every input is DEEP-COPIED. `run_crossdomain` mutates what it is handed (the render is
    built over the validator and the rung stamps the parser's routing), and the module-level
    fixtures below are shared - one test's mutation reached the next one's assertions until
    this copy existed, which is a fixture bug that reads exactly like a code bug.
    """
    import copy

    calls: list[str] = []
    parser = copy.deepcopy(PARSER) if parser is None else parser
    validator = copy.deepcopy(validator)
    po_response = copy.deepcopy(po_response)

    def mcp_probe(name: str, args: dict) -> dict:
        calls.append(name)
        return NO_ROWS if name == INCOMING_TOOL else po_response

    result = answer_mod.run_crossdomain(
        validator,
        parser=parser,
        resolved={
            "resolutions": [
                {
                    "token": CODE,
                    "matches": [
                        {
                            "entity_type": "product",
                            "canonical_code": CODE,
                            "uuid": UUID,
                            "match_tier": "exact",
                        }
                    ],
                }
            ]
        },
        session_block={"session_vars": {"variables": {}}},
        entities_names=None,
        services=AnswerServices(mcp_probe=mcp_probe, family_fetch=lambda q: {"data": []}),
        contact_id="437264483",
        space_id="364817",
        crossdomain_ladder=ladder,
        granted=["purchase_orders.placed"],  # the PO rung is per contact (8 Sep 2026)
    )
    return result, calls


class TestBlocker2TheLadderRespectsCanStateAbsence:
    @pytest.mark.parametrize(
        "ladder", [None, {}, NO_PO_LADDER, DEFAULT_LADDER],
        ids=["no-ladder", "empty", "no-po-rung", "489-default"],
    )
    def test_a_warehouse_breakdown_never_reaches_the_po_rung(self, ladder) -> None:
        """PARAMETRISED over the ladder, deliberately: the pre-fix guard tests all ran with
        no ladder configured, so none of them could have caught a rung that fires only when
        one IS - and migration 489 ships a `purchase_order` rung on `inventory` for every
        tenant, so the default is the case that matters."""
        result, calls = _run_ladder(
            validator=WAREHOUSE_BREAKDOWN, ladder=ladder, po_response=PO_ROWS
        )
        block = result["render"]["_xdBlock"]
        assert PO_TOOL not in calls, "the ladder probed a turn that cannot state absence"
        assert block["nothing_codes"] == []
        assert block["nothing_missing"] == []
        assert "but PO is placed" not in (block["block"] or "")
        assert "No stock" not in (block["block"] or "")

    def test_a_total_miss_still_reaches_the_rung(self) -> None:
        """The other side of the gate: the fix must not turn the feature off."""
        result, calls = _run_ladder(
            validator=TOTAL_MISS, ladder=DEFAULT_LADDER, po_response=PO_ROWS
        )
        assert PO_TOOL in calls
        assert "but PO is placed" in result["render"]["_xdBlock"]["block"]


class TestShouldFix89TheRungSentenceAndTeam:
    def test_ac922_says_no_po_not_no_purchase_order(self) -> None:
        result, _ = _run_ladder(validator=TOTAL_MISS, ladder=DEFAULT_LADDER, po_response=NO_ROWS)
        block = result["render"]["_xdBlock"]["block"]
        assert f"No stock, no incoming and nothing on order for {CODE}." in block
        assert "no purchase order" not in block

    def test_the_rung_that_answered_sets_the_turns_escalation_team(self) -> None:
        """The sentence offers `purchasing`; `tail/pending.escalation_team` reads the
        turn's own routing, which for a stock question is `warehouse`. One team, or the
        customer is told one thing and handed to another (the H64 shape)."""
        from app.services.chatbot.tail.pending import escalation_team

        parser = {**PARSER, "routing": {"suggested_team": "warehouse", "suggested_agent": None}}
        result, _ = _run_ladder(
            validator=TOTAL_MISS, ladder=DEFAULT_LADDER, po_response=PO_ROWS, parser=parser
        )
        block = result["render"]["_xdBlock"]
        assert "but PO is placed" in block["block"]
        # the offer itself is compose's (8 Sep 2026); the TEAM it will name is the block's
        assert "escalate" not in block["block"].lower()
        assert block["team"] == "purchasing"
        assert escalation_team(parser, None) == "purchasing"
        assert parser["crossdomain_rung_team"] == "purchasing"

    def test_a_rung_that_never_fires_leaves_the_routing_alone(self) -> None:
        parser = {**PARSER, "routing": {"suggested_team": "warehouse", "suggested_agent": None}}
        _run_ladder(
            validator=WAREHOUSE_BREAKDOWN,
            ladder=DEFAULT_LADDER,
            po_response=PO_ROWS,
            parser=parser,
        )
        assert parser["routing"]["suggested_team"] == "warehouse"
        assert "crossdomain_rung_team" not in parser


# --------------------------------------------------------------------------- #
# nit 10 - a blank `requested_attributes` entry shifted the miss label.
# --------------------------------------------------------------------------- #


class TestNit10ABlankRequestedAttributeDoesNotShiftTheLabel:
    def test_the_miss_sentence_names_the_word_that_missed(self) -> None:
        envelope = {
            "result_type": "products",
            "intro": "Here are the products I found.",
            "items": [
                {
                    "title": "SRTKT73SS",
                    "fields": [
                        {"key": "product_code", "label": "Product Code", "value": "SRTKT73SS"},
                        {"key": "spec:steel_grade", "label": "Steel grade", "value": "304"},
                    ],
                }
            ],
            "spec_vocabulary": {"steel_grade": "Steel grade"},
            "has_result": True,
        }
        # A blank entry between two real ones: the parallel-list lookup used to read
        # `req_attrs[index_in_the_filtered_list]` and name the WRONG attribute.
        out = fetch.output_structurer(
            envelope,
            {"semantic_input": {"requested_attributes": ["  ", "steel grade", "flange width"]}},
        )
        response = out["response"]
        assert "304" in response
        assert "*flange width:* not recorded for SRTKT73SS" in response
        assert "no steel grade recorded" not in response


# --------------------------------------------------------------------------- #
# Owner report, 8 Sep 2026 (the :8080 hands-on run). Two defects on the same
# three messages: "check stock srtwc286" -> "PO for SRTWC8517" -> "last in ...".
# --------------------------------------------------------------------------- #


def _emission(**over):
    """A parser emission with every key `_assert_emission` requires."""
    base = {
        "message_type": "business_query", "intent_hint": None, "domain_hint": None,
        "scope_intent": None, "is_affirmative": None, "user_goal": None,
        "access_levels": [], "date_mode": None, "date_filter_start": None,
        "date_filter_end": None, "match_mode": "and", "demand_qty": None, "entities": [],
        "entity_op": None, "scope_exclusive": None, "requested_attributes": [],
        "contains_flyer": None, "reference_positions": [], "reference_target": None,
        "person_mention": None, "is_active": None, "order_status": None,
        "correction": None, "routing": {"suggested_team": None, "suggested_agent": None},
        "escalation": {"is_escalation_confirmation": False, "company_pick": None},
    }
    base.update(over)
    return base


def _post(emission, previous=None, latest="PO for SRTWC8517"):
    from app.services.chatbot.head.output_exchange import output_exchange

    # `_unwrap` returns `json_item["output"]` when it is a dict, and `_post_process`
    # then reads `.output` off THAT - so the node's own item shape is doubly wrapped.
    return output_exchange(
        {"output": {"output": emission}},
        {
            "previous_conversation_state": previous or {},
            "latest_user_message": latest,
            "previous_response": "",
        },
    )["output"]


class TestOwner8SepPOAskTypesTheCodeAsAProduct:
    """Defect 1. `broaden_dropped: ["order:SRTWC8517"]` - the code the customer typed was
    hinted `order`, `DOMAIN_BLOCKED_HINTS["purchase_order"]` threw it away, and the lane
    answered about a product CARRIED from an earlier turn."""

    @pytest.mark.parametrize("hint", ["order", "order_number", "customer_order"])
    @pytest.mark.parametrize("domain", ["purchase_order", "spo_allocation"])
    def test_an_order_hinted_product_code_is_retyped(self, hint, domain) -> None:
        out = _post(
            _emission(
                intent_hint="check_po" if domain == "purchase_order" else "check_spo",
                domain_hint=domain,
                entities=[{"raw": "SRTWC8517", "hint": hint, "current_message": True}],
            )
        )
        assert [e["hint"] for e in out["entities"]] == ["product"]
        assert out["order_hint_retyped_to_product"] == ["SRTWC8517"]
        assert "broaden_dropped" not in out

    def test_a_real_document_number_is_not_retyped(self) -> None:
        """The negative that keeps this narrow: `202602-S0002` is a PO number, and a rule
        that retyped it would make every document ask a product ask."""
        out = _post(
            _emission(
                intent_hint="check_po",
                domain_hint="purchase_order",
                entities=[{"raw": "202602-S0002", "hint": "order", "current_message": True}],
            )
        )
        assert "order_hint_retyped_to_product" not in out

    def test_the_order_domain_is_untouched(self) -> None:
        """Scoped to the two domains whose tools take `product_ids` and no order id. Under
        `order`, an order-hinted code is exactly what it says."""
        out = _post(
            _emission(
                intent_hint="check_order",
                domain_hint="order",
                entities=[{"raw": "SRTWC8517", "hint": "order", "current_message": True}],
            )
        )
        assert "order_hint_retyped_to_product" not in out

    def test_a_carried_code_is_refused_rather_than_answered(self) -> None:
        """Defect 1(c), the owner's complaint in its purest form: every entity the customer
        named this turn was dropped and a CARRIED one survived, so the PO tool would have
        answered about a code they never typed. Refuse the scope instead."""
        out = _post(
            _emission(
                intent_hint="check_po",
                domain_hint="purchase_order",
                entities=[
                    # Not product-shaped, so the retype above cannot save it.
                    {"raw": "my order", "hint": "order", "current_message": True},
                ],
            ),
            # The carried product arrives the way it does live: off the PREVIOUS state,
            # merged back by the entity-op executor, not typed into this turn's emission.
            previous={
                "domain_hint": "purchase_order",
                "entities": [
                    {"raw": "SRTKS7547-BL-NEW", "hint": "product", "current_message": False}
                ],
            },
        )
        assert out["entities"] == []
        assert out["entities_emptied_by_filter"] is True
        assert out["carried_scope_refused"] == ["SRTKS7547-BL-NEW"]

    def test_a_surviving_current_entity_keeps_the_carried_one(self) -> None:
        """The other side: reuse is what this engine is built on, so a carried entity only
        goes when NOTHING the customer named this turn survived."""
        out = _post(
            _emission(
                intent_hint="check_po",
                domain_hint="purchase_order",
                entities=[
                    {"raw": "SRTWC8517", "hint": "product", "current_message": True},
                ],
            ),
            previous={
                "domain_hint": "purchase_order",
                "entities": [
                    {"raw": "SRTKS7547-BL-NEW", "hint": "product", "current_message": False}
                ],
            },
        )
        assert "SRTWC8517" in [e["raw"] for e in out["entities"]]
        assert "carried_scope_refused" not in out


class TestOwner8SepANewAskIsNeverAnEscalationYes:
    """Defect 2. After a stock answer offering to escalate, "PO for SRTWC8517" came back
    `request_for_help` with `is_escalation_confirmation: true`, so a fresh product question
    confirmed an offer the customer had ignored."""

    _OFFERED = {
        "response": "Would you like me to escalate to Mocha warehouse team?",
        "pending": {"kind": "escalation_offer", "team": "warehouse"},
    }

    def test_a_business_ask_over_an_open_offer_is_not_a_confirmation(self) -> None:
        out = _post(
            _emission(
                message_type="request_for_help",
                intent_hint="check_po",
                domain_hint="purchase_order",
                entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
                escalation={"is_escalation_confirmation": True, "company_pick": None},
            ),
            previous=self._OFFERED,
        )
        assert out["escalation"]["is_escalation_confirmation"] is False

    def test_a_bare_yes_is_still_a_confirmation(self) -> None:
        """The half that must NOT move: an acceptance names no product, which is what lets
        the flag carry it."""
        out = _post(
            _emission(
                message_type="request_for_help",
                intent_hint=None,
                entities=[],
                is_affirmative=True,
                escalation={"is_escalation_confirmation": True, "company_pick": None},
            ),
            previous=self._OFFERED,
            latest="yes escalate",
        )
        assert out["escalation"]["is_escalation_confirmation"] is True

    def test_a_carried_entity_alone_does_not_defuse_the_confirmation(self) -> None:
        """Both halves are required. A confirmation turn often still carries the previous
        product, and that must not be read as a new ask."""
        out = _post(
            _emission(
                message_type="request_for_help",
                intent_hint="check_stock",
                entities=[{"raw": "srtwc286", "hint": "product", "current_message": False}],
                is_affirmative=True,
                escalation={"is_escalation_confirmation": True, "company_pick": None},
            ),
            previous=self._OFFERED,
            latest="yes",
        )
        assert out["escalation"]["is_escalation_confirmation"] is True

    def test_a_business_ask_over_an_open_offer_is_not_a_decline_either(self) -> None:
        """The second half of the same turn. With the false YES defused, the model's own
        `is_affirmative: false` sent "PO for SRTWC8517" down the DECLINE arm instead, which
        answers "Escalation declined." and drops the question. Ignoring an offer is neither
        answer."""
        out = _post(
            _emission(
                message_type="business_query",
                intent_hint="check_po",
                domain_hint="purchase_order",
                is_affirmative=False,
                entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
            ),
            previous=self._OFFERED,
        )
        assert out["escalation"].get("escalation_declined") is not True
        assert out["message_type"] == "business_query"

    def test_a_bare_no_still_declines(self) -> None:
        out = _post(
            _emission(
                message_type="clarification",
                intent_hint=None,
                is_affirmative=False,
                entities=[],
            ),
            previous=self._OFFERED,
            latest="no thanks",
        )
        assert out["escalation"].get("escalation_declined") is True
        assert out["message_type"] == "casual"


class TestOwner8SepADeliveryWordPlusANameIsAnOrderAsk:
    """Defect 3, "delivery to hanlim" (owner turns 2d903c96 / 17d38019 / 3a56a48c). The
    parser is inconsistent on the phrase: 3a56a48c parsed it business_query / order /
    check_order, 2d903c96 came back `request_for_help` with BOTH hints null and only the
    customer entity, so the guard above (decisive intent AND a current entity) never fired
    and the lane went `out_of_scope`. The widened guard is structural: a switch word of ONE
    domain among THIS message's content tokens (the sanctioned `DOMAIN_SWITCH_WORDS` table,
    no word list over the text) plus an entity named this turn is a business ask."""

    _OFFERED = {
        "response": "Would you like me to escalate to Sorento customer service team?",
        "pending": {"kind": "member_offer", "team": "customer_service", "domain": "order"},
    }

    def _hanlim(self, **over):
        return _emission(
            message_type="request_for_help",
            intent_hint=None,
            domain_hint=None,
            entities=[{"raw": "hanlim", "hint": "customer", "confident": True, "current_message": True}],
            **over,
        )

    def test_the_2d903c96_shape_is_an_order_ask_not_a_help_request(self) -> None:
        out = _post(self._hanlim(), previous=self._OFFERED, latest="delivery to hanlim")
        assert out["message_type"] == "business_query"
        assert out["domain_hint"] == "order"
        assert out["intent_hint"] == "check_order"
        assert out["escalation"]["is_escalation_confirmation"] is False
        assert out["switch_word_retyped"] == "order"
        assert [e["raw"] for e in out["entities"] if e.get("current_message")] == ["hanlim"]

    def test_the_same_shape_with_no_offer_open_is_retyped_too(self) -> None:
        """The NEW arm is not gated on an open offer: a help request that names a customer
        beside a delivery word is an order ask on a cold turn as well."""
        out = _post(self._hanlim(), previous={}, latest="delivery to hanlim")
        assert out["message_type"] == "business_query"
        assert out["domain_hint"] == "order" and out["intent_hint"] == "check_order"

    def test_the_malay_delivery_word_is_the_same_ask(self) -> None:
        out = _post(self._hanlim(), previous=self._OFFERED, latest="hantar ke hanlim")
        assert out["message_type"] == "business_query" and out["domain_hint"] == "order"

    def test_when_the_model_also_said_yes_the_widened_guard_defuses_it(self) -> None:
        """The EXISTING arm (model said `is_escalation_confirmation: true`) now fires on the
        2d903c96 shape too: no decisive intent, but a switch word plus a current entity."""
        out = _post(
            self._hanlim(escalation={"is_escalation_confirmation": True, "company_pick": None}),
            previous=self._OFFERED,
            latest="delivery to hanlim",
        )
        assert out["escalation"]["is_escalation_confirmation"] is False
        assert out["message_type"] == "business_query"

    # ---- negatives: nothing else moves ---------------------------------------------- #

    def test_escalate_to_a_named_team_over_an_offer_stays_a_help_request(self) -> None:
        """"order" is a switch word, but the customer named a TEAM and no entity: a person
        was asked for, and the turn stays `request_for_help`."""
        out = _post(
            _emission(
                message_type="request_for_help",
                intent_hint=None,
                domain_hint=None,
                entities=[],
                routing={"suggested_team": "customer_service", "suggested_agent": None},
            ),
            previous=self._OFFERED,
            latest="escalate to order team",
        )
        assert out["message_type"] == "request_for_help"
        assert "switch_word_retyped" not in out

    @pytest.mark.parametrize("latest", ["yes", "ok", "no"])
    def test_a_bare_answer_has_no_entity_and_no_switch_word(self, latest: str) -> None:
        affirmative = latest != "no"
        out = _post(
            _emission(
                message_type="request_for_help" if affirmative else "clarification",
                intent_hint=None,
                entities=[],
                is_affirmative=affirmative,
                escalation={"is_escalation_confirmation": affirmative, "company_pick": None},
            ),
            previous=self._OFFERED,
            latest=latest,
        )
        assert out["escalation"]["is_escalation_confirmation"] is affirmative
        assert "switch_word_retyped" not in out

    def test_a_help_request_about_my_order_with_no_entity_is_unchanged(self) -> None:
        """A switch word alone is not an ask - "can someone help me with my order" names
        nobody and nothing, and `request_for_help` is exactly right for it."""
        emission = _emission(message_type="request_for_help", intent_hint=None, domain_hint=None, entities=[])
        out = _post(emission, previous={}, latest="can someone help me with my order")
        assert out["message_type"] == "request_for_help"
        assert out["intent_hint"] is None and out["domain_hint"] is None
        assert out["escalation"]["is_escalation_confirmation"] is False
        assert "switch_word_retyped" not in out

    def test_a_help_request_with_no_entity_is_byte_identical(self) -> None:
        """Byte identity for the turn the arm must never touch: the same emission with the
        helper reporting no switch domain produces the very same output object."""
        import app.services.chatbot.head.output_exchange as oe

        emission = _emission(message_type="request_for_help", intent_hint=None, domain_hint=None, entities=[])
        with_rule = _post(emission, previous=self._OFFERED, latest="can someone help me with my delivery")
        original = oe._switch_word_domain
        oe._switch_word_domain = lambda message: None
        try:
            without_rule = _post(emission, previous=self._OFFERED, latest="can someone help me with my delivery")
        finally:
            oe._switch_word_domain = original
        assert with_rule == without_rule
        assert with_rule["message_type"] == "request_for_help"

    def test_a_carried_entity_alone_is_not_a_current_one(self) -> None:
        """A bare "delivery" is the #6 switch-word consumer's own case (every content token
        a switch word, no current entity), so the message here carries a second token."""
        out = _post(
            _emission(
                message_type="request_for_help",
                intent_hint=None,
                domain_hint=None,
                entities=[{"raw": "hanlim", "hint": "customer", "current_message": False}],
            ),
            previous=self._OFFERED,
            latest="someone handle the delivery",
        )
        assert out["message_type"] == "request_for_help"
        assert "switch_word_retyped" not in out


class TestReviewRound2B2TheRetypeIsTheMeasuredArmOnly:
    """Review round 2, B2: the retype used to fire on `business_ask_now`, whose
    decisive-intent half caught a request for a PERSON that happened to carry a decisive
    intent and a name ("I need someone to look into HANLIM" parsed check_order): it was
    answered with a DO list instead of a human, and clearing `req_help` disarmed
    `team_unresolved` over an open offer. The retype is now gated on the measured 2d903c96
    arm only - a switch word of one domain beside an entity named this turn.

    The reviewer's own sentence, "I need someone to check my order for HANLIM", carries
    the switch word "order" and is therefore the same structural shape as "delivery to
    hanlim"; by the owner's ruling (no widening for a domain-derived team, the prompt owns
    that shape) it is the parser's to classify, not this gate's."""

    _OFFERED = {
        "response": "Would you like me to escalate to Sorento customer service team?",
        "pending": {"kind": "member_offer", "team": "customer_service", "domain": "order"},
    }

    def _person_ask(self, **over):
        return _emission(
            message_type="request_for_help",
            intent_hint="check_order",
            domain_hint="order",
            entities=[{"raw": "HANLIM", "hint": "customer", "confident": True, "current_message": True}],
            **over,
        )

    def test_a_decisive_intent_plus_a_name_with_no_switch_word_stays_a_help_request(self) -> None:
        out = _post(self._person_ask(), previous={}, latest="I need someone to look into HANLIM")
        assert out["message_type"] == "request_for_help"
        assert "switch_word_retyped" not in out

    def test_the_same_shape_over_an_open_offer_still_asks_which_team(self) -> None:
        out = _post(self._person_ask(), previous=self._OFFERED, latest="I need someone to look into HANLIM")
        assert out["message_type"] == "request_for_help"
        assert out["escalation"].get("team_unresolved") is True
        assert out["escalation"]["is_escalation_confirmation"] is False

    def test_the_2d903c96_shape_is_still_retyped(self) -> None:
        out = _post(
            _emission(
                message_type="request_for_help",
                intent_hint=None,
                domain_hint=None,
                entities=[{"raw": "hanlim", "hint": "customer", "confident": True, "current_message": True}],
            ),
            previous=self._OFFERED,
            latest="delivery to hanlim",
        )
        assert out["message_type"] == "business_query"
        assert out["switch_word_retyped"] == "order"

    def test_the_confirm_suppression_backstop_still_reads_the_decisive_intent(self) -> None:
        """`business_ask_now` keeps both halves for the said-yes arm: a decisive ask that
        names a product over an open offer is not a confirmation (owner report 8 Sep)."""
        out = _post(
            _emission(
                message_type="request_for_help",
                intent_hint="check_po",
                domain_hint="purchase_order",
                entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
                escalation={"is_escalation_confirmation": True, "company_pick": None},
            ),
            previous={"response": "Would you like me to escalate to Mocha warehouse team?",
                      "pending": {"kind": "escalation_offer", "team": "warehouse"}},
            latest="PO for SRTWC8517",
        )
        assert out["escalation"]["is_escalation_confirmation"] is False


class TestSwitchWordDomainOfThisMessage:
    """`_switch_word_domain`: the single domain whose switch word appears among the
    message's content tokens (`_TOKEN_RE` minus `SWITCH_FILLER`, the #6 consumer's own
    tokenisation); None on zero or on more than one domain."""

    @pytest.mark.parametrize(
        ("message", "domain"),
        [
            ("delivery to hanlim", "order"),
            ("any DO delivered to hanlim last week", "order"),
            ("penghantaran untuk hanlim", "order"),
            ("PO for SRTWC8517", "purchase_order"),
            ("PO?", "purchase_order"),
            ("spo SRTWC8517", "spo_allocation"),
            ("check stock srtwc286", "inventory"),
            ("stock and delivery for hanlim", None),  # two domains
            ("yes", None),
            ("can someone help me", None),
            ("do you have srtwc286", None),  # "do" is deliberately NOT a switch word
        ],
    )
    def test_domain_of(self, message: str, domain: str | None) -> None:
        from app.services.chatbot.head.output_exchange import _switch_word_domain

        assert _switch_word_domain(message) == domain
