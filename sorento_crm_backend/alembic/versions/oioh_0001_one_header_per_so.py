"""One header per SO: fold every planning_change_batch header onto the order's own
amendment_id IS NULL header (PLAN-oi-worklist-one-header.md, S3, AC-OH-34).

`derive_for_book_change` used to mint a synthetic `so_amendments` row
(`from_version_kind='planning_change_batch'`) and its own `order_inquiries` header for
every planning-change batch apply, on the theory that the DB-level singleton on
`amendment_id IS NULL` per sales order would otherwise collide with whatever `confirm()`
had just written in the same apply. It never did - `ensure_inquiry` returns the exact
header `confirm()` wrote earlier in the same apply - so that header was pure duplication:
one sales order carrying two order inquiry numbers (prod: OI-000477 and OI-000734 on
SO314593, the origin case this lane fixes). As of this revision `derive_for_book_change`
appends straight onto the order's own null-amendment header, so this migration is a
one-time cleanup of what the OLD code path already wrote.

S3 (Opus review round 1): `_fold` below is PLAIN SQL, not a call into the live service -
a migration that imports `app.services.*` couples a permanent, replayable artifact to
code that will keep changing long after this revision ships, and a later refactor of
`project_order_inquiry_service.py` (a rename, a signature change, an import it now pulls
in) would silently break `alembic upgrade head` on a fresh database. For every
`order_inquiries` row whose amendment is `planning_change_batch`: find or mint the
order's own null header (minted copies `company_id`/`state`/`raised_by`/`raised_at` off
the oldest header being folded, and mints its own `inquiry_no` the same way
`next_inquiry_no`/`_stamp_inquiry_no` do - highest already issued for the company, plus
one), move its rows onto that header, then delete the emptied header and its synthetic
amendment. Row ids, links, claims and handover records are all untouched - only
`order_inquiry_rows.order_inquiry_id` moves. Idempotent: a second run finds no
`planning_change_batch` header left and does nothing.

Reviewer round 1 S4 / round 2 item 2: a purchasing task `_hand_to_purchasing` raised off
the folded header (`projects.tasks.linked_entity_id`) is RE-POINTED at the survivor when
the survivor holds none of its own, or DELETED when the survivor already has one - a
header that reused an existing null header (the ordinary case) already got its own task
from `confirm()`'s own raise, and re-pointing the batch header's task on top would leave
the survivor carrying two.

Downgrade is a no-op: recreating the synthetic per-apply headers this revision folds away
would mean inventing which rows belonged to which now-deleted batch header, which nothing
after this revision records - there is no way back that is not itself a guess.

Revision ID: oioh_0001_one_header_per_so
Revises: undo_0003_journal_sql_null
Create Date: 2026-09-17
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger("alembic.oioh_0001")

revision = "oioh_0001_one_header_per_so"
down_revision = "undo_0003_journal_sql_null"
branch_labels = None
depends_on = None

_INQUIRY_NO_PREFIX = "OI-"
_INQUIRY_NO_DIGITS = 6


def _fold(connection) -> int:
    """The one-time cleanup itself. `connection` is any SQLAlchemy `Connection` - the
    migration's own bind, or a test's. Returns the number of headers folded.
    """
    batch_headers = connection.execute(
        sa.text(
            """
            SELECT oi.id, oi.company_id, oi.project_sales_order_id, oi.amendment_id,
                   oi.state, oi.raised_by, oi.raised_at
            FROM projects.order_inquiries oi
            JOIN projects.so_amendments a ON a.id = oi.amendment_id
            WHERE a.from_version_kind = 'planning_change_batch'
            ORDER BY oi.raised_at ASC NULLS LAST, oi.id ASC
            """
        )
    ).fetchall()

    folded = 0
    for header in batch_headers:
        target_id = connection.execute(
            sa.text(
                """
                SELECT id FROM projects.order_inquiries
                WHERE project_sales_order_id = :pso_id AND amendment_id IS NULL
                """
            ),
            {"pso_id": header.project_sales_order_id},
        ).scalar()

        if target_id is None:
            # Mint one, the same way `_stamp_inquiry_no`/`next_inquiry_no` do: highest
            # `OI-######` already issued for the company, plus one. Copies
            # company_id/state/raised_by/raised_at off the header being folded (the
            # oldest, per the ORDER BY above) rather than leaving them at whatever an
            # empty header would default to.
            latest = connection.execute(
                sa.text(
                    """
                    SELECT inquiry_no FROM projects.order_inquiries
                    WHERE company_id = :company_id AND inquiry_no LIKE :prefix
                    ORDER BY length(inquiry_no) DESC, inquiry_no DESC
                    LIMIT 1
                    """
                ),
                {"company_id": header.company_id, "prefix": f"{_INQUIRY_NO_PREFIX}%"},
            ).scalar()
            tail = (latest or "")[len(_INQUIRY_NO_PREFIX):]
            highest = int(tail) if tail.isdigit() else 0
            inquiry_no = f"{_INQUIRY_NO_PREFIX}{highest + 1:0{_INQUIRY_NO_DIGITS}d}"
            target_id = connection.execute(
                sa.text(
                    """
                    INSERT INTO projects.order_inquiries
                        (id, company_id, inquiry_no, project_sales_order_id,
                         amendment_id, state, raised_by, raised_at)
                    VALUES
                        (gen_random_uuid(), :company_id, :inquiry_no, :pso_id, NULL,
                         :state, :raised_by, :raised_at)
                    RETURNING id
                    """
                ),
                {
                    "company_id": header.company_id,
                    "inquiry_no": inquiry_no,
                    "pso_id": header.project_sales_order_id,
                    "state": header.state,
                    "raised_by": header.raised_by,
                    "raised_at": header.raised_at,
                },
            ).scalar()

        connection.execute(
            sa.text(
                """
                UPDATE projects.order_inquiry_rows
                SET order_inquiry_id = :target
                WHERE order_inquiry_id = :old
                """
            ),
            {"target": target_id, "old": header.id},
        )
        # Reviewer S4 / round 2 item 2: a purchasing task raised off the folded header
        # (`_hand_to_purchasing`'s `ProjectTask.linked_entity_type='order_inquiry'`)
        # still names it by id - re-point it, or its "Open in Order Inquiries" link
        # would 404 the moment the header underneath it is deleted below. But when the
        # SURVIVOR already carries its own task (the ordinary case - it existed before
        # this fold and `confirm()`'s own raise already handed one off for it),
        # re-pointing would give the survivor two - the folded header's task is deleted
        # instead, since the survivor's own task already says everything it said.
        target_has_task = (
            connection.execute(
                sa.text(
                    """
                    SELECT 1 FROM projects.tasks
                    WHERE linked_entity_type = 'order_inquiry' AND linked_entity_id = :target
                    LIMIT 1
                    """
                ),
                {"target": target_id},
            ).first()
            is not None
        )
        if target_has_task:
            connection.execute(
                sa.text(
                    """
                    DELETE FROM projects.tasks
                    WHERE linked_entity_type = 'order_inquiry' AND linked_entity_id = :old
                    """
                ),
                {"old": header.id},
            )
        else:
            connection.execute(
                sa.text(
                    """
                    UPDATE projects.tasks
                    SET linked_entity_id = :target
                    WHERE linked_entity_type = 'order_inquiry' AND linked_entity_id = :old
                    """
                ),
                {"target": target_id, "old": header.id},
            )
        connection.execute(
            sa.text("DELETE FROM projects.order_inquiries WHERE id = :old"),
            {"old": header.id},
        )
        if header.amendment_id:
            connection.execute(
                sa.text("DELETE FROM projects.so_amendments WHERE id = :aid"),
                {"aid": header.amendment_id},
            )
        folded += 1
    return folded


def upgrade() -> None:
    connection = op.get_bind()
    folded = _fold(connection)
    logger.info("oioh_0001: folded %d planning_change_batch header(s)", folded)


def downgrade() -> None:
    # No-op by design - see the module docstring. The synthetic per-apply headers this
    # revision folds away are gone, and nothing records enough to reconstruct which rows
    # belonged to which one.
    pass
