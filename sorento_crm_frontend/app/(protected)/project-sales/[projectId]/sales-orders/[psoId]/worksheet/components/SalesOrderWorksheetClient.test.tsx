/**
 * Stage 1A - the AutoCount worksheet screen (PLAN-scm-front-planning 1.2 steps 1-3, J02).
 *
 * What is pinned here is the export gate and the empty states, because they are what the
 * screen is for. `can_export` belongs to the server, so the screen must not invent a reason
 * of its own - but a disabled button that says nothing is worse than no button, so the two
 * local conditions (not published yet, blocking findings) exist only to name WHICH one is in
 * the way. Both are asserted through the button's title.
 *
 * Validation renders whether or not it has anything to say (AC-G02): "No blocking findings"
 * is the answer CS came for, and a card that disappears when clean does not give it.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  SalesOrderWorksheet,
  SalesOrderWorksheetLine,
} from '../../../../../_shared/types/projectSalesOrder.types';

const getSalesOrderWorksheet = vi.fn();
const downloadSalesOrderImportFile = vi.fn();
const saveBlobAs = vi.fn();
const toastError = vi.fn();

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: (...args: unknown[]) => toastError(...args) },
}));

vi.mock('../../../../../_shared/services/fileDownload', () => ({
  saveBlobAs: (...args: unknown[]) => saveBlobAs(...args),
  filenameFromContentDisposition: vi.fn(() => null),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('../../../../../_shared/services/projectSalesOrderService', () => ({
  PROJECT_SO_MOCK: false,
  getSalesOrderWorksheet: (...args: unknown[]) => getSalesOrderWorksheet(...args),
  listProjectSalesOrders: vi.fn(),
  buildSalesOrders: vi.fn(),
  getProjectSalesOrder: vi.fn(),
  acknowledgeFinding: vi.fn(),
  updateSalesOrderLine: vi.fn(),
  regroupSalesOrder: vi.fn(),
  publishSalesOrder: vi.fn(),
  downloadSalesOrderImportFile: (...args: unknown[]) => downloadSalesOrderImportFile(...args),
  previewAmendment: vi.fn(),
  createAmendment: vi.fn(),
  getAmendment: vi.fn(),
  publishAmendment: vi.fn(),
  listScheduleVersions: vi.fn(async () => []),
  listPoVersions: vi.fn(async () => []),
}));

import { SalesOrderWorksheetClient, worksheetAsTabbedText } from './SalesOrderWorksheetClient';

const LINES: SalesOrderWorksheetLine[] = [
  {
    line_no: 1,
    item_code: 'CB6633',
    description: 'CABANA S/STEEL FLOOR GRATING 6"',
    reserve_qty: '0',
    qty: '600',
    delivery_date: '2026-07-01',
    uom: 'UNIT',
    unit_price: '11.16000',
    discount: '',
    total: '6696.00',
  },
  {
    line_no: 2,
    item_code: 'TPE-9300',
    description: 'FLEXIBLE STRAIGHT CONNECTOR P10 B (4")100MM',
    reserve_qty: '0',
    qty: '135',
    delivery_date: null,
    uom: 'UNIT',
    unit_price: '0.00000',
    discount: '',
    total: '0.00',
  },
];

function worksheet(overrides: Partial<SalesOrderWorksheet> = {}): SalesOrderWorksheet {
  return {
    id: 'so-1',
    provisional_ref: 'PSO-000101',
    autocount_doc_no: 'SO376200',
    status: 'published',
    area_group: 'TOWER',
    po_number: 'HQ/26/01/121',
    customer_name: 'Hong Bee Hardware Sdn Bhd',
    header: {
      debtor: 'Hong Bee Hardware Sdn Bhd',
      your_ref_no: 'HQ/26/01/121',
      our_ref_no: 'Tuju Residences',
      our_qt_ref_no: 'QT-004188 v1',
      terms: '*Net 60 days',
    },
    lines: LINES,
    total_amount: '6696.00',
    findings: [],
    can_export: true,
    import_file_url: '/api/v1/project-sales/sales-orders/so-1/import-file',
    ...overrides,
  };
}

function renderWorksheet() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrderWorksheetClient projectId="p1" psoId="so-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SalesOrderWorksheetClient', () => {
  it('shows a skeleton while loading rather than an empty document', () => {
    getSalesOrderWorksheet.mockReturnValue(new Promise(() => {}));

    renderWorksheet();

    expect(screen.queryByText('PSO-000101')).not.toBeInTheDocument();
    expect(screen.queryByText('Header fields')).not.toBeInTheDocument();
  });

  it('says why the worksheet could not be loaded and offers both ways forward', async () => {
    getSalesOrderWorksheet.mockRejectedValue(new Error('That sales order was rebuilt'));

    renderWorksheet();

    expect(await screen.findByText('This worksheet could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('That sales order was rebuilt')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to the sales order' })).toBeInTheDocument();

    getSalesOrderWorksheet.mockResolvedValue(worksheet());
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByText('SO376200')).toBeInTheDocument();
    expect(getSalesOrderWorksheet).toHaveBeenCalledTimes(2);
  });

  it('renders the six header refs and the lines of a published worksheet', async () => {
    getSalesOrderWorksheet.mockResolvedValue(worksheet());

    renderWorksheet();

    // The AutoCount document number is the reference once it exists; the provisional ref
    // stays visible in the header fields rather than being replaced by it.
    expect(await screen.findByText('SO376200')).toBeInTheDocument();
    expect(screen.getByText('Hong Bee Hardware Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('Tuju Residences')).toBeInTheDocument();
    expect(screen.getByText('QT-004188 v1')).toBeInTheDocument();
    expect(screen.getByText('*Net 60 days')).toBeInTheDocument();
    expect(screen.getByText('PSO-000101')).toBeInTheDocument();
    expect(screen.getByText('CB6633')).toBeInTheDocument();
    expect(screen.getByText('2 lines')).toBeInTheDocument();
    // A line with no delivery date says so instead of rendering an empty cell.
    expect(screen.getByText('No date')).toBeInTheDocument();
  });

  it('renders a header ref the document does not carry as Not recorded', async () => {
    getSalesOrderWorksheet.mockResolvedValue(
      worksheet({
        header: {
          debtor: 'Hong Bee Hardware Sdn Bhd',
          your_ref_no: null,
          our_ref_no: 'Tuju Residences',
          our_qt_ref_no: null,
          terms: null,
        },
      }),
    );

    renderWorksheet();

    expect(await screen.findAllByText('Not recorded')).toHaveLength(3);
  });

  it('shows a blank Debtor as a blank one, rather than borrowing the customer name', async () => {
    getSalesOrderWorksheet.mockResolvedValue(
      worksheet({
        customer_name: 'Hong Bee Hardware Sdn Bhd',
        header: {
          debtor: null,
          your_ref_no: 'HQ/26/01/121',
          our_ref_no: 'Tuju Residences',
          our_qt_ref_no: 'QT-004188 v1',
          terms: '*Net 60 days',
        },
      }),
    );

    renderWorksheet();

    // The header block is the document. A name printed here that the CSV's Debtor row does
    // not carry would be the screen and the file disagreeing.
    expect(await screen.findAllByText('Not recorded')).toHaveLength(1);
    expect(screen.queryByText('Hong Bee Hardware Sdn Bhd')).not.toBeInTheDocument();
  });

  it('counts a single blocking finding in the singular', async () => {
    getSalesOrderWorksheet.mockResolvedValue(
      worksheet({
        can_export: false,
        findings: [
          {
            id: 'f1',
            severity: 'hard',
            code: 'line_arithmetic',
            detail: 'Line 4: 351 x 10.00 is 3,510.00 but the PO says 3,150.00.',
            line_no: 4,
          },
        ],
      }),
    );

    renderWorksheet();

    expect(await screen.findByText('1 finding stops the export')).toBeInTheDocument();
  });

  it('offers both exports when the server says the worksheet may leave', async () => {
    getSalesOrderWorksheet.mockResolvedValue(worksheet());

    renderWorksheet();

    const copy = await screen.findByRole('button', { name: /Copy for AutoCount/ });
    expect(copy).toBeEnabled();
    // A button, not a link: the file is fetched through the api client, because
    // `import_file_url` is a backend path that an anchor resolves against this origin.
    expect(screen.queryByRole('link', { name: /Download CSV/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Download CSV/ })).toBeEnabled();
  });

  it('fetches the CSV through the service and saves it under the name the backend gave', async () => {
    getSalesOrderWorksheet.mockResolvedValue(worksheet());
    downloadSalesOrderImportFile.mockResolvedValue({
      blob: new Blob(['csv']),
      filename: 'SO376200.csv',
    });

    renderWorksheet();

    fireEvent.click(await screen.findByRole('button', { name: /Download CSV/ }));

    await waitFor(() => expect(downloadSalesOrderImportFile).toHaveBeenCalledWith('so-1'));
    expect(saveBlobAs).toHaveBeenCalledTimes(1);
    expect(saveBlobAs.mock.calls[0][1]).toBe('SO376200.csv');
  });

  it('names the CSV after the provisional ref when the response names no file', async () => {
    getSalesOrderWorksheet.mockResolvedValue(worksheet());
    downloadSalesOrderImportFile.mockResolvedValue({
      blob: new Blob(['csv']),
      filename: null,
    });

    renderWorksheet();

    fireEvent.click(await screen.findByRole('button', { name: /Download CSV/ }));

    await waitFor(() => expect(saveBlobAs).toHaveBeenCalledTimes(1));
    expect(saveBlobAs.mock.calls[0][1]).toBe('PSO-000101.csv');
  });

  it('says why the CSV could not be downloaded rather than failing silently', async () => {
    getSalesOrderWorksheet.mockResolvedValue(worksheet());
    downloadSalesOrderImportFile.mockRejectedValue(new Error('That sales order was rebuilt'));

    renderWorksheet();

    fireEvent.click(await screen.findByRole('button', { name: /Download CSV/ }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('That sales order was rebuilt'));
    expect(saveBlobAs).not.toHaveBeenCalled();
  });

  it('refuses the export the server has not cleared, whatever the file url says', async () => {
    getSalesOrderWorksheet.mockResolvedValue(worksheet({ can_export: false }));

    renderWorksheet();

    const download = await screen.findByRole('button', { name: /Download CSV/ });
    expect(download).toBeDisabled();
    expect(download).toHaveAttribute('title', 'This worksheet cannot be exported yet');
    expect(downloadSalesOrderImportFile).not.toHaveBeenCalled();
  });

  it('refuses the export on a draft and says the publish is what is missing', async () => {
    getSalesOrderWorksheet.mockResolvedValue(
      worksheet({
        status: 'draft',
        autocount_doc_no: null,
        can_export: false,
        import_file_url: null,
      }),
    );

    renderWorksheet();

    const copy = await screen.findByRole('button', { name: /Copy for AutoCount/ });
    expect(copy).toBeDisabled();
    expect(copy).toHaveAttribute('title', 'Publish first');
    expect(screen.queryByRole('link', { name: /Download CSV/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Download CSV/ })).toBeDisabled();
  });

  it('refuses the export while a hard finding is unacknowledged and counts them', async () => {
    getSalesOrderWorksheet.mockResolvedValue(
      worksheet({
        can_export: false,
        findings: [
          {
            id: 'f1',
            severity: 'hard',
            code: 'line_arithmetic',
            detail: 'Line 4: 351 x 10.00 is 3,510.00 but the PO says 3,150.00.',
            line_no: 4,
          },
          {
            id: 'f2',
            severity: 'hard',
            code: 'schedule_short',
            detail: 'CB6645-NL: the schedule places 702 units but the PO orders 1,053.',
            line_no: 3,
          },
        ],
      }),
    );

    renderWorksheet();

    const copy = await screen.findByRole('button', { name: /Copy for AutoCount/ });
    expect(copy).toBeDisabled();
    expect(copy).toHaveAttribute('title', 'Fix the blocking findings first');
    expect(screen.getByText('2 findings stop the export')).toBeInTheDocument();
    expect(screen.getByText('Line 4')).toBeInTheDocument();
    // Still no warnings: the section states that rather than disappearing.
    expect(screen.getByText('No warnings.')).toBeInTheDocument();
  });

  it('lets an acknowledged hard finding through, because it no longer blocks', async () => {
    getSalesOrderWorksheet.mockResolvedValue(
      worksheet({
        findings: [
          {
            id: 'f1',
            severity: 'hard',
            code: 'line_arithmetic',
            detail: 'Line 4 does not add up.',
            line_no: 4,
            acknowledged_by_name: 'Eling',
            acknowledged_reason: 'Checked against the signed PO.',
            acknowledged_at: '2026-04-01T09:12:00',
          },
        ],
      }),
    );

    renderWorksheet();

    const copy = await screen.findByRole('button', { name: /Copy for AutoCount/ });
    expect(copy).toBeEnabled();
    expect(screen.getByText('No blocking findings.')).toBeInTheDocument();
  });

  it('shows a warning without treating it as a stop', async () => {
    getSalesOrderWorksheet.mockResolvedValue(
      worksheet({
        findings: [
          {
            id: 'f3',
            severity: 'warn',
            code: 'price_vs_quotation',
            detail: 'SRT382-6 is quoted at 13.20 and ordered at 13.77.',
            line_no: 2,
          },
        ],
      }),
    );

    renderWorksheet();

    expect(await screen.findByText('No blocking findings.')).toBeInTheDocument();
    expect(
      screen.getByText('SRT382-6 is quoted at 13.20 and ordered at 13.77.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Copy for AutoCount/ })).toBeEnabled();
  });

  it('states that a worksheet has no lines and points at the rebuild', async () => {
    getSalesOrderWorksheet.mockResolvedValue(
      worksheet({ lines: [], total_amount: '0.00', can_export: false }),
    );

    renderWorksheet();

    expect(await screen.findByText('This worksheet has no lines')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to the sales orders' })).toBeInTheDocument();
    // Every other block still renders: an empty document is still a document.
    expect(screen.getByText('Header fields')).toBeInTheDocument();
    expect(screen.getByText('No blocking findings.')).toBeInTheDocument();
    expect(screen.getByText('No warnings.')).toBeInTheDocument();
  });

  it('copies the raw document, not the formatted display values', async () => {
    getSalesOrderWorksheet.mockResolvedValue(worksheet());
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });

    renderWorksheet();

    fireEvent.click(await screen.findByRole('button', { name: /Copy for AutoCount/ }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText.mock.calls[0][0]).toBe(worksheetAsTabbedText(LINES));
  });
});

describe('worksheetAsTabbedText', () => {
  it('leads with AutoCount own columns, in AutoCount own order', () => {
    const [header] = worksheetAsTabbedText(LINES).split('\n');

    expect(header).toBe(
      'Item\tDescription\tReserve Qty\tQty\tDelivery Date\tUOM\tU/Price\tDisc.\tTotal',
    );
  });

  it('pastes the raw values, because AutoCount reads it and a person does not', () => {
    const [, first] = worksheetAsTabbedText(LINES).split('\n');

    // "600" and "11.16000", never "600 units" or "RM 11.16".
    expect(first).toBe(
      'CB6633\tCABANA S/STEEL FLOOR GRATING 6"\t0\t600\t2026-07-01\tUNIT\t11.16000\t\t6696.00',
    );
  });

  it('renders an absent date and an absent discount as the blank cell they are', () => {
    const [, , second] = worksheetAsTabbedText(LINES).split('\n');

    expect(second.split('\t')[4]).toBe('');
    expect(second.split('\t')[7]).toBe('');
  });

  it('is a header alone when the worksheet has no lines', () => {
    expect(worksheetAsTabbedText([]).split('\n')).toHaveLength(1);
  });
});
