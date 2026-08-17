"""Voice's own degraded model, and the notices the ledger has to remember.

Two columns, both from the Phase 3 review recorded in
`documentation/plans/ideation/PLAN-chatbot-media-endpoint.md` section 16.

**`system_settings.media_voice_degraded_model`** (section 16.1). Until now the
quota decision read `media_image_degraded_model` for BOTH modalities, and
migration 358 seeds that column - so every over-quota voice note was accepted at
the full standard model while the contact was told their accuracy had dropped.
The voice column ships NULL and is deliberately **not seeded**: the image tiers
were measured (section 14.1), voice was not, and a NULL degraded model means the
monthly quota is a hard refusal, which section 3.2 already specifies. That is
honest. Claiming a degradation that did not happen is the same failure as a
silent wrong answer wearing a warning label. Naming a cheaper transcription
model is an operator decision and a settings change, not a deploy.

**`contact_media_usage.notices`** (section 16.5). The customer-facing notices a
decision produced are now stored on the metered fact, because two transports
could not otherwise carry them: an idempotent replay returned an empty notice
list, so an n8n retry of a `denied_gate` reached the dealer with no message at
all, and `build_callback_body` hardcoded `notices: []`, which made the
one-shape-three-transports guarantee true only because nothing populated it.

No backfill. Existing ledger rows predate the column and their notices were
delivered on the original response; inventing text for them after the fact would
be fabricating a record of something that was never sent.

Revision ID: 359_media_voice_degraded
Revises: 358_media_image_model_tiers_seed
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "359_media_voice_degraded"
down_revision = "358_media_image_model_tiers_seed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("media_voice_degraded_model", sa.Text(), nullable=True),
    )
    op.add_column(
        "contact_media_usage",
        sa.Column("notices", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contact_media_usage", "notices")
    op.drop_column("system_settings", "media_voice_degraded_model")
