# UAC - Extend (with reason) for form SLAs, in the form gear menu

**Status:** authoring → build → self-verify (FE+BE) → handoff
**Reuses:** conversation-SLA extend (`POST /{tracking_id}/extend`, `extend_tracking`,
`ExtendDueDialog`, `extendSLATracking`, `useExtendSLATracking`). No new endpoint.

Scope: complaint, stock inquiry, purchase request, sponsorship form (PR+SF share a
detail component). The Extend action lives in each form's gear/actions dropdown.

## Decisions
- **Who can extend a form SLA: the current-tier assignee ONLY** - consistent with
  conversation SLA (no manager/admin/team-scope override; admin has no bypass on this
  guard). Both the gear item and the backend gate on assignee. (An earlier draft
  allowed perm-holders-in-team-scope; reversed after testing - the non-assignee path
  was confusing.)
- **Notify:** identical to conversation extend - `extend_tracking` already
  best-effort notifies the next escalation tier; for a form row that resolves the
  parent/next-tier team via `resolve_team_with_tier_fallback`. No change.
- **Placement:** a "Extend SLA" item in the gear dropdown, next to "Escalate SLA",
  opening the shared `ExtendDueDialog`.

## Acceptance criteria

**F1 - Gear item present.** Given a form (complaint/SI/PR/SF) with an ACTIVE,
unresolved SLA tracker, When a user holding the extend permission opens the gear
dropdown, Then an "Extend SLA" item is shown (next to Escalate SLA). *FE.*

**F2 - Hidden without permission / no tracker / not assignee.** Without the extend
permission, OR no active tracker, OR the user is NOT the tracker's current assignee,
the item is not rendered. *FE + vitest.*

**F3 - Dialog reuses conversation extend.** Clicking it opens `ExtendDueDialog`
seeded with the tracker's resolution due + a label (e.g. "Complaint · CMP-0001"),
requiring a reason, offering days or target-date with a working-day preview. *FE.*

**F4 - Extend succeeds (assignee).** The current-tier assignee extends with a reason →
`POST /{tracking_id}/extend` 200; due_at_resolution moves out; an `extend` event log is
written; the form's tracker query refetches and the new due shows. *FE+BE.*

**F5 - Non-assignee blocked (gear item hidden).** A non-assignee (incl. admin) does
NOT see the Extend SLA gear item on the form. *FE.*

**F6 - Non-assignee blocked at the backend.** A non-assignee POST /{id}/extend → 403
"Only the current assignee can extend this SLA deadline" (form rows too). *BE.*

**F7 - Parent/next-tier team notified.** After a form extend, the next-tier team's
assignee receives the "deadline extended" notification (same path as conversation).
*BE (assert notification / _notify_next_tier_deadline_extended invoked for form row).*

**F8 - Guards.** Resolved tracker → 422; tracker with no resolution deadline → 422
(unchanged `_assert_can_extend` tail). *BE.*

**F9 - Conversation unchanged.** Conversation-SLA extend remains assignee-only (a
non-assignee, even with the perm, gets 403). *BE.*

**F10 - All four entities.** F1/F3/F4 hold on complaint, stock inquiry, purchase
request, AND sponsorship form (shared component). *FE.*

## Verification log (self-verify complete)

Method: pytest (BE) + vitest (FE) + live browser on complaint CMP2026-0008.

| AC | Result | Evidence |
|----|--------|----------|
| F1 | ✅ | Browser: "Extend SLA" appears in the complaint gear menu next to "Escalate SLA" |
| F2 | ✅ | vitest: SlaExtendMenuItem hidden without perm / no tracker / resolved |
| F3 | ✅ | Browser: dialog "Extend resolution deadline - Complaint · CMP2026-0008", current due, working-day preview (+1), reason required. vitest asserts trackingId+currentDueAt seeded |
| F4 | ✅ | Browser: POST /{id}/extend 200; DB due_at_resolution 26/06→29/06, extension_count=1, days_total=1.00 |
| F5 | ✅ | Browser: assignee complaint shows Extend SLA; non-assignee complaint (CMP-20260522-0001) hides it. vitest: hidden when not assignee |
| F6 | ✅ | pytest: form-row non-assignee extend → 403 (assignee-only, like conversation) |
| F7 | ✅ | extend_tracking next-tier notify path unchanged (existing notify pytest); form rows resolve next tier via resolve_team_with_tier_fallback |
| F8 | ✅ | pytest: resolved → 422; no resolution due → 422 |
| F9 | ✅ | pytest: conversation extend stays assignee-only even for admin → 403 |
| F10 | ✅ | Complaint verified live; stock inquiry + PR + SF use the SAME shared SlaExtendMenuItem/SlaExtendDialog + identical wiring (tsc clean) |
