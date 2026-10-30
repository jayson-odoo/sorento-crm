# PLAN: Agentic W3 - approve / reject a purchase request through the agent

Status: Plan. Behaviour card posted as crew-ask; build waits on the answers, then red-first. Full track (new
write surface on a form with outward notifications; reuses the existing approval permission, no new slug, no
migration expected).
Lane AGENTIC-W3-PR-DECIDE. Builds on PR #1999 (write foundation, merged) and its plan
`PLAN-agentic-p3-writes-30oct.md` slice 5; card `CARD-agentic-p2-p3-30oct.md` row W3.

## Behaviour card

### How a purchase-request decision works today (read from the code)

- One table for both kinds: `purchase_requests` (`app/models/procurement.py:1116`), `request_type` =
  `purchase_request | sponsorship_form`. Both share one router, one detail screen and one approve slug.
- Decision fields: `approval_status` (`pending | approved | rejected`, `:1183`), `status` (moves to the same
  word on decision), `approved_at`, `approved_by` (name text), `rejected_by_id`, `approval_comments` (the
  rejection reason), `approver_user_id` (the designated approver), `requested_approval_by_user_id` (who sent it
  for approval), `revision_no`.
- Lifecycle: draft / submitted -> `set-pending-approval` (slug `send_for_approval`) -> **pending** ->
  approve / reject -> (approved only) `process` (processed_by_cs) or `close` by customer service; `void` from
  any non-terminal state.
- The in-system decision is `POST /procurement/purchase-requests/{id}/approval-decision`
  (`app/api/v1/procurement/purchase_requests.py:512`), body `{action: approved|rejected, comments}`:
  - slug `procurement.purchase_requests.approve` (`:521`); the screen shows Approve / Reject to any holder while
    the request is pending (`PurchaseRequestDetail.tsx:256,899`), not only to the designated approver;
  - handling lock `assert_can_act_on_form` (`handling_lock_service.py:156`): once the form's SLA stage is
    escalated and the lock flag is on, only the lock holder (or an admin on an unclaimed stage) may act;
  - revision fence `require_current_revision` (`revision_fence.py:214`, only when the client sends a revision);
  - router-level "only theirs" guard (`_request_own_scope.py:206`): a user limited to `view_own` gets 403 on
    every write;
  - goes through `dispatch_or_defer` (`form_action_dispatch.py:21`) as `pr.approval_decision`
    (`form_actions.py:168`): with a grace window configured and a browser caller it is parked (202,
    `pending_action_id`, `commit_at`); otherwise it runs now.
- The service `decide_approval` (`procurement_service.py:10393`) refuses a voided request, an already
  approved / rejected one ("This request has already been approved."), and one not pending. Reject needs a
  reason ("Rejection reason is required.").
- Side effects on commit (`_apply_approval_decision`, `:10457`): status written; in-app notification to the
  person who sent it for approval; a WhatsApp (Respond.io) message to the dealer contact; form-SLA event
  (`approved` / `approval_rejected`) which opens the customer-service stage; on approve the configurable
  approval automation (email).
- **Single level.** One decision per request; no multi-level chain and no per-line approval (the decision is
  for the whole request, every line).
- Grace window: per stage `form_sla_configs.grace_seconds`, else the global
  `system_settings.form_sla_grace_seconds`, which ships as **0** (`form_action_grace.py:96`). With 0 the
  decision commits at once.
- Taking it back:
  - inside the grace window: `POST /sla/form-actions/{id}/cancel` (`api/v1/sla/form_actions.py`), no slug, only
    the person who started it or an admin; nothing ran, nobody is told;
  - after commit: `POST /sla/form-actions/undo` with a mandatory reason, slug
    `sla_management.form_sla.undo_action`, guarded by `form_action_undo.evaluate`: refused when the request was
    voided, a newer action ran on it (for example customer service processed or closed it), or the stage the
    decision opened has been responded to / resolved / escalated / claimed. Undo restores the captured columns
    and notifies everyone involved.
- There is no purchase order created from a purchase request in this codebase (the request is a dealer form,
  not the procurement PR -> PO chain); "moved on" means processed / closed by customer service, voided, or the
  customer-service stage acted on.

### Rules (proposed)

1. Two general tools, both as the linked user in process (#1999 rule 5):
   - read `crm_purchase_requests_list`: requests the user may see (the route's own list + own-scope guard),
     filter by status (default pending approval), kind, text; returns number, kind, customer, title, value,
     requested by, status, `request_id`. Slug `procurement.purchase_requests.view` or `.view_own`.
   - write `crm_purchase_request_decide {request_id, decision: approve|reject, reason}`. Slug
     `procurement.purchase_requests.approve` (checked at exposure, proposal and execution, for the linked user
     AND the console operator, as #1999). Execution calls the route function
     `decide_purchase_request_approval` itself, so the handling lock, the service premise checks, the
     form-action ledger, notifications and automation are exactly the screen's. The router-level own-scope guard
     does not run on a direct call, so the tool runs the same `_request_own_scope.check` for the POST route.
2. Proposal pre-checks (nothing written): the request is pending approval, not voided, inside the user's
   reach, the handling lock lets this user act, reject has a non-empty reason. The re-check at confirm compares
   `approval_status`, `status`, `revision_no` and `updated_at`.
3. The channel is the browser one (the console is a person clicking), so the screen's configured grace window
   applies; "done" for a parked decision reads "approved, applies at HH:MM:SS unless undone".
4. Audit: the domain audit rows name the linked user with `auth_method = agent` (the #1999 actor); the
   form-action row's `requested_by_id` is the linked user; the agent ledger keeps before / after.
5. Undo: see Q1.

### Masked examples

The cloud sandbox has no access to the dev database (crew rule: never connect to a shared DB), so these are
shaped from the schema and screens, not copied rows. Real dev rows go in the hand-test script once the crew test
copy runs.

1. "Approve PR-25xxx" -> list finds one pending PR (customer C***, "Showroom display", RM 1x,xxx) -> proposal ->
   Confirm -> approved; sender notified; dealer contact gets the approval WhatsApp.
2. "Reject the sponsorship form for D*** Sdn Bhd, budget not approved this quarter" -> proposal quotes the reason
   -> Confirm -> rejected with that reason.
3. "Approve all pending from agent K***" (3 rows) -> one proposal, 3 lines, one Confirm (up to 20).
4. "Approve PR-25yyy" when it was approved on screen 2 minutes ago -> list shows approved -> the agent says so,
   no proposal. Approved between proposal and Confirm -> rejected at re-check, nothing written.
5. "Undo that" right after an approve -> Q1.

### What the user sees (owner decides wording, Q4)

Approve: `Approve purchase request PR-25xxx for C*** ("Showroom display", RM 12,500.00), sent for approval by
A***. The requester and the dealer contact will be told.`

Reject: `Reject sponsorship form SF-25xxx for D*** ("Mockup", RM 3,000.00) with the reason "Budget not
approved this quarter". The requester and the dealer contact will be told.`

After Confirm (grace window on): `Approved PR-25xxx. It applies at 14:02:31; until then Undo withdraws it and
nobody is told.` (grace off): `Approved PR-25xxx.`

### Edge cases

- Already decided / voided / not pending: refused at proposal with the service's own words; a change between
  proposal and confirm is caught by the re-check (rule 2).
- Another action already parked on the form (someone else's decision in its grace window): the route 409 "Another
  action on this form is still pending" becomes the step error.
- Escalated stage held by someone else: the handling-lock 403 text ("This form is being handled by X. Take over
  to act.") at proposal.
- Partial lines: not possible, the decision covers the whole request.
- Approver = requester: the screen allows it today (Q2).
- Reject with no reason from the user: the model asks; it never writes a reason the user did not give (Q5).
- Several requests in one ask: one proposal, one line each, steps stop at the first failure (#1999).
- Sponsorship forms: same route, slug and service (Q3).

### Questions

- **Q1 Undo.** (a) Inside the grace window: the console shows an Undo countdown on the executed step that
  withdraws the parked decision (the existing cancel, as the linked user; nothing sent). After commit: "undo
  that" makes the agent propose `crm_purchase_request_decision_undo {request_id, reason}`, confirmed like any
  write, gated by `sla_management.form_sla.undo_action` and the existing undo guardrail (refusals in its own
  words), which notifies everyone. (b) Grace-window Undo button only; reversing a committed decision stays on
  the screen. Recommend **(a)**: the grace window is seconds long, too short for a second confirm round, so it
  needs the button; after commit the guardrail and the reason already make the agent path as safe as the screen.
- **Q2 Approver = requester.** (a) Same as the screen: any holder of the approve slug may decide, including on a
  request they sent for approval; (b) the agent refuses when the linked user sent it for approval. Recommend
  **(a)**: one rule for screen and agent ("no new path"); if self-approval is wrong it is wrong on the screen
  too and belongs in its own fix.
- **Q3 Sponsorship forms.** (a) Both kinds (same route, slug, service); (b) purchase requests only. Recommend
  **(a)**: nothing differs on the server, and the summary names the kind.
- **Q4 Confirm wording.** (a) The lines above (action, number, customer, title, value, who sent it, "the
  requester and the dealer contact will be told"); (b) your wording. Recommend **(a)**: it names the outward
  message, the first one any agent write sends.
- **Q5 Reject reason.** (a) Required, taken from the user's own words and quoted in full in the proposal; the
  model asks when none was given; (b) the model may phrase the reason. Recommend **(a)**: the reason goes to the
  dealer on WhatsApp, so it must be what the user said.

## Test list (red first, Postgres)

To be filled after the answers: exposure by slug; propose writes nothing; not pending / voided / out of reach /
lock refused at proposal; confirm approves and rejects (status, comments, notifications stubbed, audit actor);
re-check after an on-screen decision; own-scope limited user refused; grace window parks and the ledger shows
`commit_at`; withdraw inside the window; undo after commit (eligible, refused when moved on, slug missing);
reason required; console operator without the slug refused.
