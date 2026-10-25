"""CHAT-SLIM-INDEX S3 engine: "zzsrt a3 flyer" on a marked version gets a Brand block and a Promotion kind block,
no Known brands / Promotion kinds per-turn line, and no Category block from the brand word."""
from __future__ import annotations

import json
import uuid

import app.main  # noqa: F401  isort:skip
from app.models.product import ProductCategory
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access  # noqa: F401
from tests.chatbot.test_lookup_lists_engine import _fresh_caches, _quiet, _seed_prompt  # noqa: F401
from tests.chatbot.test_lookup_lists_s2 import scoped
from tests.chatbot.test_lookup_lists_s3 import BRAND_CODE, HDR, brand_label, seed_world3


def test_marked_turn_offers_brand_and_promotion_kind_blocks(session_factory, seeded, stub_access, monkeypatch):
    _seed_prompt(session_factory, monkeypatch, marker=True)
    seed_world3(session_factory)
    db = session_factory()
    db.add(ProductCategory(id=str(uuid.uuid4()), category_code=BRAND_CODE, category_name=BRAND_CODE, class_label=BRAND_CODE,
                           search_synonyms=[], is_searchable=True, company_id=DEFAULT_COMPANY_ID))
    db.commit()
    want = brand_label(scoped(session_factory))
    monkeypatch.setattr(ll, "EMBED", None, raising=False)
    seen: list[str] = []

    def parse(config, user_block):
        seen.append(str(user_block))
        return _quiet()

    monkeypatch.setattr(parser_mod, "parse", parse)
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access()
    message = {"event_type": "message.received", "contact": {"id": CONTACT_ID}, "message": {
        "messageId": f"ZZT-s3-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
        "traffic": "incoming", "message": {"type": "text", "text": "zzsrt a3 flyer"}}}
    engine_mod.run_turn(_envelope(message=message), session_factory=session_factory)
    lines = seen[-1].splitlines()
    assert HDR["brand"] in lines and f"- {want}" in lines, lines
    assert HDR["promotion_kind"] in lines and "- A3 Flyer (a3_flyer)" in lines, lines
    assert not any(ln.startswith(("Known brands:", "Promotion kinds:")) for ln in lines), lines
    cat_at = [i for i, ln in enumerate(lines) if ln.startswith("Category candidates")]
    assert not cat_at or BRAND_CODE not in "\n".join(lines[cat_at[0] :]).split(HDR["brand"])[0], lines
