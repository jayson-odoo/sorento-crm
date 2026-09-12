"""Unit cover for every rule S1b took out of the parser prompt (AC-152).

D16's split is "the LLM does language, code does everything else". Each rule below used to
be stated TWICE - once as an instruction in the 46 KB system message and once as Python in
``output_exchange.py`` - and the second copy is the one that decides, because the
post-processor runs after the model and overwrites it. S1b deletes the instruction, so
these tests are what now holds the behaviour.

**Every case feeds a deliberately NON-COMPLIANT emission.** A test that feeds a compliant
one proves nothing about a prompt that no longer asks for compliance.

All six rules already shipped in the port; S1b adds no new post-processor code, it only
stops the prompt saying the same thing worse. The inventory names the fixture ids that
justify each row: ``documentation/plans/chatbot/parser-prompt-inventory.md``.

Written against the LIVE n8n body (see the plan's S1 "pending re-port"): the routing chain
is `(request_for_help ? the model's team : null) ?? derived ?? prior ?? "customer_service"`,
there is no `team_source` and no `resource_attachment` routing row.

Pure functions over dicts - no database, no network, no LLM.
"""
from __future__ import annotations

import json

import pytest

from app.services.chatbot.head.output_exchange import derive_routing, output_exchange

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def parser_output(**overrides) -> dict:
    """A well-formed 26-key emission. Overrides are the thing under test."""
    base = {
        "message_type": "business_query",
        "intent_hint": None,
        "domain_hint": None,
        "scope_intent": None,
        "is_affirmative": None,
        "user_goal": "trying to check something",
        "access_levels": [],
        "broaden_axis": None,
        "date_mode": None,
        "date_filter_start": None,
        "date_filter_end": None,
        "match_mode": "and",
        "demand_qty": None,
        "entities": [],
        "entity_op": "replace_combine",
        "scope_exclusive": False,
        "requested_attributes": [],
        "contains_flyer": False,
        "reference_positions": [],
        "reference_target": None,
        "person_mention": None,
        "is_active": None,
        "order_status": None,
        "correction": False,
        "routing": {"suggested_team": None, "suggested_agent": None},
        "escalation": {"is_escalation_confirmation": False, "company_pick": None},
    }
    base.update(overrides)
    return base


def run(output: dict, *, message: str = "", state: dict | None = None) -> dict:
    """One turn through the post-processor, the way `engine.run_turn` calls it."""
    return output_exchange(
        {"output": json.dumps(output)},
        {
            "latest_user_message": message,
            "contact_id": "ZZT-s1b-rules",
            "previous_conversation_state": state or {},
        },
    )["output"]


# --------------------------------------------------------------------------- #
# R1 - the domain to team / agent map (prompt section "Routing signals")
# --------------------------------------------------------------------------- #

# The exact map the deleted prompt rows named, plus the cert split inside
# `product_attachment` that the prompt states and the code decides.
DOMAIN_ROUTING = [
    ("master_products", "purchasing", "general_enquiries"),
    ("incoming", "purchasing", "incoming_stock_enquiries"),
    ("product_attachment", "marketing_product", "general_enquiries"),
    ("forms", "marketing_form", "marketing_form"),
    ("inventory", "warehouse", "general_enquiries"),
    ("order", "customer_service", "order_enquiries"),
    ("promotion", "marketing_promotion", "general_enquiries"),
]


@pytest.mark.parametrize(("domain", "team", "agent"), DOMAIN_ROUTING)
def test_r1_domain_to_team_map_is_code_not_prompt(domain: str, team: str, agent: str) -> None:
    """The parser emits NO team at all; the post-processor derives the whole map."""
    out = run(parser_output(domain_hint=domain, intent_hint="check_stock"))
    assert out["routing"] == {"suggested_team": team, "suggested_agent": agent}


def test_r1_ideate_routes_to_no_team_but_its_own_access_agent() -> None:
    """The one row that is a pair rather than a lookup, and the single source of truth for
    the ideate agent: the access check keys on `suggested_agent`."""
    out = run(parser_output(domain_hint="ideate", intent_hint="submit_idea"))
    assert out["routing"]["suggested_agent"] == "ideation"


def test_r1_certificate_splits_product_attachment_to_the_certification_team() -> None:
    out = run(
        parser_output(
            domain_hint="product_attachment",
            intent_hint="check_product_attachment",
            entities=[
                {
                    "raw": "SPAN cert",
                    "hint": "attachment_type",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                }
            ],
        )
    )
    assert out["routing"]["suggested_team"] == "purchasing_certification"


def test_r1_a_topic_guess_loses_to_the_derived_team_on_a_business_query() -> None:
    """This is why the domain map could be deleted rather than merely duplicated.

    The live routing chain reads the model's own team ONLY on a `request_for_help` turn.
    On every other turn `derive_routing` supplies the answer, so a topic-based guess in
    the prompt could not reach the output even when the model made one.
    """
    out = run(
        parser_output(
            domain_hint="inventory",
            intent_hint="check_stock",
            routing={
                "suggested_team": "purchasing_certification",
                "suggested_agent": "general_enquiries",
            },
        )
    )
    assert out["routing"]["suggested_team"] == "warehouse"


def test_r1_a_named_team_still_wins_which_is_why_that_rule_stayed() -> None:
    """The one routing judgement the prompt keeps: the customer NAMED a team.

    On a `request_for_help` turn the model's team is rank 1, and it is the only way a team
    can be chosen when the turn carries no domain for `derive_routing` to work from.
    """
    out = run(
        parser_output(
            message_type="request_for_help",
            routing={
                "suggested_team": "marketing_product",
                "suggested_agent": "general_enquiries",
            },
        ),
        message="please escalate to marketing product team",
    )
    assert out["routing"]["suggested_team"] == "marketing_product"


def test_r1_derive_routing_covers_every_domain_the_contract_declares() -> None:
    """No declared domain may quietly fall out of the map (H28).

    The prompt no longer carries a second copy, so a newly unmapped domain would route by
    prior state or the hard default with nothing to catch it.
    """
    from app.services.chatbot.contracts import DOMAIN_HINTS

    unmapped = [
        d
        for d in DOMAIN_HINTS
        if derive_routing({"domain_hint": d, "entities": [], "access_levels": []})
        == {"suggested_team": None, "suggested_agent": None}
    ]
    assert unmapped == [
        "portal_link",
        "resource_attachment",
        "goods_receive",
        "spo_allocation",
    ], (
        "derive_routing's coverage changed. `resource_attachment` is unmapped ON PURPOSE: "
        "the row that pairs it with marketing_product is part of the unpromoted B-TEAM-1' "
        "change (plan, S1 'pending re-port'), and the live body routes it by the prior-state "
        "carry instead."
    )


# --------------------------------------------------------------------------- #
# R6 - legacy suffixed promotion team collapses to the single base team
# --------------------------------------------------------------------------- #


def test_r6_a_brand_suffixed_promotion_team_collapses_to_the_base_team() -> None:
    out = run(
        parser_output(
            message_type="request_for_help",
            domain_hint="promotion",
            intent_hint="check_promotion",
            routing={
                "suggested_team": "marketing_promotion_cabana",
                "suggested_agent": "general_enquiries",
            },
        )
    )
    assert out["routing"]["suggested_team"] == "marketing_promotion"


# --------------------------------------------------------------------------- #
# R2 - message_type forced to business_query when a domain is set
# --------------------------------------------------------------------------- #


def test_r2_a_domain_bearing_turn_is_business_query_whatever_the_model_called_it() -> None:
    out = run(
        parser_output(message_type="clarification", domain_hint="inventory", intent_hint="check_stock")
    )
    assert out["message_type"] == "business_query"


@pytest.mark.parametrize("kept", ["casual", "request_for_help"])
def test_r2_casual_and_request_for_help_survive_the_force(kept: str) -> None:
    """The two exceptions the deleted prompt rule never stated but the code has always had."""
    out = run(parser_output(message_type=kept, domain_hint="inventory", intent_hint="check_stock"))
    assert out["message_type"] == kept


# --------------------------------------------------------------------------- #
# R3 - attachment_type is dropped when the domain is master_products
# --------------------------------------------------------------------------- #


def test_r3_attachment_type_is_dropped_when_the_domain_switches_to_master_products() -> None:
    """The model may keep the carried attachment_type; the blocklist removes it."""
    out = run(
        parser_output(
            domain_hint="master_products",
            intent_hint="check_product",
            entities=[
                {
                    "raw": "SRTWT5611",
                    "hint": "product",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                },
                {
                    "raw": "technical drawing",
                    "hint": "attachment_type",
                    "canonical_code": "technical drawing",
                    "current_message": False,
                    "confident": True,
                },
            ],
        ),
        message="list price for SRTWT5611",
    )
    hints = [e.get("hint") for e in out["entities"]]
    assert "attachment_type" not in hints
    assert "product" in hints


# --------------------------------------------------------------------------- #
# R4 - broaden_axis restores the prior domain and intent
# --------------------------------------------------------------------------- #


def test_r4_widening_one_axis_keeps_the_question_it_was_asked_about() -> None:
    """"all products" mid-order came back as the catalogue; code puts the domain back."""
    out = run(
        parser_output(
            domain_hint="master_products",
            intent_hint="check_product",
            broaden_axis="product",
            entity_op="reuse",
        ),
        message="all products",
        state={"domain_hint": "order", "intent_hint": "check_order", "entities": []},
    )
    assert out["domain_hint"] == "order"
    assert out["intent_hint"] == "check_order"
    assert out["broaden_axis_domain_restored"] is True


def test_r4_with_no_prior_domain_a_catalogue_ask_stays_a_catalogue_ask() -> None:
    out = run(
        parser_output(domain_hint="master_products", intent_hint="check_product", broaden_axis="product"),
        message="all products",
    )
    assert out["domain_hint"] == "master_products"
    assert out.get("broaden_axis_domain_restored") is None


# --------------------------------------------------------------------------- #
# R7 - a broaden beside a new activity domain is a switch (PLAN-broaden-domain-switch)
# --------------------------------------------------------------------------- #

# exec 15121180: "ANY INCOMING" after a stock turn on SRTWT04A. Parser v7 emitted
# domain_hint incoming / intent_hint check_incoming / broaden_axis all / scope_intent
# broaden / entity_op clear / entities [] - a COHERENT (incoming, check_incoming) pair,
# not the "all products" mid-order wander the restore block exists for. The prompt
# defines a widen as "KEEP domain_hint", so a coherent pair for a DIFFERENT, non-catalogue
# domain is self-contradictory: the model switched, and the restore must not undo it.


def test_ac1_broaden_beside_a_coherent_new_domain_switches_and_reuses_the_prior_product() -> None:
    out = run(
        parser_output(
            domain_hint="incoming",
            intent_hint="check_incoming",
            broaden_axis="all",
            scope_intent="broaden",
            entity_op="clear",
            entities=[],
        ),
        message="Any incoming",
        state={
            "domain_hint": "inventory",
            "intent_hint": "check_stock",
            "entities": [
                {
                    "raw": "srtwc286",
                    "hint": "product",
                    "canonical_code": "SRTWC286",
                    "current_message": True,
                    "confident": True,
                }
            ],
        },
    )
    assert out["domain_hint"] == "incoming"
    assert out["intent_hint"] == "check_incoming"
    assert out["entity_op_applied"] == "reuse"
    assert [e.get("raw") for e in out["entities"]] == ["srtwc286"]
    assert out["broaden_axis"] is None
    assert out["scope_intent"] is None
    assert out["domain_switch_over_broaden"] == "inventory"
    assert out.get("broaden_axis_domain_restored") is None


def test_ac2_a_prior_hint_blocked_under_the_new_domain_is_not_reused() -> None:
    """A carried customer entity has no place under `incoming` - stays cleared."""
    out = run(
        parser_output(
            domain_hint="incoming",
            intent_hint="check_incoming",
            broaden_axis="all",
            scope_intent="broaden",
            entity_op="clear",
            entities=[],
        ),
        message="Any incoming",
        state={
            "domain_hint": "order",
            "intent_hint": "check_order",
            "entities": [
                {
                    "raw": "hanlim",
                    "hint": "customer",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                }
            ],
        },
    )
    assert out["domain_hint"] == "incoming"
    assert out["domain_switch_over_broaden"] == "order"
    assert out["entity_op"] == "clear"
    assert out["entities"] == []


def test_ac3_a_current_message_entity_on_the_switch_leaves_entity_op_as_emitted() -> None:
    """The model named its OWN entity this turn - the reuse rescue does not apply."""
    out = run(
        parser_output(
            domain_hint="incoming",
            intent_hint="check_incoming",
            broaden_axis="all",
            scope_intent="broaden",
            entity_op="replace_combine",
            entities=[
                {
                    "raw": "SRTWT04A",
                    "hint": "product",
                    "canonical_code": "SRTWT04A",
                    "current_message": True,
                    "confident": True,
                }
            ],
        ),
        message="Any incoming for SRTWT04A",
        state={
            "domain_hint": "inventory",
            "intent_hint": "check_stock",
            "entities": [
                {
                    "raw": "srtwc286",
                    "hint": "product",
                    "canonical_code": "SRTWC286",
                    "current_message": True,
                    "confident": True,
                }
            ],
        },
    )
    assert out["domain_hint"] == "incoming"
    assert out["domain_switch_over_broaden"] == "inventory"
    assert out["entity_op"] == "replace_combine"
    assert out["entity_op_applied"] == "replace_combine"
    assert "SRTWT04A" in [e.get("raw") for e in out["entities"]]


def test_ac5_model_domain_null_still_restores_the_prior_domain() -> None:
    """Date widen (e4381b0d / 98526b81 shape): a null model domain is never a switch."""
    out = run(
        parser_output(
            domain_hint=None,
            intent_hint=None,
            broaden_axis="date",
            scope_intent="broaden",
            entity_op="clear",
        ),
        message="last month",
        state={"domain_hint": "order", "intent_hint": "check_order", "entities": []},
    )
    assert out["domain_hint"] == "order"
    assert out["intent_hint"] == "check_order"
    assert out["broaden_axis_domain_restored"] is True
    assert out.get("domain_switch_over_broaden") is None


def test_ac6_model_domain_equal_to_prior_domain_is_not_a_switch() -> None:
    """Genuine "show me everything": same domain both sides, restore path as today."""
    out = run(
        parser_output(
            domain_hint="inventory",
            intent_hint="check_stock",
            broaden_axis="all",
            scope_intent="broaden",
            entity_op="clear",
            entities=[],
        ),
        message="show me everything",
        state={
            "domain_hint": "inventory",
            "intent_hint": "check_stock",
            "entities": [
                {
                    "raw": "srtwc286",
                    "hint": "product",
                    "canonical_code": "SRTWC286",
                    "current_message": True,
                    "confident": True,
                }
            ],
        },
    )
    assert out["domain_hint"] == "inventory"
    assert out["broaden_axis_domain_restored"] is True
    assert out.get("domain_switch_over_broaden") is None
    assert out["entity_op"] == "clear"
    assert out["entities"] == []


def test_ac7_an_incoherent_domain_intent_pair_is_not_a_switch() -> None:
    """domain_hint incoming with intent_hint check_stock names no real incoming pair."""
    out = run(
        parser_output(
            domain_hint="incoming",
            intent_hint="check_stock",
            broaden_axis="all",
            scope_intent="broaden",
            entity_op="clear",
            entities=[],
        ),
        message="Any incoming",
        state={"domain_hint": "order", "intent_hint": "check_order", "entities": []},
    )
    assert out["domain_hint"] == "order"
    assert out["intent_hint"] == "check_order"
    assert out["broaden_axis_domain_restored"] is True
    assert out.get("domain_switch_over_broaden") is None


# Review, blocker B2 (9 Sep 2026): `switched` narrowed to `ba == "all"` only. The prompt's
# widen instruction says KEEP domain_hint for BOTH a `date` widen and an entity-hint widen,
# so a differing domain beside either is a known MODEL violation of its own instruction -
# the restore corrects it, exactly as it always has, and must NOT be read as a switch. Only
# `"all"` has no KEEP clause in the prompt and only `"all"` has a real capture.


def test_ac11_a_date_widen_naming_a_different_domain_still_restores() -> None:
    """Regression (1): a `date` axis must not switch - the differing domain_hint is the
    model's own violation of the prompt's "date widen KEEPS domain_hint" instruction, and
    the restore corrects it exactly as it does for every other axis but "all"."""
    out = run(
        parser_output(
            domain_hint="incoming",
            intent_hint="check_incoming",
            broaden_axis="date",
            scope_intent="broaden",
            entity_op="reuse",
            entities=[],
        ),
        message="not just August",
        state={"domain_hint": "order", "intent_hint": "check_order", "entities": []},
    )
    assert out["domain_hint"] == "order"
    assert out["broaden_axis_domain_restored"] is True
    assert out.get("domain_switch_over_broaden") is None


def test_ac12_a_date_widen_beside_a_different_domain_still_wipes_the_window() -> None:
    """Regression (2): had `switched` fired on `ba == "date"`, it would have nulled
    `broaden_axis` before the reuse executor's own `all_time` check ever saw it, so the
    OLD window would have been silently restored instead of wiped. Narrowed to "all" only,
    `broaden_axis` reaches the executor untouched and the wipe fires as it always has."""
    out = run(
        parser_output(
            domain_hint="order",
            intent_hint="check_order",
            broaden_axis="date",
            scope_intent="broaden",
            entity_op="reuse",
            entities=[],
            date_filter_start=None,
            date_filter_end=None,
        ),
        message="not just August",
        state={
            "domain_hint": "promotion",
            "intent_hint": "check_promotion",
            "entities": [],
            "date_filter_start": "2026-08-01",
            "date_filter_end": "2026-08-31",
        },
    )
    assert out["date_filter_start"] is None
    assert out["date_filter_end"] is None


def test_ac13_an_entity_hint_widen_beside_a_different_domain_drops_the_named_axis() -> None:
    """Regression (3): had `switched` fired on `ba == "customer"`, it would have nulled
    `broaden_axis` before the final `ba_final` drop pass ever saw it, so the customer the
    turn asked to widen away would have survived to the tool call. Narrowed to "all" only,
    the axis survives to the final pass and the named entity is dropped."""
    out = run(
        parser_output(
            domain_hint="order",
            intent_hint="check_order",
            broaden_axis="customer",
            scope_intent="broaden",
            entity_op="reuse",
            entities=[],
        ),
        message="for everyone",
        state={
            "domain_hint": "inventory",
            "intent_hint": "check_stock",
            "entities": [
                {
                    "raw": "hanlim",
                    "hint": "customer",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                },
                {
                    "raw": "srtwc286",
                    "hint": "product",
                    "canonical_code": "SRTWC286",
                    "current_message": True,
                    "confident": True,
                },
            ],
        },
    )
    assert [e.get("raw") for e in out["entities"]] == ["srtwc286"]
    assert [e.get("hint") for e in out["entities"]] == ["product"]


# --------------------------------------------------------------------------- #
# R5 - a compound access level splits into a tier token plus query_brands
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("levels", "tiers", "brands"),
    [
        (["Cabana Dealer"], ["dealer"], ["cabana"]),
        (["Sorento Office"], ["office"], ["sorento"]),
        (["End User"], ["end_user"], []),
        (["Mocha Dealer", "Mocha Office"], ["dealer", "office"], ["mocha"]),
        # A bare tier token, which is what the deleted "dealer with no brand" fan-out row
        # would otherwise have had the model expand into three compound strings.
        (["dealer"], ["dealer"], []),
    ],
)
def test_r5_compound_levels_split_into_tier_tokens_and_brands(
    levels: list[str], tiers: list[str], brands: list[str]
) -> None:
    out = run(
        parser_output(domain_hint="promotion", intent_hint="check_promotion", access_levels=levels),
        message="promo please",
    )
    assert out["access_levels"] == tiers
    assert out["query_brands"] == brands


def test_r5_the_compound_is_the_wire_shape_the_brand_is_read_from() -> None:
    """Why the 7-value vocabulary could NOT be replaced by a bare tier in the prompt.

    `query_brands` is harvested from the compound level; a bare tier carries no brand, and
    by the next line the compound no longer exists.
    """
    compound = run(
        parser_output(domain_hint="promotion", intent_hint="check_promotion", access_levels=["Cabana Dealer"]),
        message="promo please",
    )
    bare = run(
        parser_output(domain_hint="promotion", intent_hint="check_promotion", access_levels=["dealer"]),
        message="promo please",
    )
    assert compound["access_levels"] == bare["access_levels"] == ["dealer"]
    assert compound["query_brands"] == ["cabana"]
    assert bare["query_brands"] == []


# --------------------------------------------------------------------------- #
# Owner console defect K, rule 3 (turns d9f860d4 / dcaa8e37): a PENDING member/escalation
# offer's own entry-gate (post_process, `sel_ctx == "member_offer"` block) treats a reply
# that carries a genuine FILTER (a date window or a new entity) as "junk / no signal" -
# Tier 4 of the ladder - and re-prompts the roster (`escalation.member_reprompt =
# "out_of_range"`, `correction = True`), when the reply is actually a filter modification
# on the CARRIED domain (e.g. "delivery to hanlim, product srtwc286" -> escalate offered ->
# "last month" (a date window) or "rpacc" (a product code) should keep the offer pending,
# not reprompt it as gibberish.
# --------------------------------------------------------------------------- #


def _pending_member_offer_state(**overrides) -> dict:
    base = {
        "selection_context": "member_offer",
        "last_result_set": [
            {"idx": i, "label": f"Member {i}", "uuid": f"u{i}"} for i in range(1, 7)
        ],
        "routing": {"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
    }
    base.update(overrides)
    return base


def test_a_date_filter_reply_on_a_pending_member_offer_is_a_filter_not_junk() -> None:
    """"last month" against a 6-member roster: a date window, no pick signal at all -
    must NOT be read as an out-of-range pick and reprompted."""
    out = run(
        parser_output(
            message_type="casual",
            domain_hint=None,
            date_filter_start="2026-08-01",
            date_filter_end="2026-08-31",
            entities=[],
        ),
        message="last month",
        state=_pending_member_offer_state(),
    )
    escalation = out.get("escalation") or {}
    assert escalation.get("member_reprompt") != "out_of_range", (
        "a genuine date-filter reply must not be read as an out-of-range member pick and "
        f"reprompted: {out!r}"
    )
    assert out.get("correction") is not True, (
        f"a filter modification is not a correction of a bad pick: {out!r}"
    )


def test_a_filter_reply_keeps_the_window_and_the_carried_domain_at_the_seam() -> None:
    """The other half of the same rule, asserted where it is decided rather than by the
    absence of a reprompt: the turn takes the FILTER MODIFICATION arm, the carried domain
    is inherited (without it the date gate below drops the window it just kept), and the
    date window is still there for the answer to use."""
    out = run(
        parser_output(
            message_type="casual",
            domain_hint=None,
            date_filter_start="2026-08-01",
            date_filter_end="2026-08-31",
            entities=[],
        ),
        message="last month",
        state=_pending_member_offer_state(domain_hint="order", intent_hint="check_order"),
    )
    assert out.get("member_offer_filter_modification") is True, (
        f"the reply must be read as a narrowing of the carried question: {out!r}"
    )
    assert out["domain_hint"] == "order"
    assert out["date_filter_start"] == "2026-08-01"
    assert out["date_filter_end"] == "2026-08-31"


def test_a_date_bearing_reply_takes_the_filter_arm_under_either_message_type() -> None:
    """Owner rule (help-crm, console pass 5, item B, restated at the top of
    `test_pass5_item2_member_offer_business_query_filter_route.py`): under an open
    `member_offer`, a turn that carries a date filter is a filter modification
    REGARDLESS of `message_type` - `casual` vs `business_query` is LLM variance the
    route must not use to decide the branch. `has_filter_signal`'s own `fm_dates` read
    already does not test `message_type` at all (gate.py:2656's neighbour in this file);
    this pins that fact directly, driving the SAME date-bearing parser output through
    the arm under both message types rather than trusting it by inspection."""
    for message_type in ("casual", "business_query"):
        out = run(
            parser_output(
                message_type=message_type,
                domain_hint=None,
                intent_hint=None,
                date_filter_start="2026-08-01",
                date_filter_end="2026-08-31",
                entities=[],
            ),
            message="last month",
            state=_pending_member_offer_state(domain_hint="order", intent_hint="check_order"),
        )
        assert out.get("member_offer_filter_modification") is True, (
            f"message_type={message_type!r} must still take the filter arm: {out!r}"
        )
        assert out["date_filter_start"] == "2026-08-01", (message_type, out)
        assert out["date_filter_end"] == "2026-08-31", (message_type, out)


def test_a_product_code_reply_on_a_pending_offer_is_a_filter_not_an_abandon() -> None:
    """"rpacc" mid-offer, the case the red pass measured as passing for the WRONG reason.

    `is_new_query` is True on this shape (message_type business_query), so the ladder used
    to take "Tier 3 - NEW QUERY: abandon the offer" and the absence of `member_reprompt`
    proved nothing. The assertion is therefore on the SEAM: the turn takes the filter arm,
    the entity the customer typed survives, and the carried domain is kept - the offer is
    still pending, which the tail's `_offer_carry` then acts on."""
    out = run(
        parser_output(
            message_type="business_query",
            domain_hint=None,
            intent_hint=None,
            entities=[{"raw": "rpacc", "hint": "customer", "current_message": True}],
        ),
        message="rpacc",
        state=_pending_member_offer_state(domain_hint="order", intent_hint="check_order"),
    )
    assert out.get("member_offer_filter_modification") is True, (
        f"an entity-bearing reply narrows the carried question, it does not abandon the "
        f"offer: {out!r}"
    )
    assert out["domain_hint"] == "order"
    assert [e.get("raw") for e in out.get("entities") or []] == ["rpacc"], (
        f"the entity the customer typed must survive: {out.get('entities')!r}"
    )
    escalation = out.get("escalation") or {}
    assert escalation.get("member_reprompt") is None
    assert out.get("correction") is not True


# The BOUND on rule 3, and it needs its own cover: the three corpus captures that reach the
# filter arm are all turns where it and n8n's Tier 3 both touch nothing, so they cannot
# tell the narrow arm from the wide one and widening it back would be silent. Each case
# below fails one of the two conditions `MEMBER_OFFER_FILTER_HINTS` guards, and each dies
# if the arm goes back to "any current-message entity".


def test_a_same_domain_new_question_under_a_pending_offer_is_not_a_filter() -> None:
    """A NEW SUBJECT, not a narrowing. `customer_order` is the order domain's own subject,
    not a filter axis on it, so naming one mid-offer asks a different question and the
    offer is abandoned - the arm must not keep it pending. Nothing is reprompted either:
    a new query is not junk."""
    out = run(
        parser_output(
            message_type="business_query",
            domain_hint=None,
            intent_hint=None,
            entities=[
                {"raw": "M2609-0086", "hint": "customer_order", "current_message": True}
            ],
        ),
        message="delivery status for M2609-0086",
        state=_pending_member_offer_state(domain_hint="order", intent_hint="check_order"),
    )
    assert out.get("member_offer_filter_modification") is None, (
        f"an entity that is the domain's SUBJECT starts a new question; keeping the offer "
        f"pending behind it is what arms a stale roster: {out!r}"
    )
    escalation = out.get("escalation") or {}
    assert escalation.get("member_reprompt") is None
    assert out.get("correction") is not True


def test_a_new_intent_under_a_pending_offer_is_not_a_filter_even_on_a_filter_axis() -> None:
    """"stock for rpacc" while an ORDER roster is open. `product` IS a filter axis of the
    carried order domain, so the axis half of the guard passes and only the INTENT half
    stops it: the customer named `check_stock` where the offer was made about
    `check_order`, which is a different question however familiar the entity."""
    out = run(
        parser_output(
            message_type="business_query",
            domain_hint=None,
            intent_hint="check_stock",
            entities=[{"raw": "rpacc", "hint": "product", "current_message": True}],
        ),
        message="stock for rpacc",
        state=_pending_member_offer_state(domain_hint="order", intent_hint="check_order"),
    )
    assert out.get("member_offer_filter_modification") is None, (
        f"a new intent is a new question, whatever the entity type: {out!r}"
    )
    escalation = out.get("escalation") or {}
    assert escalation.get("member_reprompt") is None
    assert out.get("correction") is not True


# NOTE (seam not reached): a second case for "rpacc" (a product-code entity,
# `message_type: business_query`) was measured and DROPPED from this file - `is_new_query`
# is already True on that shape (message_type == "business_query"), so `post_process`'s
# entry-gate already takes "Tier 3 - NEW QUERY: abandon the offer. Touch nothing" and never
# reaches the Tier-4 reprompt this test targets; `escalation.member_reprompt` is absent
# either way, so an assertion at THIS level passes today for the wrong reason. The owner's
# actual complaint for that shape - "the patch dropped the roster (pending null,
# last_result_set [])" - happens one layer down, in `tail/compile_state.py`'s own
# no-fresh-offer reset (the SAME mechanism K rule 1 targets for tier_offer, but
# `_picker_carry`'s docstring explicitly excludes `member_offer` from any carry as a
# documented safety property - re-arming it can invisibly assign a human to somebody who
# already declined). Reconciling "keep the pending escalation across a filter-only reply"
# with "never silently re-arm a declined/answered member offer" needs a narrower rule than
# either K1's blanket carry or today's blanket exclusion, and pinning that exact rule in a
# red test was not reached in this pass - flagged here rather than shipping a test that
# would pass for the wrong reason.


# --------------------------------------------------------------------------- #
# Owner console defect K, rule 4 (turn a8472efe). A BARE entity turn (one entity, no
# intent, no domain) with a carried BUSINESS domain must INHERIT that domain and TYPE the
# entity BY THE DOMAIN (product for inventory/incoming/promotion, customer for order) -
# inheritance is blocked only when the entity RESOLVES to an incompatible type, never on
# the LLM's own (frequently wrong) hint.
#
# Today's code (`output_exchange.py`'s "domain continuity for entity-bearing
# continuations" block, ~line 1538-1564) does the OPPOSITE: it trusts the LLM's hint,
# checks it against `DOMAIN_BLOCKED_HINTS[prev_domain]`, and on a mismatch (a genuine
# product code the LLM mis-hinted "customer" under a carried "inventory" domain) sets
# `domain_inherit_blocked` and drops the inheritance - exactly turn a8472efe's shape:
# domain inventory + srtwc286 carried, "rpacc" hinted customer -> inheritance blocked,
# both codes surfaced as an ambiguous "ali or B" clarify instead of typing rpacc as the
# product it is and letting the RESOLVER decide.
# --------------------------------------------------------------------------- #


def test_a_bare_entity_inherits_the_carried_domain_and_is_retyped_by_it() -> None:
    """(a) prior domain inventory, a bare entity the LLM mis-hinted "customer" - the
    domain must still be inherited and the entity retyped "product", with no
    `domain_inherit_blocked` stamped."""
    out = run(
        parser_output(
            message_type="business_query",
            domain_hint=None,
            intent_hint=None,
            entities=[{"raw": "rpacc", "hint": "customer", "current_message": True}],
        ),
        message="rpacc",
        state={"domain_hint": "inventory", "intent_hint": "check_stock", "entities": []},
    )
    assert out["domain_hint"] == "inventory", (
        f"the carried business domain must be inherited on a bare code turn: {out!r}"
    )
    assert out.get("domain_inherit_blocked") is None, (
        f"a mis-hint must never be read as a topic switch: {out!r}"
    )
    entity_hints = {e.get("hint") for e in out.get("entities") or [] if e.get("raw") == "rpacc"}
    assert entity_hints == {"product"}, (
        f"the bare code must be RETYPED to match the inherited domain, not left as the "
        f"LLM's own (wrong) hint: {out.get('entities')!r}"
    )


def test_a_bare_entity_under_a_carried_order_domain_is_typed_as_customer() -> None:
    """(b) prior domain order, a bare entity mis-hinted "product" - typed customer."""
    out = run(
        parser_output(
            message_type="business_query",
            domain_hint=None,
            intent_hint=None,
            entities=[{"raw": "hanlim", "hint": "product", "current_message": True}],
        ),
        message="hanlim",
        state={"domain_hint": "order", "intent_hint": "check_order", "entities": []},
    )
    assert out["domain_hint"] == "order"
    assert out.get("domain_inherit_blocked") is None
    entity_hints = {e.get("hint") for e in out.get("entities") or [] if e.get("raw") == "hanlim"}
    assert entity_hints == {"customer"}, (
        f"the bare entity must be retyped customer under the carried order domain: "
        f"{out.get('entities')!r}"
    )



# TestOwnerRulingBAllOfThemOverPendingDymOffer and TestOwnerRulingD1PendingOfferTeamMismatch
# retired here (AC-1033, owner 12 Sep 2026: no persisted mirrors). Both pinned
# output_exchange.run() reading the legacy pending / dym_offer / dym_last_result_set
# markers directly out of state - pick-all over a did-you-mean offer, and a pending
# escalation offer versus a request that names a different team. Those markers no
# longer exist in SessionVars; the equivalent behaviour is the six
# dialogue/open_question.py handlers (product_pick pick-all and team_pick's
# yes/no-versus-a-fresh-ask arms), tested in tests/chatbot/test_open_question.py and
# tests/chatbot/test_open_question_clearing.py.
