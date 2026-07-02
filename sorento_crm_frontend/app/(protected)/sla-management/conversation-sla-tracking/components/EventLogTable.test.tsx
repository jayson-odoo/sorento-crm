import { describe, expect, it } from 'vitest';
import { EVENT_TYPE_OPTIONS, formatEventDuration } from './EventLogTable';

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

describe('formatEventDuration (Duration column)', () => {
  // extend stores duration as WORKING DAYS; never the event_at-from_time diff.
  it('renders extend as "+N working day(s)" from stored duration', () => {
    expect(formatEventDuration({ event_type: 'extend', duration: 1 })).toBe('+1 working day');
    expect(formatEventDuration({ event_type: 'extend', duration: 3 })).toBe('+3 working days');
  });

  it('never shows a negative duration for extend even when from_time is after event_at', () => {
    // from_time = old (future) due, event_at = now -> naive diff would be negative.
    const out = formatEventDuration({
      event_type: 'extend',
      duration: 1,
      from_time: '2026-07-04T12:06:00',
      event_at: '2026-07-02T12:09:00',
    });
    expect(out).toBe('+1 working day');
    expect(out).not.toContain('-');
  });

  it('shows elapsed time for response/resolution and never negative', () => {
    const out = formatEventDuration({
      event_type: 'response',
      from_time: '2026-06-29T02:42:00',
      event_at: '2026-06-29T04:20:00',
    });
    expect(out).not.toBe('-');
    expect(out.startsWith('-')).toBe(false);
  });

  it('shows em dash for escalation (no meaningful duration)', () => {
    expect(formatEventDuration({ event_type: 'escalation', duration: null })).toBe('-');
    expect(formatEventDuration({ event_type: 'assign', duration: null })).toBe('-');
  });

  it('shows em dash for extend with no stored duration', () => {
    expect(formatEventDuration({ event_type: 'extend', duration: null })).toBe('-');
  });

  it('shows em dash for adjust / reassignment (no elapsed span)', () => {
    expect(formatEventDuration({ event_type: 'adjust', duration: 5 })).toBe('-');
    expect(formatEventDuration({ event_type: 'reassignment', duration: null })).toBe('-');
  });

  it('falls back to stored hours for response/resolution lacking from_time', () => {
    // duration stored in HOURS for response/resolution; 2h -> non-negative span.
    const out = formatEventDuration({ event_type: 'resolution', duration: 2 });
    expect(out).not.toBe('-');
    expect(out.startsWith('-')).toBe(false);
  });
});
