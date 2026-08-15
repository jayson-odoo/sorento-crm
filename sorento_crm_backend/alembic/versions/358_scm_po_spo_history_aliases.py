"""The 27 columns of the captain's PO + SPO history export resolve (UAC AC-1.2).

Deferred from S2 with a reason: the header row of `PO & SPO 2023.xlsx` was recorded nowhere
this repository could read, and seeding invented spellings would have produced alias rows
that match nothing while reading as done. The file was measured on 2026-08-14 and its header
row is reproduced verbatim below, in file order.

They split three ways, and the split is the point.

**Nine are read.** `Item Code`, `Qty`, `Doc No`, `Doc Date`, `Delivery Date`, `Location`,
`Description`, `Creditor Name` and `FromSODocList` are what the purchase-history write path
consumes. The last one is the only place in either export where the SO<->PO pairing is
stated per LINE - the banded report carries an order-level `**SO:174830**` note that cannot
say which line it describes - so it becomes a claim that names the item.

**Two are read by the outstanding channel and deliberately NOT by this one.**
`Transfered Qty` and `Remaining Qty` are what tells an outstanding book what is still to
come. This is history: every line is written closed and fully received whatever those two
columns say, so reading them could only produce an open line, which is the one thing this
channel must never write (ADR 337).

**The rest are resolved and not read.** They are aliased to fields nothing consumes, which
is the mechanism migrations 338 and 357 already use: resolving a header and reading it are
two different things, and an alias row is what says "we know what this column is, and we are
not interested". Two of them are worth naming, because a future reader will be tempted:

  * `Shipping Order` is AutoCount's own PO-versus-SPO checkbox, and it is NOT the family.
    Nine rows of the captain's 2023 book carry `Checked` on a `######-S####` purchase order.
    The family is read from the Doc No prefix (`po_listing_reader.doc_family`), which is
    what the business quotes and cannot be wrong without being visibly wrong.
  * `Agent` on THIS book is not a salesperson. Its values are the creditor's own shorthand -
    `TAIYANG` against `XIAMEN TAIYANG TECHNOLOGY CO.,LTD`, `CAIZOU` against `CAIZHOU
    PLUMBING PRODUCTS FITTING CO LTD` - so feeding it to `sales_agent_service` would create
    38 factories in the salesperson master the outstanding SO book fills. It is aliased
    under its own doc type, where it resolves and stops there.

`Standard Price` is the item's standard price rather than what this document paid (the file
carries no unit price and no currency at all), so it is not read as a cost: the supplier cost
ranking compares what was actually paid, and a standard price in that column would be a
number that looks like evidence and is not.

Revision ID: 358_scm_po_spo_history_aliases
Revises: 46cf6ce8b6d0
"""
import sqlalchemy as sa
from alembic import op

revision = "358_scm_po_spo_history_aliases"
down_revision = "46cf6ce8b6d0"
branch_labels = None
depends_on = None

DOC_TYPE = "po_spo_history"

#: (field, alias). In the order the export writes the columns, so the list can be read
#: against the file. Stored normalised by the resolver, so the casing here is only for
#: reading. `normalize_header` strips every non-alphanumeric character, so one spelling
#: covers `ICB To DocNo` and `ICB TO DOC NO` alike.
_ALIASES = [
    # --- read by the write path ------------------------------------------------
    ("item_code", "Item Code"),
    ("qty_ordered", "Qty"),
    ("stock_location", "Location"),
    ("po_number", "Doc No"),
    ("po_date", "Doc Date"),
    ("expected_date", "Delivery Date"),
    ("item_description", "Description"),
    ("supplier_name", "Creditor Name"),
    ("so_number", "FromSODocList"),
    # --- resolved, and deliberately not read on a history book -----------------
    ("qty_received", "Transfered Qty"),
    ("qty_remaining", "Remaining Qty"),
    # A date and a container number in one cell ("14.05.23 CMAU7129817"). Not a date column
    # and not a container column; the packing-list channel owns containers.
    ("loading_date", "Loading Date"),
    ("agent", "Agent"),
    ("ref", "Ref"),
    ("shipping_order", "Shipping Order"),
    ("icb_name", "ICB Name"),
    ("account_book", "Account Book"),
    ("is_posted", "Is Posted"),
    ("running_no", "Running No"),
    ("post_gross_figure", "Post Gross Figure"),
    ("enable_auto_price", "Enable Auto Price"),
    ("icb_to_doc_no", "ICB To DocNo"),
    ("ib_from_so", "IB From SOKey"),
    ("import_post", "Import Post"),
    ("desc2", "Desc2"),
    ("width", "Width"),
    ("standard_price", "Standard Price"),
    # --- alternative spellings -------------------------------------------------
    # The same two families are exported with these headings elsewhere in AutoCount, and a
    # future spelling is meant to be an alias row rather than a release.
    ("po_number", "Document No"),
    ("po_number", "SPO No"),
    ("supplier_name", "Supplier Name"),
    ("stock_location", "Stock Location"),
    ("so_number", "From SO Doc List"),
    ("item_description", "Item Description"),
]


def _rows():
    """The seed, as tuples. Importable so `scripts/bootstrap_env` can replay it on a
    create_all database, which never runs a migration body."""
    return list(_ALIASES)


def seed(bind) -> int:
    """Insert the aliases. Idempotent through the table's own unique constraint, so a re-run
    on an already-seeded database is a no-op. Mirrors migration 357's `seed`."""
    inserted = 0
    for field, alias in _ALIASES:
        res = bind.execute(
            sa.text(
                """
                INSERT INTO import_field_alias (doc_type, field, alias, locale)
                VALUES (:d, :f, :a, 'en')
                ON CONFLICT (doc_type, field, alias) DO NOTHING
                """
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )
        inserted += res.rowcount or 0
    return inserted


def upgrade() -> None:
    seed(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    for field, alias in _ALIASES:
        bind.execute(
            sa.text(
                "DELETE FROM import_field_alias "
                "WHERE doc_type = :d AND field = :f AND alias = :a"
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )
