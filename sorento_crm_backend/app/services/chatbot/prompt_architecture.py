"""CHAT-INDEX-VIZ: what the parser prompt sends on every message, section by section.

`describe(db, version)` sizes what a stored version's RAW template gives the bot on every
message, in four groups (Rules, Examples, Product lists, Lists from other settings), rendering
the way a live turn does (registry variables filled, the closed lists blanked to their fixed
lines in index mode). A size is `round(chars / 4)`. Read-only; an estimate, not a provider count.
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
_EXAMPLE = re.compile(r'"[^"\n]+"\s*->')
_TOKEN = registry._TOKEN_RE
WAREHOUSES = {"name": "Warehouses", "source": "Warehouses", "href": "/inventory-management/warehouses"}
#: Plain names for the three lists, the same words the per-turn screen uses.
LIST_NAMES = {"specs": "Specifications", "attachment_types": "File types", "certification_types": "Certificates"}
HOW = {
    "specs": (
        "A word of the message matches a value, its name or a synonym from Product Specifications, "
        "or a code ending like -FRG; close spellings count too."
    ),
    "attachment_types": "A word matches a file type's code, name, its words or an alias keyword; close spellings count too.",
    "certification_types": (
        "A word matches a certificate kind or a certificate scheme by its name or words; close spellings count too."
    ),
    "warehouses": (
        "Not sent to the bot; a warehouse the bot reads is checked against the warehouse list "
        "(the exact code, or the part after the last dash)."
    ),
}
GROUP_NAMES = ("Rules", "Examples", "Product lists", "Lists from other settings")


def _size(chars: int) -> int:
    return round(chars / 4)


def _groups(db: Session, raw: str, blanks: dict[str, str], today: str) -> list[dict[str, Any]]:
    """The four groups, in order, with size and share; a group of size 0 is left out."""
    lines = raw.splitlines(keepends=True)
    examples = [line for line in lines if _EXAMPLE.search(line)]
    own = [line for line in lines if not _EXAMPLE.search(line)]

    def bare(chunk: list[str]) -> int:
        return len(_TOKEN.sub("", "".join(chunk)))

    def count(name: str) -> int:
        return sum(1 for m in _TOKEN.finditer("".join(own)) if m.group(1) == name)

    chars = dict.fromkeys(GROUP_NAMES, 0)
    chars["Rules"] = bare(own) + len(today) * count("current_date")
    chars["Examples"] = bare(examples)
    used = {m.group(1) for m in _TOKEN.finditer(raw)}
    for key in CLOSED_LIST_KEYS:
        if key in used:
            text = blanks.get(key) or pv.render_value(db, key)
            chars["Product lists"] += len(text) * sum(1 for m in _TOKEN.finditer(raw) if m.group(1) == key)
    others = (used & set(pv.VARIABLE_NAMES)) - set(CLOSED_LIST_KEYS) - {"current_date"}
    if others:
        values = pv.render_values_safe(db, others)
        for name, text in values.items():
            chars["Lists from other settings"] += len(text) * sum(1 for m in _TOKEN.finditer(raw) if m.group(1) == name)
    sizes = {name: _size(n) for name, n in chars.items()}
    total = sum(sizes.values())
    return [{"name": n, "size": sizes[n], "share": sizes[n] / total} for n in GROUP_NAMES if sizes[n] > 0]


def describe(db: Session, version: AIPromptVersion) -> dict[str, Any]:
    from app.models.inventory import Warehouse

    raw = version.template or ""
    mode = closed_lists_index.read_mode(db)
    uses = gate_on(raw)
    blanks = dict(closed_lists_index.SYSTEM_BLANKS) if uses and mode == closed_lists_index.MODE_INDEX else {}
    today = date.today().strftime("%A, %d %B %Y")
    groups = _groups(db, raw, blanks, today)

    lists: list[dict[str, Any]] = []
    for key in CLOSED_LIST_KEYS:
        variable = pv.VARIABLES[key]
        full = _size(len(pv.render_value(db, key)))
        lists.append({
            "key": key,
            "name": LIST_NAMES[key],
            "source": variable.source,
            "href": variable.href,
            "how": HOW[key],
            "entries": variable.count(db),
            "sent_each_message_size": _size(len(closed_lists_index.SYSTEM_BLANKS[key])) if blanks else full,
            "full_list_size": full,
        })
    lists.append({
        "key": "warehouses",
        **WAREHOUSES,
        "how": HOW["warehouses"],
        "entries": db.query(Warehouse).count(),
        "sent_each_message_size": 0,
        "full_list_size": 0,
        "checked_only": True,
    })
    return {
        "version": int(version.version),
        "mode": mode,
        "uses_closed_lists": uses,
        "total_size": sum(g["size"] for g in groups),
        "groups": groups,
        "lists": lists,
    }
