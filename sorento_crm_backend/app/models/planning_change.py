"""A planning change batch: what a re-uploaded AutoCount SO book did to the plan.

`documentation/plans/scm/PLAN-so-book-diff-replanning.md` section 2. Two append-only
tables, both records rather than working state: a batch is born only when a re-uploaded
book, an ESB push or a manual edit changed a line that is HELD by the order's active
supply decision or carries a non-cancelled Order Inquiry row
(`PLAN-scm-planning-change-gate-held-or-inquiry.md`, AC-G1) - an adopted-but-undecided
line raises nothing, so no empty batch is ever created for it - and once born, a batch is
never deleted (AC-R10, "the batch is a record").

`projects.planning_change_batches` carries the upload's own counts; `projects
.planning_change_rows` carries one row per changed planned line, the facts behind it, the
composed suggestion (the re-run diffed against what the line holds), the planner's one
decision - Confirm or Amend - and what Apply did to it.

Kept in their own module rather than folded into `app.models.project_so` because this
plan's contract explicitly asks for a new file so it never collides with the concurrent
edits already in flight on that one.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base
from app.models.base import CompanyScopedMixin


def _uuid_str() -> str:
    return str(uuid.uuid4())


# The one source kind that exists today (PLAN section 3's own note); kept as a plain
# string column rather than an enum so a later trigger (a schedule-version confirm, say)
# is a new constant, not a migration.
PLANNING_CHANGE_SOURCE_SO_BOOK_UPLOAD = "so_book_upload"

# A sales order edited BY HAND on the detail screen, not re-uploaded as a book - the same
# reaction (`planning_change_service.build_batch`) a re-uploaded book gets, just a
# different trigger. `SalesOrderService._propagate_planning_change` is the only caller;
# plain string, no migration, same reason as the constant above.
PLANNING_CHANGE_SOURCE_SO_MANUAL_EDIT = "so_manual_edit"

# `PlanningChangeRow.decision` - the one choice per row (AC-C7): Confirm the composed
# suggestion, or Amend it. `None` (unset) is the default until CS takes one.
#
# `accept` / `keep` / `board` are RETIRED with the rule table that produced them, and
# migration 515 remaps every stored one (accept/keep -> confirm, board -> NULL): they
# existed because the suggestion was a VERB a row could agree with, and agreeing with a
# verb executed nothing. The suggestion is a composition now.
#
# `confirm` posts the row's own `composition_json`, pre-filled at build from the re-run
# (`composition_from_proposal`); `amend` takes the planner's own composition, built the
# same way `BoardAmendDialog` builds one, and requires it.
PLANNING_CHANGE_DECISION_CONFIRM = "confirm"
PLANNING_CHANGE_DECISION_AMEND = "amend"

# `PlanningChangeRow.applied_state`.
PLANNING_CHANGE_STATE_PENDING = "pending"
PLANNING_CHANGE_STATE_APPLIED = "applied"
PLANNING_CHANGE_STATE_FAILED = "failed"
PLANNING_CHANGE_STATE_SUPERSEDED = "superseded"

# `PlanningChangeRow.kind` - the AutoCount book's own diff, restated as the words AC-R02
# names. `CANCELLED` renamed from `CLOSED` and `PRODUCT_CHANGED` added
# (`documentation/plans/scm/PLAN-scm-change-management-one-engine.md`, Slice A rule 5):
# "closed" read as a delivery outcome, not a change kind, and a product swap on the same
# line used to fall apart into a closed row plus an unrelated added row.
PLANNING_CHANGE_KIND_DELAYED = "delayed"
PLANNING_CHANGE_KIND_ADVANCED = "advanced"
PLANNING_CHANGE_KIND_QTY_UP = "qty_up"
PLANNING_CHANGE_KIND_QTY_DOWN = "qty_down"
PLANNING_CHANGE_KIND_CANCELLED = "cancelled"
PLANNING_CHANGE_KIND_ADDED = "added"
PLANNING_CHANGE_KIND_PRODUCT_CHANGED = "product_changed"

# `PlanningChangeRow.suggested` - the verb the planner already knows from the board
# (section 0's rule table).
PLANNING_CHANGE_REACTION_KEEP = "keep"
PLANNING_CHANGE_REACTION_RELEASE = "release"
PLANNING_CHANGE_REACTION_REPLAN = "replan"
PLANNING_CHANGE_REACTION_REDUCE = "reduce"
PLANNING_CHANGE_REACTION_RETIRE = "retire"


class PlanningChangeBatch(Base, CompanyScopedMixin):
    """One re-upload's reaction to the plan: born, reviewed, applied (or not).

    `import_job_id` is nullable because a direct caller (a test, a script) may run the
    book apply outside the worker's job wrapper; the upload path always supplies it.
    """

    __tablename__ = "planning_change_batches"
    # Born straight into `projects` (migration 29d85dc3ccc3), after the schema move (354) -
    # no pre-move name to pin, so it adopts the `project_` prefix convention the way
    # `so_supply_decisions` did (`app/models/project_so.py`,
    # `test_projects_audit_entity_types.py::test_a_model_born_after_the_move_...`).
    __audit_entity_type__ = "project_planning_change_batches"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    import_job_id = Column(
        UUID(as_uuid=False), ForeignKey("import_jobs.id", ondelete="SET NULL"), nullable=True
    )
    upload_file_name = Column(String(255), nullable=True)
    source_kind = Column(
        String(32), nullable=False, server_default=PLANNING_CHANGE_SOURCE_SO_BOOK_UPLOAD
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    applied_at = Column(DateTime(timezone=False), nullable=True)
    applied_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    order_count = Column(Integer, nullable=False, server_default="0")
    line_count = Column(Integer, nullable=False, server_default="0")
    # What Apply did, once it has run (AC-R05, AC-R09): orders revised/failed, Order
    # Inquiry rows changed, lines back on the board, whether purchasing was told. `null`
    # until Apply runs - matches `PlanningChangeBatch.result` on the wire exactly.
    result_json = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_planning_change_batches_created_at", "created_at"),
        {"schema": "projects"},
    )


class PlanningChangeRow(Base, CompanyScopedMixin):
    """One changed planned line (AC-R02): what changed, what it holds, what is suggested.

    `project_line_id` is nullable: an `added` row (a new line on the book) has no mirror
    line yet, the same reason `core_sales_order_line.project_line_id` reads null for one -
    there is nothing to hold, so nothing to freeze (AC-R03).
    """

    __tablename__ = "planning_change_rows"
    # Same convention as the batch above: born after 354, no pre-move name to pin.
    __audit_entity_type__ = "project_planning_change_rows"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    batch_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.planning_change_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_sales_order_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    project_line_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.sales_order_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The CORE line (unqualified: `public.sales_order_lines`, not the module table of the
    # same bare name - the same convention `project_so.py` uses throughout).
    core_line_id = Column(
        UUID(as_uuid=False), ForeignKey("sales_order_lines.id", ondelete="SET NULL"), nullable=True
    )
    line_no = Column(Integer, nullable=True)
    item_code = Column(String(120), nullable=True)
    product_name = Column(String(255), nullable=True)
    kind = Column(String(16), nullable=False)
    from_json = Column(JSONB, nullable=True)
    to_json = Column(JSONB, nullable=True)
    days_moved = Column(Integer, nullable=True)
    # What the line's ACTIVE decision held at build time (AC-R02), `null` on a line with
    # none (AC-R03). Frozen, exactly like `SOSupplyDecision.line_snapshots`: what Apply
    # does is judged against what the row SAID it would do, not against whatever the
    # decision holds by the time somebody presses Apply.
    held_json = Column(JSONB, nullable=True)
    facts_json = Column(JSONB, nullable=False)
    # The Order Inquiry rows this line had already raised, at build time (AC-R02's "what the
    # active decision holds today" for purchasing's own worklist). Frozen the same reason
    # `held_json` is: a row already `actioned` today must read that way even if somebody
    # actions the live row before Apply runs.
    inquiry_rows_json = Column(JSONB, nullable=True)
    # RETIRED by Slice C, nullable since migration 515: a row built today leaves both NULL
    # and says what it suggests in `suggestion_json` instead. Kept, never dropped, because
    # every row written before that migration carries its own reaction here and a batch is
    # a record (AC-R10).
    suggested = Column(String(16), nullable=True)
    why = Column(Text, nullable=True)
    # The re-run at the line's NEW state, DIFFED against `held_json` - the whole suggestion
    # (Slice C rule 3): `{"components": [...], "late_days": n|null, "shortfall_qty": s|null}`,
    # each component carrying the sentence the server composed for it. The board prints
    # those sentences verbatim, so the words on screen are the engine's own.
    suggestion_json = Column(JSONB, nullable=True)
    # The board's own contribution for the line - the re-run itself, in the shape the board
    # renders, so the row, the amend dialog and the board never show two different answers.
    proposal_json = Column(JSONB, nullable=True)
    decision = Column(String(16), nullable=True)
    # The `ConfirmLine` body this row posts at Apply. PRE-FILLED at build from the re-run
    # (`composition_from_proposal`), so Confirm posts it unchanged and Amend edits it in the
    # reused `BoardAmendDialog`. `null` on a row the engine could compose nothing for.
    composition_json = Column(JSONB, nullable=True)
    applied_state = Column(
        String(16), nullable=False, server_default=PLANNING_CHANGE_STATE_PENDING
    )
    applied_reason = Column(Text, nullable=True)
    # Deep link to the cell of this line on the board (AC-R04's "Open on the board").
    board_link = Column(Text, nullable=False, server_default="")
    # What Apply wrote for this row alone: the OI row ids it touched, the board key it
    # freed. Read back beside `applied_reason` on the batch page after Apply.
    result_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_planning_change_rows_batch", "batch_id"),
        Index("ix_planning_change_rows_order", "project_sales_order_id"),
        {"schema": "projects"},
    )
