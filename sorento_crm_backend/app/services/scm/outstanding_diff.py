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

**A line can also close by being STATED settled.** The upload is the whole order book, so a
row may arrive with nothing left on it (`qty = 0`, see `states_settled`). Against an existing
line that reads `closed` - the same word absence earns, because it is the same event - and
against nothing at all it reads `added`, which is a completed document this database has
never seen. Both are what the file says; neither is a quantity that fell to zero.
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
# A line-identity pair (see `Line.line_id` below) whose product differs and whose after side
# has not settled - `documentation/plans/scm/PLAN-scm-change-management-one-engine.md`,
# Slice A rule 5: a product swap on the SAME line reads as one row, not a `CLOSED` plus an
# unrelated `ADDED`. `CLOSED` keeps its value here - only the wire row kind is renamed
# (`app/services/planning_change_service._map_kind`).
PRODUCT_CHANGED = "product_changed"

# A quantity difference below this is treated as no change. Extracts round differently
# between exports and a 0.0001 drift is noise, not a decision.
_QTY_EPSILON = 0.0005


@dataclass(frozen=True)
class Line:
    """One outstanding order line, from either side of the comparison.

    `key_extra` exists so callers can carry the DB row id through the diff without this
    module knowing anything about the database.

    `line_id` is a caller-supplied identity - a MATCHED before/after pair on this field
    pairs FIRST, ahead of the `(doc, item, location)` + date-order fallback below, so a
    product swap on the same line reads as one `PRODUCT_CHANGED` change rather than a
    `CLOSED` plus an unrelated `ADDED` (Slice A rule 5). `None` (the default) opts a line
    entirely out of identity pairing - it is matched only by the fallback, exactly as
    before this field existed; a manual SO edit, which always knows the core line id, sets
    it, while an uploaded extract (no line number in the file, see the module docstring)
    leaves it unset.
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
    line_id: Optional[str] = None

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
                              CLOSED, UNCHANGED, PRODUCT_CHANGED)}
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


def states_settled(line: Line) -> bool:
    """Whether this INCOMING line says there is nothing left on it.

    The upload is the whole order book, so a line can arrive already finished: the reader
    carries such a row with `qty = 0` and its ordered / delivered figures in `extras`. A
    settled line is not a quantity that fell to nothing - it is the line leaving the book -
    so it classifies as `closed`, the same word the far commoner case (a line simply absent
    from the next upload) already earns. One vocabulary for one event.

    Public because the write path asks the same question, and two answers that merely agree
    today would eventually disagree about which lines to close.
    """
    return line.qty <= _QTY_EPSILON


def _classify(before: Line, after: Line) -> str:
    # The file states this line settled, so it closes. Ahead of the date and quantity
    # comparison because it outranks both: a line that has left the book has not "changed
    # quantity to zero", and calling it `qty_changed` would leave it open on a plan.
    if states_settled(after):
        return CLOSED
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


def _classify_identity(before: Line, after: Line) -> str:
    """Same as `_classify`, plus the product itself - for a pair matched by `line_id`.

    Settlement still outranks everything, including a product swap: a line that arrives
    stating nothing left on it has closed, whatever else also changed on the same row
    (`test_a_line_id_pair_settling_to_zero_closes_even_with_a_different_item_code`).
    """
    if states_settled(after):
        return CLOSED
    if before.item_code != after.item_code:
        return PRODUCT_CHANGED
    return _classify(before, after)


def _change_for_pair(before: Optional[Line], after: Optional[Line], kind: str) -> Change:
    # The NEW product/location/document name the change, when there is an after side - a
    # product swap must read as "changed to B", not "still A" (Slice A rule 5's "row
    # item_code/product_name = the new product", mirrored in
    # `planning_change_service._build_row`).
    ref = after or before
    return Change(kind, ref.doc_number, ref.item_code, ref.location, before=before, after=after)


def diff_lines(
    existing: Iterable[Line],
    incoming: Iterable[Line],
    *,
    scope_documents: Optional[Iterable[str]] = None,
) -> Diff:
    """Compare current state against an uploaded extract.

    Only documents present in `incoming` are in scope. Existing lines belonging to any other
    document are ignored entirely rather than being reported as closed.

    `scope_documents`, when given, REPLACES that derivation rather than adding to it - a
    manual SO edit removing every line off one order leaves `incoming` with nothing at all
    for that document, and deriving scope from `incoming` alone would then read the whole
    order as out of scope (untouched) rather than wholly closed. A caller that already knows
    its scope (one order, being edited) states it directly; a caller comparing an extract
    against everything it might mention (the book upload, AutoCount ingest) leaves this
    unset and keeps today's derived behaviour.

    **Pass 0, identity.** A `line_id`-carrying existing line and a `line_id`-carrying
    incoming line sharing the SAME id pair first, classified by `_classify_identity` (which
    reads a product swap as `PRODUCT_CHANGED`) - ahead of, and instead of, the
    `(doc, item, location)` + date-order matching below. A line carrying a `line_id` that
    finds no partner by that id is claimed by this pass too - it closes or adds directly,
    and never enters the fallback grouping, so two DIFFERENTLY-identified lines that merely
    happen to share item/location/date/qty are never zipped into one false "unchanged" pair
    (`test_a_line_id_pair_with_no_match_on_either_side_closes_the_old_and_adds_the_new`).
    Only lines with NO `line_id` (`None`, the default) reach the fallback, unaffected by any
    of this - the identical algorithm this module always ran.
    """
    incoming_list = list(incoming)
    scope = (
        set(scope_documents) if scope_documents is not None
        else {l.doc_number for l in incoming_list}
    )

    existing_in_scope = [l for l in existing if l.doc_number in scope]

    changes: list[Change] = []

    existing_by_lid = {l.line_id: l for l in existing_in_scope if l.line_id}
    incoming_by_lid = {l.line_id: l for l in incoming_list if l.line_id}
    matched_lids = set(existing_by_lid) & set(incoming_by_lid)

    for lid in sorted(matched_lids):
        o, n = existing_by_lid[lid], incoming_by_lid[lid]
        changes.append(_change_for_pair(o, n, _classify_identity(o, n)))

    for lid, o in existing_by_lid.items():
        if lid not in matched_lids:
            changes.append(_change_for_pair(o, None, CLOSED))
    for lid, n in incoming_by_lid.items():
        if lid not in matched_lids:
            changes.append(_change_for_pair(None, n, ADDED))

    fallback_existing = [l for l in existing_in_scope if not l.line_id]
    fallback_incoming = [l for l in incoming_list if not l.line_id]

    by_group_existing: dict[tuple, list[Line]] = {}
    for l in fallback_existing:
        by_group_existing.setdefault(l.group, []).append(l)

    by_group_incoming: dict[tuple, list[Line]] = {}
    for l in fallback_incoming:
        by_group_incoming.setdefault(l.group, []).append(l)

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
