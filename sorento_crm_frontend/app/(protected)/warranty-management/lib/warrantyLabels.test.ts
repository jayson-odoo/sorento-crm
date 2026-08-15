/**
 * `warrantyLabels` — S7b Phase 2c gate.
 *
 * Group 1 item 6: `policyLifecycle` boundaries (AC-P2b: both ends INCLUSIVE).
 * Group 1 item 7: `formatCivilDate` must never shift a civil date by timezone.
 *
 * These are prototype behaviours that already claim correctness (string-split
 * dates, three-state lifecycle) — expected to PASS. A failure here is a real
 * regression finding, not an intentional red.
 */
import { describe, it, expect, vi } from 'vitest';
import { formatCivilDate, policyLifecycle } from './warrantyLabels';
import type { WarrantyPolicyRow } from '../types/warranty-config.types';

function policy(over: Partial<WarrantyPolicyRow>): WarrantyPolicyRow {
  return {
    id: 'p1',
    version: 'v1',
    effective_from: '2000-01-01',
    effective_to: null,
    policy_text: null,
    source_attachment_name: null,
    term_count: 0,
    created_at: '2000-01-01T00:00:00',
    updated_at: null,
    ...over,
  };
}

/** Fixed "today" for every boundary test below: 2026-06-15. */
const TODAY = new Date(2026, 5, 15); // month is 0-indexed -> June

describe('policyLifecycle — boundary dates (AC-P2b: both ends inclusive)', () => {
  it('a policy starting tomorrow is "scheduled", not "in_force" or "superseded"', () => {
    vi.useFakeTimers();
    vi.setSystemTime(TODAY);
    try {
      const p = policy({ effective_from: '2026-06-16', effective_to: null });
      expect(policyLifecycle(p)).toBe('scheduled');
    } finally {
      vi.useRealTimers();
    }
  });

  it('a policy starting exactly today is "in_force" (the start boundary is inclusive)', () => {
    vi.useFakeTimers();
    vi.setSystemTime(TODAY);
    try {
      const p = policy({ effective_from: '2026-06-15', effective_to: null });
      expect(policyLifecycle(p)).toBe('in_force');
    } finally {
      vi.useRealTimers();
    }
  });

  it('a policy whose effective_to is exactly today is still "in_force" (the end boundary is inclusive)', () => {
    vi.useFakeTimers();
    vi.setSystemTime(TODAY);
    try {
      const p = policy({ effective_from: '2026-01-01', effective_to: '2026-06-15' });
      expect(policyLifecycle(p)).toBe('in_force');
    } finally {
      vi.useRealTimers();
    }
  });

  it('a policy whose effective_to was yesterday is "superseded"', () => {
    vi.useFakeTimers();
    vi.setSystemTime(TODAY);
    try {
      const p = policy({ effective_from: '2026-01-01', effective_to: '2026-06-14' });
      expect(policyLifecycle(p)).toBe('superseded');
    } finally {
      vi.useRealTimers();
    }
  });

  it('an open-ended policy that already started is "in_force"', () => {
    vi.useFakeTimers();
    vi.setSystemTime(TODAY);
    try {
      const p = policy({ effective_from: '2000-01-01', effective_to: null });
      expect(policyLifecycle(p)).toBe('in_force');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('formatCivilDate — no timezone shift (classic off-by-one-day bug)', () => {
  it('sanity control: a naive `new Date(iso)` UTC-midnight parse DOES render the previous day west of Greenwich', () => {
    // This proves the bug is real for this exact input, independent of the
    // *process*'s own TZ (Intl.DateTimeFormat's `timeZone` option is explicit,
    // so this assertion is deterministic in any CI environment).
    const naiveWrong = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Los_Angeles',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(new Date('2026-09-01'));
    expect(naiveWrong).toBe('Aug 31, 2026');
  });

  it('renders 2026-09-01 as "01 Sep 2026" — NOT the previous day a UTC-midnight parse would show', () => {
    expect(formatCivilDate('2026-09-01')).toBe('01 Sep 2026');
  });

  it('also holds under an actual non-UTC process TZ (America/Los_Angeles)', () => {
    const original = process.env.TZ;
    process.env.TZ = 'America/Los_Angeles';
    try {
      expect(formatCivilDate('2026-09-01')).toBe('01 Sep 2026');
      expect(formatCivilDate('2000-01-01')).toBe('01 Jan 2000');
    } finally {
      process.env.TZ = original;
    }
  });

  it('renders "-" for null/undefined and passes through a non-date string unchanged', () => {
    expect(formatCivilDate(null)).toBe('-');
    expect(formatCivilDate(undefined)).toBe('-');
    expect(formatCivilDate('not-a-date')).toBe('not-a-date');
  });
});
