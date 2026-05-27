"""Search query whitespace trimming.

Bug: searching for a code with a leading/trailing space (e.g. "codeA ") returned
no results because the space survived into the ILIKE / equality filter. The
free-text `query` must be trimmed regardless of which domain it routes through.
"""
from __future__ import annotations

import pytest

from app.services.query_normalizer import strip_domain_stopwords
from app.services.entity_resolver import extract_candidate_tokens


@pytest.mark.parametrize(
    "raw,domain,expected",
    [
        ("codeA ", "product", "codeA"),          # domain with stopwords
        (" codeA", "product", "codeA"),
        ("codeA ", "no_such_domain", "codeA"),    # domain without stopwords
        ("  codeA  ", "no_such_domain", "codeA"),
        ("kitchen sink promotion ", "promotion", "kitchen sink"),
    ],
)
def test_strip_domain_stopwords_trims(raw, domain, expected):
    assert strip_domain_stopwords(raw, domain) == expected


def test_strip_domain_stopwords_passes_through_none_and_blank():
    assert strip_domain_stopwords(None, "product") is None
    assert strip_domain_stopwords("", "product") == ""


def test_candidate_tokens_ignore_surrounding_space():
    assert extract_candidate_tokens("  ABC123  ") == extract_candidate_tokens("ABC123")
