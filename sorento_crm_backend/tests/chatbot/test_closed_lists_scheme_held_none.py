"""CHAT-CLOSED-LISTS HELD-WITHOUT-SCHEME (crew ruling (b), 18 Oct; TRAIN cp0-9010f39a3d,
cp0-9f9e15dd0c, cp0-7a655af8fa; synthetic codes).

A held product (or three) and a listed scheme pick the held products do not hold: the held
products stay the subject, the product-attachments fetch names them with the scheme's
certificates as the filter, and nothing of that scheme is replied exactly
`<held codes, comma-joined in held order>: no <SCHEME as on file> certificate on record.`
Never another scheme's files, never a cert-number did-you-mean, never a refetch without the
product, never a switch to crm_resource_attachments_list.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.certificate import Certificate, CertificateRevision
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, seeded, stub_access  # noqa: F401

SCHEME = "ZZSPAN"
OTHERS = ("ZZPPS", "ZZWCM")


def _seed(session_factory, products: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """products: code -> the schemes it holds a filed certificate of. The SCHEME is always on
    file as a certificate of some unrelated product's document so it is a listed scheme."""
    db = session_factory()
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT WC", company_id=DEFAULT_COMPANY_ID,
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    cert_type = AttachmentType(
        id=str(uuid.uuid4()), type_name="ZZT Certification", description="Certification by Purchasing",
        allowed_extensions="pdf", is_certificate=True,
    )
    db.add_all([cat, uom, cert_type])
    db.flush()
    ids: dict[str, str] = {}

    def product(code: str) -> Product:
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"ZZT {code}", category_id=cat.id, base_uom_id=uom.id,
            list_price=1, company_id=DEFAULT_COMPANY_ID,
        )
        db.add(p)
        db.flush()
        ids[code] = p.id
        return p

    def certificate(owner: Product, scheme: str, key: str) -> None:
        att = Attachment(
            id=str(uuid.uuid4()), original_filename=f"{owner.product_code}_{scheme}.pdf", stored_filename=uuid.uuid4().hex,
            file_path=f"https://cdn.test/{uuid.uuid4().hex}.pdf", attachment_type_id=cert_type.id, is_deleted=False,
            company_id=DEFAULT_COMPANY_ID,
        )
        db.add(att)
        db.flush()
        db.add(ProductAttachment(id=str(uuid.uuid4()), product_id=owner.id, attachment_id=att.id, company_id=DEFAULT_COMPANY_ID))
        cert = ids.get(f"cert:{scheme}")
        if cert is None:
            c = Certificate(
                id=str(uuid.uuid4()), attachment_type_id=cert_type.id, scheme=scheme,
                certificate_number=uuid.uuid4().hex[:10], status="active", company_id=None,
            )
            db.add(c)
            db.flush()
            ids[f"cert:{scheme}"] = cert = c.id
        n = int(ids.get(f"revs:{scheme}", 0)) + 1
        ids[f"revs:{scheme}"] = str(n)  # one current revision per certificate
        db.add(CertificateRevision(
            id=str(uuid.uuid4()), certificate_id=cert, revision_no=n, attachment_id=att.id, is_current=n == 1,
        ))

    for code, schemes in products.items():
        owner = product(code)
        for scheme in schemes:
            certificate(owner, scheme, scheme)
    stranger = product("ZZSTRANGER1")
    certificate(stranger, SCHEME, SCHEME)
    for scheme in OTHERS:
        if f"cert:{scheme}" not in ids:
            certificate(stranger, scheme, scheme)
    db.commit()
    return ids


def _message(text: str, n: int) -> dict[str, Any]:
    return {
        "event_type": "message.received",
        "contact": {"id": CONTACT_ID},
        "message": {
            "messageId": f"ZZT-hn-{n}-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
            "traffic": "incoming", "message": {"type": "text", "text": text},
        },
    }


def _turns(session_factory, stub_access, monkeypatch, turns, *, gate: bool = True):
    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k", closed_lists=gate,
        )

    queue = [verdict for _text, verdict in turns]
    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: queue.pop(0))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        MCPRuntimeClient, "call_tool", lambda self, name, args: calls.append((name, args)) or json.dumps({"ok": True, "items": []})
    )
    stub_access()
    out = []
    for n, (text, _verdict) in enumerate(turns):
        calls.clear()
        out.append((engine_mod.run_turn(_envelope(message=_message(text, n)), session_factory=session_factory), list(calls)))
    return out


def _product(code: str) -> dict:
    return {"raw": code, "hint": "product", "canonical_code": code, "current_message": True, "confident": True}


def _scheme(word: str = SCHEME) -> dict:
    return {"raw": word, "hint": "attachment_type", "canonical_code": SCHEME, "listed_item": SCHEME,
            "current_message": True, "confident": True}


def _kind() -> dict:
    return {"raw": "certificate", "hint": "attachment_type", "canonical_code": "certificate", "listed_item": "ZZT Certification",
            "current_message": True, "confident": True}


def _stock(*entities: dict) -> dict:
    return _parser_output(intent_hint="check_stock", domain_hint="inventory", user_goal="stock", entities=list(entities))


def _file_ask(*entities: dict) -> dict:
    return _parser_output(
        intent_hint="check_product_attachment", domain_hint="product_attachment", user_goal="file", entities=list(entities)
    )


def _text(result) -> str:
    return (result.reply or {}).get("text") or ""


def _assert_held_none(result, calls, ids, held: list[str]) -> None:
    text = _text(result)
    assert text == f"{', '.join(held)}: no {SCHEME} certificate on record.", (text, calls)
    assert "Did you mean" not in text, text
    assert not [c for c in calls if c[0] == "crm_resource_attachments_list"], calls
    for name, args in calls:
        if name == "crm_master_product_attachments_list":
            # a fetch, if sent, is about the held products and the scheme's certificates only
            assert args.get("product_ids") == [ids[c] for c in held], calls
            assert args.get("certificate_ids") == [ids[f"cert:{SCHEME}"]], calls


@pytest.mark.parametrize("with_kind", [False, True], ids=["scheme only", "scheme and certificate kind"])
def test_a_held_product_without_the_scheme_says_so_and_sends_nothing_else(with_kind, session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, {"ZZTCGB762": OTHERS})
    ask = _file_ask(_scheme(), *([_kind()] if with_kind else []))

    (_r1, _c1), (r2, c2) = _turns(
        session_factory, stub_access, monkeypatch, [("ZZTCGB762", _stock(_product("ZZTCGB762"))), ("Span certificate", ask)]
    )

    _assert_held_none(r2, c2, ids, ["ZZTCGB762"])


def test_three_held_products_with_nothing_are_named_in_held_order(session_factory, seeded, stub_access, monkeypatch):
    held = ["ZZTHA3", "ZZTHB1", "ZZTHC2"]
    ids = _seed(session_factory, {code: () for code in held})

    (_r1, _c1), (r2, c2) = _turns(
        session_factory, stub_access, monkeypatch,
        [("three codes", _stock(*[_product(c) for c in held])), ("Span certificate", _file_ask(_scheme(), _kind()))],
    )

    _assert_held_none(r2, c2, ids, held)


def test_guard_a_held_product_holding_the_scheme_still_gets_only_that_schemes_files(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, {"ZZTHOLDS1": (*OTHERS, SCHEME)})

    (_r1, _c1), (r2, c2) = _turns(
        session_factory, stub_access, monkeypatch,
        [("ZZTHOLDS1", _stock(_product("ZZTHOLDS1"))), ("Span certificate", _file_ask(_scheme(), _kind()))],
    )

    fetches = [args for name, args in c2 if name == "crm_master_product_attachments_list"]
    assert fetches and fetches[0].get("product_ids") == [ids["ZZTHOLDS1"]], (_text(r2), c2)
    assert fetches[0].get("certificate_ids") == [ids[f"cert:{SCHEME}"]], fetches
    assert "no ZZSPAN certificate on record" not in _text(r2), _text(r2)
