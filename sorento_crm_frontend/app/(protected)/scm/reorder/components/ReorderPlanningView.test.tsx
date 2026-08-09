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
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { TodayRun } from '../services/reorderRunService';

const useTodayRun = vi.fn();
const useReorderRun = vi.fn();
const useAllDispositionRecommendations = vi.fn();
const useUnlocatedDemand = vi.fn();
vi.mock('../hooks/useReorderRun', () => ({
  useTodayRun: () => useTodayRun(),
  useReorderRun: () => useReorderRun(),
  useUnlocatedDemand: () => useUnlocatedDemand(),
  useAllDispositionRecommendations: (...a: unknown[]) => useAllDispositionRecommendations(...a),
  todayRunKey: ['scm', 'reorder', 'today'],
  runHistoryKey: ['scm', 'reorder', 'history'],
  unlocatedDemandKey: ['scm', 'reorder', 'unlocated-demand'],
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
  in_progress: false,
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
  useUnlocatedDemand.mockReset().mockReturnValue({ data: undefined, isLoading: false });
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
    expect(screen.getByText(/Plan · 15\/07\/2026, 14:00/)).toBeInTheDocument();
    // The banner shows. Which of its two messages appears depends on whether a run has
    // happened today, which is the subject of the group below.
    expect(screen.getByText(/No plan has run today/i)).toBeInTheDocument();
  });
});

describe('ReorderPlanningView — "Back to today\'s plan" has somewhere to go', () => {
  // > "is this working cause I can't seemed to click it to go to today's plan"
  //
  // It was not. The banner shows whenever the run on screen is not today's, which includes
  // the case where NO run has happened today - and then "Back to today's plan" set the
  // selection to null, landed on the same run, and nothing moved. A control that cannot
  // change anything must not be offered; the page has to say why instead.

  it('does not offer the link when there is no today plan to go back to', () => {
    stubToday(todayRun({ run_id: 'run-old', is_today: false }));
    renderView();

    expect(screen.queryByRole('button', { name: /back to today/i })).not.toBeInTheDocument();
  });

  it('says no plan has run today, rather than calling the newest one a past run', () => {
    stubToday(todayRun({ run_id: 'run-old', is_today: false }));
    renderView();

    expect(screen.getByText(/No plan has run today/i)).toBeInTheDocument();
  });

  it('offers the action that does help: running one now', () => {
    stubToday(todayRun({ run_id: 'run-old', is_today: false }));
    renderView();

    fireEvent.click(screen.getByRole('button', { name: /plan now/i }));

    expect(screen.getByText('manual-plan-modal')).toBeInTheDocument();
  });
});

describe('ReorderPlanningView — a plan being built never empties the page', () => {
  // > "i think there is some conflict in backend, cuse I just can't retrieve any data"
  //
  // The job had been enqueued with no worker draining it, so a run sat unfinished all day.
  // The page picked it as today's plan, found no recommendations on it, and showed nothing
  // while 101 completed snapshots sat behind it. An unfinished run is now a banner, not the
  // plan.

  it('keeps showing the last completed plan and says a new one is being built', () => {
    stubToday(todayRun({ in_progress: true }));
    renderView();

    expect(screen.getByText(/Today's plan/)).toBeInTheDocument();
    expect(screen.getByText(/A new plan is being built/i)).toBeInTheDocument();
    expect(screen.getByText(/from the last completed one/i)).toBeInTheDocument();
  });

  it('says nothing about building when every run has finished', () => {
    stubToday(todayRun());
    renderView();

    expect(screen.queryByText(/A new plan is being built/i)).not.toBeInTheDocument();
  });

  it('says the first plan is being built rather than "No plan yet"', () => {
    // Nothing has ever completed, so there is no snapshot to fall back on. "No plan yet"
    // would read as nothing running and invite a second run.
    stubToday(todayRun({ status: 'running', finished_at: null, summary: null, in_progress: true }));
    renderView();

    expect(screen.getByText(/Building the plan/i)).toBeInTheDocument();
    expect(screen.queryByText(/No plan yet/i)).not.toBeInTheDocument();
  });
});

describe('ReorderPlanningView — demand the plan could not net', () => {
  // > "it has a few thousands of committed quantity ... but why when i search
  // >  MWC7624-RL-S10 in the reorder planning, it does not exist"
  //
  // Because the order line names no warehouse, so there is nothing to net it against and
  // the product simply is not on the grid. Absence reads as "nothing to buy" unless the
  // page says otherwise.

  it('says how much committed demand is missing and names the biggest', () => {
    stubToday(todayRun());
    useUnlocatedDemand.mockReturnValue({
      data: {
        lines: 8011,
        products: 770,
        quantity: 1130402,
        sample: [{ product_code: 'MWC7624-RL-S10', quantity: 419 }],
      },
      isLoading: false,
    });
    renderView();

    expect(screen.getByText('770')).toBeInTheDocument();
    expect(screen.getByText(/name no stock location/i)).toBeInTheDocument();
    expect(screen.getByText('MWC7624-RL-S10')).toBeInTheDocument();
  });

  it('says nothing when every order line names where it ships from', () => {
    stubToday(todayRun());
    useUnlocatedDemand.mockReturnValue({
      data: { lines: 0, products: 0, quantity: 0, sample: [] },
      isLoading: false,
    });
    renderView();

    expect(screen.queryByText(/name no stock location/i)).not.toBeInTheDocument();
  });
});
