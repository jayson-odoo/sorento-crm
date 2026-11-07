import { describe, expect, it } from 'vitest';
import {
  COLUMN_SIZES,
  changeTone,
  codesText,
  formatChange,
  formatCompactRm,
  formatRm,
  periodRange,
  previousLabel,
} from './leaderboardFormat';

// 12:00 Kuala Lumpur on the given date (UTC+8, no DST).
const kl = (date: string) => new Date(`${date}T04:00:00Z`);

describe('periodRange', () => {
  it('this month runs from the 1st to today, against the same days of last month', () => {
    expect(periodRange('this_month', kl('2026-11-07'))).toEqual({
      from: '2026-11-01', to: '2026-11-07', previousFrom: '2026-10-01', previousTo: '2026-10-07',
    });
  });

  it('this month clamps the previous end to a shorter month', () => {
    expect(periodRange('this_month', kl('2026-03-31')).previousTo).toBe('2026-02-28');
  });

  it('this month in January looks back into December', () => {
    expect(periodRange('this_month', kl('2026-01-15'))).toMatchObject({
      previousFrom: '2025-12-01', previousTo: '2025-12-15',
    });
  });

  it('last month is the whole month, against the month before', () => {
    expect(periodRange('last_month', kl('2026-11-07'))).toEqual({
      from: '2026-10-01', to: '2026-10-31', previousFrom: '2026-09-01', previousTo: '2026-09-30',
    });
    expect(periodRange('last_month', kl('2026-01-07'))).toEqual({
      from: '2025-12-01', to: '2025-12-31', previousFrom: '2025-11-01', previousTo: '2025-11-30',
    });
  });

  it('this quarter runs from the quarter start, against the same days of the previous quarter', () => {
    expect(periodRange('this_quarter', kl('2026-11-07'))).toEqual({
      from: '2026-10-01', to: '2026-11-07', previousFrom: '2026-07-01', previousTo: '2026-08-07',
    });
    expect(periodRange('this_quarter', kl('2026-02-10'))).toMatchObject({
      from: '2026-01-01', previousFrom: '2025-10-01', previousTo: '2025-11-10',
    });
  });

  it('YTD runs from 1 January, against the same dates last year (29 Feb becomes 28 Feb)', () => {
    expect(periodRange('ytd', kl('2026-11-07'))).toEqual({
      from: '2026-01-01', to: '2026-11-07', previousFrom: '2025-01-01', previousTo: '2025-11-07',
    });
    expect(periodRange('ytd', kl('2028-02-29')).previousTo).toBe('2027-02-28');
  });

  it('takes today in Kuala Lumpur, not UTC', () => {
    // 20:00 UTC on 31 Oct is already 1 Nov in Kuala Lumpur.
    expect(periodRange('this_month', new Date('2026-10-31T20:00:00Z')).from).toBe('2026-11-01');
  });
});

describe('formatting', () => {
  it('formats RM with 2 decimals', () => {
    expect(formatRm(1856856.61)).toBe('RM 1,856,856.61');
    expect(formatRm(0)).toBe('RM 0.00');
  });

  it('formats the change with a sign and 1 decimal, and a dash when there is none', () => {
    expect(formatChange(63.6)).toBe('+63.6%');
    expect(formatChange(-10.4)).toBe('-10.4%');
    expect(formatChange(0)).toBe('0.0%');
    expect(formatChange(null)).toBe('-');
  });

  it('colours up green, down red, none muted', () => {
    expect(changeTone(1)).toContain('emerald');
    expect(changeTone(-1)).toContain('destructive');
    expect(changeTone(null)).toContain('muted');
  });

  it('compacts RM for the phone podium', () => {
    expect(formatCompactRm(1856856.61)).toBe('1.86m');
    expect(formatCompactRm(291522.87)).toBe('292k');
  });

  it('labels the previous window by month when it is one month', () => {
    expect(previousLabel('2026-09-01', '2026-09-30')).toBe('Sep');
    expect(previousLabel('2026-07-01', '2026-08-07')).toBe('previous period');
    expect(previousLabel('2026-10-01', '2026-10-07')).toBe('previous period'); // part of a month
    expect(previousLabel('2026-10-02', '2026-10-31')).toBe('previous period');
    expect(previousLabel('2026-02-01', '2026-02-28')).toBe('Feb');
  });
});

describe('grid fit and codes', () => {
  it('column sizes fit the ~940px usable at 1280 with the sidebar open', () => {
    const total = Object.values(COLUMN_SIZES).reduce((a, b) => a + b, 0);
    expect(total).toBeLessThanOrEqual(940);
  });

  it('shows codes only when they say more than the name', () => {
    expect(codesText('LCL', ['LCL'])).toBe('');
    expect(codesText('LCL', [])).toBe('');
    expect(codesText('SEAN', ['SEAN I', 'SEAN III'])).toBe('SEAN I, SEAN III');
    expect(codesText('JIMMY', ['JIM-1'])).toBe('JIM-1');
    expect(codesText('A', ['A', 'A2'])).toBe('A, A2');
  });
});
