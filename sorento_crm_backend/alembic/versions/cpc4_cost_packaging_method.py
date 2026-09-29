"""Cost per packaging method (#1288, PR #1305 fix lane round 8).

Owner ruling of 28 Sep 2026 (15:2x MYT), from the supplier's own 2500 series sheet
(`CB2500SS-BL（彩盒）` 9.50, `CB2500SS-BL-DIY（OPP）` 9.90, `CB2500SS-BL-DIY（吊卡）` 9.40): "there
needs to be diffetent cost for differnet packging method correct". Plan question Q9 is reversed:
the bracket text of a supplier code is its packaging method, and a cost list line is keyed by
product code AND packaging method. A code with no bracket is the `standard` packaging.

- `cost_price_change_lines`: `packaging_method` (as written) and `packaging_key` (NFKC, trimmed,
  case folded) replace `code_note`. Data: a line's bracket note becomes its packaging method;
  a line with no note is `standard`.
- `product_supplier_costs`: the same two columns. Data: a cost row takes its source line's
  packaging; a hand-added row (no source line) is `standard`.
- `ix_product_supplier_costs_link_start` becomes `ix_product_supplier_costs_link_packaging`
  on (product_supplier_id, packaging_key, start_date): `price_in_force` now runs per packaging.

Idempotent both ways (every step checks the live schema first). The downgrade puts every
non-standard packaging back into `code_note`.

Revision ID: cpc4_cost_packaging_method
Revises: cpc3_lead_time_nullable
Create Date: 2026-09-28
"""
import re
import unicodedata

from alembic import op
import sqlalchemy as sa


revision = "cpc4_cost_packaging_method"
down_revision = "cpc3_lead_time_nullable"
branch_labels = None
depends_on = None

STANDARD = "standard"
LINES = "cost_price_change_lines"
COSTS = "product_supplier_costs"
OLD_INDEX = "ix_product_supplier_costs_link_start"
NEW_INDEX = "ix_product_supplier_costs_link_packaging"


def _key(method):
    """A frozen copy of `supplier_cost_service.packaging_key` (a migration never imports app code)."""
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", method or "")).strip()
    return text.casefold() or STANDARD


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _indexes(bind, table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(bind).get_indexes(table)}


def _add_packaging_columns(bind, table: str) -> None:
    cols = _columns(bind, table)
    for name in ("packaging_method", "packaging_key"):
        if name not in cols:
            op.add_column(
                table,
                sa.Column(name, sa.String(255), nullable=False, server_default=sa.text(f"'{STANDARD}'")),
            )


def _fill_keys(bind, table: str) -> None:
    methods = [r[0] for r in bind.execute(sa.text(f"SELECT DISTINCT packaging_method FROM {table}"))]
    for method in methods:
        bind.execute(
            sa.text(f"UPDATE {table} SET packaging_key = :k WHERE packaging_method = :m AND packaging_key <> :k"),
            {"k": _key(method), "m": method},
        )


def upgrade() -> None:
    bind = op.get_bind()

    _add_packaging_columns(bind, LINES)
    if "code_note" in _columns(bind, LINES):
        bind.execute(sa.text(
            f"UPDATE {LINES} SET packaging_method = btrim(code_note) "
            "WHERE code_note IS NOT NULL AND btrim(code_note) <> ''"
        ))
        _fill_keys(bind, LINES)
        op.drop_column(LINES, "code_note")
    else:
        _fill_keys(bind, LINES)

    _add_packaging_columns(bind, COSTS)
    bind.execute(sa.text(
        f"UPDATE {COSTS} AS c SET packaging_method = l.packaging_method, packaging_key = l.packaging_key "
        f"FROM {LINES} AS l WHERE c.source_change_line_id = l.id "
        "AND (c.packaging_method, c.packaging_key) IS DISTINCT FROM (l.packaging_method, l.packaging_key)"
    ))

    indexes = _indexes(bind, COSTS)
    if OLD_INDEX in indexes:
        op.drop_index(OLD_INDEX, table_name=COSTS)
    if NEW_INDEX not in indexes:
        op.create_index(NEW_INDEX, COSTS, ["product_supplier_id", "packaging_key", "start_date"])


def downgrade() -> None:
    bind = op.get_bind()

    indexes = _indexes(bind, COSTS)
    if NEW_INDEX in indexes:
        op.drop_index(NEW_INDEX, table_name=COSTS)
    if OLD_INDEX not in indexes:
        op.create_index(OLD_INDEX, COSTS, ["product_supplier_id", "start_date"])
    cost_cols = _columns(bind, COSTS)
    for name in ("packaging_key", "packaging_method"):
        if name in cost_cols:
            op.drop_column(COSTS, name)

    line_cols = _columns(bind, LINES)
    if "code_note" not in line_cols:
        op.add_column(LINES, sa.Column("code_note", sa.String(255), nullable=True))
    if "packaging_method" in line_cols:
        bind.execute(sa.text(
            f"UPDATE {LINES} SET code_note = packaging_method "
            f"WHERE packaging_key <> '{STANDARD}'" if "packaging_key" in line_cols else
            f"UPDATE {LINES} SET code_note = packaging_method WHERE packaging_method <> '{STANDARD}'"
        ))
    for name in ("packaging_key", "packaging_method"):
        if name in line_cols:
            op.drop_column(LINES, name)
