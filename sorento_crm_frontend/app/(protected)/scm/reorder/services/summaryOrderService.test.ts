/**
 * SCM Summary Order Report feature service - `getOrderSummaryDemand` (AC-C2.3/C2.4) and
 * `exportOrderSheet` (S4, PLAN-po-spo-site-pool-and-order-sheet-downloads, AC-19/AC-20).
 *
 * Review fix round 3, finding 6: `getOrderSummary`/`getOrderSummarySuppliers`/
 * `recordOrderDecision` and their own blocks here are deleted - the Order summary
 * report page they served is retired (S10, round 2). `getOrderSummaryDemand` survives
 * (`DemandDrillPopover` still opens it).
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
 *
 * `exportOrderSheet` has no mock branch at all - it always posts for real (S4-FE, commit
 * 1639e6685). AC-19/AC-20: it POSTs `{ run_id, format }` and returns the created
 * `MyDownload` row directly off `res.json()` - no blob is ever read off the response, and
 * `saveBlobAs`/`filenameFromContentDisposition` are not imported by this module any more.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

// The flag lives in the mock store; the store is deleted in Phase 2, so both
// branches are exercised by controlling it here rather than by editing source.
const mockStore = vi.hoisted(() => ({
  USE_SUMMARY_ORDER_MOCKS: true,
  mockOrderSummaryDemand: vi.fn(),
}));
vi.mock('../lib/summaryOrderMockStore', () => mockStore);

import { exportOrderSheet, getOrderSummaryDemand } from './summaryOrderService';

function ok(body: unknown) {
  return {
    ok: true,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}
function calledUrl(): URL {
  const calls = apiFetch.mock.calls;
  return new URL(String(calls[calls.length - 1][0]), 'http://x');
}

beforeEach(() => {
  apiFetch.mockReset();
  mockStore.mockOrderSummaryDemand.mockReset();
  mockStore.USE_SUMMARY_ORDER_MOCKS = true;
});

describe('summaryOrderService - Phase-1 mock branch', () => {
  it('serves the drill fixture for both aggregates', async () => {
    mockStore.mockOrderSummaryDemand.mockResolvedValue({ kind: 'dealer', dealer_lines: [] });
    await getOrderSummaryDemand('B2155-NL-BLUE', 'dealer', 'run-2026-w32');
    expect(mockStore.mockOrderSummaryDemand).toHaveBeenCalledWith('B2155-NL-BLUE', 'dealer');
    expect(apiFetch).not.toHaveBeenCalled();
  });
});

describe('summaryOrderService - Phase-2 real branch', () => {
  beforeEach(() => {
    mockStore.USE_SUMMARY_ORDER_MOCKS = false;
  });

  it('GETs the demand drill by PRODUCT CODE with the aggregate kind', async () => {
    apiFetch.mockResolvedValue(ok({ product_code: 'B2155-NL-BLUE', dealer_lines: [] }));
    await getOrderSummaryDemand('B2155-NL-BLUE', 'dealer', 'run-2026-w32');

    const url = calledUrl();
    expect(url.pathname).toBe('/api/v1/scm/order-summary/B2155-NL-BLUE/demand');
    expect(url.searchParams.get('kind')).toBe('dealer');
    expect(url.searchParams.get('run_id')).toBe('run-2026-w32');
  });
});

describe('summaryOrderService - exportOrderSheet (AC-19/AC-20)', () => {
  it('POSTs { run_id, format } to /order-summary/export and returns the MyDownload row '
    + 'straight off res.json() - no blob API is touched', async () => {
    const download = { id: 'dl-1', kind: 'order_sheet_xlsx', status: 'pending', filename: null };
    apiFetch.mockResolvedValue(ok(download));

    const result = await exportOrderSheet('run-2026-w32', 'xlsx');

    expect(apiFetch).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(new URL(url, 'http://x').pathname).toBe('/api/v1/scm/order-summary/export');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ run_id: 'run-2026-w32', format: 'xlsx' });
    expect(result).toEqual(download);
  });

  it('throws the extracted error message on a non-ok response (AC-20)', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 422,
      headers: { get: () => 'application/json' },
      json: async () => ({ message: 'Narrow the plan first' }),
    } as unknown as Response);

    await expect(exportOrderSheet('run-2026-w32', 'pdf')).rejects.toThrow(
      'Narrow the plan first',
    );
  });
});
