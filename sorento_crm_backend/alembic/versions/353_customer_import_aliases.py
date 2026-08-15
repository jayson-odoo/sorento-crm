"""Seed the `customer` import doc type's header aliases.

The customer importer resolves its columns through `import_field_alias` like every other
importer, so an empty alias set means the first upload reports every column unmapped and
the file looks broken. The five existing doc types each ship 10 to 31 rows; this ships the
customer one rather than leaving an admin to discover the requirement (UAC AC-4.2).

Most spellings are the AutoCount debtor-maintenance vocabulary most likely to appear plus
the obvious English variants; two (`Code`, `Phone 1`) were added after a real 4,196-row
debtor export was read on 2026-08-13. When an export arrives spelled differently the fix is
alias rows, not a release (AC-4.1) - that is the whole point of resolving through the table.

Three things deliberately absent:

* **`company_id` has no alias.** It comes from the job's company scope and must never be
  readable from a file column (AC-1.3); an alias for it would be a way to write a customer
  into another company's book from a spreadsheet.
* **No bare `Name` alias.** A one-word `Name` is ambiguous between the debtor name and the
  registered name, and the resolver's first-alias-wins rule would make which one it meant
  depend on insert order. Bare `Code` is NOT ambiguous in a debtor listing and is what the
  real export actually heads its key column, so it is seeded.
* **`customer_type` has no alias.** A real AutoCount listing's `Debtor Type` column carries
  Trade / Cash / Local, which the app does not recognise, and all 3,284 live rows read
  `company`. Mapping it would fill the discriminator the app branches on with another
  system's vocabulary. The field stays insert-only in the service, so a client who really
  does export our own values can be given an alias row deliberately (UAC decision D1).

Revision ID: 353_customer_import_aliases
Revises: 6f86dd016850
"""
import sqlalchemy as sa
from alembic import op

revision = "353_customer_import_aliases"
down_revision = "6f86dd016850"
branch_labels = None
depends_on = None


DOC_TYPE = "customer"

#: (field, alias). Locale left NULL: English headers on an AutoCount export.
_ALIASES = (
    # --- the two required columns, which are together the upsert key ----------
    # AutoCount's own Debtor export heads this column plain "Code", verified against a real
    # 4,196-row export on 2026-08-13. Without it the file cannot be read at all.
    ("customer_code", "Code"),
    ("customer_code", "Debtor Code"),
    ("customer_code", "DebtorCode"),
    ("customer_code", "Customer Code"),
    ("customer_code", "Account No"),
    ("customer_code", "Account No."),
    ("customer_code", "A/C Code"),
    ("customer_code", "AC Code"),
    ("customer_code", "Debtor A/C"),
    ("customer_code", "Debtor No"),
    ("customer_name", "Debtor Name"),
    ("customer_name", "DebtorName"),
    ("customer_name", "Customer Name"),
    ("customer_name", "Company Name"),
    ("customer_name", "Account Name"),
    # --- contact ---------------------------------------------------------------
    ("email", "Email"),
    ("email", "E-mail"),
    ("email", "Email Address"),
    ("email", "Email 1"),
    ("phone_number", "Phone"),
    # Same real export: AutoCount numbers its phone columns.
    ("phone_number", "Phone 1"),
    ("phone_number", "Phone No"),
    ("phone_number", "Phone No."),
    ("phone_number", "Tel"),
    ("phone_number", "Tel No"),
    ("phone_number", "Telephone"),
    ("phone_number", "Office Phone"),
    ("mobile_number", "Mobile"),
    ("mobile_number", "Mobile No"),
    ("mobile_number", "Mobile No."),
    ("mobile_number", "H/P"),
    ("mobile_number", "HP No"),
    ("mobile_number", "Handphone"),
    # --- legal identity --------------------------------------------------------
    ("registered_name", "Registered Name"),
    ("registered_name", "Legal Name"),
    ("registered_name", "Company Registered Name"),
    ("trading_name", "Trading Name"),
    ("trading_name", "Trade Name"),
    ("trading_name", "Business Name"),
    ("registration_number", "Registration No"),
    ("registration_number", "Registration No."),
    ("registration_number", "Company Reg No"),
    ("registration_number", "Reg No"),
    ("registration_number", "ROC No"),
    ("registration_number", "SSM No"),
    ("tax_id", "Tax ID"),
    ("tax_id", "Tax No"),
    ("tax_id", "GST No"),
    ("tax_id", "SST No"),
    ("tax_id", "TIN"),
    # --- profile ---------------------------------------------------------------
    ("industry", "Industry"),
    ("industry", "Nature of Business"),
    ("website", "Website"),
    ("website", "Web Site"),
    ("website", "URL"),
    ("country", "Country"),
    ("salutation", "Salutation"),
    ("salutation", "Title"),
    ("first_name", "First Name"),
    ("first_name", "Given Name"),
    ("last_name", "Last Name"),
    ("last_name", "Surname"),
    # Fill-if-empty only (AC-3): it decides SCM demand class, so a curated value is
    # never overwritten by a file.
    ("market_segment_code", "Market Segment"),
    ("market_segment_code", "Segment"),
    ("market_segment_code", "Segment Code"),
)


def _rows():
    """The seed, as tuples. Importable so `scripts/bootstrap_env` can replay it on a
    create_all database, which never runs a migration body."""
    return list(_ALIASES)


def seed(bind) -> int:
    """Insert the aliases. Idempotent through the table's own unique constraint, so a
    re-run on an already-seeded database is a no-op."""
    inserted = 0
    for field, alias in _ALIASES:
        res = bind.execute(
            sa.text(
                """
                INSERT INTO import_field_alias (doc_type, field, alias, locale)
                VALUES (:d, :f, :a, NULL)
                ON CONFLICT (doc_type, field, alias) DO NOTHING
                """
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )
        inserted += res.rowcount or 0
    return inserted


#: Spellings an earlier draft of THIS revision seeded and the ruling then removed (D1).
#: Deleted on upgrade so a database that ran that draft converges rather than keeping a
#: mapping the shipped file no longer has. Not in `seed()`: bootstrap replays that on every
#: run, and an admin who deliberately adds a `customer_type` alias must keep it.
_WITHDRAWN = ("Customer Type", "Debtor Type")


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM import_field_alias "
            "WHERE doc_type = :d AND field = 'customer_type' AND alias = ANY(:aliases)"
        ),
        {"d": DOC_TYPE, "aliases": list(_WITHDRAWN)},
    )
    seed(bind)


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM import_field_alias WHERE doc_type = :d").bindparams(
        d=DOC_TYPE
    ))
