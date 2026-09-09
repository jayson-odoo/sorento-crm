/**
 * AC-S10.1/AC-S10.3 (round 2, reorder-feedback-9sep): the plan's Actions menu offers
 * "Order sheet PDF" / "Order sheet Excel" calling `downloadOrderSummaryExport(runId, fmt)`,
 * and the retired "Order summary" entry is gone.
 *
 * `PlanLinesSection` is mocked to a thin stand-in rendering `secondaryActions` as buttons -
 * it owns none of the behaviour under test (that lives in `ReorderPlanView`'s own `actions`
 * array) and its real implementation pulls in the whole plan-lines grid stack.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import type { ReorderRun } from '../types/reorder.types';

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/reorder/run-1',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const downloadOrderSummaryExport = vi.fn().mockResolvedValue(undefined);
vi.mock('../services/summaryOrderService', () => ({
  downloadOrderSummaryExport: (...args: unknown[]) => downloadOrderSummaryExport(...args),
}));

vi.mock('../services/reorderRunService', () => ({
  resetRunDecisions: vi.fn(),
}));

const RUN: ReorderRun = {
  run_id: 'run-1',
  status: 'completed',
  stage: 'done',
  buy_scope: 'all',
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
        <button key={action.key} onClick={() => action.onClick?.()}>
          {action.label}
        </button>
      ))}
    </div>
  ),
}));

import { ReorderPlanView } from './ReorderPlanView';

function renderView() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ReorderPlanView runId="run-1" />
    </QueryClientProvider>,
  );
}

describe('ReorderPlanView Actions menu (AC-S10.1/AC-S10.3)', () => {
  beforeEach(() => {
    downloadOrderSummaryExport.mockClear();
  });

  it('offers Order sheet PDF and Order sheet Excel, and drops Order summary', async () => {
    renderView();
    expect(await screen.findByRole('button', { name: 'Order sheet PDF' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Order sheet Excel' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Order summary' })).not.toBeInTheDocument();
  });

  it('calls downloadOrderSummaryExport(runId, "pdf") when Order sheet PDF is clicked', async () => {
    renderView();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Order sheet PDF' }));
    expect(downloadOrderSummaryExport).toHaveBeenCalledWith('run-1', 'pdf');
  });
});
