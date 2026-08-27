/**
 * The packing list reads like a user record: one toolbar over routed tabs.
 *
 * What is under test here, in the order the brief asks for it:
 *  - the six tabs, in order, and the toolbar that sits above them (prev/next, the ONE
 *    primary action, the occasional ones behind a gear, Back);
 *  - the Proforma invoices tab that replaces the old one-line "Origin" card;
 *  - the Shipment lines editor and its new measurement columns, which is where every
 *    figure the container workbook derives actually comes from;
 *  - and the edit draft, which now lives above all six tabs because Edit is on the
 *    toolbar - so a save started on Details still writes the lines in the same PUT.
 *
 * A mixed container throughout: two factories on the lines and nobody on the header, which
 * is the shape that used to make this page say "No supplier" about a full container.
 */
import React, { Suspense } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const routerState = { pathname: '/procurement-management/packing-lists/pl-1', push: vi.fn() };

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: routerState.push, replace: vi.fn(), back: vi.fn() }),
  usePathname: () => routerState.pathname,
  useSearchParams: () => new URLSearchParams(),
}));

// `ConfirmDeleteDialog` reports through `toast.custom`; a mock without it throws inside
// react-query's error path and surfaces as an unhandled rejection that fails no test.
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
    custom: vi.fn(),
    dismiss: vi.fn(),
  },
}));

const state = {
  packingList: null as unknown,
  /** The proforma invoices behind the container - four readings of one payload. */
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

const downloadWorkbook = vi.fn(async (_id: string, _fallback?: string | null) => undefined);
vi.mock('@/app/(protected)/scm/services/fulfilmentService', () => ({
  downloadPackingListExport: (id: string, fallback?: string | null) =>
    downloadWorkbook(id, fallback),
}));

vi.mock('../components/PackingListNavigation', () => ({ default: () => null }));
vi.mock('../components/packing-list-delete-dialog', () => ({ default: () => null }));
vi.mock('../components/ClearanceDeliveryCard', () => ({ default: () => null }));
vi.mock('../components/ContainerStatusImportDialog', () => ({ default: () => null }));
vi.mock('../components/SpoPlannerTable', () => ({ default: () => <div>SPO planner body</div> }));
vi.mock('@/components/common/LinkAttachmentBrowserDialog', () => ({ default: () => null }));
// Container reads the settings provider, which this test has no business standing up.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import PackingListLayout from './layout';
import DetailsPage from './page';
import ProformaInvoicesPage from './proforma-invoices/page';
import LinesPage from './lines/page';
import DocumentsPage from './documents/page';
import SpoPage from './spo/page';
import TimelinePage from './timeline/page';

/** Two factories on the lines, nobody on the header. */
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
        material: '不锈钢',
        pcs_per_carton: '10',
        carton_length_cm: '34.00',
        carton_width_cm: '24.00',
        carton_height_cm: '30.00',
        net_weight_per_carton: '7.000',
        gross_weight_per_carton: '8.300',
        currency: 'CNY',
        unit_cost: '65.50',
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
        weight_per_carton: 4.5,
        product: { id: 'p-3', product_code: 'SRTBT2200', product_name: 'Bath Tub 1700' },
      },
    ],
    ...over,
  };
}

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
        revision_count: 2,
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
    created_by: 'Ms Tee',
  };
}

// One stable promise: `use(params)` suspends, and a promise recreated on every render
// suspends again forever.
const PARAMS = Promise.resolve({ id: 'pl-1' });

async function renderTab(tab: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <Suspense fallback={null}>
          <PackingListLayout params={PARAMS}>{tab}</PackingListLayout>
        </Suspense>
      </QueryClientProvider>,
    );
  });
}

/** Radix opens on pointerdown, which jsdom does not synthesize from a click, so drive the
 *  gear by keyboard instead (ArrowDown opens it and focuses the first item). */
async function openGear() {
  const trigger = await screen.findByRole('button', { name: 'Packing list options' });
  trigger.focus();
  fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
  return screen.findByRole('menu');
}

beforeEach(async () => {
  await PARAMS;
  vi.clearAllMocks();
  routerState.pathname = '/procurement-management/packing-lists/pl-1';
  routerState.push = vi.fn();
  state.packingList = mixedContainer();
  state.sourceInvoices = undefined;
  updatePackingList.mockReset();
  updatePackingList.mockResolvedValue({});
});

afterEach(() => cleanup());

describe('the toolbar over the tabs', () => {
  it('names the container and its factories, and offers the six tabs in order', async () => {
    await renderTab(<DetailsPage />);

    expect(screen.getByRole('heading', { name: 'FSCU8103365' })).toBeInTheDocument();
    // The factories come off the LINES: the header of a mixed container names nobody.
    // Twice on purpose - once as the toolbar's subtitle, once as the Details tab's
    // Supplier value, which has to stay there because Edit swaps it for an input in place.
    expect(
      screen.getByText(/KAILU HARDWARE FACTORY, CAIZHOU SANITARY . Shipment date/),
    ).toBeInTheDocument();

    const tabs = screen.getAllByRole('tab').map((t) => t.textContent);
    expect(tabs.map((t) => t?.replace(/\d+$/, ''))).toEqual([
      'Details',
      'Proforma invoices',
      'Shipment lines',
      'Documents',
      'SPO planner',
      'Timeline',
    ]);
  });

  it('falls back to the shipment number when the container has no number', async () => {
    state.packingList = mixedContainer({ shipping_container_number: null });
    await renderTab(<DetailsPage />);

    expect(screen.getByRole('heading', { name: 'SPO-0042' })).toBeInTheDocument();
  });

  it('carries ONE primary action: downloading the container workbook', async () => {
    await renderTab(<DetailsPage />);

    fireEvent.click(screen.getByRole('button', { name: /download packing list/i }));

    await waitFor(() => expect(downloadWorkbook).toHaveBeenCalledTimes(1));
    // Named after the container, never the id: a workbook in a downloads folder called
    // after a UUID cannot be told from any other one.
    expect(downloadWorkbook).toHaveBeenCalledWith('pl-1', 'FSCU8103365');
  });

  it('keeps the occasional actions behind the gear', async () => {
    await renderTab(<DetailsPage />);
    const menu = await openGear();

    expect(within(menu).getByText('Edit')).toBeInTheDocument();
    expect(within(menu).getByText('Import Container Status workbook')).toBeInTheDocument();
    expect(within(menu).getByText('Delete')).toBeInTheDocument();
  });

  it('offers a way back to the list', async () => {
    await renderTab(<DetailsPage />);

    expect(screen.getByRole('link', { name: /back to packing lists/i })).toHaveAttribute(
      'href',
      '/procurement-management/packing-lists',
    );
  });

  it('routes rather than swapping a local tab, so a tab is linkable', async () => {
    await renderTab(<DetailsPage />);

    fireEvent.click(screen.getByRole('tab', { name: /shipment lines/i }));

    expect(routerState.push).toHaveBeenCalledWith(
      '/procurement-management/packing-lists/pl-1/lines',
    );
  });
});

describe('the Proforma invoices tab', () => {
  it('names them with what came from each, and who converted the container', async () => {
    state.sourceInvoices = sourceInvoices();
    routerState.pathname = '/procurement-management/packing-lists/pl-1/proforma-invoices';
    await renderTab(<ProformaInvoicesPage />);

    const row = screen.getByText('PI-2026-001').closest('tr') as HTMLElement;
    expect(within(row).getByText('490 of 900')).toBeInTheDocument();
    expect(within(row).getByText('1 of 3')).toBeInTheDocument();
    expect(within(row).getByText(/Revision 2 of 2/)).toBeInTheDocument();
    expect(within(row).getByRole('link', { name: 'Open' })).toHaveAttribute(
      'href',
      '/scm/proforma-invoices/pi-1',
    );
    // The name the server resolved, never the user id the container carries.
    expect(screen.getByText(/Uploaded by Ms Tee, converted on/)).toBeInTheDocument();
  });

  it('says plainly when a container came off a real packing list instead', async () => {
    state.sourceInvoices = { invoices: [], by_shipment_line: {}, created_by: 'System' };
    routerState.pathname = '/procurement-management/packing-lists/pl-1/proforma-invoices';
    await renderTab(<ProformaInvoicesPage />);

    expect(screen.getByText('Source proforma invoices')).toBeInTheDocument();
    expect(
      screen.getByText('Read from a packing list, not drafted from a proforma invoice.'),
    ).toBeInTheDocument();
  });

  it('leaves the Timeline to the clearance checkpoints alone', async () => {
    state.sourceInvoices = sourceInvoices();
    routerState.pathname = '/procurement-management/packing-lists/pl-1/timeline';
    await renderTab(<TimelinePage />);

    expect(screen.getByText('Clearance & Delivery')).toBeInTheDocument();
    // The Origin card is gone: it is a whole tab now.
    expect(screen.queryByText(/Created from PI-2026-001/)).not.toBeInTheDocument();
  });
});

describe('the Shipment lines tab', () => {
  beforeEach(() => {
    routerState.pathname = '/procurement-management/packing-lists/pl-1/lines';
  });

  it('states what the workbook measures each line by', async () => {
    await renderTab(<LinesPage />);

    for (const name of ['Material', 'Pcs/ctn', 'L', 'W', 'H', 'NW', 'GW', 'CBM']) {
      expect(screen.getByRole('columnheader', { name })).toBeInTheDocument();
    }
    const kailu = screen.getByText('SRTWT7443').closest('tr') as HTMLElement;
    expect(within(kailu).getByText('不锈钢')).toBeInTheDocument();
    expect(within(kailu).getByText('10')).toBeInTheDocument();
    expect(within(kailu).getByText('34')).toBeInTheDocument();
    expect(within(kailu).getByText('7')).toBeInTheDocument();
    expect(within(kailu).getByText('8.3')).toBeInTheDocument();
  });

  it('reads the one old weight as the gross one, and "-" where nothing was measured', async () => {
    await renderTab(<LinesPage />);

    const unmeasured = screen.getByText('SRTBT2200').closest('tr') as HTMLElement;
    // `weight_per_carton` is the only weight most containers hold, and it is the gross.
    expect(within(unmeasured).getByText('4.5')).toBeInTheDocument();
    // Material, pcs/ctn, L, W, H, NW and CBM all state nothing rather than 0.
    const cells = Array.from(unmeasured.querySelectorAll('td')).map((c) => c.textContent);
    expect(cells[3]).toBe('-'); // material
    expect(cells[4]).toBe('-'); // pcs per carton
    expect(cells[11]).toBe('-'); // cbm
  });

  it('names the factory that loaded each line, and guesses no owner for the rest', async () => {
    await renderTab(<LinesPage />);

    const kailu = screen.getByText('SRTWT7443').closest('tr') as HTMLElement;
    expect(within(kailu).getByText('KAILU HARDWARE FACTORY')).toBeInTheDocument();
    const unclaimed = screen.getByText('SRTBT2200').closest('tr') as HTMLElement;
    expect(unclaimed.querySelectorAll('td')[1]).toHaveTextContent('-');
  });

  it('totals the volume under the column and counts what is unmeasured', async () => {
    await renderTab(<LinesPage />);

    const total = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(total).getByText('19.75')).toBeInTheDocument();
    expect(within(total).getByText('(1 unmeasured)')).toBeInTheDocument();
    expect(within(total).getByText('1510')).toBeInTheDocument();
    expect(within(total).getByText('171')).toBeInTheDocument();
  });

  it('names the invoice per line', async () => {
    state.sourceInvoices = sourceInvoices();
    await renderTab(<LinesPage />);

    const kailu = screen.getByText('SRTWT7443').closest('tr') as HTMLElement;
    expect(within(kailu).getByRole('link', { name: /PI-2026-001/ })).toHaveAttribute(
      'href',
      '/scm/proforma-invoices/pi-1',
    );
  });
});

describe('the edit draft, which now lives above every tab', () => {
  it('swaps values for inputs where the values were, on the Details tab', async () => {
    await renderTab(<DetailsPage />);

    expect(screen.queryByLabelText('Bill of Lading Number')).not.toBeInTheDocument();
    fireEvent.click(within(await openGear()).getByText('Edit'));

    expect(screen.getByLabelText('Shipping Container Number')).toHaveValue('FSCU8103365');
    // The three the container workbook prints, and the costs it apportions.
    expect(screen.getByLabelText('Seal No')).toBeInTheDocument();
    expect(screen.getByLabelText('Shipper')).toBeInTheDocument();
    expect(screen.getByLabelText('Forwarder order ref')).toBeInTheDocument();
    expect(screen.getByLabelText('Clearance cost')).toBeInTheDocument();
    expect(screen.getByLabelText('China freight cost')).toBeInTheDocument();
    expect(screen.getByLabelText('Insurance rate')).toBeInTheDocument();
    // The ones with no input counterpart stay as values - nothing moves between the two.
    expect(screen.getByText('Total Items')).toBeInTheDocument();
    expect(screen.getByText('Source sheet')).toBeInTheDocument();
  });

  it('renders the Container costs card whether or not anything is priced', async () => {
    await renderTab(<DetailsPage />);

    expect(screen.getByText('Container costs')).toBeInTheDocument();
  });

  it('saves the header and the lines in one PUT', async () => {
    await renderTab(<DetailsPage />);
    fireEvent.click(within(await openGear()).getByText('Edit'));

    fireEvent.change(screen.getByLabelText('Seal No'), { target: { value: 'J0713349' } });
    fireEvent.change(screen.getByLabelText('Clearance cost'), { target: { value: '2700' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(updatePackingList).toHaveBeenCalledTimes(1));
    const { id, data } = updatePackingList.mock.calls[0][0];
    expect(id).toBe('pl-1');
    expect(data.seal_number).toBe('J0713349');
    expect(data.clearance_cost).toBe(2700);
    expect(data.shipment_lines).toHaveLength(3);
  });

  it('sends null for a cleared cost, never a zero that would be apportioned', async () => {
    state.packingList = mixedContainer({ clearance_cost: '2700.00' });
    await renderTab(<DetailsPage />);
    fireEvent.click(within(await openGear()).getByText('Edit'));

    fireEvent.change(screen.getByLabelText('Clearance cost'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(updatePackingList).toHaveBeenCalledTimes(1));
    const { data } = updatePackingList.mock.calls[0][0];
    expect(data.clearance_cost).toBeNull();
    expect(Object.keys(data)).toContain('clearance_cost');
  });

  it('edits the measurements on the lines tab and sends them', async () => {
    routerState.pathname = '/procurement-management/packing-lists/pl-1/lines';
    await renderTab(<LinesPage />);
    fireEvent.click(within(await openGear()).getByText('Edit'));

    expect(screen.getByLabelText('Pcs per carton for SRTWT7443')).toHaveValue(10);
    fireEvent.change(screen.getByLabelText('Carton length for SRTWT7443'), {
      target: { value: '36' },
    });
    fireEvent.change(screen.getByLabelText('Gross weight for SRTWT7443'), {
      target: { value: '9.1' },
    });
    fireEvent.change(screen.getByLabelText('Material for SRTWT7443'), {
      target: { value: '铜' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(updatePackingList).toHaveBeenCalledTimes(1));
    const line = updatePackingList.mock.calls[0][0].data.shipment_lines[0];
    expect(line.carton_length_cm).toBe(36);
    expect(line.gross_weight_per_carton).toBe(9.1);
    expect(line.material).toBe('铜');
    // The unit the price is in, round-tripped: a payload carrying the cost and dropping
    // this hands the backend a number with no meaning.
    expect(line.currency).toBe('CNY');
  });

  it('totals follow the draft while somebody is typing', async () => {
    routerState.pathname = '/procurement-management/packing-lists/pl-1/lines';
    await renderTab(<LinesPage />);
    fireEvent.click(within(await openGear()).getByText('Edit'));

    fireEvent.change(screen.getByLabelText('Quantity for SRTWT7443'), {
      target: { value: '400' },
    });
    fireEvent.change(screen.getByLabelText('CBM for SRTWT7443'), { target: { value: '10' } });

    const total = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(total).getByText('1420')).toBeInTheDocument();
    expect(within(total).getByText('17.25')).toBeInTheDocument();
  });

  it('asks before removing a line, and only then drops it', async () => {
    routerState.pathname = '/procurement-management/packing-lists/pl-1/lines';
    await renderTab(<LinesPage />);
    fireEvent.click(within(await openGear()).getByText('Edit'));

    const row = screen.getByLabelText('Quantity for SRTWT7443').closest('tr') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: /remove/i }));
    expect(
      screen.getByText(/This removes SRTWT7443 from this packing list/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    await waitFor(() =>
      expect(screen.queryByLabelText('Quantity for SRTWT7443')).not.toBeInTheDocument(),
    );
    expect(updatePackingList).not.toHaveBeenCalled();
  });

  it('restores the saved values on Cancel, writing nothing', async () => {
    await renderTab(<DetailsPage />);
    fireEvent.click(within(await openGear()).getByText('Edit'));

    fireEvent.change(screen.getByLabelText('Invoice Number'), { target: { value: 'INV-77' } });
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

    expect(updatePackingList).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('Invoice Number')).not.toBeInTheDocument();
  });
});

describe('the remaining tabs still render their own bodies', () => {
  it('lists the proforma files on Documents', async () => {
    state.sourceInvoices = sourceInvoices();
    routerState.pathname = '/procurement-management/packing-lists/pl-1/documents';
    await renderTab(<DocumentsPage />);

    expect(screen.getByText('Related Documents')).toBeInTheDocument();
    expect(screen.getByText(/KAILU proforma\.xlsx/)).toBeInTheDocument();
  });

  it('asks before unlinking the attachment, never on one click', async () => {
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
    routerState.pathname = '/procurement-management/packing-lists/pl-1/documents';
    await renderTab(<DocumentsPage />);

    fireEvent.click(screen.getByTitle('Unlink attachment'));

    expect(screen.getByText('Unlink this attachment?')).toBeInTheDocument();
    expect(updatePackingList).not.toHaveBeenCalled();
  });

  it('renders the SPO planner', async () => {
    routerState.pathname = '/procurement-management/packing-lists/pl-1/spo';
    await renderTab(<SpoPage />);

    expect(screen.getByText('SPO planner body')).toBeInTheDocument();
  });
});
