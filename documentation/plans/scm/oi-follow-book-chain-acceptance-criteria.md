# UAC - Order inquiry rows follow the AutoCount book, through the PO to SPO chain, closed or not

Plan: `PLAN-oi-follow-book-chain.md`. Status: DRAFT 18 Sep 2026, awaiting owner grill (decisions D1 to D4 in the plan).

Owner ruling, 18 Sep 2026: "doesn't matter it is closed or not, if autocount has that
linking, we must use and follow that."

## Journey

**Actor:** purchasing, on Supply Chain, Order Inquiries. Nobody else acts.

**Where they arrive from:** CS keyed SO421886 in AutoCount on 17 Sep. On 18 Sep at 12:41 a
buyer in AutoCount added 2 x C-FHSS14 to purchase order 202607-S0110 against that sales order
line and transferred it to shipping order SPO-2026/09-0036 in the same sitting. The feed
pushed both within a minute. Purchasing opens Order Inquiries and searches SO421886.

**What the system already knows:** the purchase order line names the exact sales order line
(`from_so_line_ref`). The shipping order line names the exact purchase order line
(`from_po_line_ref`) and no sales order line of its own. So the book states the whole chain,
SO line to PO line to SPO line, in two columns the CRM already stores.

**Steps and the single decision each:**

1. Purchasing reads the row. It shows SPO-2026/09-0036 in the SPO column and 202607-S0110 in
   the PO column marked "via SPO", the supplier and the expected date of that shipping order.
   Decision: none. The pairing came from the book, so there is nothing to pick.
2. If the row is still "To confirm", purchasing confirms it as they do today. The link is a
   draft until then, exactly like a cascade link.
3. When the buyer later moves that purchase order line to another sales order in AutoCount,
   the link follows on the next push (already shipped, `PLAN-oi-replan-received-links.md` S5).

**What they hold at the end:** a row whose documents are the ones AutoCount names, whether
those documents are open, closed or received, with no manual linking.

**What every other stakeholder is told automatically:** a row that loses a document because
the book names it for another sales order carries a note saying which document went where and
on what date. Nobody is emailed.

**Decisions removed:** "which document is this row on" is never asked when the book answers it.

## Measured, 18 Sep 2026 03:00 prod copy plus the live rows the owner read off prod

* SO421886 line C-FHSS14, `source_ref AED_SORENTO:45810027:45810033`, qty 2, row unlinked.
* PO line `AED_SORENTO:45391885:45820014`: names that SO line, ordered 2, received 2, closed.
* SPO line `AED_SORENTO:45728035:45820113`: open, 2, names that PO line, no SO ref, 0 claims.
* 53,011 of 77,147 shipping order lines name a PO line and no SO line; 22,245 of those reach
  a sales order line only through the PO line (12 Sep copy).
* 4,692 rows are raised or partly linked with need left. The book names a PO line for 191 of
  them, a shipping order directly for 1, and a shipping order through the chain for 147.
* Of 157 chain targets, 2 are free. The other 155 are fully held by automatic links: 152 by
  another row of the SAME sales order line (no conflict, the line already holds its
  document), 19 by a DIFFERENT sales order line (the conflict D3 decides).

## Group A - the pairing rule (one rule, shared with the OI sheet importer)

Every AC is seeded on `tests/_pg_fixture.py` with its own chain. `[BE][T]` unless marked.

* **AC-FB-1 (the owner's case)** Given a linkable row with need 2 on SO line L, a PO line that
  names L and is closed with ordered 2 received 2, and a visible SPO line of 2 naming that PO
  line with no SO ref, when book pairing runs for the row, then one link of 2 is written on the
  SPO line, `auto = true`, trigger `autocount_ingest`, the row's link state is refreshed, and no
  link is written on the PO line.
* **AC-FB-2** Given the same row and an SPO line that names L directly, then the link lands on
  that SPO line.
* **AC-FB-3 (closed or not)** Given a PO line that names L, closed and fully received, with no
  shipping order behind it, then the row is linked to that PO line for min(need, ordered less
  what other links hold). The link serializes `received = true` with its received quantity.
* **AC-FB-4** Given the PO line is cancelled, or the SPO line is retired (not visible), then
  nothing is linked and the row is untouched.
* **AC-FB-5 (no double count)** Given a PO line of 10 naming L of which an SPO line of 6 names
  that PO line, and a row needing 10, then 6 land on the SPO line and 4 on the PO line.
* **AC-FB-6 (same line already holds it)** Given another row of the SAME sales order line
  already holds the whole document, including a redirected row holding a received document,
  then the new row takes nothing and nothing is displaced. This keeps step 4 of the
  `oi-replan-received-links` journey true.
* **AC-FB-7** Given a ref that matches more than one sales order line (the August ordinals),
  then it is refused and nothing is linked.
* **AC-FB-8** Given a document naming L but carrying a different product, then it is ignored.
* **AC-FB-9 [SEC]** Given the ref resolves only to another company's sales order line, then
  nothing is linked for the pushing company.
* **AC-FB-10** Given the row is not linkable by the cascade's own predicate (state, verb, ack),
  then it is untouched.
* **AC-FB-11** Given the book covers only part of the need, then the rest is left for the
  cascade, which runs after and sees only the remainder.
* **AC-FB-12 (importer unchanged)** Every existing test of
  `project_order_inquiry_import_service` stays green with no edit.

## Group B - when it runs

* **AC-FB-20 (documents first)** Given the PO and SPO were pushed before the row exists, when
  the row is raised, then book pairing runs before the raise-time cascade in the same
  transaction.
* **AC-FB-21 (row first, PO push)** Given the row exists and a PO push creates or updates a
  line naming L, then the row is linked inside that ingest call's post-write hook. A failure in
  the hook is logged and never fails the ingest.
* **AC-FB-22 (row first, SPO push)** Given the row exists and an SPO push writes a line that
  names only a PO line, and that PO line names L, then the row is linked by the hook.
* **AC-FB-23 (idempotent)** Given the same payload is pushed twice, then no second link, no
  second note and no changed timestamps on the row.
* **AC-FB-24 [SEC]** Given one push touches more rows than the cap (same figure as
  `FOLLOW_BOOK_REPAIRING_MAX_MOVES`), then the rest are skipped, logged, and counted on the
  ingest response summary.
* **AC-FB-25** A newly CREATED PO line (not only an updated one) triggers the hook. Today
  `ref_moves` captures updates only.

## Group C - the document is held by a different sales order line (decision D3)

* **AC-FB-30** Given the book names document X for L, and X is fully held by an AUTOMATIC link
  of a row on a different sales order line the book does not name for X, then that link is
  removed with the note `AutoCount states <X> is for <SO of L>, <date>`, the holder's link state
  is refreshed, the row of L is linked, and the holder is offered to the cascade again.
* **AC-FB-31** Given the holder's link is MANUAL, then the same happens (ruling 16 Sep:
  "manual links follow too"). Owner to confirm in the grill.
* **AC-FB-32** Given the holder is on a fully received document and its row is redirected, then
  it is never displaced (history).
* **AC-FB-33** Given the book ALSO names X for the holder's own line (two PO lines, one
  shipping order line each), then nothing is displaced: each row gets its own line.

## Group D - existing rows

* **AC-FB-40** `scripts/backfill_oi_follow_book.py --dry-run` prints, per company: rows named by
  the book, rows that would link, quantity, rows that would be displaced. It writes nothing.
* **AC-FB-41** `--apply` writes exactly what the dry run printed, pages by keyset, commits per
  page, goes through the ORM, and a second run writes nothing.
* **AC-FB-42** On the 18 Sep copy the dry run reports 191 rows named by the book, and the
  SO421886 C-FHSS14 row links to SPO-2026/09-0036 once the 18 Sep 12:41 documents are present.

## Group E - what purchasing sees

* **AC-FB-50 [E2E]** Order Inquiries, reached by sidebar clicks, search SO421886: the C-FHSS14
  row shows SPO-2026/09-0036, PO 202607-S0110 marked "via SPO", supplier XIAMEN TAIYANG
  TECHNOLOGY CO.,LTD. No clipping at 375px and 1280px. No console errors.
* **AC-FB-51 [FE]** No frontend file changes. If the run shows one is needed, it is raised as a
  finding, not absorbed.

## Out of scope

* No writer of `scm.order_link_claim` for the chain. Ruling 9 Sep 2026: the refs are the truth,
  the claim table is many to many and carries no quantity.
* No new column, no migration, no new screen, no new permission.
