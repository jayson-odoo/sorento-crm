/**
 * `PLAN-oi-request-cs-reserve.md` section 6c F1, coordinator fix round: the configured
 * default pool must reach every `projects.order_inquiries.reserve` holder (Eling, CS),
 * who does not hold `user_management.settings.view`. Pinned by reading the default
 * through the narrow `/settings/app-config` projection (never the full settings blob,
 * which 403s for exactly that viewer) - mocking ONLY `apiFetch`'s app-config response
 * (no settings-blob mock at all) is what proves the read moved.
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

function okResponse(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  apiFetch.mockReset();
  getStockDetail.mockReset();
});

describe('useReserveRowOptions: F1 default pool reaches a viewer with no settings permission', () => {
  it('a viewer with no user_management.settings.view still gets the configured pool as the default Location', async () => {
    // ONLY the app-config projection is mocked - no settings-blob mock exists at all,
    // the same as a real caller who would 403 on GET /settings/ but never calls it here.
    apiFetch.mockResolvedValue(
      okResponse({ oi_reserve_default_pool_warehouse_id: 'brw-id' }),
    );
    getStockDetail.mockResolvedValue({
      product_id: 'prod-1',
      group: 'pools',
      locations: [
        { warehouse_id: 'brw-id', location: 'BRW', available_qty: '90' },
        // The row's OWN site pool (DC1, off `location: 'DC1-BB'` below) is a
        // DIFFERENT pool - proving BRW wins because it is the CONFIGURED default,
        // not merely because it happens to be the row's own site.
        { warehouse_id: 'dc1-id', location: 'DC1', available_qty: '5' },
      ],
    });

    const { result } = renderHook(
      () =>
        useReserveRowOptions([
          { key: 'row-1', productId: 'prod-1', location: 'DC1-BB' },
        ]),
      { wrapper },
    );

    await waitFor(() =>
      expect(result.current['row-1'].defaultWarehouseId).toBe('brw-id'),
    );
    expect(apiFetch).toHaveBeenCalledWith('/api/user-management/settings/app-config');
  });
});
