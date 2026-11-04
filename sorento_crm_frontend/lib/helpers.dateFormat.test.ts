/**
 * DATE-FORMAT-UNIFY: the shared formatters every screen uses. Date `dd/mm/yyyy`, range
 * `dd/mm/yyyy - dd/mm/yyyy` (the range picker's own shape), date-time `dd/mm/yyyy, h:mm am`.
 */
import { describe, it, expect } from 'vitest';
import {
  formatDateInMalaysia,
  formatDateRange,
  formatDateTime,
  formatDateTimeInMalaysia,
} from './helpers';

describe('formatDateInMalaysia', () => {
  it('zero-pads a calendar day off the wire', () => {
    expect(formatDateInMalaysia('2026-01-01')).toBe('01/01/2026');
  });
  it('reads a UTC instant in Malaysia (16:00 UTC is the next day)', () => {
    expect(formatDateInMalaysia('2026-03-31T16:00:00Z')).toBe('01/04/2026');
  });
});

describe('formatDateRange', () => {
  it('joins both ends with " - "', () => {
    expect(formatDateRange('2026-01-01', '2026-03-31')).toBe('01/01/2026 - 31/03/2026');
  });
  it('shows the one end it has', () => {
    expect(formatDateRange('2026-01-01', null)).toBe('01/01/2026');
    expect(formatDateRange(undefined, '2026-03-31')).toBe('31/03/2026');
  });
  it('returns the fallback without either end', () => {
    expect(formatDateRange(null, null)).toBe('');
    expect(formatDateRange(null, undefined, '-')).toBe('-');
  });
});

describe('date-time style is one style: dd/mm/yyyy, h:mm am/pm', () => {
  it('formatDateTimeInMalaysia', () => {
    expect(formatDateTimeInMalaysia('2026-09-30T04:23:00Z')).toBe('30/09/2026, 12:23 pm');
  });
  it('formatDateTime writes am/pm in lower case like the Malaysia helper', () => {
    expect(formatDateTime('2026-09-30T12:23:00')).toBe('30/09/2026, 12:23 pm');
    expect(formatDateTime('2026-09-30T00:05:00')).toBe('30/09/2026, 12:05 am');
  });
});
