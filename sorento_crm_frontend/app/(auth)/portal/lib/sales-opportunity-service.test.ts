/**
 * sales-opportunity-service: the portal contract with
 * `/api/v1/public/portal/sales-opportunities` and `/lookups/products` (plan section 16;
 * UAC S2-3 to S2-6, S2-9, S2-15, S2-16).
 *
 * Same shape as `price-tag-request-service.r9.test.ts`: `portalFetch` is mocked, `unwrap`/
 * `extractApiError` stay real, so a wrong path/method/body or a dropped error message fails
 * for the right reason. `./sales-opportunity-service` does not exist yet on this branch, so
 * this whole file is expected to fail to resolve the import.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./portal-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./portal-client')>();
  return { ...actual, portalFetch: vi.fn() };
});

import { portalFetch } from './portal-client';
import {
  createPortalSalesOpportunity,
  getPortalCustomerOptions,
  getPortalOpportunityMeta,
  getPortalProductOptions,
  getPortalSalesOpportunity,
  listPortalSalesOpportunities,
  updatePortalSalesOpportunity,
} from './sales-opportunity-service';

const mockFetch = vi.mocked(portalFetch);

const BASE = '/api/v1/public/portal/sales-opportunities';

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as never;
}

function fail(status: number, message: string) {
  // extractApiError checks content-type first; a stub without headers falls into the
  // text branch and answers the fallback instead of the server's message (repo convention,
  // see price-tag-request-service.r9.test.ts).
  return {
    ok: false,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({ message }),
    text: async () => JSON.stringify({ message }),
  } as never;
}

beforeEach(() => mockFetch.mockReset());

describe('listPortalSalesOpportunities', () => {
  it('GETs the base path and returns the items array', async () => {
    mockFetch.mockResolvedValue(ok({ items: [{ id: 'o1' }, { id: 'o2' }] }));
    const rows = await listPortalSalesOpportunities();
    expect(mockFetch).toHaveBeenCalledWith(BASE);
    expect(rows).toEqual([{ id: 'o1' }, { id: 'o2' }]);
  });
});

describe('getPortalSalesOpportunity', () => {
  it('GETs the detail path', async () => {
    mockFetch.mockResolvedValue(ok({ id: 'o1' }));
    const row = await getPortalSalesOpportunity('o1');
    expect(mockFetch).toHaveBeenCalledWith(`${BASE}/o1`);
    expect(row).toEqual({ id: 'o1' });
  });
});

describe('createPortalSalesOpportunity', () => {
  it('POSTs the body as JSON', async () => {
    mockFetch.mockResolvedValue(ok({ id: 'o1' }));
    const body = {
      prospect_name: 'ZZT Prospect',
      title: 'ZZT Opp',
      expected_amount: '500',
      expected_close_date: '2026-11-01',
      lines: [{ product_id: 'p1', qty: 2 }],
    };
    await createPortalSalesOpportunity(body);
    expect(mockFetch).toHaveBeenCalledWith(BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  });
});

describe('updatePortalSalesOpportunity', () => {
  it('PATCHes the detail path with the body as JSON', async () => {
    mockFetch.mockResolvedValue(ok({ id: 'o1' }));
    const body = { status_id: 'st-qualified' };
    await updatePortalSalesOpportunity('o1', body);
    expect(mockFetch).toHaveBeenCalledWith(`${BASE}/o1`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  });
});

describe('getPortalCustomerOptions', () => {
  it('GETs customer-options with q and returns items/prospect/blocked as-is', async () => {
    mockFetch.mockResolvedValue(
      ok({ items: [{ customer_id: 'c1', customer_code: 'C1', customer_name: 'Kedai Mine' }], prospect: null, blocked: null }),
    );
    const result = await getPortalCustomerOptions('kedai');
    expect(mockFetch).toHaveBeenCalledWith(`${BASE}/customer-options?q=kedai`);
    expect(result.items).toEqual([{ customer_id: 'c1', customer_code: 'C1', customer_name: 'Kedai Mine' }]);
    expect(result.prospect).toBeNull();
    expect(result.blocked).toBeNull();
  });
});

describe('getPortalOpportunityMeta', () => {
  it('GETs the meta path', async () => {
    mockFetch.mockResolvedValue(ok({ stages: [], lost_reasons: [] }));
    const meta = await getPortalOpportunityMeta();
    expect(mockFetch).toHaveBeenCalledWith(`${BASE}/meta`);
    expect(meta).toEqual({ stages: [], lost_reasons: [] });
  });
});

describe('getPortalProductOptions', () => {
  it('GETs the shared product lookup with q and maps id/code/name', async () => {
    mockFetch.mockResolvedValue(
      ok([{ product_id: 'p1', product_code: 'ZZT-001', product_name: 'ZZT Basin' }]),
    );
    const options = await getPortalProductOptions('basin');
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/public/portal/lookups/products?q=basin');
    expect(options).toEqual([{ id: 'p1', code: 'ZZT-001', name: 'ZZT Basin' }]);
  });
});

describe('error propagation', () => {
  it('a non-ok response throws an Error carrying the server message', async () => {
    mockFetch.mockResolvedValue(fail(422, 'A customer or a prospect is required.'));
    await expect(
      createPortalSalesOpportunity({ title: 'ZZT', expected_amount: '1', expected_close_date: '2026-11-01' }),
    ).rejects.toThrow(/customer or a prospect/);
  });
});
