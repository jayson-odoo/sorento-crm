import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  listPortalRevisionConfigs,
  updatePortalRevisionConfig,
  savePortalRevisionGlobals,
  type PortalRevisionConfigInput,
  type PortalRevisionGlobals,
} from '../services/portalRevisionConfigService';

export const PORTAL_REVISION_CONFIGS_KEY = ['portal-revision-configs'];

export function usePortalRevisionConfigs() {
  return useQuery({
    queryKey: PORTAL_REVISION_CONFIGS_KEY,
    queryFn: listPortalRevisionConfigs,
    retry: 1,
  });
}

export function useUpdatePortalRevisionConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      sourceEntityType,
      input,
    }: {
      sourceEntityType: string;
      input: PortalRevisionConfigInput;
    }) => updatePortalRevisionConfig(sourceEntityType, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PORTAL_REVISION_CONFIGS_KEY });
      toast.success('Revision config saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useSavePortalRevisionGlobals() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (globals: PortalRevisionGlobals) => savePortalRevisionGlobals(globals),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
      toast.success('Portal revision settings saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
