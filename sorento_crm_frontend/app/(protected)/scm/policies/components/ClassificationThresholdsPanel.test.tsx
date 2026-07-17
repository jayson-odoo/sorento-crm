/**
 * ClassificationThresholdsPanel — loading / empty / error / data states + save.
 *   AC-CFG-1 (renders the single row, empty state, "next analytics run" copy),
 *   AC-CFG-2 (save upserts with fractional values), AC-STD-4.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const hooks = vi.hoisted(() => ({
  useClassification: vi.fn(),
  useSaveClassification: vi.fn(),
}));
vi.mock('../hooks/usePolicies', () => hooks);

import { ClassificationThresholdsPanel } from './ClassificationThresholdsPanel';

const DATA = { abc_a_pct: 0.8, abc_b_pct: 0.15, xyz_x_max: 0.5, xyz_y_max: 1, exists: true };
const mutateAsync = vi.fn();

beforeEach(() => {
  hooks.useClassification.mockReset();
  hooks.useSaveClassification.mockReset();
  mutateAsync.mockReset().mockResolvedValue(DATA);
  hooks.useSaveClassification.mockReturnValue({ mutateAsync, isPending: false });
});

describe('ClassificationThresholdsPanel', () => {
  it('renders a loading skeleton (no inputs) while loading', () => {
    hooks.useClassification.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    render(<ClassificationThresholdsPanel />);
    expect(screen.queryByDisplayValue('80')).not.toBeInTheDocument();
    // "next analytics run" copy always present (AC-CFG-1).
    expect(screen.getByText(/next analytics run/i)).toBeInTheDocument();
  });

  it('renders the error state', () => {
    hooks.useClassification.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(<ClassificationThresholdsPanel />);
    expect(screen.getByText(/Failed to load classification thresholds/i)).toBeInTheDocument();
  });

  it('renders the empty state (seeded defaults) when no row exists yet (AC-CFG-1)', () => {
    hooks.useClassification.mockReturnValue({
      data: { ...DATA, exists: false },
      isLoading: false,
      isError: false,
    });
    render(<ClassificationThresholdsPanel />);
    expect(screen.getByText(/No thresholds saved yet/i)).toBeInTheDocument();
  });

  it('renders the stored values as percentages / CVs (AC-CFG-1)', () => {
    hooks.useClassification.mockReturnValue({ data: DATA, isLoading: false, isError: false });
    render(<ClassificationThresholdsPanel />);
    expect(screen.getByDisplayValue('80')).toBeInTheDocument(); // abc_a_pct 0.8 → 80%
    expect(screen.getByDisplayValue('15')).toBeInTheDocument(); // abc_b_pct 0.15 → 15%
    expect(screen.getByDisplayValue('0.5')).toBeInTheDocument(); // xyz_x_max
  });

  it('save upserts the row with fractional values (AC-CFG-2)', async () => {
    hooks.useClassification.mockReturnValue({ data: DATA, isLoading: false, isError: false });
    render(<ClassificationThresholdsPanel />);
    fireEvent.click(screen.getByRole('button', { name: /Save thresholds/i }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync).toHaveBeenCalledWith({
      abc_a_pct: 0.8,
      abc_b_pct: 0.15,
      xyz_x_max: 0.5,
      xyz_y_max: 1,
    });
  });

  it('blocks a save where A + B ≥ 100% (AC-CFG-2 client mirror)', () => {
    hooks.useClassification.mockReturnValue({
      data: { abc_a_pct: 0.6, abc_b_pct: 0.5, xyz_x_max: 0.5, xyz_y_max: 1, exists: true },
      isLoading: false,
      isError: false,
    });
    render(<ClassificationThresholdsPanel />);
    fireEvent.click(screen.getByRole('button', { name: /Save thresholds/i }));
    expect(screen.getByText(/A \+ B must be below 100%/i)).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});
