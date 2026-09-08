"""D9 / AC-930 / AC-931: `DOMAIN_SPEC` is the one declaration, and nothing drifted.

Adding ONE domain (`purchase_order`) meant editing six independent literals, each of them
a per-domain fact written down twice or more. `contracts.DOMAIN_SPEC` collapses five of
them into one row per domain; this file is the gate that keeps it honest, in two halves:

* **Nothing moved.** Each derived view is compared against a SNAPSHOT of the literal it
  replaced, taken before the deletion (extended by the `purchase_order` entries the same
  change added). A refactor that quietly re-spells a switch word or drops a tool fails
  here, on the exact key, rather than as a live turn that stops routing.
* **Nothing can drift again.** Every `DOMAIN_HINTS` member has a row; every name in
  `CHATBOT_READ_ONLY_TOOLS` is accounted for exactly once; the table agrees with the
  replay-graded `derive_routing` ladder; and the two CORE-side copies of
  `DEFAULT_UNSUPPORTED_DOMAINS` (which cannot import the package, AC-002) agree with it.

The tables that are NOT folded in are asserted to still be independent, on purpose: the
hazard tables in `head/output_exchange.py` each carry a hand-earned annotation naming the
live turn that put a row there, and a uniform table would lose the reason with the shape.
"""
from __future__ import annotations

import pytest

from app.services.chatbot import contracts
from app.services.chatbot.head import output_exchange as oe
from app.services.chatbot.head.route import DEFAULT_UNSUPPORTED_DOMAINS
from app.services.chatbot.lanes.business.fetch import CHATBOT_READ_ONLY_TOOLS

# --------------------------------------------------------------------------- #
# The snapshots. Taken from the literals as they stood on 7 Sep 2026, immediately
# before the deletion, and extended ONLY by the `purchase_order` entries the same
# change added. Hand-copied on purpose: a snapshot derived from the thing it
# guards guards nothing.
# --------------------------------------------------------------------------- #

BARE_ENTITY_TYPE_BY_DOMAIN_BEFORE = {
    "inventory": "product",
    "incoming": "product",
    "promotion": "product",
    "order": "customer",
}

DOMAIN_SWITCH_WORDS_BEFORE = {
    "promo": "promotion",
    "promos": "promotion",
    "promotion": "promotion",
    "promotions": "promotion",
    "promosi": "promotion",
    "stock": "inventory",
    "stocks": "inventory",
    "inventory": "inventory",
    "stok": "inventory",
    "qty": "inventory",
    "quantity": "inventory",
    "order": "order",
    "orders": "order",
    "outstanding": "order",
    "tempahan": "order",
    # 8 Sep 2026 (owner turn 2d903c96 "delivery to hanlim"): the delivery vocabulary.
    "delivery": "order",
    "deliveries": "order",
    "deliver": "order",
    "delivered": "order",
    "penghantaran": "order",
    "hantar": "order",
    "dihantar": "order",
    "incoming": "incoming",
    "eta": "incoming",
    "shipment": "incoming",
    "shipments": "incoming",
    "arriving": "incoming",
    "container": "incoming",
    "containers": "incoming",
    "catalogue": "master_products",
    "catalog": "master_products",
    "spec": "master_products",
    "specs": "master_products",
    "specification": "master_products",
    "specifications": "master_products",
    "dimension": "master_products",
    "dimensions": "master_products",
    # 8 Sep 2026: the measured triggers the two rows' own comments name (turns 18d9b95c,
    # bd6eacf4 / 796957f4).
    "po": "purchase_order",
    "spo": "spo_allocation",
}

DEFAULT_UNSUPPORTED_DOMAINS_BEFORE = ("goods_receive",)

DOMAIN_HINTS_BEFORE = (
    "master_products",
    "product_attachment",
    "promotion",
    "forms",
    "inventory",
    "order",
    "incoming",
    "portal_link",
    "resource_attachment",
    "goods_receive",
    "spo_allocation",
    "ideate",
    "purchase_order",
)

INTENT_HINTS_BEFORE = (
    "check_stock",
    "check_product",
    "check_incoming",
    "check_promotion",
    "check_order",
    "get_forms",
    "check_product_attachment",
    "get_resource_attachment",
    "get_portal_link",
    "check_goods_receive",
    "check_spo",
    "submit_idea",
    "check_po",
)

CHATBOT_READ_ONLY_TOOLS_BEFORE = frozenset(
    {
        "crm_certificates_list",
        "crm_complaint_analytics",
        "crm_complaints_list",
        "crm_forms_management_forms_list",
        "crm_incoming_stock_by_product",
        "crm_incoming_stock_list",
        "crm_incoming_stock_shipments",
        "crm_inventory_stock_balance_list",
        "crm_inventory_warehouses_list",
        "crm_lookup_resolve",
        "crm_marketing_promotion_attachments_list",
        "crm_marketing_promotion_products_list",
        "crm_marketing_promotions_list",
        "crm_master_brands_list",
        "crm_master_customers_list",
        "crm_master_product_attachments_list",
        "crm_master_product_categories_list",
        "crm_master_products_list",
        "crm_master_units_of_measure_list",
        # `crm_order_analytics` left the pool on 8 Sep 2026 (see the `order` row).
        "crm_order_management_orders_by_product_list",
        "crm_order_management_orders_list",
        "crm_portal_link_get",
        "crm_procurement_po_placed_list",
        "crm_procurement_spo_allocations_last_receipt_list",
        "crm_project_detail",
        "crm_project_forecast",
        "crm_project_quotations_list",
        "crm_projects_list",
        "crm_resource_attachments_catalogue",
        "crm_resource_attachments_current_stock_list",
        "crm_resource_attachments_list",
        "crm_sla_conversation_event_logs_list",
        "crm_sla_conversation_tracking_dashboard",
        "crm_sla_conversation_tracking_list",
        "crm_system_tool_capabilities_summary",
        "user_guides_read",
    }
)


class TestNothingMovedInTheCollapse:
    def test_domain_hints_is_the_same_tuple(self) -> None:
        assert contracts.DOMAIN_HINTS == DOMAIN_HINTS_BEFORE

    def test_intent_hints_are_the_same_set(self) -> None:
        """Set, not tuple: flattening the table reorders them, and nothing reads the order
        (`Literal[...]` and `frozenset(INTENT_HINTS)` are the only two consumers)."""
        assert set(contracts.INTENT_HINTS) == set(INTENT_HINTS_BEFORE)
        assert len(contracts.INTENT_HINTS) == len(set(contracts.INTENT_HINTS))

    def test_bare_entity_type_by_domain_is_unchanged(self) -> None:
        assert contracts.BARE_ENTITY_TYPE_BY_DOMAIN == BARE_ENTITY_TYPE_BY_DOMAIN_BEFORE
        assert oe.BARE_ENTITY_TYPE_BY_DOMAIN is contracts.BARE_ENTITY_TYPE_BY_DOMAIN

    def test_domain_switch_words_is_unchanged(self) -> None:
        assert contracts.DOMAIN_SWITCH_WORDS == DOMAIN_SWITCH_WORDS_BEFORE
        assert oe.DOMAIN_SWITCH_WORDS is contracts.DOMAIN_SWITCH_WORDS

    def test_default_unsupported_domains_is_unchanged(self) -> None:
        assert contracts.DEFAULT_UNSUPPORTED_DOMAINS == DEFAULT_UNSUPPORTED_DOMAINS_BEFORE
        assert DEFAULT_UNSUPPORTED_DOMAINS is contracts.DEFAULT_UNSUPPORTED_DOMAINS

    def test_the_read_only_tool_pool_is_unchanged(self) -> None:
        assert CHATBOT_READ_ONLY_TOOLS == CHATBOT_READ_ONLY_TOOLS_BEFORE


class TestTheTableIsComplete:
    def test_every_domain_hint_has_a_row(self) -> None:
        """AC-930. Trivially true while `DOMAIN_HINTS` is projected off the table, and it
        is asserted anyway: the day someone re-hardcodes the tuple, this is what fails."""
        missing = [d for d in contracts.DOMAIN_HINTS if d not in contracts.DOMAIN_SPEC]
        assert not missing, f"domains with no DOMAIN_SPEC row: {missing}"

    def test_every_intent_belongs_to_exactly_one_domain(self) -> None:
        seen: dict[str, str] = {}
        for domain, spec in contracts.DOMAIN_SPEC.items():
            for intent in spec.intents:
                assert intent not in seen, (
                    f"{intent!r} is claimed by both {seen[intent]!r} and {domain!r}"
                )
                seen[intent] = domain
        assert set(seen) == set(contracts.INTENT_HINTS)

    def test_every_switch_word_belongs_to_exactly_one_domain(self) -> None:
        seen: dict[str, str] = {}
        for domain, spec in contracts.DOMAIN_SPEC.items():
            for word in spec.switch_words:
                assert word not in seen, (
                    f"switch word {word!r} is claimed by both {seen[word]!r} and "
                    f"{domain!r} - the inverted dict would silently keep the last one"
                )
                seen[word] = domain

    def test_every_read_only_tool_is_claimed_exactly_once(self) -> None:
        """AC-930. "Claimed by exactly one domain" OR named in
        `UNDOMAINED_CHATBOT_TOOLS` as claimed by nobody on purpose - and the two sets are
        disjoint and cover the pool, so no tool is unaccounted for and none is counted
        twice.

        The escape hatch is not a loophole: twelve of the thirty-seven tools answer
        surfaces the chatbot does not route to by `domain_hint` at all (projects,
        complaints, SLA) or are helpers a lane reaches for by name. Inventing a domain for
        each would put twelve members into `DOMAIN_HINTS` that the parser must never emit.
        """
        claimed = list(contracts.DOMAIN_CLAIMED_TOOLS)
        assert len(claimed) == len(set(claimed)), (
            "a tool is claimed by two domains: "
            + ", ".join(sorted({t for t in claimed if claimed.count(t) > 1}))
        )
        undomained = set(contracts.UNDOMAINED_CHATBOT_TOOLS)
        assert not (set(claimed) & undomained), (
            "a tool is both claimed by a domain and listed as undomained: "
            + ", ".join(sorted(set(claimed) & undomained))
        )
        assert set(claimed) | undomained == CHATBOT_READ_ONLY_TOOLS

    def test_every_escalation_team_is_a_declared_team(self) -> None:
        for domain, spec in contracts.DOMAIN_SPEC.items():
            if spec.escalation_team is not None:
                assert spec.escalation_team in contracts.SUGGESTED_TEAMS, (
                    f"{domain!r} escalates to {spec.escalation_team!r}, which is not a "
                    "SUGGESTED_TEAMS member"
                )

    @pytest.mark.parametrize("domain", sorted(contracts.DOMAIN_SPEC))
    def test_the_table_agrees_with_the_replay_graded_routing_ladder(self, domain: str) -> None:
        """`derive_routing` is a PORTED NODE graded byte-for-byte against captured n8n
        executions, so it stays the executable copy and the table mirrors it. This is what
        stops the pair drifting - it is the same H28 shape the table exists to close, one
        level up.

        Asked with no entities and no access levels, which is the only input that isolates
        the domain: `product_attachment`'s ladder splits on a per-TURN certificate signal,
        so this asks for its non-cert arm, which is what the row records.
        """
        routed = oe.derive_routing(
            {"domain_hint": domain, "entities": [], "access_levels": []}
        )
        assert routed["suggested_team"] == contracts.DOMAIN_SPEC[domain].escalation_team

    def test_only_a_domain_with_no_tool_is_unsupported_by_default(self) -> None:
        """The refusal is a consequence, not a policy: `goods_receive` is refused because
        nothing can answer it. A domain with tools that is still marked unsupported would
        be a deliberate policy and needs saying out loud here first."""
        for domain in contracts.DEFAULT_UNSUPPORTED_DOMAINS:
            assert not contracts.DOMAIN_SPEC[domain].tools, (
                f"{domain!r} is unsupported by default but claims tools - if that is a "
                "policy rather than an absence, say so in DOMAIN_SPEC and change this test"
            )


class TestTheCoreSideCopiesAgree:
    """AC-002 forbids core importing `app/services/chatbot/`, so two core-side readers of
    `DEFAULT_UNSUPPORTED_DOMAINS` reach it through `app/modules/chatbot/lane_vocabulary.py`
    and one (a DDL string) cannot. This is the gate on all three."""

    def test_the_module_doorway_publishes_the_derived_list(self) -> None:
        from app.modules.chatbot.lane_vocabulary import default_unsupported_domains

        assert default_unsupported_domains() == list(contracts.DEFAULT_UNSUPPORTED_DOMAINS)

    def test_the_system_setting_python_default_is_the_derived_list(self) -> None:
        from app.models.user import SystemSetting

        column = SystemSetting.__table__.c.chatbot_unsupported_domains
        assert column.default.arg(None) == list(contracts.DEFAULT_UNSUPPORTED_DOMAINS)

    def test_the_system_setting_server_default_matches_the_derived_list(self) -> None:
        """The one copy that has to stay a literal: `server_default` is the DDL text
        Postgres stores in the column definition, and it must equal what migration 488's
        `alter_column` wrote. Pinned rather than derived, the same trade
        `CHATBOT_READ_ONLY_TOOLS` makes against the MCP catalogue."""
        import json

        from app.models.user import SystemSetting

        column = SystemSetting.__table__.c.chatbot_unsupported_domains
        server_default = str(column.server_default.arg)
        assert json.loads(server_default) == list(contracts.DEFAULT_UNSUPPORTED_DOMAINS), (
            f"the column's server_default {server_default!r} no longer matches "
            f"{list(contracts.DEFAULT_UNSUPPORTED_DOMAINS)} - a domain's "
            "`default_supported` changed without the migration that moves the DDL default "
            "and backfills the rows still on the old one"
        )

    def test_the_settings_reset_table_uses_the_doorway_not_a_literal(self) -> None:
        """`PUT /settings/general` treats an explicit null as "reset to the default". That
        table was the THIRD copy of this list and the one A6 missed."""
        import inspect

        from app.api.v1.user_management import settings as settings_mod

        source = inspect.getsource(settings_mod._update_general_settings_impl)
        assert '"chatbot_unsupported_domains": default_unsupported_domains()' in source, (
            "the null-reset table is back to a hardcoded list; it must read the chatbot "
            "module's doorway so it cannot disagree with route.decide"
        )


class TestTheHazardTablesStayIndependent:
    """The tables D9 deliberately does NOT fold in. Each carries a hand-earned annotation
    naming the live turn that put a row there (owner rulings K2 to K4, C1, the 2026-08-09
    promotion-brand leak), and folding them into a uniform table would keep the shape and
    lose the reason. Asserted so a later "finish the job" pass has to argue with a test."""

    @pytest.mark.parametrize(
        "name",
        [
            "AXIS_BY_DOMAIN",
            "DOMAIN_SUBJECT_AXIS",
            "DOMAIN_SUBJECT_HINT",
            "DOMAIN_BLOCKED_HINTS",
            "MEMBER_OFFER_FILTER_HINTS",
            "DOMAIN_BROADEN_BLOCKED_HINTS",
        ],
    )
    def test_the_table_still_lives_beside_its_evidence(self, name: str) -> None:
        assert hasattr(oe, name)
        assert not hasattr(contracts, name), (
            f"{name} moved into contracts.py. It is a per-domain HAZARD, not a per-domain "
            "fact: every row names the live turn that earned it, and those notes belong "
            "with the readers they constrain."
        )

    @pytest.mark.parametrize(
        "name",
        [
            "DOMAIN_SUBJECT_AXIS",
            "DOMAIN_SUBJECT_HINT",
            "DOMAIN_BLOCKED_HINTS",
            "DOMAIN_BROADEN_BLOCKED_HINTS",
        ],
    )
    def test_no_hazard_table_names_a_domain_the_contract_does_not_declare(
        self, name: str
    ) -> None:
        unknown = [d for d in getattr(oe, name) if d not in contracts.DOMAIN_HINTS]
        assert not unknown, f"{name} has rows for undeclared domains: {unknown}"
