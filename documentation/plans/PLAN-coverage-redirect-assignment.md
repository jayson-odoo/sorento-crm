# PLAN - Coverage redirects assignment/escalation (not just notify)

**Status:** Designed (grilled 2026-06-24). Not started.

Today "Coverage" (`NotificationSubscription`: subscriber covers target, optional `expires_at`)
only fans out **notify copies** to the coverer. Change: during the coverage window, SLA
work that would route to the covered colleague is **assigned directly to the coverer** - no
manual takeover. Colleague on leave → I hold their incoming work automatically.

## Decisions (locked)

1. **Forward-only.** Only NEW routing during the window redirects. The colleague's
   already-open tasks stay with them (use takeover for those). No sweep on coverage create.
2. **Redirect everything (all routing surfaces):** form-SLA initial assignment, form-SLA
   escalation, conversation-SLA initial assignment, conversation-SLA escalation, AND manual
   reassign. Whenever a resolved assignee == a covered user, swap to their coverer.
3. **Per-coverage mode toggle (`redirect_assignments`), single REDIRECT coverer enforced.**
   Coverage is per-row either **auto-assign** (`redirect_assignments=True`) or **notify-only**
   (`False`, the original fan-out behaviour). The column defaults to `false` (server_default),
   so existing rows stay notify-only - backward-compatible. Enforcement in `subscribe()`:
 - Self-coverage → 422.
 - Adding redirect=ON → 409 if ANY active non-expired coverage exists for that target by a
     different subscriber (an auto-redirect coverer must be the SOLE coverer). Message names
     the current coverer + until-date.
 - Adding redirect=OFF → 409 ONLY if an active redirect=ON coverage exists for that target
     (can't notify-cover someone already auto-redirected). Otherwise allowed - MULTIPLE
     notify-only coverages per target are permitted.
 - Same subscriber re-subscribing the same target → upsert (updates the mode + expiry),
     never a conflict.
   `active_coverer_for()` returns only `redirect_assignments=True` coverers (≤1 by the rule
   above), so only auto-assign coverages redirect routing; notify-only keep fanning out copies.
4. **Round-robin fairness.** When RR picks the covered user, the cursor still advances as if
   they were assigned (so rotation is fair when they return) - only the resulting
   `assigned_to_id` is swapped to the coverer. Do NOT skip them in the rotation.
5. **One hop, no chains.** Resolve coverage exactly once. If the coverer is themselves
   covered, the task still lands on the (first) coverer - no transitive redirect (avoids
   loops). Guard self-coverage (coverer == target rejected at subscribe).
6. **Coverage end = forward-only revert.** When `expires_at` passes or the coverage row is
   deleted, new routing goes back to the colleague; tasks the coverer already holds stay.
7. **Notification + audit.** The coverer is now the real assignee → gets the normal
   assignment/escalation notification (no separate coverage-copy needed, and with single-
   coverer there are no other subscribers to fan out to). The assignment/escalation/reassign
   **event log records the redirect** (e.g. reason/context "covering for <colleague>") so the
   trail shows why it landed on the coverer. Title/body may prefix "(covering for <name>)".

## Backend

### Coverage service (`app/services/coverage_subscription_service.py`)
- `active_coverer_for(target_user_id) -> Optional[str]`: the single active, non-expired
  coverer's user id (earliest-created; single-coverer is enforced so there's ≤1).
- `subscribe(...)`: before create, if another active non-expired coverage exists for the same
  `target_user_id` (different subscriber) → raise `AppException(409/422)` naming the current
  coverer + until. Also reject `subscriber_id == target_user_id` (self-coverage).

### Redirect helper (new, in sla_service or a small shared module)
- `resolve_assignee_with_coverage(db, assignee: dict) -> tuple[dict, Optional[str]]`:
  given a resolved assignee dict (`{id, email, name, respond_user_id}`), if
  `active_coverer_for(assignee["id"])` returns a coverer, build the coverer's assignee dict
  (reuse `AccessAgentService._user_info`) and return `(coverer_dict, covered_user_id)`; else
  `(assignee, None)`. One hop.

### Inject points (apply the helper right before `assigned_to_id` is set)
- `form_sla_service._start_for_config` (~line 663, after RR/override resolves `assignee`).
- `form_sla_service._escalate_tracker` (~line 412/424).
- `sla_service.get_escalation_assignee_for_tier` (~line 1832) - or at the `escalate_tracking`
  caller, so conversation escalation redirects.
- Conversation-SLA initial assignment (n8n create path) - wherever the initial `assigned_to_id`
  is resolved.
- `sla_service.reassign` (~line 1400) - redirect the manual target too (decision 2).
  (Takeover assigns to the initiator, not "to" the covered user → no redirect there.)
- RR: the swap happens AFTER `get_next_assignee` advanced the cursor (decision 4) - so leave
  `get_next_assignee` untouched; swap the returned dict.

### Event log
When redirected, stamp the assignment/escalation/reassignment event log with the coverage
context (covered-for user id/name in `reason` or a structured note) - best-effort, never
blocks the routing. Wrap any naive-UTC datetimes with `_to_aware_utc()` per the gotcha.

## Frontend
- Coverage card (`Coverage` component): update the helper copy from "Get notified about a
  colleague's SLA assignments while you cover for them" → reflect that work is **routed** to
  you (e.g. "Their SLA tasks are assigned to you while you cover for them").
- `Add` error: surface the single-coverer rejection via `extractApiError` + toast (already the
  pattern); no new UI.
- Optional: a small "covering for <name>" chip on redirected pending-task rows (nice-to-have,
  not required).

## Tests
- pytest: `active_coverer_for` (single, expired excluded, none); `subscribe` rejects 2nd active
  coverage + self-coverage; redirect helper swaps when covered, passes through when not, one-
  hop only; form assignment redirects; form escalation redirects; conversation escalation
  redirects; reassign redirects; RR cursor still advances to the covered user (fairness);
  expired/ended coverage → no redirect; event log records covered-for.
- vitest: coverage card copy + Add error toast on duplicate.

## Three-phase
P1 (copy + error states already mostly exist) → P2 backend redirect + tests → P3 review.
