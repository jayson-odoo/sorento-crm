"""The PDPA collection notice becomes data (fork 6, hard gate on S3).

`consumer_profiles.consent_notice_version` has existed since S2b and recorded a literal -
``2026-08-BM-EN-DRAFT`` - that pointed at no text anywhere. The column's whole job is to
answer "which wording did this person actually see", so until now it answered nothing.

This adds the table that stamp resolves into, and seeds v1 of the consumer intake notice in
Bahasa Malaysia and English (PDPA 2010 s.7(2)).

**Append-only by design.** A published row is never edited; correcting wording publishes a
new version. That is why the table has no `updated_at`: the column would advertise a
mutation that must not happen, and consent evidence that can be rewritten after the fact is
not evidence.

**The placeholder stamp is cleared, not translated into v1.** Any profile carrying
``2026-08-BM-EN-DRAFT`` was created by a staff-side path that showed nobody a notice, so
re-pointing it at v1 would assert that those people read wording that did not exist when
they were recorded. NULL is the honest value: we do not know what they saw, because nothing
was shown. Both environments hold zero such rows today, so this is a guard rather than a
repair.

Revision ID: 322_consent_notices
Revises: 321_sla_waiting_attribution
Create Date: 2026-08-03

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "322_consent_notices"
down_revision = "321_sla_waiting_attribution"
branch_labels = None
depends_on = None

_TABLE = "consent_notices"
_PLACEHOLDER = "2026-08-BM-EN-DRAFT"


def _inspector():
    return sa.inspect(op.get_bind())


def _tables() -> set:
    return set(_inspector().get_table_names())


def upgrade() -> None:
    tables = _tables()

    if _TABLE not in tables:
        op.create_table(
            _TABLE,
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("notice_key", sa.String(length=64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("purpose", sa.String(length=32), nullable=False),
            sa.Column("body_en", sa.Text(), nullable=False, server_default=""),
            sa.Column("body_ms", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            sa.Column("published_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("published_by", sa.String(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.UniqueConstraint("notice_key", "version", name="uq_consent_notices_key_version"),
            sa.CheckConstraint(
                "(is_published = false) OR (published_at IS NOT NULL)",
                name="ck_consent_notices_published_at",
            ),
        )
        op.create_index(
            "ix_consent_notices_key_published", _TABLE, ["notice_key", "is_published"]
        )

    # Seeded through the app-side seeder so the wording lives in exactly ONE place. A
    # migration restating the text would drift from the service that serves it, and the
    # drift would be invisible until somebody compared two long paragraphs by eye.
    from sqlalchemy.orm import Session

    from app.services.consent_notice_service import seed_consent_notices

    session = Session(bind=op.get_bind())
    try:
        seed_consent_notices(session)
        session.commit()
    finally:
        session.close()

    if "consumer_profiles" in tables:
        op.execute(
            sa.text(
                "UPDATE consumer_profiles SET consent_notice_version = NULL "
                "WHERE consent_notice_version = :placeholder"
            ).bindparams(placeholder=_PLACEHOLDER)
        )


def downgrade() -> None:
    if _TABLE in _tables():
        op.drop_index("ix_consent_notices_key_published", table_name=_TABLE)
        op.drop_table(_TABLE)
