/**
 * A target's periods from its date range and optional split: the frontend mirror of the
 * backend's `period_service.generate_periods` (plan 3.1, 16.2; UAC S1-19), so the Set target
 * modal's hint (period count, the last period's dates) never disagrees with what Save creates.
 *
 * No split: one period. Every N days, weeks or months: period k starts k*N units after the
 * ORIGINAL start (a month step clamped to the month's last day, so 31 Jan gives 31 Jan,
 * 28 Feb, 31 Mar), each ends the day before the next, the last at `end`. Both ends counted.
 * Dates are `YYYY-MM-DD` strings in and out, computed in UTC so no timezone moves a day.
 */
import type { TargetSplitUnit } from '../types/salesTarget.types';

export const MAX_PERIODS = 104;

export interface Period {
  start: string;
  end: string;
}

function parse(day: string): Date {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function format(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function addDays(date: Date, days: number): Date {
  return new Date(date.getTime() + days * 86_400_000);
}

export function addMonths(date: Date, months: number): Date {
  const index = date.getUTCFullYear() * 12 + date.getUTCMonth() + months;
  const year = Math.floor(index / 12);
  const month = index - year * 12;
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return new Date(Date.UTC(year, month, Math.min(date.getUTCDate(), lastDay)));
}

export function generatePeriods(
  start: string,
  end: string,
  splitEvery: number | null,
  splitUnit: TargetSplitUnit | null,
): Period[] {
  if (end < start) throw new Error('The end date is before the start date.');
  if (!splitEvery || !splitUnit) return [{ start, end }];

  const first = parse(start);
  const last = parse(end);
  const starts: Date[] = [];
  for (let k = 0; ; k += 1) {
    const begin =
      splitUnit === 'day'
        ? addDays(first, k * splitEvery)
        : splitUnit === 'week'
          ? addDays(first, 7 * k * splitEvery)
          : addMonths(first, k * splitEvery);
    if (begin > last) break;
    starts.push(begin);
    if (starts.length > MAX_PERIODS) {
      throw new Error(`That split makes more than ${MAX_PERIODS} periods.`);
    }
  }
  return starts.map((begin, i) => ({
    start: format(begin),
    end: i + 1 < starts.length ? format(addDays(starts[i + 1], -1)) : end,
  }));
}
