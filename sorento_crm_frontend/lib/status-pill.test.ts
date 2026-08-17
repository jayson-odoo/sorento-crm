/**
 * The shared status-pill palette. Covers the `processing` entry added for the
 * flyer-read background job (AC-FE.2 / AC-FE.6): a queued read must read as
 * "waiting on something" - the same amber as the other pending states - not as
 * an outcome.
 */
import { describe, expect, it } from 'vitest';

import { statusPillClass } from './status-pill';

describe('statusPillClass', () => {
  it('is the amber "waiting" colour for a flyer reading that is processing', () => {
    expect(statusPillClass('processing')).toBe('bg-amber-100 text-amber-800');
  });

  it('is the same amber as the other pending statuses, not a colour of its own', () => {
    expect(statusPillClass('processing')).toBe(statusPillClass('pending'));
  });

  it('normalises case and spacing the same way every other status does', () => {
    expect(statusPillClass('Processing')).toBe('bg-amber-100 text-amber-800');
    expect(statusPillClass(' processing ')).toBe('bg-amber-100 text-amber-800');
  });

  it('falls back to neutral for an unrecognised status', () => {
    expect(statusPillClass('made-up-status')).toBe('bg-muted text-muted-foreground');
    expect(statusPillClass(null)).toBe('bg-muted text-muted-foreground');
    expect(statusPillClass(undefined)).toBe('bg-muted text-muted-foreground');
  });
});
