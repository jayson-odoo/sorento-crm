/* -------------------------------------------------------------------------------------
 * Phase 1 fixtures for Form SLA Undo. One entry per AC-U-7 state so the prototype can be
 * exercised in a browser before any endpoint exists.
 *
 * Driven by `?formActionMock=<scenario>` on a form detail URL. Deleted in Phase 2 except
 * where a vitest case reuses a fixture.
 * ----------------------------------------------------------------------------------- */

import type {
  FormActionOutcome,
  FormUndoEligibility,
  PendingFormAction,
} from '../formAction';

export type FormActionScenario =
  | 'idle'
  | 'pending'
  | 'pending_not_mine'
  | 'committing'
  | 'ineligible'
  | 'failed'
  | 'undoable'
  | 'undoable_tells_contact'
  | 'blocked_next_stage'
  | 'blocked_no_permission';

export interface MockFormActionState {
  pending: PendingFormAction | null;
  outcome: FormActionOutcome | null;
  eligibility: FormUndoEligibility | null;
}

/** Naive UTC (no tz suffix), exactly as the backend serializes tracking timestamps. */
function naiveUtcIn(seconds: number): string {
  return new Date(Date.now() + seconds * 1000).toISOString().replace(/\.\d+Z$/, '');
}

function pendingAction(overrides: Partial<PendingFormAction> = {}): PendingFormAction {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    action_key: 'pr.approval_decision',
    action_label: 'Approval',
    requested_by_id: 'mock-user-1',
    requested_by_name: 'Sabrina',
    commit_at: naiveUtcIn(10),
    window_seconds: 10,
    can_cancel: true,
    ...overrides,
  };
}

function eligibility(overrides: Partial<FormUndoEligibility> = {}): FormUndoEligibility {
  return {
    can_undo: true,
    action_key: 'pr.approval_decision',
    action_label: 'Approval',
    committed_at: naiveUtcIn(-3600),
    blocked_reason: null,
    blocked_by_name: null,
    blocked_at: null,
    tells_contact: false,
    ...overrides,
  };
}

export const FORM_ACTION_FIXTURES: Record<FormActionScenario, MockFormActionState> = {
  idle: { pending: null, outcome: null, eligibility: null },

  pending: { pending: pendingAction(), outcome: null, eligibility: null },

  // Someone else's pending action: the countdown shows, the Undo button does not.
  pending_not_mine: {
    pending: pendingAction({ can_cancel: false, requested_by_name: 'Aisyah' }),
    outcome: null,
    eligibility: null,
  },

  // commit_at already passed - the bar reads "Finalizing…" and CTAs stay disabled.
  committing: {
    pending: pendingAction({ commit_at: naiveUtcIn(-2) }),
    outcome: null,
    eligibility: null,
  },

  ineligible: {
    pending: null,
    outcome: {
      status: 'ineligible',
      reason: 'the form was resolved by someone else while the action was pending',
    },
    eligibility: null,
  },

  failed: {
    pending: null,
    outcome: { status: 'failed', reason: 'the approval could not be applied' },
    eligibility: null,
  },

  undoable: { pending: null, outcome: null, eligibility: eligibility() },

  undoable_tells_contact: {
    pending: null,
    outcome: null,
    eligibility: eligibility({ tells_contact: true }),
  },

  blocked_next_stage: {
    pending: null,
    outcome: null,
    eligibility: eligibility({
      can_undo: false,
      blocked_reason: 'next_stage_acted',
      blocked_by_name: 'Farah',
      blocked_at: naiveUtcIn(-1800),
    }),
  },

  blocked_no_permission: {
    pending: null,
    outcome: null,
    eligibility: eligibility({ can_undo: false, blocked_reason: 'no_permission' }),
  },
};

export function isFormActionScenario(value: string | null): value is FormActionScenario {
  return !!value && value in FORM_ACTION_FIXTURES;
}
