"""Price badge textColor default fix (B1, code review)

`KonvaTagLayer` and `TagSheetRenderer` used to hardcode '#000000' for an
unboxed price badge's amount; both now honour the layer's own `textColor`
(D22, PLAN-price-tag-ai-extract-resolver.md), which for a `list_only` badge
has always defaulted to `#ffffff` (`defaultPriceBadgeProps`, meant for the
white-on-red `promo` variant, not the plain unboxed one). Every ALREADY
SEEDED list_only badge carries that stored default, so honouring textColor
as-is would flip every one of them to white text on the tag's own
background - invisible. `defaultPriceBadgeProps` is fixed going forward
(list_only now defaults to '#000000'); this migration is the one-way half
for what already exists.

Walks every stored tag doc:

* `tag_template.doc` / `tag_template_version.doc` - the tag TEMPLATE
  library's own flat `layers` array.
* `page.draft_doc` / `page.doc` / `page_version.doc` where `kind = 'tag_sheet'`
  - PRICE TAG REQUEST design docs, which live in the same tables a catalogue
  page uses (discriminated by `kind`), nested `sheets[].tags[].layers[]`.

Only an UNBOXED (`showBox` not `true`) `variant: "list_only"` `price_badge`
layer whose `textColor` is exactly the retired default `#ffffff` is touched -
a designer who explicitly picked white keeps it. There is no way to tell
"never set, still the old default" from "set to white on purpose" after the
fact once both read the same value, so the retired default's own value IS the
signal: what printed black (every one of these, since the canvas/PDF
hardcoded black regardless of this field until D22) keeps printing black, and
a designer who picks white from here on gets white.

`_locate`/the table-walk shape mirrors `ptag_0009_combos_tags`'s own guard: a
test runs on its own scratch `..._dealer_kit` schema, where the bare table
name is right and a literal `dealer_kit.` prefix would send the write to a
prod-copy database on a developer machine; production has `dealer_kit` OFF
the search_path, where the bare name resolves to nothing and the rewrite
would be a silent no-op.

Revision ID: ptag_0010_badge_textcolor
Revises: ptag_0008_pins_versions
Create Date: 2026-09-15
"""
import json
import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger("alembic.runtime.migration")


revision = "ptag_0010_badge_textcolor"
down_revision = "ptag_0008_pins_versions"
branch_labels = None
depends_on = None

_OLD_DEFAULT = "#ffffff"
_NEW_DEFAULT = "#000000"


def _locate(conn, table: str) -> str | None:
    """Where `table` actually lives for THIS connection, ready to interpolate.

    The bare name when the search_path already finds it (a test on its
    scratch schema), `dealer_kit.<table>` when it does not (production), and
    None when the table is absent altogether - see `ptag_0009_combos_tags`
    for the full rationale, copied here unchanged.
    """
    inspector = sa.inspect(conn)
    if inspector.has_table(table):
        return table
    if inspector.has_table(table, schema="dealer_kit"):
        return f"dealer_kit.{table}"
    return None


def _fix_layers(layers) -> bool:
    """Rewrite matching `price_badge` layers IN PLACE. Returns whether anything changed."""
    changed = False
    for layer in layers or []:
        if not isinstance(layer, dict):
            continue
        props = layer.get("props")
        if not isinstance(props, dict) or props.get("kind") != "price_badge":
            continue
        if props.get("variant") != "list_only":
            continue
        if props.get("showBox") is True:
            continue
        if str(props.get("textColor") or "").lower() != _OLD_DEFAULT:
            continue
        props["textColor"] = _NEW_DEFAULT
        changed = True
    return changed


def fix_template_doc(doc) -> bool:
    """A `tag_template[_version].doc` - a flat `layers` array."""
    if not isinstance(doc, dict):
        return False
    return _fix_layers(doc.get("layers"))


def fix_tag_sheet_doc(doc) -> bool:
    """A `page[_version]` doc, only when it is a tag sheet - `sheets[].tags[].layers[]`."""
    if not isinstance(doc, dict) or doc.get("kind") != "tag_sheet":
        return False
    changed = False
    for sheet in doc.get("sheets") or []:
        if not isinstance(sheet, dict):
            continue
        for placed in sheet.get("tags") or []:
            if not isinstance(placed, dict):
                continue
            if _fix_layers(placed.get("layers")):
                changed = True
    return changed


def _rewrite_table(conn, table: str, columns: tuple, fixer) -> int:
    located = _locate(conn, table)
    if located is None:
        return 0
    schema = "dealer_kit" if located.startswith("dealer_kit.") else None
    available = {c["name"] for c in sa.inspect(conn).get_columns(table, schema=schema)}
    cols = [c for c in columns if c in available]
    if not cols:
        return 0
    selected = ", ".join(cols)
    rows = conn.execute(
        sa.text(f"SELECT id, {selected} FROM {located}")  # noqa: S608 - fixed names
    ).fetchall()
    rewritten = 0
    for row in rows:
        mapping = dict(row._mapping)
        updates = {}
        for column in cols:
            raw = mapping.get(column)
            if raw is None:
                continue
            doc = json.loads(raw) if isinstance(raw, str) else raw
            if fixer(doc):
                updates[column] = json.dumps(doc)
        if not updates:
            continue
        assignments = ", ".join(f"{c} = CAST(:{c} AS jsonb)" for c in updates)
        conn.execute(
            sa.text(f"UPDATE {located} SET {assignments} WHERE id = :row_id"),  # noqa: S608
            {**updates, "row_id": mapping["id"]},
        )
        rewritten += 1
    return rewritten


def upgrade() -> None:
    conn = op.get_bind()
    template_rows = _rewrite_table(conn, "tag_template", ("doc",), fix_template_doc)
    template_rows += _rewrite_table(conn, "tag_template_version", ("doc",), fix_template_doc)
    sheet_rows = _rewrite_table(conn, "page", ("draft_doc", "doc"), fix_tag_sheet_doc)
    sheet_rows += _rewrite_table(conn, "page_version", ("doc",), fix_tag_sheet_doc)
    logger.info(
        "ptag_0010: rewrote textColor on %s tag_template doc row(s), %s page doc row(s)",
        template_rows,
        sheet_rows,
    )


def downgrade() -> None:
    """Not reversed - the same reason `ptag_0009_combos_tags` does not reverse
    its own doc rewrite: a value overwritten to '#000000' cannot be told apart
    from a designer who typed '#000000' on purpose, so there is nothing
    correct to restore it to."""
    pass
