"""CHAT-SLIM-INDEX S3 salesperson visibility: the Salesperson block is built only for a contact the sales report lane
lets rank by sales agent: the `sales_orders.sales_report` reveal (route: api/v1/order_management/report_ask.py:353-366,
`contact_asker.may_ask_sales_ranking`, services/contact_asker.py:150; a non-granted contact is refused any agent axis).
Contract: `load_rows(db, *, include_salespeople: bool)`; the engine passes it from that grant.
The grant is delivered both ways the engine could read it: the stubbed access snapshot's `attributes` and
`contact_field_reveal_service.granted_keys`. Postgres only, fake data.
"""
from __future__ import annotations

import json
import uuid

import app.main  # noqa: F401  isort:skip
from app.services import contact_field_reveal_service
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access  # noqa: F401
from tests.chatbot.test_lookup_lists_engine import _fresh_caches, _quiet, _seed_prompt  # noqa: F401
from tests.chatbot.test_lookup_lists_s2 import scoped
from tests.chatbot.test_lookup_lists_s3 import HDR, seed_world3

GRANT = "sales_orders.sales_report"


def test_load_rows_includes_salespeople_only_when_asked(session_factory):
    seed_world3(session_factory)
    db = scoped(session_factory)
    assert "ZZ SEAN I" in {r.label for r in ll.load_rows(db, include_salespeople=True) if r.list_name == "salesperson"}
    assert not [r for r in ll.load_rows(db, include_salespeople=False) if r.list_name == "salesperson"]


def _turn(session_factory, stub_access, monkeypatch, *, granted: bool) -> list[str]:
    _seed_prompt(session_factory, monkeypatch, marker=True)
    seed_world3(session_factory)
    monkeypatch.setattr(ll, "EMBED", None, raising=False)
    seen: list[str] = []

    def parse(config, user_block):
        seen.append(str(user_block))
        return _quiet()

    keys = [GRANT] if granted else []
    monkeypatch.setattr(parser_mod, "parse", parse)
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    monkeypatch.setattr(contact_field_reveal_service, "granted_keys", lambda db, contact: list(keys))
    stub_access(attributes=keys or None)
    message = {"event_type": "message.received", "contact": {"id": CONTACT_ID}, "message": {
        "messageId": f"ZZT-sp-{uuid.uuid4().hex[:6]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
        "traffic": "incoming", "message": {"type": "text", "text": "zz sean i"}}}
    engine_mod.run_turn(_envelope(message=message), session_factory=session_factory)
    return seen[-1].splitlines()


def test_contact_with_the_sales_report_grant_gets_the_salesperson_block(session_factory, seeded, stub_access, monkeypatch):
    lines = _turn(session_factory, stub_access, monkeypatch, granted=True)
    assert HDR["salesperson"] in lines and "- ZZ SEAN I" in lines, lines


def test_contact_without_the_grant_gets_no_salesperson_block_and_no_agent_name(session_factory, seeded, stub_access, monkeypatch):
    lines = _turn(session_factory, stub_access, monkeypatch, granted=False)
    assert HDR["salesperson"] not in lines, lines
    assert "ZZ SEAN I" not in "\n".join(lines).replace("Current user message: zz sean i", ""), lines
