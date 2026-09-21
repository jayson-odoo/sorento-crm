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
Revises: ptag_0013_r10
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s0"
down_revision = "ptag_0013_r10"
branch_labels = None
depends_on = None


# The rows this migration seeds are FROZEN beside it, in
# `alembic/_chatbot_policy_seed.py` - never read from `app/services/chatbot/turn/
# policy_rows.py` or `app/modules/chatbot/lane_vocabulary.py`. A migration has to produce
# the same database whenever it runs, and importing live application code at module scope
# means an `alembic upgrade head` replayed from genesis a year from now seeds whatever
# those files say THEN, or fails outright if the import has moved. Same precedent as
# `alembic/_legacy_prompt_bodies.py`. The two copies are identical at this revision, and
# the one that may move afterwards is the app's: a policy change is a NEW migration
# against `chatbot_domains` / `chatbot_entity_kinds`, never an edit to either file.


def seed_domains_and_kinds(bind) -> tuple[int, int]:
    """Insert the `chatbot_domains` / `chatbot_entity_kinds` seed rows, skipping any
    name/kind already present.

    Shared by `upgrade()` (a table this same migration just created, so always empty -
    `intents`/`tools`/`switch_words`/`ladder` are still JSONB at that point, `s4b`
    converts them to `text[]` later in the chain) and
    `scripts.bootstrap_env.seed_chatbot_policy` (a `create_all`-built table, which
    reflects every column at its FINAL model type - `text[]` for those four - and every
    other column this migration adds, but none of the INSERTs a migration BODY only
    runs through `alembic upgrade`) - so the two paths read the exact same rows and
    cannot drift. Both tables are REFLECTED rather than declared with a fixed column
    type for exactly that reason: the same values (Python lists/dicts) bind correctly
    against either shape once SQLAlchemy knows the column's real type from the catalog,
    which a hardcoded `sa.table(..., sa.column("intents", JSONB()))` cannot do for both
    callers at once. Idempotent: re-run against an already-seeded table is a no-op, and
    bootstrap may run twice.
    """
    # Imported HERE, by bare module name, the same way `475_chatbot_parser_prompt_slim`
    # reads `_legacy_prompt_bodies` (alembic puts its own directory on `sys.path`; a
    # caller loading this module directly - `scripts.bootstrap_env` - adds it too).
    from _chatbot_policy_seed import (
        DATE_PARAM_TOOLS as _DATE_PARAM_TOOLS,
        DEFAULT_DOMAIN_ROWS as _DOMAINS,
        DEFAULT_KIND_ROWS as _ENTITY_KINDS,
    )

    metadata = sa.MetaData()
    domains_table = sa.Table("chatbot_domains", metadata, autoload_with=bind)
    kinds_table = sa.Table("chatbot_entity_kinds", metadata, autoload_with=bind)

    existing_names = {
        row[0] for row in bind.execute(sa.text("SELECT name FROM chatbot_domains"))
    }
    domains_inserted = 0
    for i, row in enumerate(_DOMAINS):
        if row["name"] in existing_names:
            continue
        bind.execute(
            domains_table.insert().values(
                # Explicit rather than relying on a server default: `chatbot_domains.id`
                # has one on a REAL migrated database (this migration's own DDL, above)
                # but not on a `create_all`-built one (the model declares only a Python-
                # side default, which a reflected `Table` never sees) - an explicit
                # value is correct either way.
                id=str(uuid.uuid4()),
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
        domains_inserted += 1

    existing_kinds = {
        row[0] for row in bind.execute(sa.text("SELECT kind FROM chatbot_entity_kinds"))
    }
    kinds_inserted = 0
    for i, row in enumerate(_ENTITY_KINDS):
        if row["kind"] in existing_kinds:
            continue
        bind.execute(
            kinds_table.insert().values(
                # See the `domains_table` insert above - explicit for the same reason
                # (`chatbot_entity_kinds.id`, chatbot_rearch_s6f, has no server default).
                id=str(uuid.uuid4()),
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
        kinds_inserted += 1

    return domains_inserted, kinds_inserted


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

    seed_domains_and_kinds(bind)

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
    from _chatbot_policy_seed import DEFAULT_TIER_ORDER as _TIER_ORDER

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
