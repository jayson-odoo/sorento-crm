/**
 * S4 (PLAN-po-spo-site-pool-and-order-sheet-downloads, AC-19/AC-20/AC-21): the plan's
 * Actions menu still offers "Order sheet PDF" / "Order sheet Excel", but both now go
 * through the async My Downloads pipeline (`useExportOrderSheet`) instead of streaming a
 * blob directly - no `downloadOrderSummaryExport` call, no saved file. Both menu items
 * disable while a request is in flight (AC-21, "double click = one row").
 *
 * `PlanLinesSection` is mocked to a thin stand-in rendering `secondaryActions` as buttons,
 * forwarding `disabled` - it owns none of the behaviour under test (that lives in
 * `ReorderPlanView`'s own `actions` array) and its real implementation pulls in the whole
 * plan-lines grid stack. `exportOrderSheet` (the service function `useExportOrderSheet`
 * calls) is the ONLY thing mocked below the hook, so the mutation, its query
 * invalidation and its toast all run for real.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import type { ReorderRun } from '../types/reorder.types';

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/reorder/run-1',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

const exportOrderSheet = vi.fn();
const getOrderSummaryDemand = vi.fn();
vi.mock('../services/summaryOrderService', () => ({
  exportOrderSheet: (...args: unknown[]) => exportOrderSheet(...args),
  getOrderSummaryDemand: (...args: unknown[]) => getOrderSummaryDemand(...args),
}));

vi.mock('../services/reorderRunService', () => ({
  resetRunDecisions: vi.fn(),
}));

const RUN: ReorderRun = {
  run_id: 'run-1',
  status: 'completed',
  stage: 'writing_recommendations',
  buy_scope: 'warehouse',
  summary: null,
  error: null,
  started_at: '2026-09-09T08:00:00Z',
  plan_horizon_start: null,
  plan_horizon_date: null,
} as ReorderRun;

vi.mock('../hooks/useReorderRun', () => ({
  useReorderRunDetail: () => ({ data: RUN, isLoading: false, isError: false, error: null }),
  useUnlocatedDemand: () => ({ data: { products: 0, quantity: 0 } }),
  runHistoryKey: ['scm', 'reorder', 'history'],
  todayRunKey: ['scm', 'reorder', 'today'],
}));

vi.mock('./PlanLinesSection', () => ({
  PlanLinesSection: ({ secondaryActions }: { secondaryActions?: ToolbarAction[] }) => (
    <div data-testid="plan-lines-section">
      {(secondaryActions ?? []).map((action) => (
        <button key={action.key} disabled={action.disabled} onClick={() => action.onClick?.()}>
          {action.label}
        </button>
      ))}
    </div>
  ),
}));

import { ReorderPlanView } from './ReorderPlanView';

function renderView() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries');
  render(
    <QueryClientProvider client={queryClient}>
      <ReorderPlanView runId="run-1" />
    </QueryClientProvider>,
  );
  return { invalidateQueries };
}

describe('ReorderPlanView Actions menu - order sheet export (AC-19/AC-20/AC-21)', () => {
  beforeEach(() => {
    exportOrderSheet.mockReset();
    getOrderSummaryDemand.mockReset();
    toastSuccess.mockClear();
    toastError.mockClear();
  });

  it('offers Order sheet PDF and Order sheet Excel', async () => {
    renderView();
    expect(await screen.findByRole('button', { name: 'Order sheet PDF' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Order sheet Excel' })).toBeInTheDocument();
  });

  it('AC-19: posts through exportOrderSheet(runId, "pdf"), invalidates my-downloads and '
    + 'the entity-downloads key for this run, and toasts the preparing message - no blob '
    + 'is saved', async () => {
    exportOrderSheet.mockResolvedValue({
      id: 'dl-1', kind: 'order_sheet_pdf', status: 'pending', filename: null,
    });
    const { invalidateQueries } = renderView();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Order sheet PDF' }));

    await waitFor(() => expect(exportOrderSheet).toHaveBeenCalledWith('run-1', 'pdf'));
    await waitFor(() =>
      expect(toastSuccess).toHaveBeenCalledWith(
        'Preparing the order sheet - it will appear in My Downloads.',
      ),
    );
    expect(invalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['my-downloads'] }),
    );
    expect(invalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['entity-downloads', 'reorder_run', 'run-1'] }),
    );
  });

  it('AC-19: Order sheet Excel posts format "xlsx"', async () => {
    exportOrderSheet.mockResolvedValue({
      id: 'dl-2', kind: 'order_sheet_xlsx', status: 'pending', filename: null,
    });
    renderView();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Order sheet Excel' }));

    await waitFor(() => expect(exportOrderSheet).toHaveBeenCalledWith('run-1', 'xlsx'));
  });

  it('AC-20: a rejected export toasts the extracted error message (the 422 "Narrow the '
    + 'plan first" text reaches the buyer)', async () => {
    exportOrderSheet.mockRejectedValue(new Error('Narrow the plan first'));
    renderView();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Order sheet PDF' }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Narrow the plan first'));
  });

  it('AC-21: both menu items disable while a request is in flight (double click = one '
    + 'row)', async () => {
    let resolveExport: (value: unknown) => void = () => {};
    exportOrderSheet.mockImplementation(
      () => new Promise((resolve) => { resolveExport = resolve; }),
    );
    renderView();
    const user = userEvent.setup();

    const pdfButton = await screen.findByRole('button', { name: 'Order sheet PDF' });
    const xlsxButton = screen.getByRole('button', { name: 'Order sheet Excel' });
    expect(pdfButton).not.toBeDisabled();
    expect(xlsxButton).not.toBeDisabled();

    await user.click(pdfButton);

    await waitFor(() => expect(pdfButton).toBeDisabled());
    expect(xlsxButton).toBeDisabled();
    expect(exportOrderSheet).toHaveBeenCalledTimes(1);

    resolveExport({ id: 'dl-3', kind: 'order_sheet_pdf', status: 'pending', filename: null });
    await waitFor(() => expect(pdfButton).not.toBeDisabled());
  });
});
