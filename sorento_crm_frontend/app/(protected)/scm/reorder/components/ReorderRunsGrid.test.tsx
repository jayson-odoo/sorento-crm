/**
 * The plans list (plan 4.1, UAC A1-A3, A5).
 *
 * A plan is a record, so it is a DataGrid row that opens at its own address. What stood here
 * before was a card of hand-rolled buttons under the latest plan's grid.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReorderRunHistoryItem } from '../services/reorderRunService';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => '/scm/reorder',
  useSearchParams: () => new URLSearchParams(),
}));

// The saved column order/visibility is a server read this suite has no backend for; without
// it stubbed the DataGrid renders no rows in jsdom.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const runsState: { data: { data: ReorderRunHistoryItem[]; pagination: Record<string, number> } } = {
  data: { data: [], pagination: { page: 1, limit: 25, total: 0, total_pages: 1 } },
};
vi.mock('../hooks/useReorderRun', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useReorderRun')>();
  return {
    ...actual,
    useReorderRuns: () => ({
      data: runsState.data,
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    }),
  };
});

// The Start Plan modal has its own suite; here it only has to exist behind the button.
vi.mock('./RunPlanningModal', () => ({
  RunPlanningModal: ({ open }: { open: boolean }) => (open ? <div>start-plan-modal</div> : null),
}));

import { ReorderRunsGrid } from './ReorderRunsGrid';

function run(over: Partial<ReorderRunHistoryItem> = {}): ReorderRunHistoryItem {
  return {
    run_id: 'run-a',
    status: 'completed',
    buy_scope: 'warehouse',
    warehouse_codes: ['BRW'],
    warehouse_count: 1,
    started_at: '2026-08-27T01:50:00',
    finished_at: '2026-08-27T01:52:00',
    plan_horizon_date: '2026-09-30',
    product_count: 184,
    decided_product_count: 20,
    confirmed_product_count: 0,
    summary: {
      buy_count: 120,
      disposition_count: 4,
      exception_count: 0,
      total_cash_impact: 6232043,
      recommendation_count: 184,
    },
    ...over,
  } as ReorderRunHistoryItem;
}

function renderList(runs: ReorderRunHistoryItem[] = [run()]) {
  runsState.data = {
    data: runs,
    pagination: { page: 1, limit: 25, total: runs.length, total_pages: 1 },
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ReorderRunsGrid />
    </QueryClientProvider>,
  );
}

const headerNames = () =>
  Array.from(document.querySelectorAll('thead th')).map((th) => th.textContent?.trim() ?? '');

beforeEach(() => vi.clearAllMocks());

describe('ReorderRunsGrid - the columns (A1)', () => {
  it('lists a plan by when it ran, what it covered and where it is up to', () => {
    renderList();
    expect(headerNames()).toEqual([
      'Plan', 'Sales order cut-off', 'Warehouses', 'Products', 'Lines', 'Decided',
      'Status', 'Cash if all accepted',
    ]);
  });

  it('states the plan by its date and time, never by its id', () => {
    renderList();
    const row = screen.getByText(/27\/08\/2026/).closest('tr') as HTMLElement;
    expect(row.textContent).not.toContain('run-a');
    expect(within(row).getByText('30/09/2026')).toBeInTheDocument();
    expect(within(row).getByText('BRW')).toBeInTheDocument();
    // Products and Lines both read 184 on this plan, which is the normal case.
    expect(within(row).getAllByText('184')).toHaveLength(2);
    expect(within(row).getByText('20 / 184')).toBeInTheDocument();
    expect(within(row).getByText(/6,232,043/)).toBeInTheDocument();
  });

  it('reads "All" for a plan that narrowed to no product list', () => {
    renderList([run({ product_count: null })]);
    expect(screen.getByText('All')).toBeInTheDocument();
  });

  it('says nothing about a cut-off the plan never carried', () => {
    renderList([run({ plan_horizon_date: null })]);
    const row = screen.getByText(/27\/08\/2026/).closest('tr') as HTMLElement;
    expect(within(row).getAllByText('-').length).toBeGreaterThan(0);
  });
});

describe('ReorderRunsGrid - the status is derived (A5)', () => {
  it('a finished plan nobody has confirmed reads Planning', () => {
    renderList([run({ confirmed_product_count: 0 })]);
    expect(screen.getByText('Planning')).toBeInTheDocument();
  });

  it('every product confirmed reads Confirmed', () => {
    renderList([run({ product_count: 184, confirmed_product_count: 184 })]);
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
  });

  it('an unfinished run reads Running', () => {
    renderList([run({ status: 'running', summary: null })]);
    expect(screen.getByText('Running')).toBeInTheDocument();
  });

  it('a failed run reads Failed', () => {
    renderList([run({ status: 'failed', summary: null })]);
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('the scheduled run wears a daily badge; a manual one does not', () => {
    renderList([run({ is_scheduled: true })]);
    expect(screen.getByText('daily')).toBeInTheDocument();
  });

  it('never guesses "daily" from the clock when the backend has not said', () => {
    renderList([run()]);
    expect(screen.queryByText('daily')).not.toBeInTheDocument();
  });
});

describe('ReorderRunsGrid - the toolbar and the row click (A2, A3)', () => {
  it('offers exactly one primary button, Start Plan', () => {
    renderList();
    expect(screen.getByRole('button', { name: /Start Plan/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Manual plan/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Upload data/i })).not.toBeInTheDocument();
  });

  it('Start Plan opens the modal', () => {
    renderList();
    fireEvent.click(screen.getByRole('button', { name: /Start Plan/i }));
    expect(screen.getByText('start-plan-modal')).toBeInTheDocument();
  });

  it('the Actions menu holds the upload entries and Refresh', async () => {
    renderList();
    const trigger = screen.getByRole('button', { name: /Actions/i });
    // Radix opens its menu on pointerdown, not on click.
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
    expect(await screen.findByText('Upload sales orders')).toBeInTheDocument();
    expect(screen.getByText('Upload purchase orders')).toBeInTheDocument();
    expect(screen.getByText('Upload reorder levels')).toBeInTheDocument();
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('clicking anywhere on a row opens that plan', () => {
    renderList();
    fireEvent.click(screen.getByText(/27\/08\/2026/));
    expect(push).toHaveBeenCalledWith('/scm/reorder/run-a');
  });
});
