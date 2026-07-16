import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReorderRecommendation } from '../types/reorder.types';

// jsdom polyfills required by ScrollArea / DataGrid + scrollIntoView on select.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
Element.prototype.scrollIntoView = () => {};

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/reorder',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { ReorderPlanningView } from './ReorderPlanningView';

function json(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function summary() {
  return {
    buy_count: 1,
    disposition_count: 0,
    exception_count: 0,
    total_cash_impact: 5000,
    recommendation_count: 1,
  };
}

function historyItem(runId: string, code: string, startedAt: string) {
  return {
    run_id: runId,
    status: 'completed',
    buy_scope: 'network',
    warehouse_codes: [code],
    warehouse_count: 1,
    started_at: startedAt,
    finished_at: startedAt,
    summary: summary(),
  };
}

function recFor(runId: string): ReorderRecommendation {
  return {
    id: `rec-${runId}`,
    type: 'buy',
    sku: `SKU-${runId}`,
    product_name: `Product ${runId}`,
    abc_class: 'A',
    xyz_class: 'X',
    warehouse_code: 'WH-KL',
    warehouse_name: 'Kuala Lumpur DC',
    is_network: false,
    allocation: null,
    order_qty: 100,
    recommended_qty: 90,
    reorder_point: 80,
    min_qty: null,
    max_qty: null,
    order_up_to: null,
    net_position: 40,
    days_of_cover: 5,
    reason: 'reorder_point',
    reason_label: 'net ≤ ROP',
    confidence: 'high',
    sample_size: 20,
    supplier: {
      supplier_code: 'SUP-1',
      supplier_name: 'Acme',
      unit_cost: 50,
      lead_time_days: 14,
      composite_score: 80,
      is_primary: true,
    },
    alternatives: [],
    is_exception: false,
    disposition_action: null,
    transfer_flag: null,
    forecast_daily_demand: 8,
    lead_time_days: 14,
    lead_time_source: 'measured',
    safety_stock: 20,
    safety_stock_method: 'fixed_days',
    safety_stock_fallback: null,
    service_level: 0.95,
    safety_days: 7,
    review_days: 30,
    moq: 10,
    order_multiple: 5,
    policy_type: 'reorder_point',
    supplier_selection: 'primary',
    unit_cost: null,
    cash_impact: null,
    rank: null,
    rank_score: null,
    funding_status: null,
    days_to_stockout: null,
    rank_factors: [],
  };
}

/** Route the mocked apiFetch by path segments after `reorder-runs`. */
function route(recCalls: string[]) {
  apiFetch.mockImplementation((url: string) => {
    const u = new URL(String(url), 'http://x');
    const seg = u.pathname.split('/').filter(Boolean);
    const idx = seg.indexOf('reorder-runs');
    const after = seg.slice(idx + 1);
    if (after.length === 0) {
      // list history — newest first
      return Promise.resolve(
        json({
          data: [
            historyItem('run-b', 'WH-B', '2026-07-16T02:00:00'),
            historyItem('run-a', 'WH-A', '2026-07-15T02:00:00'),
          ],
          pagination: { page: 1, limit: 8, total: 2, total_pages: 1 },
        }),
      );
    }
    if (after.length >= 2 && after[1] === 'recommendations') {
      recCalls.push(after[0]);
      return Promise.resolve(
        json({
          data: [recFor(after[0])],
          pagination: { page: 1, limit: 25, total: 1, total_pages: 1 },
        }),
      );
    }
    // detail GET /reorder-runs/{id}
    return Promise.resolve(
      json({
        run_id: after[0],
        status: 'completed',
        stage: 'writing_recommendations',
        buy_scope: 'network',
        error: null,
        summary: summary(),
      }),
    );
  });
}

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => apiFetch.mockReset());

describe('ReorderPlanningView — run history', () => {
  it('lists past runs and, on selecting one, loads that run’s recommendations without re-running', async () => {
    const recCalls: string[] = [];
    route(recCalls);
    render(<ReorderPlanningView />, { wrapper });

    // history renders both runs (idle state — no live run yet)
    expect(await screen.findByText('No planning run yet')).toBeTruthy();
    await screen.findByText('WH-A');
    await screen.findByText('WH-B');

    // pick the older run (run-a) from history
    const row = screen.getByText('WH-A').closest('button')!;
    fireEvent.click(row);

    // its recommendations load (GET /reorder-runs/run-a/recommendations) — no POST fired
    await waitFor(() => expect(recCalls).toContain('run-a'));
    expect(apiFetch.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === 'POST')).toBe(
      false,
    );

    // the viewing banner + the selected run's SKU render
    expect(await screen.findByText(/Viewing an earlier run from/i)).toBeTruthy();
    expect(await screen.findByText('SKU-run-a')).toBeTruthy();
  });
});
