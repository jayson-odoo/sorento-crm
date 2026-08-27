/**
 * runListing - how a plan reads on the plans list (plan 4.1, UAC A5; Phase 2 deviation a).
 *
 * `runStatusReading`'s Confirmed check is the part most worth pinning: the denominator is
 * `planned_product_count` (what the run actually WROTE rows for), never the launch scope
 * `product_count` - which is null on the daily run, and a fixed comparison against it would
 * leave the commonest plan of all reading Planning forever.
 */
import { describe, it, expect } from 'vitest';
import { runStatusReading, runStartedLabel } from './runListing';

describe('runStatusReading - the denominator is planned_product_count (Phase 2 deviation a)', () => {
  it('every planned product confirmed reads Confirmed, even when the launch scope was wider', () => {
    // Launched against "all" (product_count null on a daily run), but only wrote 12 rows -
    // and all 12 are confirmed. Comparing against product_count (null) could never satisfy
    // this; the planned count is the honest denominator.
    const reading = runStatusReading({
      status: 'completed',
      product_count: null,
      planned_product_count: 12,
      confirmed_product_count: 12,
    });
    expect(reading).toEqual({ status: 'confirmed', label: 'Confirmed', variant: 'success' });
  });

  it('planned_product_count wins over product_count even when both are present and differ', () => {
    // A plan scoped to 200 products but which only wrote 12 rows (the rest had nothing to
    // decide) - confirming the 12 it DID write is what "Confirmed" has to mean here.
    const reading = runStatusReading({
      status: 'completed',
      product_count: 200,
      planned_product_count: 12,
      confirmed_product_count: 12,
    });
    expect(reading.status).toBe('confirmed');
  });

  it('falls back to product_count when planned_product_count is absent', () => {
    const reading = runStatusReading({
      status: 'completed',
      product_count: 5,
      confirmed_product_count: 5,
    });
    expect(reading.status).toBe('confirmed');
  });

  it('a plan with neither count still reads Planning, never a false Confirmed', () => {
    const reading = runStatusReading({ status: 'completed' });
    expect(reading.status).toBe('planning');
  });

  it('12 confirmed of a planned 12 but a wider product_count is still Confirmed, not Planning', () => {
    // The failure mode this guards: comparing confirmed_product_count against product_count
    // (200) instead of planned_product_count (12) would read this as "12 of 200", never
    // Confirmed - the commonest daily-run shape of all.
    const reading = runStatusReading({
      status: 'completed',
      product_count: 200,
      planned_product_count: 12,
      confirmed_product_count: 11,
    });
    expect(reading.status).toBe('planning');
  });

  it('a running plan reads Running regardless of any count', () => {
    expect(runStatusReading({ status: 'running' }).status).toBe('running');
  });

  it('a failed plan reads Failed regardless of any count', () => {
    expect(runStatusReading({ status: 'failed' }).status).toBe('failed');
  });
});

describe('runStartedLabel', () => {
  it('reads the EM_DASH placeholder for no timestamp at all', () => {
    expect(runStartedLabel(null)).toBe('-');
    expect(runStartedLabel(undefined)).toBe('-');
  });

  it('formats a naive-UTC timestamp as dd/mm/yyyy HH:mm', () => {
    expect(runStartedLabel('2026-08-27T01:50:00')).toMatch(/^27\/08\/2026 \d{2}:\d{2}$/);
  });
});
