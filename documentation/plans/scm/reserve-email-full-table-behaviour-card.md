# Behaviour card: reserve request / reserved emails, full table (RESERVE-EMAIL-FULL-TABLE)

Status: waiting on the owner (card v1, 31 Oct 2026). No code yet.

**This reverses owner note 3 on OI-STAGED-NOTIFY mock v1** (the 5-OI cap with "and N more order
inquiries", `oi-staged-notify-behaviour-card.md` :94-97). The stakeholder asked for the opposite on
30 Oct: everything in the body, so nobody has to click in.

## What the stakeholder asked (30 Oct, purchasing/stock, via owner 31 Oct)

- Use the OI export layout (SO DATE, SO NO, ITEM CODE, QTY, REQUESTED RESERVE, RESERVED, TOTAL QTY,
  DELIVERY DATE, PROJECT/CUSTOMER) in BOTH emails: the reserve request to her and the reserved
  notice back, with RESERVED filled in.
- With the full table in the body, Cc to all CS is fine. If people have to click in, each CS should
  see only their own orders.

## Today (main, checked 31 Oct)

| What | Where |
| --- | --- |
| Batched email shows the first 5 OIs (OI NO / S/O NO / CUSTOMER / LINES), then "and N more order inquiries" | cap `order_inquiry_reserve_service.py:1215-1218`, template `oisn_0001_staged_notify.py:148-160` |
| Batched button opens `?reserve=needs_reserve` / `?reserve=reserved`: everyone's OIs, not this email's | `order_inquiry_reserve_service.py:1219` |
| Single-OI email already has a per-line table, but not in the export's columns (request: ITEM CODE / DELIVERY DATE / QTY / REMAINING / REQUESTED / LOCATION; reserved: ITEM CODE / QTY / REQUESTED / RESERVED / BALANCE / LOCATION / REASON) | seeded layout, frozen in `oisn_0001_staged_notify.py:58-130` |
| One email per To person, Cc lists merged (owner rule 6) | `park_send.py:95-100`, `PLAN-oi-staged-notify-14oct.md:46` |
| Every row the batched email needs is already built per OI (`reserve.rows`), with SO no, SO date, customer, project from `_handover_order_facts` | `order_inquiry_reserve_service.py:308-371`, `project_order_inquiry_service.py:5653-5728` |

The templates live in the database (seeded by `oisn_0001`), so changing what they print needs a
guarded data migration, the same in-place pattern `oisn_0001` used: update a row only while it still
holds the seeded text, and leave an admin-edited template alone. That is template data only, with no
schema change, but strictly it means this lane is not the "no migration" small-fix track.

## Card

### (1) Full per-line table in the body, no cap, in both emails

One row per OI line in the email. Same table for one OI and for a batch. Columns are the export's,
in the export's order:

`SO DATE | SO NO | ITEM CODE | QTY | REQUESTED RESERVE | RESERVED | BALANCE | TOTAL QTY | DELIVERY DATE | PROJECT/CUSTOMER`

- **Request email:** RESERVED shows what is already reserved on that line (blank when 0, same as
  the export at `order_inquiry_worklist_service.py:258-262`). BALANCE = still to buy.
- **Reserved email:** RESERVED is filled with what CS just reserved. BALANCE = what is still left to
  buy after this reserve (it already exists as `balance`, `order_inquiry_reserve_service.py:432,441`).
  REASON / "Released ... (received)" text stays as a small line under the row when there is one
  (today's REASON column, `:374-380`), so the table stays at 10 columns.
- **TOTAL QTY:** in the export it is the total of a supplier-and-item-code run
  (`order_inquiry_worklist_service.py:3693`). The email has no supplier, so the proposal is the total
  QTY of that item code within this email, printed on the last row of each item code (same "last
  row of the run" habit as the sheet). Alternative: drop the column from the email.
- Rows sorted by SO NO, then ITEM CODE. The OI NO + #request stays in a small grey group line above
  each OI's rows so CS can still find it on screen.
- Header: the count line stays ("Eling reserved stock on 11 order inquiries (37 lines)").
- LOCATION drops out (it is not in the export). Say if they want it kept.

**Large batches (for example 200 lines).** No cap, and the email stays one email. The real risk is
Gmail, which cuts off an email body over about 102 KB and shows "[Message clipped] View entire
message". 200 rows x 10 cells with our email layout's inline styles is in that range, so it can clip.
Recommendation:

- (a, recommended) **No cap.** Keep the row markup lean (styles on the table and header only, not on
  every cell) so 200 lines fit under the clip size, and measure the rendered size of a 200-line email
  in a test. Past the clip size, Gmail's "View entire message" still shows every row, and nothing is
  lost.
- (b) A cap (for example 300 lines) with "and N more lines, see the attached sheet" plus the OI export
  for exactly these OIs as an .xlsx attachment. That adds an attachment path to these emails. Hold it
  until (a) is shown to clip in real use.

### (2) The button opens exactly the OIs in this email

Today the batched button opens everyone's reserved list. Proposal: the button opens the OI list
filtered to this email's OIs:
`/project-sales/order-inquiries?inquiry_no=OI-2610-0012,OI-2610-0015,...` (OI numbers, no UUIDs),
with a new `inquiry_no` multi-value filter on the headers list (backend filter + one URL param on
`OrderInquiryHeadersList.tsx`, which already restores `?reserve=`, `?agent=` etc. from the URL at
`:104-140`). A single-OI email keeps today's link straight to that OI's detail page.

200 lines is at most a few dozen OIs, so the URL stays well under 2 KB. Label: "View these 11
order inquiries".

### (3) Per-CS split: recommend no split now

With the full table in the body, the stakeholder accepts one Cc-all email. **Recommendation: no
split**, keep owner rule 6 (one email per To person, Cc merged).

If you do want a split later, "the CS" for an SO has to come from a field that names a person with
an email address. What exists (still to be confirmed against dev data, see (4)):

| Candidate | Field | Points at a user (has an email)? |
| --- | --- | --- |
| OI raised by | `order_inquiries.raised_by` (`project_so.py:851`) | Yes, but mostly the admin account on imported OIs |
| SO sales agent | `sales_orders.sales_agent_id` -> `sales_agents` (`order.py:662`) | **No.** `sales_agents` holds a code + `person_label` and no user link (`sales_agent.py:44-80`), so an email cannot be routed by it without a new agent-to-user mapping |
| Customer account owner | `customers.account_owner_user_id` (`order.py:151`) | Yes |

Note: the crew pointer `order.py:445,457` (`agent`, `salesman`) is on the `orders` (delivery
orders) table, not `sales_orders`.

The OI list already has an `?agent=` filter (`OrderInquiriesClient.tsx:420,465`), so "Niki sees
Niki's" in the app is a filter by sales agent today, without any email change.

### (4) Real examples (masked)

Requested from crew as a `crew-data-request:` on PR #2046 (queries in the PR comment):
3-5 recent parked or sent reserve batches (OI count, line count, largest batch), and for 20 recent
OIs: raised_by, the SO's sales agent code + person_label, and the customer's account owner, so (3)
can be answered with evidence. This section is filled in when the data comes back.

## Questions for the owner

- Q1: full table, no cap, both emails: (a) no cap, lean markup, measure clip size (recommended) /
  (b) cap + xlsx attachment.
- Q2: button: (a) filtered to this email's OI numbers (recommended) / (b) keep the global list.
- Q3: per-CS: (a) no split, one Cc-all email (recommended) / (b) split; then which field (agent needs a
  new agent-to-user mapping; account owner works today).
- Q4: TOTAL QTY: (a) per item code within the email (recommended) / (b) drop it.

Next after the answers: a Lavish email mockup (real masked case, existing email layout blocks) filed
as its own ask; then red-first tests, build, kill tests, reviewer, guide update, hand-test script.
