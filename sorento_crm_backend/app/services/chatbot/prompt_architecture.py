"""CHAT-INDEX-VIZ: what the parser prompt sends on every message, section by section.

`describe(db, version)` splits a stored version's RAW template at its `== TITLE ==` headings,
renders each section the way a live turn renders the whole prompt (registry variables filled,
the closed lists blanked to their fixed lines in index mode) and counts tokens as
`round(len(text) / 4)`. Read-only; the numbers are an estimate, not the provider's count.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptVersion
from app.services import ai_prompt_registry as registry
from app.services import chatbot_prompt_vars as pv
from app.services.chatbot.head import closed_lists_index
from app.services.chatbot.head.closed_lists_prompt import gate_on

PROMPT_KEY = "chatbot_semantic_parser"
CLOSED_LIST_KEYS = tuple(closed_lists_index.SYSTEM_BLANKS)
_HEADING = re.compile(r"^== (.+) ==$", re.MULTILINE)
#: Plain names for the three lists, the same words the per-turn screen uses.
LIST_NAMES = {"specs": "Specifications", "attachment_types": "File types", "certification_types": "Certificates"}
WAREHOUSES = {"name": "Warehouses", "source": "Warehouses", "href": "/inventory-management/warehouses"}


def _tokens(text: str) -> int:
    return round(len(text) / 4)


def _sections(raw: str) -> list[tuple[str, str]]:
    """(title, raw text) pairs; text before the first heading is "Opening" (dropped when blank)."""
    marks = list(_HEADING.finditer(raw))
    out: list[tuple[str, str]] = []
    opening = raw[: marks[0].start()] if marks else raw
    if opening.strip():
        out.append(("Opening", opening))
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(raw)
        out.append((mark.group(1).strip(), raw[mark.end() : end]))
    return out


def _kind(text: str) -> str:
    found = registry.extract_tokens(text)
    if found & set(CLOSED_LIST_KEYS):
        return "closed_lists"
    return "filled_from_data" if found else "text"


def describe(db: Session, version: AIPromptVersion) -> dict[str, Any]:
    from app.models.inventory import Warehouse

    raw = version.template or ""
    mode = closed_lists_index.read_mode(db)
    uses = gate_on(raw)
    blanks = dict(closed_lists_index.SYSTEM_BLANKS) if uses and mode == closed_lists_index.MODE_INDEX else {}
    today = date.today().strftime("%A, %d %B %Y")

    sections = []
    for title, text in _sections(raw):
        prompt = registry.RenderedPrompt(text=text, name=PROMPT_KEY, version=version.version)
        rendered, _ = registry.render_resolved(db, PROMPT_KEY, prompt, current_date=today, **blanks)
        sections.append({"title": title, "tokens": _tokens(rendered), "kind": _kind(text)})

    lists: list[dict[str, Any]] = []
    for key in CLOSED_LIST_KEYS:
        variable = pv.VARIABLES[key]
        full = _tokens(pv.render_value(db, key))
        lists.append({
            "key": key,
            "name": LIST_NAMES[key],
            "source": variable.source,
            "href": variable.href,
            "entries": variable.count(db),
            "sent_each_message_tokens": _tokens(closed_lists_index.SYSTEM_BLANKS[key]) if blanks else full,
            "full_list_tokens": full,
        })
    lists.append({
        "key": "warehouses",
        **WAREHOUSES,
        "entries": db.query(Warehouse).count(),
        "sent_each_message_tokens": 0,
        "full_list_tokens": 0,
        "checked_only": True,
    })
    return {
        "version": int(version.version),
        "mode": mode,
        "uses_closed_lists": uses,
        "total_tokens": sum(s["tokens"] for s in sections),
        "sections": sections,
        "lists": lists,
    }
