"""Strip domain-noise tokens from free-text `query` parameters.

The chatbot routes user phrases like "kitchen sink promotion" into the MCP
promotions tool's `query` arg. The word "promotion" is conversational
context — the actual promotion in the DB is "Kitchen Sink Special". Searching
"kitchen sink promotion" against `Promotion.name` ILIKE matches nothing.

This normalizer keeps the per-domain stopword catalog in ONE place. Each
list endpoint passes its own `domain_key`. Adding a new stopword (or a new
domain) is a config edit here — no prompt change, no per-route diff.
"""
from __future__ import annotations

import re
from typing import Optional

# domain_key → tokens to strip (lowercased, punctuation-free).
# Tokens are matched whole-word, case-insensitive, after stripping common
# trailing punctuation. Keep singular AND plural / common variants.
DOMAIN_STOPWORDS: dict[str, set[str]] = {
    "promotion": {
        "promotion", "promotions", "promo", "promos",
        "campaign", "campaigns",
        "offer", "offers", "deal", "deals",
    },
    "order": {
        "order", "orders", "so", "sales",
    },
    "delivery_order": {
        "delivery", "deliveries", "do", "dispatch", "dispatches", "shipment", "shipments",
    },
    "goods_receiving": {
        "grn", "grns", "receiving", "incoming", "inbound",
    },
    "stock": {
        "stock", "stocks", "inventory", "inventories",
    },
    "product": {
        "product", "products", "item", "items", "sku", "skus",
    },
    "marketing_form": {
        "form", "forms", "submission", "submissions",
    },
    "product_image": {
        "image", "images", "photo", "photos", "picture", "pictures",
    },
}

_TOKEN_SPLIT_RE = re.compile(r"\s+")
_PUNCT_STRIP = ".,!?;:\"'()[]{}"


def strip_domain_stopwords(query: Optional[str], domain_key: str) -> Optional[str]:
    """Remove domain-noise tokens from `query` for the given `domain_key`.

    Returns the stripped string. If stripping leaves nothing meaningful,
    returns the ORIGINAL query (so downstream search still has something
    to match against rather than degenerating to a list-all). Returns
    None / empty unchanged.
    """
    if not query or not query.strip():
        return query
    stop = DOMAIN_STOPWORDS.get(domain_key)
    if not stop:
        return query

    tokens = [t for t in _TOKEN_SPLIT_RE.split(query.strip()) if t]
    kept = [t for t in tokens if t.lower().strip(_PUNCT_STRIP) not in stop]
    stripped = " ".join(kept).strip()

    # Don't reduce the query to empty — that turns a search into list-all.
    if not stripped:
        return query
    return stripped
