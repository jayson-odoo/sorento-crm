/**
 * The CRM price tag requests queue - the "Product data" column (AC-D6,
 * PLAN-price-tag-currency-token-extract-prompt.md section D).
 *
 * `DataGridTable` DOES render rows under jsdom once the column-preferences
 * fetch is stubbed (project_datagrid_jsdom_rows_mockable.md memory) - the one
 * mock below is what makes every row assertion here real rather than
 * vacuously passing against a permanent skeleton.
 *
 * Written test-FIRST: the column does not exist yet, so both tests fail
 * today on `screen.findByText` timing out / the count never appearing.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/dealer-kit/price-tag-requests',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// DataGrid persists column prefs via this hook (fires a real network call) -
// stubbed, or the grid renders skeletons forever and no row is assertable.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const listPriceTagRequests = vi.fn();
const claimPriceTagRequest = vi.fn();
vi.mock('../../services/priceTagRequestService', () => ({
  listPriceTagRequests: (...a: unknown[]) => listPriceTagRequests(...a),
  claimPriceTagRequest: (...a: unknown[]) => claimPriceTagRequest(...a),
}));

import PriceTagRequestsList from './PriceTagRequestsList';
import type { PriceTagRequestSummary } from '../../services/priceTagRequestService';

// `data_changed_tag_count` does not exist on `PriceTagRequestSummary` yet
// (AC-D5); this local shape is the future contract the FE type will grow.
type RowWithChangeCount = PriceTagRequestSummary & { data_changed_tag_count?: number };

function row(overrides: Partial<RowWithChangeCount> = {}): RowWithChangeCount {
  return {
    id: 'req-1',
    doc_number: 'PT-000001',
    debtor_code: null,
    debtor_name: 'ZZT Dealer',
    needed_by_date: null,
    notes: null,
    status: 'designing',
    line_count: 1,
    created_at: '2026-09-01T00:00:00Z',
    assigned_to_id: 'user-1',
    assigned_to_name: 'Marketing Mei',
    contact_name: 'Sales Sam',
    ...overrides,
  };
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PriceTagRequestsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PriceTagRequestsList - Product data column (AC-D6)', () => {
  it('renders "Product data changed · 2" for a row with data_changed_tag_count 2', async () => {
    listPriceTagRequests.mockResolvedValue({
      data: [row({ id: 'req-1', data_changed_tag_count: 2 })],
      pagination: { total: 1, page: 1, limit: 50 },
    });

    renderList();

    expect(await screen.findByText('Product data changed · 2')).toBeInTheDocument();
  });

  it('renders an empty cell - no pill - for a row with data_changed_tag_count 0', async () => {
    listPriceTagRequests.mockResolvedValue({
      data: [row({ id: 'req-2', data_changed_tag_count: 0 })],
      pagination: { total: 1, page: 1, limit: 50 },
    });

    renderList();

    // The row itself rendered, so an absent pill below is a real negative,
    // not a permanent-skeleton false pass.
    await screen.findByText('PT-000001');
    expect(screen.queryByText(/Product data changed/)).toBeNull();
  });
});
