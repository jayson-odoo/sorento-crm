"""``unique_code(alpha=True)`` never spells a digit.

Release run 36592312452: round 7's "65502 eta" pick list also carried
``ZZT-ZZR3B-ae65502c``, a basin whose eight random hex characters happened to contain the
digits the message asked for. The substring match is correct app behaviour, so the test
data is what has to stay clear of digit tokens.
"""
from __future__ import annotations

import re

from tests._pg_fixture import TEST_PREFIX, unique_code


def test_alpha_suffix_carries_no_digit():
    for _ in range(5000):
        code = unique_code("ZZR3B", alpha=True)
        stem, suffix = code.rsplit("-", 1)
        assert stem == f"{TEST_PREFIX}-ZZR3B"
        assert re.fullmatch(r"[a-p]{8}", suffix), code


def test_alpha_keeps_the_default_shape_and_uniqueness():
    plain = unique_code("ZZR3B")
    assert re.fullmatch(rf"{TEST_PREFIX}-ZZR3B-[0-9a-f]{{8}}", plain), plain
    alphas = {unique_code("X", alpha=True) for _ in range(2000)}
    assert len(alphas) == 2000
    assert unique_code(alpha=True).startswith(f"{TEST_PREFIX}-")
