"""Fuzzy access-level resolution in ContactAccessTypeService.enforce_access_levels_for_contact.

Covers the relaxed matcher that accepts common AI/user phrasing variants
(plurals, code form, no-space concat, single-word subset) while preserving
strict ambiguity / unknown-value guards.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.contact_access_type_service import ContactAccessTypeService


def _service_with_active(active_rows):
    """Build a service whose contact has the given rows as active.

    `active_rows` accepts either (code, name) 2-tuples (keywords default to [])
    or (code, name, keywords) 3-tuples.
    """
    svc = ContactAccessTypeService(MagicMock())
    catalog_rows = [
        (r[0], r[1], r[2] if len(r) > 2 else [])
        for r in active_rows
    ]
    codes = [r[0] for r in catalog_rows]
    svc.resolve_contact_access_codes = MagicMock(return_value=codes)  # type: ignore[method-assign]
    svc.resolve_active_access_levels_for_contact = MagicMock(  # type: ignore[method-assign]
        return_value=[{"name": r[1]} for r in catalog_rows]
    )
    svc.db.query.return_value.filter.return_value.all.return_value = catalog_rows
    return svc


def test_exact_name_match():
    svc = _service_with_active([("sorento_dealer", "Sorento Dealer"), ("end_user", "End User")])
    assert svc.enforce_access_levels_for_contact("r", "s", ["Sorento Dealer"]) == ["sorento_dealer"]


def test_exact_code_match_with_underscores():
    svc = _service_with_active([("sorento_dealer", "Sorento Dealer")])
    assert svc.enforce_access_levels_for_contact("r", "s", ["sorento_dealer"]) == ["sorento_dealer"]


def test_plural_form_matches():
    svc = _service_with_active([("sorento_dealer", "Sorento Dealer")])
    assert svc.enforce_access_levels_for_contact("r", "s", ["Sorento Dealers"]) == ["sorento_dealer"]


def test_concat_no_space_form_matches():
    svc = _service_with_active([("end_user", "End User")])
    assert svc.enforce_access_levels_for_contact("r", "s", ["enduser"]) == ["end_user"]


def test_single_token_uniquely_matches():
    svc = _service_with_active([("sorento_dealer", "Sorento Dealer"), ("end_user", "End User")])
    # "dealer" only present in one active code → accept.
    assert svc.enforce_access_levels_for_contact("r", "s", ["dealer"]) == ["sorento_dealer"]


def test_single_token_ambiguous_raises_403():
    svc = _service_with_active([
        ("sorento_dealer", "Sorento Dealer"),
        ("mocha_dealer", "Mocha Dealer"),
    ])
    with pytest.raises(HTTPException) as exc:
        svc.enforce_access_levels_for_contact("r", "s", ["dealer"])
    assert exc.value.status_code == 403
    detail = exc.value.detail
    assert detail["code"] == "ACCESS_LEVELS_AMBIGUOUS"
    assert set(detail["candidates"]["dealer"]) == {"Sorento Dealer", "Mocha Dealer"}


def test_unknown_value_raises_403():
    svc = _service_with_active([("end_user", "End User")])
    with pytest.raises(HTTPException) as exc:
        svc.enforce_access_levels_for_contact("r", "s", ["wholesaler"])
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "ACCESS_LEVELS_NOT_PERMITTED"


def test_empty_with_single_active_auto_defaults():
    svc = _service_with_active([("end_user", "End User")])
    assert svc.enforce_access_levels_for_contact("r", "s", None) == ["end_user"]
    assert svc.enforce_access_levels_for_contact("r", "s", []) == ["end_user"]


def test_empty_with_multiple_active_raises_422():
    svc = _service_with_active([("sorento_dealer", "Sorento Dealer"), ("end_user", "End User")])
    with pytest.raises(HTTPException) as exc:
        svc.enforce_access_levels_for_contact("r", "s", None)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "ACCESS_LEVELS_REQUIRED"


def test_dedupe_across_variants():
    svc = _service_with_active([("sorento_dealer", "Sorento Dealer")])
    result = svc.enforce_access_levels_for_contact(
        "r", "s", ["Sorento Dealer", "sorento_dealer", "Sorento Dealers", "dealer"]
    )
    assert result == ["sorento_dealer"]


# ---------------- keyword-alias resolution ----------------


def test_keyword_alias_resolves():
    """Admin-curated keyword on the row resolves a free-text input."""
    svc = _service_with_active([
        ("end_user", "End User", ["customer", "consumer", "homeowner"]),
    ])
    assert svc.enforce_access_levels_for_contact("r", "s", ["customer"]) == ["end_user"]
    assert svc.enforce_access_levels_for_contact("r", "s", ["Homeowner"]) == ["end_user"]


def test_keyword_alias_ambiguity_raises():
    """Same keyword on two active rows → ambiguous 403."""
    svc = _service_with_active([
        ("end_user", "End User", ["customer"]),
        ("vip_user", "VIP User", ["customer"]),
    ])
    with pytest.raises(HTTPException) as exc:
        svc.enforce_access_levels_for_contact("r", "s", ["customer"])
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "ACCESS_LEVELS_AMBIGUOUS"


# ---------------- reverse-subset (noisy phrase) ----------------


def test_reverse_subset_extra_words_match():
    """Caller adds qualifier words around the canonical name — still resolves."""
    svc = _service_with_active([("end_user", "End User")])
    assert svc.enforce_access_levels_for_contact("r", "s", ["end user as customer"]) == ["end_user"]
    assert svc.enforce_access_levels_for_contact("r", "s", ["the sorento end user account"]) == ["end_user"]
