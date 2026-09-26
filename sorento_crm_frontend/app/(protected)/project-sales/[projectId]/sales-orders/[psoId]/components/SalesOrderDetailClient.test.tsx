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
const unpublishSalesOrder = vi.fn();
const bulkSetLinesStockLocation = vi.fn();
const regroupSalesOrder = vi.fn();
const downloadSalesOrderImportFile = vi.fn();
const saveBlobAs = vi.fn();
const toastError = vi.fn();
const listScheduleFindings = vi.fn();
const acknowledgeScheduleFinding = vi.fn();
const listScheduleVersions = vi.fn();

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: (...args: unknown[]) => toastError(...args) },
}));

const push = vi.fn();
let originParam: string | null = null;
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/sales-orders/so-1',
  useSearchParams: () => new URLSearchParams(originParam ? { from: originParam } : ''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('../../../../_shared/services/projectSalesOrderService', () => ({
  PROJECT_SO_MOCK: false,
  // The pager fetches the page the URL names through this (S3-05).
  listProjectSalesOrders: vi.fn(async () => ({
    data: [{ id: 'so-0' }, { id: 'so-1' }, { id: 'so-2' }],
    total: 3,
    page: 1,
    limit: 25,
  })),
  buildSalesOrders: vi.fn(),
  getProjectSalesOrder: (...args: unknown[]) => getProjectSalesOrder(...args),
  acknowledgeFinding: (...args: unknown[]) => acknowledgeFinding(...args),
  updateSalesOrderLine: vi.fn(),
  regroupSalesOrder: (...args: unknown[]) => regroupSalesOrder(...args),
  publishSalesOrder: (...args: unknown[]) => publishSalesOrder(...args),
  unpublishSalesOrder: (...args: unknown[]) => unpublishSalesOrder(...args),
  bulkSetLinesStockLocation: (...args: unknown[]) => bulkSetLinesStockLocation(...args),
  downloadSalesOrderImportFile: (...args: unknown[]) => downloadSalesOrderImportFile(...args),
  previewAmendment: vi.fn(),
  createAmendment: vi.fn(),
  getAmendment: vi.fn(),
  publishAmendment: vi.fn(),
  listScheduleVersions: (...args: unknown[]) => listScheduleVersions(...args),
  listScheduleFindings: (...args: unknown[]) => listScheduleFindings(...args),
  acknowledgeScheduleFinding: (...args: unknown[]) => acknowledgeScheduleFinding(...args),
  listPoVersions: vi.fn(async () => []),
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
    data: { id: 'p1', title: 'Setia Alam', project_code: 'PRJ-000001', can_edit: canEditProject },
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
  originParam = null;
  canEditProject = true;
  // Default: AutoCount agrees, so the amend path is open.
  listDivergences.mockResolvedValue({ data: [], total: 0, page: 1, limit: 100 });
  listScheduleFindings.mockResolvedValue([]);
  listScheduleVersions.mockResolvedValue([]);
});

/** A row's Flag pill opens its popover; the finding and its Dismiss live there (lesson (b)). */
async function openFlag(name: RegExp) {
  fireEvent.click(await screen.findByRole('button', { name }));
  return within(await screen.findByRole('dialog'));
}

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

  it('shows every line and no gate count when nothing is open', async () => {
    getProjectSalesOrder.mockResolvedValue(detail());

    renderDetail();

    expect(await screen.findByText('SRT382-6')).toBeInTheDocument();
    expect(screen.getByText('CB6633')).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: /Need attention/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/block(s)? publish$/)).not.toBeInTheDocument();
    // The lines are summed as decimals and shown beside the header total.
    expect(screen.getAllByText('RM 8,554.95').length).toBeGreaterThan(0);
  });

  it('refuses to publish while a hard finding stands, and lists what blocks it', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({ status: 'blocked', hard_findings: 1, findings: [HARD] }),
    );

    renderDetail();

    // S7-1: the count under Publish replaces the refusal banner.
    expect(await screen.findByText('1 blocks publish')).toBeInTheDocument();
    expect(screen.queryByText(/Publishing is refused:/)).not.toBeInTheDocument();
    // The sentence the backend wrote, not the code.
    const flag = await openFlag(/Blocks publish on line 1/);
    expect(flag.getByText(HARD.detail)).toBeInTheDocument();
    expect(screen.queryByText('line_arithmetic')).not.toBeInTheDocument();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });

    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText('Publishing is refused')).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();
    expect(publishSalesOrder).not.toHaveBeenCalled();
  });

  it('anchors a blocking finding to its line, and opens on Need attention (lesson (c))', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({ status: 'blocked', hard_findings: 1, findings: [HARD] }),
    );

    renderDetail();

    const attention = await screen.findByRole('radio', { name: 'Need attention (1)' });
    expect(attention).toHaveAttribute('data-state', 'on');
    const row = screen.getByText('CB6633').closest('tr') as HTMLElement;
    expect(within(row).getByText('Blocks publish')).toBeInTheDocument();
    expect(screen.queryByText('SRT382-6')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', { name: 'All lines (2)' }));
    expect(screen.getByText('SRT382-6')).toBeInTheDocument();
  });

  it('refuses an empty acknowledgement and sends the typed reason', async () => {
    getProjectSalesOrder.mockResolvedValue(detail({ warn_findings: 1, findings: [WARN] }));
    acknowledgeFinding.mockResolvedValue(detail());

    renderDetail();

    const flag = await openFlag(/Needs acknowledgement on line 2/);
    fireEvent.click(flag.getByRole('button', { name: 'Dismiss with a reason' }));

    const dialog = await screen.findByRole('dialog', { name: /Dismiss with a reason/ });
    const record = within(dialog).getByRole('button', { name: 'Dismiss 1' });
    expect(record).toBeDisabled();

    // Whitespace is not a reason.
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: '   ' } });
    expect(within(dialog).getByRole('button', { name: 'Dismiss 1' })).toBeDisabled();
    expect(acknowledgeFinding).not.toHaveBeenCalled();

    fireEvent.change(within(dialog).getByLabelText(/Reason/), {
      target: { value: 'Customer agreed the revised price on 01/04.' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Dismiss 1' }));

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

    // The reason stays on the sales order with the name against it, one click into the Flag.
    const flag = await openFlag(/Dismissed on line 2/);
    expect(
      flag.getByText('Eling: Customer agreed the revised price on 01/04.'),
    ).toBeInTheDocument();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });

    fireEvent.click(await screen.findByRole('button', { name: 'Publish' }));

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

  it('returns to the origin once Done is clicked after a successful Publish, when it carries one (S4-2)', async () => {
    originParam = '/project-sales/p1?tab=sales-orders';
    getProjectSalesOrder.mockResolvedValue(detail());
    publishSalesOrder.mockResolvedValue({
      status: 'published',
      provisional_ref: 'PSO-000123',
      autocount_doc_no: 'SO397450',
      can_export: true,
    });

    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: 'Publish' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish' }));

    await waitFor(() => expect(publishSalesOrder).toHaveBeenCalledWith('so-1'));
    fireEvent.click(await screen.findByRole('button', { name: 'Done' }));

    expect(push).toHaveBeenCalledWith('/project-sales/p1?tab=sales-orders');
  });

  it('stays on the page once Done is clicked with no origin (S4-3)', async () => {
    originParam = null;
    getProjectSalesOrder.mockResolvedValue(detail());
    publishSalesOrder.mockResolvedValue({
      status: 'published',
      provisional_ref: 'PSO-000123',
      autocount_doc_no: 'SO397450',
      can_export: true,
    });

    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: 'Publish' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish' }));

    await waitFor(() => expect(publishSalesOrder).toHaveBeenCalledWith('so-1'));
    fireEvent.click(await screen.findByRole('button', { name: 'Done' }));

    expect(push).not.toHaveBeenCalled();
  });

  it('never navigates to a crafted external `from` (S1, open redirect)', async () => {
    originParam = 'https://elsewhere.test/steal-session';
    getProjectSalesOrder.mockResolvedValue(detail());
    publishSalesOrder.mockResolvedValue({
      status: 'published',
      provisional_ref: 'PSO-000123',
      autocount_doc_no: 'SO397450',
      can_export: true,
    });

    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: 'Publish' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish' }));

    await waitFor(() => expect(publishSalesOrder).toHaveBeenCalledWith('so-1'));
    fireEvent.click(await screen.findByRole('button', { name: 'Done' }));

    expect(push).not.toHaveBeenCalled();
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

  it('dismisses a hard finding through the same one-step dialog as a warning', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({ status: 'blocked', hard_findings: 1, findings: [HARD] }),
    );
    acknowledgeFinding.mockResolvedValue(detail());

    renderDetail();

    const flag = await openFlag(/Blocks publish on line 1/);
    fireEvent.click(flag.getByRole('button', { name: 'Dismiss with a reason' }));

    const dialog = await screen.findByRole('dialog', { name: /Dismiss with a reason/ });
    expect(within(dialog).getByText('Blocks publish')).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText(/Reason/), {
      target: { value: 'PO amount is a typo, confirmed by email 02/04.' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Dismiss 1' }));

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

  it('offers Unpublish on a published order, and it is absent from a draft', async () => {
    getProjectSalesOrder.mockResolvedValue(detail({ status: 'draft' }));
    renderDetail();
    let gear = await openGear();
    expect(gear.queryByRole('menuitem', { name: 'Unpublish' })).not.toBeInTheDocument();

    getProjectSalesOrder.mockResolvedValue(
      detail({ status: 'published', autocount_doc_no: 'SO397450' }),
    );
    renderDetail();
    gear = await openGear();
    expect(gear.getByRole('menuitem', { name: 'Unpublish' })).toBeInTheDocument();
  });

  it('unpublishes an order once the confirm dialog is accepted, and names it in the ask', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({ status: 'published', autocount_doc_no: 'SO397450' }),
    );
    unpublishSalesOrder.mockResolvedValue({ status: 'draft', provisional_ref: 'PSO-000123' });

    renderDetail();
    const gear = await openGear();
    fireEvent.click(gear.getByRole('menuitem', { name: 'Unpublish' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText('Unpublish SO397450?')).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Unpublish' }));

    await waitFor(() => expect(unpublishSalesOrder).toHaveBeenCalledWith('so-1'));
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

    // Published with nothing open: the AutoCount differences tab is the one that opens.
    expect(await screen.findByText(/autocount disagrees on 4 rows/i)).toBeInTheDocument();
    expect(screen.getByText(/waiting 3 days/i)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'AutoCount differences (4)' })).toHaveAttribute(
      'data-state',
      'active',
    );
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

  it('S3-03: walks the page of project sales orders the URL names', async () => {
    getProjectSalesOrder.mockResolvedValue(detail());

    renderDetail();

    await screen.findAllByText('PSO-000123');
    await waitFor(() => expect(screen.getByText('2 / 3')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Next sales order' }));

    // The step names the page the record sits on, so the walk survives it.
    expect(push).toHaveBeenCalledWith(
      '/project-sales/p1/sales-orders/so-2?page=1&limit=50&from=so-2',
    );
  });

  /**
   * The pager stands down for the duration of an edit session, the same way the quotation
   * document's does, and for the same reason: the staged work would in fact survive a step away,
   * but a Next sitting beside Cancel and Save reads like it will discard it, and a control
   * nobody dares press is worse than one that is absent.
   */
  it('stands the pager down while an edit session is open, and brings it back on Cancel', async () => {
    getProjectSalesOrder.mockResolvedValue(detail());

    renderDetail();

    expect(await screen.findByRole('button', { name: 'Next sales order' })).toBeInTheDocument();

    const gear = await openGear();
    fireEvent.click(gear.getByRole('menuitem', { name: /Edit this sales order/ }));
    await screen.findByRole('button', { name: 'Save sales order' });

    expect(screen.queryByRole('button', { name: 'Next sales order' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Previous sales order' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(await screen.findByRole('button', { name: 'Next sales order' })).toBeInTheDocument();
  });
});

/**
 * S7: the sales order review screen (`mockups/sales-order-review.html`). One lines table with
 * the order's and the schedule's findings on its rows, two tabs, the gate stated once under
 * Publish by the same rule the server refuses with.
 */
describe('SalesOrderDetailClient, the S7 review screen', () => {
  const PAIR = { purchase_order_id: 'po-1', schedule_version_id: 'sv-2' };
  const SHORT: ProjectSalesOrderFinding = {
    id: 'f-short',
    severity: 'hard',
    code: 'schedule_short',
    detail: 'CB6633: the PO orders 600 but the schedule only places 0.',
    line_id: 'l1',
    line_no: 1,
    detail_json: { product_code: 'CB6633' },
  };
  const COLUMN: ProjectSalesOrderFinding = {
    id: 's-column',
    severity: 'hard',
    code: 'unresolved_product',
    detail: "The schedule column 'BUI-HB-CB6633SS' is not mapped to a product.",
    detail_json: { customer_code_raw: 'BUI-HB-CB6633SS' },
  };
  const OVER: ProjectSalesOrderFinding = {
    id: 's-over',
    severity: 'hard',
    code: 'schedule_over',
    detail: 'The schedule asks for 40 of ZZ900, which is not on this purchase order at all.',
    detail_json: { product_code: 'ZZ900' },
  };

  it('S7-1: the meta line names the project, the area group, the customer PO version and Activity', async () => {
    listScheduleVersions.mockResolvedValue([{ id: 'sv-2', version_no: 2, po_version_no: 1 }]);
    getProjectSalesOrder.mockResolvedValue(detail(PAIR));

    renderDetail();

    expect(
      await screen.findByText(
        /Setia Alam \(PRJ-000001\) · Area group TOWER · Customer PO HQ\/26\/01\/121 v1/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View activity' })).toHaveAttribute(
      'href',
      '/project-sales/p1?tab=activity',
    );
    expect(screen.queryByRole('tab', { name: /Activity/ })).not.toBeInTheDocument();
  });

  it('S7-2: two tabs, Lines and AutoCount differences, and no Findings tab', async () => {
    getProjectSalesOrder.mockResolvedValue(detail({ findings: [HARD] }));

    renderDetail();

    await screen.findByText('CB6633');
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Lines',
      'AutoCount differences',
    ]);
    expect(screen.getByRole('tab', { name: 'Lines' })).toHaveAttribute('data-state', 'active');
    expect(screen.queryByRole('tab', { name: /Findings/ })).not.toBeInTheDocument();
  });

  it('S7-3: a schedule finding naming no line is a row of the same table, naming its source', async () => {
    listScheduleFindings.mockResolvedValue([OVER]);
    getProjectSalesOrder.mockResolvedValue(detail(PAIR));

    renderDetail();

    const row = (await screen.findByText('ZZ900')).closest('tr') as HTMLElement;
    expect(within(row).getByText('Blocks publish')).toBeInTheDocument();
    const flag = await openFlag(/Blocks publish on ZZ900/);
    expect(flag.getByText('Schedule')).toBeInTheDocument();
    expect(flag.getByText(OVER.detail)).toBeInTheDocument();
    // No separate schedule findings card any more (S3-6).
    expect(screen.queryByText('Schedule / PO findings')).not.toBeInTheDocument();
  });

  it('R23: the unmapped column and the short it causes are one row, cleared with one Dismiss', async () => {
    listScheduleFindings.mockResolvedValue([COLUMN]);
    acknowledgeFinding.mockResolvedValue(detail(PAIR));
    acknowledgeScheduleFinding.mockResolvedValue({});
    getProjectSalesOrder.mockResolvedValue(
      detail({ ...PAIR, status: 'blocked', findings: [SHORT] }),
    );

    renderDetail();

    await waitFor(() => expect(listScheduleFindings).toHaveBeenCalledWith('po-1', 'sv-2'));
    const flag = await openFlag(/Blocks publish on line 1/);
    expect(await flag.findByText('Sales order and Schedule')).toBeInTheDocument();
    expect(flag.getByText(SHORT.detail)).toBeInTheDocument();
    expect(flag.getByText(COLUMN.detail)).toBeInTheDocument();
    expect(flag.getAllByRole('button', { name: 'Dismiss with a reason' })).toHaveLength(1);
    // No second row for the column.
    expect(screen.queryByText('BUI-HB-CB6633SS')).not.toBeInTheDocument();

    fireEvent.click(flag.getByRole('button', { name: 'Dismiss with a reason' }));
    const dialog = await screen.findByRole('dialog', { name: /Dismiss with a reason/ });
    // Review N1: the reason is typed with both sentences in view, not only the first.
    expect(dialog.textContent).toContain(COLUMN.detail);
    fireEvent.change(within(dialog).getByLabelText(/Reason/), {
      target: { value: 'Column remapped on the schedule, v3 due.' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Dismiss 2' }));

    await waitFor(() =>
      expect(acknowledgeScheduleFinding).toHaveBeenCalledWith(
        'po-1',
        's-column',
        'Column remapped on the schedule, v3 due.',
      ),
    );
    expect(acknowledgeFinding).toHaveBeenCalledWith(
      'so-1',
      'f-short',
      'Column remapped on the schedule, v3 due.',
    );
  });

  it('lesson (e): the gate count is the server rule, and every blocker is in Need attention', async () => {
    const acknowledgedHard: ProjectSalesOrderFinding = {
      ...HARD,
      id: 'f-hard-done',
      line_id: 'l2',
      line_no: 2,
      acknowledged_at: '2026-09-01T00:00:00',
      acknowledged_by_name: null,
    };
    const orderLevelHard: ProjectSalesOrderFinding = {
      id: 'f-total',
      severity: 'hard',
      code: 'total_mismatch',
      detail: 'The lines add up to 8,554.95 but the PO says 8,550.00.',
    };
    // A schedule finding never blocks an order's publish on the server, so it is not counted.
    listScheduleFindings.mockResolvedValue([OVER]);
    getProjectSalesOrder.mockResolvedValue(
      detail({ ...PAIR, status: 'blocked', findings: [HARD, acknowledgedHard, orderLevelHard] }),
    );

    renderDetail();

    expect(await screen.findByText('2 block publish')).toBeInTheDocument();
    // HARD on line 1, the order-level total, and the schedule row: all need attention.
    expect(await screen.findByRole('radio', { name: 'Need attention (3)' })).toHaveAttribute(
      'data-state',
      'on',
    );
    expect(screen.getByText('CB6633')).toBeInTheDocument();
    expect(screen.getByText(orderLevelHard.detail)).toBeInTheDocument();
    // The line whose finding is dismissed does not need attention.
    expect(screen.queryByText('SRT382-6')).not.toBeInTheDocument();
  });

  it('S7-4: the summary card renders a dash for every unknown value', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({ area_group: null, created_at: null, customer_name: null, lines: [], line_count: 0 }),
    );

    renderDetail();

    await screen.findByText('Reference we raised');
    for (const label of [
      'Area group',
      'Billed to',
      'Sum of the lines',
      'Drafted',
      'Published',
      'AutoCount document',
    ]) {
      const field = screen.getByText(label, { selector: 'p' }).parentElement as HTMLElement;
      expect(within(field).getByText('-')).toBeInTheDocument();
    }
  });

  it('the AutoCount differences tab says so plainly before the order is published', async () => {
    getProjectSalesOrder.mockResolvedValue(detail());

    renderDetail();

    fireEvent.mouseDown(await screen.findByRole('tab', { name: 'AutoCount differences' }));
    expect(await screen.findByText('Not in AutoCount yet')).toBeInTheDocument();
  });

  // Owner hand test, PR #1264 note 3: "each sales agent is assigned to a location group like BB
  // then the stock location is automatically BRW-BB". The server derives it; the screen states
  // it once and never offers a picker for it.
  it('note 3: states the derived stock location once, with no bulk picker on the Lines tab', async () => {
    getProjectSalesOrder.mockResolvedValue(detail({ stock_location: 'BRW-BB' }));

    renderDetail();

    expect(await screen.findByText(/Stock location BRW-BB/)).toBeInTheDocument();
    expect(screen.queryByText(/Apply to all lines/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Stock location for all lines/)).not.toBeInTheDocument();
    expect(screen.queryByText(/No stock location/)).not.toBeInTheDocument();
  });

  it('note 3: flags an order whose location cannot be derived, naming the missing link', async () => {
    getProjectSalesOrder.mockResolvedValue(
      detail({
        stock_location: null,
        stock_location_gap: 'Sales agent LCL has no location group.',
      }),
    );

    renderDetail();

    const flag = await screen.findByText('No stock location');
    expect(flag).toHaveAttribute('title', 'Sales agent LCL has no location group.');
    expect(screen.queryByText(/Apply to all lines/)).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: /warehouse/i })).not.toBeInTheDocument();
  });
});
