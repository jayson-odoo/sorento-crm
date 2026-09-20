/**
 * AutocountPullReview - rows-cache refresh on review (D1, small-fix track).
 *
 * `AutocountPullReview.test.tsx` mocks `PullChangesTab` (and therefore `ImportJobRowsCard`)
 * away entirely, so it cannot see the defect: the Changes tab delegates to the SAME
 * `useImportJobRows` / `import-job-rows` query key every other importer's job detail page
 * uses, with a 60s `staleTime` shared across all of them. A rows fetch that ran while a pull
 * was still `building`/`previewing` (or any other mount of that key inside the 60s window -
 * a prior visit to the same job, a back/forward nav) can still be served, stale and empty,
 * once the pull reaches `review`.
 *
 * This file renders the REAL `PullChangesTab` -> `ImportJobRowsCard` -> `useImportJobRows`
 * chain against a REAL `QueryClient`, with only the rows SERVICE call
 * (`getImportJobRows`) mocked - and the REAL `useRefreshRowsOnReview` hook (only `usePull` /
 * `useDownloadPullXlsx` / `useConfirmPull` are mocked, per layering: component -> hook).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ImportJobRow } from '../../types/importJob.types';

const usePull = vi.fn();
const useDownloadPullXlsx = vi.fn();
const useConfirmPull = vi.fn();
vi.mock('../hooks/useAutocountPull', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useAutocountPull')>();
  return {
    ...actual,
    usePull: (...a: unknown[]) => usePull(...a),
    useDownloadPullXlsx: (...a: unknown[]) => useDownloadPullXlsx(...a),
    useConfirmPull: (...a: unknown[]) => useConfirmPull(...a),
  };
});

// Not under test here - kept out so a click into either tab can never fire a real network
// call; `PullChangesTab` (and `ImportJobRowsCard` beneath it) stay real.
vi.mock('./PullExcelViewTab', () => ({ PullExcelViewTab: () => <div data-testid="excel-tab-body" /> }));
vi.mock('./PullCompareTab', () => ({ PullCompareTab: () => <div data-testid="compare-tab-body" /> }));

const getImportJobRows = vi.fn();
const downloadImportJobRowsCsv = vi.fn();
vi.mock('../../services/importJobService', () => ({
  getImportJobRows: (...a: unknown[]) => getImportJobRows(...a),
  downloadImportJobRowsCsv: (...a: unknown[]) => downloadImportJobRowsCsv(...a),
}));

import { AutocountPullReview } from './AutocountPullReview';

const JOB_ID = '226ea85c-0000-4000-8000-000000000000';
const ROWS_QUERY_KEY = ['import-job-rows', JOB_ID, 0, 25, undefined, undefined, undefined];

const EIGHT_ROWS: ImportJobRow[] = [
  {
    id: 'row-1',
    row_number: 1,
    outcome: 'created',
    code: 'created',
    label: 'Product created',
    message: 'Product created',
    identity: { item_code: 'SRTKT1861SS' },
  },
  ...Array.from({ length: 7 }, (_, i) => ({
    id: `row-fail-${i}`,
    row_number: i + 2,
    outcome: 'failed' as const,
    code: 'row_error',
    label: 'Row could not be written',
    message: `Price to zero rejected: manual override required (row ${i + 2})`,
    identity: { item_code: `SRTKT186${i}SS` },
  })),
];

function basePull(overrides: Record<string, unknown> = {}) {
  return {
    job_id: JOB_ID,
    entity: 'products',
    phase: 'building',
    progress: null,
    header: null,
    counts: null,
    confirm_blocked_reason: null,
    compare: null,
    apply_job_id: null,
    warnings: [],
    ...overrides,
  };
}

function renderWithClient(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <AutocountPullReview jobId={JOB_ID} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  usePull.mockReset();
  useDownloadPullXlsx.mockReset();
  useConfirmPull.mockReset();
  useDownloadPullXlsx.mockReturnValue({ mutate: vi.fn(), isPending: false });
  useConfirmPull.mockReturnValue({ mutate: vi.fn(), isPending: false });
  getImportJobRows.mockReset();
  downloadImportJobRowsCsv.mockReset();
});

describe('AutocountPullReview - rows cache refresh on review (D1)', () => {
  it('does not serve a stale, empty rows cache once the pull is in review', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // A rows fetch that ran earlier (or during `building`) and cached an empty result -
    // fresh `dataUpdatedAt` (set by `setQueryData` itself), well inside the 60s `staleTime`.
    client.setQueryData(ROWS_QUERY_KEY, { data: [], pagination: { total: 0, page: 1, limit: 25 }, empty: true });
    getImportJobRows.mockResolvedValue({
      data: EIGHT_ROWS,
      pagination: { total: 8, page: 1, limit: 25 },
      empty: false,
    });

    usePull.mockReturnValue({ data: basePull({ phase: 'review' }), isLoading: false });
    renderWithClient(client);

    // RED before the fix: the seeded empty cache entry is fresh, so the Changes tab keeps
    // showing "0 matching" and `getImportJobRows` is never called again.
    await waitFor(() => expect(screen.getByText('8 matching')).toBeInTheDocument());
    expect(
      screen.getByText('Price to zero rejected: manual override required (row 2)'),
    ).toBeInTheDocument();
  });

  it('refetches once on the previewing -> review transition, not again on a later same-phase render', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    getImportJobRows.mockResolvedValue({
      data: EIGHT_ROWS,
      pagination: { total: 8, page: 1, limit: 25 },
      empty: false,
    });

    usePull.mockReturnValue({ data: basePull({ phase: 'previewing' }), isLoading: false });
    const { rerender } = renderWithClient(client);

    // `PullChangesTab` is not mounted while `previewing` (AC scope, `inReview` gate), so no
    // fetch has happened yet.
    expect(getImportJobRows).not.toHaveBeenCalled();

    usePull.mockReturnValue({ data: basePull({ phase: 'review' }), isLoading: false });
    rerender(
      <QueryClientProvider client={client}>
        <AutocountPullReview jobId={JOB_ID} />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(getImportJobRows).toHaveBeenCalledTimes(1));

    // A later render reporting the SAME phase (e.g. a poll tick) must not invalidate again.
    usePull.mockReturnValue({ data: basePull({ phase: 'review' }), isLoading: false });
    rerender(
      <QueryClientProvider client={client}>
        <AutocountPullReview jobId={JOB_ID} />
      </QueryClientProvider>,
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(getImportJobRows).toHaveBeenCalledTimes(1);
  });

  it('a jobId change at the SAME phase still refetches (N4, opus review, fix round 3)', async () => {
    // The app router keeps `AutocountPullReview` mounted across a prev/next job navigation
    // (`RecordNavigation` on the job detail page) - job B can be observed in `review` from
    // the very first render this component sees of it, the same phase job A was already in,
    // so a phase-keyed ref alone would wrongly treat this as "nothing changed".
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const OTHER_JOB_ID = '9fa255f5-0000-4000-8000-000000000000';
    const OTHER_KEY = ['import-job-rows', OTHER_JOB_ID, 0, 25, undefined, undefined, undefined];
    // Job B's own stale, empty cache entry - a prior visit to job B while it was still
    // building, exactly test 1's scenario, just for a different job.
    client.setQueryData(OTHER_KEY, { data: [], pagination: { total: 0, page: 1, limit: 25 }, empty: true });
    getImportJobRows.mockResolvedValue({
      data: EIGHT_ROWS,
      pagination: { total: 8, page: 1, limit: 25 },
      empty: false,
    });

    usePull.mockReturnValue({ data: basePull({ phase: 'review' }), isLoading: false });
    const { rerender } = renderWithClient(client);
    await waitFor(() => expect(getImportJobRows).toHaveBeenCalledTimes(1));

    usePull.mockReturnValue({ data: basePull({ job_id: OTHER_JOB_ID, phase: 'review' }), isLoading: false });
    rerender(
      <QueryClientProvider client={client}>
        <AutocountPullReview jobId={OTHER_JOB_ID} />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText('8 matching')).toBeInTheDocument());
    expect(getImportJobRows).toHaveBeenCalledWith(
      OTHER_JOB_ID,
      expect.objectContaining({ pageIndex: 0 }),
    );
  });
});
