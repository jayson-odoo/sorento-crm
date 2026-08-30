/**
 * GRNList - the Status column reads as a soft pastel pill, the same chip the rest
 * of the app uses (complaints / PR / SF / stock inquiries via lib/status-pill),
 * rather than a solid badge that looks like a clickable button.
 *
 * Mocks follow the house pattern for DataGrid list tests: the data hook, the
 * listing-column-preferences hook (required or the grid never settles),
 * next/navigation, ResizeObserver, and the upload-activity drawer.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/grn',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/components/upload-activity', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }),
}));

const useGRNsMock = vi.fn();
// The row "..." menu resolves permissions; this test has no session or query
// client, and RBAC has its own tests.
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

vi.mock('../hooks/useGRN', () => ({
  useGRNs: (...args: unknown[]) => useGRNsMock(...args),
  // The bulk-delete dialog renders with the list, so its hook has to exist.
  useBulkDeleteGRNs: () => ({ mutateAsync: vi.fn(), isPending: false }),
  // The row "..." menu shares the record's action set, which sets status.
  useUpdateGRN: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useDeleteGRN: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import GRNList from './GRNList';

const ROWS = [
  {
    id: 'grn-1',
    picking_number: 'GR-001114',
    spo_number: 'PO-000338',
    picking_date: '2026-06-22',
    picking_status: 'approved',
    items_count: 9,
  },
  {
    id: 'grn-2',
    picking_number: 'GR-001115',
    spo_number: 'SPO-2026/06-0014',
    picking_date: '2026-06-23',
    picking_status: 'draft',
    items_count: 36,
  },
];

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <GRNList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  useGRNsMock.mockReturnValue({
    data: { data: ROWS, pagination: { total: ROWS.length, page: 1, limit: 50 } },
    isLoading: false,
  });
});

describe('GRNList status column', () => {
  it('renders each status as a pastel pill, not a solid badge', async () => {
    renderList();

    const approved = await waitFor(() => screen.getByText('Approved'));
    expect(approved.className).toContain('rounded-full');
    expect(approved.className).toContain('bg-blue-100');
    expect(approved.className).toContain('text-blue-800');
    // A solid-filled badge is what this replaced; the pill must not carry one.
    expect(approved.className).not.toContain('bg-green-500');
    expect(approved.className).not.toContain('bg-primary');
  });

  it('colours a different status differently, from the shared palette', async () => {
    renderList();

    const draft = await waitFor(() => screen.getByText('Draft'));
    expect(draft.className).toContain('rounded-full');
    expect(draft.className).toContain('bg-muted');
  });
});
