/**
 * S8 / AC-8.5 - the proforma invoice's General tab renders its source files as file CARDS
 * (`PLAN-scm-ui-feedback-14sep.md`, J6, ruling R8).
 *
 * TEST-FIRST. Today the Source files block is an inline `<ul>` built from `invoice.source_ref`
 * (a bare filename string) and the packing query's `file` - no Preview, no Download, no size,
 * and the `source_files[]` array the backend has been sending since AC-B14 is never read at
 * all (zero references in the whole frontend). Every test below is expected to be red until
 * S8 lands.
 *
 * No Unlink here, deliberately: a PI source file is the evidence of what was uploaded, and
 * detaching it from this screen would be a claim nobody made. That is why `AttachmentFileCard`
 * takes `onUnlink` as an option rather than drawing one always.
 *
 * Mock surface copied from `ProformaInvoiceDetail.test.tsx`, plus the attachment preview
 * service and download hook the card reaches for.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
/* The grace window is the server's; what this file proves is that the control parks one. */
const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'proforma_invoice.delete',
  entity_type: 'proforma_invoice',
  entity_id: 'pi-1',
  commit_at: '2026-08-30T10:00:10',
  window_seconds: 10,
});
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ProformaInvoiceDetail as ProformaInvoiceDetailData } from '../../../services/proformaInvoiceService';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

// What the file card calls. Mocked at the service/hook boundary, the same seam the packing
// list's own Related Documents card uses.
const { getAttachmentPreviewUrlMock, downloadMock } = vi.hoisted(() => ({
  getAttachmentPreviewUrlMock: vi.fn(),
  downloadMock: vi.fn(),
}));
vi.mock(
  '@/app/(protected)/resource-management/attachments/services/attachmentService',
  () => ({ getAttachmentPreviewUrl: getAttachmentPreviewUrlMock }),
);
vi.mock('@/app/(protected)/resource-management/attachments/hooks/useAttachments', () => ({
  useDownloadAttachment: () => ({ mutateAsync: downloadMock, isPending: false }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

const push = vi.fn();
const replace = vi.fn();
// The tab lives in the URL (S1) - a real `URLSearchParams` so `.get('tab')` and `.toString()`
// both behave, swappable per test to prove a reload lands back on the tab named in it.
let currentSearchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/proforma-invoices/pi-1',
  useRouter: () => ({ push, replace }),
  useSearchParams: () => currentSearchParams,
}));

// The WHOLE surface the components under test call. `ConfirmDeleteDialog` reports through
// `toast.custom`, and a mock without it threw inside react-query's own error path - which
// surfaced as an unhandled rejection that failed no test and hid any real one behind it.
vi.mock('@/lib/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    custom: vi.fn(),
    dismiss: vi.fn(),
  },
}));

// The line grid's product picker is server-searched; this suite is not testing the catalogue.
// A `vi.fn()` (not a bare async function) so the AC-B3/AC-B5 tests can hand back a real
// page for the ONE product being picked, without the rest of the suite caring.
const { getProductsMock } = vi.hoisted(() => ({
  getProductsMock: vi.fn().mockResolvedValue({ data: [], pagination: { total: 0 } }),
}));
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProducts: getProductsMock,
}));

// The master list (AC-B4), not free text - fed to every UoM cell's SearchableSelect.
// `vi.hoisted` because the array has to exist before `vi.mock`'s own hoisting runs it: the
// real `useUOMSelectQuery` is a `useQuery` with `staleTime: Infinity`, so `data` is the SAME
// reference across renders once loaded - a fresh literal returned from the mock on every
// call would fabricate an instability the real hook does not have, and cascade into the
// Lines grid's `columns` memo recomputing (and remounting every row's `SearchableSelect`)
// on every unrelated render.
const { UOM_OPTIONS } = vi.hoisted(() => ({
  UOM_OPTIONS: [
    { id: 'u-pcs', uom_code: 'PCS', uom_name: 'Pieces' },
    { id: 'u-box', uom_code: 'BOX', uom_name: 'Box' },
    { id: 'u-set', uom_code: 'SET', uom_name: 'Set' },
  ],
}));
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query', () => ({
  useUOMSelectQuery: () => ({
    data: UOM_OPTIONS,
    isLoading: false,
  }),
}));

const state = {
  data: undefined as ProformaInvoiceDetailData | undefined,
  isLoading: false,
  isError: false,
};

/** The writes, so a test can assert what the page ASKED the backend for. */
const writes = {
  matchCode: vi.fn(),
  forgetMatch: vi.fn(),
  save: vi.fn(),
  markAsRevision: vi.fn(),
  convert: vi.fn(),
};

vi.mock('../../../hooks/useProformaInvoices', () => ({
  // The pager reads the list page through the entity's shared key + fetch (S3-03).
  proformaInvoicesPagerQuery: {
    listQueryKey: () => ['scm-proforma-invoices'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  // The real key-builder, not a stub: `useProformaInvoicePacking`'s queryFn reads the
  // detail query's cache through this exact key (AC-E2 fix) - a mock that dropped it
  // left the packing query's `queryFn` throwing on every fetch, silently emptying every
  // dialog/tab that reads packing rows in this suite.
  proformaInvoiceDetailQueryKey: (id: string | null) => ['scm', 'proforma-invoices', 'detail', id],
  useProformaInvoice: () => state,
  // The header's pager pulls the neighbour list through this hook - one row is not enough to
  // show a pager (RecordNavigation's `items.length < 2` guard), so it stays out of the way.
  useProformaInvoices: () => ({ data: undefined, isLoading: false }),
  useConvertProformaInvoicesToDraftShipment: () => ({
    mutateAsync: writes.convert,
    isPending: false,
  }),
  useSaveProformaInvoice: () => ({ mutateAsync: writes.save, isPending: false }),
  useMarkProformaInvoiceAsRevision: () => ({
    mutateAsync: writes.markAsRevision,
    isPending: false,
  }),
}));

vi.mock('../../../hooks/useSupplierCodeAliases', () => ({
  useMatchSupplierCode: () => ({ mutateAsync: writes.matchCode, isPending: false }),
  useForgetSupplierCodeMatch: () => ({ mutateAsync: writes.forgetMatch, isPending: false }),
}));

vi.mock('../../../hooks/useFulfilment', () => ({
  useContainerSizes: () => ({
    data: [
      { id: 'size-40hq', code: '40HQ', label: '40ft high cube', cbm: 65, is_default: true },
      { id: 'size-20gp', code: '20GP', label: '20ft standard', cbm: 28, is_default: false },
    ],
    isLoading: false,
  }),
  // The Packing tab's "Attach packing list" mounts `SupplierDocumentsUploadDialog`
  // (S2), whose self-serve supplier picker reads this hook - irrelevant here since the
  // dialog is opened with `supplierId` already fixed to the invoice's own.
  useFulfilmentSuppliers: () => ({ data: [], isLoading: false }),
}));

import { ProformaInvoiceDetail } from './ProformaInvoiceDetail';

function detail(over: Partial<ProformaInvoiceDetailData> = {}): ProformaInvoiceDetailData {
  return {
    id: 'pi-1',
    supplier_id: 'sup-1',
    supplier_code: 'KAILU',
    supplier_name: 'Kailu Hardware Factory',
    pi_number: 'PI-2026-001',
    // Ours and theirs: `pi_number` is the number we minted, `supplier_ref` the one the
    // factory printed on the document (S1, AC-A2/A5).
    supplier_ref: 'KL20260801',
    invoice_date: '2026-08-01',
    currency: 'CNY',
    container_no: 'TEMU1234567',
    seal_no: 'WHA4528193',
    consignee: 'SORENTO SDN BHD',
    bl_no: 'BL-991',
    total_amount: 1000,
    line_count: 1,
    source_ref: 'proforma.xlsx',
    block_index: 0,
    uploaded_by: 'Ms Tee',
    created_at: '2026-08-01T02:00:00',
    updated_at: '2026-08-01T02:00:00',
    total_cbm: 69.36,
    unmeasured_lines: 0,
    status: 'current',
    revision_no: 1,
    revision_count: 1,
    adjusted_by: null,
    adjusted_at: null,
    is_adjusted: false,
    placement: 'not_converted',
    placed_qty: 0,
    total_qty: 10,
    remaining_qty: 10,
    packing_lists: [],
    lines: [
      {
        id: 'line-1',
        line_no: 1,
        row_number: 2,
        item_code: 'ITEM-1',
        description: 'Widget',
        qty: 10,
        uom: 'PCS',
        unit_price: 100,
        amount: 1000,
        po_ref: 'PO-1',
        remark: null,
        cartons: 10,
        cbm_per_unit: 0.17,
        cbm_total: 1.7,
        net_weight: 40,
        gross_weight: 50,
        supplier_qty: 10,
        supplier_unit_price: 100,
        placed_qty: 0,
        remaining_qty: 10,
        packing_lists: [],
        matched_by: null,
        match_source: null,
        match_id: null,
        product_id: 'prod-item-1',
        product_set_id: null,
        product_code: 'ITEM-1',
        set_code: null,
        matched: true,
        shipment_id: null,
        shipment_number: null,
        unmatched_reason: null,
      },
    ],
    converted_shipments: [],
    revisions: [
      {
        id: 'pi-1',
        pi_number: 'PI-2026-001',
        revision_no: 1,
        status: 'current',
        invoice_date: '2026-08-01',
        total_amount: 1000,
        line_count: 1,
      },
    ],
    revision_of_pi_number: null,
    diff: null,
    ...over,
  };
}

function renderDetail() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = () => (
    <QueryClientProvider client={qc}>
      <ProformaInvoiceDetail id="pi-1" />
    </QueryClientProvider>
  );
  const view = render(tree());
  // The detail hook is mocked, so a write's invalidation cannot be observed the usual way.
  // `refresh` replays what the refetch would do.
  return { ...view, refresh: () => view.rerender(tree()) };
}

beforeEach(() => {
  state.data = undefined;
  state.isLoading = false;
  state.isError = false;
  push.mockReset();
  replace.mockReset();
  currentSearchParams = new URLSearchParams();
  writes.save.mockReset().mockResolvedValue(undefined);
  writes.forgetMatch.mockReset().mockResolvedValue(undefined);
  writes.markAsRevision.mockReset().mockResolvedValue(undefined);
  getProductsMock.mockReset().mockResolvedValue({ data: [], pagination: { total: 0 } });
  getAttachmentPreviewUrlMock.mockReset().mockResolvedValue('https://cdn.example/att-1');
  downloadMock.mockReset().mockResolvedValue(new Blob(['x']));
  vi.spyOn(window, 'open').mockImplementation(() => null);
});
/** `source_files` is new on the payload (S8's backend half), so the fixture reaches past the
 *  current type rather than waiting for it. */
function withSourceFiles(entries: Array<Record<string, unknown>>, over: Record<string, unknown> = {}) {
  return { ...detail(over), source_files: entries } as unknown as ProformaInvoiceDetailData;
}

const PI_FILE = {
  id: 'link-1',
  attachment_id: 'att-1',
  name: 'Sorento PI 260801.xlsx',
  type: 'Proforma Invoice',
  file_size_bytes: 18342,
  mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  uploaded_at: '2026-08-01T02:00:00',
  download_url: '/api/v1/resource-management/attachments/att-1/download',
};

const PACKING_FILE = {
  id: 'link-2',
  attachment_id: 'att-2',
  name: 'Sorento packing 260801.xlsx',
  type: 'Packing List',
  file_size_bytes: 9021,
  mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  uploaded_at: '2026-08-02T02:00:00',
  download_url: '/api/v1/resource-management/attachments/att-2/download',
};

/** The Source files block, which the General tab already labels. */
function sourceFiles(): HTMLElement {
  return screen.getByLabelText('Source files');
}

describe('ProformaInvoiceDetail - Source files (AC-8.5)', () => {
  it('draws one card per entry, naming each file and its type and size', () => {
    state.data = withSourceFiles([PI_FILE, PACKING_FILE]);
    renderDetail();

    const block = within(sourceFiles());
    expect(block.getByText('Sorento PI 260801.xlsx')).toBeInTheDocument();
    expect(block.getByText(/Proforma Invoice/)).toBeInTheDocument();
    expect(block.getByText(/17\.91 KB/)).toBeInTheDocument();
    expect(block.getByText('Sorento packing 260801.xlsx')).toBeInTheDocument();
    expect(block.getByText(/Packing List/)).toBeInTheDocument();
    expect(block.getByText(/8\.81 KB/)).toBeInTheDocument();
  });

  it('gives every card a Preview and a Download, and no Unlink', () => {
    state.data = withSourceFiles([PI_FILE, PACKING_FILE]);
    renderDetail();

    const block = within(sourceFiles());
    expect(block.getAllByRole('button', { name: /preview/i })).toHaveLength(2);
    expect(block.getAllByRole('button', { name: /download/i })).toHaveLength(2);
    expect(block.queryByRole('button', { name: /unlink/i })).toBeNull();
  });

  it('previews the ATTACHMENT id, never the link id', async () => {
    state.data = withSourceFiles([PI_FILE]);
    renderDetail();

    fireEvent.click(within(sourceFiles()).getByRole('button', { name: /preview/i }));

    await waitFor(() => expect(getAttachmentPreviewUrlMock).toHaveBeenCalledWith('att-1'));
    await waitFor(() =>
      expect(window.open).toHaveBeenCalledWith(
        'https://cdn.example/att-1',
        '_blank',
        'noopener,noreferrer',
      ),
    );
  });

  it('downloads the attachment the card names', async () => {
    state.data = withSourceFiles([PACKING_FILE]);
    renderDetail();

    fireEvent.click(within(sourceFiles()).getByRole('button', { name: /download/i }));

    await waitFor(() => expect(downloadMock).toHaveBeenCalledWith('att-2'));
  });

  it('says an invoice with no file on record has none', () => {
    state.data = withSourceFiles([], { source_ref: null });
    renderDetail();

    expect(within(sourceFiles()).getByText('No source file on record.')).toBeInTheDocument();
  });
});
