"""Product specifications fix round 2 (#1286, PR #1302 review B-1 and S-3).

Two data repairs, both idempotent:

1. ``product_spec_registry.derivation_rules`` becomes nullable, and NULL is the one
   marker for "this key reads with the shipped rules". Until now an empty list meant
   that, so removing a key's only rule (or saving an empty list) brought the shipped
   rules straight back and the product kept reading the removed value (review B-1).
   Every stored empty list meant "shipped" when it was written, so each one becomes
   NULL here, and from now on an empty list means "no rules".

2. ``brand`` is no longer a specification (spec_0001), so a customer or segment
   visibility policy that names it can never hide or show it again, and re-saving that
   policy is refused as "Unknown spec key: brand" (review S-3). Owner ruling assumed
   (fix round 2): the brand stays out of the registry and is always shown; it is taken
   out of every stored policy, and each policy changed is logged.

Revision ID: spec_0003_rules_null_brand_pol
Revises: spec_0002_rule_builders
Create Date: 2026-09-26
"""

from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

revision = "spec_0003_rules_null_brand_pol"
down_revision = "spec_0002_rule_builders"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _rules_null_is_shipped(bind) -> None:
    op.execute("ALTER TABLE product_spec_registry ALTER COLUMN derivation_rules DROP DEFAULT")
    op.execute("ALTER TABLE product_spec_registry ALTER COLUMN derivation_rules DROP NOT NULL")
    cleared = bind.execute(
        text(
            "UPDATE product_spec_registry SET derivation_rules = NULL"
            " WHERE derivation_rules = '[]'::jsonb RETURNING spec_key"
        )
    ).all()
    if cleared:
        logger.warning(
            "spec_0003: %s keys with no stored rules now read the shipped rules by NULL: %s",
            len(cleared),
            ", ".join(sorted(key for (key,) in cleared)),
        )


def _brand_out_of_visibility_policies(bind) -> None:
    changed = bind.execute(
        text(
            "UPDATE spec_visibility_policies"
            " SET spec_keys = array_remove(spec_keys, 'brand'),"
            " excluded_spec_keys = array_remove(excluded_spec_keys, 'brand')"
            " WHERE 'brand' = ANY(COALESCE(spec_keys, '{}'))"
            " OR 'brand' = ANY(COALESCE(excluded_spec_keys, '{}'))"
            " RETURNING id, contact_id, segment_code"
        )
    ).all()
    for policy_id, contact_id, segment_code in changed:
        logger.warning(
            "spec_0003: brand taken out of the visibility policy %s (contact %s, segment %s);"
            " the brand is not a specification and is always shown",
            policy_id,
            contact_id,
            segment_code,
        )


def upgrade() -> None:
    bind = op.get_bind()
    _rules_null_is_shipped(bind)
    _brand_out_of_visibility_policies(bind)


def downgrade() -> None:
    # The NULL marker folds back into the old empty list. A key someone emptied on
    # purpose reads the shipped rules again after a downgrade: the old schema has no way
    # to say "no rules". The brand is not put back into any policy.
    op.execute(
        "UPDATE product_spec_registry SET derivation_rules = '[]'::jsonb"
        " WHERE derivation_rules IS NULL"
    )
    op.execute(
        "ALTER TABLE product_spec_registry ALTER COLUMN derivation_rules SET DEFAULT '[]'::jsonb"
    )
    op.execute("ALTER TABLE product_spec_registry ALTER COLUMN derivation_rules SET NOT NULL")
