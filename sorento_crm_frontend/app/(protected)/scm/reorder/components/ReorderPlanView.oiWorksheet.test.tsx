/**
 * Lane C, PLAN-order-sheet-oi-reports-22sep.md (AC-C1): the plan's Actions menu offers a
 * FOURTH export - "OI worksheet Excel" - directly under "Low stock report Excel", going
 * through the same async My Downloads pipeline as the other three. ALL FOUR items disable
 * while ANY of the three export mutations is pending.
 *
 * Same stand-ins as `ReorderPlanView.lowStock.test.tsx`: `PlanLinesSection` renders the
 * toolbar actions as buttons, and the service functions are the only things mocked below
 * the hooks - the mutations, their query invalidation and their toasts all run for real.
 *
 * "OI worksheet Excel" does not exist on the menu yet, so AC-1's button lookup fails to
 * find the role - `TestingLibraryElementError: Unable to find an accessible element` -
 * not a fixture bug, until C1-FE lands.
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
const exportOiWorksheet = vi.fn();
const getOrderSummaryDemand = vi.fn();
// `importActual` keeps the module's other exports real; only the functions this file
// controls are stubbed.
vi.mock('../services/summaryOrderService', async () => {
  const actual = await vi.importActual<typeof import('../services/summaryOrderService')>(
    '../services/summaryOrderService',
  );
  return {
    ...actual,
    exportOrderSheet: (...args: unknown[]) => exportOrderSheet(...args),
    exportOiWorksheet: (...args: unknown[]) => exportOiWorksheet(...args),
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

describe('ReorderPlanView Actions menu - OI worksheet (AC-C1)', () => {
  beforeEach(() => {
    exportOrderSheet.mockReset();
    exportOiWorksheet.mockReset();
    getOrderSummaryDemand.mockReset();
    toastSuccess.mockClear();
    toastError.mockClear();
  });

  it('AC-C1: offers "OI worksheet Excel" directly under "Low stock report Excel"', async () => {
    renderView();
    expect(
      await screen.findByRole('button', { name: 'OI worksheet Excel' }),
    ).toBeInTheDocument();

    const exportKeys = renderedActions
      .map((a) => a.key)
      .filter((k) => k.startsWith('order_sheet') || k === 'low_stock_xlsx' || k === 'oi_worksheet_xlsx');
    expect(exportKeys).toEqual([
      'order_sheet_pdf', 'order_sheet_xlsx', 'low_stock_xlsx', 'oi_worksheet_xlsx',
    ]);
  });

  it('AC-C1/AC-C2: calls exportOiWorksheet(runId), invalidates my-downloads and this '
    + "run's entity-downloads key, and toasts the preparing message", async () => {
    exportOiWorksheet.mockResolvedValue({
      id: 'dl-42', kind: 'oi_worksheet_xlsx', status: 'pending', filename: null,
    });
    const { invalidateQueries } = renderView();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'OI worksheet Excel' }));

    await waitFor(() => expect(exportOiWorksheet).toHaveBeenCalledWith('run-1'));
    expect(exportOrderSheet).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(toastSuccess).toHaveBeenCalledWith(
        'Preparing the OI worksheet - it will appear in My Downloads.',
      ),
    );
    expect(invalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['my-downloads'] }),
    );
    expect(invalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['entity-downloads', 'reorder_run', 'run-1'] }),
    );
  });

  it('AC-C2: a refused export toasts the extracted message', async () => {
    exportOiWorksheet.mockRejectedValue(new Error('Narrow the plan first'));
    renderView();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'OI worksheet Excel' }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Narrow the plan first'));
  });

  it('AC-C1: the three export items disable while ANY export is in flight; the low stock '
    + 'item opens a page (PLAN-excel-preview-26sep S1), so it stays enabled',
    async () => {
    let resolveExport: (value: unknown) => void = () => {};
    exportOiWorksheet.mockImplementation(
      () => new Promise((resolve) => { resolveExport = resolve; }),
    );
    renderView();
    const user = userEvent.setup();

    const worksheet = await screen.findByRole('button', { name: 'OI worksheet Excel' });
    const pdf = screen.getByRole('button', { name: 'Order sheet PDF' });
    const xlsx = screen.getByRole('button', { name: 'Order sheet Excel' });
    const lowStock = screen.getByRole('button', { name: 'Low stock report Excel' });
    expect(worksheet).not.toBeDisabled();

    await user.click(worksheet);

    await waitFor(() => expect(worksheet).toBeDisabled());
    expect(pdf).toBeDisabled();
    expect(xlsx).toBeDisabled();
    expect(lowStock).not.toBeDisabled();
    expect(exportOiWorksheet).toHaveBeenCalledTimes(1);

    resolveExport({ id: 'dl-42', kind: 'oi_worksheet_xlsx', status: 'pending', filename: null });
    await waitFor(() => expect(worksheet).not.toBeDisabled());
  });
});
