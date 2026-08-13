'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  approveLoadingPlan,
  createLoadingPlan,
  deleteLoadingPlan,
  getContainerSizes,
  getFulfilmentSuppliers,
  getLoadingPlan,
  getLoadingPlans,
  getPlanNotices,
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

/** S8 - the notices produced by approving a plan, and the one action that produces them. */
export function usePlanNotices(planId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'notices', planId],
    queryFn: () => getPlanNotices(planId as string),
    enabled: !!planId,
    refetchOnWindowFocus: false,
  });
}

export function useApproveLoadingPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => approveLoadingPlan(planId),
    onSuccess: (out, planId) => {
      qc.invalidateQueries({ queryKey: [...KEY, 'notices', planId] });
      // Say what actually happened per channel. "Notice sent" when the supplier has no address
      // on file would be the screen telling the user something untrue.
      const sent = out.notices.filter((n) => n.status === 'sent').length;
      if (sent) toast.success(`Notice sent on ${sent === 1 ? '1 channel' : `${sent} channels`}.`);
      else toast.warning('Notice created. No channel could send it, so send the document by hand.');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
