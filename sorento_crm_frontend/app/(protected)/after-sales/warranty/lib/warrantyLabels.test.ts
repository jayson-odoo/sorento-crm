/**
 * AFTER-SALES-P2 red tests (UAC F3, owner rule: dates dd/mm/yyyy): ported from #163
 * `warrantyLabels*.test.ts`, re-pointed at the new location.
 *
 * Module the coder builds: `./warrantyLabels` (this folder) exporting
 *   formatCivilDate(iso)        '2026-09-01' -> '01/09/2026', null -> '-', junk passes through
 *   nextCivilDay(iso), previousCivilDay(iso)   'YYYY-MM-DD' or null; never shifted by timezone
 *   policyLifecycle({effective_from, effective_to}) 'in_force' | 'scheduled' | 'superseded' (both ends inclusive)
 *   POLICY_LIFECYCLE_LABEL      { in_force: 'In force', scheduled: 'Scheduled', superseded: 'Superseded' }
 *   formatMatchTypeLabel(type)  series -> Series, model_list -> Model list, category -> Category, code_prefix -> Code prefix
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  POLICY_LIFECYCLE_LABEL,
  formatCivilDate,
  formatMatchTypeLabel,
  nextCivilDay,
  policyLifecycle,
  previousCivilDay,
} from './warrantyLabels';

afterEach(() => vi.useRealTimers());

function at(day: string, from: string, to: string | null) {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(`${day}T12:00:00`));
  return policyLifecycle({ effective_from: from, effective_to: to });
}

describe('formatCivilDate', () => {
  it('renders dd/mm/yyyy', () => {
    expect(formatCivilDate('2026-09-01')).toBe('01/09/2026');
    expect(formatCivilDate('2000-01-01')).toBe('01/01/2000');
  });
  it('does not shift under a western process timezone', () => {
    const original = process.env.TZ;
    process.env.TZ = 'America/Los_Angeles';
    try {
      expect(formatCivilDate('2026-09-01')).toBe('01/09/2026');
    } finally {
      process.env.TZ = original;
    }
  });
  it('dash for empty, passthrough for junk', () => {
    expect(formatCivilDate(null)).toBe('-');
    expect(formatCivilDate(undefined)).toBe('-');
    expect(formatCivilDate('not-a-date')).toBe('not-a-date');
  });
});

describe('civil day arithmetic', () => {
  it('next day rolls month, year and leap day', () => {
    expect(nextCivilDay('2026-01-31')).toBe('2026-02-01');
    expect(nextCivilDay('2025-12-31')).toBe('2026-01-01');
    expect(nextCivilDay('2028-02-28')).toBe('2028-02-29');
    expect(nextCivilDay('2027-02-28')).toBe('2027-03-01');
  });
  it('previous day rolls back across month and year', () => {
    expect(previousCivilDay('2027-01-01')).toBe('2026-12-31');
    expect(previousCivilDay('2026-03-01')).toBe('2026-02-28');
  });
  it('null for empty or malformed input', () => {
    expect(nextCivilDay(null)).toBeNull();
    expect(nextCivilDay('x')).toBeNull();
    expect(previousCivilDay('')).toBeNull();
  });
});

describe('policyLifecycle (both ends inclusive)', () => {
  it('starting tomorrow is scheduled', () => expect(at('2026-06-15', '2026-06-16', null)).toBe('scheduled'));
  it('starting today is in force', () => expect(at('2026-06-15', '2026-06-15', null)).toBe('in_force'));
  it('ending today is still in force', () => expect(at('2026-06-15', '2026-01-01', '2026-06-15')).toBe('in_force'));
  it('ended yesterday is superseded', () => expect(at('2026-06-15', '2026-01-01', '2026-06-14')).toBe('superseded'));
  it('has the pill words', () => {
    expect(POLICY_LIFECYCLE_LABEL).toEqual({ in_force: 'In force', scheduled: 'Scheduled', superseded: 'Superseded' });
  });
});

describe('formatMatchTypeLabel', () => {
  it('uses plain words', () => {
    expect(formatMatchTypeLabel('series')).toBe('Series');
    expect(formatMatchTypeLabel('model_list')).toBe('Model list');
    expect(formatMatchTypeLabel('code_prefix')).toBe('Code prefix');
    expect(formatMatchTypeLabel('category')).toBe('Category');
  });
});
