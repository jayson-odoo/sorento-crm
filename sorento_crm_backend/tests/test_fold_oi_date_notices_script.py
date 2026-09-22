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

from datetime import date, datetime
from decimal import Decimal

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
    IV_ADVANCE,
    IV_DELAY,
    IV_ORDER,
    OrderInquiryRow,
)

from .test_order_inquiry_handshake import NOW, WAS, _raise_one_row, _uid, api, world

import scripts.fold_oi_date_notices as fold_script

__all__ = ["api", "world"]  # re-exported fixture; keeps linters from calling it unused


def _notice_and_buy_row(
    api,
    *,
    qty="10",
    verb=IV_ADVANCE,
    note="Was 2026-08-25",
    notice_date=NOW,
    buy_ack=ACK_ACKNOWLEDGED,
):
    """A live buy row plus a live ADVANCE/DELAY notice row on the SAME so_line_id - the
    duplicate the script folds.

    Review round (22 Sep): the notice carries the NEW date and the buy row still carries
    the OLD one, which is the whole shape on prod - the notice is the ONLY row that ever
    said the date had moved, so a fold that cancels it without moving the buy row loses
    the move entirely. `notice_date=None` seeds the one shape the script must refuse:
    a notice with no date of its own to hand over.

    `buy_ack` is the buy row's own handshake (owner ruling, 22 Sep). It defaults to
    ACKNOWLEDGED - the duplicate this script folds is, on prod, overwhelmingly a row
    purchasing had already taken on - and `ACK_AWAITING` seeds the other half of the
    gate: a row nobody has read keeps its handshake and its NULL `changed_at`."""
    _client, world = api
    fixture = _raise_one_row(api, qty=qty)
    buy_row = fixture["row"]
    assert buy_row.delivery_date == WAS, buy_row.delivery_date
    assert buy_row.ack_state == ACK_AWAITING, "the confirm raises it awaiting"
    if buy_ack != ACK_AWAITING:
        buy_row.ack_state = buy_ack
        buy_row.acknowledged_by = world.buyer
        buy_row.acknowledged_at = datetime.utcnow()
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


def test_fold_script_apply_cancels_notice_and_stamps_an_acknowledged_buy_row(api):
    """AC-B2-12 on a row purchasing had already taken on: the fold restates an
    instruction they are holding, so it goes BACK to To confirm and stamps when it was
    amended under them - the same handshake gate `_stamp_date_move` reads (owner ruling,
    22 Sep)."""
    seeded = _notice_and_buy_row(
        api, qty="10", verb=IV_ADVANCE, note="Was 2026-08-25",
        buy_ack=ACK_ACKNOWLEDGED,
    )
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
    assert seeded["buy_row"].ack_state == ACK_CHANGED, "back to To confirm"
    assert seeded["buy_row"].changed_at is not None
    assert seeded["buy_row"].note and "Was" in seeded["buy_row"].note
    assert report["folded"] == 1, report


def test_fold_script_apply_leaves_an_awaiting_buy_rows_handshake_alone(api):
    """AC-B2-12's handshake gate, the other half (owner ruling, 22 Sep). A row nobody has
    read yet is still folded - the date, the Was columns and the note all land, because
    they are what the Was / Now table prints - but its handshake is not touched and
    `changed_at` stays NULL: the column answers "when CS last amended a row purchasing had
    already acknowledged", and there is no acknowledgement here to have amended under."""
    seeded = _notice_and_buy_row(
        api, qty="10", verb=IV_DELAY, note="Was 2026-08-25", buy_ack=ACK_AWAITING,
    )
    world = seeded["world"]

    report = fold_script.run(world.db, apply=True)
    world.db.commit()

    world.db.expire_all()
    world.db.refresh(seeded["notice"])
    world.db.refresh(seeded["buy_row"])
    assert seeded["notice"].state == INQUIRY_CANCELLED, "the duplicate is still folded"
    assert seeded["buy_row"].delivery_date == NOW, "the date still moves"
    assert seeded["buy_row"].previous_delivery_date == WAS
    assert seeded["buy_row"].note and "Was" in seeded["buy_row"].note
    assert seeded["buy_row"].ack_state == ACK_AWAITING, "handshake untouched"
    assert seeded["buy_row"].changed_at is None, "nobody had read it, so nothing to stamp"
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
    # The seed is ACKNOWLEDGED by default, so this is a REAL stamp rather than a NULL
    # compared against itself - the idempotency claim is worth nothing otherwise.
    stamped_changed_at = seeded["buy_row"].changed_at
    assert stamped_changed_at is not None

    second = fold_script.run(world.db, apply=True)
    world.db.commit()

    world.db.expire_all()
    world.db.refresh(seeded["buy_row"])
    assert seeded["buy_row"].note == stamped_note, "second run changes nothing further"
    assert seeded["buy_row"].previous_delivery_date == stamped_previous_date
    assert seeded["buy_row"].changed_at == stamped_changed_at
    assert second["folded"] == 0, second
    assert second["pairs"] == [], second


# ---------------------------------------------------------------------------
# Round 3: fold onto EVERY live buy row of the line, only on the Was date
# ---------------------------------------------------------------------------


def test_fold_script_apply_folds_every_live_buy_row_of_the_line(api):
    """Round-3 fix: a line may carry more than one live buy row (AC-B2-5's own shape) -
    the notice folds onto EVERY one of them still on the date it names, not only the
    first ever raised. Kill test: restoring the old `setdefault` (one buy row per line)
    turns this red - the second row is left bare, untouched and unstamped."""
    seeded = _notice_and_buy_row(api, qty="10", verb=IV_ADVANCE, note="Was 2026-08-25")
    world = seeded["world"]
    buy_row_a = seeded["buy_row"]

    buy_row_b = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=buy_row_a.order_inquiry_id,
        so_line_id=buy_row_a.so_line_id, item_code=buy_row_a.item_code, qty=Decimal("4"),
        delivery_date=WAS, verb=IV_ORDER, state=INQUIRY_RAISED, ack_state=ACK_AWAITING,
    )
    world.db.add(buy_row_b)
    world.db.commit()

    report = fold_script.run(world.db, apply=True)
    world.db.commit()

    world.db.expire_all()
    world.db.refresh(seeded["notice"])
    world.db.refresh(buy_row_a)
    world.db.refresh(buy_row_b)
    assert seeded["notice"].state == INQUIRY_CANCELLED
    for row in (buy_row_a, buy_row_b):
        assert row.delivery_date == NOW, (row.id, row.delivery_date)
        assert row.previous_delivery_date == WAS, row.id
        assert row.note and "Was" in row.note, row.id
    assert report["folded"] == 2, report


def test_fold_script_apply_leaves_a_buy_row_already_moved_off_the_was_date(api):
    """Round-3 recency guard: a buy row that no longer sits on the notice's OWN Was
    date - moved by some other means since the notice was raised - must never be
    folded onto, and never moved backwards. Left untouched and counted separately; the
    notice stays LIVE (not cancelled) so a person can still see and resolve it by hand.
    Kill test: dropping the `buy_row.delivery_date == was_date` recency check turns
    this red - the already-moved row gets re-stamped and the notice gets cancelled."""
    seeded = _notice_and_buy_row(api, qty="6", verb=IV_DELAY, note="Was 2026-08-25")
    world = seeded["world"]
    buy_row = seeded["buy_row"]
    later = date(2026, 9, 10)
    buy_row.delivery_date = later
    world.db.commit()

    report = fold_script.run(world.db, apply=True)
    world.db.commit()

    world.db.expire_all()
    world.db.refresh(seeded["notice"])
    world.db.refresh(buy_row)
    assert seeded["notice"].state != INQUIRY_CANCELLED, "left live for a person to see"
    assert buy_row.delivery_date == later, "never moved backwards"
    assert buy_row.previous_delivery_date is None, "buy row untouched"
    assert report["skipped_row_not_on_was_date"] == 1, report
    assert report["folded"] == 0, report
