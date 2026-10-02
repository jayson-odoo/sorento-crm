"""The ledger family of a customer row: the TRADING NAME behind it.

A shop is often several `customers` rows, one per ledger, that differ only by a bracketed
marker: `CHIN CHUN HARDWARE SDN BHD - [A/C I]`, `HANLIM TRADING (JB) SDN BHD (SRT)`. Ledgers
of one name are one customer. `ledger_family_key` is the comparison key two such rows share;
`ledger_family_label` is what the family is called.

Core, not the chatbot package: the chatbot's narrower (`app/services/chatbot/turn/narrow.py`)
groups a customer roster by it, and the stock-ask record (`app/services/stock_ask_service.py`)
names a customer-less ask by it (ASKS-UX item 4). Core must never import
`app.services.chatbot` (`tests/chatbot/test_import_boundary.py`), so the rule lives here and
both import it. Written with string operations rather than regexes because the chatbot's turn
package, which imports it, may not call `re` (AC-1520), and the rule was born there.
"""
from __future__ import annotations

#: Words that name a company's LEGAL FORM, not the business (`gate._LEGAL_FORM` on main,
#: spelled as words because the turn package may not use regular expressions).
_LEGAL_FORM_WORDS = frozenset({"SDN", "BHD"})


def _without_brackets(text: str) -> str:
    """`text` with every bracketed or parenthesised run removed.

    The ledger marker a customer row carries is always bracketed - `CHIN CHUN HARDWARE
    SDN BHD - [A/C I]`, `HANLIM TRADING (JB) SDN BHD (SRT)` - and it is the only part of
    the name that differs between the ledgers of one trading name.
    """
    out: list[str] = []
    depth = 0
    for ch in text:
        if ch in "[(":
            depth += 1
            continue
        if ch in "])":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out)


def ledger_family_key(text: str) -> str:
    """The TRADING NAME behind a customer row, as a comparison key.

    Main's `gate._cust_base`, rule for rule: upper-cased, bracketed parts dropped, the
    legal-form words dropped, everything non-alphanumeric collapsed to one space.
    """
    stripped = _without_brackets(text.upper())
    cleaned = "".join(ch if ch.isalnum() else " " for ch in stripped)
    return " ".join(w for w in cleaned.split() if w not in _LEGAL_FORM_WORDS)


def ledger_family_label(text: str) -> str:
    """What the family is CALLED: the row's own name without its ledger marker."""
    cleaned = " ".join(_without_brackets(text).split()).strip().strip("-").strip()
    return cleaned or text


_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}


def account_level_from_name(name: str | None) -> int | None:
    """The `A/C <n>` marker inside a `[..]` or `(..)` of a customer name, as a number.

    Roman I..X or arabic, any case, whitespace tolerant. Read ONCE, by the `acct_ledger_0001`
    seed; the live bot reads the `customers.account_level` setting, never the name.
    """
    if not name:
        return None
    depth = 0
    run: list[str] = []
    for ch in name.upper():
        if ch in "[(":
            if depth == 0:
                run = []
            depth += 1
            continue
        if ch in "])":
            if depth == 1:
                level = _marker_level("".join(run))
                if level is not None:
                    return level
            depth = max(0, depth - 1)
            continue
        if depth >= 1:
            run.append(ch)
    return None


def _marker_level(inside: str) -> int | None:
    """`A/C II` -> 2, from the text inside one bracket pair; None when it is not a marker."""
    text = " ".join(inside.split())
    if not text.startswith("A/C "):
        return None
    token = text[4:].strip()
    if token.isdigit():
        return int(token) or None
    return _ROMAN.get(token)
