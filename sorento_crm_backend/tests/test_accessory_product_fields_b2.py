"""SPEC-SHEET-DESIGNER-PARITY B2: a catalogue product listed as an accessory carries brand,
description, spec_sheet_description and dimensions, so the new card fields are not blank on a
price tag. A library accessory stays null."""
from __future__ import annotations

import uuid

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.schemas.price_tag import TagAccessory

from tests._pg_fixture import blank_session
from tests.test_accessories import _accessory, _product  # noqa: F401
from tests.test_accessory_card_fields import _scope_listeners  # noqa: F401  (autouse fixture)


def test_a_product_entry_carries_the_spec_sheet_card_fields():
    from app.models.product import Brand
    from app.services.accessory_service import tag_product_entry

    with blank_session() as db:
        waste = _product(db, "ZZB2CARD")
        waste.description = "Pop-up waste"
        waste.spec_sheet_description = "Sheet waste copy"
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZB2" + waste.id[:6], brand_name="ACME")
        db.add(brand)
        db.flush()
        waste.brand_id = brand.id
        db.flush()

        entry = tag_product_entry(db, waste)
        assert entry["brand"] == "ACME"
        assert entry["description"] == "Pop-up waste"
        assert entry["spec_sheet_description"] == "Sheet waste copy"
        assert "dimensions" in entry
        wire = TagAccessory(**entry).model_dump()
        for key in ("brand", "description", "spec_sheet_description", "dimensions"):
            assert key in wire
        assert wire["brand"] == "ACME"
        assert wire["spec_sheet_description"] == "Sheet waste copy"


def test_the_spec_sheet_text_falls_back_to_the_description():
    from app.services.accessory_service import tag_product_entry

    with blank_session() as db:
        waste = _product(db, "ZZB2FB")
        waste.description = "Plain only"
        db.flush()
        assert tag_product_entry(db, waste)["spec_sheet_description"] == "Plain only"


def test_a_library_accessory_has_none_of_them():
    from app.services.accessory_service import tag_accessory

    with blank_session() as db:
        entry = tag_accessory(db, _accessory(db, "ZZ b2 lib"))
        for key in ("brand", "description", "spec_sheet_description", "dimensions"):
            assert entry.get(key) is None
