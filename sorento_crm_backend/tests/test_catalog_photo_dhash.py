"""dHash of a catalogue photo, for the look-alike check (CATALOG-IMAGES S2, red).

Contract: ``PLAN-catalog-image-extract-27oct.md`` "Worker task" (dhash, Hamming
distance <= 10 flags a look-alike). Pure: no database.
"""
from __future__ import annotations

import re

import pytest

from app.services.dealer_kit.catalog_photos import dhash, hamming
from app.services.catalogue_photo_service import LOOKALIKE_MAX_DISTANCE
from tests._catalogue_photo_images import encode, pattern

SEED = 7
OTHER_SEED = 21


def test_the_lookalike_threshold_is_ten() -> None:
    assert LOOKALIKE_MAX_DISTANCE == 10


def test_dhash_is_sixteen_lowercase_hex_characters() -> None:
    value = dhash(encode(pattern(SEED)))

    assert re.fullmatch(r"[0-9a-f]{16}", value), value


def test_hamming_of_equal_hashes_is_zero() -> None:
    value = dhash(encode(pattern(SEED)))

    assert hamming(value, value) == 0


def test_hamming_counts_differing_bits() -> None:
    assert hamming("0000000000000000", "0000000000000003") == 2
    assert hamming("ffffffffffffffff", "0000000000000000") == 64


def test_the_same_picture_at_another_size_and_quality_is_within_the_threshold() -> None:
    original = dhash(encode(pattern(SEED, (240, 240)), "JPEG", 90))
    smaller = dhash(encode(pattern(SEED, (320, 320)).resize((160, 160)), "JPEG", 60))
    larger = dhash(encode(pattern(SEED, (240, 240)).resize((480, 480)), "JPEG", 80))

    assert hamming(original, smaller) <= LOOKALIKE_MAX_DISTANCE
    assert hamming(original, larger) <= LOOKALIKE_MAX_DISTANCE


def test_a_clearly_different_picture_is_beyond_the_threshold() -> None:
    first = dhash(encode(pattern(SEED)))
    second = dhash(encode(pattern(OTHER_SEED)))

    assert hamming(first, second) > LOOKALIKE_MAX_DISTANCE


def test_png_and_jpeg_of_one_picture_hash_alike() -> None:
    as_png = dhash(encode(pattern(SEED), "PNG"))
    as_jpeg = dhash(encode(pattern(SEED), "JPEG", 85))

    assert hamming(as_png, as_jpeg) <= LOOKALIKE_MAX_DISTANCE
