/**
 * P7 - the drafts list.
 *
 * What is pinned here is what a reviewer must be able to read in one pass: which drafts
 * exist, which of them cannot publish, and where each split came from. The grouping origin
 * is asserted because the area split is a proposal: the same real PO produced a TOWER split,
 * a COMMON AREA split and an early product subset with no area logic at all.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';
import type { ProjectSalesOrderRow } from '../../_shared/types/projectSalesOrder.types';

const listProjectSalesOrders = vi.fn();
const buildSalesOrders = vi.fn();
const listScheduleVersions = vi.fn();
const push = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));

/**
 * The shared DataGrid holds its skeleton rows until saved column preferences resolve, and
 * that query never settles under jsdom. Stubbed so the rows themselves can be asserted.
 */
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('../../_shared/services/projectSalesOrderService', () => ({
  PROJECT_SO_MOCK: false,
  listProjectSalesOrders: (...args: unknown[]) => listProjectSalesOrders(...args),
  buildSalesOrders: (...args: unknown[]) => buildSalesOrders(...args),
  getProjectSalesOrder: vi.fn(),
  acknowledgeFinding: vi.fn(),
  updateSalesOrderLine: vi.fn(),
  regroupSalesOrder: vi.fn(),
  publishSalesOrder: vi.fn(),
  previewAmendment: vi.fn(),
  createAmendment: vi.fn(),
  getAmendment: vi.fn(),
  publishAmendment: vi.fn(),
  listScheduleVersions: (...args: unknown[]) => listScheduleVersions(...args),
  listPoVersions: vi.fn(async () => []),
}));

vi.mock('../../_shared/hooks/useProjects', () => ({
  useProject: () => ({ data: undefined, isLoading: false, isError: false }),
  usePurchaseOrders: () => ({
    data: [
      {
        id: 'po-1',
        project_id: 'p1',
        po_source: 'trading_house',
        po_number: 'HQ/26/01/121',
        po_date: '2026-01-19',
        issuing_party_name: 'Buimaco Sdn Bhd',
        line_count: 52,
        line_total: '1810640.62',
        model_mismatch_count: 0,
        price_mismatch_count: 0,
      },
    ],
    isLoading: false,
    isError: false,
  }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    id,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    id?: string;
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

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Tuju Residences',
    outcome: 'won',
    is_critical: false,
    brands: [],
    brand_ids: [],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    ...overrides,
  };
}

function row(overrides: Partial<ProjectSalesOrderRow> = {}): ProjectSalesOrderRow {
  return {
    id: 'so-tower',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: null,
    area_group: 'TOWER',
    status: 'draft',
    grouping_origin: 'area',
    line_count: 99,
    total_amount: '1611107.81',
    hard_findings: 0,
    warn_findings: 2,
    is_pre_order: false,
    is_sponsorship: false,
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    created_at: '2026-04-02T02:15:00',
    ...overrides,
  };
}

function renderPanel(overrides: Partial<Project> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrdersPanel project={project(overrides)} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listScheduleVersions.mockResolvedValue([
    {
      id: 'sched-v1',
      version_no: 1,
      revision_label: 'R1',
      issuer_party_label: 'Buimaco Sdn Bhd',
      schedule_date: '2026-01-19',
      confirmed_at: '2026-01-20T02:00:00',
    },
  ]);
});

describe('SalesOrdersPanel', () => {
  it('shows the loading state without flashing the empty state', () => {
    listProjectSalesOrders.mockReturnValue(new Promise(() => {}));

    renderPanel();

    expect(screen.getByText('Sales orders')).toBeInTheDocument();
    expect(screen.queryByText('No sales order drafted yet')).not.toBeInTheDocument();
  });

  it('states the empty case, with the one way in still in the toolbar', async () => {
    listProjectSalesOrders.mockResolvedValue({ data: [], total: 0, page: 1, limit: 25 });

    renderPanel();

    expect(await screen.findByText('No sales order drafted yet')).toBeInTheDocument();
    // ONE button, in the toolbar (ADR 1d). The centred duplicate is gone.
    expect(screen.getByRole('button', { name: /Build drafts/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Build the first drafts/ })).toBeNull();
  });

  it('reports a failure to load instead of an empty table', async () => {
    listProjectSalesOrders.mockRejectedValue(new Error('The list endpoint is not up yet'));

    renderPanel();

    expect(await screen.findByText('Sales orders could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('The list endpoint is not up yet')).toBeInTheDocument();
  });

  it('shows where each split came from, its value to the cent, and what blocks it', async () => {
    listProjectSalesOrders.mockResolvedValue({
      data: [
        row(),
        row({
          id: 'so-common',
          provisional_ref: 'PSO-000124',
          area_group: 'COMMON AREA',
          status: 'blocked',
          line_count: 41,
          total_amount: '74677.32',
          hard_findings: 2,
          warn_findings: 1,
        }),
        row({
          id: 'so-subset',
          provisional_ref: 'PSO-000101',
          autocount_doc_no: 'SO376200',
          area_group: null,
          status: 'published',
          grouping_origin: 'subset',
          line_count: 12,
          total_amount: '48120.00',
          warn_findings: 0,
          is_pre_order: true,
        }),
      ],
      total: 3,
      page: 1,
      limit: 25,
    });

    renderPanel();

    expect(await screen.findByText('PSO-000123')).toBeInTheDocument();
    // A published order is known by its AutoCount number, never by an id.
    expect(screen.getByText('SO376200')).toBeInTheDocument();
    // Both area splits say so on their own row; the subset says it had no area logic.
    expect(screen.getAllByText('Split by schedule area')).toHaveLength(2);
    expect(screen.getByText('Product subset, no area')).toBeInTheDocument();
    expect(screen.getByText('No area')).toBeInTheDocument();

    // Cents survive: 1,611,107.81 is what the printed sales order says.
    expect(screen.getByText('RM 1,611,107.81')).toBeInTheDocument();
    expect(screen.getByText('2 blocking')).toBeInTheDocument();
    expect(screen.getByText('2 warnings')).toBeInTheDocument();
    expect(screen.getByText('1 warning')).toBeInTheDocument();
    expect(screen.getByText('Nothing flagged')).toBeInTheDocument();
    expect(screen.getByText('1 cannot publish yet')).toBeInTheDocument();
    expect(screen.getByText('Pre-order')).toBeInTheDocument();
  });

  it('sums the page value as decimals, not floats', async () => {
    listProjectSalesOrders.mockResolvedValue({
      data: [
        row({ id: 'a', total_amount: '0.07' }),
        row({ id: 'b', provisional_ref: 'PSO-000124', total_amount: '0.01' }),
      ],
      total: 2,
      page: 1,
      limit: 25,
    });

    renderPanel();

    // 0.07 + 0.01 is exactly 0.08. As floats it is 0.07999999999999999.
    expect(await screen.findByText('RM 0.08 on this page')).toBeInTheDocument();
  });

  it('builds only after the pair is confirmed, and warns that drafts are replaced', async () => {
    listProjectSalesOrders.mockResolvedValue({ data: [], total: 0, page: 1, limit: 25 });
    buildSalesOrders.mockResolvedValue({ data: [row()], total: 1, page: 1, limit: 25 });

    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: /Build drafts/ }));

    fireEvent.change(await screen.findByLabelText('Select a purchase order'), {
      target: { value: 'po-1' },
    });
    fireEvent.change(await screen.findByLabelText('Select a schedule version'), {
      target: { value: 'sched-v1' },
    });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Build drafts' }));

    expect(await screen.findByText('Build the drafts?')).toBeInTheDocument();
    expect(
      screen.getByText(/Drafts built earlier from the same pair are replaced/),
    ).toBeInTheDocument();
    expect(buildSalesOrders).not.toHaveBeenCalled();

    fireEvent.click(
      within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Build drafts' }),
    );

    await waitFor(() => expect(buildSalesOrders).toHaveBeenCalledWith('po-1', 'sched-v1'));
  });

  it('hides the build control on a project the user may not edit', async () => {
    listProjectSalesOrders.mockResolvedValue({ data: [row()], total: 1, page: 1, limit: 25 });

    renderPanel({ can_edit: false });

    await screen.findByText('PSO-000123');
    expect(screen.queryByRole('button', { name: /Build drafts/ })).not.toBeInTheDocument();
  });
});
