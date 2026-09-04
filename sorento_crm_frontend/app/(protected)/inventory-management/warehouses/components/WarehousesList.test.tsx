/**
 * Warehouses list - the `Fulfilment planning` column (borrow ladder v7.1 S1, AC-S1-3).
 *
 * One thing pinned: the flag is READABLE from the list, as On or Off per row, so an admin
 * can see which bins are in the plan without opening each record. `useListingColumnPreferences`
 * is mocked because the DataGrid renders no rows in jsdom without it.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Warehouse } from '../types/warehouse.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => '/inventory-management/warehouses',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

vi.mock('@/components/upload-activity', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }),
}));

vi.mock('../services/warehouseService', () => ({
  bulkImportWarehouses: vi.fn(),
  validateWarehouseImport: vi.fn(),
}));

const rows: Warehouse[] = [
  {
    id: '11111111-1111-4111-8111-111111111111',
    warehouse_code: 'BRW-BB',
    warehouse_name: 'Brickworks BB',
    location: 'Brickworks',
    manager_id: null,
    is_active: true,
    created_at: new Date('2026-01-05T02:00:00Z'),
    updated_at: null,
    counts_as_available: true,
    fulfilment_planning: true,
    pool_warehouse_id: null,
    pool_warehouse_code: null,
  },
  {
    id: '22222222-2222-4222-8222-222222222222',
    warehouse_code: 'BRW-HP',
    warehouse_name: 'Brickworks HP',
    location: 'Brickworks',
    manager_id: null,
    is_active: true,
    created_at: new Date('2026-01-05T02:00:00Z'),
    updated_at: null,
    counts_as_available: true,
    fulfilment_planning: false,
    pool_warehouse_id: null,
    pool_warehouse_code: null,
  },
];

// Partial mock: anything the list reaches for that is not overridden here stays real and
// inert, because the service beneath it is stubbed above.
vi.mock('../hooks/useWarehouses', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/useWarehouses')>()),
  useWarehouses: () => ({
    data: { data: rows, pagination: { page: 1, limit: 50, total: rows.length, total_pages: 1 } },
    isLoading: false,
    isError: false,
  }),
}));

import WarehousesList from './WarehousesList';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <WarehousesList />
    </QueryClientProvider>,
  );
}

function rowFor(code: string): HTMLElement {
  const cell = screen.getByText(code);
  return cell.closest('tr') as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('WarehousesList - Fulfilment planning column', () => {
  it('renders the column header', () => {
    renderList();
    expect(screen.getAllByText('Fulfilment planning').length).toBeGreaterThan(0);
  });

  it('reads On for a flagged bin and Off for one outside the plan', () => {
    renderList();
    expect(within(rowFor('BRW-BB')).getByText('On')).toBeInTheDocument();
    expect(within(rowFor('BRW-HP')).getByText('Off')).toBeInTheDocument();
  });
});
