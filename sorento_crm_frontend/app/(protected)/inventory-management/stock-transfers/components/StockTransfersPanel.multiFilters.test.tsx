/**
 * FILTER-MULTISELECT PR4: the Transfers page's State, Source, From, To and Item filters take several
 * values (OR within a filter, AND across), comma-joined to the service and in the page URL. An older
 * link holding one value reads back as a one-value filter. There is no chip row on this page.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/inventory-management/stock-transfers',
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/app/(protected)/inventory-management/warehouses/services/warehouseService', () => ({
  getWarehouses: vi.fn().mockResolvedValue({
    data: [
      { id: 'w-a', warehouse_code: 'ZZTA', warehouse_name: 'Alpha' },
      { id: 'w-b', warehouse_code: 'ZZTB', warehouse_name: 'Beta' },
      { id: 'w-c', warehouse_code: 'ZZTC', warehouse_name: 'Gamma' },
    ],
  }),
}));
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForLineSelect: vi.fn().mockResolvedValue([
    { id: 'p-1', product_code: 'ZZT-P1', product_name: 'One' },
    { id: 'p-2', product_code: 'ZZT-P2', product_name: 'Two' },
  ]),
}));
const listStockTransfers = vi.hoisted(() => vi.fn());
vi.mock('../services/stockTransferService', () => ({
  listStockTransfers: (...args: unknown[]) => listStockTransfers(...args),
  getStockTransfer: vi.fn(),
  approveStockTransfer: vi.fn(),
  markStockTransferMoved: vi.fn(),
  cancelStockTransfer: vi.fn(),
  bulkApproveStockTransfers: vi.fn(),
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

import { StockTransfersPanel } from './StockTransfersPanel';

const ROW = {
  id: 'tr-1', transfer_no: 'TR-000001', state: 'proposed', kind: 'pool', qty: '71', product_id: 'p-1',
  item_code: 'ZZT-P1', product_name: 'One', from_warehouse_id: 'w-a', from_location: 'ZZTA', to_warehouse_id: 'w-b',
  to_location: 'ZZTB', sales_order_id: null, so_number: null, so_line_no: null, project_sales_order_id: 'pso-1',
  customer_name: null, sales_agent_id: null, agent_code: null, agent_name: null, supply_decision_id: null,
  revision_no: null, proposed_at: '2026-08-25T08:42:00', approved_by: null, approved_by_name: null, approved_at: null,
  moved_by: null, moved_by_name: null, moved_at: null, cancelled_by: null, cancelled_by_name: null,
  cancelled_at: null, cancelled_reason: null, autocount_ref: null, created_at: '2026-08-25T08:42:00',
  updated_at: '2026-08-25T08:42:00',
};

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => {
  const calls = listStockTransfers.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};
const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function box(value: string, nth = 0) {
  await waitFor(() => {
    if (boxesWith(value).length <= nth) throw new Error(`no multi control offering option "${value}" (#${nth})`);
  });
  return boxesWith(value)[nth];
}
const selected = (el: HTMLSelectElement) => Array.from(el.selectedOptions, (o) => o.value).sort();

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <StockTransfersPanel listingKey="inventory.stock_transfers.view" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  url.search = '';
  listStockTransfers.mockResolvedValue({ data: [ROW], pagination: { total: 1, page: 1, limit: 25 }, empty: false });
  if (!window.matchMedia) {
    (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
      matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
    });
  }
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => cleanup());

describe('Stock transfers - multi filters', () => {
  it('offers State, Source, From, To and Item as multi controls', async () => {
    renderPanel();
    await screen.findByText('TR-000001');
    expect((await box('proposed')).hasAttribute('multiple')).toBe(true);
    await box('own_group');
    await box('w-a', 0);
    await box('w-a', 1);
    await box('p-1');
  });

  it('two states reach the service as a set of two', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('TR-000001');
    await user.selectOptions(await box('proposed'), ['proposed', 'approved']);
    await waitFor(() => expect(setOf(lastParams().state)).toEqual(['approved', 'proposed']));
  });

  it('two sources reach the service as a set of two', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('TR-000001');
    await user.selectOptions(await box('own_group'), ['own_group', 'borrow']);
    await waitFor(() => expect(setOf(lastParams().kind)).toEqual(['borrow', 'own_group']));
  });

  it('two From, two To and two Items each reach the service as a set of two', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('TR-000001');
    await user.selectOptions(await box('w-a', 0), ['w-a', 'w-b']);
    await user.selectOptions(await box('w-a', 1), ['w-b', 'w-c']);
    await user.selectOptions(await box('p-1'), ['p-1', 'p-2']);
    await waitFor(() => {
      expect(setOf(lastParams().from_warehouse_id)).toEqual(['w-a', 'w-b']);
      expect(setOf(lastParams().to_warehouse_id)).toEqual(['w-b', 'w-c']);
      expect(setOf(lastParams().product_id)).toEqual(['p-1', 'p-2']);
    });
  });

  it('filters AND across: several states with a source', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('TR-000001');
    await user.selectOptions(await box('proposed'), ['proposed', 'approved']);
    await user.selectOptions(await box('own_group'), ['pool']);
    await waitFor(() => {
      expect(setOf(lastParams().state)).toEqual(['approved', 'proposed']);
      expect(setOf(lastParams().kind)).toEqual(['pool']);
    });
  });

  it('a link with several values per filter restores every control and the request', async () => {
    url.search = 'state=proposed%2Capproved&kind=pool%2Cborrow&from_warehouse_id=w-a%2Cw-b&to_warehouse_id=w-c&product_id=p-1%2Cp-2';
    renderPanel();
    await screen.findByText('TR-000001');
    await waitFor(() => {
      expect(setOf(lastParams().state)).toEqual(['approved', 'proposed']);
      expect(setOf(lastParams().kind)).toEqual(['borrow', 'pool']);
      expect(setOf(lastParams().from_warehouse_id)).toEqual(['w-a', 'w-b']);
      expect(setOf(lastParams().to_warehouse_id)).toEqual(['w-c']);
      expect(setOf(lastParams().product_id)).toEqual(['p-1', 'p-2']);
    });
    expect(selected(await box('proposed'))).toEqual(['approved', 'proposed']);
    await waitFor(async () => expect(selected(await box('p-1'))).toEqual(['p-1', 'p-2']));
  });

  it('an older link with one value per filter reads back as one-value filters', async () => {
    url.search = 'state=moved&kind=own_group&from_warehouse_id=w-a';
    renderPanel();
    await screen.findByText('TR-000001');
    await waitFor(() => {
      expect(setOf(lastParams().state)).toEqual(['moved']);
      expect(setOf(lastParams().kind)).toEqual(['own_group']);
      expect(setOf(lastParams().from_warehouse_id)).toEqual(['w-a']);
    });
    expect(selected(await box('proposed'))).toEqual(['moved']);
  });

  it('unticking every state drops the filter from the request', async () => {
    url.search = 'state=proposed%2Capproved';
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('TR-000001');
    await user.deselectOptions(await box('proposed'), ['proposed', 'approved']);
    await waitFor(() => expect(setOf(lastParams().state)).toEqual([]));
  });
});
