"""The brand and company a set of product rows belongs to, read for routing (#865).

Core, not the chatbot package: the bot's escalation lane (`focus_product_origin`) and the
quotation drawing/photo request (`product_drawing_request_service`) route by the same rule,
and core must never import `app.services.chatbot` (`tests/chatbot/test_import_boundary.py`).
The package imports this instead.
"""
from __future__ import annotations

from typing import Any, Iterable

# `escalation-context`'s own STOPGAP mirror of the parser fork's map. The real source is
# the CRM `companies.code` column threaded through the resolver; kept byte-identical here
# and in `head/output_exchange.CO_ALIASES` until that lands. `lanes/escalation.py`
# re-exports it under the same name.
CO_ALIASES: dict[str, list[str]] = {
    "sorento": ["sorento", "srt"],
    "mocha": ["mocha", "mch"],
    "cabana": ["cabana", "cbn"],
}


def company_brand(name: Any, code: Any) -> str | None:
    """The brand a company's name stands for, or None (fix round 4).

    The Mocha company sells only the MOCHA brand, and its rows carry no brand row, so
    the company is the brand. The incumbent Sorento company is not: it carries several
    brands (SORENTO, MOCHA), so a Sorento row without a brand row names none, as before.
    Keyed off `CO_ALIASES`, the escalation lane's own company vocabulary.
    """
    keys = {str(v).strip().lower() for v in (name, code) if v}
    for brand, aliases in CO_ALIASES.items():
        if brand != "sorento" and keys & {brand, *aliases}:
            return brand
    return None


def product_origin(db: Any, product_ids: Iterable[str]) -> dict[str, Any]:
    """`{brand, company}` of the product rows `product_ids` names, across every company.

    A row's brand is its brand row, else the brand its company stands for
    (`company_brand`). One brand is the answer; rows that disagree name none, because a
    guess there picks a person for the wrong brand. Lower-cased, the spelling
    `next-assignee` narrows by. `company` names where the rows were found.
    """
    ids = sorted({str(pid) for pid in product_ids if pid})
    if not ids:
        return {"brand": None, "company": None}
    from sqlalchemy import func

    from app.models.base import company_scope
    from app.models.company import Company
    from app.models.product import Brand, Product

    # A savepoint, so a read that fails aborts only itself and never the caller's unit of
    # work. This read is for routing only; the caller's company scope is restored after it.
    with db.begin_nested(), company_scope(db, None):
        rows = (
            db.query(func.lower(Brand.brand_code), Company.name, Company.code)
            .select_from(Product)
            .outerjoin(Brand, Brand.id == Product.brand_id)
            .join(Company, Company.id == Product.company_id)
            .filter(Product.id.in_(ids))
            .distinct()
            .all()
        )
    brands = sorted(
        {
            str(brand).strip() if brand and str(brand).strip() else company_brand(name, company_code)
            for brand, name, company_code in rows
        }
        - {None}
    )
    companies = sorted({str(name) for _brand, name, _code in rows if name})
    return {
        "brand": brands[0] if len(brands) == 1 else None,
        "company": " and ".join(companies) or None,
    }
