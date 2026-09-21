"""Re-seed the spec registry vocabulary: "close couple" is a word for close_coupled

Hand pass 12 R8 (owner ruling, 21 Sep 2026, live turn 7c39e638 "Can you suggest close
couple wc available stock in p trap"). The `product_type` row shipped "close coupled",
"close-coupled", "two piece" and "coupled", so the phrase the customer actually typed
bound no product type at all and the set answer spanned every water closet with stock,
the wall-hung one included.

`seed_spec_registry` is the ONE place that vocabulary lives (`SPEC_REGISTRY_SEED`), and
it already repairs a seed-sourced row's synonyms in place while leaving a row a human
took ownership of (`source != "seed"`) alone. It has only ever been RUN by
`311m_spec_tables_uuid_id`, though, so a word added to the seed after that revision was
stamped could never reach an installed database - the same "the deploy must ship the
config" rule `chatbot_rearch_s12` was written for on the same day.

Idempotent by construction: the seed is a set-to-correct-value repair, so a second run
writes nothing. No downgrade body - removing a spelling the catalogue understands would
only make an installed database understand less, and the seed is the source of truth for
what it should say.

Measured blast radius (hand pass 12 Phase 3, on the 15 Sep 2026 prod-copy clone): this
run created 1 spec key and repaired 5 vocabularies. It is a whole-seeder re-run, not a
"close couple" spelling fix alone - `SPEC_REGISTRY_SEED` gained derivation rules across
13 commits since `311m_spec_tables_uuid_id` last ran it, and every one of them reaches an
installed database for the first time here, in the same pass as this ruling's own words.

Revision ID: spec_vocab_close_couple
Revises: chatbot_rearch_s12
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy.orm import Session

revision = "spec_vocab_close_couple"
down_revision = "chatbot_rearch_s12"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    from app.services.product_spec_registry import seed_spec_registry

    session = Session(bind=op.get_bind())
    try:
        result = seed_spec_registry(session)
        session.commit()
        logger.info(
            "spec registry re-seeded: %s created, %s vocabulary repairs",
            result["created"],
            result["updated"],
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Nothing to undo: see the docstring."""
