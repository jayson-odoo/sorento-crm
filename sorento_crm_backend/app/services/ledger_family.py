"""The ledger family of a customer row: which which-one-list entry it belongs to.

A shop is often several `customers` rows, one per ledger, that differ only by a bracketed
marker: `CHIN CHUN HARDWARE SDN BHD - [A/C I]`, `HANLIM TRADING (JB) SDN BHD (SRT)`. Ledgers of
one trading name are one customer, and the office's customer groups join ledgers of different
names and name the entry (owner ruling 9 Nov 2026: "answer by the group ... return all
accounts"). `ledger_family_key` is the comparison key the rows of one entry share;
`ledger_family_label` is what the entry is called; `trading_name_key` is the name rule.

`group_names` / `family_words` name a list of customer rows by group only (DO-ASK-SIMPLIFY
rule 1, owner rule 2 Oct 2026: no count, no "and N more"), for the chatbot's DO headers and
its customer-scope refusal line alike.

Core, not the chatbot package: the chatbot's narrower (`app/services/chatbot/turn/narrow.py`)
groups a customer roster by it, and the stock-ask record (`app/services/stock_ask_service.py`)
names a customer-less ask by it (ASKS-UX item 4). Core must never import
`app.services.chatbot` (`tests/chatbot/test_import_boundary.py`), so the rule lives here and
both import it. Written with string operations rather than regexes because the chatbot's turn
package, which imports it, may not call `re` (AC-1520), and the rule was born there.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar

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


def normalise_customer_name(text: str) -> str:
    """The key the group map uses: upper-cased, whitespace collapsed."""
    return " ".join(text.upper().split())


class _TurnGroups:
    """The turn's customer groups (the office's explicit links, CUSTOMER-GROUP-GATE), indexed
    once so a roster of hundreds of names does no scan per name. Pure strings, no DB, no `re`.
    They decide what an answer is CALLED and join ledgers of different names; same-name ledgers
    are one entry with or without them (owner ruling 9 Nov 2026, see `ledger_family_key`)."""

    def __init__(self, mapping: Mapping[str, str], ids: Mapping[str, str] | None) -> None:
        #: normalised customer name -> group name
        self.by_name = {normalise_customer_name(k): v for k, v in mapping.items()}
        #: customer id -> group name; None when the turn loaded no id map (a name-only caller)
        self.by_id = {str(k): v for k, v in ids.items()} if ids is not None else None
        labels = [*mapping.values(), *(ids or {}).values()]
        #: normalised group names, so a picked line's label (the group's name) keys as the group
        #: (a KEY only; it never makes a ledger a member)
        self.own = {normalise_customer_name(v) for v in labels}
        #: trading name -> the group an UNGROUPED ledger of that name is answered with (owner Q1,
        #: 9 Nov 2026: "we should treat it as part of group also"). Answer-time only: no data link.
        #: A group's own name first; then the names of the group's ledgers (a group named after
        #: one shop can hold a sibling of another name), unless two groups claim that name. Two
        #: groups of one trading name: the smallest name, so the label never depends on DB order.
        self.joins: dict[str, str] = {}
        for g in sorted(set(labels)):
            self.joins.setdefault(trading_name_key(g), g)
        by_member: dict[str, set[str]] = {}
        for name, g in mapping.items():
            by_member.setdefault(trading_name_key(name), set()).add(g)
        for key, found in by_member.items():
            if key and len(found) == 1:
                self.joins.setdefault(key, next(iter(found)))
        self.joins.pop("", None)


_GROUPS: ContextVar[_TurnGroups | None] = ContextVar("ledger_family_groups", default=None)

@contextmanager
def customer_groups(mapping: Mapping[str, str], ids: Mapping[str, str] | None = None) -> Iterator[None]:
    """Hold the turn's groups for the block: `mapping` (customer name -> group name, for a caller
    holding only a name) and `ids` (customer id -> group name, authoritative for a caller holding
    the row's id). Both empty = no groups: ledgers join by trading name alone.

    Set once per turn by the engine and by `stock_ask_service`."""
    token = _GROUPS.set(_TurnGroups(mapping, ids) if (mapping or ids) else None)
    try:
        yield
    finally:
        _GROUPS.reset(token)


def without_ledger_marker(text: str) -> str:
    """`text` without its bracketed ledger markers, for a line that must not print one."""
    cleaned = " ".join(_without_brackets(text).split()).strip().strip("-").strip()
    return cleaned or text


def customer_group_of(text: str, uuid: str | None = None) -> str | None:
    """The group name the turn holds for this customer row, or None.

    By the row's id when the caller has it and the turn loaded the id map (explicit, so two
    rows of one full name can sit apart); else by the row's exact normalised FULL name only
    (owner ruling (b), 2 Oct 2026): no marker-stripped probe, no "is a group's own name"
    probe. A name the map leaves out (rows in and out of a group, or in two) is ungrouped."""
    groups = _GROUPS.get()
    if groups is None:
        return None
    if uuid and groups.by_id is not None:
        return groups.by_id.get(str(uuid))
    return groups.by_name.get(normalise_customer_name(text))


def _words(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text.upper())
    return " ".join(w for w in cleaned.split() if w not in _LEGAL_FORM_WORDS)


def group_key(group_name: str) -> str:
    """The comparison key of a customer GROUP: the trading name of its own name, so a ledger of
    that trading name, grouped or not, is the same entry (owner Q1, 9 Nov 2026: "we should treat it
    as part of group also ... we should be more lenient")."""
    return trading_name_key(group_name)


def trading_name_key(text: str) -> str:
    """The TRADING NAME a word or a ledger name speaks for: upper-cased, bracketed parts dropped,
    the legal-form words dropped, everything non-alphanumeric collapsed to one space. Search
    matches a typed word with it, and `ledger_family_key` joins same-name ledgers with it."""
    return _words(_without_brackets(text.upper()))


def supplier_family_key(text: str) -> str:
    """The key the records of ONE supplier share: its trading name (`trading_name_key`), so
    HANLIM TRADING (400-H018) and HANLIM TRADING (403-H007) are one supplier (owner ruling
    "2120a", 7 Nov 2026: same-name suppliers are ONE supplier, grouped by `ledger_family`, and
    the bot never asks which one). The `ledger_family` rule as it stood before
    CUSTOMER-GROUP-GATE: that ruling (explicit groups only) is about customer ledgers, and a
    supplier has no customer group (GATE-SUPPLIER-FAMILY)."""
    return trading_name_key(text)


def supplier_family_label(text: str) -> str:
    """What a supplier family is CALLED: the record's name without its bracketed code."""
    return without_ledger_marker(text)


def group_named(text: str) -> str | None:
    """The key of the turn's customer group whose own name `text` is, or None (a word typed as
    a group's exact name speaks for that group)."""
    groups = _GROUPS.get()
    if groups is not None and normalise_customer_name(text) in groups.own:
        return group_key(text)
    return None


def entry_group(text: str, uuid: str | None = None) -> str | None:
    """The customer group this row's entry is answered with, or None: its own group (by id, else
    exact full name), else the group of its trading name (owner Q1, 9 Nov 2026)."""
    group = customer_group_of(text, uuid)
    if group is not None:
        return group
    groups = _GROUPS.get()
    if groups is None:
        return None
    return groups.joins.get(trading_name_key(text))


def ledger_family_key(text: str, uuid: str | None = None) -> str:
    """The key the rows of ONE customer entry share: one answer covers them all, never a
    "which account?" between them.

    Owner ruling, 9 Nov 2026 (re-land of CUSTOMER-GROUP-GATE): "it should just answer by the
    group, the user doesn't care about which account la, we should just return all accounts".
    A row whose entry has a customer group (`entry_group`) answers with that GROUP's key; every
    other row with its trading name, so the ledgers of one name are one entry. Access scope is
    the caller's: only rows the asker may see ever reach here.
    """
    own = trading_name_key(text)
    group = entry_group(text, uuid)
    if group is not None:
        return group_key(group) or own
    return own


def ledger_family_label(text: str, uuid: str | None = None) -> str:
    """What the entry is CALLED: its group's name (`entry_group`), else the row's own name
    without its ledger marker."""
    return entry_group(text, uuid) or without_ledger_marker(text)


def customer_header_words(entries: Iterable[tuple[str, str | None]]) -> str:
    """The words a `Customer:` line prints for `entries` = `(customer name, group name or None)`.

    One word per customer entry (`ledger_family_key`): a group by its name, an ungrouped ledger by
    its own full name, except that an ungrouped ledger of a group's trading name (in these
    entries) prints as that group (owner Q1, 9 Nov 2026). First-seen order, identical words once,
    no count, none dropped."""
    pairs = [(str(n or "").strip(), g) for n, g in entries]
    groups: dict[str, str] = {}
    for n, g in pairs:
        if n and g:
            groups.setdefault(group_key(g), g)
            groups.setdefault(trading_name_key(n), g)
    words: list[str] = []
    for name, group in pairs:
        if not name:
            continue
        word = group or groups.get(trading_name_key(name)) or name
        if word not in words:
            words.append(word)
    return ", ".join(words)


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


def _without_trailing_marker(name: str) -> str:
    """One ledger's group name: its name without the bracketed ledger marker at its END
    ("HANLIM TRADING SDN BHD [A/C I]", "... - [IBORN]", "... (CERAMIC & ELLECI)"); a bracket
    inside the name ("CHENG HUAT HARDWARE (SENTUL) SDN BHD") is part of it and stays."""
    text = " ".join(name.split()).strip().rstrip("-").strip()
    while text.endswith(("]", ")")):
        runs = _bracket_runs(text)
        if not runs or not text.endswith(runs[-1]):
            break
        stripped = text[: -len(runs[-1])].strip().rstrip("-").strip()
        if not stripped:
            break
        text = stripped
    return text


def group_names(names: list[str]) -> list[str]:
    """The group (trading) names behind customer rows, each once, in first-seen order.

    Owner rule (2 Oct 2026): when the chatbot names a customer company it shows the GROUP
    NAME ONLY ("HANLIM TRADING SDN BHD"), never a ledger marker, an account count or "and N
    more". Rows of one family (`ledger_family_key`) are one group; its name keeps the
    brackets every row shares (the branch in "CHENG HUAT HARDWARE (SENTUL) SDN BHD") and
    drops the ones that tell the ledgers apart.
    """
    families: dict[str, list[str]] = {}
    for name in dict.fromkeys(n for n in names if n):
        families.setdefault(ledger_family_key(name) or name, []).append(name)
    return list(
        dict.fromkeys(
            _without_trailing_marker(_shared_label(rows) if len(rows) > 1 else rows[0])
            for rows in families.values()
        )
    )


def family_words(names: list[str]) -> str | None:
    """DO-ASK-SIMPLIFY rule 1: the customer rows in scope, named once per group, comma
    separated ("HANLIM TRADING SDN BHD"; "CHIN CHUN HARDWARE SDN BHD, JIMMY - I"). Each DO
    row still carries its own full ledger name; only the header shortens."""
    groups = group_names(names)
    return ", ".join(groups) if groups else None


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
