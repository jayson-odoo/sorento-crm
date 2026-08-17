# 8. PO intake lines edit per cell; quotation lines edit staged

Date: 2026-08-12
Status: accepted

## Context

The module carries two editable line tables, and they deliberately do not share an
editing paradigm:

- **Quotation lines** edit through the shared `InlineLineTable` in a STAGED session:
  nothing is written until the document's one Save, and Cancel discards everything.
- **PO intake lines** edit through a bespoke `CellInput`-inside-DataGrid: each cell
  commits on blur, one field at a time, against the stored row.

The 2026-08-12 audit flagged this as the module's most "out of place" feature - two
paradigms one screen apart - and asked for either convergence or a written reason.

## Decision

Keep both, because the two screens answer different questions.

A quotation is AUTHORED. The salesperson is composing an offer: adding lines, moving
sections, trying prices. Half-composed states are not facts about anything, so nothing
may persist until the whole edit is deliberately saved, and walking away must cost
nothing. That is exactly what the staged `InlineLineTable` session provides.

A PO intake line is RECONCILED. The row already exists - it is what the extractor read
off the customer's paper - and the person is correcting individual misreadings against
the scan pinned beside the grid: this qty, that code. Each correction is an independent
fact, true the moment it is typed, and losing forty of them because the tab closed
before a Save would mean re-reading forty cells against a ten-page scan. Cell-commit is
the honest model for that work. It is also why the grid is a DataGrid and not
`InlineLineTable`: rows are never added or reordered here (the paper decides the rows),
so the spreadsheet-entry affordances would offer edits the domain forbids.

The boundary is the `confirmed_at` stamp: after confirmation the version is immutable
and both paradigms collapse to the same read-only rendering.

## Consequences

- `CellInput` stays a private detail of `POIntakeLinesGrid`; nothing else may adopt it
  without revisiting this ADR. A third editing paradigm is the failure mode this
  document exists to prevent.
- Any future screen that AUTHORS lines uses `InlineLineTable`; any screen that CORRECTS
  extracted rows in place may use the cell-commit grid.
- The vocabulary convergence (terse headings, v1/v2 chips, one money renderer) shipped
  with the audit fixes; the paradigm difference is the one divergence that remains, and
  it is now a decision rather than an accident.
