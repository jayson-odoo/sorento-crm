# Search-scope disclosure: "Customer: X / Product: Y / Dates: Z" ahead of a
# single-domain ORDER hit (PLAN-chatbot-answer-half-reattach.md slice R5, AC-1694 to
# AC-1696).
#
# A direct, RESTRICTED port of origin/main's own `tail/compile_state.py::
# _search_scope_header` (deleted on this branch by the S3 turn re-architecture,
# `129c403c7`): only the two "always" axes (Customer, Product) plus the Dates line -
# the four ask-scoped axes (Order/Transporter/Container/Warehouse) are R6's own
# territory (no fixture in this slice ever names one), and the media-confirm /
# escalate-branch / empty-result-set guards main's version carries do not apply here -
# the bridge's own callers already know this is a genuine, single-domain hit before
# they ever reach this module. `tail/` (not `turn/`) because it is free to use `re`
# and to read the resolver's own gate/resolved dicts, the same freedom
# `answer_bridge.py` already has.
from __future__ import annotations

import re
from typing import Any, Mapping

# NARROWED (main, captain ruling 2026-08-24, ported verbatim): this header describes
# a DELIVERY ORDER search specifically - it used to gate on "domains the CRM
# date-filters", which let it render "Customer: all customers" on an inbound
# shipment answer, meaningless (a container has no customer).
_DATE_SCOPE_DOMAINS = frozenset({"order"})

_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _format_date(value: Any) -> str:
    """ISO to DD/MM/YYYY, matching the row fields the CRM already renders."""
    m = _ISO_DATE_RE.match(str(value or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else str(value or "")


def _fold(value: Any) -> str:
    """The same `[-\\s]+`-stripped, lower-cased key `turn.state.fold_token` computes -
    duplicated as a plain string op (not imported) because this module answers to no
    purity guard, but the fold rule itself is one rule, not two."""
    return re.sub(r"[-\s]+", "", str(value or "")).strip().lower()


def _raw_of_token(qf: Mapping[str, Any], token: str) -> str:
    """The word the customer actually typed for a resolver token, off the parser's
    own entities - a resolved code is not always what they wrote."""
    key = _fold(token)
    for ent in (qf.get("entities") or []) if isinstance(qf, Mapping) else []:
        if not isinstance(ent, dict):
            continue
        if _fold(ent.get("raw")) == key or _fold(ent.get("canonical_code")) == key:
            return str(ent.get("raw") or token)
    return str(token)


def _axis_words(
    gate_json: Mapping[str, Any] | None,
    resolver_json: Mapping[str, Any] | None,
    qf: Mapping[str, Any],
    *,
    types: set[str],
) -> str | None:
    """The words this axis is IN SCOPE by, rendered from the GATE's own
    `compatible_entities` (what was actually put in scope), never from the parser's
    hints alone - a pick off a numbered list scopes the search to ONE row, and the
    header must say so."""
    gate_entities = gate_json.get("compatible_entities") if isinstance(gate_json, Mapping) else None
    rows = [e for e in (gate_entities or []) if isinstance(e, dict) and e.get("entity_type") in types]
    if not rows:
        return None
    words: list[str] = []
    resolutions = resolver_json.get("resolutions") if isinstance(resolver_json, Mapping) else None
    for res in resolutions or []:
        if not isinstance(res, dict):
            continue
        hits = any(
            isinstance(m, dict) and m.get("entity_type") in types for m in (res.get("matches") or [])
        )
        token = str(res.get("token") or "").strip()
        if hits and token:
            raw = _raw_of_token(qf, token)
            if raw not in words:
                words.append(raw)
    if not words:
        for e in (qf.get("entities") or []) if isinstance(qf, Mapping) else []:
            if not isinstance(e, dict):
                continue
            if str(e.get("hint") or "") in types:
                value = str(e.get("raw") or "").strip()
                if value and value not in words:
                    words.append(value)
    if not words:
        for row in rows:
            value = str(row.get("title") or row.get("code") or "").strip()
            if value and value not in words:
                words.append(value)
    return ", ".join(words) if words else None


def _focus_words(rows: Any) -> str | None:
    """The SAME axis, off the FOCUS carry - a bare positional pick ("1") names no
    entity of its own, so `resolve_kinds` never ran this turn and the gate has
    nothing to read (`ResolveOutcome.payload is None`). The subject is still on the
    focus (`turn/apply.py::_narrow_and_plan`'s own `_set_kind_field`, written the
    turn a resolver last settled it, or the pick that just answered a customer
    picker), so this is the fallback `_axis_words` itself has none for."""
    words: list[str] = []
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        value = str(row.get("name") or row.get("raw") or row.get("canonical_code") or "").strip()
        if value and value not in words:
            words.append(value)
    return ", ".join(words) if words else None


def search_scope_header(
    *,
    domain: str | None,
    qf: Mapping[str, Any] | None,
    gate_json: Mapping[str, Any] | None,
    resolver_json: Mapping[str, Any] | None,
    focus_customers: Any = None,
    focus_products: Any = None,
) -> str | None:
    """"Customer: .../Product: .../Dates: ..." for a single ORDER-domain business
    turn - `None` outside that one domain (`_DATE_SCOPE_DOMAINS`), so the caller's
    own text is untouched for everything else.

    `domain` is the FETCH's own domain (`FetchSpec.domain`), not `qf`'s
    `domain_hint` - main's own port reads `qf.domain_hint or prev.domain_hint`
    because a positional pick names no domain of its own (AC-816 rule 4), and the
    fetch plan has already done that same carry-forward reconciliation by the time
    this runs.
    """
    q = qf if isinstance(qf, Mapping) else {}
    if str(domain or "").lower() not in _DATE_SCOPE_DOMAINS:
        return None
    start = q.get("date_filter_start")
    end = q.get("date_filter_end")
    if not start and not end:
        dates = "all dates"
    elif start and end and start == end:
        dates = _format_date(start) or "all dates"
    else:
        dates = f"{_format_date(start) if start else 'earliest'} to {_format_date(end) if end else 'today'}"
    customer_words = _axis_words(gate_json, resolver_json, q, types={"customer"}) or _focus_words(
        focus_customers
    )
    product_words = _axis_words(gate_json, resolver_json, q, types={"product"}) or _focus_words(
        focus_products
    )
    return "\n".join(
        [
            f"Customer: {customer_words or 'all customers'}",
            f"Product: {product_words or 'all products'}",
            f"Dates: {dates}",
        ]
    )
