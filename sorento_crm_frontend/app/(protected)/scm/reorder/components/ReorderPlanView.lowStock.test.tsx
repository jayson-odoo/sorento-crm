/**
 * PLAN-low-stock-report S4 (AC-1/AC-2): the plan's Actions menu offers a THIRD export -
 * "Low stock report Excel" - directly under "Order sheet Excel", going through the same
 * async My Downloads pipeline as the two order sheet items.
 *
 * PLAN-low-stock-export-split-25sep (R3, AC-16 to AC-19): the item now opens
 * `LowStockExportDialog` instead of exporting straight away - these tests click through the
 * dialog's own "Export" button (default split "none") rather than asserting the toolbar
 * item calls the export directly.
 *
 * Same stand-ins as `ReorderPlanView.orderSheet.test.tsx`: `PlanLinesSection` renders the
 * toolbar actions as buttons (it owns none of the behaviour under test, and its real
 * implementation pulls in the whole plan-lines grid stack), and the service functions are
 * the only things mocked below the hooks - the mutations, their query invalidation and
 * their toasts all run for real. `previewLowStockExport` is left as the REAL (pure)
 * implementation; only the network-shaped functions are stubbed.
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
const getLowStockPreview = vi.fn();
// `previewLowStockExport` is kept as the REAL export (a pure function over whatever
// `getLowStockPreview` answers) - only the network-shaped functions are stubbed here.
vi.mock('../services/summaryOrderService', async () => {
  const actual = await vi.importActual<typeof import('../services/summaryOrderService')>(
    '../services/summaryOrderService',
  );
  return {
    ...actual,
    exportOrderSheet: (...args: unknown[]) => exportOrderSheet(...args),
    exportLowStockReport: (...args: unknown[]) => exportLowStockReport(...args),
    getOrderSummaryDemand: (...args: unknown[]) => getOrderSummaryDemand(...args),
    getLowStockPreview: (...args: unknown[]) => getLowStockPreview(...args),
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

describe('ReorderPlanView Actions menu - low stock report (AC-1/AC-2)', () => {
  beforeEach(() => {
    exportOrderSheet.mockReset();
    exportLowStockReport.mockReset();
    getOrderSummaryDemand.mockReset();
    getLowStockPreview.mockReset();
    getLowStockPreview.mockResolvedValue({
      rows: 100,
      sheet_counts: { supplier: 5, category: 3, supplier_category: 8 },
    });
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

  it('AC-16/AC-17: opens the split dialog, then Export calls exportLowStockReport(runId, '
    + '"none"), invalidates my-downloads and this run\'s entity-downloads key, and toasts '
    + 'the preparing message', async () => {
    exportLowStockReport.mockResolvedValue({
      id: 'dl-9', kind: 'low_stock_xlsx', status: 'pending', filename: null,
    });
    const { invalidateQueries } = renderView();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Low stock report Excel' }));
    // The dialog opened rather than exporting straight away.
    expect(exportLowStockReport).not.toHaveBeenCalled();
    await user.click(await screen.findByRole('button', { name: 'Export' }));

    await waitFor(() => expect(exportLowStockReport).toHaveBeenCalledWith('run-1', 'none'));
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

  it('AC-18: a refused export toasts the extracted message (the 422 "Narrow the plan first" '
    + 'text reaches the buyer) and the dialog stays open', async () => {
    exportLowStockReport.mockRejectedValue(new Error('Narrow the plan first'));
    renderView();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Low stock report Excel' }));
    await user.click(await screen.findByRole('button', { name: 'Export' }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Narrow the plan first'));
    // Nothing else changes: the dialog's own Export button is still on screen.
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
  });

  it('AC-19: all three export items disable while the dialog\'s export is in flight', async () => {
    let resolveExport: (value: unknown) => void = () => {};
    exportLowStockReport.mockImplementation(
      () => new Promise((resolve) => { resolveExport = resolve; }),
    );
    renderView();
    const user = userEvent.setup();

    const lowStock = await screen.findByRole('button', { name: 'Low stock report Excel' });
    const pdf = screen.getByRole('button', { name: 'Order sheet PDF' });
    const xlsx = screen.getByRole('button', { name: 'Order sheet Excel' });
    expect(lowStock).not.toBeDisabled();

    await user.click(lowStock);
    await user.click(await screen.findByRole('button', { name: 'Export' }));

    await waitFor(() => expect(lowStock).toBeDisabled());
    expect(pdf).toBeDisabled();
    expect(xlsx).toBeDisabled();
    expect(exportLowStockReport).toHaveBeenCalledTimes(1);

    resolveExport({ id: 'dl-9', kind: 'low_stock_xlsx', status: 'pending', filename: null });
    await waitFor(() => expect(lowStock).not.toBeDisabled());
  });

  it('AC-16/AC-17 (reviewer kill test B1/B2): picking Supplier then Export calls '
    + 'exportLowStockReport(\'run-1\', \'supplier\') - not the "none" default every other '
    + 'test in this file leaves selected - and the dialog is GONE once the export '
    + 'resolves (the success counterpart of AC-18\'s "stays open on refusal")', async () => {
    exportLowStockReport.mockResolvedValue({
      id: 'dl-10', kind: 'low_stock_xlsx', status: 'pending', filename: null,
    });
    renderView();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Low stock report Excel' }));
    const supplierRadio = document.getElementById('low-stock-split-supplier');
    expect(supplierRadio).not.toBeNull();
    await user.click(supplierRadio as HTMLElement);
    await user.click(await screen.findByRole('button', { name: 'Export' }));

    await waitFor(() =>
      expect(exportLowStockReport).toHaveBeenCalledWith('run-1', 'supplier'),
    );

    // The dialog is gone - no more "Export" button, no dialog role left in the document.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Export' })).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
