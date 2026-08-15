import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  createReorderRun,
  getCustomerOrders,
  getReorderRun,
  getRecommendations,
  listReorderRuns,
} from './reorderRunService';

function ok(body: unknown) {
  return {
    ok: true,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

/** Parse the URL passed to apiFetch on its last call. */
function calledUrl(): URL {
  const calls = apiFetch.mock.calls;
  const raw = String(calls[calls.length - 1][0]);
  return new URL(raw, 'http://x');
}

function lastInit(): RequestInit {
  const calls = apiFetch.mock.calls;
  return (calls[calls.length - 1][1] ?? {}) as RequestInit;
}

beforeEach(() => apiFetch.mockReset());

describe('reorderRunService - createReorderRun', () => {
  it('POSTs warehouse_codes + null budget, and normalises the 202 body', async () => {
    apiFetch.mockResolvedValue(
      ok({ run_id: 'run-9', status: 'running', buy_scope: 'network', stage: 'resolving_policies' }),
    );
    const run = await createReorderRun({ warehouse_codes: ['WH-KL', 'WH-JB'] });

    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/scm/reorder-runs');
    const init = lastInit();
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({
      warehouse_codes: ['WH-KL', 'WH-JB'],
      budget_id: null,
      include_market: false,
    });
    expect(run).toMatchObject({ run_id: 'run-9', status: 'running', summary: null, error: null });
  });

  it('forwards include_market when the market factor is toggled on (M7)', async () => {
    apiFetch.mockResolvedValue(
      ok({ run_id: 'run-10', status: 'running', buy_scope: 'warehouse', stage: 'resolving_policies' }),
    );
    await createReorderRun({
      warehouse_codes: ['WH-KL'],
      include_market: true,
    });
    expect(JSON.parse(String(lastInit().body))).toMatchObject({ include_market: true });
  });

  it('OMITS product_codes when the run was not narrowed, so an all-products run is unchanged (AC-B8a)', async () => {
    apiFetch.mockResolvedValue(
      ok({ run_id: 'run-11', status: 'running', buy_scope: 'warehouse', stage: 'resolving_policies' }),
    );
    await createReorderRun({ warehouse_codes: ['WH-KL'], product_codes: [] });
    expect(JSON.parse(String(lastInit().body))).not.toHaveProperty('product_codes');
  });

  it('forwards product_codes as human codes when the run IS narrowed (AC-B8a)', async () => {
    apiFetch.mockResolvedValue(
      ok({ run_id: 'run-12', status: 'running', buy_scope: 'warehouse', stage: 'resolving_policies' }),
    );
    await createReorderRun({
      warehouse_codes: ['WH-KL'],
      product_codes: ['SRTWT7408', 'SRTBS4832'],
    });
    expect(JSON.parse(String(lastInit().body))).toMatchObject({
      product_codes: ['SRTWT7408', 'SRTBS4832'],
    });
  });
});

describe('reorderRunService - getReorderRun', () => {
  it('maps the poll payload including the completed summary', async () => {
    apiFetch.mockResolvedValue(
      ok({
        run_id: 'run-9',
        status: 'completed',
        stage: 'writing_recommendations',
        buy_scope: 'warehouse',
        error: null,
        summary: {
          buy_count: 5,
          disposition_count: 2,
          exception_count: 1,
          total_cash_impact: 12345,
          recommendation_count: 8,
        },
      }),
    );
    const run = await getReorderRun('run-9');
    expect(calledUrl().pathname).toBe('/api/v1/scm/reorder-runs/run-9');
    expect(run.status).toBe('completed');
    expect(run.buy_scope).toBe('warehouse');
    expect(run.summary?.recommendation_count).toBe(8);
  });
});

describe('reorderRunService - getRecommendations', () => {
  it('sends page/limit + sort/dir + type + query as server-side params', async () => {
    apiFetch.mockResolvedValue(
      ok({ data: [], pagination: { page: 3, limit: 25, total: 0, total_pages: 1 } }),
    );
    await getRecommendations('run-9', {
      pageIndex: 2,
      pageSize: 25,
      type: 'exception',
      searchQuery: 'basin',
      sorting: [{ id: 'order_qty', desc: true }],
    });
    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/scm/reorder-runs/run-9/recommendations');
    expect(u.searchParams.get('page')).toBe('3'); // 0-based → 1-based
    expect(u.searchParams.get('limit')).toBe('25');
    expect(u.searchParams.get('sort')).toBe('order_qty');
    expect(u.searchParams.get('dir')).toBe('desc');
    expect(u.searchParams.get('type')).toBe('exception');
    expect(u.searchParams.get('query')).toBe('basin');
  });

  it('omits type + sort when unset', async () => {
    apiFetch.mockResolvedValue(
      ok({ data: [], pagination: { page: 1, limit: 25, total: 0, total_pages: 1 } }),
    );
    await getRecommendations('run-9', { pageIndex: 0, pageSize: 25, type: null });
    const u = calledUrl();
    expect(u.searchParams.get('type')).toBeNull();
    expect(u.searchParams.get('sort')).toBeNull();
    expect(u.searchParams.get('query')).toBeNull();
  });
});

describe('reorderRunService - listReorderRuns', () => {
  it('requests newest-first page/limit and returns the history envelope', async () => {
    apiFetch.mockResolvedValue(
      ok({
        data: [
          {
            run_id: 'run-b',
            status: 'completed',
            buy_scope: 'network',
            warehouse_codes: ['WH-KL', 'WH-JB'],
            warehouse_count: 2,
            started_at: '2026-07-16T02:00:00',
            finished_at: '2026-07-16T02:00:05',
            summary: {
              buy_count: 4,
              disposition_count: 1,
              exception_count: 0,
              total_cash_impact: 9000,
              recommendation_count: 5,
            },
          },
        ],
        pagination: { page: 2, limit: 8, total: 12, total_pages: 2 },
      }),
    );
    const page = await listReorderRuns(2, 8);
    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/scm/reorder-runs');
    expect(u.searchParams.get('page')).toBe('2'); // 1-based page → page param
    expect(u.searchParams.get('limit')).toBe('8');
    expect(page.pagination.total).toBe(12);
    expect(page.data[0].run_id).toBe('run-b');
    expect(page.data[0].warehouse_codes).toEqual(['WH-KL', 'WH-JB']);
    expect(page.data[0].summary?.recommendation_count).toBe(5);
  });
});

describe('reorderRunService - getCustomerOrders (AC-4.1)', () => {
  it('asks for the run, product, side and customer key it was opened on', async () => {
    apiFetch.mockResolvedValue(
      ok({
        lines: [
          {
            so_number: 'SO414050',
            order_date: '2026-07-12',
            qty: 60,
            unit_price: 0.94,
            warehouse_code: 'BRW-BB',
          },
        ],
        total: 27,
        shown: 1,
      }),
    );
    const out = await getCustomerOrders('run-1', 'prod-1', 'project', 'debtor:300-R009');

    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/scm/reorder-runs/run-1/customer-orders');
    expect(u.searchParams.get('product_id')).toBe('prod-1');
    expect(u.searchParams.get('segment')).toBe('project');
    // The three-case key travels verbatim: the backend, not the FE, decides what a
    // `debtor:` prefix means.
    expect(u.searchParams.get('customer_key')).toBe('debtor:300-R009');
    expect(u.searchParams.get('limit')).toBe('20');
    expect(out.total).toBe(27);
    expect(out.lines[0].unit_price).toBe(0.94);
  });

  it('surfaces the backend message rather than an empty list', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 422,
      headers: { get: () => 'application/json' },
      json: async () => ({ message: 'Unknown segment.' }),
    } as unknown as Response);

    await expect(
      getCustomerOrders('run-1', 'prod-1', 'wholesale', 'none'),
    ).rejects.toThrow('Unknown segment.');
  });
});
