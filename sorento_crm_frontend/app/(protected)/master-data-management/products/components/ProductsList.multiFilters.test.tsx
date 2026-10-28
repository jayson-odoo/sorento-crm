/**
 * FILTER-MULTISELECT PR4: the Products list's Category and Brand filters take several values (OR within
 * a filter, AND across), comma-joined to the data service and in the page URL. An older link holding
 * one value reads back as a one-value filter. Status and Variant stay single controls.
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
const selected = (el: HTMLSelectElement) => Array.from(el.selectedOptions, (o) => o.value).sort();
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

describe('Products - multi Category and Brand filters', () => {
  it('Category and Brand are multi controls', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await box('cat-1')).hasAttribute('multiple')).toBe(true);
    expect((await box('br-1')).hasAttribute('multiple')).toBe(true);
  });

  it('two categories reach the service as a set of two and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('cat-1'), ['cat-1', 'cat-2']);
    await waitFor(() => expect(setOf(lastParams().category_id)).toEqual(['cat-1', 'cat-2']));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('several brands with several categories AND across', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('cat-1'), ['cat-2', 'cat-3']);
    await user.selectOptions(await box('br-1'), ['br-1', 'br-2']);
    await waitFor(() => {
      expect(setOf(lastParams().category_id)).toEqual(['cat-2', 'cat-3']);
      expect(setOf(lastParams().brand_id)).toEqual(['br-1', 'br-2']);
    });
  });

  it('Clear filters drops both multi filters', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('cat-1'), ['cat-1', 'cat-2']);
    await user.selectOptions(await box('br-1'), ['br-1', 'br-2']);
    await waitFor(() => expect(setOf(lastParams().brand_id)).toEqual(['br-1', 'br-2']));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => {
      expect(setOf(lastParams().category_id)).toEqual([]);
      expect(setOf(lastParams().brand_id)).toEqual([]);
    });
  });

  it('a link with several categories and brands restores both controls and the request', async () => {
    nav.params = new URLSearchParams('category_id=cat-1%2Ccat-3&brand_id=br-1%2Cbr-2');
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => {
      expect(setOf(lastParams().category_id)).toEqual(['cat-1', 'cat-3']);
      expect(setOf(lastParams().brand_id)).toEqual(['br-1', 'br-2']);
    });
    await waitFor(async () => expect(selected(await box('cat-1'))).toEqual(['cat-1', 'cat-3']));
    await waitFor(async () => expect(selected(await box('br-1'))).toEqual(['br-1', 'br-2']));
  });

  it('an older link with one category and one brand reads back as one-value filters', async () => {
    nav.params = new URLSearchParams('category_id=cat-2&brand_id=br-1');
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => {
      expect(setOf(lastParams().category_id)).toEqual(['cat-2']);
      expect(setOf(lastParams().brand_id)).toEqual(['br-1']);
    });
    await waitFor(async () => expect(selected(await box('cat-1'))).toEqual(['cat-2']));
  });
});
