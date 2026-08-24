"""Strip domain-noise tokens from free-text `query` parameters.

The chatbot routes user phrases like "kitchen sink promotion" into the MCP
promotions tool's `query` arg. The word "promotion" is conversational
context - the actual promotion in the DB is "Kitchen Sink Special". Searching
"kitchen sink promotion" against `Promotion.name` ILIKE matches nothing.

This normalizer keeps the per-domain stopword catalog in ONE place. Each
list endpoint passes its own `domain_key`. Adding a new stopword (or a new
domain) is a config edit here - no prompt change, no per-route diff.
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
    # NOTE: image / photo / picture / drawing / certificate are NOT stopwords.
    # They are real `attachment_type.type_name` tokens ("Product Photos",
    # "Technical Drawing", "Certificate of Conformity"). Stripping them broke
    # multi-word entity-token resolution like "actual photo" → "actual",
    # which then substring-matched the wrong attachment_type row.
    # Entity-label noise that the upstream agent often prepends to the actual
    # value ("Customer Chin Chun", "Supplier Sorento Sdn Bhd"). Without these,
    # the resolver's fuzzy ILIKE / embedding both run against the label-polluted
    # token and miss the real row. Union into _ENTITY_STOPWORDS in
    # `app/api/v1/system/references.py:_strip_entity_stopwords`.
    "customer": {
        "customer", "customers",
        "client", "clients",
        "debtor", "debtors",
        "company", "account",
    },
    "supplier": {
        "supplier", "suppliers",
        "vendor", "vendors",
    },
    "brand": {
        "brand", "brands",
    },
    "warehouse": {
        "warehouse", "warehouses",
        "location", "locations",
    },
    "transporter": {
        "transporter", "transporters",
        "carrier", "carriers",
        "courier", "couriers",
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
    trimmed = query.strip()
    stop = DOMAIN_STOPWORDS.get(domain_key)
    if not stop:
        return trimmed

    tokens = [t for t in _TOKEN_SPLIT_RE.split(trimmed) if t]
    kept = [t for t in tokens if t.lower().strip(_PUNCT_STRIP) not in stop]
    stripped = " ".join(kept).strip()

    # Don't reduce the query to empty - that turns a search into list-all.
    if not stripped:
        return trimmed
    return stripped
