-- Add source_entity_type and source_entity_id to conversation_sla_tracking
-- (Same as Alembic revision 032_sla_source_entity - run this if migration hasn't been applied)

ALTER TABLE conversation_sla_tracking
  ADD COLUMN IF NOT EXISTS source_entity_type VARCHAR(50) NULL,
  ADD COLUMN IF NOT EXISTS source_entity_id VARCHAR(100) NULL;

CREATE INDEX IF NOT EXISTS ix_conversation_sla_tracking_source_entity
  ON conversation_sla_tracking (source_entity_type, source_entity_id);
