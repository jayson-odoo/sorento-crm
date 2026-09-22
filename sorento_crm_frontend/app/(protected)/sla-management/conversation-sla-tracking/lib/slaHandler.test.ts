import { describe, it, expect } from 'vitest';

import { slaHandler } from './slaHandler';

/**
 * Who is assigned to the row (feedback 2026-08-16, item 1; superseded by
 * owner ruling S4, 23 Sep 2026, PLAN-keep-assignee-on-resolve-22sep). Resolve
 * keeps `assigned_to_id` for audit now, so "Assigned to" names the assignee
 * whether the row is open or resolved - who resolved it is a separate fact
 * shown elsewhere (the detail header subtitle), not this helper's job.
 */
describe('slaHandler', () => {
  it('an open row names its assignee', () => {
    expect(slaHandler({ assigned_user_name: 'Aisyah' })).toEqual({
      prefix: 'Assigned to',
      name: 'Aisyah',
    });
  });

  it('falls back through the assignee shapes the API sends', () => {
    expect(
      slaHandler({ assigned_user: { name: null, email: 'ben@sorento.test' } }),
    ).toEqual({ prefix: 'Assigned to', name: 'ben@sorento.test' });
  });

  it('a resolved row still names its assignee, not its resolver', () => {
    // A real row (from either the list or the detail fetch) carries is_resolved
    // and resolved_by_user_name alongside the assignee fields; assigned via a
    // variable, not a literal, so it matches what callers actually pass.
    const row = {
      assigned_user_name: 'Ben Lim',
      is_resolved: true,
      resolved_by_user_name: 'Charissa',
    };
    expect(slaHandler(row)).toEqual({ prefix: 'Assigned to', name: 'Ben Lim' });
  });

  it('never prints a UUID: the backend falls back to the raw id column', () => {
    expect(
      slaHandler({
        assigned_to: '8f14e45f-ceea-467a-9c8b-0f3f6a1d5c22',
      }),
    ).toEqual({ prefix: 'Assigned to', name: null });
  });

  it('names nobody rather than guessing when there is nothing to name', () => {
    expect(slaHandler({})).toEqual({
      prefix: 'Assigned to',
      name: null,
    });
  });
});
