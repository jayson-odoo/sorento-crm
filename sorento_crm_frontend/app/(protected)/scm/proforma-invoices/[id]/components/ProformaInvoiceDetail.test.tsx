/**
 * The proforma-invoice detail page, after the conformance pass.
 *
 * What this pins:
 *
 * - A record header that reads like the purchase order's: the number and its badges on the
 *   left, and on the right the pager, ONE primary CTA, a gear menu holding every secondary
 *   action, and Back. Read-only provenance is a meta line under the title, never a tab body.
 * - Four tabs in a fixed order, the SAME set in view and in edit: editing swaps a value for
 *   an input where the value was.
 * - Editing is a LOCAL DRAFT. A removed line is struck through with an Undo; an added line is
 *   a blank row; nothing at all is written until Save, and Save is ONE call carrying the
 *   number, the container size and the whole line array.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
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

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/proforma-invoices/pi-1',
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));

// The WHOLE surface the components under test call. `ConfirmDeleteDialog` reports through
// `toast.custom`, and a mock without it threw inside react-query's own error path - which
// surfaced as an unhandled rejection that failed no test and hid any real one behind it.
vi.mock('sonner', () => ({
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
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProducts: async () => ({ data: [], pagination: { total: 0 } }),
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
  deleteInvoice: vi.fn(),
  markAsRevision: vi.fn(),
};

vi.mock('../../../hooks/useProformaInvoices', () => ({
  useProformaInvoice: () => state,
  // The header's pager pulls the neighbour list through this hook - one row is not enough to
  // show a pager (RecordNavigation's `items.length < 2` guard), so it stays out of the way.
  useProformaInvoices: () => ({ data: undefined, isLoading: false }),
  useConvertProformaInvoicesToDraftShipment: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
  useSaveProformaInvoice: () => ({ mutateAsync: writes.save, isPending: false }),
  useDeleteProformaInvoice: () => ({ mutateAsync: writes.deleteInvoice, isPending: false }),
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

/** Radix opens a dropdown on POINTERDOWN, not on click - a plain click is a silent no-op. */
function openActions() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /more actions/i }), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
}

/**
 * `mouseDown`, not `click`: Radix's tab trigger selects on mouse-down, and a plain `click`
 * event is a silent no-op. Exact names, because `/lines/i` matches BOTH "Lines" and
 * "Packing lists".
 */
function openTab(name: 'General' | 'Lines' | 'Revisions' | 'Packing lists') {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

/** Open the gear menu and press Edit, which is where editing starts from now. */
function beginEdit() {
  openActions();
  fireEvent.click(screen.getByRole('menuitem', { name: /^edit$/i }));
}

function lastSavePayload() {
  return writes.save.mock.calls[writes.save.mock.calls.length - 1][0] as {
    pi_number?: string;
    container_size_id?: string | null;
    lines?: Array<Record<string, unknown>>;
  };
}

beforeEach(() => {
  state.data = undefined;
  state.isLoading = false;
  state.isError = false;
  push.mockReset();
  writes.save.mockReset().mockResolvedValue(undefined);
  writes.deleteInvoice.mockReset().mockResolvedValue(undefined);
  writes.forgetMatch.mockReset().mockResolvedValue(undefined);
  writes.markAsRevision.mockReset().mockResolvedValue(undefined);
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
});

describe('ProformaInvoiceDetail - the record header', () => {
  it('names the invoice, its currency and where its goods are', () => {
    state.data = detail();
    renderDetail();

    // Twice on purpose: the header title, and the General tab's first field - the number is
    // the first thing the edit view swaps for an input, so it has to be there to swap.
    expect(screen.getAllByText('PI-2026-001')).toHaveLength(2);
    // Same story for the currency: the header badge, and the General tab's Currency field.
    expect(screen.getAllByText('CNY')).toHaveLength(2);
    expect(screen.getByText('Not converted')).toBeInTheDocument();
  });

  it('puts the read-only provenance in a meta line, never inside a tab', () => {
    state.data = detail({ adjusted_by: 'Ms Tee', adjusted_at: '2026-08-02T02:00:00' });
    renderDetail();

    expect(screen.getByText(/proforma\.xlsx/)).toBeInTheDocument();
    expect(screen.getByText(/Uploaded by Ms Tee/)).toBeInTheDocument();
    expect(screen.getByText(/Adjusted by Ms Tee/)).toBeInTheDocument();
  });

  it('offers Convert as the ONE primary action, with everything else in the gear menu', () => {
    state.data = detail();
    renderDetail();

    expect(
      screen.getByRole('button', { name: /convert to packing list/i }),
    ).toBeInTheDocument();
    // Not loose buttons any more: Edit, Export and Delete are behind the gear.
    expect(screen.queryByRole('button', { name: /^edit$/i })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /export adjusted pi/i }),
    ).not.toBeInTheDocument();
  });

  it('lists every secondary action in the gear menu, in one place', () => {
    state.data = detail();
    renderDetail();

    openActions();

    expect(screen.getByRole('menuitem', { name: /^edit$/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /export adjusted pi/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /mark as revision of/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /delete invoice/i })).toBeInTheDocument();
  });

  it('keeps Back to the list as the last thing on the row', () => {
    state.data = detail();
    renderDetail();

    expect(screen.getByRole('link', { name: /back to proforma invoices/i })).toBeInTheDocument();
  });

  it('offers "Convert the rest" while something is still to place', () => {
    state.data = detail({ placement: 'split', placed_qty: 4, remaining_qty: 6 });
    renderDetail();

    expect(screen.getByRole('button', { name: /convert the rest/i })).toBeInTheDocument();
  });

  it('offers no convert at all once every line is placed', () => {
    state.data = detail({
      placement: 'converted',
      placed_qty: 10,
      remaining_qty: 0,
      packing_lists: [
        {
          shipment_id: 'sh-1',
          shipment_number: 'FSCU8103365',
          shipment_status: 'draft',
          qty: 10,
          lines: 1,
        },
      ],
    });
    renderDetail();

    expect(screen.queryByRole('button', { name: /convert/i })).not.toBeInTheDocument();
  });
});

describe('ProformaInvoiceDetail - deleting the invoice', () => {
  it('asks first, and routes back to the list once it is done', async () => {
    state.data = detail();
    renderDetail();

    openActions();
    fireEvent.click(screen.getByRole('menuitem', { name: /delete invoice/i }));

    expect(screen.getByText(/deletes proforma invoice PI-2026-001/)).toBeInTheDocument();
    expect(writes.deleteInvoice).not.toHaveBeenCalled();

    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: /^delete$/i }),
    );

    await waitFor(() => expect(writes.deleteInvoice).toHaveBeenCalledWith('pi-1'));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/scm/proforma-invoices'));
  });

  it('refuses on an invoice already in a packing list, and says why', () => {
    state.data = detail({
      converted_shipments: [{ shipment_id: 'sh-1', shipment_number: 'FSCU8103365' }],
    });
    renderDetail();

    openActions();
    const item = screen.getByRole('menuitem', { name: /delete invoice/i });
    expect(item).toHaveAttribute('data-disabled');
    expect(item).toHaveAttribute('title', expect.stringContaining('FSCU8103365'));
  });
});

describe('ProformaInvoiceDetail - the tabs', () => {
  it('renders four tabs, in a fixed order', () => {
    state.data = detail();
    renderDetail();

    const names = screen.getAllByRole('tab').map((t) => t.textContent);
    expect(names).toEqual(['General', 'Lines', 'Revisions', 'Packing lists']);
  });

  it('names each card of the General tab as its own region', () => {
    state.data = detail();
    renderDetail();

    expect(screen.getByRole('region', { name: 'Invoice' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Supplier' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Volume' })).toBeInTheDocument();
  });

  it('states the volume against the named container and how far over it is (AC-D2)', () => {
    state.data = detail();
    renderDetail();

    expect(screen.getByText('69.36 cbm')).toBeInTheDocument();
    expect(screen.getByText(/of 65 \(40HQ\) - 107% full/)).toBeInTheDocument();
    expect(screen.getByText('over by 4.36 cbm')).toBeInTheDocument();
  });

  it('counts the unmeasured lines rather than reading them as an empty container', () => {
    state.data = detail({
      total_cbm: null,
      unmeasured_lines: 2,
      fill_pct: null,
      over_by_cbm: null,
    });
    renderDetail();

    expect(screen.getByText('No volume on this invoice')).toBeInTheDocument();
    expect(screen.getByText('2 unmeasured lines')).toBeInTheDocument();
  });

  it('renders the lines with the weights the supplier stated', () => {
    state.data = detail();
    renderDetail();
    openTab('Lines');

    // ITEM-1 twice: the supplier's own code, and the product it binds to (the same code
    // here, which is what an exact match looks like).
    expect(screen.getAllByText('ITEM-1')).toHaveLength(2);
    expect(screen.getByText('Widget')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
  });

  it('states plainly when the invoice has no lines, rather than an empty table', () => {
    state.data = detail({ lines: [], line_count: 0 });
    renderDetail();
    openTab('Lines');

    expect(screen.getByText('This proforma invoice has no lines.')).toBeInTheDocument();
  });

  it('renders the Revisions tab on an original too, with an empty state', () => {
    state.data = detail();
    renderDetail();
    openTab('Revisions');

    expect(
      screen.getByText('This is the only version the supplier has sent.'),
    ).toBeInTheDocument();
  });

  it('renders the Packing lists tab with an empty state and the Convert CTA', () => {
    state.data = detail();
    renderDetail();
    openTab('Packing lists');

    expect(
      screen.getByText('Nothing from this invoice is in a packing list yet.'),
    ).toBeInTheDocument();
    // The next step from the empty state is the SAME action as the header's primary.
    expect(screen.getAllByRole('button', { name: /convert to packing list/i }).length).toBe(2);
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
    openTab('Packing lists');

    expect(screen.getByRole('link', { name: /FSCU8103365/ })).toHaveAttribute(
      'href',
      '/procurement-management/packing-lists/sh-1',
    );
    expect(screen.getByText('6 left')).toBeInTheDocument();
  });

  it('names a line nothing could carry, instead of calling it placed', () => {
    state.data = detail({
      lines: [
        {
          ...detail().lines[0],
          matched: false,
          product_code: null,
          remaining_qty: 0,
          unmatched_reason: "No catalogue product matches this line's item code.",
        },
      ],
    });
    renderDetail();
    openTab('Packing lists');

    expect(
      screen.getByText(/No catalogue product matches this line's item code/),
    ).toBeInTheDocument();
  });
});

describe('ProformaInvoiceDetail - editing is a draft until Save', () => {
  it('swaps values for inputs in place, leaving the tabs and their order alone', () => {
    state.data = detail();
    renderDetail();

    expect(screen.queryByLabelText('PI number')).not.toBeInTheDocument();
    beginEdit();

    expect(screen.getByLabelText('PI number')).toHaveValue('PI-2026-001');
    expect(screen.getByLabelText('Container size')).toBeInTheDocument();
    // Same tabs, same order, mid-edit.
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'General',
      'Lines',
      'Revisions',
      'Packing lists',
    ]);
  });

  it('states that nothing is written until Save, and offers only Cancel and Save', () => {
    state.data = detail();
    renderDetail();
    beginEdit();

    expect(screen.getByText('Nothing is written until you press Save.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^save$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^cancel$/i })).toBeInTheDocument();
    // Nav and the way out act on the STORED invoice, so they are not offered over a screen
    // full of unsaved changes.
    expect(
      screen.queryByRole('link', { name: /back to proforma invoices/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /more actions/i })).not.toBeInTheDocument();
  });

  it('writes nothing while the quantity is being typed', () => {
    state.data = detail();
    renderDetail();
    beginEdit();
    openTab('Lines');

    fireEvent.change(screen.getByLabelText('Quantity for ITEM-1'), { target: { value: '8' } });

    expect(writes.save).not.toHaveBeenCalled();
  });

  it('moves the fill bar live as the quantity is typed, before any save (AC-E3)', () => {
    state.data = detail();
    renderDetail();
    beginEdit();
    openTab('Lines');
    fireEvent.change(screen.getByLabelText('Quantity for ITEM-1'), { target: { value: '20' } });
    openTab('General');

    // 20 x 0.17 cbm, computed from the per-unit figure the supplier stated.
    expect(screen.getByText('3.4 cbm')).toBeInTheDocument();
    expect(screen.queryByText(/over by/)).not.toBeInTheDocument();
  });

  it('sends the WHOLE line array in one call on Save', async () => {
    state.data = detail();
    renderDetail();
    beginEdit();
    openTab('Lines');
    fireEvent.change(screen.getByLabelText('Quantity for ITEM-1'), { target: { value: '8' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(writes.save).toHaveBeenCalledTimes(1));
    const payload = lastSavePayload();
    expect(payload.pi_number).toBe('PI-2026-001');
    expect(payload.lines).toHaveLength(1);
    expect(payload.lines?.[0]).toMatchObject({
      id: 'line-1',
      item_code: 'ITEM-1',
      qty: 8,
      uom: 'PCS',
      cartons: 10,
      cbm_per_unit: 0.17,
      unit_price: 100,
      net_weight: 40,
      gross_weight: 50,
    });
  });

  it('carries a corrected PI number on the same save', async () => {
    state.data = detail();
    renderDetail();
    beginEdit();
    fireEvent.change(screen.getByLabelText('PI number'), { target: { value: 'PI-REAL-9 ' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(writes.save).toHaveBeenCalledTimes(1));
    expect(lastSavePayload().pi_number).toBe('PI-REAL-9');
  });

  it('refuses to save a blank PI number, and writes nothing', async () => {
    state.data = detail();
    renderDetail();
    beginEdit();
    fireEvent.change(screen.getByLabelText('PI number'), { target: { value: '  ' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(writes.save).not.toHaveBeenCalled());
    expect(screen.getByLabelText('PI number')).toBeInTheDocument();
  });

  it('marks a removed line struck through, with an Undo, and writes nothing yet', () => {
    state.data = detail();
    renderDetail();
    beginEdit();
    openTab('Lines');

    fireEvent.click(screen.getByRole('button', { name: /^remove$/i }));

    expect(writes.save).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /^undo$/i })).toBeInTheDocument();
    // Still on screen - it is marked, not gone.
    expect(screen.getByLabelText('Item code for line 1')).toBeInTheDocument();
  });

  it('puts a removed line back on Undo', () => {
    state.data = detail();
    renderDetail();
    beginEdit();
    openTab('Lines');

    fireEvent.click(screen.getByRole('button', { name: /^remove$/i }));
    fireEvent.click(screen.getByRole('button', { name: /^undo$/i }));

    expect(screen.getByRole('button', { name: /^remove$/i })).toBeInTheDocument();
  });

  it('leaves a removed line OUT of the array on Save', async () => {
    state.data = detail();
    renderDetail();
    beginEdit();
    openTab('Lines');

    fireEvent.click(screen.getByRole('button', { name: /^remove$/i }));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(writes.save).toHaveBeenCalledTimes(1));
    expect(lastSavePayload().lines).toEqual([]);
  });

  it('adds a blank draft row from Add line, and sends it with no id', async () => {
    state.data = detail();
    renderDetail();
    beginEdit();
    openTab('Lines');

    fireEvent.click(screen.getByRole('button', { name: /add line/i }));
    fireEvent.change(screen.getByLabelText('Item code for line 2'), {
      target: { value: 'HAND-1' },
    });
    fireEvent.change(screen.getByLabelText('Quantity for HAND-1'), { target: { value: '4' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(writes.save).toHaveBeenCalledTimes(1));
    const lines = lastSavePayload().lines ?? [];
    expect(lines).toHaveLength(2);
    expect(lines[1]).toMatchObject({ item_code: 'HAND-1', qty: 4 });
    expect(lines[1]).not.toHaveProperty('id');
  });

  it('refuses an added line with no quantity, and writes nothing', async () => {
    state.data = detail();
    renderDetail();
    beginEdit();
    openTab('Lines');

    fireEvent.click(screen.getByRole('button', { name: /add line/i }));
    fireEvent.change(screen.getByLabelText('Item code for line 2'), {
      target: { value: 'HAND-1' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(writes.save).not.toHaveBeenCalled());
  });

  it('offers no Add line while only reading', () => {
    state.data = detail();
    renderDetail();
    openTab('Lines');

    expect(screen.queryByRole('button', { name: /add line/i })).not.toBeInTheDocument();
  });

  it('discards the whole draft on Cancel', () => {
    state.data = detail();
    renderDetail();
    beginEdit();
    fireEvent.change(screen.getByLabelText('PI number'), { target: { value: 'PI-WRONG' } });
    openTab('Lines');
    fireEvent.change(screen.getByLabelText('Quantity for ITEM-1'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

    expect(writes.save).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('Quantity for ITEM-1')).not.toBeInTheDocument();
    openTab('General');
    expect(screen.getAllByText('PI-2026-001')).toHaveLength(2);
    expect(screen.queryByText('PI-WRONG')).not.toBeInTheDocument();
  });

  it('offers no Edit at all on an invoice already in a packing list', () => {
    state.data = detail({
      converted_shipments: [{ shipment_id: 'sh-1', shipment_number: 'FSCU8103365' }],
    });
    renderDetail();

    openActions();
    expect(screen.queryByRole('menuitem', { name: /^edit$/i })).not.toBeInTheDocument();
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

  it('says which revision this is, in the header and in the tab (AC-E7)', () => {
    state.data = revised();
    renderDetail();

    expect(screen.getByText('Revision 2 of 2')).toBeInTheDocument();
    openTab('Revisions');
    expect(screen.getAllByText('Revision 2 of 2')).toHaveLength(2);
    expect(screen.getByText('Revision 1 - superseded')).toBeInTheDocument();
  });

  it('names how many lines the supplier repriced, and by what (AC-E8)', () => {
    state.data = revised();
    renderDetail();
    openTab('Revisions');

    expect(screen.getByText('Price changed on 1 line')).toBeInTheDocument();
    expect(screen.getByText(/against PI-2026-001/)).toBeInTheDocument();
    expect(screen.getByText('CNY 90.00')).toBeInTheDocument();
  });

  it('offers no Edit and no Convert on a superseded revision (AC-E7, AC-E10)', () => {
    state.data = detail({ status: 'superseded' });
    renderDetail();

    expect(screen.getByText('Superseded')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /convert to packing list/i }),
    ).not.toBeInTheDocument();
    openActions();
    expect(screen.queryByRole('menuitem', { name: /^edit$/i })).not.toBeInTheDocument();
  });

  it('offers to link a mis-filed new PI to the one it revises (AC-E11)', () => {
    state.data = detail();
    renderDetail();

    openActions();
    expect(screen.getByRole('menuitem', { name: /mark as revision of/i })).toBeInTheDocument();
  });

  it('does not offer to link one that is already a revision', () => {
    state.data = revised();
    renderDetail();

    openActions();
    expect(
      screen.queryByRole('menuitem', { name: /mark as revision of/i }),
    ).not.toBeInTheDocument();
  });
});

describe('F11 - answering a supplier code by hand', () => {
  it('offers Match to product on a line that binds to nothing', () => {
    state.data = detail({
      lines: [
        {
          ...detail().lines[0],
          matched: false,
          product_code: null,
          unmatched_reason: "No catalogue product matches this line's item code.",
        },
      ],
    });
    renderDetail();
    openTab('Lines');

    expect(screen.getByRole('button', { name: /match to product/i })).toBeInTheDocument();
  });

  it('marks a bind the ladder worked out, and names the rung in the title', () => {
    state.data = detail({
      lines: [
        { ...detail().lines[0], match_source: 'auto', matched_by: 'token_set', match_id: 'a-1' },
      ],
    });
    renderDetail();
    openTab('Lines');

    expect(screen.getByText('auto')).toHaveAttribute('title', 'Matched by token_set');
    expect(screen.getByRole('button', { name: /^change$/i })).toBeInTheDocument();
  });

  it('says nothing about a code that matched exactly', () => {
    state.data = detail();
    renderDetail();
    openTab('Lines');

    expect(screen.queryByText('auto')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^change$/i })).not.toBeInTheDocument();
  });

  it('asks before forgetting a recorded match, and quotes both codes', () => {
    state.data = detail({
      lines: [
        {
          ...detail().lines[0],
          item_code: 'SRTWC8357-RL-300',
          product_code: 'SRTWC8357-300-RL',
          match_source: 'auto',
          matched_by: 'token_set',
          match_id: 'alias-1',
        },
      ],
    });
    renderDetail();
    openTab('Lines');

    fireEvent.click(screen.getByRole('button', { name: /^forget$/i }));

    expect(
      screen.getByText(
        /Forget that SRTWC8357-RL-300 means SRTWC8357-300-RL\? Next upload will match it again by the ladder\./,
      ),
    ).toBeInTheDocument();
    expect(writes.forgetMatch).not.toHaveBeenCalled();
  });

  it('forgets the recorded match on confirm, named by the ruling and never by the line', async () => {
    state.data = detail({
      lines: [
        {
          ...detail().lines[0],
          match_source: 'auto',
          matched_by: 'token_set',
          match_id: 'alias-1',
        },
      ],
    });
    renderDetail();
    openTab('Lines');

    fireEvent.click(screen.getByRole('button', { name: /^forget$/i }));
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: /^forget$/i }),
    );

    await waitFor(() => expect(writes.forgetMatch).toHaveBeenCalledWith('alias-1'));
  });
});
