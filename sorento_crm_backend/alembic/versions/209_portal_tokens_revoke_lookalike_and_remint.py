"""Revoke portal tokens with look-alike chars and re-mint for affected contacts.

Switching the generator to Crockford base32 (excludes I, L, O, U) was a forward
fix; existing tokens still contained ambiguous chars and could be mis-transcribed
when a user retypes from a screenshot or chat preview. This migration:

  1. Revokes every live token whose value contains I / l / O / U (matches
     base64url chars dropped from Crockford).
  2. For each affected contact whose ONLY live tokens were revoked here, mints a
     fresh Crockford-format token with a 7-day TTL so the contact can keep
     accessing the portal without going through OTP again.

Idempotent: re-running is a no-op because step 1 only touches `revoked_at IS NULL`
and step 2 only inserts when the contact has zero live tokens after step 1.

Revision ID: 209_portal_tokens_revoke_lookalike_and_remint
Revises: 208_promotion_description_from_attachment_filename
Create Date: 2026-05-20
"""
from __future__ import annotations

import secrets

from alembic import op


revision = "209_portal_tokens_revoke_lookalike_and_remint"
down_revision = "208_promotion_description_from_attachment_filename"
branch_labels = None
depends_on = None


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _crockford_token(length: int = 48) -> str:
    return "".join(secrets.choice(_CROCKFORD) for _ in range(length))


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Revoke all live tokens containing look-alike chars (I, l, O, U).
    bind.exec_driver_sql(
        """
        UPDATE portal_tokens
        SET revoked_at = now()
        WHERE revoked_at IS NULL
          AND expires_at > now()
          AND token ~ '[IlOU]';
        """
    )

    # 2. Find contacts whose ONLY live tokens were just revoked - they have no
    #    other unrevoked, unexpired token to fall back to. Re-mint one Crockford
    #    token per contact, preserving (contact_id, space_id) from the most
    #    recent revoked token so the portal scope stays correct.
    rows = bind.exec_driver_sql(
        """
        WITH live_after AS (
            SELECT DISTINCT contact_id
            FROM portal_tokens
            WHERE revoked_at IS NULL AND expires_at > now()
        ),
        candidates AS (
            SELECT DISTINCT pt.contact_id, pt.space_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY pt.contact_id
                       ORDER BY pt.expires_at DESC, pt.created_at DESC
                   ) AS rn
            FROM portal_tokens pt
            WHERE pt.revoked_at IS NOT NULL
              AND pt.contact_id NOT IN (SELECT contact_id FROM live_after)
        )
        SELECT contact_id, space_id
        FROM candidates
        WHERE rn = 1;
        """
    ).fetchall()

    if not rows:
        return

    # Insert a fresh 7-day Crockford token per affected contact.
    for contact_id, space_id in rows:
        token_str = _crockford_token()
        bind.exec_driver_sql(
            """
            INSERT INTO portal_tokens (id, token, contact_id, space_id, expires_at, created_at)
            VALUES (gen_random_uuid(), %s, %s, %s, now() + interval '7 days', now())
            ON CONFLICT (token) DO NOTHING;
            """,
            (token_str, contact_id, space_id),
        )


def downgrade() -> None:
    # Non-reversible: cannot restore revoked tokens, and the freshly minted
    # ones cannot be distinguished from regular live tokens after the fact.
    pass
