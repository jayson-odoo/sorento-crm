# UAC: SCM UI feedback batch, 14 Sep 2026

Plan: `PLAN-scm-ui-feedback-14sep.md` (journeys J1-J6 at its top)

## S1 - Supplier codes search

- AC-1.1 [FE] Given the Supplier codes tab, a search box sits above the Needs-a-decision
  card; typing `CWC605` shows only queue rows whose code contains it (case-insensitive) and
  only Remembered rows whose code or matched code contains it. (J1)
- AC-1.2 [FE] Typing a "Supplier says" fragment (e.g. `180横排`) matches queue rows by that
  text. (J1)
- AC-1.3 [FE] `CWC 250` (two tokens) shows only rows matching both tokens. (J1)
- AC-1.4 [FE] Card titles read `Needs a decision (n of total)` and `Remembered (n of total)`
  while a filter is active, plain `(total)` when the box is empty; Confirm (n) counts decided
  rows regardless of the filter. (J1)
- AC-1.5 [FE] No match renders "No code matches" in place of the table body; clearing the
  box restores every row. (J1)

## S2 - Order inquiries token search

- AC-2.1 [BE] `query=SO366990 SRTWT6801` returns only rows on SO366990 whose item/product
  matches SRTWT6801; `query=SRTWT6801 SO366990` returns the same set. (J2)
- AC-2.2 [BE] A single token behaves exactly as today across all eleven columns; the
  user-email column keeps its prefix match. (J2)
- AC-2.3 [BE] Leading/trailing/multiple spaces are ignored; an all-space query filters
  nothing. (J2)
- AC-2.4 [BE] The summary tiles and the export honour the same token split as the list. (J2)
- AC-2.5 [FE] The search box, placeholder and URL `?query=` sync are unchanged; no
  explanatory text is added to the page. (J2)

## S3 - Loading plan General tab

- AC-3.1 [FE] The page header shows the supplier name and breadcrumb only: no status badge,
  no Started/up to/Stock list line. (J3)
- AC-3.2 [FE] The tab strip reads `General | Lines | Supplier codes (n) | Sent`; opening a
  plan without `?tab=` lands on Lines. (J3)
- AC-3.3 [FE] The General tab shows a `Plan` card with Status (badge), Supplier, Started,
  Plan window, Stock list, each as a label above its value, two columns from 640px, one
  column at 375px, none clipped. (J3)
- AC-3.4 [FE] The prev/next pager, gear and Save cluster stay where they are and work on
  every tab. (J3)
- AC-3.5 [FE] `Field` is imported from `components/common/Field` by both the PI detail and
  the loading plan; no second copy remains. (J3)

## S4 - "By" shows names

- AC-4.1 [BE] After a stock-list upload that auto-matches codes, the new alias rows carry
  the uploader's name (or email) in `created_by`, never their id. (J4)
- AC-4.2 [BE] An alias row already holding a user id in `created_by` lists as that user's
  name (email when the name is blank); an id that matches no user lists as null; a plain
  name passes through untouched; one users query per list call. (J4)
- AC-4.3 [FE] The By cell renders the name, or a dash for null; no cell ever shows a
  UUID-shaped string. (J4)

## S5 / S6 - Remembered table

- AC-5.1 [FE] "Matched to" shows `SRTWC8357-RL-P` (product code) or the set code only;
  `Dismissed` rows still say Dismissed; a row with neither shows a dash. (J4)
- AC-6.1 [FE] The Remembered table has columns Code, Matched to, When, By, Forget and no
  How column; Forget still runs its countdown and deletes. (J4)

## S7 - PI Lines: one Product control

- AC-7.1 [FE] The Invoice lines table has no Match column, no Matched / Not in catalogue
  badges and no "Match to product or set" button. (J5)
- AC-7.2 [FE] In read mode, a line with an item code shows a `Search a product or set`
  select in the Product column; its options list sets first (Set badge) then products, and
  the current match is shown as the code. (J5)
- AC-7.3 [FE] Picking an option on a coded line POSTs the supplier-code alias immediately
  (no Edit, no Save), the cell shows the new code, the toast reports the rebind count, and
  the select is disabled while the request is in flight. (J5)
- AC-7.4 [FE] Picking a set option sends `product_set_id`, not `product_id`. (J5)
- AC-7.5 [FE] Clearing the select on a line with a remembered match starts the 5 s
  reversible countdown in the cell with Cancel; on lapse the alias is deleted and the line
  shows the placeholder again; Cancel restores the code. A line with no alias offers no
  clear. (J5)
- AC-7.6 [FE] A line with a blank item code keeps today's behaviour: select only in edit
  mode, pick patches the draft (product or set), Save persists it. (J5)
- AC-7.7 [FE] A user without `scm.proforma_invoice.adjust` sees the code as text, not a
  select. (J5)
- AC-7.8 [BE] An alias written for `srtwc8366-rl ` (case/space variant) re-points the line
  holding `SRTWC8366-RL`. (J5)

## S8 - PI Source files card

- AC-8.1 [FE] `AttachmentFileCard` renders name, `type • size KB`, Preview and Download
  icon buttons with accessible labels, and Unlink only when `onUnlink` is passed. (J6)
- AC-8.2 [FE] The packing list Related Documents card renders through `AttachmentFileCard`
  with preview, download and its existing unlink flow unchanged. (J6)
- AC-8.3 [BE] `GET /api/v1/scm/proforma-invoices/{id}` `source_files[]` entries carry
  `attachment_id`, `file_size_bytes`, `mime_type`, `type`, `name`, `uploaded_at`. (J6)
- AC-8.4 [BE] A packing-list workbook uploaded against an invoice is linked to that invoice
  and appears in `source_files` with type "Packing list". (J6)
- AC-8.5 [FE] The PI General tab Source files section renders one card per `source_files`
  entry; Preview opens the preview URL, Download saves the file, no Unlink is offered; an
  invoice with no files shows "No source file on record". (J6)
- AC-8.6 [E2E] On the lane stack, PI-2609-008 shows two cards (invoice workbook, packing
  workbook) with working Preview and Download. (J6)
