import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import type { ListPagerPage, ListPagerParams } from '@/hooks/useListPager';
import { getCampaigns, getCampaign, getCampaignTypes, createCampaign, updateCampaign } from '../services/campaignService';
import type { CampaignFormData } from '../types/campaign.types';

type CampaignsListParams = DataGridApiFetchParams & {
  campaign_type_id?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  budget_min?: number;
  budget_max?: number;
};

/**
 * One key for the list and the pager, or they cache separately and the pager
 * refetches a page the list is already holding.
 */
export function campaignsListQueryKey(params: CampaignsListParams): QueryKey {
  return [
    'campaigns',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.campaign_type_id,
    params.status,
    params.date_from,
    params.date_to,
    params.budget_min,
    params.budget_max,
  ];
}

/** The URL's own params, in the shape the list asks its questions in. */
function campaignsListParamsFromUrl(params: ListPagerParams): CampaignsListParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    status: params.filters.status,
  };
}

/** The pager's two hooks into the campaigns list. */
export const campaignsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    campaignsListQueryKey(campaignsListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getCampaigns(campaignsListParamsFromUrl(params)),
};

export function useCampaigns(params: CampaignsListParams) {
  return useQuery({
    queryKey: campaignsListQueryKey(params),
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

