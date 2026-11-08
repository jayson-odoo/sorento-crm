"""PRICETAG-DISCONTINUED-PICK: a discontinued combo option is a valid pick on a price tag request.

UAC: `documentation/plans/dealer-kit/pricetag-discontinued-pick-acceptance-criteria.md` (AC-5).

Owner, 7 Nov: "discontinued should still be able to choose". The portal picker now lets the
salesperson pick a discontinued option; these pin that the server takes the pick on save and that
the tag data reads it back as the picked option, so a future discontinued reject cannot land
silently.
"""
from __future__ import annotations

import os

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

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


def _tap_combo(db):
    host = seed.product(db, "ZZDHOST", list_price="1000.00")
    taps = [seed.product(db, f"ZZDT{i}", list_price="270.00") for i in range(3)]
    taps[1].is_discontinued = True
    db.flush()
    cb = seed.combo(db, host, "ZZT tap combo", parts=[{"product": p, "group": "Tap"} for p in taps])
    return host, cb, taps


def test_a_discontinued_option_picked_in_a_group_saves_and_reads_back_picked(db):
    host, cb, taps = _tap_combo(db)
    request = seed.submit_one(
        db,
        host,
        cb,
        [{"product_id": taps[1].id, "role": "Tap", "candidates": [p.id for p in taps]}],
    )
    db.flush()

    (part,) = request.lines[0].parts
    assert part.product_id == taps[1].id

    (row,) = seed.rows(db, request)
    assert [p["code"] for p in row["own_parts"]] == [taps[1].product_code]
    picked = {o["product_id"]: o["picked"] for g in row["combo"]["choices"] for o in g["options"]}
    assert picked == {taps[0].id: False, taps[1].id: True, taps[2].id: False}


def test_an_open_group_listing_a_discontinued_candidate_saves(db):
    host, cb, taps = _tap_combo(db)
    request = seed.submit_one(db, host, cb, [{"role": "Tap", "candidates": [p.id for p in taps]}])
    db.flush()

    (part,) = request.lines[0].parts
    assert part.product_id is None
    assert sorted(part.candidates) == sorted(p.id for p in taps)
