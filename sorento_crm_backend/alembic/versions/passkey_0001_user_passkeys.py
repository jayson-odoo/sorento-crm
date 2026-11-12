"""user_passkeys table, users.passkey_enabled, user_sessions.auth_method accepts 'passkey'

PASSKEY-LOGIN (AC-04, AC-05, AC-06). Additive: one new table, one new column defaulting every
existing user to OFF, and the auth_method CHECK widened. `user_sessions` is read on every
request, so the widened CHECK is added NOT VALID (no scan under the lock) and then VALIDATEd
(a scan that only takes SHARE UPDATE EXCLUSIVE, so reads and writes carry on).

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
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS passkey_enabled")
    op.execute("DROP TABLE IF EXISTS user_passkeys")
