/**
 * Orders list - remembered view (PLAN-listing-view-memory, rollout to Sales Orders).
 *
 * Mirrors `StockInquiriesList.viewMemory.test.tsx`. The whole listing renders with the
 * REAL `useListingViewPreferences`; only the preferences transport and the data hook are
 * stubbed. Pins:
 * - the data query is held until the stored view resolves and then fires ONCE, already
 *     sorted and filtered (AC-B3);
 * - the shipped default is Delivery Order Date descending (`order_date`, newest first);
 * - a restored filter (status / lines / advanced) is stated as one chip above the grid and
 *     its Clear drops every filter axis, refetches unfiltered and writes an explicit null
 *     (AC-C1 / AC-C2);
 * - a blob from an older `filtersVersion` is discarded while the sort is kept (AC-B4);
 * - page number and search text are never in the write (AC-D1 / AC-D2).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  cleanup,
  fireEvent,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver =
  ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/order-management/orders',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: async () => {},
    isLoading: false,
  }),
}));

const service = vi.hoisted(() => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(),
}));
vi.mock(
  '@/lib/listing-column-preferences/listColumnPreferencesService',
  () => ({
    getUserListColumnConfig: (...a: unknown[]) =>
      service.getUserListColumnConfig(...a),
    upsertUserListColumnConfig: (...a: unknown[]) =>
      service.upsertUserListColumnConfig(...a),
    resetUserListColumnConfig: vi.fn(async () => undefined),
  }),
);

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

const hooks = vi.hoisted(() => ({ useOrders: vi.fn() }));
vi.mock('../hooks/useOrders', () => ({
  useOrders: (...a: unknown[]) => hooks.useOrders(...a),
}));

const statusHook = vi.hoisted(() => ({ useOrderStatusSelectQuery: vi.fn() }));
vi.mock('../../shared/hooks/use-order-status-select-query', () => ({
  useOrderStatusSelectQuery: (...a: unknown[]) =>
    statusHook.useOrderStatusSelectQuery(...a),
}));

vi.mock('../actions', () => ({
  OrderRowActions: () => <span>actions</span>,
}));

vi.mock('@/components/upload-activity', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }),
}));

vi.mock('@/hooks/useDeferredBulkAction', () => ({
  useDeferredBulkAction: () => ({ run: vi.fn(), isStarting: false }),
}));

vi.mock('@/lib/pending-entity-store', () => ({
  pendingEntityKey: (type: string, id: string) => `${type}:${id}`,
  usePendingEntityKeys: () => new Set<string>(),
}));

vi.mock('@/components/template/TemplateUploadDialog', () => ({
  TemplateUploadDialog: () => null,
}));
vi.mock('./OrderTrackingUploadDialog', () => ({
  OrderTrackingUploadDialog: () => null,
}));
vi.mock('./OrderLinesImportDialog', () => ({
  OrderLinesImportDialog: () => null,
}));

vi.mock('../services/orderService', () => ({
  bulkImportOrders: vi.fn(),
  importOrderTracking: vi.fn(),
  validateOrderTracking: vi.fn(),
  validateDeliveryOrderDetail: vi.fn(),
}));

// Stubbed as a deterministic native control (same technique used elsewhere in the
// suite), so picking an option is a plain `fireEvent.change` rather than a Radix
// popover interaction in jsdom. `id` carries through so the page's `<Label htmlFor>`
// still resolves an accessible name.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options,
    placeholder,
  }: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    // Deterministic stand-in for the real Radix popover, same technique used
    // elsewhere in the suite (e.g. page.defaultUom.test.tsx); a plain
    // fireEvent.change is reliable in jsdom where driving the real popover is not.
    // eslint-disable-next-line no-restricted-syntax
    <select
      id={id}
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import OrdersList from './OrdersList';
import type { Order } from '../types/order.types';

const LISTING_KEY = '/order-management/orders';

type ListParams = {
  pageIndex: number;
  pageSize: number;
  sorting: { id: string; desc: boolean }[];
  searchQuery: string;
  order_status_id?: string;
  has_order_lines?: 'all' | 'yes' | 'no';
  advancedFilter?: unknown;
  enabled: boolean;
};

function storedConfig(config: Record<string, unknown> | null) {
  service.getUserListColumnConfig.mockResolvedValue({
    listing_key: LISTING_KEY,
    config,
  });
  service.upsertUserListColumnConfig.mockImplementation(
    async (listingKey: string, payload: unknown) => ({
      listing_key: listingKey,
      config: payload,
    }),
  );
}

function order(over: Partial<Order> = {}): Order {
  return {
    id: 'do-1',
    order_number: 'DO-2026-0001',
    debtor_name: 'Acme Sdn Bhd',
    order_date: new Date('2026-07-01T00:00:00'),
    subtotal_amount: 0,
    discount_amount: 0,
    tax_amount: 0,
    total_amount: 0,
    created_at: new Date('2026-07-01T00:00:00'),
    updated_at: new Date('2026-07-01T00:00:00'),
    synced_to_excel: false,
    ...over,
  } as Order;
}

function mockList(rows: Order[]) {
  hooks.useOrders.mockReturnValue({
    data: {
      data: rows,
      empty: rows.length === 0,
      pagination: { page: 1, total: rows.length },
    },
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: vi.fn(),
  });
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OrdersList />
    </QueryClientProvider>,
  );
}

/** Every set of params the data hook was asked to fetch with (`enabled: true`). */
function enabledFetches(): ListParams[] {
  return hooks.useOrders.mock.calls
    .map((c) => c[0] as ListParams)
    .filter((p) => p.enabled);
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  statusHook.useOrderStatusSelectQuery.mockReturnValue({
    data: [
      { id: 'st-1', status_code: 'PENDING', status_name: 'Pending' },
      { id: 'st-2', status_code: 'DELIVERED', status_name: 'Delivered' },
    ],
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('OrdersList remembered view', () => {
  it('falls back to the shipped default (Delivery Order Date, newest first) with nothing stored (AC-B2)', async () => {
    storedConfig(null);
    mockList([order()]);
    renderList();

    // The first render is gated: nothing has been fetched yet.
    expect((hooks.useOrders.mock.calls[0][0] as ListParams).enabled).toBe(false);

    expect(await screen.findByText('DO-2026-0001')).toBeInTheDocument();

    const fetched = enabledFetches();
    expect(fetched.length).toBeGreaterThan(0);
    for (const p of fetched) {
      expect(p.sorting).toEqual([{ id: 'order_date', desc: true }]);
      expect(p.order_status_id).toBeUndefined();
      expect(p.has_order_lines).toBe('all');
      expect(p.advancedFilter).toBeUndefined();
    }
    expect(
      screen.queryByRole('button', { name: /^Clear filter:/ }),
    ).not.toBeInTheDocument();
    // Applying the (empty) stored view is not a change, so nothing is written back.
    await new Promise((r) => setTimeout(r, 200));
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
  });

  it('fetches once already sorted and filtered from a stored view, and states it as a chip (AC-B1 / AC-B3)', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'debtor_name', desc: false }],
      filters: { order_status_id: 'st-1', has_order_lines: 'yes' },
      filtersVersion: 1,
    });
    mockList([order()]);
    renderList();

    expect(await screen.findByText('DO-2026-0001')).toBeInTheDocument();

    const fetched = enabledFetches();
    expect(fetched.length).toBeGreaterThan(0);
    for (const p of fetched) {
      expect(p.sorting).toEqual([{ id: 'debtor_name', desc: false }]);
      expect(p.order_status_id).toBe('st-1');
      expect(p.has_order_lines).toBe('yes');
    }

    const clear = await screen.findByRole('button', {
      name: /^Clear filter:/,
    });
    expect(clear.closest('span')?.textContent).toContain('Pending');
    expect(clear.closest('span')?.textContent).toContain(
      'Has order lines: Yes',
    );
  });

  it('discards a filter blob written by an older page shape but keeps the sort (AC-B4)', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'debtor_name', desc: false }],
      // An older shape of this page stored a bare status string.
      filters: { status: 'st-1' },
      filtersVersion: 0,
    });
    mockList([order()]);
    renderList();

    expect(await screen.findByText('DO-2026-0001')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /^Clear filter:/ }),
    ).not.toBeInTheDocument();

    const last = enabledFetches().at(-1)!;
    expect(last.sorting).toEqual([{ id: 'debtor_name', desc: false }]);
    expect(last.order_status_id).toBeUndefined();
    expect(last.has_order_lines).toBe('all');

    await new Promise((r) => setTimeout(r, 200));
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
  });

  it('writes an upsert on a status change, debounced, with no page/query keys (AC-D1 / AC-D2)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    storedConfig(null);
    mockList([order()]);
    renderList();

    await vi.waitFor(() => {
      expect(screen.getByText('DO-2026-0001')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText('Status'), {
      target: { value: 'st-1' },
    });

    await vi.advanceTimersByTimeAsync(900);

    await vi.waitFor(() => {
      expect(service.upsertUserListColumnConfig).toHaveBeenCalled();
    });
    const [key, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(key).toBe(LISTING_KEY);
    expect(payload).toMatchObject({
      filters: { order_status_id: 'st-1' },
      filtersVersion: 1,
    });
    expect(payload).not.toHaveProperty('page');
    expect(payload).not.toHaveProperty('pageIndex');
    expect(payload).not.toHaveProperty('query');
    expect(payload).not.toHaveProperty('searchQuery');
    vi.useRealTimers();
  });

  it('Clear on the chip resets every filter axis, refetches unfiltered and writes null (AC-C1 / AC-C2)', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'order_date', desc: true }],
      filters: { order_status_id: 'st-1', has_order_lines: 'yes' },
      filtersVersion: 1,
    });
    mockList([order()]);
    renderList();

    const clear = await screen.findByRole('button', {
      name: /^Clear filter:/,
    });
    fireEvent.click(clear);

    await waitFor(() => {
      expect(
        screen.queryByRole('button', { name: /^Clear filter:/ }),
      ).not.toBeInTheDocument();
    });

    const last = enabledFetches().at(-1)!;
    expect(last.order_status_id).toBeUndefined();
    expect(last.has_order_lines).toBe('all');
    expect(last.pageIndex).toBe(0);

    await waitFor(
      () => {
        expect(service.upsertUserListColumnConfig).toHaveBeenCalled();
      },
      { timeout: 3000 },
    );
    const [key, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(key).toBe(LISTING_KEY);
    expect(payload).toMatchObject({ filters: null, filtersVersion: null });
    expect(payload.sorting).toEqual([{ id: 'order_date', desc: true }]);
  });

  it('a stored advanced filter reaches the fetch, states "Advanced filter" on the chip, and Clear nulls it (AC-B1 / AC-C1 / AC-C2)', async () => {
    const advancedFilter = {
      op: 'and',
      children: [{ field_key: 'debtor_name', op: 'contains', value: 'Acme' }],
    };
    storedConfig({
      version: 1,
      sorting: [{ id: 'order_date', desc: true }],
      filters: { advancedFilter },
      filtersVersion: 1,
    });
    mockList([order()]);
    renderList();

    expect(await screen.findByText('DO-2026-0001')).toBeInTheDocument();

    const fetched = enabledFetches();
    expect(fetched.length).toBeGreaterThan(0);
    for (const p of fetched) {
      expect(p.advancedFilter).toEqual(advancedFilter);
    }

    const clear = await screen.findByRole('button', {
      name: /^Clear filter:/,
    });
    expect(clear.closest('span')?.textContent).toContain('Advanced filter');

    fireEvent.click(clear);

    await waitFor(() => {
      expect(
        screen.queryByRole('button', { name: /^Clear filter:/ }),
      ).not.toBeInTheDocument();
    });
    const last = enabledFetches().at(-1)!;
    expect(last.advancedFilter).toBeUndefined();

    await waitFor(
      () => {
        expect(service.upsertUserListColumnConfig).toHaveBeenCalled();
      },
      { timeout: 3000 },
    );
    const [key, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(key).toBe(LISTING_KEY);
    expect(payload).toMatchObject({ filters: null, filtersVersion: null });
  });

  it('sorting by a different column reaches the debounced upsert (AC-B5)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    storedConfig(null);
    mockList([order()]);
    renderList();

    await vi.waitFor(() => {
      expect(screen.getByText('DO-2026-0001')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Debtor Name/ }));

    await vi.advanceTimersByTimeAsync(900);

    await vi.waitFor(() => {
      expect(service.upsertUserListColumnConfig).toHaveBeenCalled();
    });
    const [key, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(key).toBe(LISTING_KEY);
    expect(payload.sorting).toEqual([{ id: 'debtor_name', desc: false }]);
    vi.useRealTimers();
  });
});
