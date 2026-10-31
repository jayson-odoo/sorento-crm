# Behaviour card: reserve request / reserved emails, full table (RESERVE-EMAIL-FULL-TABLE)

Status: approved (31 Oct 2026). Owner approved mockup v4 with one change, OI NO first, and left the Excel download as it is (`mockups/reserve-email-full-table-mock-v2.html`, same path by brief). Contract: `reserve-email-full-table-acceptance-criteria.md`.

**This reverses owner note 3 on OI-STAGED-NOTIFY mock v1** (the 5-OI cap with "and N more order
inquiries", `oi-staged-notify-behaviour-card.md` :94-97). **It also reverses owner rule 6 of
`PLAN-oi-staged-notify-14oct.md:46`** (one email per To person with every raiser merged on Cc).
After this lane, there is one email per To person per raising CS. **Owner note 1 on mockup v2 also
overrides the stakeholder's "RESERVED filled in" ask:** there is no RESERVED column, and the STATUS
column carries the reserved figure instead.

## What the stakeholder asked (30 Oct, purchasing/stock, via owner 31 Oct)

- Use the OI export layout in BOTH emails (the reserve request and the reserved notice), with
  RESERVED filled in.
- "CS want see own sales order only - niki see niki, cyndi see cyndi."

## Owner answers (31 Oct, card v1)

| Q | Answer |
| --- | --- |
| Q1 full table | (a) Every line in both emails, no cap. Lean markup, and a test measures the clip size. |
| Q2 button | (a) The button opens exactly this email's OIs. |
| Q3 per CS | **Split.** One email per CS, by who raised the OI (`order_inquiries.raised_by`). Each email holds only the OIs that CS raised, and its Cc is only that CS. |
| Q4 TOTAL QTY | **Dropped.** LOCATION is dropped too (not asked to keep it). |

## Owner notes on mockup v2 (31 Oct)

| Note | Meaning | In mockup v3 |
| --- | --- | --- |
| "Remive reserved snd balance column" | Drop RESERVED and BALANCE | Gone from both emails. The reserved email gains STATUS where RESERVED was. |
| "Remove #123" | Drop the `#n` request number | Gone from subject, heading, intro and the grey OI line. |
| "If rejecred need to say rejected instead of reserved 0" | A Reserve 0 line says Rejected | STATUS reads Rejected, reason underneath. An all-rejected email also says Rejected in subject and heading. |
| "Yes" on L1 | Legacy imports need no special case | See L below, now closed. |

## Owner notes on mockup v3 (31 Oct)

| Note | In mockup v4 |
| --- | --- |
| "I think the Oi put as a column instead of group like that, easier to filter" | Flat table: OI NO on every row, no group lines. |
| "Rejected need to show the reason, does this coincide with how they want the excel to be represented when downloading the OI from system?" | A REASON column in the row. The Excel comparison is below. |

## Today (main, checked 31 Oct)

| What | Where |
| --- | --- |
| Batched email shows the first 5 OIs (OI NO / S/O NO / CUSTOMER / LINES), then "and N more order inquiries" | cap `order_inquiry_reserve_service.py:1215-1218`, template `oisn_0001_staged_notify.py:148-160` |
| Batched button opens `?reserve=needs_reserve` / `?reserve=reserved`: everyone's OIs | `order_inquiry_reserve_service.py:1219` |
| Single-OI table uses other columns (request: ITEM CODE / DELIVERY DATE / QTY / REMAINING / REQUESTED / LOCATION; reserved: ITEM CODE / QTY / REQUESTED / RESERVED / BALANCE / LOCATION / REASON) | seeded layout, frozen in `oisn_0001_staged_notify.py:58-130` |
| Grouping: one email per first recipient (To), with the raisers and requesters of every item merged onto it | `park_send.py:78-100` |
| Recipients: the request goes To the users set on the automation (Eling), Cc the requester (`include_actor`) and the raiser. The reserved notice goes To the requester, Cc the raiser. | `oirs_0001_reserve_requests.py:380-405`, `automation_recipients.py:113-131` |
| Rows, SO no, SO date, customer and project are already built per OI | `order_inquiry_reserve_service.py:308-371`, `project_order_inquiry_service.py:5653-5728` |

The templates live in the database (seeded by `oisn_0001`), so the new table ships as a guarded
template-data migration using `oisn_0001`'s in-place pattern: update a row only while it still
holds the seeded text, and leave an admin-edited template alone. No schema change.

## Behaviour

### (1) Full per-line table in both emails, no cap

One flat table for one OI and for a batch. Column names and order come from the export's
`EXPORT_HEADINGS` (`order_inquiry_worklist_service.py:196-240`). OI NO goes first (owner, v4), and REASON
goes last, by the export's own rule that a new column goes after the existing ones (`:216-219`):

- **Request email (8 columns):** `OI NO | SO DATE | S/O NO | ITEM CODE | QTY | REQUESTED RESERVE | DELIVERY DATE | PROJECT/CUSTOMER`
- **Reserved email (9 columns, 10 with REASON):** `OI NO | SO DATE | S/O NO | ITEM CODE | QTY | REQUESTED RESERVE | STATUS | DELIVERY DATE | PROJECT/CUSTOMER | REASON`

| CS's answer on the line | STATUS shows | REASON shows |
| --- | --- | --- |
| `qty_reserved >= qty_requested` (an amend can raise it past the ask, `order_inquiry_reserve_service.py:889,996`) | Reserved 80 | Blank, unless documents were released ("Released ... (received).", `:379`) |
| `0 < qty_reserved < qty_requested` | Partial 150 of 212 | CS's reason |
| `qty_reserved = 0` ("Reserve 0", `:942`) | Rejected | CS's reason |

This is display only: no new status, no schema change. A line amended back to 0 also reads Rejected.
REASON prints only when a line in that email has one: on the dev copy no line has any, so an always-on
column would be empty on every real email so far.

**When there is no reason:** the form requires one whenever Reserved is below Requested
(`ReserveLineForm.tsx:35,112`). The server only requires it below what the line could still take
(`order_inquiry_reserve_service.py:847,854,262`), and an amendment across two requests sets it on the
last row touched (`:974`). So a blank can reach the email, and a Rejected or Partial line without a
reason prints "No reason given". Card v3 and the v3 ask called the reason mandatory on any short
answer. That was too broad.

**Subject and heading follow the answers on the email's lines:**

| Lines | Subject |
| --- | --- |
| All reserved | Reserved: 2 order inquiries raised by User-H (User-G) |
| Some partial or rejected | Reserved: OI-2610-0025 - SO424763, raised by User-E, 1 rejected (User-G) |
| All rejected | Rejected: OI-2609-0780 - SO423386, raised by User-C (User-G) |

A one-OI email names the OI and SO instead of a count, as today, without the `#n`.

**With BALANCE gone:** today's "Check the balance still to buy" line goes too. On OI-2609-0165, QTY is
170 and STATUS is Reserved 70, so the reader works out the 100 still to buy.

- OI NO is on every row, with no group lines. A request's note, when it has one, prints under the
  table as "Note (OI-...): ...", as today's single email does (`oisn_0001_staged_notify.py:70`). Today's
  bulk email drops it.
- Lines sort by ITEM CODE, then DELIVERY DATE, as the export does after SUPPLIER
  (`order_inquiry_worklist_service.py:3938`). A batch's OIs can interleave, and the OI NO column keeps
  them apart.
- "N lines still to reserve" still prints when a request has open lines (`:459`).
- **One OI, several open requests:** one email and one table. Today each request gets its own email
  (`_groups`, `:1228-1244`, parked; `commit_request`, `:1013-1048`, answered together). Without `#n`
  those emails would read as duplicates, and removing the split is less code.
- The card uses the layout's "wide" width (900 px; `email_layout.py:404`), as the handover email does
  (`oihr_0004_wide_line_table.py`). Today's reserve emails use the standard 600 px.

**Size, measured on the v4 columns** with the app's own renderer (`email_layout.render_document`,
default theme, masked real rows):

| Lines | Request (8 columns) | Reserved (9) | Reserved with REASON (10) |
| --- | --- | --- | --- |
| 100 | 75 KB | 84 KB | 91 KB |
| 110 | 81 KB | 91 KB | 100 KB |
| 200 | 141 KB | 159 KB | 174 KB |

**Gmail starts clipping at about 102 KB: about 140 lines on the request email, about 125 on the reserved
email, and about 110 when REASON prints** (estimated from these renders). Most of each row's size is the
per-cell default style `inline_defaults` adds (`email_layout.py:439-489`). Above the clip size, Gmail shows "[Message
clipped] View entire message", which opens every row, so nothing is lost. Real volume on the 28 Oct
dev copy was 71 request lines across 28 OIs in 30 days, from one requester. After the per-CS split
below, each email is smaller still. A test pins the rendered size of a 110-line email so a markup
change that bloats rows is caught.

On a desktop, measured in a browser, the email stays on the 900 px card, except when REASON prints:
those 10 columns need about 955 to 1000 px, so the card grows to fit. On a phone (375 px) it is about 720
to 990 px wide, so the reader scrolls sideways, heading included. A wrapper scrolling only the table did
not help: the card's table layout grows to fit it anyway. No wrapper is added. UNVERIFIED in real mail
apps, which may shrink the email instead; the hand test covers a phone.

### Email compared with the OI Excel download

The owner asked if this coincides with the Excel. **Yes for the columns they share, no for the outcome.**
The PDF prints the same 19 columns as the Excel (`export_pdf`, `order_inquiry_worklist_service.py:3726-3734`).

| Excel column, in order | Request email | Reserved email | Why |
| --- | --- | --- | --- |
| SO DATE, S/O NO, ITEM CODE, QTY | Yes | Yes | Same (mockups up to v3 wrongly said SO NO) |
| REQUESTED RESERVE | Yes | Yes | Same on a first request. If a line was asked again, the email shows this request's figure and the Excel adds what earlier requests kept (`:563`) |
| RESERVED | No | STATUS in this place | Owner note on v2 |
| TOTAL QTY | No | No | Owner answer on card v1 |
| DELIVERY DATE, PROJECT/CUSTOMER | Yes | Yes | Same |
| SUPPLIER, PO NO | No | No | Not in the columns the stakeholder asked for |
| LOCATION | No | No | Owner answer on card v1 |
| ACKNOWLEDGED, TAKEN, REMAINING, SUGGESTED, CHANGE QUANTITY, CHANGE DATE, REMARK | No | No | Not in the columns the stakeholder asked for |
| *In the email only:* OI NO | Yes | Yes | Owner note on v3 |
| *In the email only:* STATUS | No | Yes | Owner notes on v2 |
| *In the email only:* REASON | No | When a line has one | Owner note on v3 |

**The gap:** in the Excel, a rejected line reads the same as one still waiting for CS. REQUESTED RESERVE
stays filled after CS answers (`:516-522`, `:2601`), RESERVED prints blank at 0 (`:258-262`), and the
reason appears nowhere. **Owner left the Excel as it is** (31 Oct, on mockup v4). Trigger for a follow-up:
the first time someone needs a rejected line's reason from the download.

### (2) The button opens exactly this email's OIs

`/project-sales/order-inquiries?inquiry_no=OI-...,OI-...` (OI numbers, no UUIDs). This adds a new
multi-value `inquiry_no` filter on the headers list: the backend filter, plus one URL param in
`OrderInquiryHeadersList.tsx`, which already restores its filters from the URL (`:104-140`).
Label: "View these N order inquiries". A one-OI email keeps today's direct link to that OI.

### (3) One email per raising CS

**Evidence (28 Oct dev copy, masked; data not committed):**

- On the 20 most recent OIs, `raised_by` is set on all 20, across 5 distinct named staff users.
  None was raised by an `admin%` email account (0 of 946 OIs overall).
- The legacy OIs imported on 20 Sep show the **owner's own account** as raiser: the importer
  stamps `raised_by = self.actor` (`project_order_inquiry_import_service.py:2749-2754`).
- `raised_by` equals the SO's sales-agent person on 0 of 20. So the raiser is the CS, not the
  salesperson.
- `customers.account_owner_user_id` is NULL on 20 of 20, so it is not a usable alternative.
- The sales agent has no user link (on the dev DB, `sales_agents.contact_id` points at a contact, not a user), so
  it cannot address an email.
- The 5 OIs in the mockup have 4 different raisers. On each, the raiser, the person who asked for the
  reserve and the person who reserved are three different people, so the split changes real emails.

Card v1 said `raised_by` is "mostly the admin account on imported OIs". **That was wrong.** On OIs
raised after the import, `raised_by` is the CS who raised them.

**Rule:** group the parked items by (To person, raiser). Each group's recipients resolve from that
group's own items only, so the Cc holds that one CS (plus the requester on the request email, as
today) and never another CS. For a batch of OIs raised by 3 CS, Eling gets 3 request emails and the
requester gets 3 reserved emails. Each CS sees only their own OIs, and the button opens only those.
The change sits in `OrderInquiryReserveService._groups` (`order_inquiry_reserve_service.py:1224`);
`park_send.group_by_recipient` and the recipient resolver stay as they are.

**Subject names the CS:** "Reserved: 2 order inquiries raised by User-A (User-G)" / "Reserve
requests: 2 order inquiries raised by User-A (User-F)".

### L. Closed, L1: OIs from the 20 Sep legacy import (raised by the owner's account)

**Owner chose L1 on mockup v2.** The options as they were offered:

There is no marker on an OI that says "imported": the importer writes the same `raised` history row
as a hand raise (`:2760-2762`), so the owner's account is just the raiser.

- **(L1, recommended) No special case.** The owner's account is treated as one more raiser: the
  legacy OIs form their own email, To Eling / the requester as usual, Cc the owner's account. No CS
  sees another CS's orders. No new rule or setting is needed, and the group shrinks to nothing as
  the legacy OIs complete.
- **(L2, crew's suggestion)** Legacy OIs go in one email to the requester only, with no raiser on Cc.
  This needs a way to tell "legacy" apart: a new setting naming the importer account, or a hard-coded
  raised-before-21-Sep cutoff. That is new machinery for a set of OIs that only shrinks.

### (4) Real case

The mockup (filed as its own ask) renders 5 real OIs, 22 lines, from the 28 Oct dev copy, masked, with
their real raisers: 4 emails each way. Only the partial and rejected answers and their reasons are
illustrative, and the mockup says so. On that copy every answered line is a full answer and no line has
reason text, so no real Partial or Rejected exists yet, and until one happens every line reads "Reserved
N". The hand test has to create both with a real Reserve 0 and a short answer on the test copy.

The masked data does not say whether the OIs raised by User-H are legacy imports on the owner's account.
The rule is the same either way (L1).

## Build after the mockup OK (small fix track, plus one template-data migration)

1. Red tests first: full table rows and columns in both emails for 1 and N OIs; no "more" line; no
   RESERVED, BALANCE or `#n` anywhere, plain text included; STATUS for full, partial and rejected, and
   an amend above the ask and back to 0; subject and heading for all
   reserved, mixed and all rejected; OI NO on every row and no group lines; columns follow `EXPORT_HEADINGS` order (a test reads the constant,
   so the email cannot drift from the export); REASON prints only when a line has one, and "No reason given"
   on a Rejected or Partial line without one; button URL lists exactly the email's OI numbers; split by raiser
   (two CS lead to two emails, each Cc only its CS, each table only its OIs); a single-raiser batch
   stays one email; one OI with several requests is one email, parked and answered together; a size
   test for 110 lines; the migration updates a seeded template and leaves an edited one alone; the
   headers list `inquiry_no` filter (BE + FE URL round trip).
2. Build: `_groups` split by raiser and no more per-request split, flat `reserve.groups` context with
   each line's STATUS, template migration, `inquiry_no` filter.
3. Kill tests, reviewer, guide update, hand-test script.
