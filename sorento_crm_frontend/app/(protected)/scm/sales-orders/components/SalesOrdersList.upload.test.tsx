/**
 * The order book upload lives on Reorder planning as the reason the whole plan is computed
 * from it - but a sales order manager reasonably looks for it here too. This pins the wiring
 * ONLY: the toolbar opens the real, unforked `OutstandingUploadDialog` with `kind="sales-orders"`,
 * and once it queues an upload, this list's own query and the reorder plan's two queries are
 * invalidated the same way `ReorderPlanningView`'s `uploadQueued` does. The dialog's own
 * behaviour (the Test verdict, the two-step guarantee, ...) is pinned once in
 * `../../reorder/components/OutstandingUploadDialog.test.tsx` and is not re-asserted here.
 *
 * The action is called "Upload sales orders", never "Upload outstanding sales orders": the
 * file carries the whole book, completed orders included, and the old wording had the captain
 * asking which half of it he was meant to export.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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
Element.prototype.scrollIntoView = vi.fn();

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const push = vi.fn();
vi.mock('next/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/navigation')>()),
  useRouter: () => ({ push }),
  usePathname: () => '/scm/sales-orders',
  useSearchParams: () => new URLSearchParams(),
}));

const EMPTY = { data: [], isLoading: false };
vi.mock('../../hooks/useScmOptions', () => ({
  useCustomerOptions: () => ({
    data: [{ value: '300-R009', label: 'Rowenda Kitchen Sdn Bhd' }],
    isLoading: false,
  }),
  useOrderTypeOptions: () => EMPTY,
  useProductOptions: () => EMPTY,
  useSupplierOptions: () => EMPTY,
  useCategoryOptions: () => EMPTY,
  useWarehouseOptions: () => EMPTY,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('../../hooks/useSalesOrders', () => ({
  useSalesOrders: () => ({
    data: { data: [], pagination: { total: 0, page: 1, limit: 25 }, empty: true },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
  useSalesOrderAgents: () => ({ data: [], isLoading: false }),
  useCreateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateDoFromSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

// The drawer bridge the dialog notifies on a successful queue - not this list's concern.
const notifyImportQueued = vi.fn();
vi.mock('@/components/upload-activity/useImportJobDrawer', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued }),
}));

const previewOutstandingImport = vi.fn();
const applyOutstandingImport = vi.fn();
const getOutstandingUploadConfig = vi.fn();
vi.mock('../../reorder/services/outstandingImportService', () => ({
  previewOutstandingImport: (...a: unknown[]) => previewOutstandingImport(...a),
  applyOutstandingImport: (...a: unknown[]) => applyOutstandingImport(...a),
  getOutstandingUploadConfig: (...a: unknown[]) => getOutstandingUploadConfig(...a),
}));

import SalesOrdersList from './SalesOrdersList';

const QUEUED = { message: 'Order book upload queued.', job_id: 'job-2026-08-19', id: 'row-1' };

const PREVIEW = {
  doc_type: 'outstanding_so',
  ok: true,
  scope_documents: ['SO900001'],
  counts: { added: 1, qty_changed: 0, date_moved: 0, date_and_qty_changed: 0, closed: 0, unchanged: 0 },
  total_rows: 1,
  unmapped_headers: [],
  missing_columns: [],
  row_problems: [],
  resolution_issues: [],
  unmapped_agents: [],
  samples: {},
};

function xlsx(name = 'outstanding-so.xlsx'): File {
  return new File([new Uint8Array(16)], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  render(
    <QueryClientProvider client={qc}>
      <SalesOrdersList />
    </QueryClientProvider>,
  );
  return { invalidateSpy };
}

beforeEach(() => {
  push.mockReset();
  notifyImportQueued.mockReset();
  previewOutstandingImport.mockReset().mockResolvedValue(PREVIEW);
  applyOutstandingImport.mockReset().mockResolvedValue(QUEUED);
  getOutstandingUploadConfig
    .mockReset()
    .mockResolvedValue({ allowed_extensions: ['.xlsx', '.xlsm', '.xls'] });
});

describe('SalesOrdersList - upload sales orders', () => {
  it('is not open until the toolbar button is pressed', () => {
    renderList();
    expect(
      screen.queryByRole('heading', { name: /Upload sales orders/i }),
    ).toBeNull();
  });

  it('opens the real, unforked outstanding-upload dialog scoped to sales orders', async () => {
    renderList();

    // Two secondary actions (Refresh, Upload) collapse into the shared "Actions" dropdown -
    // open it first, the same as the Delivery Orders list. Radix's dropdown trigger opens on
    // pointerdown, not click - same reason `openFilters()` in the filters suite uses it.
    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), {
      ctrlKey: false,
      button: 0,
    });
    fireEvent.click(await screen.findByText('Upload sales orders'));

    expect(
      await screen.findByRole('heading', { name: /Upload sales orders/i }),
    ).toBeInTheDocument();
  });

  it('invalidates the sales-orders list and the reorder plan queries once the upload queues', async () => {
    const { invalidateSpy } = renderList();

    fireEvent.pointerDown(screen.getByRole('button', { name: /^Actions/i }), {
      ctrlKey: false,
      button: 0,
    });
    fireEvent.click(await screen.findByText('Upload sales orders'));
    await screen.findByRole('heading', { name: /Upload sales orders/i });

    fireEvent.change(screen.getByLabelText('Sales orders file'), {
      target: { files: [xlsx()] },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Test$/i }));
    await waitFor(() => expect(previewOutstandingImport).toHaveBeenCalledWith('sales-orders', expect.any(File)));

    fireEvent.click(await screen.findByRole('button', { name: /Confirm upload/i }));

    await waitFor(() => expect(applyOutstandingImport).toHaveBeenCalledWith('sales-orders', expect.any(File)));
    // The dialog itself owns the "queued" toast and the drawer notification - both are
    // pinned in OutstandingUploadDialog.test.tsx. What this list adds on top is invalidating
    // its own listing, plus the two reorder-plan queries the upload also feeds.
    await waitFor(() => expect(notifyImportQueued).toHaveBeenCalledTimes(1));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['scm', 'sales-orders'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['scm', 'reorder', 'today'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['scm', 'reorder', 'history'] });

    // The dialog closes itself on a successful queue.
    await waitFor(() =>
      expect(
        screen.queryByRole('heading', { name: /Upload sales orders/i }),
      ).toBeNull(),
    );
  });
});
