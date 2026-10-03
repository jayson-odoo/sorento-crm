"""user_sessions.auth_method accepts 'dev_login'

DEV-LOGIN-BYPASS (owner, 3 Oct 2026; crew answer Q1 (a)): a passwordless sign-in on a local
test copy records its own auth_method so a dev session stays distinguishable in audit and the
session list. Additive: the CHECK constraint is widened, no row changes.

Also the join revision for main's fork: CUSTOMER-GROUP (#1441, cust_group_0001) and
REGION-PACKING-LIST (#1439, rpl_0001_regions) both branched from picker_no_cap_0001 and merged
back to back, leaving main with two heads. Neither touches user_sessions.

Revision ID: dev_login_0001
Revises: cust_group_0001, rpl_0001_regions
"""
from __future__ import annotations

from alembic import op

revision = "dev_login_0001"
down_revision = ("cust_group_0001", "rpl_0001_regions")
branch_labels = None
depends_on = None

_OLD = "('password', 'phone_otp', 'portal_link', 'impersonation')"
_NEW = "('password', 'phone_otp', 'portal_link', 'impersonation', 'dev_login')"


def upgrade() -> None:
    op.execute("ALTER TABLE user_sessions DROP CONSTRAINT IF EXISTS ck_user_sessions_auth_method")
    op.execute(
        "ALTER TABLE user_sessions ADD CONSTRAINT ck_user_sessions_auth_method "
        f"CHECK (auth_method IN {_NEW})"
    )


def downgrade() -> None:
    # A dev session cannot satisfy the narrower check, so those rows go first.
    op.execute("DELETE FROM user_sessions WHERE auth_method = 'dev_login'")
    op.execute("ALTER TABLE user_sessions DROP CONSTRAINT IF EXISTS ck_user_sessions_auth_method")
    op.execute(
        "ALTER TABLE user_sessions ADD CONSTRAINT ck_user_sessions_auth_method "
        f"CHECK (auth_method IN {_OLD})"
    )
