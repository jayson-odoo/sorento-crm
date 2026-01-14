import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getSLAPolicies, getSLAPolicy, createSLAPolicy, updateSLAPolicy, deleteSLAPolicy, getSLAPolicyTiers, createSLAPolicyTier, updateSLAPolicyTier, deleteSLAPolicyTier } from '../services/slaPolicyService';
import type { SLAPolicyFormData, SLAPolicyTierFormData } from '../types/slaPolicy.types';

export function useSLAPolicies(params: DataGridApiFetchParams & { status?: string }) {
  return useQuery({
    queryKey: ['sla-policies', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.status],
    queryFn: () => getSLAPolicies(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useSLAPolicy(id: string | null) {
  return useQuery({
    queryKey: ['sla-policy', id],
    queryFn: () => {
      if (!id) throw new Error('SLA policy ID is required');
      return getSLAPolicy(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateSLAPolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SLAPolicyFormData) => createSLAPolicy(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sla-policies'] });
      toast.success('SLA policy created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create SLA policy'),
  });
}

export function useUpdateSLAPolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<SLAPolicyFormData> }) => updateSLAPolicy(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sla-policies'] });
      queryClient.invalidateQueries({ queryKey: ['sla-policy'] });
      toast.success('SLA policy updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update SLA policy'),
  });
}

export function useDeleteSLAPolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteSLAPolicy(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sla-policies'] });
      toast.success('SLA policy deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete SLA policy'),
  });
}

// SLA Policy Tier hooks
export function useSLAPolicyTiers(policyId: string | null) {
  return useQuery({
    queryKey: ['sla-policy-tiers', policyId],
    queryFn: () => {
      if (!policyId) throw new Error('Policy ID is required');
      return getSLAPolicyTiers(policyId);
    },
    enabled: !!policyId,
    retry: 1,
  });
}

export function useCreateSLAPolicyTier() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ policyId, data }: { policyId: string; data: SLAPolicyTierFormData }) => createSLAPolicyTier(policyId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['sla-policy-tiers', variables.policyId] });
      queryClient.invalidateQueries({ queryKey: ['sla-policy', variables.policyId] });
      toast.success('SLA policy tier created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create SLA policy tier'),
  });
}

export function useUpdateSLAPolicyTier() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ policyId, tierId, data }: { policyId: string; tierId: string; data: Partial<SLAPolicyTierFormData> }) => updateSLAPolicyTier(policyId, tierId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['sla-policy-tiers', variables.policyId] });
      queryClient.invalidateQueries({ queryKey: ['sla-policy', variables.policyId] });
      toast.success('SLA policy tier updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update SLA policy tier'),
  });
}

export function useDeleteSLAPolicyTier() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ policyId, tierId }: { policyId: string; tierId: string }) => deleteSLAPolicyTier(policyId, tierId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['sla-policy-tiers', variables.policyId] });
      queryClient.invalidateQueries({ queryKey: ['sla-policy', variables.policyId] });
      toast.success('SLA policy tier deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete SLA policy tier'),
  });
}
