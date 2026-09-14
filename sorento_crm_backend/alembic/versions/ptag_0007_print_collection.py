"""r9 S2 + S3: pinned change requests, the print choice and the collection hand-over.

One revision for two slices because they share a table's worth of DDL and a
single deploy: the review comments table (D4), the print choice and collection
columns (D7/D9), the auto-collect setting (D10) and its scheduled task (D11),
plus the data step that retires ``ready`` (D8).

The two data steps are NAMED functions rather than inline SQL. ``blank_session``
builds the schema from ``Base.metadata``, so a migration's data step is only
testable by importing the revision and calling it (precedent:
``487_chatbot_warehouse_cue``).

Revision ID: ptag_0007_print_collection
Revises: 511_committed_v_line_owed
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "ptag_0007_print_collection"
down_revision = "511_committed_v_line_owed"
branch_labels = None
depends_on = None


def map_ready_rows_to_approved(bind) -> int:
    """``ready`` is retired (D8): every row that carried it becomes ``approved``.

    It said a PDF existed and nothing about whether anybody had the tags. The
    office print now records the hand-over instead, and a self print simply
    ends at approved - which is what these rows were.

    Returns the number of rows moved, so the caller (and its test) can say.
    """
    result = bind.execute(
        text(
            "UPDATE price_tag_requests SET status = 'approved' WHERE status = 'ready'"
        )
    )
    return result.rowcount or 0


def seed_auto_collect_task(bind) -> None:
    """The hourly sweep that closes an untouched hand-over (D11).

    Same shape as ``promotion_active_window``: enabled, hourly, idempotent.
    The sweep itself reads the configured days and does nothing at 0.
    """
    # An explicit id: `scheduled_tasks.id` is a plain UUID column whose default
    # lives in Python, not in the database, so an INSERT that omits it violates
    # the not-null constraint wherever the schema was built from the models.
    bind.execute(
        text(
            """
            INSERT INTO scheduled_tasks (
                id, key, name, description, enabled, interval_unit, interval_value,
                timezone, start_at, next_run_at, created_at, updated_at
            ) VALUES (
                :task_id,
                'price_tag_auto_collect',
                'Price tag auto collect',
                'Marks a price tag request collected once it has been ready for '
                'collection longer than the configured number of days.',
                true,
                'hours',
                1,
                'UTC',
                NULL,
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc'
            )
            ON CONFLICT (key) DO NOTHING
            """
        ),
        {"task_id": str(uuid.uuid4())},
    )


def backfill_review_round(bind) -> int:
    """``review_round`` for every row that predates the counter (r9 leftover R1).

    The counter is the number of ``Marked proof ready`` page-version snapshots
    this request's own design carries, floored at 1 once the request has
    actually been sent for review (``proof_ready`` onward) - a floor of 0
    there would read as "never sent" for a row that plainly was. A row that
    never reached review, or is terminal with no design at all, keeps
    whatever the snapshot count says, which is 0 when there is no design.

    Returns the number of rows touched.
    """
    result = bind.execute(
        text(
            """
            UPDATE price_tag_requests r
            SET review_round = GREATEST(
                COALESCE(
                    (
                        SELECT COUNT(*)
                        FROM page_version pv
                        WHERE pv.page_id = r.page_id
                          AND pv.commit_message = 'Marked proof ready'
                    ),
                    0
                ),
                CASE
                    WHEN r.status IN (
                        'proof_ready', 'changes_requested', 'approved',
                        'ready_for_collection', 'collected'
                    ) THEN 1
                    ELSE 0
                END
            )
            """
        )
    )
    return result.rowcount or 0


def upgrade() -> None:
    # --- S2/D4: the pinned change requests themselves -----------------------
    op.create_table(
        "price_tag_review_comments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("price_tag_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "line_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("price_tag_request_lines.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("round", sa.Integer(), nullable=False, server_default="1"),
        # Fractions of the TAG box, never page millimetres.
        sa.Column("x", sa.Numeric(6, 4), nullable=True),
        sa.Column("y", sa.Numeric(6, 4), nullable=True),
        sa.Column("w", sa.Numeric(6, 4), nullable=True),
        sa.Column("h", sa.Numeric(6, 4), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "author_contact_id",
            sa.Text(),
            sa.ForeignKey("respond_contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "author_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column(
            "resolved_by_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=False),
            # The mixin's own column carries this FK; a table created without
            # it takes rows the rest of the schema would refuse.
            sa.ForeignKey("companies.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_ptag_review_comments_request_id",
        "price_tag_review_comments",
        ["request_id"],
    )
    op.create_index(
        "ix_ptag_review_comments_line_id", "price_tag_review_comments", ["line_id"]
    )
    op.create_index(
        "ix_price_tag_review_comments_company_id",
        "price_tag_review_comments",
        ["company_id"],
    )

    # --- S3/D7 + D9: who prints, and the hand-over --------------------------
    op.add_column(
        "price_tag_requests", sa.Column("print_by", sa.String(8), nullable=True)
    )
    op.add_column(
        "price_tag_requests",
        sa.Column("ready_for_collection_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        "price_tag_requests",
        sa.Column("collected_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        "price_tag_requests",
        sa.Column(
            "collected_by_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "price_tag_requests",
        sa.Column(
            "collected_by_contact_id",
            sa.Text(),
            sa.ForeignKey("respond_contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "price_tag_requests",
        sa.Column(
            "collected_auto", sa.Boolean(), nullable=False, server_default="false"
        ),
    )

    # --- S2/D4: the review round, counted not derived -----------------------
    # Derived from the "Marked proof ready" snapshots, the round never moved:
    # that snapshot is only written when a draft exists, and the designer's own
    # CTA saves first, so the send usually skipped it - every round came back
    # as 1, the assignee's bell deduplicated every later round away and the
    # salesperson's confirmation counted the wrong send.
    op.add_column(
        "price_tag_requests",
        sa.Column("review_round", sa.Integer(), nullable=False, server_default="0"),
    )

    # --- S3/D10: how long an untouched hand-over waits ----------------------
    op.add_column(
        "system_settings",
        sa.Column(
            "price_tag_auto_collect_days",
            sa.Integer(),
            nullable=False,
            server_default="7",
        ),
    )

    bind = op.get_bind()
    map_ready_rows_to_approved(bind)
    seed_auto_collect_task(bind)
    backfill_review_round(bind)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text("DELETE FROM scheduled_tasks WHERE key = 'price_tag_auto_collect'")
    )
    op.drop_column("system_settings", "price_tag_auto_collect_days")
    for column in (
        "review_round",
        "collected_auto",
        "collected_by_contact_id",
        "collected_by_user_id",
        "collected_at",
        "ready_for_collection_at",
        "print_by",
    ):
        op.drop_column("price_tag_requests", column)
    op.drop_index(
        "ix_price_tag_review_comments_company_id",
        table_name="price_tag_review_comments",
    )
    op.drop_index(
        "ix_ptag_review_comments_line_id", table_name="price_tag_review_comments"
    )
    op.drop_index(
        "ix_ptag_review_comments_request_id", table_name="price_tag_review_comments"
    )
    op.drop_table("price_tag_review_comments")
