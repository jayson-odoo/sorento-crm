"""The last seven columns of the captain's outstanding-SO export stop reading as unrecognised.

His real file carries 20 columns and seven of them resolved to nothing, so every upload
reported them and the "columns I could not place" list - whose job is to warn that an export
has CHANGED - cried wolf on a file we had already seen. A list that is never empty is a list
nobody reads.

They split two ways, and the split is the point.

**`Agent` gets a real field.** It is read by the reader, carried per document, stamped onto
`sales_orders.sales_agent_id`, and is the fourth and last source the demand class is resolved
from (UAC AC-3). Throwing it away was why SO375073 in his file reported as unclassifiable
while the salesperson who sold it sat in a column we had discarded.

**The other six are deliberately ignored.** `Ref Doc No`, `Ref`, `Item Description`,
`Discount`, `Total (Inc)` and `IB From POKey` describe money, cross-references and free text
that the outstanding book has nowhere to put and no use for. They are aliased to fields the
reader does not consume, which is the mechanism `Unit Price` and `Note` (migration 338)
already use: resolving a header and reading it are two different things, and an alias row is
what says "we know what this column is, and we are not interested". Inventing storage for
them so they would resolve would be worse - a column nothing reads, that a later reader might
start trusting.

The header cell really does read `IB From POKey`; the feedback note wrote `IB From PO`. Both
spellings are seeded, since one of them is what somebody will type into a hand-corrected
export.

**PO/SPO history (UAC AC-1.2) is NOT in this revision.** That file's 27 headers are not
recorded anywhere this branch can read, and seeding invented spellings would produce aliases
that match nothing while looking done. It needs the real header row, and it ships with S5,
which is the slice that reads that format anyway.

Revision ID: 357_scm_so_agent_aliases
Revises: 356_sales_agent_master
"""
import sqlalchemy as sa
from alembic import op

revision = "357_scm_so_agent_aliases"
down_revision = "356_sales_agent_master"
branch_labels = None
depends_on = None


#: (doc_type, field, alias, locale). Stored normalised by the resolver, so the casing here is
#: only for reading.
_ALIASES = [
    # --- read and spent (AC-3) -------------------------------------------------
    ("outstanding_so", "agent", "AGENT", "en"),
    ("outstanding_so", "agent", "SALES AGENT", "en"),
    ("outstanding_so", "agent", "SALESMAN", "en"),
    ("outstanding_so", "agent", "SALESPERSON", "en"),
    # --- resolved and deliberately not read ------------------------------------
    # The document this order was raised against (a quotation, a customer PO). It names
    # another system's document, and nothing in the outstanding book resolves it.
    ("outstanding_so", "ref_doc_no", "REF DOC NO", "en"),
    ("outstanding_so", "ref", "REF", "en"),
    # The item's own description. `products` is the record of that, and letting a file
    # restate it would make the catalogue say whatever the last export said.
    ("outstanding_so", "item_description", "ITEM DESCRIPTION", "en"),
    ("outstanding_so", "item_description", "DESCRIPTION", "en"),
    # Money on the sales side. The outstanding book plans quantities and dates; what the line
    # sold for belongs to the history feed, which reads its own file.
    ("outstanding_so", "discount", "DISCOUNT", "en"),
    # Only ONE spelling of this one. `normalize_header` strips every non-alphanumeric
    # character, so `TOTAL (INC)` and `TOTAL INC` fold to the same key - a second row would
    # read as a second spelling being covered while inserting a duplicate that resolves
    # nothing new. `IB From PO` below is the opposite case and IS a distinct key.
    ("outstanding_so", "total_inc", "TOTAL (INC)", "en"),
    # AutoCount's internal key for the purchase order an inter-branch line came from. An
    # opaque key into another system, useless without that system.
    ("outstanding_so", "ib_from_po", "IB FROM POKEY", "en"),
    ("outstanding_so", "ib_from_po", "IB FROM PO", "en"),
]


def _rows():
    """The seed, as tuples. Importable so `scripts/bootstrap_env` can replay it on a
    create_all database, which never runs a migration body."""
    return list(_ALIASES)


def seed(bind) -> int:
    """Insert the aliases. Idempotent through the table's own unique constraint, so a re-run
    on an already-seeded database is a no-op. Mirrors migration 338's `seed` rather than
    restating its SQL differently."""
    inserted = 0
    for doc_type, field, alias, locale in _ALIASES:
        res = bind.execute(
            sa.text(
                """
                INSERT INTO import_field_alias (doc_type, field, alias, locale)
                VALUES (:d, :f, :a, :l)
                ON CONFLICT (doc_type, field, alias) DO NOTHING
                """
            ),
            {"d": doc_type, "f": field, "a": alias, "l": locale},
        )
        inserted += res.rowcount or 0
    return inserted


def upgrade() -> None:
    seed(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    for doc_type, field, alias, _locale in _ALIASES:
        bind.execute(
            sa.text(
                "DELETE FROM import_field_alias "
                "WHERE doc_type = :d AND field = :f AND alias = :a"
            ),
            {"d": doc_type, "f": field, "a": alias},
        )
