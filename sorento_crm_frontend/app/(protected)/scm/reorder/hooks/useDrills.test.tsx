/**
 * SCM M8 — useDrills (M8-A1/A2). The two heavy drills must be LAZY: the query
 * only fires when `enabled` (the popover is open) AND the id is present, so the
 * plan grid loads without N drill round-trips. `useExplainDemand` passes a null
 * warehouseId straight through (network row → demand sums across warehouses).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getRecommendationNet = vi.fn();
const getRecommendationDemand = vi.fn();
vi.mock('../services/drillService', () => ({
  getRecommendationNet: (...a: unknown[]) => getRecommendationNet(...a),
  getRecommendationDemand: (...a: unknown[]) => getRecommendationDemand(...a),
}));

import { useExplainDemand, useExplainNet } from './useDrills';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  getRecommendationNet.mockReset().mockResolvedValue({ on_hand: 1, on_order: 0, committed: 0, net: 1, committed_sos: [] });
  getRecommendationDemand.mockReset().mockResolvedValue({ product_id: 'p', warehouse_id: null, avg_daily_demand: 5, demand_cv: 0.2, method: 'x', demand_dos: [], buckets: [] });
});

describe('useExplainNet — lazy on popover open (M8-A1)', () => {
  it('does NOT fetch while the popover is closed (enabled=false)', () => {
    renderHook(() => useExplainNet('rec-1', false), { wrapper });
    expect(getRecommendationNet).not.toHaveBeenCalled();
  });

  it('does NOT fetch without a rec id even when enabled', () => {
    renderHook(() => useExplainNet(null, true), { wrapper });
    expect(getRecommendationNet).not.toHaveBeenCalled();
  });

  it('fetches once the popover opens (enabled=true)', async () => {
    const { result } = renderHook(() => useExplainNet('rec-1', true), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getRecommendationNet).toHaveBeenCalledWith('rec-1');
  });
});

describe('useExplainDemand — lazy on popover open (M8-A2)', () => {
  it('does NOT fetch while closed', () => {
    renderHook(() => useExplainDemand('prod-1', 'wh-1', false), { wrapper });
    expect(getRecommendationDemand).not.toHaveBeenCalled();
  });

  it('does NOT fetch without a product id', () => {
    renderHook(() => useExplainDemand(null, 'wh-1', true), { wrapper });
    expect(getRecommendationDemand).not.toHaveBeenCalled();
  });

  it('fetches with product + warehouse when opened', async () => {
    const { result } = renderHook(() => useExplainDemand('prod-1', 'wh-1', true), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getRecommendationDemand).toHaveBeenCalledWith('prod-1', 'wh-1');
  });

  it('passes a null warehouseId through for a network row', async () => {
    const { result } = renderHook(() => useExplainDemand('prod-1', null, true), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getRecommendationDemand).toHaveBeenCalledWith('prod-1', null);
  });
});
