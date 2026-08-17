/**
 * Stage 1B - the fulfilment planning / reconciliation service (contract section 3).
 *
 * Two paths live in one file behind the `PROJECT_SO_MOCK` switch this module imports from
 * `projectSalesOrderService`, so both are exercised here: the mock path (every fixture the
 * slice note's section 3 promises, plus the two failure cases) and the real path (the three
 * documented URLs, envelope normalisation, and `extractApiError` on failure). Because the
 * switch is read as a plain import at module load, each path is loaded through
 * `vi.resetModules` + `vi.doMock` + a dynamic `import()` rather than a single static import.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
});

describe('mock path (NEXT_PUBLIC_PROJECT_SO_MOCK=1)', () => {
  async function loadMockService() {
    vi.doMock('./projectSalesOrderService', () => ({ PROJECT_SO_MOCK: true }));
    return import('./fulfilmentPlanningService');
  }

  it('lists the golden fixture set', async () => {
    const { listFulfilmentPlanning } = await loadMockService();

    const result = await listFulfilmentPlanning();

    expect(result.data.map((row) => row.id)).toEqual([
      'mock-pso-clean',
      'mock-pso-missing',
      'mock-pso-ambiguous',
      'mock-pso-nodoc',
      'mock-pso-unavailable',
    ]);
    expect(result.total).toBe(5);
  });

  it('serves the empty list on mock_case=empty', async () => {
    const { listFulfilmentPlanning } = await loadMockService();

    const result = await listFulfilmentPlanning({ mock_case: 'empty' });

    expect(result.data).toEqual([]);
    expect(result.total).toBe(0);
  });

  it('rejects the list on mock_case=error', async () => {
    const { listFulfilmentPlanning } = await loadMockService();

    await expect(listFulfilmentPlanning({ mock_case: 'error' })).rejects.toThrow(
      'Failed to load the fulfilment planning list',
    );
  });

  it('serves the needs-review fixture: header linked, every line linked, no exceptions', async () => {
    const { getReconciliation } = await loadMockService();

    const summary = await getReconciliation('mock-pso-clean');

    expect(summary.review_state).toBe('needs_cs_review');
    expect(summary.header.outcome).toBe('linked');
    expect(summary.exceptions).toEqual([]);
    expect(summary.lines_linked).toBe(summary.lines_total);
    expect(summary.lines.every((line) => line.link === 'linked')).toBe(true);
  });

  it('serves the missing-line-and-surplus-core-line fixture as two separate exceptions', async () => {
    const { getReconciliation } = await loadMockService();

    const summary = await getReconciliation('mock-pso-missing');

    expect(summary.review_state).toBe('awaiting_reconciliation');
    const kinds = summary.exceptions.map((exception) => exception.kind);
    expect(kinds).toContain('missing');
    expect(kinds).toContain('surplus');
    expect(summary.lines.some((line) => line.link === 'missing')).toBe(true);
  });

  it('serves the ambiguous-pair fixture with a candidate count on each side', async () => {
    const { getReconciliation } = await loadMockService();

    const summary = await getReconciliation('mock-pso-ambiguous');

    const ambiguous = summary.lines.filter((line) => line.link === 'ambiguous');
    expect(ambiguous).toHaveLength(2);
    expect(ambiguous.every((line) => line.candidate_count === 2)).toBe(true);
    expect(summary.exceptions.every((exception) => exception.kind === 'ambiguous')).toBe(true);
  });

  it('serves the no-document fixture with a null core order and no reconciled_at', async () => {
    const { getReconciliation } = await loadMockService();

    const summary = await getReconciliation('mock-pso-nodoc');

    expect(summary.header.outcome).toBe('no_document');
    expect(summary.header.core_so_number).toBeNull();
    expect(summary.reconciled_at).toBeNull();
    expect(summary.exceptions.some((exception) => exception.kind === 'header')).toBe(true);
  });

  it('rejects the reconciliation read for the fixture built to always fail', async () => {
    const { getReconciliation } = await loadMockService();

    await expect(getReconciliation('mock-pso-unavailable')).rejects.toThrow(
      'Failed to load the reconciliation',
    );
  });

  it('rejects the rerun for the same failing fixture', async () => {
    const { rerunReconciliation } = await loadMockService();

    await expect(rerunReconciliation('mock-pso-unavailable')).rejects.toThrow(
      'Failed to load the reconciliation',
    );
  });

  it('rerun answers with the same fixture the read would', async () => {
    const { getReconciliation, rerunReconciliation } = await loadMockService();

    const read = await getReconciliation('mock-pso-clean');
    const rerun = await rerunReconciliation('mock-pso-clean');

    expect(rerun).toEqual(read);
  });
});

describe('real path (PROJECT_SO_MOCK=false)', () => {
  const apiFetch = vi.fn();

  function ok(body: unknown) {
    return { ok: true, json: async () => body } as Response;
  }

  function fail() {
    return { ok: false, headers: { get: () => 'application/json' }, json: async () => ({}) } as unknown as Response;
  }

  async function loadRealService() {
    vi.doMock('./projectSalesOrderService', () => ({ PROJECT_SO_MOCK: false }));
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
