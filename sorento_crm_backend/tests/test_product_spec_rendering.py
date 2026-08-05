"""The rendered spec sentence: the only text spec search ever matches at query time.

Product resolution is code-only by design (`entity_resolver.py:2945`), because a
description cross-reference like "USED FOR SRTWC6015-RL-UF" must not resolve that row
for token SRTWC6015. Spec search does not loosen that rule; it routes around it by
never searching the description at all. The searchable text is built from spec VALUES,
so a foreign product code cannot enter the index: no registry key can take a product
code as a value.

Ticket: jayson-odoo/sorento-crm#75. Contract:
documentation/plans/products/spec-search-acceptance-criteria.md AC-T0d-01 .. AC-T0d-07.
"""
from __future__ import annotations

import re

import pytest

from app.services.product_spec_rendering import CODE_SHAPES, render_spec_sentence


def _values(**pairs) -> dict:
    return {key: {"value": value} for key, value in pairs.items()}


# AC-T0d-02: built from values, reading as language rather than a key dump.
def test_renders_a_readable_sentence():
    sentence = render_spec_sentence(
        _values(
            **{
                "class": "Kitchen Sink",
                "brand": "Sorento",
                "material": "stainless_steel",
                "mounting": "wall_hung",
                "finish": "black",
                "dim_length": 1000,
                "dim_width": 500,
                "dim_height": 140,
                "control_type": "single_lever",
            }
        )
    )

    assert sentence.startswith("Sorento kitchen sink.")
    assert "Stainless steel." in sentence
    assert "Wall mounted." in sentence
    assert "Black finish." in sentence
    assert "1000 x 500 x 140 mm." in sentence
    assert "Single lever." in sentence


# AC-T0d-04: a round product reads as a diameter, never as length by width. This is the
# whole point of the shape work: 231 codes store a round product as rectangular.
def test_round_product_renders_as_a_diameter():
    sentence = render_spec_sentence(
        _values(
            **{
                "class": "Wash Basin",
                "brand": "Sorento",
                "shape": "round",
                "diameter": 407,
                "depth": 120,
            }
        )
    )

    assert "Round." in sentence
    assert "407 mm diameter." in sentence
    assert " x " not in sentence


def test_rectangular_dimensions_render_as_a_triple():
    sentence = render_spec_sentence(_values(dim_length=798, dim_width=500, dim_height=220))
    assert "798 x 500 x 220 mm." in sentence


def test_partial_dimensions_still_render():
    sentence = render_spec_sentence(_values(dim_length=798, dim_width=500))
    assert "798 x 500 mm." in sentence


def test_thickness_is_stated_separately():
    sentence = render_spec_sentence(_values(dim_length=798, dim_width=500, thickness=1.2))
    assert "1.2 mm thick." in sentence


# AC-T0d-05: an empty sentence would match every query, so no document is produced.
@pytest.mark.parametrize("values", [{}, {"is_accessory": {"value": False}}])
def test_nothing_worth_saying_renders_nothing(values):
    assert render_spec_sentence(values) is None


def test_accessory_is_stated_so_the_ranker_can_read_it_back():
    sentence = render_spec_sentence(
        _values(**{"class": "Kitchen Sink", "is_accessory": True, "material": "stainless_steel"})
    )
    assert "Accessory or spare part." in sentence


# AC-T0d-03: the guard that makes description-derived search safe.
def test_no_product_code_survives_into_the_sentence():
    # A derivation should never produce a code as a value, but the renderer is the
    # last line of defence and must not depend on that holding.
    sentence = render_spec_sentence(
        _values(
            **{
                "class": "Water Closet",
                "brand": "Sorento",
                "material": "ceramic",
                "finish": "SRTWC6015-RL-UF",  # a code smuggled in as a value
            }
        )
    )

    assert "SRTWC6015" not in sentence
    for pattern in CODE_SHAPES:
        assert not re.search(pattern, sentence), pattern


@pytest.mark.parametrize(
    "smuggled",
    ["SRTKS4028B", "CKS1050-BL", "ACC-CB8002-HN", "BRC2112UWP-S", "40MM-TAIL"],
)
def test_every_real_code_shape_is_stripped(smuggled):
    sentence = render_spec_sentence(
        _values(**{"class": "Kitchen Sink", "brand": "Cabana", "finish": smuggled})
    )
    assert smuggled not in (sentence or "")


def test_a_measurement_is_not_mistaken_for_a_code():
    # The stripper must not eat legitimate content: "1000 x 500 x 140 mm" contains
    # digits, and an over-eager code pattern would remove the dimensions entirely.
    sentence = render_spec_sentence(_values(dim_length=1000, dim_width=500, dim_height=140))
    assert "1000 x 500 x 140 mm." in sentence
