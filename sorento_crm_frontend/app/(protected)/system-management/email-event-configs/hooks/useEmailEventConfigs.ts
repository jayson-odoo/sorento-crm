import { useQuery } from '@tanstack/react-query';
import { useEntityMutation } from '@/hooks/useEntityMutation';
import {
  listEmailEventConfigs,
  updateEmailEventConfig,
} from '../services/emailEventConfigsService';
import type {
  EmailEventConfig,
  EmailEventConfigUpdate,
} from '../types/emailEventConfig.types';

export function useEmailEventConfigs() {
  return useQuery({
    queryKey: ['email-event-configs'],
    queryFn: listEmailEventConfigs,
    staleTime: 1000 * 30,
    refetchOnWindowFocus: false,
  });
}

/**
 * Backs both the kill switch and the Save overrides button on the same row.
 * Optimistic (S7-01) for the switch's sake: it is the control that has to move
 * on press, and the overrides inherit the same rollback for free.
 */
export function useUpdateEmailEventConfig() {
  return useEntityMutation<
    { event_key: string; payload: EmailEventConfigUpdate },
    EmailEventConfig
  >({
    mutationFn: ({ event_key, payload }) => updateEmailEventConfig(event_key, payload),
    keys: [['email-event-configs']],
    matchRow: (row, variables) => row.event_key === variables.event_key,
    patchRow: (variables) => ({ ...variables.payload }),
    successMessage: () => 'Event config updated.',
    errorMessage: 'Could not update the event config',
  });
}
