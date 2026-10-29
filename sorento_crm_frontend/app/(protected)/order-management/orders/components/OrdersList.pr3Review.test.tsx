/**
 * FILTER-MULTISELECT PR3 review: a status id the options do not hold (an old link, or before the status
 * lookup answers) is never shown as its own label. Uses the real SearchableMultiSelect.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import OrdersList from './OrdersList';

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
  usePathname: () => '/order-management/orders',
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (listingKey: string) => ({ listing_key: listingKey, config: null })),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, config: unknown) => ({ listing_key: listingKey, config })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));
const useOrders = vi.fn();
vi.mock('../hooks/useOrders', () => ({ useOrders: (...a: unknown[]) => useOrders(...a) }));
vi.mock('../../shared/hooks/use-order-status-select-query', () => ({
  useOrderStatusSelectQuery: () => ({
    data: [
      { id: 'st-new', status_name: 'ZZT New' },
      { id: 'st-proc', status_name: 'ZZT Processing' },
      { id: 'st-done', status_name: 'ZZT Delivered' },
    ],
  }),
}));
vi.mock('../actions', () => ({ OrderRowActions: () => null }));
vi.mock('@/components/upload-activity', () => ({ useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }) }));
vi.mock('@/hooks/useDeferredBulkAction', () => ({ useDeferredBulkAction: () => ({ start: vi.fn(), pending: false }) }));
vi.mock('@/lib/pending-entity-store', () => ({
  pendingEntityKey: (t: string, id: string) => `${t}:${id}`,
  usePendingEntityKeys: () => new Set<string>(),
}));
vi.mock('@/app/(protected)/system-management/import-jobs/autocount-pull/hooks/useAutocountPull', () => ({
  useAutocountPullAction: () => ({ label: 'Pull from AutoCount', onClick: vi.fn(), disabled: false }),
}));
vi.mock('@/app/(protected)/system-management/import-jobs/autocount-pull/components/PullScopeDialog', () => ({
  PullScopeDialog: () => null,
}));
vi.mock('@/components/template/TemplateUploadDialog', () => ({ TemplateUploadDialog: () => null }));
vi.mock('./OrderTrackingUploadDialog', () => ({ OrderTrackingUploadDialog: () => null }));
vi.mock('./OrderLinesImportDialog', () => ({ OrderLinesImportDialog: () => null }));
beforeEach(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
  url.search = '';
  useOrders.mockReset();
  useOrders.mockReturnValue({
    data: { data: [{ id: 'o-1', order_number: 'ZZT-DO-1' }], pagination: { total: 1, page: 1, limit: 50, pages: 1 } },
    isLoading: false, isPlaceholderData: false, isError: false, error: null, refetch: vi.fn(), isFetching: false,
  });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrdersList />
    </QueryClientProvider>,
  );
}

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-/i;
const ORPHAN = '9f1b6c52-4d1e-4a39-8a77-0c2d5e8b1f34';

describe('Delivery orders - a status id the options do not hold', () => {
  it('shows no UUID in the Status trigger or a chip', async () => {
    url.search = `order_status_id=${ORPHAN}`;
    renderIt();
    await screen.findByText('ZZT-DO-1');
    expect(document.body.textContent ?? '').not.toMatch(UUID);
  });

  it('shows no UUID beside a known status either', async () => {
    url.search = `order_status_id=st-new%2C${ORPHAN}`;
    renderIt();
    await screen.findByText('ZZT-DO-1');
    expect(document.body.textContent ?? '').not.toMatch(UUID);
    expect(document.body.textContent ?? '').toMatch(/ZZT New/);
  });
});
