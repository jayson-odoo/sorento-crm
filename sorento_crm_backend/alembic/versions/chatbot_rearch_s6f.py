"""`chatbot_entity_kinds` gets a uuid `id` primary key (ADR-PRODUCT-STANDARDS Data Model).

`tests/test_schema_uuid_id_principle.py` fails any domain table with no uuid `id`. S0
gave `chatbot_entity_kinds` a natural `kind` text primary key - the one column every
reader (`turn/policy.py::load_policy`, the S5 CRUD routes, `_find_kind`) already looks
up by - but the table is a first-class domain table, not a junction, and the default
is compliance, the same way `chatbot_domains` already carries `id` beside its own
natural key (`name`). `kind` keeps every existing reader working unchanged: it becomes
a `NOT NULL UNIQUE` column instead of the primary key, so `ChatbotEntityKind.kind ==
...` lookups are untouched.

Revision ID: chatbot_rearch_s6f
Revises: chatbot_rearch_s6e
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s6f"
down_revision = "chatbot_rearch_s6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chatbot_entity_kinds "
        "ADD COLUMN id uuid NOT NULL DEFAULT gen_random_uuid()"
    )
    op.execute("ALTER TABLE chatbot_entity_kinds DROP CONSTRAINT chatbot_entity_kinds_pkey")
    op.execute("ALTER TABLE chatbot_entity_kinds ADD PRIMARY KEY (id)")
    op.execute("ALTER TABLE chatbot_entity_kinds ADD CONSTRAINT chatbot_entity_kinds_kind_key UNIQUE (kind)")
    op.execute("ALTER TABLE chatbot_entity_kinds ALTER COLUMN id DROP DEFAULT")


def downgrade() -> None:
    op.execute("ALTER TABLE chatbot_entity_kinds DROP CONSTRAINT chatbot_entity_kinds_kind_key")
    op.execute("ALTER TABLE chatbot_entity_kinds DROP CONSTRAINT chatbot_entity_kinds_pkey")
    op.execute("ALTER TABLE chatbot_entity_kinds ADD PRIMARY KEY (kind)")
    op.execute("ALTER TABLE chatbot_entity_kinds DROP COLUMN id")
