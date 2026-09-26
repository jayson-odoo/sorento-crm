import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  createSalesOpportunity,
  deleteSalesOpportunity,
  getSalesOpportunities,
  getSalesOpportunity,
  getSalesOpportunityAgentOptions,
  getSalesOpportunityMeta,
  updateSalesOpportunity,
} from '../services/salesOpportunityService';
import type {
  SalesOpportunityDetail,
  SalesOpportunityListParams,
  SalesOpportunitySavePayload,
} from '../types/salesOpportunity.types';

export const SALES_OPPORTUNITIES_KEY = ['sales-opportunities'] as const;
export const SALES_OPPORTUNITY_KEY = ['sales-opportunity'] as const;
export const SALES_OPPORTUNITY_META_KEY = ['sales-opportunity-meta'] as const;
export const SALES_OPPORTUNITY_AGENT_OPTIONS_KEY = ['sales-opportunity-agent-options'] as const;

export function useSalesOpportunities(params: SalesOpportunityListParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [...SALES_OPPORTUNITIES_KEY, params],
    queryFn: () => getSalesOpportunities(params),
  });
}

export function useSalesOpportunity(id: string | null) {
  return useQuery({
    queryKey: [...SALES_OPPORTUNITY_KEY, id],
    queryFn: () => getSalesOpportunity(id as string),
    enabled: !!id,
    retry: 1,
  });
}

export function useSalesOpportunityMeta() {
  return useQuery({
    queryKey: SALES_OPPORTUNITY_META_KEY,
    queryFn: getSalesOpportunityMeta,
    staleTime: 60_000,
  });
}

export function useSalesOpportunityAgentOptions(enabled = true) {
  return useQuery({
    queryKey: SALES_OPPORTUNITY_AGENT_OPTIONS_KEY,
    queryFn: getSalesOpportunityAgentOptions,
    enabled,
    staleTime: 30_000,
  });
}

/**
 * The customer page's Opportunities section (S2-12, J8): every opportunity naming this
 * customer, newest first, unpaged - a dealer's own pipeline is a handful of rows.
 */
export function useCustomerOpportunities(customerId: string | null) {
  return useQuery({
    queryKey: [...SALES_OPPORTUNITIES_KEY, 'by-customer', customerId],
    queryFn: async () => {
      const result = await getSalesOpportunities({
        pageIndex: 0,
        pageSize: 100,
        customerId: customerId as string,
      });
      return result.data;
    },
    enabled: !!customerId,
  });
}

/**
 * One save shape for both the Log opportunity modal (no `id`: create) and the detail
 * page's in-place edit (`id`: patch) - same split as `useSaveSalesTeam`. The id travels
 * IN the mutate payload rather than fixed per hook instance, so one hook instance can
 * back a list of rows (or a modal reused across opens) without being re-created per id.
 */
export function useSaveSalesOpportunity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...payload
    }: SalesOpportunitySavePayload & { id?: string }): Promise<SalesOpportunityDetail> =>
      id ? updateSalesOpportunity(id, payload) : createSalesOpportunity(payload),
    onSuccess: (_opportunity, variables) => {
      queryClient.invalidateQueries({ queryKey: SALES_OPPORTUNITIES_KEY });
      queryClient.invalidateQueries({ queryKey: SALES_OPPORTUNITY_KEY });
      toast.success(variables.id ? 'Opportunity saved' : 'Opportunity logged');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save opportunity'),
  });
}

export function useDeleteSalesOpportunity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteSalesOpportunity(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SALES_OPPORTUNITIES_KEY });
      queryClient.invalidateQueries({ queryKey: SALES_OPPORTUNITY_KEY });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete opportunity'),
  });
}
