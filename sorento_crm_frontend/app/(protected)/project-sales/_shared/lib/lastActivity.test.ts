import { describe, expect, it } from 'vitest';
import { describeLastActivity } from './lastActivity';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

describe('describeLastActivity', () => {
  it('gives the timestamp, not a relative label', () => {
    const result = describeLastActivity('2026-07-28T09:15:00');

    expect(result).toBe(formatDateTimeInMalaysia('2026-07-28T09:15:00'));
    expect(result).not.toMatch(/today|ago|yesterday/i);
    // A real date is in there, not a word.
    expect(result).toMatch(/\d/);
  });

  it('is null when nothing has happened, so the caller shows its own empty state', () => {
    expect(describeLastActivity(null)).toBeNull();
    expect(describeLastActivity(undefined)).toBeNull();
    expect(describeLastActivity('')).toBeNull();
  });

  it('is null rather than blank when the stamp cannot be read', () => {
    // A blank cell reads as a broken column; "No activity" reads as missing data.
    expect(describeLastActivity('not a date')).toBeNull();
  });

  it('distinguishes two stamps on the same day', () => {
    // The whole point of the change: two rows touched hours apart both said "today".
    const morning = describeLastActivity('2026-07-28T01:15:00');
    const evening = describeLastActivity('2026-07-28T13:45:00');

    expect(morning).not.toBe(evening);
  });
});
