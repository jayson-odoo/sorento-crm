# Behaviour card v2: the reserve email's button opens that email's lines (OI-RESERVE-ROUND, 3 Nov)

Status: Plan. Card v2 after the owner's scope cut (3 Nov ~23:05). Size S, small fix track: no
migration, no auth/RBAC change, expected diff well under 300 lines. Plan:
`PLAN-oi-reserve-round.md`, UAC: `oi-reserve-round-acceptance-criteria.md`.

crew-lane: OI-RESERVE-ROUND

## Scope (owner, 3 Nov ~23:05)

Only the "Open order inquiry" button in the reserve emails (the request email to CS and the
reserved notice back to the requester). It opens exactly the lines that email covers, in every
state: still open, reserved, partly reserved, rejected. Not the "Request to reserve" filter that
hides answered lines. The 31 Oct rule stands: the button is scoped to that email's OIs.

Dropped: one summary per round, when it is sent, who gets it, incoming cover, a "Changed" email,
any change to parking. Email text, table, recipients and timing stay as they are.

## What the button does today

| Email covers | Link today | What opens | Where |
| --- | --- | --- | --- |
| One OI, one request | `/order-inquiries/<OI>?reserve=<request id>` | The OI page, Lines tab, State preselected to "Request to reserve". A line CS has answered leaves that state, so the reserved notice opens on the lines still open and hides the ones just reserved, partly reserved or rejected. The last notice of a request opens on an empty table. | link: `order_inquiry_reserve_service.py:371`, `:478`, `:599-600`; preselect: `OrderInquiryLinesTab.tsx:183-191` |
| One OI, several notices sent together (parked) | `/order-inquiries/<OI>` | Every line of the OI, including lines nobody asked to reserve. | `order_inquiry_reserve_service.py:601-602` |
| Two or more OIs | `/order-inquiries?inquiry_no=a,b,c` | The Documents view (one row per OI), not lines. Switching to Lines shows every line of those OIs, not only the lines asked. | link: `:597-598`; Documents: `OrderInquiryHeadersList.tsx:104-115`; Lines: `order_inquiry_worklist_service.py:1528-1530` |

## Does this need a round id? No.

Every reserve email is rendered from one or more request contexts (`merged_context`,
`order_inquiry_reserve_service.py:504`), and each context is one request
(`OrderInquiryReserveRequest`, `project_so.py:1413`). The request id is already in today's
single-OI link. So the link carries the email's request ids: a 21-OI email is 21 ids, about 780
characters, fine in a link. No new column, no migration, size S.

## Rules

**R1. The email's lines** are the OI rows named by every request row of every request the email
was built from. A line asked in another request only does not belong to this email.

**R2. One OI:** the link is `/order-inquiries/<OI>?reserve=<id>` (one request, unchanged) or
`?reserve=<id>,<id>` (several requests of the same OI sent together). The OI page's Lines tab
shows exactly those lines, in every state. A new **Request** dropdown beside State (the same
multi-select) shows "Request #1" ticked; clearing it shows every line, ticking two shows both.
The State filter starts empty. The dropdown only appears when the OI has a reserve request.

**R3. Two or more OIs:** the link is
`/order-inquiries?display=lines&inquiry_no=a,b,c&reserve_request=<id>,<id>,...`. The list opens
on Lines, narrowed on the server to exactly those lines, in every state. Today's
"Order inquiries: a, b, +19" chip stays; a second chip "Reserve requests: 21" carries the
narrowing and clears it. Arriving with `inquiry_no` keeps today's defaults (Confirm: All).

**R4. Emails already sent** with the one-OI link (the 3 Nov notices) are fixed by R2 with no
resend, because their link shape does not change. Older batch links (`?inquiry_no=` alone)
keep opening the Documents view.

**R5. Nothing else changes:** the email's words, table, recipients, timing and parking.

## Real examples (dev DB `sorento_prod_1020`, names masked by crew)

| # | Case | Today | After |
| --- | --- | --- | --- |
| E1 | OI-2610-0057 has three requests, one line each: #1 CB6633-PP 80, #2 CB6638 212, #3 SRTWT2225 42 (Q-B). | Request #2's email opens on "Request to reserve": all three lines, because each is open on its own request. | Request #2's email shows the CB6638 line only. |
| E2 | OI-2609-0676 request #1 asks M3155 on three lines (78, 87, 72) (Q-B). | Once CS reserves two of them, the notice opens on the one line still open. | The notice shows all three lines with their state. |
| E3 | 1 Nov 06:38-06:40: the purchaser sent 9 requests on 9 OIs in three minutes, raised by 5 CS (Q-A). #2046 splits that send per raising CS; one email covers OI-2609-0029 (3 lines asked) and OI-2609-0742 (1 line asked). | The button opens the Documents view with those two OIs. | The button opens Lines with those 4 lines. |
| E4 | Prod 3 Nov 16:32-16:36, OI-2609-0404 #1: CS answered five lines one at a time, five notices (not on dev, dev restored 20 Oct; seeded in tests). | Each notice hid more lines; the fifth opened on "No line matches the filter". | Every notice, already sent ones included, shows the five lines with their state. |

Dev has no partial or rejected request rows (crew count: 103 rows, 0 partial, 0 rejected), so
the tests seed those shapes.

## Edge cases

| Case | Behaviour |
| --- | --- |
| Partly reserved (3 of 5) or rejected (0) | Shown, with today's State cell for that line. |
| A line asked in request #1 (rejected) and again in #2 | Shows in both emails' views. Its State cell is the line's current state; a per-request column was dropped with the scope cut. |
| A request later cancelled by the requester | Its email still opens its lines. |
| An unknown or foreign request id in `?reserve=` | Ignored: the OI page shows every line, as today without the param. |
| A malformed id in `reserve_request` on the list | 422, like the list's other id filters (`order_inquiries.py:159`). |
| `?reserve=needs_reserve` / `parked` (the list's own status, carried by the pager, AC-RF-81) | Unchanged: preselects "Request to reserve". `reserved` / `notice_parked` unchanged: no preselect. |
| The OI row named by a request row was later replaced by an amendment | The OI page still shows its line (a line matches through any row it folds, `OrderInquiryLinesTab.tsx:229-231`). The list hides cancelled rows by default, so that line is missing there until State includes Cancelled. |

## Screen change

One dropdown added to the OI page's Lines toolbar (beside State, same `SearchableMultiSelect`)
and one chip on the list's existing filter summary. No new screen. Proposed: no mock, the hand
test shows it (asked in the crew-ask).
