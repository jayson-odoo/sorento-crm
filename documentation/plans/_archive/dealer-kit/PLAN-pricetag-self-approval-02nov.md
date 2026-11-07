# PLAN: Price tag self-approval, edit after approval, escalate to configured assignee

Status: implemented (#2101 merged 4 Nov after owner hand test OK; follow-up PR carries the crew re-pass items).
Track: normal (no migration, but the diff is over 300 lines and changes the portal's write routes).
Lane: PRICETAG-SELF-APPROVAL (#2101). Sibling lane: PRICETAG-TEMPLATE-PER-PRODUCT (#2100).
Source: "Feedback on Price Tag" meeting 2 Nov 2026 + owner rulings 2 Nov ~21:10.
UAC: `pricetag-self-approval-acceptance-criteria.md` (same folder).

## Journey (owner rulings, 2 Nov)

- The salesperson fills the request, sees the generated tag and approves it himself. Marketing
  leaves the normal flow.
- After approval he can edit and re-approve. Each edit is a revision. No cap.
- When he finds a problem he cannot fix himself, he presses Escalate and writes a note. The request goes
  to the assignee the form SLA config names (Akmal today; not hard-coded). Only then does marketing act.

## What exists today (origin/main 46de2f6d, verified)

- Status graph `new -> designing -> proof_ready -> approved -> ready_for_collection -> collected`,
  with `changes_requested` looping back (`price_tag_request_service.py:57-95`).
- Submit sets `new`, emits the form SLA `submit` event, and `auto_assign_from_tracker` copies the
  tracker's assignee and moves the request to `designing` (`portal_price_tag.py:448-518`,
  `price_tag_request_service.py:1161-1213`). The assignee comes from the form SLA config, never a name.
- Marketing draws the tag sheet in the CRM designer; `PUT .../design` writes a `PageVersion`
  (`price_tag_requests.py:1257-1395`). Approve moves the request to `approved` and auto-queues the PDF from the latest
  version (`price_tag_request_service.py:1353-1366`); the export refuses a request with no user id
  (`tag_sheet_export_service.py:142`).
- A post-submit edit goes through the generic revision engine (`portal_revision_service.revise`,
  `:1584`), gated by Settings > Portal revisions (default cap 2, price tag row off), refused at
  `approved` (`_PTAG_ADAPTER.terminal_statuses`, `:613`), and it restarts the SLA flow to `new`
  (`:611`), which in the new flow would hand the request back to marketing.
- The portal shows the design only from `proof_ready` (`PriceTagRequestForm.tsx:132`).

## Owner ruling 3 Nov 14:10: one step from the create screen

The form has no plain Submit. A new request or a reopened draft ends in **Approve** (the draft is
submitted and approved in one call, `POST .../submit-approve {doc}`, the sheet built from its saved
tags) or **Escalate to marketing** (`POST .../submit-escalate {note}`, the same escalation as R6).
Everything that can refuse (completeness, the sheet, a missing template, an empty note) runs before
the draft stops being a draft. Approve is off, with the reason beside it, when the live preview
reports an item with no template. The two-click path (submit, then approve on the detail page) is
what an EDIT leads to now: an edited request returns to Design Ready and is approved there. The plain
`/submit` route stays for the API but the form no longer calls it.

## Design change after the card: no column, no migration

"Marketing holds it" is DERIVED, not stored (`PriceTagRequestService.is_with_marketing`): a submitted
request at `new` / `designing` / `changes_requested`, or a `proof_ready` with an assignee. The normal
flow never puts a submitted request at those statuses, and its own proof has nobody assigned. So
`escalated_at` / `escalated_by_contact_id` and the backfill are dropped: in-flight work keeps its place
with no data change (R10), and there is no migration to order against #2100's. Where the card says
"escalated", read "with marketing". The escalation itself is recorded by the review comment (who, when,
the note), the status change (ORM audit) and the form SLA tracker it opens. Edit and escalate both clear
the assignee, which is what hands the request back (edit) or lets the config pick (escalate).

## Rules (the behaviour card)

R1. **Submit, normal flow.** Submit validates as today, then lands the request at `proof_ready`
   ("waiting for your approval"). It emits NO form SLA event, assigns nobody and rings nobody in
   marketing. The salesperson gets the "submitted" confirmation as today.

R2. **The generated tag.** The tag sheet is built on the client from the request's stored tags
   (one placement per `price_tag_request_tags` row, on the line's template) with #2100's
   `buildRequestSheet` and its `POST /lookups/tag-preview {request_id}` data (merged into this branch;
   #2100 merges first).

R3. **Approve, his own proof.** `POST .../approve` carries `{doc}`. Under a row lock (two clicks at
   once: the second gets 409) the server checks it is a tag sheet of THIS request's tags (at most 50
   sheets; no tag placed more often than its quantity), then REBUILDS it: positions and sheets come from
   the client, each placement's template, layers and size come from the line's published template,
   bound to the line's product or set, and every other key is dropped (review B2: what a tag says is not
   the client's to write). A line with no template: 422 `NO_TEMPLATE`. The page is created if missing,
   every tag is pinned to master data as of the approval, the rebuilt sheet becomes the page's next
   `PageVersion` ("Approved by <name>"), the request moves to `approved` and the PDF is queued. The
   export's requesting user falls back to the contact id when nobody is assigned.

R4. **Edit.** Allowed from his own proof (`proof_ready`, no assignee) and `approved` (either flow).
   Refused from `ready_for_collection` / `collected` / `rejected` / `void`, and while marketing holds the
   request (`new` / `designing` / `changes_requested`, or a `proof_ready` with an assignee). It uses the
   existing revise path: reason required, a `portal_form_revisions` row with the post-edit snapshot,
   `revision_no + 1`. For price tags it **does not read Settings > Portal revisions** (no cap, always
   on) and **does not restart the SLA flow**: the request goes back to `proof_ready` with the assignee
   cleared, so it is his again. Any open tracker from an earlier escalation is voided as today.

R5. **PDF after an edit.** The old PDF stops downloading the moment the edit lands (download allowed
   only at `approved` / `ready_for_collection` / `collected`). Only an export rendered from the page's
   LATEST version counts, for the download, the button's status and the "already in flight" reuse
   (review B1), so between re-approval and the new PDF the button reads Preparing, never the old file.

R6. **Escalate.** Allowed from his own proof and `approved`. Note required. Effect: the note is
   stored as a general review comment (marketing's designer already lists them), the assignee is cleared,
   status goes to `new`, any open SLA stage from an earlier escalation is voided (review S1), the form SLA
   `submit` event opens a fresh stage, and `auto_assign_from_tracker` moves it to `designing` under the
   config's assignee, the same code submit used to run. No active config, or no assignee on it: it stays
   `new` for a Claim. The staff `/transition` route refuses `new`: Escalate is the only way back there.

R7. **After escalation** it is today's loop exactly: marketing designs, marks proof ready, and the
   salesperson approves (no `doc`; marketing's saved version is what gets approved and printed) or
   requests changes.

R8. **Marketing's side.** On his own proof the CRM offers no Claim and no Design (only Void), and the
   design routes refuse it (409). The CRM list still shows every request with its status.

R9. **Audit trail.** Status, assignee and line changes are captured by the ORM audit listeners
   (`audit_service.register_audit_listeners`); each edit is a `portal_form_revisions` row with reason and
   snapshot (the Revisions tab); each approval is a `PageVersion` naming who approved it; each escalation
   is a review comment row (who, when, the note) plus the SLA stage it opens.

R10. **Requests in flight at deploy.** No data change:
   - Submitted and with marketing (`new`, `designing`, `changes_requested`, or `proof_ready` with an
     assignee): they finish exactly as today. A claimed one stays claimed, one in design stays in
     design, a proof stays ready for his approval (approve with no `doc`, marketing's version).
   - `approved`: untouched. Its PDF stays. He can now edit (then self-approve a generated tag) or
     escalate.
   - `ready_for_collection` / `collected` / `rejected` / `void` / drafts: untouched.

## Go-live (with #2100)

Production has no product-template links at deploy, and since #2100 a product with no link has no
template at all: its line cannot be self-approved ("No tag template yet for <code>. Escalate it to
marketing.") and would have to be escalated. So marketing bulk-assigns templates (Tag Templates >
Assign to products) before release, crew tells the owner, and self-approval is announced to
salespeople only after the links are seeded.

## Edge cases

- Approve with no `doc` on a normal-flow request: 422 `DOC_REQUIRED`. Approve WITH a `doc` on an
  escalated request: the doc is ignored (marketing's version is the one that was reviewed).
- A placement pointing at another request's tag: 422, nothing written.
- Double-tap Approve: the second call meets `approved` and gets 409 (transition table), no second version.
- Revise stale guard (`expected_revision_no`) works as today.
- Office print: `approved -> ready_for_collection` unchanged; once the office has printed, edits and escalations
  are refused (the paper exists).
- No form SLA tracking for normal-flow requests (nobody is on the clock). SLA reports count escalations only.

## The office collection step (owner, 2 Nov ~21:40)

"Ready for collection" is not really in use: the salesperson prints. Nothing is removed. The status and
its columns stay in the graph and in the data; it is still reachable only for a request whose Printing
answer is "Office prints", and the auto-collect sweep still closes any that exist. Edit and Escalate
are refused from it (Q4 a), behind `is_with_salesperson`, the one check to change for (b).

## Questions for the owner (with recommendations)

Q1. In-flight `new` requests nobody has claimed yet: (a) stay with marketing (backfilled as escalated),
    (b) go back to the salesperson for self-approval. Rec (a): nobody's request changes hands silently;
    marketing just finishes it.
Q2. Submit then Approve as two clicks on the same screen, or one "Submit and approve" click? Rec two clicks.
    The approve screen builds from the stored tags, so the PDF is what was on screen. One click would need
    a second, server-side builder.
Q3. Settings > Portal revisions price tag row: hide it, since price tags no longer read it (no cap,
    always on)? Rec yes.
Q4. Edit or escalate after the office marked it ready for collection: (a) refused, (b) allowed and the
    collection is undone. Rec (a): the tags are already printed.

## Files (both price tag lanes)

This lane: `price_tag_request_service.py` (transitions, is_with_marketing / is_with_salesperson,
self_approve, escalate, design gate), `portal_price_tag.py` (`/submit`, `/approve`, new `/escalate`,
download status check, `self_review` / `can_escalate` on the detail body), `portal_revision_service.py`
(price tag policy and no restart), `revision_configs.py` (price tag row hidden), FE
`PriceTagSelfApproval.tsx` (new), `PriceTagRequestForm.tsx` post-submit actions, the portal service,
`priceTagRequestActions.ts` (CRM offers nothing on his own proof).
#2100: `_add_lines` template field, lookups, form Preview section, `request-tags.ts` builder.

## Follow-up after merge (crew re-pass, 4 Nov)

- Approve on the draft form is full width in the stacked 375 layout, like Save Draft and Escalate.
- The CRM Design card hint says "Open the designer to draw the tags." on a request somebody holds,
  "Claim the request..." only when nobody does.
- One Approve took 27 s on the crew copy (others 2.6-8 s, a retime 9 s). Profiled: the server work of
  `submit-approve` is about 0.4 s (two preview resolves of about 0.04 s, pins, version, export
  enqueue). The rest is the salesperson's WhatsApp, sent inline by `transition_status` through
  `respond_messaging_service`: a Respond.io window lookup and a send, each with a 15 s timeout
  (`integration_service.py`), the lookup cached for 45 s. The crew copy routes Respond.io through a
  dead proxy, so a cold approve waits on the timeouts and a retry inside 45 s skips the lookup. In
  production it is one fast round trip. Trigger for changing it: if Respond.io latency shows up in
  production, send the salesperson's message after the response (a background task) for every price
  tag transition at once, not only Approve.

## Owner hand test #2138 (5 Nov)

- Escalate to marketing checks the form first (dealer, lines, template pick, numbers: the same
  checks and messages as Approve) and marks what is missing on the form; nothing opens until it
  passes (`readyToFinish` in `PriceTagRequestForm.tsx`).
- When it passes, a centred dialog (`EscalateDialog` in `PriceTagSelfApproval.tsx`, the app's
  `Dialog`) asks "What needs fixing?" (required) and Need by (the shared `DatePicker`, dd/mm/yyyy,
  a date after today), with Send to marketing and Cancel, full width at 375.
- Need by left the draft form for that dialog. A draft keeps its stored value and the dialog opens
  on it; Approve still sends the stored value. A revision (no Escalate there) keeps the field on the
  form. The portal read view and the CRM detail still show Need by.
- The other two Escalate buttons (gear menu, own-proof card) open the same dialog with the note only:
  the request already exists and its Need by was set when it was created or escalated.
