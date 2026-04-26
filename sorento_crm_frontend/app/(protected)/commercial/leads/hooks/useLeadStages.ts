import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  createLeadStage,
  deleteLeadStage,
  deleteLeadStageByCode,
  getLeadStageByCode,
  getLeadStages,
  updateLeadStage,
  updateLeadStageByCode,
  type LeadStageCreatePayload,
} from '../services/leadStageService';
import type { CommercialLeadStage } from '../types/lead.types';

export function useLeadStagesList() {
  return useQuery({
    queryKey: ['commercial-lead-stages'],
    queryFn: getLeadStages,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useLeadStageByCode(stageCode: string | null) {
  return useQuery({
    queryKey: ['commercial-lead-stage', stageCode],
    queryFn: () => {
      if (!stageCode) throw new Error('Code required');
      return getLeadStageByCode(stageCode);
    },
    enabled: !!stageCode,
    retry: 1,
  });
}

export function useCreateLeadStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: LeadStageCreatePayload) => createLeadStage(data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-lead-stages'] });
      toast.success('Stage created');
    },
    onError: (e: Error) => toast.error(e.message || 'Create failed'),
  });
}

export function useUpdateLeadStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<
        Pick<
          CommercialLeadStage,
          'stage_name' | 'sort_order' | 'is_terminal' | 'allows_conversion' | 'can_go_back' | 'is_active' | 'is_cancelled'
        >
      >;
    }) => updateLeadStage(id, data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-lead-stages'] });
      void qc.invalidateQueries({ queryKey: ['commercial-leads'] });
      toast.success('Stage updated');
    },
    onError: (e: Error) => toast.error(e.message || 'Update failed'),
  });
}

export function useUpdateLeadStageByCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      stageCode,
      data,
    }: {
      stageCode: string;
      data: Partial<
        Pick<
          CommercialLeadStage,
          'stage_name' | 'sort_order' | 'is_terminal' | 'allows_conversion' | 'can_go_back' | 'is_active' | 'is_cancelled'
        >
      >;
    }) => updateLeadStageByCode(stageCode, data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-lead-stages'] });
      void qc.invalidateQueries({ queryKey: ['commercial-lead-stage'] });
      void qc.invalidateQueries({ queryKey: ['commercial-leads'] });
      toast.success('Stage updated');
    },
    onError: (e: Error) => toast.error(e.message || 'Update failed'),
  });
}

export function useDeleteLeadStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteLeadStage(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-lead-stages'] });
      toast.success('Stage deleted');
    },
    onError: (e: Error) => toast.error(e.message || 'Delete failed'),
  });
}

export function useDeleteLeadStageByCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (stageCode: string) => deleteLeadStageByCode(stageCode),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-lead-stages'] });
      void qc.invalidateQueries({ queryKey: ['commercial-lead-stage'] });
      toast.success('Stage deleted');
    },
    onError: (e: Error) => toast.error(e.message || 'Delete failed'),
  });
}
