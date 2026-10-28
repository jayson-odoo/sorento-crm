/**
 * FILTER-MULTISELECT PR4b: the SPO allocations list's Product and Warehouse filters take several values
 * (OR within a filter, AND across), comma-joined to the data hook and in the page URL. An older link
 * holding one value reads back as a one-value filter. Harness mirrors SPOAllocationsList.test.tsx.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/spo-allocations',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
type MenuProps = { children?: React.ReactNode; onClick?: () => void; disabled?: boolean };
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: MenuProps) => <>{children}</>,
  DropdownMenuContent: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick, disabled }: MenuProps) => (
    <button type="button" onClick={onClick} disabled={disabled}>{children}</button>
  ),
  DropdownMenuCheckboxItem: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuGroup: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuPortal: ({ children }: MenuProps) => <>{children}</>,
  DropdownMenuSub: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuSubContent: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuSubTrigger: ({ children }: MenuProps) => <div>{children}</div>,
}));

vi.mock('@/components/upload-activity', () => ({ useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }) }));
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProducts: vi.fn(async () => ({
    data: [
      { id: 'p-1', product_code: 'ZZT-P1', product_name: 'One' },
      { id: 'p-2', product_code: 'ZZT-P2', product_name: 'Two' },
      { id: 'p-3', product_code: 'ZZT-P3', product_name: 'Three' },
    ],
    pagination: { total: 3 },
  })),
}));
vi.mock('@/app/(protected)/inventory-management/warehouses/services/warehouseService', () => ({
  getWarehouses: vi.fn(async () => ({
    data: [
      { id: 'w-1', warehouse_code: 'ZZTW1', warehouse_name: 'One' },
      { id: 'w-2', warehouse_code: 'ZZTW2', warehouse_name: 'Two' },
    ],
    pagination: { total: 2 },
  })),
}));
vi.mock('../services/spoAllocationService', () => ({ importSPOAllocations: vi.fn(), validateSPOAllocations: vi.fn() }));
const useSPODocuments = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useSPODocuments', () => ({ useSPODocuments: (...a: unknown[]) => useSPODocuments(...a) }));
vi.mock('@/hooks/useDeferredBulkAction', () => ({
  useDeferredBulkAction: () => ({ run: vi.fn(), isStarting: false }),
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

import SPOAllocationsList from './SPOAllocationsList';

const ROW = {
  id: 'ZZT-SPO-1', spo_number: 'ZZT-SPO-1', doc_date: '2026-08-01', supplier_name: 'Acme Sanitary', supplier_extra_count: 0,
  status: 'outstanding', earliest_eta: '2026-08-15', total_allocated: 500, total_received: 100, balance: 400, line_count: 2,
  worst_overdue_days: 0, containers: [],
};
const lastParams = () => useSPODocuments.mock.calls[useSPODocuments.mock.calls.length - 1][0] as Record<string, unknown>;
const products = () => setOf(lastParams().productId ?? lastParams().productIds);
const warehouses = () => setOf(lastParams().warehouseId ?? lastParams().warehouseIds);
const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
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
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <SPOAllocationsList />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT-SPO-1');
  const button = screen.queryAllByRole('button', { name: /^filters/i })[0];
  if (button && !screen.queryAllByRole('listbox').length) await user.click(button);
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  url.search = '';
  useSPODocuments.mockReturnValue({
    data: { data: [ROW], pagination: { page: 1, total: 1 } },
    isLoading: false, isFetching: false, isPlaceholderData: false, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

describe('SPO allocations - multi Product and Warehouse filters', () => {
  it('Product and Warehouse are multi controls', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await box('p-1')).hasAttribute('multiple')).toBe(true);
    expect((await box('w-1')).hasAttribute('multiple')).toBe(true);
  });

  it('two products reach the hook as a set of two and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('p-1'), ['p-1', 'p-2']);
    await waitFor(() => expect(products()).toEqual(['p-1', 'p-2']));
    expect(within(filtersButton()).getByText('1')).toBeInTheDocument();
  });

  it('two warehouses ANDed with two products', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('p-1'), ['p-2', 'p-3']);
    await user.selectOptions(await box('w-1'), ['w-1', 'w-2']);
    await waitFor(() => {
      expect(products()).toEqual(['p-2', 'p-3']);
      expect(warehouses()).toEqual(['w-1', 'w-2']);
    });
  });

  it('Clear filters drops both multi filters', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('p-1'), ['p-1', 'p-2']);
    await user.selectOptions(await box('w-1'), ['w-1', 'w-2']);
    await waitFor(() => expect(warehouses()).toEqual(['w-1', 'w-2']));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => {
      expect(products()).toEqual([]);
      expect(warehouses()).toEqual([]);
    });
  });

  it('a link with several products and warehouses restores both controls and the request', async () => {
    url.search = 'product_id=p-1%2Cp-3&warehouse_id=w-1%2Cw-2';
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => {
      expect(products()).toEqual(['p-1', 'p-3']);
      expect(warehouses()).toEqual(['w-1', 'w-2']);
    });
    expect(selected(await box('p-1'))).toEqual(['p-1', 'p-3']);
    expect(selected(await box('w-1'))).toEqual(['w-1', 'w-2']);
  });

  it('an older link with one product and one warehouse reads back as one-value filters', async () => {
    url.search = 'product_id=p-2&warehouse_id=w-2';
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => {
      expect(products()).toEqual(['p-2']);
      expect(warehouses()).toEqual(['w-2']);
    });
    expect(selected(await box('p-1'))).toEqual(['p-2']);
  });
});
