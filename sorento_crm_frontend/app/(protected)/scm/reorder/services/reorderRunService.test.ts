import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  createReorderRun,
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

describe('reorderRunService — createReorderRun', () => {
  it('POSTs warehouse_codes + buy_scope + null budget, and normalises the 202 body', async () => {
    apiFetch.mockResolvedValue(
      ok({ run_id: 'run-9', status: 'running', buy_scope: 'network', stage: 'resolving_policies' }),
    );
    const run = await createReorderRun({ warehouse_codes: ['WH-KL', 'WH-JB'], buy_scope: 'network' });

    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/scm/reorder-runs');
    const init = lastInit();
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({
      warehouse_codes: ['WH-KL', 'WH-JB'],
      buy_scope: 'network',
      budget_id: null,
    });
    expect(run).toMatchObject({ run_id: 'run-9', status: 'running', summary: null, error: null });
  });
});

describe('reorderRunService — getReorderRun', () => {
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

describe('reorderRunService — getRecommendations', () => {
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

describe('reorderRunService — listReorderRuns', () => {
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
