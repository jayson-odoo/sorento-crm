'use client';

/**
 * Hooks for the cost price change set domain (#1288, Lane A). UI -> hook -> service, per
 * `PRINCIPLES.md` layering; the service underneath is the Phase 1 mock
 * (`../services/costPriceService.ts`), swapped for real `apiFetch` calls in Phase 2.
 */

import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import * as costPriceService from '../services/costPriceService';
import type { LineDecision } from '../types/costPrice.types';
import { OpenSetExistsError, type CostPriceListParams } from '../services/costPriceService';

export { OpenSetExistsError };

export type { CostPriceListParams };

export function costPriceChangeSetsListQueryKey(params: CostPriceListParams): QueryKey {
  return ['cost-price-change-sets', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.status, params.supplier_id];
}

export async function fetchCostPriceChangeSetsPage(params: CostPriceListParams): Promise<ListPagerPage> {
  const result = await costPriceService.getCostPriceChangeSets(params);
  return { data: result.data, total: result.total };
}

function costPriceListParamsFromUrl(params: ListPagerParams): CostPriceListParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    status: params.filters.status ? params.filters.status.split(',').filter(Boolean) : undefined,
    supplier_id: params.filters.supplier_id || undefined,
  };
}

export const costPriceChangeSetsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    costPriceChangeSetsListQueryKey(costPriceListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    fetchCostPriceChangeSetsPage(costPriceListParamsFromUrl(params)),
};

export function useCostPriceChangeSets(params: CostPriceListParams) {
  return useQuery({
    queryKey: costPriceChangeSetsListQueryKey(params),
    queryFn: () => costPriceService.getCostPriceChangeSets(params),
    ...LIST_QUERY_OPTIONS,
  });
}

export function useCostPriceChangeSet(id: string | null) {
  return useQuery({
    queryKey: ['cost-price-change-set', id],
    queryFn: () => costPriceService.getCostPriceChangeSet(id as string),
    enabled: !!id,
  });
}

export function useCostPriceChangeLines(id: string | null) {
  return useQuery({
    queryKey: ['cost-price-change-set', id, 'lines'],
    queryFn: () => costPriceService.getCostPriceChangeLines(id as string),
    enabled: !!id,
  });
}

export function useCostPriceChangeSetHistory(id: string | null) {
  return useQuery({
    queryKey: ['cost-price-change-set', id, 'history'],
    queryFn: () => costPriceService.getCostPriceChangeSetHistory(id as string),
    enabled: !!id,
  });
}

function invalidateSet(queryClient: ReturnType<typeof useQueryClient>, id: string) {
  queryClient.invalidateQueries({ queryKey: ['cost-price-change-set', id] });
  queryClient.invalidateQueries({ queryKey: ['cost-price-change-sets'] });
}

export function useProbeCostPriceFile() {
  return useMutation({ mutationFn: (file: File) => costPriceService.probeCostPriceFile(file) });
}

export function useUploadCostPriceFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: costPriceService.UploadCostPriceFileInput) => costPriceService.uploadCostPriceFile(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cost-price-change-sets'] });
    },
    onError: (error: Error) => {
      if (!(error instanceof OpenSetExistsError)) toast.error(error.message);
    },
  });
}

export function usePatchCostPriceChangeLine(setId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { lineId: string; patch: costPriceService.PatchLineInput }) =>
      costPriceService.patchCostPriceChangeLine(setId as string, input.lineId, input.patch),
    onSuccess: () => {
      if (setId) {
        queryClient.invalidateQueries({ queryKey: ['cost-price-change-set', setId, 'lines'] });
        invalidateSet(queryClient, setId);
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useSubmitCostPriceChangeSet(setId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => costPriceService.submitCostPriceChangeSet(setId),
    onSuccess: () => {
      toast.success('Submitted for verification.');
      invalidateSet(queryClient, setId);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useDecideCostPriceLine(setId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { lineId: string; decision: LineDecision; reason?: string }) =>
      costPriceService.decideCostPriceLine(setId, input.lineId, input.decision, input.reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cost-price-change-set', setId, 'lines'] });
      invalidateSet(queryClient, setId);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useDecideAllCostPriceLines(setId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (decision: 'accepted' | 'rejected') => costPriceService.decideAllCostPriceLines(setId, decision),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cost-price-change-set', setId, 'lines'] });
      invalidateSet(queryClient, setId);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useReturnCostPriceChangeSet(setId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => costPriceService.returnCostPriceChangeSet(setId, reason),
    onSuccess: () => {
      toast.success('Returned to the submitter.');
      queryClient.invalidateQueries({ queryKey: ['cost-price-change-set', setId, 'lines'] });
      invalidateSet(queryClient, setId);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useRefreshCostPricePrices(setId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => costPriceService.refreshCostPricePrices(setId),
    onSuccess: () => {
      toast.success('Prices refreshed.');
      queryClient.invalidateQueries({ queryKey: ['cost-price-change-set', setId, 'lines'] });
      invalidateSet(queryClient, setId);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useApplyCostPriceChangeSet(setId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => costPriceService.applyCostPriceChangeSet(setId),
    onSuccess: (detail) => {
      toast.success(`${detail.code} applied.`);
      queryClient.invalidateQueries({ queryKey: ['cost-price-change-set', setId, 'lines'] });
      invalidateSet(queryClient, setId);
      queryClient.invalidateQueries({ queryKey: ['supplier-cost-lists'] });
      queryClient.invalidateQueries({ queryKey: ['product-suppliers'] });
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
