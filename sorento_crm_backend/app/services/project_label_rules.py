"""The project label on a sales order - PLAN-so-project-label.md.

Sales orders carry no project column of their own. The name a project goes by is scattered
across three free-text places today: the Order Inquiry sheet's `PROJECT/CUSTOMER` cell, the
AutoCount SO note, and the AutoCount `Ref`. This module holds every rule that turns one of
those three into `sales_orders.project_label` - nothing here reads or writes the database
directly, so a test exercises each rule as a pure function.

Precedence, highest wins: `inquiry` 4 > `note` 3 > `ref` 2 > `delivery` 1 (`SOURCE_RANK`). A
writer only overwrites a stored label when its rank is >= the stored one - equal rank
overwrites, so a corrected sheet or note lands - and nothing ever CLEARS a label. A manual
edit (rank 5) is a later slice, not built here.
"""
from __future__ import annotations

import re
from typing import Optional

#: Highest wins. `apply_project_label` refuses to overwrite a stored label with one from a
#: lower-ranked source; equal rank overwrites, so a re-run of the same source lands a
#: correction.
SOURCE_RANK: dict[str, int] = {
    "inquiry": 4,
    "note": 3,
    "ref": 2,
    "delivery": 1,
}


def label_from_inquiry_cell(cell: Optional[str]) -> Optional[str]:
    """The Order Inquiry sheet's `PROJECT/CUSTOMER` cell, project half only.

    The owner's call: the customer is the part before the FIRST `/`, the project is
    everything after it. `URC ENGINEERING / BAMBOO RESIDENCE / KUALA LUMPUR` names a
    customer (URC ENGINEERING) and a project with its own slash in it (BAMBOO RESIDENCE /
    KUALA LUMPUR) - splitting on the LAST slash would cut that project in two. No slash at
    all means the cell is a customer name only, so there is no project to read off it.
    """
    if not cell:
        return None
    if "/" not in cell:
        return None
    _customer, remainder = cell.split("/", 1)
    # Every remaining slash normalised to one space either side, then whitespace collapsed -
    # "EKOTITIWANGSA/KL" and "EKOTITIWANGSA / KL" are the same project typed two ways.
    remainder = re.sub(r"\s*/\s*", " / ", remainder)
    remainder = " ".join(remainder.split())
    return remainder or None


#: A PROJECT/PROJ line, optionally qualified `CODE`/`TITLE` (`PROJECT CODE:`,
#: `PROJECT TITLE:`), separated by `:` or `;`. Leading punctuation (`***`, `**`) is
#: consumed by `\W*` rather than stripped first, so the match still anchors to the start
#: of the line.
_PROJECT_LINE_RE = re.compile(
    r"^\W*(?:PROJECT|PROJ)(?:\s*(CODE|TITLE))?\s*[:;]\s*(.+)$",
    re.IGNORECASE,
)

#: A delivery-address block header: `DELIVERY ADDRESS`, `DELIVERY TO ADDRESS`,
#: `DELIVER TO`, bare `DELIVERY`, or `SITE` - the HEADER KEYWORD only, anchored, with no
#: trailing `\s*` runs competing against each other (security review, SPL-B1: the old
#: pattern's two adjacent `\s*` groups took 48s to reject a 100KB run of spaces after
#: `DELIVERY`). What follows the header - a colon-led value, or nothing - is read in
#: PYTHON, not the regex; see the loop below. The dead bare-`DELIVERY` alternative is
#: gone too, since `DELIVERY(\s+TO)?(\s+ADDRESS)?` already matches bare `DELIVERY`.
_DELIVERY_LINE_RE = re.compile(
    r"^\W*(DELIVERY(\s+TO)?(\s+ADDRESS)?|DELIVER\s+TO|SITE)\b",
    re.IGNORECASE,
)

#: A unit/lot number leading a delivery site line - `A-25-07`, `B-43-08`, `12-09`,
#: `P-40-1`, `A1-13-09` - stripped so the label is the development's name, not its unit.
_UNIT_TOKEN_RE = re.compile(r"^[A-Za-z]?-?\d{1,3}(?:-\d{1,3}){1,2}-?[A-Za-z]?,?\s+")

#: A value that is NOTHING but a date (`27/08/2026`, `27-08`, `27.08.2026`) - `DELIVERY:
#: 27/08/2026` names when the goods arrive, not where, and a bare date is never a project
#: (security review, SPL-S3).
_DATE_ONLY_RE = re.compile(r"^\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?$")

#: The longest line `label_from_note` will run a regex over, and the most lines it will
#: look at (security review, SPL-B1). `internal_note` is capped to 8000 characters at the
#: contract edge (`CanonicalSalesOrder`), but this function is also called directly by the
#: Order Inquiry importer's own notes and migration 511's backfill over whatever a
#: pre-existing row already holds - neither of which carries that cap, so the guard
#: belongs here too.
_MAX_NOTE_LINES = 200
_MAX_LINE_LENGTH = 300


def _clean_delivery_value(raw: str) -> Optional[str]:
    value = _UNIT_TOKEN_RE.sub("", raw.strip())
    value = value.rstrip(", ").strip()
    if not value or _DATE_ONLY_RE.match(value):
        return None
    return value


def label_from_note(plain_text: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """The AutoCount SO note, read for a project name.

    1. A `PROJECT`/`PROJ` line, case-insensitive. A bare name line or a `PROJECT TITLE`
       line beats a `PROJECT CODE` line when both exist in the same note - a code alone
       (`PROJECT CODE: 50-02`) is the label only when nothing else names the project.
       Source `note`.
    2. Else a delivery block: `DELIVERY ADDRESS`, `DELIVERY TO`, `DELIVER TO`, `SITE`. The
       value is the text after the colon when there is one, else the next non-empty line,
       with a leading unit token (`A-25-07`) stripped. Source `delivery`.
    3. Else `(None, None)` - `OWN COLLECT`, a delivery DATE, a contact line, none of these
       name a project.
    """
    if not plain_text:
        return (None, None)
    lines = plain_text.splitlines()[:_MAX_NOTE_LINES]

    best: Optional[tuple[int, str]] = None
    for line in lines:
        if len(line) > _MAX_LINE_LENGTH:
            continue
        match = _PROJECT_LINE_RE.match(line)
        if not match:
            continue
        modifier = (match.group(1) or "").upper()
        # Plain `.rstrip` on a fixed, tiny set of characters - linear in the value's own
        # length, not the regex substitution this replaced (security review, SPL-B1).
        # `*` included: `*** PROJECT : PINE LEGACY ***` closes the same way it opens.
        value = match.group(2).strip().rstrip(" \t.,;:-*")
        if not value:
            continue
        # A code alone is the label only when nothing better is on offer - a bare name
        # line or a TITLE line always outranks it.
        priority = 0 if modifier == "CODE" else 1
        if best is None or priority > best[0]:
            best = (priority, value)
    if best is not None:
        return (best[1], "note")

    for index, line in enumerate(lines):
        if len(line) > _MAX_LINE_LENGTH:
            continue
        match = _DELIVERY_LINE_RE.match(line)
        if not match:
            continue
        # The header regex only ever matches the KEYWORD - what follows (a colon-led
        # value, or nothing) is read here, not by the regex, so there is nothing left
        # for two `\s*` runs to compete over.
        remainder = line[match.end() :].lstrip()
        inline_value = remainder[1:].strip() if remainder.startswith(":") else ""
        if inline_value:
            cleaned = _clean_delivery_value(inline_value)
            if cleaned:
                return (cleaned, "delivery")
            continue
        for next_line in lines[index + 1 :]:
            if len(next_line) > _MAX_LINE_LENGTH:
                continue
            if next_line.strip():
                cleaned = _clean_delivery_value(next_line)
                if cleaned:
                    return (cleaned, "delivery")
                break

    return (None, None)


#: An agent's own stamp on the order, not a project - `JF- 9/9 3.50`, `JH-21/08/2026 11.32
#: AM`: initials, a dash, and a date. The broader `^[A-Z]{2,8}-\d` this used to also carry
#: killed real project names of the same shape (security review: `MRT-2 DEPOT`) - the
#: date-bearing pattern alone is what actually distinguishes a stamp from a name.
_AGENT_STAMP_RE = re.compile(
    r"^[A-Z]{2,8}\s*-\s*\d{1,2}/\d{1,2}",
    re.IGNORECASE,
)

#: `Ref` values that name a sale type rather than a project.
_NON_PROJECT_REFS = {"RETAIL", "END USER", "REPLACEMENT", "REPLACEMENT ORDER"}


def label_from_ref(ref: Optional[str]) -> Optional[str]:
    """AutoCount `SO.Ref`, read for a project name.

    None for blank, for an agent's own stamp (`JF- 9/9 3.50`), and for a sale-type word
    (`RETAIL`, `END USER`, `REPLACEMENT`, `REPLACEMENT ORDER`) - everything else is the
    trimmed text (`THE MET KL`, `KSL BLOSSOM 733U @ SETIA ALAM`).
    """
    if not ref:
        return None
    trimmed = ref.strip()
    if not trimmed:
        return None
    if _AGENT_STAMP_RE.match(trimmed):
        return None
    if trimmed.upper() in _NON_PROJECT_REFS:
        return None
    return trimmed


#: The longest label ever written, and the single place that bound is enforced (security
#: review, SPL-S2) - `apply_project_label` is the one choke point every writer (the
#: AutoCount ingest, the Order Inquiry importer, migration 511's backfill) already goes
#: through, so capping here bounds all three without a truncation of its own in each.
_MAX_LABEL_LENGTH = 200


def apply_project_label(order, label: Optional[str], source: Optional[str]) -> bool:
    """Writes `project_label`/`project_label_source` on `order` under the precedence gate.

    Never writes a `None` label. Writes when the order has none yet, or when the new
    source's rank is >= the stored one; otherwise leaves the order - label, source AND
    `updated_at` - untouched, so a lower-ranked re-push cannot even trip the ORM's `onupdate`.
    Returns whether it wrote.
    """
    if not label or not source:
        return False
    label = label.strip()[:_MAX_LABEL_LENGTH] or None
    if not label:
        return False
    new_rank = SOURCE_RANK.get(source, 0)
    if order.project_label:
        current_rank = SOURCE_RANK.get(order.project_label_source, 0)
        if new_rank < current_rank:
            return False
    order.project_label = label
    order.project_label_source = source
    return True
