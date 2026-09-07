"""Header capture for supplier documents (R13, purchasing consolidation batch, lane C).

The Jiexia proforma invoice and packing list both write their container's identity as
labelled cells ABOVE the table (`箱号:X / 封签号:Y`), name the customer once (`客户：SORENTO SDN
BHD`) and carry the invoice's own number and date (`INVOICE NO.:`, `日期 :`) - none of which the
`packing_list` / `proforma_invoice` doc types resolve today, because 311/375/428 were seeded
against a DIFFERENT supplier's wording (`货柜号`, not `箱号`; `单价`/`总金额` only for whichever
doc type had not already gained them under a different alias).

Checked against 311 (`311_scm_purchasing_base.py`), 375 (`375_scm_proforma_invoice.py`,
`375_kailu_packing_list_aliases.py`) and 428 (`428_scm_pi_cbm_adjust_revision.py`) before
writing this list - only the alias TEXT missing for each doc type is seeded here; a header
that already resolves (`品名`, `数量`, `商标`, `CBM/CTN` for packing_list, `单价` for
proforma_invoice) is left alone rather than given a second, competing alias row.

Three genuinely NEW fields, resolved for both doc types: `seal_no` (`封签号`, the container's
seal), `consignee` (`客户`, who is billed) and `supplier_code` (`洁厦型号` / `JIEXIA MODEL`, the
factory's OWN model number - kept distinct from `item_code`, which is `客户型号`: OUR catalogue
code, printed as a SEPARATE column on both documents). Neither reader stores `supplier_code`
onto a line today; the alias still resolves it, so it stops appearing in `unmapped_headers`
and is available the day a reader wants it.

`import_field_alias`'s unique constraint is `(doc_type, field, alias)`, and the resolver takes
the FIRST alias that maps to a field on a collision - so `INVOICE NO.` for `packing_list` is
new (that doc type has no `pi_number` alias yet), while for `proforma_invoice` it needs no row
at all: `normalize_header` folds `INVOICE NO.` and the already-seeded `Invoice No` to the same
key.

Revision ID: 483_supplier_doc_aliases
Revises: 482_attachment_type_default_dir
"""
import sqlalchemy as sa
from alembic import op

revision = "483_supplier_doc_aliases"
down_revision = "482_attachment_type_default_dir"
branch_labels = None
depends_on = None


#: (doc_type, field, alias, locale). Seeded for BOTH doc types (R13); a doc type that already
#: resolves a given header via a different spelling is skipped for that pair - see the
#: per-row comments below.
_ALIASES = [
    # --- container identity, new to both doc types ------------------------------
    ("packing_list", "container_no", "箱号", "zh"),
    ("proforma_invoice", "container_no", "箱号", "zh"),
    ("packing_list", "seal_no", "封签号", "zh"),
    ("proforma_invoice", "seal_no", "封签号", "zh"),
    ("packing_list", "consignee", "客户", "zh"),
    ("proforma_invoice", "consignee", "客户", "zh"),
    # --- the invoice's own number and date ---------------------------------------
    # packing_list has neither field aliased at all yet. proforma_invoice already
    # resolves "Invoice No" (375) to the same normalised key as "INVOICE NO." and
    # has no bare "日期" (only "Date 日期" / "Invoice Date" / "Date").
    ("packing_list", "pi_number", "INVOICE NO.", "en"),
    ("packing_list", "invoice_date", "日期", "zh"),
    ("proforma_invoice", "invoice_date", "日期", "zh"),
    # --- OUR code vs the factory's OWN code --------------------------------------
    ("packing_list", "item_code", "客户型号", "zh"),
    ("proforma_invoice", "item_code", "客户型号", "zh"),
    ("packing_list", "supplier_code", "洁厦型号", "zh"),
    ("proforma_invoice", "supplier_code", "洁厦型号", "zh"),
    ("packing_list", "supplier_code", "JIEXIA MODEL", "en"),
    ("proforma_invoice", "supplier_code", "JIEXIA MODEL", "en"),
    # --- money, new text for whichever doc type does not already have it --------
    # packing_list has "RMB" -> unit_price (311) but not the plain "单价"; proforma_invoice
    # already has "单价" (375).
    ("packing_list", "unit_price", "单价", "zh"),
    # Neither doc type has "总金额" - packing_list has "金额（rmb）", proforma_invoice has
    # "金额" / "总价" / "总价（元）" / "AMOUNT" / "TOTAL", none of which normalise the same.
    ("packing_list", "amount", "总金额", "zh"),
    ("proforma_invoice", "amount", "总金额", "zh"),
    # --- CARTONS/CBM, English spellings neither doc type has ---------------------
    ("packing_list", "cartons", "CARTONS", "en"),
    ("proforma_invoice", "cartons", "CARTONS", "en"),
    ("packing_list", "cbm_total", "CBM", "en"),
    ("proforma_invoice", "cbm_total", "CBM", "en"),
    ("proforma_invoice", "cbm_per_carton", "CBM/CTN", "en"),
    # packing_list already has "CBM/CTN" -> cbm_per_carton (375 kailu).
    # --- carton weights - resolved for completeness, not read by either line yet,
    # same "resolved and deliberately not read" trade 375 kailu made for `NW`/`GW` -----
    ("packing_list", "carton_gross_weight", "UNIT G.W/KGS", "en"),
    ("proforma_invoice", "carton_gross_weight", "UNIT G.W/KGS", "en"),
    ("packing_list", "total_gross_weight", "TOTAL G.W/KGS", "en"),
    ("proforma_invoice", "total_gross_weight", "TOTAL G.W/KGS", "en"),
    ("packing_list", "carton_net_weight", "UNIT N.W/KGS", "en"),
    ("proforma_invoice", "carton_net_weight", "UNIT N.W/KGS", "en"),
    ("packing_list", "total_net_weight", "TOTAL N.W /KGS", "en"),
    ("proforma_invoice", "total_net_weight", "TOTAL N.W /KGS", "en"),
]


def _rows():
    """The seed, as tuples. Importable so `scripts/bootstrap_env` can replay it on a
    create_all database, which never runs a migration body (same convention 375/428 use)."""
    return list(_ALIASES)


def seed(bind) -> int:
    """Insert the aliases. Idempotent through the table's own unique constraint."""
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
