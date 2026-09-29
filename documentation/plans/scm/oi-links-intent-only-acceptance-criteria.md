# UAC: the planning side never changes an Order Inquiry document link, it records intent

Plan: `PLAN-oi-links-intent-only.md`. Lane REDEAL-CLOSED-PO follow-up. Owner ruling
29 Sep 2026: "shrinking a line shouldn't trim its own PO link ... a cancelled line
shouldn't directly hand its PO link to its sibling, new buy shouldn't get draft PO links
also, the PO link is based on autocount linkage as source of truth".

Vocabulary: a DOCUMENT LINK is an `order_inquiry_links` row with `po_line_id` or
`spo_allocation_id`; a PLANNING ACTION is a fulfilment board Confirm or a planning-change
Apply; the NOTICE is a sentence on the batch row's `result_json["released_documents"]`.

Supersedes AC-P3-6 and AC-P3-8 (`scm-cs-planning-uat-acceptance-criteria.md`), AC-RL-11's
open-link release (`oi-replan-received-links-acceptance-criteria.md`) and D7's SPO unlink
(`scm-change-management-one-engine-acceptance-criteria.md`).

- AC-IO-1 [BE][T] (was AC-P3-8) Given a placed row of 234 linked 134 on a PO line, when the
  book drops the line to 100 and the batch is applied, then the row reads qty 100 and
  state `placed`, its link still reads 134, the PO line's linked total is unchanged, and
  the row's note names the over-linked quantity as purchasing's to adjust in AutoCount.
- AC-IO-2 [BE][T] Given a placed row whose whole need is met from stock at apply (the
  SO397450 advance shape, 432 on two POs), when the batch is applied, then the row is
  cancelled AND keeps both links, the PO lines stay claimed by that row, no pool row is
  written, and the batch row records one notice per PO.
- AC-IO-3 [BE][T] (was AC-P3-6) Given a cancelled line whose placement sits on two PO lines
  and a same-order survivor with headroom for one of them, when the batch is applied, then
  the survivor gains no link and no "Took" note, the cancelled row keeps both links, and the
  batch row records the intent naming the survivor for purchasing.
- AC-IO-4 [BE][T] (was AC-RL-11) Given a row linked to a received PO line and an open PO
  line, when the settle redirects it, then the open link stays on the row, the received
  link stays as history, and no link is written onto either line.
- AC-IO-5 [BE][T] (G2) Given a planning-change apply that raises or settles a Buy row with
  an open PO line available for the product, when the deferred cascade runs, then the row
  holds no real document link; at most a suggested link.
- AC-IO-6 [BE][T] (was D7) Given a held SPO share the book delays past its window, when the
  batch is applied, then the SPO link stays on the row, the SPO's allocated quantity is
  unchanged, and the batch row records the release for purchasing.
- AC-IO-7 [BE] The sync (`follow_book_for_rows`, `follow_book_repairing`, the importer),
  a person's own act at Order Inquiries and CS reserve are unchanged.
- AC-IO-8 [UI] After Confirm on a changed order, Order Inquiries shows every PO and SPO
  link exactly as before the Confirm; the board row's "Where it went" list shows the
  notices.
