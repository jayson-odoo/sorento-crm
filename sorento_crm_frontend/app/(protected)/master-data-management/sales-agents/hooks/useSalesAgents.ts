import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import {
  annotateSalesAgent,
  bulkAnnotateSalesAgents,
  assignSalesAgentCustomers,
  getSalesAgent,
  getSalesAgentCustomers,
  getSalesAgents,
} from '../services/salesAgentService';
import type {
  MirrorAnnotationPayload,
  SalesAgentBulkAnnotatePayload,
} from '../types/salesAgent.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function salesAgentsListQueryKey(params: DataGridApiFetchParams): QueryKey {
  return [
    'sales-agents',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
  ];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function salesAgentsListParamsFromUrl(
  params: ListPagerParams,
): DataGridApiFetchParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
  };
}

/** The pager's two hooks into the sales agents list. */
export const salesAgentsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    salesAgentsListQueryKey(salesAgentsListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getSalesAgents(salesAgentsListParamsFromUrl(params)),
};

export function useSalesAgents(params: DataGridApiFetchParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: salesAgentsListQueryKey(params),
    queryFn: () => getSalesAgents(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

/** One agent by id, for the record page at `/master-data-management/sales-agents/{id}`. */
export function useSalesAgent(id: string | null) {
  return useQuery({
    queryKey: ['sales-agent', id],
    queryFn: () => {
      if (!id) throw new Error('Sales agent ID is required');
      return getSalesAgent(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

/** Set one annotation across a selection. Toasts the COUNT, because the whole point of the
 *  action is that it touched more than the row the user is looking at. */
export function useBulkAnnotateSalesAgents() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SalesAgentBulkAnnotatePayload) => bulkAnnotateSalesAgents(data),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['sales-agents'] });
      toast.success(`${res.updated} sales agent${res.updated === 1 ? '' : 's'} updated`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update the selected agents'),
  });
}

export function useAnnotateSalesAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MirrorAnnotationPayload }) =>
      annotateSalesAgent(id, data),
    onSuccess: (_res, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['sales-agents'] });
      queryClient.invalidateQueries({ queryKey: ['sales-agent', id] });
      toast.success('Sales agent updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save sales agent'),
  });
}

/** The agent's customers key. The unassign countdown invalidates it after the server commits. */
export const SALES_AGENT_CUSTOMERS_PREFIX = ['sales-agent-customers'] as const;
export const salesAgentCustomersKey = (agentId: string) => [...SALES_AGENT_CUSTOMERS_PREFIX, agentId];

export function useSalesAgentCustomers(agentId: string, params: DataGridApiFetchParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [
      ...salesAgentCustomersKey(agentId),
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
    ],
    queryFn: () => getSalesAgentCustomers(agentId, params),
    enabled: !!agentId,
    retry: 1,
  });
}

export function useAssignSalesAgentCustomers(agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (customerIds: string[]) => assignSalesAgentCustomers(agentId, customerIds),
    onSuccess: (customers) => {
      // The whole prefix: the customer left another agent's tab too, and that tab may be cached.
      queryClient.invalidateQueries({ queryKey: SALES_AGENT_CUSTOMERS_PREFIX });
      // The customer's own detail shows its agent.
      queryClient.invalidateQueries({ queryKey: ['customer'] });
      // The contact card shows the agent per linked customer, so it must refetch too.
      queryClient.invalidateQueries({ queryKey: ['contact-customers'] });
      toast.success(
        customers.length === 1 ? 'Customer assigned' : `${customers.length} customers assigned`,
      );
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to assign customers'),
  });
}
