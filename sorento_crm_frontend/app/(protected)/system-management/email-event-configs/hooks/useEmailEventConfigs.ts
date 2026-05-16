import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  listEmailEventConfigs,
  updateEmailEventConfig,
} from '../services/emailEventConfigsService';
import type { EmailEventConfigUpdate } from '../types/emailEventConfig.types';

export function useEmailEventConfigs() {
  return useQuery({
    queryKey: ['email-event-configs'],
    queryFn: listEmailEventConfigs,
    staleTime: 1000 * 30,
    refetchOnWindowFocus: false,
  });
}

export function useUpdateEmailEventConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ event_key, payload }: { event_key: string; payload: EmailEventConfigUpdate }) =>
      updateEmailEventConfig(event_key, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['email-event-configs'] });
      toast.success('Event config updated.');
    },
    onError: (err: Error) => toast.error(err.message),
  });
}
