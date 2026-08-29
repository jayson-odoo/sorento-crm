/**
 * Deleting a draft from the project's sales order list.
 *
 * Its own file, so it does not collide with `SalesOrdersPanel.test.tsx` (which pins what the
 * list must say in one pass). What is pinned here is the client's reason for asking - *"the
 * sales order must be able to get deleted so the process of building the draft SO can be
 * repeated"* - and the two rules that go with it: the standard confirmation copy naming the
 * count, and a published order that cannot be deleted at all because it is in AutoCount.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';
import type { ProjectSalesOrderRow } from '../../_shared/types/projectSalesOrder.types';

const listProjectSalesOrders = vi.fn();
const deleteProjectSalesOrder = vi.fn();
const bulkDeleteProjectSalesOrders = vi.fn();
const push = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

/** The shared DataGrid holds skeleton rows until saved column preferences resolve. */
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('../../_shared/services/projectSalesOrderService', () => ({
  PROJECT_SO_MOCK: false,
  listProjectSalesOrders: (...args: unknown[]) => listProjectSalesOrders(...args),
  buildSalesOrders: vi.fn(),
  deleteProjectSalesOrder: (...args: unknown[]) => deleteProjectSalesOrder(...args),
  bulkDeleteProjectSalesOrders: (...args: unknown[]) =>
    bulkDeleteProjectSalesOrders(...args),
  saveSalesOrderDocument: vi.fn(),
  getProjectSalesOrder: vi.fn(),
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
}));

vi.mock('../../_shared/hooks/useProjects', () => ({
  useProject: () => ({ data: undefined, isLoading: false, isError: false }),
  usePurchaseOrders: () => ({ data: [], isLoading: false, isError: false }),
  projectKey: (projectId: string) => ['projects', 'detail', projectId],
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options,
    placeholder,
  }: {
    id?: string;
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      id={id}
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

import { SalesOrdersPanel } from './SalesOrdersPanel';

const PROJECT = {
  id: 'p1',
  project_code: 'PRJ-0001',
  title: 'Tuju Residences',
  can_edit: true,
} as unknown as Project;

function row(overrides: Partial<ProjectSalesOrderRow> = {}): ProjectSalesOrderRow {
  return {
    id: 'so-1',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: null,
    area_group: 'TOWER',
    status: 'draft',
    grouping_origin: 'area',
    line_count: 99,
    total_amount: '1611107.81',
    hard_findings: 0,
    warn_findings: 0,
    is_pre_order: false,
    is_sponsorship: false,
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    created_at: '2026-04-02T02:15:00',
    ...overrides,
  };
}

function renderPanel(rows: ProjectSalesOrderRow[], project: Project = PROJECT) {
  listProjectSalesOrders.mockResolvedValue({
    data: rows,
    total: rows.length,
    page: 1,
    limit: 25,
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrdersPanel project={project} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  deleteProjectSalesOrder.mockResolvedValue({
    success: true,
    provisional_ref: 'PSO-000123',
    deleted: {},
  });
  bulkDeleteProjectSalesOrders.mockResolvedValue({
    success: true,
    deleted_count: 1,
    deleted: {},
    refused: [],
  });
});

describe('deleting a draft from the list', () => {
  it('asks with the standard copy and names the line count', async () => {
    renderPanel([row()]);

    fireEvent.click(await screen.findByRole('button', { name: 'Delete PSO-000123' }));

    expect(await screen.findByText('Confirm delete')).toBeInTheDocument();
    expect(
      screen.getByText(
        /Delete PSO-000123 and its 99 lines\? This action cannot be undone\./,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/the drafts can be built again/)).toBeInTheDocument();
  });

  it('deletes the row that was clicked, and does not open it', async () => {
    renderPanel([row(), row({ id: 'so-2', provisional_ref: 'PSO-000124', line_count: 41 })]);

    fireEvent.click(await screen.findByRole('button', { name: 'Delete PSO-000124' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(deleteProjectSalesOrder).toHaveBeenCalledWith('so-2'));
    // The row itself navigates, so the icon must not carry the click up with it.
    expect(push).not.toHaveBeenCalled();
  });

  it('says one line, not "1 lines"', async () => {
    renderPanel([row({ line_count: 1 })]);

    fireEvent.click(await screen.findByRole('button', { name: 'Delete PSO-000123' }));

    expect(screen.getByText(/and its 1 line\?/)).toBeInTheDocument();
  });

  it('refuses a published order, and the button says why rather than vanishing', async () => {
    renderPanel([row({ status: 'published', autocount_doc_no: 'SO397450' })]);

    const button = await screen.findByRole('button', { name: 'Delete SO397450' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', 'Published orders are amended, not deleted');
  });

  it('offers no delete at all to a reader', async () => {
    renderPanel([row()], { ...PROJECT, can_edit: false } as Project);

    await screen.findByText('PSO-000123');
    expect(screen.queryByRole('button', { name: /^Delete / })).toBeNull();
  });
});

describe('deleting a batch of drafts', () => {
  it('ticks rows, and refuses to tick one that cannot be deleted', async () => {
    renderPanel([
      row(),
      row({ id: 'so-2', provisional_ref: 'PSO-000124', status: 'published' }),
      row({ id: 'so-3', provisional_ref: 'PSO-000125', autocount_doc_no: 'SO397450' }),
    ]);

    expect(await screen.findByRole('checkbox', { name: 'Select PSO-000123' })).toBeEnabled();
    // Published, and adopted by AutoCount: two separate facts, each with its own sentence.
    const published = screen.getByRole('checkbox', { name: 'Select PSO-000124' });
    expect(published).toBeDisabled();
    expect(published.closest('[title]')).toHaveAttribute(
      'title',
      'Published orders are amended, not deleted',
    );
    const adopted = screen.getByRole('checkbox', { name: 'Select SO397450' });
    expect(adopted).toBeDisabled();
    expect(adopted.closest('[title]')).toHaveAttribute(
      'title',
      'In AutoCount as SO397450, so it is amended, not deleted',
    );
  });

  it('offers the batch action only once something is ticked, and names the count', async () => {
    renderPanel([row(), row({ id: 'so-2', provisional_ref: 'PSO-000124' })]);

    await screen.findByRole('checkbox', { name: 'Select PSO-000123' });
    expect(screen.queryByRole('button', { name: /Delete \d+ sales order/ })).toBeNull();
    // The counts row is what the header says with nothing selected.
    expect(screen.getByText('2 sales orders')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select PSO-000123' }));

    expect(
      await screen.findByRole('button', { name: 'Delete 1 sales order' }),
    ).toBeInTheDocument();
    expect(screen.getByText('1 selected')).toBeInTheDocument();
    // One statement at a time: the counts row stands down while a selection is live.
    expect(screen.queryByText('2 sales orders')).toBeNull();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select PSO-000124' }));

    expect(
      await screen.findByRole('button', { name: 'Delete 2 sales orders' }),
    ).toBeInTheDocument();
  });

  it('the header checkbox ticks every selectable row on the page, and no other', async () => {
    renderPanel([
      row(),
      row({ id: 'so-2', provisional_ref: 'PSO-000124' }),
      row({ id: 'so-3', provisional_ref: 'PSO-000125', status: 'published' }),
    ]);

    // The rows FIRST. The grid draws its header before the list query settles, and "select
    // all on this page" over an empty page selects nothing - which is the component behaving
    // correctly and the test racing it.
    await screen.findByRole('checkbox', { name: 'Select PSO-000123' });
    fireEvent.click(
      screen.getByRole('checkbox', { name: 'Select all rows on this page' }),
    );

    expect(
      await screen.findByRole('button', { name: 'Delete 2 sales orders' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Select PSO-000125' })).not.toBeChecked();
  });

  it('asks with the count, sends the ticked ids in one call, and clears the selection', async () => {
    bulkDeleteProjectSalesOrders.mockResolvedValue({
      success: true,
      deleted_count: 2,
      deleted: { 'projects.sales_orders': 2 },
      refused: [],
    });
    renderPanel([row(), row({ id: 'so-2', provisional_ref: 'PSO-000124' })]);

    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select PSO-000123' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select PSO-000124' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete 2 sales orders' }));

    expect(await screen.findByText('Confirm delete')).toBeInTheDocument();
    expect(
      screen.getByText(
        /Delete 2 sales orders and their lines\? This action cannot be undone\./,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/the drafts can be built again/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() =>
      expect(bulkDeleteProjectSalesOrders).toHaveBeenCalledWith(['so-1', 'so-2']),
    );
    // One call for the whole selection, never one per row.
    expect(bulkDeleteProjectSalesOrders).toHaveBeenCalledTimes(1);
    expect(deleteProjectSalesOrder).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Delete \d+ sales order/ })).toBeNull(),
    );
  });

  it('says "1 sales order", not "1 sales orders"', async () => {
    renderPanel([row()]);

    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select PSO-000123' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete 1 sales order' }));

    // "1 sales orders" and "and their lines" for one record are both wrong, and both were
    // in the first cut of this copy.
    expect(
      await screen.findByText(/Delete 1 sales order and its lines\?/),
    ).toBeInTheDocument();
    expect(screen.getByText(/the draft can be built again/)).toBeInTheDocument();
  });

  it('keeps the selection when the server refuses the batch', async () => {
    bulkDeleteProjectSalesOrders.mockRejectedValue(
      new Error(
        '1 of the selected sales orders cannot be deleted, so none were. PSO-000124: it is published.',
      ),
    );
    renderPanel([row(), row({ id: 'so-2', provisional_ref: 'PSO-000124' })]);

    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select PSO-000123' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select PSO-000124' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete 2 sales orders' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(bulkDeleteProjectSalesOrders).toHaveBeenCalled());
    // Un-tick the two named and retry is only possible if the selection survived.
    // The confirmation stays open on a refusal and dialogs are modal since UAC
    // S1-01, so the panel behind it is inerted - hence `hidden`, which is what
    // "still there, underneath the dialog" means to the accessibility tree.
    expect(
      await screen.findByRole('button', { name: 'Delete 2 sales orders', hidden: true }),
    ).toBeInTheDocument();
  });

  it('offers no selection at all to a reader', async () => {
    renderPanel([row()], { ...PROJECT, can_edit: false } as Project);

    await screen.findByText('PSO-000123');
    expect(screen.queryByRole('checkbox')).toBeNull();
  });
});
