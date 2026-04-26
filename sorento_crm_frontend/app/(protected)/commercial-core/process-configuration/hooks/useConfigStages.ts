import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  listConfigStages,
  getConfigStageByCode,
  createConfigStage,
  updateConfigStage,
  deleteConfigStage,
  type ConfigStageResource,
} from '../services/configStageService';
import type { ConfigStageFormData } from '../types/configStage.types';

export function useConfigStages(resource: ConfigStageResource, params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: ['commercial-config-stages', resource, params.pageIndex, params.pageSize],
    queryFn: () => listConfigStages(resource, params),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useConfigStageByCode(resource: ConfigStageResource, code: string | null) {
  return useQuery({
    queryKey: ['commercial-config-stage', resource, code],
    queryFn: () => {
      if (!code) throw new Error('Code required');
      return getConfigStageByCode(resource, code);
    },
    enabled: !!code,
    retry: 1,
  });
}

export function useCreateConfigStage(resource: ConfigStageResource) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ConfigStageFormData) => createConfigStage(resource, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-config-stages', resource] });
      toast.success('Saved');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateConfigStage(resource: ConfigStageResource) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ code, data }: { code: string; data: Partial<ConfigStageFormData> }) =>
      updateConfigStage(resource, code, data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-config-stages', resource] });
      void qc.invalidateQueries({ queryKey: ['commercial-config-stage', resource] });
      toast.success('Saved');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteConfigStage(resource: ConfigStageResource) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (code: string) => deleteConfigStage(resource, code),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-config-stages', resource] });
      toast.success('Deleted');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
