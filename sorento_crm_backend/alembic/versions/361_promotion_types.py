"""Promotion types, with per-type behaviour after the end date.

Creates `promotion_types`, points `promotions` at it, seeds the five kinds
Sorento actually runs, and classifies the promotions already in the table from
their filenames.

The seed and the backfill are both idempotent: the seed inserts only what is
missing by `type_code`, and the backfill is a JOIN-based "set to the correct
value where it differs", so re-running corrects a previous run instead of
skipping rows it already touched. It never overwrites a `manual` row -- a human
correction outranks the classifier by definition.

Revision ID: 361_promotion_types
Revises: 357_merge_grn_spo_fm_heads
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "361_promotion_types"
down_revision = "357_merge_grn_spo_fm_heads"
branch_labels = None
depends_on = None


# (code, name, show_expired, year_end, max_age_days, markers, priority, is_default, sort, description)
SEED_TYPES = [
    (
        "special",
        "Special Promo",
        False,
        False,
        None,
        ["special"],
        10,
        False,
        10,
        "One-month / seasonal / clearance offer. Cannot be honoured after its end date.",
    ),
    (
        "pp",
        "PP Promo",
        True,
        True,
        None,
        ["pp"],
        20,
        False,
        20,
        "PP offer. Still usable after expiry until the end of the year it ended in.",
    ),
    (
        "focus_item",
        "Focus Item",
        True,
        True,
        None,
        ["focus", "focus item"],
        30,
        False,
        30,
        "Focus-item offer. Still usable after expiry until the end of the year it ended in.",
    ),
    (
        "a3_flyer",
        "A3 Flyer",
        True,
        False,
        180,
        ["a3", "a3 flyer"],
        40,
        False,
        40,
        "A3 flyer, usually a six-month run. Still usable for 180 days after it ends.",
    ),
    (
        "standard",
        "Standard Promo",
        True,
        True,
        None,
        [],
        99,
        True,
        99,
        "The default: a promotion whose name carries no marker. Usually three months, "
        "still usable after expiry until the end of the year it ended in.",
    ),
]


def upgrade():
    op.create_table(
        "promotion_types",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("type_code", sa.String(50), nullable=False, unique=True),
        sa.Column("type_name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("show_expired", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "expired_valid_until_year_end", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("expired_max_age_days", sa.Integer(), nullable=True),
        sa.Column("match_markers", JSONB(), nullable=False, server_default="[]"),
        sa.Column("match_priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "company_id",
            UUID(as_uuid=False),
            sa.ForeignKey("companies.id", name="fk_promotion_types_company_id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_promotion_types_match_priority", "promotion_types", ["match_priority"])
    op.create_index("ix_promotion_types_company_id", "promotion_types", ["company_id"])
    # One default type, enforced by the database rather than by whoever edits next.
    op.create_index(
        "uq_promotion_types_single_default",
        "promotion_types",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    op.add_column("promotions", sa.Column("promotion_type_id", UUID(as_uuid=False), nullable=True))
    op.add_column("promotions", sa.Column("promotion_type_source", sa.String(10), nullable=True))
    op.create_foreign_key(
        "fk_promotions_promotion_type_id",
        "promotions",
        "promotion_types",
        ["promotion_type_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_promotions_promotion_type_id", "promotions", ["promotion_type_id"])

    conn = op.get_bind()
    _seed_types(conn)
    _backfill_promotion_types(conn)


def _seed_types(conn):
    """Insert the five kinds Sorento runs, skipping any `type_code` already there."""
    for (
        code,
        name,
        show_expired,
        year_end,
        max_age,
        markers,
        priority,
        is_default,
        sort_order,
        description,
    ) in SEED_TYPES:
        conn.execute(
            sa.text(
                """
                INSERT INTO promotion_types (
                    id, type_code, type_name, description, show_expired,
                    expired_valid_until_year_end, expired_max_age_days,
                    match_markers, match_priority, is_default, sort_order
                )
                SELECT gen_random_uuid(), :code, :name, :description, :show_expired,
                       :year_end, :max_age, CAST(:markers AS jsonb), :priority,
                       :is_default, :sort_order
                WHERE NOT EXISTS (SELECT 1 FROM promotion_types WHERE type_code = :code)
                """
            ),
            {
                "code": code,
                "name": name,
                "description": description,
                "show_expired": show_expired,
                "year_end": year_end,
                "max_age": max_age,
                "markers": _json(markers),
                "priority": priority,
                "is_default": is_default,
                "sort_order": sort_order,
            },
        )


def _json(value) -> str:
    import json

    return json.dumps(value)


def _backfill_promotion_types(conn):
    """Classify the promotions already in the table from their descriptions.

    Runs the same word-boundary marker rule the runtime classifier uses, in SQL,
    so a fresh install and a migrated one agree. Rows a human has already typed
    (`promotion_type_source = 'manual'`) are left alone.
    """
    rows = conn.execute(
        sa.text(
            "SELECT id, type_code, match_markers, match_priority "
            "FROM promotion_types ORDER BY match_priority ASC, type_code ASC"
        )
    ).fetchall()
    if not rows:
        return
    default_row = conn.execute(
        sa.text("SELECT id FROM promotion_types WHERE is_default LIMIT 1")
    ).fetchone()

    promos = conn.execute(
        sa.text(
            "SELECT p.id, p.description, a.original_filename "
            "FROM promotions p "
            "LEFT JOIN LATERAL ("
            "  SELECT att.original_filename FROM promotion_attachments pa "
            "  JOIN attachments att ON att.id = pa.attachment_id "
            "  WHERE pa.promotion_id = p.id "
            "  ORDER BY pa.is_primary DESC, pa.sort_order ASC NULLS LAST LIMIT 1"
            ") a ON true "
            "WHERE p.promotion_type_source IS DISTINCT FROM 'manual'"
        )
    ).fetchall()

    import re

    def normalize(text):
        if not text:
            return ""
        return re.sub(r"[^A-Za-z0-9]+", " ", text).upper().strip()

    def classify(text):
        normalized = normalize(text)
        if normalized:
            for row in rows:
                markers = row[2] or []
                if not isinstance(markers, list):
                    continue
                for marker in markers:
                    if not isinstance(marker, str):
                        continue
                    marker_norm = normalize(marker)
                    if not marker_norm:
                        continue
                    pattern = r"(?<![A-Z0-9])" + re.escape(marker_norm) + r"(?![A-Z0-9])"
                    if re.search(pattern, normalized):
                        return row[0]
        return default_row[0] if default_row else None

    for promo_id, description, filename in promos:
        type_id = classify(filename or description)
        if type_id is None:
            continue
        conn.execute(
            sa.text(
                "UPDATE promotions SET promotion_type_id = :type_id, "
                "promotion_type_source = 'auto' "
                "WHERE id = :id AND (promotion_type_id IS DISTINCT FROM :type_id "
                "  OR promotion_type_source IS DISTINCT FROM 'auto')"
            ),
            {"type_id": type_id, "id": promo_id},
        )


def downgrade():
    op.drop_index("ix_promotions_promotion_type_id", table_name="promotions")
    op.drop_constraint("fk_promotions_promotion_type_id", "promotions", type_="foreignkey")
    op.drop_column("promotions", "promotion_type_source")
    op.drop_column("promotions", "promotion_type_id")
    op.drop_index("uq_promotion_types_single_default", table_name="promotion_types")
    op.drop_index("ix_promotion_types_company_id", table_name="promotion_types")
    op.drop_index("ix_promotion_types_match_priority", table_name="promotion_types")
    op.drop_table("promotion_types")
