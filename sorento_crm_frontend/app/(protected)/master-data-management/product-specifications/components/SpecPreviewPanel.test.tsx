/**
 * "See what would change" (AC-S1.8, plan D5, D10): a pending spinner with no
 * countdown, the four counts once done, the sample table, and Save staying
 * enabled throughout - preview is advice, not a gate, so this component never
 * disables anything outside itself.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

const mockUseSpecPreview = vi.fn();
vi.mock('../hooks/useSpecPreview', () => ({
  useSpecPreview: (...args: unknown[]) => mockUseSpecPreview(...args),
}));

import SpecPreviewPanel from './SpecPreviewPanel';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('idle', () => {
  it('shows the button and no counts', () => {
    mockUseSpecPreview.mockReturnValue({
      status: 'idle',
      result: null,
      error: null,
      run: vi.fn(),
    });
    render(<SpecPreviewPanel specKey="dim_length" rules={[]} />);

    expect(
      screen.getByRole('button', { name: 'See what would change' }),
    ).toBeEnabled();
    expect(screen.queryByText('changed')).not.toBeInTheDocument();
  });
});

describe('pending', () => {
  it('shows a spinner with no countdown, and disables only its own button', () => {
    mockUseSpecPreview.mockReturnValue({
      status: 'pending',
      result: null,
      error: null,
      run: vi.fn(),
    });
    render(<SpecPreviewPanel specKey="dim_length" rules={[]} />);

    expect(screen.getByText('Checking...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Checking/ })).toBeDisabled();
    // No countdown anywhere on the pending state - the job's duration is not knowable.
    expect(screen.queryByText(/\d+s/)).not.toBeInTheDocument();
  });
});

describe('done', () => {
  it('shows the four counts in the owner\'s words and the sample with code and name', () => {
    mockUseSpecPreview.mockReturnValue({
      status: 'done',
      result: {
        status: 'done',
        changed: 3,
        now_set: 1,
        no_longer_set: 2,
        unchanged: 40,
        drift: 0,
        sample: [
          { code: 'ZZT-WC-001', name: 'Wall basin', before: 300, after: 320 },
          { code: 'ZZT-BA-002', name: 'Bath tub', before: null, after: 800 },
        ],
      },
      error: null,
      run: vi.fn(),
    });
    render(<SpecPreviewPanel specKey="dim_length" rules={[]} />);

    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('changed')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('now set')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('no longer set')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
    expect(screen.getByText('unchanged')).toBeInTheDocument();
    expect(screen.queryByText('added')).not.toBeInTheDocument();
    expect(screen.queryByText('removed')).not.toBeInTheDocument();

    expect(screen.getByText('ZZT-WC-001')).toBeInTheDocument();
    expect(screen.getByText('Wall basin')).toBeInTheDocument();
    expect(screen.getByText('ZZT-BA-002')).toBeInTheDocument();
    expect(screen.getByText('Bath tub')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument();
  });

  it('says how many stored values differ from today\'s rules, when any do', () => {
    mockUseSpecPreview.mockReturnValue({
      status: 'done',
      result: { status: 'done', changed: 0, now_set: 1, no_longer_set: 0, unchanged: 9, drift: 66, sample: [] },
      error: null,
      run: vi.fn(),
    });
    render(<SpecPreviewPanel specKey="finish" rules={[]} />);

    expect(
      screen.getByText(
        "66 products have a stored value that differs from today's rules; saving this rule refreshes them too.",
      ),
    ).toBeInTheDocument();
  });

  it('says one product in the singular', () => {
    mockUseSpecPreview.mockReturnValue({
      status: 'done',
      result: { status: 'done', changed: 0, now_set: 0, no_longer_set: 0, unchanged: 9, drift: 1, sample: [] },
      error: null,
      run: vi.fn(),
    });
    render(<SpecPreviewPanel specKey="finish" rules={[]} />);

    expect(
      screen.getByText("1 product has a stored value that differs from today's rules; saving this rule refreshes it too."),
    ).toBeInTheDocument();
  });

  it('says nothing about stored values when none differ', () => {
    mockUseSpecPreview.mockReturnValue({
      status: 'done',
      result: { status: 'done', changed: 0, now_set: 0, no_longer_set: 0, unchanged: 9, drift: 0, sample: [] },
      error: null,
      run: vi.fn(),
    });
    render(<SpecPreviewPanel specKey="finish" rules={[]} />);

    expect(screen.queryByText(/stored value/)).not.toBeInTheDocument();
  });

  it('keeps the button enabled so a second run can be started - preview is advice, not a gate', () => {
    mockUseSpecPreview.mockReturnValue({
      status: 'done',
      result: {
        status: 'done',
        changed: 0,
        now_set: 0,
        no_longer_set: 0,
        unchanged: 5,
        sample: [],
      },
      error: null,
      run: vi.fn(),
    });
    render(<SpecPreviewPanel specKey="dim_length" rules={[]} />);

    expect(
      screen.getByRole('button', { name: 'See what would change' }),
    ).toBeEnabled();
  });
});

describe('error', () => {
  it('shows the failure message', () => {
    mockUseSpecPreview.mockReturnValue({
      status: 'error',
      result: null,
      error: 'Could not preview these rules',
      run: vi.fn(),
    });
    render(<SpecPreviewPanel specKey="dim_length" rules={[]} />);

    expect(
      screen.getByText('Could not preview these rules'),
    ).toBeInTheDocument();
  });
});
