"""Shape B's `require` seam: a pure map off what the parser already emits.

Work item B1 (`PLAN-attribute-first-asks.md`). No message-text matching beyond the
existing `_CERT_RE` on an `attachment_type` entity's own `raw` - `derive_require` is
`derive_routing`'s sibling (`app/services/chatbot/head/output_exchange.py`), not a
second parser. A turn whose intent carries no leg returns `None` and behaves exactly
as it does today (AC-1322's invariant).

Contract: `documentation/plans/chatbot/attribute-first-asks-acceptance-criteria.md`
AC-1303, AC-1304.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot.head.output_exchange import _CERT_RE

# Intents that need nothing beyond their own name to name a leg - the customer's own
# word for each is also the leg's key, which is what `derive_predicate_words` below
# subtracts from the described set.
_BARE_LEG_BY_INTENT: dict[str, str] = {
    "check_stock": "stock",
    "check_incoming": "incoming",
    "check_promotion": "promotion",
}


def _attachment_type_raws(parser_output: dict[str, Any]) -> list[str]:
    """Every `attachment_type` entity's own raw, in order, non-empty, deduped."""
    raws: list[str] = []
    for entity in parser_output.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        if str(entity.get("hint") or "").strip().lower() != "attachment_type":
            continue
        raw = str(entity.get("raw") or "").strip()
        if raw and raw not in raws:
            raws.append(raw)
    return raws


def derive_require(parser_output: dict[str, Any]) -> dict[str, Any] | None:
    """`{leg: value}` for the turn's intent, or `None` when it carries no leg.

    `check_product_attachment` splits on the FIRST `attachment_type` entity's raw:
    a cert-shaped word (`_CERT_RE`, the same regex `derive_routing` already uses for
    the cert-vs-photo team split) maps to the `certificate` leg; any other label
    passes through verbatim as the `attachment_type` leg, resolved server-side
    (`_leg_attachment_type` in `product_predicate_service.py`) so a new document
    class never needs a parser prompt change.
    """
    intent = parser_output.get("intent_hint")
    if intent in _BARE_LEG_BY_INTENT:
        return {_BARE_LEG_BY_INTENT[intent]: True}

    if intent == "check_product_attachment":
        raws = _attachment_type_raws(parser_output)
        if not raws:
            return None
        raw = raws[0]
        if _CERT_RE.search(raw):
            return {"certificate": True}
        return {"attachment_type": raw}

    return None


def derive_predicate_words(parser_output: dict[str, Any], require: dict[str, Any] | None) -> list[str]:
    """Every word the described set must strip from the customer's own query.

    Every `attachment_type` entity's raw, plus the intent's own word for a bare leg
    (`stock`, `incoming`, `promotion` - the leg key IS the word, since nothing else
    named it). `check_product_attachment` needs no extra word: the attachment_type
    raw already covers it.
    """
    if not require:
        return []
    words = _attachment_type_raws(parser_output)
    intent = parser_output.get("intent_hint")
    if intent in _BARE_LEG_BY_INTENT:
        leg = _BARE_LEG_BY_INTENT[intent]
        if leg not in words:
            words.append(leg)
    return words
