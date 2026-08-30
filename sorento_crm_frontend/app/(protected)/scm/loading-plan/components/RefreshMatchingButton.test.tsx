/**
 * R18 - Refresh matching: the ladder runs again over what is still unbound.
 *
 * What is pinned here is that the button asks for the supplier on screen, and that it goes
 * quiet while the answer is in flight - a second click would re-run the same pass and the
 * counts the toast reports would then describe the first one.
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
  it('re-runs the ladder for the supplier on screen', () => {
    render(<RefreshMatchingButton supplierId="sup-1" />);

    fireEvent.click(screen.getByTestId('refresh-matching'));

    expect(state.rematch).toHaveBeenCalledWith({ supplier_id: 'sup-1' });
  });

  it('is disabled while the pass is in flight', () => {
    state.pending = true;
    render(<RefreshMatchingButton supplierId="sup-1" />);

    expect(screen.getByTestId('refresh-matching')).toBeDisabled();
  });

  it('is disabled with no supplier, since there is nothing to re-match', () => {
    render(<RefreshMatchingButton supplierId="" />);

    expect(screen.getByTestId('refresh-matching')).toBeDisabled();
    fireEvent.click(screen.getByTestId('refresh-matching'));
    expect(state.rematch).not.toHaveBeenCalled();
  });
});
