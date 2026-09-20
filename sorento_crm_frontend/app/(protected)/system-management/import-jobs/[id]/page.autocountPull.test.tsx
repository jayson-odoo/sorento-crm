/**
 * Import job detail page - AutoCount pull dispatch (AC-RV-1, AC-BD-6; captain's P1, P2).
 *
 * P1: a job whose `job_type` is `autocount_products_pull` (or `autocount_stock_pull`) renders
 * `AutocountPullReview` above the usual cards; any other job type renders exactly as before
 * (no AutocountPullReview, the usual Job Summary card still there).
 * P2: for a building pull the generic 2s job-status poll (`useImportJobStatus`) is not used -
 * pinned here by letting the REAL hook run against a mocked `getImportJobStatus` and asserting
 * it is never called while phase is `building`, even after 10s of fake-timer advancement (a real
 * 2s-interval poll would have fired ~5 times by then).
 *
 * This dispatch logic (`AUTOCOUNT_PULL_JOB_TYPES`, `isPullJob`, `pullStillBuilding`) is already
 * correct in Phase 1 `page.tsx` - it does not depend on `autocountPullService`'s `USE_MOCK`
 * branch at all, so both tests are expected to be GREEN already (guards against a future
 * regression), not red for a missing-contract reason. Listed because the captain's test list
 * names them explicitly.
 */
import React, { Suspense } from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
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

vi.mock('../hooks/useImportJobs', async () => {
  const actual = await vi.importActual<typeof import('../hooks/useImportJobs')>('../hooks/useImportJobs');
  return {
    ...actual,
    useCancelImportJob: () => ({ mutate: vi.fn(), isPending: false }),
  };
});

vi.mock('../components/OutcomeBreakdownCard', () => ({
  OutcomeBreakdownCard: () => <div data-testid="outcome-breakdown" />,
}));
vi.mock('../components/ImportJobRowsCard', () => ({
  ImportJobRowsCard: () => <div data-testid="rows-card" />,
}));
vi.mock('../components/PlanningChangeOutcomeCard', () => ({
  PlanningChangeOutcomeCard: () => <div data-testid="planning-change" />,
}));

const usePull = vi.fn();
vi.mock('../autocount-pull/hooks/useAutocountPull', () => ({
  usePull: (...a: unknown[]) => usePull(...a),
}));
vi.mock('../autocount-pull/components/AutocountPullReview', () => ({
  AutocountPullReview: () => <div data-testid="autocount-pull-review" />,
}));

import ImportJobDetailPage from './page';

const PARAMS = Promise.resolve({ id: 'job-1' });

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return (
    <QueryClientProvider client={client}>
      <Suspense fallback={null}>{ui}</Suspense>
    </QueryClientProvider>
  );
}

function ordinaryJob(overrides: Record<string, unknown> = {}) {
  return {
    id: 'job-1',
    job_id: 'job-1',
    job_type: 'product_import',
    status: 'finished',
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

beforeEach(async () => {
  cleanup();
  getImportJob.mockReset();
  getImportJobs.mockReset();
  getImportJobSourceUrl.mockReset();
  getImportJobStatus.mockReset();
  usePull.mockReset();
  getImportJobs.mockResolvedValue({ data: [], pagination: { total: 0, page: 1 }, empty: true });
  // Pre-resolve so `use(params)` never suspends the very first render in this file (a bare
  // `Promise.resolve` is still pending on the microtask queue the instant it is created).
  await PARAMS;
});

describe('P1: AutocountPullReview dispatch by job_type', () => {
  it('renders AutocountPullReview for job_type autocount_products_pull', async () => {
    getImportJob.mockResolvedValue(ordinaryJob({ job_type: 'autocount_products_pull' }));
    usePull.mockReturnValue({ data: { job_id: 'job-1', phase: 'review' } });

    await act(async () => {
      render(wrap(<ImportJobDetailPage params={PARAMS} />));
    });

    expect(await screen.findByTestId('autocount-pull-review')).toBeInTheDocument();
  });

  it('does NOT render AutocountPullReview for any other job_type, and renders the usual Job Summary card', async () => {
    getImportJob.mockResolvedValue(ordinaryJob({ job_type: 'product_import' }));
    usePull.mockReturnValue({ data: undefined });

    render(wrap(<ImportJobDetailPage params={PARAMS} />));

    expect(await screen.findByText('Job Summary')).toBeInTheDocument();
    expect(screen.queryByTestId('autocount-pull-review')).not.toBeInTheDocument();
  });
});

describe('P2: the generic 2s job poll is not used for a building pull', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('getImportJobStatus is never called while the pull is building, even after 10s', async () => {
    getImportJob.mockResolvedValue(ordinaryJob({ job_type: 'autocount_products_pull', status: 'pending' }));
    usePull.mockReturnValue({ data: { job_id: 'job-1', phase: 'building' } });

    render(wrap(<ImportJobDetailPage params={PARAMS} />));
    // Something from the job query has to land first, or this would trivially pass.
    await screen.findByText('Job Summary');

    vi.useFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });

    expect(getImportJobStatus).not.toHaveBeenCalled();
  });

  it('control: getImportJobStatus IS used for an ordinary in-progress (non-pull) job', async () => {
    getImportJob.mockResolvedValue(ordinaryJob({ job_type: 'product_import', status: 'started' }));
    getImportJobStatus.mockResolvedValue({ job_id: 'job-1', status: 'started' });
    usePull.mockReturnValue({ data: undefined });

    render(wrap(<ImportJobDetailPage params={PARAMS} />));

    await waitFor(() => expect(getImportJobStatus).toHaveBeenCalled());
  });
});

describe('D2 (small-fix track, browser e2e run 3): Results / Outcome breakdown / Rows never render for a pull job', () => {
  it.each(['building', 'previewing', 'review', 'confirmed', 'failed', 'expired'])(
    'phase %s: none of Results, Outcome breakdown or Rows render - only the pull card and Job Summary',
    async (phase) => {
      getImportJob.mockResolvedValue(ordinaryJob({ job_type: 'autocount_products_pull', status: 'finished' }));
      usePull.mockReturnValue({ data: { job_id: 'job-1', phase } });

      render(wrap(<ImportJobDetailPage params={PARAMS} />));

      await screen.findByTestId('autocount-pull-review');
      expect(screen.getByText('Job Summary')).toBeInTheDocument();
      expect(screen.queryByText('Results')).not.toBeInTheDocument();
      expect(screen.queryByTestId('outcome-breakdown')).not.toBeInTheDocument();
      expect(screen.queryByTestId('rows-card')).not.toBeInTheDocument();
    },
  );

  it('an autocount_stock_pull job also never renders the three cards', async () => {
    getImportJob.mockResolvedValue(ordinaryJob({ job_type: 'autocount_stock_pull', status: 'finished' }));
    usePull.mockReturnValue({ data: { job_id: 'job-1', phase: 'review' } });

    render(wrap(<ImportJobDetailPage params={PARAMS} />));

    await screen.findByTestId('autocount-pull-review');
    expect(screen.queryByText('Results')).not.toBeInTheDocument();
    expect(screen.queryByTestId('outcome-breakdown')).not.toBeInTheDocument();
    expect(screen.queryByTestId('rows-card')).not.toBeInTheDocument();
  });

  it('control: a non-pull job type always renders the three cards, whatever usePull returns', async () => {
    getImportJob.mockResolvedValue(ordinaryJob({ job_type: 'product_import', status: 'finished' }));
    usePull.mockReturnValue({ data: { job_id: 'job-1', phase: 'building' } });

    render(wrap(<ImportJobDetailPage params={PARAMS} />));

    await screen.findByText('Job Summary');
    expect(screen.getByText('Results')).toBeInTheDocument();
    expect(screen.getByTestId('outcome-breakdown')).toBeInTheDocument();
    expect(screen.getByTestId('rows-card')).toBeInTheDocument();
  });
});
