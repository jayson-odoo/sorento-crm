'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  createLoadingPlan,
  deleteLoadingPlan,
  getContainerSizes,
  getFulfilmentSuppliers,
  getLoadingPlan,
  getLoadingPlans,
  getSupplierStock,
  getUnfinishedStock,
  updateLoadingPlan,
  type LoadingPlan,
  type LoadingPlanRequest,
} from '../services/fulfilmentService';

const KEY = ['scm', 'fulfilment'] as const;

const cold = { staleTime: 5 * 60_000, refetchOnWindowFocus: false, retry: 1 } as const;

export function useFulfilmentSuppliers() {
  return useQuery({ queryKey: [...KEY, 'suppliers'], queryFn: getFulfilmentSuppliers, ...cold });
}

export function useContainerSizes() {
  return useQuery({ queryKey: [...KEY, 'container-sizes'], queryFn: getContainerSizes, ...cold });
}

export function useSupplierStock(supplierId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'stock', supplierId],
    queryFn: () => getSupplierStock(supplierId as string),
    enabled: !!supplierId,
    refetchOnWindowFocus: false,
  });
}

export function useUnfinishedStock(supplierId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'unfinished', supplierId],
    queryFn: () => getUnfinishedStock(supplierId as string),
    enabled: !!supplierId,
    refetchOnWindowFocus: false,
  });
}

export function useLoadingPlans(supplierId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'plans', supplierId],
    queryFn: () => getLoadingPlans(supplierId ?? undefined),
    enabled: !!supplierId,
    refetchOnWindowFocus: false,
  });
}

export function useLoadingPlanDetail(planId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'plan', planId],
    queryFn: () => getLoadingPlan(planId as string),
    enabled: !!planId,
    refetchOnWindowFocus: false,
  });
}

/** Invalidate everything keyed on one supplier: a new snapshot changes every plan under it. */
function useSupplierInvalidator() {
  const qc = useQueryClient();
  return (supplierId: string | null) => {
    void qc.invalidateQueries({ queryKey: [...KEY, 'stock', supplierId] });
    void qc.invalidateQueries({ queryKey: [...KEY, 'unfinished', supplierId] });
    void qc.invalidateQueries({ queryKey: [...KEY, 'plans', supplierId] });
  };
}

export function useStockListApplied() {
  return useSupplierInvalidator();
}

export function useBuildLoadingPlan() {
  const invalidate = useSupplierInvalidator();
  return useMutation({
    mutationFn: (body: LoadingPlanRequest) => createLoadingPlan(body),
    onSuccess: (plan: LoadingPlan) => {
      invalidate(plan.supplier_id);
      toast.success(
        `Planned ${plan.planned_cbm.toLocaleString()} of ${plan.capacity_cbm.toLocaleString()} cbm.`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useRerunLoadingPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; container_count?: number; container_type?: string }) =>
      updateLoadingPlan(id, body),
    onSuccess: (plan: LoadingPlan) => {
      qc.setQueryData([...KEY, 'plan', plan.id], plan);
      void qc.invalidateQueries({ queryKey: [...KEY, 'plans', plan.supplier_id] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteLoadingPlan(supplierId: string | null) {
  const invalidate = useSupplierInvalidator();
  return useMutation({
    mutationFn: (id: string) => deleteLoadingPlan(id),
    onSuccess: () => {
      invalidate(supplierId);
      toast.success('Loading plan deleted.');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
