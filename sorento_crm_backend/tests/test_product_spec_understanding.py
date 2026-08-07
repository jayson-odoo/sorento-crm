"""The semantic half: understand the sentence, but never let a model invent vocabulary.

The ranker stays deterministic and explainable. This module is the only place a model
touches spec search, and the whole design is the boundary around it — the model decides
what the customer MEANT, the registry still decides what EXISTS. Every test here is
about that boundary holding, not about the model being clever.

No test calls a real provider. A test that needed a network round trip and an API key
would be skipped in CI, which is the same as not having it.

Ticket: jayson-odoo/sorento-crm#98.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.models.product import ProductCategory, UnitOfMeasure
from app.services import product_spec_understanding as understanding
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_registry import seed_spec_registry
from app.services.product_spec_understanding import understand_phrase
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        s.add_all(
            [
                ProductCategory(
                    id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS"
                ),
                ProductCategory(
                    id=str(uuid.uuid4()), category_code="SRT-WC", category_name="SRT-WC"
                ),
                UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece"),
            ]
        )
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        yield s


def _model_returning(payload: dict, monkeypatch, *, tokens: int = 120):
    """Pin the provider to a fixed reply so the boundary can be tested, not the model."""
    result = SimpleNamespace(
        content=json.dumps(payload),
        prompt_tokens=tokens,
        completion_tokens=10,
        total_tokens=tokens + 10,
    )
    provider = SimpleNamespace(chat=lambda *a, **k: result)
    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db: (provider, "openai", "gpt-test")
    )


def _keys(result) -> dict:
    return {entry["key"]: entry["value"] for entry in result.specs}


# --------------------------------------------------------------------------- #
# the boundary: the model may not invent vocabulary
# --------------------------------------------------------------------------- #
def test_an_unknown_spec_key_is_dropped(db, monkeypatch):
    _model_returning(
        {"specs": [{"key": "levitation", "value": "yes"}, {"key": "trap_type", "value": "p_trap"}]},
        monkeypatch,
    )

    result = understand_phrase(db, "a floating toilet")

    assert "levitation" not in _keys(result), "a key the registry does not define must not survive"
    assert _keys(result)["trap_type"] == "p_trap"


def test_an_unknown_enum_value_is_dropped(db, monkeypatch):
    _model_returning({"specs": [{"key": "mounting", "value": "levitating"}]}, monkeypatch)

    result = understand_phrase(db, "a floating basin")

    assert "mounting" not in _keys(result)


def test_a_value_given_in_customer_words_is_canonicalised(db, monkeypatch):
    # The model answers with what the customer said; the catalog stores a slug.
    _model_returning({"specs": [{"key": "mounting", "value": "wall hung"}]}, monkeypatch)

    assert _keys(understand_phrase(db, "hung on the wall"))["mounting"] == "wall_hung"


def test_a_numeric_answer_carrying_a_unit_is_normalised(db, monkeypatch):
    """Models echo the customer's unit back even when told the key is in mm."""
    _model_returning({"specs": [{"key": "trap_length", "value": "8 inch"}]}, monkeypatch)

    assert _keys(understand_phrase(db, 'trap 8"'))["trap_length"] == pytest.approx(203.2)


# --------------------------------------------------------------------------- #
# degradation: search must never get worse because a model had a bad day
# --------------------------------------------------------------------------- #
def test_a_provider_failure_falls_back_to_the_literal_reading(db, monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("provider is down")

    monkeypatch.setattr(
        understanding,
        "_resolve_provider",
        lambda db: (SimpleNamespace(chat=explode), "openai", "gpt-test"),
    )

    result = understand_phrase(db, "wall hung water closet")

    assert result.source == "deterministic"
    assert _keys(result)["mounting"] == "wall_hung", "the literal resolver still works"


def test_unparseable_json_falls_back(db, monkeypatch):
    provider = SimpleNamespace(
        chat=lambda *a, **k: SimpleNamespace(
            content="not json at all", prompt_tokens=1, completion_tokens=1, total_tokens=2
        )
    )
    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db: (provider, "openai", "gpt-test")
    )

    assert understand_phrase(db, "wall hung water closet").source == "deterministic"


def test_no_configured_provider_falls_back(db, monkeypatch):
    monkeypatch.setattr(understanding, "_resolve_provider", lambda db: (None, "openai", ""))

    result = understand_phrase(db, "double bowl kitchen sink")

    assert result.source == "deterministic"
    assert _keys(result)["bowl_count"] == 2


def test_the_literal_reading_is_a_floor_the_model_cannot_lower(db, monkeypatch):
    """A synonym that matched outright is not something a model should overrule.

    The model returns only a class here; "double bowl" still has to survive, because
    the customer typed words that mean exactly one thing.
    """
    _model_returning({"specs": [{"key": "class", "value": "Kitchen Sink"}]}, monkeypatch)

    result = understand_phrase(db, "double bowl kitchen sink")

    assert _keys(result)["bowl_count"] == 2
    assert _keys(result)["class"] == "Kitchen Sink"


def test_the_model_wins_where_the_two_disagree_on_one_key(db, monkeypatch):
    # Both readings produce `mounting`; the model saw the whole sentence, so it wins.
    _model_returning({"specs": [{"key": "mounting", "value": "floor_standing"}]}, monkeypatch)

    result = understand_phrase(db, "not wall hung, I want it on the floor")

    assert _keys(result)["mounting"] == "floor_standing"


# --------------------------------------------------------------------------- #
# housekeeping
# --------------------------------------------------------------------------- #
def test_the_whole_phrase_stays_available_as_free_text(db, monkeypatch):
    # The rendered sentence is matched against free terms; dropping the phrase would
    # lose recall the model cannot replace.
    _model_returning({"specs": [], "free_terms": ["sorento"]}, monkeypatch)

    result = understand_phrase(db, "sorento kitchen sink")

    assert "sorento kitchen sink" in result.free_terms


def test_an_empty_phrase_does_not_call_the_model(db, monkeypatch):
    def explode(db_):  # pragma: no cover - must never run
        raise AssertionError("no provider call for an empty phrase")

    monkeypatch.setattr(understanding, "_resolve_provider", explode)

    assert understand_phrase(db, "   ").specs == []


def test_allow_model_false_skips_the_provider(db, monkeypatch):
    def explode(db_):  # pragma: no cover - must never run
        raise AssertionError("provider must not be resolved when disabled")

    monkeypatch.setattr(understanding, "_resolve_provider", explode)

    result = understand_phrase(db, "double bowl kitchen sink", allow_model=False)

    assert result.source == "deterministic"
    assert _keys(result)["bowl_count"] == 2


# --------------------------------------------------------------------------- #
# open vocabularies: `brand` and `class` have no closed list in the registry
# --------------------------------------------------------------------------- #
def test_an_open_vocabulary_key_is_given_the_catalogs_own_values(db):
    """Told only that `brand` is an enum, a model cannot know "sorento" is one.

    That is exactly what happened: the model answered "the term 'sorento' is unclear and
    does not map to any specification", which was the correct answer to a badly-posed
    question. The values have to come from the catalog, because that is the only place
    they exist.
    """
    import uuid as _uuid
    from decimal import Decimal

    from app.models.product import Product
    from app.models.product_spec import ProductSpecifications
    from app.services.product_spec_understanding import _vocabulary

    category = db.query(ProductCategory).filter_by(category_code="SRT-KS").one()
    uom = db.query(UnitOfMeasure).filter_by(uom_code="ZZT-PCS").one()
    product = Product(
        id=str(_uuid.uuid4()),
        product_code="ZZT-BRANDED",
        product_name="ZZT-BRANDED",
        description="SORENTO KITCHEN SINK",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("1.00"),
    )
    db.add(product)
    db.flush()
    db.add(
        ProductSpecifications(
            product_id=product.id,
            values={"brand": {"value": "Sorento"}, "class": {"value": "Kitchen Sink"}},
            provenance={},
        )
    )
    db.flush()

    described, _index, open_values = _vocabulary(db)
    brand = next(e for e in described if e["spec_key"] == "brand")

    assert "Sorento" in brand.get("allowed_values", []), "the model must be shown real brands"
    assert "Sorento" in open_values["brand"]


def test_a_brand_is_returned_in_the_catalogs_own_spelling(db, monkeypatch):
    """The model echoes the customer's casing; the ranker compares against the catalog."""
    import uuid as _uuid
    from decimal import Decimal

    from app.models.product import Product
    from app.models.product_spec import ProductSpecifications

    category = db.query(ProductCategory).filter_by(category_code="SRT-KS").one()
    uom = db.query(UnitOfMeasure).filter_by(uom_code="ZZT-PCS").one()
    product = Product(
        id=str(_uuid.uuid4()),
        product_code="ZZT-BRANDED2",
        product_name="ZZT-BRANDED2",
        description="SORENTO KITCHEN SINK",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("1.00"),
    )
    db.add(product)
    db.flush()
    db.add(
        ProductSpecifications(
            product_id=product.id,
            values={"brand": {"value": "Sorento"}},
            provenance={},
        )
    )
    db.flush()

    _model_returning({"specs": [{"key": "brand", "value": "sorento"}]}, monkeypatch)

    assert _keys(understand_phrase(db, "sorento sink"))["brand"] == "Sorento"
