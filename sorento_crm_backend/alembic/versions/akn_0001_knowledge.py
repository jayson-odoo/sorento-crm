"""AGENTIC-KNOWLEDGE P1: which attachment types the AI may read, and each file's read status

Revision ID: akn_0001_knowledge
Revises: agp2_0001_router
Create Date: 2026-10-31 00:00:00.000000

Additive and idempotent. `attachment_types.ai_audience` (off / staff / dealer / public, default off, so
no existing type becomes readable) and `ai_escalate_team_id` (the team a question the documents do not
answer is referred to). `attachments.ai_read_*` records what the read job did with the file. The
knowledge chunks themselves live in the existing embedding tables (source_type `knowledge`).
"""
from alembic import op

revision = "akn_0001_knowledge"
down_revision = "agp2_0001_router"
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    "ALTER TABLE attachment_types ADD COLUMN IF NOT EXISTS ai_audience VARCHAR(16) NOT NULL DEFAULT 'off'",
    "ALTER TABLE attachment_types ADD COLUMN IF NOT EXISTS ai_escalate_team_id UUID NULL "
    "REFERENCES teams(id) ON DELETE SET NULL",
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_attachment_types_ai_audience') THEN
            ALTER TABLE attachment_types ADD CONSTRAINT ck_attachment_types_ai_audience
                CHECK (ai_audience IN ('off', 'staff', 'dealer', 'public'));
        END IF;
    END $$
    """,
    "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS ai_read_status VARCHAR(16) NULL",
    "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS ai_read_pages INTEGER NULL",
    "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS ai_read_ocr_pages INTEGER NULL",
    "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS ai_read_cost_usd NUMERIC(10, 4) NULL",
    "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS ai_read_error TEXT NULL",
    "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS ai_read_at TIMESTAMP NULL",
)


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade() -> None:
    for column in ("ai_read_at", "ai_read_error", "ai_read_cost_usd", "ai_read_ocr_pages", "ai_read_pages", "ai_read_status"):
        op.execute(f"ALTER TABLE attachments DROP COLUMN IF EXISTS {column}")
    op.execute("ALTER TABLE attachment_types DROP CONSTRAINT IF EXISTS ck_attachment_types_ai_audience")
    op.execute("ALTER TABLE attachment_types DROP COLUMN IF EXISTS ai_escalate_team_id")
    op.execute("ALTER TABLE attachment_types DROP COLUMN IF EXISTS ai_audience")
