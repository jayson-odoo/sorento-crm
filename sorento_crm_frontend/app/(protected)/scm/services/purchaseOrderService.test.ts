/**
 * SCM M4 Slice B - purchaseOrderService (list incl. drafts, bulk-confirm, create-GR).
 * Pins the FE→BE contract documented at the top of `purchaseOrderService.ts`.
 *   AC-M4.6 (draft POs listed; confirm → active/on-order; create-GR from active)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  bulkConfirmPurchaseOrders,
  createGrFromPurchaseOrder,
  getPurchaseOrders,
} from './purchaseOrderService';

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}
function fail(detail: string, status = 400) {
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
function lastInit(): RequestInit {
  const calls = apiFetch.mock.calls;
  return (calls[calls.length - 1][1] ?? {}) as RequestInit;
}

beforeEach(() => apiFetch.mockReset());

describe('purchaseOrderService - list (AC-M4.6)', () => {
  it('GETs /purchase-orders with buildDataGridParams page/limit/sort/dir + status filter', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { page: 1, total: 0 } }));
    await getPurchaseOrders({
      pageIndex: 1,
      pageSize: 25,
      sortField: 'po_number',
      sortDir: 'desc',
      searchQuery: 'PO-DRAFT',
      status: 'draft_recommendation',
      supplier: null,
    });
    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/scm/purchase-orders');
    expect(u.searchParams.get('page')).toBe('2'); // 0-based index 1 → 1-based page 2
    expect(u.searchParams.get('limit')).toBe('25');
    expect(u.searchParams.get('sort')).toBe('po_number');
    expect(u.searchParams.get('dir')).toBe('desc');
    expect(u.searchParams.get('query')).toBe('PO-DRAFT');
    expect(u.searchParams.get('status')).toBe('draft_recommendation');
  });

  it('omits status + sort when unset (drafts included by default)', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { page: 1, total: 0 } }));
    await getPurchaseOrders({ pageIndex: 0, pageSize: 25, status: null, supplier: null });
    const u = calledUrl();
    expect(u.searchParams.get('status')).toBeNull();
    expect(u.searchParams.get('sort')).toBeNull();
  });

  it('surfaces the backend error on a failed list', async () => {
    apiFetch.mockResolvedValue(fail('Module disabled', 403));
    await expect(
      getPurchaseOrders({ pageIndex: 0, pageSize: 25, status: null, supplier: null }),
    ).rejects.toThrow('Module disabled');
  });
});

describe('purchaseOrderService - bulk-confirm (AC-M4.6)', () => {
  it('POSTs the draft ids to /bulk-confirm and returns the confirmed count', async () => {
    apiFetch.mockResolvedValue(ok({ confirmed_count: 2 }));
    const res = await bulkConfirmPurchaseOrders(['po-1', 'po-2']);
    expect(calledUrl().pathname).toBe('/api/v1/scm/purchase-orders/bulk-confirm');
    expect(lastInit().method).toBe('POST');
    expect(JSON.parse(String(lastInit().body))).toEqual({ ids: ['po-1', 'po-2'] });
    expect(res).toEqual({ confirmed_count: 2 });
  });

  it('surfaces the backend error on failure', async () => {
    apiFetch.mockResolvedValue(fail('No drafts in selection'));
    await expect(bulkConfirmPurchaseOrders(['po-1'])).rejects.toThrow('No drafts in selection');
  });
});

describe('purchaseOrderService - create-GR (AC-M4.6)', () => {
  it('POSTs to /purchase-orders/{id}/create-gr and returns the GR reference', async () => {
    apiFetch.mockResolvedValue(ok({ gr_reference: 'GR-2026/07-0003' }));
    const res = await createGrFromPurchaseOrder('po-5');
    expect(calledUrl().pathname).toBe('/api/v1/scm/purchase-orders/po-5/create-gr');
    expect(lastInit().method).toBe('POST');
    expect(res).toEqual({ gr_reference: 'GR-2026/07-0003' });
  });

  it('surfaces the backend error on failure', async () => {
    apiFetch.mockResolvedValue(fail('PO is still a draft'));
    await expect(createGrFromPurchaseOrder('po-5')).rejects.toThrow('PO is still a draft');
  });
});
