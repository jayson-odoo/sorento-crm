/**
 * PackingListsList - Upload becomes the Drive-style packing list CTA, the reader (Upload
 * supplier documents) moves to the gear (R3, CAPTAIN REVERSED 7 Sep 2026).
 *
 * Upload opens the generic Create Attachment dialog preset and locked to the Packing List
 * type, gated on the write route's own permission (`resource.attachments.upload`) rather
 * than the page's own - same pattern as the reader route below. The reader
 * (`POST /api/v1/scm/packing-lists/apply`) is gated on `scm.reorder.run`, an `scm`-module
 * permission - a tenant with `procurement` but not `scm` (or a user without that
 * permission) can see this list but cannot reach the reader route, so it drops from the
 * gear (review round 1 B4, preserved through the reversal).
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

/** The dropdown-menu stub renders children and, for an item, wires the click - that is
 *  the whole surface this list touches, so it is typed rather than left as `any`. */
type MenuSlotProps = { children?: React.ReactNode };
type MenuItemProps = MenuSlotProps & { onClick?: () => void; disabled?: boolean };

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: MenuSlotProps) => <>{children}</>,
  DropdownMenuContent: ({ children }: MenuSlotProps) => (
    <div data-testid="menu-content">{children}</div>
  ),
  DropdownMenuItem: ({ children, onClick, disabled }: MenuItemProps) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  DropdownMenuCheckboxItem: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuGroup: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuPortal: ({ children }: MenuSlotProps) => <>{children}</>,
  DropdownMenuSub: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuSubContent: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuSubTrigger: ({ children }: MenuSlotProps) => <div>{children}</div>,
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

// The reader dialog (opened only when it's reachable) sources its own supplier list -
// irrelevant to gating, stubbed so opening it never reaches the network.
vi.mock('@/app/(protected)/scm/services/fulfilmentService', () => ({
  previewSupplierDocuments: vi.fn(),
  applySupplierDocuments: vi.fn(),
  getFulfilmentSuppliers: vi.fn(async () => []),
}));

const useAttachmentTypesList = vi.fn();
vi.mock('@/app/(protected)/resource-management/attachments/hooks/useAttachments', () => ({
  useAttachmentTypesList: (...a: unknown[]) => useAttachmentTypesList(...a),
}));

// The Drive upload dialog itself is out of scope here (covered by its own test file) -
// stubbed to a marker that exposes the props this list passed it, so gating/preset
// behaviour is asserted without dragging in its type list / directory tree / upload
// mutation network.
type AttachmentUploadDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultTypeId?: string;
  lockType?: boolean;
  defaultDirectoryId?: string | null;
};
vi.mock('@/app/(protected)/resource-management/attachments/components/AttachmentUploadDialog', () => ({
  default: ({ open, defaultTypeId, lockType, defaultDirectoryId }: AttachmentUploadDialogProps) =>
    open ? (
      <div data-testid="attachment-upload-dialog">
        <span data-testid="default-type-id">{defaultTypeId ?? ''}</span>
        <span data-testid="lock-type">{String(!!lockType)}</span>
        <span data-testid="default-directory-id">{defaultDirectoryId ?? ''}</span>
      </div>
    ) : null,
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

const PACKING_LIST_TYPE = {
  id: 'pl-type',
  code: 'packing_list',
  type_name: 'Packing List',
  default_directory_id: 'dir-1',
};

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockList([row()]);
  useTenantModules.mockReturnValue({ enabledModuleKeys: new Set(['procurement', 'scm']), isLoading: false });
  // Both write routes reachable by default - `scm.reorder.run` for the reader,
  // `resource.attachments.upload` for the Drive upload.
  useHasAnyPermission.mockReturnValue(true);
  useAttachmentTypesList.mockReturnValue({ data: [PACKING_LIST_TYPE], isLoading: false });
});

describe('PackingListsList - Upload is the primary CTA (AC-B1, CAPTAIN REVERSED 7 Sep)', () => {
  it('shows Upload as the primary button', () => {
    renderList();
    expect(screen.getByRole('button', { name: /^Upload$/i })).toBeInTheDocument();
  });

  it('clicking Upload opens the Create Attachment dialog preset and locked to Packing List', () => {
    renderList();
    fireEvent.click(screen.getByRole('button', { name: /^Upload$/i }));

    expect(screen.getByTestId('attachment-upload-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('default-type-id')).toHaveTextContent('pl-type');
    expect(screen.getByTestId('lock-type')).toHaveTextContent('true');
    expect(screen.getByTestId('default-directory-id')).toHaveTextContent('dir-1');
  });

  it('puts Create Packing List and Import Container Status in the gear, with no supplier-document upload of its own (S3, AC-C2)', () => {
    renderList();
    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), { button: 0 });

    expect(screen.getByRole('button', { name: /Create Packing List/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Import Container Status/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Upload supplier documents/i })).not.toBeInTheDocument();
  });

  it('Create Packing List in the gear routes to the manual form', () => {
    renderList();
    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), { button: 0 });
    fireEvent.click(screen.getByRole('button', { name: /Create Packing List/i }));

    expect(routerPush).toHaveBeenCalledWith('/procurement-management/packing-lists/new');
  });
});

describe('PackingListsList - falls back to unpreset Upload when the type cannot be resolved', () => {
  it('opens the dialog unpreset and unlocked when no attachment type matches', () => {
    useAttachmentTypesList.mockReturnValue({ data: [], isLoading: false });
    renderList();
    fireEvent.click(screen.getByRole('button', { name: /^Upload$/i }));

    expect(screen.getByTestId('default-type-id')).toHaveTextContent('');
    expect(screen.getByTestId('lock-type')).toHaveTextContent('false');
  });
});

describe('PackingListsList - falls back to Create Packing List when the Drive upload is out of reach', () => {
  it('without resource.attachments.upload: Create Packing List is primary, Upload is gone entirely', () => {
    useHasAnyPermission.mockImplementation((slugs: string[]) =>
      slugs.includes('resource.attachments.upload') ? false : true,
    );
    renderList();

    expect(screen.getByRole('button', { name: /^Create Packing List$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Upload$/i })).not.toBeInTheDocument();

    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), { button: 0 });
    // Not duplicated in the gear now that it is the primary action - exactly one on screen.
    expect(screen.getAllByText('Create Packing List')).toHaveLength(1);
  });

  it('primary Create Packing List routes to the manual form', () => {
    useHasAnyPermission.mockImplementation((slugs: string[]) =>
      slugs.includes('resource.attachments.upload') ? false : true,
    );
    renderList();

    fireEvent.click(screen.getByRole('button', { name: /^Create Packing List$/i }));
    expect(routerPush).toHaveBeenCalledWith('/procurement-management/packing-lists/new');
  });
});
