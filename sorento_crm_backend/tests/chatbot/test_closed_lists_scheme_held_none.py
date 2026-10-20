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


# --- R2-4 KIND-NONE-HELD (reviewer nit, ruling (b) safety) -----------------------------------


def _no_kind_world(session_factory, code: str, *, scheme_out_of_scope: bool = False) -> dict[str, str]:
    from sqlalchemy import text

    from app.models.company import Company

    ids = _seed(session_factory, {code: OTHERS})
    db = session_factory()
    db.execute(text("UPDATE attachment_types SET is_certificate = false"))
    if scheme_out_of_scope:
        other = "00000000-0000-0000-0000-000000000002"
        db.add(Company(id=other, name="Other", code=unique_code("OTH")[:20]))
        db.flush()
        db.execute(text("UPDATE certificates SET company_id = :c WHERE scheme = :s"), {"c": other, "s": SCHEME})
    db.commit()
    return ids


def _spy_scheme_without_product(monkeypatch) -> list:
    from app.services.chatbot.head import scheme_index

    notes: list = []
    real = scheme_index.scheme_without_product

    def spy(*args, **kwargs):
        out = real(*args, **kwargs)
        notes.append(out[1])
        return out

    monkeypatch.setattr(scheme_index, "scheme_without_product", spy)
    return notes


@pytest.mark.parametrize("out_of_scope", [False, True], ids=["scheme in scope", "scheme out of scope"])
def test_with_no_certificate_kind_listed_a_held_product_keeps_the_turn_off_scheme_without_product(
    out_of_scope, session_factory, seeded, stub_access, monkeypatch
):
    """No attachment type is a certificate kind and a product is held (in the conversation
    focus, not yet in the verdict). `scheme_without_product` must not run: the held product is
    never dropped and the reply is never the bare `No <SCHEME> certificate on record.` without
    the held code. What the turn does instead is asserted, not left to an empty fetch list."""
    ids = _no_kind_world(session_factory, "ZZTKN1", scheme_out_of_scope=out_of_scope)
    notes = _spy_scheme_without_product(monkeypatch)

    (_r1, _c1), (r2, c2) = _turns(
        session_factory, stub_access, monkeypatch,
        [("ZZTKN1", _stock(_product("ZZTKN1"))), ("Span certificate", _file_ask(_scheme()))],
    )

    text = _text(r2)
    assert not [n for n in notes if n], notes
    assert text != f"No {SCHEME} certificate on record.", text
    assert "ZZTKN1" in text, (text, c2)
    fetches = [args for name, args in c2 if name == "crm_master_product_attachments_list"]
    assert all(args.get("product_ids") == [ids["ZZTKN1"]] for args in fetches), c2
    assert not [c for c in c2 if c[0] == "crm_resource_attachments_list"], c2


def test_scheme_without_product_never_runs_when_the_verdict_holds_a_product(session_factory):
    """`scheme_without_product` filtered every carried product out of the verdict and sent the
    scheme's whole list. A verdict holding any product entity (said, or carried with a uuid)
    is left exactly as it is, with no note."""
    from app.models.base import set_company_scope
    from app.services.chatbot.head.scheme_index import scheme_without_product

    ids = _seed(session_factory, {"ZZTKN2": OTHERS})
    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    carried = {"raw": "ZZTKN2", "hint": "product", "canonical_code": "ZZTKN2", "uuid": ids["ZZTKN2"],
               "current_message": False, "confident": True}
    verdict = {"domain_hint": "product_attachment", "entities": [carried, {**_scheme(), "listed": "cert_scheme"}]}

    assert scheme_without_product(db, verdict) == (verdict, None)
