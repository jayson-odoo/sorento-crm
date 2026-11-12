/**
 * RESERVE-DIALOG-ON-HAND (owner 11 Nov 2026: "reserve dialog actually we should just show
 * on hand qty simple as that"). The reserve dialogs' Location options state the plain on
 * hand at each pool, the same `stock.quantity_on_hand` the Stock status screen prints:
 * no SO subtracted, no SPO added, no transferable or covered logic.
 *
 * The fixture is the reported shape: 171 on hand at BRW, 6 owed on an open line of a
 * non-transferable SO and 4 incoming on an open SPO allocation, so the old
 * `available_qty` (171 - 6 + 4 = 169) differs from on hand.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

const getStockDetail = vi.fn();
vi.mock('../services/fulfilmentPlanningService', () => ({
  getStockDetail: (...args: unknown[]) => getStockDetail(...args),
}));

import { useReserveRowOptions } from './useReserveRowOptions';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  apiFetch.mockReset();
  getStockDetail.mockReset();
  apiFetch.mockResolvedValue({ ok: false, json: async () => ({}) } as unknown as Response);
});

describe('useReserveRowOptions: the reserve dialog states plain on hand', () => {
  it('labels each pool with its on hand, never on hand less SO plus SPO', async () => {
    getStockDetail.mockResolvedValue({
      product_id: 'prod-1',
      group: 'pools',
      locations: [
        {
          warehouse_id: 'brw-id',
          location: 'BRW',
          qty_on_hand: '171',
          so_qty: '6',
          spo_qty: '4',
          available_qty: '169',
        },
      ],
    });

    const { result } = renderHook(
      () => useReserveRowOptions([{ key: 'row-1', productId: 'prod-1', location: 'BRW-BB' }]),
      { wrapper },
    );

    await waitFor(() => expect(result.current['row-1'].options).toHaveLength(1));
    const row = result.current['row-1'];
    expect(row.options[0]).toEqual({ value: 'brw-id', label: 'BRW  on hand 171' });
    expect(row.onHandQtyByWarehouseId).toEqual({ 'brw-id': 171 });
  });
});
