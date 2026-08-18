/**
 * ProductsList - product-discontinued deep-link `brand_id` preservation (AC-17).
 *
 * The reload-clean effect (ProductsList.tsx ~line 120) strips every persisted
 * list param on a hard refresh EXCEPT a "products discontinued" deep link, which
 * is an explicit navigation intent. It must keep BOTH `discontinued_batch_id` and
 * `brand_id` (comma-joined scope filter), never just the batch id. On a normal
 * (non-reload) navigation, a comma-valued `brand_id` still filters the grid via
 * `getProducts`, even though it has no single-select dropdown equivalent.
 *
 * Same DataGrid/service-mock technique as ProductsList.discontinued.test.tsx.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getProducts = vi.fn();

vi.mock('@/components/ui/data-grid', () => ({
  DataGrid: () => null,
}));

vi.mock('../services/productService', () => ({
  getProducts: (...a: unknown[]) => getProducts(...a),
  bulkImportProducts: vi.fn(),
  validateProductsImport: vi.fn(),
}));

const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  router: { replace: vi.fn(), push: vi.fn() },
}));
vi.mock('next/navigation', () => ({
  // A STABLE router object, matching ProductsList.discontinued.test.tsx: a new
  // object literal on every call makes the reload-clean effect's dependency
  // array change identity every render, which loops the effect (and, via the
  // real component's other state updates, the whole render) without end.
  useRouter: () => nav.router,
  usePathname: () => '/master-data-management/products',
  useSearchParams: () => nav.params,
}));

vi.mock('../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({ data: [] }),
}));

vi.mock('../../shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [] }),
}));

vi.mock('@/components/upload-activity', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }),
}));

import ProductsList from './ProductsList';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProductsList />
    </QueryClientProvider>,
  );
}

let getEntriesSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  nav.params = new URLSearchParams();
  nav.router.replace.mockReset();
  nav.router.push.mockReset();
  getProducts.mockReset();
  getProducts.mockResolvedValue({
    data: [],
    pagination: { total: 0, page: 1, limit: 10 },
  });
  getEntriesSpy = vi
    .spyOn(performance, 'getEntriesByType')
    .mockReturnValue([] as unknown as PerformanceEntryList);
});

afterEach(() => {
  getEntriesSpy.mockRestore();
  cleanup();
});

describe('ProductsList - discontinued-notice deep link survives reload-clean', () => {
  it('keeps discontinued_batch_id AND brand_id, dropping every other param', async () => {
    getEntriesSpy.mockReturnValue([{ type: 'reload' }] as unknown as PerformanceEntryList);
    nav.params = new URLSearchParams(
      'discontinued_batch_id=batch-1&brand_id=b1,b2&query=stale&page=3',
    );

    renderList();

    await waitFor(() => expect(nav.router.replace).toHaveBeenCalled());
    const [calledWith] = nav.router.replace.mock.calls[0];
    const url = new URL(calledWith, 'http://localhost');
    expect(url.pathname).toBe('/master-data-management/products');
    expect(url.searchParams.get('discontinued_batch_id')).toBe('batch-1');
    expect(url.searchParams.get('brand_id')).toBe('b1,b2');
    expect(url.searchParams.get('query')).toBeNull();
    expect(url.searchParams.get('page')).toBeNull();
  });

  it('keeps only discontinued_batch_id when the deep link has no brand filter', async () => {
    getEntriesSpy.mockReturnValue([{ type: 'reload' }] as unknown as PerformanceEntryList);
    nav.params = new URLSearchParams('discontinued_batch_id=batch-1&query=stale');

    renderList();

    await waitFor(() => expect(nav.router.replace).toHaveBeenCalled());
    const [calledWith] = nav.router.replace.mock.calls[0];
    const url = new URL(calledWith, 'http://localhost');
    expect(url.searchParams.get('discontinued_batch_id')).toBe('batch-1');
    expect(url.searchParams.get('brand_id')).toBeNull();
  });

  it('drops every param, including a lone brand_id, when there is no batch id', async () => {
    getEntriesSpy.mockReturnValue([{ type: 'reload' }] as unknown as PerformanceEntryList);
    nav.params = new URLSearchParams('brand_id=b1,b2&query=stale');

    renderList();

    await waitFor(() => expect(nav.router.replace).toHaveBeenCalled());
    expect(nav.router.replace).toHaveBeenCalledWith('/master-data-management/products');
  });

  it('a normal (non-reload) navigation with a comma brand_id still filters the grid', async () => {
    // No 'reload' navigation entry -> isReloadRef stays false -> the normal
    // param-restore branch runs instead of the reload-clean one.
    nav.params = new URLSearchParams('discontinued_batch_id=batch-1&brand_id=b1,b2');

    renderList();

    await waitFor(() => expect(getProducts).toHaveBeenCalled());
    const call = getProducts.mock.calls.at(-1)?.[0];
    expect(call.discontinued_batch_id).toBe('batch-1');
    expect(call.brand_id).toBe('b1,b2');
    // The reload-clean branch must not have fired at all on a non-reload nav.
    expect(nav.router.replace).not.toHaveBeenCalled();
  });
});
