/**
 * PlanningModePanel - the ONE universal auto/manual switch (S1, UAC A).
 *   Renders current mode, confirms before flipping ("applies from the next
 *   run"), fires the mutation with the picked mode, and leaves the row alone
 *   when a flip is cancelled.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const hooks = vi.hoisted(() => ({
  usePlanningMode: vi.fn(),
  useSavePlanningMode: vi.fn(),
}));
vi.mock('../hooks/usePolicies', () => hooks);

import { PlanningModePanel } from './PlanningModePanel';

const mutateAsync = vi.fn();

beforeEach(() => {
  hooks.usePlanningMode.mockReset();
  hooks.useSavePlanningMode.mockReset();
  mutateAsync.mockReset().mockResolvedValue({ mode: 'manual' });
  hooks.useSavePlanningMode.mockReturnValue({ mutateAsync, isPending: false });
});

describe('PlanningModePanel', () => {
  it('renders a loading skeleton while loading', () => {
    hooks.usePlanningMode.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    render(<PlanningModePanel />);
    expect(screen.queryByRole('radio', { name: /Auto/i })).not.toBeInTheDocument();
  });

  it('renders the error state', () => {
    hooks.usePlanningMode.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(<PlanningModePanel />);
    expect(screen.getByText(/Failed to load planning mode/i)).toBeInTheDocument();
  });

  it('renders the current mode selected (auto)', () => {
    hooks.usePlanningMode.mockReturnValue({ data: { mode: 'auto' }, isLoading: false, isError: false });
    render(<PlanningModePanel />);
    expect(screen.getByRole('radio', { name: /Auto/i })).toHaveAttribute('data-state', 'checked');
    expect(screen.getByRole('radio', { name: /Manual/i })).toHaveAttribute('data-state', 'unchecked');
  });

  it('renders the current mode selected (manual)', () => {
    hooks.usePlanningMode.mockReturnValue({ data: { mode: 'manual' }, isLoading: false, isError: false });
    render(<PlanningModePanel />);
    expect(screen.getByRole('radio', { name: /Manual/i })).toHaveAttribute('data-state', 'checked');
    expect(screen.getByRole('radio', { name: /Auto/i })).toHaveAttribute('data-state', 'unchecked');
  });

  it('picking the other option opens a confirm dialog stating the next-run effect', () => {
    hooks.usePlanningMode.mockReturnValue({ data: { mode: 'auto' }, isLoading: false, isError: false });
    render(<PlanningModePanel />);
    fireEvent.click(screen.getByRole('radio', { name: /Manual/i }));
    expect(screen.getByText(/Switch to manual planning\?/i)).toBeInTheDocument();
    expect(screen.getByText(/starting with the next run/i)).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('confirming the dialog fires the mutation with the picked mode', async () => {
    hooks.usePlanningMode.mockReturnValue({ data: { mode: 'auto' }, isLoading: false, isError: false });
    render(<PlanningModePanel />);
    fireEvent.click(screen.getByRole('radio', { name: /Manual/i }));
    fireEvent.click(screen.getByRole('button', { name: /Switch to manual/i }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ mode: 'manual' }));
  });

  it('cancelling the dialog leaves the mode unchanged', () => {
    hooks.usePlanningMode.mockReturnValue({ data: { mode: 'auto' }, isLoading: false, isError: false });
    render(<PlanningModePanel />);
    fireEvent.click(screen.getByRole('radio', { name: /Manual/i }));
    fireEvent.click(screen.getByRole('button', { name: /Cancel/i }));
    expect(screen.queryByText(/Switch to manual planning\?/i)).not.toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('the radio reflects the clicked option while the confirm dialog is still open ' +
    '(Fix 7, 2026-08-12: it used to stay on the OLD server value until confirmed)', () => {
    hooks.usePlanningMode.mockReturnValue({ data: { mode: 'auto' }, isLoading: false, isError: false });
    render(<PlanningModePanel />);
    fireEvent.click(screen.getByRole('radio', { name: /Manual/i }));

    expect(screen.getByText(/Switch to manual planning\?/i)).toBeInTheDocument();
    // The open alert dialog marks the rest of the page aria-hidden, so the radios must be
    // queried with `hidden: true` here - that inert-marking is exactly what the fix is
    // guarding against being confused with the radio's OWN checked state.
    expect(screen.getByRole('radio', { name: /Manual/i, hidden: true })).toHaveAttribute(
      'data-state', 'checked',
    );
    expect(screen.getByRole('radio', { name: /Auto/i, hidden: true })).toHaveAttribute(
      'data-state', 'unchecked',
    );
  });

  it('the radio reverts to the server value once the dialog is cancelled', () => {
    hooks.usePlanningMode.mockReturnValue({ data: { mode: 'auto' }, isLoading: false, isError: false });
    render(<PlanningModePanel />);
    fireEvent.click(screen.getByRole('radio', { name: /Manual/i }));
    fireEvent.click(screen.getByRole('button', { name: /Cancel/i }));

    expect(screen.getByRole('radio', { name: /Auto/i })).toHaveAttribute('data-state', 'checked');
    expect(screen.getByRole('radio', { name: /Manual/i })).toHaveAttribute('data-state', 'unchecked');
  });

  it('picking the already-active option does not open a confirm dialog', () => {
    hooks.usePlanningMode.mockReturnValue({ data: { mode: 'auto' }, isLoading: false, isError: false });
    render(<PlanningModePanel />);
    fireEvent.click(screen.getByRole('radio', { name: /Auto/i }));
    expect(screen.queryByText(/Switch to/i)).not.toBeInTheDocument();
  });
});
