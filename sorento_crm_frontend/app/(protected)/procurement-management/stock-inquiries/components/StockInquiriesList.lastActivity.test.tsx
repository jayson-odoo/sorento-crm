/**
 * Stock inquiry OFFICE list - "Last activity" column and default sort.
 *
 * The list now defaults to sorting by `last_activity_at` (backend:
 * coalesce(last_revised_at, created_at)) and the former "Created" column
 * (`accessorKey: 'created_at'`) is now `id: 'last_activity_at'`, header
 * "Last activity" - rendering "Revised <date>" when `revision_no > 0` and
 * `last_revised_at` is set, else the created date with no prefix.
 *
 * Mocks: next/navigation, sonner, the data hook, and the listing-column
 * preferences hook (required for any DataGrid list test).
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

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: async () => {},
    isLoading: false,
  }),
}));

// The list holds its data query until the remembered view resolves; under jsdom
// nothing answers that request, so without this stub the grid sits on skeletons.
vi.mock(
  '@/lib/listing-column-preferences/listColumnPreferencesService',
  () => ({
    getUserListColumnConfig: vi.fn(async (listingKey: string) => ({
      listing_key: listingKey,
      config: null,
    })),
    upsertUserListColumnConfig: vi.fn(
      async (listingKey: string, config: unknown) => ({
        listing_key: listingKey,
        config,
      }),
    ),
    resetUserListColumnConfig: vi.fn(async () => undefined),
  }),
);

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => <span>downloads</span>,
}));

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
import { formatDateTimeInMalaysia } from '@/lib/helpers';

function inquiry(
  over: Partial<Record<keyof StockInquiry, unknown>> = {},
): StockInquiry {
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
});

describe('StockInquiriesList last activity column', () => {
  it('renders the "Last activity" column header', () => {
    mockList([inquiry()]);
    renderList();
    expect(screen.getByText('Last activity')).toBeInTheDocument();
    expect(screen.queryByText('Created')).not.toBeInTheDocument();
  });

  it('shows "Revised <date>" for a revised row and a bare created date otherwise', async () => {
    mockList([
      inquiry({
        id: 'si-revised',
        inquiry_number: 'SI-26-0001',
        revision_no: 2,
        // A plain ISO string here, not a Date object: `created_at` and
        // `last_revised_at` both flow through `formatDateTimeInMalaysia`
        // identically, and comparing against `formatExpected` (same helper,
        // same string form) keeps the assertion timezone-independent - a
        // `Date` object and its equivalent naive-ISO string are NOT
        // guaranteed to format the same (Date -> local-TZ parse, string ->
        // naive-UTC parse per `toUTCDate`).
        created_at: '2026-07-01T00:00:00',
        last_revised_at: '2026-07-15T00:00:00',
      }),
      inquiry({
        id: 'si-untouched',
        inquiry_number: 'SI-26-0002',
        revision_no: 0,
        created_at: '2026-07-03T00:00:00',
        last_revised_at: null,
      }),
    ]);
    renderList();

    const revisedText = `Revised ${formatExpected('2026-07-15T00:00:00')}`;
    const createdText = formatExpected('2026-07-03T00:00:00');

    // Rows arrive once the remembered view resolves and releases the data query.
    expect(await screen.findByText(revisedText)).toBeInTheDocument();
    expect(screen.getByText(createdText)).toBeInTheDocument();
    // The revised row's own created date must NOT appear - last_revised_at wins.
    expect(
      screen.queryByText(formatExpected('2026-07-01T00:00:00')),
    ).not.toBeInTheDocument();
  });

  it('calls the data hook with sorting [{ id: "last_activity_at", desc: true }] on first load', () => {
    mockList([inquiry()]);
    renderList();

    expect(hooks.useStockInquiries).toHaveBeenCalled();
    const callArgs = hooks.useStockInquiries.mock.calls[0][0];
    expect(callArgs.sorting).toEqual([{ id: 'last_activity_at', desc: true }]);
  });
});

// Mirrors formatDateTimeInMalaysia's formatting so assertions don't hardcode
// a timezone-dependent string.
function formatExpected(iso: string): string {
  return formatDateTimeInMalaysia(iso);
}
