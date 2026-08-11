import { describe, expect, it } from 'vitest';

import {
  asUtc,
  ctasDisabledForView,
  isDeferredFormAction,
  resolveFormActionView,
  UNDO_BLOCKED_COPY,
  type FormUndoEligibility,
  type PendingFormAction,
} from './formAction';

const NOW = Date.parse('2026-08-10T09:30:00Z');

function pending(overrides: Partial<PendingFormAction> = {}): PendingFormAction {
  return {
    id: 'a1',
    action_key: 'pr.approval_decision',
    action_label: 'Approval',
    requested_by_id: 'u1',
    requested_by_name: 'Sabrina',
    // Naive UTC, exactly as the backend serializes it — no trailing Z.
    commit_at: '2026-08-10T09:30:10',
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
    committed_at: '2026-08-10T08:30:00',
    blocked_reason: null,
    blocked_by_name: null,
    blocked_at: null,
    tells_contact: false,
    ...overrides,
  };
}

describe('asUtc', () => {
  it('treats a timezone-less backend timestamp as UTC', () => {
    // Without this the browser parses it as LOCAL time — 8h out in UTC+8, which would
    // make a fresh countdown read as already finished.
    expect(asUtc('2026-08-10T09:30:10')).toBe('2026-08-10T09:30:10Z');
  });

  it('leaves an already-zoned timestamp alone', () => {
    expect(asUtc('2026-08-10T09:30:10Z')).toBe('2026-08-10T09:30:10Z');
    expect(asUtc('2026-08-10T17:30:10+08:00')).toBe('2026-08-10T17:30:10+08:00');
  });
});

describe('resolveFormActionView', () => {
  it('is idle with nothing pending and nothing undoable', () => {
    expect(
      resolveFormActionView({ pending: null, outcome: null, eligibility: null, now: NOW }),
    ).toEqual({ kind: 'idle' });
  });

  it('is pending while the window is still open', () => {
    const view = resolveFormActionView({
      pending: pending(),
      outcome: null,
      eligibility: null,
      now: NOW,
    });
    expect(view.kind).toBe('pending');
  });

  it('crosses into committing once commit_at has passed', () => {
    const view = resolveFormActionView({
      pending: pending(),
      outcome: null,
      eligibility: null,
      now: NOW + 11_000,
    });
    expect(view.kind).toBe('committing');
  });

  it('prefers a pending action over undo eligibility', () => {
    // Both may be present: a previous action is undoable AND a new one is queued.
    // Offering Undo then would race two writers on the same form.
    const view = resolveFormActionView({
      pending: pending(),
      outcome: null,
      eligibility: eligibility(),
      now: NOW,
    });
    expect(view.kind).toBe('pending');
  });

  it('surfaces an ineligible outcome', () => {
    const view = resolveFormActionView({
      pending: null,
      outcome: { status: 'ineligible', reason: 'someone else resolved it' },
      eligibility: null,
      now: NOW,
    });
    expect(view).toEqual({ kind: 'ineligible', reason: 'someone else resolved it' });
  });

  it('surfaces a failed outcome', () => {
    const view = resolveFormActionView({
      pending: null,
      outcome: { status: 'failed', reason: 'could not be applied' },
      eligibility: null,
      now: NOW,
    });
    expect(view.kind).toBe('failed');
  });

  it('is undoable when the server says so', () => {
    const view = resolveFormActionView({
      pending: null,
      outcome: null,
      eligibility: eligibility(),
      now: NOW,
    });
    expect(view.kind).toBe('undoable');
  });

  it('is blocked, not idle, when a committed action cannot be reversed', () => {
    const view = resolveFormActionView({
      pending: null,
      outcome: null,
      eligibility: eligibility({
        can_undo: false,
        blocked_reason: 'next_stage_acted',
        blocked_by_name: 'Farah',
      }),
      now: NOW,
    });
    expect(view.kind).toBe('undo_blocked');
  });

  it('is idle when eligibility names no action at all', () => {
    const view = resolveFormActionView({
      pending: null,
      outcome: null,
      eligibility: eligibility({ can_undo: false, action_key: null, blocked_reason: 'no_action' }),
      now: NOW,
    });
    expect(view.kind).toBe('idle');
  });
});

describe('isDeferredFormAction', () => {
  it('narrows the shared 202 body every deferrable route answers with', () => {
    expect(
      isDeferredFormAction({
        deferred: true,
        pending_action_id: 'a1',
        action_key: 'si.project_sales_approve',
        commit_at: '2026-08-11T00:00:10',
        window_seconds: 10,
      }),
    ).toBe(true);
  });

  it('rejects an ordinary entity payload, null, and non-objects', () => {
    expect(isDeferredFormAction({ id: 'x', status: 'approved' })).toBe(false);
    expect(isDeferredFormAction(null)).toBe(false);
    expect(isDeferredFormAction(undefined)).toBe(false);
    expect(isDeferredFormAction('deferred')).toBe(false);
    // `deferred` must be the literal true, not merely truthy.
    expect(isDeferredFormAction({ deferred: 1 })).toBe(false);
  });
});

describe('UNDO_BLOCKED_COPY', () => {
  it('has copy for the pending-action refusal so the dialog never renders a raw code', () => {
    expect(UNDO_BLOCKED_COPY.action_pending).toMatch(/still pending/i);
  });
});

describe('ctasDisabledForView', () => {
  it('suppresses the form CTAs while an action is in flight', () => {
    expect(ctasDisabledForView({ kind: 'pending', action: pending() })).toBe(true);
    expect(ctasDisabledForView({ kind: 'committing', action: pending() })).toBe(true);
  });

  it('leaves them alone otherwise', () => {
    expect(ctasDisabledForView({ kind: 'idle' })).toBe(false);
    expect(ctasDisabledForView({ kind: 'undoable', eligibility: eligibility() })).toBe(false);
    expect(ctasDisabledForView({ kind: 'failed', reason: 'x' })).toBe(false);
  });
});
