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
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_REJECTED,
    OrderInquiryLink,
    OrderInquiryRow,
)

from .test_order_inquiry_handshake import _open_po_line, _raise_one_row, api, world

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


def test_the_backfilled_timestamp_is_real_utc_not_a_wall_clock_offset(api):
    """B3 (review of PR #471). Alembic's own connection (`alembic/env.py`) never forces
    `-c timezone=utc` the way `app.database.engine` does, so a bare `now()` in a
    migration returns whatever the SESSION's timezone GUC says - measured here as
    `Asia/Seoul` on a connection that does not force one. `now() AT TIME ZONE 'utc'` is
    immune to that: it has to keep reading real UTC into this naive-UTC column whatever
    the session's own clock reads.
    """
    _client, world = api
    row = _raise_one_row(api)["row"]
    row.ack_state = ACK_AWAITING
    row.acknowledged_by = None
    row.acknowledged_at = None
    world.db.commit()

    # `SET LOCAL` is scoped to this transaction only, so the outer rollback undoes it -
    # a non-UTC session is exactly what alembic's own connection looks like today.
    world.db.execute(text("SET LOCAL timezone TO 'Asia/Seoul'"))
    _run_upgrade(world.db)

    world.db.expire_all()
    refreshed = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert refreshed.acknowledged_at is not None
    drift = abs(refreshed.acknowledged_at - datetime.utcnow())
    assert drift < timedelta(minutes=5), (
        f"acknowledged_at drifted {drift} from real UTC - the bare now() bug is back"
    )


def test_a_legacy_confirmed_rows_links_are_frozen_manual_before_the_backfill(api):
    """S2 (review of PR #471). A row a human Confirmed BEFORE this deploy holds links the
    SAME raise-time cascade writes for every row - `auto = true` regardless of who
    pressed Confirm - so left alone, `_cascade_only` reads a legacy confirmed row exactly
    like a fresh draft nobody has touched, and Auto link all / a purchase-order confirm
    could re-deal or retire a document a real Confirm press already promised. The
    migration must flip those links to `auto = false` before it runs the ack_state
    backfill.
    """
    _client, world = api
    _po, _po_line = _open_po_line(world, qty=50)
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    links = world.db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id).all()
    assert links, "the raise-time cascade has to have linked it for this test to mean anything"
    assert all(link.auto for link in links), "cascade links start auto=True"

    # Simulate a genuine PRE-S1 human Confirm press: acknowledged by a real actor, before
    # this migration ever ran (the shape `acknowledged_by IS NOT NULL` identifies).
    row.acknowledged_by = world.buyer
    row.acknowledged_at = datetime.utcnow() - timedelta(days=3)
    world.db.commit()

    _run_upgrade(world.db)

    world.db.expire_all()
    refreshed_links = (
        world.db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id).all()
    )
    assert refreshed_links
    assert all(link.auto is False for link in refreshed_links), (
        "a legacy human-confirmed row's links must read manual after the migration"
    )


def test_a_fresh_born_acknowledged_rows_links_are_left_alone(api):
    """The other half of S2: a row born-acknowledged with NO actor
    (`acknowledged_by IS NULL` - a system-attributed site, e.g. an unattended import) is
    not a legacy Confirm - its links stay `auto = true`, exactly the cascade-only reading
    S1's own `_cascade_only` needs to keep working for a row nobody has ever manually
    touched. `acknowledged_by IS NOT NULL` alone would ALSO match a fresh S1 row born
    acknowledged under the confirming actor (`_handshake_for_raise`'s own attribution) -
    but that ordering never happens in practice: this migration runs once, at deploy, over
    rows the OLD code wrote, and the old code never attributed a fresh raise to anybody."""
    _client, world = api
    _po, _po_line = _open_po_line(world, qty=50)
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    row.acknowledged_by = None
    world.db.commit()

    _run_upgrade(world.db)

    world.db.expire_all()
    refreshed_links = (
        world.db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id).all()
    )
    assert refreshed_links
    assert all(link.auto is True for link in refreshed_links)
