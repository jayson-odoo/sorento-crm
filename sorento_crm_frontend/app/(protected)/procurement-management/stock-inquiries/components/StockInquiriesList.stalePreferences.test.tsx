/**
 * Stock inquiry OFFICE list - stale saved column preferences must not hide the
 * renamed column.
 *
 * The "Last activity" column's react-table id changed from `created_at` to
 * `last_activity_at`. A user with a SAVED preference row from before the
 * rename still names `created_at` in its `columnOrder` / `columnVisibility`.
 * `useListingColumnPreferences` filters unknown ids out of both, so the stale
 * entry is simply dropped rather than silently suppressing the new column -
 * this test exercises the REAL hook (not the usual stub) against a mocked
 * service response to prove that.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor, act } from '@testing-library/react';
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
  usePathname: () => '/procurement-management/stock-inquiries',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => <span>downloads</span>,
}));

// Real useListingColumnPreferences hook runs; only the HTTP-backed service is
// mocked, standing in for a preference row saved before the id rename.
vi.mock(
  '@/lib/listing-column-preferences/listColumnPreferencesService',
  () => ({
    getUserListColumnConfig: vi.fn().mockResolvedValue({
      listing_key: '/procurement-management/stock-inquiries',
      config: {
        version: 1,
        // Stale entries from before the rename: the grid's own leaf ids no
        // longer include `created_at`, only `last_activity_at`.
        columnOrder: ['inquiry_number', 'created_at', 'status'],
        columnVisibility: { created_at: false, status: true },
        columnSizing: {},
      },
    }),
    upsertUserListColumnConfig: vi
      .fn()
      .mockResolvedValue({ listing_key: '', config: null }),
    resetUserListColumnConfig: vi.fn().mockResolvedValue(undefined),
  }),
);

const hooks = vi.hoisted(() => ({ useStockInquiries: vi.fn() }));
vi.mock('../hooks/useStockInquiries', () => ({
  useStockInquiries: (...a: unknown[]) => hooks.useStockInquiries(...a),
  useBulkDeleteStockInquiries: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

import StockInquiriesList from './StockInquiriesList';
import type { StockInquiry } from '../types/stockInquiry.types';
import * as service from '@/lib/listing-column-preferences/listColumnPreferencesService';

function inquiry(over: Partial<StockInquiry> = {}): StockInquiry {
  return {
    id: 'si-1',
    inquiry_number: 'SI-26-0184',
    product_code: 'ABC-1',
    status: 'pending_purchasing',
    revision_no: 0,
    created_at: new Date('2026-07-01T00:00:00'),
    updated_at: new Date('2026-07-01T00:00:00'),
    ...over,
  } as StockInquiry;
}

function mockList(rows: StockInquiry[]) {
  hooks.useStockInquiries.mockReturnValue({
    data: {
      data: rows,
      empty: rows.length === 0,
      pagination: { page: 1, total: rows.length },
    },
    isLoading: false,
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
      <StockInquiriesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  (
    service.getUserListColumnConfig as ReturnType<typeof vi.fn>
  ).mockResolvedValue({
    listing_key: '/procurement-management/stock-inquiries',
    config: {
      version: 1,
      columnOrder: ['inquiry_number', 'created_at', 'status'],
      columnVisibility: { created_at: false, status: true },
      columnSizing: {},
    },
  });
});

describe('StockInquiriesList stale saved column preferences', () => {
  it('keeps "Last activity" visible when the saved config still names created_at', async () => {
    mockList([inquiry()]);
    renderList();

    // Wait for the saved-config fetch to fire, then let react-query resolve
    // it and the hook's apply effect actually run and commit. "Last activity"
    // is present on the FIRST render too (before any saved config is
    // applied), so asserting on it alone would pass trivially without ever
    // exercising the apply path - the extra real-clock wait lets that async
    // chain (query resolve -> re-render -> effect -> setColumnVisibility ->
    // re-render) settle before the assertion that matters.
    await waitFor(() => {
      expect(service.getUserListColumnConfig).toHaveBeenCalled();
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(screen.getByText('Last activity')).toBeInTheDocument();

    // The stale "Created" label must never reappear - the column was renamed,
    // not restored.
    expect(screen.queryByText('Created')).not.toBeInTheDocument();
  });
});
