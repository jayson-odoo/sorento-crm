# The order list conversation: a delivery order, sales order or outstanding list the
# customer is reading, and the words that move it (#1262 fix lane round 7, the owner's
# hand test of round 6, 27 Sep 2026).
#
# Two seams, both in `engine._run_stages`:
#
# * `order_list_verdict` reads the message against the open list BEFORE the verdict is
#   applied, the way the top selling lane reads a message against its ranking: a brand
#   word alone switches the brand and re-runs the list (R3), the clear words drop the
#   brand and re-run it (R5), and a fresh order ask that names its own subject but no
#   brand starts with all brands (R4). The parser's own reading of these messages is
#   not stable (v40 read "how aobut mocha" as a request for help), so the words decide.
# * `list_reply` takes the escalate offer and the routing picker out of a reply inside
#   the list, and says an empty result in one line (R6). The escalation lane stays one
#   message away: a request for a person never reaches a business reply at all.
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from app.services.chatbot import jsc
from app.services.chatbot.dealer_stock import refers_to_salesman
from app.services.chatbot.turn.pending import ESCALATION_OFFER_KINDS

_WORD_RE = re.compile(r"[0-9a-z]+")

#: Statuses with a lane of their own, never an order list.
_NOT_A_LIST = frozenset({"sales_report", "sales_analysis", "top_selling"})

#: Words that may sit beside a brand word in "how about mocha", "mocha only?",
#: "then sorento brand". Matched allowing one slip in a word of four letters or more
#: ("aobut").
_SWITCH_FILLER = frozenset(
    {
        "how", "about", "what", "and", "or", "then", "only", "instead", "brand", "brands",
        "for", "the", "ok", "okay", "pls", "please", "now", "so", "show", "me", "try",
        "with", "in", "just", "check", "see", "same", "but", "also",
    }
)

_CLEAR_VERBS = frozenset({"all", "any", "every", "both", "clear", "remove", "no", "drop", "reset", "without"})
_BRAND_NOUNS = frozenset({"brand", "brands"})
_CLEAR_FILLER = frozenset({"the", "filter", "pls", "please", "ok", "okay", "show", "just", "a", "any"})

#: The one line an empty list reads. The header above it says what was searched.
EMPTY_LIST_LINE = "No orders matched these."


def _words(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").casefold())


def _is_filler(word: str) -> bool:
    from app.services.chatbot.turn_runtime import _osa_distance

    if word in _SWITCH_FILLER:
        return True
    return len(word) >= 4 and any(len(f) >= 4 and _osa_distance(word, f) <= 1 for f in _SWITCH_FILLER)


def is_open_order_list(focus: Any) -> bool:
    """Is the conversation on an order list (a DO, SO or outstanding list)?"""
    domains = list(getattr(focus, "domains", None) or [])
    return "order" in domains and getattr(focus, "status", None) not in _NOT_A_LIST


def clears_the_brand(text: str) -> bool:
    """"all brand", "all brands", "any brand", "clear the brand", "remove the brand",
    "no brand" and the like: a brand noun, a clearing word, nothing else."""
    words = _words(text)
    if not words or len(words) > 5:
        return False
    return (
        bool(set(words) & _BRAND_NOUNS)
        and bool(set(words) & _CLEAR_VERBS)
        and all(w in _BRAND_NOUNS | _CLEAR_VERBS | _CLEAR_FILLER for w in words)
    )


def brand_word_alone(db: Session, text: str) -> str | None:
    """The brand word of a message that is a brand word and filler only ("how aobut
    mocha", "mocha?", "sorento"), read against the live brands the same way the brand
    filter reads it (`turn_runtime.brand_rows_for_word`). None for anything else."""
    from app.services.chatbot.turn_runtime import active_brands, brand_rows_for_word

    words = _words(text)
    if not words or len(words) > 5:
        return None
    others = [w for w in words if not _is_filler(w)]
    if len(others) != 1:
        return None
    word = others[0]
    try:
        brands = active_brands(db)
    except Exception:  # noqa: BLE001 - no brand list means no brand word, never a failure
        return None
    return word if brand_rows_for_word(brands, word) else None


def _continuation(verdict: dict[str, Any], *, entities: list[dict[str, Any]]) -> dict[str, Any]:
    """The verdict of a bare continuation of the open list: an order read with no domain
    word of its own, so the document, status, customer and dates carry (round 5 R2), and
    nothing of the parser's escalation reading left on it."""
    escalation = verdict.get("escalation") if isinstance(verdict.get("escalation"), dict) else {}
    return {
        **verdict,
        "message_type": "business_query",
        "intent_hint": "check_order",
        "domain_hint": "order",
        "domain_in_message": False,
        "entities": entities,
        "escalation": {**escalation, "is_escalation_confirmation": False, "escalation_declined": False},
        "person_mention": None,
        "reference_positions": [],
        "reference_target": None,
        "is_affirmative": None,
        "scope_intent": "specific",
        "broaden_axis": None,
        "correction": False,
        "topic_reset": False,
        "document": None,
        "status": None,
        "order_status": None,
        "date_mode": None,
        "date_filter_start": None,
        "date_filter_end": None,
    }


def _names_own_subject(verdict: dict[str, Any]) -> bool:
    return any(
        isinstance(e, dict)
        and e.get("current_message") is not False
        and jsc.js_string(e.get("hint") or "").strip().lower() in ("customer", "product")
        for e in (verdict.get("entities") or [])
    )


def _names_a_brand(verdict: dict[str, Any]) -> bool:
    return any(
        isinstance(e, dict) and jsc.js_string(e.get("hint") or "").strip().lower() == "brand"
        for e in (verdict.get("entities") or [])
    )


def order_list_verdict(db: Session, verdict: dict[str, Any], state: Any, text: str) -> tuple[dict[str, Any], Any, str | None]:
    """The verdict and state to apply for this message, and the rule that fired.

    * R5 the clear words over an open list: a continuation with the brand dropped.
    * R3 a brand word alone over an open list: a continuation filtered by that brand.
    * R4 an order ask that names its own subject and no brand: all brands, whatever
      the conversation carried. A bare continuation ("and hanlim?", a number, "what
      about August") names no domain word and keeps the brand.
    """
    focus = state.focus
    pending = state.pending
    if pending is not None and getattr(pending, "kind", None) in ESCALATION_OFFER_KINDS:
        open_pending = None
    else:
        open_pending = pending
    if is_open_order_list(focus):
        if clears_the_brand(text):
            state = replace(state, focus=replace(focus, outstanding_brand_ids=[]), pending=open_pending)
            return _continuation(verdict, entities=[]), state, "order_list_brand_cleared"
        word = brand_word_alone(db, text)
        if word is not None:
            entity = {"raw": word, "hint": "brand", "canonical_code": None, "current_message": True, "confident": True}
            return _continuation(verdict, entities=[entity]), replace(state, pending=open_pending), "order_list_brand_switched"
    if (
        focus.outstanding_brand_ids
        and jsc.js_string(verdict.get("domain_hint") or "").strip() == "order"
        and verdict.get("domain_in_message") is True
        and _names_own_subject(verdict)
        and not _names_a_brand(verdict)
    ):
        return verdict, replace(state, focus=replace(focus, outstanding_brand_ids=[])), "order_list_fresh_ask_all_brands"
    return verdict, state, None


def list_reply(answer: Any, *, focus: Any, fetch_plan: Any, envelopes: list[dict[str, Any]]) -> Any:
    """R6: a reply inside an order list carries no escalate offer and no routing picker,
    and an empty list says so in one line under the header (`EMPTY_LIST_LINE`), keeping
    any "could not find" note. Any other reply is returned as is."""
    fetch = list(getattr(fetch_plan, "fetch", None) or [])
    if len(fetch) != 1 or fetch[0].domain != "order" or not envelopes:
        return answer
    if getattr(focus, "status", None) in _NOT_A_LIST:
        return answer
    from app.services.chatbot.turn.fetch import envelope_missed

    text, _had = refers_to_salesman(getattr(answer, "text", "") or "")
    question = answer.question
    if question is not None:
        if question.kind in ESCALATION_OFFER_KINDS:
            question = None
        elif (question.payload or {}).get("escalate_offered") is True:
            question = replace(question, payload={**question.payload, "escalate_offered": False})
    envelope = envelopes[0]
    if envelope_missed(envelope) and not envelope.get("denied") and question is None:
        text = _one_line_miss(text)
    if text == answer.text and question is answer.question and answer.offer is None:
        return answer
    return replace(answer, text=text, question=question, offer=None)


_HEADER_LABELS = ("Customer:", "Product:", "Brand:", "Dates:", "Order:", "Transporter:", "Container:", "Warehouse:", "Location:", "Order date:")


def _one_line_miss(text: str) -> str:
    """The header lines and the "could not find" notes of a miss, then one line."""
    kept = [
        line.strip()
        for line in (text or "").splitlines()
        if line.strip().startswith(_HEADER_LABELS) or "find" in line.casefold()
    ]
    return "\n".join([*kept, EMPTY_LIST_LINE]) if kept else EMPTY_LIST_LINE
