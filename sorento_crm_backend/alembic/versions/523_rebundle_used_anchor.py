"""Backfill: move any companion row's `bundled_with_row_id` anchor off a USED host row.

SO314592 (prod, 21 Sep 2026): before `_is_host_row` (`project_order_inquiry_service.py`)
excluded `redirected_to_pool`, `derive_bundles` could anchor a companion on an already-USED
host row - measured live on 2 rows, 1 inquiry (SO314592 SRTWC8605-SC-RL). That fix stops
this happening going forward; this migration is the one-time catch-up for whatever an
earlier pass left anchored on a used row, via
`app/services/oi_bundle_used_anchor_backfill.py::rebundle_rows_anchored_on_used_hosts`.

Data-only, no schema change. Downgrade is a no-op: the rows this moves are exactly the
ones already reading a used row's own coverage as if it were theirs, and there is no
sensible "back" to a wrong anchor - the same reasoning `522_oi_cancelled_used_confirm.py`
downgrades on.

Revision ID: 523_rebundle_used_anch
Revises: 522_oi_cancelled_used_confirm
Create Date: 2026-09-21
"""
from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

from app.services.oi_bundle_used_anchor_backfill import rebundle_rows_anchored_on_used_hosts

revision = "523_rebundle_used_anch"
down_revision = "522_oi_cancelled_used_confirm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        moved = rebundle_rows_anchored_on_used_hosts(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print(f"523_rebundle_used_anch: re-anchored {moved} row(s) off a used host")


def downgrade() -> None:
    # No-op by design - see the module docstring.
    pass
