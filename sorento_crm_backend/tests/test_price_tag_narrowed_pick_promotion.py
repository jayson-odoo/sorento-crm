"""PRICETAG-DISCONTINUED-PICK round 3: a pick that narrows a group past its promotion saves.

Crew pass on 07667140: the form auto-picks a line's promotion while a choice group is still
open, when any candidate counts as covering it (AC-S7-2). Picking an option the promotion does not
cover then left that promotion on the line, and Save answered 422 PROMOTION_NOT_AVAILABLE. Not
caused by discontinued products: any uncovered pick did it.

Rule: when the line's promotion covers one of the line's OWN combo options but nothing actually
on the line any more, the save drops the promotion (stores none) instead of refusing. Such a
promotion prices nothing on the line, so no price moves. Every other refusal stays a 422
(wrong audience, covers nothing at all: `test_portal_price_tag_revise.py`).
"""
from __future__ import annotations

import os

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.error_handler import AppException

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)


def _sink_with_taps(db, *, combo_sell=None):
    host = seed.product(db, "ZZNHOST", list_price="1000.00")
    taps = [seed.product(db, f"ZZNT{i}", list_price=f"{270 + i * 10}.00") for i in range(3)]
    fields = {"sell_price": combo_sell} if combo_sell is not None else {}
    cb = seed.combo(db, host, "ZZT sink + tap", parts=[{"product": p, "group": "Tap"} for p in taps], **fields)
    # The promotion covers ONLY the last tap, the way 8d2ff6a3 covers only SRTKT71SS-BL on dev.
    promo = seed.promotion(db, [(taps[2], "200.00")])
    return host, cb, taps, promo


def _picked(taps, index):
    return [{"product_id": taps[index].id, "role": "Tap", "candidates": []}]


def test_an_open_group_keeps_a_promotion_that_covers_one_of_its_candidates(db):
    host, cb, taps, promo = _sink_with_taps(db)
    request = seed.submit_one(
        db, host, cb, [{"role": "Tap", "candidates": [t.id for t in taps]}], promotion_id=promo.id
    )
    db.flush()
    assert request.lines[0].promotion_id == promo.id


def test_a_pick_outside_the_promotion_saves_and_drops_it(db):
    host, cb, taps, promo = _sink_with_taps(db)
    request = seed.submit_one(db, host, cb, _picked(taps, 0), promotion_id=promo.id)
    db.flush()
    line = request.lines[0]
    assert line.promotion_id is None
    assert [p.product_id for p in line.parts] == [taps[0].id]


def _row_without_ids(row):
    """The tag row with the ids that differ between two requests taken out."""
    skip = {"line_id", "tag_id", "request_id", "id", "promotion_id", "promotion_name", "promotion_expired_on"}
    if isinstance(row, dict):
        return {k: _row_without_ids(v) for k, v in row.items() if k not in skip}
    if isinstance(row, list):
        return [_row_without_ids(v) for v in row]
    return row


def test_a_promotion_on_an_unpicked_option_moves_nothing_on_the_tag(db):
    """Why dropping it is safe: a line that really CARRIES the promotion (written straight onto
    it, past the save) prints exactly what the same line with none prints."""
    host, cb, taps, promo = _sink_with_taps(db, combo_sell="1500.00")
    carried = seed.submit_one(db, host, cb, _picked(taps, 0), price_type="selling")
    plain = seed.submit_one(db, host, cb, _picked(taps, 0), price_type="selling")
    carried.lines[0].promotion_id = promo.id
    db.flush()
    (a,) = seed.rows(db, carried)
    (b,) = seed.rows(db, plain)
    assert _row_without_ids(a) == _row_without_ids(b)


def test_a_promotion_on_an_upgrade_is_still_refused_when_the_upgrade_is_not_on_the_line(db):
    """Reviewer round 3: the tag prices every upgrade of the package under the line's promotion
    (`tag_data_service._line_slots`), so dropping an upgrade's promotion WOULD move a price.
    That stays the 422 it was on main."""
    host = seed.product(db, "ZZNUHOST", list_price="1000.00")
    taps = [seed.product(db, f"ZZNUT{i}", list_price="270.00") for i in range(2)]
    upgrade = seed.product(db, "ZZNUUP", list_price="500.00")
    cb = seed.combo(
        db,
        host,
        "ZZT sink + tap + upgrade",
        parts=[{"product": p, "group": "Tap"} for p in taps] + [{"product": upgrade, "is_upgrade": True}],
    )
    promo = seed.promotion(db, [(upgrade, "350.00")])
    with pytest.raises(AppException) as refused:
        seed.submit_one(db, host, cb, _picked(taps, 0), promotion_id=promo.id)
    assert refused.value.code == "PROMOTION_NOT_AVAILABLE"


def test_a_pick_the_promotion_covers_keeps_it(db):
    host, cb, taps, promo = _sink_with_taps(db)
    request = seed.submit_one(db, host, cb, _picked(taps, 2), promotion_id=promo.id)
    db.flush()
    assert request.lines[0].promotion_id == promo.id


def test_a_promotion_that_covers_nothing_of_the_combo_is_still_refused(db):
    host, cb, taps, _promo = _sink_with_taps(db)
    stranger = seed.product(db, "ZZNOTHER", list_price="10.00")
    elsewhere = seed.promotion(db, [(stranger, "5.00")])
    with pytest.raises(AppException) as refused:
        seed.submit_one(db, host, cb, _picked(taps, 0), promotion_id=elsewhere.id)
    assert refused.value.code == "PROMOTION_NOT_AVAILABLE"
