/**
 * spoDocumentStatus - wording/colouring for the SPO document list + form view
 * (PLAN-spo-investigation-grid.md markup rulings; UAC AC-2, AC-6).
 *
 *   - AC-2/AC-6: the Outstanding status pill reads GREEN, matching the PO page.
 *   - AC-6/Q4: the planning-span badge carries all four states (In plan / Pool /
 *     Off / No location).
 *   - Overdue days read amber once late (> 0), plain muted at zero.
 *   - ETA renders AS IS (dd/mm/yyyy), never NaN/NaN/NaN on a bad/missing input.
 */
import { describe, it, expect } from 'vitest';
import {
  spoDocumentStatusPill,
  planningSpanBadge,
  fmtEta,
  fmtQty,
  overdueClassName,
} from './spoDocumentStatus';

describe('spoDocumentStatusPill (AC-2, AC-6)', () => {
  it('words Outstanding as success (green), matching the PO page', () => {
    const pill = spoDocumentStatusPill('outstanding');
    expect(pill.label).toBe('Outstanding');
    expect(pill.variant).toBe('success');
  });

  it('words Completed as secondary, not success', () => {
    const pill = spoDocumentStatusPill('completed');
    expect(pill.label).toBe('Completed');
    expect(pill.variant).toBe('secondary');
    expect(pill.variant).not.toBe('success');
  });
});

describe('planningSpanBadge - all four states (Q4, AC-6)', () => {
  it('in_plan -> "In plan"', () => {
    expect(planningSpanBadge('in_plan')).toMatchObject({ label: 'In plan' });
  });
  it('pool -> "Pool"', () => {
    expect(planningSpanBadge('pool')).toMatchObject({ label: 'Pool' });
  });
  it('off -> "Off"', () => {
    expect(planningSpanBadge('off')).toMatchObject({ label: 'Off' });
  });
  it('none -> "No location" (a data gap, worded warning not destructive)', () => {
    const badge = planningSpanBadge('none');
    expect(badge.label).toBe('No location');
    expect(badge.variant).toBe('warning');
  });

  it('every state gets a distinct label - a captain reading the column never sees a repeat', () => {
    const labels = (['in_plan', 'pool', 'off', 'none'] as const).map(
      (s) => planningSpanBadge(s).label,
    );
    expect(new Set(labels).size).toBe(4);
  });
});

describe('overdueClassName - amber once late (Q16)', () => {
  it('reads amber for a positive overdue day count', () => {
    expect(overdueClassName(1)).toContain('amber');
    expect(overdueClassName(31)).toContain('amber');
  });
  it('reads plain muted at zero', () => {
    expect(overdueClassName(0)).not.toContain('amber');
    expect(overdueClassName(0)).toContain('muted');
  });
});

describe('fmtEta - renders AS IS, no masking (Q3)', () => {
  it('formats an ISO date as dd/mm/yyyy', () => {
    expect(fmtEta('2026-08-01')).toBe('01/08/2026');
  });
  it('renders a placeholder 2029/2030 date as-is, never TBA', () => {
    expect(fmtEta('2029-12-31')).toBe('31/12/2029');
  });
  it('renders a dash for a null/undefined/invalid date, never NaN/NaN/NaN', () => {
    expect(fmtEta(null)).toBe('-');
    expect(fmtEta(undefined)).toBe('-');
    expect(fmtEta('not-a-date')).toBe('-');
  });
});

describe('fmtQty', () => {
  it('renders a dash for null/undefined/non-finite', () => {
    expect(fmtQty(null)).toBe('-');
    expect(fmtQty(undefined)).toBe('-');
    expect(fmtQty(Number.NaN)).toBe('-');
  });
  it('renders a thousands-separated quantity, zero included', () => {
    expect(fmtQty(0)).toBe('0');
    expect(fmtQty(1234)).toBe('1,234');
  });
});
