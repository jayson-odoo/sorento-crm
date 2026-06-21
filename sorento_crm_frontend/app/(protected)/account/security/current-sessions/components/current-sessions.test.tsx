import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('@/hooks/useSessions', () => ({
  useSessionsQuery: vi.fn(),
  useRevokeSessionMutation: vi.fn(),
  useRevokeOtherSessionsMutation: vi.fn(),
}));

import {
  useSessionsQuery,
  useRevokeSessionMutation,
  useRevokeOtherSessionsMutation,
} from '@/hooks/useSessions';
import { CurrentSessions } from './current-sessions';

const revokeMutate = vi.fn();
const revokeOthersMutate = vi.fn();

function mockMutations() {
  (useRevokeSessionMutation as any).mockReturnValue({ mutate: revokeMutate, isPending: false });
  (useRevokeOtherSessionsMutation as any).mockReturnValue({
    mutate: revokeOthersMutate,
    isPending: false,
  });
}

describe('CurrentSessions (your devices)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockMutations();
  });

  it('renders the loading state', () => {
    (useSessionsQuery as any).mockReturnValue({ isLoading: true });
    render(<CurrentSessions />);
    expect(screen.getByText(/loading sessions/i)).toBeInTheDocument();
  });

  it('renders the empty state', () => {
    (useSessionsQuery as any).mockReturnValue({ isLoading: false, isError: false, data: [] });
    render(<CurrentSessions />);
    expect(screen.getByText(/no active sessions found/i)).toBeInTheDocument();
  });

  it('renders the error state', () => {
    (useSessionsQuery as any).mockReturnValue({
      isLoading: false,
      isError: true,
      error: new Error('boom'),
    });
    render(<CurrentSessions />);
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('lists devices, marks the current one, and enables log-out-others', () => {
    (useSessionsQuery as any).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [
        { id: 'a', device_label: 'Chrome on macOS', current: true, ip_address: '1.1.1.1' },
        { id: 'b', device_label: 'Safari on iPhone', current: false, ip_address: '2.2.2.2' },
      ],
    });
    render(<CurrentSessions />);
    expect(screen.getByText('Chrome on macOS')).toBeInTheDocument();
    expect(screen.getByText('Safari on iPhone')).toBeInTheDocument();
    expect(screen.getByText(/this device/i)).toBeInTheDocument();
    const others = screen.getByRole('button', { name: /log out all other devices/i });
    expect(others).toBeEnabled();
  });

  it('disables log-out-others when only the current device exists', () => {
    (useSessionsQuery as any).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [{ id: 'a', device_label: 'Chrome on macOS', current: true }],
    });
    render(<CurrentSessions />);
    expect(screen.getByRole('button', { name: /log out all other devices/i })).toBeDisabled();
  });

  it('confirms and revokes a single device', async () => {
    (useSessionsQuery as any).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [
        { id: 'a', device_label: 'Chrome on macOS', current: true },
        { id: 'b', device_label: 'Safari on iPhone', current: false },
      ],
    });
    render(<CurrentSessions />);
    fireEvent.click(screen.getByRole('button', { name: /^sign out$/i }));
    const confirm = await screen.findByRole('button', { name: /^sign out$/i });
    fireEvent.click(confirm);
    await waitFor(() => expect(revokeMutate).toHaveBeenCalledWith('b'));
  });
});
