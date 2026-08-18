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
