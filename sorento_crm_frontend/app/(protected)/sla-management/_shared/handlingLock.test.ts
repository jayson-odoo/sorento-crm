import { describe, it, expect } from 'vitest';
import {
  businessCtasEnabledForState,
  resolveHandlingLockState,
  type HandlingLockState,
  type HandlingLockTracker,
  type ResolveHandlingLockInput,
} from './handlingLock';

function tracker(partial: Partial<HandlingLockTracker> = {}): HandlingLockTracker {
  return {
    id: 'trk-1',
    source_entity_type: 'complaint',
    current_tier: 2,
    escalated_at: '2026-07-01T00:00:00',
    is_resolved: false,
    handled_by_id: null,
    handled_by_name: null,
    handled_at: null,
    assigned_to_id: 'assignee-1',
    ...partial,
  };
}

function input(partial: Partial<ResolveHandlingLockInput> = {}): ResolveHandlingLockInput {
  return {
    activeTracker: tracker(),
    currentUserId: 'me',
    isEligible: true,
    isAdmin: false,
    flagEnabledForType: true,
    ...partial,
  };
}

describe('resolveHandlingLockState', () => {
  it('not_escalated when the flag is off for the type (P1-7)', () => {
    expect(resolveHandlingLockState(input({ flagEnabledForType: false }))).toBe('not_escalated');
  });

  it('not_escalated when there is no active tracker', () => {
    expect(resolveHandlingLockState(input({ activeTracker: null }))).toBe('not_escalated');
  });

  it('not_escalated when the tracker is tier 1 (not escalated)', () => {
    expect(
      resolveHandlingLockState(
        input({ activeTracker: tracker({ current_tier: 1, escalated_at: null }) }),
      ),
    ).toBe('not_escalated');
  });

  it('not_escalated when never escalated even at a tier-2 START (project_sales)', () => {
    // project_sales begins at tier 2 with no tier 1; a fresh form has escalated_at=null
    // and must NOT show the handling-lock banner.
    expect(
      resolveHandlingLockState(
        input({ activeTracker: tracker({ current_tier: 2, escalated_at: null }) }),
      ),
    ).toBe('not_escalated');
  });

  it('not_escalated when the active tracker is resolved', () => {
    expect(
      resolveHandlingLockState(input({ activeTracker: tracker({ is_resolved: true }) })),
    ).toBe('not_escalated');
  });

  it('unclaimed when escalated + eligible + no holder (P1-1)', () => {
    expect(resolveHandlingLockState(input({ activeTracker: tracker({ handled_by_id: null }) }))).toBe(
      'unclaimed',
    );
  });

  it('mine when escalated + I hold the lock (P1-2)', () => {
    expect(
      resolveHandlingLockState(input({ activeTracker: tracker({ handled_by_id: 'me' }) })),
    ).toBe('mine');
  });

  it('mine even for an admin who happens to hold the lock (precedence)', () => {
    expect(
      resolveHandlingLockState(
        input({ isAdmin: true, isEligible: false, activeTracker: tracker({ handled_by_id: 'me' }) }),
      ),
    ).toBe('mine');
  });

  it('other_holds when escalated + eligible + someone else holds (P1-3)', () => {
    expect(
      resolveHandlingLockState(
        input({ activeTracker: tracker({ handled_by_id: 'jane', handled_by_name: 'Jane' }) }),
      ),
    ).toBe('other_holds');
  });

  it('not_eligible when escalated + not eligible + not admin (P1-4)', () => {
    expect(
      resolveHandlingLockState(
        input({
          isEligible: false,
          isAdmin: false,
          activeTracker: tracker({ handled_by_id: 'jane', handled_by_name: 'Jane' }),
        }),
      ),
    ).toBe('not_eligible');
  });

  it('admin_unclaimed when escalated + admin + no holder (P1-5)', () => {
    expect(
      resolveHandlingLockState(
        input({ isAdmin: true, isEligible: false, activeTracker: tracker({ handled_by_id: null }) }),
      ),
    ).toBe('admin_unclaimed');
  });

  it('admin_other_holds when escalated + admin + someone else holds (P1-6)', () => {
    expect(
      resolveHandlingLockState(
        input({
          isAdmin: true,
          isEligible: false,
          activeTracker: tracker({ handled_by_id: 'jane', handled_by_name: 'Jane' }),
        }),
      ),
    ).toBe('admin_other_holds');
  });

  it('compares holder/current-user ids as strings (mixed types)', () => {
    expect(
      resolveHandlingLockState(
        input({ currentUserId: '42', activeTracker: tracker({ handled_by_id: '42' }) }),
      ),
    ).toBe('mine');
  });
});

describe('businessCtasEnabledForState — truth table', () => {
  const enabled: HandlingLockState[] = ['not_escalated', 'mine', 'admin_unclaimed'];
  const disabled: HandlingLockState[] = [
    'unclaimed',
    'other_holds',
    'not_eligible',
    'admin_other_holds',
  ];

  it.each(enabled)('CTAs ENABLED for %s', (state) => {
    expect(businessCtasEnabledForState(state)).toBe(true);
  });

  it.each(disabled)('CTAs DISABLED for %s', (state) => {
    expect(businessCtasEnabledForState(state)).toBe(false);
  });
});
