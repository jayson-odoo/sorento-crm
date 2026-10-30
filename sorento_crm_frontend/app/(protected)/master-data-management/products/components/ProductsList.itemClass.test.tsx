/**
 * ITEM-CLASS: the Products list gets an Item Class column right after Brand (sortable server side as
 * `item_class`) and a multi-select Item Class filter whose ids reach the service comma-joined.
 */
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const getProducts = vi.hoisted(() => vi.fn());
vi.mock('../services/productService', () => ({
  getProducts: (...a: unknown[]) => getProducts(...a),
  bulkImportProducts: vi.fn(),
  validateProductsImport: vi.fn(),
}));
const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  router: { replace: () => {}, push: () => {} },
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => false }));
vi.mock('next/navigation', () => ({
  useRouter: () => nav.router,
  usePathname: () => '/master-data-management/products',
  useSearchParams: () => nav.params,
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
vi.mock('../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({
    data: [
      { id: 'cat-1', category_name: 'ZZT Sinks' },
      { id: 'cat-2', category_name: 'ZZT Taps' },
      { id: 'cat-3', category_name: 'ZZT Basins' },
    ],
  }),
}));
vi.mock('../../shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({
    data: [
      { id: 'br-1', brand_name: 'ZZT Brand One' },
      { id: 'br-2', brand_name: 'ZZT Brand Two' },
    ],
  }),
}));
vi.mock('../../shared/hooks/use-item-class-select-query', () => ({
  useItemClassSelectQuery: () => ({
    data: [
      { id: 'ic-1', item_class_code: 'A', item_class_name: 'ZZT Class One', is_active: true },
      { id: 'ic-2', item_class_code: 'B', item_class_name: 'ZZT Class Two', is_active: true },
    ],
  }),
}));
vi.mock('@/components/upload-activity', () => ({ useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }) }));
vi.mock('@/app/(protected)/system-management/import-jobs/autocount-pull/hooks/useAutocountPull', () => ({
  useAutocountPullAction: () => ({ visible: false, label: '', onSelect: () => {} }),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setLoaded);
    }, [fetchOptions]);
    return (
      <select multiple aria-label={placeholder ?? 'multi'} value={value}
        onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {(fetchOptions ? loaded : (options ?? [])).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  };
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import ProductsList from './ProductsList';

const ROW = {
  id: 'row-1', product_code: 'ZZT-PROD-1', product_name: 'ZZT Product', list_price: 100, is_active: true,
  item_class: { id: 'ic-1', item_class_code: 'A', item_class_name: 'ZZT Class One' },
  is_variant: false, variant_of: null, variant_child_count: 0, created_at: new Date('2026-01-01T00:00:00Z'),
};
const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => {
  const calls = getProducts.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};
const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function box(value: string) {
  await waitFor(() => {
    if (!boxesWith(value).length) throw new Error(`no multi control offering option "${value}"`);
  });
  return boxesWith(value)[0];
}
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <ProductsList />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT Product');
  await user.click(filtersButton());
}

beforeEach(() => {
  getProducts.mockReset();
  getProducts.mockResolvedValue({ data: [ROW], pagination: { total: 1, page: 1, limit: 50 } });
  nav.params = new URLSearchParams();
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => cleanup());

describe('Products - Item Class', () => {
  it('sends the chosen class ids comma-joined as item_class_id', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const control = await box('ic-1');
    await user.selectOptions(control, ['ic-1', 'ic-2']);
    await waitFor(() => expect(setOf(lastParams().item_class_id)).toEqual(['ic-1', 'ic-2']));
  });

  it('shows the class name in a column that follows Brand and sorts as item_class', async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(
      <QueryClientProvider client={client}>
        <ProductsList />
      </QueryClientProvider>,
    );
    expect((await screen.findAllByText('ZZT Class One')).length).toBeGreaterThan(0);
    const headers = Array.from(document.querySelectorAll('th'));
    const titles = headers.map((h) => h.textContent ?? '');
    const brand = titles.findIndex((t) => t.includes('Brand'));
    const klass = titles.findIndex((t) => t.includes('Item Class'));
    expect(brand).toBeGreaterThan(-1);
    expect(klass).toBe(brand + 1);
    await user.click(within(headers[klass]).getByText('Item Class'));
    await waitFor(() => {
      const sorting = lastParams().sorting as Array<{ id: string }>;
      expect(sorting[0].id).toBe('item_class');
    });
  });
});
