/**
 * Crew pass on #2101: after Mark ready for collection the designer showed "Save
 * failed" because a draft autosave met the server's 409. Autosave runs only while
 * the server would take the write (`validate_designable`).
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { isDesignableRequest } from './RequestTagDesigner';

describe('isDesignableRequest', () => {
  it.each([
    ['designing', null, true],
    ['changes_requested', null, true],
    ['new', 'user-1', true],
    ['proof_ready', 'user-1', true],
    ['new', null, false],
    ['proof_ready', null, false],
    ['approved', 'user-1', false],
    ['ready_for_collection', 'user-1', false],
    ['collected', 'user-1', false],
    ['void', 'user-1', false],
  ])('%s with assignee %s -> %s', (status, assigned, expected) => {
    expect(isDesignableRequest({ status, assigned_to_id: assigned })).toBe(expected);
  });
});
