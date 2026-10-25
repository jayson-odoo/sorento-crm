# UAC: per-SO remark in the Confirm purchasing email (FULFIL-SO-REMARK, 25 Oct 2026)

Plan: `PLAN-fulfil-so-remark-25oct.md`. Rules: `CARD-fulfil-so-remark-25oct.md` (FINAL, owner-approved
25 Oct 05:39). "MOCK" below means the text contains `MOCK`, case-insensitive (covers MOCKUP, MOCK UP,
MOCK-UP).

## Shared service (foundryx-shared-service)

- **SS-1** The AutoCount SO header preset query selects `ShipInfo`; it maps to the canonical SO
  header field `ship_info` and is sent to Sorento on the `sales_orders` push.
- **SS-2** The SO line preset query selects `FurtherDescription` (raw, not RTF-stripped) and
  `SectionHeading`: the Description of the nearest text-only line before it (same DocKey, lower Seq,
  ItemCode or Qty NULL, Description not blank), NULL when there is none. They map to the SO line
  fields `line_remark` and `section_heading`. PO and SPO lines are unchanged. The item-line cut
  (`ItemCode IS NOT NULL AND Qty IS NOT NULL`) and the header LineCount still agree.
- **SS-3** Existing SO tasks whose header/line query is byte-identical to the previous preset are
  rewritten to the new query by a backfill run from a module migration; any other task keeps its
  query and gets the new mapping rows seeded disabled with a warning. The backfill is idempotent.
  The docs name the manual step for a hand-written query (prod AED_SORENTO).

## CRM: storage and ingest

- **AC-1** `POST /external/ingest/sales_orders` stores header `ship_info` on `sales_orders.ship_info`
  and line `line_remark` / `section_heading` on `sales_order_lines`. `line_remark` arrives as RTF
  and is stored as plain text (the `internal_note` stripper). A re-ingest with new values overwrites;
  a payload without the key leaves the stored value as it is (same as `po_ref`).
- **AC-2** One alembic revision adds the three nullable columns; `alembic heads` shows one head; the
  revision id is at most 32 characters.

## CRM: rules (one module, used by the board and the email)

- **AC-3** A line is a mockup line when the SO's note is MOCK, or its `line_remark` is MOCK, or its
  `section_heading` is MOCK.
- **AC-4** The SO remark type from `ship_info`: contains `SPON` -> `Sponsorship`; else contains
  `PURCHASE REQ`, or starts with `PR` followed by a digit (after leading spaces; `PRR26-...` does not
  match) -> `Purchase Request`; else none. Case-insensitive.
- **AC-5** Default remark for the lines chosen for one SO: the remark type when there is one; else
  `Mockup` when at least one chosen line is a mockup line; else blank.
- **AC-6** Line labels: only when the chosen lines of one SO include both mockup and non-mockup lines,
  each chosen mockup line is labelled `Mockup`.

## CRM: board and Confirm guide

- **AC-7** The fulfilment-planning board returns `is_mockup` on each line contribution and
  `remark_type` (`Sponsorship` / `Purchase Request` / null) on each order standing.
- **AC-8** Each SO page of the Confirm guide shows a `Remark` text input directly under the SO header
  row, prefilled with the AC-5 default for that page's lines, editable, clearable (clear button),
  at most 100 characters. Closing and reopening the guide recomputes the default (an edit is not
  kept).
- **AC-9** When AC-6 applies, each mockup line on that page shows a `Mockup` badge; otherwise no line
  shows it.
- **AC-10** Confirm sends `so_remark` for every order: the field's value, `""` when cleared.

## CRM: purchasing email

- **AC-11** The email's SO table has REMARK as its last column (HTML and text part). Each SO row shows
  its `so_remark`. When an order arrives without `so_remark` (null / absent), the AC-5 default for
  that order's lines in this email is used; `""` prints a blank cell.
- **AC-12** When AC-6 applies to the lines of one SO in the email, each mockup line's REMARK cell
  reads `Mockup`, or `Mockup, <its existing text>`. Other cells are unchanged.
- **AC-13** "Send to purchasing" (resend from open OI rows) prints the AC-5 default and the AC-12
  labels computed from the resent lines.
- **AC-14** Template migration `oihr_0010`: updates `order_inquiry_handover_default` only while it is
  exactly `oihr_0009`'s; leaves an admin-edited row alone with a logged warning; inserts when missing;
  idempotent; downgrade restores `oihr_0009`'s layout.
- **AC-15** Unchanged: the OI Excel attachment, the preview dry run, every other email cell.

## CRM: Sales Order page (owner add-on, 25 Oct ~13:05)

- **AC-16** The SO detail API used by Project Sales Admin > Sales Orders returns `remark` (the AC-5
  default computed over ALL the SO's live lines, cancelled lines skipped: `Sponsorship` / `Purchase Request` / `Mockup` / "") and
  `ship_info` (as stored), and per line `is_mockup` and `mockup_label` (true only when AC-6 holds over
  the SO's live lines and that line is a live mockup line). Computed with the same rules module.
- **AC-17** The General tab shows read-only `Remark` and `Shipping Info` fields with the page's
  existing read-only field component; an empty value shows the page's usual empty marker.
- **AC-18** The Lines tab shows the `Mockup` badge (same Badge as the Confirm guide) on lines whose
  `mockup_label` is true; none otherwise. Usable at 375px and 1280px.
- Cases: SO427488 -> Remark `Purchase Request`, Shipping Info `PURCHASE REQUEST`; SO427563 ->
  `Sponsorship` + badge on MSK11A only; SO427088 -> `Mockup`, no badges; SO419417 -> `Mockup` +
  badges on CB2829-DIY, SRT2403-CR, SRTWB1515; SO427174 -> blank, no badges.

## Card cases (must each have a test)

SO419417 shape (3 of 24 lines line-remarked MOCK): all chosen -> `Mockup` + 3 labels; only the 3
chosen -> `Mockup`, no labels; only the other 21 chosen -> blank. Note MOCK (SO427088) -> `Mockup`,
no labels. Shipping Info `SPONSORSHIP` + note MOCK (SO421287) -> `Sponsorship`. Shipping Info
`PURCHASE REQUEST` -> `Purchase Request`; `PR26-0375` -> `Purchase Request`; `PRR26-0120` -> none.
Heading line `MOCK UP - BLOCK 1` followed by items, then heading `BLOCK 1 & 3 - JUL 27` (SO421072
shape): only the items between the two headings are mockup lines.
