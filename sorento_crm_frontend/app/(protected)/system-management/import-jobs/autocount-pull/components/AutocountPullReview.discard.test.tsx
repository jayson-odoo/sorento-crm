/**
 * AutocountPullReview - Discard + Pull again, RED tests (AC-DS-9, AC-DS-10, AC-DS-11).
 *
 * Plan: documentation/plans/autocount/PLAN-autocount-pull-discard.md
 * UAC:  documentation/plans/autocount/autocount-pull-discard-acceptance-criteria.md
 *
 * `hooks/useAutocountPull` is mocked (component -> hooks, per layering), same pattern as
 * `AutocountPullReview.test.tsx` - so a `useDiscardPull` that does not exist yet in the real
 * module does not matter here: the mock factory supplies whatever key this file names.
 *
 * RED reason today: `AutocountPullReview.tsx` renders no "Discard" button, no "Pull again"
 * button, no `discarded` phase pill/label, and never calls `useDiscardPull`/`useStartPull` at
 * all - every test below is red because the markup simply is not there yet.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

const usePull = vi.fn();
const useDownloadPullXlsx = vi.fn();
const useConfirmPull = vi.fn();
const useDiscardPull = vi.fn();
const useStartPull = vi.fn();
vi.mock('../hooks/useAutocountPull', () => ({
  usePull: (...a: unknown[]) => usePull(...a),
  useDownloadPullXlsx: (...a: unknown[]) => useDownloadPullXlsx(...a),
  useConfirmPull: (...a: unknown[]) => useConfirmPull(...a),
  useDiscardPull: (...a: unknown[]) => useDiscardPull(...a),
  useStartPull: (...a: unknown[]) => useStartPull(...a),
  useRefreshRowsOnReview: vi.fn(),
}));

vi.mock('./PullChangesTab', () => ({ PullChangesTab: () => <div data-testid="changes-tab-body" /> }));
vi.mock('./PullExcelViewTab', () => ({ PullExcelViewTab: () => <div data-testid="excel-tab-body" /> }));
vi.mock('./PullCompareTab', () => ({ PullCompareTab: () => <div data-testid="compare-tab-body" /> }));

import { AutocountPullReview } from './AutocountPullReview';

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
  useDiscardPull.mockReset();
  useStartPull.mockReset();
  push.mockClear();
  toastError.mockClear();
  toastSuccess.mockClear();
  useDownloadPullXlsx.mockReturnValue({ mutate: vi.fn(), isPending: false });
  useConfirmPull.mockReturnValue({ mutate: vi.fn(), isPending: false });
  useDiscardPull.mockReturnValue({ mutate: vi.fn(), isPending: false });
  useStartPull.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

describe('AC-DS-9: Discard button visibility', () => {
  it.each(['building', 'previewing', 'review'])('shows Discard while phase is %s', (phase) => {
    usePull.mockReturnValue({ data: basePull({ phase }), isLoading: false });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.getByRole('button', { name: 'Discard' })).toBeInTheDocument();
  });

  it.each(['confirmed', 'failed', 'expired', 'discarded'])(
    'does NOT show Discard while phase is %s',
    (phase) => {
      usePull.mockReturnValue({ data: basePull({ phase }), isLoading: false });

      render(<AutocountPullReview jobId="job-1" />);

      expect(screen.queryByRole('button', { name: 'Discard' })).not.toBeInTheDocument();
    },
  );
});

describe('AC-DS-10: clicking Discard', () => {
  it('calls the discard mutation exactly once with the job id, no dialog', () => {
    const mutate = vi.fn();
    useDiscardPull.mockReturnValue({ mutate, isPending: false });
    usePull.mockReturnValue({ data: basePull({ phase: 'review' }), isLoading: false });

    render(<AutocountPullReview jobId="job-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith('job-1');
    // Immediate, no dialog, no countdown (plan: owner ruling 21 Sep) - never a confirm modal.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('the card shows the Discarded badge once the phase is discarded', () => {
    usePull.mockReturnValue({ data: basePull({ phase: 'discarded' }), isLoading: false });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.getByText('Discarded')).toBeInTheDocument();
  });
});

describe('AC-DS-11: Pull again', () => {
  it.each(['failed', 'expired', 'discarded'])('shows on phase %s', (phase) => {
    usePull.mockReturnValue({ data: basePull({ phase }), isLoading: false });

    render(<AutocountPullReview jobId="job-1" />);

    expect(screen.getByRole('button', { name: 'Pull again' })).toBeInTheDocument();
  });

  it.each(['building', 'previewing', 'review', 'confirmed'])(
    'does NOT show on phase %s',
    (phase) => {
      usePull.mockReturnValue({ data: basePull({ phase }), isLoading: false });

      render(<AutocountPullReview jobId="job-1" />);

      expect(screen.queryByRole('button', { name: 'Pull again' })).not.toBeInTheDocument();
    },
  );

  it('clicking it starts a pull for the SAME entity and navigates to the new job', async () => {
    const mutateAsync = vi
      .fn()
      .mockResolvedValue({ job_id: 'new-job-9', entity: 'products', phase: 'building' });
    useStartPull.mockReturnValue({ mutateAsync, isPending: false });
    usePull.mockReturnValue({ data: basePull({ phase: 'failed', entity: 'products' }), isLoading: false });

    render(<AutocountPullReview jobId="job-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Pull again' }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith('products'));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/system-management/import-jobs/new-job-9'));
  });

  it('a start failure toasts the mapped startPullErrorMessage, never a raw error', async () => {
    const mutateAsync = vi.fn().mockRejectedValue({ code: 'TOO_MANY_BUILDS', message: 'raw' });
    useStartPull.mockReturnValue({ mutateAsync, isPending: false });
    usePull.mockReturnValue({ data: basePull({ phase: 'expired', entity: 'products' }), isLoading: false });

    render(<AutocountPullReview jobId="job-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Pull again' }));

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith('A pull was just started. Try again in a minute.'),
    );
  });
});
