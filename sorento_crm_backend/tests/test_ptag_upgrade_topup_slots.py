"""PRICETAG-UPGRADE-VARIANTS BE test 1 (AC-U3, AC-U8): upgrade slot rows carry `topup_amount`.

Written test-FIRST. Contract: PLAN-pricetag-upgrade-variants-09nov.md S1 "BE": `_line_slots` and
`_preview_slots` upgrade rows gain `topup_amount` (the part's top-up). Postgres only, own seed chain.
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests import _ptag_variant_seed as vseed
from tests._pg_fixture import blank_session


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


def test_be1_a_line_upgrade_row_carries_the_parts_topup(db):
    s = vseed.sink_combo(db)
    request = seed.submit_one(db, s["host"], s["combo"], [{"product_id": s["fixed"].id}])
    db.flush()
    row = seed.rows(db, request)[0]
    (upgrade,) = row["slots"]["upgrades"]
    assert upgrade["code"] == "SRTKT71SS"
    assert upgrade["chosen"] is False
    assert "topup_amount" in upgrade, "the upgrade slot row has no topup_amount"
    assert float(upgrade["topup_amount"]) == 150.0
    assert float(upgrade["list_price"]) == 440.0


def test_be1_a_picked_upgrade_row_still_carries_its_topup(db):
    s = vseed.sink_combo(db)
    parts = [{"product_id": s["fixed"].id}, {"product_id": s["upgrade"].id, "role": "Upgrade"}]
    request = seed.submit_one(db, s["host"], s["combo"], parts)
    db.flush()
    (upgrade,) = seed.rows(db, request)[0]["slots"]["upgrades"]
    assert upgrade["chosen"] is True
    assert float(upgrade["topup_amount"]) == 150.0


def test_be1_the_editor_preview_upgrade_row_carries_the_topup(db):
    from app.services.dealer_kit import tag_data_service

    s = vseed.sink_combo(db)
    slots = tag_data_service._preview_slots(db, s["combo"], s["host"])
    (upgrade,) = slots["upgrades"]
    assert upgrade["code"] == "SRTKT71SS"
    assert float(upgrade["topup_amount"]) == 150.0


def test_be1_an_upgrade_with_no_topup_reads_null(db):
    from app.services.dealer_kit import tag_data_service

    s = vseed.sink_combo(db)
    for part in s["combo"].parts:
        if part.is_upgrade:
            part.topup_amount = None
    db.flush()
    (upgrade,) = tag_data_service._preview_slots(db, s["combo"], s["host"])["upgrades"]
    assert "topup_amount" in upgrade
    assert upgrade["topup_amount"] is None


def test_be1_fixed_part_rows_gain_no_topup_figure(db):
    from app.services.dealer_kit import tag_data_service

    s = vseed.sink_combo(db)
    slots = tag_data_service._preview_slots(db, s["combo"], s["host"])
    (fixed,) = slots["fixed"]
    assert fixed.get("topup_amount") is None
