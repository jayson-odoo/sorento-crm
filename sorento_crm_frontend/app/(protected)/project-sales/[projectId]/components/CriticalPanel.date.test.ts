import { describe, expect, it } from 'vitest';
import { formatCriticalDate } from './CriticalPanel';

describe('Critical card date (crew M1, PS-QUOTE-RULES)', () => {
  it('reads the stored naive-UTC stamp as UTC and shows the Malaysia date', () => {
    // 22:46 UTC on 2 Nov is 06:46 MYT on 3 Nov.
    expect(formatCriticalDate('2026-11-02T22:46:00')).toBe('03/11/2026');
  });

  it('shows nothing for a missing or unreadable stamp', () => {
    expect(formatCriticalDate(null)).toBeNull();
    expect(formatCriticalDate('not a date')).toBeNull();
  });
});
