/**
 * The sales order edit view, and the delete that makes rebuilding a draft repeatable.
 *
 * Kept in its own file rather than added to `SalesOrderDetailClient.test.tsx`, which pins the
 * two-tier publish gate: these are a different concern and the mock surface is different.
 *
 * What is pinned:
 * - Edit changes no section and moves no field. The one editable header field becomes an input
 *   where it already stood, and every read-only fact beside it stays a fact.
 * - One Save, one request, carrying only what changed.
 * - Cancel puts the screen back with nothing written.
 * - Save asks once, naming the count, when lines are actually leaving.
 * - Delete asks with the standard copy, and a published order is refused before the click.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  ProjectSalesOrderDetail,
  ProjectSalesOrderLine,
} from '../../../../_shared/types/projectSalesOrder.types';

const getProjectSalesOrder = vi.fn();
const saveSalesOrderDocument = vi.fn();
const deleteProjectSalesOrder = vi.fn();
const push = vi.fn();
const toastSuccess = vi.fn();
const toastError = vi.fn();

vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    custom: vi.fn(),
  },
}));

let search = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/sales-orders/so-1',
  useSearchParams: () => search,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('../../../../_shared/services/projectSalesOrderService', () => ({
  PROJECT_SO_MOCK: false,
  listProjectSalesOrders: vi.fn(),
  buildSalesOrders: vi.fn(),
  getProjectSalesOrder: (...args: unknown[]) => getProjectSalesOrder(...args),
  saveSalesOrderDocument: (...args: unknown[]) => saveSalesOrderDocument(...args),
  deleteProjectSalesOrder: (...args: unknown[]) => deleteProjectSalesOrder(...args),
  acknowledgeFinding: vi.fn(),
  updateSalesOrderLine: vi.fn(),
  regroupSalesOrder: vi.fn(),
  publishSalesOrder: vi.fn(),
  downloadSalesOrderImportFile: vi.fn(),
  previewAmendment: vi.fn(),
  createAmendment: vi.fn(),
  getAmendment: vi.fn(),
  publishAmendment: vi.fn(),
  listScheduleVersions: vi.fn(async () => []),
  listPoVersions: vi.fn(async () => []),
  salesOrderNeighboursPath: (projectId: string) =>
    `/api/v1/project-sales/projects/${projectId}/sales-orders/neighbours`,
}));

// The header's prev/next pager. Mocked at the shared hook so nothing is fetched here; the
// pager itself is covered in SalesOrderDetailClient.test.tsx.
vi.mock('@/hooks/useRecordNeighbours', () => ({
  useRecordNeighbours: () => ({
    prevId: null,
    nextId: null,
    index: null,
    total: 0,
    isLoading: false,
  }),
}));

vi.mock('../../../../_shared/services/soDivergenceService', () => ({
  listDivergences: vi.fn(async () => ({ data: [], total: 0, page: 1, limit: 100 })),
  getDivergence: vi.fn(),
  ingestSalesOrderFile: vi.fn(),
  resolveDivergenceRow: vi.fn(),
  downloadCorrectiveImportFile: vi.fn(),
}));

vi.mock('../../../../_shared/services/projectAllocationService', () => ({
  listAllocations: vi.fn(async () => ({ data: [], total: 0, page: 1, limit: 100 })),
  listAllocationCandidates: vi.fn(async () => []),
  confirmAllocation: vi.fn(),
  deleteAllocation: vi.fn(),
  listClaims: vi.fn(async () => ({ data: [], total: 0, page: 1, limit: 100 })),
  decideClaim: vi.fn(),
}));

vi.mock('../../../../_shared/hooks/useProjects', () => ({
  useProject: () => ({ data: { id: 'p1', can_edit: true }, isLoading: false, isError: false }),
  usePurchaseOrders: () => ({ data: [], isLoading: false, isError: false }),
  projectKey: (projectId: string) => ['projects', 'detail', projectId],
}));

vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query', () => ({
  useUOMSelectQuery: () => ({
    data: [{ id: 'u1', uom_code: 'UNIT', uom_name: 'Unit' }],
    isLoading: false,
  }),
}));

vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForVariantSelect: vi.fn(async () => []),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options,
    placeholder,
    selectedOption,
  }: {
    id?: string;
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    selectedOption?: { value: string; label: string };
  }) => (
    <select
      id={id}
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? (selectedOption ? [selectedOption] : [])).map((option) => (
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
    product_id: 'p1',
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
    stock_location: 'BRW-BB',
  },
  {
    id: 'l2',
    line_no: 2,
    product_id: 'p2',
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
    stock_location: 'BRW-BB',
  },
];

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

/** The gear. Radix opens it on pointerDown, not click. */
async function openGear() {
  fireEvent.pointerDown(
    await screen.findByRole('button', { name: 'Sales order actions' }),
    { button: 0, ctrlKey: false },
  );
  return screen.findByRole('menu');
}

/** Opens the gear and clicks one of its items. */
async function chooseAction(name: RegExp) {
  await openGear();
  const item = await screen.findByRole('menuitem', { name });
  fireEvent.click(item);
  return item;
}

async function startEditing() {
  await chooseAction(/Edit this sales order/);
  await screen.findByRole('button', { name: 'Save' });
}

beforeEach(() => {
  vi.clearAllMocks();
  search = new URLSearchParams();
  getProjectSalesOrder.mockResolvedValue(detail());
  saveSalesOrderDocument.mockImplementation(async () => detail());
  deleteProjectSalesOrder.mockResolvedValue({
    success: true,
    provisional_ref: 'PSO-000123',
    deleted: {},
  });
});

describe('the edit view is the read view', () => {
  it('reads every field, with nothing to type into, until Edit is pressed', async () => {
    renderDetail();

    expect(
      await screen.findByRole('heading', { level: 1, name: 'PSO-000123' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Area group')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Area group' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
  });

  it('swaps the one editable field for an input where it already stood', async () => {
    renderDetail();
    await startEditing();

    // Same label, same place, now an input holding the stored value.
    expect(screen.getByLabelText('Area group')).toHaveValue('TOWER');
    // And every read-only fact beside it is still on screen.
    expect(screen.getByText('Reference we raised')).toBeInTheDocument();
    expect(screen.getByText('AutoCount document')).toBeInTheDocument();
    expect(screen.getByText('Buimaco Sdn Bhd (Project)')).toBeInTheDocument();
  });

  it('says that nothing is written yet, and offers Save only once something changed', async () => {
    renderDetail();
    await startEditing();

    expect(screen.getByText('Nothing is written until you press Save.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Area group'), { target: { value: 'PODIUM' } });

    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
  });

  it('withholds Publish while a session is open, so nothing acts on unsaved changes', async () => {
    renderDetail();
    expect(await screen.findByRole('button', { name: /Publish/ })).toBeInTheDocument();

    await startEditing();

    expect(screen.queryByRole('button', { name: /Publish/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Move lines/ })).not.toBeInTheDocument();
  });
});

describe('arriving from the list with ?edit=1', () => {
  it('opens the session on arrival, so Edit in the list lands in the same one screen', async () => {
    search = new URLSearchParams('edit=1');
    renderDetail();

    expect(await screen.findByRole('button', { name: 'Save' })).toBeInTheDocument();
    expect(screen.getByLabelText('Area group')).toHaveValue('TOWER');
  });

  it('does not reopen the session after Cancel', async () => {
    search = new URLSearchParams('edit=1');
    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument(),
    );
  });

  it('refuses to open a session on a published order the server would refuse', async () => {
    search = new URLSearchParams('edit=1');
    getProjectSalesOrder.mockResolvedValue(detail({ status: 'published' }));
    renderDetail();

    await screen.findByRole('button', { name: 'Sales order actions' });
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
  });
});

describe('one Save', () => {
  it('sends only the header when only the header changed', async () => {
    renderDetail();
    await startEditing();

    fireEvent.change(screen.getByLabelText('Area group'), { target: { value: 'PODIUM' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(saveSalesOrderDocument).toHaveBeenCalledTimes(1));
    expect(saveSalesOrderDocument).toHaveBeenCalledWith('so-1', { area_group: 'PODIUM' });
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Sales order saved'));
    // Back to the read view.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument(),
    );
  });

  it('sends the whole line set when a line changed, in one request', async () => {
    renderDetail();
    await startEditing();

    fireEvent.change(screen.getByRole('textbox', { name: /Qty on CB6633/ }), {
      target: { value: '601' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(saveSalesOrderDocument).toHaveBeenCalledTimes(1));
    const [, body] = saveSalesOrderDocument.mock.calls[0];
    expect(body.lines).toHaveLength(2);
    expect(body.lines[0]).toMatchObject({ id: 'l1', qty: '601' });
    expect(body.lines[1]).toMatchObject({ id: 'l2', qty: '135' });
    expect(body.area_group).toBeUndefined();
  });

  it('refuses to save a line that has nothing to call it, and says how many', async () => {
    renderDetail();
    await startEditing();

    fireEvent.click(screen.getByRole('button', { name: /Add a line/ }));
    // A row added and typed into, but with neither a product nor a description.
    fireEvent.change(screen.getAllByRole('textbox', { name: /^Qty on line 3/ })[0], {
      target: { value: '5' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        'One line still needs a quantity, and a product or a description.',
      ),
    );
    expect(saveSalesOrderDocument).not.toHaveBeenCalled();
  });

  it('asks once, naming the count, before lines actually leave', async () => {
    renderDetail();
    await startEditing();

    fireEvent.click(screen.getByRole('button', { name: /Remove CB6633/ }));
    // Staged, not done: no dialog yet.
    expect(screen.queryByText('Confirm delete')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText('Confirm delete')).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        'Saving removes 1 line from PSO-000123. This action cannot be undone.',
      ),
    ).toBeInTheDocument();
    expect(saveSalesOrderDocument).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Save and remove 1 line' }));

    await waitFor(() => expect(saveSalesOrderDocument).toHaveBeenCalledTimes(1));
    const [, body] = saveSalesOrderDocument.mock.calls[0];
    expect(body.lines).toHaveLength(1);
    expect(body.lines[0].id).toBe('l2');
  });

  it('Cancel writes nothing and puts the read view back', async () => {
    renderDetail();
    await startEditing();

    fireEvent.change(screen.getByLabelText('Area group'), { target: { value: 'PODIUM' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(saveSalesOrderDocument).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByRole('textbox', { name: 'Area group' })).not.toBeInTheDocument(),
    );
    // The stored value, not what was typed.
    expect(screen.getByText('TOWER')).toBeInTheDocument();
  });
});

describe('deleting the draft', () => {
  it('asks with the standard copy, names the line count, and leaves the list', async () => {
    renderDetail();
    await chooseAction(/Delete this sales order/);

    expect(await screen.findByText('Confirm delete')).toBeInTheDocument();
    expect(
      screen.getByText(
        /Delete PSO-000123 and its 2 lines\? This action cannot be undone\./,
      ),
    ).toBeInTheDocument();
    // The reason it is safe: the documents it was built from are untouched.
    expect(screen.getByText(/the drafts can be built again/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(deleteProjectSalesOrder).toHaveBeenCalledWith('so-1'));
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/project-sales/p1?tab=sales-orders'),
    );
  });

  it('refuses both the edit and the delete on a published order, and says why', async () => {
    getProjectSalesOrder.mockResolvedValue(detail({ status: 'published' }));
    renderDetail();

    await openGear();

    const edit = await screen.findByRole('menuitem', { name: /Edit this sales order/ });
    const remove = await screen.findByRole('menuitem', { name: /Delete this sales order/ });
    expect(edit).toHaveAttribute('aria-disabled', 'true');
    expect(remove).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText('Published, so raise a revision instead')).toBeInTheDocument();
    expect(screen.getByText('In AutoCount, so amend it instead')).toBeInTheDocument();
  });
});
