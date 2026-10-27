# PLAN: hide the book S/O on a PO line AutoCount removed (27 Oct 2026)

Status: built, reviewer READY, awaiting CI and hand test (small fix track: no migration, no auth/RBAC change, no new ingest surface)

UAC: `hide-removed-line-so-27oct-acceptance-criteria.md`

## Ruling

Owner, 27 Oct: a PO line AutoCount REMOVED (the CRM keeps it as a Cancelled record because
something references it) must not show the S/O it used to link to, "cause autocount already
don't have this linkage". This narrows the 26 Oct AC-REMOVED-LINES Q5 ("no UI change") and
AC-RL-05 (`from_so_line_ref` kept) for DISPLAY only: the stored column stays as audit, the
screens stop printing it.

Real case: PO 202607-S0081, SRTSA-SS line qty 546. AutoCount PODTL 45713392 is gone, the PO is
not cancelled, and no current SRTSA-SS PO line points at SO396348 (AutoCount links PO lines to
SOs via PODTL.FromSODtlKey / FromSODocList). The CRM's S/O SO396348 on that line is a leftover.

## How the CRM tells a removed line apart (no new column)

A `purchase_order_lines` row reads `line_status = cancelled` from exactly three writers:

1. the header is cancelled (`document_ingest_service._line_status`, `deletion_service` ~602);
2. AutoCount Cancel PO documents cancelled all of it (`autocount_cancel_ingest_service` ~860,
   which also sets `cancelled_by_cancel_doc = True`);
3. the leftover sweep of a push that no longer carries the line (`document_ingest_service`
   ~1648-1682, #1878), on a header the push does not cancel.

So: removed = `line_status == cancelled` AND header status != `cancelled` AND NOT
`cancelled_by_cancel_doc`. One helper, `order_link_service.book_so_ref_of(line, header_status)`,
returns `None` for such a line and the stored ref otherwise; every reader that prints the book
S/O for a PO line passes its result to `book_so_fields` instead of the raw column. The rule also
covers lines removed before this change (prod data), which a new flag would not without a
backfill.

## Scope

Changed: every read that prints a PO line's book S/O (list in the PR body with file:line).
Untouched: the stored `from_so_line_ref`, the SPO column, "Received N" pills, claims/links
(already released by #1878), AutoCount-cancelled lines (header or cancel doc), which keep
their S/O and red label (LINKAGE-UNIFY Q5).

## Accepted edge cases (reviewer, 27 Oct)

- A removed line whose PO header is cancelled LATER reads as header-cancelled and shows its old
  S/O again. The rule reads the line's current state, not its history; a marker column would be
  needed to tell the two apart, and the case is rare.
- A line fully cancelled by Cancel PO documents and THEN removed keeps its S/O, consistent with
  the removed-line release, which also skips it (already cancelled).
- The sweep also cancels ref-less and duplicate-ref leftovers on an open header; those are hidden
  too, which matches the ruling (the book no longer names them either).
- The sales-order side "Received N" (`project_supply_service`, joins on `from_so_line_ref`) is
  unchanged on purpose: it is the AutoCount transfer and receipt record, out of scope here.

## Readers checked

Changed: `purchase_order_service.serialize` (PO detail and update), `order_inquiry_worklist_service
.get_po_detail` (order inquiry PO popup). Ruled out: PO list (`BOOK_SO_NOT_RESOLVED`), Stock Debt
book pins (open lines only), OI sheet import pairing (live lines only), claims and
`_exact_so_line_for` (claims on a removed line are deleted by `release_removed_lines`),
`_refs_named_by_book` (coarse pre-filter), `external/contract.py` (sends the stored ref back to the
ESB, must stay unfiltered), MCP (no S/O field), SPO allocations (out of scope).

Evidence: `evidence/hide-removed-line-so/` (Lines tab at 1600px and 375px, sandbox seed).
