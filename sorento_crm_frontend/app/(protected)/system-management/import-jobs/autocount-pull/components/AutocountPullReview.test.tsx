/**
 * AutocountPullReview - SR2 red tests (AC-RV-1, AC-RV-6, AC-CM-6/P11).
 *
 * Pins the real pull contract from `PLAN-autocount-pull-review.md` ("Routes" + the pull job
 * metadata shape): the review card reads snapshot facts from a NESTED `header` object
 * (`header.companyCode`, `header.extractedAt`, `header.expiresAt`, `header.snapshotId`), not the
 * flat `company_code` / `extracted_at` / `expires_at` / (dropped) `error_message` fields Phase 1
 * read directly off the pull. `hooks/useAutocountPull` is mocked (component -> hooks, per
 * layering) so this exercises `AutocountPullReview` in isolation; the three line tabs are
 * stubbed to their own components' tests.
 *
 * RED reason: `AutocountPullReview.tsx` still reads `pull.company_code` / `pull.extracted_at` /
 * `pull.expires_at`, which are `undefined` on a pull shaped like the real route response, so the
 * snapshot-time text (R3) never renders. R1/R2/R5 mostly already pass under Phase 1 code (listed
 * as guards, noted per test).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

// PLAN-autocount-pull-discard.md: the component now calls `useRouter()` (Pull again's
// navigation, AC-DS-11) - harness-only, no assertion in this file depends on it.
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

const usePull = vi.fn();
const useDownloadPullXlsx = vi.fn();
const useConfirmPull = vi.fn();
vi.mock('../hooks/useAutocountPull', () => ({
  usePull: (...a: unknown[]) => usePull(...a),
  useDownloadPullXlsx: (...a: unknown[]) => useDownloadPullXlsx(...a),
  useConfirmPull: (...a: unknown[]) => useConfirmPull(...a),
  // Discard/Pull again (PLAN-autocount-pull-discard.md, AC-DS-9..11) - harness-only stubs,
  // not under test here (see AutocountPullReview.discard.test.tsx for their coverage).
  useDiscardPull: () => ({ mutate: vi.fn(), isPending: false }),
  useStartPull: () => ({ mutateAsync: vi.fn(), isPending: false }),
  // No-op here: this file mocks the whole hooks module and never wraps its renders in a
  // `QueryClientProvider`. The rows-refresh behaviour itself (D1, small-fix track) has its
  // own coverage, unmocked, in `AutocountPullReview.rowsRefresh.test.tsx`.
  useRefreshRowsOnReview: vi.fn(),
}));

vi.mock('./PullChangesTab', () => ({ PullChangesTab: () => <div data-testid="changes-tab-body" /> }));
vi.mock('./PullExcelViewTab', () => ({ PullExcelViewTab: () => <div data-testid="excel-tab-body" /> }));
vi.mock('./PullCompareTab', () => ({ PullCompareTab: () => <div data-testid="compare-tab-body" /> }));

import { AutocountPullReview } from './AutocountPullReview';

const PRODUCTS_HEADER = {
  snapshotId: 'a1b2c3d4-e5f6-4789-a012-3456789abcde',
  entity: 'products',
  companyCode: 'SRT',
  extractedAt: '2026-09-20T02:00:00Z', // 10:00 MYT
  expiresAt: '2026-09-21T02:00:00Z', // 10:00 MYT the next day
  recordCount: 10,
  complete: true,
  contentHash: 'deadbeef',
  zeroListPriceCount: 0,
  negativeListPriceCount: 0,
};

const PRODUCT_COUNTS = {
  received: 10,
  new: 6,
  changed: 2,
  unchanged: 1,
  failed: 0,
  left_out: 1,
  price_to_zero: 0,
};

function basePull(overrides: Record<string, unknown> = {}) {
  return {
    job_id: 'f47ac10b-58cc-4372-a567-0e02b2c3d479',
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

beforeEach(() => {
  usePull.mockReset();
  useDownloadPullXlsx.mockReset();
  useConfirmPull.mockReset();
  useDownloadPullXlsx.mockReturnValue({ mutate: vi.fn(), isPending: false });
  useConfirmPull.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

describe('AutocountPullReview - status pill (AC-RV-1, R1 - largely a guard)', () => {
  const CASES: Array<[string, string]> = [
    ['building', 'Building'],
    ['previewing', 'Preparing'],
    ['review', 'Awaiting confirm'],
    ['confirmed', 'Confirmed'],
    ['failed', 'Failed'],
    ['expired', 'Expired'],
  ];

  it.each(CASES)('R1: phase %s shows the %s pill', (phase, label) => {
    usePull.mockReturnValue({
      data: basePull({
        phase,
        header: phase === 'review' || phase === 'confirmed' ? PRODUCTS_HEADER : null,
        counts: phase === 'review' || phase === 'confirmed' ? PRODUCT_COUNTS : null,
      }),
      isLoading: false,
    });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

describe('AutocountPullReview - building progress (AC-BD-6, R2 - largely a guard)', () => {
  it('R2a: shows a progressbar reflecting the right value when progress is present', () => {
    usePull.mockReturnValue({
      data: basePull({ phase: 'building', progress: { pagesDone: 2, pagesTotal: 4 } }),
      isLoading: false,
    });

    const { container } = render(<AutocountPullReview jobId="job-1" />);

    // The shared `Progress` primitive (`components/ui/progress.tsx`) never forwards `value`
    // to Radix, so it never carries `aria-valuenow` - the indicator's own transform is the
    // only place the real value shows up under jsdom.
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
    const indicator = container.querySelector('[data-slot="progress-indicator"]') as HTMLElement;
    expect(indicator.style.transform).toContain('-50%');
    expect(screen.getByText('Page 2 of 4')).toBeInTheDocument();
  });

  it('R2b: shows a spinner and no progressbar when progress is absent', () => {
    usePull.mockReturnValue({
      data: basePull({ phase: 'building', progress: null }),
      isLoading: false,
    });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });
});

describe('AutocountPullReview - review phase (AC-RV-1, R3)', () => {
  function reviewPull(overrides: Record<string, unknown> = {}) {
    return basePull({ phase: 'review', header: PRODUCTS_HEADER, counts: PRODUCT_COUNTS, ...overrides });
  }

  it('R3a: shows the snapshot time and valid-until time FROM THE HEADER', () => {
    usePull.mockReturnValue({ data: reviewPull(), isLoading: false });

    render(<AutocountPullReview jobId="job-1" />);

    // header.extractedAt / header.expiresAt formatted dd/MM/yyyy HH:mm, Asia/Kuala_Lumpur.
    expect(screen.getByText(/20\/09\/2026 10:00/)).toBeInTheDocument();
    expect(screen.getByText(/21\/09\/2026 10:00/)).toBeInTheDocument();
  });

  it('R3b: renders the counters from `counts`', () => {
    usePull.mockReturnValue({ data: reviewPull(), isLoading: false });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.getByText('Received')).toBeInTheDocument();
    expect(screen.getByText('New')).toBeInTheDocument();
    expect(screen.getByText('Changed')).toBeInTheDocument();
  });

  it('R3c: three line tabs in order Changes, Excel view, Compare with my Excel, plus Download and Confirm', () => {
    usePull.mockReturnValue({ data: reviewPull(), isLoading: false });

    render(<AutocountPullReview jobId="job-1" />);

    const tabs = screen.getAllByRole('tab').map((t) => t.textContent);
    expect(tabs).toEqual(['Changes', 'Excel view', 'Compare with my Excel']);
    expect(screen.getByRole('button', { name: /Download/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm/ })).toBeInTheDocument();
  });
});

describe('AutocountPullReview - no UUID anywhere (AC-RV-6, R4)', () => {
  const UUID_RE = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i;

  it('R4: job_id and header.snapshotId are both UUIDs, neither appears in the rendered text', () => {
    usePull.mockReturnValue({
      data: basePull({
        job_id: 'f47ac10b-58cc-4372-a567-0e02b2c3d479',
        phase: 'review',
        header: PRODUCTS_HEADER,
        counts: PRODUCT_COUNTS,
      }),
      isLoading: false,
    });

    const { container } = render(<AutocountPullReview jobId="f47ac10b-58cc-4372-a567-0e02b2c3d479" />);

    expect(container.textContent ?? '').not.toMatch(UUID_RE);
  });
});

describe('AutocountPullReview - Confirm enablement (AC-CM-6/P11, R5)', () => {
  it('R5a: enabled with compare null', () => {
    usePull.mockReturnValue({
      data: basePull({ phase: 'review', header: PRODUCTS_HEADER, counts: PRODUCT_COUNTS, compare: null }),
      isLoading: false,
    });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.getByRole('button', { name: /Confirm/ })).not.toBeDisabled();
  });

  it('R5b: enabled with a compare summary that has differences (advisory only, never blocks)', () => {
    usePull.mockReturnValue({
      data: basePull({
        phase: 'review',
        header: PRODUCTS_HEADER,
        counts: PRODUCT_COUNTS,
        compare: {
          filename: 'my.xlsx',
          compared_at: '2026-09-20T03:00:00Z',
          total: 10,
          matched: 7,
          different: 3,
          only_in_excel: 0,
          only_in_pull: 0,
        },
      }),
      isLoading: false,
    });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.getByRole('button', { name: /Confirm/ })).not.toBeDisabled();
  });

  it('R5c: disabled with confirm_blocked_reason set', () => {
    usePull.mockReturnValue({
      data: basePull({
        phase: 'review',
        header: PRODUCTS_HEADER,
        counts: PRODUCT_COUNTS,
        confirm_blocked_reason: 'AutoCount sent rows with a real quantity Sorento could not place as stock. Pull again.',
      }),
      isLoading: false,
    });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.getByRole('button', { name: /Confirm/ })).toBeDisabled();
  });
});

describe('AutocountPullReview - warnings (captain ruling, SR4 fix round)', () => {
  it('a known warning code renders as one line near the header', () => {
    usePull.mockReturnValue({
      data: basePull({
        phase: 'confirmed',
        header: PRODUCTS_HEADER,
        counts: PRODUCT_COUNTS,
        warnings: ['stock_list_not_archived'],
      }),
      isLoading: false,
    });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.getByText('Stock List file was not replaced')).toBeInTheDocument();
  });
});

describe('AutocountPullReview - confirmed phase actions (captain ruling, Phase 3 fix round, V-4)', () => {
  it('Download is available once confirmed too; Confirm is not', () => {
    usePull.mockReturnValue({
      data: basePull({
        phase: 'confirmed',
        header: PRODUCTS_HEADER,
        counts: PRODUCT_COUNTS,
        apply_job_id: 'b2c3d4e5-f6a7-4890-b123-456789abcdef',
      }),
      isLoading: false,
    });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.getByRole('button', { name: /Download/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Confirm$/ })).not.toBeInTheDocument();
  });
});
