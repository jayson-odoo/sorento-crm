/**
 * The loading-plan toast quotes volumes, so it has to quote them the way the trade does.
 *
 * Three decimals: the panel the user is looking at while the toast appears prints
 * `68.125 cbm`, and a toast rounding the same figure to `68.13` reads as two different
 * numbers for one plan.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const success = vi.fn();
const createLoadingPlan = vi.fn();

vi.mock('sonner', () => ({
  toast: { success: (...a: unknown[]) => success(...a), error: vi.fn() },
}));

vi.mock('../services/fulfilmentService', () => ({
  createLoadingPlan: (...a: unknown[]) => createLoadingPlan(...a),
  rerunLoadingPlan: vi.fn(),
  approveLoadingPlan: vi.fn(),
  getContainerSizes: vi.fn(),
  getSupplierStock: vi.fn(),
  getUnfinishedPoLines: vi.fn(),
  getLoadingPlans: vi.fn(),
  applyStockList: vi.fn(),
  previewStockList: vi.fn(),
}));

import { useBuildLoadingPlan } from './useFulfilment';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  success.mockReset();
  createLoadingPlan.mockReset();
});

describe('useBuildLoadingPlan', () => {
  it('quotes both volumes to three decimals', async () => {
    createLoadingPlan.mockResolvedValue({
      supplier_id: 'sup-1',
      planned_cbm: 34.125,
      capacity_cbm: 68.125,
    });
    const { result } = renderHook(() => useBuildLoadingPlan(), { wrapper });

    result.current.mutate({ supplier_id: 'sup-1' } as never);

    await waitFor(() => expect(success).toHaveBeenCalled());
    expect(success).toHaveBeenCalledWith('Planned 34.125 of 68.125 cbm.');
  });

  it('does not pad whole volumes with decimals they were not given', async () => {
    createLoadingPlan.mockResolvedValue({
      supplier_id: 'sup-1',
      planned_cbm: 34,
      capacity_cbm: 68,
    });
    const { result } = renderHook(() => useBuildLoadingPlan(), { wrapper });

    result.current.mutate({ supplier_id: 'sup-1' } as never);

    await waitFor(() => expect(success).toHaveBeenCalled());
    expect(success).toHaveBeenCalledWith('Planned 34 of 68 cbm.');
  });
});
