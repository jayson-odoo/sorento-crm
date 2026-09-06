/**
 * PackingListsList - Upload packing list CTA, gated on the reader route's own
 * permission/module rather than the page's (AC-B1, review round 1 B4).
 *
 * `POST /api/v1/scm/packing-lists/apply` is gated on `scm.reorder.run`, an `scm`-module
 * permission - a different module from the one that gates viewing this list
 * (`procurement`). A tenant with `procurement` but not `scm` (or a user without that
 * permission) can see this list but cannot reach the reader route the CTA opens, so the
 * primary button falls back to `Create Packing List` and the reader is dropped from the
 * gear menu (it would otherwise duplicate the primary).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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

const routerPush = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/packing-lists',
  useRouter: () => ({ push: routerPush }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: any) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: any) => <>{children}</>,
  DropdownMenuContent: ({ children }: any) => <div data-testid="menu-content">{children}</div>,
  DropdownMenuItem: ({ children, onClick, disabled }: any) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  DropdownMenuCheckboxItem: ({ children }: any) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: any) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuGroup: ({ children }: any) => <div>{children}</div>,
  DropdownMenuPortal: ({ children }: any) => <>{children}</>,
  DropdownMenuSub: ({ children }: any) => <div>{children}</div>,
  DropdownMenuSubContent: ({ children }: any) => <div>{children}</div>,
  DropdownMenuSubTrigger: ({ children }: any) => <div>{children}</div>,
}));

vi.mock('@/components/upload-activity', () => ({
  useUploadManager: () => ({ startSession: vi.fn() }),
}));

const usePackingLists = vi.fn();
vi.mock('../hooks/usePackingLists', () => ({
  usePackingLists: (...a: unknown[]) => usePackingLists(...a),
  // Both dialogs are always mounted (closed by default) - idle stubs so mounting them
  // never needs a live mutation.
  useBulkDeletePackingLists: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeletePackingList: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('../services/packingListService', () => ({
  getLatestContainerStatusDocument: vi.fn(),
}));

// The reader dialog (opened only when the CTA is reachable) sources its own supplier list -
// irrelevant to gating, stubbed so opening it never reaches the network.
vi.mock('@/app/(protected)/scm/services/fulfilmentService', () => ({
  previewPackingList: vi.fn(),
  applyPackingList: vi.fn(),
  getFulfilmentSuppliers: vi.fn(async () => []),
}));

const useHasAnyPermission = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({
  useHasAnyPermission: (...a: unknown[]) => useHasAnyPermission(...a),
}));

const useTenantModules = vi.fn();
vi.mock('@/hooks/useTenantModules', () => ({
  useTenantModules: () => useTenantModules(),
}));

import PackingListsList from './PackingListsList';
import type { PackingList } from '../types/packingList.types';

function row(over: Partial<PackingList> = {}): PackingList {
  return {
    id: 'pl-1',
    shipment_number: 'PL-2026-0001',
    shipping_container_number: 'TEMU1234567',
    supplier: { id: 'sup-1', supplier_code: 'SUP1', supplier_name: 'Acme Sanitary' },
    shipment_date: '2026-08-01',
    estimated_arrival_date: null,
    shipment_status: 'in_transit',
    total_items_shipped: 100,
    created_at: '2026-08-01T00:00:00Z',
    ...over,
  } as PackingList;
}

function mockList(rows: PackingList[]) {
  usePackingLists.mockReturnValue({
    data: { data: rows, pagination: { page: 1, total: rows.length } },
    isLoading: false,
    isFetching: false,
    isPlaceholderData: false,
    refetch: vi.fn(),
  });
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PackingListsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockList([row()]);
  useTenantModules.mockReturnValue({ enabledModuleKeys: new Set(['procurement', 'scm']), isLoading: false });
  useHasAnyPermission.mockReturnValue(true);
});

describe('PackingListsList - Upload packing list is primary when reachable (AC-B1)', () => {
  it('shows Upload packing list as the primary button', () => {
    renderList();
    expect(screen.getByRole('button', { name: /Upload packing list/i })).toBeInTheDocument();
  });

  it('puts Create Packing List and Import Container Status in the gear menu', () => {
    renderList();
    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), { button: 0 });

    expect(screen.getByRole('button', { name: /Create Packing List/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Import Container Status/i })).toBeInTheDocument();
  });

  it('Create Packing List in the gear routes to the manual form', () => {
    renderList();
    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), { button: 0 });
    fireEvent.click(screen.getByRole('button', { name: /Create Packing List/i }));

    expect(routerPush).toHaveBeenCalledWith('/procurement-management/packing-lists/new');
  });
});

describe('PackingListsList - falls back to Create Packing List when the reader is out of reach (review B4)', () => {
  it('without scm.reorder.run: Create Packing List is primary, Upload is gone entirely', () => {
    useHasAnyPermission.mockReturnValue(false);
    renderList();

    expect(screen.getByRole('button', { name: /^Create Packing List$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Upload packing list/i })).not.toBeInTheDocument();

    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), { button: 0 });
    // Not duplicated in the gear now that it is the primary action - exactly one on screen.
    expect(screen.getAllByText('Create Packing List')).toHaveLength(1);
  });

  it('without the scm module enabled: same fallback, even with the permission', () => {
    useTenantModules.mockReturnValue({ enabledModuleKeys: new Set(['procurement']), isLoading: false });
    renderList();

    expect(screen.getByRole('button', { name: /^Create Packing List$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Upload packing list/i })).not.toBeInTheDocument();
  });

  it('primary Create Packing List routes to the manual form', () => {
    useHasAnyPermission.mockReturnValue(false);
    renderList();

    fireEvent.click(screen.getByRole('button', { name: /^Create Packing List$/i }));
    expect(routerPush).toHaveBeenCalledWith('/procurement-management/packing-lists/new');
  });
});
