-- LEAN: the stored parser reasoning effort setting, sorento_explore1020 ONLY (alembic lean_0001_parser_reasoning
-- adds the same column on every migrated install; the explore copy is applied by hand).
--
-- Run (the lead runs it; crew agents never write the DB):
--   psql "$EXPLORE_DATABASE_URL" -v ON_ERROR_STOP=1 -f documentation/plans/chatbot/lean-index/explore-reasoning.sql
--
-- Idempotent (`IF NOT EXISTS`). Default `off` sends no reasoning effort, as today. To try an effort afterwards:
--   UPDATE system_settings SET chatbot_parser_reasoning_effort = 'low';   -- off | low; anything else reads as off
--   (widen only per the trigger at head/parser.py REASONING_EFFORTS)

\set ON_ERROR_STOP on

SELECT current_database() = 'sorento_explore1020' AS on_explore \gset
\if :on_explore
\else
  \echo 'refused: this file runs on sorento_explore1020 only'
  \quit
\endif

ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS chatbot_parser_reasoning_effort VARCHAR(16) NOT NULL DEFAULT 'off';

SELECT chatbot_parser_reasoning_effort FROM system_settings;
