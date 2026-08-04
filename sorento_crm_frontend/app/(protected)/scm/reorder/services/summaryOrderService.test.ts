/**
 * SCM Summary Order Report feature service (UAC Group C2 / C3).
 *
 * Two things are pinned here, because they are the two things Phase 2 flips:
 *
 *  1) The MOCK branch, which is what Phase 1 actually runs: `USE_SUMMARY_ORDER_MOCKS`
 *     true must serve the fixture and make NO request. A mock branch that quietly
 *     calls the backend is the failure this catches.
 *  2) The REAL branch's request shape - flat `/api/v1/scm/order-summary`, human
 *     codes in the path, and `extractApiError` on a non-ok response. It is
 *     unreachable while the flag is on, so nothing but a test can prove it right
 *     before the flag flips.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

// The flag lives in the mock store; the store is deleted in Phase 2, so both
// branches are exercised by controlling it here rather than by editing source.
const mockStore = vi.hoisted(() => ({
  USE_SUMMARY_ORDER_MOCKS: true,
  mockOrderSummary: vi.fn(),
  mockOrderSummaryDemand: vi.fn(),
  mockOrderSummarySuppliers: vi.fn(),
  mockRecordOrderDecision: vi.fn(),
}));
vi.mock('../lib/summaryOrderMockStore', () => mockStore);

import {
  getOrderSummary,
  getOrderSummaryDemand,
  getOrderSummarySuppliers,
  recordOrderDecision,
} from './summaryOrderService';

function ok(body: unknown) {
  return {
    ok: true,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}
function fail(detail: string, status = 404) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    text: async () => JSON.stringify({ detail }),
  } as unknown as Response;
}
function calledUrl(): URL {
  const calls = apiFetch.mock.calls;
  return new URL(String(calls[calls.length - 1][0]), 'http://x');
}

beforeEach(() => {
  apiFetch.mockReset();
  mockStore.mockOrderSummary.mockReset();
  mockStore.mockOrderSummaryDemand.mockReset();
  mockStore.mockOrderSummarySuppliers.mockReset();
  mockStore.mockRecordOrderDecision.mockReset();
  mockStore.USE_SUMMARY_ORDER_MOCKS = true;
});

describe('summaryOrderService - Phase-1 mock branch', () => {
  it('serves the report fixture and never touches the network', async () => {
    mockStore.mockOrderSummary.mockResolvedValue({ run_id: 'run-2026-w32', rows: [] });
    const out = await getOrderSummary({ run_id: 'run-2026-w32', as_of: '2026-08-03' });
    expect(out.run_id).toBe('run-2026-w32');
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('serves the drill fixture for both aggregates', async () => {
    mockStore.mockOrderSummaryDemand.mockResolvedValue({ kind: 'dealer', dealer_lines: [] });
    await getOrderSummaryDemand('B2155-NL-BLUE', 'dealer', 'run-2026-w32');
    expect(mockStore.mockOrderSummaryDemand).toHaveBeenCalledWith('B2155-NL-BLUE', 'dealer');
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('serves the supplier fixture', async () => {
    mockStore.mockOrderSummarySuppliers.mockResolvedValue({ candidates: [] });
    await getOrderSummarySuppliers('SRTWT7408');
    expect(mockStore.mockOrderSummarySuppliers).toHaveBeenCalledWith('SRTWT7408');
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('serves the mocked decision without posting anything', async () => {
    mockStore.mockRecordOrderDecision.mockResolvedValue({ chosen_qty: 600 });
    const out = await recordOrderDecision('B2155-NL-BLUE', {
      run_id: 'run-2026-w32',
      chosen_qty: 600,
      supplier_code: 'GDS',
    });
    expect(out.chosen_qty).toBe(600);
    expect(apiFetch).not.toHaveBeenCalled();
  });
});

describe('summaryOrderService - Phase-2 real branch', () => {
  beforeEach(() => {
    mockStore.USE_SUMMARY_ORDER_MOCKS = false;
  });

  it('GETs the flat /scm/order-summary route with run_id and as_of', async () => {
    apiFetch.mockResolvedValue(ok({ run_id: 'run-2026-w32', rows: [] }));
    await getOrderSummary({ run_id: 'run-2026-w32', as_of: '2026-08-03' });

    const url = calledUrl();
    // Flat under /scm/, like every other SCM route - no nested reorder/ segment.
    expect(url.pathname).toBe('/api/v1/scm/order-summary');
    expect(url.searchParams.get('run_id')).toBe('run-2026-w32');
    expect(url.searchParams.get('as_of')).toBe('2026-08-03');
    // Human codes only: no product/supplier id of any kind is sent.
    expect(url.search).not.toMatch(/product_id|supplier_id|warehouse_id/);
  });

  it('omits both params rather than sending empty ones when reading the current run', async () => {
    apiFetch.mockResolvedValue(ok({ rows: [] }));
    await getOrderSummary();
    expect(calledUrl().pathname).toBe('/api/v1/scm/order-summary');
    expect(calledUrl().search).toBe('');
  });

  it('GETs the demand drill by PRODUCT CODE with the aggregate kind', async () => {
    apiFetch.mockResolvedValue(ok({ product_code: 'B2155-NL-BLUE', dealer_lines: [] }));
    await getOrderSummaryDemand('B2155-NL-BLUE', 'dealer', 'run-2026-w32');

    const url = calledUrl();
    expect(url.pathname).toBe('/api/v1/scm/order-summary/B2155-NL-BLUE/demand');
    expect(url.searchParams.get('kind')).toBe('dealer');
    expect(url.searchParams.get('run_id')).toBe('run-2026-w32');
  });

  it('GETs the supplier candidates by product code', async () => {
    apiFetch.mockResolvedValue(ok({ product_code: 'SRTSK2210', candidates: [] }));
    await getOrderSummarySuppliers('SRTSK2210');
    expect(calledUrl().pathname).toBe('/api/v1/scm/order-summary/SRTSK2210/suppliers');
  });

  it('POSTs the decision with the chosen quantity and supplier CODE', async () => {
    apiFetch.mockResolvedValue(ok({ product_code: 'B2155-NL-BLUE', chosen_qty: 600 }));
    await recordOrderDecision('B2155-NL-BLUE', {
      run_id: 'run-2026-w32',
      chosen_qty: 600,
      supplier_code: 'GDS',
    });

    expect(calledUrl().pathname).toBe('/api/v1/scm/order-summary/B2155-NL-BLUE/decision');
    const init = apiFetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({
      run_id: 'run-2026-w32',
      chosen_qty: 600,
      supplier_code: 'GDS',
    });
  });

  it('sends a quantity ABOVE the shortfall unchanged - it is a decision, not an error', async () => {
    apiFetch.mockResolvedValue(ok({ chosen_qty: 600 }));
    await recordOrderDecision('B2155-NL-BLUE', {
      run_id: 'run-2026-w32',
      chosen_qty: 600,
      supplier_code: 'GDS',
    });
    const init = apiFetch.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body)).chosen_qty).toBe(600);
  });

  it('throws the extracted backend message when the report cannot be built', async () => {
    apiFetch.mockResolvedValue(fail('No run for 2026-07-27'));
    await expect(getOrderSummary({ as_of: '2026-07-27' })).rejects.toThrow('No run for 2026-07-27');
  });

  it('throws the extracted message when the decision is refused', async () => {
    apiFetch.mockResolvedValue(fail('Supplier GDS is not linked to this product', 409));
    await expect(
      recordOrderDecision('B2155-NL-BLUE', {
        run_id: 'run-2026-w32',
        chosen_qty: 600,
        supplier_code: 'GDS',
      }),
    ).rejects.toThrow('Supplier GDS is not linked to this product');
  });

  it('percent-encodes a product code so a slash in it cannot escape the path', async () => {
    apiFetch.mockResolvedValue(ok({ candidates: [] }));
    await getOrderSummarySuppliers('B2155/NL');
    expect(String(apiFetch.mock.calls[0][0])).toContain('B2155%2FNL');
  });
});
