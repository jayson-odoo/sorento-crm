"""user_passkeys table, users.passkey_enabled, portal_otp_codes.purpose, 'passkey' sessions

PASSKEY-LOGIN (AC-04, AC-05, AC-06, AC-27). Additive: one new table, a column defaulting every
existing user to OFF, a column marking every existing OTP code as a sign-in code, and the
auth_method CHECK widened.

Alembic runs this revision in one transaction, so adding the CHECK NOT VALID and then
VALIDATEing it holds the ACCESS EXCLUSIVE lock from the ADD until COMMIT either way: it buys no
lock benefit here and is kept only as the standard spelling. The cost is the VALIDATE scan of
`user_sessions`, measured at 58 ms on 500k rows (PLAN-passkey-login-12nov.md).

Revision ID: passkey_0001_user_passkeys
Revises: il_0002_integration_log_search
"""
from __future__ import annotations

from alembic import op

revision = "passkey_0001_user_passkeys"
down_revision = "il_0002_integration_log_search"
branch_labels = None
depends_on = None

_OLD = "('password', 'phone_otp', 'portal_link', 'impersonation', 'dev_login')"
_NEW = "('password', 'phone_otp', 'portal_link', 'impersonation', 'dev_login', 'passkey')"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_passkeys (
            id UUID PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            credential_id TEXT NOT NULL,
            public_key BYTEA NOT NULL,
            sign_count BIGINT NOT NULL DEFAULT 0,
            transports JSON,
            aaguid VARCHAR,
            backed_up BOOLEAN NOT NULL DEFAULT false,
            name VARCHAR(100) NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            last_used_at TIMESTAMP WITHOUT TIME ZONE,
            CONSTRAINT user_passkeys_credential_id_key UNIQUE (credential_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_passkeys_user_id ON user_passkeys (user_id)")
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS passkey_enabled BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE portal_otp_codes ADD COLUMN IF NOT EXISTS purpose VARCHAR(20) NOT NULL "
        "DEFAULT 'sign_in'"
    )
    op.execute("ALTER TABLE user_sessions DROP CONSTRAINT IF EXISTS ck_user_sessions_auth_method")
    op.execute(
        "ALTER TABLE user_sessions ADD CONSTRAINT ck_user_sessions_auth_method "
        f"CHECK (auth_method IN {_NEW}) NOT VALID"
    )
    op.execute("ALTER TABLE user_sessions VALIDATE CONSTRAINT ck_user_sessions_auth_method")


def downgrade() -> None:
    # A passkey session cannot satisfy the narrower check, so those rows go first.
    op.execute("DELETE FROM user_sessions WHERE auth_method = 'passkey'")
    op.execute("ALTER TABLE user_sessions DROP CONSTRAINT IF EXISTS ck_user_sessions_auth_method")
    op.execute(
        "ALTER TABLE user_sessions ADD CONSTRAINT ck_user_sessions_auth_method "
        f"CHECK (auth_method IN {_OLD}) NOT VALID"
    )
    op.execute("ALTER TABLE user_sessions VALIDATE CONSTRAINT ck_user_sessions_auth_method")
    # A re-check code is never a sign-in code; with the column gone it would read as one.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'portal_otp_codes' AND column_name = 'purpose'
            ) THEN
                DELETE FROM portal_otp_codes WHERE purpose = 'reauth';
            END IF;
        END $$
        """
    )
    op.execute("ALTER TABLE portal_otp_codes DROP COLUMN IF EXISTS purpose")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS passkey_enabled")
    op.execute("DROP TABLE IF EXISTS user_passkeys")
