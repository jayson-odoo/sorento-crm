/**
 * PLAN-low-stock-report S4 (AC-1): the plan's Actions menu offers "Low stock report Excel"
 * directly under "Order sheet Excel".
 *
 * PLAN-excel-preview-26sep S1 (AC-16; owner ruling 26 Sep, Q3): the item OPENS the low stock
 * report page for this run, where the split and filters are chosen against a preview. The
 * split dialog is gone; nothing is exported from this screen.
 *
 * Same stand-ins as `ReorderPlanView.orderSheet.test.tsx`: `PlanLinesSection` renders the
 * toolbar actions as buttons (it owns none of the behaviour under test, and its real
 * implementation pulls in the whole plan-lines grid stack), and the service functions are
 * the only things mocked below the hooks.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import type { ReorderRun } from '../types/reorder.types';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/reorder/run-1',
  useRouter: () => ({ push }),
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
vi.mock('../services/summaryOrderService', async () => {
  const actual = await vi.importActual<typeof import('../services/summaryOrderService')>(
    '../services/summaryOrderService',
  );
  return {
    ...actual,
    exportOrderSheet: (...args: unknown[]) => exportOrderSheet(...args),
    getOrderSummaryDemand: (...args: unknown[]) => getOrderSummaryDemand(...args),
  };
});

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

describe('ReorderPlanView Actions menu - low stock report', () => {
  beforeEach(() => {
    exportOrderSheet.mockReset();
    getOrderSummaryDemand.mockReset();
    push.mockReset();
    toastSuccess.mockClear();
    toastError.mockClear();
  });

  it('AC-1: offers "Low stock report Excel" directly under "Order sheet Excel"', async () => {
    renderView();
    expect(
      await screen.findByRole('button', { name: 'Low stock report Excel' }),
    ).toBeInTheDocument();

    const exportKeys = renderedActions
      .map((a) => a.key)
      .filter((k) => k.startsWith('order_sheet') || k === 'low_stock_xlsx');
    expect(exportKeys).toEqual(['order_sheet_pdf', 'order_sheet_xlsx', 'low_stock_xlsx']);
  });

  it('AC-16: the item opens the run low stock report page, with no dialog and no export',
    async () => {
      renderView();
      const user = userEvent.setup();

      await user.click(await screen.findByRole('button', { name: 'Low stock report Excel' }));

      await waitFor(() => expect(push).toHaveBeenCalledWith('/scm/low-stock-report/run-1'));
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(exportOrderSheet).not.toHaveBeenCalled();
      expect(toastSuccess).not.toHaveBeenCalled();
    });
});
