import { useQuery } from '@tanstack/react-query';
import {
  getActivityFeed,
  type GetActivityFeedParams,
} from '../services/activityService';

/**
 * Query hook for the Activity Timeline, backed by `GET /api/v1/audit/activity`.
 * Loading / empty / error states are driven by react-query.
 */
export function useActivityFeed(params: GetActivityFeedParams) {
  return useQuery({
    queryKey: [
      'activity-feed',
      params.entity_types,
      params.action,
      params.user_id,
      params.date_from,
      params.date_to,
      params.q,
      params.trace_id,
      params.page,
      params.limit,
    ],
    queryFn: () => getActivityFeed(params),
    staleTime: 1000 * 60 * 2,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
