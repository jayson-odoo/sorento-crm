"""Seed the two image model tiers on the system_settings singleton.

Migration 356 shipped `media_image_provider`, `media_image_model` and
`media_image_degraded_model` as NULL, because at that point nobody had measured
which model belonged in which tier and defaulting a paid model on a guess is
worse than shipping nothing. The corpus measurement in
`documentation/plans/ideation/PLAN-chatbot-media-endpoint.md` section 14.1
settled it, so the values are now seeded:

* `media_image_provider` = `openai`, `media_image_model` = `gpt-4o` - the
  standard tier.
* `media_image_degraded_model` = `gpt-4o-mini` - the degraded tier.

The evidence, so this is stated rather than asserted. On the same image, same
prompt, temperature 0, N=5 per arm: `gpt-4o-mini` failed to flag a
handwritten-over-printed quantity amendment in **0 of 5** runs and misread the
printed value (`16` for `6`) identically in **20 of 20** calls across every arm
it ran in. `gpt-4o`, on the unchanged prompt, flagged the amendment **5 of 5**,
read the value correctly, ran faster (mean 6.5s versus 9.7s) and used roughly
13x fewer prompt tokens on the same image (2,963 versus 38,437), because the two
models tokenize an image differently.

That makes the degraded tier genuinely and *measurably* worse, in exactly the way
the customer-facing degradation notice warns about: at that tier the model does
not fail visibly, it hands back a confident wrong number. Seeding both means
hitting the monthly quota degrades out of the box rather than being a hard
refusal, which is what UAC S2-06 asks for.

**Seeded here rather than as a Python-side column default, deliberately.** A
column carrying a default is one an operator can never clear back to NULL:
SQLAlchemy cannot distinguish "set this column to None" from "did not mention
this column", so the default would silently reassert itself. A one-time seed
gives the shipped value while leaving the field editable *and* clearable - a
NULL `media_image_degraded_model` still means "no degraded tier, refuse at the
quota", and that remains reachable.

Idempotent in the house style: each column is set only WHERE it is currently
NULL, so re-running is safe and an operator who has already named their own
model is never overwritten.

Revision ID: 358_media_image_model_tiers_seed
Revises: 357_chatbot_media_permissions
"""
import sqlalchemy as sa
from alembic import op

revision = "358_media_image_model_tiers_seed"
down_revision = "357_chatbot_media_permissions"
branch_labels = None
depends_on = None


# (column, seeded value). Section 14.1 of the plan is the measurement behind each.
_SEEDS = (
    ("media_image_provider", "openai"),
    ("media_image_model", "gpt-4o"),
    ("media_image_degraded_model", "gpt-4o-mini"),
)


def upgrade() -> None:
    bind = op.get_bind()
    for column, value in _SEEDS:
        bind.execute(
            sa.text(
                f"UPDATE system_settings SET {column} = :value "
                f"WHERE {column} IS NULL"
            ),
            {"value": value},
        )


def downgrade() -> None:
    # Clear only the values this migration would have written. An operator who
    # has since chosen their own model keeps it - a downgrade is not a licence
    # to discard configuration.
    bind = op.get_bind()
    for column, value in _SEEDS:
        bind.execute(
            sa.text(
                f"UPDATE system_settings SET {column} = NULL WHERE {column} = :value"
            ),
            {"value": value},
        )
