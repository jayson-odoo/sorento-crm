"""Brands whose promotions carry no selling price (CABANA-NO-SELLING-PRICE, 2 Nov 2026).

`Brand.no_promo_selling_price` is the one switch. Writers (the n8n external promotions
API, the promotion editor) drop or refuse a selling price and the discount derived from
it on such a brand's promotion lines; readers (price tags, the promotion-products API
that MCP and the chatbot read) never show one, so flipping the flag hides old values
without a data change.
"""
from __future__ import annotations

from typing import Optional


def brand_has_no_selling_price(product) -> bool:
    """Whether `product`'s brand says its promotions carry no selling price."""
    brand = getattr(product, "brand", None) if product is not None else None
    return bool(getattr(brand, "no_promo_selling_price", False))


def refusal_message(product) -> str:
    brand = getattr(product, "brand", None)
    name: Optional[str] = getattr(brand, "brand_name", None) or getattr(brand, "brand_code", None)
    return f"{name or 'This brand'} promotions carry no selling price."
