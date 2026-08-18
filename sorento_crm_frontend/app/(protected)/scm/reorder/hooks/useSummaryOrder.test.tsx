/**
 * SCM front planning stage 2 - useRecordOrderDecision's success toast (AC-F12).
 *
 * The toast confirms a decision, so it has to render the quantity the way the row
 * accepted it: at the ROW'S frozen `uom_decimal_places`, which the caller passes as a
 * mutation variable because the decision response carries no precision of its own. An
 * integer format read an accepted `2.75 kg` back as "3", and a confirmation that
 * disagrees with the decision it is confirming is worse than no confirmation.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    error: (...a: unknown[]) => toastError(...a),
    success: (...a: unknown[]) => toastSuccess(...a),
  },
}));

import { useRecordOrderDecision } from './useSummaryOrder';

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

function decided(chosen_qty: number) {
  return {
    product_code: 'CW-BASIN-450',
    chosen_qty,
    suggested_qty: chosen_qty,
    chosen_supplier_code: 'SUP-ALPHA',
    chosen_supplier_name: 'Alpha Supplies',
    decided_by: 'Mr Loo',
    decided_at: '2026-08-17T09:00:00',
    location_allocations: [],
  };
}

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  return { client, wrapper };
}

async function record(chosen_qty: number, decimalPlaces: number | null | undefined) {
  apiFetch.mockResolvedValue(ok(decided(chosen_qty)));
  const { wrapper } = makeWrapper();
  const { result } = renderHook(() => useRecordOrderDecision({ run_id: 'run-1' }), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({
      productCode: 'CW-BASIN-450',
      input: { run_id: 'run-1', chosen_qty, supplier_code: 'SUP-ALPHA' },
      decimalPlaces,
    });
  });
  return String(toastSuccess.mock.calls[0][0]);
}

beforeEach(() => {
  apiFetch.mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
});

describe('useRecordOrderDecision - the toast renders at the row precision (AC-F12)', () => {
  it('keeps the fraction of a measure-unit quantity at 3 places', async () => {
    const message = await record(2.75, 3);

    expect(message).toContain('2.75');
    expect(message).not.toContain('ordering 3 ');
  });

  it('states a whole-unit quantity as a whole number at 0 places', async () => {
    const message = await record(12, 0);

    expect(message).toContain('12');
  });

  it('falls back to whole units when the row has no frozen precision', async () => {
    const message = await record(3, undefined);

    expect(message).toContain('CW-BASIN-450');
    expect(message).toContain('3');
    expect(message).toContain('Alpha Supplies');
  });
});
