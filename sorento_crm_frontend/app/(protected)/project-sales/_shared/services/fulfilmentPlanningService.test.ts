/**
 * Stage 1B - the fulfilment planning / reconciliation service (contract section 3).
 *
 * What is pinned here is the wire: the three documented URLs and their methods, the query
 * params the worklist sends, envelope normalisation both ways round, and `extractApiError`
 * on every failure. `@/lib/api` and `@/lib/api-client` are replaced through
 * `vi.resetModules` + `vi.doMock` + a dynamic `import()`, because the module reads them at
 * load time.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
});

describe('fulfilmentPlanningService', () => {
  const apiFetch = vi.fn();

  function ok(body: unknown) {
    return { ok: true, json: async () => body } as Response;
  }

  function fail() {
    return { ok: false, headers: { get: () => 'application/json' }, json: async () => ({}) } as unknown as Response;
  }

  async function loadRealService() {
    vi.doMock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));
    vi.doMock('@/lib/api-client', async (importOriginal) => {
      const actual = await importOriginal<typeof import('@/lib/api-client')>();
      return { ...actual, extractApiError: vi.fn(async () => 'Backend said no') };
    });
    return import('./fulfilmentPlanningService');
  }

  it('lists via the documented GET url, carrying page, limit, query and filters', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 2, limit: 10 } }));
    const { listFulfilmentPlanning } = await loadRealService();

    await listFulfilmentPlanning({
      page: 2,
      limit: 10,
      query: 'buimaco',
      review_state: 'needs_cs_review',
      project_id: 'proj-1',
    });

    const [url] = apiFetch.mock.calls[0];
    expect(url).toContain('/api/v1/project-sales/fulfilment-planning?');
    expect(url).toContain('page=2');
    expect(url).toContain('limit=10');
    expect(url).toContain('query=buimaco');
    expect(url).toContain('review_state=needs_cs_review');
    expect(url).toContain('project_id=proj-1');
  });

  it('normalises the standard {data, pagination} envelope', async () => {
    apiFetch.mockResolvedValue(
      ok({
        data: [{ id: 'r1' }],
        pagination: { total: 7, page: 2, limit: 10 },
      }),
    );
    const { listFulfilmentPlanning } = await loadRealService();

    const result = await listFulfilmentPlanning({ page: 2, limit: 10 });

    expect(result).toEqual({ data: [{ id: 'r1' }], total: 7, page: 2, limit: 10 });
  });

  it('falls back to a flat {data, total, page, limit} envelope', async () => {
    apiFetch.mockResolvedValue(ok({ data: [{ id: 'r1' }], total: 1, page: 1, limit: 25 }));
    const { listFulfilmentPlanning } = await loadRealService();

    const result = await listFulfilmentPlanning();

    expect(result).toEqual({ data: [{ id: 'r1' }], total: 1, page: 1, limit: 25 });
  });

  it('defaults an envelope with no total to the row count', async () => {
    apiFetch.mockResolvedValue(ok({ data: [{ id: 'r1' }, { id: 'r2' }] }));
    const { listFulfilmentPlanning } = await loadRealService();

    const result = await listFulfilmentPlanning();

    expect(result.total).toBe(2);
    expect(result.data).toHaveLength(2);
  });

  it('surfaces the backend message when the list fails', async () => {
    apiFetch.mockResolvedValue(fail());
    const { listFulfilmentPlanning } = await loadRealService();

    await expect(listFulfilmentPlanning()).rejects.toThrow('Backend said no');
  });

  it('reads one reconciliation via the documented GET url', async () => {
    apiFetch.mockResolvedValue(ok({ project_sales_order_id: 'pso-1', review_state: 'needs_cs_review' }));
    const { getReconciliation } = await loadRealService();

    await getReconciliation('pso-1');

    expect(apiFetch).toHaveBeenCalledWith('/api/v1/project-sales/sales-orders/pso-1/reconciliation');
  });

  it('surfaces the backend message when the reconciliation read fails', async () => {
    apiFetch.mockResolvedValue(fail());
    const { getReconciliation } = await loadRealService();

    await expect(getReconciliation('pso-1')).rejects.toThrow('Backend said no');
  });

  it('reruns via a POST to the documented url', async () => {
    apiFetch.mockResolvedValue(ok({ project_sales_order_id: 'pso-1', review_state: 'needs_cs_review' }));
    const { rerunReconciliation } = await loadRealService();

    await rerunReconciliation('pso-1');

    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/project-sales/sales-orders/pso-1/reconcile');
    expect(init).toEqual({ method: 'POST' });
  });

  it('surfaces the backend message when the rerun fails', async () => {
    apiFetch.mockResolvedValue(fail());
    const { rerunReconciliation } = await loadRealService();

    await expect(rerunReconciliation('pso-1')).rejects.toThrow('Backend said no');
  });
});
