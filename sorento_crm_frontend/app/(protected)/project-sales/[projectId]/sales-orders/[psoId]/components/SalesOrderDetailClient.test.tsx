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

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/sales-orders/so-1',
  useSearchParams: () => new URLSearchParams(),
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
  previewAmendment: vi.fn(),
  createAmendment: vi.fn(),
  getAmendment: vi.fn(),
  publishAmendment: vi.fn(),
  listScheduleVersions: vi.fn(async () => []),
  listPoVersions: vi.fn(async () => []),
}));

vi.mock('../../../../_shared/hooks/useProjects', () => ({
  useProject: () => ({ data: { id: 'p1', can_edit: true }, isLoading: false, isError: false }),
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

beforeEach(() => {
  vi.clearAllMocks();
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
          },
        ],
      }),
    );
    publishSalesOrder.mockResolvedValue({
      status: 'published',
      provisional_ref: 'PSO-000123',
      autocount_doc_no: 'SO397450',
      import_file_url: 'https://example.test/import.csv',
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
    expect(
      screen.getByRole('link', { name: 'Download the import file' }),
    ).toHaveAttribute('href', 'https://example.test/import.csv');
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
    expect(screen.queryByRole('button', { name: 'Move lines' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Import file' })).toBeInTheDocument();
  });

  it('re-splits the lines and says once that the shape is remembered', async () => {
    getProjectSalesOrder.mockResolvedValue(detail());
    regroupSalesOrder.mockResolvedValue({ data: [], total: 0, page: 1, limit: 25 });

    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: 'Move lines' }));

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
});
