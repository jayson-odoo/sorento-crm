import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

/**
 * The shared reassign picker (UAC AC-N7). A reply from a user with no Respond
 * mapping cannot carry a real sender identity, so the picker says who is linked
 * and can filter to them. The linkage rides on the picker's OWN rows
 * (`respond_linked` on visible-users), so it is available to every holder of
 * the picker - it used to come from a second, `user_management.users.view`-gated
 * call that degraded to no-badge-no-filter for exactly the SLA agents who need
 * it.
 */
const visibleUsers = vi.fn();
vi.mock('../hooks/useTeamPendingSLA', () => ({
  useVisibleUsers: () => visibleUsers(),
}));

import ReassignDialog from './ReassignDialog';

const USERS = [
  { id: 'u-1', name: 'Aisyah Rahman', email: 'aisyah@sorento.test', respond_linked: true },
  { id: 'u-2', name: 'Ben Lim', email: 'ben@sorento.test', respond_linked: false },
];

beforeEach(() => {
  visibleUsers.mockReturnValue({ data: USERS, isLoading: false, error: null });
});

function renderDialog(props: Partial<React.ComponentProps<typeof ReassignDialog>> = {}) {
  const onConfirm = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <ReassignDialog open onOpenChange={onOpenChange} onConfirm={onConfirm} {...props} />,
  );
  return { onConfirm, onOpenChange };
}

/** The options only exist once the popover is open. */
function openPicker() {
  fireEvent.click(screen.getByRole('combobox'));
}

describe('ReassignDialog (AC-N7)', () => {
  it('badges the Respond-linked colleagues in the list', async () => {
    renderDialog();
    openPicker();

    await waitFor(() => expect(screen.getByText('Aisyah Rahman')).toBeDefined());
    expect(screen.getByTestId('respond-linked-badge-u-1')).toBeDefined();
    expect(screen.queryByTestId('respond-linked-badge-u-2')).toBeNull();
  });

  it('filters to Respond-linked only', async () => {
    renderDialog();
    fireEvent.click(screen.getByTestId('reassign-respond-linked-filter'));
    openPicker();

    await waitFor(() => expect(screen.getByText('Aisyah Rahman')).toBeDefined());
    expect(screen.queryByText('Ben Lim')).toBeNull();
  });

  it('badge and filter come from the picker rows, so they are always offered', async () => {
    renderDialog();

    expect(screen.getByTestId('reassign-respond-linked-filter')).toBeDefined();
    openPicker();
    await waitFor(() => expect(screen.getByText('Aisyah Rahman')).toBeDefined());
    expect(screen.getByTestId('respond-linked-badge-u-1')).toBeDefined();
  });

  it('nobody linked: the filter empties the list rather than lying about it', async () => {
    visibleUsers.mockReturnValue({
      data: USERS.map((u) => ({ ...u, respond_linked: false })),
      isLoading: false,
      error: null,
    });
    renderDialog();
    fireEvent.click(screen.getByTestId('reassign-respond-linked-filter'));
    openPicker();

    await waitFor(() =>
      expect(screen.getByText('No Respond-linked colleagues.')).toBeDefined(),
    );
  });

  it('confirms with the chosen colleague', async () => {
    const { onConfirm } = renderDialog();
    openPicker();

    fireEvent.click(await screen.findByText('Ben Lim'));
    fireEvent.click(screen.getByRole('button', { name: 'Reassign' }));

    expect(onConfirm).toHaveBeenCalledWith('u-2');
  });

  it('drops a selection the filter has just hidden', async () => {
    const { onConfirm } = renderDialog();
    openPicker();
    fireEvent.click(await screen.findByText('Ben Lim'));

    fireEvent.click(screen.getByTestId('reassign-respond-linked-filter'));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Reassign' })).toBeDisabled(),
    );
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('shows the loading and empty states', async () => {
    visibleUsers.mockReturnValue({ data: [], isLoading: true, error: null });
    renderDialog();
    expect(screen.getByText('Loading users…')).toBeDefined();
  });

  it('surfaces a failed user list', () => {
    visibleUsers.mockReturnValue({
      data: [],
      isLoading: false,
      error: new Error('Failed to fetch visible users'),
    });
    renderDialog();
    expect(screen.getByText('Failed to fetch visible users')).toBeDefined();
  });
});
