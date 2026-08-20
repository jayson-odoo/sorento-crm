/**
 * Stock inquiry list - revision surfacing (UAC H4 / N1-N3).
 *
 * The "Rev N" badge and the `-R{n}` document-number suffix both come off the
 * denormalized `revision_no` already on the row: no per-row query.
 *
 * Mocks: next/navigation, sonner, the data hook, the listing-column preferences
 * hook (required for any DataGrid list test), and the preferences SERVICE - the
 * list gates its data query on the remembered view having resolved, and under
 * jsdom nothing answers that request, so the grid would sit on skeletons.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
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
  usePathname: () => '/procurement-management/stock-inquiries',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

// The real `useListingViewPreferences` runs; only its transport is stubbed, so the
// list's "wait for the remembered view, then fetch once" gate is exercised rather
// than mocked away. No stored view here, so the listing gets its shipped defaults.
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (listingKey: string) => ({
    listing_key: listingKey,
    config: null,
  })),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, config: unknown) => ({
    listing_key: listingKey,
    config,
  })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => <span>downloads</span>,
}));

const hooks = vi.hoisted(() => ({ useStockInquiries: vi.fn() }));
vi.mock('../hooks/useStockInquiries', () => ({
  useStockInquiries: (...a: unknown[]) => hooks.useStockInquiries(...a),
  useBulkDeleteStockInquiries: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));

import StockInquiriesList from './StockInquiriesList';
import type { StockInquiry } from '../types/stockInquiry.types';

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
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StockInquiriesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('StockInquiriesList revision surfacing', () => {
  it('shows no badge and a bare number at revision 0', async () => {
    mockList([inquiry({ revision_no: 0 })]);
    renderList();
    // Rows arrive once the remembered view resolves and releases the data query.
    expect(await screen.findByText('SI-26-0184')).toBeInTheDocument();
    expect(screen.queryByText(/^Rev \d+$/)).not.toBeInTheDocument();
  });

  it('shows "Rev 2" and the -R2 suffixed number once revised', async () => {
    mockList([inquiry({ id: 'si-2', revision_no: 2 })]);
    renderList();
    expect(await screen.findByText('Rev 2')).toBeInTheDocument();
    expect(screen.getByText('SI-26-0184-R2')).toBeInTheDocument();
    expect(screen.queryByText('SI-26-0184')).not.toBeInTheDocument();
  });

  it('renders the badge per row without any extra request', async () => {
    mockList([
      inquiry({ id: 'si-1', inquiry_number: 'SI-26-0001', revision_no: 0 }),
      inquiry({ id: 'si-2', inquiry_number: 'SI-26-0002', revision_no: 1 }),
      inquiry({ id: 'si-3', inquiry_number: 'SI-26-0003', revision_no: 5 }),
    ]);
    renderList();
    expect(await screen.findByText('SI-26-0001')).toBeInTheDocument();
    expect(screen.getByText('SI-26-0002-R1')).toBeInTheDocument();
    expect(screen.getByText('SI-26-0003-R5')).toBeInTheDocument();
    expect(screen.getByText('Rev 1')).toBeInTheDocument();
    expect(screen.getByText('Rev 5')).toBeInTheDocument();
    // One list query, no per-row revision lookup.
    expect(hooks.useStockInquiries).toHaveBeenCalled();
  });
});
