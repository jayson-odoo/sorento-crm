"""HELD-OVER-NAMED-CLASS (CHAT-CLOSED-LISTS, TRAIN cp0-41147cbf9f, 7a655af8fa, c026f64f50; synthetic codes).

A message that names its own subject by CLASS (a current-message entity hinted `category` or
`product_type`) plus a scheme or a brand, and no product code, is not about the products the
conversation still holds from an unrelated earlier turn. The held products used to become the
subject, the engine replaced the class fetch's answer with "<held>: no SPAN certificate on
record." / "<held>: none on record with <brand>", and the correct files were thrown away.
"""
from __future__ import annotations

import json
import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.certificate import Certificate, CertificateProduct, CertificateRevision
from app.models.product import Brand, Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import _envelope
from tests.chatbot.test_closed_lists_scheme_held_none import (  # noqa: F401
    SCHEME, _file_ask, _kind, _message, _product, _scheme as _scheme_pick, _stock, _text, _turns, seeded, stub_access,
)


def _seed(session_factory) -> dict[str, str]:
    db = session_factory()
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    cert_type = AttachmentType(
        id=str(uuid.uuid4()), type_name="ZZT Certification", description="Certification by Purchasing",
        allowed_extensions="pdf", is_certificate=True,
    )
    brand = Brand(id=str(uuid.uuid4()), brand_code="ZZSORENTO", brand_name="ZZSORENTO", company_id=DEFAULT_COMPANY_ID)
    cats = {
        key: ProductCategory(
            id=str(uuid.uuid4()), category_code=unique_code(key.upper())[:50], category_name=name, class_label=name, search_synonyms=[name], company_id=DEFAULT_COMPANY_ID,
        )
        for key, name in (("wb", "ZZ Wash Basin"), ("sh", "Shower"), ("av", "Zyx Angle Valve"))
    }
    db.add_all([uom, cert_type, brand, *cats.values()])
    db.flush()
    backfill_category_signals(db)
    seed_spec_registry(db)
    ids: dict[str, str] = {}

    def product(code: str, cat: str, *, brand_row=None, cert: bool = False) -> None:
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"ZZT {code}", description=f"SORENTO {cats[cat].class_label.upper()} {code}", is_active=True, category_id=cats[cat].id, base_uom_id=uom.id,
            list_price=1, company_id=DEFAULT_COMPANY_ID, brand_id=brand_row.id if brand_row else None,
        )
        db.add(p)
        db.flush()
        derive_for_code(db, code)
        ids[code] = p.id
        if not cert:
            return
        att = Attachment(
            id=str(uuid.uuid4()), original_filename=f"{code}_{SCHEME}.pdf", stored_filename=uuid.uuid4().hex,
            file_path=f"https://cdn.test/{code}.pdf", attachment_type_id=cert_type.id, is_deleted=False, company_id=DEFAULT_COMPANY_ID,
        )
        db.add(att)
        db.flush()
        db.add(ProductAttachment(id=str(uuid.uuid4()), product_id=p.id, attachment_id=att.id, company_id=DEFAULT_COMPANY_ID))
        c = Certificate(
            id=str(uuid.uuid4()), attachment_type_id=cert_type.id, scheme=SCHEME, certificate_number=uuid.uuid4().hex[:10],
            status="active", company_id=None,
        )
        db.add(c)
        db.flush()
        db.add(CertificateRevision(id=str(uuid.uuid4()), certificate_id=c.id, revision_no=1, attachment_id=att.id, is_current=True))
        db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=c.id, product_id=p.id, source="manual"))
        db.flush()
        ids[f"cert:{code}"] = c.id

    product("ZZWB1", "wb")
    product("ZZCWB1", "wb")
    product("ZZSH1", "sh", cert=True)
    product("ZZAV1", "av", brand_row=brand, cert=True)
    product("ZZAV2", "av", brand_row=brand, cert=True)
    db.commit()
    return ids


def _category(raw: str, canonical=None) -> dict:
    """As the real parses read: hint `category`, the customer's own word, canonical code null or a slug."""
    return {"raw": raw, "hint": "category", "canonical_code": canonical, "current_message": True, "confident": True}


def _kind_pick(raw: str = "cert") -> dict:
    """The real parse's kind pick ("span", "cert"): attachment_type, canonical `certificate`."""
    return {"raw": raw, "hint": "attachment_type", "canonical_code": "certificate", "listed_item": "ZZT Certification",
            "current_message": True, "confident": True}


def _span_pick() -> dict:
    """The real parse's scheme pick: raw 'span', canonical `certificate`, listed_item the scheme."""
    return {"raw": "span", "hint": "attachment_type", "canonical_code": "certificate", "listed_item": SCHEME,
            "current_message": True, "confident": True}


def _ask(*entities: dict) -> dict:
    """The real parse's top-level fields (cp0-41147cbf9f, c026f64f50): apply's new-ask / drop-held
    path keys on `domain_in_message`."""
    return {
        **_file_ask(*entities), "domain_in_message": True, "domain_hint": "product_attachment",
        "intent_hint": "check_product_attachment", "entity_op": "replace_combine", "scope_intent": "specific",
        "message_type": "business_query", "continuation": False, "topic_reset": False, "match_mode": "and",
        "anaphora": {"backward_reference": False},
        "open_question_answer": {"mode": None, "items": [], "picked": [], "qty_for_all": None},
    }


def _scheme(word: str = SCHEME) -> dict:
    return _scheme_pick(word)


def _brand() -> dict:
    return {"raw": "ZZSORENTO", "hint": "brand", "canonical_code": "ZZSORENTO", "current_message": True, "confident": True}


def _turns_with_files(session_factory, stub_access, monkeypatch, turns, ids):
    """As `_turns`, but the attachments fetch answers with one certificate file per asked product
    that holds one (the envelope shape the MCP presenter returns)."""
    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k", closed_lists=True,
        )

    queue = [verdict for _text_, verdict in turns]
    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: queue.pop(0))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    calls: list[tuple[str, dict]] = []
    holders = {ids[code]: code for code in ("ZZSH1", "ZZAV1", "ZZAV2")}

    def call_tool(self, name, args):
        calls.append((name, args))
        if name != "crm_master_product_attachments_list":
            return json.dumps({"ok": True, "items": []})
        rows = [(holders[pid], f"{holders[pid]}_{SCHEME}.pdf") for pid in args.get("product_ids") or [] if pid in holders]
        return json.dumps({
            "result_type": "product_attachments", "intro": "I have attached the file(s) below.", "ok": True,
            "items": [
                {"title": code, "flags": {"discontinued": False, "expired": False, "expiring_soon": False}, "fields": [
                    {"label": "Product Code", "value": code}, {"label": "Attachment Type", "value": "ZZT Certification"},
                    {"label": "File Name", "value": name},
                ]} for code, name in rows
            ],
            "attachments": [{"url": f"https://example.invalid/{name}", "filename": name, "mimeType": "application/pdf",
                             "attachmentType": "ZZT Certification"} for _code, name in rows],
            "action_links": [], "last_updated_at": None, "has_result": bool(rows),
        })

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", call_tool)
    stub_access()
    out = []
    for n, (text, _verdict) in enumerate(turns):
        calls.clear()
        out.append((engine_mod.run_turn(_envelope(message=_message(text, n)), session_factory=session_factory), list(calls)))
    return out


def _product_fetches(calls) -> list[dict]:
    return [a for n, a in calls if n == "crm_master_product_attachments_list"]


def test_a_scheme_over_a_named_class_is_not_about_the_held_product(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory)

    (_r1, _c1), (r2, c2) = _turns_with_files(
        session_factory, stub_access, monkeypatch,
        [("ZZWB1", _stock(_product("ZZWB1"))),
         ("Shower span cert", _ask(_category("shower"), _span_pick()))],
        ids,
    )

    text = _text(r2)
    assert not text.startswith("ZZWB1:"), (text, c2)
    fetches = _product_fetches(c2)
    assert all(ids["ZZWB1"] not in (args.get("product_ids") or []) for args in fetches), c2
    assert any(
        ids["ZZSH1"] in (args.get("product_ids") or []) and ids["cert:ZZSH1"] in (args.get("certificate_ids") or [])
        for args in fetches
    ), (text, c2)
    assert "ZZWB1" not in text, text


def test_a_brand_over_a_named_class_is_not_about_the_held_product(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory)

    (_r1, _c1), (r2, c2) = _turns_with_files(
        session_factory, stub_access, monkeypatch,
        [("ZZCWB1", _stock(_product("ZZCWB1"))),
         ("sorento angle valve cert", _ask(_brand(), _category("zyx angle valve"), _kind_pick()))],
        ids,
    )

    text = _text(r2)
    assert "none on record" not in text, (text, c2)
    assert not text.startswith("ZZCWB1:"), text
    fetches = _product_fetches(c2)
    assert all(ids["ZZCWB1"] not in (args.get("product_ids") or []) for args in fetches), c2
    assert any({ids["ZZAV1"], ids["ZZAV2"]} <= set(args.get("product_ids") or []) for args in fetches), (text, c2)
    assert "ZZCWB1" not in text, text


def test_guard_no_class_entity_still_takes_the_held_path(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)

    (_r1, _c1), (r2, _c2) = _turns(
        session_factory, stub_access, monkeypatch,
        [("ZZWB1", _stock(_product("ZZWB1"))), ("Span certificate", _file_ask(_scheme(), _kind()))],
    )

    assert _text(r2) == f"ZZWB1: no {SCHEME} certificate on record.", _text(r2)
