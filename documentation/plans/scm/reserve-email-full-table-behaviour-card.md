# Behaviour card: reserve request / reserved emails, full table (RESERVE-EMAIL-FULL-TABLE)

Status: card v2 (31 Oct 2026). Owner has answered Q1-Q4. Next: the email mockup ask (open point L below).
No code until the owner OKs the mockup.

**This reverses owner note 3 on OI-STAGED-NOTIFY mock v1** (the 5-OI cap with "and N more order
inquiries", `oi-staged-notify-behaviour-card.md` :94-97). **It also reverses owner rule 6 of
`PLAN-oi-staged-notify-14oct.md:46`** (one email per To person with every raiser merged on Cc).
After this lane, there is one email per To person per raising CS.

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

One table for one OI and for a batch, in the export's column order without TOTAL QTY:

`SO DATE | SO NO | ITEM CODE | QTY | REQUESTED RESERVE | RESERVED | BALANCE | DELIVERY DATE | PROJECT/CUSTOMER`

- A grey line above each OI's rows names the OI and its request numbers (for example "OI-2610-0057
  #1, #2, #3").
- OIs are sorted by SO NO, and lines by item code, then delivery date.
- **Request email:** RESERVED shows what is already reserved on the line (blank when 0, as the
  export does, `order_inquiry_worklist_service.py:258-262`). BALANCE = QTY minus that.
- **Reserved email:** RESERVED = what CS reserved. BALANCE = still to buy after it
  (`balance`, `order_inquiry_reserve_service.py:432,441`). The reason / "Released ... (received)"
  text, when a row has one, prints as a small line under that row.
- The card uses the layout's "wide" width (900 px; `email_layout.py:404`). Today's reserve emails
  use the standard 600 px.

**Size, measured** with the app's own renderer (`email_layout.render_document`, default theme,
masked real rows): 22 lines = 28 KB, 50 = 52 KB, 100 = 94 KB, **about 110 = 102 KB, the size at
which Gmail starts clipping**, and 200 = 178 KB. Most of each row's ~800 bytes is the per-cell default
style `inline_defaults` adds (`email_layout.py:439-489`). Above the clip size, Gmail shows "[Message
clipped] View entire message", which opens every row, so nothing is lost. Real volume on the 28 Oct
dev copy was 71 request lines across 28 OIs in 30 days, from one requester. After the per-CS split
below, each email is smaller still. A test pins the rendered size of a 110-line email so a markup
change that bloats rows is caught.

On a phone (375 px), the table is wider than the screen and the mail app scrolls it sideways.

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

### L. Open point: OIs from the 20 Sep legacy import (raised by the owner's account)

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

The mockup (filed as its own ask) renders 5 real OIs, 22 lines, from the 28 Oct dev copy, masked.
That data pull did not include `raised_by` for these 5 OIs, so the mockup's split across CS is
illustrative and says so.

## Build after the mockup OK (small fix track, plus one template-data migration)

1. Red tests first: full table rows and columns in both emails for 1 and N OIs; no "more" line;
   button URL lists exactly the email's OI numbers; split by raiser (two CS lead to two emails, each Cc
   only its CS, each table only its OIs); a single-raiser batch stays one email; reserved RESERVED and
   BALANCE values; a size test for 110 lines; the migration updates a seeded template and leaves an
   edited one alone; the headers list `inquiry_no` filter (BE + FE URL round trip).
2. Build: `_groups` split, flat `reserve.groups` context, template migration, `inquiry_no` filter.
3. Kill tests, reviewer, guide update, hand-test script.
