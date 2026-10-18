"""CHAT-CLOSED-LISTS SCHEME-NO-PRODUCT (TRAIN cp0-fce51f2811; residual 1 of 7b7db72b; synthetic codes).

Nothing held (the previous bot message was a product did-you-mean, not picked) and the message
is "Span certificate" (a listed scheme pick). The clarify policy for domain product_attachment is
DEFAULT, not ask (narrow_by_tier on `product`; a roster policy with no product candidate returns
no ask), so the scheme's certificates are sent, company-scoped, only that scheme's files, within
the set-reply cap of 50 rows in one message, and never the needs-a-filter refusal. The open
product_pick of the previous turn is not answered by this message.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.certificate import Certificate, CertificateRevision
from app.models.company import Company
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, seeded, stub_access  # noqa: F401

OTHER_COMPANY = "00000000-0000-0000-0000-000000000002"
SCHEME = "ZZSPAN"
LINKED = 55  # more than the set-reply cap of 50
NEIGHBOURS = ("ZZCWC609-RL", "ZZCWC601", "ZZCWC602")


def _seed(session_factory) -> dict[str, Any]:
    db = session_factory()
    db.add(Company(id=OTHER_COMPANY, name="Other", code=unique_code("OTH")[:20]))
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT cat", company_id=DEFAULT_COMPANY_ID,
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    cert_type = AttachmentType(
        id=str(uuid.uuid4()), type_name="ZZT Certification", description="Certification by Purchasing",
        allowed_extensions="pdf", is_certificate=True,
    )
    db.add_all([cat, uom, cert_type])
    db.flush()
    out: dict[str, Any] = {"ours": [], "theirs": [], "other_scheme": []}

    def product(code: str) -> Product:
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"ZZT {code}", category_id=cat.id, base_uom_id=uom.id,
            list_price=1, company_id=DEFAULT_COMPANY_ID,
        )
        db.add(p)
        db.flush()
        return p

    def linked_certificate(owner: Product, scheme: str, company_id: str | None, bucket: str) -> None:
        att = Attachment(
            id=str(uuid.uuid4()), original_filename=f"{owner.product_code}_{scheme}.pdf", stored_filename=uuid.uuid4().hex,
            file_path=f"https://cdn.test/{uuid.uuid4().hex}.pdf", attachment_type_id=cert_type.id, is_deleted=False,
            company_id=company_id or DEFAULT_COMPANY_ID,
        )
        db.add(att)
        db.flush()
        db.add(ProductAttachment(
            id=str(uuid.uuid4()), product_id=owner.id, attachment_id=att.id, company_id=company_id or DEFAULT_COMPANY_ID,
        ))
        cert = Certificate(
            id=str(uuid.uuid4()), attachment_type_id=cert_type.id, scheme=scheme,
            certificate_number=uuid.uuid4().hex[:10], status="active", company_id=company_id,
        )
        db.add(cert)
        db.flush()
        db.add(CertificateRevision(id=str(uuid.uuid4()), certificate_id=cert.id, revision_no=1, attachment_id=att.id, is_current=True))
        out[bucket].append(cert.id)

    for code in NEIGHBOURS:
        product(code)
    for n in range(LINKED):
        linked_certificate(product(f"ZZTS{n:03d}"), SCHEME, DEFAULT_COMPANY_ID, "ours")
    linked_certificate(product("ZZTFOREIGN1"), SCHEME, OTHER_COMPANY, "theirs")
    linked_certificate(product("ZZTPPS1"), "ZZPPS", DEFAULT_COMPANY_ID, "other_scheme")
    db.commit()
    return out


def _message(text: str, n: int) -> dict[str, Any]:
    return {
        "event_type": "message.received",
        "contact": {"id": CONTACT_ID},
        "message": {
            "messageId": f"ZZT-snp-{n}-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
            "traffic": "incoming", "message": {"type": "text", "text": text},
        },
    }


def _rows(n: int) -> list[dict[str, Any]]:
    return [
        {"title": f"ZZTS{i:03d}", "flags": {}, "fields": [
            {"label": "Product Code", "value": f"ZZTS{i:03d}"}, {"label": "File Name", "value": f"ZZTS{i:03d}_{SCHEME}.pdf"},
        ]}
        for i in range(n)
    ]


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

    def call_tool(self, name, args):
        calls.append((name, args))
        if name == "crm_master_product_attachments_list":
            # The real endpoint pages at `limit: int = Query(50, ...)`
            # (app/api/v1/master_data/product_attachments.py:153): default 50, ceiling
            # MAX_PAGE_LIMIT 1000 (app/schemas/common.py:31).
            rows = _rows(LINKED)[: int(args.get("limit") or 50)]
            return json.dumps({
                "result_type": "product_attachments", "intro": "I have attached the file(s) below.", "ok": True,
                "items": rows, "attachments": [], "action_links": [], "last_updated_at": None, "has_result": True,
            })
        return json.dumps({"ok": True, "items": []})

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", call_tool)
    stub_access()
    out = []
    for n, (text, _verdict) in enumerate(turns):
        calls.clear()
        out.append((engine_mod.run_turn(_envelope(message=_message(text, n)), session_factory=session_factory), list(calls)))
    return out


def _product(code: str) -> dict:
    return {"raw": code, "hint": "product", "canonical_code": None, "current_message": True, "confident": True}


def _scheme() -> dict:
    return {"raw": "Span", "hint": "attachment_type", "canonical_code": SCHEME, "listed_item": SCHEME,
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


def _after_the_did_you_mean(session_factory, stub_access, monkeypatch, *entities: dict, gate: bool = True):
    return _turns(
        session_factory, stub_access, monkeypatch,
        [("ZZCWC605-RL", _stock(_product("ZZCWC605-RL"))), ("Span certificate", _file_ask(*entities))],
        gate=gate,
    )


@pytest.mark.parametrize("with_kind", [False, True], ids=["scheme only", "scheme and certificate kind"])
def test_a_scheme_with_no_product_sends_the_schemes_own_company_certificates(with_kind, session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory)

    (r1, _c1), (r2, c2) = _after_the_did_you_mean(session_factory, stub_access, monkeypatch, _scheme(), *([_kind()] if with_kind else []))

    assert "Did you mean" in _text(r1), _text(r1)  # the open product_pick the scheme message does not answer
    fetches = [args for name, args in c2 if name == "crm_master_product_attachments_list"]
    assert fetches, (_text(r2), c2)
    sent = set(fetches[0].get("certificate_ids") or [])
    assert sent and sent <= set(ids["ours"]), fetches
    assert not sent & set(ids["theirs"]), "another company's certificate of the scheme must never be sent"
    assert not sent & set(ids["other_scheme"]), "only that scheme's files"
    assert not fetches[0].get("product_ids"), "the open product_pick is not answered by the scheme message"
    assert "search every product attachment" not in _text(r2), _text(r2)


def test_the_reply_carries_at_most_the_set_reply_cap_of_50_rows(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)

    (_r1, _c1), (r2, c2) = _after_the_did_you_mean(session_factory, stub_access, monkeypatch, _scheme(), _kind())

    text = _text(r2)
    assert "search every product attachment" not in text, text
    shown = set(re.findall(r"ZZTS\d{3}", text))
    assert 0 < len(shown) <= 50, (len(shown), text[:400])


def test_the_scheme_message_never_gets_the_needs_a_filter_refusal(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)

    (_r1, _c1), (r2, _c2) = _after_the_did_you_mean(session_factory, stub_access, monkeypatch, _scheme())

    assert "That would search every product attachment" not in _text(r2), _text(r2)


def test_gate_off_the_turn_is_unchanged(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)

    (_r1, _c1), (r2, _c2) = _after_the_did_you_mean(session_factory, stub_access, monkeypatch, _scheme(), gate=False)

    assert _text(r2)  # the pre-gate path still answers something; nothing new is asserted about it


def test_nothing_held_at_all_sends_the_schemes_certificates_and_never_the_refusal(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory)

    [(r, calls)] = _turns(session_factory, stub_access, monkeypatch, [("Span certificate", _file_ask(_scheme()))])

    fetches = [args for name, args in calls if name == "crm_master_product_attachments_list"]
    assert fetches, (_text(r), calls)
    sent = set(fetches[0].get("certificate_ids") or [])
    assert sent and sent <= set(ids["ours"]), fetches
    assert "That would search every product attachment" not in _text(r), _text(r)


# --- R2-1 BRAND-SCOPE-ATTACH: the scheme message of a brand-scoped contact ---------------------


def _brand_world(session_factory) -> dict[str, str]:
    """A MOCHA-scoped contact; a SPAN certificate file on an in-brand and an out-of-brand product."""
    from sqlalchemy import text

    from app.models.product import Brand

    db = session_factory()
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT cat", company_id=DEFAULT_COMPANY_ID,
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    cert_type = AttachmentType(
        id=str(uuid.uuid4()), type_name="ZZT Certification", description="Certification by Purchasing",
        allowed_extensions="pdf", is_certificate=True,
    )
    brands = {
        key: Brand(id=str(uuid.uuid4()), brand_code=unique_code(key)[:50], brand_name=f"ZZT {key}", company_id=DEFAULT_COMPANY_ID)
        for key in ("mocha", "sorento")
    }
    db.add_all([cat, uom, cert_type, *brands.values()])
    db.flush()
    out: dict[str, str] = {}
    for key, code in (("mocha", "ZZTMOCHA1"), ("sorento", "ZZTSOREN1")):
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"ZZT {code}", category_id=cat.id, base_uom_id=uom.id,
            list_price=1, company_id=DEFAULT_COMPANY_ID, brand_id=brands[key].id,
        )
        att = Attachment(
            id=str(uuid.uuid4()), original_filename=f"{code}_{SCHEME}.pdf", stored_filename=uuid.uuid4().hex,
            file_path=f"https://cdn.test/{code}.pdf", attachment_type_id=cert_type.id, is_deleted=False,
            company_id=DEFAULT_COMPANY_ID,
        )
        db.add_all([p, att])
        db.flush()
        db.add(ProductAttachment(id=str(uuid.uuid4()), product_id=p.id, attachment_id=att.id, company_id=DEFAULT_COMPANY_ID))
        cert = Certificate(
            id=str(uuid.uuid4()), attachment_type_id=cert_type.id, scheme=SCHEME, certificate_number=uuid.uuid4().hex[:10],
            status="active", company_id=DEFAULT_COMPANY_ID,
        )
        db.add(cert)
        db.flush()
        db.add(CertificateRevision(id=str(uuid.uuid4()), certificate_id=cert.id, revision_no=1, attachment_id=att.id, is_current=True))
        out[key] = code
    db.execute(
        text("UPDATE respond_contacts SET brand_ids = CAST(:b AS uuid[]) WHERE respond_io_id = :cid"),
        {"b": "{" + brands["mocha"].id + "}", "cid": str(CONTACT_ID)},
    )
    db.commit()
    return out


def test_a_brand_scoped_contact_never_gets_an_out_of_brand_products_certificate_file(session_factory, seeded, stub_access, monkeypatch):
    """The fetch is run for real through the route's service under the contact's brand scope,
    and every row's file is listed the way the MCP presenter does (even with product null)."""
    from app.models.base import set_brand_scope, set_company_scope
    from app.services.chatbot.engine import _contact_brand_scope
    from app.services.product_service import ProductAttachmentService

    codes = _brand_world(session_factory)
    leaked: list[str] = []

    def call_tool(self, name, args):
        if name != "crm_master_product_attachments_list":
            return json.dumps({"ok": True, "items": []})
        db = session_factory()
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        set_brand_scope(db, _contact_brand_scope(session_factory, str(seeded_contact_id)))
        payload = ProductAttachmentService(db).list_product_attachments(
            limit=50, certificate_ids=args.get("certificate_ids"), attachment_type_ids=args.get("attachment_type_ids"),
        )
        leaked.extend(row.attachment.original_filename for row in payload["data"])
        items = [
            {"title": row.attachment.original_filename, "flags": {}, "fields": [
                {"label": "File Name", "value": row.attachment.original_filename},
            ]}
            for row in payload["data"]
        ]
        return json.dumps({
            "result_type": "product_attachments", "intro": "I have attached the file(s) below.", "ok": True,
            "items": items, "attachments": [], "action_links": [], "last_updated_at": None, "has_result": bool(items),
        })

    from sqlalchemy import text

    seeded_contact_id = session_factory().execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": str(CONTACT_ID)}
    ).scalar()
    [(r, _calls)] = _turns_with(session_factory, stub_access, monkeypatch, call_tool, [("Span certificate", _file_ask(_scheme()))])

    text_out = _text(r)
    assert not any(codes["sorento"] in name for name in leaked), (leaked, text_out)
    assert codes["sorento"] not in text_out, text_out
    assert codes["mocha"] in text_out, text_out


def _turns_with(session_factory, stub_access, monkeypatch, call_tool, turns):
    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k", closed_lists=True,
        )

    queue = [verdict for _text, verdict in turns]
    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: queue.pop(0))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", call_tool)
    stub_access()
    return [
        (engine_mod.run_turn(_envelope(message=_message(text, n)), session_factory=session_factory), [])
        for n, (text, _v) in enumerate(turns)
    ]


# --- R2-3 SCHEME-NONE-IN-SCOPE (reviewer SF2, 18 Oct) -----------------------------------------


def _only_another_company_holds_the_scheme(session_factory) -> None:
    db = session_factory()
    db.add(Company(id=OTHER_COMPANY, name="Other", code=unique_code("OTH")[:20]))
    cert_type = AttachmentType(
        id=str(uuid.uuid4()), type_name="ZZT Certification", description="Certification by Purchasing",
        allowed_extensions="pdf", is_certificate=True,
    )
    db.add(cert_type)
    db.flush()
    db.add(Certificate(
        id=str(uuid.uuid4()), attachment_type_id=cert_type.id, scheme=SCHEME, certificate_number=uuid.uuid4().hex[:10],
        status="active", company_id=OTHER_COMPANY,
    ))
    db.commit()


def test_a_scheme_with_no_certificate_in_scope_and_nothing_held_says_so_plainly(session_factory, seeded, stub_access, monkeypatch):
    """Scheme lists are the same for every company, so the scheme can be listed while no
    certificate of it is in the contact's scope: said plainly, nothing sent."""
    _only_another_company_holds_the_scheme(session_factory)

    [(r, calls)] = _turns(session_factory, stub_access, monkeypatch, [("Span certificate", _file_ask(_scheme()))])

    assert _text(r) == f"No {SCHEME} certificate on record.", (_text(r), calls)
    assert not [c for c in calls if c[0] in ("crm_master_product_attachments_list", "crm_resource_attachments_list")], calls
