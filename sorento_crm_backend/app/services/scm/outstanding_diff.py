"""What an uploaded outstanding-orders extract CHANGES. Pure, no database, no Excel.

The AutoCount extract carries no line number (see
`documentation/plans/scm/scm-autocount-extract-spec.md`), so a line cannot be identified by
id across weekly uploads. It has to be identified by content - and content alone is not
enough either, because one sales order routinely carries the SAME item at two different
delivery dates. The real Tuju Residence extract has SRTWC8613-RL twice on SO397450, 135 due
1 Jul and 72 due 3 Aug.

That rules out the two obvious identities:

* `(doc, item, location)` alone collapses those two lines into one and loses a date.
* `(doc, item, location, date)` keeps them apart but makes a moved date look like one line
  closed and a different line added - which destroys the entire point of the feature,
  because "the project moved, so the delivery dates shifted" is the single most common
  change this module exists to react to.

So matching happens in two passes within each `(doc, item, location)` group:

1. **Exact date matches pair first.** A line whose date did not move is never mistaken for
   one that did.
2. **Whatever is left pairs in date order.** Leftover existing lines sorted by date against
   leftover incoming lines sorted by date, zipped. Surplus incoming is `added`, surplus
   existing is `closed`.

Pass 2 is a rule a person can check by eye: "you had lines due 1 Jul and 3 Aug, you now have
15 Jul and 3 Aug, so the 1 Jul line moved to 15 Jul." It is deterministic and independent of
row order in the file. It is also, deliberately, only a claim about which line moved - never
about what to do next. ADR-0012 governs that: the diff finds the exception, the item decides
the recommendation.

**Scope is derived from the file, never asked.** The documents named in the extract ARE the
scope. A line missing from the file for a document that IS in the file has been delivered or
cancelled, so it closes. A document not in the file at all is untouched, because a
single-project export must not read as every other project having been delivered.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

# Change kinds. `unchanged` is carried rather than dropped so the preview can say "412 lines
# unchanged" - a diff that shows only changes cannot be distinguished from a diff that
# silently failed to read most of the file.
ADDED = "added"
QTY_CHANGED = "qty_changed"
DATE_MOVED = "date_moved"
DATE_AND_QTY_CHANGED = "date_and_qty_changed"
CLOSED = "closed"
UNCHANGED = "unchanged"

# A quantity difference below this is treated as no change. Extracts round differently
# between exports and a 0.0001 drift is noise, not a decision.
_QTY_EPSILON = 0.0005


@dataclass(frozen=True)
class Line:
    """One outstanding order line, from either side of the comparison.

    `key_extra` exists so callers can carry the DB row id through the diff without this
    module knowing anything about the database.
    """

    doc_number: str
    item_code: str
    location: str
    qty: float
    required_date: Optional[date] = None
    row_ref: Optional[str] = None          # source row number, or DB line id
    label: str = ""                        # customer / supplier, for display only
    # True when `required_date` is None NOT because the file left the cell blank, but
    # because the reader could not parse whatever was in it (`outstanding_reader`'s
    # "could not read the date" problem). A blank cell states nothing and a moved-to-None
    # date is real; an unreadable one states nothing USABLE, and must not be classified or
    # written as a move - see `_classify` and `outstanding_import_service._write_date`.
    date_unreadable: bool = False

    @property
    def group(self) -> tuple[str, str, str]:
        return (self.doc_number, self.item_code, self.location)


@dataclass(frozen=True)
class Change:
    kind: str
    doc_number: str
    item_code: str
    location: str
    before: Optional[Line]
    after: Optional[Line]

    @property
    def qty_delta(self) -> float:
        a = self.after.qty if self.after else 0.0
        b = self.before.qty if self.before else 0.0
        return a - b

    @property
    def days_moved(self) -> Optional[int]:
        if not (self.before and self.after):
            return None
        if self.before.required_date is None or self.after.required_date is None:
            return None
        return (self.after.required_date - self.before.required_date).days


@dataclass
class Diff:
    """Everything the confirm screen needs, and nothing it does not."""

    scope_documents: tuple[str, ...] = ()
    changes: list[Change] = field(default_factory=list)

    def of_kind(self, *kinds: str) -> list[Change]:
        return [c for c in self.changes if c.kind in kinds]

    @property
    def counts(self) -> dict[str, int]:
        out = {k: 0 for k in (ADDED, QTY_CHANGED, DATE_MOVED, DATE_AND_QTY_CHANGED,
                              CLOSED, UNCHANGED)}
        for c in self.changes:
            out[c.kind] = out.get(c.kind, 0) + 1
        return out

    @property
    def has_material_change(self) -> bool:
        """Whether anything at all would change. Drives "nothing to confirm" on the screen."""
        return any(c.kind != UNCHANGED for c in self.changes)


def _sort_key(line: Line) -> tuple:
    # `None` dates sort last, deterministically, without comparing None to a date.
    return (line.required_date is None, line.required_date or date.min, line.qty,
            line.row_ref or "")


def _classify(before: Line, after: Line) -> str:
    # An unreadable incoming date states nothing usable about the date, so it is never a
    # move - the line's date is read as whatever it already was (`_write_date` writes it
    # that way too). Only the quantity can still change on such a row.
    date_moved = (not after.date_unreadable) and before.required_date != after.required_date
    qty_changed = abs(after.qty - before.qty) > _QTY_EPSILON
    if date_moved and qty_changed:
        return DATE_AND_QTY_CHANGED
    if date_moved:
        return DATE_MOVED
    if qty_changed:
        return QTY_CHANGED
    return UNCHANGED


def diff_lines(existing: Iterable[Line], incoming: Iterable[Line]) -> Diff:
    """Compare current state against an uploaded extract.

    Only documents present in `incoming` are in scope. Existing lines belonging to any other
    document are ignored entirely rather than being reported as closed.
    """
    incoming_list = list(incoming)
    scope = {l.doc_number for l in incoming_list}

    by_group_existing: dict[tuple, list[Line]] = {}
    for l in existing:
        if l.doc_number not in scope:
            continue          # out of scope: absence here means nothing at all
        by_group_existing.setdefault(l.group, []).append(l)

    by_group_incoming: dict[tuple, list[Line]] = {}
    for l in incoming_list:
        by_group_incoming.setdefault(l.group, []).append(l)

    changes: list[Change] = []

    for group in sorted(set(by_group_existing) | set(by_group_incoming)):
        olds = sorted(by_group_existing.get(group, []), key=_sort_key)
        news = sorted(by_group_incoming.get(group, []), key=_sort_key)
        doc, item, loc = group

        # --- pass 1: identical dates pair first, so a line that did not move is never
        # mistaken for one that did.
        remaining_old: list[Line] = []
        news_by_date: dict[Optional[date], list[Line]] = {}
        for n in news:
            news_by_date.setdefault(n.required_date, []).append(n)
        for o in olds:
            bucket = news_by_date.get(o.required_date)
            if bucket:
                n = bucket.pop(0)
                changes.append(Change(_classify(o, n), doc, item, loc, before=o, after=n))
            else:
                remaining_old.append(o)
        remaining_new = [n for bucket in news_by_date.values() for n in bucket]

        # --- pass 2: whatever is left pairs in date order. Re-sorted because the leftovers
        # came out of a dict and their order must not depend on iteration order.
        remaining_old.sort(key=_sort_key)
        remaining_new.sort(key=_sort_key)
        for o, n in zip(remaining_old, remaining_new):
            changes.append(Change(_classify(o, n), doc, item, loc, before=o, after=n))

        for o in remaining_old[len(remaining_new):]:
            changes.append(Change(CLOSED, doc, item, loc, before=o, after=None))
        for n in remaining_new[len(remaining_old):]:
            changes.append(Change(ADDED, doc, item, loc, before=None, after=n))

    return Diff(scope_documents=tuple(sorted(scope)), changes=changes)
