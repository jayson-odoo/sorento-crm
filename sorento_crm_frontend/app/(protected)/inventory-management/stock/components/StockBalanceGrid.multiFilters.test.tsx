/**
 * FILTER-MULTISELECT PR4: the Stock balance grid's Warehouse and Status filters take several values
 * (OR within a filter, AND across), comma-joined (or listed) to the data hook. The backend already
 * takes a `warehouse_ids` list; Status buckets are critical / low / normal / overstock.
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
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => '/inventory-management/stock',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
vi.mock('@/components/upload-activity', () => ({ useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }) }));
vi.mock('@/app/(protected)/system-management/import-jobs/autocount-pull/hooks/useAutocountPull', () => ({
  useAutocountPullAction: () => ({ visible: false, label: '', onSelect: () => {} }),
}));
vi.mock('@/app/(protected)/resource-management/attachments/services/attachmentService', () => ({
  replaceLatestStockList: vi.fn(),
  getCurrentStockListAttachment: vi.fn().mockResolvedValue(null),
}));
vi.mock('@/app/(protected)/inventory-management/warehouses/services/warehouseService', () => ({
  getWarehouses: vi.fn().mockResolvedValue({
    data: [
      { id: 'wh-1', warehouse_code: 'ZZT1', warehouse_name: 'ZZT Main' },
      { id: 'wh-2', warehouse_code: 'ZZT2', warehouse_name: 'ZZT Second' },
      { id: 'wh-3', warehouse_code: 'ZZT3', warehouse_name: 'ZZT Third' },
    ],
  }),
}));
vi.mock('../services/stockService', () => ({
  exportStockBalance: vi.fn(), bulkImportStock: vi.fn(), validateStockImport: vi.fn(),
}));
const hookCalls = vi.hoisted(() => [] as Array<Record<string, unknown>>);
vi.mock('../hooks/useStock', () => ({
  useStockBalance: (params: Record<string, unknown>) => {
    hookCalls.push(params);
    return {
      data: {
        data: [{
          id: 's-1', product_id: 'p-1', warehouse_id: 'wh-1', quantity_on_hand: 5, quantity_reserved: 1,
          quantity_available: 4, product: { id: 'p-1', product_code: 'ZZT-STOCK', product_name: 'ZZT Tile', reorder_level: 10 },
          warehouse: { id: 'wh-1', warehouse_name: 'ZZT Main' },
        }],
        pagination: { page: 1, limit: 50, total: 1 },
      },
      isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
    };
  },
  useBulkDeleteStock: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import StockBalanceGrid from './StockBalanceGrid';

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => hookCalls[hookCalls.length - 1];
/** The warehouse filter may ride `warehouse_ids` (the backend's list) or keep `warehouse_id`. */
const warehouses = () => setOf(lastParams().warehouse_ids ?? lastParams().warehouse_id);
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
      <StockBalanceGrid />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT-STOCK');
  await user.click(filtersButton());
}

beforeEach(() => {
  hookCalls.length = 0;
  Element.prototype.scrollIntoView = vi.fn();
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});
afterEach(() => cleanup());

describe('Stock balance - multi Warehouse and Status filters', () => {
  it('Warehouse and Status are multi controls', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await box('wh-1')).hasAttribute('multiple')).toBe(true);
    expect((await box('critical')).hasAttribute('multiple')).toBe(true);
  });

  it('two warehouses reach the request as a list of two and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('wh-1'), ['wh-1', 'wh-2']);
    await waitFor(() => expect(warehouses()).toEqual(['wh-1', 'wh-2']));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('two status buckets reach the request as a set of two', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('critical'), ['critical', 'low']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['critical', 'low']));
  });

  it('warehouses AND status', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('wh-1'), ['wh-2', 'wh-3']);
    await user.selectOptions(await box('critical'), ['low', 'overstock']);
    await waitFor(() => {
      expect(warehouses()).toEqual(['wh-2', 'wh-3']);
      expect(setOf(lastParams().status)).toEqual(['low', 'overstock']);
    });
  });

  it('the All warehouses / All statuses sentinels are never sent', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await box('critical');
    expect(warehouses()).toEqual([]);
    expect(setOf(lastParams().status)).toEqual([]);
  });

  it('Clear filters drops both multi filters', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('wh-1'), ['wh-1', 'wh-2']);
    await user.selectOptions(await box('critical'), ['critical', 'low']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['critical', 'low']));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => {
      expect(warehouses()).toEqual([]);
      expect(setOf(lastParams().status)).toEqual([]);
    });
  });
});
