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

from collections.abc import Iterable, Iterator, Mapping, Sequence
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
    """The turn's customer groups (owner ruling 2 Oct 2026: a group is the office's own
    say-so, the name rule only the fallback), indexed once so a roster of hundreds of names
    does no scan per name. Pure strings, no DB, no `re`."""

    def __init__(self, mapping: Mapping[str, str]) -> None:
        #: normalised customer name -> group name
        self.by_name = {normalise_customer_name(k): v for k, v in mapping.items()}
        #: normalised group name -> group name (a group is its own customer)
        self.own = {normalise_customer_name(v): v for v in mapping.values()}
        #: the comparison keys the groups answer with -> the group's name
        self.keys = {_words(v): v for v in mapping.values()}


_GROUPS: ContextVar[_TurnGroups | None] = ContextVar("ledger_family_groups", default=None)

#: Appended to an UNGROUPED row's key when a group of the turn has the same one, so
#: `JUBIN BMS (NS)` (no group) stays apart from the `JUBIN BMS SDN BHD` group it used to be
#: merged into. No name rule can produce it.
_UNGROUPED = " (NO GROUP)"

#: Owner ruling pending (2 Oct 2026). Does an UNGROUPED ledger whose name-rule key equals a
#: group's key (`JUBIN BMS (NS) SDN BHD` beside the `JUBIN BMS SDN BHD` group) JOIN that group
#: (True) or stay a separate customer (False, today's behaviour)? The ONE switch: the header
#: formatter, `ledger_family_key` and `gate._cust_base` all read it, so flipping it is this line.
UNGROUPED_JOINS_NAME_MATCHED_GROUP = False


def apart_from_group(key: str) -> str:
    """`key` (an UNGROUPED row's name-rule key) as the turn compares it: kept apart from a
    group of the turn with the same key unless `UNGROUPED_JOINS_NAME_MATCHED_GROUP`."""
    groups = _GROUPS.get()
    if not UNGROUPED_JOINS_NAME_MATCHED_GROUP and groups is not None and key in groups.keys:
        return key + _UNGROUPED
    return key


@contextmanager
def customer_groups(mapping: Mapping[str, str]) -> Iterator[None]:
    """Hold `mapping` (customer name -> group name) for the block. Empty = name rule only.

    Set once per turn by the engine and by `stock_ask_service`; outside any block the name
    rule answers alone."""
    token = _GROUPS.set(_TurnGroups(mapping) if mapping else None)
    try:
        yield
    finally:
        _GROUPS.reset(token)


def _label_without_marker(text: str) -> str:
    cleaned = " ".join(_without_brackets(text).split()).strip().strip("-").strip()
    return cleaned or text


def _without_marker(text: str) -> str:
    """`text` without its `[A/C n]` / `(A/C n)` account marker only; any other bracketed run
    (`(NS)`, `(1990)`) is part of the name and stays."""
    out: list[str] = []
    run: list[str] | None = None
    for ch in text:
        if run is None:
            if ch in "[(":
                run = [ch]
            else:
                out.append(ch)
            continue
        run.append(ch)
        if ch in "])":
            inside = "".join(run[1:-1])
            if _marker_level(" ".join(inside.upper().split())) is None:
                out.extend(run)
            run = None
    if run is not None:
        out.extend(run)
    return " ".join("".join(out).split())


def customer_group_of(text: str) -> str | None:
    """The group name the turn holds for this customer name, or None (use the name rule).

    Found by the row's own name, then by its name without the account marker only (`X [A/C II]`
    follows a grouped `X`), then as a group's own name (the group is its own customer)."""
    groups = _GROUPS.get()
    if groups is None:
        return None
    for probe in (normalise_customer_name(text), normalise_customer_name(_without_marker(text))):
        if probe in groups.by_name:
            return groups.by_name[probe]
        if probe in groups.own:
            return groups.own[probe]
    return None


def _words(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text.upper())
    return " ".join(w for w in cleaned.split() if w not in _LEGAL_FORM_WORDS)


def ledger_family_key(text: str) -> str:
    """The TRADING NAME behind a customer row, as a comparison key.

    Main's `gate._cust_base`, rule for rule: upper-cased, bracketed parts dropped, the
    legal-form words dropped, everything non-alphanumeric collapsed to one space. A name
    the turn's customer groups cover answers with its GROUP's key instead (the group name
    whole, so `JUBIN BMS (1990) SDN BHD` is not `JUBIN BMS`).
    """
    group = customer_group_of(text)
    if group is not None:
        return _words(group)
    return apart_from_group(_words(_without_brackets(text.upper())))


def ledger_family_label(text: str) -> str:
    """What the family is CALLED: the group's name when the turn has one for the row,
    else the row's own name without its ledger marker."""
    group = customer_group_of(text)
    if group is not None:
        return group
    groups = _GROUPS.get()
    name_key = _words(_without_brackets(text.upper()))
    if groups is not None and name_key in groups.keys:
        if UNGROUPED_JOINS_NAME_MATCHED_GROUP:
            return groups.keys[name_key]
        # An ungrouped row sharing a group's key keeps its own parentheticals, so its line
        # reads `JUBIN BMS (NS) SDN BHD` beside the group's, not as the group's twin.
        return _without_marker(text).strip().strip("-").strip() or text
    return _label_without_marker(text)


def _bracket_runs(text: str) -> list[str]:
    """The top-level bracketed or parenthesised runs of `text`, each whole, upper-cased."""
    runs: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in text:
        if ch in "[(":
            if depth == 0:
                cur = []
            depth += 1
        if depth:
            cur.append(ch)
        if ch in "])" and depth:
            depth -= 1
            if depth == 0:
                runs.append(" ".join("".join(cur).upper().split()))
    return runs


def shared_bracket_label(names: Sequence[str]) -> str:
    """The name several ledgers of one family share: the first name with every bracketed run
    dropped EXCEPT those every name carries (`(SENTUL)`, `(M)`); a run only some carry
    (`(CERAMIC & ELLECI)`) or an `[A/C n]` account marker is a ledger's, not the company's name."""
    names = [n for n in names if n]
    if not names:
        return ""
    shared = set(_bracket_runs(names[0]))
    for name in names[1:]:
        shared &= set(_bracket_runs(name))
    # An account marker is the ledger's, never the company's name, even when all share it.
    shared = {r for r in shared if _marker_level(r[1:-1].strip()) is None}
    out: list[str] = []
    depth = 0
    run: list[str] = []
    for ch in names[0]:
        if ch in "[(":
            if depth == 0:
                run = []
            depth += 1
        if depth:
            run.append(ch)
            if ch in "])":
                depth -= 1
                if depth == 0:
                    text = "".join(run)
                    if " ".join(text.upper().split()) in shared:
                        out.append(text)
            continue
        out.append(ch)
    cleaned = " ".join("".join(out).split()).strip().strip("-").strip()
    return cleaned or names[0]


def customer_header_words(entries: Iterable[tuple[str, str | None]]) -> str:
    """The words a `Customer:` line prints for `entries` = `(customer name, group name or None)`.

    A ledger joins a company line ONLY through its explicit customer group (owner ruling (b),
    2 Oct 2026: no automatic name-rule joining). One word per group (its name), one per
    ungrouped ledger (its own full name); first-seen order, identical words once, no count,
    none dropped. An ungrouped ledger whose name-rule key is a group's key (in these entries)
    prints as that group only under `UNGROUPED_JOINS_NAME_MATCHED_GROUP`."""
    pairs = [(str(n).strip(), g) for n, g in entries if n and str(n).strip()]
    groups = {_words(g): g for _n, g in pairs if g}
    words: list[str] = []
    for name, group in pairs:
        if not group and UNGROUPED_JOINS_NAME_MATCHED_GROUP:
            group = groups.get(_words(_without_brackets(name.upper())))
        word = group or name
        if word not in words:
            words.append(word)
    return ", ".join(words)


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
