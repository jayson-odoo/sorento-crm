import { describe, expect, it } from 'vitest';
import { EVENT_TYPE_OPTIONS } from './EventLogTable';

describe('EventLogTable event type filter', () => {
  it('includes the reassignment event type (assignee-driven routing correction)', () => {
    const values = EVENT_TYPE_OPTIONS.map((o) => o.value);
    expect(values).toContain('reassignment');
    const reassignment = EVENT_TYPE_OPTIONS.find((o) => o.value === 'reassignment');
    expect(reassignment?.label).toBe('Reassignment');
  });

  it('keeps the existing event types', () => {
    const values = EVENT_TYPE_OPTIONS.map((o) => o.value);
    for (const expected of ['__all__', 'assign', 'adjust', 'escalation', 'response', 'resolution']) {
      expect(values).toContain(expected);
    }
  });
});
