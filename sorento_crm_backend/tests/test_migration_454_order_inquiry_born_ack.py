"""AC-1.4 (`PLAN-scm-reorder-oi-feedback-1sep.md` S1, G4): the backfill migration.

Every pre-existing `awaiting` row becomes `acknowledged`, system-attributed
(`acknowledged_by IS NULL`). A `changed`, `acknowledged` or `rejected` row is left exactly
as it is - the migration's own docstring is explicit that only `awaiting` is in scope.

Driven through `upgrade()` against the real database inside a rolled-back transaction,
the same pattern `tests/test_migration_450_spec_rules_backfill.py` uses and for the same
reason: real rows via the ordinary raise (`test_order_inquiry_handshake`'s harness), then
the migration's own SQL run over the same connection.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_REJECTED,
    OrderInquiryRow,
)

from .test_order_inquiry_handshake import _raise_one_row, api, world

__all__ = ["api", "world"]  # re-exported fixtures; keeps linters from calling them unused

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "454_order_inquiry_born_ack.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_454", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        module.upgrade()


def test_every_awaiting_row_is_acknowledged_system_attributed(api):
    _client, world = api
    row = _raise_one_row(api)["row"]
    row.ack_state = ACK_AWAITING
    row.acknowledged_by = None
    row.acknowledged_at = None
    world.db.commit()

    _run_upgrade(world.db)

    world.db.expire_all()
    refreshed = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert refreshed.ack_state == ACK_ACKNOWLEDGED
    assert refreshed.acknowledged_by is None, "system attribution: no actor to name"
    assert refreshed.acknowledged_at is not None


def test_a_changed_row_is_left_exactly_as_it_is(api):
    _client, world = api
    row = _raise_one_row(api)["row"]
    row.ack_state = ACK_CHANGED
    row.changed_at = datetime.utcnow()
    row.acknowledged_by = world.cs_user
    world.db.commit()
    stamped_at = row.changed_at

    _run_upgrade(world.db)

    world.db.expire_all()
    refreshed = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert refreshed.ack_state == ACK_CHANGED
    assert refreshed.changed_at == stamped_at


def test_a_rejected_row_is_left_exactly_as_it_is(api):
    _client, world = api
    fixture = _raise_one_row(api)
    row = fixture["row"]
    from .test_order_inquiry_handshake import LIST, _as_purchasing

    with _as_purchasing(world) as buyer:
        response = buyer.post(
            f"{LIST}/{row.id}/reject", json={"reason": "No supplier"}
        )
        assert response.status_code == 200, response.text
    world.db.commit()

    _run_upgrade(world.db)

    world.db.expire_all()
    refreshed = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert refreshed.ack_state == ACK_REJECTED
    assert refreshed.rejected_reason == "No supplier"


def test_an_already_acknowledged_row_is_untouched(api):
    _client, world = api
    row = _raise_one_row(api)["row"]
    assert row.ack_state == ACK_ACKNOWLEDGED, "born acknowledged already"
    stamped_by, stamped_at = row.acknowledged_by, row.acknowledged_at

    _run_upgrade(world.db)

    world.db.expire_all()
    refreshed = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert refreshed.acknowledged_by == stamped_by
    assert refreshed.acknowledged_at == stamped_at
