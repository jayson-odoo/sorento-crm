"""Strip secrets already written into audit_logs (issue #1281).

`users` was audited with no column filter, so every user write, logins included,
copied the bcrypt `password` hash into `old_values` / `new_values`; the same held
for `project_quotation_issues.sign_token`, a bearer link token. The listener no
longer writes them (`app.models.audit.AUDIT_SECRET_KEYS`); this removes the copies
already stored. Keys only: the rest of each row, the audit record, stays intact.
Top-level keys only: the listener now also strips nested ones, but no audited model
stored a secret inside a JSON value, so there are no nested copies to remove.

Deploy window: each of the two UPDATEs is a full sequential scan of `audit_logs`
inside the deploy transaction, because no index covers `?|`. That is acceptable at
the table's size when this was written; on a much larger table, check the row count
(`SELECT count(*) FROM audit_logs`) before deploying and expect the scan to hold
row locks on the matching rows until the transaction commits.

Downgrade is a no-op on purpose: a stripped hash cannot, and must not, come back.

Revision ID: 527_audit_logs_scrub_secrets
Revises: sales_0002_team_leader
"""
from alembic import op

revision = "527_audit_logs_scrub_secrets"
down_revision = "sales_0002_team_leader"
branch_labels = None
depends_on = None

# Same set as app.models.audit.AUDIT_SECRET_KEYS, frozen here so the
# migration keeps meaning what it meant when it ran.
SECRET_KEYS = (
    "password",
    "password_hash",
    "hashed_password",
    "sign_token",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "key_hash",
    "secret",
    "client_secret",
)


def upgrade() -> None:
    keys = "ARRAY[" + ", ".join(f"'{k}'" for k in SECRET_KEYS) + "]::text[]"
    for column in ("old_values", "new_values"):
        op.execute(
            f"UPDATE audit_logs SET {column} = {column} - {keys} "
            f"WHERE jsonb_typeof({column}) = 'object' AND {column} ?| {keys}"
        )


def downgrade() -> None:
    pass
