/**
 * Lane C, PLAN-order-sheet-oi-reports-22sep.md (AC-C1/AC-C2): `exportOiWorksheet` - the
 * "OI worksheet Excel" export - through the SAME `/order-summary/export` pipeline
 * `exportOrderSheet` already uses (and the low stock report once did), with a third `format` value
 * (`'oi_worksheet'`). Modelled directly on `summaryOrderService.test.ts`'s own
 * `exportLowStockReport` block.
 *
 * `exportOiWorksheet` does not exist in `summaryOrderService.ts` yet, so every case here
 * is red for a TypeError ("... is not a function" / `undefined`), not a fixture bug, until
 * C1-FE lands.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

const mockStore = vi.hoisted(() => ({
  USE_SUMMARY_ORDER_MOCKS: false,
  mockOrderSummaryDemand: vi.fn(),
}));
vi.mock('../lib/summaryOrderMockStore', () => mockStore);

import { exportOiWorksheet } from './summaryOrderService';

function ok(body: unknown) {
  return {
    ok: true,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('summaryOrderService - exportOiWorksheet (AC-C1/AC-C2)', () => {
  it('POSTs the same export endpoint with format "oi_worksheet" and returns the '
    + 'MyDownload row', async () => {
    const download = { id: 'dl-42', kind: 'oi_worksheet_xlsx', status: 'pending', filename: null };
    apiFetch.mockResolvedValue(ok(download));

    const result = await exportOiWorksheet('run-2026-w38');

    expect(apiFetch).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(new URL(url, 'http://x').pathname).toBe('/api/v1/scm/order-summary/export');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({
      run_id: 'run-2026-w38',
      format: 'oi_worksheet',
    });
    expect(result).toEqual(download);
  });

  it('throws the extracted error message on a non-ok response', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 422,
      headers: { get: () => 'application/json' },
      json: async () => ({ message: 'Narrow the plan first' }),
    } as unknown as Response);

    await expect(exportOiWorksheet('run-2026-w38')).rejects.toThrow('Narrow the plan first');
  });
});
