"""Price tag combos: packages on the product, parts under a line, tags under a line

PLAN-price-tag-combos.md D1/D2/D3. Built INCREMENTALLY across the lane's slices, in
one revision file, because they are one schema change: S1 lands step 1's DDL, S2 and
S3 add the rest to this same file before the lane opens its PR.

Step 1 (S1): the new tables and columns.

  * `product_combos` / `product_combo_parts` - the catalogue package on the host
    product (D1).
  * `price_tag_request_line_parts` - what the salesperson asked to come with a line,
    plus `lines.combo_id` and `lines.package_warning` (D2). The line columns land
    with the table they belong to rather than a slice later: the model declares them
    the moment `PriceTagRequestLinePart` exists, and a model column with no database
    column behind it breaks every read of the table.
  * `system_settings.price_tag_guarded_classes` - the classes the S2 guard warns
    about, seeded with the two the owner named. NOT NULL with a default rather than
    NULL, or the guard would warn about nothing on every existing tenant, which reads
    as the feature not working.

Steps 2 to 4 (S3, here): `price_tag_request_tags` and one tag per existing line
with its quantity and override copied across; every saved tag sheet document
re-keyed from `request_line_id` to the new `request_tag_id`; the r9 pin remap,
guarded so it is a documented no-op until r9 merges; and dropping the three line
columns that retire with it.

The document rewrite is the one-way half. It walks EVERY `page.draft_doc` /
`page.doc` and `page_version.doc` whose `kind = 'tag_sheet'` in production: a
doc that comes out wrong is a design marketing has to redraw, and one that comes
out EMPTY looks exactly like a request nobody ever designed. Two rules keep it
honest:

* The document tables are LOCATED, never spelled either way. A test runs with a
  scratch `..._dealer_kit` schema on its search_path, where the bare name is
  right and a literal `dealer_kit.` prefix would send the write to the REAL
  schema (a prod copy on a developer machine). Production has `dealer_kit` OFF
  the search_path, where the bare name resolves to nothing and the rewrite would
  be a silent no-op. `_locate` asks the connection which of the two it is.
* A placement whose line no longer exists is DROPPED from the doc and counted,
  never left un-keyed - the designer would otherwise read a tag it can neither
  resolve nor delete.

Revision ID: ptag_0009_combos_tags
Revises: 510_spec_visibility_policies
Create Date: 2026-09-14
"""
import logging

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

logger = logging.getLogger("alembic.runtime.migration")


revision = "ptag_0009_combos_tags"
down_revision = "510_spec_visibility_policies"
branch_labels = None
depends_on = None

GUARDED_CLASSES_DEFAULT = '["Bathroom Furniture", "Kitchen Sink"]'


def upgrade() -> None:
    # ---------------------------------------------------------------- D1 combos
    op.create_table(
        "product_combos",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "host_product_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("host_product_id", "name", name="uq_product_combos_host_name"),
    )
    op.create_index("ix_product_combos_host_product_id", "product_combos", ["host_product_id"])

    op.create_table(
        "product_combo_parts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "combo_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_combos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "part_product_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("choice_group", sa.String(length=100), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("combo_id", "part_product_id", name="uq_product_combo_parts_product"),
    )
    op.create_index("ix_product_combo_parts_combo_id", "product_combo_parts", ["combo_id"])
    op.create_index(
        "ix_product_combo_parts_part_product_id", "product_combo_parts", ["part_product_id"]
    )

    # ------------------------------------------------------- D2 parts on a line
    op.add_column(
        "price_tag_request_lines",
        sa.Column(
            "combo_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_combos.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "price_tag_request_lines", sa.Column("package_warning", sa.Text(), nullable=True)
    )

    op.create_table(
        "price_tag_request_line_parts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "line_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("price_tag_request_lines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.Column(
            "candidates",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "(product_id IS NOT NULL AND candidates = '[]'::jsonb) "
            "OR (product_id IS NULL AND jsonb_array_length(candidates) > 0)",
            name="ck_ptag_line_parts_resolved_or_open",
        ),
    )
    op.create_index(
        "ix_price_tag_request_line_parts_line_id", "price_tag_request_line_parts", ["line_id"]
    )

    # ------------------------------------------------- D2 the guarded class list
    op.add_column(
        "system_settings",
        sa.Column(
            "price_tag_guarded_classes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(f"'{GUARDED_CLASSES_DEFAULT}'::jsonb"),
        ),
    )

    # ------------------------------------------------------- D3 tags on a line
    op.create_table(
        "price_tag_request_tags",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "line_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("price_tag_request_lines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "choices", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("marketing_price_override", sa.Numeric(15, 2), nullable=True),
        sa.Column("marketing_override_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_price_tag_request_tags_line_id", "price_tag_request_tags", ["line_id"]
    )

    conn = op.get_bind()

    # -- Step 2: one tag per EXISTING line, quantity and override carried across.
    conn.execute(
        sa.text(
            "INSERT INTO price_tag_request_tags "
            "(id, line_id, sort_order, quantity, choices, "
            " marketing_price_override, marketing_override_reason) "
            "SELECT gen_random_uuid(), id, 0, COALESCE(quantity, 1), '{}'::jsonb, "
            "       marketing_price_override, marketing_override_reason "
            "FROM price_tag_request_lines"
        )
    )
    tag_by_line = {
        str(row._mapping["line_id"]): str(row._mapping["id"])
        for row in conn.execute(
            sa.text("SELECT id, line_id FROM price_tag_request_tags")
        )
    }

    rewritten, orphans = _rekey_tag_sheet_docs(conn, tag_by_line)
    logger.info(
        "ptag_0009: re-keyed %s tag sheet document rows; dropped %s orphan placed tags",
        rewritten,
        orphans,
    )

    # -- Step 3: r9's pins, if r9 is on this branch. A no-op otherwise.
    _remap_r9_pins(conn, tag_by_line)

    # -- Step 4: the line columns that retire with the move.
    op.drop_column("price_tag_request_lines", "alternatives")
    op.drop_column("price_tag_request_lines", "marketing_price_override")
    op.drop_column("price_tag_request_lines", "marketing_override_reason")


def _locate(conn, table: str) -> str | None:
    """Where `table` actually lives for THIS connection, ready to interpolate.

    The bare name when the search_path already finds it (a test on its scratch
    schema), `dealer_kit.<table>` when it does not (production), and None when
    the table is absent altogether. A scratch schema is only ever on its own
    session's search_path, so the bare probe can never pick another run's.
    """
    inspector = sa.inspect(conn)
    if inspector.has_table(table):
        return table
    if inspector.has_table(table, schema="dealer_kit"):
        return f"dealer_kit.{table}"
    return None


def _rekey_tag_sheet_docs(conn, tag_by_line: dict) -> tuple[int, int]:
    """Point every placed tag at its line's TAG. Returns (docs rewritten, orphans).

    A copy keeps its own `-cN` placement id: the suffix is how `tagsFromDoc`
    tells copy 0 (the master, whose layers are the design) from the rest, and
    renaming it would make every reopened sheet look undesigned.
    """
    import json

    rewritten = 0
    orphans = 0

    def _rewrite(doc):
        nonlocal orphans
        if not isinstance(doc, dict) or doc.get("kind") != "tag_sheet":
            return None
        changed = False
        for sheet in doc.get("sheets") or []:
            kept = []
            for placed in sheet.get("tags") or []:
                if not isinstance(placed, dict):
                    continue
                line_id = placed.get("request_line_id")
                if not line_id:
                    # Already re-keyed (a second run of this migration, or a doc
                    # the designer saved after the rename). Nothing to do.
                    kept.append(placed)
                    continue
                # Deliberately NOT "skip anything that already has a
                # request_tag_id": a placement carrying BOTH keys is one whose
                # tag id came from somewhere other than this table, and the
                # authority is the line. Re-keying it and dropping the old key
                # is also what keeps a second run of this migration a no-op.
                tag_id = tag_by_line.get(str(line_id))
                if tag_id is None:
                    orphans += 1
                    changed = True
                    continue
                placed = {k: v for k, v in placed.items() if k != "request_line_id"}
                placed["request_tag_id"] = tag_id
                kept.append(placed)
                changed = True
            sheet["tags"] = kept
        return doc if changed else None

    for table, columns in (("page", ("draft_doc", "doc")), ("page_version", ("doc",))):
        located = _locate(conn, table)
        if located is None:
            continue
        schema = "dealer_kit" if located.startswith("dealer_kit.") else None
        available = {c["name"] for c in sa.inspect(conn).get_columns(table, schema=schema)}
        cols = [c for c in columns if c in available]
        if not cols:
            continue
        selected = ", ".join(cols)
        rows = conn.execute(
            sa.text(f"SELECT id, {selected} FROM {located}")  # noqa: S608 - fixed names
        ).fetchall()
        for row in rows:
            mapping = dict(row._mapping)
            updates = {}
            for column in cols:
                raw = mapping.get(column)
                doc = json.loads(raw) if isinstance(raw, str) else raw
                fixed = _rewrite(doc)
                if fixed is not None:
                    updates[column] = json.dumps(fixed)
            if not updates:
                continue
            assignments = ", ".join(f"{c} = CAST(:{c} AS jsonb)" for c in updates)
            conn.execute(
                sa.text(f"UPDATE {located} SET {assignments} WHERE id = :row_id"),  # noqa: S608
                {**updates, "row_id": mapping["id"]},
            )
            rewritten += 1

    return rewritten, orphans


def _remap_r9_pins(conn, tag_by_line: dict) -> None:
    """r9's review pins and pinned line data follow the line onto its tag (AC-S3-7).

    Whoever merges SECOND owns the remap (the plan's risk register). On a main
    without r9 every branch below is skipped and this is a documented no-op.
    """
    import json

    inspector = sa.inspect(conn)

    if inspector.has_table("price_tag_review_comments"):
        comment_columns = {c["name"] for c in inspector.get_columns("price_tag_review_comments")}
        if "line_id" in comment_columns and "tag_id" not in comment_columns:
            op.add_column(
                "price_tag_review_comments",
                sa.Column(
                    "tag_id",
                    postgresql.UUID(as_uuid=False),
                    sa.ForeignKey("price_tag_request_tags.id", ondelete="CASCADE"),
                    nullable=True,
                ),
            )
            op.create_index(
                "ix_ptag_review_comments_tag_id", "price_tag_review_comments", ["tag_id"]
            )
            conn.execute(
                sa.text(
                    "UPDATE price_tag_review_comments c SET tag_id = t.id "
                    "FROM price_tag_request_tags t WHERE t.line_id = c.line_id"
                )
            )
            op.drop_column("price_tag_review_comments", "line_id")

    line_columns = {c["name"] for c in inspector.get_columns("price_tag_request_lines")}
    if "pinned_tag_data" not in line_columns:
        return

    for column, spec in (
        ("pinned_tag_data", sa.Column("pinned_tag_data", postgresql.JSONB(), nullable=True)),
        ("pinned_at", sa.Column("pinned_at", sa.DateTime(timezone=False), nullable=True)),
        ("data_change_ack_hash", sa.Column("data_change_ack_hash", sa.Text(), nullable=True)),
    ):
        if column in line_columns:
            op.add_column("price_tag_request_tags", spec)

    rows = conn.execute(
        sa.text(
            "SELECT id, pinned_tag_data FROM price_tag_request_lines "
            "WHERE pinned_tag_data IS NOT NULL"
        )
    ).fetchall()
    for row in rows:
        mapping = dict(row._mapping)
        tag_id = tag_by_line.get(str(mapping["id"]))
        if tag_id is None:
            continue
        raw = mapping["pinned_tag_data"]
        pinned = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(pinned, dict):
            pinned = {k: v for k, v in pinned.items() if k != "line_id"}
            pinned["tag_id"] = tag_id
        conn.execute(
            sa.text(
                "UPDATE price_tag_request_tags SET pinned_tag_data = CAST(:d AS jsonb) "
                "WHERE id = :i"
            ),
            {"d": json.dumps(pinned), "i": tag_id},
        )

    for column in ("pinned_tag_data", "pinned_at", "data_change_ack_hash"):
        if column in line_columns:
            op.drop_column("price_tag_request_lines", column)

    versions_table = _locate(conn, "page_version")
    if versions_table is None:
        return
    version_schema = "dealer_kit" if versions_table.startswith("dealer_kit.") else None
    if "pinned_line_data" not in {
        c["name"] for c in inspector.get_columns("page_version", schema=version_schema)
    }:
        return
    versions = conn.execute(
        sa.text(
            f"SELECT id, pinned_line_data FROM {versions_table} "  # noqa: S608
            "WHERE pinned_line_data IS NOT NULL"
        )
    ).fetchall()
    if True:
        for row in versions:
            mapping = dict(row._mapping)
            raw = mapping["pinned_line_data"]
            keyed = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(keyed, dict):
                continue
            rekeyed = {
                tag_by_line.get(str(line_id), str(line_id)): value
                for line_id, value in keyed.items()
            }
            conn.execute(
                sa.text(
                    f"UPDATE {versions_table} SET pinned_line_data = CAST(:d AS jsonb) "  # noqa: S608
                    "WHERE id = :i"
                ),
                {"d": json.dumps(rekeyed), "i": mapping["id"]},
            )


def downgrade() -> None:
    """Restore the SCHEMA, not the data.

    The document re-key is not reversed: a doc keyed on a tag that is about to be
    deleted has nothing to point back at, and this migration is applied forward
    on production.

    Every step is guarded by the inspector because this revision was built
    INCREMENTALLY across the lane's slices - a developer database may sit at
    step 1 while the file already describes step 4, and an unguarded
    `drop_table` there fails on a table the database was never given.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    line_columns = {c["name"] for c in inspector.get_columns("price_tag_request_lines")}

    for column, spec in (
        ("marketing_override_reason", sa.Column("marketing_override_reason", sa.Text(), nullable=True)),
        ("marketing_price_override", sa.Column("marketing_price_override", sa.Numeric(15, 2), nullable=True)),
        (
            "alternatives",
            sa.Column(
                "alternatives",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        ),
    ):
        if column not in line_columns:
            op.add_column("price_tag_request_lines", spec)

    # r9's remap, reversed BEFORE the table it points at goes (AC-S3-7). The
    # forward step only fires when r9 is present; so does this one, and both are
    # a no-op on a branch without it. Reversible because
    # `price_tag_request_tags.line_id` still says which line every tag belongs
    # to - it is the same join, run the other way.
    if inspector.has_table("price_tag_review_comments") and inspector.has_table(
        "price_tag_request_tags"
    ):
        comment_columns = {
            c["name"] for c in inspector.get_columns("price_tag_review_comments")
        }
        if "tag_id" in comment_columns and "line_id" not in comment_columns:
            op.add_column(
                "price_tag_review_comments",
                sa.Column(
                    "line_id",
                    postgresql.UUID(as_uuid=False),
                    sa.ForeignKey("price_tag_request_lines.id", ondelete="CASCADE"),
                    nullable=True,
                ),
            )
            conn.execute(
                sa.text(
                    "UPDATE price_tag_review_comments c SET line_id = t.line_id "
                    "FROM price_tag_request_tags t WHERE t.id = c.tag_id"
                )
            )
            op.drop_column("price_tag_review_comments", "tag_id")

    if inspector.has_table("price_tag_request_tags"):
        tag_columns = {c["name"] for c in inspector.get_columns("price_tag_request_tags")}
        for column, spec in (
            ("pinned_tag_data", sa.Column("pinned_tag_data", postgresql.JSONB(), nullable=True)),
            ("pinned_at", sa.Column("pinned_at", sa.DateTime(timezone=False), nullable=True)),
            (
                "data_change_ack_hash",
                sa.Column("data_change_ack_hash", sa.Text(), nullable=True),
            ),
        ):
            if column in tag_columns and column not in line_columns:
                op.add_column("price_tag_request_lines", spec)
        if "pinned_tag_data" in tag_columns and "pinned_tag_data" not in line_columns:
            conn.execute(
                sa.text(
                    "UPDATE price_tag_request_lines l "
                    "SET pinned_tag_data = t.pinned_tag_data, pinned_at = t.pinned_at, "
                    "    data_change_ack_hash = t.data_change_ack_hash "
                    "FROM price_tag_request_tags t "
                    "WHERE t.line_id = l.id AND t.pinned_tag_data IS NOT NULL"
                )
            )
        op.drop_table("price_tag_request_tags")
    if "price_tag_guarded_classes" in {
        c["name"] for c in inspector.get_columns("system_settings")
    }:
        op.drop_column("system_settings", "price_tag_guarded_classes")
    if inspector.has_table("price_tag_request_line_parts"):
        op.drop_table("price_tag_request_line_parts")
    for column in ("package_warning", "combo_id"):
        if column in line_columns:
            op.drop_column("price_tag_request_lines", column)
    if inspector.has_table("product_combo_parts"):
        op.drop_table("product_combo_parts")
    if inspector.has_table("product_combos"):
        op.drop_table("product_combos")
