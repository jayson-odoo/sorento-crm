"""#2397 reviewer re-check (crew 14 Nov, option b): two guards the #2370 regression fix lacked.

1. `code_sizes._offerable_rows` drops a product hidden from the chat (`chat_searchable_products`),
   fed a hidden row directly. Upstream probes already filter hidden rows today, so this pins the
   safety net itself: it fails if the filter is removed.
2. Order with a predicate: a letters-only token the parser hands as a PRODUCT (the AC-19 case:
   "ABCDE" misses but sits inside catalogue codes ABCDE-K / ABCDE-M) together with a certificate
   filter gets the certificate miss ("Couldn't find ... certificate"), not a list of its substring
   neighbours. AC-19's widening stays on the did-you-mean paths only (answer.py described-set guard).
"""

from __future__ import annotations

import uuid
from typing import Any

from tests._pg_fixture import blank_session, unique_code


def _company_category_uom(db: Any, prefix: str, *, category_searchable: bool = True):
    from app.models.company import Company
    from app.models.product import ProductCategory, UnitOfMeasure

    company = Company(id=str(uuid.uuid4()), code=unique_code(prefix)[:50], name=unique_code(prefix))
    db.add(company)
    db.flush()
    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("CAT")[:50],
        category_name=f"ZZT {prefix} category",
        company_id=company.id,
        is_searchable=category_searchable,
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:20], uom_name="Each", company_id=company.id)
    db.add_all([category, uom])
    db.flush()
    return company, category, uom


def _product(db: Any, company: Any, category: Any, uom: Any, code: str, **extra: Any):
    from app.models.product import Product

    p = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=extra.pop("product_name", code),
        description=extra.pop("description", "ZZT TEST PRODUCT"),
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=10,
        is_active=True,
        company_id=company.id,
        **extra,
    )
    db.add(p)
    return p


def test_offerable_rows_drops_a_product_hidden_from_the_chat():
    from app.models.base import set_company_scope
    from app.services.chatbot.lanes.business.code_sizes import _offerable_rows

    with blank_session() as db:
        company, category, uom = _company_category_uom(db, "ZZTOR")
        _, hidden_category, _ = _company_category_uom(db, "ZZTORH", category_searchable=False)
        visible = _product(db, company, category, uom, unique_code("ZZTVIS")[:40])
        hidden_own = _product(db, company, category, uom, unique_code("ZZTHID")[:40], is_searchable=False)
        hidden_cat = _product(db, company, hidden_category, uom, unique_code("ZZTHCT")[:40])
        db.commit()
        set_company_scope(db, frozenset({company.id, hidden_category.company_id}))

        rows = [
            {"uuid": visible.id, "code": visible.product_code},
            {"uuid": hidden_own.id, "code": hidden_own.product_code},
            {"uuid": hidden_cat.id, "code": hidden_cat.product_code},
        ]
        kept = [r["code"] for r in _offerable_rows(db, rows)]

    assert kept == [visible.product_code], kept


def test_predicate_with_letters_only_parser_product_gets_the_certificate_miss_not_its_neighbours():
    from app.models.base import set_company_scope
    from app.services.chatbot.lanes.business import resolve_gate
    from app.services.chatbot.lanes.business.answer import not_found_error_message
    from app.services.chatbot.lanes.business.services import ResolveGateServices
    from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
    from app.config import settings

    with blank_session() as db:
        company, category, uom = _company_category_uom(db, "ZZTAC")
        for code in ("ABCDE-K", "ABCDE-M"):
            _product(db, company, category, uom, code)
        db.commit()
        set_company_scope(db, frozenset({company.id}))

        def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
            payload = {**body, "spec_fallback": False, "understand_phrase": False}
            principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
            return resolve_reference_post(ResolveReferenceRequest(**payload), current_user=principal, db=db)

        services = ResolveGateServices(access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None)
        ctx = {
            "text": {"message": {"message": {"text": "ABCDE has cert?"}}},
            "contact": {"id": "999"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_product_attachment",
                    "domain_hint": "product_attachment",
                    "match_mode": "or",
                    "access_levels": [],
                    "entities": [
                        {"raw": "ABCDE", "hint": "product"},
                        {"raw": "cert", "hint": "attachment_type"},
                    ],
                }
            },
        }
        out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")
        msg = not_found_error_message(
            {}, parser=ctx["parse"]["output"], resolved=out.get("resolved") or {}, gate=out.get("gate") or {}
        )
        text = (msg.get("escalate_message") or "").strip()

    assert text.startswith("Couldn't find"), text
    assert "certificate" in text.lower(), text
    assert not text.startswith("Here's what you want"), text
