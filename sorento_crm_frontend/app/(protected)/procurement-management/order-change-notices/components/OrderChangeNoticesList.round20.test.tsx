/**
 * OCN-ORDER-CHANGE-NOTICE round 20, I7 (list): a sortable "Requested by" column replaces
 * "Sales in charge". Same harness as OrderChangeNoticesList.test.tsx.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/procurement-management/order-change-notices',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [{ id: 'zzt-u1', name: 'Sales Person A' }]),
}));

const svc = vi.hoisted(() => ({ list: vi.fn(), types: vi.fn() }));
vi.mock('../services/orderChangeNoticeService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderChangeNoticeService')>();
  return {
    ...actual,
    listOrderChangeNotices: (...args: unknown[]) => svc.list(...args),
    listChangeTypes: (...args: unknown[]) => svc.types(...args),
  };
});

import OrderChangeNoticesList from './OrderChangeNoticesList';
import { CHANGE_TYPES, ocnRow } from './ocnTestData';

const ROWS = [
  ocnRow({
    sales_in_charge_user_id: undefined,
    sales_in_charge_name: undefined,
    requested_by_contact_id: 'contact-a',
    requested_by: 'Requestor A',
  }),
];

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderChangeNoticesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  svc.list.mockResolvedValue({ data: ROWS, pagination: { total: ROWS.length, page: 1, limit: 25 } });
  svc.types.mockResolvedValue(CHANGE_TYPES);
});

describe('round 20: Requested by column (I7)', () => {
  it('has a "Requested by" column showing the contact name and no "Sales in charge" column', async () => {
    mount();
    expect(await screen.findByRole('columnheader', { name: /^Requested by$/ })).toBeTruthy();
    expect(screen.queryByRole('columnheader', { name: /Sales in charge/i })).toBeNull();
    expect(await screen.findByText('Requestor A')).toBeTruthy();
  });

  it('sorts on the server with the sort key requested_by', async () => {
    mount();
    const header = await screen.findByRole('columnheader', { name: /^Requested by$/ });
    // The sort button is disabled while the first page loads: wait for a row first.
    await screen.findByText('Requestor A');
    fireEvent.click(header.querySelector('button') ?? header);
    await waitFor(() => {
      const last = svc.list.mock.calls.at(-1)?.[0] as { sorting?: Array<{ id: string }> };
      expect(last.sorting?.[0]?.id).toBe('requested_by');
    });
  });
});
