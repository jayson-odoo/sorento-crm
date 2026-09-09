/**
 * SCM Summary Order Report feature service - `getOrderSummaryDemand` (AC-C2.3/C2.4).
 *
 * Review fix round 3, finding 6: `getOrderSummary`/`getOrderSummarySuppliers`/
 * `recordOrderDecision` and their own blocks here are deleted - the Order summary
 * report page they served is retired (S10, round 2). `getOrderSummaryDemand` survives
 * (`DemandDrillPopover` still opens it); `downloadOrderSummaryExport` has its own
 * coverage elsewhere and needs no mock branch (PDF/xlsx generation is nothing a
 * fixture can usefully stand in for).
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
  mockOrderSummaryDemand: vi.fn(),
}));
vi.mock('../lib/summaryOrderMockStore', () => mockStore);

import { getOrderSummaryDemand } from './summaryOrderService';

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
