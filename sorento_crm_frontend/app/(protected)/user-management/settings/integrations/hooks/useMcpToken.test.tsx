/**
 * MCP-TOKEN-UI: the plain token from Rotate never lands in the query cache (review S3).
 * Real QueryClient; only the service and the toast are mocked.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const FAKE = 'fake-token-for-tests-only-0000000000000wxyz';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../services/mcpTokenService', () => ({
  getMcpToken: vi.fn(),
  setMcpEnforce: vi.fn(),
  revokePreviousMcpToken: vi.fn(),
  rotateMcpToken: vi.fn(async () => ({
    configured: true,
    masked: '****wxyz',
    unreadable: false,
    enforce: false,
    rotated_at: '2026-10-30T10:00:00+00:00',
    previous_valid_until: null,
    grace_hours: 24,
    token: FAKE,
  })),
}));

import { MCP_TOKEN_KEY, useRotateMcpToken } from './useMcpToken';

describe('useRotateMcpToken', () => {
  it('hands the token to the caller but keeps it out of the query cache', async () => {
    const client = new QueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useRotateMcpToken(), { wrapper });
    let handed: string | undefined;
    act(() => {
      result.current.mutate(undefined, {
        onSuccess: (r) => {
          handed = r.token;
        },
      });
    });
    await waitFor(() => expect(handed).toBe(FAKE));
    const cached = client.getQueryData(MCP_TOKEN_KEY) as Record<
      string,
      unknown
    >;
    expect(cached.masked).toBe('****wxyz');
    expect('token' in cached).toBe(false);
    expect(
      JSON.stringify(
        client
          .getQueryCache()
          .getAll()
          .map((q) => q.state.data),
      ),
    ).not.toContain(FAKE);
  });
});
