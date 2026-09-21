/**
 * Import job detail page - Back button, RED tests (AC-DS-12, AC-DS-13).
 *
 * Plan: documentation/plans/autocount/PLAN-autocount-pull-discard.md
 * UAC:  documentation/plans/autocount/autocount-pull-discard-acceptance-criteria.md
 *
 * Today the header's Back button is hardcoded "Back to Import Jobs" in every case (4 places
 * in `page.tsx`; the one under test here is the main, loaded-job render, which keeps
 * `?page=&pageSize=` when the caller came from the Import Jobs list). The plan asks for two
 * MORE labels/targets on a pull job opened WITHOUT a `page` query param: "Back to Products"
 * (`/master-data-management/products`, confirmed against `apps-dropdown-menu.tsx`'s own Products
 * link) or "Back to Stock" (`/inventory-management/stock`, confirmed against where
 * `StockBalanceGrid` is mounted, `inventory-management/stock/page.tsx`, and `config/menu.
 * config.tsx`'s own `path`) - everything else (WITH a `page` param, or any non-pull job type)
 * keeps today's behaviour unchanged.
 *
 * Mocking style follows `page.autocountPull.test.tsx` (same page, same mocked dependency set) -
 * `useSearchParams` here is a test-controlled mutable `URLSearchParams` so each test can drive a
 * different query string without a second render harness.
 *
 * RED reason: AC-DS-12 (no `page` param, pull job -> "Back to Products"/"Back to Stock") is
 * genuinely new behaviour the page does not have yet. AC-DS-13 (`page` param, or a non-pull job,
 * keeps "Back to Import Jobs") is largely already true today - listed as a guard per the
 * captain's test list, not because it currently reds.
 */
import React, { Suspense } from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

let searchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParams,
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
  AutocountPullReview: ({ jobId }: { jobId: string }) => (
    <div data-testid="autocount-pull-review" data-job-id={jobId} />
  ),
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
  searchParams = new URLSearchParams();
  getImportJob.mockReset();
  getImportJobs.mockReset();
  getImportJobSourceUrl.mockReset();
  getImportJobStatus.mockReset();
  usePull.mockReset();
  getImportJobs.mockResolvedValue({ data: [], pagination: { total: 0, page: 1 }, empty: true });
  await PARAMS;
});

describe('AC-DS-12: opened WITHOUT a `page` query param', () => {
  it('a products pull reads "Back to Products" and links to /master-data-management/products', async () => {
    getImportJob.mockResolvedValue(ordinaryJob({ job_type: 'autocount_products_pull', status: 'finished' }));
    usePull.mockReturnValue({ data: { job_id: 'job-1', phase: 'review' } });

    await act(async () => {
      render(wrap(<ImportJobDetailPage params={PARAMS} />));
    });
    await screen.findByTestId('autocount-pull-review');

    const link = screen.getByRole('link', { name: /Back to Products/ });
    expect(link).toHaveAttribute('href', '/master-data-management/products');
  });

  it('a stock pull reads "Back to Stock" and links to /inventory-management/stock', async () => {
    getImportJob.mockResolvedValue(ordinaryJob({ job_type: 'autocount_stock_pull', status: 'finished' }));
    usePull.mockReturnValue({ data: { job_id: 'job-1', phase: 'review' } });

    await act(async () => {
      render(wrap(<ImportJobDetailPage params={PARAMS} />));
    });
    await screen.findByTestId('autocount-pull-review');

    const link = screen.getByRole('link', { name: /Back to Stock/ });
    expect(link).toHaveAttribute('href', '/inventory-management/stock');
  });
});

describe('AC-DS-13: keeps "Back to Import Jobs" (guards - largely already true today)', () => {
  it('a pull job opened WITH a `page` query param keeps "Back to Import Jobs" and the page/pageSize', async () => {
    searchParams = new URLSearchParams('page=2&pageSize=25');
    getImportJob.mockResolvedValue(ordinaryJob({ job_type: 'autocount_products_pull', status: 'finished' }));
    usePull.mockReturnValue({ data: { job_id: 'job-1', phase: 'review' } });

    await act(async () => {
      render(wrap(<ImportJobDetailPage params={PARAMS} />));
    });
    await screen.findByTestId('autocount-pull-review');

    expect(screen.queryByRole('link', { name: /Back to Products/ })).not.toBeInTheDocument();
    const link = screen.getByRole('link', { name: /Back to Import Jobs/ });
    expect(link).toHaveAttribute('href', '/system-management/import-jobs?page=2&pageSize=25');
  });

  it('a non-pull job never reads "Back to Products"/"Back to Stock", whatever usePull returns', async () => {
    getImportJob.mockResolvedValue(ordinaryJob({ job_type: 'product_import', status: 'finished' }));
    usePull.mockReturnValue({ data: undefined });

    render(wrap(<ImportJobDetailPage params={PARAMS} />));
    await screen.findByText('Job Summary');

    expect(screen.queryByRole('link', { name: /Back to Products/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Back to Stock/ })).not.toBeInTheDocument();
    const link = screen.getByRole('link', { name: /Back to Import Jobs/ });
    expect(link).toHaveAttribute('href', '/system-management/import-jobs');
  });
});
