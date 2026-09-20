/**
 * Import job detail page - AutoCount pull poll burst (B1, small-fix track).
 *
 * Reported live: on the Building -> Preparing transition the page fired about 40
 * `GET /api/v1/autocount/pulls/{id}` requests in 350ms, then settled to the correct
 * one-per-10s cadence. This exercises the REAL `usePull` hook (from BOTH of its call
 * sites - `ImportJobDetailPage` and `AutocountPullReview`, unmocked, exactly as they
 * run together in production) against a mocked `autocountPullService`, and drives the
 * poll's own 10s tick to flip the mocked response from `building` to `previewing` -
 * the same transition the owner saw. Asserts the service is called at most twice
 * within the second following the flip - one settled call is correct, a handful more
 * from two independent observers sharing the query key is tolerated, but not a burst.
 */
import React, { Suspense } from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/system-management/import-jobs/job-1',
}));

vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const getImportJob = vi.fn();
const getImportJobs = vi.fn();
const getImportJobSourceUrl = vi.fn();
const getImportJobStatus = vi.fn();
vi.mock('../services/importJobService', () => ({
  getImportJob: (...a: unknown[]) => getImportJob(...a),
  getImportJobs: (...a: unknown[]) => getImportJobs(...a),
  getImportJobSourceUrl: (...a: unknown[]) => getImportJobSourceUrl(...a),
  getImportJobStatus: (...a: unknown[]) => getImportJobStatus(...a),
}));

vi.mock('../components/OutcomeBreakdownCard', () => ({
  OutcomeBreakdownCard: () => <div data-testid="outcome-breakdown" />,
}));
vi.mock('../components/ImportJobRowsCard', () => ({
  ImportJobRowsCard: () => <div data-testid="rows-card" />,
}));
vi.mock('../components/PlanningChangeOutcomeCard', () => ({
  PlanningChangeOutcomeCard: () => <div data-testid="planning-change" />,
}));

const getPull = vi.fn();
vi.mock('../autocount-pull/services/autocountPullService', () => ({
  getPull: (...a: unknown[]) => getPull(...a),
  getCurrentPull: vi.fn(),
  startPull: vi.fn(),
  getPullRows: vi.fn(),
  downloadPullXlsx: vi.fn(),
  comparePull: vi.fn(),
  confirmPull: vi.fn(),
}));

import ImportJobDetailPage from './page';

const PARAMS = Promise.resolve({ id: 'job-1' });

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return (
    <React.StrictMode>
      <QueryClientProvider client={client}>
        <Suspense fallback={null}>{ui}</Suspense>
      </QueryClientProvider>
    </React.StrictMode>
  );
}

function ordinaryJob(overrides: Record<string, unknown> = {}) {
  return {
    id: 'job-1',
    job_id: 'job-1',
    job_type: 'autocount_products_pull',
    status: 'started',
    user_id: 'me',
    total_rows: 5,
    processed_rows: 5,
    successful_rows: 5,
    failed_rows: 0,
    skipped_rows: 0,
    result: null,
    error: null,
    created_at: new Date('2026-09-20T00:00:00Z'),
    ...overrides,
  };
}

function pullWithPhase(phase: string) {
  return {
    job_id: 'job-1',
    entity: 'products',
    phase,
    progress: null,
    header: null,
    counts: null,
    confirm_blocked_reason: null,
    compare: null,
    apply_job_id: null,
    apply_status: null,
    warnings: [],
  };
}

beforeEach(async () => {
  cleanup();
  getImportJob.mockReset();
  getImportJobs.mockReset();
  getImportJobSourceUrl.mockReset();
  getImportJobStatus.mockReset();
  getPull.mockReset();
  getImportJobs.mockResolvedValue({ data: [], pagination: { total: 0, page: 1 }, empty: true });
  getImportJobStatus.mockResolvedValue({ job_id: 'job-1', status: 'started' });
  await PARAMS;
});

afterEach(() => {
  vi.useRealTimers();
});

describe('B1: no poll burst on the building -> previewing transition', () => {
  it('calls getPull at most twice within the first second after the flip', async () => {
    getImportJob.mockResolvedValue(ordinaryJob());
    let phase = 'building';
    getPull.mockImplementation(() => Promise.resolve(pullWithPhase(phase)));

    vi.useFakeTimers();
    await act(async () => {
      render(wrap(<ImportJobDetailPage params={PARAMS} />));
    });
    // Let the initial mount settle (job query + both usePull observers' first fetch).
    for (let i = 0; i < 20; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
    }
    expect(screen.getByText('Job Summary')).toBeInTheDocument();

    // Flip the mocked phase, then let the poll's own 10s tick pick it up - the same
    // shape as the live transition (FoundryX finishes Building, the next poll sees
    // Preparing for the first time).
    phase = 'previewing';
    const callsBeforeFlip = getPull.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    const callsRightAfterFlip = getPull.mock.calls.length - callsBeforeFlip;

    // Continue for one more second, fine-grained, so a tight re-render/refetch loop
    // (rather than the intended 10s interval) would show up here.
    for (let i = 0; i < 20; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(50);
      });
    }
    const callsWithinFirstSecond = getPull.mock.calls.length - callsBeforeFlip;

    expect(callsRightAfterFlip).toBeLessThanOrEqual(2);
    expect(callsWithinFirstSecond).toBeLessThanOrEqual(2);
  });
});
