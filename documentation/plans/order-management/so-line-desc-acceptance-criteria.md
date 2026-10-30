# UAC: SO line description (SO-LINE-DESC, 30 Oct 2026)

Plan: `PLAN-so-line-desc-30oct.md`. Card + owner answers: `SO-LINE-DESC-card.md`. Mock:
`documentation/mockups/SO-LINE-DESC/index.html`.

"Description" below = the AutoCount SO line description (SODTL.Description), which shared service
already sends on each sales order line as `product_name`. "Ticked product" = a product whose
"Show SO line description in OI email" tick is on.

## Storage and ingest

- AC-1 A sales order push whose line carries `product_name: "SORENTO ACCESSORIES SRTWC8320-S150-UF PUSH BUTTON ONLY"`
  stores exactly that text (trimmed) on the CRM sales order line.
- AC-2 A later push of the same line WITHOUT the `product_name` key leaves the stored description as is.
  A push with `product_name: null` clears it. A blank or whitespace-only value stores nothing (NULL).
- AC-3 Product resolution is unchanged: the line still resolves its product exactly as before.

## Screens

- AC-4 SO detail > Lines shows a "Description" column right after Product, on every line, read-only
  (also in edit mode). Long text truncates with the full text on hover. No description = empty cell.
  The SO detail API returns `description` on each line.
- AC-5 Fulfilment planning list view shows a "Description" column right after Product, taken from the
  core SO line the row belongs to. No description, or no core SO line = empty cell. The board API
  returns `description` on each row.
- AC-6 Both columns usable and not clipped at 375px and 1280px (table scrolls inside its container).

## Product tick

- AC-7 Products carry a tick "Show SO line description in OI email", default off. It is a switch on the
  product create/edit form beside Serial/Batch Tracking, and a badge "SO line description in OI email:
  Yes/No" in the product detail flags row. Saving the form persists it; the product API returns it.
- AC-8 A product push from shared service never changes the tick.
- AC-9 After the migration, every product with code RPACC is ticked; no other product is.

## OI email, send preview, Excel attachment (no new column)

- AC-10 For an OI line whose product is ticked and whose SO line has a description that is non-blank
  and not equal to the code, the ITEM CODE value is `<code> - <description>` (one space, hyphen, one
  space), e.g. `RPACC - SORENTO ACCESSORIES SRTWC8320-S150-UF PUSH BUTTON ONLY`.
- AC-11 Otherwise the ITEM CODE value is the bare code: product not ticked (e.g. RPAC), description
  empty, or description equal to the code. Never a trailing ` - `.
- AC-12 The same ITEM CODE string appears in the email HTML body, the email plain-text part, the
  send/resend preview body and the Excel attachment's ITEM CODE cell, for the same lines.
- AC-13 A code switch (line with an old code shown beside NEW ITEM CODE): each side follows AC-10/11
  by ITS OWN product's tick, using the SO line's description. An unchanged line never shows NEW ITEM CODE.
- AC-14 In the email body (and so the preview) an ITEM CODE cell carrying a description wraps; a bare
  code keeps today's no-wrap. In the Excel, a decorated ITEM CODE cell has wrap text on; the column
  width is unchanged.
- AC-15 The resend flow's own check that each row's code is in the body still passes for decorated lines
  (`app/services/oi_handover_resend.py:210`).

## Rollout

- AC-16 Existing SO lines get their description after one shared-service Repush of sales orders, run
  after the CRM release and after confirming the connection sends contract v2. Its load is measured
  and crew-noted before it runs.
