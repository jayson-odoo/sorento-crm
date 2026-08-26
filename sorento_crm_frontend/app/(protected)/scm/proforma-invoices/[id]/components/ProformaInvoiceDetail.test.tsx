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
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
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
  markAsRevision: vi.fn(),
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
  useMarkProformaInvoiceAsRevision: () => ({
    mutateAsync: writes.markAsRevision,
    isPending: false,
  }),
  // The convert dialog offers this supplier's open drafts to add to (F10).
  useDraftShipments: () => ({ data: [], isLoading: false }),
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
        supplier_qty: 10,
        supplier_unit_price: 100,
        placed_qty: 0,
        remaining_qty: 10,
        packing_lists: [],
        product_code: 'ITEM-1',
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
  writes.markAsRevision.mockReset();
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
          placed_qty: 0, remaining_qty: 5, packing_lists: [],
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

describe('F5b - revisions', () => {
  const revised = () =>
    detail({
      pi_number: 'PI-2026-001-R2',
      status: 'current',
      revision_no: 2,
      revision_count: 2,
      revision_of_pi_number: 'PI-2026-001',
      revisions: [
        {
          id: 'pi-0',
          pi_number: 'PI-2026-001',
          revision_no: 1,
          status: 'superseded',
          invoice_date: '2026-07-20',
          total_amount: 900,
          line_count: 1,
        },
        {
          id: 'pi-1',
          pi_number: 'PI-2026-001-R2',
          revision_no: 2,
          status: 'current',
          invoice_date: '2026-08-01',
          total_amount: 1000,
          line_count: 1,
        },
      ],
      diff: {
        compared_to_id: 'pi-0',
        compared_to_pi_number: 'PI-2026-001',
        price_changed_lines: 1,
        qty_changed_lines: 0,
        added_lines: 0,
        removed_lines: 0,
        changes: [
          {
            item_code: 'ITEM-1',
            occurrence: 1,
            description: 'Widget',
            status: 'changed' as const,
            qty_was: 10,
            qty_now: 10,
            qty_changed: false,
            unit_price_was: 90,
            unit_price_now: 100,
            unit_price_changed: true,
            amount_was: 900,
            amount_now: 1000,
          },
        ],
      },
    });

  it('says which revision this is, in the header and in the section (AC-E7)', () => {
    state.data = revised();
    renderDetail();

    // Once in the header badge, once in the Revisions section - both places a reader looks.
    expect(screen.getAllByText('Revision 2 of 2')).toHaveLength(2);
    expect(screen.getByText('Revision 1 - superseded')).toBeInTheDocument();
  });

  it('names how many lines the supplier repriced, and by what (AC-E8)', () => {
    state.data = revised();
    renderDetail();

    expect(screen.getByText('Price changed on 1 line')).toBeInTheDocument();
    expect(screen.getByText(/against PI-2026-001/)).toBeInTheDocument();
    // The old price appears only in the diff; the new one also sits in the lines grid.
    expect(screen.getByText('CNY 90.00')).toBeInTheDocument();
    expect(screen.getAllByText('CNY 100.00').length).toBeGreaterThanOrEqual(2);
  });

  it('renders the revisions section on an original too, with an empty state', () => {
    state.data = detail();
    renderDetail();

    expect(screen.getByText('Revisions')).toBeInTheDocument();
    expect(
      screen.getByText('This is the only version the supplier has sent.'),
    ).toBeInTheDocument();
  });

  it('offers no Edit and no Convert on a superseded revision (AC-E7, AC-E10)', () => {
    state.data = detail({ status: 'superseded' });
    renderDetail();

    expect(screen.getByText('Superseded')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^edit$/i })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /convert to draft shipment/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText('A superseded revision is read-only.')).toBeInTheDocument();
  });

  it('offers to link a mis-filed new PI to the one it revises (AC-E11)', () => {
    state.data = detail();
    renderDetail();

    expect(screen.getByRole('button', { name: /mark as revision of/i })).toBeInTheDocument();
  });

  it('does not offer to link one that is already a revision', () => {
    state.data = revised();
    renderDetail();

    expect(
      screen.queryByRole('button', { name: /mark as revision of/i }),
    ).not.toBeInTheDocument();
  });
});

describe('F10 - the invoice says which packing list it is in', () => {
  it('reads Not converted before anything is placed (AC-F8)', () => {
    state.data = detail();
    renderDetail();

    // Twice on purpose: the header field, and the lines grid's own column header - the
    // invoice-level answer and the per-line one are different questions (AC-F8).
    expect(screen.getAllByText('In packing list')).toHaveLength(2);
    expect(screen.getAllByText('Not converted').length).toBeGreaterThanOrEqual(1);
  });

  it('names the packing list, and what is left when it is split (Q9)', () => {
    state.data = detail({
      placement: 'split',
      placed_qty: 4,
      remaining_qty: 6,
      packing_lists: [
        {
          shipment_id: 'sh-1',
          shipment_number: 'FSCU8103365',
          shipment_status: 'draft',
          qty: 4,
          lines: 1,
        },
      ],
      lines: [
        {
          ...detail().lines[0],
          placed_qty: 4,
          remaining_qty: 6,
          packing_lists: [{ shipment_id: 'sh-1', shipment_number: 'FSCU8103365', qty: 4 }],
        },
      ],
    });
    renderDetail();

    expect(screen.getAllByRole('link', { name: /FSCU8103365/ }).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/Split - 6 still to place/)).toBeInTheDocument();
    expect(screen.getByText('6 left')).toBeInTheDocument();
  });

  it('offers "Convert the rest" while something is still to place', () => {
    state.data = detail({ placement: 'split', placed_qty: 4, remaining_qty: 6 });
    renderDetail();

    expect(screen.getByRole('button', { name: /convert the rest/i })).toBeInTheDocument();
  });

  it('offers no convert at all once every line is placed', () => {
    state.data = detail({ placement: 'converted', placed_qty: 10, remaining_qty: 0 });
    renderDetail();

    expect(screen.queryByRole('button', { name: /convert/i })).not.toBeInTheDocument();
  });
});
