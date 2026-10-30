"""Keyword ranking of the assistant's MCP tools against their capability text (no vectors).

Tool vectors are retired (the embedding keep set holds records only), so the tool pick scores each enabled tool by
how many of the query's words appear in its capability text (`build_capability_documents`: name, intent, aliases,
typical user questions, description), rarer words counting more, with the portal pin and the small intent nudges the
semantic ranking used to carry.
"""
from __future__ import annotations

import functools
import math
import re
from typing import Any

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "the and for are you can how what whats who when where which with from that this has had does did "
    "our your any all get give show tell use used using not but about into per of to in on at is it do we i me my a an "
    "unit units qty quantity item items "
    "be or as by if".split()
)
#: Where a word is found changes what it says about the tool.
_NAME_WEIGHT, _ALIAS_WEIGHT, _QUESTION_WEIGHT, _INTENT_WEIGHT, _TEXT_WEIGHT = 3.0, 2.5, 2.0, 1.5, 1.0


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower()) if len(w) >= 3 and w not in _STOP and not w.isdigit()}


_SAME = {"many": "much"}


def _stem(word: str) -> str:
    word = _SAME.get(word, word)
    for suffix in ("ies", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def _stems(text: str) -> set[str]:
    return {_stem(w) for w in _words(text)}


@functools.lru_cache(maxsize=1)
def _tool_texts() -> dict[str, dict[str, Any]]:
    from app.services.mcp_tool_capability_service import build_capability_documents

    out: dict[str, dict[str, Any]] = {}
    for doc in build_capability_documents(include_planned=False):
        md = doc.metadata or {}
        body = doc.body_text or ""
        intent = next((ln[len("Intent:"):] for ln in body.splitlines() if ln.startswith("Intent:")), "")
        description = next((ln[len("Description:"):] for ln in body.splitlines() if ln.startswith("Description:")), "")
        out[doc.source_key] = {
            "name": _stems(doc.source_key.replace("_", " ")),
            "alias": _stems(" ".join(md.get("aliases") or [])),
            "question": _stems(" ".join(md.get("typical_user_questions") or [])),
            "intent": _stems(intent),
            "text": _stems(description),
            "category": str(md.get("category") or ""),
        }
    return out


def _nudge(name: str, category: str, q: str) -> float:
    """The small intent corrections the semantic ranking carried, on whole-query keywords."""
    score = 0.0
    inbound = any(w in q for w in ("incoming", "inbound", "packing list", "shipment", "arriving", "arrival", " eta"))
    if inbound:
        score += 1.5 if category == "general_enquiries.incoming_stock" else 0.0
        score -= 1.0 if category in ("general_enquiries.stock", "general_enquiries.stock_ledger") else 0.0
    if category.startswith("internal_admin") and not any(w in q for w in ("admin", "raw", "back-office", "back office", "internal")):
        score -= 3.0
    if any(w in q for w in ("ledger", "transaction history", "movement history")):
        score += 1.5 if category == "general_enquiries.stock_ledger" else 0.0
        score -= 1.0 if category == "general_enquiries.stock" else 0.0
    elif not inbound:
        # A plain stock question is about what is on hand, not what is on its way.
        if "stock" in q or any(w in q for w in ("balance", "available", "on hand", "how many")):
            score += 2.5 if category == "general_enquiries.stock" else 0.0
            score -= 2.0 if category == "general_enquiries.incoming_stock" else 0.0
            score -= 1.0 if category == "general_enquiries.stock_ledger" else 0.0
    if any(w in q for w in ("delivery status", "status of delivery", "where is my delivery")):
        score += 2.5 if category == "order_enquiries" else 0.0
        score -= 3.0 if category == "general_enquiries.incoming_stock" else 0.0
    return score


def rank_tools(query: str, enabled_tools: list[str], top_k: int, *, portal_intent: bool = False) -> list[dict[str, Any]]:
    """The `top_k` enabled tools best matching `query`; each has tool_name, score, why_selected, is_current."""
    texts = _tool_texts()
    pool = {n: texts[n] for n in (enabled_tools or list(texts)) if n in texts}
    if not pool:
        return []
    q = (query or "").lower()
    qwords = _stems(q)
    df: dict[str, int] = {}
    for t in pool.values():
        for w in set().union(t["name"], t["alias"], t["question"], t["intent"], t["text"]):
            df[w] = df.get(w, 0) + 1
    n = len(pool)

    def idf(w: str) -> float:
        return math.log((n + 1) / (df.get(w, 0) + 0.5)) + 0.1

    scored: list[tuple[float, str]] = []
    for name, t in pool.items():
        score = 0.0
        for w in qwords:
            best = max(
                (weight for part, weight in (
                    ("name", _NAME_WEIGHT), ("alias", _ALIAS_WEIGHT), ("question", _QUESTION_WEIGHT),
                    ("intent", _INTENT_WEIGHT), ("text", _TEXT_WEIGHT),
                ) if w in t[part]),
                default=0.0,
            )
            score += best * idf(w)
        if score <= 0 and not (portal_intent and name == "crm_portal_link_get"):
            continue
        score += _nudge(name, t["category"], q)
        if portal_intent:
            score += 100.0 if name == "crm_portal_link_get" else -5.0
        scored.append((score, name))
    scored.sort(key=lambda r: (-r[0], r[1]))
    return [
        {"tool_name": name, "score": round(score, 3), "why_selected": "keyword match on the tool's capability text",
         "is_current": True, "chunk_text": "", "missing_params": []}
        for score, name in scored[:top_k]
    ]
