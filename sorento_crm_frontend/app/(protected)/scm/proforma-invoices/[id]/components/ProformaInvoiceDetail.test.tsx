/**
 * The proforma-invoice detail page: meta strip (Created/Uploaded-style fields never inside a
 * tab body) plus the lines grid, both always rendered per the CRUD standard - even when the
 * lines list is empty, the section stays and states so explicitly.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/proforma-invoices/pi-1',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const state = {
  data: undefined as ProformaInvoiceDetailData | undefined,
  isLoading: false,
  isError: false,
};

/** The three adjust writes, so a test can assert what the page ASKED the backend for. */
const writes = {
  updateLine: vi.fn(),
  removeLine: vi.fn(),
  updateInvoice: vi.fn(),
};

vi.mock('../../../hooks/useProformaInvoices', () => ({
  useProformaInvoice: () => state,
  // The header's ProformaInvoiceNavigation (S9) pulls the neighbour list via this hook - one
  // row is not enough to show a pager (see RecordNavigation's `items.length < 2` guard), so
  // it stays hidden and out of these tests' way without a dedicated navigation test.
  useProformaInvoices: () => ({ data: undefined, isLoading: false }),
  useConvertProformaInvoicesToDraftShipment: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
  useUpdateProformaInvoiceLine: () => ({ mutateAsync: writes.updateLine, isPending: false }),
  useDeleteProformaInvoiceLine: () => ({ mutateAsync: writes.removeLine, isPending: false }),
  useUpdateProformaInvoice: () => ({ mutateAsync: writes.updateInvoice, isPending: false }),
}));

vi.mock('../../../hooks/useFulfilment', () => ({
  useContainerSizes: () => ({
    data: [
      { id: 'size-40hq', code: '40HQ', label: '40ft high cube', cbm: 65, is_default: true },
      { id: 'size-20gp', code: '20GP', label: '20ft standard', cbm: 28, is_default: false },
    ],
    isLoading: false,
  }),
}));

import { ProformaInvoiceDetail } from './ProformaInvoiceDetail';

function detail(over: Partial<ProformaInvoiceDetailData> = {}): ProformaInvoiceDetailData {
  return {
    id: 'pi-1',
    supplier_id: 'sup-1',
    supplier_code: 'KAILU',
    supplier_name: 'Kailu Hardware Factory',
    pi_number: 'PI-2026-001',
    invoice_date: '2026-08-01',
    currency: 'CNY',
    container_no: 'TEMU1234567',
    bl_no: 'BL-991',
    total_amount: 1000,
    line_count: 1,
    source_ref: 'proforma.xlsx',
    block_index: 0,
    uploaded_by: 'Ms Tee',
    created_at: '2026-08-01T02:00:00',
    updated_at: '2026-08-01T02:00:00',
    container_size_id: null,
    container_size_code: '40HQ',
    container_cbm: 65,
    total_cbm: 69.36,
    unmeasured_lines: 0,
    fill_pct: 106.71,
    over_by_cbm: 4.36,
    status: 'current',
    revision_no: 1,
    revision_count: 1,
    adjusted_by: null,
    adjusted_at: null,
    is_adjusted: false,
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
        supplier_qty: 10,
        supplier_unit_price: 100,
        product_code: 'ITEM-1',
        matched: true,
        shipment_id: null,
        shipment_number: null,
        unmatched_reason: null,
      },
    ],
    converted_shipments: [],
    ...over,
  };
}

function renderDetail() {
  // ConfirmDeleteDialog (the line-removal confirmation) runs its own mutation, so the page
  // needs a client even though every data hook here is mocked.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ProformaInvoiceDetail id="pi-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  state.data = undefined;
  state.isLoading = false;
  state.isError = false;
  writes.updateLine.mockReset();
  writes.removeLine.mockReset();
  writes.updateInvoice.mockReset();
});

describe('ProformaInvoiceDetail - loading / error / data states', () => {
  it('shows a loading skeleton while the detail is fetched', () => {
    state.isLoading = true;
    renderDetail();

    expect(screen.queryByText('PI-2026-001')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to proforma invoices/i })).toBeInTheDocument();
  });

  it('says the invoice was not found rather than rendering a blank page', () => {
    state.isError = true;
    renderDetail();

    expect(screen.getByText('Proforma invoice not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to proforma invoices/i })).toBeInTheDocument();
  });

  it('renders the meta strip fields, none of them inside a tab', () => {
    state.data = detail();
    renderDetail();

    expect(screen.getByText('PI-2026-001')).toBeInTheDocument();
    expect(screen.getByText(/Kailu Hardware Factory/)).toBeInTheDocument();
    expect(screen.getByText('(KAILU)')).toBeInTheDocument();
    expect(screen.getByText('TEMU1234567')).toBeInTheDocument();
    expect(screen.getByText('BL-991')).toBeInTheDocument();
    expect(screen.getByText('Ms Tee')).toBeInTheDocument();
    expect(screen.getByText('proforma.xlsx')).toBeInTheDocument();
  });

  it('renders the invoice lines with matched/unmatched product status', () => {
    state.data = detail({
      lines: [
        { ...detail().lines[0] },
        {
          id: 'line-2', line_no: 2, row_number: 3, item_code: 'ZZ-NOPE',
          description: 'Unknown part', qty: 5, uom: 'PCS', unit_price: 20, amount: 100,
          po_ref: null, remark: null, cartons: null, cbm_per_unit: null, cbm_total: null,
          supplier_qty: 5, supplier_unit_price: 20,
          product_code: null, matched: false,
          shipment_id: null, shipment_number: null, unmatched_reason: null,
        },
      ],
    });
    renderDetail();

    // ITEM-1 appears twice - the line's own item code column, and the matched product code
    // subtext under the Matched badge (both correctly the same code here).
    expect(screen.getAllByText('ITEM-1').length).toBeGreaterThanOrEqual(2);
    // "Matched" also names the column header, so the badge is one of at least two matches.
    expect(screen.getAllByText('Matched').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('ZZ-NOPE')).toBeInTheDocument();
    expect(screen.getByText('Not in catalogue')).toBeInTheDocument();
  });

  it('states plainly when the invoice has no lines, rather than an empty table', () => {
    state.data = detail({ lines: [], line_count: 0 });
    renderDetail();

    expect(screen.getByText('This proforma invoice has no lines.')).toBeInTheDocument();
  });
});

describe('F5 - volume, and adjusting the invoice to fit the container', () => {
  it('states the volume against the named container and how far over it is (AC-D2)', () => {
    state.data = detail();
    renderDetail();

    expect(screen.getByText('69.36 cbm')).toBeInTheDocument();
    expect(screen.getByText(/of 65 \(40HQ\) - 107% full/)).toBeInTheDocument();
    expect(screen.getByText('over by 4.36 cbm')).toBeInTheDocument();
  });

  it('counts the unmeasured lines rather than reading them as an empty container', () => {
    state.data = detail({ total_cbm: null, unmeasured_lines: 2, fill_pct: null, over_by_cbm: null });
    renderDetail();

    expect(screen.getByText('No volume on this invoice')).toBeInTheDocument();
    expect(screen.getByText('2 unmeasured lines')).toBeInTheDocument();
  });

  it("shows the supplier's own quantity beside ours once the two differ (AC-E1)", () => {
    state.data = detail({
      lines: [{ ...detail().lines[0], qty: 8, supplier_qty: 10 }],
    });
    renderDetail();

    expect(screen.getByText('Supplier: 10')).toBeInTheDocument();
  });

  it('says nothing about the supplier quantity while the two agree', () => {
    state.data = detail();
    renderDetail();

    expect(screen.queryByText(/^Supplier: /)).not.toBeInTheDocument();
  });

  it('swaps the quantity for an input in place, leaving the layout alone (AC-E1)', async () => {
    state.data = detail();
    renderDetail();

    expect(screen.queryByLabelText('Quantity for ITEM-1')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

    expect(screen.getByLabelText('Quantity for ITEM-1')).toBeInTheDocument();
    // Every other field stays exactly where it was - same fields, same order.
    expect(screen.getByText('TEMU1234567')).toBeInTheDocument();
    expect(screen.getByText('Container size')).toBeInTheDocument();
  });

  it('sends only the lines whose quantity actually changed', async () => {
    state.data = detail();
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    fireEvent.change(screen.getByLabelText('Quantity for ITEM-1'), {
      target: { value: '8' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(writes.updateLine).toHaveBeenCalledTimes(1));
    expect(writes.updateLine).toHaveBeenCalledWith({ lineId: 'line-1', qty: 8 });
    expect(writes.updateInvoice).not.toHaveBeenCalled();
  });

  it('writes nothing at all when the operator changes nothing', async () => {
    state.data = detail();
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() =>
      expect(screen.queryByLabelText('Quantity for ITEM-1')).not.toBeInTheDocument(),
    );
    expect(writes.updateLine).not.toHaveBeenCalled();
    expect(writes.updateInvoice).not.toHaveBeenCalled();
  });

  it('moves the fill bar live as the quantity is typed, before any save (AC-E3)', async () => {
    state.data = detail();
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    fireEvent.change(screen.getByLabelText('Quantity for ITEM-1'), {
      target: { value: '20' },
    });

    // 20 x 0.17 cbm, computed from the per-unit figure the supplier stated.
    expect(screen.getByText('3.4 cbm')).toBeInTheDocument();
    expect(screen.queryByText(/over by/)).not.toBeInTheDocument();
  });

  it('cancels back to the supplier figures without writing anything', async () => {
    state.data = detail();
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    fireEvent.change(screen.getByLabelText('Quantity for ITEM-1'), {
      target: { value: '1' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

    expect(writes.updateLine).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('Quantity for ITEM-1')).not.toBeInTheDocument();
    expect(screen.getByText('69.36 cbm')).toBeInTheDocument();
  });

  it('asks before removing a line, and only removes once confirmed', async () => {
    state.data = detail();
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    fireEvent.click(screen.getByRole('button', { name: /remove/i }));

    expect(screen.getByText(/This removes ITEM-1 from PI-2026-001/)).toBeInTheDocument();
    expect(writes.removeLine).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    await waitFor(() => expect(writes.removeLine).toHaveBeenCalledWith('line-1'));
  });

  it('offers no Edit on an invoice already in a packing list', () => {
    state.data = detail({
      converted_shipments: [{ shipment_id: 'sh-1', shipment_number: 'FSCU8103365' }],
    });
    renderDetail();

    expect(screen.queryByRole('button', { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Already in a packing list/)).toBeInTheDocument();
  });
});
