"""S5 - where a WhatsApp burst leaves its fingerprint.

Two columns on `complaints`, and the first one is the whole point.

`intake_burst_key` is the idempotency key n8n retries against (AC-C0d). It carries a
**UNIQUE index**, not just a lookup: the first draft resolved the key with a
`remarks_internal ILIKE '%[intake:...]%'` scan, which is wrong twice over. It is an
unindexed sequential scan of every complaint, and lookup-then-insert loses a race - two
n8n retries arriving together both find nothing and both insert, producing exactly the
second Complaint the key exists to prevent. A unique index makes the database refuse the
duplicate instead of the application hoping to notice it. Same reasoning as the
conversation-SLA singleton index (migration 180).

Partial (`WHERE intake_burst_key IS NOT NULL`), because every complaint created by CS, the
portal or a form has no burst key and they must not collide with each other on NULL.

`intake_transcript` holds the burst verbatim, in the order it was sent. It is what a human
reads when the extraction is wrong, and the ORDER is itself evidence: photos arriving before
the words that explain them is the ordinary shape of a real report (AC-C3), and a store that
normalised the sequence away would hide it. Kept separate from `defect_description`, which
holds what the extractor MADE of the burst - conflating the two loses the ability to tell a
bad extraction from a badly-worded message.

Revision ID: 324_complaint_intake_burst
Revises: 323_complaint_line_claim
"""
from alembic import op
import sqlalchemy as sa

revision = "324_complaint_intake_burst"
down_revision = "323_complaint_line_claim"
branch_labels = None
depends_on = None

TABLE = "complaints"
INDEX = "uq_complaints_intake_burst_key"


def _columns(bind) -> set:
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
            ),
            {"t": TABLE},
        )
    }


def upgrade() -> None:
    bind = op.get_bind()
    held = _columns(bind)

    if "intake_burst_key" not in held:
        op.add_column(TABLE, sa.Column("intake_burst_key", sa.String(120), nullable=True))
    if "intake_transcript" not in held:
        op.add_column(TABLE, sa.Column("intake_transcript", sa.Text(), nullable=True))

    # The constraint that makes a retry safe. Created unconditionally-but-guarded so a
    # shared dev database that already holds the columns still gets the index.
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {INDEX}
            ON {TABLE} (intake_burst_key)
            WHERE intake_burst_key IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text(f"DROP INDEX IF EXISTS {INDEX}"))
    held = _columns(bind)
    for name in ("intake_transcript", "intake_burst_key"):
        if name in held:
            op.drop_column(TABLE, name)
