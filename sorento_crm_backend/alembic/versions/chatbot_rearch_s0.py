"""Chatbot turn re-architecture S0 (PLAN-chatbot-turn-rearch.md, AC-1501 to AC-1503).

Two new tables, seeded from the code constants they replace:

* `chatbot_domains` - one row per `contracts.DOMAIN_SPEC` entry (AC-1501). Guardrail:
  the seed stays byte-identical to the constant until the constant is deleted (S6);
  `tests/chatbot/test_rearch_s0_domains_seed.py` reads this table on every run.
* `chatbot_entity_kinds` - one row per `contracts.ENTITY_HINTS` kind (AC-1502). NOT the
  tier order - that is `system_settings.chatbot_tier_order` below (captain ruling,
  16 Sep 2026): `tier` is not one of the 12 `ENTITY_HINTS` and never gets a row here.

Plus additive columns for AC-1503 (`respond_contacts`), AC-1505 (`conversation_frames`)
and AC-1502's tier order (`system_settings`) - all three are plain model columns
`create_all` already reflects for the test suite; added here too so a REAL migrated
database (never `create_all`) carries them.

Revision ID: chatbot_rearch_s0
Revises: ptag_0010_badge_textcolor
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s0"
down_revision = "ptag_0010_badge_textcolor"
branch_labels = None
depends_on = None


# --------------------------------------------------------------------------- #
# chatbot_domains seed - one row per app.services.chatbot.contracts.DOMAIN_SPEC entry,
# in that dict's own declaration order (sort_order). Every fact below is read off that
# constant (or a sibling one named in the docstring), not invented: label from
# lanes.business.answer.DOMAIN_LABELS where named, escalation_team_code from
# DOMAIN_SPEC.escalation_team (one of contracts.SUGGESTED_TEAMS), takes_date_filter from
# whether any of the domain's tools appears in lanes.business.fetch.DATE_PARAMS,
# reveal_key from the three named grant constants (answer.DOMAIN_GRANT_REQUIRED,
# answer._CROSSDOMAIN_RUNG_GRANT) plus the inline "inventory.sellable" gate in fetch.py,
# ladder from answer.DEFAULT_CROSSDOMAIN_LADDER (== the system_settings
# chatbot_crossdomain_ladder default, migration 491), narrowing from the six triples
# AC-1526 names literally.
# --------------------------------------------------------------------------- #
_DOMAINS = [
    dict(
        name="master_products",
        label="product information",
        intents=["check_product"],
        tools=[
            "crm_master_products_list",
            "crm_master_brands_list",
            "crm_master_product_categories_list",
            "crm_master_units_of_measure_list",
        ],
        escalation_team_code="purchasing",
        switch_words=[
            "catalogue", "catalog", "spec", "specs", "specification",
            "specifications", "dimension", "dimensions",
        ],
        narrowing={},
        reveal_key=None,
        supported=True,
        ladder=[],
    ),
    dict(
        name="product_attachment",
        label="product attachments",
        intents=["check_product_attachment"],
        tools=["crm_master_product_attachments_list", "crm_certificates_list"],
        escalation_team_code="marketing_product",
        switch_words=[],
        narrowing={"attachment_type": "narrow_by_type"},
        reveal_key=None,
        supported=True,
        ladder=[],
    ),
    dict(
        name="promotion",
        label="promotions",
        intents=["check_promotion"],
        tools=[
            "crm_marketing_promotions_list",
            "crm_marketing_promotion_attachments_list",
            "crm_marketing_promotion_products_list",
        ],
        escalation_team_code="marketing_promotion",
        switch_words=["promo", "promos", "promotion", "promotions", "promosi"],
        narrowing={"tier": "narrow_by_tier"},
        reveal_key=None,
        supported=True,
        ladder=[],
    ),
    dict(
        name="forms",
        label="forms",
        intents=["get_forms"],
        tools=["crm_forms_management_forms_list"],
        escalation_team_code="marketing_form",
        switch_words=[],
        narrowing={},
        reveal_key=None,
        supported=True,
        ladder=[],
    ),
    dict(
        name="inventory",
        label="stock",
        intents=["check_stock", "low_stock_report"],
        tools=[
            "crm_inventory_stock_balance_list",
            "crm_inventory_warehouses_list",
            "crm_low_stock_report",
        ],
        escalation_team_code="warehouse",
        switch_words=[
            "stock", "stocks", "inventory", "stok", "qty", "quantity",
            "low stock", "reorder report", "below level",
        ],
        narrowing={"product": "list_all"},
        # The inline gate in lanes/business/fetch.py: a sellable-stock answer is
        # refused without this reveal.
        reveal_key="inventory.sellable",
        supported=True,
        ladder=["incoming", "purchase_order"],
    ),
    dict(
        name="order",
        label="orders",
        intents=["check_order"],
        tools=[
            "crm_order_management_orders_list",
            "crm_order_management_orders_by_product_list",
            "crm_master_customers_list",
            "crm_outstanding_report",
        ],
        escalation_team_code="customer_service",
        switch_words=[
            "order", "orders", "outstanding", "tempahan",
            "delivery", "deliveries", "deliver", "delivered",
            "penghantaran", "hantar", "dihantar",
        ],
        narrowing={"customer": "must_narrow_one"},
        # answer._OUTSTANDING_SO_GRANT ("sales_orders.outstanding"): the SO arm of an
        # outstanding-order answer is refused without it.
        reveal_key="sales_orders.outstanding",
        supported=True,
        ladder=[],
    ),
    dict(
        name="incoming",
        label="incoming stock",
        intents=["check_incoming"],
        tools=[
            "crm_incoming_stock_list",
            "crm_incoming_stock_by_product",
            "crm_incoming_stock_shipments",
        ],
        escalation_team_code="purchasing",
        switch_words=["incoming", "eta", "shipment", "shipments", "arriving", "container", "containers"],
        narrowing={"product": "narrow_to_code"},
        reveal_key=None,
        supported=True,
        ladder=["inventory", "purchase_order"],
    ),
    dict(
        name="portal_link",
        label="this request",
        intents=["get_portal_link"],
        tools=["crm_portal_link_get"],
        escalation_team_code=None,
        switch_words=[],
        narrowing={},
        reveal_key=None,
        supported=True,
        ladder=[],
    ),
    dict(
        name="resource_attachment",
        label="resource attachments",
        intents=["get_resource_attachment"],
        tools=[
            "crm_resource_attachments_list",
            "crm_resource_attachments_catalogue",
            "crm_resource_attachments_current_stock_list",
        ],
        escalation_team_code=None,
        switch_words=[],
        narrowing={},
        reveal_key=None,
        supported=True,
        ladder=[],
    ),
    dict(
        name="goods_receive",
        label="goods receive",
        intents=["check_goods_receive"],
        tools=[],
        escalation_team_code=None,
        switch_words=[],
        narrowing={},
        reveal_key=None,
        supported=False,
        ladder=[],
    ),
    dict(
        name="spo_allocation",
        label="last in",
        intents=["check_spo"],
        tools=["crm_procurement_spo_allocations_last_receipt_list"],
        escalation_team_code=None,
        switch_words=["spo"],
        narrowing={"product": "narrow_to_code"},
        reveal_key=None,
        supported=True,
        ladder=[],
    ),
    dict(
        name="ideate",
        label="ideas",
        intents=["submit_idea"],
        tools=[],
        escalation_team_code=None,
        switch_words=[],
        narrowing={},
        reveal_key=None,
        supported=True,
        ladder=[],
    ),
    dict(
        name="purchase_order",
        label="outstanding purchase orders",
        intents=["check_po"],
        tools=["crm_procurement_po_placed_list"],
        escalation_team_code="purchasing",
        switch_words=["po"],
        narrowing={"product": "narrow_to_code"},
        # answer._CROSSDOMAIN_RUNG_GRANT: the PO rung of the cross-domain climb is
        # refused without it.
        reveal_key="purchase_orders.placed",
        supported=True,
        ladder=[],
    ),
    dict(
        name="purchase_cost",
        label="last purchase cost",
        intents=["check_po_cost"],
        tools=["crm_procurement_po_last_cost_list"],
        escalation_team_code="purchasing",
        switch_words=[],
        narrowing={"product": "narrow_to_code"},
        # answer.DOMAIN_GRANT_REQUIRED["purchase_cost"]: the whole domain is refused
        # without it.
        reveal_key="purchase_orders.cost",
        supported=True,
        ladder=[],
    ),
]

# lanes/business/fetch.DATE_PARAMS's own keys - which tools take a date window. A
# domain's takes_date_filter is true when ANY of its tools appears here (AC-1501).
_DATE_PARAM_TOOLS = {
    "crm_order_management_orders_list",
    "crm_order_management_orders_by_product_list",
    "crm_incoming_stock_list",
    "crm_incoming_stock_by_product",
    "crm_incoming_stock_shipments",
    "crm_marketing_promotions_list",
    "crm_resource_attachments_list",
    "crm_resource_attachments_catalogue",
    "crm_sla_conversation_event_logs_list",
    "crm_procurement_po_placed_list",
    "crm_outstanding_report",
    "crm_low_stock_report",
}

# --------------------------------------------------------------------------- #
# chatbot_entity_kinds seed - one row per contracts.ENTITY_HINTS kind, in that tuple's
# own order. base_property_words is populated for "product" only, from
# lanes/business/fetch._BASE_PROPERTY_WORDS plus "discontinued" (-> is_discontinued,
# AC-1502's own literal) and "brand" (-> some column, non-empty).
# --------------------------------------------------------------------------- #
_PRODUCT_BASE_PROPERTY_WORDS = {
    "price": "list_price",
    "list price": "list_price",
    "harga": "list_price",
    "cost": "cost_price",
    "dimension": "dimensions",
    "dimensions": "dimensions",
    "size": "dimensions",
    "ukuran": "dimensions",
    "saiz": "dimensions",
    "description": "description",
    "name": "product_name",
    "discontinued": "is_discontinued",
    "brand": "brand_id",
}

_ENTITY_KINDS = [
    dict(
        kind="product",
        label="Product",
        resolver_source="master_products",
        did_you_mean=True,
        default_narrowing="list_all",
        family_grouping="base_code",
        base_property_words=_PRODUCT_BASE_PROPERTY_WORDS,
    ),
    dict(
        kind="promotion",
        label="Promotion",
        resolver_source="promotions",
        did_you_mean=True,
        default_narrowing="optional_filter",
        family_grouping=None,
        base_property_words={},
    ),
    dict(
        kind="customer",
        label="Customer",
        resolver_source="customers",
        did_you_mean=True,
        default_narrowing="must_narrow_one",
        family_grouping="ledger_family",
        base_property_words={},
    ),
    dict(
        kind="transporter",
        label="Transporter",
        resolver_source="transporters",
        did_you_mean=True,
        default_narrowing="optional_filter",
        family_grouping=None,
        base_property_words={},
    ),
    dict(
        kind="inbound_shipment",
        label="Inbound shipment",
        resolver_source="packing_lists",
        did_you_mean=False,
        default_narrowing="optional_filter",
        family_grouping=None,
        base_property_words={},
    ),
    dict(
        kind="warehouse",
        label="Warehouse",
        resolver_source="warehouses",
        did_you_mean=True,
        default_narrowing="optional_filter",
        family_grouping=None,
        base_property_words={},
    ),
    dict(
        kind="attachment",
        label="Attachment",
        resolver_source="attachments",
        did_you_mean=False,
        default_narrowing="not_applicable",
        family_grouping=None,
        base_property_words={},
    ),
    dict(
        kind="form",
        label="Form",
        resolver_source="forms",
        did_you_mean=False,
        default_narrowing="not_applicable",
        family_grouping=None,
        base_property_words={},
    ),
    dict(
        kind="order",
        label="Order",
        resolver_source="orders",
        did_you_mean=False,
        default_narrowing="not_applicable",
        family_grouping=None,
        base_property_words={},
    ),
    dict(
        kind="category",
        label="Category",
        resolver_source="product_categories",
        did_you_mean=True,
        default_narrowing="optional_filter",
        family_grouping=None,
        base_property_words={},
    ),
    dict(
        kind="brand",
        label="Brand",
        resolver_source="brands",
        did_you_mean=True,
        default_narrowing="optional_filter",
        family_grouping=None,
        base_property_words={},
    ),
    dict(
        kind="attachment_type",
        label="Attachment type",
        resolver_source="attachment_types",
        did_you_mean=True,
        default_narrowing="narrow_by_type",
        family_grouping=None,
        base_property_words={},
    ),
]

# system_settings.chatbot_tier_order's default - lanes/business/tier_gate.TIER_ORDER's
# own literal order (AC-1502, captain ruling 16 Sep 2026).
_TIER_ORDER = ["dealer", "office", "end_user"]


def upgrade() -> None:
    bind = op.get_bind()

    # ---- chatbot_domains -------------------------------------------------- #
    op.create_table(
        "chatbot_domains",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("intents", sa.dialects.postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("tools", sa.dialects.postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("primary_tool", sa.Text(), nullable=True),
        sa.Column("escalation_team_code", sa.Text(), nullable=True),
        sa.Column("switch_words", sa.dialects.postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("narrowing", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("takes_date_filter", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reveal_key", sa.Text(), nullable=True),
        sa.Column("supported", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ladder", sa.dialects.postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    domains_table = sa.table(
        "chatbot_domains",
        sa.column("name", sa.Text()),
        sa.column("label", sa.Text()),
        sa.column("intents", sa.dialects.postgresql.JSONB()),
        sa.column("tools", sa.dialects.postgresql.JSONB()),
        sa.column("primary_tool", sa.Text()),
        sa.column("escalation_team_code", sa.Text()),
        sa.column("switch_words", sa.dialects.postgresql.JSONB()),
        sa.column("narrowing", sa.dialects.postgresql.JSONB()),
        sa.column("takes_date_filter", sa.Boolean()),
        sa.column("reveal_key", sa.Text()),
        sa.column("supported", sa.Boolean()),
        sa.column("ladder", sa.dialects.postgresql.JSONB()),
        sa.column("sort_order", sa.Integer()),
    )
    for i, row in enumerate(_DOMAINS):
        bind.execute(
            domains_table.insert().values(
                name=row["name"],
                label=row["label"],
                intents=row["intents"],
                tools=row["tools"],
                primary_tool=row["tools"][0] if row["tools"] else None,
                escalation_team_code=row["escalation_team_code"],
                switch_words=row["switch_words"],
                narrowing=row["narrowing"],
                takes_date_filter=any(t in _DATE_PARAM_TOOLS for t in row["tools"]),
                reveal_key=row["reveal_key"],
                supported=row["supported"],
                ladder=row["ladder"],
                sort_order=i,
            )
        )

    # ---- chatbot_entity_kinds ---------------------------------------------- #
    op.create_table(
        "chatbot_entity_kinds",
        sa.Column("kind", sa.Text(), primary_key=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("resolver_source", sa.Text(), nullable=False),
        sa.Column("did_you_mean", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("default_narrowing", sa.Text(), nullable=False),
        sa.Column("family_grouping", sa.Text(), nullable=True),
        sa.Column("base_property_words", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    kinds_table = sa.table(
        "chatbot_entity_kinds",
        sa.column("kind", sa.Text()),
        sa.column("label", sa.Text()),
        sa.column("resolver_source", sa.Text()),
        sa.column("did_you_mean", sa.Boolean()),
        sa.column("default_narrowing", sa.Text()),
        sa.column("family_grouping", sa.Text()),
        sa.column("base_property_words", sa.dialects.postgresql.JSONB()),
        sa.column("sort_order", sa.Integer()),
    )
    for i, row in enumerate(_ENTITY_KINDS):
        bind.execute(
            kinds_table.insert().values(
                kind=row["kind"],
                label=row["label"],
                resolver_source=row["resolver_source"],
                did_you_mean=row["did_you_mean"],
                default_narrowing=row["default_narrowing"],
                family_grouping=row["family_grouping"],
                base_property_words=row["base_property_words"],
                sort_order=i,
            )
        )

    # ---- respond_contacts (AC-1503) ---------------------------------------- #
    op.add_column(
        "respond_contacts",
        sa.Column("chatbot_profile", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "respond_contacts",
        sa.Column("chatbot_recall_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # ---- conversation_frames (AC-1505) -------------------------------------- #
    op.add_column("conversation_frames", sa.Column("contact_respond_id", sa.String(128), nullable=True))
    op.create_index(
        "ix_conversation_frames_contact_respond_id",
        "conversation_frames",
        ["contact_respond_id"],
    )
    op.add_column(
        "conversation_frames",
        sa.Column("entities", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "conversation_frames",
        sa.Column("turn_ids", sa.dialects.postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )
    op.add_column("conversation_frames", sa.Column("opened_at", sa.DateTime(), nullable=True))

    # ---- system_settings.chatbot_tier_order (AC-1502) ----------------------- #
    op.add_column(
        "system_settings",
        sa.Column(
            "chatbot_tier_order",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=json.dumps(_TIER_ORDER),
        ),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "chatbot_tier_order")

    op.drop_column("conversation_frames", "opened_at")
    op.drop_column("conversation_frames", "turn_ids")
    op.drop_column("conversation_frames", "entities")
    op.drop_index("ix_conversation_frames_contact_respond_id", table_name="conversation_frames")
    op.drop_column("conversation_frames", "contact_respond_id")

    op.drop_column("respond_contacts", "chatbot_recall_enabled")
    op.drop_column("respond_contacts", "chatbot_profile")

    op.drop_table("chatbot_entity_kinds")
    op.drop_table("chatbot_domains")
