"""Repair legacy `undo_journal` rows: JSON literal null -> real SQL NULL.

Revision ID: undo_0003_journal_sql_null
Revises: undo_0002_seed_undone
Create Date: 2026-09-17

Hotfix companion to the model change in the same commit
(`app.models.project_so.SOSupplyDecision.undo_journal` now `JSONB(none_as_null=True)`):
before that column option existed, the two Core SQL clears in
`app.services.project_supply_undo_service` (`UndoJournal.attach`, `undo_last_confirm`)
wrote `.values(undo_journal=None)` and SQLAlchemy's JSON type serialised that Python
`None` VALUE as the JSON literal `null` rather than a SQL NULL. The column itself was
never NULL - it held a JSON scalar - so `_journalled_decision_clause`'s old
`undo_journal.isnot(None)` guard read it as present and Postgres's own
`jsonb_array_length` then threw (`InvalidParameterValue: cannot get array length of a
scalar`), 500ing the fulfilment planning board read for any order carrying one
(shipped to prod in #985 04:37Z).

The code fix (model + `_journalled_decision_clause` reading `jsonb_typeof(...) =
'array'`) stops the crash for every row from here on, including any future write that
still passes a bare Python `None` through. This migration is the one-time data repair
for rows the bug already wrote before this deploy: turn the JSON literal `null` back
into a real SQL NULL, so a raw `... IS NULL` read (or any future guard that assumes
"unjournalled" means SQL NULL) agrees with every row again.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "undo_0003_journal_sql_null"
down_revision = "undo_0002_seed_undone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "UPDATE projects.so_supply_decisions "
            "SET undo_journal = NULL "
            "WHERE jsonb_typeof(undo_journal) = 'null'"
        )
    )
    print(f"undo_0003: repaired {result.rowcount or 0} journal(s)")


def downgrade() -> None:
    # No-op: a real SQL NULL and a JSON literal `null` were always meant to be the
    # same "unjournalled" state (docstring on the `undo_journal` column). There is no
    # prior state to restore to - reintroducing JSON nulls would just be re-planting
    # the bug this migration exists to repair.
    pass
