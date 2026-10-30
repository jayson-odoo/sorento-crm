"""OI-AUTO-CONFIRM AC-AC-17c / 23 (owner 30 Oct ~10:35): rows a PERSON confirmed before this
ships stay Done through the backfill, as a manual Confirm; system-done rows are never frozen.

`backfill_auto_confirm(connection)` must, for an `acknowledged` row with `acknowledged_by` set,
write `ack_override = 'confirmed'`, `ack_override_by = acknowledged_by`,
`ack_override_at = acknowledged_at`, and leave the row `acknowledged` whatever its cover.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import text

from app.models.project_so import ACK_ACKNOWLEDGED, ACK_AWAITING, ACK_CHANGED
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from . import test_order_inquiry_bundles as _bundles
from .test_oi_auto_confirm import _new_user, _reload
from .test_oi_auto_confirm_backfill import STAMP, _po_link, _read
from .test_oi_auto_confirm_backfill import bundle_world  # noqa: F401  (fixture)
from .test_order_inquiry_handshake import _open_po_line, _raise_one_row, _settle
from .test_order_inquiry_handshake import api, world  # noqa: F401  (fixtures)


def _person_confirm(db, row, user_id):
    db.execute(
        text(
            f"UPDATE {_bundles.P}.order_inquiry_rows SET ack_state = 'acknowledged', "
            "acknowledged_by = :u, acknowledged_at = :at WHERE id = :i"
        ),
        {"u": user_id, "at": STAMP, "i": row.id},
    )
    db.flush()


def _assert_kept(row, user_id):
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert row.ack_override == "confirmed"
    assert row.ack_override_by == user_id
    assert row.ack_override_at == row.acknowledged_at == STAMP
    assert row.acknowledged_by == user_id


def test_a_person_confirmed_row_with_no_link_stays_done_as_a_manual_confirm(bundle_world):
    from app.services.oi_auto_confirm_backfill import backfill_auto_confirm

    w = bundle_world
    user = _new_user(w.db)
    row = w.row("CKS1050", 10)
    _person_confirm(w.db, row, user)

    backfill_auto_confirm(w.db.connection())
    w.db.flush()

    _assert_kept(_read(w, row), user)


def test_a_person_confirmed_covered_row_also_gets_the_manual_confirm(bundle_world):
    from app.services.oi_auto_confirm_backfill import backfill_auto_confirm

    w = bundle_world
    user = _new_user(w.db)
    row = w.row("CKS1050", 10)
    _po_link(w, row, "CKS1050", 10)
    _person_confirm(w.db, row, user)

    backfill_auto_confirm(w.db.connection())
    w.db.flush()

    _assert_kept(_read(w, row), user)


def test_a_system_done_row_whose_cover_is_gone_is_decided_by_the_rule_and_never_frozen(bundle_world):
    from app.services.oi_auto_confirm_backfill import backfill_auto_confirm

    w = bundle_world
    row = w.row("CKS1050", 10)
    w.db.execute(
        text(
            f"UPDATE {_bundles.P}.order_inquiry_rows SET ack_state = 'acknowledged', "
            "acknowledged_by = NULL, acknowledged_at = :at WHERE id = :i"
        ),
        {"at": STAMP, "i": row.id},
    )
    w.db.flush()

    backfill_auto_confirm(w.db.connection())
    w.db.flush()

    r = _read(w, row)
    assert r.ack_state == ACK_AWAITING
    assert r.ack_override is None and r.ack_override_by is None and r.ack_override_at is None


def test_an_awaiting_covered_row_goes_done_by_the_system_with_no_override(bundle_world):
    from app.services.oi_auto_confirm_backfill import backfill_auto_confirm

    w = bundle_world
    row = w.row("CKS1050", 10, ack_state=ACK_AWAITING)
    _po_link(w, row, "CKS1050", 10)

    backfill_auto_confirm(w.db.connection())
    w.db.flush()

    r = _read(w, row)
    assert r.ack_state == ACK_ACKNOWLEDGED and r.acknowledged_by is None
    assert r.ack_override is None


def test_a_second_run_returns_zero_with_person_confirmed_rows_present(bundle_world):
    from app.services.oi_auto_confirm_backfill import backfill_auto_confirm

    w = bundle_world
    user = _new_user(w.db)
    kept = w.row("CKS1050", 10)
    _person_confirm(w.db, kept, user)
    covered = w.row("X", 5, ack_state=ACK_AWAITING)
    _po_link(w, covered, "X", 5)
    connection = w.db.connection()

    first = backfill_auto_confirm(connection)
    w.db.flush()
    second = backfill_auto_confirm(connection)
    w.db.flush()

    assert first > 0
    assert second == 0
    _assert_kept(_read(w, kept), user)


def test_after_the_backfill_links_come_and_go_but_a_cs_amendment_hands_the_row_to_the_rule(api):
    from app.services.oi_auto_confirm_backfill import backfill_auto_confirm

    _client, w = api
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    user = _new_user(w.db)
    _person_confirm(w.db, row, user)
    backfill_auto_confirm(w.db.connection())
    w.db.flush()
    assert _reload(w.db, row).ack_override == "confirmed"

    svc = ProjectOrderInquiryService(w.db)
    _po, line = _open_po_line(w, qty=50)
    svc.place_on_po_allocations(
        str(row.id), [{"po_line_id": str(line.id), "qty": "10"}], actor_user_id=user
    )
    w.db.commit()
    assert _reload(w.db, row).ack_state == ACK_ACKNOWLEDGED
    svc.unplace(str(row.id), actor_user_id=user)
    w.db.commit()
    r = _reload(w.db, row)
    assert r.ack_state == ACK_ACKNOWLEDGED, "losing the link does not reopen a manual Confirm"
    assert r.ack_override == "confirmed"

    svc.place_on_po_allocations(
        str(row.id), [{"po_line_id": str(line.id), "qty": "10"}], actor_user_id=user
    )
    w.db.commit()
    _settle(w, fixture, qty="14")
    r = _reload(w.db, row)
    assert r.ack_override is None and r.ack_override_by is None and r.ack_override_at is None
    assert r.ack_state == ACK_CHANGED, "10 linked of 14: the rule decides"
