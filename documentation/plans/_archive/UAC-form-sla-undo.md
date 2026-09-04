# Form SLA Undo - acceptance criteria

> Status: DRAFT 2026-08-10, written FIRST per methodology. Grilled with the user before any code.
> Trigger: a sponsorship form was approved by accident and could not be reversed. The approval had
> already emailed the requester, WhatsApp'd the contact, closed the approver's SLA stage and opened
> the customer-service stage with a new assignee and a running clock.
>
> Decisions locked with the user (2026-08-10):
> 1. The grace window **defers the whole action**. Nothing happens until it commits.
> 2. Every form-SLA resolve event is in scope (20 pairs, ~14 distinct service actions).
> 3. Grace is a **per-stage `grace_seconds`** with a **global default** in system settings.
> 4. Deferral applies to **in-system UI callers only**. Public token, portal, n8n and MCP commit
>    immediately and are unchanged.
> 5. In-grace Undo is the **actor's own**, no permission needed. Admin may also cancel.
> 6. Post-grace Undo is **refused once the next stage has been acted on**.
> 7. The contact-facing correction reuses the **existing structured update template**. No new
>    WhatsApp template.
> 8. **Every path writes an audit trail** - request, commit, in-grace undo, post-grace undo,
>    refusal.
>
> Decisions added 2026-08-10 after plan review:
> 9. Post-grace Undo reverts the **last committed action only**, with **no time limit**. Walking
>    further back means pressing Undo again, each press re-checking the guardrail.
> 10. A pending action **blocks the form's edit endpoints too**, not only its CTAs.
> 11. Finalize reversal (`_finalize_request` / `_finalize_complaint`) is **designed and delivered
>     in this feature**, not deferred.
>
> Correction on first survey: the draft claimed PDF generation and approval automation hang off
> finalize. They do not. `_finalize_*` does exactly three things - status + `resolved_at`/`by`,
> a Respond.io status-update message, and the `resolved` SLA event.
> `_dispatch_approval_automation` hangs off the **approval decision**, not finalize. Both
> finalize actions are therefore ordinarily invertible.

## Journey

Three actors. The system's job is to make a wrong click cheap for ten seconds, and recoverable
but deliberate after that.

### Sabrina - the approver who clicked the wrong button

Arrives at the sponsorship form detail page from her SLA task list. The system already knows the
form, her stage, her tier, and that she is the assigned approver.

1. **She clicks Approve.** The page does not jump to "Approved". A bar appears where the action
   buttons were: *"Approving SF26-0326 - 9s. Undo."* The other CTAs are disabled. The single
   decision available to her is: leave it, or take it back.
2. **She realises it was the wrong form and clicks Undo.** The bar disappears, the form returns
   to exactly the state it was in before her click. No email left the building, no WhatsApp
   reached the contact, no customer-service task was created, nobody was notified, and nothing
   went into the SLA history except an audit line saying she requested and withdrew an approval.
3. **Or she does nothing.** At zero the bar is replaced by the approved state, and only then does
   the rest of the world hear about it - requester email, contact WhatsApp, CS stage opened and
   assigned, approval automation dispatched.
4. **What she holds at the end**: either a form untouched, or an approved form identical in every
   respect to what today's Approve produces. There is no third, half-applied state.

### Mr Loo - the admin undoing an approval an hour later

Arrives from the same form. He did not make the mistake; he is fixing it. The system already
knows who approved, when, which stage it closed, which stage it opened, and whether that next
stage has been touched.

1. **He opens the form and sees an Undo action** in the actions menu, present only because he
   holds the permission and only because the last action is still reversible. If the CS PIC has
   already responded or resolved, the action is visible but disabled, and hovering says *"Cannot
   undo: Farah responded to the customer-service stage on 10 Aug 14:32."* He is told why, not
   left guessing.
2. **He confirms in a dialog** that names exactly what will happen, in plain terms: the approval
   is reversed, the customer-service task assigned to Farah is voided, the form goes back to
   Sabrina at the approval stage, and the contact is told the form is under review again. He
   types a reason. The reason is mandatory - an undo without one is unexplainable a month later.
3. **He presses Undo.** The form is back with Sabrina, her stage clock restarted, and three
   messages go out automatically: Sabrina is told the form has returned to her, Farah is told her
   task was voided and by whom, and the contact gets a correction through the existing update
   template.
4. **What he holds at the end**: a form in a coherent earlier state, and an audit entry naming
   him, the reason, and everything that was reversed.

### Farah - the CS PIC whose task disappears

She never comes to the system for this. She is told.

1. **She gets an in-app notification, and email or WhatsApp per her preferences**: her task on
   SF26-0326 was voided by Mr Loo, with his reason.
2. Her SLA task vanishes from her pending list. It does not sit there half-alive, and it does not
   count against her SLA statistics.

## Definitions

- **Deferrable action** - a (form type, event) pair that resolves an SLA stage, listed in the
  action registry. 20 pairs today.
- **Pending action** - a requested but not-yet-executed deferrable action, holding everything
  needed to run it later.
- **Grace window** - seconds between request and commit. `form_sla_configs.grace_seconds`, falling
  back to `system_settings.form_sla_grace_seconds` when NULL.
- **In-grace undo** - cancelling a pending action. Nothing to reverse because nothing ran.
- **Post-grace undo** - compensating reversal of an action that already committed.
- **Guardrail** - the check that refuses a post-grace undo when the next stage has been acted on.

## Acceptance criteria

### Deferral - request and commit

- **AC-D-1** An in-system UI call to a deferrable action whose resolved grace is `> 0` creates a
  `pending` action row and returns `202` with `{pending_action_id, commit_at, window_seconds}`.
  No domain field changes, no notification is sent, no SLA tracker is touched.
- **AC-D-2** The same action with resolved grace `0` executes immediately and returns exactly what
  it returns today. Response shape for the immediate path is unchanged.
- **AC-D-3** Public approval-token, portal, `X-API-Key`, n8n and MCP callers always take the
  immediate path regardless of configured grace. Their response shapes are unchanged.
- **AC-D-4** The scheduler sweep executes pending rows whose `commit_at` has passed, in request
  order per form, and the executed action produces **byte-for-byte the same side effects** as the
  immediate path - same status writes, same emails, same Respond.io outbox rows, same
  `emit_form_event`, same automation dispatch.
- **AC-D-5** A read of the form whose pending action is already due commits it lazily before
  serving, so a stopped scheduler delays but never loses an action.
- **AC-D-6** Commit is idempotent. A row committed by the sweep and the lazy path concurrently
  executes once. Enforced by a conditional status transition, not by hoping.
- **AC-D-7** At most one pending action per form row, enforced by a partial unique index. A second
  action attempted while one is pending is refused with `409` naming the pending action.
- **AC-D-8** A pending action whose premise has changed by commit time (form status no longer the
  one captured at request, or the stage tracker resolved by another path) is **voided, not
  executed**, with `resolution_reason='ineligible'`, and the requester is notified.
- **AC-D-10** While an action is pending, the form's **edit endpoints are blocked too**, returning
  `409` naming the pending action, so the action commits against exactly the state it was requested
  on. The FE disables the edit affordances and says why.
- **AC-D-9** Commit failure leaves the row `failed` with the error recorded, does not retry
  blindly, surfaces on the form, and never leaves the form half-mutated - the executor runs in one
  transaction per domain write, matching the existing method's own commit boundaries.

### In-grace undo

- **AC-IG-1** The requester can cancel their own pending action with no permission grant.
- **AC-IG-2** A superadmin or admin can cancel anyone's pending action. Nobody else can, including
  the assignee of the stage being resolved.
- **AC-IG-3** Cancel after `commit_at` has passed, or on an already-committed row, returns `409`
  with a message telling the user it already committed and to use Undo instead. No silent success.
- **AC-IG-4** Cancelling leaves the form in the exact state it held before the request - verified
  by asserting the domain row is unchanged, no `conversation_sla_tracking` row was created or
  mutated, no `notification_delivery` row, no `integration_log` row.
- **AC-IG-5** No notification of any kind is sent on an in-grace cancel, to anyone.

### Post-grace undo - eligibility

- **AC-PG-1** Only the **last committed** deferrable action on a form is undoable. **No time
  limit** - an action from a year ago is still reversible provided the guardrail passes. Pressing
  Undo again walks one further step back, re-checking the guardrail each time.
- **AC-PG-2** Refused when the next-stage tracker spawned by that action has been responded to,
  resolved, escalated, taken over, or reassigned. The refusal names the person and the timestamp.
- **AC-PG-3** Refused when the form's status has moved beyond what the action set - some other
  transition happened after it.
- **AC-PG-4** Requires the `sla_management.form_sla.undo_action` permission. Absent, the action is
  not rendered and the endpoint returns `403`.
- **AC-PG-5** A reason is mandatory. Empty or whitespace returns `422`.
- **AC-PG-6** Eligibility is exposed as a read - the FE never has to guess. The form detail
  response carries `{can_undo, blocked_reason, blocked_by_name, blocked_at, undoable_action}`.
- **AC-PG-7** The check is re-run server-side at execution time. A stale FE that renders an
  enabled button is refused at the endpoint.

### Post-grace undo - effect

- **AC-PGE-1** The inverse restores the domain fields the action set, to the values captured in
  the pending/history row at request time. Not to a guessed default - to the recorded prior value.
- **AC-PGE-2** The next-stage tracker spawned by the action is **voided**, not deleted. It leaves
  the assignee's pending list and is excluded from SLA statistics.
- **AC-PGE-3** The previous stage tracker is **reopened** - `is_resolved` cleared, assignee
  restored to who held it, clock restarted from the undo moment against the stage's own hours.
  Its original breach history is preserved, not rewritten.
- **AC-PGE-4** Reopening respects the handling lock: if the reopened stage was escalated
  (`escalated_at` set), it comes back escalated and locked, not silently un-escalated.
- **AC-PGE-5** Undo of an action that spawned nothing (a terminal resolve with no `next_config_id`)
  reopens the stage and voids nothing. No error.
- **AC-PGE-6** Two undos racing on one form: one wins, the loser gets `409`.
- **AC-PGE-7** Undoing a **finalize** (`_finalize_request` / `_finalize_complaint`) restores the
  captured lifecycle status and clears `resolved_at` / `resolved_by`, reopens the customer-service
  stage tracker, and sends the contact a correction. Nothing is voided - finalize spawns no next
  stage.
- **AC-PGE-8** Undoing a finalize that moved a complaint **out of** `LINKABLE_STATUSES`
  (`processed_by_cs`, `fulfilled`) returns it to a linkable status, and the delivery-order
  auto-linker treats it as linkable again on the next order-side change. The undo does not itself
  retro-link.

### Notification

- **AC-N-1** The reopened stage's assignee is notified they hold the form again, unless they are
  the person who pressed Undo.
- **AC-N-2** The voided stage's assignee is notified their task was voided, by whom, and why,
  unless they pressed Undo.
- **AC-N-3** Both follow the existing SLA notify matrix - stage-level bool AND the recipient's
  per-event channel preferences. In-app always sends.
- **AC-N-4** The contact is notified through the **existing structured update template**, in-window
  as text and out-of-window as the template, carrying the same portal link the stage's other
  messages carry. No new template is created.
- **AC-N-5** The contact is notified **only when the committed action had already told them
  something**. An undo of an internal-only transition does not message the customer.
- **AC-N-6** Every Respond.io send writes an `integration_log` row on success **and** failure, per
  the outbox rule.
- **AC-N-7** A notification failure never fails the undo. The reversal is already committed;
  failures are logged and surfaced, not raised.

### Audit

- **AC-A-1** Every request, commit, in-grace cancel, post-grace undo and refusal writes an audit
  entry naming the actor, the form, the action, the timestamp, and for undo the reason.
- **AC-A-2** SLA event logs are written for the void and the reopen, so the tracker timeline reads
  correctly afterwards. Naive datetimes are made aware before they reach `create_event_log`, per
  the Malaysia-time rule.
- **AC-A-3** The form's SLA history shows the undo as its own entry. A reader can see the approval
  happened and was reversed - the approval is not erased.
- **AC-A-4** Cancelled and voided pending rows are retained, never deleted.

### UI

- **AC-U-1** The countdown reuses the takeover countdown component. Fixed denominator derived from
  the two stored UTC stamps so it survives remount and tab switches.
- **AC-U-2** During the window the form's other CTAs are disabled, and the reason is stated.
- **AC-U-3** The countdown survives a page refresh - it is server state, not a client timer.
- **AC-U-4** At zero the FE refetches rather than assuming success, and renders whatever the
  server says, including the `ineligible` and `failed` outcomes.
- **AC-U-5** Post-grace Undo lives in the form's actions menu behind an `AlertDialog` with a
  mandatory reason field. Standard destructive-confirm copy.
- **AC-U-6** Works at 375px - the countdown bar and the dialog both.
- **AC-U-7** Every state is rendered: no pending action, pending, committing, committed, cancelled,
  ineligible, failed, undoable, blocked-with-reason.

### Settings

- **AC-S-0** There is **no** undo time-limit setting. AC-PG-1 has no window, so none is added.
- **AC-S-1** `system_settings.form_sla_grace_seconds` is the global default, editable in Settings,
  default `0` so nothing changes on deploy until it is turned on.
- **AC-S-2** `form_sla_configs.grace_seconds` is nullable per stage and overrides the global when
  set. Editable in the form-SLA config UI.
- **AC-S-3** Both new columns appear in the GET serializer **and** the update schema - the manual
  dict builders, not only the model.

## Out of scope

- Rewinding to an arbitrary point in history.
- Undoing anything that is not a form-SLA resolve event (edits, uploads, attachments).
- Undoing an action a machine caller performed through a deferred path - machines do not defer.
- Recalling a WhatsApp message. It cannot be done; a correction is sent instead.
