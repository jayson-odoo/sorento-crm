# Behaviour card: OI reserve rounds (OI-RESERVE-ROUND, 3 Nov)

Status: Plan. Card v1, waiting on owner answers (Q1-Q5). Size M, LEAD pattern. Expected track:
standard (one additive migration: one nullable column plus a template-data update), no auth/RBAC change.

crew-lane: OI-RESERVE-ROUND

## What the owner asked (3 Nov 19:15)

When CS reserves after a "Request CS to reserve", the notice goes back to the requester (Joey)
and the CS. Clicking "Open order inquiry" in that notice shows what was reserved **in this
round**. Prod 3 Nov 16:32-16:36 sent five separate emails in four minutes, one per line, each
reading "Reserved: OI-2609-0404 #1 - SO414932 - Eling reserved stock for OI-2609-0404 #1".
Owner on WhatsApp, 30 Oct, about a 21-OI request: "should add up to 21 OIs, I see she did not
reserve some, maybe in incoming, but hard to see".

## First answer: do we track reserve rounds today?

**Partly. One OI's request is tracked end to end. A request covering several OIs is not tracked as
one thing. Every Reserve click mails at once, and the email button cannot show what was reserved.**

| Fact | Where |
| --- | --- |
| A request is `OrderInquiryReserveRequest`, one per OI, addressed as `OI-x #ordinal`. It records requester, time, note, state (requested -> reserved / cancelled) and `parked_at`. | `sorento_crm_backend/app/models/project_so.py:1413-1461` |
| Its lines are `OrderInquiryReserveRequestRow`: `qty_requested`, CS's `qty_reserved` (NULL while open, 0 = rejected), `reason`, `warehouse_id`, plus `notified_qty` (the figure purchasing was last told) and `notice_parked_at/by`. | `project_so.py:1464-1515` |
| Each CS reserve / unreserve action is an `OrderInquiryReserveEvent` (kind, qty, actor, time). | `project_so.py:1526-1564`, written at `order_inquiry_reserve_service.py:1104,1129,1159` |
| The reserved stock itself is an `OrderInquiryLink` with `reserve_request_row_id` set ("Reserved @ CODE"). | `order_inquiry_reserve_service.py:1091-1102` |
| **There is no batch id.** `create_request` is per OI (`POST /order-inquiries/{id}/reserve-requests`, `orderInquiryReserveService.ts:58-66`). A 21-OI request is 21 separate requests: each is parked, then one "send all parked" mails them all (`order_inquiry_reserve_service.py:1417-1442`). That send is grouped per (To, raising CS, requester) at mail time only (`_groups`, `order_inquiry_reserve_service.py:1350-1378`), and the group is never stored. | as cited |
| **Every Reserve click mails.** `commit_request` is one call per OI per click and queues one `order_inquiry_reserved` email per requester (`order_inquiry_reserve_service.py:1168-1216`). Eling reserving five lines of OI-2609-0404 one at a time gave five emails. The OI list's bulk Reserve makes one call per OI (`OrderInquiriesClient.tsx:1319-1338`), so N OIs still give N emails. | as cited |
| Batching already exists but is opt-in. With `park_notice` the commit parks the notice (`_stamp_notice`, `:1220-1244`), and "send all parked reserves" mails them grouped (`:1444-1468`). CS must choose it on each commit, and on 3 Nov nobody did. | as cited |
| **Recipients:** To the requester, Cc the raiser of the OI. The CS who reserved is not on it. | `alembic/versions/oirs_0001_reserve_requests.py:390-404` |
| **The button cannot show this round.** One OI's link is `/order-inquiries/<oi>?reserve=<request id>` (`order_inquiry_reserve_service.py:478`). The page only uses the param to preselect the "Reserve requested" state filter (`OrderInquiryLinesTab.tsx:183-191`), and a line CS has just answered is no longer in that state. So the link opens on the lines still open and hides the ones just reserved. Several OIs link to `?inquiry_no=a,b,c` on the list (`:597-598`): every line of those OIs, with no round column. | as cited |

**The 31 Oct full-table ruling** (RESERVE-EMAIL-FULL-TABLE) is merged on main as #2046 (`1fc0fab9`).
`oisn_0002_full_table.py` moves both templates to the full table with no "#n" in the subject
(`:187-191`). The 3 Nov prod subject still reads "Reserved: OI-2609-0404 #1 - SO414932", which is
the pre-#2046 subject (`oisn_0002_full_table.py:99`, frozen old value). So on 3 Nov 16:32 prod
either ran a release without #2046, or the guarded data migration skipped an admin-edited
template. The 30 Oct "... and 15 more" email predates #2046. **Check on prod:**
`oi-reserve-round-dev-examples.sql` Q-F. This lane builds on #2046's table, so the answer changes
how the hand-test reads, not the design.

## Real examples (dev data)

Crew runs `oi-reserve-round-dev-examples.sql` (read-only) and pastes the output. Each example
below names the query it comes from. The rows get filled in once the output arrives.

| # | Shape | Query |
| --- | --- | --- |
| E1 | OI-2609-0404: one request, lines answered one by one by Eling, one email each | Q-C, Q-G |
| E2 | Joey's 30 Oct multi-OI send (~21 OIs, split by raising CS): which lines are reserved, rejected, still open | Q-A, Q-B |
| E3 | Partial reserve (0 < reserved < asked) with reason | Q-B |
| E4 | Line open or rejected while a PO/SPO/incoming link covers it ("maybe in incoming") | Q-E |
| E5 | Same OI line asked in two rounds (round 1 rejected/partial, round 2 asks the balance) | Q-D |

## Rules (proposed)

**R1. A round is one request email.** When the requester presses Send (single OI) or "send all
parked" (several OIs), each email that goes out to CS is one round. #2046 already splits these
emails by raising CS, so a round holds one requester's OIs for one raising CS. Every request in
that email gets the same `round_id`, a new nullable UUID column on
`order_inquiry_reserve_requests` stamped at send. A parked request has no round until it is sent.
This needs no new table: whether the summary has gone out is already readable per line
(`notified_qty` against `qty_reserved`). Requests sent before this lane are backfilled with
`round_id = id`, which makes each old OI request a round of its own.

**R2. One summary per round, not one per click.** A CS reserve or reject on a line in a round
parks that line's notice instead of mailing it, so `park_notice` becomes the default. The round's
summary email goes out when **every line in the round is answered** (reserved, partial or
rejected) or withdrawn. CS can also press **Send summary now** at any time (see Q1). The existing
"send all parked reserves" gains a round grouping and sends one email per round.

**R3. The summary goes To the requester, Cc the raising CS and every CS who reserved or rejected
a line in that round** (see Q2). There is one raiser per round (R1), so each CS still sees only
their own OIs (the 31 Oct rule).

**R4. The summary lists the WHOLE round**, every line asked, not only the lines the last click
touched. The columns are the #2046 table: OI NO, SO date, SO no, item, qty, requested, STATUS,
delivery, project/customer, reason. STATUS for this round is one of: `Reserved N`,
`Partial N of M`, `Rejected` (reason under it), `Not reserved yet` (the line was still open when
CS pressed Send now), `Withdrawn` (the requester cancelled it). The heading counts the lines, for
example "21 OIs, 34 lines: 25 reserved, 3 partial, 4 rejected, 2 not reserved yet". There is no
TOTAL QTY and no cap. Email, preview and attachment are the same rows (the tally rule).

**R5. The button opens the round.** Both the request email and the summary link to the OI list's
Lines view filtered by `?round=<round_id>`. That view shows exactly the email's lines, each with
three extra columns: **Requested this round**, **Reserved this round** (the line's answer on this
round's request row, so an earlier or later round's qty never leaks in), and **Status this round**
(the R4 words). Its Balance column already exists. The filter shows as a clearable chip, for
example "Round: Joey 30 Oct 14:05". Every column sorts server-side, and the round's status filter
is multi-select. A round of one OI opens the same list view, so there is one destination.

**R6. A change after the summary** (CS amends a reserved qty, or answers a line after Send now)
parks a notice on that round. The next Send summary (or the round completing) mails a short
"Changed" email for that round, listing only the lines whose figure moved since the last mail.
`notified_qty` already tracks this (see Q4).

**R7. Nothing changes in how CS reserves.** The same Reserve and Reject on the OI detail page and
on the OI list. Only the mailing time and the link change.

## Edge cases

| Case | Behaviour |
| --- | --- |
| Partial reserve (3 of 5) | STATUS "Partial 3 of 5", reason required (existing rule). The line counts as answered for R2. Balance shows what is left to buy. |
| Rejected (Reserve 0) | STATUS "Rejected" with reason (#2046 wording). Counts as answered. |
| Line covered by incoming PO/SPO, CS leaves it | It stays open, so the round stays open and no summary goes out until CS rejects it ("on incoming SPO-x") or presses Send now (Q1, Q3). The round view shows the line's other cover so the requester can see why (Q3). |
| Requester cancels the request part-way | Open lines become `Withdrawn`. If nothing is left open, the round is complete and the summary goes out, unless every line was withdrawn and none answered, in which case no email. |
| Second request on the same OI (#2) | A new round. A line asked in both rounds appears in both round views, each with that round's own answer. Round 1's view keeps "Rejected" even after round 2 reserves the balance. |
| CS reserves a line from round 2 while round 1 is still open on another line of the same OI | `commit_request` already answers the line's newest open request (`order_inquiry_reserve_service.py:914-927`), so the answer belongs to round 2 only. |
| Two CS answer lines in one round | Both are Cc'd on the summary (R3). Each event already records its own actor. |
| Amend that lands back on the figure already mailed | No notice. `_stamp_notice` already drops it (`:1234-1236`). |
| Old requests (before this lane) | `round_id = id`. The old link `?reserve=<request id>` redirects to `?round=<same id>`, so old emails open the round view. |
| Round with lines across several CS raisers | Cannot happen: a round is one email, and #2046 already splits emails per raising CS. |

## Questions for the owner (max 5)

**Q1. When does the round summary go out?**
(a) When every line in the round is answered or withdrawn, plus a **Send summary now** button
for CS. (b) Every Reserve click (today: 5 emails in 4 minutes). (c) (a) plus an automatic
end-of-day flush (18:00) for rounds left half-answered.
**Recommendation: (a).** It is one email per round, and Send now covers lines CS cannot answer
yet. (c) adds a scheduled job for a case the OI list's existing "parked notices" count already shows.

**Q2. Who gets the summary?**
(a) To the requester, Cc the raising CS and every CS who reserved or rejected a line in the round.
(b) To the requester, Cc only the CS who reserved (drop the raiser). (c) Today's: requester and
raiser, without the CS who reserved.
**Recommendation: (a).** You named the requester and "the CS". The raising CS keeps the copy they
get today, and the reserving CS (Eling) gets a record of what she sent.

**Q3. Lines CS leaves open because stock is incoming: how are they seen?**
(a) The round view (and the email's REASON cell for open lines) shows the line's other cover, for
example "SPO-2610-0012 x5 incoming". CS still answers the line or presses Send now. (b) The system
answers such lines automatically as "Covered by incoming". (c) Nothing extra, the line just reads
"Not reserved yet".
**Recommendation: (a).** It shows why a line was not reserved (your 30 Oct "hard to see") without
the system deciding for CS.

**Q4. CS changes a reserved qty after the summary went out.**
(a) One short "Changed" email for that round, with only the moved lines, sent with the next Send
summary. (b) No email; the round view shows the new figure. (c) Re-send the whole round summary.
**Recommendation: (a).** Purchasing may already have bought the balance. A change must reach them,
and an email of only the changed lines is easy to read.

**Q5. Should the REQUEST email's button also open the round view** (the same lines, before CS
answers), replacing today's `?inquiry_no=` list?
(a) Yes, one round view for both emails. (b) No, keep the request button as is.
**Recommendation: (a).** One destination. The request email's "exactly this email's OIs" rule
(31 Oct) becomes exactly this email's lines, which is narrower and still true.

## Out of scope

- How CS picks lines or quantities (OI-BULK-RESERVE, RESERVE-REQ-PICK).
- The request email's own table (#2046 stands).
- Any change to stock links, balance or coverage maths.
