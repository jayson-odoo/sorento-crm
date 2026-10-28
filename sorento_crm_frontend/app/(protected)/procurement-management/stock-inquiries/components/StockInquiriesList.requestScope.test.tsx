/**
 * PORTAL-P4-REQUESTS S1 (P4-22, P4-23, P4-26): the Stock Inquiry list for a LIMITED user (holds `.view_own`,
 * not `.view`) and an unchanged staff user (control). Scaffolding copied from StockInquiriesList.revisionBadge.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
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
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (listingKey: string) => ({ listing_key: listingKey, config: null })),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, config: unknown) => ({ listing_key: listingKey, config })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => <span>downloads</span>,
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

const hooks = vi.hoisted(() => ({ useStockInquiries: vi.fn() }));
vi.mock('../hooks/useStockInquiries', () => ({
  useStockInquiries: (...a: unknown[]) => hooks.useStockInquiries(...a),
  useBulkDeleteStockInquiries: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));

import StockInquiriesList from './StockInquiriesList';
import type { StockInquiry } from '../types/stockInquiry.types';

const LIMITED = ['procurement.stock_inquiries.view_own', 'procurement.stock_inquiries.add'];
const STAFF = [
  'procurement.stock_inquiries.view',
  'procurement.stock_inquiries.add',
  'procurement.stock_inquiries.delete',
];

function row(over: Partial<StockInquiry> = {}): StockInquiry {
  return {
    id: 'si-1',
    inquiry_number: 'SI-26-0184',
    product_code: 'ABC-1',
    status: 'draft',
    revision_no: 0,
    created_at: new Date('2026-07-01T00:00:00'),
    updated_at: new Date('2026-07-01T00:00:00'),
    ...over,
  } as StockInquiry;
}

function renderList(slugs: string[]) {
  held = new Set(slugs);
  hooks.useStockInquiries.mockReturnValue({
    data: { data: [row()], empty: false, pagination: { page: 1, total: 1 } },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  });
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

describe('Stock Inquiry list, limited user', () => {
  it('shows Create Stock Inquiry (holds .add)', async () => {
    renderList(LIMITED);
    expect(await screen.findByText('SI-26-0184')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Create Stock Inquiry/ }).length).toBeGreaterThan(0);
  });

  it('hides Create when .add is not held', async () => {
    renderList(['procurement.stock_inquiries.view_own']);
    expect(await screen.findByText('SI-26-0184')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Create Stock Inquiry/ })).toBeNull();
  });

  it('offers no bulk Delete after selecting a row', async () => {
    renderList(LIMITED);
    await screen.findByText('SI-26-0184');
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'Select row' })[0]);
    expect(screen.queryByRole('button', { name: /^Delete$/ })).toBeNull();
  });

  it('status filter offers Draft', async () => {
    renderList(LIMITED);
    await screen.findByText('SI-26-0184');
    const trigger = screen.getByRole('button', { name: /^Filters?/ });
    fireEvent.pointerDown(trigger, { button: 0, pointerId: 1 });
    fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
    fireEvent.click(trigger);
    expect(await screen.findByRole('button', { name: 'Draft' })).toBeInTheDocument();
  });
});

describe('Stock Inquiry list, staff user (control, P4-26)', () => {
  it('still offers bulk Delete after selecting a row', async () => {
    renderList(STAFF);
    await screen.findByText('SI-26-0184');
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'Select row' })[0]);
    expect(await screen.findByRole('button', { name: /^Delete$/ })).toBeInTheDocument();
  });
});

describe('every column header sorts (P4-23), for limited and staff alike', () => {
  const COLUMNS = [
    'Stock inquiry number', 'Rev', 'Product Code', 'Item Description', 'Project Customer', 'Project Name',
    'Quantity', 'Delivery Date', 'Remark', 'Salesperson', 'Status', 'Assigned To',
    'Handled By', 'Print Count',
  ];
  it.each([['limited', LIMITED], ['staff', STAFF]])('%s: each header is a sort button', async (_n, slugs) => {
    renderList(slugs);
    await screen.findByText('SI-26-0184');
    const missing: string[] = [];
    for (const title of COLUMNS) {
      // A sortable header carries the sort glyph (up-down, or an arrow once active); an unsortable one is a bare label.
      const th = screen.queryAllByText(title).map((el) => el.closest('th')).find(Boolean);
      const sortable = !!th?.querySelector('svg.lucide-chevrons-up-down, svg.lucide-arrow-up, svg.lucide-arrow-down');
      if (!sortable) missing.push(title);
    }
    expect(missing).toEqual([]);
  });
});
