/**
 * UI v2 phase 0, slice S2 (red first). UAC F-1, F-2 (R1: one date formatter).
 *
 * EXPORT CONTRACT:
 *   lib/format/date.ts : formatDate(input), formatDateTime(input), formatDateRange(start, end, fallback = ''),
 *                        formatTime(input)
 *   input: Date | string | number | null | undefined. A naive string ("2026-11-10T01:42:00" or
 *   "2026-11-10 01:42:00.123456") is UTC; output is Malaysia time (UTC+8). A bare "YYYY-MM-DD" is a
 *   calendar day, not shifted. Empty or invalid input gives '' (never throws, never "Invalid Date").
 *   lib/helpers.ts date helpers delegate to these, with identical output (F-2).
 */
import { describe, expect, it } from 'vitest';
import { formatDate, formatDateRange, formatDateTime, formatTime, normaliseApiDateString } from './date';
import * as helpers from '@/lib/helpers';

describe('formatDate', () => {
  it('writes dd/mm/yyyy', () => {
    expect(formatDate('2026-11-10')).toBe('10/11/2026');
    expect(formatDate('2026-01-01')).toBe('01/01/2026');
  });
  it('reads a naive UTC string in Malaysia (16:00 UTC is the next day)', () => {
    expect(formatDate('2026-03-31T16:00:00')).toBe('01/04/2026');
    expect(formatDate('2026-03-31T16:00:00Z')).toBe('01/04/2026');
  });
});

describe('formatDateTime', () => {
  it('gives dd/mm/yyyy, h:mm am from a naive UTC string in Malaysia time', () => {
    expect(formatDateTime('2026-11-10T01:42:00')).toBe('10/11/2026, 9:42 am');
    expect(formatDateTime('2026-11-10 01:42:00.123456')).toBe('10/11/2026, 9:42 am');
  });
  it('writes lower-case am/pm across noon and midnight', () => {
    expect(formatDateTime('2026-09-30T04:23:00Z')).toBe('30/09/2026, 12:23 pm');
    expect(formatDateTime('2026-09-29T16:05:00Z')).toBe('30/09/2026, 12:05 am');
  });
});

describe('formatDateRange', () => {
  it('joins both ends with " - "', () => {
    expect(formatDateRange('2026-01-01', '2026-03-31')).toBe('01/01/2026 - 31/03/2026');
  });
  it('shows the one end it has; neither end gives the fallback', () => {
    expect(formatDateRange('2026-01-01', null)).toBe('01/01/2026');
    expect(formatDateRange(undefined, '2026-03-31')).toBe('31/03/2026');
    expect(formatDateRange(null, null)).toBe('');
    expect(formatDateRange(null, undefined, '-')).toBe('-');
  });
});

describe('formatTime', () => {
  it('gives h:mm am in Malaysia time', () => {
    expect(formatTime('2026-11-10T01:42:00')).toBe('9:42 am');
    expect(formatTime('2026-11-10T12:30:00')).toBe('8:30 pm');
  });
});

describe('empty or invalid input gives an empty string', () => {
  it.each([null, undefined, '', 'not a date'])('%s', (bad) => {
    expect(formatDate(bad as never)).toBe('');
    expect(formatDateTime(bad as never)).toBe('');
    expect(formatTime(bad as never)).toBe('');
  });
});

describe('lib/helpers date functions return the same strings as lib/format/date (F-2)', () => {
  const samples = ['2026-11-10', '2026-03-31T16:00:00Z', '2026-11-10T01:42:00', '2026-09-30T04:23:00Z'];
  it('formatDateInMalaysia === formatDate', () => {
    for (const s of samples) expect(helpers.formatDateInMalaysia(s)).toBe(formatDate(s));
  });
  it('formatDateTimeInMalaysia === formatDateTime', () => {
    for (const s of samples.slice(1)) expect(helpers.formatDateTimeInMalaysia(s)).toBe(formatDateTime(s));
  });
  it('helpers.formatDateRange === formatDateRange', () => {
    expect(helpers.formatDateRange('2026-01-01', '2026-03-31')).toBe(formatDateRange('2026-01-01', '2026-03-31'));
    expect(helpers.formatDateRange(null, null, '-')).toBe(formatDateRange(null, null, '-'));
  });
});

describe('normaliseApiDateString', () => {
  it('turns the API space separator and microseconds into an ISO string every browser parses', () => {
    expect(normaliseApiDateString('2026-11-10 01:42:00.123456')).toBe('2026-11-10T01:42:00.123');
  });
  it('leaves an ISO string alone', () => {
    expect(normaliseApiDateString('2026-11-10T01:42:00Z')).toBe('2026-11-10T01:42:00Z');
  });
});
