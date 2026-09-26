/**
 * PLAN-excel-preview-26sep S1 (AC-10..AC-17): the standalone low stock report page. The body
 * is the workbook the user will download, split supplier and category by default, narrowed by
 * searchable supplier / category filters, with a count line and one Download. No reorder
 * planning chrome, no UUID on screen.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { LowStockView } from '../types/lowStockReport.types';

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/low-stock-report/run-1',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title, children, actions }: { title: React.ReactNode; children?: React.ReactNode; actions?: React.ReactNode }) => (
    <header>
      <h1>{title}</h1>
      {children}
      {actions}
    </header>
  ),
}));

const getLowStockView = vi.fn();
vi.mock('../services/lowStockReportService', () => ({
  getLowStockView: (...a: unknown[]) => getLowStockView(...a),
}));

const start = vi.fn();
let preparing = false;
vi.mock('../hooks/useLowStockDownload', () => ({
  useLowStockDownload: () => ({ start, preparing }),
}));

import { LowStockReportView } from './LowStockReportView';

const RUN_ID = '0b6f3c8e-1d2a-4c5b-9e7f-123456789abc';

function view(overrides: Partial<LowStockView> = {}): LowStockView {
  return {
    run: { run_id: RUN_ID, as_of: '2026-09-26', generated_at: '2026-09-26T07:40:12.345678' },
    split: 'supplier_category',
    columns: ['Item code', 'Description', 'BRW on hand'],
    rows: [
      ['A-1', 'Basin', 3],
      ['B-2', 'Tap', 90],
    ],
    sheets: [
      { title: 'Acme - BASIN - Low', row_indexes: [0], low: true },
      { title: 'Acme - BASIN', row_indexes: [0, 1], low: false },
    ],
    facets: {
      suppliers: [
        { key: 'Acme', rows: 2, low: 1 },
        { key: 'Kohler', rows: 5, low: 0 },
      ],
      categories: [{ key: 'BASIN', rows: 7, low: 1 }],
    },
    counts: { rows: 2, low: 1, sheets: 2 },
    over_cap: false,
    max_rows: 5000,
    filename: 'low-stock-26092026.xlsx',
    ...overrides,
  };
}

/** `null` is the sidebar's page: no run named, the newest one opens. */
function renderPage(runId: string | null = RUN_ID) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LowStockReportView runId={runId ?? undefined} />
    </QueryClientProvider>,
  );
}

function lastViewCall() {
  const calls = getLowStockView.mock.calls;
  return calls[calls.length - 1][0];
}

beforeEach(() => {
  getLowStockView.mockReset();
  start.mockReset();
  preparing = false;
});

describe('LowStockReportView', () => {
  it('opens split by supplier and category, shows the sheets, the count line and the date', async () => {
    getLowStockView.mockResolvedValue(view());
    renderPage();

    expect(await screen.findByRole('tab', { name: 'Acme - BASIN - Low' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Low stock report' })).toBeInTheDocument();
    // Review N3: the subtitle reads as the approved mockup.
    expect(screen.getByText('Daily plan, 26 Sep 2026 07:40')).toBeInTheDocument();
    expect(screen.getByText('2 rows, 2 sheets')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Supplier and category' })).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(lastViewCall()).toEqual({
      runId: RUN_ID,
      split: 'supplier_category',
      suppliers: [],
      categories: [],
    });
    expect(document.body.textContent).not.toContain(RUN_ID);
  });

  it('a plan with no computed time names its date alone', async () => {
    getLowStockView.mockResolvedValue(
      view({ run: { run_id: RUN_ID, as_of: '2026-09-05', generated_at: null } }),
    );
    renderPage();

    expect(await screen.findByText('Daily plan, 5 Sep 2026')).toBeInTheDocument();
  });

  it('refetches with the chosen split', async () => {
    getLowStockView.mockResolvedValue(view());
    renderPage();
    await screen.findByText('2 rows, 2 sheets');

    await userEvent.click(screen.getByRole('tab', { name: 'Supplier' }));

    await waitFor(() => expect(lastViewCall().split).toBe('supplier'));
  });

  it('refetches with the picked suppliers, each option showing its counts', async () => {
    getLowStockView.mockResolvedValue(view());
    renderPage();
    await screen.findByText('2 rows, 2 sheets');

    fireEvent.click(screen.getByRole('combobox', { name: 'Suppliers' }));
    const option = await screen.findByRole('option', { name: /Kohler/ });
    expect(option.textContent).toMatch(/0 low of 5/);
    fireEvent.click(option);

    await waitFor(() => expect(lastViewCall().suppliers).toEqual(['Kohler']));
  });

  it('Download sends exactly what the page shows', async () => {
    getLowStockView.mockResolvedValue(view());
    renderPage();
    await screen.findByText('2 rows, 2 sheets');

    await userEvent.click(screen.getByRole('button', { name: /Download/ }));

    expect(start).toHaveBeenCalledWith({
      runId: RUN_ID,
      split: 'supplier_category',
      suppliers: [],
      categories: [],
    });
  });

  it('holds Download back while a changed split and filter settle, then sends the new ones', async () => {
    // Review B2 (AC-13 / AC-14): a click inside the debounce, or while the new view is still
    // loading, would build a file for a split the grid does not show yet.
    getLowStockView.mockResolvedValueOnce(view());
    let answer: (v: LowStockView) => void = () => {};
    getLowStockView.mockImplementation(
      () => new Promise<LowStockView>((resolve) => (answer = resolve)),
    );
    renderPage();
    await screen.findByText('2 rows, 2 sheets');
    const download = () => screen.getByRole('button', { name: /Download/ });
    expect(download()).toBeEnabled();

    await userEvent.click(screen.getByRole('tab', { name: 'Supplier' }));
    fireEvent.click(screen.getByRole('combobox', { name: 'Suppliers' }));
    fireEvent.click(await screen.findByRole('option', { name: /Kohler/ }));

    // Inside the debounce: the old grid is still on screen.
    expect(download()).toBeDisabled();
    // The debounced request has gone out and is still loading.
    await waitFor(() =>
      expect(lastViewCall()).toEqual({
        runId: RUN_ID,
        split: 'supplier',
        suppliers: ['Kohler'],
        categories: [],
      }),
    );
    expect(download()).toBeDisabled();
    await userEvent.click(download());
    expect(start).not.toHaveBeenCalled();

    answer(
      view({
        split: 'supplier',
        sheets: [
          { title: 'Kohler - Low', row_indexes: [], low: true },
          { title: 'Kohler', row_indexes: [1], low: false },
        ],
        counts: { rows: 1, low: 0, sheets: 2 },
      }),
    );
    await screen.findByText('1 row, 2 sheets');
    await waitFor(() => expect(download()).toBeEnabled());
    await userEvent.click(download());

    expect(start).toHaveBeenCalledTimes(1);
    expect(start).toHaveBeenCalledWith({
      runId: RUN_ID,
      split: 'supplier',
      suppliers: ['Kohler'],
      categories: [],
    });
  });

  it('the newest-run page downloads the run the view answered with', async () => {
    getLowStockView.mockResolvedValue(view());
    renderPage(null);
    await screen.findByText('2 rows, 2 sheets');
    expect(lastViewCall().runId).toBeUndefined();

    await userEvent.click(screen.getByRole('button', { name: /Download/ }));

    expect(start.mock.calls[0][0].runId).toBe(RUN_ID);
  });

  it('reads Preparing... while the file is being built', async () => {
    preparing = true;
    getLowStockView.mockResolvedValue(view());
    renderPage();
    await screen.findByText('2 rows, 2 sheets');
    const button = screen.getByRole('button', { name: /Preparing/ });
    expect(button).toBeDisabled();
  });

  it('over the cap: says so, shows no sheets and disables Download', async () => {
    getLowStockView.mockResolvedValue(
      view({ over_cap: true, rows: [], sheets: [], counts: { rows: 6200, low: 900, sheets: 400 } }),
    );
    renderPage();

    expect(
      await screen.findByText('6,200 rows is over the 5,000 row limit. Narrow by supplier or category.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Download/ })).toBeDisabled();
    expect(screen.queryByRole('grid')).not.toBeInTheDocument();
  });

  it('an empty plan says so and disables Download', async () => {
    getLowStockView.mockResolvedValue(
      view({
        rows: [],
        sheets: [
          { title: 'Low stock', row_indexes: [], low: true },
          { title: 'All', row_indexes: [], low: false },
        ],
        facets: { suppliers: [], categories: [] },
        counts: { rows: 0, low: 0, sheets: 2 },
      }),
    );
    renderPage();

    expect(await screen.findByText('No products on this plan')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Download/ })).toBeDisabled();
  });

  it('an error shows the message and Retry reads again', async () => {
    getLowStockView.mockRejectedValueOnce(new Error('Reorder run not found'));
    getLowStockView.mockResolvedValue(view());
    renderPage();

    expect(await screen.findByText('Reorder run not found')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('2 rows, 2 sheets')).toBeInTheDocument();
  });

  it('shows the low sheet\'s empty state in the grid', async () => {
    getLowStockView.mockResolvedValue(
      view({
        sheets: [
          { title: 'Kohler - Low', row_indexes: [], low: true },
          { title: 'Kohler', row_indexes: [1], low: false },
        ],
      }),
    );
    renderPage();

    expect(await screen.findByText('Nothing low here')).toBeInTheDocument();
    const tabs = screen.getAllByRole('tablist');
    expect(within(tabs[tabs.length - 1]).getAllByRole('tab')).toHaveLength(2);
  });
});
