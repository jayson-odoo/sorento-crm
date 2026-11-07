import { useQuery } from '@tanstack/react-query';
import {
  getLeaderboard,
  getLeaderboardOptions,
  type LeaderboardParams,
} from '@/services/salesLeaderboardService';

export const SALES_LEADERBOARD_KEY = ['sales-leaderboard'] as const;
export const SALES_LEADERBOARD_OPTIONS_KEY = ['sales-leaderboard-options'] as const;

/** `enabled` is false while a Custom range is still half picked. */
export function useSalesLeaderboardQuery(params: LeaderboardParams, enabled = true) {
  return useQuery({
    queryKey: [...SALES_LEADERBOARD_KEY, params],
    queryFn: () => getLeaderboard(params),
    enabled,
    // Keep the last board while the next one loads, but never behind a disabled (half-picked) range.
    placeholderData: enabled ? (previous) => previous : undefined,
    retry: 1,
  });
}

export function useSalesLeaderboardOptionsQuery() {
  return useQuery({
    queryKey: SALES_LEADERBOARD_OPTIONS_KEY,
    queryFn: getLeaderboardOptions,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}
