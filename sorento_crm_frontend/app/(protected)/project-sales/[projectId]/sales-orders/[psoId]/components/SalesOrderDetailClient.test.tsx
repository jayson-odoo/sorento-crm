/**
 * P7 - the two tier gate on one draft.
 *
 * The decisions pinned here are the ones the gate exists for: a hard finding refuses publish
 * and says which line it is about, a warning publishes only once a reason is typed, and an
 * empty reason is refused rather than sent for the server to reject.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  ProjectSalesOrderDetail,
  ProjectSalesOrderFinding,
  ProjectSalesOrderLine,
} from '../../../../_shared/types/projectSalesOrder.types';

const getProjectSalesOrder = vi.fn();
const acknowledgeFinding = vi.fn();
const publishSalesOrder = vi.fn();
const regroupSalesOrder = vi.fn();
const downloadSalesOrderImportFile = vi.fn();
const saveBlobAs = vi.fn();
const toastError = vi.fn();

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: (...args: unknown[]) => toastError(...args) },
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/sales-orders/so-1',
  useSearchParams: () => new URLSearchParams(),
}));

/**
 * The pager's data. Mocked at the shared hook so no fetch is attempted and the arguments
 * the feature hook passes (the neighbours path, and the id) can be asserted.
 */
const recordNeighbours = vi.fn((..._args: unknown[]) => ({
  prevId: 'so-0',
  nextId: 'so-2',
  index: 2,
  total: 3,
  isLoading: false,
}));
vi.mock('@/hooks/useRecordNeighbours', () => ({
  useRecordNeighbours: (...args: unknown[]) => recordNeighbours(...args),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('../../../../_shared/services/projectSalesOrderService', () => ({
  PROJECT_SO_MOCK: false,
  listProjectSalesOrders: vi.fn(),
  buildSalesOrders: vi.fn(),
  getProjectSalesOrder: (...args: unknown[]) => getProjectSalesOrder(...args),
  acknowledgeFinding: (...args: unknown[]) => acknowledgeFinding(...args),
  updateSalesOrderLine: vi.fn(),
  regroupSalesOrder: (...args: unknown[]) => regroupSalesOrder(...args),
  publishSalesOrder: (...args: unknown[]) => publishSalesOrder(...args),
  downloadSalesOrderImportFile: (...args: unknown[]) => downloadSalesOrderImportFile(...args),
  previewAmendment: vi.fn(),
  createAmendment: vi.fn(),
  getAmendment: vi.fn(),
  publishAmendment: vi.fn(),
  listScheduleVersions: vi.fn(async () => []),
  listPoVersions: vi.fn(async () => []),
  salesOrderNeighboursPath: (projectId: string) =>
    `/api/v1/project-sales/projects/${projectId}/sales-orders/neighbours`,
}));

vi.mock('../../../../_shared/services/fileDownload', () => ({
  saveBlobAs: (...args: unknown[]) => saveBlobAs(...args),
  filenameFromContentDisposition: vi.fn(() => null),
}));

const listDivergences = vi.fn();
vi.mock('../../../../_shared/services/soDivergenceService', () => ({
  listDivergences: (...args: unknown[]) => listDivergences(...args),
  getDivergence: vi.fn(),
  ingestSalesOrderFile: vi.fn(),
  resolveDivergenceRow: vi.fn(),
  downloadCorrectiveImportFile: vi.fn(),
}));

let canEditProject = true;
vi.mock('../../../../_shared/hooks/useProjects', () => ({
  useProject: () => ({
    data: { id: 'p1', can_edit: canEditProject },
    isLoading: false,
    isError: false,
  }),
  usePurchaseOrders: () => ({ data: [], isLoading: false, isError: false }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { SalesOrderDetailClient } from './SalesOrderDetailClient';

const LINES: ProjectSalesOrderLine[] = [
  {
    id: 'l1',
    line_no: 1,
    product_code: 'CB6633',
    description: 'CABANA S/STEEL FLOOR GRATING 6"',
    qty: '600',
    uom: 'UNIT',
    unit_price: '11.16000',
    amount: '6696.00',
    delivery_date: '2026-07-01',
    phase_label: 'Level 2 & 7',
    explosion_source: 'none',
    source_po_line_no: 1,
  },
  {
    id: 'l2',
    line_no: 2,
    product_code: 'SRT382-6',
    description: 'SORENTO STAINLESS STEEL FLOOR GRATING 6" x 6"',
    qty: '135',
    uom: 'UNIT',
    unit_price: '13.77000',
    amount: '1858.95',
    delivery_date: '2026-07-01',
    phase_label: 'Level 2 & 7',
    explosion_source: 'none',
    source_po_line_no: 2,
  },
];

const HARD: ProjectSalesOrderFinding = {
  id: 'f-hard',
  severity: 'hard',
  code: 'line_arithmetic',
  detail: 'Line 1: 600 x 11.16 is 6,696.00 but the PO says 6,690.00.',
  line_id: 'l1',
  line_no: 1,
};

const WARN: ProjectSalesOrderFinding = {
  id: 'f-warn',
  severity: 'warn',
  code: 'price_vs_quotation',
  detail: 'SRT382-6 is quoted at 13.20 and ordered at 13.77.',
  line_id: 'l2',
  line_no: 2,
};

function detail(overrides: Partial<ProjectSalesOrderDetail> = {}): ProjectSalesOrderDetail {
  return {
    id: 'so-1',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: null,
    area_group: 'TOWER',
    status: 'draft',
    grouping_origin: 'area',
    line_count: LINES.length,
    total_amount: '8554.95',
    hard_findings: 0,
    warn_findings: 0,
    is_pre_order: false,
    is_sponsorship: false,
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    created_at: '2026-04-02T02:15:00',
    lines: LINES,
    findings: [],
    ...overrides,
  };
}

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrderDetailClient projectId="p1" psoId="so-1" />
    </QueryClientProvider>,
  );
}

function openDivergence(overrides: Record<string, unknown> = {}) {
  return {
    data: [
      {
        id: 'd1',
        project_sales_order_id: 'so-1',
        project_id: 'p1',
        project_title: 'Tuju Residences',
        sales_order_ref: 'SO397450',
        provisional_ref: 'PSO-000123',
        autocount_doc_no: 'SO397450',
        status: 'open',
        compared_count: 52,
        agreeing_count: 48,
        differing_count: 4,
        unresolved_count: 4,
        corrective_publish_required: false,
        detected_at: '2026-08-01T02:00:00',
        resolved_at: null,
        age_days: 3,
        ...overrides,
      },
    ],
    total: 1,
    page: 1,
    limit: 100,
  };
}

/**
 * Into the gear, which is where everything that is not the one call to action now lives.
 * Radix opens its menus on pointerdown, which fireEvent.click does not send.
 */
async function openGear() {
  fireEvent.pointerDown(
    await screen.findByRole('button', { name: 'Sales order actions' }),
    { button: 0, ctrlKey: false },
  );
  return within(await screen.findByRole('menu'));
}

beforeEach(() => {
  vi.clearAllMocks();
  canEditProject = true;
  // Default: AutoCount agrees, so the amend path is open.
  listDivergences.mockResolvedValue({ data: [], total: 0, page: 1, limit: 100 });
  recordNeighbours.mockReturnValue({
    prevId: 'so-0',
    nextId: 'so-2',
    index: 2,
    total: 3,
    isLoading: false,
  });
});

describe('SalesOrderDetailClient', () => {
  it('renders a skeleton while loading, not an empty draft', () => {
    getProjectSalesOrder.mockReturnValue(new Promise(() => {}));

    renderDetail();

    expect(screen.queryByText('PSO-000123')).not.toBeInTheDocument();
    expect(screen.queryByText('Blocking')).not.toBeInTheDocument();
  });

  it('says why a draft could not be loaded and offers a way back', async () => {
    getProjectSalesOrder.mockRejectedValue(new Error('That draft was rebuilt'));

    renderDetail();

    expect(await screen.findByText('This sales order could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('That draft was rebuilt')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to sales orders' })).toBeInTheDocument();
  });

  it('states that nothing is blocking and no warnings stand, rather than hiding the sections', async () => {
    getProjectSalesOrder.mockResolvedValue(detail());

    renderDetail();

    expect(await screen.findByText('Nothing is blocking this sales order.')).toBeInTheDocument();
    expect(screen.getByText('No warnings on this sales order.')).toBeInTheDocument();
    expect(screen.getByText('Nothing else to note.')).toBeInTheDocument();
    // The lines are summed as decimals and shown beside the header total.
    expect(screen.getAllByText('RM 8,554.95').length).toBeGreaterThan(0);
  });

  it('refuses to publish while a hard finding stands, and lists what blocks it', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({ status: 'blocked', hard_findings: 1, findings: [HARD] }),
    );

    renderDetail();

    expect(
      await screen.findByText(
        'Publishing is refused: 1 finding must be fixed or overridden.',
      ),
    ).toBeInTheDocument();
    // The sentence the backend wrote, not the code.
    expect(screen.getAllByText(HARD.detail).length).toBeGreaterThan(0);
    expect(screen.queryByText('line_arithmetic')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText('Publishing is refused')).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();
    expect(publishSalesOrder).not.toHaveBeenCalled();
  });

  it('anchors a blocking finding to its line', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({ status: 'blocked', hard_findings: 1, findings: [HARD] }),
    );

    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: 'Show line 1' }));

    // The table narrows to that line; the other line is out of the way.
    expect(screen.getByRole('button', { name: 'Show all lines' })).toBeInTheDocument();
    expect(screen.queryByText('SRT382-6')).not.toBeInTheDocument();
  });

  it('refuses an empty acknowledgement and sends the typed reason', async () => {
    getProjectSalesOrder.mockResolvedValue(detail({ warn_findings: 1, findings: [WARN] }));
    acknowledgeFinding.mockResolvedValue(detail());

    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: 'Clear with a reason' }));

    const dialog = await screen.findByRole('dialog');
    const record = within(dialog).getByRole('button', { name: 'Record the reason' });
    expect(record).toBeDisabled();

    // Whitespace is not a reason.
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: '   ' } });
    expect(within(dialog).getByRole('button', { name: 'Record the reason' })).toBeDisabled();
    expect(acknowledgeFinding).not.toHaveBeenCalled();

    fireEvent.change(within(dialog).getByLabelText(/Reason/), {
      target: { value: 'Customer agreed the revised price on 01/04.' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Record the reason' }));

    await waitFor(() =>
      expect(acknowledgeFinding).toHaveBeenCalledWith(
        'so-1',
        'f-warn',
        'Customer agreed the revised price on 01/04.',
      ),
    );
  });

  it('publishes once the warning carries a reason, and shows the reference and the file', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({
        warn_findings: 1,
        findings: [
          {
            ...WARN,
            acknowledged_by_name: 'Eling',
            acknowledged_reason: 'Customer agreed the revised price on 01/04.',
            acknowledged_at: '2026-04-01T09:12:00',
          },
        ],
      }),
    );
    publishSalesOrder.mockResolvedValue({
      status: 'published',
      provisional_ref: 'PSO-000123',
      autocount_doc_no: 'SO397450',
      import_file_url: 'https://example.test/import.csv',
      can_export: true,
    });

    renderDetail();

    // The reason stays on the sales order with the name against it.
    expect(await screen.findByText('Cleared by Eling')).toBeInTheDocument();
    expect(
      screen.getByText('Customer agreed the revised price on 01/04.'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText('Publish PSO-000123?')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish' }));

    await waitFor(() => expect(publishSalesOrder).toHaveBeenCalledWith('so-1'));
    expect(await screen.findByText('This sales order is SO397450.')).toBeInTheDocument();

    // Fetched through the service, not linked to: the url is a backend path and an anchor
    // would resolve it against this origin.
    downloadSalesOrderImportFile.mockResolvedValue({
      blob: new Blob(['csv']),
      filename: 'SO397450.csv',
    });
    fireEvent.click(screen.getByRole('button', { name: 'Download the import file' }));

    await waitFor(() => expect(downloadSalesOrderImportFile).toHaveBeenCalledWith('so-1'));
    expect(saveBlobAs.mock.calls[0][1]).toBe('SO397450.csv');
  });

  it('names the warnings that have no reason before an irreversible publish', async () => {
    getProjectSalesOrder.mockResolvedValue(detail({ warn_findings: 1, findings: [WARN] }));

    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: 'Publish' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(
      within(dialog).getByText('1 warning has no reason recorded:'),
    ).toBeInTheDocument();
  });

  it('takes a hard override through a second, explicit confirmation', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({ status: 'blocked', hard_findings: 1, findings: [HARD] }),
    );
    acknowledgeFinding.mockResolvedValue(detail());

    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: 'Override with a reason' }));

    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Reason/), {
      target: { value: 'PO amount is a typo, confirmed by email 02/04.' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Override' }));

    const confirm = await screen.findByRole('alertdialog');
    expect(within(confirm).getByText('Publish past a hard stop?')).toBeInTheDocument();
    expect(acknowledgeFinding).not.toHaveBeenCalled();

    fireEvent.click(within(confirm).getByRole('button', { name: 'Override and record' }));

    await waitFor(() =>
      expect(acknowledgeFinding).toHaveBeenCalledWith(
        'so-1',
        'f-hard',
        'PO amount is a typo, confirmed by email 02/04.',
      ),
    );
  });

  it('hides the write controls on a published order', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({
        status: 'published',
        autocount_doc_no: 'SO397450',
        published_at: '2026-04-02T03:00:00',
        import_file_url: 'https://example.test/import.csv',
      }),
    );

    renderDetail();

    // Twice on purpose: the page heading and the AutoCount document field.
    expect(await screen.findAllByText('SO397450')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();

    const gear = await openGear();
    expect(gear.queryByRole('menuitem', { name: /Move lines/ })).not.toBeInTheDocument();
    // The export survives publication - it is how the order reaches AutoCount.
    expect(gear.getByRole('menuitem', { name: /Import file/ })).toBeInTheDocument();
  });

  it('refuses the import file the server has not cleared, whatever the url says', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({
        status: 'published',
        autocount_doc_no: 'SO397450',
        // Published, so the file has an address; blocked, so it may not be taken. The
        // route 422s this fetch, and the button has to say so before it is clicked.
        import_file_url: '/api/v1/project-sales/sales-orders/so-1/import-file',
        can_export: false,
        hard_findings: 1,
        findings: [HARD],
      }),
    );

    renderDetail();

    const gear = await openGear();
    const item = gear.getByRole('menuitem', { name: /Import file/ });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    // The reason is on the item, not in a tooltip: a hover cannot be read on a phone.
    expect(within(item).getByText('Clear the blocking findings first')).toBeInTheDocument();
    expect(downloadSalesOrderImportFile).not.toHaveBeenCalled();
  });

  it('offers the import file when the server has cleared the export', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({
        status: 'published',
        autocount_doc_no: 'SO397450',
        import_file_url: '/api/v1/project-sales/sales-orders/so-1/import-file',
        can_export: true,
      }),
    );

    renderDetail();

    const gear = await openGear();
    expect(gear.getByRole('menuitem', { name: /Import file/ })).not.toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });

  it('fetches the import file through the service and names it as the backend did', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({
        status: 'published',
        autocount_doc_no: 'SO397450',
        // No `can_export`: a row cached from before the field shipped falls back to the
        // url being there, which is what the button used to go on.
        import_file_url: '/api/v1/project-sales/sales-orders/so-1/import-file',
      }),
    );
    downloadSalesOrderImportFile.mockResolvedValue({
      blob: new Blob(['csv']),
      filename: 'SO397450.csv',
    });

    renderDetail();

    fireEvent.click((await openGear()).getByRole('menuitem', { name: /Import file/ }));

    await waitFor(() => expect(downloadSalesOrderImportFile).toHaveBeenCalledWith('so-1'));
    expect(saveBlobAs).toHaveBeenCalledTimes(1);
    expect(saveBlobAs.mock.calls[0][1]).toBe('SO397450.csv');
  });

  it('falls back to the provisional reference when the response names no file', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({
        status: 'published',
        import_file_url: '/api/v1/project-sales/sales-orders/so-1/import-file',
      }),
    );
    downloadSalesOrderImportFile.mockResolvedValue({
      blob: new Blob(['csv']),
      filename: null,
    });

    renderDetail();

    fireEvent.click((await openGear()).getByRole('menuitem', { name: /Import file/ }));

    await waitFor(() => expect(saveBlobAs).toHaveBeenCalledTimes(1));
    expect(saveBlobAs.mock.calls[0][1]).toBe('PSO-000123.csv');
  });

  it('says why the import file could not be downloaded', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({
        status: 'published',
        import_file_url: '/api/v1/project-sales/sales-orders/so-1/import-file',
      }),
    );
    downloadSalesOrderImportFile.mockRejectedValue(new Error('That order was rebuilt'));

    renderDetail();

    fireEvent.click((await openGear()).getByRole('menuitem', { name: /Import file/ }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('That order was rebuilt'));
    expect(saveBlobAs).not.toHaveBeenCalled();
  });

  it('re-splits the lines and says once that the shape is remembered', async () => {
    getProjectSalesOrder.mockResolvedValue(detail());
    regroupSalesOrder.mockResolvedValue({ data: [], total: 0, page: 1, limit: 25 });

    renderDetail();

    fireEvent.click((await openGear()).getByRole('menuitem', { name: /Move lines/ }));

    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByText(
        'The shape you publish is remembered for this customer and proposed on their next purchase order.',
      ),
    ).toBeInTheDocument();

    fireEvent.click(within(dialog).getByLabelText('Select line 2'));
    fireEvent.change(within(dialog).getByLabelText('Select a group'), {
      target: { value: '__new__' },
    });
    fireEvent.change(within(dialog).getByLabelText('New group name'), {
      target: { value: 'COMMON AREA' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: /Move 1/ }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Re-split' }));

    const confirm = await screen.findByRole('alertdialog');
    fireEvent.click(within(confirm).getByRole('button', { name: 'Re-split' }));

    await waitFor(() =>
      expect(regroupSalesOrder).toHaveBeenCalledWith('so-1', [
        { area_group: 'TOWER', line_ids: ['l1'] },
        { area_group: 'COMMON AREA', line_ids: ['l2'] },
      ]),
    );
  });

  // ---------------------------------------------------------------- P8a (AC-N5)

  it('blocks the revision review while AutoCount is unreconciled', async () => {
    getProjectSalesOrder.mockResolvedValue(detail({ status: 'published' }));
    listDivergences.mockResolvedValue(openDivergence());

    renderDetail();

    // Disabled rather than hidden: an item that vanished teaches nobody why.
    const gear = await openGear();
    const amend = gear.getByRole('menuitem', { name: /review a revision/i });
    expect(amend).toHaveAttribute('aria-disabled', 'true');
    // Not a link at all while it is refused: there is nowhere for it to go.
    expect(amend).not.toHaveAttribute('href');
  });

  it('says how many rows differ and how long they have waited', async () => {
    getProjectSalesOrder.mockResolvedValue(detail({ status: 'published' }));
    listDivergences.mockResolvedValue(openDivergence());

    renderDetail();

    expect(await screen.findByText(/autocount disagrees on 4 rows/i)).toBeInTheDocument();
    expect(screen.getByText(/waiting 3 days/i)).toBeInTheDocument();
    expect(screen.getByText(/our values are unchanged/i)).toBeInTheDocument();
  });

  it('offers a way to the reconciliation screen', async () => {
    getProjectSalesOrder.mockResolvedValue(detail({ status: 'published' }));
    listDivergences.mockResolvedValue(openDivergence());

    renderDetail();

    const link = await screen.findByRole('link', { name: /^reconcile$/i });
    expect(link).toHaveAttribute('href', '/project-sales/p1/sales-orders/so-1/divergence');
  });

  it('leaves the revision review reachable when AutoCount agrees', async () => {
    getProjectSalesOrder.mockResolvedValue(detail({ status: 'published' }));

    renderDetail();

    // `asChild` puts the menuitem role on the anchor itself, so the item IS the link.
    const gear = await openGear();
    expect(gear.getByRole('menuitem', { name: /review a revision/i })).toHaveAttribute(
      'href',
      '/project-sales/p1/sales-orders/so-1/revisions',
    );
    expect(screen.queryByText(/autocount disagrees/i)).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------- Stage 1B (AC-A03)

  it('shows the review state pill beside the status once the backend has derived one', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({ review_state: 'awaiting_reconciliation', exception_count: 2 }),
    );

    renderDetail();

    expect(
      await screen.findByText('Awaiting reconciliation · 2 exceptions'),
    ).toBeInTheDocument();
  });

  it('renders no review state pill until the backend derives one', async () => {
    getProjectSalesOrder.mockResolvedValue(detail());

    renderDetail();

    await screen.findAllByText('PSO-000123');
    expect(screen.queryByText('Needs CS review')).not.toBeInTheDocument();
    expect(screen.queryByText('Awaiting reconciliation')).not.toBeInTheDocument();
  });
});

/**
 * The header standard: ONE call to action, everything else behind the gear, and a pager.
 *
 * The client's words about the five buttons this replaced: "too many buttons up here, need a
 * call to action, then the reset just put inside the gear". So what is pinned is that the
 * screen never offers two things at once, that the one it does offer is the one the status is
 * waiting for, and that nothing was dropped on the way into the menu.
 */
describe('SalesOrderDetailClient header', () => {
  /** Every action that used to stand in the header, by the role it would have out here. */
  function expectNoLooseActions() {
    expect(screen.queryByRole('link', { name: 'Worksheet' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move lines' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Import file' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Order inquiry' })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /review a revision/i }),
    ).not.toBeInTheDocument();
  }

  it('offers Publish, and nothing else, on a draft somebody may edit', async () => {
    getProjectSalesOrder.mockResolvedValue(detail());

    renderDetail();

    expect(await screen.findByRole('button', { name: 'Publish' })).toBeInTheDocument();
    expectNoLooseActions();
    expect(
      screen.queryByRole('link', { name: /compare with autocount/i }),
    ).not.toBeInTheDocument();
  });

  it('offers Compare with AutoCount on a published order, and no Publish', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({ status: 'published', autocount_doc_no: 'SO397450' }),
    );

    renderDetail();

    const cta = await screen.findByRole('link', { name: /compare with autocount/i });
    expect(cta).toHaveAttribute('href', '/project-sales/p1/sales-orders/so-1/divergence');
    expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();
    expectNoLooseActions();
  });

  it('renames the call to action Reconcile while AutoCount disagrees', async () => {
    getProjectSalesOrder.mockResolvedValue(detail({ status: 'published' }));
    listDivergences.mockResolvedValue(openDivergence());

    renderDetail();

    const cta = await screen.findByRole('link', { name: /reconcile autocount/i });
    expect(cta).toHaveAttribute('href', '/project-sales/p1/sales-orders/so-1/divergence');
  });

  it('falls back to the worksheet for a reader, who can neither publish nor reconcile', async () => {
    canEditProject = false;
    getProjectSalesOrder.mockResolvedValue(detail());

    renderDetail();

    const cta = await screen.findByRole('link', { name: 'Worksheet' });
    expect(cta).toHaveAttribute('href', '/project-sales/p1/sales-orders/so-1/worksheet');
    expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();

    // It is the call to action, so it is not ALSO a menu item.
    const gear = await openGear();
    expect(gear.queryByRole('menuitem', { name: 'Worksheet' })).not.toBeInTheDocument();
    // A reader may not edit or delete, so neither is offered.
    expect(gear.queryByRole('menuitem', { name: /Edit this sales order/ })).toBeNull();
    expect(gear.queryByRole('menuitem', { name: /Delete this sales order/ })).toBeNull();
    // The menu still has the revision review in it, so it is never an empty gear.
    expect(gear.getByRole('menuitem', { name: /review a revision/i })).toBeInTheDocument();
  });

  it('keeps every other action in the gear', async () => {
    getProjectSalesOrder.mockResolvedValue(detail());

    renderDetail();

    const gear = await openGear();
    expect(gear.getByRole('menuitem', { name: 'Worksheet' })).toHaveAttribute(
      'href',
      '/project-sales/p1/sales-orders/so-1/worksheet',
    );
    expect(gear.getByRole('menuitem', { name: /review a revision/i })).toBeInTheDocument();
    expect(gear.getByRole('menuitem', { name: /Move lines/ })).toBeInTheDocument();
    expect(gear.getByRole('menuitem', { name: /Edit this sales order/ })).toBeInTheDocument();
    // Destructive last.
    const items = gear.getAllByRole('menuitem');
    expect(items[items.length - 1]).toHaveTextContent('Delete this sales order');
  });

  it('walks the project sales orders without going back to the list', async () => {
    getProjectSalesOrder.mockResolvedValue(detail());

    renderDetail();

    await screen.findAllByText('PSO-000123');
    // The pager reads the project's own sequence, for THIS order.
    expect(recordNeighbours).toHaveBeenCalledWith(
      '/api/v1/project-sales/projects/p1/sales-orders/neighbours',
      'so-1',
    );
    expect(screen.getByText('2 / 3')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Next sales order' }));

    expect(push).toHaveBeenCalledWith('/project-sales/p1/sales-orders/so-2');
  });
});
