/**
 * AutocountPullReview - preview progress bar (B3, small-fix track).
 *
 * A full-size products preview sits 4-5 minutes on a bare spinner today. Once the preview
 * task publishes `preview_progress`, the `previewing` phase shows the SAME progress bar
 * component the `building` phase uses, with "N of M" text; a bare spinner remains while
 * `preview_progress` is still null (nothing published yet).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

const usePull = vi.fn();
const useDownloadPullXlsx = vi.fn();
const useConfirmPull = vi.fn();
vi.mock('../hooks/useAutocountPull', () => ({
  usePull: (...a: unknown[]) => usePull(...a),
  useDownloadPullXlsx: (...a: unknown[]) => useDownloadPullXlsx(...a),
  useConfirmPull: (...a: unknown[]) => useConfirmPull(...a),
  // No-op here: this file mocks the whole hooks module and never wraps its renders in a
  // `QueryClientProvider`. The rows-refresh behaviour itself (D1, small-fix track) has its
  // own coverage, unmocked, in `AutocountPullReview.rowsRefresh.test.tsx`.
  useRefreshRowsOnReview: vi.fn(),
}));

vi.mock('./PullChangesTab', () => ({ PullChangesTab: () => <div data-testid="changes-tab-body" /> }));
vi.mock('./PullExcelViewTab', () => ({ PullExcelViewTab: () => <div data-testid="excel-tab-body" /> }));
vi.mock('./PullCompareTab', () => ({ PullCompareTab: () => <div data-testid="compare-tab-body" /> }));

import { AutocountPullReview } from './AutocountPullReview';

function basePull(overrides: Record<string, unknown> = {}) {
  return {
    job_id: 'job-1',
    entity: 'products',
    phase: 'previewing',
    progress: null,
    preview_progress: null,
    header: null,
    counts: null,
    confirm_blocked_reason: null,
    compare: null,
    apply_job_id: null,
    warnings: [],
    ...overrides,
  };
}

beforeEach(() => {
  usePull.mockReset();
  useDownloadPullXlsx.mockReset();
  useConfirmPull.mockReset();
  useDownloadPullXlsx.mockReturnValue({ mutate: vi.fn(), isPending: false });
  useConfirmPull.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

describe('AutocountPullReview - preview progress (B3)', () => {
  it('shows the progress bar and "N of M" text once preview_progress is published', () => {
    usePull.mockReturnValue({
      data: basePull({ preview_progress: { processed: 300, total: 1200 } }),
      isLoading: false,
    });

    const { container } = render(<AutocountPullReview jobId="job-1" />);

    expect(screen.getByRole('progressbar')).toBeInTheDocument();
    expect(screen.getByText('300 of 1,200')).toBeInTheDocument();
    const indicator = container.querySelector('[data-slot="progress-indicator"]') as HTMLElement;
    // 300/1200 = 25% -> translateX(-75%)
    expect(indicator.style.transform).toContain('-75%');
  });

  it('shows a bare spinner while preview_progress is still null', () => {
    usePull.mockReturnValue({
      data: basePull({ preview_progress: null }),
      isLoading: false,
    });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Loading')).toBeInTheDocument();
  });

  it('a completed preview (processed === total) still renders, at 100%', () => {
    usePull.mockReturnValue({
      data: basePull({ preview_progress: { processed: 10, total: 10 } }),
      isLoading: false,
    });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.getByText('10 of 10')).toBeInTheDocument();
  });
});
