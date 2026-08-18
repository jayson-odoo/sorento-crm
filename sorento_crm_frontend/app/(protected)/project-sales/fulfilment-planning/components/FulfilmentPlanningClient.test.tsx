/**
 * Stage 1B - the fulfilment planning worklist (journey step 1, AC-A03, AC-G02).
 *
 * The screen is a worklist, not a report: every row carries exactly one review state pill
 * for the whole sales order, never a per-line "3 of 4 confirmed" reading. What is worth
 * pinning here is that the pill text matches what the row is, the review-state filter and
 * the search box both reach the service as query params, every response shape (loading,
 * error, and each empty-state copy) renders explicitly, and a row is the way into its sheet.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FulfilmentPlanningRow } from '../../_shared/types/fulfilmentPlanning.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/fulfilment-planning',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const listFulfilmentPlanning = vi.fn();
const getReconciliation = vi.fn();
const rerunReconciliation = vi.fn();
const adoptSalesOrder = vi.fn();
const getSupply = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  listFulfilmentPlanning: (...args: unknown[]) => listFulfilmentPlanning(...args),
  getReconciliation: (...args: unknown[]) => getReconciliation(...args),
  rerunReconciliation: (...args: unknown[]) => rerunReconciliation(...args),
  adoptSalesOrder: (...args: unknown[]) => adoptSalesOrder(...args),
  getSupply: (...args: unknown[]) => getSupply(...args),
  confirmSupply: vi.fn(),
  ConfirmSupplyError: class extends Error {},
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
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

import { FulfilmentPlanningClient } from './FulfilmentPlanningClient';

function row(overrides: Partial<FulfilmentPlanningRow> = {}): FulfilmentPlanningRow {
  return {
    id: 'pso-1',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: 'SO376201',
    project_id: 'proj-1',
    project_code: 'PRJ-0041',
    project_name: 'Tuju Residences',
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    area_group: 'TOWER',
    status: 'published',
    line_count: 4,
    lines_linked: 4,
    exception_count: 0,
    review_state: 'needs_cs_review',
    updated_at: '2026-08-14T02:41:00',
    ...overrides,
  };
}

function envelope(rows: FulfilmentPlanningRow[]) {
  return { data: rows, total: rows.length, page: 1, limit: 25 };
}

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FulfilmentPlanningClient />
    </QueryClientProvider>,
  );
}

/** Radix opens its dropdown menus on pointerdown, which fireEvent.click does not send. */
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('FulfilmentPlanningClient', () => {
  it('shows the loading state without flashing an empty or error copy', () => {
    listFulfilmentPlanning.mockReturnValue(new Promise(() => {}));

    renderClient();

    expect(screen.queryByText('Nothing is outstanding')).not.toBeInTheDocument();
    expect(screen.queryByText('The planning list could not be loaded')).not.toBeInTheDocument();
  });

  it('renders one pill per row, carrying the exception count where there is one', async () => {
    listFulfilmentPlanning.mockResolvedValue(
      envelope([
        row({ id: 'pso-clean', review_state: 'needs_cs_review', exception_count: 0 }),
        row({
          id: 'pso-open',
          provisional_ref: 'PSO-000124',
          review_state: 'awaiting_reconciliation',
          exception_count: 3,
        }),
      ]),
    );

    renderClient();

    expect(await screen.findByText('Needs CS review')).toBeInTheDocument();
    expect(screen.getByText('Awaiting reconciliation · 3 exceptions')).toBeInTheDocument();
  });

  it('reads the review-state filter into the query params it sends', async () => {
    listFulfilmentPlanning.mockResolvedValue(envelope([row()]));
    renderClient();

    await waitFor(() =>
      expect(listFulfilmentPlanning).toHaveBeenCalledWith(
        expect.objectContaining({ review_state: undefined }),
      ),
    );

    openFilters();
    const picker = within(screen.getByRole('menu')).getByRole('combobox');
    fireEvent.change(picker, { target: { value: 'needs_cs_review' } });

    await waitFor(() =>
      expect(listFulfilmentPlanning).toHaveBeenCalledWith(
        expect.objectContaining({ review_state: 'needs_cs_review' }),
      ),
    );
  });

  it('sends the typed search as the query param', async () => {
    listFulfilmentPlanning.mockResolvedValue(envelope([row()]));
    renderClient();

    await screen.findByText('PSO-000123');

    fireEvent.change(
      screen.getByPlaceholderText('Search sales order, project or customer'),
      { target: { value: 'buimaco' } },
    );

    await waitFor(() =>
      expect(listFulfilmentPlanning).toHaveBeenCalledWith(
        expect.objectContaining({ query: 'buimaco' }),
      ),
    );
  });

  it('offers the sales order book as the next step when nothing is outstanding', async () => {
    listFulfilmentPlanning.mockResolvedValue(envelope([]));

    renderClient();

    expect(await screen.findByText('Nothing is outstanding')).toBeInTheDocument();
    expect(
      screen.getByText(
        'An outstanding project sales order appears here on its own, with no upload and nothing to publish.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open the sales order book' })).toHaveAttribute(
      'href',
      '/scm/sales-orders',
    );
  });

  it('says so when the review-state filter itself has nothing left to show (needs review)', async () => {
    listFulfilmentPlanning.mockResolvedValue(envelope([]));
    renderClient();

    openFilters();
    fireEvent.change(within(screen.getByRole('menu')).getByRole('combobox'), {
      target: { value: 'needs_cs_review' },
    });

    expect(
      await screen.findByText('No sales order is waiting on a decision'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Clear the review state filter to see the rest of the sales orders.'),
    ).toBeInTheDocument();
  });

  it('says so when the review-state filter itself has nothing left to show (awaiting reconciliation)', async () => {
    listFulfilmentPlanning.mockResolvedValue(envelope([]));
    renderClient();

    openFilters();
    fireEvent.change(within(screen.getByRole('menu')).getByRole('combobox'), {
      target: { value: 'awaiting_reconciliation' },
    });

    expect(await screen.findByText('Every sales order here is reconciled')).toBeInTheDocument();
  });

  it('reports a load failure instead of an empty table', async () => {
    listFulfilmentPlanning.mockRejectedValue(new Error('Backend is down'));

    renderClient();

    expect(
      await screen.findByText('The planning list could not be loaded'),
    ).toBeInTheDocument();
    expect(screen.getByText('Backend is down')).toBeInTheDocument();

    listFulfilmentPlanning.mockResolvedValue(envelope([row()]));
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    await screen.findByText('PSO-000123');
    expect(listFulfilmentPlanning).toHaveBeenCalledTimes(2);
  });

  it('opens the sheet for the row that was clicked', async () => {
    listFulfilmentPlanning.mockResolvedValue(envelope([row()]));
    getReconciliation.mockReturnValue(new Promise(() => {}));

    renderClient();

    fireEvent.click(await screen.findByText('PSO-000123'));

    const dialog = await screen.findByRole('dialog');
    // Shown twice inside the sheet: the title, and the AutoCount doc field in the header strip.
    expect(within(dialog).getAllByText('SO376201').length).toBeGreaterThan(0);
    await waitFor(() => expect(getReconciliation).toHaveBeenCalledWith('pso-1'));
  });
});

/**
 * The AutoCount-driven arm (PLAN-fulfilment-planning-from-autocount-so, journey steps 1
 * and 2). What is worth pinning is that an order nobody planned appears at all, reads Not
 * started, states the facts CS judges it on, and offers exactly one decision.
 */
describe('FulfilmentPlanningClient, the AutoCount sales-order arm', () => {
  /** An outstanding core sales order with no planning record: no id, no Project SO. */
  function notStarted(overrides: Partial<FulfilmentPlanningRow> = {}): FulfilmentPlanningRow {
    return {
      row_kind: 'sales_order',
      id: null,
      sales_order_id: 'so-345418',
      so_number: 'SO345418',
      origin: null,
      provisional_ref: null,
      autocount_doc_no: null,
      project_id: null,
      project_label: 'PEMBINAAN YUEN SENG / TAMAN IMPIAN',
      customer_name: 'PEMBINAAN YUEN SENG SDN BHD (PROJECT)',
      status: null,
      line_count: 1,
      lines_linked: 0,
      exception_count: 0,
      outstanding_qty: '202.0000',
      earliest_required_date: '2025-06-15',
      review_state: 'not_started',
      updated_at: null,
      ...overrides,
    };
  }

  it('shows an unplanned core sales order as Not started, with no Project SO invented for it', async () => {
    listFulfilmentPlanning.mockResolvedValue(envelope([notStarted()]));

    renderClient();

    expect(await screen.findByText('SO345418')).toBeInTheDocument();
    expect(screen.getByText('Not started')).toBeInTheDocument();
    // AC-FP01: no reference and no document number claiming an upload that never happened.
    expect(screen.getByText('Not authored here')).toBeInTheDocument();
    expect(screen.queryByText('PSO-')).not.toBeInTheDocument();
  });

  it('states the facts the row is judged on: customer, project, earliest required date and outstanding quantity', async () => {
    listFulfilmentPlanning.mockResolvedValue(envelope([notStarted()]));

    renderClient();

    expect(
      await screen.findByText('PEMBINAAN YUEN SENG SDN BHD (PROJECT)'),
    ).toBeInTheDocument();
    expect(screen.getByText('PEMBINAAN YUEN SENG / TAMAN IMPIAN')).toBeInTheDocument();
    expect(screen.getByText('15/06/2025')).toBeInTheDocument();
    // The decimal string off the wire is read as a quantity, not as a machine's "202.0000".
    expect(screen.getByText('202')).toBeInTheDocument();
  });

  it('says the order named no project rather than showing a bare dash', async () => {
    listFulfilmentPlanning.mockResolvedValue(
      envelope([notStarted({ project_label: null, project_name: null })]),
    );

    renderClient();

    expect(await screen.findByText('Not named on the order')).toBeInTheDocument();
  });

  it('counts a not-started order plainly, never as "0 linked" of a mirror nobody wrote', async () => {
    listFulfilmentPlanning.mockResolvedValue(
      envelope([notStarted({ line_count: 40, lines_linked: 0 })]),
    );

    renderClient();

    await screen.findByText('SO345418');
    expect(screen.queryByText('0 linked / 40')).not.toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
  });

  it('renders the list in the order the server sent it, earliest required date first', async () => {
    listFulfilmentPlanning.mockResolvedValue(
      envelope([
        notStarted({
          sales_order_id: 'so-391698',
          so_number: 'SO391698',
          earliest_required_date: '2022-07-03',
        }),
        notStarted({
          sales_order_id: 'so-346436',
          so_number: 'SO346436',
          earliest_required_date: '2025-04-23',
        }),
        notStarted({
          sales_order_id: 'so-396071',
          so_number: 'SO396071',
          earliest_required_date: '2025-09-01',
        }),
      ]),
    );

    renderClient();

    await screen.findByText('SO391698');
    const rendered = screen
      .getAllByTitle(/^SO\d+$/)
      .map((node) => node.textContent);
    expect(rendered).toEqual(['SO391698', 'SO346436', 'SO396071']);
  });

  it('Start planning is the row’s one decision, and it opens the order it just created', async () => {
    listFulfilmentPlanning.mockResolvedValue(envelope([notStarted()]));
    adoptSalesOrder.mockResolvedValue({
      project_sales_order_id: 'pso-adopted-345418',
      so_number: 'SO345418',
      review_state: 'needs_cs_review',
      already_adopted: false,
    });
    getReconciliation.mockReturnValue(new Promise(() => {}));

    renderClient();

    fireEvent.click(await screen.findByRole('button', { name: /start planning/i }));

    await waitFor(() => expect(adoptSalesOrder).toHaveBeenCalledWith('so-345418'));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getAllByText('SO345418').length).toBeGreaterThan(0);
    await waitFor(() =>
      expect(getReconciliation).toHaveBeenCalledWith('pso-adopted-345418'),
    );
  });

  it('does not open a sheet, or write anything, when a not-started row itself is clicked', async () => {
    listFulfilmentPlanning.mockResolvedValue(envelope([notStarted()]));

    renderClient();

    fireEvent.click(await screen.findByText('SO345418'));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(adoptSalesOrder).not.toHaveBeenCalled();
  });

  it('offers the Not started filter, and reaches the service with it', async () => {
    listFulfilmentPlanning.mockResolvedValue(envelope([notStarted()]));

    renderClient();
    await screen.findByText('SO345418');

    openFilters();
    const select = within(screen.getByRole('menu')).getByRole('combobox');
    expect(within(select).getByRole('option', { name: 'Not started' })).toBeInTheDocument();
    fireEvent.change(select, { target: { value: 'not_started' } });

    await waitFor(() =>
      expect(listFulfilmentPlanning).toHaveBeenCalledWith(
        expect.objectContaining({ review_state: 'not_started' }),
      ),
    );
  });

  it('keeps the authored rows and their state beside the adopted ones', async () => {
    listFulfilmentPlanning.mockResolvedValue(
      envelope([
        notStarted(),
        row({
          id: 'pso-authored',
          row_kind: 'planning_record',
          origin: 'authored',
          review_state: 'awaiting_reconciliation',
          exception_count: 3,
        }),
      ]),
    );

    renderClient();

    expect(await screen.findByText('Not started')).toBeInTheDocument();
    expect(
      screen.getByText('Awaiting reconciliation · 3 exceptions'),
    ).toBeInTheDocument();
    expect(screen.getByText('PSO-000123')).toBeInTheDocument();
  });
});
