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


# --------------------------------------------------------------------------- #
# excluded values: a catalog value that is not a thing anyone searches for
# --------------------------------------------------------------------------- #
def _branded(db, code: str, brand: str):
    """One product carrying a brand, so the open vocabulary has it to offer."""
    import uuid as _uuid
    from decimal import Decimal

    from app.models.product import Product
    from app.models.product_spec import ProductSpecifications

    category = db.query(ProductCategory).filter_by(category_code="SRT-KS").one()
    uom = db.query(UnitOfMeasure).filter_by(uom_code="ZZT-PCS").one()
    product = Product(
        id=str(_uuid.uuid4()),
        product_code=code,
        product_name=code,
        description="KITCHEN SINK",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("1.00"),
    )
    db.add(product)
    db.flush()
    db.add(
        ProductSpecifications(
            product_id=product.id, values={"brand": {"value": brand}}, provenance={}
        )
    )
    db.flush()
    return product


def test_an_excluded_value_is_never_offered_to_the_model(db):
    """OTHERS and NO LOGO record the ABSENCE of a brand.

    Offered as enum options they read as "none of the above", and the model filed every
    word it could not place under one — "interlignet wc" came back branded OTHERS. Not
    being shown a value is a harder guarantee than a rule telling the model to avoid it.
    """
    from app.services.product_spec_understanding import _vocabulary

    _branded(db, "ZZT-EXC-1", "OTHERS")
    _branded(db, "ZZT-EXC-2", "SORENTO")

    described, _index, open_values = _vocabulary(db)
    brand = next(e for e in described if e["spec_key"] == "brand")

    assert "SORENTO" in brand["allowed_values"]
    assert "OTHERS" not in brand["allowed_values"]
    assert "OTHERS" not in open_values["brand"]


def test_an_excluded_value_is_rejected_even_if_the_model_returns_it(db, monkeypatch):
    # Belt as well as braces: the prompt is not the only thing standing between a
    # placeholder brand and a customer's shortlist.
    _branded(db, "ZZT-EXC-3", "OTHERS")
    _model_returning({"specs": [{"key": "brand", "value": "OTHERS"}]}, monkeypatch)

    assert "brand" not in _keys(understand_phrase(db, "interlignet wc"))


# --------------------------------------------------------------------------- #
# a refusal is not a request
# --------------------------------------------------------------------------- #
def test_a_refused_value_is_kept_out_of_the_specs(db, monkeypatch):
    """"not glass" must not arrive as material=glass.

    The literal resolver sees the word "glass" and nothing else — it has no concept of
    "not" — so a phrase that rules a material out was scoring products made of it. The
    model's refusal has to survive being merged with that reading, or the deterministic
    floor reinstates the exact thing the customer refused.
    """
    _model_returning(
        {
            "specs": [{"key": "class", "value": "Wash Basin"}],
            "exclusions": [{"key": "material", "value": "glass"}],
        },
        monkeypatch,
    )

    result = understand_phrase(db, "wash basin not glass")

    assert "material" not in _keys(result), "a refusal must never become a request"
    assert {(e["key"], e["value"]) for e in result.exclusions} == {("material", "glass")}


def test_a_value_both_asked_for_and_refused_resolves_to_refused(db, monkeypatch):
    # The model sometimes answers "not glass" with both. The refusal is the more
    # specific statement, and getting this backwards is the worst possible answer.
    _model_returning(
        {
            "specs": [{"key": "material", "value": "glass"}],
            "exclusions": [{"key": "material", "value": "glass"}],
        },
        monkeypatch,
    )

    result = understand_phrase(db, "anything but glass")

    assert "material" not in _keys(result)


def test_a_refusal_of_an_unknown_value_is_dropped(db, monkeypatch):
    # Exclusions go through the same registry gate as requests: an exclusion nothing
    # can match would be a silent filter on a word the catalog never stores.
    _model_returning(
        {"specs": [], "exclusions": [{"key": "material", "value": "unobtainium"}]},
        monkeypatch,
    )

    assert understand_phrase(db, "not unobtainium").exclusions == []


def test_resolve_provider_uses_the_configured_providers_own_default_model():
    """A provider with no model named must get ITS default, not another vendor's.

    The old two-branch fallback ("gpt-4o if openai else claude-sonnet-4-6") handed
    a Gemini-configured install an Anthropic model id, which Google answers with a
    404 that reads like the feature is broken.
    """
    from app.models.ai_assistant import AIAssistantConfig
    from app.services.llm_provider import GeminiProvider

    with blank_session() as db:
        db.add(
            AIAssistantConfig(
                provider="gemini", model="", api_key_ciphertext="ZZT-gemini-key"
            )
        )
        db.commit()

        provider, provider_name, model_name = understanding._resolve_provider(db)

        assert isinstance(provider, GeminiProvider)
        assert provider_name == "gemini"
        assert model_name == "gemini-2.5-flash"


def test_a_gemini_agent_never_borrows_an_openai_assistants_key(monkeypatch):
    """The per-agent provider is operator-settable, so it is often NOT the one
    the assistant row runs on. Reading the generic key column regardless posted
    the OpenAI key to Google: a live credential handed to another vendor, and a
    400 that reads like a Gemini outage. No key resolves, so the caller degrades
    to the literal reading instead."""
    from app.config import settings as app_settings
    from app.models.ai_assistant import AIAssistantConfig

    monkeypatch.setattr(app_settings, "gemini_api_key", None, raising=False)
    monkeypatch.setattr(understanding, "agent_model", lambda db, name: ("gemini", ""))

    with blank_session() as db:
        db.add(
            AIAssistantConfig(
                provider="openai", model="", api_key_ciphertext="ZZT-openai-key"
            )
        )
        db.commit()

        provider, provider_name, _ = understanding._resolve_provider(db)

        assert provider is None
        assert provider_name == "gemini"


def test_an_agent_on_the_assistants_own_provider_still_uses_the_generic_key(
    monkeypatch,
):
    """The guard must not break the ordinary install."""
    from app.models.ai_assistant import AIAssistantConfig
    from app.services.llm_provider import OpenAIProvider

    monkeypatch.setattr(understanding, "agent_model", lambda db, name: ("openai", ""))

    with blank_session() as db:
        db.add(
            AIAssistantConfig(
                provider="openai", model="", api_key_ciphertext="ZZT-openai-key"
            )
        )
        db.commit()

        provider, provider_name, _ = understanding._resolve_provider(db)

        assert isinstance(provider, OpenAIProvider)
        assert provider.api_key == "ZZT-openai-key"
        assert provider_name == "openai"


# --------------------------------------------------------------------------- #
# provider / model pairing: an agent pointed at Gemini with no model of its own
# must not inherit the assistant's OpenAI model id and post it to Google
# --------------------------------------------------------------------------- #


def test_an_agent_on_gemini_without_a_model_gets_gemini_default_not_the_assistants(
    db, monkeypatch
):
    from app.models.ai_assistant import AIAssistantConfig
    from app.services import llm_provider

    db.add(
        AIAssistantConfig(
            provider="openai",
            model="gpt-4o",
            api_key_ciphertext="ZZT-openai-key",
            gemini_api_key_ciphertext="ZZT-gemini-key",
        )
    )
    db.flush()
    monkeypatch.setattr(understanding, "agent_model", lambda *_a, **_k: ("gemini", None))

    provider, provider_name, model_name = understanding._resolve_provider(db)

    assert provider_name == "gemini"
    assert isinstance(provider, llm_provider.GeminiProvider)
    assert model_name == llm_provider.default_model_for("gemini")
    assert provider.api_key == "ZZT-gemini-key"


def test_an_agent_with_no_provider_of_its_own_inherits_the_assistants_pair(db, monkeypatch):
    from app.models.ai_assistant import AIAssistantConfig

    db.add(
        AIAssistantConfig(
            provider="openai", model="gpt-4o", api_key_ciphertext="ZZT-openai-key"
        )
    )
    db.flush()
    monkeypatch.setattr(understanding, "agent_model", lambda *_a, **_k: (None, None))

    _, provider_name, model_name = understanding._resolve_provider(db)

    assert (provider_name, model_name) == ("openai", "gpt-4o")
