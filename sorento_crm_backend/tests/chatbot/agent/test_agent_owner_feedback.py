"""AGENTIC-UNIFY hand-test feedback (owner message: "Any sposnroship doem oending approval?").

Red first. A user who cannot see purchase requests and sponsorship forms is told that area is outside their
access, in a sentence made of the constant `TOOL_LABELS` text (no outside text in the system role); the
agent's markdown links read as WhatsApp text; a guide read shows its title, never a bare id; and a blank
guide query is refused before the MCP server is reached.
"""
from __future__ import annotations

import copy
import re
import uuid

import pytest

from app.services.chatbot.agent.formatting import to_whatsapp
from app.services.chatbot.agent.loop import run_agent_turn, tool_detail
from app.services.chatbot.agent.tools import TOOL_LABELS, ToolResult
from app.services.llm_provider import ChatResult
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_agent_contact

OWNER_MESSAGE = "Any sposnroship doem oending approval?"
LIST_PRS = "crm_purchase_requests_list"
LABEL = TOOL_LABELS[LIST_PRS]
CATALOG = {
    "user_guides_read": {
        "description": "Read the CRM user guides",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
}


class Provider:
    def __init__(self):
        self.seen: list[dict] = []

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        self.seen.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)})
        return ChatResult(
            content="", prompt_tokens=10, completion_tokens=2, total_tokens=12,
            tool_calls=[{"id": "a1", "name": "answer", "arguments": {"text": "Noted.", "figures": [], "not_found": [], "not_checked": []}}],
        )


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _first_call(db, slugs):
    contact = seed_agent_contact(db, slugs=slugs)
    provider = Provider()
    run_agent_turn(
        db, contact_respond_id=contact["respond_id"], text=OWNER_MESSAGE, provider=provider,
        mcp_call=lambda name, args: (_ for _ in ()).throw(AssertionError("no MCP call in this test")), catalog={},
    )
    first = provider.seen[0]
    names = {t["function"]["name"] for t in first["tools"]}
    return first["messages"][0]["content"], names


# ------------------------------------------------------------------ 1. the system text names the missing area


def test_a_user_without_the_purchase_request_slugs_is_told_the_area_is_outside_their_access(db):
    system, names = _first_call(db, ("inventory.stock.view",))

    assert LIST_PRS not in names
    lines = [line for line in system.splitlines() if LABEL in line]
    assert lines, f"the system text must name {LABEL!r} as unavailable"
    assert any("outside" in line and "access" in line for line in lines)


def test_a_user_with_the_sponsorship_view_slug_has_the_tool_and_no_such_line(db):
    system, names = _first_call(db, ("procurement.sponsorship_forms.view",))

    assert LIST_PRS in names
    assert LABEL not in system


# ------------------------------------------------------------------ 2. markdown links as WhatsApp text


def test_a_bold_link_keeps_its_label_and_drops_the_path():
    text = "please open [**Procurement → Sponsorship Forms**](/procurement-management/sponsorship-forms) directly"
    assert to_whatsapp(text) == "please open *Procurement → Sponsorship Forms* directly"


def test_the_guides_bold_around_a_link_form_reads_the_same_way():
    text = "please open **[Procurement → Sponsorship Forms](/procurement-management/sponsorship-forms)** directly"
    assert to_whatsapp(text) == "please open *Procurement → Sponsorship Forms* directly"


def test_a_link_to_a_full_address_keeps_the_address_after_the_label():
    assert to_whatsapp("see [the page](https://x.test/a) now") == "see the page (https://x.test/a) now"


def test_text_without_links_is_unchanged_by_link_handling():
    assert to_whatsapp("Stock is [12] units (see list)") == "Stock is [12] units (see list)"


# ------------------------------------------------------------------ 3. a guide read shows its title, never a bare id


def test_a_guide_read_detail_shows_the_title_and_no_id():
    ident = str(uuid.uuid4())

    detail = tool_detail("user_guides_read", {"query": ident}, ToolResult("ok", data={}), {ident: "Approve a form"})

    assert "Approve a form" in detail
    assert ident not in detail
    assert "(query: )" not in detail


def test_a_guide_read_with_an_unknown_id_never_shows_an_empty_parenthesis():
    ident = str(uuid.uuid4())
    detail = tool_detail("user_guides_read", {"query": ident}, ToolResult("ok", data={}), {})
    assert ident not in detail and "(query: )" not in detail


# ------------------------------------------------------------------ 4. a blank guide query never reaches the server


@pytest.mark.parametrize("args", [{"query": ""}, {"query": "   "}, {}], ids=["empty", "blank", "missing"])
def test_a_blank_guide_query_is_invalid_and_makes_no_mcp_call(monkeypatch, args):
    from app.services.chatbot.agent import tools
    from app.services.chatbot.agent.access import AgentContext

    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True)
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    calls: list = []
    ctx = AgentContext(
        contact_pk="pk-1", contact_respond_id="ZZT-RESPOND-1", space_id="364817", user_id="user-1",
        user_name="ZZT User", grants=frozenset(),
    )

    out = tools.dispatch(
        None, ctx, "user_guides_read", args, call=lambda n, a: calls.append((n, a)), catalog=CATALOG, timeout=5.0,
    )

    assert out.status == "invalid"
    assert calls == []
