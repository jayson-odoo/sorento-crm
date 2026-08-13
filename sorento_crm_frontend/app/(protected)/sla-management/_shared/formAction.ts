/* -------------------------------------------------------------------------------------
 * Form SLA Undo - framework-free types + view-state resolver (PLAN-form-sla-undo.md).
 *
 * Two mechanisms share one surface:
 *   - IN-GRACE: the click created a `pending` action and NOTHING else happened. Undo
 *     deletes the row; nobody is told. Actor (or an admin) only, no permission needed.
 *   - POST-GRACE: the action already committed. Undo is a compensating reversal, is
 *     permission-gated, needs a reason, and is refused once the next stage has been
 *     acted on.
 *
 * This module is deliberately React-free so the state machine is unit-testable without
 * rendering - same split as `handlingLock.ts`.
 * ----------------------------------------------------------------------------------- */

/** Lifecycle of a row in `sla_form_actions`. */
export type FormActionStatus =
  | 'pending'
  | 'committed'
  | 'cancelled'
  | 'ineligible'
  | 'failed'
  | 'undone';

/** Why a post-grace undo is refused. Server-owned; the FE only maps it to copy. */
export type UndoBlockedReason =
  | 'no_action'
  | 'next_stage_acted'
  | 'status_moved'
  | 'not_invertible'
  | 'no_permission'
  | 'action_pending';

/**
 * The 202 body a domain route answers with instead of the updated entity when the
 * action was parked for its grace window. Every deferrable route shares this shape -
 * the dispatcher builds it in one place (`form_action_dispatch.py`).
 */
export interface DeferredFormAction {
  deferred: true;
  pending_action_id: string;
  action_key: string;
  commit_at: string | null;
  window_seconds: number | null;
}

/** Narrow a mutation result: updated entity, or "parked - offer the countdown". */
export function isDeferredFormAction(result: unknown): result is DeferredFormAction {
  return (
    !!result &&
    typeof result === 'object' &&
    (result as DeferredFormAction).deferred === true
  );
}

/** A requested-but-not-yet-executed action. Nothing in the domain has changed yet. */
export interface PendingFormAction {
  id: string;
  action_key: string;
  /** Human label for the verb, e.g. "Approval" - server-supplied so copy stays in one place. */
  action_label: string;
  requested_by_id: string;
  requested_by_name: string;
  /** Naive UTC (no tz suffix), like every other tracking timestamp. */
  commit_at: string;
  /** Full window in seconds - the bar's fixed denominator, so a remount cannot rescale it. */
  window_seconds: number;
  /** Viewer-relative: the requester, or an admin. */
  can_cancel: boolean;
}

/**
 * The two outcomes the client cannot predict: the action was voided because its premise
 * changed, or executing it failed. Surfaced once, then cleared.
 */
export interface FormActionOutcome {
  status: Extract<FormActionStatus, 'ineligible' | 'failed'>;
  reason: string;
}

/** Rides on GET /current: the most recent action that ended without applying. */
export interface LastFormActionOutcome {
  action_id: string;
  action_key: string;
  action_label: string;
  status: string;
  reason: string;
  resolved_at: string | null;
}

/**
 * The outcome to SHOW, or null. Only the action the viewer just watched counts -
 * they saw the countdown for `watchedId`, so its disappearance needs explaining;
 * an old failure from last week must not resurface on an unrelated page load.
 */
export function watchedOutcome(
  lastOutcome: LastFormActionOutcome | null | undefined,
  watchedId: string | null,
): FormActionOutcome | null {
  if (!lastOutcome || !watchedId) return null;
  if (lastOutcome.action_id !== watchedId) return null;
  if (lastOutcome.status !== 'ineligible' && lastOutcome.status !== 'failed') return null;
  return { status: lastOutcome.status, reason: lastOutcome.reason };
}

/** Rides on the form detail response so the FE never guesses (AC-PG-6). */
export interface FormUndoEligibility {
  can_undo: boolean;
  action_key: string | null;
  action_label: string | null;
  /** Naive UTC. */
  committed_at: string | null;
  blocked_reason: UndoBlockedReason | null;
  blocked_by_name: string | null;
  blocked_at: string | null;
  /** True when the committed action already told the contact something (AC-N-5). */
  tells_contact: boolean;
}

/**
 * What the detail page should render. One discriminated union covering every state in
 * AC-U-7, so a screen cannot silently omit one.
 */
export type FormActionView =
  /** No pending action and nothing undoable - today's behaviour, render nothing. */
  | { kind: 'idle' }
  /** Counting down. Other CTAs disabled; Undo available to the requester/admin. */
  | { kind: 'pending'; action: PendingFormAction }
  /** commit_at has passed; waiting for the server to confirm. Still no CTAs. */
  | { kind: 'committing'; action: PendingFormAction }
  /** The pending action was voided because the form moved underneath it. */
  | { kind: 'ineligible'; reason: string }
  /** Executing the action failed. The form is unchanged; the error is shown. */
  | { kind: 'failed'; reason: string }
  /** A committed action can be reversed. */
  | { kind: 'undoable'; eligibility: FormUndoEligibility }
  /** A committed action exists but cannot be reversed; the reason names who and when. */
  | { kind: 'undo_blocked'; eligibility: FormUndoEligibility };

export interface ResolveFormActionInput {
  pending: PendingFormAction | null;
  outcome: FormActionOutcome | null;
  eligibility: FormUndoEligibility | null;
  /** Epoch ms. Injected so tests do not depend on the wall clock. */
  now: number;
}

/** Treat a timezone-less ISO timestamp (naive UTC from the backend) as UTC. */
export function asUtc(iso: string): string {
  return /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`;
}

/**
 * Precedence matters: a pending action outranks undo eligibility, because while one is
 * in flight the previous committed action must not be reversible too - that would race
 * two writers on the same form.
 */
export function resolveFormActionView(input: ResolveFormActionInput): FormActionView {
  const { pending, outcome, eligibility, now } = input;

  if (pending) {
    const target = Date.parse(asUtc(pending.commit_at));
    return now >= target
      ? { kind: 'committing', action: pending }
      : { kind: 'pending', action: pending };
  }

  if (outcome) {
    return outcome.status === 'ineligible'
      ? { kind: 'ineligible', reason: outcome.reason }
      : { kind: 'failed', reason: outcome.reason };
  }

  if (eligibility && eligibility.action_key) {
    return eligibility.can_undo
      ? { kind: 'undoable', eligibility }
      : { kind: 'undo_blocked', eligibility };
  }

  return { kind: 'idle' };
}

/** True while the form's other business CTAs must be disabled (AC-U-2, AC-D-10). */
export function ctasDisabledForView(view: FormActionView): boolean {
  return view.kind === 'pending' || view.kind === 'committing';
}

/** Copy for a refusal. `blocked_by_name` / `blocked_at` are appended by the caller. */
export const UNDO_BLOCKED_COPY: Record<UndoBlockedReason, string> = {
  no_action: 'There is no completed action on this form to undo.',
  next_stage_acted: 'The next stage has already been acted on.',
  status_moved: 'This form has moved on since that action.',
  not_invertible: 'This action cannot be reversed automatically.',
  no_permission: 'You do not have permission to undo actions on this form.',
  action_pending: 'Another action on this form is still pending. Let it apply or withdraw it first.',
};
