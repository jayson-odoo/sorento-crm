/**
 * Tests for useDemandSeries — the lazy 12-month DO-outflow trend fetch backing
 * the expandable Product row's sparkline.
 *  - disabled (no fetch) when the row isn't expanded / SKU is empty
 *  - hits /dashboard/demand-series with sku (+ optional warehouse)
 *  - returns the parsed monthly series
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));
vi.mock('@/lib/api-client', () => ({
  extractApiError: async () => 'error',
  buildDataGridParams: () => new URLSearchParams(),
}));

import { useDemandSeries } from './useScmDashboard';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

const SERIES = {
  sku: 'WESERP10B',
  product_name: 'Weber ERP 10B',
  warehouse_code: null,
  xyz_class: 'Z',
  points: [
    { month: '2025-08', qty: 0 },
    { month: '2026-07', qty: 100 },
  ],
  total_qty: 100,
  peak_qty: 100,
};

beforeEach(() => apiFetch.mockReset());

describe('useDemandSeries', () => {
  it('does not fetch while disabled (row collapsed)', () => {
    apiFetch.mockResolvedValue(ok(SERIES));
    renderHook(() => useDemandSeries('WESERP10B', null, false), { wrapper });
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('does not fetch with an empty sku', () => {
    apiFetch.mockResolvedValue(ok(SERIES));
    renderHook(() => useDemandSeries('', null, true), { wrapper });
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('fetches the monthly series when enabled and passes the sku', async () => {
    apiFetch.mockResolvedValue(ok(SERIES));
    const { result } = renderHook(
      () => useDemandSeries('WESERP10B', null, true),
      { wrapper },
    );
    await waitFor(() => expect(result.current.data).toBeDefined());
    const url = String(apiFetch.mock.calls.at(-1)?.[0]);
    expect(url).toContain('/api/v1/scm/dashboard/demand-series');
    expect(url).toContain('sku=WESERP10B');
    expect(result.current.data?.points).toHaveLength(2);
    expect(result.current.data?.xyz_class).toBe('Z');
  });

  it('forwards a warehouse scope when provided', async () => {
    apiFetch.mockResolvedValue(ok({ ...SERIES, warehouse_code: 'WH-A' }));
    const { result } = renderHook(
      () => useDemandSeries('WESERP10B', 'WH-A', true),
      { wrapper },
    );
    await waitFor(() => expect(result.current.data).toBeDefined());
    const url = String(apiFetch.mock.calls.at(-1)?.[0]);
    expect(url).toContain('warehouse=WH-A');
  });
});
