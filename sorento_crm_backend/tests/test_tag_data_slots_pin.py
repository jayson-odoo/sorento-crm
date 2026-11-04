"""PRICETAG-COMBO-RENDER fix round 1 (B1, L1): `slots` on a pinned tag.

A pinned tag keeps the data of the pin (r9). The only thing read fresh is the tag's own pick of a
group left open, exactly like `combo.picked`: it re-chooses among the candidates the pin holds and
never re-reads master data.
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests import _ptag_shapes_seed as shapes
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)

D = Decimal


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)
    monkeypatch.setattr(
        "app.services.dealer_kit.product_images.resolve_signed_url",
        lambda path, **_kwargs: f"https://signed.example.test/{path.rsplit('/', 1)[-1]}",
    )


def _open_group(db, s, count=2):
    """An S1 line whose tap group is left open between the first `count` options; pinned by the first read."""
    parts = [{"product_id": None, "role": "Kitchen tap", "candidates": [x.id for x in s["options"][:count]]}]
    request = seed.submit_one(db, s["host"], s["combo"], parts)
    db.flush()
    seed.rows(db, request)  # pins the tag
    return request, request.lines[0].tags[0]


def _reread(db, request, tag):
    db.expire_all()
    (row,) = [r for r in seed.rows(db, request) if r["tag_id"] == tag.id]
    return row


def test_a_choice_made_after_the_pin_keeps_the_pinned_position_data(db):
    s = shapes.s1(db)
    request, tag = _open_group(db, s)
    pinned_price = s["options"][1].list_price
    tag.choices = {"Kitchen tap": s["options"][1].id}
    s["options"][1].list_price = D("999.00")
    db.flush()
    row = _reread(db, request, tag)
    (pick,) = row["slots"]["groups"][0]["picks"]
    assert pick["code"] == "SRTKT1863SS"
    assert pick["list_price"] == pinned_price, "the pin is not rebuilt from master data"


def test_changing_the_choice_swaps_the_pick_among_the_pinned_candidates(db):
    s = shapes.s1(db)
    request, tag = _open_group(db, s)
    tag.choices = {"Kitchen tap": s["options"][0].id}
    db.flush()
    assert shapes.codes(_reread(db, request, tag)["slots"]["groups"][0]["picks"]) == ["SRTKT1862SS"]
    tag.choices = {"Kitchen tap": s["options"][1].id}
    db.flush()
    assert shapes.codes(_reread(db, request, tag)["slots"]["groups"][0]["picks"]) == ["SRTKT1863SS"]


def test_a_list_price_request_prints_no_offer_on_a_position(db):
    s = shapes.s1(db)
    promo = seed.promotion(db, [(s["options"][0], "50.00")])
    parts = shapes.pick_parts(s["group"], s["options"][0])
    request = seed.submit_one(db, s["host"], s["combo"], parts, price_mode="list", promotion_id=promo.id)
    db.flush()
    row = seed.rows(db, request)[0]
    assert row["slots"]["groups"][0]["picks"][0]["sell_price"] is None
    request = seed.submit_one(db, s["host"], s["combo"], parts, price_mode="selling", promotion_id=promo.id)
    db.flush()
    assert seed.rows(db, request)[0]["slots"]["groups"][0]["picks"][0]["sell_price"] == D("50.00")
