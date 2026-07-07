/**
 * Verifies the products list query key includes `variant_filter`, so changing the
 * Base/Variant/All filter produces a distinct cache key and triggers a refetch
 * (rather than serving the previous filter's cached page).
 */
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getProducts = vi.fn(async () => ({ data: [], pagination: { total: 0 } }));

vi.mock('../services/productService', () => ({
  getProducts: (...a: unknown[]) => getProducts(...a),
  // useProducts.ts imports the whole surface; stub the rest so the module loads.
  getProduct: vi.fn(),
  createProduct: vi.fn(),
  updateProduct: vi.fn(),
  deleteProduct: vi.fn(),
  duplicateProduct: vi.fn(),
  bulkUpdateProducts: vi.fn(),
  bulkDeleteProducts: vi.fn(),
  getPriceHistory: vi.fn(),
  setVariantParent: vi.fn(),
  unlinkVariant: vi.fn(),
  resetVariantAuto: vi.fn(),
  PRODUCT_NEIGHBOURS_PATH: '/api/v1/master-data/products/neighbours',
}));

import { useProducts } from './useProducts';
import type { GetProductsParams } from '../services/productService';

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

const base: GetProductsParams = {
  pageIndex: 0,
  pageSize: 50,
  sorting: [],
  searchQuery: '',
};

beforeEach(() => {
  getProducts.mockClear();
});

describe('useProducts variant_filter query key', () => {
  it('defaults to fetching without a variant_filter (all)', async () => {
    const Wrapper = wrapper();
    renderHook(() => useProducts({ ...base }), { wrapper: Wrapper });

    await waitFor(() => expect(getProducts).toHaveBeenCalledTimes(1));
    expect(getProducts).toHaveBeenCalledWith(
      expect.not.objectContaining({ variant_filter: expect.anything() }),
    );
  });

  it('refetches when variant_filter changes (new cache key)', async () => {
    const Wrapper = wrapper();
    const { rerender } = renderHook((p: GetProductsParams) => useProducts(p), {
      wrapper: Wrapper,
      initialProps: { ...base, variant_filter: 'all' } as GetProductsParams,
    });

    await waitFor(() => expect(getProducts).toHaveBeenCalledTimes(1));

    rerender({ ...base, variant_filter: 'base' });

    await waitFor(() => expect(getProducts).toHaveBeenCalledTimes(2));
    expect(getProducts).toHaveBeenLastCalledWith(
      expect.objectContaining({ variant_filter: 'base' }),
    );
  });
});
