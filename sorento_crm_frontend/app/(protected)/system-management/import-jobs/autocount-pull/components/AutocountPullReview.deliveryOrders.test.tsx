/**
 * AutocountPullReview - Delivery Orders entity (lane DO-PULL-CRM, AC-DP-42).
 *
 * A third value in the review card's entity switches: the header names the entity, the
 * counters row shows the nine DO counters (plan 1.3), the scope line prints what the pull
 * covered, and Confirm stays enabled (warnings never block). Same harness as
 * `AutocountPullReview.test.tsx` (hooks mocked, tabs stubbed).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

const usePull = vi.fn();
vi.mock('../hooks/useAutocountPull', () => ({
  usePull: (...a: unknown[]) => usePull(...a),
  useDownloadPullXlsx: () => ({ mutate: vi.fn(), isPending: false }),
  useConfirmPull: () => ({ mutate: vi.fn(), isPending: false }),
  useDiscardPull: () => ({ mutate: vi.fn(), isPending: false }),
  useStartPull: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRefreshRowsOnReview: vi.fn(),
}));

vi.mock('./PullChangesTab', () => ({ PullChangesTab: () => <div data-testid="changes-tab-body" /> }));
vi.mock('./PullExcelViewTab', () => ({ PullExcelViewTab: () => <div data-testid="excel-tab-body" /> }));
vi.mock('./PullCompareTab', () => ({ PullCompareTab: () => <div data-testid="compare-tab-body" /> }));

import { AutocountPullReview } from './AutocountPullReview';

const DO_HEADER = {
  snapshotId: 'a1b2c3d4-e5f6-4789-a012-3456789abcde',
  entity: 'delivery_orders',
  companyCode: 'SRT',
  extractedAt: '2026-09-30T02:00:00Z',
  expiresAt: '2026-10-01T02:00:00Z',
  recordCount: 948,
  complete: true,
  contentHash: 'deadbeef',
};

const DO_COUNTS = {
  received: 948,
  created: 500,
  updated: 12,
  adopted: 430,
  unchanged: 3,
  lines_to_delete: 7,
  failed: 2,
  retryable: 1,
  with_warnings: 435,
};

function doPull(overrides: Record<string, unknown> = {}) {
  return {
    job_id: 'f47ac10b-58cc-4372-a567-0e02b2c3d479',
    entity: 'delivery_orders',
    company_code: 'SRT',
    phase: 'review',
    progress: null,
    header: DO_HEADER,
    counts: DO_COUNTS,
    confirm_blocked_reason: null,
    compare: null,
    apply_job_id: null,
    warnings: [],
    scope: null,
    ...overrides,
  };
}

beforeEach(() => {
  usePull.mockReset();
});

describe('AutocountPullReview - delivery orders (AC-DP-42)', () => {
  it('names the entity and shows the nine DO counters with their values', () => {
    usePull.mockReturnValue({ data: doPull(), isLoading: false });

    render(<AutocountPullReview jobId="job-do" />);

    expect(screen.getByText(/AutoCount delivery orders pull, SRT/)).toBeInTheDocument();
    for (const label of [
      'Received',
      'New',
      'Updated',
      'Adopted by number',
      'Unchanged',
      'Lines to delete',
      'Failed',
      'Retry later',
      'With warnings',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText('948')).toBeInTheDocument();
    expect(screen.getByText('430')).toBeInTheDocument();
    expect(screen.getByText('435')).toBeInTheDocument();
    // Warnings never block Confirm (SO-link ruling, 30 Sep).
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Download xlsx' })).toBeInTheDocument();
  });

  it('prints the scope: the 31-day default, a day window, or one document', () => {
    usePull.mockReturnValue({ data: doPull(), isLoading: false });
    const { rerender, unmount } = render(<AutocountPullReview jobId="job-do" />);
    expect(screen.getByText(/Last 31 days/)).toBeInTheDocument();

    usePull.mockReturnValue({
      data: doPull({ scope: { fromDay: '2026-09-01', toDay: '2026-09-30' } }),
      isLoading: false,
    });
    rerender(<AutocountPullReview jobId="job-do" />);
    expect(screen.getByText(/01\/09\/2026 to 30\/09\/2026/)).toBeInTheDocument();

    usePull.mockReturnValue({ data: doPull({ scope: { docNo: 'DO-2609/0077' } }), isLoading: false });
    rerender(<AutocountPullReview jobId="job-do" />);
    expect(screen.getByText(/DO DO-2609\/0077/)).toBeInTheDocument();
    unmount();
  });

  it('does not print a scope line for a products pull', () => {
    usePull.mockReturnValue({
      data: doPull({
        entity: 'products',
        header: { ...DO_HEADER, entity: 'products' },
        counts: { received: 1, new: 1, changed: 0, unchanged: 0, failed: 0, left_out: 0, price_to_zero: 0 },
      }),
      isLoading: false,
    });
    render(<AutocountPullReview jobId="job-p" />);
    expect(screen.queryByText(/Last 31 days/)).not.toBeInTheDocument();
  });
});
