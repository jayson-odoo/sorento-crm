/**
 * DOC-RELATIONS: the Related table's service hits each record's own `/related` route with the
 * server-side sort. Paths are asserted directly: a typo is a 404 on the backend, not an error here.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import { getRelatedDocuments } from './relatedDocumentsService';

const BODY = { sales_orders: [], delivery_orders: [], billing_documents: [], rows: [] };

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

beforeEach(() => apiFetch.mockReset());

describe('getRelatedDocuments', () => {
  it.each([
    ['sales_order', '/api/v1/scm/sales-orders/so-1/related'],
    ['delivery_order', '/api/v1/order-management/orders/so-1/related'],
    ['billing_document', '/api/v1/finance/billing-documents/so-1/related'],
  ] as const)('reads %s relations from its own route', async (kind, path) => {
    apiFetch.mockResolvedValue(ok(BODY));
    await getRelatedDocuments(kind, 'so-1', 'amount', 'desc');
    const [url] = apiFetch.mock.calls[0];
    expect(url.split('?')[0]).toBe(path);
    const qs = new URLSearchParams(url.split('?')[1]);
    expect(qs.get('sort')).toBe('amount');
    expect(qs.get('dir')).toBe('desc');
  });

  it('throws the server message on a refusal', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 403,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: 'Permission required: scm.dashboard.view' }),
    } as Response);
    await expect(getRelatedDocuments('sales_order', 'so-1', 'doc_date', 'asc')).rejects.toThrow(
      /Permission required/,
    );
  });
});
