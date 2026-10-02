"""The ledger family of a customer row: the TRADING NAME behind it.

A shop is often several `customers` rows, one per ledger, that differ only by a bracketed
marker: `CHIN CHUN HARDWARE SDN BHD - [A/C I]`, `HANLIM TRADING (JB) SDN BHD (SRT)`. Ledgers
of one name are one customer. `ledger_family_key` is the comparison key two such rows share;
`ledger_family_label` is what the family is called.

`family_words` names a list of customer rows that way in one line, group names only (DO-ASK-SIMPLIFY rule 1),
for the chatbot's DO header and its empty-list (miss) header alike.

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


def _bracket_runs(text: str) -> list[str]:
    """Every top-level bracketed or parenthesised run in `text`, brackets included."""
    runs: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch in "[(":
            if depth == 0:
                start = i
            depth += 1
        elif ch in "])" and depth:
            depth -= 1
            if depth == 0:
                runs.append(text[start : i + 1])
    return runs


def _shared_label(names: list[str]) -> str:
    """The family's name: the first row's name without the bracketed parts that tell its
    ledgers apart ("[A/C I]", "[IBORN]"), keeping any every ledger shares, such as the
    branch in "CHENG HUAT HARDWARE (SENTUL) SDN BHD"."""
    first = names[0]
    for run in _bracket_runs(first):
        if not all(run in other for other in names[1:]):
            first = first.replace(run, " ", 1)
    cleaned = " ".join(first.split()).strip().strip("-").strip()
    return cleaned or ledger_family_label(names[0])


def family_words(names: list[str]) -> str | None:
    """DO-ASK-SIMPLIFY rule 1 (owner, 2 Oct 2026): the customer rows in scope, named once.

    Owner rule (2 Oct 2026, PR #1435): a customer company is named by its GROUP NAME ONLY.
    The rows of one ledger family (the ledgers of one trading name) print the family label,
    "HANLIM TRADING SDN BHD", with no "(6 accounts)" count; one row prints its family label
    too, without its ledger marker, as `turn/compose.py`'s header always has. Several
    families are each named, "A, B and C", never "A and 2 more". Each DO row still carries
    its own full ledger name; only the header shortens.
    """
    # One ledger reached twice (a picked option carries its uuid twice) is one account.
    kept = list(dict.fromkeys(name for name in names if name))
    if not kept:
        return None
    families: dict[str, list[str]] = {}
    for name in kept:
        families.setdefault(ledger_family_key(name) or name, []).append(name)
    labels = [
        ledger_family_label(rows[0]) if len(rows) == 1 else _shared_label(rows)
        for rows in families.values()
    ]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


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
