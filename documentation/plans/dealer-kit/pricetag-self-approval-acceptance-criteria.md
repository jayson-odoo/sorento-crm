# UAC: Price tag self-approval (PRICETAG-SELF-APPROVAL)

Plan: `PLAN-pricetag-self-approval-02nov.md`.

- AC1 Submit lands at `proof_ready`, no form SLA tracker opened, `assigned_to_id` NULL.
- AC2 Approve (normal flow) with a valid doc writes a new `PageVersion`, pins tag data, moves to `approved`,
  queues one export whose requesting user is the contact when nobody is assigned.
- AC3 Approve (normal flow) without a doc: 422 `DOC_REQUIRED`, nothing written.
- AC4 Approve with a placement whose `request_tag_id` is not this request's: 422, no version, status unchanged.
- AC5 Approve on an escalated `proof_ready` request approves marketing's latest version; a sent doc writes nothing.
- AC6 Edit (revise) at `approved`: allowed with Settings > Portal revisions off and past any cap; writes a
  revision row; status back to `proof_ready`; assignee cleared; no new SLA tracker.
- AC7 Edit refused at `ready_for_collection`, `collected`, `void`, and while escalated in marketing's hands.
- AC8 Download refused after an edit until re-approved; after re-approval the newest export is served.
- AC9 Escalate requires a note; clears the assignee; stores the note as a
  review comment; with an active form SLA config the request ends at `designing` under the config's assignee.
- AC10 Escalate with no active config leaves the request `new`, unassigned and claimable.
- AC11 Escalate refused from `ready_for_collection` / `collected` / `void` / already escalated.
- AC12 Claim and design save refused (409) for his own proof; the CRM offers no Design action on it.
- AC13 No data change at deploy: a submitted `new` / `designing` / `changes_requested` request, or a
  `proof_ready` with an assignee, reads as with marketing; an `approved` one is his to edit or escalate.
- AC14 Portal form: at `proof_ready` (normal flow) shows the generated tag with Approve, Edit, Escalate; at
  `approved` shows Download, Edit, Escalate; escalated and in marketing's hands shows today's review actions only.
