"""Order inquiry reserve events: allow a `reserved` event of 0 (`PLAN-oi-request-cs-
reserve.md` section 6e.4, security N3, AC-RS-78c).

"Reserve 0" is CS's recorded decision not to reserve a requested line. It writes no link
(a link of 0 would breach `ck_order_inquiry_links_qty_positive`, and there is nothing to
link), so without an event the line's History showed no trace of the decision. The
events table's own CHECK was `qty > 0`; it becomes `qty >= 0`. Only `commit_request`
writes a zero, and only as a `reserved` event.

Raw SQL with the same `_schema()` helper `oirs_0002_reserve_round2.py` carries (a raw
identifier is not rewritten by `schema_translate_map`). Idempotent: the constraint is
dropped IF EXISTS and re-added under the same name. Downgrade deletes the zero events
(the only rows the old CHECK refuses) and restores `qty > 0`.

Revision ID: oirs_0004_reserve_event_zero
Revises: oirs_0003_reserve_commit_tmpl
Create Date: 2026-09-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "oirs_0004_reserve_event_zero"
down_revision = "oirs_0003_reserve_commit_tmpl"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_order_inquiry_reserve_events_qty_positive"


def _schema(bind, module: str) -> str:
    current = bind.exec_driver_sql("SELECT current_schema()").scalar()
    return module if current in (None, "public") else f"{current}_{module}"


def _set_check(bind, expression: str) -> None:
    projects = _schema(bind, "projects")
    bind.execute(
        sa.text(
            f'ALTER TABLE "{projects}".order_inquiry_reserve_events '
            f"DROP CONSTRAINT IF EXISTS {_CONSTRAINT}"
        )
    )
    bind.execute(
        sa.text(
            f'ALTER TABLE "{projects}".order_inquiry_reserve_events '
            f"ADD CONSTRAINT {_CONSTRAINT} CHECK ({expression})"
        )
    )


def upgrade() -> None:
    _set_check(op.get_bind(), "qty >= 0")


def downgrade() -> None:
    bind = op.get_bind()
    projects = _schema(bind, "projects")
    bind.execute(
        sa.text(f'DELETE FROM "{projects}".order_inquiry_reserve_events WHERE qty = 0')
    )
    _set_check(bind, "qty > 0")
