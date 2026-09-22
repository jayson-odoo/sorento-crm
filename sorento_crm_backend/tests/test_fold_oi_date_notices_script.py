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

from .test_order_inquiry_handshake import NOW, WAS, _raise_one_row, _uid, api, world

import scripts.fold_oi_date_notices as fold_script

__all__ = ["api", "world"]  # re-exported fixture; keeps linters from calling it unused


def _notice_and_buy_row(
    api, *, qty="10", verb=IV_ADVANCE, note="Was 2026-08-25", notice_date=NOW
):
    """A live buy row plus a live ADVANCE/DELAY notice row on the SAME so_line_id - the
    duplicate the script folds.

    Review round (22 Sep): the notice carries the NEW date and the buy row still carries
    the OLD one, which is the whole shape on prod - the notice is the ONLY row that ever
    said the date had moved, so a fold that cancels it without moving the buy row loses
    the move entirely. `notice_date=None` seeds the one shape the script must refuse:
    a notice with no date of its own to hand over."""
    _client, world = api
    fixture = _raise_one_row(api, qty=qty)
    buy_row = fixture["row"]
    assert buy_row.delivery_date == WAS, buy_row.delivery_date
    notice = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=buy_row.order_inquiry_id,
        so_line_id=buy_row.so_line_id, item_code=buy_row.item_code, qty=Decimal(qty),
        delivery_date=notice_date, verb=verb, state=INQUIRY_RAISED,
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

    # AC-B2-11: the notice's own delivery date is on the reported line, so a dry run can
    # be read for WHERE each buy row is about to be moved to, not only where it sits.
    reported = next(
        pair for pair in pairs if pair.get("buy_row_id") == str(seeded["buy_row"].id)
    )
    assert reported["notice_date"] == NOW.isoformat(), reported
    assert reported["buy_row_date"] == WAS.isoformat(), reported

    world.db.expire_all()
    world.db.refresh(seeded["notice"])
    world.db.refresh(seeded["buy_row"])
    assert seeded["notice"].state != INQUIRY_CANCELLED, "dry run changes nothing"
    assert seeded["buy_row"].previous_delivery_date is None, "dry run changes nothing"
    assert seeded["buy_row"].changed_at is None, "dry run changes nothing"
    assert seeded["buy_row"].delivery_date == WAS, "dry run changes nothing"


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
    # Review round (22 Sep): the NOTICE was the only row carrying the new date, so the
    # fold has to hand it over - a buy row left on the old date with the notice cancelled
    # would have lost the date move the notice existed to announce.
    assert seeded["buy_row"].delivery_date == NOW, "the buy row ends on the notice's date"
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
    assert seeded["buy_row"].delivery_date == WAS, "buy row untouched"
    assert report["skipped_no_was"] == 1, report


def test_fold_script_apply_skips_a_notice_with_no_delivery_date_of_its_own(api):
    """Review round (22 Sep). The notice is the only row carrying the NEW date, so a
    notice that has none has nothing to hand over: cancelling it would lose the move it
    announced and leave the buy row reading as though the date had never changed. Left
    alone and counted, the same rule as a notice with no parseable "Was" date above."""
    seeded = _notice_and_buy_row(
        api, qty="8", verb=IV_DELAY, note="Was 2026-08-25", notice_date=None
    )
    world = seeded["world"]

    report = fold_script.run(world.db, apply=True)
    world.db.commit()

    world.db.expire_all()
    world.db.refresh(seeded["notice"])
    world.db.refresh(seeded["buy_row"])
    assert seeded["notice"].state != INQUIRY_CANCELLED, "no date to hand over, left alone"
    assert seeded["buy_row"].delivery_date == WAS, "buy row untouched"
    assert seeded["buy_row"].previous_delivery_date is None, "buy row untouched"
    assert report["skipped_no_notice_date"] == 1, report


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
