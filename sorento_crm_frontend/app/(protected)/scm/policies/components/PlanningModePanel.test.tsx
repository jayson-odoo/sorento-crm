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
  useCoverScope: vi.fn(),
  useSaveCoverScope: vi.fn(),
}));
vi.mock('../hooks/usePolicies', () => hooks);

import { PlanningModePanel } from './PlanningModePanel';

const mutateAsync = vi.fn();
const mutateCover = vi.fn();

beforeEach(() => {
  hooks.usePlanningMode.mockReset();
  hooks.useSavePlanningMode.mockReset();
  hooks.useCoverScope.mockReset();
  hooks.useSaveCoverScope.mockReset();
  mutateAsync.mockReset().mockResolvedValue({ mode: 'manual' });
  mutateCover.mockReset();
  hooks.useSavePlanningMode.mockReturnValue({ mutateAsync, isPending: false });
  hooks.useSaveCoverScope.mockReturnValue({ mutate: mutateCover, isPending: false });
  hooks.useCoverScope.mockReturnValue({
    data: { cover_scope: 'own_pool' },
    isLoading: false,
    isError: false,
  });
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

  it('cancelling the dialog leaves the mode unchanged', async () => {
    hooks.usePlanningMode.mockReturnValue({ data: { mode: 'auto' }, isLoading: false, isError: false });
    render(<PlanningModePanel />);
    fireEvent.click(screen.getByRole('radio', { name: /Manual/i }));
    fireEvent.click(screen.getByRole('button', { name: /Cancel/i }));
    // The AlertDialog spring's exit (M2-05) unmounts it a tick after the click.
    await waitFor(() => expect(screen.queryByText(/Switch to manual planning\?/i)).not.toBeInTheDocument());
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

  it('the radio reverts to the server value once the dialog is cancelled', async () => {
    hooks.usePlanningMode.mockReturnValue({ data: { mode: 'auto' }, isLoading: false, isError: false });
    render(<PlanningModePanel />);
    fireEvent.click(screen.getByRole('radio', { name: /Manual/i }));
    fireEvent.click(screen.getByRole('button', { name: /Cancel/i }));
    // The AlertDialog spring's exit (M2-05) inerts the radios for one extra
    // tick beyond the click.
    await waitFor(() => expect(screen.queryByText(/Switch to manual planning\?/i)).not.toBeInTheDocument());

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

/**
 * Cover from - where a plan row may take stock from before it buys (AC-3.2).
 *
 * > "why am I allowed to use stock from other locations? It is either I use stock from BRW,
 * >  or buy."
 */
describe('PlanningModePanel - Cover from', () => {
  beforeEach(() => {
    hooks.usePlanningMode.mockReturnValue({
      data: { mode: 'auto' }, isLoading: false, isError: false,
    });
  });

  it('renders the saved scope', () => {
    render(<PlanningModePanel />);
    expect(screen.getByText('Cover from')).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toHaveTextContent('Own site only');
  });

  it('renders the other scope when that is what is saved', () => {
    hooks.useCoverScope.mockReturnValue({
      data: { cover_scope: 'all_locations' }, isLoading: false, isError: false,
    });
    render(<PlanningModePanel />);
    expect(screen.getByRole('combobox')).toHaveTextContent('Any location');
  });

  it('shows a skeleton while the setting loads, never a guessed value', () => {
    hooks.useCoverScope.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    render(<PlanningModePanel />);
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('renders the error state', () => {
    hooks.useCoverScope.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(<PlanningModePanel />);
    expect(screen.getByText(/Failed to load the cover setting/i)).toBeInTheDocument();
  });

  it('picking the other option saves it', async () => {
    render(<PlanningModePanel />);
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByText('Any location'));
    await waitFor(() =>
      expect(mutateCover).toHaveBeenCalledWith({ cover_scope: 'all_locations' }),
    );
  });
});
