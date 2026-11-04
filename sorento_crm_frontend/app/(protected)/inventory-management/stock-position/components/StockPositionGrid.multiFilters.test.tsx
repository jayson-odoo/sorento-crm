/**
 * STOCKPOS-FILTER-MULTI (FILTER-MULTISELECT owner rule 27 Oct): Supplier, Brand and Warehouse each
 * take several values (OR within a filter, AND across), reach the data hook and the export as the
 * same selection, and ride the page URL so Back from Stock status restores them.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const nav = vi.hoisted(() => ({ search: '', replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/inventory-management/stock-position',
  useRouter: () => ({ push: vi.fn(), replace: nav.replace }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
const savedConfig = vi.hoisted(() => ({
  useUserListColumnConfigQuery: vi.fn(() => ({ data: { config: null }, isSuccess: true, isError: false }) as unknown),
}));
vi.mock('@/lib/listing-column-preferences/useUserListColumnConfigQuery', () => savedConfig);
const exporter = vi.hoisted(() => ({ exportStockPosition: vi.fn(async () => {}) }));
vi.mock('../services/stockPositionService', () => exporter);
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({
    data: [
      { id: 'b-1', brand_name: 'Brand One' },
      { id: 'b-2', brand_name: 'Brand Two' },
      { id: 'b-3', brand_name: 'Brand Three' },
    ],
  }),
}));
vi.mock('@/services/supplierSelectService', () => ({
  getSuppliersSelect: async () => [
    { value: 's-1', label: 'Supplier One' },
    { value: 's-2', label: 'Supplier Two' },
  ],
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('', 0).then(setLoaded);
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

const hook = vi.hoisted(() => ({ useStockPosition: vi.fn() }));
vi.mock('../hooks/useStockPosition', () => hook);

import StockPositionGrid from './StockPositionGrid';

function withData() {
  hook.useStockPosition.mockReturnValue({
    data: {
      data: [],
      warehouses: [{ id: 'w-1', code: 'BRW' }, { id: 'w-2', code: 'DC1' }],
      pagination: { page: 1, limit: 50, total: 0, total_pages: 0 },
    },
    isLoading: false, isFetching: false, isPlaceholderData: false, error: null, refetch: vi.fn(),
  });
}
const lastFilters = () => hook.useStockPosition.mock.calls.at(-1)![1] as Record<string, string[] | undefined>;
const lastParams = () => hook.useStockPosition.mock.calls.at(-1)![0] as { pageIndex: number };

function renderGrid() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <StockPositionGrid />
    </QueryClientProvider>,
  );
}

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /^Filters/ }));
}

beforeEach(() => {
  nav.search = '';
  nav.replace.mockReset();
  hook.useStockPosition.mockReset();
  exporter.exportStockPosition.mockClear();
  withData();
});
afterEach(() => cleanup());

describe('Stock position: Supplier, Brand, Warehouse are multi-select', () => {
  it('a second Brand pick adds to the first, it does not replace it', async () => {
    const user = userEvent.setup();
    renderGrid();
    await openFilters(user);
    const brand = await screen.findByRole('listbox', { name: 'All brands' });
    expect(brand.hasAttribute('multiple')).toBe(true);
    await user.selectOptions(brand, ['b-1']);
    await user.selectOptions(brand, ['b-2']);
    await waitFor(() => expect(lastFilters().brandIds).toEqual(['b-1', 'b-2']));
  });

  it('Supplier and Warehouse take several values too; the three AND, the page resets to 1', async () => {
    const user = userEvent.setup();
    renderGrid();
    await openFilters(user);
    const supplier = await screen.findByRole('listbox', { name: 'All suppliers' });
    await waitFor(() => expect(supplier.querySelector('option[value="s-2"]')).toBeTruthy());
    await user.selectOptions(supplier, ['s-1', 's-2']);
    await user.selectOptions(screen.getByRole('listbox', { name: 'All warehouses' }), ['w-1', 'w-2']);
    await waitFor(() =>
      expect(lastFilters()).toMatchObject({ supplierIds: ['s-1', 's-2'], warehouseIds: ['w-1', 'w-2'] }),
    );
    expect(lastParams().pageIndex).toBe(0);
  });

  it('the export reads the same selection', async () => {
    const user = userEvent.setup();
    renderGrid();
    await openFilters(user);
    await user.selectOptions(await screen.findByRole('listbox', { name: 'All brands' }), ['b-1', 'b-3']);
    await user.keyboard('{Escape}'); // close the Filters popover
    await user.click(screen.getByText('Export to Excel'));
    await waitFor(() => expect(exporter.exportStockPosition).toHaveBeenCalled());
    const calls = exporter.exportStockPosition.mock.calls as unknown as [unknown, { brandIds?: string[] }][];
    expect(calls[0][1].brandIds).toEqual(['b-1', 'b-3']);
  });

  it('writes the selection to the page URL comma-joined, so Back returns to it', async () => {
    const user = userEvent.setup();
    renderGrid();
    await openFilters(user);
    await user.selectOptions(await screen.findByRole('listbox', { name: 'All brands' }), ['b-1', 'b-2']);
    await waitFor(() => {
      const url = String(nav.replace.mock.calls.at(-1)?.[0] ?? '');
      expect(new URL(url, 'http://x').searchParams.get('brand_id')).toBe('b-1,b-2');
    });
  });

  it("the list's own URL write does not re-apply onto the search box while the user keeps typing", async () => {
    // The router commits what the list writes, as Next does: the next render reads it back.
    nav.replace.mockImplementation((url: string) => {
      nav.search = new URL(url, 'http://x').searchParams.toString();
    });
    const user = userEvent.setup();
    const { rerender } = renderGrid();
    const box = screen.getByPlaceholderText('Search item code or description...') as HTMLInputElement;
    await user.type(box, 'abc');
    await waitFor(() => expect(nav.search).toContain('query=abc'), { timeout: 2000 });
    await user.type(box, 'd');
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <StockPositionGrid />
      </QueryClientProvider>,
    );
    expect(box.value).toBe('abcd');
  });

  it('restores the selection, sort and page from the URL', () => {
    nav.search = 'page=2&limit=50&sort=total_stock&dir=desc&brand_id=b-1,b-2&supplier_id=s-1&warehouse_id=w-2';
    renderGrid();
    // The restore applies during the first render, so the committed render reads it (no request for defaults).
    const first = hook.useStockPosition.mock.calls.at(-1)!;
    expect(first[1]).toMatchObject({ brandIds: ['b-1', 'b-2'], supplierIds: ['s-1'], warehouseIds: ['w-2'] });
    expect(first[0]).toMatchObject({ pageIndex: 1, sorting: [{ id: 'total_stock', desc: true }] });
  });

  it('a saved hidden column does not reset the page restored from the URL', () => {
    savedConfig.useUserListColumnConfigQuery.mockReturnValueOnce({
      data: { config: { columnVisibility: { 'wh:DC1': false } } },
      isSuccess: true,
      isError: false,
    });
    nav.search = 'page=3&limit=50&sort=total_stock&dir=desc';
    renderGrid();
    const last = hook.useStockPosition.mock.calls.at(-1)!;
    expect(last[1]).toMatchObject({ hiddenColumns: ['wh:DC1'] });
    expect(last[0]).toMatchObject({ pageIndex: 2 });
  });
});
