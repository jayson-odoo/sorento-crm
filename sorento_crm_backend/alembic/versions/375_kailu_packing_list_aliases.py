"""The captain's real Kailu packing list resolves no item code and no quantity column.

`Sorento装箱单（凯路）260717.xls` is a packing list in the plainest possible wording: the
model number column is headed `型号`, the description `货名`, the line volume `体积`, the
brand `牌子/LOGO`. Migration 311 seeded the spellings the PI-format lists use - `产品型号`,
`品名`, `总体积(cbm)`, `商标` - and none of the bare forms. With only those seeds the reader
finds no `item_code` column, `_is_header` never fires, and the preview comes back
`missing_columns=['item_code','qty']`: the upload dialog reports "This file has no item_code,
qty column" about a file that is nothing but item codes and quantities.

Nothing about the reader is wrong. A supplier who words a column differently is a row
somebody inserts, which is exactly what this is.

**Four aliases the reader spends.** `型号` -> item_code and `数量` (already seeded in 311)
are what make the header a header; `货名` -> product_name, `体积` -> cbm_total and
`牌子/LOGO` -> brand are carried per line.

`体积` is the LINE TOTAL on this file - cartons x CBM/CTN - not a per-unit figure, which is
why it aliases to `cbm_total`. 311's `体积(cbm)` is the per-unit column and stays mapped to
`cbm_per_unit`; `normalize_header` strips the bracketed unit rather than the characters
inside it, so the two fold to distinct keys (`体积` vs `体积cbm`) and neither steals the
other's column. The reader derives cbm_per_unit = total / qty when only the total is given.

**Nine more are resolved and deliberately not read.** This is migration 338's and 357's
mechanism: resolving a header and reading it are two different things, and an alias row is
what says "we know what this column is, and we are not interested". Without them every
upload of this file lists nine columns as unrecognised, and a "columns I could not place"
list that is never empty - on a file we have already seen - is a list nobody reads.

`No.` is the printed row number, `材质` the material, `PCS/CTN` the carton pack size,
`包装规格cm` the carton L/W/H (three columns under one heading), `CBM/CTN` the per-carton
volume, and `TOTAL KGS` / `总毛重` the shipment weight totals.

The cost is doc-type-wide, not per-file: these rows resolve for EVERY packing list, so a
future supplier whose `TOTAL KGS` or `No.` means something we should read will resolve
silently instead of appearing in `unmapped_headers` and prompting a look. That is the same
trade 357 made for the outstanding-SO wording, and undoing it for one supplier is a DELETE
of that supplier's row, not a release.

**NW and GW are the trap.** On this file they are PER-CARTON weights (the sub-header row
under them reads `KG`), not line weights: line 1 carries 860 pieces in 86 cartons at NW 7.0,
and the line's real net weight is the 602 in `TOTAL KGS`. Aliasing them to 311's
`net_weight` / `gross_weight` would store a carton's weight as the whole line's and be wrong
by a factor of the carton count, silently. They alias to `carton_net_weight` /
`carton_gross_weight`, which no reader consumes, so the columns resolve without being
believed. Storing them properly needs a per-carton field on the line, and that is a change
to the reader and the receipt, not a seed row.

Revision ID: 375_kailu_packing_list_aliases
Revises: 374_merge_proj_media_flyer
"""
import sqlalchemy as sa
from alembic import op

revision = "375_kailu_packing_list_aliases"
down_revision = "374_merge_proj_media_flyer"
branch_labels = None
depends_on = None


#: (doc_type, field, alias, locale). Stored normalised by the resolver, so the casing here is
#: only for reading.
_ALIASES = [
    # --- read and spent --------------------------------------------------------
    ("packing_list", "item_code", "型号", "zh"),
    ("packing_list", "product_name", "货名", "zh"),
    # The LINE total (cartons x CBM/CTN), distinct from 311's per-unit `体积(cbm)`.
    ("packing_list", "cbm_total", "体积", "zh"),
    ("packing_list", "brand", "牌子/LOGO", "zh"),
    # --- resolved and deliberately not read ------------------------------------
    # The printed line number. It numbers the paper, not the goods.
    ("packing_list", "row_no", "No.", "en"),
    # What the item is made of. `products` is the record of that.
    ("packing_list", "material", "材质", "zh"),
    # Carton pack size and carton dimensions. The receipt counts pieces and cartons; how the
    # pieces are arranged inside a carton is the factory's business.
    ("packing_list", "pcs_per_carton", "PCS/CTN", "en"),
    ("packing_list", "packing_dim", "包装规格cm", "zh"),
    ("packing_list", "cbm_per_carton", "CBM/CTN", "en"),
    # PER-CARTON weights, not line weights - see the note above. Mapping these to
    # `net_weight` / `gross_weight` would be wrong by the carton count.
    ("packing_list", "carton_net_weight", "NW", "en"),
    ("packing_list", "carton_gross_weight", "GW", "en"),
    # Shipment weight totals, which the line-level reader has nowhere to put.
    ("packing_list", "total_net_weight", "TOTAL KGS", "en"),
    ("packing_list", "total_gross_weight", "总毛重", "zh"),
]


def _rows():
    """The seed, as tuples. Importable so `scripts/bootstrap_env` can replay it on a
    create_all database, which never runs a migration body."""
    return list(_ALIASES)


def seed(bind) -> int:
    """Insert the aliases. Idempotent through the table's own unique constraint, so a re-run
    on an already-seeded database is a no-op. Mirrors migration 357's `seed` rather than
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
