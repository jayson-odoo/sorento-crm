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
