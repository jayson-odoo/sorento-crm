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

  // ------------------------------------------------ Stage 1C: supply and confirm
  it('reads the composition via the documented GET url', async () => {
    apiFetch.mockResolvedValue(ok({ project_sales_order_id: 'pso-1', lines: [] }));
    const { getSupply } = await loadRealService();

    await getSupply('pso-1');

    expect(apiFetch).toHaveBeenCalledWith('/api/v1/project-sales/sales-orders/pso-1/supply');
  });

  it('surfaces the backend message when the composition read fails', async () => {
    apiFetch.mockResolvedValue(fail());
    const { getSupply } = await loadRealService();

    await expect(getSupply('pso-1')).rejects.toThrow('Backend said no');
  });

  it('confirms with one POST carrying the whole order, under the documented keys', async () => {
    apiFetch.mockResolvedValue(
      ok({
        revision_no: 1,
        confirmed_at: '2026-08-18T02:00:00',
        review_state: 'confirmed',
        inquiry_rows_created: 1,
        exceptions: [],
      }),
    );
    const { confirmSupply } = await loadRealService();

    const body = {
      lines: [
        {
          project_line_id: 'pl-1',
          timely_spo_qty: '100',
          reserve: [{ warehouse_id: 'wh-brw', qty: '200' }],
          borrow: [
            {
              source: 'other_project' as const,
              warehouse_id: 'wh-jb',
              donor_project_id: 'proj-2',
              qty: '40',
              reason: 'Their hand-over is in December.',
            },
          ],
          buy_qty: '260',
          buy_reason: null,
        },
      ],
    };
    const result = await confirmSupply('pso-1', body);

    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/project-sales/sales-orders/pso-1/confirm');
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
    expect(JSON.parse(init.body)).toEqual(body);
    expect(result.revision_no).toBe(1);
  });

  it('carries the failing lines off a refusal, with the message from the shared extractor', async () => {
    // The refusal body is the shared AppException envelope plus `failing_lines`. The
    // extractor answers with a string, so the list is read off a clone of the same
    // response - losing it would lose exactly the part CS acts on.
    const failing = [
      { line_no: 1, item_code: 'CB6633', reason: 'Only 25 units are still free at BRW-BB.' },
      { line_no: 2, item_code: 'CB2201', reason: 'The open quantity changed to 80.' },
    ];
    const refusal = {
      ok: false,
      headers: { get: () => 'application/json' },
      clone: () => ({
        json: async () => ({
          message: 'This sales order could not be confirmed',
          code: 'supply_confirm_refused',
          failing_lines: failing,
        }),
      }),
      json: async () => ({ message: 'This sales order could not be confirmed' }),
    } as unknown as Response;
    apiFetch.mockResolvedValue(refusal);
    const { confirmSupply, ConfirmSupplyError } = await loadRealService();

    const error = await confirmSupply('pso-1', { lines: [] }).catch((caught) => caught);

    expect(error).toBeInstanceOf(ConfirmSupplyError);
    expect(error.message).toBe('Backend said no');
    expect(error.failingLines).toEqual(failing);
  });

  it('still refuses with a message when the body names no line at all', async () => {
    const refusal = {
      ok: false,
      headers: { get: () => 'text/html' },
      clone: () => ({
        json: async () => {
          throw new Error('not json');
        },
      }),
      json: async () => ({}),
    } as unknown as Response;
    apiFetch.mockResolvedValue(refusal);
    const { confirmSupply } = await loadRealService();

    const error = await confirmSupply('pso-1', { lines: [] }).catch((caught) => caught);

    expect(error.message).toBe('Backend said no');
    expect(error.failingLines).toEqual([]);
  });
});
