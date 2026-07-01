import { useQuery } from '@tanstack/react-query';
import {
  getActivityFeed,
  type GetActivityFeedParams,
} from '../services/activityService';

/**
 * PHASE-1 stubbed query hook for the Activity Timeline.
 *
 * Backed by the mock resolver in `activityService`; the `mockState` param lets
 * the page demo loading / empty / error / success without a backend. When the
 * real `GET /api/v1/audit/activity` lands in Phase-2 only the service changes —
 * this hook's shape stays identical.
 */
export function useActivityFeed(params: GetActivityFeedParams) {
  return useQuery({
    queryKey: [
      'activity-feed',
      params.mockState,
      params.entity_types,
      params.action,
      params.user_id,
      params.date_from,
      params.date_to,
      params.q,
      params.page,
      params.limit,
    ],
    queryFn: () => getActivityFeed(params),
    staleTime: 1000 * 60 * 2,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
