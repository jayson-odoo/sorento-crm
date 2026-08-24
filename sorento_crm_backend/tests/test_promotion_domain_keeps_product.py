"""domain_hint=promotion must KEEP resolved products and surface their promos.

Regression: a product SKU resolved cleanly under domain_hint=promotion, but the
expander replaced the product matches with description-text promo matches only.
A SKU never matches a promo description, so a valid product returned empty. Now
the expander keeps the products AND walks promotion_products backward (via
_build_promotions_for_products) to surface the containing promos (incl inactive,
flagged). See references.py _expand_products_via_promotions.
"""
from app.api.v1.system import references as R


def _patch_helpers(monkeypatch, *, token_promos, member_promos):
    # No promo matches by DESCRIPTION text (a SKU never matches a promo desc).
    monkeypatch.setattr(R, "_resolve_promotion_ids_for_token", lambda db, tok, codes: set(token_promos))
    monkeypatch.setattr(R, "_build_promotion_resolutions", lambda db, ids: [])
    # Reverse membership walk: the promos that CONTAIN the resolved products.
    monkeypatch.setattr(R, "_build_promotions_for_products", lambda db, uuids, codes: list(member_promos))
    # These must NOT fire once a member promo exists (promo-first short-circuit).
    monkeypatch.setattr(R, "_build_product_resolutions_from_promotions", lambda *a, **k: [("SHOULD_NOT_RUN")])
    monkeypatch.setattr(R, "_resolve_products_by_brand_access", lambda *a, **k: [("SHOULD_NOT_RUN")])


def test_product_kept_and_member_promo_surfaced(monkeypatch):
    product = {
        "entity_type": "product",
        "uuid": "p-uuid-1",
        "canonical_code": "SRTWC8517-SH-UF",
        "display": {"product_name": "SRTWC8517-SH-UF", "is_active": True},
    }
    member_promo = {
        "entity_type": "promotion",
        "uuid": "promo-uuid-1",
        "canonical_code": "promo-uuid-1",
        "match_field": "promotion_membership",
        "match_tier": "via_product",
        "display": {"description": "A3 FLYER", "is_active": False, "products": ["SRTWC8517-SH-UF"]},
    }
    _patch_helpers(monkeypatch, token_promos=set(), member_promos=[member_promo])

    result = {"resolutions": [{"token": "SRTWC8517-SH-UF", "matches": [product], "ambiguous": False}]}
    out = R._expand_products_via_promotions(
        db=None, result=result, tokens=["SRTWC8517-SH-UF"], access_level_names=[], wants_products=True
    )

    matches = out["resolutions"][0]["matches"]
    kinds = [(m["entity_type"], m["uuid"]) for m in matches]
    # Product is KEPT (the core requirement) …
    assert ("product", "p-uuid-1") in kinds
    # … and its promo is surfaced via membership, ahead of the product.
    assert ("promotion", "promo-uuid-1") in kinds
    assert kinds.index(("promotion", "promo-uuid-1")) < kinds.index(("product", "p-uuid-1"))
    # Token is resolved (has matches), not stranded as unresolved.
    assert out["unresolved_tokens"] == []


def test_product_kept_even_when_no_promo_at_all(monkeypatch):
    """No promo (desc OR membership) - product still returned, never wiped."""
    product = {
        "entity_type": "product",
        "uuid": "p-uuid-2",
        "canonical_code": "SRTWC9615",
        "display": {"product_name": "SRTWC9615", "is_active": True},
    }
    _patch_helpers(monkeypatch, token_promos=set(), member_promos=[])

    result = {"resolutions": [{"token": "SRTWC9615", "matches": [product], "ambiguous": False}]}
    out = R._expand_products_via_promotions(
        db=None, result=result, tokens=["SRTWC9615"], access_level_names=[], wants_products=True
    )

    matches = out["resolutions"][0]["matches"]
    assert [m["uuid"] for m in matches] == ["p-uuid-2"]
    assert out["unresolved_tokens"] == []
