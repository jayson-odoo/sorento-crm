import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getLeaderboard = vi.hoisted(() => vi.fn());
vi.mock('@/services/salesLeaderboardService', () => ({
  getLeaderboard,
  getLeaderboardOptions: vi.fn(),
}));

import { useSalesLeaderboardQuery } from './useSalesLeaderboardQuery';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    {children}
  </QueryClientProvider>
);

describe('useSalesLeaderboardQuery', () => {
  it('keeps the last board while the next range loads, but shows none behind a disabled range', async () => {
    getLeaderboard.mockResolvedValue({ rows: [{ rank: 1 }] });
    const { result, rerender } = renderHook(
      ({ from, enabled }) => useSalesLeaderboardQuery({ date_from: from, date_to: '2026-10-31' }, enabled),
      { wrapper, initialProps: { from: '2026-10-01', enabled: true } },
    );
    await waitFor(() => expect(result.current.data).toBeTruthy());

    rerender({ from: '', enabled: false });
    expect(result.current.data).toBeUndefined();
    expect(getLeaderboard).toHaveBeenCalledTimes(1);
  });
});
