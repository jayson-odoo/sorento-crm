"""The flyer check: does it ask the right questions, and can it be gamed?"""
from __future__ import annotations

from app.services.spec_findability import angles_for, customer_phrase


def test_the_code_never_reaches_the_query():
    """Otherwise this is a code lookup and every card passes.

    A card that prints its own code would be found by that code alone, whether or not a
    single spec had ever been derived - so the sweep would report perfect findability
    for a catalogue with no vocabulary at all.
    """
    card = "2-Ways Exposed Shower Set SRTWT9605-RG • Rose Gold + Matt Black RM 599"
    said = customer_phrase(card, "SRTWT9605-RG")

    assert "SRTWT9605-RG" not in said
    assert "RM" not in said
    # What a person would actually say survives.
    assert "Ways" in said and "Rose Gold" in said


def test_only_what_the_card_states_is_asked_for():
    """A spec only the description mentions is not something the customer can say."""
    values = {
        "product_type": {"value": "shower_set"},
        "finish": {"value": "rose_gold"},
        "material": {"value": "brass"},
    }
    provenance = {
        "product_type": {"source": "flyer"},
        "finish": {"source": "flyer"},
        # Derived from the description; the card says nothing about it.
        "material": {"source": "derived"},
    }
    names = {a.name for a in angles_for(values, provenance, "2 ways shower set")}

    assert "one:product_type" in names
    assert "one:finish" in names
    assert "one:material" not in names, "asking for a spec the card never printed flatters the result"
    assert "without:finish" in names


def test_brand_is_not_an_angle():
    """Near enough every row is SORENTO, so it separates nothing."""
    values = {"brand": {"value": "SORENTO"}, "product_type": {"value": "mirror"}}
    provenance = {"brand": {"source": "flyer"}, "product_type": {"source": "flyer"}}
    names = {a.name for a in angles_for(values, provenance, "mirror")}

    assert "one:brand" not in names
    assert "one:product_type" in names


def test_the_cheap_sweep_asks_only_the_broad_questions():
    """756 cards times seventeen angles is four hours. Detail is for the failures."""
    values = {"product_type": {"value": "mirror"}, "finish": {"value": "black"}}
    provenance = {"product_type": {"source": "flyer"}, "finish": {"source": "flyer"}}

    broad = [a.name for a in angles_for(values, provenance, "black mirror", detail=False)]
    full = [a.name for a in angles_for(values, provenance, "black mirror")]

    assert broad == ["card", "all"]
    assert len(full) > len(broad)
