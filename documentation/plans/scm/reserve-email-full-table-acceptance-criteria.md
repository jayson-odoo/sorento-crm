# UAC: reserve request / reserved emails, full table (RESERVE-EMAIL-FULL-TABLE)

Owner approved mockup v4 on 31 Oct 2026 with one change: **OI NO is the first column in both emails**.
Mockup: `mockups/reserve-email-full-table-mock-v2.html`. Card: `reserve-email-full-table-behaviour-card.md`.
The Excel and PDF download stay as they are (owner, "other than that all ok" on Q3).

"Request email" = trigger `order_inquiry_reserve_requested`. "Reserved email" = trigger
`order_inquiry_reserved`. "Batch" = an email covering 2 or more OIs. Everything below applies to the
parked send, the parked preview and the immediate (not parked) send unless it says otherwise.

## A. Table

- **AC-RF-01** Request email table columns, exactly and in this order:
  `OI NO | SO DATE | S/O NO | ITEM CODE | QTY | REQUESTED RESERVE | DELIVERY DATE | PROJECT/CUSTOMER`
- **AC-RF-02** Reserved email table columns, exactly and in this order:
  `OI NO | SO DATE | S/O NO | ITEM CODE | QTY | REQUESTED RESERVE | STATUS | DELIVERY DATE | PROJECT/CUSTOMER`,
  plus `REASON` as the last column only under AC-RF-15.
- **AC-RF-03** Apart from OI NO, STATUS and REASON, every heading is spelled as in `EXPORT_HEADINGS`
  (`order_inquiry_worklist_service.py`) and keeps its relative order there. STATUS sits where RESERVED
  sits. A test reads the constant, so the email cannot drift from the export.
- **AC-RF-04** The table is flat: one row per line, OI NO on every row, no group rows, no `colspan`. A
  one-OI email and a batch use the same table.
- **AC-RF-05** No cap: every line of every OI prints (test with 7 OIs). No "and N more" text anywhere.
- **AC-RF-06** Rows sort by ITEM CODE, then DELIVERY DATE as a real date (25/01/2027 before 02/03/2027),
  then OI NO. A line with no delivery date sorts last in its item code.
- **AC-RF-07** Values: SO DATE and DELIVERY DATE as dd/mm/yyyy. S/O NO is the OI's SO number. PROJECT/CUSTOMER
  is `project_customer_label` ("CUSTOMER / PROJECT"). QTY is the line's qty. REQUESTED RESERVE is this
  request row's `qty_requested`. Quantities print as `_qty_str` does (80, not 80.0000). A missing value
  prints empty, never "None".
- **AC-RF-08** RESERVED, BALANCE, REMAINING, TOTAL QTY and LOCATION headings, and any `#n` request number,
  appear nowhere: subject, heading, intro, table or plain text. "Check the balance still to buy" is gone.
- **AC-RF-09** The plain-text body carries the same lines in the same column order, and the button's URL.
- **AC-RF-10** The document uses the layout's `wide` width. OI NO and STATUS cells do not wrap (`nowrap`).

## B. STATUS and REASON (reserved email)

- **AC-RF-11** `qty_reserved >= qty_requested` reads `Reserved N`, N being `qty_reserved`.
- **AC-RF-12** `0 < qty_reserved < qty_requested` reads `Partial X of Y`, X = reserved, Y = requested.
- **AC-RF-13** `qty_reserved = 0` reads `Rejected`.
- **AC-RF-14** An amendment back to 0 reads `Rejected`. An amendment above the ask reads `Reserved N`.
- **AC-RF-15** The REASON column prints only when a line in that email has a reason, or falls under
  AC-RF-16. A line's reason is what the reserved email already carries, so "Released ... (received)."
  text comes first when documents were released (`_context_reason`).
- **AC-RF-16** A Rejected or Partial line with no reason reads `No reason given` in REASON. A fully
  reserved line with no reason is empty.
- **AC-RF-17** Rejected and Partial cells stand out (red and amber bold, as in the mockup).

## C. Words

Where `{raiser}` is unknown (`raised_by` is NULL), drop the "raised by" part entirely.
`{what}` is `{OI} - {SO}, raised by {raiser}` for one OI and `{k} order inquiries raised by {raiser}` for a
batch. `{short}` is `{OI} raised by {raiser}` for one OI and the same batch text for a batch. `{tag}` lists
only non-zero counts in this order: `1 partial`, `1 rejected`. "line" is singular for 1.

| Email | Subject | Heading | Intro |
| --- | --- | --- | --- |
| Request, one OI | `Reserve request: {what} ({requester})` | `{short} needs your reserve` | `{requester} asks CS to reserve stock on {short} (3 lines).` |
| Request, batch | `Reserve requests: {what} ({requester})` | `{short} need your reserve` | same as above |
| Reserved, all lines reserved | `Reserved: {what} ({actor})` | `Reserved: {short}` | `{actor} reserved all 5 lines on {short}.` (1 line: `reserved 1 line on`) |
| Reserved, some partial or rejected | `Reserved: {what}, {tag} ({actor})` | `Reserved: {short}, {tag}` | `{actor} answered 10 lines on {short}: 9 reserved, {tag}.` (leave out `0 reserved`) |
| Reserved, all rejected | `Rejected: {what} ({actor})` | `Rejected: {short}` | `{actor} rejected 5 lines on {short}.` |

- **AC-RF-18** Subject, heading and intro match the table above.
- **AC-RF-19** Under the table: request email `Requested by {requester} on {today}.`, reserved email
  `Answered by {actor} on {today}.`. A request's note prints under the table as `Note ({OI}): {text}`, one
  line per note. `{n} line(s) still to reserve.` still prints when requests in the email have open rows.

## D. Button

- **AC-RF-20** Batch: label `View these {k} order inquiries`, URL
  `{base}/project-sales/order-inquiries?inquiry_no=OI-1,OI-2` listing exactly this email's OIs, sorted.
- **AC-RF-21** One OI: label `View this order inquiry`, URL goes straight to that OI's page (today's
  link, with `?reserve=` when the email covers one request and without it when it covers several; no
  `inquiry_no=`).
- **AC-RF-22** `GET /api/v1/project-sales/order-inquiry-headers?inquiry_no=OI-1,OI-2` returns exactly those
  OIs. Matching is exact: `OI-2610-002` does not match `OI-2610-0025`. An unknown number adds nothing. An
  empty value is ignored. Company scope still applies. Comma-separated and repeated params both work.
- **AC-RF-23** The OI list reads `inquiry_no` from the URL, sends it to the API, keeps it in the URL across
  filter, sort and page changes, and shows a removable filter so the user can clear it.
- **AC-RF-24** Arriving with `inquiry_no` and no explicit `state` shows state All, so a completed OI in the
  email still appears (same rule as `?reserve=`). No UUIDs show anywhere.

## E. One email per raising CS

- **AC-RF-30** Parked requests on OIs raised by 2 CS become 2 emails. Each table holds only that CS's OIs,
  and each Cc has that CS and the requester, never the other CS.
- **AC-RF-31** Parked notices on OIs raised by 2 CS become 2 emails, To the requester, Cc only that email's CS.
- **AC-RF-32** 2 OIs raised by one CS stay one email.
- **AC-RF-33** An OI raised by the owner's account (a legacy import) is treated like any other raiser: its
  own email, that account on Cc. There is no legacy marker and no special case.
- **AC-RF-34** OIs with `raised_by` NULL form their own email with no raiser on Cc. It is not merged into
  another CS's email.
- **AC-RF-35** The preview returns the same emails as the send, and `emails_sent`, `items_sent`,
  `inquiry_total` agree with them.
- **AC-RF-36** Different To persons still get separate emails.
- **AC-RF-37** Different requesters still get separate emails, even with the same To person, so one requester
  is never on the Cc of another requester's email (`test_fix_N1` in `test_oi_staged_notify.py` pins this).

## F. One OI, several requests

- **AC-RF-40** Parked: one OI with 2 open requests is one email with both requests' lines. Every request and
  row in it is stamped as sent.
- **AC-RF-41** Immediate: `commit_request` answering 2 requests on one OI with the same requester is one email
  with both requests' lines.
- **AC-RF-42** Immediate: `commit_request` answering requests on 2 OIs is 2 emails, as today.
- **AC-RF-43** Immediate: 2 requests on one OI with different requesters are 2 emails.
- **AC-RF-44** Immediate: `create_request` without park sends the same table as the parked send.

## G. Template migration

- **AC-RF-50** A template still holding `oisn_0001_staged_notify`'s subject and layout is updated in place:
  subject, `layout_json`, `body_text`. No schema change.
- **AC-RF-51** An admin-edited template is left alone and still renders: the context keeps the keys today's
  templates read (`reserve.requests`, `oi_count`, `line_count`, `more_count`, `rows`, `ordinal`, `link`).
- **AC-RF-52** Upgrade is idempotent. Downgrade restores `oisn_0001`'s values only on a row still holding
  this revision's values.
- **AC-RF-53** The revision id is at most 32 characters. The file never contains either full template code as
  one token (built from two halves, as `oisn_0001` does: other OI tests scan for that token).

## H. Size and the export

- **AC-RF-60** A 105-line reserved email with a REASON column renders at or below 102 KiB (the Gmail clip size).
  Measured on the build: about 881 B per row, so the clip falls at about 108 lines. The pin catches markup that
  bloats rows. The UAC first said 110 lines, from the mockup's shorter item codes; the lead moved it on 1 Nov.
- **AC-RF-70** `EXPORT_HEADINGS` and the Excel and PDF download are unchanged.
