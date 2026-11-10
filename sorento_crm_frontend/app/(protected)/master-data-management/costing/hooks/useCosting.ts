import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  addPartyProducts,
  createExchangeRate,
  exportCosting,
  getCategoryRules,
  getCostingRowHistory,
  getCostingRows,
  getCostingRowSuppliers,
  getCostingSettings,
  getExchangeRates,
  getParty,
  getPartyProductIds,
  saveCategoryRule,
  saveCostingRows,
  saveCostingSettings,
  saveParty,
} from '../services/costingService';
import type {
  CostingRowsParams,
  CostingSupplierParams,
  ExchangeRateBody,
  PartyBody,
  SaveRowsBody,
  CostingSettings,
} from '../types/costing.types';

export const COSTING_ROWS_KEY = ['costing-rows'] as const;
export const COSTING_SUPPLIERS_KEY = ['costing-suppliers'] as const;
export const COSTING_HISTORY_KEY = ['costing-history'] as const;
export const COSTING_SETTINGS_KEY = ['costing-settings'] as const;
export const COSTING_RULES_KEY = ['costing-category-rules'] as const;
export const COSTING_RATES_KEY = ['costing-exchange-rates'] as const;
export const COSTING_PARTY_KEY = ['costing-party'] as const;

const message = (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback);

export function useCostingRows(params: CostingRowsParams, enabled = true) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [...COSTING_ROWS_KEY, params],
    queryFn: ({ signal }) => getCostingRows(params, signal),
    enabled,
  });
}

export function useCostingSuppliers(productId: string, scope: CostingSupplierParams, enabled = true) {
  return useQuery({
    queryKey: [...COSTING_SUPPLIERS_KEY, productId, scope],
    queryFn: () => getCostingRowSuppliers(productId, scope),
    enabled: enabled && !!productId,
  });
}

export function useCostingHistory(productId: string | null, partyId: string | null) {
  return useQuery({
    queryKey: [...COSTING_HISTORY_KEY, productId, partyId],
    queryFn: () => getCostingRowHistory(productId as string, partyId),
    enabled: !!productId,
  });
}

/** The one Save of the page: one PATCH of only the changed cells. */
export function useSaveCostingRows() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SaveRowsBody) => saveCostingRows(body),
    onSuccess: () => {
      toast.success('Costing saved');
      void qc.invalidateQueries({ queryKey: COSTING_ROWS_KEY });
      void qc.invalidateQueries({ queryKey: COSTING_SUPPLIERS_KEY });
      void qc.invalidateQueries({ queryKey: COSTING_HISTORY_KEY });
    },
    onError: (error) => toast.error(message(error, 'Failed to save costing')),
  });
}

export function useExportCosting() {
  return useMutation({
    mutationFn: (params: CostingRowsParams) => exportCosting(params),
    onError: (error) => toast.error(message(error, 'Failed to export costing')),
  });
}

export function useCostingSettings(enabled = true) {
  return useQuery({ queryKey: COSTING_SETTINGS_KEY, queryFn: getCostingSettings, enabled });
}

export function useSaveCostingSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CostingSettings) => saveCostingSettings(body),
    onSuccess: () => {
      toast.success('Settings saved');
      void qc.invalidateQueries({ queryKey: COSTING_SETTINGS_KEY });
      void qc.invalidateQueries({ queryKey: COSTING_ROWS_KEY });
    },
    onError: (error) => toast.error(message(error, 'Failed to save the settings')),
  });
}

export function useCategoryRules(enabled = true) {
  return useQuery({ queryKey: COSTING_RULES_KEY, queryFn: getCategoryRules, enabled });
}

export function useSaveCategoryRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { categoryId: string; mode: string | null; value: number | null }) =>
      saveCategoryRule(v.categoryId, { mode: v.mode, value: v.value }),
    onError: (error) => toast.error(message(error, 'Failed to save the transport rule')),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: COSTING_RULES_KEY });
      void qc.invalidateQueries({ queryKey: COSTING_ROWS_KEY });
    },
  });
}

export function useExchangeRates(enabled = true) {
  return useQuery({ queryKey: COSTING_RATES_KEY, queryFn: () => getExchangeRates(), enabled });
}

export function useCreateExchangeRate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ExchangeRateBody) => createExchangeRate(body),
    onSuccess: () => {
      toast.success('Rate added');
      void qc.invalidateQueries({ queryKey: COSTING_RATES_KEY });
      void qc.invalidateQueries({ queryKey: COSTING_ROWS_KEY });
    },
    onError: (error) => toast.error(message(error, 'Failed to add the rate')),
  });
}

export function useCostingParty(customerId: string | null) {
  return useQuery({
    queryKey: [...COSTING_PARTY_KEY, customerId],
    queryFn: () => getParty(customerId as string),
    enabled: !!customerId,
  });
}

export function usePartyProductIds(customerId: string | null, enabled = true) {
  return useQuery({
    queryKey: [...COSTING_PARTY_KEY, customerId, 'product-ids'],
    queryFn: () => getPartyProductIds(customerId as string),
    enabled: enabled && !!customerId,
  });
}

export function useSaveParty() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { customerId: string; body: PartyBody }) => saveParty(v.customerId, v.body),
    onSuccess: () => {
      toast.success('Party saved');
      void qc.invalidateQueries({ queryKey: COSTING_ROWS_KEY });
      void qc.invalidateQueries({ queryKey: COSTING_PARTY_KEY });
    },
    onError: (error) => toast.error(message(error, 'Failed to save the party')),
  });
}

export function useAddPartyProducts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { customerId: string; productIds: string[] }) =>
      addPartyProducts(v.customerId, v.productIds),
    onSuccess: (result) => {
      toast.success(
        result.already
          ? `Added ${result.added}, ${result.already} already on the list`
          : `Added ${result.added} product${result.added === 1 ? '' : 's'}`,
      );
      void qc.invalidateQueries({ queryKey: COSTING_ROWS_KEY });
      void qc.invalidateQueries({ queryKey: COSTING_PARTY_KEY });
    },
    onError: (error) => toast.error(message(error, 'Failed to add the products')),
  });
}
