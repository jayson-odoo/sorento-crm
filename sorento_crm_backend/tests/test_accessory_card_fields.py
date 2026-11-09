"""TAG-ACC-CARD-RESIZE Q4: a catalogue product listed as an accessory carries what a card's
`{{product.*}}` fields read: its sell price (offer for the viewer, else null), its spec lines
and its own price tag description, read live. A library accessory carries none of them.
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.schemas.price_tag import TagAccessory
from app.services.company_scope import register_company_scope_listeners

from tests._pg_fixture import blank_session
from tests.test_accessories import _accessory, _product  # noqa: F401


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


def test_a_product_entry_carries_sell_price_spec_lines_and_its_description(db):
    from app.services.accessory_service import tag_product_entry
    from app.services.dealer_kit.pricing import resolve_prices
    from app.services.dealer_kit.tag_data_service import staff_viewer

    waste = _product(db, "ZZCARD")
    waste.description = "Pop-up waste\nBrass, 80 mm"
    waste.price_tag_description = "<p><strong>Brass</strong> waste</p>"
    db.flush()

    entry = tag_product_entry(db, waste)
    expected = resolve_prices(db, [waste], staff_viewer(), None)[waste.id]

    assert entry["price_tag_description"] == "<p><strong>Brass</strong> waste</p>"
    assert entry["spec_lines"] == ["Pop-up waste", "Brass, 80 mm"]
    assert "sell_price" in entry
    assert entry["sell_price"] == (float(expected.offer_price) if expected.offer_price is not None else None)
    # The tag schema keeps them (response_model drops undeclared fields without a word).
    wire = TagAccessory(**entry).model_dump()
    assert wire["price_tag_description"] == entry["price_tag_description"]
    assert wire["spec_lines"] == ["Pop-up waste", "Brass, 80 mm"]
    assert "sell_price" in wire


def test_a_library_accessory_has_no_product_fields(db):
    from app.services.accessory_service import tag_accessory

    row = _accessory(db, "ZZ card lib")
    entry = tag_accessory(db, row)
    assert entry.get("sell_price") is None
    assert entry.get("spec_lines") is None
    assert entry.get("price_tag_description") is None


def test_a_product_entry_sell_price_is_the_viewers_offer(db, monkeypatch):
    """The offer `resolve_prices` gives this viewer is what `{{product.sell_price}}` prints."""
    from decimal import Decimal
    from types import SimpleNamespace

    from app.services.accessory_service import tag_product_entry
    from app.services.dealer_kit import pricing

    waste = _product(db, "ZZCARDSP")
    monkeypatch.setattr(
        pricing,
        "resolve_prices",
        lambda _db, products, _viewer, _promo: {
            p.id: SimpleNamespace(list_price=Decimal("100.00"), offer_price=Decimal("79.00")) for p in products
        },
    )
    entry = tag_product_entry(db, waste)
    assert entry["list_price"] == Decimal("100.00")
    assert entry["sell_price"] == Decimal("79.00")
    assert TagAccessory(**entry).sell_price == 79.0
