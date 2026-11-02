# Behaviour card: PS-QUOTE-VIEWS (view count on the proposal/quotation sign link)

Source: owner 2 Nov 2026 ~21:20 MYT ("View count, yes, we need to do."), Kay item 5 ("Viewed: x times").
Plan: `PLAN-quote-views-2nov.md` (same folder). Code read on origin/main 46de2f6d.

## What exists today (facts)

- The customer link is `/quotation-sign/{token}` (FE `app/(auth)/quotation-sign/[token]/page.tsx`). The page is
  a CLIENT component (`QuotationSignClient`) that fetches `GET /api/v1/public/quotation-sign/{token}`
  (`app/api/v1/public/quotation_sign.py:35-50`) with plain `fetch`, never a staff bearer
  (`quotationSignService.ts`, header comment point 1).
- The token resolves to ONE issue (R1, R2 ...) of a document (`get_issue_by_sign_token`,
  `project_quotation_document_service.py:1091-1124`). Opening records nothing; the issue row keeps only
  `accepted_at` and `changes_requested_at` (`models/projects.py:1286-1300`).
- The salesperson opening the link in WhatsApp is already a project feed event (`record_whatsapp_opened`,
  `project_quotation_document_service.py:1054-1088`); that is the salesperson, not the customer.
- Proposal vs quotation (PS-PROPOSAL-QUOTATION #2097): both kinds keep sharing this sign page and the issue
  table, so a view recorded per ISSUE works for both without knowing the kind.

## Rules after this lane

1. **What counts as a view.** The sign page, once it has loaded the quotation, sends one small
   `POST /api/v1/public/quotation-sign/{token}/view` with a random browser id it keeps in local storage.
   The GET stays read-only (link scanners and prefetchers call GETs).
2. **Unique per browser per 30 minutes.** A second open from the same browser on the same issue within 30
   minutes of its last COUNTED view is not counted (refresh, tab switch, phone lock).
3. **Bots excluded.** WhatsApp, Gmail, Outlook, Telegram, Slack, Facebook, Twitter/X, LinkedIn, Skype and
   generic crawler previews fetch the page HTML and do not run the page script, so they never send the beacon.
   The beacon also refuses a known preview/bot user agent (belt and braces, for scanners that do run script).
4. **Staff excluded.** Before sending, the page asks NextAuth (`/api/auth/session`, same origin) whether the
   browser is signed in to the CRM; a signed-in browser sends nothing. So the salesperson testing the link,
   or management checking it, does not inflate the count.
5. **What is stored** (new table `projects.quotation_issue_views`, one small additive migration): `issue_id`,
   `company_id`, `viewed_at`, `device` (`mobile` / `tablet` / `desktop`, derived from the user agent, which is
   then thrown away), `visitor_hash` (SHA-256 of the random browser id, first 32 hex). **No IP address, no
   user agent, no location, no name is stored.** The browser id is random and identifies a browser, not a
   person; it is used only for the 30-minute de-duplication.
6. **What the salesperson and management see.** On the proposal/quotation page, under the page header with the
   other read-only facts: **"Viewed 3 times, last 2 Nov 2026, 9:41 pm"** for the revision the customer holds
   now (latest issue), or "Not viewed yet" once issued. Hidden before the first issue (no link exists).
   Below it, a "View log" list (newest first, up to 50): time, revision (R1/R2 or A/B per #2097), device.
7. **Abuse.** The beacon is rate limited per token through the shared fail-open limiter (same as
   `amendment-request`), so a script cannot fill the table.
8. **Expired or unknown link:** the beacon answers the same 404 as the page and records nothing.

## Examples (dev data shape; cloud sandbox has no prod copy, real rows on request)

- A. PRJQ-2026-0003-R1 sent on WhatsApp at 9:00 pm. WhatsApp builds its preview (no script) -> 0 views. The
  customer taps it on an iPhone at 9:05 -> "Viewed 1 time, last 2 Nov 2026, 9:05 pm"; log: 9:05 pm, R1,
  mobile.
- B. Same customer refreshes at 9:10 and again at 9:20 -> still 1. Opens again at 9:40 (35 min after 9:05)
  -> 2. Forwards it to their boss, who opens it on a laptop at 9:12 -> counted (different browser) -> 3.
- C. The salesperson clicks the link from the CRM on their own laptop while signed in -> not counted.
- D. Salesperson revises and issues R2 -> the header shows R2's views ("Not viewed yet"); the log still lists
  the R1 rows marked R1.
- E. A proposal under #2097 (PRJQ-2026-0005-A) and its later quotation (QT-2026-0001-R1): each its own
  document, each its own count.

## Edge cases

- Customer opens an OLD revision's link after R2 went out: the view is recorded on R1 (the log shows R1), the
  header count (R2) does not move.
- Local storage blocked (private mode): the page makes a fresh id each load, so a refresh can count again;
  acceptable (rare, and the 30-minute rule still collapses same-load re-renders).
- Signed-in check fails or times out: the beacon is sent (the customer is never signed in to the CRM; a missed
  exclusion only costs a staff view, never a customer one).
- Accepted quotation re-opened by the customer: still counted (they looked at it).

## Touches shared with parallel lanes

- PS-PROPOSAL-QUOTATION (#2097): same sign page and document page. This lane adds one hook call in
  `QuotationSignClient.tsx` and one read-only block under the document page header; it does not touch
  labels or kinds. The revision label comes from the issue (`our_ref_text`), so their A/B lettering shows as
  is.
- No other PS lane touches the sign router or `quotation_issues`.

## Questions (each with a recommendation)

Q1. Which count goes in the header? (a) The current revision only, with the log showing all revisions.
(b) All revisions summed. Rec (a): the salesperson acts on whether the customer read what they hold now.

Q2. Who sees the view log? (a) Everyone who can open the document (salesperson + management), no new
permission. (b) A new "view log" permission for management only. Rec (a): it holds nothing sensitive (time,
revision, device), and a new permission is machinery for no evidenced need.

Q3. Notify the salesperson on a first view? (a) No, count only (this lane). (b) In-app alert on the first view
of each revision. Rec (a): not asked for; name it as a follow-up if Kay wants it.

Q4. Unique window. (a) 30 minutes per browser per revision, fixed in code. (b) A System Settings value.
Rec (a): one number, no evidence anyone will tune it.
