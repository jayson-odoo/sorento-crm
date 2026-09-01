/**
 * "Preview on catalogue" (AC-B.4): a pending spinner with no countdown, the four
 * counts once done, the sample table, and Save staying enabled throughout - preview
 * is advice, not a gate, so this component never disables anything outside itself.
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
      screen.getByRole('button', { name: 'Preview on catalogue' }),
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

    expect(screen.getByText('Running...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Running/ })).toBeDisabled();
    // No countdown anywhere on the pending state - the job's duration is not knowable.
    expect(screen.queryByText(/\d+s/)).not.toBeInTheDocument();
  });
});

describe('done', () => {
  it('shows the four counts and the sample table', () => {
    mockUseSpecPreview.mockReturnValue({
      status: 'done',
      result: {
        status: 'done',
        changed: 3,
        added: 1,
        removed: 2,
        unchanged: 40,
        sample: [
          { code: 'ZZT-WC-001', before: 300, after: 320 },
          { code: 'ZZT-BA-002', before: null, after: 800 },
        ],
      },
      error: null,
      run: vi.fn(),
    });
    render(<SpecPreviewPanel specKey="dim_length" rules={[]} />);

    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('changed')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('added')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('removed')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
    expect(screen.getByText('unchanged')).toBeInTheDocument();

    expect(screen.getByText('ZZT-WC-001')).toBeInTheDocument();
    expect(screen.getByText('ZZT-BA-002')).toBeInTheDocument();
  });

  it('keeps the button enabled so a second run can be started - preview is advice, not a gate', () => {
    mockUseSpecPreview.mockReturnValue({
      status: 'done',
      result: {
        status: 'done',
        changed: 0,
        added: 0,
        removed: 0,
        unchanged: 5,
        sample: [],
      },
      error: null,
      run: vi.fn(),
    });
    render(<SpecPreviewPanel specKey="dim_length" rules={[]} />);

    expect(
      screen.getByRole('button', { name: 'Preview on catalogue' }),
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
