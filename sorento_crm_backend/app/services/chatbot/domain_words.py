# Stock is stock, incoming is incoming (owner ruling, PR #1329 hand test, 28 Sep 2026:
# "why stock maps to incoming one ah? stock is stock, incoming is incoming, no such thing
# as incoming stock").
#
# Measured: after "incoming SRTWC286-SH-NEW", the message "stoick SRTWC286-SH-NEW" gave
# the parser no domain (the typo), `apply()` carried the focus domain `incoming`, and the
# stock ask ran `crm_incoming_stock_list`. Nothing in the engine read the customer's own
# stock word, so a parser reading of `incoming`, or of no domain over a carried incoming
# focus, answered a stock ask from the incoming tool.
#
# The rule, read off the message BEFORE `apply()` (the seam `order_list.order_list_verdict`
# already reads a brand word at):
#
#   * a stock word and no incoming word -> the stock domain, where the turn would
#     otherwise land on incoming or on no domain at all;
#   * a quantity ("X x 150") and no incoming word, over a turn that would otherwise land
#     on incoming -> the stock domain (a quantity is a stock ask);
#   * an incoming word and no stock word -> the incoming domain, where the turn would
#     otherwise land on stock;
#   * both words ("incoming stock X", "stock and eta for X") -> the parser's reading.
#
# A reading of any OTHER domain (orders, promotions, purchase orders ...) is never
# touched: this rule only settles which of the two the customer asked for.
#
# The words are the two domains' own `switch_words` (`chatbot_domains`, read through the
# policy), not a second list. Pure: no I/O.
from __future__ import annotations

import re
from typing import Any, Iterable

STOCK = "inventory"
INCOMING = "incoming"

_INTENT = {STOCK: "check_stock", INCOMING: "check_incoming"}

_WORD_RE = re.compile(r"[0-9a-z]+")

#: The stock word a customer's typo is read against: "stoick", "stcok", "stockk". Only an
#: extra letter, a missing one or two swapped neighbours - never a changed letter, which
#: makes another word ("stick", "stack").
_TYPO_ROOTS = ("stock",)


def _words_of(policy: Any, domain: str) -> frozenset[str]:
    from app.services.chatbot.turn.policy import default_policy, domain_switch_words

    table = domain_switch_words(policy if policy is not None else default_policy())
    return frozenset(w for w, d in table.items() if d == domain and " " not in w)


def _one_slip(word: str, root: str) -> bool:
    """`word` is `root` with one letter added, one dropped, or two neighbours swapped."""
    if abs(len(word) - len(root)) == 1:
        short, long_ = sorted((word, root), key=len)
        return any(long_[:i] + long_[i + 1 :] == short for i in range(len(long_)))
    if len(word) == len(root) and word != root:
        diff = [i for i in range(len(word)) if word[i] != root[i]]
        return (
            len(diff) == 2
            and diff[1] == diff[0] + 1
            and word[diff[0]] == root[diff[1]]
            and word[diff[1]] == root[diff[0]]
        )
    return False


def _says(words: Iterable[str], vocabulary: frozenset[str], *, typos: bool) -> bool:
    for word in words:
        if word in vocabulary:
            return True
        if typos and len(word) >= 4 and any(_one_slip(word, root) for root in _TYPO_ROOTS):
            return True
    return False


def _asks_quantity(verdict: dict[str, Any]) -> bool:
    if verdict.get("demand_qty"):
        return True
    return any(
        isinstance(e, dict) and e.get("quantity") not in (None, "", 0)
        for e in verdict.get("entities") or []
    )


def _domains_read(verdict: dict[str, Any]) -> list[str]:
    asks = [a.get("domain") for a in verdict.get("asks") or [] if isinstance(a, dict)]
    if asks:
        return [d for d in asks if d]
    return [verdict["domain_hint"]] if verdict.get("domain_hint") else []


def _to(verdict: dict[str, Any], wrong: str, right: str) -> dict[str, Any]:
    out = dict(verdict)
    asks = [a for a in verdict.get("asks") or [] if isinstance(a, dict)]
    if asks:
        swapped, seen = [], set()
        for ask in asks:
            ask = {**ask, "domain": right} if ask.get("domain") == wrong else ask
            if ask.get("domain") in seen:
                continue
            seen.add(ask.get("domain"))
            swapped.append(ask)
        out["asks"] = swapped
    if out.get("domain_hint") in (wrong, None):
        out["domain_hint"] = right
    if out.get("intent_hint") in (_INTENT[wrong], None):
        out["intent_hint"] = _INTENT[right]
    return out


def stock_or_incoming(
    verdict: dict[str, Any], text: str, *, carried: Iterable[str], policy: Any = None
) -> tuple[dict[str, Any], str | None]:
    """The verdict with the customer's own stock or incoming word applied, and the rule
    that fired (None, and the verdict itself untouched, when none did).

    `carried` is the focus domain(s) the turn would inherit when the verdict names none.
    """
    if verdict.get("message_type") not in (None, "business_query"):
        return verdict, None
    words = _WORD_RE.findall((text or "").casefold())
    stock_word = _says(words, _words_of(policy, STOCK), typos=True)
    incoming_word = _says(words, _words_of(policy, INCOMING), typos=False)
    if stock_word == incoming_word:
        if stock_word or not _asks_quantity(verdict):
            return verdict, None
    read = _domains_read(verdict)
    lands = read or list(carried or [])

    if not incoming_word and INCOMING in lands:
        if stock_word:
            return _to(verdict, INCOMING, STOCK), "stock_word"
        if _asks_quantity(verdict):
            return _to(verdict, INCOMING, STOCK), "stock_quantity"
    if stock_word and not incoming_word and not read:
        return _to(verdict, INCOMING, STOCK), "stock_word"
    if incoming_word and not stock_word and STOCK in lands:
        return _to(verdict, STOCK, INCOMING), "incoming_word"
    return verdict, None
