/**
 * SCM M8 — ReorderPlanningView (slice D). The reorder page opens straight to
 * today's scheduled snapshot (no "Run planning" click), falls back to an empty
 * state on a fresh install, and reflects a PAST run in its header with that run's
 * date + time.
 *   M8-D3 opens to today's plan · M8-D4 empty state + Manual plan · M8-D11 past-run header
 *   M8-C12 "Stock allocation" summary card
 *
 * The data hooks + heavy child grids are mocked so the orchestration is isolated.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { TodayRun } from '../services/reorderRunService';

const useTodayRun = vi.fn();
const useReorderRun = vi.fn();
const useAllDispositionRecommendations = vi.fn();
vi.mock('../hooks/useReorderRun', () => ({
  useTodayRun: () => useTodayRun(),
  useReorderRun: () => useReorderRun(),
  useAllDispositionRecommendations: (...a: unknown[]) => useAllDispositionRecommendations(...a),
  todayRunKey: ['scm', 'reorder', 'today'],
  runHistoryKey: ['scm', 'reorder', 'history'],
}));

const useReorderPlan = vi.fn();
vi.mock('../hooks/useReorderPlan', () => ({ useReorderPlan: (...a: unknown[]) => useReorderPlan(...a) }));

vi.mock('../hooks/useDecisions', () => ({ decisionsKey: (id: string | null) => ['scm', 'reorder', 'decisions', id] }));

// Heavy children stubbed to sentinels so we assert orchestration, not their internals.
vi.mock('./CashCopilotResults', () => ({ CashCopilotResults: () => <div>cash-copilot</div> }));
vi.mock('./PlanAssistant', () => ({ PlanAssistant: () => <div>plan-assistant</div> }));
vi.mock('./DispositionResultsGrid', () => ({ DispositionResultsGrid: () => <div>disposition-grid</div> }));
vi.mock('./RunHistoryPanel', () => ({ RunHistoryPanel: () => <div>run-history</div> }));
vi.mock('./RunPlanningModal', () => ({ RunPlanningModal: ({ open }: { open: boolean }) => (open ? <div>manual-plan-modal</div> : null) }));
// Its own channels and dialogs are UploadDataMenu.test.tsx's subject. What this file
// checks is that the page OFFERS it, in both the populated and the empty state.
vi.mock('./UploadDataMenu', () => ({ UploadDataMenu: () => <div>upload-data-menu</div> }));

import { ReorderPlanningView } from './ReorderPlanningView';

const todayRun = (over: Partial<TodayRun> = {}): TodayRun => ({
  run_id: 'run-today',
  status: 'completed',
  buy_scope: 'network',
  warehouse_codes: ['WH-KL'],
  warehouse_count: 1,
  started_at: '2026-07-15T06:00:00',
  finished_at: '2026-07-15T06:00:08',
  is_today: true,
  summary: { buy_count: 7, disposition_count: 3, exception_count: 0, total_cash_impact: 125000, recommendation_count: 10 },
  ...over,
});

function stubToday(data: TodayRun | null, extra: Record<string, unknown> = {}) {
  useTodayRun.mockReturnValue({ data, isLoading: false, isError: false, error: null, refetch: vi.fn(), ...extra });
}

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ReorderPlanningView />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useTodayRun.mockReset();
  useReorderRun.mockReset().mockReturnValue({ run: null, isRunning: false, isComplete: false, isFailed: false, error: null, start: vi.fn(), reset: vi.fn() });
  useAllDispositionRecommendations.mockReset().mockReturnValue({ data: [], isLoading: false });
  useReorderPlan.mockReset().mockReturnValue({ isLoading: false, isError: false, error: null, refetch: vi.fn(), applyProposalLine: vi.fn(), rows: [] });
});

describe('ReorderPlanningView — opens to today (M8-D3 / M8-C12)', () => {
  it('renders today’s plan header + the buy co-pilot without a run click', () => {
    stubToday(todayRun());
    renderView();
    expect(screen.getByText(/Today's plan · /)).toBeInTheDocument();
    expect(screen.getByText('cash-copilot')).toBeInTheDocument();
    expect(screen.getByText('plan-assistant')).toBeInTheDocument();
    // M8-C12 — the disposition card is labelled "Stock allocation"
    expect(screen.getByText('Stock allocation')).toBeInTheDocument();
  });
});

describe('ReorderPlanningView — first-view fallback (M8-D4)', () => {
  it('shows the empty state + Manual plan when no run exists yet', () => {
    stubToday(null);
    renderView();
    expect(screen.getByText('No plan yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Manual plan/i })).toBeInTheDocument();
  });
});

describe('ReorderPlanningView — loading + error', () => {
  it('renders a skeleton while today’s run is loading (no header yet)', () => {
    useTodayRun.mockReturnValue({ data: null, isLoading: true, isError: false, error: null, refetch: vi.fn() });
    renderView();
    expect(screen.queryByText(/Today's plan/)).not.toBeInTheDocument();
    expect(screen.queryByText('No plan yet')).not.toBeInTheDocument();
  });

  it('renders the error card with a retry when today’s run fails to load', () => {
    useTodayRun.mockReturnValue({ data: null, isLoading: false, isError: true, error: new Error('boom'), refetch: vi.fn() });
    renderView();
    expect(screen.getByText('boom')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Try again/i })).toBeInTheDocument();
  });
});

describe('ReorderPlanningView — the upload channels', () => {
  // The plan is computed from these files, so loading them is a planning action and
  // belongs on this screen.
  it('offers the upload menu from the toolbar', () => {
    stubToday(todayRun());
    renderView();

    expect(screen.getByText('upload-data-menu')).toBeInTheDocument();
  });

  it('offers the same menu from the no-plan empty state', () => {
    // A fresh install has no plan AND no book - the upload has to be reachable from
    // the state the user actually lands in, not only from a populated plan.
    stubToday(null);
    renderView();

    expect(screen.getByText('upload-data-menu')).toBeInTheDocument();
  });
});

describe('ReorderPlanningView — past-run header (M8-D11)', () => {
  it('stops saying "Today\'s plan" and shows the run\'s date + time when viewing a past run', () => {
    // is_today=false → the default run is a past snapshot, not today's.
    stubToday(todayRun({ run_id: 'run-old', is_today: false }));
    renderView();
    expect(screen.queryByText(/Today's plan/)).not.toBeInTheDocument();
    // header reads "Plan · <date>, <time>" (started_at 06:00 UTC → 14:00 Asia/KL)
    // and the past-run banner shows — the point is date AND time, not "Today's plan".
    expect(screen.getByText(/Plan · 15 Jul 2026, 14:00/)).toBeInTheDocument();
    expect(screen.getByText(/You are viewing a past run/i)).toBeInTheDocument();
  });
});
