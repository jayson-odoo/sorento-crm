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

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  listFulfilmentPlanning: (...args: unknown[]) => listFulfilmentPlanning(...args),
  getReconciliation: (...args: unknown[]) => getReconciliation(...args),
  rerunReconciliation: (...args: unknown[]) => rerunReconciliation(...args),
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

    expect(screen.queryByText('No published Project SO yet')).not.toBeInTheDocument();
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

  it('offers the pipeline as the next step when nothing has published yet', async () => {
    listFulfilmentPlanning.mockResolvedValue(envelope([]));

    renderClient();

    expect(await screen.findByText('No published Project SO yet')).toBeInTheDocument();
    expect(
      screen.getByText(
        'A sales order appears here once it is published from a project. Publish one from the project, then upload its AutoCount document.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open the pipeline' })).toHaveAttribute(
      'href',
      '/project-sales/pipeline',
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
      await screen.findByText('No sales order has finished reconciling yet'),
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
