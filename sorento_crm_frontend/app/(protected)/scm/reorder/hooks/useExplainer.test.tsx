/**
 * SCM M8 — useMarketProposal (slice E, M8-E5). The unified assistant's "Search
 * market" runs a live scan and returns a CONFIRM-GATED per-line qty proposal; the
 * hook wraps the mutation, forwarding the run id + query/signal to the endpoint.
 * Nothing is written here — the returned lines are proposals the user confirms.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getMarketProposal = vi.fn();
vi.mock('../services/explainerService', () => ({
  getMarketProposal: (...a: unknown[]) => getMarketProposal(...a),
  // The hook module imports several service fns at load — stub the rest as noops.
  askRecommendation: vi.fn(),
  askRunChat: vi.fn(),
  getRecommendationAdvisory: vi.fn(),
  getRecommendationExplanation: vi.fn(),
  getRunOverview: vi.fn(),
  searchMarket: vi.fn(),
}));

import { useMarketProposal } from './useExplainer';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => getMarketProposal.mockReset());

describe('useMarketProposal (M8-E5)', () => {
  it('forwards the run id + a free-text query, resolving to the proposal card', async () => {
    getMarketProposal.mockResolvedValue({
      signal_summary: 'Ceramic prices trending +8%',
      source_url: 'https://example.test/report',
      lines: [
        { rec_id: 'rec-1', sku: 'CW-BASIN-450', product_name: 'Basin', old_qty: 320, new_qty: 380, unit_cost: 42, cash_impact_delta: 2520, reason: 'seasonal uplift' },
      ],
    });
    const { result } = renderHook(() => useMarketProposal('run-9'), { wrapper });
    let res!: Awaited<ReturnType<typeof result.current.mutateAsync>>;
    await act(async () => {
      res = await result.current.mutateAsync({ query: 'ceramic price trend' });
    });
    expect(getMarketProposal).toHaveBeenCalledWith('run-9', { query: 'ceramic price trend' });
    expect(res.lines).toHaveLength(1);
    expect(res.lines[0].new_qty).toBe(380);
  });

  it('forwards a signal id + category ref when re-proposing a cached signal', async () => {
    getMarketProposal.mockResolvedValue({ signal_summary: null, source_url: null, lines: [] });
    const { result } = renderHook(() => useMarketProposal('run-9'), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ signalId: 'sig-1', categoryRef: 'CAT-CERAMIC' });
    });
    expect(getMarketProposal).toHaveBeenCalledWith('run-9', { signalId: 'sig-1', categoryRef: 'CAT-CERAMIC' });
  });
  // The failure → error-bubble path is exercised end-to-end in PlanAssistant.test.tsx.
});
