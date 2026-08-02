"""After-sales S1: who a contact is, which Dealer a Complaint is for, and where the
Site actually is.

Two nullable bindings on `respond_contacts` replace a door question the portal would
otherwise have to ask; the Complaint gets a real Dealer FK, a real Site and a
reporter role; and the sales-agent code stops being an unmappable string. None of it
is user-visible in this slice, which is exactly why it needs to be right: every later
slice reads these four answers and none of them can see whether the answer is wrong.

**Two bindings, not three.** The plan's schema block says
`technician_id uuid REFERENCES technicians(id)`. `technicians` does not exist - not in
`app/models/`, not in any revision - and S6 (AC-F6) is the slice that creates it, so
Postgres could not create the constraint here at all. AC-B13 defers it. A stub table
would hand S6 a half-defined core entity to migrate, which is worse than an absent
one, and a nullable FK added later is cheap and purely additive. The derivation
already reads the third binding defensively, so S6 is this column and nothing else.

**`respond_contacts.user_id` is VARCHAR, not uuid.** `users.id` is `Column(String)`
and stays that way until the uuid-id PR stack converts it; a uuid column cannot
foreign-key a text one. Every other binding added here IS a uuid, so matching the
neighbours is the natural instinct and it is the thing that fails - as a hard DDL
error in production and as a silent type mismatch in any fixture that only writes
uuids. Same boundary AC-A2 records.

**`latitude` / `longitude` are `numeric(10,7)`, never float or text** (AC-B21). The
pin is what a technician navigates to. Float does not round-trip a coordinate copied
between systems, and text cannot be bounded-box queried. Scale 7 is about a
centimetre; five decimals is about a metre and four is a street. Precision 10 leaves
three integer digits, which covers longitude to 180. `site_maps_url` from the plan's
schema block is deliberately NOT created: AC-M37 replaced it with the pin plus the
typed address before it was ever written, and creating it would mean shipping a
column that has to be dropped plus an argument about whether it survives.

**`reported_by_role` is ADDED, and the backfill is in this migration.** Not a rename:
renaming a live column makes the migration irreversible mid-release and buys nothing,
while `customer_type` / `customer_name` / `salesperson` are kept read-only for one
release and dropped later. And not a follow-up script, because a data step outside
the migration is a step that gets skipped on one environment, after which the column
is populated in production and NULL in staging for reasons nobody can reconstruct.

**Blanks and account categories backfill to NULL, never to a role.** The plan says
"the 7 blanks become `cs`" and is wrong twice. Counted against the live table (47
rows): `Project` 24, `SMC` 7, `Salesperson` 5, `Dealer` 4, NULL 3, `End User` 3,
`E Commerce` 1. So the 7 was the `SMC` count, not the blank count, and mapping an
unknown value to `cs` asserts Customer Service reported those complaints, which
nothing supports. 32 of the 47 rows therefore stay NULL, and that is the honest
answer: a guess cannot be told from a fact afterwards (AC-B16).

`Salesperson` is in the map even though it is absent from the configured
`complaints_customer_type` lookup options (Dealer / Project / SMC / E Commerce / End
User). A mapping derived from the option list alone silently misses 5 live rows
(AC-B17).

The mapping below is a FROZEN SNAPSHOT of the DEPRECATED block at the bottom of
`app/services/party_service.py`, not an import of it. That block is scheduled for
deletion when the legacy column is dropped, and a migration that imports code which
is scheduled for deletion breaks
the next time somebody rebuilds a database from scratch. Change one, change the
other, in the same commit.

**`salesman_code_users` exists because the map has nowhere else to live** (AC-B18).
AC-B11 says the codes map "as configured" and never says configured where. `users`
has no code column, and one person carries four codes (`SEAN` / `SEAN I` /
`SEAN III` / `SEAN IV`), so a column could not hold them. Deliberately not
company-partitioned: every suffix appears under BOTH Sorento and Mocha in `orders`,
so the suffix is not a company split and one global vocabulary is correct.

**What stays broken after this migration.** `customer_type`, `customer_name` and
`complaints.salesperson` are still read by nine modules (the frozen inventory in
`tests/test_after_sales_legacy_column_guard.py` is the drop worklist), so the columns
cannot go yet and AC-B6a as written is unsatisfiable in this slice.
`customers.account_owner_user_id` is still 0 of 3,284 populated: this migration only
creates the map table, and `scripts/seed_customer_account_owner.py` has to be run
against real data (dry run first) before salesperson resolution answers anything.
`complaints.customer_id` is NULL on every existing row: no attempt is made to derive
a Dealer from the free-text `customer_name`, because a fuzzy backfill onto a party
FK is the mis-routing this slice exists to prevent.

Every idempotency guard here is load-bearing: the shared dev database is stamped on
another worktree's chain, so these columns get applied by hand there and a plain
`add_column` would abort the whole upgrade.

Revision ID: 316_after_sales_parties
Revises: 315_wf_submission_attachments
Create Date: 2026-08-02

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "316_after_sales_parties"
down_revision = "315_wf_submission_attachments"
branch_labels = None
depends_on = None

_CONTACTS = "respond_contacts"
_COMPLAINTS = "complaints"
_CODE_MAP = "salesman_code_users"

# Normalized legacy value -> reported_by_role. Frozen snapshot of the DEPRECATED
# block in app/services/party_service.py; anything absent stays NULL by design.
_ROLE_BACKFILL = (
    ("dealer", "dealer"),
    ("end user", "end_user"),
    ("enduser", "end_user"),
    ("salesperson", "salesperson"),
    ("sales person", "salesperson"),
    ("cs", "cs"),
    ("customer service", "cs"),
    ("technician", "technician"),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set:
    return {c["name"] for c in _inspector().get_columns(table)}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _create_fk_if_missing(name: str, source: str, target: str, columns: list, refs: list) -> None:
    if name not in {fk.get("name") for fk in _inspector().get_foreign_keys(source)}:
        op.create_foreign_key(name, source, target, columns, refs, ondelete="SET NULL")


def _create_index_if_missing(name: str, table: str, columns: list) -> None:
    if name not in {ix["name"] for ix in _inspector().get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    # --- respond_contacts: the two bindings S1 ships (AC-B1 as corrected by AC-B13)
    _add_column_if_missing(_CONTACTS, sa.Column("customer_id", UUID(as_uuid=False), nullable=True))
    _add_column_if_missing(_CONTACTS, sa.Column("user_id", sa.String(), nullable=True))
    _create_fk_if_missing(
        "fk_respond_contacts_customer_id", _CONTACTS, "customers", ["customer_id"], ["id"]
    )
    _create_fk_if_missing("fk_respond_contacts_user_id", _CONTACTS, "users", ["user_id"], ["id"])
    _create_index_if_missing("ix_respond_contacts_customer_id", _CONTACTS, ["customer_id"])
    _create_index_if_missing("ix_respond_contacts_user_id", _CONTACTS, ["user_id"])

    # --- complaints: the Dealer, the Site, the reporter role
    _add_column_if_missing(_COMPLAINTS, sa.Column("customer_id", UUID(as_uuid=False), nullable=True))
    _add_column_if_missing(_COMPLAINTS, sa.Column("site_address", sa.Text(), nullable=True))
    _add_column_if_missing(_COMPLAINTS, sa.Column("site_contact_name", sa.Text(), nullable=True))
    _add_column_if_missing(_COMPLAINTS, sa.Column("site_contact_phone", sa.Text(), nullable=True))
    _add_column_if_missing(_COMPLAINTS, sa.Column("latitude", sa.Numeric(10, 7), nullable=True))
    _add_column_if_missing(_COMPLAINTS, sa.Column("longitude", sa.Numeric(10, 7), nullable=True))
    _add_column_if_missing(_COMPLAINTS, sa.Column("place_id", sa.String(length=128), nullable=True))
    _add_column_if_missing(
        _COMPLAINTS, sa.Column("reported_by_role", sa.String(length=20), nullable=True)
    )
    _create_fk_if_missing(
        "fk_complaints_customer_id", _COMPLAINTS, "customers", ["customer_id"], ["id"]
    )
    _create_index_if_missing("ix_complaints_customer_id", _COMPLAINTS, ["customer_id"])

    # --- the reported_by_role backfill (AC-B6, AC-B16, AC-B17)
    # Case, whitespace and separator tolerant, because the source is free text: the
    # same normalization the runtime shim applies. Guarded on IS NULL so a re-run is
    # a no-op and a value corrected by hand afterwards is never overwritten.
    values = ", ".join(f"('{legacy}', '{role}')" for legacy, role in _ROLE_BACKFILL)
    op.execute(
        sa.text(
            rf"""
            UPDATE {_COMPLAINTS} AS c
               SET reported_by_role = m.role
              FROM (VALUES {values}) AS m(legacy, role)
             WHERE c.reported_by_role IS NULL
               AND btrim(
                     regexp_replace(
                       lower(coalesce(c.customer_type, '')), '[\s_-]+', ' ', 'g'
                     )
                   ) = m.legacy
            """
        )
    )

    # --- the persisted sales-agent code map (AC-B18)
    if _CODE_MAP not in _inspector().get_table_names():
        op.create_table(
            _CODE_MAP,
            sa.Column(
                "id",
                UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("salesman_code", sa.String(length=100), nullable=False),
            # varchar, for the same reason respond_contacts.user_id is.
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("salesman_code", name="uq_salesman_code_users_code"),
        )
    _create_index_if_missing("ix_salesman_code_users_user_id", _CODE_MAP, ["user_id"])


def downgrade() -> None:
    # The backfill is not undone: reported_by_role goes with the column it lives on.
    if _CODE_MAP in _inspector().get_table_names():
        op.drop_table(_CODE_MAP)

    for name, table in (
        ("ix_complaints_customer_id", _COMPLAINTS),
        ("ix_respond_contacts_user_id", _CONTACTS),
        ("ix_respond_contacts_customer_id", _CONTACTS),
    ):
        if name in {ix["name"] for ix in _inspector().get_indexes(table)}:
            op.drop_index(name, table_name=table)

    for name, table in (
        ("fk_complaints_customer_id", _COMPLAINTS),
        ("fk_respond_contacts_user_id", _CONTACTS),
        ("fk_respond_contacts_customer_id", _CONTACTS),
    ):
        if name in {fk.get("name") for fk in _inspector().get_foreign_keys(table)}:
            op.drop_constraint(name, table, type_="foreignkey")

    for table, columns in (
        (
            _COMPLAINTS,
            (
                "reported_by_role",
                "place_id",
                "longitude",
                "latitude",
                "site_contact_phone",
                "site_contact_name",
                "site_address",
                "customer_id",
            ),
        ),
        (_CONTACTS, ("user_id", "customer_id")),
    ):
        present = _columns(table)
        for column in columns:
            if column in present:
                op.drop_column(table, column)
