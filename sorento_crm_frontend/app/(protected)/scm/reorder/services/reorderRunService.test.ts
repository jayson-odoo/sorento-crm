import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  createReorderRun,
  getCustomerOrders,
  getBuyRecommendationsForCash,
  getCoveredRecommendations,
  getReorderRun,
  getRecommendations,
  getProductImage,
  getProductImages,
  getTodayRun,
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

describe('reorderRunService - getTodayRun (AC-F01 / AC-F10, Stage 2 grain pass-through)', () => {
  it('returns decision_grain and front_planning_contract_version VERBATIM off a front-planning run', async () => {
    apiFetch.mockResolvedValue(
      ok({
        run_id: 'run-today',
        status: 'completed',
        buy_scope: 'network',
        decision_grain: 'location',
        front_planning_contract_version: 1,
        warehouse_codes: ['WH-KL'],
        warehouse_count: 1,
        started_at: '2026-08-03T02:00:00',
        finished_at: '2026-08-03T02:05:00',
        summary: null,
        is_today: true,
        in_progress: false,
      }),
    );
    const run = await getTodayRun();
    expect(calledUrl().pathname).toBe('/api/v1/scm/reorder-runs/today');
    expect(run).not.toBeNull();
    expect(run?.decision_grain).toBe('location');
    expect(run?.front_planning_contract_version).toBe(1);
  });

  it('does NOT fill in a grain on a legacy run - both fields stay null, verbatim', async () => {
    apiFetch.mockResolvedValue(
      ok({
        run_id: 'run-legacy',
        status: 'completed',
        buy_scope: 'network',
        decision_grain: null,
        front_planning_contract_version: null,
        warehouse_codes: ['WH-KL'],
        warehouse_count: 1,
        started_at: '2026-06-01T02:00:00',
        finished_at: '2026-06-01T02:05:00',
        summary: null,
        is_today: false,
        in_progress: false,
      }),
    );
    const run = await getTodayRun();
    expect(run?.decision_grain).toBeNull();
    expect(run?.front_planning_contract_version).toBeNull();
  });

  it('returns null - not a default run object - when no run exists yet', async () => {
    apiFetch.mockResolvedValue(ok(null));
    expect(await getTodayRun()).toBeNull();
  });

  it('surfaces the backend message when the read fails', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 500,
      headers: { get: () => 'application/json' },
      json: async () => ({ message: 'Database unavailable' }),
    } as unknown as Response);
    await expect(getTodayRun()).rejects.toThrow('Database unavailable');
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

  it("returns each row's project_need / retail_need / decisions_read_only UNTOUCHED (Stage 2)", async () => {
    apiFetch.mockResolvedValue(
      ok({
        data: [
          {
            id: 'rec-1',
            project_need: 120,
            retail_need: 55,
            decisions_read_only: true,
          },
          {
            id: 'rec-2',
            // NULL on a legacy row - the service must not coerce this to 0.
            project_need: null,
            retail_need: null,
            decisions_read_only: false,
          },
        ],
        pagination: { page: 1, limit: 25, total: 2, total_pages: 1 },
      }),
    );
    const page = await getRecommendations('run-9', { pageIndex: 0, pageSize: 25 });
    expect(page.data[0]).toMatchObject({
      project_need: 120,
      retail_need: 55,
      decisions_read_only: true,
    });
    expect(page.data[1]).toMatchObject({
      project_need: null,
      retail_need: null,
      decisions_read_only: false,
    });
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

  it("preserves each history row's OWN stamped grain, so a past run is never relabelled with today's policy (AC-F10)", async () => {
    apiFetch.mockResolvedValue(
      ok({
        data: [
          {
            run_id: 'run-old-location',
            status: 'completed',
            buy_scope: 'network',
            decision_grain: 'location',
            front_planning_contract_version: 1,
            warehouse_codes: ['WH-KL'],
            warehouse_count: 1,
            started_at: '2026-07-01T02:00:00',
            finished_at: '2026-07-01T02:05:00',
            summary: null,
          },
          {
            run_id: 'run-legacy',
            status: 'completed',
            buy_scope: 'network',
            decision_grain: null,
            front_planning_contract_version: null,
            warehouse_codes: ['WH-KL'],
            warehouse_count: 1,
            started_at: '2026-01-01T02:00:00',
            finished_at: '2026-01-01T02:05:00',
            summary: null,
          },
        ],
        pagination: { page: 1, limit: 8, total: 2, total_pages: 1 },
      }),
    );
    const page = await listReorderRuns(1, 8);
    expect(page.data[0].decision_grain).toBe('location');
    expect(page.data[0].front_planning_contract_version).toBe(1);
    // The legacy row is not backfilled to today's default grain.
    expect(page.data[1].decision_grain).toBeNull();
    expect(page.data[1].front_planning_contract_version).toBeNull();
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

describe('reorderRunService - getProductImages (AC-7)', () => {
  it('reads which products have a photo from one endpoint', async () => {
    apiFetch.mockResolvedValue(ok({ has_image: { p1: true } }));

    const out = await getProductImages('run-9');

    expect(calledUrl().pathname).toBe('/api/v1/scm/reorder-runs/run-9/product-images');
    expect(out.has_image.p1).toBe(true);
  });

  it('normalises a body with no images at all, so the caller never guards for it', async () => {
    apiFetch.mockResolvedValue(ok({}));
    expect(await getProductImages('run-9')).toEqual({ has_image: {} });
  });

  it('surfaces the backend message rather than a blank failure', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 404,
      headers: { get: () => 'application/json' },
      json: async () => ({ message: 'Reorder run not found.' }),
      text: async () => JSON.stringify({ message: 'Reorder run not found.' }),
    } as unknown as Response);

    await expect(getProductImages('nope')).rejects.toThrow(/not found/i);
  });
});

describe('reorderRunService - getProductImage (AC-7)', () => {
  it('signs one product photo, on the popover that asked for it', async () => {
    apiFetch.mockResolvedValue(
      ok({ url: 'https://cdn.test.invalid/p1.jpg?Signature=stub', is_primary: true }),
    );

    const out = await getProductImage('run-9', 'p1');

    expect(calledUrl().pathname).toBe('/api/v1/scm/reorder-runs/run-9/product-images/p1');
    expect(out).toEqual({ url: 'https://cdn.test.invalid/p1.jpg?Signature=stub', is_primary: true });
  });

  it('reads a product with no photo as a null url, not a failure', async () => {
    apiFetch.mockResolvedValue(ok({ url: null, is_primary: false }));
    expect(await getProductImage('run-9', 'p2')).toEqual({ url: null, is_primary: false });
  });
});

// ---------------------------------------------------------------------------
// paging the whole set: same rows, same order, without the staircase
// ---------------------------------------------------------------------------

/** A page of `n` rows whose ids name the page they came from. */
function page(pageNo: number, n: number, totalPages: number) {
  return ok({
    data: Array.from({ length: n }, (_, i) => ({ id: `p${pageNo}-r${i}` })),
    pagination: { page: pageNo, limit: 1000, total: totalPages * n, total_pages: totalPages },
  });
}

describe('reorderRunService - fetching every page of a plan', () => {
  it('returns the pages in order, so the merged list matches the serial loop', async () => {
    apiFetch
      .mockResolvedValueOnce(page(1, 2, 3))
      .mockResolvedValueOnce(page(2, 2, 3))
      .mockResolvedValueOnce(page(3, 2, 3));

    const rows = await getBuyRecommendationsForCash('run-1');

    expect(rows.map((r) => r.id)).toEqual([
      'p1-r0', 'p1-r1', 'p2-r0', 'p2-r1', 'p3-r0', 'p3-r1',
    ]);
  });

  it('asks for pages 2..N together rather than one after the other', async () => {
    // Page 1 has to be awaited alone - it is what reports total_pages. Everything after it
    // is independent, and issuing those serially is what made a big plan a staircase of
    // round trips. Proven by holding page 2 open: page 3 must already have been requested.
    let releasePage2: (v: unknown) => void = () => {};
    const page2 = new Promise((res) => {
      releasePage2 = res;
    });
    apiFetch
      .mockResolvedValueOnce(page(1, 1, 3))
      .mockImplementationOnce(() => page2)
      .mockResolvedValueOnce(page(3, 1, 3));

    const pending = getBuyRecommendationsForCash('run-1');
    // Page 2 is deliberately still unresolved here. If pages were fetched serially the
    // count would sit at 2 forever and this would time out.
    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(3));

    releasePage2(page(2, 1, 3));
    const rows = await pending;
    expect(rows.map((r) => r.id)).toEqual(['p1-r0', 'p2-r0', 'p3-r0']);
  });

  it('a single-page plan makes exactly one request', async () => {
    apiFetch.mockResolvedValueOnce(page(1, 3, 1));

    const rows = await getCoveredRecommendations('run-1');

    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(rows).toHaveLength(3);
  });
});

describe('reorderRunService - the page fetch stays inside the API pool', () => {
  /**
   * Pages that resolve on a later tick, recording how many were in flight at once.
   * `delay` is per page index, so a page can be made to finish out of turn.
   */
  function trackedPages(total: number, delay: (n: number) => number = () => 0) {
    const seen = { now: 0, peak: 0, order: [] as number[] };
    let asked = 0;
    apiFetch.mockImplementation(() => {
      asked += 1;
      const n = asked;
      seen.now += 1;
      seen.peak = Math.max(seen.peak, seen.now);
      return new Promise((res) => {
        setTimeout(() => {
          seen.now -= 1;
          seen.order.push(n);
          res(page(n, 1, total));
        }, delay(n));
      });
    });
    return seen;
  }

  it('never has more than five pages in flight at once', async () => {
    // Ten pages. Uncapped this puts nine on the wire together, and with the four type
    // queries running at the same time that is ~36 database sessions from a single tab
    // against a pool of 10 + 20 overflow.
    const seen = trackedPages(10);

    const rows = await getBuyRecommendationsForCash('run-1');

    expect(rows).toHaveLength(10);
    expect(seen.peak).toBeLessThanOrEqual(5);
    // And it does use the width it is allowed - a cap that serialised would be no better
    // than the loop this replaced.
    expect(seen.peak).toBeGreaterThan(1);
  });

  it('keeps the pages in order even though they finish out of order', async () => {
    // Later pages finish FIRST: page 4 after 0ms, page 1 after 30ms.
    const seen = trackedPages(4, (n) => (4 - n) * 10);

    const rows = await getBuyRecommendationsForCash('run-1');

    expect(rows.map((r) => r.id)).toEqual(['p1-r0', 'p2-r0', 'p3-r0', 'p4-r0']);
    // The completion order really was not the request order.
    expect(seen.order).not.toEqual([1, 2, 3, 4]);
  });

  it('one page failing fails the whole plan rather than returning a short list', async () => {
    apiFetch
      .mockResolvedValueOnce(page(1, 1, 3))
      .mockResolvedValueOnce(page(2, 1, 3))
      .mockResolvedValueOnce({
        ok: false,
        headers: { get: () => 'application/json' },
        json: async () => ({ detail: 'page 3 exploded' }),
      } as unknown as Response);

    await expect(getBuyRecommendationsForCash('run-1')).rejects.toThrow('page 3 exploded');
  });
});
