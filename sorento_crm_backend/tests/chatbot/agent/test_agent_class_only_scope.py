"""TAG-BRAND-CLASS review B1: the agent's list lookup reads brand tokens only.

A contact limited by item class alone (All brands + "No class, DIY") carries `class:` tokens and no
brand id. The lookup used to treat every token as a brand id (the retired `<brand>/<class>` shape),
so such a contact matched no brand name at all.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.chatbot.agent import tools
from app.services.chatbot.head import list_resolver, lookup_lists
from app.services.chatbot.head.lookup_lists import LookupRow


def _captured(monkeypatch, scope):
    rows = [
        LookupRow("brand", "b-sorento", "SORENTO", ["SORENTO"], homes=["label"]),
        LookupRow("brand", "b-mocha", "MOCHA", ["MOCHA"], homes=["label"]),
    ]
    monkeypatch.setattr(lookup_lists, "load_rows", lambda db, **kw: rows)
    seen: list = []

    def _resolve(spans, rows_in, embed=None):
        seen.extend(rows_in)
        return [SimpleNamespace(status="unresolved", candidates=[]) for _ in spans]

    monkeypatch.setattr(list_resolver, "resolve", _resolve)
    tools._list_matches(None, SimpleNamespace(brand_scope=scope), ["sorento"], ["brand"])
    return {r.key for r in seen}


def test_class_only_scope_keeps_every_brand(monkeypatch):
    assert _captured(monkeypatch, frozenset({"class:__NONE__", "class:DIY"})) == {"b-sorento", "b-mocha"}


def test_brand_scope_still_limits_brands(monkeypatch):
    assert _captured(monkeypatch, frozenset({"b-sorento", "class:DIY"})) == {"b-sorento"}
