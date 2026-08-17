"""Merge the four concurrent heads after main took onboarding, spec
verification and brand-member routing while the flyer spec proposals
slice was in flight. No schema change.

Revision ID: 372_merge_flyer_specs_heads
"""

revision = "372_merge_flyer_specs_heads"
down_revision = (
    "369_merge_onboarding_tickets",
    "370_merge_tickets_spec_verif",
    "371_brand_member_routing",
    "370_flyer_spec_proposals",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
