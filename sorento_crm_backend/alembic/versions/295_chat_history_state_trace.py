"""Per-turn conversation state transition on chat_histories + debugging view.

Adds one opaque jsonb column `state_trace`, populated by n8n on INCOMING rows only,
carrying the per-turn conversation-state transition (v1):

    {v, before, parser_raw, parser_applied, after}

`after: null` is meaningful and expected on real traffic (no-access refusals,
voice-not-allowed, LLM-fallback branches never write state). It is NOT an error, NOT
`{}`, and NOT absent — so the column is opaque jsonb and nothing on the path coerces it.

The column is nullable with no server_default, so Postgres records the change in catalog
only — no table rewrite, no long ACCESS EXCLUSIVE, safe against live without a window.
No index in v1: the access pattern (trace for this turn / this contact, recently) is
already served by the existing partial btree indexes; a whole-document GIN would be paid
on every insert to accelerate a flag-search nobody has run yet.

`public.v_turn_state_transition` turns the raw 3 KB jsonb into the answer to "which turn
silently dropped that entity, and what fired?" — entities lost/gained as set arithmetic,
the decision flags that fired, and whether post-processing overruled the LLM.

Naming deviation flagged for review: `v_` prefix + `public` schema, per the brief. The
repo's sole view precedent is `scm.<name>_v` (suffix, namespaced). Chosen `public` because
this reads a `public` table and there is no dedicated schema for it.

CAVEAT for whoever adds the sixth computed column: `CREATE OR REPLACE VIEW` cannot change
the output column list or types, only the body. Any change to the view's columns needs an
explicit `DROP VIEW` first — a bare re-run of this migration will fail otherwise.

Revision ID: 295_chat_history_state_trace
Revises: 294_chat_latency_percentile
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "295_chat_history_state_trace"
down_revision = "294_chat_latency_percentile"
branch_labels = None
depends_on = None


# Written against n8n contract items N1 (before/after are the UNWRAPPED variables object),
# N2 (entities is an array of objects keyed by `raw`; identity = lower(btrim(raw))),
# N3 (scope_exclusive_applied/entity_op_applied/entities_filtered/dym_pick_applied are
# booleans; domain_signal_source is a string). If those move, re-issue with DROP VIEW.
_STATE_TRANSITION_V = """
CREATE OR REPLACE VIEW public.v_turn_state_transition AS
WITH t AS (
    SELECT id, turn_id, contact_id, phone_number, first_name,
           sent_at, message, state_trace
    FROM   chat_histories
    WHERE  type = 'incoming'
      AND  state_trace IS NOT NULL
),
flags AS (
    SELECT t.id,
           (jsonb_typeof(t.state_trace->'after') <> 'null') AS wrote_state,
           t.state_trace->'parser_raw'                       AS praw,
           t.state_trace->'parser_applied'                   AS papp
    FROM t
),
b AS (
    SELECT t.id,
           lower(btrim(e->>'raw'))                       AS k,
           COALESCE(e->>'raw', '')                       AS label,
           COALESCE(e->>'entity_type', e->>'hint', '?')  AS etype
    FROM t, LATERAL jsonb_array_elements(
             COALESCE(t.state_trace->'before'->'entities', '[]'::jsonb)) e
    WHERE  e->>'raw' IS NOT NULL
),
a AS (
    SELECT t.id,
           lower(btrim(e->>'raw'))                       AS k,
           COALESCE(e->>'raw', '')                       AS label,
           COALESCE(e->>'entity_type', e->>'hint', '?')  AS etype
    FROM t, LATERAL jsonb_array_elements(
             COALESCE(t.state_trace->'after'->'entities', '[]'::jsonb)) e
    WHERE  e->>'raw' IS NOT NULL
)
SELECT
    t.turn_id,
    t.id                                        AS chat_history_id,
    t.contact_id,
    t.phone_number,
    t.first_name,
    t.sent_at,
    t.message                                   AS incoming_message,
    f.wrote_state,
    COALESCE(t.state_trace->>'v', '?')          AS trace_version,

    -- entities present BEFORE but absent AFTER. NULL (not '{}') when the turn wrote
    -- no state -- absence of a write is not evidence of a loss.
    CASE WHEN f.wrote_state THEN COALESCE((
        SELECT array_agg(DISTINCT b.etype || ':' || b.label ORDER BY b.etype || ':' || b.label)
        FROM b WHERE b.id = t.id
          AND NOT EXISTS (SELECT 1 FROM a WHERE a.id = t.id AND a.k = b.k)
    ), '{}') END                                AS entities_lost,

    CASE WHEN f.wrote_state THEN COALESCE((
        SELECT array_agg(DISTINCT a.etype || ':' || a.label ORDER BY a.etype || ':' || a.label)
        FROM a WHERE a.id = t.id
          AND NOT EXISTS (SELECT 1 FROM b WHERE b.id = t.id AND b.k = a.k)
    ), '{}') END                                AS entities_gained,

    -- which decision flags fired this turn. Booleans: set when true.
    -- domain_signal_source is a string: reported as source=<value> when non-null.
    COALESCE((
        SELECT array_agg(x ORDER BY x) FROM (
            SELECT 'scope_exclusive_applied' AS x
              WHERE (f.papp->>'scope_exclusive_applied')::text = 'true'
            UNION ALL SELECT 'entity_op_applied'
              WHERE (f.papp->>'entity_op_applied')::text = 'true'
            UNION ALL SELECT 'entities_filtered'
              WHERE (f.papp->>'entities_filtered')::text = 'true'
            UNION ALL SELECT 'dym_pick_applied'
              WHERE (f.papp->>'dym_pick_applied')::text = 'true'
            UNION ALL SELECT 'source=' || (f.papp->>'domain_signal_source')
              WHERE f.papp->>'domain_signal_source' IS NOT NULL
        ) s
    ), '{}')                                    AS cause_flags,

    -- did post-processing overrule the LLM? NULL when parser_raw was not captured.
    CASE WHEN f.praw IS NULL OR jsonb_typeof(f.praw) = 'null' THEN NULL
         ELSE COALESCE((
            SELECT array_agg(x ORDER BY x) FROM (
                SELECT 'domain' AS x
                  WHERE f.praw->>'domain_hint' IS DISTINCT FROM f.papp->>'domain_hint'
                UNION ALL SELECT 'scope'
                  WHERE f.praw->>'scope_exclusive' IS DISTINCT FROM f.papp->>'scope_exclusive'
                UNION ALL SELECT 'entities'
                  WHERE COALESCE(f.praw->'entities','[]'::jsonb)
                     IS DISTINCT FROM COALESCE(f.papp->'entities','[]'::jsonb)
            ) s
         ), '{}')
    END                                         AS parser_drift,

    t.state_trace                               AS raw_trace
FROM t JOIN flags f ON f.id = t.id;
"""


def _existing_columns(conn) -> set[str]:
    rows = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'chat_histories'"
        )
    )
    return {r[0] for r in rows}


def upgrade():
    conn = op.get_bind()
    if "state_trace" not in _existing_columns(conn):
        op.add_column(
            "chat_histories",
            sa.Column("state_trace", postgresql.JSONB(), nullable=True),
        )
    op.execute(_STATE_TRANSITION_V)


def downgrade():
    # Drop the view before the column it depends on. Explicit, not CASCADE, so the
    # down-migration is auditable rather than silently taking the view with it.
    op.execute("DROP VIEW IF EXISTS public.v_turn_state_transition")
    op.drop_column("chat_histories", "state_trace")
