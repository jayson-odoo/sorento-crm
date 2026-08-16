import { describe, it, expect } from 'vitest';

import { slaHandler } from './slaHandler';

/**
 * Who handled the row (feedback 2026-08-16, item 1). Resolving a conversation
 * ticket NULLs `assigned_to_id` by design, so "Assigned to" on a resolved row
 * is empty by construction - and empty is exactly what the reader is trying to
 * find out.
 */
describe('slaHandler', () => {
  it('an open row names its assignee', () => {
    expect(slaHandler({ is_resolved: false, assigned_user_name: 'Aisyah' })).toEqual({
      prefix: 'Assigned to',
      name: 'Aisyah',
    });
  });

  it('falls back through the assignee shapes the API sends', () => {
    expect(
      slaHandler({ assigned_user: { name: null, email: 'ben@sorento.test' } }),
    ).toEqual({ prefix: 'Assigned to', name: 'ben@sorento.test' });
  });

  it('a resolved row names its resolver instead', () => {
    expect(
      slaHandler({
        is_resolved: true,
        assigned_user_name: null,
        resolved_by_user_name: 'Charissa',
      }),
    ).toEqual({ prefix: 'Resolved by', name: 'Charissa' });
  });

  it('never prints a UUID: the backend falls back to the raw id column', () => {
    expect(
      slaHandler({
        is_resolved: true,
        resolved_by_user_name: '8f14e45f-ceea-467a-9c8b-0f3f6a1d5c22',
      }),
    ).toEqual({ prefix: 'Resolved by', name: null });
  });

  it('names nobody rather than guessing when there is nothing to name', () => {
    expect(slaHandler({ is_resolved: false })).toEqual({
      prefix: 'Assigned to',
      name: null,
    });
  });
});
