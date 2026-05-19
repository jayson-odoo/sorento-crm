"""Set promotions.description to the linked attachment's original_filename.

Picks one attachment per promotion using a deterministic priority:
  1. is_primary = TRUE
  2. lowest non-null sort_order
  3. earliest created_at
  4. lowest promotion_attachments.id (tiebreak)

Strips a trailing file extension (.pdf / .xlsx / .xls / .docx / .png / .jpg / .jpeg)
from the filename before assignment so the description reads as a label, not a
file path. Promotions with no linked attachment are left untouched.

Idempotent — only writes where the derived value differs from the current
description (per `feedback_backfill_idempotent`).

Revision ID: 208_promotion_description_from_attachment_filename
Revises: 207_orders_customer_id_backfill
Create Date: 2026-05-19
"""
from __future__ import annotations

from alembic import op


revision = "208_promotion_description_from_attachment_filename"
down_revision = "207_orders_customer_id_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                pa.promotion_id,
                a.original_filename,
                ROW_NUMBER() OVER (
                    PARTITION BY pa.promotion_id
                    ORDER BY
                        pa.is_primary DESC,
                        pa.sort_order NULLS LAST,
                        pa.created_at ASC,
                        pa.id ASC
                ) AS rn
            FROM promotion_attachments pa
            JOIN attachments a ON a.id = pa.attachment_id
            WHERE a.is_deleted = FALSE
              AND a.original_filename IS NOT NULL
              AND btrim(a.original_filename) <> ''
        ),
        chosen AS (
            SELECT
                promotion_id,
                regexp_replace(
                    original_filename,
                    '\\.(pdf|xlsx|xls|docx|doc|png|jpg|jpeg)$',
                    '',
                    'i'
                ) AS derived_description
            FROM ranked
            WHERE rn = 1
        )
        UPDATE promotions p
        SET description = c.derived_description
        FROM chosen c
        WHERE p.id = c.promotion_id
          AND p.description IS DISTINCT FROM c.derived_description;
        """
    )


def downgrade() -> None:
    # Non-reversible: the prior descriptions are not preserved anywhere. Leave
    # the populated descriptions in place — operators can re-author manually.
    pass
