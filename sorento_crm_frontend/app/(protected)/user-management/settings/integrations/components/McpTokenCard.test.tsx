/**
 * Settings -> Integrations, MCP access token card (MCP-TOKEN-UI).
 * Hooks are mocked so each test drives the query / mutation state directly.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

const mockQuery = vi.fn();
const mockRotate = vi.fn();
const mockEnforce = vi.fn();
const mockRevoke = vi.fn();

vi.mock('../hooks/useMcpToken', () => ({
  useMcpToken: () => mockQuery(),
  useRotateMcpToken: () => ({ mutate: mockRotate, isPending: false }),
  useSetMcpEnforce: () => ({ mutate: mockEnforce, isPending: false }),
  useRevokePreviousMcpToken: () => ({ mutate: mockRevoke, isPending: false }),
}));

import McpTokenCard from './McpTokenCard';
import type { McpTokenState } from '../services/mcpTokenService';

const FAKE = 'fake-token-for-tests-only-0000000000000wxyz';

function state(overrides: Partial<McpTokenState> = {}): McpTokenState {
  return {
    configured: false,
    masked: null,
    unreadable: false,
    enforce: false,
    rotated_at: null,
    previous_valid_until: null,
    grace_hours: 24,
    ...overrides,
  };
}

beforeEach(() => {
  mockQuery.mockReturnValue({
    isLoading: false,
    isError: false,
    data: state(),
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('McpTokenCard', () => {
  it('offers Generate when no token is set, and Enforce is disabled', () => {
    render(<McpTokenCard />);
    expect(screen.getByText('MCP access token')).toBeTruthy();
    expect(screen.getByText('Not set')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Generate token' })).toBeTruthy();
    const enforce = screen.getByRole('switch', { name: 'Enforce' });
    expect(enforce.hasAttribute('disabled')).toBe(true);
  });

  it('shows the masked token and Rotate once one is set', () => {
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: state({ configured: true, masked: '****wxyz' }),
    });
    render(<McpTokenCard />);
    expect(screen.getByText('****wxyz')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Rotate token' })).toBeTruthy();
    const enforce = screen.getByRole('switch', { name: 'Enforce' });
    expect(enforce.hasAttribute('disabled')).toBe(false);
  });

  it('shows a new token once after Generate, with a copy button', () => {
    mockRotate.mockImplementation(
      (_v: unknown, opts: { onSuccess: (r: { token: string }) => void }) =>
        opts.onSuccess({ token: FAKE }),
    );
    render(<McpTokenCard />);
    fireEvent.click(screen.getByRole('button', { name: 'Generate token' }));
    expect(
      (screen.getByLabelText('New MCP token') as HTMLInputElement).value,
    ).toBe(FAKE);
    expect(screen.getByRole('button', { name: 'Copy MCP token' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Hide token' }));
    expect(screen.queryByLabelText('New MCP token')).toBeNull();
    expect(screen.queryByDisplayValue(FAKE)).toBeNull();
  });

  it('switches Enforce through the mutation', () => {
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: state({ configured: true, masked: '****wxyz' }),
    });
    render(<McpTokenCard />);
    fireEvent.click(screen.getByRole('switch', { name: 'Enforce' }));
    expect(mockEnforce).toHaveBeenCalledWith(true);
  });

  it('shows the previous token grace window and revokes it', () => {
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: state({
        configured: true,
        masked: '****wxyz',
        previous_valid_until: '2026-10-31T10:00:00+00:00',
      }),
    });
    render(<McpTokenCard />);
    expect(screen.getByText(/Previous token valid until/)).toBeTruthy();
    fireEvent.click(
      screen.getByRole('button', { name: 'Revoke previous now' }),
    );
    expect(mockRevoke).toHaveBeenCalled();
  });

  it('hides the grace line when there is no previous token', () => {
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: state({ configured: true, masked: '****wxyz' }),
    });
    render(<McpTokenCard />);
    expect(screen.queryByText(/Previous token valid until/)).toBeNull();
    expect(
      screen.queryByRole('button', { name: 'Revoke previous now' }),
    ).toBeNull();
  });

  it('flags a token that no longer decrypts', () => {
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: state({ configured: true, unreadable: true }),
    });
    render(<McpTokenCard />);
    expect(screen.getByText('Saved token unreadable, rotate it')).toBeTruthy();
  });

  it('renders the load error with a Retry', () => {
    const refetch = vi.fn();
    mockQuery.mockReturnValue({
      isLoading: false,
      isError: true,
      error: new Error('Failed to load the MCP token'),
      refetch,
    });
    render(<McpTokenCard />);
    expect(screen.getByText('Failed to load the MCP token')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(refetch).toHaveBeenCalled();
  });
});
