'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  createReorderPolicy,
  deleteReorderPolicy,
  getClassification,
  getCoverScope,
  getClassScopeOptions,
  getFulfilmentPriority,
  getPlanningMode,
  getProductScopeOptions,
  getSupplierScoring,
  getWarehouseScopeOptions,
  listReorderPolicies,
  resolvePolicy,
  saveClassification,
  saveCoverScope,
  saveFulfilmentPriority,
  savePlanningMode,
  saveSupplierScoring,
  updateReorderPolicy,
  type PolicyListQuery,
} from '../services/scmPolicyService';
import type {
  AbcXyzWrite,
  CoverScopeWrite,
  FulfilmentPriorityWrite,
  PlanningModeWrite,
  ReorderPolicyWrite,
  SupplierScoringWrite,
} from '../types/policy.types';

const REORDER_KEY = ['scm', 'policies', 'reorder'] as const;
const CLASSIFICATION_KEY = ['scm', 'policies', 'classification'] as const;
const SUPPLIER_KEY = ['scm', 'policies', 'supplier-scoring'] as const;
const PLANNING_MODE_KEY = ['scm', 'policies', 'planning-mode'] as const;
const COVER_SCOPE_KEY = ['scm', 'policies', 'cover-scope'] as const;
const FULFILMENT_PRIORITY_KEY = ['scm', 'policies', 'fulfilment-priority'] as const;

const optionOpts = { staleTime: 5 * 60_000, refetchOnWindowFocus: false, retry: 1 } as const;

// ── Reorder policies ────────────────────────────────────────────────────────

export function useReorderPolicies(query: PolicyListQuery) {
  return useQuery({
    queryKey: [...REORDER_KEY, query],
    queryFn: () => listReorderPolicies(query),
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useCreatePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ReorderPolicyWrite) => createReorderPolicy(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REORDER_KEY });
      toast.success('Policy created');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdatePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ReorderPolicyWrite }) =>
      updateReorderPolicy(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REORDER_KEY });
      toast.success('Policy updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeletePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteReorderPolicy(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REORDER_KEY });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// ── Classification thresholds ───────────────────────────────────────────────

export function useClassification() {
  return useQuery({
    queryKey: CLASSIFICATION_KEY,
    queryFn: getClassification,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useSaveClassification() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AbcXyzWrite) => saveClassification(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CLASSIFICATION_KEY });
      toast.success('Classification thresholds saved');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// ── Supplier scoring ────────────────────────────────────────────────────────

export function useSupplierScoring() {
  return useQuery({
    queryKey: SUPPLIER_KEY,
    queryFn: getSupplierScoring,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useSaveSupplierScoring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SupplierScoringWrite) => saveSupplierScoring(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SUPPLIER_KEY });
      toast.success('Supplier scoring saved');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// ── Planning mode (single global switch, S1) ────────────────────────────────

export function usePlanningMode() {
  return useQuery({
    queryKey: PLANNING_MODE_KEY,
    queryFn: getPlanningMode,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useSavePlanningMode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PlanningModeWrite) => savePlanningMode(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLANNING_MODE_KEY });
      toast.success('Planning mode saved - applies from the next run');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// ── Cover scope (where "use stock" may draw from) ───────────────────────────

export function useCoverScope() {
  return useQuery({
    queryKey: COVER_SCOPE_KEY,
    queryFn: getCoverScope,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useSaveCoverScope() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CoverScopeWrite) => saveCoverScope(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: COVER_SCOPE_KEY });
      toast.success('Cover setting saved');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// ── Fulfilment priority (single active `scm.priority_policy` row) ──────────

export function useFulfilmentPriority() {
  return useQuery({
    queryKey: FULFILMENT_PRIORITY_KEY,
    queryFn: getFulfilmentPriority,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useSaveFulfilmentPriority() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FulfilmentPriorityWrite) => saveFulfilmentPriority(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FULFILMENT_PRIORITY_KEY });
      toast.success('Fulfilment priority saved');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// ── Resolution preview ──────────────────────────────────────────────────────

export function useResolvePolicy() {
  return useMutation({
    mutationFn: ({ productId, warehouseCode }: { productId: string; warehouseCode: string | null }) =>
      resolvePolicy(productId, warehouseCode),
    onError: (e: Error) => toast.error(e.message),
  });
}

// ── Scope-target + preview pickers ──────────────────────────────────────────

export function useProductScopeOptions() {
  return useQuery({
    queryKey: ['scm', 'policies', 'opts', 'products'],
    queryFn: getProductScopeOptions,
    ...optionOpts,
  });
}

export function useClassScopeOptions() {
  return useQuery({
    queryKey: ['scm', 'policies', 'opts', 'classes'],
    queryFn: getClassScopeOptions,
    ...optionOpts,
  });
}

export function useWarehouseScopeOptions() {
  return useQuery({
    queryKey: ['scm', 'policies', 'opts', 'warehouses'],
    queryFn: getWarehouseScopeOptions,
    ...optionOpts,
  });
}
