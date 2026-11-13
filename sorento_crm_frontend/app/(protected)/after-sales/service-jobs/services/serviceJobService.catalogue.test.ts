/**
 * AFTER-SALES-P2 browser pass: `searchCatalogueProducts` reads the products list that exists in the real app,
 * `GET /api/v1/master-data/products` (the backend list route takes the search term as `query`; `/api/v1/products` is a 404).
 * The Add product picker and the rule tester picker both go through it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import { searchCatalogueProducts } from './serviceJobService';

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({
    ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({ data: [{ id: 'p-1', product_code: 'SRTWC6020-SH-UF', product_name: 'Water closet', list_price: 1 }], pagination: { total: 1, page: 1, limit: 20 } }),
  });
});

describe('searchCatalogueProducts', () => {
  it('calls /api/v1/master-data/products with the search term as query', async () => {
    await searchCatalogueProducts('WC6020');
    const url = new URL(String(apiFetch.mock.calls[0][0]), 'http://x');
    expect(url.pathname).toBe('/api/v1/master-data/products');
    expect(url.searchParams.get('query')).toBe('WC6020');
  });

  it('returns only id, code and name', async () => {
    expect(await searchCatalogueProducts('WC')).toEqual([{ id: 'p-1', product_code: 'SRTWC6020-SH-UF', product_name: 'Water closet' }]);
  });
});
