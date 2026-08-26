/**
 * A mixed container has no supplier on its header, and this page used to say "No supplier"
 * about a container two factories had loaded. The factories are on the LINES; the page reads
 * them from there, and names each line's factory next to it so a line can be traced back to
 * the packing list it came off.
 *
 * The line response carries `supplier_id` only, so the names come from the shared supplier
 * select - a UUID is never shown.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const searchParams = { value: new URLSearchParams() };

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => searchParams.value,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const state = {
  packingList: null as unknown,
  /** The proforma invoices behind the container - F10's four readings of one payload. */
  sourceInvoices: undefined as unknown,
};

const updatePackingList = vi.fn();

vi.mock('../hooks/usePackingLists', () => ({
  usePackingList: () => ({ data: state.packingList, isLoading: false }),
  useDeletePackingList: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdatePackingList: () => ({ mutateAsync: updatePackingList, isPending: false }),
  usePackingListSourceInvoices: () => ({ data: state.sourceInvoices, isLoading: false }),
  // Checkpoint labels and order come from config, and the edit-in-place clearance fields
  // read the same list the timeline does.
  useClearanceCheckpoints: () => ({
    data: [
      { field: 'etd_date', label: 'ETD', caption: null },
      { field: 'estimated_arrival_date', label: 'ETA', caption: null },
      { field: 'gatepass_date', label: 'Gatepass', caption: null },
    ],
    isLoading: false,
    isError: false,
  }),
}));

vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProducts: vi.fn(async () => ({ data: [] })),
}));

vi.mock('../../suppliers/hooks/useSupplierSelectQuery', () => ({
  useSupplierSelectQuery: () => ({
    data: [
      { id: 'sup-a', supplier_code: '400-K029', supplier_name: 'KAILU HARDWARE FACTORY' },
      { id: 'sup-b', supplier_code: '400-C011', supplier_name: 'CAIZHOU SANITARY' },
    ],
  }),
}));

vi.mock('@/app/(protected)/resource-management/attachments/hooks/useAttachments', () => ({
  useDownloadAttachment: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/app/(protected)/resource-management/attachments/services/attachmentService', () => ({
  getAttachmentPreviewUrl: vi.fn(),
}));

vi.mock('./PackingListNavigation', () => ({ default: () => null }));
vi.mock('./packing-list-delete-dialog', () => ({ default: () => null }));
vi.mock('./ClearanceDeliveryCard', () => ({ default: () => null }));
vi.mock('@/components/common/LinkAttachmentBrowserDialog', () => ({ default: () => null }));

import PackingListDetail from './PackingListDetail';

/** Two factories on the lines, nobody on the header - the shape the fix is about. */
function mixedContainer(over: Record<string, unknown> = {}) {
  return {
    id: 'pl-1',
    shipment_number: 'SPO-0042',
    supplier_id: null,
    supplier: undefined,
    shipment_date: '2026-07-30',
    shipping_container_number: 'FSCU8103365',
    shipment_status: 'in_transit',
    created_at: '2026-07-30',
    updated_at: '2026-07-30',
    synced_to_excel: false,
    shipment_lines: [
      {
        id: 'l-1',
        shipment_id: 'pl-1',
        product_id: 'p-1',
        quantity_shipped: 490,
        cartons_count: 86,
        cbm: '12.5',
        supplier_id: 'sup-a',
        product: { id: 'p-1', product_code: 'SRTWT7443', product_name: 'Basin Mixer Tall' },
      },
      {
        id: 'l-2',
        shipment_id: 'pl-1',
        product_id: 'p-2',
        quantity_shipped: 900,
        cartons_count: 55,
        cbm: 7.25,
        supplier_id: 'sup-b',
        product: { id: 'p-2', product_code: 'MCHWT1200', product_name: 'Shower Set' },
      },
      {
        id: 'l-3',
        shipment_id: 'pl-1',
        product_id: 'p-3',
        quantity_shipped: 120,
        cartons_count: 30,
        supplier_id: null,
        product: { id: 'p-3', product_code: 'SRTBT2200', product_name: 'Bath Tub 1700' },
      },
    ],
    ...over,
  };
}

function renderDetail() {
  // ConfirmDeleteDialog (the line-removal confirmation) runs its own mutation, so the page
  // needs a client even though every data hook here is mocked.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PackingListDetail packingListId="pl-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParams.value = new URLSearchParams();
  state.packingList = mixedContainer();
  state.sourceInvoices = undefined;
  updatePackingList.mockReset();
  updatePackingList.mockResolvedValue({});
});

describe('PackingListDetail - who loaded this container', () => {
  it('names every factory on the lines when the header names none', () => {
    state.packingList = mixedContainer();
    renderDetail();

    expect(
      screen.getByText(/KAILU HARDWARE FACTORY, CAIZHOU SANITARY/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/No supplier/)).not.toBeInTheDocument();
  });

  it('still says "No supplier" when nothing on the container claims a factory', () => {
    const list = mixedContainer();
    list.shipment_lines.forEach((l) => {
      l.supplier_id = null;
    });
    state.packingList = list;
    renderDetail();

    expect(screen.getByText(/No supplier/)).toBeInTheDocument();
  });

  it("keeps the header's own supplier when the container is a single factory's", () => {
    state.packingList = mixedContainer({
      supplier_id: 'sup-a',
      supplier: {
        id: 'sup-a',
        supplier_code: '400-K029',
        supplier_name: 'KAILU HARDWARE FACTORY',
      },
    });
    renderDetail();

    expect(screen.getByText(/KAILU HARDWARE FACTORY •/)).toBeInTheDocument();
  });
});

describe('PackingListDetail - the line table', () => {
  beforeEach(() => {
    // The lines tab is the one under test; Radix only mounts the active tab's body.
    searchParams.value = new URLSearchParams('tab=lines');
  });

  it('names the factory that loaded each line', () => {
    renderDetail();

    const header = screen.getByRole('columnheader', { name: 'Supplier' });
    expect(header).toBeInTheDocument();

    const kailuLine = screen.getByText('SRTWT7443').closest('tr') as HTMLElement;
    expect(within(kailuLine).getByText('KAILU HARDWARE FACTORY')).toBeInTheDocument();
    const caizhouLine = screen.getByText('MCHWT1200').closest('tr') as HTMLElement;
    expect(within(caizhouLine).getByText('CAIZHOU SANITARY')).toBeInTheDocument();
  });

  it('leaves a line nobody has claimed blank rather than guessing an owner', () => {
    renderDetail();

    const unclaimed = screen.getByText('SRTBT2200').closest('tr') as HTMLElement;
    // The supplier cell, second after the product - "-" also stands for an unallocated
    // quantity further along the row.
    expect(unclaimed.querySelectorAll('td')[1]).toHaveTextContent('-');
    expect(within(unclaimed).queryByText(/FACTORY|SANITARY/)).not.toBeInTheDocument();
  });
});

describe('F6 - the container states how much room it takes', () => {
  beforeEach(() => {
    searchParams.value = new URLSearchParams('tab=lines');
  });

  it('shows cartons and CBM per line, decimal on the wire included (AC-F2)', () => {
    renderDetail();

    expect(screen.getByRole('columnheader', { name: 'CBM' })).toBeInTheDocument();
    const kailuLine = screen.getByText('SRTWT7443').closest('tr') as HTMLElement;
    expect(within(kailuLine).getByText('12.5')).toBeInTheDocument();
    expect(within(kailuLine).getByText('86')).toBeInTheDocument();
  });

  it('reads "-" on a line nobody measured, never 0 (AC-F2)', () => {
    renderDetail();

    const unmeasured = screen.getByText('SRTBT2200').closest('tr') as HTMLElement;
    // The CBM cell is the fifth: product, supplier, quantity, cartons, cbm.
    expect(unmeasured.querySelectorAll('td')[4]).toHaveTextContent('-');
  });

  it('totals the volume under the column and counts what is unmeasured', () => {
    renderDetail();

    const total = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(total).getByText('19.75')).toBeInTheDocument();
    expect(within(total).getByText('(1 unmeasured)')).toBeInTheDocument();
    // Quantity and cartons total too, so the footer answers the whole row.
    expect(within(total).getByText('1510')).toBeInTheDocument();
    expect(within(total).getByText('171')).toBeInTheDocument();
  });
});

/** One PI behind this container, charging half of the KAILU line. */
function sourceInvoices() {
  return {
    invoices: [
      {
        id: 'pi-1',
        pi_number: 'PI-2026-001',
        supplier_id: 'sup-a',
        supplier_name: 'KAILU HARDWARE FACTORY',
        invoice_date: '2026-07-17',
        revision_no: 2,
        status: 'current' as const,
        source_ref: 'KAILU proforma.xlsx',
        currency: 'CNY',
        lines: 1,
        total_lines: 3,
        qty: 490,
        total_qty: 900,
        amount: 32095,
      },
    ],
    by_shipment_line: {
      'l-1': [{ proforma_invoice_id: 'pi-1', pi_number: 'PI-2026-001', qty: 490 }],
    },
  };
}

describe('F10 - which proforma invoices this container was drafted from', () => {
  it('names them in the Details tab with what came from each (AC-F9)', async () => {
    searchParams.value = new URLSearchParams('tab=details');
    state.sourceInvoices = sourceInvoices();
    renderDetail();

    expect(screen.getByText('Source proforma invoices')).toBeInTheDocument();
    const row = screen.getByText('PI-2026-001').closest('tr') as HTMLElement;
    expect(within(row).getByText('490 of 900')).toBeInTheDocument();
    expect(within(row).getByText('1 of 3')).toBeInTheDocument();
    expect(within(row).getByText('Revision 2')).toBeInTheDocument();
  });

  it('says so plainly when a container came off a real packing list instead', () => {
    searchParams.value = new URLSearchParams('tab=details');
    state.sourceInvoices = { invoices: [], by_shipment_line: {} };
    renderDetail();

    expect(screen.getByText('Source proforma invoices')).toBeInTheDocument();
    expect(
      screen.getByText(/This container was not drafted from a proforma invoice/),
    ).toBeInTheDocument();
  });

  it('names the invoice per line in the Lines tab (AC-F9)', () => {
    searchParams.value = new URLSearchParams('tab=lines');
    state.sourceInvoices = sourceInvoices();
    renderDetail();

    expect(screen.getByRole('columnheader', { name: 'From PI' })).toBeInTheDocument();
    const kailuLine = screen.getByText('SRTWT7443').closest('tr') as HTMLElement;
    expect(within(kailuLine).getByRole('link', { name: /PI-2026-001/ })).toHaveAttribute(
      'href',
      '/scm/proforma-invoices/pi-1',
    );
    const other = screen.getByText('MCHWT1200').closest('tr') as HTMLElement;
    expect(within(other).queryByText('PI-2026-001')).not.toBeInTheDocument();
  });

  it('opens the timeline with where the container came from (AC-F9)', () => {
    searchParams.value = new URLSearchParams('tab=timeline');
    state.sourceInvoices = sourceInvoices();
    renderDetail();

    expect(screen.getByText(/Created from PI-2026-001/)).toBeInTheDocument();
  });

  it('lists the proforma files in the Documents tab (AC-F9)', () => {
    searchParams.value = new URLSearchParams('tab=documents');
    state.sourceInvoices = sourceInvoices();
    renderDetail();

    expect(screen.getByText('Proforma invoices')).toBeInTheDocument();
    expect(screen.getByText(/KAILU proforma\.xlsx/)).toBeInTheDocument();
  });
});

describe('F9 - the packing list edits in place', () => {
  it('swaps values for inputs where the values were, leaving the layout alone (AC-F3)', () => {
    searchParams.value = new URLSearchParams('tab=details');
    renderDetail();

    expect(screen.queryByLabelText('Bill of Lading Number')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

    expect(screen.getByLabelText('Bill of Lading Number')).toBeInTheDocument();
    expect(screen.getByLabelText('Shipping Container Number')).toHaveValue('FSCU8103365');
    // Same fields, same order - the ones with no input counterpart stay as values.
    expect(screen.getByText('Total Items')).toBeInTheDocument();
    expect(screen.getByText('Source sheet')).toBeInTheDocument();
  });

  it('offers the clearance dates where they are read, so nothing loses its editor', () => {
    searchParams.value = new URLSearchParams('tab=details');
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

    expect(screen.getByLabelText('ETD')).toBeInTheDocument();
    expect(screen.getByLabelText('Gatepass')).toBeInTheDocument();
    // ETA is edited in the header field, and is not asked for twice.
    expect(screen.queryByLabelText('ETA')).not.toBeInTheDocument();
  });

  it('saves the whole packing list in one PUT, lines included (AC-F3)', async () => {
    searchParams.value = new URLSearchParams('tab=details');
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    fireEvent.change(screen.getByLabelText('Invoice Number'), {
      target: { value: 'INV-77' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(updatePackingList).toHaveBeenCalledTimes(1));
    const payload = updatePackingList.mock.calls[0][0];
    expect(payload.id).toBe('pl-1');
    expect(payload.data.invoice_number).toBe('INV-77');
    expect(payload.data.shipment_lines).toHaveLength(3);
  });

  it('restores the saved values on Cancel, writing nothing', () => {
    searchParams.value = new URLSearchParams('tab=details');
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    fireEvent.change(screen.getByLabelText('Invoice Number'), {
      target: { value: 'INV-77' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

    expect(updatePackingList).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('Invoice Number')).not.toBeInTheDocument();
  });

  it('edits a line where it is read, and totals follow the draft (AC-F4)', async () => {
    searchParams.value = new URLSearchParams('tab=lines');
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

    const qty = screen.getByLabelText('Quantity for SRTWT7443');
    expect(qty).toHaveValue(490);
    fireEvent.change(qty, { target: { value: '400' } });
    fireEvent.change(screen.getByLabelText('CBM for SRTWT7443'), {
      target: { value: '10' },
    });

    const total = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(total).getByText('1420')).toBeInTheDocument();
    expect(within(total).getByText('17.25')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(updatePackingList).toHaveBeenCalledTimes(1));
    const line = updatePackingList.mock.calls[0][0].data.shipment_lines[0];
    expect(line.quantity_shipped).toBe(400);
    expect(line.cbm).toBe(10);
  });

  it('asks before removing a line, and only then drops it (AC-F4)', async () => {
    searchParams.value = new URLSearchParams('tab=lines');
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

    const row = screen.getByLabelText('Quantity for SRTWT7443').closest('tr') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: /remove/i }));
    expect(screen.getByText(/This removes SRTWT7443 from this packing list/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    await waitFor(() =>
      expect(screen.queryByLabelText('Quantity for SRTWT7443')).not.toBeInTheDocument(),
    );
    expect(updatePackingList).not.toHaveBeenCalled();
  });

  it('adds a line through a searchable product picker (AC-F4)', () => {
    searchParams.value = new URLSearchParams('tab=lines');
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    fireEvent.click(screen.getByRole('button', { name: /add line/i }));

    expect(screen.getByLabelText('Quantity for the new line')).toBeInTheDocument();
  });

  it('asks before unlinking the attachment, never on one click', () => {
    searchParams.value = new URLSearchParams('tab=documents');
    state.packingList = mixedContainer({
      attachment_id: 'att-1',
      attachment: {
        id: 'att-1',
        original_filename: 'FSCU8103365.pdf',
        stored_filename: 'x.pdf',
        file_path: '/x.pdf',
        file_size_bytes: 2048,
        mime_type: 'application/pdf',
        attachment_type: null,
      },
    });
    renderDetail();

    fireEvent.click(screen.getByTitle('Unlink attachment'));

    expect(screen.getByText('Unlink this attachment?')).toBeInTheDocument();
    expect(updatePackingList).not.toHaveBeenCalled();
  });
});

describe('F9 - clearing a field actually clears it', () => {
  beforeEach(() => {
    searchParams.value = new URLSearchParams('tab=details');
  });

  it('sends null for a cleared text field, never omits it (AC-F3)', async () => {
    state.packingList = mixedContainer({ invoice_number: 'INV-1', notes: 'left over' });
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

    fireEvent.change(screen.getByLabelText('Invoice Number'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(updatePackingList).toHaveBeenCalledTimes(1));
    const { data } = updatePackingList.mock.calls[0][0];
    // JSON.stringify drops `undefined`, and the backend PUT is exclude_unset - so an
    // omitted key means "unchanged" and the value the operator deleted comes back.
    expect(data.invoice_number).toBeNull();
    expect(data.notes).toBeNull();
    expect(Object.keys(data)).toContain('invoice_number');
  });

  it('sends null for a cleared clearance date too', async () => {
    state.packingList = mixedContainer({ etd_date: '2026-08-05' });
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

    fireEvent.change(screen.getByLabelText('ETD'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(updatePackingList).toHaveBeenCalledTimes(1));
    expect(updatePackingList.mock.calls[0][0].data.etd_date).toBeNull();
  });

  it('still sends a value that was typed rather than cleared', async () => {
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

    fireEvent.change(screen.getByLabelText('Bill of Lading Number'), {
      target: { value: 'BL-9' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(updatePackingList).toHaveBeenCalledTimes(1));
    expect(updatePackingList.mock.calls[0][0].data.bill_of_lading_number).toBe('BL-9');
  });
});
