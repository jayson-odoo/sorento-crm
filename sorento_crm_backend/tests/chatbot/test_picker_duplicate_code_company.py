"""DUP-CODE-LABEL: a code two companies share is named with its company on every domain.

Live: a picker listed 'MKT8811SS' twice; two active products carry that code, one in Sorento and
one in Mocha. The picker labels by bare code (lanes/business/gate.py `flat_labels`); the
'(Company)' suffix exists only on product_attachment (F16), because `incoming`'s annotator
(lanes/business/pickers.py `annotate_incoming`) re-joins the rendered lines to the probe BY CODE
TEXT, so a suffixed line used to read a false "- no incoming". Rule: the suffix shows on every
domain whenever two rows share a code, and the annotator keys on the product, not the line text.

Fresh world (ZZ data): ZZDUP881SS active and chat-searchable in BOTH companies the contact
belongs to, plus ZZDUP881BL (Sorento only) so "zzdup881" has a 3-option picker. Real engine,
real resolver (company scoped), the MCP tool stubbed: the incoming probe answers only for the
Sorento ZZDUP881SS, in the presenter's item shape (title, Company / Product Code fields, the
product as `entity_id`).
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.chatbot import turn_runtime
from app.services.chatbot.head import parser as parser_mod
from tests._pg_fixture import unique_code
from tests.chatbot._r9_engine_console import answer, product
from tests.chatbot._turn_helpers import verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, stub_access  # noqa: F401 - a pytest fixture
from tests.chatbot.test_rearch_s3_attribute_first import SORENTO, _db, _link_contact_company
from tests.chatbot.test_rearch_s3_roster_from_resolver import _seed_contact

MOCHA = "00000000-0000-0000-0000-0000000d0b81"
SHARED = "ZZDUP881SS"
SOLO = "ZZDUP881BL"
INCOMING = "crm_incoming_stock_list"
_LINE = re.compile(r"^(\d+)\.\s+(.*)$")


class Console:
    def __init__(self, session_factory, monkeypatch, stub_access) -> None:
        from app.models.company import Company
        from app.models.product import Product, ProductCategory, UnitOfMeasure

        self.session_factory = session_factory
        self.tool_calls: list[tuple[str, dict[str, Any]]] = []
        self.state: dict[str, Any] | None = None
        self._next: dict[str, Any] | None = None
        both = frozenset({SORENTO, MOCHA})
        db = _db(session_factory, scope=both)
        db.add(Company(id=MOCHA, name="ZZT Mocha Co", code=unique_code("ZZMOC")[:20]))
        db.commit()
        _seed_contact(session_factory, phone="+60900008811")
        _link_contact_company(session_factory, company_id=SORENTO)
        _link_contact_company(session_factory, company_id=MOCHA)
        db = _db(session_factory, scope=both)
        self.company_name = {cid: name for cid, name in db.query(Company.id, Company.name).filter(Company.id.in_([SORENTO, MOCHA]))}
        self.ids: dict[tuple[str, str], str] = {}
        for company_id, codes in ((SORENTO, (SHARED, SOLO)), (MOCHA, (SHARED,))):
            cat = ProductCategory(
                id=str(uuid.uuid4()), category_code=unique_code("ZZDC")[:50], category_name="ZZT dup", company_id=company_id,
            )
            uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("ZZDU")[:20], uom_name="Each", company_id=company_id)
            db.add_all([cat, uom])
            db.flush()
            for code in codes:
                pid = str(uuid.uuid4())
                db.add(Product(
                    id=pid, product_code=code, product_name=f"ZZT {code}", category_id=cat.id, base_uom_id=uom.id,
                    list_price=1, is_active=True, company_id=company_id,
                ))
                self.ids[(company_id, code)] = pid
        db.commit()
        self.code_of = {pid: code for (_c, code), pid in self.ids.items()}
        self.company_of = {pid: c for (c, _code), pid in self.ids.items()}
        stub_access()
        monkeypatch.setattr(turn_runtime, "_stock_availability_only", lambda *a, **k: False)

        def fake_resolve_config(db, *, current_date, override_version_id=None):
            return parser_mod.ParserConfig(system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k")

        def fake_parse(config, user_block):
            return self._next

        incoming_pid = self.ids[(SORENTO, SHARED)]

        def fake_call_tool(client, name: str, args: dict[str, Any]) -> str:
            self.tool_calls.append((name, args))
            if name == INCOMING:
                asked = set(args.get("product_ids") or []) or {incoming_pid}
                items = [
                    {
                        "title": SHARED, "entity_id": incoming_pid,
                        "flags": {"discontinued": False, "expired": False, "expiring_soon": False},
                        "fields": [
                            {"key": "company_name", "label": "Company", "value": self.company_name[SORENTO]},
                            {"key": "product_code", "label": "Product Code", "value": SHARED},
                            {"key": "remaining_incoming_quantity", "label": "Incoming Quantity", "value": 20},
                        ],
                    }
                ] if incoming_pid in asked else []
                return json.dumps({"ok": True, "items": items, "has_result": bool(items)})
            return json.dumps({"ok": True, "items": [], "has_result": False})

        from app.services.ai_assistant_service import MCPRuntimeClient

        monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
        monkeypatch.setattr(parser_mod, "parse", fake_parse)
        monkeypatch.setattr(MCPRuntimeClient, "call_tool", fake_call_tool)

    def say(self, message: str, v: dict[str, Any]) -> str:
        self._next = v
        out = engine_mod.run_turn(
            _envelope(
                is_test=True,
                previous_conversation_state=self.state,
                message={
                    "event_type": "message.received",
                    "contact": {"id": CONTACT_ID},
                    "message": {
                        "messageId": f"ZZT-dup-{uuid.uuid4().hex[:10]}", "contactId": CONTACT_ID, "channelId": "whatsapp",
                        "traffic": "incoming", "message": {"type": "text", "text": message},
                    },
                },
            ),
            session_factory=self.session_factory,
        )
        assert out.error is None, out.error
        self.state = out.session_patch
        return (out.reply or {}).get("text") or ""

    def suffixed(self, company_id: str) -> str:
        return f"{SHARED} ({self.company_name[company_id]})"


def _lines(text: str) -> dict[int, str]:
    """{position: the numbered line's text}."""
    return {int(m.group(1)): m.group(2) for m in (_LINE.match(line) for line in text.split("\n")) if m}


def _ask(domain: str) -> dict[str, Any]:
    intent = {"inventory": "check_stock", "incoming": "check_incoming", "product_attachment": "check_product_attachment"}[domain]
    entities = [product("zzdup881")]
    if domain == "product_attachment":
        # A listed document type, so the ask is a file ask about the products (not "which kind of file").
        entities.append({"raw": "photo", "hint": "attachment_type", "canonical_code": "photo", "confident": True, "current_message": True})
    return verdict(domain_hint=domain, intent_hint=intent, domain_in_message=True, entities=entities)


@pytest.fixture
def console(session_factory, monkeypatch, stub_access):
    return Console(session_factory, monkeypatch, stub_access)


# --- R1: the suffix on every domain -----------------------------------------------------------


def test_r1_a_code_two_companies_share_is_named_with_its_company(console):
    """On a non-attachment domain. Measured on HEAD: of the domains the picker serves, incoming
    is the one a product family reaches; a stock ask over the family fans out to every member
    (its miss line already names each row's company), so it has no picker to label."""
    text = console.say("zzdup881 incoming", _ask("incoming"))

    lines = list(_lines(text).values())
    assert len(lines) == 3, text
    named = [line.split(" - ")[0] for line in lines]
    assert console.suffixed(SORENTO) in named and console.suffixed(MOCHA) in named, text
    assert SHARED not in named, text  # never the bare code


# --- R2: each suffixed incoming line carries its own product's state -------------------------


def test_r2_each_shared_code_line_carries_its_own_products_incoming(console):
    """Only the Sorento ZZDUP881SS has incoming. Each numbered line is tied to its product by the
    stored roster (position -> uuid), so the check holds whatever the line's label reads: today
    the annotator joins the probe by code text and both ZZDUP881SS lines read "has incoming"."""
    text = console.say("zzdup881 incoming", _ask("incoming"))

    lines = _lines(text)
    options = {o["position"]: o["uuid"] for o in ((console.state or {}).get("open_question") or {}).get("options") or []}
    assert len(lines) == 3 and set(options) == set(lines), (text, options)
    has = console.ids[(SORENTO, SHARED)]
    for position, line in lines.items():
        expected = " - has incoming" if options[position] == has else " - no incoming"
        assert line.endswith(expected), (position, line, text)


def test_r3_a_re_asked_roster_still_names_the_shared_code_with_its_company(console):
    """A reply that answers nothing on the roster (a position past its end) re-prints the stored
    roster (`turn/compose.compose_question`, from the stored options' labels). Measured on
    6b8986ed7a: the re-asked lines read the bare code twice ("2. ZZDUP881SS", "3. ZZDUP881SS")."""
    console.say("zzdup881 incoming", _ask("incoming"))

    text = console.say("7", verdict(
        message_type="business_query", domain_hint="incoming", domain_in_message=False,
        reference_positions=[7], open_question_answer=answer("pick", picked=[7]),
    ))

    named = [line.split(" - ")[0] for line in _lines(text).values()]
    assert len(named) == 3, text
    assert console.suffixed(SORENTO) in named and console.suffixed(MOCHA) in named, text


# --- guards (pass on HEAD) --------------------------------------------------------------------


@pytest.mark.parametrize("domain", ["incoming", "product_attachment"])
def test_guard_a_code_no_other_company_shares_has_no_suffix(console, domain):
    text = console.say(f"zzdup881 {domain}", _ask(domain))

    solo = [line for line in _lines(text).values() if line.startswith(SOLO)]
    assert solo and all(line.split(" - ")[0] == SOLO for line in solo), text


def test_guard_product_attachment_keeps_its_company_suffix(console):
    text = console.say("zzdup881 files", _ask("product_attachment"))

    named = list(_lines(text).values())
    assert console.suffixed(SORENTO) in named and console.suffixed(MOCHA) in named, text


@pytest.mark.parametrize("position", [2, 3])
def test_guard_a_bare_number_picks_the_product_on_that_line(console, position):
    text = console.say("zzdup881 incoming", _ask("incoming"))
    lines = _lines(text)
    assert len(lines) == 3, text
    options = {o.get("position"): o for o in ((console.state or {}).get("open_question") or {}).get("options") or []}

    since = len(console.tool_calls)
    console.say(str(position), verdict(
        message_type="business_query", domain_hint="incoming", domain_in_message=False,
        reference_positions=[position], open_question_answer=answer("pick", picked=[position]),
    ))

    fetched = [pid for name, args in console.tool_calls[since:] if name == INCOMING for pid in args.get("product_ids") or []]
    assert len(fetched) == 1, console.tool_calls[since:]
    picked = fetched[0]
    label = lines[position].split(" - ")[0]
    assert label.split(" (")[0] == console.code_of[picked], (lines, console.code_of[picked])
    if "(" in label:
        assert label == console.suffixed(console.company_of[picked]), (label, picked)
    option = options.get(position) or {}
    option_uuid = option.get("uuid") or (option.get("payload") or {}).get("uuid")
    if option_uuid:
        assert option_uuid == picked, (option, picked)
