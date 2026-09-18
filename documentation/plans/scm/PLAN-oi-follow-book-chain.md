# PLAN - Order inquiry rows follow the AutoCount book, through the PO to SPO chain

Status: DRAFT 18 Sep 2026. Awaiting owner grill on D1 to D4 below. No code written.
UAC: `oi-follow-book-chain-acceptance-criteria.md`. Branch `lane/oi-follow-book-chain`.
Domain: SCM, order inquiries. Owner ruling 18 Sep 2026: "doesn't matter it is closed or not,
if autocount has that linking, we must use and follow that."

## 1. Journey

Held in the UAC's `Journey` section. One actor (purchasing), zero decisions: the row already
shows the documents AutoCount names for it.

## 2. What was measured before writing this

The owner's case, SO421886 / C-FHSS14 / qty 2, read off prod on 18 Sep:

| Row | State in the CRM |
| --- | --- |
| SO line `...45810027:45810033` | held since 17 Sep 07:26 |
| PO 202607-S0110 line `...45391885:45820014` | arrived 18 Sep 04:42 UTC, names that SO line, ordered 2, received 2, closed |
| SPO-2026/09-0036 line `...45728035:45820113` | open, 2, names that PO line, SO ref empty, 0 claims |
| Order inquiry row | "Not linked", PO and SPO blank |

The feed is not at fault: the PO line reached the CRM within a minute of being saved.

**This already ships, and is merely not called for live rows.** The OI sheet importer pairs
exactly this way (`project_order_inquiry_import_service._pair`): the ref first, a purchase
order line followed through to the shipping order it became, the purchase order line itself
only for the remainder, nothing counted twice, cancelled lines refused, and closed or fully
delivered lines included (D8 of that plan). Its capacity is the document's whole quantity
less what links already hold, so "closed or not" is already how it reads. The owner's ruling
of 14 Sep ("the source of truth is the autocount linkage") built it. Live rows never reach it:

* The cascade (`auto_place_for_products`) reads claims and open balance only. A closed PO line
  has no open balance; a chain-only SPO line has no claim.
* `follow_book_repairing` (S5, 16 Sep) only MOVES an existing link when a ref changes. It
  returns early when the target has no link, and `ref_moves` captures updated PO lines only,
  never a created one and never an SPO line that names only a PO line.

So this is a repair plan: call the existing pairing for live rows. It is not a build plan.

Size of it on the 18 Sep 03:00 copy: 4,692 rows have need left; the book names a document for
191 of them. Of 157 chain targets, 152 are already held by another row of the same sales
order line (nothing to do), 19 by a different sales order line (D3), 2 are free. The daily
flow is the point, not the backlog: every sales order bought and transferred in one sitting
lands in this gap.

## 3. Decisions for the owner (each with a recommendation)

**D1. A real link, or a read-only "AutoCount says" display?** Recommend a REAL link, written
by the one link writer (`_write_link`), `auto = true`, trigger `autocount_ingest`, which is
what the sheet importer has written 6,000 times. A display-only fact would be a second
meaning in the same two columns, and the Buy card and stock debt would still count the row as
unbought.

**D2. Which document carries the link when the PO line became a shipping order?** Recommend
the shipping order line, with the PO shown beside it "via SPO" (the worklist already does
this). The PO line takes only what did not ship. This is the importer's rule and the owner's
14 Sep ruling on double counting.

**D3. The book names a document another sales order's row already holds (19 rows today).**
Recommend the book wins: the holder's link is removed with a note naming the document, the
sales order it went to and the date; the holder is offered to the cascade again; manual links
follow too (ruling 16 Sep). Never displaced: a row of the same sales order line, and a
redirected row holding a received document. The alternative, leaving the holder and the book
row unlinked, keeps the screen disagreeing with AutoCount, which is what the ruling forbids.

**D4. AC-RL-43 (16 Sep): a book MOVE skips a fully received document.** Today's ruling reads
as lifting it. Recommend lifting it for a closed PO line that still has an open shipping order
behind it (goods not landed, the owner's case), and KEEPING it where the goods have landed,
because moving a landed link rewrites what a row was told it bought a year ago
(`oi-replan-received-links` journey, step 4). First links to a landed document are still
written (AC-FB-3): that is history being recorded, not rewritten.

## 4. Design

One function, three callers, no new table, column, migration, permission or screen.

**4.1 The function.** `ProjectOrderInquiryService.follow_book_for_rows(row_ids, *, trigger,
company_id, actor_user_id)`:

1. Narrow `row_ids` to linkable rows with need left (`_linkable_row_for_core_line`'s
   predicate, `_unlinked_need`), resolve each to its core sales order line.
2. Hand `(need, core line)` pairs to the importer's pairing. `_pair` reads only
   `match.raisable`, `match.row.qty`, `match.core_line` and `plan.bought_rows`, so the seam is
   a small extraction: `pair_needs(db, needs)` holding today's body, with `_pair` building its
   `needs` from the plan and calling it. No behaviour change for the importer (AC-FB-12).
3. Write each take through `_write_link(..., auto_trigger="autocount_ingest")`, then
   `refresh_link_state` once for the rows touched.
4. D3: before step 3, when a book-named target has no free capacity, find the links holding
   it whose row is on a different core sales order line that the book does not name for that
   target, remove them through `_remove_links` with the note, and collect those rows for one
   cascade pass at the end.

**4.2 Callers.**

* Top of `auto_place_for_products`, for the rows that pass is about to deal. Every cascade
  trigger (Confirm, Link now, the board) therefore honours the book first and deals only the
  remainder (AC-FB-11, AC-FB-20).
* `ingest.py` `_run_supersede_and_relink_hooks`, after `follow_book_repairing`: the SO line
  refs named by PO lines written this push (created AND updated, AC-FB-25), resolved to rows.
* `ingest.py` beside `_run_shipping_order_forward_match_hook`: SPO lines written this push,
  their own SO ref or the SO ref of the PO line they name, resolved to rows.

Both hooks keep the existing shape: `begin_nested`, own commit, best-effort, capped, dropped
count on the response summary.

**4.3 Backfill.** `scripts/backfill_oi_follow_book.py`, `--dry-run` default, per company, keyset
pages of row ids, calls `follow_book_for_rows`. ORM only (raw SQL bypasses the company scope).

**4.4 Frontend.** None expected. The worklist already prints a shipping order link, its source
PO "via SPO", and the received figure. Phase 1 (frontend mock) is therefore not applicable,
and that is recorded in the PR description. Browser verification still runs (AC-FB-50).

## 5. What is deliberately not built

* No chain writer for `scm.order_link_claim` (my first proposal). Ruling 9 Sep: the refs are
  the truth; claims are many to many with no quantity. A real link makes the claim moot.
* No "book pairing" flag column on the link. The row note already carries the trigger.
* No reservation of a book-named document before its row exists. D3 corrects it when the row
  arrives. Trigger to revisit: displacement notes becoming a daily sight for purchasing.

## 6. Slices (one lane, one PR)

| Slice | Holds | ACs |
| --- | --- | --- |
| S1 | `pair_needs` extraction + `follow_book_for_rows` + the cascade caller | FB-1 to FB-12, FB-20 |
| S2 | the two ingest hooks, cap, created-line capture | FB-21 to FB-25 |
| S3 | displacement (after D3 is ruled) and AC-RL-43 (after D4) | FB-30 to FB-33 |
| S4 | backfill script, dry run on the 18 Sep copy | FB-40 to FB-42 |
| S5 | browser evidence run | FB-50, FB-51 |

## 7. Testing seams (agreed before Phase 2)

* Pytest on Postgres through `tests/_pg_fixture.py`, seeding its own company, product, sales
  order line with `source_ref`, PO line, SPO line, inquiry row. Reuse `_seed_so_line`,
  `_po_line`, `_spo_line` from `tests/test_ingest_documents_v5_so_po_links.py`.
* Service seam: `follow_book_for_rows` directly. Route seam: `POST /api/v1/external/ingest`
  for POs and SPOs, asserting the link exists after the call returns.
* Importer regression: its existing test files, unedited.
* Security review is in scope: external ingest surface and company scoping.
* One agent on the backend test database at a time.

## 8. Rollout

Deploy, run the backfill dry run on prod, read the displaced count with the owner, then
apply. Until the backfill runs, only rows touched by a new push or a cascade pass change.
