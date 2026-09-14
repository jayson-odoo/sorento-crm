/**
 * PLAN-low-stock-report S4 (AC-1/AC-2): the plan's Actions menu offers a THIRD export -
 * "Low stock report (Excel)" - directly under "Order sheet Excel", going through the same
 * async My Downloads pipeline as the two order sheet items.
 *
 * Same stand-ins as `ReorderPlanView.orderSheet.test.tsx`: `PlanLinesSection` renders the
 * toolbar actions as buttons (it owns none of the behaviour under test, and its real
 * implementation pulls in the whole plan-lines grid stack), and the two service functions
 * are the only things mocked below the hooks - the mutations, their query invalidation and
 * their toasts all run for real.
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
const exportLowStockReport = vi.fn();
const getOrderSummaryDemand = vi.fn();
vi.mock('../services/summaryOrderService', () => ({
  exportOrderSheet: (...args: unknown[]) => exportOrderSheet(...args),
  exportLowStockReport: (...args: unknown[]) => exportLowStockReport(...args),
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
  started_at: '2026-09-14T08:00:00Z',
  plan_horizon_start: null,
  plan_horizon_date: null,
} as ReorderRun;

vi.mock('../hooks/useReorderRun', () => ({
  useReorderRunDetail: () => ({ data: RUN, isLoading: false, isError: false, error: null }),
  useUnlocatedDemand: () => ({ data: { products: 0, quantity: 0 } }),
  runHistoryKey: ['scm', 'reorder', 'history'],
  todayRunKey: ['scm', 'reorder', 'today'],
}));

const renderedActions: ToolbarAction[] = [];
vi.mock('./PlanLinesSection', () => ({
  PlanLinesSection: ({ secondaryActions }: { secondaryActions?: ToolbarAction[] }) => {
    renderedActions.length = 0;
    renderedActions.push(...(secondaryActions ?? []));
    return (
      <div data-testid="plan-lines-section">
        {(secondaryActions ?? []).map((action) => (
          <button key={action.key} disabled={action.disabled} onClick={() => action.onClick?.()}>
            {action.label}
          </button>
        ))}
      </div>
    );
  },
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

describe('ReorderPlanView Actions menu - low stock report (AC-1/AC-2)', () => {
  beforeEach(() => {
    exportOrderSheet.mockReset();
    exportLowStockReport.mockReset();
    getOrderSummaryDemand.mockReset();
    toastSuccess.mockClear();
    toastError.mockClear();
  });

  it('AC-1: offers "Low stock report (Excel)" directly under "Order sheet Excel"', async () => {
    renderView();
    expect(
      await screen.findByRole('button', { name: 'Low stock report (Excel)' }),
    ).toBeInTheDocument();

    const exportKeys = renderedActions
      .map((a) => a.key)
      .filter((k) => k.startsWith('order_sheet') || k === 'low_stock_xlsx');
    expect(exportKeys).toEqual(['order_sheet_pdf', 'order_sheet_xlsx', 'low_stock_xlsx']);
  });

  it('AC-2: calls exportLowStockReport(runId), invalidates my-downloads and this run\'s '
    + 'entity-downloads key, and toasts the preparing message', async () => {
    exportLowStockReport.mockResolvedValue({
      id: 'dl-9', kind: 'low_stock_xlsx', status: 'pending', filename: null,
    });
    const { invalidateQueries } = renderView();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Low stock report (Excel)' }));

    await waitFor(() => expect(exportLowStockReport).toHaveBeenCalledWith('run-1'));
    // The order sheet is NOT started by this item.
    expect(exportOrderSheet).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(toastSuccess).toHaveBeenCalledWith(
        'Preparing the low stock report - it will appear in My Downloads.',
      ),
    );
    expect(invalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['my-downloads'] }),
    );
    expect(invalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['entity-downloads', 'reorder_run', 'run-1'] }),
    );
  });

  it('AC-2: a refused export toasts the extracted message (the 422 "Narrow the plan first" '
    + 'text reaches the buyer)', async () => {
    exportLowStockReport.mockRejectedValue(new Error('Narrow the plan first'));
    renderView();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Low stock report (Excel)' }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Narrow the plan first'));
  });

  it('AC-1: all three export items disable while ANY export is in flight', async () => {
    let resolveExport: (value: unknown) => void = () => {};
    exportLowStockReport.mockImplementation(
      () => new Promise((resolve) => { resolveExport = resolve; }),
    );
    renderView();
    const user = userEvent.setup();

    const lowStock = await screen.findByRole('button', { name: 'Low stock report (Excel)' });
    const pdf = screen.getByRole('button', { name: 'Order sheet PDF' });
    const xlsx = screen.getByRole('button', { name: 'Order sheet Excel' });
    expect(lowStock).not.toBeDisabled();

    await user.click(lowStock);

    await waitFor(() => expect(lowStock).toBeDisabled());
    expect(pdf).toBeDisabled();
    expect(xlsx).toBeDisabled();
    expect(exportLowStockReport).toHaveBeenCalledTimes(1);

    resolveExport({ id: 'dl-9', kind: 'low_stock_xlsx', status: 'pending', filename: null });
    await waitFor(() => expect(lowStock).not.toBeDisabled());
  });
});
