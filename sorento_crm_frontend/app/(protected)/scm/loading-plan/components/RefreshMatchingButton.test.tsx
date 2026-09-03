/**
 * R18 - Refresh matching: the ladder runs again over what is still unbound.
 *
 * What is pinned here is that the button asks for THIS PLAN's rows (S6, AC-C7), and that it
 * goes quiet while the answer is in flight - a second click would re-run the same pass and
 * the counts the toast reports would then describe the first one.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const state = {
  rematch: vi.fn(),
  pending: false,
};

vi.mock('../../hooks/useSupplierCodeAliases', () => ({
  useRematchSupplierCodes: () => ({ mutate: state.rematch, isPending: state.pending }),
}));

import { RefreshMatchingButton } from './RefreshMatchingButton';

beforeEach(() => {
  state.rematch.mockClear();
  state.pending = false;
});

describe('RefreshMatchingButton', () => {
  it('re-runs the ladder for the plan on screen', () => {
    render(<RefreshMatchingButton planId="plan-1" />);

    fireEvent.click(screen.getByTestId('refresh-matching'));

    expect(state.rematch).toHaveBeenCalledWith({ plan_id: 'plan-1' });
  });

  it('is disabled while the pass is in flight', () => {
    state.pending = true;
    render(<RefreshMatchingButton planId="plan-1" />);

    expect(screen.getByTestId('refresh-matching')).toBeDisabled();
  });

  it('is disabled with no plan, since there is nothing to re-match', () => {
    render(<RefreshMatchingButton planId="" />);

    expect(screen.getByTestId('refresh-matching')).toBeDisabled();
    fireEvent.click(screen.getByTestId('refresh-matching'));
    expect(state.rematch).not.toHaveBeenCalled();
  });
});
