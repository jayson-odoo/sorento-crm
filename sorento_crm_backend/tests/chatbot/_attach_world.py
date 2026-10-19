"""Shared seed and turn runner for the round 4 attachment red tests (not a test module).

Real shapes, as the round 1 lessons demand: stub parses carry the real top-level fields of the
traced turn (g1755c lane.jsonl, understood stage); every certificate file is the full link chain
(certificate -> current revision -> attachment -> product_attachments -> product, plus a
certificate_products row); a class resolves through an exact class_label; the MCP stub answers
attachment fetches with a files envelope (`has_result` True) for the ids it is asked about.
Synthetic ZZ data only.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from app.models.certificate import Certificate, CertificateProduct, CertificateRevision
from app.models.product import Brand, Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests.chatbot.test_engine import CONTACT_ID, _envelope

ATTACH_TOOL = "crm_master_product_attachments_list"


class World:
    """Rows added through `add_*`; `files` is what the MCP stub can answer with."""

    def __init__(self, session_factory) -> None:
        self.db = session_factory()
        self.uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
        self.db.add(self.uom)
        self.db.flush()
        self.types: dict[str, AttachmentType] = {}
        self.cats: dict[str, ProductCategory] = {}
        self.brands: dict[str, Brand] = {}
        self.products: dict[str, Product] = {}
        self.certs: dict[str, str] = {}
        self.files: list[dict[str, str]] = []

    def type(self, name: str, *, cert: bool = False, code: str | None = None) -> AttachmentType:
        if name not in self.types:
            row = AttachmentType(
                id=str(uuid.uuid4()), type_name=name, code=code, description=name if cert else None,
                allowed_extensions="pdf", is_certificate=cert,
            )
            self.db.add(row)
            self.db.flush()
            self.types[name] = row
        return self.types[name]

    def brand(self, name: str) -> Brand:
        if name not in self.brands:
            row = Brand(id=str(uuid.uuid4()), brand_code=name, brand_name=name, company_id=DEFAULT_COMPANY_ID)
            self.db.add(row)
            self.db.flush()
            self.brands[name] = row
        return self.brands[name]

    def category(self, label: str) -> ProductCategory:
        if label not in self.cats:
            row = ProductCategory(
                id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name=label, class_label=label,
                search_synonyms=[label], company_id=DEFAULT_COMPANY_ID,
            )
            self.db.add(row)
            self.db.flush()
            self.cats[label] = row
        return self.cats[label]

    def product(self, code: str, *, brand: str | None = None, category: str = "ZZ Plain") -> Product:
        if code not in self.products:
            row = Product(
                id=str(uuid.uuid4()), product_code=code, product_name=f"ZZT {code}", category_id=self.category(category).id,
                base_uom_id=self.uom.id, list_price=1, is_active=True, company_id=DEFAULT_COMPANY_ID,
                brand_id=self.brand(brand).id if brand else None,
            )
            self.db.add(row)
            self.db.flush()
            self.products[code] = row
        return self.products[code]

    def file(self, product_code: str, *, type_name: str, cert: bool = False, scheme: str | None = None,
             number: str | None = None, brand: str | None = None, category: str = "ZZ Plain", key: str | None = None) -> dict[str, str]:
        """One file on a product; a certificate file also gets its certificate, current revision and
        certificate_products row (the real link chain)."""
        p = self.product(product_code, brand=brand, category=category)
        kind = self.type(type_name, cert=cert)
        name = f"{product_code}_{scheme or type_name}.pdf".replace(" ", "_")
        att = Attachment(
            id=str(uuid.uuid4()), original_filename=name, stored_filename=uuid.uuid4().hex,
            file_path=f"https://cdn.test/{name}", attachment_type_id=kind.id, is_deleted=False, company_id=DEFAULT_COMPANY_ID,
        )
        self.db.add(att)
        self.db.flush()
        self.db.add(ProductAttachment(id=str(uuid.uuid4()), product_id=p.id, attachment_id=att.id, company_id=DEFAULT_COMPANY_ID))
        row = {"product_id": p.id, "code": product_code, "filename": name, "type_id": kind.id, "cert_id": ""}
        if cert:
            c = Certificate(
                id=str(uuid.uuid4()), attachment_type_id=kind.id, scheme=scheme, certificate_number=number or uuid.uuid4().hex[:10],
                status="active", company_id=None,
            )
            self.db.add(c)
            self.db.flush()
            self.db.add(CertificateRevision(id=str(uuid.uuid4()), certificate_id=c.id, revision_no=1, attachment_id=att.id, is_current=True))
            self.db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=c.id, product_id=p.id, source="manual"))
            self.db.flush()
            row["cert_id"] = c.id
            self.certs[key or f"{scheme}:{product_code}"] = c.id
        self.files.append(row)
        return row

    def commit(self) -> "World":
        self.db.commit()
        return self


def real_parse(entities: list[dict], **over: Any) -> dict[str, Any]:
    """A file-ask parse with the real top-level fields (cp0 understood stage)."""
    from tests.chatbot.test_engine import _parser_output

    base = _parser_output(
        intent_hint="check_product_attachment", domain_hint="product_attachment", user_goal="file", entities=entities,
    )
    base.update({
        "domain_in_message": True, "entity_op": "replace_combine", "scope_intent": None, "message_type": "business_query",
        "continuation": False, "topic_reset": False, "match_mode": "and", "anaphora": {"backward_reference": False},
        "open_question_answer": {"mode": None, "items": [], "picked": [], "qty_for_all": None},
    })
    base.update(over)
    return base


def entity(raw: str, hint: str, *, canonical: str | None = None, listed: str | None = None, confident: bool = True, **extra: Any) -> dict:
    return {"raw": raw, "hint": hint, "canonical_code": canonical, "listed_item": listed, "confident": confident,
            "hint_confident": confident, "current_message": True, **extra}


def _message(text: str, n: int) -> dict[str, Any]:
    return {
        "event_type": "message.received",
        "contact": {"id": CONTACT_ID},
        "message": {"messageId": f"ZZT-r4-{n}-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
                    "traffic": "incoming", "message": {"type": "text", "text": text}},
    }


def run_turns(session_factory, stub_access, monkeypatch, turns, world: World, *, gate: bool = True):
    """[(result, calls)] per turn; the attachments fetch answers with the files matching its ids."""
    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k", closed_lists=gate,
        )

    queue = [verdict for _t, verdict in turns]
    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: queue.pop(0))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    calls: list[tuple[str, dict]] = []

    def call_tool(self, name, args):
        calls.append((name, args))
        if name != ATTACH_TOOL:
            return json.dumps({"ok": True, "items": []})
        pids, cids, tids = (set(args.get(k) or []) for k in ("product_ids", "certificate_ids", "attachment_type_ids"))
        rows = [] if not (pids or cids or tids) else [
            f for f in world.files
            if (not pids or f["product_id"] in pids) and (not cids or f["cert_id"] in cids) and (not tids or f["type_id"] in tids)
        ]
        return json.dumps({
            "result_type": "product_attachments", "intro": "I have attached the file(s) below.", "ok": True,
            "items": [{"title": f["code"], "flags": {"discontinued": False, "expired": False, "expiring_soon": False}, "fields": [
                {"label": "Product Code", "value": f["code"]}, {"label": "File Name", "value": f["filename"]},
            ]} for f in rows],
            "attachments": [{"url": f"https://example.invalid/{f['filename']}", "filename": f["filename"],
                             "mimeType": "application/pdf"} for f in rows],
            "action_links": [], "last_updated_at": None, "has_result": bool(rows),
        })

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", call_tool)
    stub_access()
    out = []
    for n, (text, _v) in enumerate(turns):
        calls.clear()
        out.append((engine_mod.run_turn(_envelope(message=_message(text, n)), session_factory=session_factory), list(calls)))
    return out


def text_of(result) -> str:
    return (result.reply or {}).get("text") or ""


def fetches(calls) -> list[dict]:
    return [a for n, a in calls if n == ATTACH_TOOL]
