/**
 * OrdersList — AutoCount source gate on the mixed delivery-order list.
 *   - an autocount row renders the AutoCount provenance badge and its
 *     bulk-delete select checkbox is DISABLED (read-only, cannot be actioned);
 *   - a manual row renders NO badge and its select checkbox is ENABLED
 *     (full CRUD, selectable for bulk delete);
 *   - empty + loading states render without crashing.
 *
 * NOTE: this list has no per-row Edit/Delete buttons — those live on the detail
 * page (OrderDetail). The only row-level mutating action on the list is
 * bulk-delete selection, so that is the "action" gated here. Detail-page
 * read-only gating (Edit/Delete/annotation card) is exercised via Playwright.
 *
 * The data hook is mocked; DataGrid's browser-only deps are stubbed inline.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
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
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/order-management/orders',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/components/upload-activity', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }),
}));

vi.mock('../../shared/hooks/use-order-status-select-query', () => ({
  useOrderStatusSelectQuery: () => ({ data: [] }),
}));

const mockUseOrders = vi.fn();
vi.mock('../hooks/useOrders', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    useOrders: (params: unknown) => mockUseOrders(params),
  };
});

import OrdersList from './OrdersList';

const AUTOCOUNT_ROW = {
  id: 'ord-ac',
  order_number: 'AC-SMOKE-DO-1',
  source: 'autocount' as const,
  sync_source: 'autocount',
  internal_note: null,
  follow_up: false,
  subtotal_amount: 0,
  discount_amount: 0,
  tax_amount: 0,
  total_amount: 0,
  created_at: '2026-07-26T00:00:00',
  updated_at: '2026-07-26T00:00:00',
  synced_to_excel: false,
};

const MANUAL_ROW = {
  id: 'ord-manual',
  order_number: 'DO-MANUAL-1',
  source: 'manual' as const,
  sync_source: 'manual',
  internal_note: null,
  follow_up: false,
  subtotal_amount: 0,
  discount_amount: 0,
  tax_amount: 0,
  total_amount: 0,
  created_at: '2026-07-25T00:00:00',
  updated_at: '2026-07-25T00:00:00',
  synced_to_excel: false,
};

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrdersList />
    </QueryClientProvider>,
  );
}

/** The select checkbox lives in the first cell of a row; find it by the row's order number. */
function rowSelectCheckbox(orderNumber: string): HTMLElement {
  const rowEl = screen.getByText(orderNumber).closest('tr');
  expect(rowEl).not.toBeNull();
  return within(rowEl as HTMLElement).getByRole('checkbox', { name: /select row/i });
}

beforeEach(() => {
  cleanup();
  mockUseOrders.mockReset();
});

describe('OrdersList AutoCount source gate', () => {
  it('shows the AutoCount badge on the synced row and none on the manual row', () => {
    mockUseOrders.mockReturnValue({
      data: { data: [AUTOCOUNT_ROW, MANUAL_ROW], pagination: { total: 2, page: 1, limit: 50 } },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    });
    renderList();

    expect(screen.getByText('AC-SMOKE-DO-1')).toBeInTheDocument();
    expect(screen.getByText('DO-MANUAL-1')).toBeInTheDocument();
    // Exactly one provenance badge — only the autocount row carries it.
    expect(screen.getAllByText('AutoCount')).toHaveLength(1);
  });

  it('disables bulk-delete selection on the autocount row but not the manual row', () => {
    mockUseOrders.mockReturnValue({
      data: { data: [AUTOCOUNT_ROW, MANUAL_ROW], pagination: { total: 2, page: 1, limit: 50 } },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    });
    renderList();

    expect(rowSelectCheckbox('AC-SMOKE-DO-1')).toBeDisabled();
    expect(rowSelectCheckbox('DO-MANUAL-1')).not.toBeDisabled();
  });

  it('renders the empty state without crashing', () => {
    mockUseOrders.mockReturnValue({
      data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    });
    renderList();
    expect(screen.getByPlaceholderText('Search delivery orders...')).toBeInTheDocument();
  });

  it('renders the loading state without crashing', () => {
    mockUseOrders.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: true,
    });
    renderList();
    expect(screen.getByPlaceholderText('Search delivery orders...')).toBeInTheDocument();
  });
});
