/**
 * SCM M8 — drill feature service (Phase 2, test-first).
 * The two lazy plan-grid drills fetch their working keyed off the recommendation:
 *   M8-A1 Net breakdown       → GET /scm/recommendations/{id}/explain-net
 *   M8-A2 Days-cover demand   → GET /scm/analytics/explain/demand?product_id&warehouse_id
 * Assert the exact endpoint + params (the demand drill MUST hit /analytics/explain/demand),
 * and that a non-ok response throws the extracted backend message.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { getRecommendationDemand, getRecommendationNet } from './drillService';

function ok(body: unknown) {
  return {
    ok: true,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}
function fail(detail: string) {
  return {
    ok: false,
    status: 404,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    text: async () => JSON.stringify({ detail }),
  } as unknown as Response;
}
function calledUrl(): URL {
  const calls = apiFetch.mock.calls;
  return new URL(String(calls[calls.length - 1][0]), 'http://x');
}

beforeEach(() => apiFetch.mockReset());

describe('getRecommendationNet (M8-A1)', () => {
  it('GETs the rec explain-net endpoint and returns the committed-SO breakdown', async () => {
    apiFetch.mockResolvedValue(
      ok({
        on_hand: 100,
        on_order: 40,
        committed: 60,
        net: 80,
        committed_sos: [{ so_number: 'SO-2026-0007', qty: 60, customer_name: 'Bina Jaya', order_date: '2026-07-10' }],
      }),
    );
    const nb = await getRecommendationNet('rec-1');
    expect(calledUrl().pathname).toBe('/api/v1/scm/recommendations/rec-1/explain-net');
    expect(nb.net).toBe(80);
    expect(nb.committed_sos[0].so_number).toBe('SO-2026-0007');
  });

  it('throws the extracted message on a non-ok response', async () => {
    apiFetch.mockResolvedValue(fail('Recommendation not found'));
    await expect(getRecommendationNet('rec-x')).rejects.toThrow('Recommendation not found');
  });
});

describe('getRecommendationDemand (M8-A2 → /analytics/explain/demand)', () => {
  it('hits /analytics/explain/demand with product_id + warehouse_id', async () => {
    apiFetch.mockResolvedValue(
      ok({
        product_id: 'prod-1',
        warehouse_id: 'wh-1',
        avg_daily_demand: 12,
        demand_cv: 0.34,
        method: 'moving_average',
        demand_dos: [{ order_id: 'ord-1', do_number: 'DO-2026-0100', order_date: '2026-07-01', qty_out: 25 }],
        buckets: [],
      }),
    );
    const d = await getRecommendationDemand('prod-1', 'wh-1');
    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/scm/analytics/explain/demand');
    expect(u.searchParams.get('product_id')).toBe('prod-1');
    expect(u.searchParams.get('warehouse_id')).toBe('wh-1');
    expect(d.avg_daily_demand).toBe(12);
    expect(d.demand_dos[0].do_number).toBe('DO-2026-0100');
  });

  it('omits warehouse_id for a network row (demand sums across warehouses)', async () => {
    apiFetch.mockResolvedValue(
      ok({ product_id: 'prod-1', warehouse_id: null, avg_daily_demand: 8, demand_cv: null, method: 'x', demand_dos: [], buckets: [] }),
    );
    await getRecommendationDemand('prod-1', null);
    const u = calledUrl();
    expect(u.searchParams.get('product_id')).toBe('prod-1');
    expect(u.searchParams.has('warehouse_id')).toBe(false);
  });

  it('throws the extracted message on a non-ok response', async () => {
    apiFetch.mockResolvedValue(fail('No demand series'));
    await expect(getRecommendationDemand('prod-x', null)).rejects.toThrow('No demand series');
  });
});
