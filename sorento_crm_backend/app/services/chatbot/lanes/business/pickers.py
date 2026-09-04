"""Ports of `annotate-incoming-picker.js` (35) and `annotate-customer-picker.js` (122).

Both annotate the picker text the gate ALREADY rendered: same lines, same order, same
numbering, a suffix per numbered line and at most one trailing sentence. Display only -
`compatible_entities`, the roster the next-turn pick resolves against, is untouched by
either, and that is what makes them safe to run after the gate has decided.

`out = gate` in both bodies: the annotator MUTATES the gate item and returns it, so the
`offer` exit carries the gate's own keys plus `escalate_message` / `is_clarification`.
Reproduced, because `not-found-error-message` downstream spreads that item.

The probe seam is a parameter, not a call: `probe` is whatever `sub-get-results` returned
(`{answers|items: [...]}`), or `None` when it did not run. `annotate_customer` tells the
two apart on purpose - a probe that FAILED must render the bare picker, never a confident
"- no delivery" on evidence that was never gathered.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.chatbot import jsc

# JS `\d` is ASCII-only; Python's matches every Unicode decimal, so `[0-9]` it is. `$`
# becomes `\Z` because Python's `$` also matches before a trailing newline.
_NUMBERED_LINE = re.compile(r"^\s*[0-9]+\.\s+(.+?)\s*\Z")
_PRODUCT_CODE_LABEL = re.compile(r"product\s*code", re.IGNORECASE)
_CUSTOMER_LABEL = re.compile(r"^\s*customer\s*\Z", re.IGNORECASE)
_BRACKET_OR_PAREN = re.compile(r"\[[^\]]*\]|\([^)]*\)")
_LEGAL_FORM = re.compile(r"\bSDN\.?\s*BHD\.?\b|\bSDN\b|\bBHD\b")
_NON_ALNUM_UPPER = re.compile(r"[^A-Z0-9]+")

# `dym-annotate`'s `_PAGE_SATURATION`, retuned to the WINDOWED page (2026-08-25). Nothing
# in the envelope reports truncation, so a page that comes back AT the server's hard limit
# is the only available signal that rows were cut, and an attribution built on a truncated
# page is wrong in the one direction that matters. 1000 = the date-scoped cap the orders
# route itself enforces.
PAGE_SATURATION = 1000

# The probe's injected default window, mirrored here so the miss claim stays honest: on a
# defaulted probe the suffix says "no recent delivery", because "recent" bounds the claim
# to the window that was actually measured.
CUSTOMER_PROBE_WINDOW_DAYS = 90


def _norm(value: Any) -> str:
    """`s => String(s ?? '').trim().toLowerCase()`."""
    return jsc.nullish_str(value).strip().lower()


def _probe_rows(probe: Any) -> list[Any] | None:
    """`answers`, else `items`, else None. Neither being an array is the FAILURE signal.

    `sub-get-results` emits one of the two on every successful read, so "neither" can only
    mean the probe did not run or errored out - which `annotate_customer` renders as the
    bare picker rather than as an empty result set.
    """
    if isinstance(jsc.get(probe, "answers"), list):
        return probe["answers"]
    if isinstance(jsc.get(probe, "items"), list):
        return probe["items"]
    return None


def _annotate_lines(source: str, suffix_for) -> str:
    """Map the numbered lines through `suffix_for`; header lines pass through untouched."""
    out_lines = []
    for line in source.split("\n"):
        match = _NUMBERED_LINE.match(line)
        if not match:
            out_lines.append(line)  # header / non-item line
            continue
        out_lines.append(line + suffix_for(match.group(1)))
    return "\n".join(out_lines)


def annotate_incoming(gate: dict[str, Any] | None, *, probe: Any) -> dict[str, Any]:
    """`annotate-incoming-picker` - "- has incoming" / "- no incoming" per numbered line."""
    out = gate if isinstance(gate, dict) else {}
    probe = probe if jsc.truthy(probe) else {}

    # Codes WITH incoming from the probe's answers (`crm_incoming_stock_list` returns a row
    # per product that HAS incoming; title / "Product Code" field = the code). Absent = none.
    answers = _probe_rows(probe)
    if answers is None:
        answers = []
    has_incoming: set[str] = set()
    for a in answers:
        code = jsc.get(a, "title") if jsc.truthy(a) else a
        if not jsc.truthy(code) and jsc.truthy(a) and isinstance(jsc.get(a, "fields"), list):
            field = jsc.find(
                jsc.get(a, "fields"),
                lambda x: bool(_PRODUCT_CODE_LABEL.search(jsc.js_string(jsc.get(x, "label")))),
            )
            code = jsc.get(field, "value") if jsc.truthy(field) else field
        if jsc.truthy(code):
            has_incoming.add(_norm(code))

    clarification = jsc.get(out, "gate_clarification")
    source = jsc.js_string(clarification) if jsc.truthy(clarification) else ""
    annotated = _annotate_lines(
        source, lambda label: " - has incoming" if _norm(label) in has_incoming else " - no incoming"
    )
    message = annotated
    if len(has_incoming) == 0:
        message += "\n\nNone of these have incoming stock right now."
    out["escalate_message"] = message
    out["is_clarification"] = False  # parity with the not-found require_specific branch
    return out


def _customer_base(value: Any) -> str:
    """`base` - the same base-name rule the picker groups by, so an order row's
    "MASTILE KLANG SDN BHD [A/C I]" matches the "MASTILE KLANG SDN BHD" line it came from.
    """
    s = jsc.nullish_str(value).upper()
    s = _BRACKET_OR_PAREN.sub(" ", s)
    s = _LEGAL_FORM.sub(" ", s)
    s = _NON_ALNUM_UPPER.sub(" ", s)
    return s.strip()


def _customer_of_row(a: Any) -> Any:
    """`custOfRow` - the "Customer" field, else `customer_name`, else `customer`."""
    if not jsc.truthy(a):
        return None
    if isinstance(jsc.get(a, "fields"), list):
        field = jsc.find(
            jsc.get(a, "fields"),
            lambda x: bool(
                _CUSTOMER_LABEL.match(jsc.js_string(jsc.get(x, "label") or ""))
            ),
        )
        if jsc.truthy(field) and jsc.truthy(jsc.get(field, "value")):
            return jsc.js_string(jsc.get(field, "value"))
    return jsc.get(a, "customer_name") or jsc.get(a, "customer") or None


def annotate_customer(
    gate: dict[str, Any] | None, *, probe: Any, parser: dict[str, Any] | None
) -> dict[str, Any]:
    """`annotate-customer-picker` - which candidates have a matching delivery."""
    out = gate if isinstance(gate, dict) else {}
    probe = probe if jsc.truthy(probe) else {}
    parser = parser if isinstance(parser, dict) else {}

    # WHICH WINDOW WAS PROBED: the probe always sends a delivery-date window - the parser's
    # own bounds when the customer named one, else the injected 90-day default. This mirror
    # of "defaulted iff the parser supplied NEITHER bound" is what keeps the suffix wording
    # honest; change the probe's default without revisiting this and the claim loses its bound.
    probe_windowed = (
        jsc.get(parser, "date_filter_start") is None and jsc.get(parser, "date_filter_end") is None
    )

    out["is_clarification"] = False  # parity with the not-found require_specific branch
    out["customer_probe_window_days"] = CUSTOMER_PROBE_WINDOW_DAYS if probe_windowed else None

    # THE BARE PICKER: `not-found-error-message` renders a require_specific turn as
    # `escalate_message = gate.gate_clarification` verbatim, so this string IS today's live
    # output for this turn. Every arm that cannot honestly annotate returns exactly it.
    clarification = jsc.get(out, "gate_clarification")
    bare = jsc.js_string(clarification) if jsc.truthy(clarification) else ""

    # D2 - PROBE FAILED vs PROBE FOUND NOTHING. The probe carries
    # `onError: continueRegularOutput`, so a transient failure arrives as an ordinary item.
    # Without this arm the failure is indistinguishable from an empty answer set and every
    # line renders a confident "- no delivery" on evidence that was never gathered.
    rows = _probe_rows(probe)
    if rows is None:
        out["escalate_message"] = bare
        out["customer_probe_hits"] = None  # null = not measured
        out["customer_probe_skip_reason"] = "probe_unavailable"
        return out

    # F - PAGE SATURATION. A saturated page withholds the annotation and renders the bare
    # picker; it can NEVER invent one.
    if len(rows) >= PAGE_SATURATION:
        out["escalate_message"] = bare
        out["customer_probe_hits"] = None
        out["customer_probe_skip_reason"] = "page_saturated"
        return out

    with_delivery: set[str] = set()
    for row in rows:
        base = _customer_base(_customer_of_row(row))
        if base:
            with_delivery.add(base)

    # NO reordering, no renumbering - the numbers are the pick affordance. Suffixes only,
    # and a plain hyphen, never an em-dash.
    suffix_hit = " - has delivery"
    suffix_miss = " - no recent delivery" if probe_windowed else " - no delivery"
    annotated = _annotate_lines(
        bare,
        lambda label: suffix_hit if _customer_base(label) in with_delivery else suffix_miss,
    )
    message = annotated
    if len(with_delivery) == 0:
        message += (
            "\n\nNone of these have a recent delivery."
            if probe_windowed
            else "\n\nNone of these have a matching delivery."
        )
    out["escalate_message"] = message
    out["customer_probe_hits"] = len(with_delivery)
    out["customer_probe_skip_reason"] = None
    return out
