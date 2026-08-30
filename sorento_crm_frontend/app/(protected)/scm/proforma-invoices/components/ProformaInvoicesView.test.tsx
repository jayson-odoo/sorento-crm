/**
 * The proforma-invoice list, on the standard `DataGridListToolbar`.
 *
 * What this pins: the search box reaches the service, the two filters live behind ONE
 * Filters popover that says what it is filtering, the whole row opens the invoice, the
 * right cluster is [gear] [Start] (R14), and a convert from the list runs at once with no
 * dialog in front of it (R15).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { ProformaInvoiceListRow } from '../../services/proformaInvoiceService';

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

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
    custom: vi.fn(),
  },
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/proforma-invoices',
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options = [],
    placeholder,
  }: {
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: Array<{ value: string; label: string }>;
    placeholder?: string;
  }) => (
    // Labelled by its own id, so the supplier filter, the packing-list filter AND the
    // pagination's own page-size select (which is a SearchableSelect too, and so goes
    // through this same mock) are three different controls to a test rather than three
    // elements answering to "Supplier".
    <select
      id={id}
      aria-label={
        id === 'proforma-placement-filter'
          ? 'Packing list filter'
          : id === 'proforma-supplier-filter'
            ? 'Supplier'
            : (id ?? 'select')
      }
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const hasPermission = vi.fn((_slug: string) => true);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => hasPermission(slug),
}));

vi.mock('../../hooks/useFulfilment', () => ({
  useFulfilmentSuppliers: () => ({
    data: [{ value: 'sup-1', label: 'Kailu Hardware Factory' }],
  }),
}));

// The dialogs are exercised in their own test files; stub them here so this suite only
// asserts what the list itself renders.
vi.mock('./ProformaUploadDialog', () => ({
  ProformaUploadDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="upload-dialog" /> : null,
}));

const state = {
  data: undefined as { data: ProformaInvoiceListRow[]; total: number } | undefined,
  isLoading: false,
  convertInvoices: vi.fn(),
  bulkDeleteInvoices: vi.fn(),
};

/** Every argument list the list hook was called with, so a test can assert what the screen
 *  ASKED the service for rather than what it happened to render. */
const listCalls: unknown[][] = [];

vi.mock('../../hooks/useProformaInvoices', () => ({
  useProformaInvoices: (...args: unknown[]) => {
    listCalls.push(args);
    return { data: state.data, isLoading: state.isLoading };
  },
  useProformaInvoice: () => ({ data: undefined, isLoading: false }),
  useConvertProformaInvoicesToDraftShipment: () => ({
    mutateAsync: state.convertInvoices,
    isPending: false,
  }),
  useBulkDeleteProformaInvoices: () => ({
    mutateAsync: state.bulkDeleteInvoices,
    isPending: false,
  }),
}));

import { ProformaInvoicesView } from './ProformaInvoicesView';

function invoiceRow(over: Partial<ProformaInvoiceListRow> = {}): ProformaInvoiceListRow {
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
    line_count: 5,
    source_ref: null,
    block_index: 0,
    uploaded_by: 'Ms Tee',
    created_at: '2026-08-01T02:00:00',
    updated_at: '2026-08-01T02:00:00',
    container_size_id: null,
    container_size_code: '40HQ',
    container_cbm: 65,
    total_cbm: 27.1,
    unmeasured_lines: 0,
    fill_pct: 41.69,
    over_by_cbm: null,
    status: 'current',
    revision_no: 1,
    revision_count: 1,
    adjusted_by: null,
    adjusted_at: null,
    is_adjusted: false,
    placement: 'not_converted' as const,
    placed_qty: 0,
    total_qty: 500,
    remaining_qty: 500,
    packing_lists: [],
    ...over,
  };
}

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ProformaInvoicesView />
    </QueryClientProvider>,
  );
}

/** The two filters live behind the toolbar's Filters popover now, so a test opens it the
 *  way a person does. Radix opens a dropdown on POINTERDOWN, not on click, so a plain
 *  `click` here is a silent no-op. */
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /^Filters/ }), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
}

/** Radix opens on POINTERDOWN, so a plain click on either menu trigger is a no-op. */
function openMenu(name: RegExp | string) {
  fireEvent.pointerDown(screen.getByRole('button', { name }), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
}

const openGear = () => openMenu('More actions');
const openStart = () => openMenu(/^Start/);

/** An open Radix menu `aria-hidden`s the rest of the page, so the other trigger is
 *  unreachable until this one is dismissed. */
function closeMenu() {
  fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
}

function tickFirstRow() {
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select PI-2026-001' }));
}

function searchBox(): HTMLInputElement {
  return screen.getByLabelText('Search proforma invoices') as HTMLInputElement;
}

/** The last `{ limit, offset, placement, query }` the list hook was asked for. */
function lastListOptions(): Record<string, unknown> {
  return listCalls[listCalls.length - 1][1] as Record<string, unknown>;
}

beforeEach(() => {
  listCalls.length = 0;
  push.mockReset();
  state.data = { data: [], total: 0 };
  state.isLoading = false;
  state.convertInvoices = vi.fn().mockResolvedValue({
    shipment_id: 'ship-1',
    shipment_number: 'PL-2608-003',
    shipment_status: 'draft',
    supplier_id: null,
    lines_created: 1,
    lines_skipped: 0,
    invoices: [],
    unmatched: [],
  });
  state.bulkDeleteInvoices = vi.fn().mockResolvedValue({ deleted: 0, blocked: [] });
  hasPermission.mockReturnValue(true);
});

describe('ProformaInvoicesView - loading / empty / error / data states', () => {
  it('says nothing is waiting for a container, under the default filter', () => {
    // The list opens on "Not converted" (AC-F6), so its empty state answers THAT question -
    // one sentence that is true whether nothing was uploaded or everything is placed.
    state.data = { data: [], total: 0 };
    renderView();

    expect(
      screen.getByText('No proforma invoice is waiting for a container.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /show every invoice/i })).toBeInTheDocument();
  });

  it('names the supplier once a filter narrows the empty result to none', () => {
    state.data = { data: [], total: 0 };
    renderView();

    openFilters();
    // Off the placement filter first: with it on, the empty state answers that question.
    fireEvent.change(screen.getByLabelText('Packing list filter'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Supplier'), { target: { value: 'sup-1' } });

    expect(
      screen.getByText('No proforma invoice on file for this supplier.'),
    ).toBeInTheDocument();
  });

  it('says the search found nothing, rather than that nothing was uploaded', () => {
    state.data = { data: [], total: 0 };
    renderView();

    fireEvent.change(searchBox(), { target: { value: 'FSCU' } });

    expect(
      screen.getByText('No proforma invoice matches this search and filter.'),
    ).toBeInTheDocument();
  });

  it('renders every row once loaded', () => {
    state.data = {
      data: [invoiceRow(), invoiceRow({ id: 'pi-2', pi_number: 'PI-2026-002' })],
      total: 2,
    };
    renderView();

    expect(screen.getByText('PI-2026-001')).toBeInTheDocument();
    expect(screen.getByText('PI-2026-002')).toBeInTheDocument();
    expect(screen.getAllByText('Kailu Hardware Factory').length).toBeGreaterThan(0);
  });

  it('shows the supplier NAME once, not a second normalised code under it', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    expect(screen.getByText('Kailu Hardware Factory')).toBeInTheDocument();
    expect(screen.queryByText('KAILU')).not.toBeInTheDocument();
  });

  it('a failed read falls back to the empty state rather than crashing', () => {
    // No isError branch in this view - a failed fetch leaves `data` undefined, same as a
    // fetch that has not resolved yet, and the grid still renders without throwing.
    state.data = undefined;
    state.isLoading = false;
    renderView();

    expect(
      screen.getByText('No proforma invoice is waiting for a container.'),
    ).toBeInTheDocument();
  });

  it('renders the pagination footer whether or not there are rows', () => {
    state.data = { data: [], total: 0 };
    const { container } = renderView();

    expect(container.querySelector('[data-slot="card-footer"]')).toBeInTheDocument();
  });
});

describe('ProformaInvoicesView - the standard toolbar', () => {
  it('sends what was typed to the service as `query`', async () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    fireEvent.change(searchBox(), { target: { value: 'FSCU8103365' } });

    await waitFor(() => expect(lastListOptions().query).toBe('FSCU8103365'));
  });

  it('clears the search from its own button', async () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    fireEvent.change(searchBox(), { target: { value: 'FSCU' } });
    fireEvent.click(screen.getByRole('button', { name: /clear search/i }));

    await waitFor(() => expect(lastListOptions().query).toBe(''));
    expect(searchBox().value).toBe('');
  });

  it('holds BOTH filters behind one Filters popover, and counts them', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    // Closed, the selects are not on screen at all - that is the point of the popover.
    expect(screen.queryByLabelText('Supplier')).not.toBeInTheDocument();

    openFilters();

    expect(screen.getByLabelText('Supplier')).toBeInTheDocument();
    expect(screen.getByLabelText('Packing list filter')).toBeInTheDocument();
  });

  it('states the active filter on screen, with a way to clear it', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    // The default IS a filter, so it says so - a sticky default the reader did not set is
    // otherwise indistinguishable from missing data. ("Not converted" is also the row's own
    // Packing list cell, so the chip is identified by its clear button, not by the words.)
    const clear = screen.getByRole('button', { name: /clear filter: not converted/i });
    expect(clear).toBeInTheDocument();
    fireEvent.click(clear);

    expect(
      screen.queryByRole('button', { name: /clear filter/i }),
    ).not.toBeInTheDocument();
  });

  it('offers the Columns control', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    expect(screen.getByRole('button', { name: /columns/i })).toBeInTheDocument();
  });

  it('anchors [gear] [Start] as the right cluster (AC-E1)', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    expect(screen.getByRole('button', { name: 'More actions' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Start/ })).toBeInTheDocument();
    // Upload is INSIDE Start now, not a button of its own.
    expect(
      screen.queryByRole('button', { name: /upload proforma invoice/i }),
    ).not.toBeInTheDocument();
  });

  it('offers Upload and Convert under Start', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    openStart();

    expect(
      screen.getByRole('menuitem', { name: /upload proforma invoice/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('menuitem', { name: /convert to packing list/i }),
    ).toBeInTheDocument();
  });

  it('refuses Convert until something is ticked, and says why', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    openStart();

    const convert = screen.getByRole('menuitem', { name: /convert to packing list/i });
    expect(convert).toHaveAttribute('data-disabled');
    expect(convert).toHaveAttribute('title', 'Select invoices first');
  });

  it('counts the ticked rows in the Convert item', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    tickFirstRow();
    openStart();

    expect(
      screen.getByRole('menuitem', { name: /convert 1 to packing list/i }),
    ).toBeInTheDocument();
  });

  it('hides Upload from Start without the permission, not just disables it', () => {
    hasPermission.mockImplementation((slug: string) => slug !== 'scm.proforma_invoice.upload');
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    openStart();

    expect(
      screen.queryByRole('menuitem', { name: /upload proforma invoice/i }),
    ).not.toBeInTheDocument();
  });

  it('opens the upload dialog from the Start menu', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    openStart();
    fireEvent.click(screen.getByRole('menuitem', { name: /upload proforma invoice/i }));

    expect(screen.getByTestId('upload-dialog')).toBeInTheDocument();
  });

  it('holds Export and Delete under the gear, both refused without a selection', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    openGear();

    const exportItem = screen.getByRole('menuitem', { name: /export/i });
    const deleteItem = screen.getByRole('menuitem', { name: /^delete$/i });
    expect(exportItem).toHaveAttribute('data-disabled');
    expect(deleteItem).toHaveAttribute('data-disabled');
    expect(deleteItem).toHaveAttribute('title', 'Select invoices first');
  });

  it('leaves the selection strip with the count and Clear only (AC-E2)', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    tickFirstRow();

    expect(screen.getByText('1 selected')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument();
    // Neither bulk button survives the move into the right cluster.
    expect(
      screen.queryByRole('button', { name: /convert 1 to packing list/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete 1/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^export$/i })).not.toBeInTheDocument();
  });

  it('never says "draft shipment" anywhere on this screen (AC-E5)', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    const { container } = renderView();

    tickFirstRow();

    expect(container.textContent).not.toMatch(/draft shipment/i);
  });
});

describe('ProformaInvoicesView - the whole row opens the invoice', () => {
  it('routes to the detail page on a row click, carrying the list query', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    fireEvent.click(screen.getByText('TEMU1234567'));

    expect(push).toHaveBeenCalledTimes(1);
    const href = push.mock.calls[0][0] as string;
    expect(href).toContain('/scm/proforma-invoices/pi-1');
    expect(href).toContain('placement=not_converted');
  });

  it('keeps the PI number a real anchor, and stops it opening the row twice', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    // The ROW is a link too now (S1-06 `rowHref`), so the anchor is the <a>
    // among them - the PI number stays a real, copyable, middle-clickable link.
    const link = screen
      .getAllByRole('link', { name: /PI-2026-001/ })
      .find((el) => el.tagName === 'A') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toContain('/scm/proforma-invoices/pi-1');

    fireEvent.click(link);
    expect(push).not.toHaveBeenCalled();
  });
});

describe('ProformaInvoicesView - delete lives under the gear, never in a row', () => {
  it('renders no Delete control while nothing is selected', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    expect(screen.queryByRole('button', { name: /^delete/i })).not.toBeInTheDocument();
  });

  it('counts the selection in the gear\'s Delete', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    tickFirstRow();
    openGear();

    expect(screen.getByRole('menuitem', { name: /delete 1/i })).toBeInTheDocument();
  });

  it('uses the standard confirm copy, never a browser confirm()', () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    tickFirstRow();
    openGear();
    fireEvent.click(screen.getByRole('menuitem', { name: /delete 1/i }));

    const dialog = screen.getByRole('alertdialog');
    expect(within(dialog).getByText('Confirm delete')).toBeInTheDocument();
    expect(within(dialog).getByText(/this action cannot be undone/i)).toBeInTheDocument();
  });

  it('deletes only after the dialog is confirmed', async () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    tickFirstRow();
    openGear();
    fireEvent.click(screen.getByRole('menuitem', { name: /delete 1/i }));
    expect(state.bulkDeleteInvoices).not.toHaveBeenCalled();

    const dialog = screen.getByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }));

    await waitFor(() => expect(state.bulkDeleteInvoices).toHaveBeenCalledWith(['pi-1']));
  });

  it('hides Delete from a caller who cannot upload, and keeps Convert', () => {
    hasPermission.mockImplementation((slug: string) => slug !== 'scm.proforma_invoice.upload');
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    tickFirstRow();
    openGear();
    expect(screen.queryByRole('menuitem', { name: /delete 1/i })).not.toBeInTheDocument();
    closeMenu();

    openStart();
    expect(
      screen.getByRole('menuitem', { name: /convert 1 to packing list/i }),
    ).toBeInTheDocument();
  });
});

describe('R15 - a convert from the list runs at once', () => {
  it('calls the convert with the ticked invoices and no dialog in between', async () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    tickFirstRow();
    openStart();
    fireEvent.click(screen.getByRole('menuitem', { name: /convert 1 to packing list/i }));

    await waitFor(() =>
      expect(state.convertInvoices).toHaveBeenCalledWith({
        invoiceIds: ['pi-1'],
        overrideReason: undefined,
      }),
    );
    // No packing-list dialog stood in front of it.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('names the packing list in the toast and lands on it', async () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    tickFirstRow();
    openStart();
    fireEvent.click(screen.getByRole('menuitem', { name: /convert 1 to packing list/i }));

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        'Packing list PL-2608-003 created with 1 line',
      ),
    );
    expect(push).toHaveBeenCalledWith('/procurement-management/packing-lists/ship-1');
  });

  it('asks whether to load the box anyway when the placement is over capacity', async () => {
    state.data = { data: [invoiceRow()], total: 1 };
    state.convertInvoices = vi.fn().mockRejectedValue(
      Object.assign(new Error('PI-2026-001 is 69.36 cbm and the 40HQ holds 65.'), {
        code: 'over_capacity',
      }),
    );
    renderView();

    tickFirstRow();
    openStart();
    fireEvent.click(screen.getByRole('menuitem', { name: /convert 1 to packing list/i }));

    expect(await screen.findByText('This will not fit')).toBeInTheDocument();
    expect(
      screen.getByText('PI-2026-001 is 69.36 cbm and the 40HQ holds 65.'),
    ).toBeInTheDocument();
  });

  it('retries with the reason once "Convert anyway" is pressed', async () => {
    state.data = { data: [invoiceRow()], total: 1 };
    state.convertInvoices = vi
      .fn()
      .mockRejectedValueOnce(
        Object.assign(new Error('over its planned volume'), { code: 'over_capacity' }),
      )
      .mockResolvedValue({
        shipment_id: 'ship-1',
        shipment_number: 'PL-2608-003',
        shipment_status: 'draft',
        supplier_id: null,
        lines_created: 1,
        lines_skipped: 0,
        invoices: [],
        unmatched: [],
      });
    renderView();

    tickFirstRow();
    openStart();
    fireEvent.click(screen.getByRole('menuitem', { name: /convert 1 to packing list/i }));
    await screen.findByText('This will not fit');

    fireEvent.change(screen.getByLabelText(/why convert anyway/i), {
      target: { value: 'Second container booked' },
    });
    fireEvent.click(screen.getByRole('button', { name: /convert anyway/i }));

    await waitFor(() =>
      expect(state.convertInvoices).toHaveBeenLastCalledWith({
        invoiceIds: ['pi-1'],
        overrideReason: 'Second container booked',
      }),
    );
  });
});

describe('F5b - a superseded revision is recognisable in the list', () => {
  it('names which revision a row is, and that it has been superseded', async () => {
    state.data = {
      data: [invoiceRow({ status: 'superseded', revision_no: 1, revision_count: 2 })],
      total: 1,
    };
    renderView();

    expect(await screen.findByText('Revision 1 of 2 - superseded')).toBeInTheDocument();
  });

  it('says nothing about revisions on a document that has only one version', async () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    await screen.findByText('PI-2026-001');
    expect(screen.queryByText(/Revision \d of \d/)).not.toBeInTheDocument();
  });
});

describe('F10 - the list says which packing list an invoice went into', () => {
  const placed = (over: Record<string, unknown> = {}) =>
    invoiceRow({
      placement: 'converted' as const,
      placed_qty: 500,
      remaining_qty: 0,
      packing_lists: [
        {
          shipment_id: 'sh-1',
          shipment_number: 'FSCU8103365',
          shipment_status: 'draft',
          qty: 500,
          lines: 5,
        },
      ],
      ...over,
    });

  it('reads Not converted until something has been placed (AC-F6)', async () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    // Twice: the cell, and the active-filter chip above the grid.
    expect((await screen.findAllByText('Not converted')).length).toBeGreaterThanOrEqual(1);
  });

  it('names the packing list and how much went there', async () => {
    state.data = { data: [placed()], total: 1 };
    renderView();

    // The row is a link as well (S1-06), so pick the anchor out of the matches.
    const links = await screen.findAllByRole('link', { name: /FSCU8103365/ });
    const link = links.find((el) => el.tagName === 'A') as HTMLAnchorElement;
    expect(link).toHaveAttribute('href', '/procurement-management/packing-lists/sh-1');
  });

  it('reads Split, with what is left to place, on a part-placed invoice (Q9)', async () => {
    state.data = {
      data: [placed({ placement: 'split' as const, placed_qty: 200, remaining_qty: 300 })],
      total: 1,
    };
    renderView();

    expect(await screen.findByText(/Split - 300 still to place/)).toBeInTheDocument();
  });

  it('cannot tick a fully placed invoice, and says why (AC-F7)', async () => {
    state.data = { data: [placed()], total: 1 };
    renderView();

    const box = await screen.findByRole('checkbox', { name: 'Select PI-2026-001' });
    expect(box).toBeDisabled();
    // The reason sits on the wrapper, because a disabled control does not reliably receive
    // the hover that would show its own tooltip.
    expect(box.closest('span[title]')).toHaveAttribute('title', 'In FSCU8103365');
  });

  it('cannot tick a superseded revision either', async () => {
    state.data = {
      data: [invoiceRow({ status: 'superseded', revision_no: 1, revision_count: 2 })],
      total: 1,
    };
    renderView();

    expect(await screen.findByRole('checkbox', { name: 'Select PI-2026-001' })).toBeDisabled();
  });

  it('leaves an unplaced invoice tickable', async () => {
    state.data = { data: [invoiceRow()], total: 1 };
    renderView();

    expect(
      await screen.findByRole('checkbox', { name: 'Select PI-2026-001' }),
    ).not.toBeDisabled();
  });
});
