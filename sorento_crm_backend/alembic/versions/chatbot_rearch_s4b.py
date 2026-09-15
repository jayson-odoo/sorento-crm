"""`chatbot_domains`' list columns become real `text[]`, as AC-1501 declares them.

S0 created `intents`, `tools`, `switch_words` and `ladder` as JSONB. AC-1501 declares
all four as `text[]`, and the difference is not cosmetic: a JSONB column answers
`switch_words || ARRAY['word']` with `operator does not exist`, so every ordinary array
operation an operator, a route or a test would reach for has to be written as a JSON
round trip instead. `narrowing` and `base_property_words` stay JSONB, which is what the
same AC says they are - they are maps, not lists.

Data survives the change. Postgres refuses a subquery in a `USING` transform, so the
unpack runs as an ordinary UPDATE into a temporary column rather than inside the
`ALTER ... TYPE` - three statements per column instead of one, same result.

Revision ID: chatbot_rearch_s4b
Revises: chatbot_rearch_s4
"""
from alembic import op

revision = "chatbot_rearch_s4b"
down_revision = "chatbot_rearch_s4"
branch_labels = None
depends_on = None

_LIST_COLUMNS = ("intents", "tools", "switch_words", "ladder")


def upgrade() -> None:
    for column in _LIST_COLUMNS:
        op.execute(f"ALTER TABLE chatbot_domains ADD COLUMN {column}_arr text[]")
        op.execute(
            f"UPDATE chatbot_domains SET {column}_arr = ("
            f"  SELECT coalesce(array_agg(value), ARRAY[]::text[]) "
            f"  FROM jsonb_array_elements_text({column}) AS value"
            f")"
        )
        op.execute(f"ALTER TABLE chatbot_domains DROP COLUMN {column}")
        op.execute(f"ALTER TABLE chatbot_domains RENAME COLUMN {column}_arr TO {column}")
        op.execute(
            f"ALTER TABLE chatbot_domains ALTER COLUMN {column} SET DEFAULT ARRAY[]::text[], "
            f"ALTER COLUMN {column} SET NOT NULL"
        )


def downgrade() -> None:
    for column in _LIST_COLUMNS:
        op.execute(
            f"ALTER TABLE chatbot_domains ALTER COLUMN {column} DROP DEFAULT, "
            f"ALTER COLUMN {column} TYPE jsonb USING to_jsonb({column}), "
            f"ALTER COLUMN {column} SET DEFAULT '[]'::jsonb"
        )
