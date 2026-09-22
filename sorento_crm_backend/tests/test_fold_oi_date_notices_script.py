"""S2 cleanup script - `scripts/fold_oi_date_notices.py`
(`PLAN-board-oi-mechanical-22sep.md`, `board-oi-mechanical-22sep-acceptance-criteria.md`,
AC-B2-11/12/13).

TEST-FIRST: the script does not exist yet, so the module import below fails at collection
- ImportError/ModuleNotFoundError, the right red for a slice not yet built, and every test
in this file reports it.

Interface this pins (the coder's to satisfy, not a copy of an existing one - no fold
script exists anywhere in this codebase to match): `run(db, *, apply: bool = False) ->
dict` with keys `pairs` (one dict per live ADVANCE/DELAY row whose `so_line_id` carries a
non-cancelled buy row: `oi_number`, `item_code`, `qty`, `notice_date`, `buy_row_id`,
`buy_row_date`), `folded` (count actually folded) and `skipped_no_was` (count left alone
for lacking a parseable "Was <date>" in the notice's own note). `--dry-run` (default) /
`--apply` on the CLI are the script's own concern (argv parsing); these tests drive the
service-shaped `run()` directly, on a private session, the way `tests/test_backfill_
retire_superseded_order_inquiry_rows.py` drives its own backfill's `run`.

Runs on the REAL database (`test_order_inquiry_handshake`'s `world`/`api`, rolled back via
a savepoint): `scm.committed_v` and the handshake columns live only in the migrated
schema. Every row is seeded here behind the ZZT marker - CI's database has no data.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.models.project_so import (
    ACK_AWAITING,
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
    IV_ADVANCE,
    IV_DELAY,
    OrderInquiryRow,
)

from .test_order_inquiry_handshake import WAS, _raise_one_row, _uid, api, world

import scripts.fold_oi_date_notices as fold_script

__all__ = ["api", "world"]  # re-exported fixture; keeps linters from calling it unused


def _notice_and_buy_row(api, *, qty="10", verb=IV_ADVANCE, note="Was 2026-08-25"):
    """A live buy row plus a live ADVANCE/DELAY notice row on the SAME so_line_id - the
    duplicate the script folds."""
    _client, world = api
    fixture = _raise_one_row(api, qty=qty)
    buy_row = fixture["row"]
    notice = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=buy_row.order_inquiry_id,
        so_line_id=buy_row.so_line_id, item_code=buy_row.item_code, qty=Decimal(qty),
        delivery_date=buy_row.delivery_date, verb=verb, state=INQUIRY_RAISED,
        ack_state=ACK_AWAITING, note=note,
    )
    world.db.add(notice)
    world.db.commit()
    return {"world": world, "fixture": fixture, "buy_row": buy_row, "notice": notice}


# ---------------------------------------------------------------------------
# AC-B2-11: dry run
# ---------------------------------------------------------------------------


def test_fold_script_dry_run_lists_pairs_and_changes_nothing(api):
    seeded = _notice_and_buy_row(api, qty="10", verb=IV_ADVANCE, note="Was 2026-08-25")
    world = seeded["world"]

    report = fold_script.run(world.db, apply=False)

    pairs = report["pairs"]
    assert any(
        pair.get("buy_row_id") == str(seeded["buy_row"].id) for pair in pairs
    ), pairs

    world.db.expire_all()
    world.db.refresh(seeded["notice"])
    world.db.refresh(seeded["buy_row"])
    assert seeded["notice"].state != INQUIRY_CANCELLED, "dry run changes nothing"
    assert seeded["buy_row"].previous_delivery_date is None, "dry run changes nothing"
    assert seeded["buy_row"].changed_at is None, "dry run changes nothing"


# ---------------------------------------------------------------------------
# AC-B2-12: apply
# ---------------------------------------------------------------------------


def test_fold_script_apply_cancels_notice_and_stamps_buy_row(api):
    seeded = _notice_and_buy_row(api, qty="10", verb=IV_ADVANCE, note="Was 2026-08-25")
    world = seeded["world"]

    report = fold_script.run(world.db, apply=True)
    world.db.commit()

    world.db.expire_all()
    world.db.refresh(seeded["notice"])
    world.db.refresh(seeded["buy_row"])
    assert seeded["notice"].state == INQUIRY_CANCELLED
    assert "Folded into the buy row by script" in (seeded["notice"].note or "")
    assert seeded["buy_row"].previous_delivery_date == WAS
    assert seeded["buy_row"].changed_at is not None
    assert seeded["buy_row"].note and "Was" in seeded["buy_row"].note
    assert report["folded"] == 1, report


def test_fold_script_apply_skips_a_notice_with_no_was_date_and_reports_it(api):
    """AC-B2-12's second half: a notice whose note carries no parseable "Was <date>" is
    left alone and counted separately, never cancelled and never used to stamp the buy
    row - a script that guessed a date nobody wrote would be worse than leaving the
    duplicate standing."""
    seeded = _notice_and_buy_row(
        api, qty="6", verb=IV_DELAY, note="No previous delivery date"
    )
    world = seeded["world"]

    report = fold_script.run(world.db, apply=True)
    world.db.commit()

    world.db.expire_all()
    world.db.refresh(seeded["notice"])
    world.db.refresh(seeded["buy_row"])
    assert seeded["notice"].state != INQUIRY_CANCELLED, "no Was date to fold, left alone"
    assert seeded["buy_row"].previous_delivery_date is None, "buy row untouched"
    assert report["skipped_no_was"] == 1, report


# ---------------------------------------------------------------------------
# AC-B2-13: idempotent
# ---------------------------------------------------------------------------


def test_fold_script_apply_is_idempotent(api):
    seeded = _notice_and_buy_row(api, qty="10", verb=IV_ADVANCE, note="Was 2026-08-25")
    world = seeded["world"]

    fold_script.run(world.db, apply=True)
    world.db.commit()
    world.db.expire_all()
    world.db.refresh(seeded["buy_row"])
    stamped_note = seeded["buy_row"].note
    stamped_previous_date = seeded["buy_row"].previous_delivery_date
    stamped_changed_at = seeded["buy_row"].changed_at

    second = fold_script.run(world.db, apply=True)
    world.db.commit()

    world.db.expire_all()
    world.db.refresh(seeded["buy_row"])
    assert seeded["buy_row"].note == stamped_note, "second run changes nothing further"
    assert seeded["buy_row"].previous_delivery_date == stamped_previous_date
    assert seeded["buy_row"].changed_at == stamped_changed_at
    assert second["folded"] == 0, second
    assert second["pairs"] == [], second
