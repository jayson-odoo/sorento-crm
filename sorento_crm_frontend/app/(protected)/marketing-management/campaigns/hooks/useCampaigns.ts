import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getCampaigns, getCampaign, getCampaignTypes, createCampaign, updateCampaign, deleteCampaign } from '../services/campaignService';
import type { CampaignFormData } from '../types/campaign.types';

export function useCampaigns(params: DataGridApiFetchParams & { campaign_type_id?: string; status?: string; date_from?: string; date_to?: string; budget_min?: number; budget_max?: number }) {
  return useQuery({
    queryKey: ['campaigns', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.campaign_type_id, params.status, params.date_from, params.date_to, params.budget_min, params.budget_max],
    queryFn: () => getCampaigns(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useCampaign(id: string | null) {
  return useQuery({
    queryKey: ['campaign', id],
    queryFn: () => {
      if (!id) throw new Error('Campaign ID is required');
      return getCampaign(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCampaignTypes() {
  return useQuery({
    queryKey: ['campaign-types'],
    queryFn: getCampaignTypes,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useCreateCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CampaignFormData) => createCampaign(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
      toast.success('Campaign created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create campaign'),
  });
}

export function useUpdateCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CampaignFormData> }) => updateCampaign(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
      queryClient.invalidateQueries({ queryKey: ['campaign'] });
      toast.success('Campaign updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update campaign'),
  });
}

export function useDeleteCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteCampaign(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
      toast.success('Campaign deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete campaign'),
  });
}
