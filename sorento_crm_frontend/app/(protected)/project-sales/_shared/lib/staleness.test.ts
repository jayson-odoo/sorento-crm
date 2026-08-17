/**
 * S5b - the ladder's wording (AC-H6).
 *
 * The copy IS the feature here, so it is what gets pinned. Two properties matter: each rung
 * says what happens next (not just that something is wrong), and the Unattended rung states
 * plainly that nothing has been reassigned - the sentence that stops a salesperson thinking
 * the system took their project away.
 */
import { describe, expect, it } from 'vitest';
import { describeStaleness } from './staleness';

function project(overrides: Record<string, unknown> = {}) {
  return {
    stale_level: 0,
    stale_reason: null,
    stale_since: null,
    days_since_last_activity: 0,
    ...overrides,
  } as Parameters<typeof describeStaleness>[0];
}

describe('describeStaleness', () => {
  it('says nothing at all when the project is fine', () => {
    expect(describeStaleness(project())).toBeNull();
  });

  it('asks for an update at the first rung', () => {
    const result = describeStaleness(
      project({ stale_level: 1, stale_reason: 'no_activity', days_since_last_activity: 30 }),
    );
    expect(result?.label).toBe('Needs an update');
    expect(result?.detail).toContain('30 days');
    expect(result?.detail).toMatch(/set the next action/i);
    expect(result?.tone).toBe('notice');
  });

  it('says management has been copied at the second rung, because they have', () => {
    const result = describeStaleness(
      project({ stale_level: 2, stale_reason: 'no_activity', days_since_last_activity: 60 }),
    );
    expect(result?.label).toBe('Falling behind');
    expect(result?.detail).toMatch(/management has been copied/i);
  });

  it('states that nothing has been reassigned at the Unattended rung', () => {
    const result = describeStaleness(
      project({ stale_level: 3, stale_reason: 'no_activity', days_since_last_activity: 90 }),
    );
    expect(result?.label).toBe('Unattended');
    expect(result?.detail).toMatch(/ask to take it over/i);
    expect(result?.detail).toMatch(/nothing has been reassigned/i);
    expect(result?.tone).toBe('critical');
  });

  it('distinguishes a missed promise from plain silence', () => {
    const overdue = describeStaleness(
      project({ stale_level: 1, stale_reason: 'overdue_task', days_since_last_activity: 0 }),
    );
    expect(overdue?.detail).toMatch(/next action is overdue/i);
    expect(overdue?.detail).not.toMatch(/nobody has touched it/i);
  });

  it('does not invent a day count it was not given', () => {
    const result = describeStaleness(
      project({ stale_level: 1, stale_reason: 'no_activity', days_since_last_activity: null }),
    );
    expect(result?.detail).toMatch(/gone quiet/i);
    expect(result?.detail).not.toMatch(/null|NaN|undefined/);
  });
});
