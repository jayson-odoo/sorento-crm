# PLAN: Price tag self-approval, edit after approval, escalate to configured assignee

Status: Plan (behaviour card posted for owner answers, build started on the parts the questions do not block).
Track: normal (one additive migration; not small fix track).
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

## Rules (the behaviour card)

R1. **Submit, normal flow.** Submit validates as today, then lands the request at `proof_ready`
   ("waiting for your approval"). It emits NO form SLA event, assigns nobody and rings nobody in
   marketing. The salesperson gets the "submitted" confirmation as today.

R2. **The generated tag.** The tag sheet is built on the client from the request's stored tags
   (one placement per `price_tag_request_tags` row, on the line's template), using the builder and the
   `POST /lookups/tag-preview` data that #2100 delivers. Until #2100 lands, this lane's screen builds with the
   existing `defaultTemplateFor` / `starterTemplateFor` + `autoArrange`, the same code marketing's
   designer opens a fresh request with.

R3. **Approve, normal flow.** `POST .../approve` carries `{doc}`. The server checks that it is a tag
   sheet and that every placement's `request_tag_id` is one of THIS request's tags (else 422), creates the
   page if it is missing, pins each tag's data (master data as of the approval), writes the doc as the
   page's next `PageVersion` ("Approved by <name>"), moves the request to `approved`, and queues the PDF.
   So the PDF is exactly what he approved. The export's requesting user falls back to the contact id
   when nobody is assigned (as the portal export route already does).

R4. **Edit after approval.** Allowed from `proof_ready` (normal flow) and `approved` (either flow).
   Refused from `ready_for_collection` / `collected` / `rejected` / `void`, and refused while
   marketing holds an escalated request (`new` / `designing` / `changes_requested` / `proof_ready` with
   `escalated_at` set). This uses the existing revise path: reason required, a `portal_form_revisions` row
   with the post-edit snapshot, `revision_no + 1`. For price tags it **does not read Settings > Portal
   revisions** (no cap, always on) and it **does not restart the SLA flow**: the request goes back to
   `proof_ready` for his own approval, and `escalated_at` is cleared (the request is his again). Any open tracker
   from an earlier escalation is voided as today.

R5. **PDF after an edit.** The old PDF stops being downloadable the moment the edit lands (download
   allowed only at `approved` / `ready_for_collection` / `collected`). Re-approve writes a new
   `PageVersion` and a new export; download serves the newest completed export, which is the
   re-approved one.

R6. **Escalate.** Allowed from `proof_ready` (normal flow) and `approved` (either flow). Note
   required. Effect: `escalated_at` + `escalated_by_contact_id` set, the note stored as a general review
   comment (marketing's designer already lists them), status to `new`, form SLA `submit` event emitted,
   and `auto_assign_from_tracker` moves it to `designing` under the config's assignee, the same code as
   today's submit. No active config, or no assignee on it: the request stays `new` and marketing claims it
   (unchanged Claim path).

R7. **After escalation** it is today's loop exactly: marketing designs, marks proof ready, and the salesperson
   approves (no `doc`; marketing's saved version is what gets approved and printed) or requests changes.

R8. **Marketing's side.** Claim and the designer are refused for a request that is not escalated
   (409 `NOT_ESCALATED`): in the normal flow there is nothing for marketing to do. The CRM list still shows
   every request, with an Escalated marker, so the office can see what exists.

R9. **Audit trail.** Every status, `escalated_at` and line change is captured by the ORM audit listeners
   (`audit_service.register_audit_listeners`); each edit is a `portal_form_revisions` row with reason and
   snapshot (the Revisions tab); each approval is a `PageVersion` naming who approved it; the escalation
   note is a review comment row.

R10. **Requests in flight at deploy** (migration backfill, no status changes):
   - Submitted, not terminal, in marketing's hands (`new`, `designing`, `changes_requested`,
     `proof_ready`): `escalated_at = created_at`, so they finish exactly as today with marketing.
     A claimed one stays claimed, one in design stays in design, a proof stays ready for his approval
     (approve with no `doc`, marketing's version).
   - `approved`: untouched (`escalated_at` NULL). Its PDF stays. He can now edit (then self-approve
     a generated tag) or escalate.
   - `ready_for_collection` / `collected` / `rejected` / `void` / drafts: untouched.

## Edge cases

- Approve with no `doc` on a normal-flow request: 422 `DOC_REQUIRED`. Approve WITH a `doc` on an
  escalated request: the doc is ignored (marketing's version is the one that was reviewed).
- A placement pointing at another request's tag: 422, nothing written.
- Double-tap Approve: the second call meets `approved` and gets 409 (transition table), no second version.
- Revise stale guard (`expected_revision_no`) works as today.
- Office print: `approved -> ready_for_collection` unchanged; once the office has printed, edits and escalations
  are refused (the paper exists).
- No form SLA tracking for normal-flow requests (nobody is on the clock). SLA reports count escalations only.

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

This lane: `price_tag_request_service.py` (transitions, submit/approve/escalate), `portal_price_tag.py`
(`/submit`, `/approve`, new `/escalate`, download status check), `portal_revision_service.py` (price tag
policy and restart), `price_tag_requests.py` (claim/design gate), new alembic migration (`escalated_at`,
`escalated_by_contact_id` + backfill), schemas, `PriceTagRequestForm.tsx` post-submit actions.
#2100: `_add_lines` template field, lookups, form Preview section, `request-tags.ts` builder.
