import { useQuery } from '@tanstack/react-query';

import { getMediaRequest } from '../services/conversationSLATrackingService';

/** The side panel's read of one product drawing or photo task. */
export function useMediaRequest(id: string | null) {
  return useQuery({
    queryKey: ['media-request', id],
    queryFn: () => getMediaRequest(id as string),
    enabled: !!id,
  });
}
